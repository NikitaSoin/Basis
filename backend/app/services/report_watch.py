"""Автообнаружение и разбор вышедших отчётов (Обозреватель, Направление 3 —
автопайплайн, дополняет earnings.py).

Разрыв, который закрывает этот модуль: earnings.py умеет РАЗОБРАТЬ отчёт
(LLM-дайджест по цифрам), но детектит выход отчёта ТОЛЬКО через ручное
обновление financials.json (report-fetcher/financial-analyst — Claude-
субагенты, оператор запускает вручную) — без этого шага новый отчёт молча
не попадает в разбор, даже если событие есть в календаре.

Здесь — независимый путь, без обращения к financials.json. ТРИ источника
детекта: MOEX ir-calendar (~76 тикеров, см. _due_ir_rows), Лента новостей
(любой тикер с деловым освещением, см. _due_news_reports), ГИР БО bo.nalog.gov.ru
(годовая РСБУ напрямую из госресурса — СТРУКТУРИРОВАННО, без LLM для цифр, см.
_due_girbo_reports; честно: только годовая, РСБУ юрлица не консолидация, банки/
МОЕХ отсутствуют — отчитываются перед ЦБ отдельно).
  ДЕТЕКТ  → calendar_events (event_type=earnings), не обработанные ранее
            (дедуп по calendar_event_id — см. миграцию d2b22f2662ba).
  ТЕКСТ   → каскад источников, по убыванию надёжности:
            1) market_updates (Лента новостей, уже LLM-очищенная выжимка,
               тикер уже размечен news_pipeline.py) — самый общий источник,
               покрывает практически любую компанию, у которой было
               освещение в деловых СМИ;
            2) СКРИН существенные факты (id=36) за окно вокруг даты события,
               по ИНН эмитента (см. calendar_events._load_inn_ticker_map) —
               те же категории «Решения СД»/«Раскрытие... отчёта», что уже
               используются для дивидендного календаря;
            3) АЗИПИ (e-disclosure.azipi.ru) — тот же шаблон Положения №714-П,
               доп. охват для эмитентов вне СКРИН/ПРАЙМ (см. _from_azipi);
            4) заголовок/описание самого календарного события — последний
               резерв, слабый (часто без цифр).
  🔴 Из 5 аккредитованных ЦБ агрегаторов (официальный список: cbr.ru/vfs/
     finmarkets/files/supervision/list_information_agency.xlsx) интегрированы
     СКРИН/ПРАЙМ/АЗИПИ — все три ДОСТУПНЫ без анти-бота (проверено вручную).
     e-disclosure.ru (Интерфакс, вероятно САМЫЙ полный агрегатор) — за
     полноценным JS-challenge (ServicePipe), это НЕ вопрос User-Agent —
     обычный HTTP-клиент его не проходит принципиально, нужен headless-браузер
     (доп. инфраструктура на проде) или платный обход — решение владельца, не
     подключено. АК&М (disclosure.ru) — не проверен подробно (низкий приоритет,
     старый сайт), точка расширения на будущее.
  ИЗВЛЕЧЕНИЕ → LLM (DeepSeek через app.services.llm), СТРОГО «null, если
            данных нет» — не выдумываем цифры. Финотчёт — headline-цифры +
            дайджест (переиспользует шаблон earnings.py._digest). Операционный
            релиз — короткие KPI-маркеры, без попытки впихнуть в P&L-схему.
  ХРАНЕНИЕ → earnings_reports/figures/digest — ТЕ ЖЕ таблицы, что у
            financials.json-пути (frontend не меняется); financials.json
            (вкладка «Финансы») НЕ трогаем — он остаётся выверенным аналитиком
            слоем, этот пайплайн — отдельный ознакомительный «лента событий».

Честная деградация: источник не нашёлся или в тексте нет цифр →
status="needs_source", разбор не публикуется. Не сканируем бесконечно одно и
то же событие: как только создана запись (любого статуса) с этим
calendar_event_id — повторно не трогаем (ручной ре-триггер — прямое удаление
записи, случай редкий).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.earnings import EarningsReport, EarningsFigures, EarningsDigest
from app.services import tinkoff_quotes
from app.services.earnings import _digest, _multiples  # переиспользуем прежний шаблон

logger = logging.getLogger(__name__)

_SKRIN_BASE = "https://disclosure.skrin.ru"
_WINDOW_DAYS = 5   # окно вокруг event_date, где ищем текст (публикация может отставать)
# 🔴 Найдено на бою 2026-07-12: тикер-тег (affected_tickers) СЛИШКОМ широкий фильтр —
# крупный банк вроде SBER попадает почти в любую новость про банковское регулирование
# (реформа банкротства, комиссии СБП и т.п.), а не только про свой отчёт. Без фильтра
# по ключевым словам первые 3 статьи по дате оказались НЕ об отчёте (реформа банкротства
# 07.07), хотя реальная «Сбер +20% по РСБУ» (09.07) в окне БЫЛА — просто позже по
# сортировке. Фильтр по ключевым словам обязателен, не только дата+тикер.
_REPORT_KEYWORDS_RE = re.compile(
    r"отч[её]т|результат|прибыл|выручк|мсфо|рсбу|финанс|дивиденд|ebitda|пассажиропоток|"
    r"добыч|производств|выпуск",
    re.IGNORECASE)


# ----------------------------- источник 0: собственный RSS компании (высший приоритет) -----------------------------
# Официальный первоисточник — когда есть, качественнее новостного пересказа: у Роснефти
# RSS пресс-релизов (rosneft.ru/press/releases/rss/) отдаёт ПОЛНУЮ таблицу цифр (выручка/
# EBITDA/прибыль/CapEx поквартально по МСФО) прямо в поле <yandex:full-text> — проверено
# вручную 2026-07-14. 🔴 НЕ универсально: параллельное агентское исследование 13 крупных
# компаний вне MOEX ir-calendar нашло такую ленту ТОЛЬКО у Татнефти (tatneft.ru/rss/ru,
# подтверждён живым HTTP 200 с прод-сервера — сам сайт недоступен из sandbox инструмента
# исследования, аналогично известной блокировке DeepSeek/FRED egress, см. память проекта).
# У остальных 11 — нет RSS/Atom/JSON API на предсказуемых путях (Лукойл/Новатэк/Сургут/
# Русал/НЛМК/АЛРОСА/Транснефть/Башнефть/ПИК/ВСМПО — проверено вручную и агентами). URL
# угадать нельзя (пробовали десяток типовых путей — не работает) — список пополняется
# ТОЛЬКО подтверждённым ручным/агентским обнаружением per-компания, не догадками.
_COMPANY_RSS = {
    "ROSN": "https://www.rosneft.ru/press/releases/rss/",
    "TATN": "https://www.tatneft.ru/rss/ru",
}


def _from_company_rss(ticker: str, event_date: date) -> str | None:
    import html as _html
    from email.utils import parsedate_to_datetime
    url = _COMPANY_RSS.get(ticker)
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=15, headers=_HTTP_UA, follow_redirects=True)
        r.raise_for_status()
        xml = r.text
    except Exception:  # noqa: BLE001
        return None
    lo, hi = event_date - timedelta(days=2), event_date + timedelta(days=_WINDOW_DAYS)
    for it in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title_m = re.search(r"<title>(.*?)</title>", it, re.S)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        if not title_m or not pub_m:
            continue
        title = _html.unescape(_html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title_m.group(1)))).strip()
        if not _REPORT_KEYWORDS_RE.search(title):
            continue
        try:
            pub_date = parsedate_to_datetime(pub_m.group(1)).date()
        except (TypeError, ValueError):
            continue
        if not (lo <= pub_date <= hi):
            continue
        ft_m = re.search(r"<yandex:full-text>(.*?)</yandex:full-text>", it, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", it, re.S)
        raw = (ft_m or desc_m).group(1) if (ft_m or desc_m) else ""
        # 🔴 двойное HTML-экранирование в этой ленте (&amp;laquo; вместо &laquo;) —
        # тот же паттерн, что у hh.ru (см. macro_hh_sync.py) — unescape дважды.
        raw = _html.unescape(_html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", raw)))
        return re.sub(r"\s+", " ", f"{title}\n{re.sub(r'<[^>]+>', ' ', raw)}")
    return None


# ----------------------------- источник 1: Лента новостей -----------------------------
def _from_market_updates(db: Session, ticker: str, event_date: date) -> str | None:
    from app.models.market import MarketUpdate
    lo = event_date - timedelta(days=1)
    hi = event_date + timedelta(days=_WINDOW_DAYS)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.affected_tickers.contains([ticker]),
                    MarketUpdate.published_at >= lo, MarketUpdate.published_at <= hi,
                    MarketUpdate.status == "published")
            .order_by(MarketUpdate.published_at.asc()).limit(20).all())
    if not rows:
        return None
    relevant = [r for r in rows if _REPORT_KEYWORDS_RE.search(f"{r.title} {r.summary or ''}")]
    picked = relevant[:3] if relevant else rows[:3]
    parts = []
    for r in picked:
        parts.append(f"{r.title}\n{r.summary or ''}\n{r.impact_comment or ''}".strip())
    return "\n\n---\n\n".join(parts)


# ----------------------------- источник 2: СКРИН существенные факты -----------------------------
_SKRIN_ROW_RE = re.compile(
    r"openFirmProf\('(\d+)'\);\">([^<]+)</a></span>&nbsp;&nbsp;"
    r"<span class=\"SkrinHref\" ><a  href='javascript:ShowMessage\((\d+),(\d+)\)'>([^<]+)</a>"
)
_SKRIN_RELEVANT = ("решения совета директоров", "решения общего собрания",
                  "решения единственного акционера", "раскрытие в сети интернет",
                  "раскрытие эмитентом ежеквартального отчета")


def _from_skrin(inn: str, event_date: date) -> str | None:
    if not inn:
        return None
    for delta in range(-1, _WINDOW_DAYS + 1):
        d = event_date + timedelta(days=delta)
        if d > date.today():
            continue
        try:
            r = httpx.get(f"{_SKRIN_BASE}/EventList.asp", params={"id": 36, "dt": f"{d.year}-{d.month}-{d.day}"},
                          timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            html = r.content.decode("cp1251", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        time.sleep(0.25)
        for row_inn, _name, eid, agency, title in _SKRIN_ROW_RE.findall(html):
            if row_inn != inn or not any(k in title.strip().lower() for k in _SKRIN_RELEVANT):
                continue
            try:
                mr = httpx.get(f"{_SKRIN_BASE}/printMessage.asp", params={"eid": eid, "Agency": agency},
                               timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                mr.raise_for_status()
                msg = re.sub(r"<[^>]+>", " ", mr.content.decode("cp1251", errors="replace"))
                return re.sub(r"\s+", " ", msg)
            except Exception:  # noqa: BLE001
                continue
    return None


# ----------------------------- источник 3: АЗИПИ (e-disclosure.azipi.ru) -----------------------------
# 5-й аккредитованный ЦБ агрегатор (официальный список: cbr.ru/vfs/finmarkets/files/
# supervision/list_information_agency.xlsx, сверено 2026-07-13 — код 2). Тот же типовой
# шаблон Положения №714-П, что у СКРИН/ПРАЙМ (проверено вручную на Роснефти) — но НЕТ
# кросс-компанийного дневного фида (в отличие от СКРИН `EventList.asp`), только поиск
# по ИНН → персональная страница эмитента → список сообщений на ОДНОЙ странице.
# Дороже по запросам (2 хода вместо 1), поэтому идёт ПОСЛЕ СКРИН в каскаде — доп. охват
# для эмитентов, которые публикуются здесь, а не (или не только) на СКРИН/ПРАЙМ.
_AZIPI_BASE = "https://e-disclosure.azipi.ru"
_HTTP_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _azipi_org_url(inn: str) -> str | None:
    try:
        r = httpx.get(f"{_AZIPI_BASE}/search/index.php",
                      params={"orgs": "Y", "ORG_INN": inn, "search_organization": "Поиск"},
                      timeout=15, headers=_HTTP_UA, follow_redirects=True)
        r.raise_for_status()
        m = re.search(r'href="(/organization/personal-pages/\d+/)"', r.text)
        return f"{_AZIPI_BASE}{m.group(1)}" if m else None
    except Exception:  # noqa: BLE001
        return None


def _from_azipi(inn: str, event_date: date) -> str | None:
    if not inn:
        return None
    org_url = _azipi_org_url(inn)
    if not org_url:
        return None
    try:
        r = httpx.get(org_url, timeout=15, headers=_HTTP_UA, follow_redirects=True)
        html = r.text
    except Exception:  # noqa: BLE001
        return None
    lo, hi = event_date - timedelta(days=1), event_date + timedelta(days=_WINDOW_DAYS)
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "/messages/" not in row:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 3:
            continue
        date_txt = re.sub(r"<[^>]+>", "", cells[0]).strip()
        try:
            d, mo, y = date_txt.split(".")
            row_date = date(int(y), int(mo), int(d))
        except ValueError:
            continue
        if not (lo <= row_date <= hi):
            continue
        title_l = re.sub(r"<[^>]+>", " ", cells[2]).strip().lower()
        if not any(k in title_l for k in _SKRIN_RELEVANT):  # те же категории Положения №714-П
            continue
        m = re.search(r'href="(/messages/\d+/)"', cells[2])
        if not m:
            continue
        try:
            mr = httpx.get(f"{_AZIPI_BASE}{m.group(1)}", timeout=15, headers=_HTTP_UA, follow_redirects=True)
            msg_html = re.sub(r"<script[^>]*>.*?</script>", " ", mr.text, flags=re.S)
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", msg_html))
        except Exception:  # noqa: BLE001
            continue
    return None


# ----------------------------- источник 4: ПРАЙМ (disclosure.1prime.ru) -----------------------------
# Был подключён ТОЛЬКО в дивидендный календарь (calendar_events.build_prime_disclosure,
# 14 хардкод-тикеров) — упущение report_watch не переиспользовал. Тот же шаблон
# Положения №714-П, тот же паттерн, что СКРИН/АЗИПИ (поиск по ИНН → таблица сообщений).
_PRIME_BASE = "https://disclosure.1prime.ru"


_PRIME_EVENT_DATE_RE = re.compile(
    r"Дата наступления события[^:]*:\s*(\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+\S+\s+\d{4})", re.IGNORECASE)


def _from_prime(inn: str, event_date: date) -> str | None:
    """🔴 Таблица ПРАЙМ: cells[0] — порядковый НОМЕР строки, НЕ дата (в отличие от
    СКРИН/АЗИПИ) — дату можно узнать только из содержимого самого сообщения (поле
    «Дата наступления события», тот же шаблон Положения №714-П). Фильтр по категории
    сначала (дёшево), дату проверяем ПОСЛЕ фетча содержимого (дороже, но иначе никак)."""
    if not inn:
        return None
    try:
        r = httpx.get(f"{_PRIME_BASE}/portal/default.aspx", params={"emId": inn}, timeout=15, headers=_HTTP_UA)
        r.raise_for_status()
        html = r.text
    except Exception:  # noqa: BLE001
        return None
    lo, hi = event_date - timedelta(days=1), event_date + timedelta(days=_WINDOW_DAYS)
    checked = 0
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "GetMessage" not in row or checked >= 10:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 2:
            continue
        title_l = re.sub(r"<[^>]+>", " ", cells[1]).strip().lower()
        if not any(k in title_l for k in _SKRIN_RELEVANT):
            continue
        gm = re.search(r"guid=(\{[0-9A-Fa-f-]+\})", row)
        if not gm:
            continue
        checked += 1
        try:
            mr = httpx.get(f"{_PRIME_BASE}/Portal/GetMessage.aspx", params={"emId": inn, "guid": gm.group(1)},
                           timeout=15, headers=_HTTP_UA)
            msg_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", mr.text))
        except Exception:  # noqa: BLE001
            continue
        dm = _PRIME_EVENT_DATE_RE.search(msg_text)
        msg_date = _parse_ru_date_str(dm.group(1)) if dm else None
        if msg_date and lo <= msg_date <= hi:
            return msg_text
    return None


def _parse_ru_date_str(s: str) -> date | None:
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})\s+(\S+)\s+(\d{4})", s)
    if m:
        d, mon_ru, y = m.groups()
        months = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
                  "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
        mo = months.get(mon_ru.lower())
        if mo:
            try:
                return date(int(y), mo, int(d))
            except ValueError:
                return None
    return None


def _source_text(db: Session, event: CalendarEvent, inn: str | None) -> tuple[str, str] | None:
    cr = _from_company_rss(event.ticker, event.event_date)
    if cr:
        return cr, "company_rss"
    mu = _from_market_updates(db, event.ticker, event.event_date)
    if mu:
        return mu, "market_updates"
    sk = _from_skrin(inn, event.event_date)
    if sk:
        return sk, "skrin_disclosure"
    pr = _from_prime(inn, event.event_date)
    if pr:
        return pr, "prime_disclosure"
    az = _from_azipi(inn, event.event_date)
    if az:
        return az, "azipi_disclosure"
    desc = (event.payload or {}).get("description") or ""
    fallback = f"{event.title}\n{desc}".strip()
    # заголовок без описания — почти никогда не содержит цифр, не считаем источником
    if desc:
        return fallback, "calendar_title"
    return None


# ----------------------------- извлечение цифр (LLM) -----------------------------
_FIN_SYS = (
    "Ты — финансовый аналитик-экстрактор. Из текста (новость/раскрытие информации) "
    "извлекаешь ТОЛЬКО те финансовые показатели компании, которые ЯВНО названы. "
    "ЗАПРЕЩЕНО придумывать или оценивать отсутствующие числа — если показателя нет "
    "в тексте, верни null. Числа — в млн ₽ (переведи из млрд/трлн, если нужно). "
    "Верни JSON."
)
_FIN_SPEC = (
    'Формат JSON: {"revenue": число|null, "revenue_yoy_pct": число|null, '
    '"ebitda": число|null, "ebitda_yoy_pct": число|null, '
    '"net_profit": число|null, "net_profit_yoy_pct": число|null, '
    '"net_debt": число|null, "has_figures": true|false}. '
    'has_figures=false, если в тексте нет ни одного числового финансового показателя.'
)


def _extract_financial(text_blob: str) -> dict | None:
    from app.services.llm import complete, LLMError
    try:
        res = complete(_FIN_SYS + "\n" + _FIN_SPEC, text_blob[:6000], json_mode=True,
                       max_tokens=600, temperature=0.1)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (финансы) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    return res


_OPS_SYS = (
    "Ты — финансовый редактор. Из текста (операционный релиз/новость о компании) "
    "извлекаешь КЛЮЧЕВЫЕ операционные показатели (натуральные объёмы: пассажиропоток, "
    "выпуск продукции, добыча, число клиентов и т.п. — НЕ финансовые ₽-показатели). "
    "ЗАПРЕЩЕНО придумывать числа. Тон фактический, без советов «купить/продать». Верни JSON."
)
_OPS_SPEC = (
    'Формат JSON: {"has_figures": true|false, "one_liner": "суть одной строкой (<=120 симв)", '
    '"kpis": ["маркеры с ✅/❌/❗️ — 2-5 пунктов, каждый с конкретным числом/%"], '
    '"summary": "1-2 фразы фактического резюме"}. '
    'has_figures=false, если в тексте нет ни одного конкретного числа/показателя.'
)


def _extract_operational(text_blob: str) -> dict | None:
    from app.services.llm import complete, LLMError
    try:
        res = complete(_OPS_SYS + "\n" + _OPS_SPEC, text_blob[:6000], json_mode=True,
                       max_tokens=700, temperature=0.2)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (операционка) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    return res


# ----------------------------- вспомогательное -----------------------------
def _period_label(event: CalendarEvent) -> str:
    m = re.search(r"за\s+(\d+М|\d+\s*кв(?:артал)?|\d{4}(?:\s*год)?)", event.title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return event.event_date.isoformat()


def _live_price(ticker: str, db: Session) -> tuple[float | None, float | None]:
    live = None
    try:
        if tinkoff_quotes.is_available():
            q = (tinkoff_quotes.get_all_prices() or {}).get(ticker)
            if q and q.get("price") is not None:
                live = float(q["price"])
    except Exception:  # noqa: BLE001
        pass
    row = db.execute(text("""
        SELECT q.close FROM quotes q JOIN companies c ON c.id=q.company_id
        WHERE c.ticker=:t AND q.close IS NOT NULL ORDER BY q.date DESC LIMIT 1
    """), {"t": ticker}).first()
    close = float(row.close) if row else None
    return live, close


def _store_report(db: Session, report: EarningsReport, company: Company, text_blob: str | None,
                  is_operational: bool, price_now: float | None, mcap: float | None,
                  fig_override: dict | None = None) -> str:
    """Общее ядро сохранения — используется MOEX-путём (process_event), news-путём
    (process_news_item) и ГИР БО-путём (process_girbo_report). `report` уже
    сконструирован (не добавлен в сессию), text_blob=None означает «источник не
    нашёлся вовсе». fig_override — готовые цифры (ГИР БО, структурированный источник,
    без LLM-угадывания) в ТОМ ЖЕ формате, что возвращает _extract_financial — если
    задан, LLM-экстракция чисел пропускается (цифры уже точные, из госресурса)."""
    if fig_override is None and not text_blob:
        db.add(report); db.commit()
        return "needs_source"
    if is_operational:
        opd = _extract_operational(text_blob)
        if not opd:
            db.add(report); db.commit()
            return "needs_source"
        db.add(report); db.flush()
        db.add(EarningsFigures(report_id=report.id, extracted_fields=opd))
        db.add(EarningsDigest(
            report_id=report.id, headline=f"{company.name}: {report.period}",
            one_liner=opd.get("one_liner"), what_report_showed=opd.get("kpis"),
            summary=opd.get("summary"), importance="medium", model_used="deepseek"))
        report.status = "processed"
        db.commit()
        return "created"
    fig_raw = fig_override if fig_override is not None else _extract_financial(text_blob)
    if not fig_raw:
        db.add(report); db.commit()
        return "needs_source"

    def _prev(cur, yoy):
        if cur is None or yoy is None or yoy == -100:
            return None
        try:
            return round(cur / (1 + yoy / 100), 2)
        except ZeroDivisionError:
            return None
    fig = {
        "ticker": report.ticker, "name": company.name, "sector": company.sector,
        "period": report.period, "standard": report.standard, "unit": "млн",
        "revenue": fig_raw.get("revenue"), "revenue_prev": _prev(fig_raw.get("revenue"), fig_raw.get("revenue_yoy_pct")),
        "ebitda": fig_raw.get("ebitda"), "ebitda_prev": _prev(fig_raw.get("ebitda"), fig_raw.get("ebitda_yoy_pct")),
        "net_profit": fig_raw.get("net_profit"), "net_profit_prev": _prev(fig_raw.get("net_profit"), fig_raw.get("net_profit_yoy_pct")),
        "net_debt": fig_raw.get("net_debt"), "adjusted_profit": None, "is_company_adjusted": False,
    }
    mult = _multiples(fig, price_now, mcap)
    digest = _digest(fig, mult)
    db.add(report); db.flush()
    db.add(EarningsFigures(
        report_id=report.id, revenue_ttm=fig.get("revenue"), ebitda=fig.get("ebitda"),
        net_profit_ttm=fig.get("net_profit"), net_debt=fig.get("net_debt"),
        nd_ebitda=mult.get("nd_ebitda"), price=mult.get("price"), market_cap=mult.get("market_cap"),
        pe_ttm=mult.get("pe_ttm"), pb=mult.get("pb"), ev_ebitda=mult.get("ev_ebitda"),
        is_company_adjusted=False,
        prev={"revenue": fig.get("revenue_prev"), "ebitda": fig.get("ebitda_prev"),
              "net_profit": fig.get("net_profit_prev")},
        extracted_fields=fig_raw))
    if digest:
        db.add(EarningsDigest(
            report_id=report.id, headline=digest.get("headline"), one_liner=digest.get("one_liner"),
            metrics_snapshot=mult, what_report_showed=digest.get("what_report_showed"),
            what_changed=digest.get("what_changed"), summary=digest.get("summary"),
            importance=digest.get("importance"), model_used="deepseek"))
        report.status = "processed"
    else:
        report.status = "extract_failed"
    db.commit()
    return "created"


def process_event(db: Session, event: CalendarEvent, company: Company, market_cap: float | None,
                  inn_map: dict[str, list[str]]) -> str:
    """Обработать одно календарное earnings-событие (MOEX ir-calendar-путь, ~76
    тикеров). Идемпотентно — дедуп по calendar_event_id."""
    if db.query(EarningsReport).filter_by(calendar_event_id=event.id).first():
        return "exists"
    inn = next((i for i, tickers in inn_map.items() if event.ticker in tickers), None)
    src = _source_text(db, event, inn)
    standard = event.status  # уже нормализовано build_ir_calendar/_classify_report_kind
    is_operational = bool(standard and "операцион" in standard.lower())
    report_type = "operating" if is_operational else (
        "annual" if re.search(r"\bгод(?:а)?\b", event.title, re.IGNORECASE)
        and not re.search(r"\d+\s*(?:М|кв)", event.title, re.IGNORECASE) else "quarter")
    report = EarningsReport(
        ticker=event.ticker, period=_period_label(event), standard=standard,
        report_type=report_type, published_at=event.event_date,
        source="report_watch", source_url=event.source_url,
        status="needs_source", calendar_event_id=event.id)
    if src:
        report.source = src[1]
    live, close = _live_price(event.ticker, db)
    price_now = live or close
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    return _store_report(db, report, company, src[0] if src else None, is_operational, price_now, mcap)


def process_news_item(db: Session, item: dict, company: Company, market_cap: float | None) -> str:
    """Обработать одну статью Ленты новостей, детектированную как отчёт/операционный
    релиз (см. _due_news_reports) — покрывает ЛЮБУЮ компанию с новостным освещением,
    не только ~76 тикеров MOEX ir-calendar. Идемпотентно — дедуп по market_update_id.
    Доп. защита от дублей с MOEX-путём: если для этого тикера уже есть отчёт с
    published_at в пределах недели — считаем то же самое событие, пропускаем."""
    mu_id = item["market_update_id"]
    if db.query(EarningsReport).filter_by(market_update_id=mu_id).first():
        return "exists"
    ticker = item["ticker"]
    pub_date = item["published_at"]
    nearby = (db.query(EarningsReport)
              .filter(EarningsReport.ticker == ticker,
                      EarningsReport.published_at.isnot(None),
                      EarningsReport.published_at >= pub_date - timedelta(days=4),
                      EarningsReport.published_at <= pub_date + timedelta(days=4))
              .first())
    if nearby:
        return "exists"  # то же событие уже накрыто MOEX-путём (process_event)
    text_blob = f"{item['title']}\n{item.get('summary') or ''}\n{item.get('impact_comment') or ''}".strip()
    blob_l = text_blob.lower()
    # 🔴 Найдено на бою 2026-07-14: явный финансовый стандарт (МСФО/РСБУ) должен
    # ПЕРЕВЕШИВАТЬ операционные ключевые слова — релиз Роснефти «РЕЗУЛЬТАТЫ... ПО МСФО»
    # содержит «ДОБЫЧА» как попутный контекст, но это финотчёт с выручкой/EBITDA/прибылью
    # в тексте; без приоритета is_operational=True уводил его в operational-путь и терял
    # реальные финансовые цифры, которые были прямо в тексте.
    has_fin_standard = "мсфо" in blob_l or "рсбу" in blob_l
    is_operational = not has_fin_standard and any(
        k in blob_l for k in ("операцион", "пассажиропоток", "добыч", "производств", "выпуск"))
    standard = "МСФО" if "мсфо" in blob_l else "РСБУ" if "рсбу" in blob_l else (
        "операционные результаты" if is_operational else "отчётность")
    m = re.search(r"за\s+(\d+М|\d+\s*кв(?:артал)?|\d{4}(?:\s*год)?|первое полугодие|полугодии)",
                 text_blob, re.IGNORECASE)
    period = m.group(1).strip() if m else pub_date.isoformat()
    report_type = "operating" if is_operational else (
        "annual" if re.search(r"\bгод(?:а)?\b", text_blob, re.IGNORECASE)
        and not re.search(r"\d+\s*(?:М|кв)", text_blob, re.IGNORECASE) else "quarter")
    report = EarningsReport(
        ticker=ticker, period=period, standard=standard, report_type=report_type,
        published_at=pub_date, source="market_updates", source_url=None,
        status="needs_source", market_update_id=mu_id)
    live, close = _live_price(ticker, db)
    price_now = live or close
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    try:
        return _store_report(db, report, company, text_blob, is_operational, price_now, mcap)
    except IntegrityError:
        # (ticker, period, standard) уже занято другим путём — тот же реальный отчёт.
        db.rollback()
        return "exists"


def _due_company_rss_reports(days_back: int) -> list[dict]:
    """Прямой обход _COMPANY_RSS (не через MOEX ir-calendar — ROSN/TATN в него НЕ входят,
    calendar-путь их никогда не увидит). Дёшево: всего 2 тикера сейчас, по одному
    HTTP-запросу на ленту."""
    out = []
    today = date.today()
    for ticker in _COMPANY_RSS:
        text_blob = _from_company_rss(ticker, today - timedelta(days=days_back // 2))
        if text_blob:
            out.append({"ticker": ticker, "text": text_blob})
    return out


def process_company_rss_item(db: Session, item: dict, company: Company, market_cap: float | None) -> str:
    """Обработать одну статью из собственного RSS компании (см. _COMPANY_RSS) —
    первоисточник, качественнее новостного пересказа. Дедуп — (ticker, period,
    standard) constraint + защита от дублей с другими путями по близости даты
    (та же логика, что process_news_item)."""
    ticker = item["ticker"]
    text_blob = item["text"]
    blob_l = text_blob.lower()
    # 🔴 Найдено на бою 2026-07-14: явный финансовый стандарт (МСФО/РСБУ) должен
    # ПЕРЕВЕШИВАТЬ операционные ключевые слова — релиз Роснефти «РЕЗУЛЬТАТЫ... ПО МСФО»
    # содержит «ДОБЫЧА» как попутный контекст, но это финотчёт с выручкой/EBITDA/прибылью
    # в тексте; без приоритета is_operational=True уводил его в operational-путь и терял
    # реальные финансовые цифры, которые были прямо в тексте.
    has_fin_standard = "мсфо" in blob_l or "рсбу" in blob_l
    is_operational = not has_fin_standard and any(
        k in blob_l for k in ("операцион", "пассажиропоток", "добыч", "производств", "выпуск"))
    standard = "МСФО" if "мсфо" in blob_l else "РСБУ" if "рсбу" in blob_l else (
        "операционные результаты" if is_operational else "отчётность")
    m = re.search(r"за\s+(\d+\s*кв(?:артал)?\.?|\d+\s*мес\.?|\d{4}(?:\s*г(?:од)?)?|1 пол\.?|полугодие)",
                 text_blob, re.IGNORECASE)
    period = m.group(1).strip() if m else date.today().isoformat()
    report_type = "operating" if is_operational else (
        "annual" if re.search(r"\bгод", text_blob, re.IGNORECASE) and "кв" not in blob_l else "quarter")
    if db.query(EarningsReport).filter_by(ticker=ticker, period=period, standard=standard).first():
        return "exists"
    report = EarningsReport(
        ticker=ticker, period=period, standard=standard, report_type=report_type,
        published_at=date.today(), source="company_rss", source_url=_COMPANY_RSS.get(ticker),
        status="needs_source")
    live, close = _live_price(ticker, db)
    price_now = live or close
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    try:
        return _store_report(db, report, company, text_blob, is_operational, price_now, mcap)
    except IntegrityError:
        db.rollback()
        return "exists"


# ----------------------------- ГИР БО (bo.nalog.gov.ru) — годовая РСБУ-отчётность -----------------------------
# Государственный ресурс ФНС (обязательная сдача годовой бухотчётности по 402-ФЗ) — НЕ
# один из 5 ЦБ-аккредитованных агрегаторов раскрытия, отдельная система. Проверено вручную
# 2026-07-13: чистый JSON без анти-бота (`advanced-search/organizations/search` →
# `nbo/organizations/{id}/bfo/`). ГЛАВНОЕ ПРЕИМУЩЕСТВО — цифры приходят СТРУКТУРИРОВАННО
# (стандартные коды форм 0710001 баланс / 0710002 P&L), точность гарантирована
# источником, LLM здесь НЕ извлекает числа (только пишет дайджест по готовым цифрам,
# как и раньше через _digest).
# 🔴 Честные ограничения: (1) ТОЛЬКО годовая отчётность, нет квартальной/промежуточной;
# (2) РСБУ отдельного юрлица, НЕ консолидированная МСФО группы — для холдингов может
# отличаться от группы; (3) банки/НФО и биржа (СБЕР/ВТБ/Т-Банк/MOEX — проверено)
# ОТСУТСТВУЮТ — отчитываются перед ЦБ по другому регламенту, не через ФНС; (4) отдельные
# компании (Роснефть — проверено вручную) отсутствуют по неясной причине (вероятно
# освобождение от публичного раскрытия для части санкционных эмитентов) — не все 261
# тикера будут найдены. Единицы измерения на сайте — ТЫСЯЧИ ₽, у нас конвенция млн ₽ —
# делим на 1000.
_GIRBO_BASE = "https://bo.nalog.gov.ru"


def _girbo_org_id(inn: str) -> int | None:
    try:
        r = httpx.get(f"{_GIRBO_BASE}/advanced-search/organizations/search",
                      params={"query": inn, "page": 0, "size": 5}, timeout=15, headers=_HTTP_UA)
        r.raise_for_status()
        content = r.json().get("content") or []
        return content[0]["id"] if content else None
    except Exception:  # noqa: BLE001
        return None


def _girbo_annual_reports(org_id: int) -> list[dict]:
    try:
        r = httpx.get(f"{_GIRBO_BASE}/nbo/organizations/{org_id}/bfo/", timeout=20, headers=_HTTP_UA)
        r.raise_for_status()
        return r.json() or []
    except Exception:  # noqa: BLE001
        return []


def _girbo_figures(entry: dict) -> dict | None:
    """Headline-цифры из структурированной формы — БЕЗ LLM. Та же форма (revenue/
    revenue_yoy_pct/...), что возвращает _extract_financial, чтобы _store_report
    работал одинаково для обоих путей."""
    try:
        corr = entry["typeCorrections"][0]["correction"]
    except (KeyError, IndexError, TypeError):
        return None
    bal, pnl = corr.get("balance") or {}, corr.get("financialResult") or {}

    def cur(d, code):
        v = d.get(f"current{code}")
        return float(v) / 1000 if v is not None else None  # тыс. ₽ -> млн ₽

    def prev(d, code):
        v = d.get(f"previous{code}")
        return float(v) / 1000 if v is not None else None

    def yoy(c, p):
        if c is None or not p:
            return None
        return round((c - p) / abs(p) * 100, 1)
    revenue, revenue_prev = cur(pnl, 2110), prev(pnl, 2110)
    net_profit, net_profit_prev = cur(pnl, 2400), prev(pnl, 2400)
    if revenue is None and net_profit is None:
        return None
    ltl, stl, cash = cur(bal, 1410) or 0, cur(bal, 1510) or 0, cur(bal, 1250) or 0
    return {
        "has_figures": True,
        "revenue": revenue, "revenue_yoy_pct": yoy(revenue, revenue_prev),
        "net_profit": net_profit, "net_profit_yoy_pct": yoy(net_profit, net_profit_prev),
        "ebitda": None, "ebitda_yoy_pct": None,  # ГИР БО не даёт EBITDA — не прикидываем
        "net_debt": (ltl + stl - cash) if (ltl or stl or cash) else None,
    }


def process_girbo_report(db: Session, ticker: str, inn: str, company: Company,
                         market_cap: float | None, org_id: int, entry: dict) -> str:
    """Обработать один годовой отчёт ГИР БО. Дедуп — обычный (ticker, period,
    standard) constraint earnings_reports (standard-метка уникальна для этого пути,
    не пересекается с МСФО/обычной «РСБУ» из других источников)."""
    period = str(entry.get("period") or "")
    if not period:
        return "needs_source"
    if db.query(EarningsReport).filter_by(ticker=ticker, period=period, standard="РСБУ (ГИР БО)").first():
        return "exists"
    fig_raw = _girbo_figures(entry)
    published_at = None
    if entry.get("actualBfoDate"):
        try:
            published_at = date.fromisoformat(entry["actualBfoDate"][:10])
        except ValueError:
            pass
    report = EarningsReport(
        ticker=ticker, period=period, standard="РСБУ (ГИР БО)", report_type="annual",
        published_at=published_at, source="girbo",
        source_url=f"{_GIRBO_BASE}/organizations-card/{org_id}",
        status="needs_source")
    if not fig_raw:
        db.add(report); db.commit()
        return "needs_source"
    live, close = _live_price(ticker, db)
    price_now = live or close
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    return _store_report(db, report, company, None, False, price_now, mcap, fig_override=fig_raw)


def _due_girbo_reports(companies: dict, inn_by_ticker: dict[str, str]) -> list[dict]:
    """Обходит компании с известным ИНН, ищет в ГИР БО. Не найден в ГИР БО (банк/МОЕХ/
    санкционное освобождение и т.п.) — тихо пропускаем, это честное ограничение
    источника, не ошибка."""
    out = []
    for ticker, inn in inn_by_ticker.items():
        if ticker not in companies or not inn:
            continue
        org_id = _girbo_org_id(inn)
        time.sleep(0.15)
        if not org_id:
            continue
        reports = _girbo_annual_reports(org_id)
        time.sleep(0.15)
        if not reports:
            continue
        latest = max(reports, key=lambda r: r.get("period") or "")
        out.append({"ticker": ticker, "inn": inn, "org_id": org_id, "entry": latest})
    return out


_MOEX_IR_CALENDAR = "https://iss.moex.com/iss/cci/calendars/ir-calendar.json"


def _due_ir_rows(companies: dict, days_back: int) -> list[dict]:
    """Прямой опрос MOEX ir-calendar (НЕ через calendar_events!) за отчётные события с
    event_date в [today-days_back, today] — уже ДОЛЖНЫ были выйти.
    🔴 calendar_events хранит ТОЛЬКО форвард (build_ir_calendar сам фильтрует
    `event_date < today: continue` — витрина календаря показывает только предстоящее,
    прошлое туда никогда не попадает). Проверено локально 2026-07-12: 0 earnings-строк
    с event_date <= today в calendar_events, при этом У САМОГО MOEX прошлые даты ЕСТЬ
    (AFLT: записи с 2024 года) — значит слепая зона именно в НАШЕЙ форвард-фильтрации,
    не в источнике. Поэтому детект report_watch идёт мимо calendar_events, напрямую
    к MOEX, с собственным окном [today-days_back, today]."""
    today = date.today()
    lo = today - timedelta(days=days_back)
    try:
        r = httpx.get(_MOEX_IR_CALENDAR, params={"limit": "max"}, timeout=30)
        r.raise_for_status()
        block = (r.json() or {}).get("cci_ir_calendar") or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("report_watch: MOEX ir-calendar недоступен: %s", type(e).__name__)
        return []
    cols = block.get("columns") or []
    rows = block.get("data") or []
    if not cols or not rows:
        return []
    idx = {c: i for i, c in enumerate(cols)}
    out = []
    for row in rows:
        if row[idx["event_type_name"]] != "Публикация отчетности":
            continue
        secid = row[idx["secid"]]
        if secid not in companies:
            continue
        raw_date = row[idx["event_date"]]
        if not raw_date:
            continue
        try:
            ev_date = date.fromisoformat(raw_date[:10])
        except (TypeError, ValueError):
            continue
        if not (lo <= ev_date <= today):
            continue
        out.append({
            "secid": secid, "event_date": ev_date, "event_id": row[idx["event_id"]],
            "description": (row[idx["event_description"]] or "").strip(),
            "event_link": row[idx["event_link"]],
        })
    return out


def _get_or_create_calendar_event(db: Session, row: dict, company: Company) -> CalendarEvent:
    """Служебная запись calendar_events под уже ПРОШЕДШЕЕ MOEX-событие (форвард-витрина
    build_ir_calendar такие не хранит — см. _due_ir_rows) — нужна только как якорь
    дедупа earnings_reports.calendar_event_id, на публичный /market/calendar не влияет
    (event_type тот же 'earnings', но дата в прошлом — витрина и так их не показывает)."""
    from app.services.calendar_events import _upsert, _classify_report_kind
    dedup_key = f"ir_calendar_past:{row['secid']}:{row['event_id']}"
    existing = db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()
    if existing:
        return existing
    status = _classify_report_kind(row["description"])
    _upsert(db, [{
        "event_type": "earnings", "event_date": row["event_date"], "event_time": None,
        "ticker": row["secid"], "sector": company.sector,
        "title": f"{company.name}: {row['description']}"[:300], "status": status,
        "source": "moex_ir_calendar", "source_url": row["event_link"] or "",
        "payload": {"subtype": "report", "confidence": "public_aggregated", "description": row["description"][:500]},
        "dedup_key": dedup_key,
    }])
    return db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()


def _due_news_reports(db: Session, companies: dict, days_back: int) -> list[dict]:
    """Сканирует Ленту новостей ПРЯМО (в обход MOEX ir-calendar) на статьи о вышедшей
    отчётности/операционке — покрывает ЛЮБУЮ компанию с новостным освещением (все
    ~261, не только 76 из MOEX ir-calendar). Один market_updates.id может дать
    несколько строк (статья упоминает несколько тикеров — напр. секторный обзор) —
    это нормально, process_news_item дедупит по (ticker, published_at±4д)."""
    from app.models.market import MarketUpdate
    from datetime import datetime, timezone
    lo = datetime.combine(date.today() - timedelta(days=days_back), datetime.min.time(), tzinfo=timezone.utc)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.status == "published", MarketUpdate.published_at >= lo).all())
    out = []
    for r in rows:
        blob = f"{r.title} {r.summary or ''}"
        if not _REPORT_KEYWORDS_RE.search(blob):
            continue
        for t in (r.affected_tickers or []):
            if t in companies:
                out.append({"market_update_id": r.id, "ticker": t, "published_at": r.published_at.date(),
                            "title": r.title, "summary": r.summary, "impact_comment": r.impact_comment})
    return out


def refresh(db: Session, days_back: int = 5, run_girbo: bool = True) -> dict:
    """Ежедневный обход, ТРИ независимых пути обнаружения:
    1) MOEX ir-calendar «Публикация отчетности» (~76/261 эмитентов с публичным
       IR-календарём) — даёт точную ожидаемую дату вперёд, для остальных источник
       просто не покрывает (честное ограничение, см. _due_ir_rows).
    2) Прямой скан Ленты новостей по ключевым словам отчётности (см.
       _due_news_reports) — покрывает ЛЮБУЮ компанию с освещением в деловых СМИ,
       не привязан к тому, есть ли у эмитента публичный IR-календарь. Дедуп против
       пути (1) — по близости published_at (см. process_news_item).
    3) ГИР БО (bo.nalog.gov.ru) — годовая РСБУ-отчётность напрямую из госресурса,
       СТРУКТУРИРОВАННО (без LLM-угадывания цифр). Полный обход ~261 тикеров
       (2 запроса на тикер) — дороже путей 1-2, поэтому run_girbo=False для быстрых
       интерактивных debug-триггеров (по умолчанию True для суточного крона)."""
    from app.services.calendar_events import _load_inn_ticker_map
    companies = {c.ticker: c for c in db.query(Company).all()}
    inn_map = _load_inn_ticker_map()
    res = {"created": 0, "needs_source": 0, "exists": 0, "errors": 0, "skipped_no_company": 0}

    due_rows = _due_ir_rows(companies, days_back)
    for row in due_rows:
        company = companies.get(row["secid"])
        if not company:
            res["skipped_no_company"] += 1
            continue
        try:
            event = _get_or_create_calendar_event(db, row, company)
            r = process_event(db, event, company, float(company.market_cap) if company.market_cap else None, inn_map)
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("report_watch: ошибка по событию (ir) %s/%s: %s", row["secid"], row["event_id"], type(e).__name__)
            res["errors"] += 1
            db.rollback()

    news_items = _due_news_reports(db, companies, days_back)
    for item in news_items:
        company = companies.get(item["ticker"])
        if not company:
            res["skipped_no_company"] += 1
            continue
        try:
            r = process_news_item(db, item, company, float(company.market_cap) if company.market_cap else None)
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("report_watch: ошибка по новости %s/%s: %s", item["ticker"], item["market_update_id"], type(e).__name__)
            res["errors"] += 1
            db.rollback()

    girbo_items = []
    if run_girbo:
        inn_by_ticker = {}
        for inn, tickers in inn_map.items():
            for t in tickers:
                inn_by_ticker.setdefault(t, inn)
        girbo_items = _due_girbo_reports(companies, inn_by_ticker)
        for item in girbo_items:
            company = companies.get(item["ticker"])
            if not company:
                res["skipped_no_company"] += 1
                continue
            try:
                r = process_girbo_report(db, item["ticker"], item["inn"], company,
                                         float(company.market_cap) if company.market_cap else None,
                                         item["org_id"], item["entry"])
                res[r] = res.get(r, 0) + 1
            except IntegrityError:
                db.rollback()
                res["exists"] += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("report_watch: ошибка ГИР БО %s: %s", item["ticker"], type(e).__name__)
                res["errors"] += 1
                db.rollback()

    rss_items = _due_company_rss_reports(days_back)
    for item in rss_items:
        company = companies.get(item["ticker"])
        if not company:
            res["skipped_no_company"] += 1
            continue
        try:
            r = process_company_rss_item(db, item, company, float(company.market_cap) if company.market_cap else None)
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("report_watch: ошибка company_rss %s: %s", item["ticker"], type(e).__name__)
            res["errors"] += 1
            db.rollback()

    logger.info("report_watch: %s (ir-событий: %d, новостных кандидатов: %d, ГИР БО: %d, company_rss: %d)",
                res, len(due_rows), len(news_items), len(girbo_items), len(rss_items))
    return res
