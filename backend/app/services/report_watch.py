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

import html as _html
import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.earnings import EarningsReport, EarningsFigures, EarningsDigest
from app.services import tinkoff_quotes
from app.services.agent_web import fetch_document
from app.services.earnings import _digest, _multiples  # переиспользуем прежний шаблон

logger = logging.getLogger(__name__)

_SKRIN_BASE = "https://disclosure.skrin.ru"
_WINDOW_DAYS = 5   # окно вокруг event_date, где ищем текст (публикация может отставать)
# 🔴 Найдено на бою 2026-07-28 (жалоба владельца: «отчёт POSI вышел, а разбора нет»):
# calendar_event существовал, событие обработалось В ДЕНЬ публикации, но суточный крон
# report_watch (20:45 МСК) проверил Ленту НОВОСТЕЙ ДО того, как там появилась статья
# про сам отчёт (та вышла через несколько часов) — источник не нашёлся, легла запись
# needs_source, а докстринг этого модуля («повторно не трогаем, ручной ре-триггер —
# случай редкий») не даёт ей шанса на самоисцеление на следующих суточных прогонах.
# Для крупных/заметных эмитентов такая гонка НЕ редкость — новость может выйти в
# любое время суток, а прогон один раз в день. Фикс: на КАЖДОМ следующем суточном
# прогоне, пока needs_source-запись моложе этого окна, пробуем источник ЗАНОВО (см.
# _stale_needs_source) — если источник нашёлся, старая запись удаляется и создаётся
# новая обработанная взамен. Старше окна — не трогаем: даём странице «отчёт не вышел»
# (corporate_news.py, _MISSING_GRACE_DAYS=7) честно сработать, не устраиваем вечный
# опрос по-настоящему не вышедших отчётов.
_RETRY_WINDOW_DAYS = 5
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

# 🔴 ДЕТЕКТ ≠ РАНЖИРОВАНИЕ (найдено на бою 2026-07-25, жалоба владельца «в Отчётах
# мусорные новости»): _REPORT_KEYWORDS_RE выше задуман как РАНЖИРУЮЩИЙ (что ближе к
# началу пула текстов в _from_market_updates — см. комментарий там), но
# _due_news_reports использовал его как ЕДИНСТВЕННЫЙ фильтр детекта «новость = отчёт»
# — и «дивиденд»/«производств»/«добыч»/«финанс» пропускали в Отчёты что угодно:
# «СД рекомендовал дивиденды», «Добыча газа в РФ», «Производство пива в РФ»,
# «Индекс снизился из-за дивидендных отсечек». Хуже того — мусорная запись потом
# БЛОКИРОВАЛА реальный отчёт через дедуп ±4 дня (кейс НОВАТЭКа: «Добыча газа в РФ»
# 22.07 не пустила настоящий МСФО-отчёт 24.07). Для детекта — СТРОГИЙ паттерн:
# только формулировки, которыми деловые СМИ анонсируют именно вышедшую отчётность.
_NEWS_REPORT_DETECT_RE = re.compile(
    r"отчита|отч[её]тность|финансовые результаты|операционные результаты|"
    r"результаты (?:за|по) |мсфо|рсбу|чистая прибыль|чистый убыток|ebitda",
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
            .order_by(MarketUpdate.published_at.asc()).limit(30).all())
    if not rows:
        return None
    # 🔴 Найдено на бою 2026-07-14: жёсткий keyword-фильтр ПОЛНОСТЬЮ вытеснял генуинно
    # релевантные статьи без точного слова из списка — реальная новость «Мосбиржа
    # зафиксировала рекорд... на денежном рынке» (без слов «отчёт»/«результат» и т.п.)
    # была отброшена в пользу ложного срабатывания на «финанс» в НЕсвязанной новости про
    # регулирование геймификации (тикер-тег MOEX тоже туда попал — банки/биржа широко
    # упоминаются в регуляторных новостях). Теперь keyword — РАНЖИРОВАНИЕ (что ближе к
    # началу текста), НЕ исключающий фильтр — берём более широкий пул, keyword-совпадения
    # первыми, но НЕ выбрасываем остальное: пусть LLM-экстракция сама решит по has_figures.
    def _relevance(r):
        matched = bool(_REPORT_KEYWORDS_RE.search(f"{r.title} {r.summary or ''}"))
        dist = abs((r.published_at.date() - event_date).days)
        return (0 if matched else 1, dist)
    picked = sorted(rows, key=_relevance)[:6]
    parts = []
    for r in picked:
        parts.append(f"{r.title}\n{r.summary or ''}\n{r.impact_comment or ''}".strip())
    # 🔴 Выжимка ленты — 2-4 предложения на новость, и СМИ в них чаще всего называет
    # ОДНО число («прибыль выросла вдвое»). Разбор по такому обрывку честно выходил
    # без выручки/EBITDA/GMV — «нет данных» писал сам дайджест (владелец 2026-07-30,
    # кейс Ozon: прибыль есть, остального нет, хотя в полном релизе всё было).
    # Полные тексты статей в БД не храним намеренно (только summary + ссылка) —
    # поэтому здесь ДОТЯГИВАЕМ полный текст по source_url; не вышло — работаем по
    # выжимке, как раньше (честная деградация).
    #
    # Для фетча — СВОЙ порядок, не общий _relevance: в день отчёта у крупной
    # компании в ленте до 30 смежных новостей («риски БПЛА», «отменил звонок»),
    # и общий keyword («отчитался о мерах») выносил их в топ. Числа релиза несут
    # заголовки с прибылью/выручкой/EBITDA/GMV — их тянем первыми, до 4 статей,
    # и останавливаемся, как только собрали достаточно полного текста.
    fin_kw = re.compile(r"прибыл|убыт|выручк|ebitda|oibda|gmv|результат", re.I)
    fetch_order = sorted(picked, key=lambda r: (0 if fin_kw.search(r.title or "") else 1))
    full_parts = []
    for r in fetch_order[:6]:
        if len(full_parts) >= 4:
            break
        full = _fetch_article_text(r.source_url)
        if full:
            full_parts.append(f"[ПОЛНЫЙ ТЕКСТ] {r.title}\n{full}")
    # 🔴 Полные тексты — В НАЧАЛО блоба: экстрактор режет вход ([:12000]), и когда
    # полные статьи стояли ПОСЛЕ шести выжимок, числа Коммерсанта оказывались за
    # линией отреза — третья причина «нет выручки» в кейсе Ozon (2026-07-31).
    return "\n\n---\n\n".join(full_parts + parts)


_ARTICLE_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _fetch_article_text(url: str | None, limit: int = 7000) -> str | None:
    """Полный текст статьи по URL новости. Один GET с браузерным UA и коротким
    таймаутом; из HTML берём абзацы <p> (обвязка/меню при склейке тегов в текст
    дают в основном короткие строки — отфильтровываются порогом длины)."""
    if not url or not url.startswith("http"):
        return None
    try:
        r = httpx.Client(timeout=12, headers={"User-Agent": _ARTICLE_UA},
                         follow_redirects=True).get(url)
        r.raise_for_status()
        html_text = r.text
    except Exception as e:  # noqa: BLE001
        logger.info("report_watch: полный текст %s недоступен (%s)", url[:60], type(e).__name__)
        return None
    # 🔴 script/style/noscript — ДО извлечения абзацев: у Коммерсанта инлайн-скрипты
    # (window.kommersantAnalytics = {...}) попадали внутрь захвата, проходили фильтр
    # длины и при лимите вытесняли реальный текст статьи (найдено 2026-07-31 через
    # /debug/fetch-article: head ответа был чистым JS). Тот же приём, что в
    # macro_cb_sync._fetch_text.
    html_text = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ",
                       html_text, flags=re.S | re.I)
    html_text = re.sub(r"<!--.*?-->", " ", html_text, flags=re.S)
    def _clean_lines(fragment: str) -> list[str]:
        out = []
        for raw_line in fragment.split("\n"):
            t = _html.unescape(re.sub(r"\s+", " ", raw_line)).strip()
            # навигация/подписи короче 60 символов — режем; остатки кода (фигурные
            # скобки, window./function) — не текст статьи
            if len(t) >= 60 and not re.search(r"[{}]|window\.|function\s*\(", t) \
                    and re.search(r"[.,]", t):
                out.append(t)
        return out

    paras = re.findall(r"<p[^>]*>(.*?)</p>", html_text, re.S | re.I)
    chunks = []
    for p in paras:
        chunks.extend(_clean_lines(re.sub(r"<[^>]+>", " ", p)))
    text_out = "\n".join(chunks)[:limit]
    if len(text_out) >= 300:
        return text_out
    # Фолбэк для страниц, где текст НЕ в <p> (smart-lab держит тело поста в div):
    # зачистка всех тегов с переносами по блочным элементам + те же фильтры строк.
    rough = re.sub(r"<(?:br|/p|/div|/li|/h\d|/tr)[^>]*>", "\n", html_text, flags=re.I)
    rough = re.sub(r"<[^>]+>", " ", rough)
    text_out = "\n".join(_clean_lines(rough))[:limit]
    return text_out if len(text_out) >= 300 else None


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
    '"net_debt": число|null, '
    '"extra_metrics": [{"name": "название показателя как в тексте (GMV, OIBDA, '
    'скорр. EBITDA, FCF, процентный доход, выручка сегмента и т.п.)", '
    '"value": "значение С ЕДИНИЦЕЙ как в тексте (напр. 780,6 млрд ₽ или 28,5 млн)", '
    '"yoy_pct": число|null}] — до 4 показателей, которые компания САМА выделяет в '
    'релизе сверх выручки/EBITDA/прибыли (у Ozon это GMV, у банка — процентный/'
    'комиссионный доход, у телекома — OIBDA); нет таких — пустой список, '
    '"has_figures": true|false, "is_company_report": true|false}. '
    'has_figures=false, если в тексте нет ни одного числового финансового показателя. '
    'is_company_report=true ТОЛЬКО если текст — корпоративная отчётность/релиз/'
    'результаты ИМЕННО названной компании; false — если это отраслевая, страновая '
    'или общерыночная новость (напр. «добыча газа в РФ», «производство в отрасли», '
    '«индекс снизился»), даже если компания в ней упоминается. Рыночные дайджесты '
    'и обзоры дня («рынок акций вырос, акции компании X +10%») — тоже false: движение '
    'котировок компании внутри обзора рынка НЕ является её отчётностью.'
)


def _extract_financial(text_blob: str, company_name: str | None = None) -> dict | None:
    from app.services.llm import complete, LLMError
    # Гейт релевантности живёт В ТОМ ЖЕ вызове экстракции (не отдельный LLM-запрос):
    # цифры «есть» и в отраслевой статистике («Производство лекарств в РФ выросло на
    # 13,9%») — has_figures сам по себе мусор не отсекает (найдено на бою 2026-07-25).
    user = (f"КОМПАНИЯ, по которой ищем отчётность: {company_name}\n\n{text_blob[:12000]}"
            if company_name else text_blob[:12000])
    try:
        res = complete(_FIN_SYS + "\n" + _FIN_SPEC, user, json_mode=True,
                       max_tokens=600, temperature=0.1)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (финансы) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    if company_name and res.get("is_company_report") is False:
        logger.info("report_watch: текст отклонён гейтом релевантности (%s, финансы)", company_name)
        return None
    return res


_OPS_SYS = (
    "Ты — финансовый редактор. Из текста (операционный релиз/новость о компании) "
    "извлекаешь КЛЮЧЕВЫЕ операционные показатели (натуральные объёмы: пассажиропоток, "
    "выпуск продукции, добыча, число клиентов и т.п. — НЕ финансовые ₽-показатели). "
    "ЗАПРЕЩЕНО придумывать числа. Тон фактический, без советов «купить/продать». Верни JSON."
)
_OPS_SPEC = (
    'Формат JSON: {"has_figures": true|false, "is_company_report": true|false, '
    '"one_liner": "суть одной строкой (<=120 симв)", '
    '"kpis": ["маркеры с ✅/❌/❗️ — 2-5 пунктов, каждый с конкретным числом/%"], '
    '"summary": "1-2 фразы фактического резюме"}. '
    'has_figures=false, если в тексте нет ни одного конкретного числа/показателя. '
    'is_company_report=true ТОЛЬКО если текст — операционный релиз/результаты ИМЕННО '
    'названной компании; false — если это отраслевая/страновая/рыночная статистика '
    '(напр. «добыча газа в РФ», «производство пива в России»), даже если компания '
    'в тексте упоминается.'
)


def _extract_operational(text_blob: str, company_name: str | None = None) -> dict | None:
    from app.services.llm import complete, LLMError
    # См. комментарий в _extract_financial — гейт релевантности в том же вызове.
    user = (f"КОМПАНИЯ, по которой ищем операционный релиз: {company_name}\n\n{text_blob[:6000]}"
            if company_name else text_blob[:6000])
    try:
        res = complete(_OPS_SYS + "\n" + _OPS_SPEC, user, json_mode=True,
                       max_tokens=700, temperature=0.2)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (операционка) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    if company_name and res.get("is_company_report") is False:
        logger.info("report_watch: текст отклонён гейтом релевантности (%s, операционка)", company_name)
        return None
    return res


# ----------------------------- богатый разбор (когда есть реальный текст) -----------------------------
# Владелец, 2026-07-23: «Отчёты» в Обозревателе ощущались беднее «Разбора документа по
# ссылке» у ассистента — хотя это ОДНА И ТА ЖЕ модель (app.services.llm). Разница была не
# в модели, а в том, что видит модель: _digest() всегда получает 4 сжатых числа
# (_extract_financial), даже когда text_blob здесь на руках содержит куда больше (полный
# RSS-текст пресс-релиза, текст раскрытия СКРИН/ПРАЙМ/АЗИПИ) — richness текста терялась
# до того, как модель его видела. _digest_rich — тот же принцип, что
# document_analyst.analyze_document (см. этот файл): модель получает ВЕСЬ текст источника
# + уже проверенные цифры как опору, не только числа.
_RICH_SYS = (
    "Ты — финансовый аналитик Basis (не брокер, без «купить/продать» и целевых цен). "
    "Тебе даны: ТЕКСТ источника о вышедшей отчётности компании (пресс-релиз/раскрытие/"
    "новость), точные извлечённые headline-цифры (проверенная основа — НЕ выдумывай "
    "новые числа сверх текста) и КОНТЕКСТ ПЛАТФОРМЫ (ставка ЦБ, показатели компании из "
    "нашей карточки). Разбери СОДЕРЖАТЕЛЬНО, как это делает сильный независимый "
    "аналитик: не «выросло/упало», а ПОЧЕМУ (драйверы: цены, объёмы, курс, ставка, "
    "разовые статьи), КАК результат ложится в текущий рыночный контекст и ЗА ЧЕМ "
    "СЛЕДИТЬ дальше (катализаторы: дивидендное решение, гайденс, следующий отчёт, "
    "долговая нагрузка при текущей ставке). Комментарии менеджмента, сегменты, "
    "качество прибыли (разовые vs операционные) — обязательно, если есть в тексте. "
    "Прогнозов цен и рекомендаций НЕ давать; «что дальше» — только наблюдаемые "
    "события и условия («если X, то Y»), не предсказания. Тон фактический, "
    "нейтральный, независимый. Верни JSON."
)
_RICH_SPEC = (
    'Формат JSON: {"headline": "шапка: Компания (ТИКЕР) · период, стандарт", '
    '"one_liner": "одна строка сути (<=120 симв)", '
    '"highlights": ["конкретный факт/тезис ИЗ ТЕКСТА, не только цифра — до 5 пунктов"], '
    '"risks_or_caveats": ["на что обратить внимание / оговорки — до 5 пунктов"], '
    '"data_gaps": "чего в тексте не хватает для полной картины, коротко (или null)", '
    '"what_changed": "что изменилось vs прошлый период — по тексту и цифрам (1-3 фразы)", '
    '"market_context": "как результат ложится в текущий контекст (ставка, сектор, курс, '
    'спрос) — 1-3 фразы ПО ДАННЫМ контекста платформы и текста, без выдумок (или null)", '
    '"watch_next": ["за чем следить дальше: конкретное наблюдаемое событие/условие '
    '(дивидендная рекомендация, гайденс, следующий отчёт, рефинансирование долга) — '
    'до 3 пунктов, БЕЗ рекомендаций и целевых цен"], '
    '"summary": "2-4 фразы фактического резюме без советов", '
    '"importance": "high|medium|low"}'
)


def _platform_context(db: Session, ticker: str) -> dict:
    """Компактный контекст ПЛАТФОРМЫ для глубокого разбора: ставка ЦБ + ключевые
    числа карточки компании. Только уже посчитанное — никакой новой аналитики;
    любой сбой → пустой словарь (разбор не должен падать из-за контекста)."""
    ctx: dict = {}
    try:
        row = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='key_rate' "
            "AND metric='level' ORDER BY as_of DESC LIMIT 1")).first()
        if row:
            ctx["key_rate_pct"] = float(row[0])
        row = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='inflation' "
            "AND metric='yoy' ORDER BY as_of DESC LIMIT 1")).first()
        if row:
            ctx["inflation_yoy_pct"] = float(row[0])
    except Exception:  # noqa: BLE001
        pass
    try:
        import json as _json
        from pathlib import Path
        fp = Path(__file__).parent.parent.parent / "companies" / ticker.upper() / "financials.json"
        if fp.exists():
            fin = _json.loads(fp.read_text(encoding="utf-8"))
            meta = fin.get("meta") or {}
            bs = fin.get("balance_sheet") or {}
            gov_fp = fp.parent / "governance.json"
            ctx["company"] = {
                "sector": meta.get("sector"),
                "nd_ebitda_last": (lambda a: a[-1] if isinstance(a, list) and a else a)(
                    (bs.get("ratios") or {}).get("net_debt_ebitda")),
                "data_flags": (fin.get("data_flags") or [])[:2] or None,
            }
            if gov_fp.exists():
                dv = (_json.loads(gov_fp.read_text(encoding="utf-8")).get("dividends") or {})
                ctx["company"]["dividend_policy"] = dv.get("policy_text")
    except Exception:  # noqa: BLE001
        pass
    return ctx


def _digest_rich(text_blob: str, fig: dict, mult: dict, platform_ctx: dict | None = None) -> dict | None:
    """Как _digest(), но модель видит РЕАЛЬНЫЙ ТЕКСТ источника целиком (до 8000 симв.),
    не только 4 сжатых числа — вызывается вместо _digest() всюду, где text_blob достаточно
    содержателен (см. _store_report). Возвращает None при сбое LLM — вызывающий код
    деградирует на узкий _digest()."""
    from app.services.llm import complete, LLMError
    def chg(cur, prev):
        if cur is None or prev in (None, 0):
            return None
        return round((cur - prev) / abs(prev) * 100, 1)
    figures_ctx = {
        "company": fig.get("name"), "ticker": fig["ticker"], "period": fig["period"],
        "standard": fig.get("standard"),
        "revenue": fig.get("revenue"), "revenue_yoy_pct": chg(fig.get("revenue"), fig.get("revenue_prev")),
        "ebitda": fig.get("ebitda"), "ebitda_yoy_pct": chg(fig.get("ebitda"), fig.get("ebitda_prev")),
        "net_profit": fig.get("net_profit"), "net_profit_yoy_pct": chg(fig.get("net_profit"), fig.get("net_profit_prev")),
        "net_debt": fig.get("net_debt"), "nd_ebitda": mult.get("nd_ebitda"),
        "pe_ttm": mult.get("pe_ttm"), "pb": mult.get("pb"), "ev_ebitda": mult.get("ev_ebitda"),
    }
    ctx_part = (f"\n\nКОНТЕКСТ ПЛАТФОРМЫ (ставка/инфляция/карточка компании):\n"
                f"{json.dumps(platform_ctx, ensure_ascii=False)}" if platform_ctx else "")
    user = (f"ИЗВЛЕЧЁННЫЕ ЦИФРЫ (проверенные, используй как основу):\n"
            f"{json.dumps(figures_ctx, ensure_ascii=False)}{ctx_part}"
            f"\n\n=== ТЕКСТ ИСТОЧНИКА ===\n{text_blob[:12000]}")
    try:
        res = complete(_RICH_SYS + "\n" + _RICH_SPEC, user, json_mode=True, max_tokens=1500, temperature=0.2)
        return res if isinstance(res, dict) else None
    except LLMError as e:
        logger.warning("Богатый разбор отчёта %s: LLM недоступен: %s", fig["ticker"], e)
        return None


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
    # 🔴 Найдено на бою 2026-07-14: is_operational решается ДО того, как виден реальный
    # текст (по общей метке календаря вроде «отчётность», не по содержимому) — событие
    # MOEX классифицировалось как «финансовое», а реальный текст оказался про объём
    # торгов/число клиентов (операционные метрики, не revenue/EBITDA/прибыль) —
    # _extract_financial честно говорил has_figures=false, событие терялось. Теперь при
    # неудаче ПЕРВОГО типа (по классификации) пробуем ВТОРОЙ — реальное содержимое решает,
    # не предварительный ярлык. fig_override (ГИР БО, гарантированно финансовый
    # структурированный источник) — без пробы, доверяем классификации как раньше.
    if fig_override is None and text_blob:
        opd = _extract_operational(text_blob, company.name) if is_operational else None
        fig_raw = None if is_operational else _extract_financial(text_blob, company.name)
        if is_operational and not opd:
            fig_raw = _extract_financial(text_blob, company.name)
        elif not is_operational and not fig_raw:
            opd = _extract_operational(text_blob, company.name)
        if opd:
            # 🔴 Найдено на бою 2026-07-28 (жалоба владельца, кейс GMKN): фоллбэк на
            # операционный разбор МЕНЯЕТ, какой экстрактор реально сработал, но не
            # чинил report.standard/report_type, заданные заранее по (возможно
            # неверной) классификации ДО того, как виден текст — GMKN сохранился с
            # standard="МСФО" при чисто операционном содержимом (объёмы производства
            # металлов, ни одной финансовой цифры). Раз в БД реально лёг операционный
            # дайджест — ярлык должен соответствовать содержимому, а не догадке.
            report.standard = "операционные результаты"
            report.report_type = "operating"
            db.add(report); db.flush()
            db.add(EarningsFigures(report_id=report.id, extracted_fields=opd))
            db.add(EarningsDigest(
                report_id=report.id, headline=f"{company.name}: {report.period}",
                one_liner=opd.get("one_liner"), what_report_showed=opd.get("kpis"),
                summary=opd.get("summary"), importance="medium", model_used="deepseek"))
            report.status = "processed"
            db.commit()
            return "created"
        if is_operational and fig_raw:
            # Зеркальный случай: изначально классифицировали как операционный релиз
            # (report.standard="операционные результаты"), но реально сохраняем
            # финансовые цифры (fig_raw) — текст не содержал явного «МСФО»/«РСБУ»
            # (иначе has_fin_standard не пустил бы is_operational=True с самого
            # начала), поэтому честный ярлык — общее «отчётность», а не оставшееся
            # от неверной догадки «операционные результаты».
            report.standard = "отчётность"
            report.report_type = "quarter" if report.report_type == "operating" else report.report_type
    else:
        fig_raw = fig_override
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
    # Богатый разбор, когда на руках реальный текст источника (не просто заголовок
    # календаря) — модель видит текст целиком, не только 4 сжатых числа. Порог 150
    # символов отсекает тривиальные обрывки (типовой calendar_title-фолбэк без
    # description); при неудаче LLM/пустом ответе — честная деградация на _digest().
    digest = (_digest_rich(text_blob, fig, mult, platform_ctx=_platform_context(db, fig["ticker"]))
              if text_blob and len(text_blob) >= 150 else None)
    if not digest:
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
        # market_context/watch_next — внутри metrics_snapshot (JSONB), НЕ отдельными
        # колонками: в migrations/versions СЕЙЧАС 4 alembic-головы, `alembic upgrade
        # head` на бою при multiple heads падает (Dockerfile глотает ошибку «…failed —
        # continuing»), т.е. новая миграция МОЛЧА не применилась бы и колонок на бою
        # не было бы. Починка голов — отдельная задача (см. журнал 2026-07-30).
        db.add(EarningsDigest(
            report_id=report.id, headline=digest.get("headline"), one_liner=digest.get("one_liner"),
            metrics_snapshot={**(mult or {}),
                              "market_context": digest.get("market_context"),
                              "watch_next": digest.get("watch_next")},
            what_report_showed=digest.get("what_report_showed"),
            highlights=digest.get("highlights"), risks_or_caveats=digest.get("risks_or_caveats"),
            data_gaps=digest.get("data_gaps"),
            what_changed=digest.get("what_changed"), summary=digest.get("summary"),
            importance=digest.get("importance"), model_used="deepseek"))
        report.status = "processed"
    else:
        report.status = "extract_failed"
    db.commit()
    return "created"


def _classify_standard(headline: str, blob_l: str) -> tuple[str, bool]:
    """Различить МСФО/РСБУ/операционные результаты/отчётность по тексту.
    🔴 Найдено на бою 2026-07-28 (жалоба владельца, кейс ГАЗПРОМ): наивный
    порядок «МСФО, иначе РСБУ» по всему телу текста ломается, когда статья
    упоминает ОБА стандарта — реальный текст: заголовок и цифры «Чистая
    прибыль... по РСБУ», но попутно поясняется, что дивиденды считаются по
    МСФО ("Отчётность по РСБУ, а не по МСФО" — так LLM же и написал в risks,
    а standard всё равно сохранился как "МСФО", потому что "мсфо" тоже
    встретилось где-то в тексте). Заголовок почти всегда точно называет,
    ЧЬИ ИМЕННО цифры несёт это конкретное событие — если там указан только
    один стандарт, доверяем ему; на оба сразу в заголовке (редкость) —
    fallback на старую логику по всему блобу."""
    headline_l = headline.lower()
    has_fin_standard = "мсфо" in blob_l or "рсбу" in blob_l
    is_operational = not has_fin_standard and any(
        k in blob_l for k in ("операцион", "пассажиропоток", "добыч", "производств", "выпуск"))
    if "рсбу" in headline_l and "мсфо" not in headline_l:
        standard = "РСБУ"
    elif "мсфо" in headline_l and "рсбу" not in headline_l:
        standard = "МСФО"
    else:
        standard = "МСФО" if "мсфо" in blob_l else "РСБУ" if "рсбу" in blob_l else (
            "операционные результаты" if is_operational else "отчётность")
    return standard, is_operational


def _stale_needs_source(existing: EarningsReport) -> bool:
    """True — существующая needs_source-запись ещё в окне ретрая (см.
    _RETRY_WINDOW_DAYS), стоит удалить и попробовать источник заново. Записи
    ЛЮБОГО другого статуса (processed/extract_failed) — не трогаем, они не
    ждут повторной попытки."""
    if existing.status != "needs_source":
        return False
    age = datetime.now(timezone.utc) - existing.created_at
    return age <= timedelta(days=_RETRY_WINDOW_DAYS)


def process_event(db: Session, event: CalendarEvent, company: Company, market_cap: float | None,
                  inn_map: dict[str, list[str]]) -> str:
    """Обработать одно календарное earnings-событие (MOEX ir-calendar-путь, ~76
    тикеров). Идемпотентно — дедуп по calendar_event_id, кроме свежих
    needs_source (см. _stale_needs_source) — им даём повторную попытку найти
    источник на следующем суточном прогоне."""
    existing = db.query(EarningsReport).filter_by(calendar_event_id=event.id).first()
    if existing:
        if not _stale_needs_source(existing):
            return "exists"
        db.delete(existing)
        db.commit()
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
    existing_mu = db.query(EarningsReport).filter_by(market_update_id=mu_id).first()
    if existing_mu:
        if not _stale_needs_source(existing_mu):
            return "exists"
        db.delete(existing_mu)
        db.commit()
    ticker = item["ticker"]
    pub_date = item["published_at"]
    text_blob = f"{item['title']}\n{item.get('summary') or ''}\n{item.get('impact_comment') or ''}".strip()
    # Заголовочный blob фиксируем ДО обогащения полным текстом — период отчёта
    # и report_type определяются по НЕМУ (заголовок新ости практически всегда несёт
    # период: «за первое полугодие», «за 1П 2026»), а не по полному тексту статьи:
    # на перепрогоне 2026-07-26 период MAGN определился как «2025 год» — парсер
    # зацепил «за 2025 год» из СЕРЕДИНЫ статьи (сравнение с прошлым годом), а не
    # реальный период отчёта.
    headline_blob = text_blob
    # 🔴 Обогащение — ОБЩИМ каскадом _from_market_updates, не только СВОЕЙ новостью.
    # Четвёртая (последняя) причина «нет выручки» в кейсе Ozon (2026-07-31): триггером
    # news-пути становится ПЕРВАЯ по времени подходящая заметка дня («отчитался о
    # мерах по рискам», 06:48), а статья с цифрами (Ъ, 07:32) — отдельная запись
    # ленты, и прежний код качал полный текст только новости-триггера. Каскад же
    # собирает ДО 6 новостей тикера в окне, тянет до 4 полных текстов с приоритетом
    # финансовых заголовков (прибыль/выручка/EBITDA/GMV) и ставит их в начало блоба.
    # Деградация прежняя: каскад пуст → полный текст своей новости → голая выжимка.
    enriched = _from_market_updates(db, ticker, pub_date)
    if enriched and len(enriched) > len(text_blob) + 200:
        text_blob = enriched
    elif item.get("source_url"):
        full = fetch_document(item["source_url"], max_chars=10000)
        if not full.get("error") and (full.get("chars") or 0) > len(text_blob) + 200:
            text_blob = f"{text_blob}\n\n=== ПОЛНЫЙ ТЕКСТ ИСТОЧНИКА ===\n{full['text']}"
    blob_l = text_blob.lower()
    nearby = (db.query(EarningsReport)
              .filter(EarningsReport.ticker == ticker,
                      EarningsReport.published_at.isnot(None),
                      EarningsReport.published_at >= pub_date - timedelta(days=4),
                      EarningsReport.published_at <= pub_date + timedelta(days=4))
              .first())
    if nearby:
        # 🔴 Найдено на бою 2026-07-29 (жалоба владельца — Сбер/Яндекс отчёты весь
        # день не разбирались, «у всех уже всё разобрано, у нас пусто»): ПУСТАЯ
        # needs_source-заглушка (из более раннего тика крона, ещё до того, как
        # новость реально вышла) блокировала ЛЮБОЙ более поздний, содержательный
        # кандидат через этот же дедуп ±4 дня — новая статья с реальными цифрами
        # получала "exists" против записи без единой цифры внутри. Свежую (см.
        # _stale_needs_source) заглушку удаляем и даём кандидату шанс создать
        # НАСТОЯЩУЮ запись — не ждём следующего тика крона, как раньше.
        if _stale_needs_source(nearby):
            db.delete(nearby)
            db.commit()
        else:
            # 🔴 Дедуп ±4 дня НЕ должен считать операционную/мусорную запись эквивалентом
            # ФИНАНСОВОГО отчёта (найдено на бою 2026-07-25): у НОВАТЭКа запись
            # «операционные результаты» от 22.07 (на деле — мусор от общестрановой
            # новости «Добыча газа в РФ») заблокировала настоящий МСФО-отчёт от 24.07;
            # у Северстали smart-lab-запись «операционные результаты» блокировала
            # МСФО-версию. Если новый кандидат несёт явный финансовый стандарт
            # (МСФО/РСБУ), а существующая рядом запись — НЕ финансовая, пропускаем его
            # дальше: страховка от реального дубля остаётся на уникальном индексе
            # (ticker, period, standard) — IntegrityError ниже.
            cand_is_financial = "мсфо" in blob_l or "рсбу" in blob_l
            nearby_is_financial = (nearby.standard or "").upper() in ("МСФО", "РСБУ")
            if not (cand_is_financial and not nearby_is_financial):
                return "exists"  # то же событие уже накрыто MOEX-путём (process_event)
    # Классификация стандарта/операционности — см. _classify_standard (МСФО/РСБУ
    # по заголовку в приоритете; операционные ключевые слова только если явного
    # финансового стандарта нигде нет — см. докстринг функции, кейсы Роснефти и
    # ГАЗПРОМа).
    standard, is_operational = _classify_standard(headline_blob, blob_l)
    # Период — ТОЛЬКО из заголовка (headline_blob), не из полного текста статьи
    # (см. комментарий выше). Паттерн расширен: «в первом полугодии» / «за 1П» /
    # «в I полугодии» — реальный заголовок Северстали «Прибыль... снизилась на 89%
    # в первом полугодии» раньше не матчился (требовался предлог «за») и период
    # падал в сырую дату публикации.
    m = re.search(r"(?:за|в)\s+(\d+М|\d+\s*кв(?:артал)?[а-я]*|\d{4}(?:\s*год)?|"
                  r"перво[ем]\s+полугоди[ие]|I\s+полугоди[ие]|1П\s*\d{4}|полугодии)",
                  headline_blob, re.IGNORECASE)
    period = m.group(1).strip() if m else pub_date.isoformat()
    # Нормализация: «первом полугодии»/«I полугодии» → «1П<год публикации>» —
    # единый вид с остальными путями (и уникальный индекс (ticker, period,
    # standard) начинает реально дедупить одинаковые полугодия).
    if re.match(r"(?:перво|I\s)", period, re.IGNORECASE):
        period = f"1П{pub_date.year}"
    report_type = "operating" if is_operational else (
        "annual" if re.search(r"\bгод(?:а)?\b", headline_blob, re.IGNORECASE)
        and not re.search(r"\d+\s*(?:М|кв|П)", headline_blob, re.IGNORECASE) else "quarter")
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
    # Классификация — см. _classify_standard; заголовок здесь заменяет первая
    # строка RSS-текста (нет отдельного title/summary, как у Ленты новостей).
    standard, is_operational = _classify_standard(text_blob.split("\n", 1)[0], blob_l)
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


def ingest_agent_source(db: Session, ticker: str, text_blob: str, source_url: str | None,
                        period: str | None, standard: str | None) -> dict:
    """Приём ПОЛНОГО текста отчётного релиза от АГЕНТА-ДОБЫТЧИКА (владелец 2026-07-31:
    «report-fetcher же как-то добывает всё без проблем» — тот же класс агента, но по
    расписанию: облачный агент ищет релиз там, куда curl с прод-сервера не проходит
    (IR-сайты за анти-ботами, зеркала, полные статьи), и POST-ит текст сюда).

    Дальше — РОВНО текущий конвейер (_store_report: экстракция цифр → _digest_rich с
    контекстом платформы): агент только добывает, анализирует прод. Существующая
    свежая запись тикера ЗАМЕНЯЕТСЯ, только если новая получилась содержательнее
    (есть digest и добыто больше цифр) — агент не может ухудшить карточку."""
    ticker = ticker.upper()
    company = db.query(Company).filter(Company.ticker == ticker).first()
    if company is None:
        return {"error": f"компания {ticker} не найдена"}
    if not text_blob or len(text_blob) < 300:
        return {"error": "text слишком короткий (<300 символов)"}

    per = (period or "").strip()
    if not per:
        m = re.search(r"за\s+(\d+\s*кв(?:артал)?\.?|\d+\s*мес\.?|\d{4}(?:\s*г(?:од)?)?|"
                      r"1 пол\.?|полугодие)", text_blob, re.IGNORECASE)
        per = m.group(1).strip() if m else date.today().isoformat()
    std = (standard or "").strip() or ("МСФО" if re.search(r"МСФО|IFRS", text_blob, re.I)
                                      else "отчётность")
    report_type = "annual" if re.search(r"\bгод", per, re.I) else "quarter"

    # 🔴 ГЕЙТ «НЕ УХУДШАЙ» (найдено на бою 2026-07-31: добытчик заменил полноценный
    # разбор Ozon записью со смартлаб-поста и кривыми ярлыками — прежний код удалял
    # ВСЕ свежие записи тикера, хотя докстринг обещал замену «только если
    # содержательнее»). Правило: processed-запись С ВЫРУЧКОЙ — неприкосновенна;
    # если такая есть, добыча завершает работу чисткой пустых дублей, ничего не
    # создавая. Под замену идут только слабые записи (needs_source / без выручки).
    olds = (db.query(EarningsReport)
            .filter(EarningsReport.ticker == ticker,
                    EarningsReport.published_at.isnot(None),
                    EarningsReport.published_at >= date.today() - timedelta(days=10)).all())
    good = [r for r in olds
            if r.status == "processed" and r.figures is not None
            and r.figures.revenue_ttm is not None]
    weak = [r for r in olds if r not in good]
    for r in weak:
        db.delete(r)
    db.commit()
    if good:
        return {"result": "kept_better", "kept_period": good[0].period,
                "deleted_weak": len(weak)}

    report = EarningsReport(
        ticker=ticker, period=per, standard=std, report_type=report_type,
        published_at=date.today(), source="agent_fetcher", source_url=source_url,
        status="needs_source")
    live, close = _live_price(ticker, db)
    price_now = live or close
    mcap = None
    row = db.execute(text("SELECT market_cap FROM companies WHERE ticker=:t"), {"t": ticker}).first()
    if row and row[0]:
        mcap = float(row[0])
    try:
        res = _store_report(db, report, company, text_blob, False, price_now, mcap)
    except IntegrityError:
        db.rollback()
        return {"error": "integrity (дубль period/standard)"}
    return {"result": res, "period": per, "standard": std, "deleted_weak": len(weak)}


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


def _get_or_create_calendar_event(db: Session, row: dict, company: Company,
                                  source: str = "moex_ir_calendar", key_prefix: str = "ir_calendar_past",
                                  confidence: str = "public_aggregated") -> CalendarEvent:
    """Служебная запись calendar_events под уже ПРОШЕДШЕЕ событие (форвард-витрина
    build_ir_calendar/build_corporate такие не хранит — см. _due_ir_rows/_due_smartlab_rows)
    — нужна только как якорь дедупа earnings_reports.calendar_event_id, на публичный
    /market/calendar не влияет (событие в прошлом — витрина и так их не показывает).
    Параметризовано по источнику — переиспользуется и MOEX-, и smart-lab-путём."""
    from app.services.calendar_events import _upsert, _classify_report_kind
    dedup_key = f"{key_prefix}:{row['secid']}:{row['event_id']}"
    existing = db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()
    if existing:
        return existing
    status = _classify_report_kind(row["description"])
    _upsert(db, [{
        "event_type": "earnings", "event_date": row["event_date"], "event_time": None,
        "ticker": row["secid"], "sector": company.sector,
        "title": f"{company.name}: {row['description']}"[:300], "status": status,
        "source": source, "source_url": row["event_link"] or "",
        "payload": {"subtype": "report", "confidence": confidence, "description": row["description"][:500]},
        "dedup_key": dedup_key,
    }])
    return db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()


# ----------------------------- smart-lab (детект дат, НЕ данные) -----------------------------
# Владелец одобрил 2026-07-14: разрешено ТОЛЬКО для дат/детекта («в этот день у компании X
# вышел отчёт») + как крайний резерв текста, если свои методы (RSS компании/Лента новостей/
# СКРИН/ПРАЙМ/АЗИПИ/ГИР БО) ничего не нашли — прежний запрет («не тянуть с конкурента»)
# был конкретно про ДИВИДЕНДНЫЕ СУММЫ (см. чекпойнт дивидендного календаря 2026-07-12),
# остаётся в силе для того сценария. Здесь используем ТОЛЬКО факт даты + расширяем детект
# заметно за пределы 76 тикеров MOEX ir-calendar (smart-lab, в отличие от нашей витрины,
# реально хранит историю — проверено вручную: `from_{прошлая дата}` отдаёт события, а не 404).
_SMARTLAB_CAL = "https://smart-lab.ru/calendar/stocks/"


def _due_smartlab_rows(companies: dict, days_back: int, max_pages: int = 3) -> list[dict]:
    from app.services.calendar_events import _classify_corp
    today = date.today()
    start_str = (today - timedelta(days=days_back)).strftime("%d.%m.%Y")
    html_pages = []
    for page_n in range(1, max_pages + 1):
        url = f"{_SMARTLAB_CAL}from_{start_str}/" + (f"page{page_n}/" if page_n > 1 else "")
        try:
            r = httpx.get(url, timeout=20, headers=_HTTP_UA, follow_redirects=True)
            r.raise_for_status()
            page_html = r.text
        except Exception:  # noqa: BLE001
            break
        time.sleep(0.3)
        n_rows = len(re.findall(r"<tr[^>]*>.*?\d{2}\.\d{2}\.\d{4}", page_html, re.S))
        html_pages.append(page_html)
        if n_rows < 25:
            break
    html = "".join(html_pages)
    out = []
    seen = set()
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        cells = [c for c in cells if c and c != "&nbsp;"]
        if len(cells) < 2 or not re.match(r"\d{2}\.\d{2}\.\d{4}", cells[0]):
            continue
        try:
            dd, mm, yy = cells[0].split(".")
            ev_date = date(int(yy), int(mm), int(dd))
        except ValueError:
            continue
        if ev_date > today:
            continue  # будущее уже покрыто build_corporate/build_ir_calendar — тут только прошлое
        desc = cells[1].replace("&gt;", "").strip()
        if _classify_corp(desc) != "report":
            continue
        ticker = desc.split(":")[0].strip() if ":" in desc else None
        if not ticker or ticker not in companies or (ticker, ev_date) in seen:
            continue
        seen.add((ticker, ev_date))
        out.append({"secid": ticker, "event_date": ev_date,
                    "event_id": f"sl{ev_date.isoformat()}_{abs(hash(desc)) % 1_000_000}",
                    "description": desc, "event_link": None})
    return out


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
        # Строгий детект-паттерн, НЕ ранжирующий _REPORT_KEYWORDS_RE — см. комментарий
        # у _NEWS_REPORT_DETECT_RE (мусор из-за «дивиденд»/«добыч»/«производств»).
        if not _NEWS_REPORT_DETECT_RE.search(blob):
            continue
        tickers = r.affected_tickers or []
        # Отчёт — событие ОДНОЙ компании. Отраслевые/страновые/рыночные обзоры
        # («Brent подорожала», «Добыча газа в РФ») тегируются десятками тикеров
        # (реальный пример с боя: 23 тикера) — и раньше каждый из них получал
        # свою мусорную запись в Отчёты. Порог 2 покрывает легитимный случай
        # обычка+преф одного эмитента (SBER/SBERP, TATN/TATNP).
        if len(tickers) > 2:
            continue
        for t in tickers:
            if t in companies:
                out.append({"market_update_id": r.id, "ticker": t, "published_at": r.published_at.date(),
                            "title": r.title, "summary": r.summary, "impact_comment": r.impact_comment,
                            "source_url": r.source_url})
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

    # smart-lab — ТОЛЬКО детект дат (владелец одобрил 2026-07-14, см. докстринг
    # _due_smartlab_rows), расширяет охват заметно за пределы 76 тикеров MOEX.
    # Пропускаем (тикер, дата), уже покрытые MOEX-путём выше — не задваиваем событие.
    ir_covered = {(r["secid"], r["event_date"]) for r in due_rows}
    smartlab_rows = [r for r in _due_smartlab_rows(companies, days_back) if (r["secid"], r["event_date"]) not in ir_covered]
    for row in smartlab_rows:
        company = companies.get(row["secid"])
        if not company:
            res["skipped_no_company"] += 1
            continue
        try:
            event = _get_or_create_calendar_event(db, row, company, source="smartlab",
                                                  key_prefix="smartlab_past", confidence="public_aggregated")
            r = process_event(db, event, company, float(company.market_cap) if company.market_cap else None, inn_map)
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("report_watch: ошибка по событию (smartlab) %s/%s: %s", row["secid"], row["event_id"], type(e).__name__)
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

    logger.info("report_watch: %s (ir-событий: %d, smart-lab: %d, новостных кандидатов: %d, ГИР БО: %d, company_rss: %d)",
                res, len(due_rows), len(smartlab_rows), len(news_items), len(girbo_items), len(rss_items))
    return res
