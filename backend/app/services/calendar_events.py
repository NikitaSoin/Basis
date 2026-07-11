"""Агрегатор календаря событий (Обозреватель, Направление 4).

Собирает CalendarEvent из готовых источников (без новых интеграций, кроме MOEX ISS,
который уже используется): дивиденды (ISS), облигации (таблица Bond), макрорелизы
(RateMeeting ЦБ + оценочный релиз ИПЦ). IPO — из Ленты (анонсы). Корпсобытия
(e-disclosure) — точка расширения (см. build_corporate).

Расчётные поля — КОДОМ: buy_by_date = дата отсечки − 1 ТОРГОВЫЙ день (режим T+1),
dividend_yield = сумма/текущая цена. Для флоатеров/близких оферт доходность
помечается индикативной (на стороне витрины — по payload).
Дедуп — по dedup_key (ON CONFLICT DO UPDATE), повторный прогон не плодит дубли.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.bond import Bond

logger = logging.getLogger(__name__)

# Нерабочие дни РФ 2026 (для корректного T+1; приблизительно по производств. календарю).
_RU_HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6),
    date(2026, 1, 7), date(2026, 1, 8), date(2026, 2, 23), date(2026, 3, 9),
    date(2026, 5, 1), date(2026, 5, 11), date(2026, 6, 12), date(2026, 11, 4),
}


def prev_trading_day(d: date) -> date:
    """Предыдущий ТОРГОВЫЙ день (минус выходные и праздники РФ). Для T+1 «купить до»."""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5 or cur in _RU_HOLIDAYS_2026:
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    """Следующий ТОРГОВЫЙ день. Обратная prev_trading_day — для перевода
    «последний день с дивидендом» (buy_by) в дату закрытия реестра (T+1)."""
    cur = d + timedelta(days=1)
    while cur.weekday() >= 5 or cur in _RU_HOLIDAYS_2026:
        cur += timedelta(days=1)
    return cur


def _latest_closes(db: Session) -> dict[str, float]:
    rows = db.execute(text("""
        SELECT DISTINCT ON (q.company_id) c.ticker, q.close
        FROM quotes q JOIN companies c ON c.id = q.company_id
        WHERE q.close IS NOT NULL
        ORDER BY q.company_id, q.date DESC
    """)).fetchall()
    return {r.ticker: float(r.close) for r in rows if r.close is not None}


def _upsert(db: Session, events: list[dict]) -> int:
    """Идемпотентная заливка по dedup_key."""
    n = 0
    for e in events:
        stmt = pg_insert(CalendarEvent).values(**e)
        stmt = stmt.on_conflict_do_update(
            index_elements=["dedup_key"],
            set_={k: e[k] for k in ("event_date", "event_time", "ticker", "sector",
                                    "title", "status", "source", "source_url", "payload")},
        )
        db.execute(stmt)
        n += 1
    db.commit()
    return n


def _rates_csv_dividends() -> list[dict]:
    """Анонсированные ближайшие дивиденды из rates.csv (REGISTRYCLOSEDATE + DIVIDENDVALUE
    — поля листинга MOEX). Это ОСНОВНОЙ источник БУДУЩИХ отсечек (ISS /dividends.json
    отдаёт только историю выплат). Файл: 1-я строка 'rates', 2-я пустая, затем заголовок."""
    import csv, os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "rates.csv")
    out: list[dict] = []
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="cp1251") as f:
            f.readline(); f.readline()  # 'rates' + пустая строка
            for r in csv.DictReader(f, delimiter=";"):
                rc = (r.get("REGISTRYCLOSEDATE") or "").strip()
                dv = (r.get("DIVIDENDVALUE") or "").strip()
                if not rc or dv in ("", "0", "0.0", "0.00"):
                    continue
                try:
                    out.append({"ticker": r["SECID"], "record_date": rc, "amount": float(dv)})
                except (ValueError, KeyError):
                    continue
    except Exception:  # noqa: BLE001
        return out
    return out


# ----------------------------- ДИВИДЕНДЫ (rates.csv + MOEX ISS) -----------------------------
def build_dividends(db: Session, lookback_days: int = 400) -> list[dict]:
    """Дивиденды: будущие отсечки из rates.csv (листинг MOEX) + история из ISS.
    buy_by (T+1) и дивдоходность считаются КОДОМ. ISS /dividends.json — только история,
    поэтому будущие берём из rates.csv (DIVIDENDVALUE/REGISTRYCLOSEDATE)."""
    from app.services.moex_dividends import fetch_dividends
    companies = {c.ticker: c for c in db.query(Company).all()}
    closes = _latest_closes(db)
    cutoff = date.today() - timedelta(days=lookback_days)
    out: list[dict] = []

    # 1) будущие/анонсированные — из rates.csv (основной источник предстоящих отсечек)
    for r in _rates_csv_dividends():
        ticker = r["ticker"]; c = companies.get(ticker)
        if not c:
            continue
        try:
            rec = date.fromisoformat(r["record_date"])
        except (TypeError, ValueError):
            continue
        if rec < cutoff:
            continue
        price = closes.get(ticker); amount = r["amount"]
        dy = round(amount / price * 100, 2) if price else None
        buy_by = prev_trading_day(rec)
        out.append({
            "event_type": "dividend", "event_date": rec, "event_time": None,
            "ticker": ticker, "sector": c.sector,
            "title": f"{c.name}: дивиденд {amount:g} ₽/акц.",
            "status": "объявлен", "source": "moex_listing",
            "source_url": f"https://www.moex.com/ru/issue.aspx?code={ticker}",
            "payload": {"amount": amount, "currency": "RUB", "record_date": rec.isoformat(),
                        "buy_by_date": buy_by.isoformat(), "dividend_yield": dy},
            "dedup_key": f"dividend:{ticker}:{rec.isoformat()}",
        })
    for ticker, c in companies.items():
        try:
            rows = fetch_dividends(ticker)
        except Exception:  # noqa: BLE001 — недоступность одной бумаги не валит весь прогон
            continue
        for r in rows:
            try:
                rec = date.fromisoformat(r["record_date"])
            except (TypeError, ValueError):
                continue
            if rec < cutoff:
                continue
            amount = r["amount"]
            price = closes.get(ticker)
            dy = round(amount / price * 100, 2) if price else None
            buy_by = prev_trading_day(rec)
            out.append({
                "event_type": "dividend", "event_date": rec, "event_time": None,
                "ticker": ticker, "sector": c.sector,
                "title": f"{c.name}: дивиденд {amount:g} ₽/акц.",
                "status": "объявлен", "source": "moex_iss",
                "source_url": f"https://www.moex.com/ru/issue.aspx?code={ticker}",
                "payload": {"amount": amount, "currency": r.get("currency", "RUB"),
                            "record_date": rec.isoformat(), "buy_by_date": buy_by.isoformat(),
                            "dividend_yield": dy},
                "dedup_key": f"dividend:{ticker}:{rec.isoformat()}",
            })
    return out


# ----------------------------- ОБЛИГАЦИИ (таблица Bond) -----------------------------
def build_bonds(db: Session) -> list[dict]:
    """Оферты и погашения облигаций из таблицы Bond (источник — MOEX ISS, грузится ежедн.)."""
    today = date.today()
    out: list[dict] = []
    bonds = db.query(Bond).filter(Bond.is_defaulted.isnot(True)).all()
    for b in bonds:
        common = {
            "coupon_type": b.coupon_type, "coupon_percent": float(b.coupon_percent) if b.coupon_percent is not None else None,
            "ytm": float(b.ytm) if b.ytm is not None else None, "ytm_kind": b.ytm_kind,
            "face_value": float(b.face_value) if b.face_value is not None else None,
            "rating": b.agency_rating,
            # доходность индикативна для флоатеров и при близкой оферте
            "yield_indicative": bool(b.coupon_type == "floater" or b.offer_date),
        }
        if b.offer_date and b.offer_date >= today:
            out.append({
                "event_type": "bond_offer", "event_date": b.offer_date, "event_time": None,
                "ticker": b.secid, "sector": None,
                "title": f"{b.short_name}: оферта (пут)", "status": None, "source": "moex_iss",
                "source_url": f"https://www.moex.com/ru/issue.aspx?code={b.secid}",
                "payload": {**common, "kind": "offer"},
                "dedup_key": f"bond_offer:{b.secid}:{b.offer_date.isoformat()}",
            })
        if b.maturity_date and b.maturity_date >= today:
            out.append({
                "event_type": "bond_maturity", "event_date": b.maturity_date, "event_time": None,
                "ticker": b.secid, "sector": None,
                "title": f"{b.short_name}: погашение", "status": None, "source": "moex_iss",
                "source_url": f"https://www.moex.com/ru/issue.aspx?code={b.secid}",
                "payload": {**common, "kind": "maturity"},
                "dedup_key": f"bond_maturity:{b.secid}:{b.maturity_date.isoformat()}",
            })
    return out


# ----------------------------- ФЬЮЧЕРСЫ (экспирации) -----------------------------
def build_futures(db: Session) -> list[dict]:
    """Экспирации фьючерсов (из таблицы futures, если есть). Полезное из прежнего календаря."""
    today = date.today()
    out: list[dict] = []
    try:
        rows = db.execute(text(
            "SELECT secid, short_name, expiration_date, asset_name FROM futures "
            "WHERE expiration_date >= :t ORDER BY expiration_date LIMIT 200"), {"t": today}).all()
    except Exception:  # noqa: BLE001 — таблицы может не быть
        return out
    for r in rows:
        out.append({
            "event_type": "expiration", "event_date": r[2], "event_time": None,
            "ticker": r[0], "sector": None,
            "title": f"{r[1]}: экспирация фьючерса", "status": None, "source": "moex_iss",
            "source_url": f"https://www.moex.com/ru/contract.aspx?code={r[0]}",
            "payload": {"asset_name": r[3]},
            "dedup_key": f"expiration:{r[0]}:{r[2].isoformat()}",
        })
    return out


# ЦБ публикует график заседаний по ключевой ставке на год вперёд (обычно в декабре).
# Опорные заседания (с публикацией среднесрочного прогноза) помечены отдельно.
# Источник: https://cbr.ru/dkp/cal_mp/ — ОБНОВЛЯТЬ ЕЖЕГОДНО, когда публикуют график
# следующего года (декабрь). Проверено веб-поиском 2026-07-09.
_CB_RATE_SCHEDULE_2026 = [
    ("2026-02-13", True), ("2026-03-20", False), ("2026-04-24", True),
    ("2026-06-19", False), ("2026-07-24", True), ("2026-09-11", False),
    ("2026-10-23", True), ("2026-12-18", False),
]


# ----------------------------- МАКРОРЕЛИЗЫ (ЦБ + ИПЦ) -----------------------------
def build_macro(db: Session) -> list[dict]:
    """Заседания ЦБ по ставке (весь известный график на год, не только ближайшее из
    RateMeeting) + оценочный релиз ИПЦ."""
    out: list[dict] = []
    today = date.today()
    for d_str, is_key in _CB_RATE_SCHEDULE_2026:
        d = date.fromisoformat(d_str)
        if d < today:
            continue
        title = "Заседание ЦБ РФ по ключевой ставке" + (" (опорное, с прогнозом)" if is_key else "")
        out.append({
            "event_type": "macro", "event_date": d, "event_time": "13:30",
            "ticker": None, "sector": None,
            "title": title, "status": "ожидается",
            "source": "cbr", "source_url": "https://www.cbr.ru/dkp/cal_mp/",
            "payload": {"kind": "cb_rate", "key_meeting": is_key,
                       "note": "Решение ~13:30, пресс-конференция ~15:00 МСК"},
            "dedup_key": f"macro:cb_rate:{d.isoformat()}",
        })
    # Оценочный релиз месячной инфляции Росстата (~12-е число след. месяца).
    nm = (today.replace(day=1) + timedelta(days=32)).replace(day=12)
    out.append({
        "event_type": "macro", "event_date": nm, "event_time": None,
        "ticker": None, "sector": None,
        "title": "Инфляция (ИПЦ) за месяц — публикация Росстата", "status": "ожидается (оценка даты)",
        "source": "rosstat", "source_url": "https://rosstat.gov.ru/statistics/price",
        "payload": {"kind": "cpi", "estimated": True},
        "dedup_key": f"macro:cpi:{nm.isoformat()}",
    })
    return out


# ----------------------------- РОССТАТ: график анонсов (реальные даты) -----------------------------
_ROSSTAT_ANNOUNCEMENTS = "https://rosstat.gov.ru/announcements"


def build_rosstat_releases(db: Session) -> list[dict]:
    """Реальный график публикаций Росстата (ИПЦ/ИЦП/ВВП/безработица/зарплата и т.д.) —
    НЕ оценка формулой (как build_macro.cpi выше), а факт из официального графика
    на весь текущий период. Страница отдаёт HTML-таблицу с прямыми ссылками вида
    .../N_DD-MM-YYYY.html — дата публикации зашита в href, надёжнее парсинга русских
    названий месяцев текстом. TLS-сертификат сайта не проходит стандартную проверку
    (не WAF, просто неполная цепочка) — verify=False, как для других обходных путей
    Rosstat в проекте."""
    import re
    import httpx
    out: list[dict] = []
    today = date.today()
    try:
        r = httpx.get(_ROSSTAT_ANNOUNCEMENTS, timeout=30, verify=False,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь Росстата: страница недоступна: %s", type(e).__name__)
        return out
    for table in re.findall(r"<table>(.*?)</table>", html, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(tds) != 3:
                continue
            title_td = tds[1]
            m = re.search(r"_(\d{2})-(\d{2})-(\d{4})\.html", title_td)
            if not m:
                continue
            dd, mo, yyyy = m.groups()
            try:
                ev_date = date(int(yyyy), int(mo), int(dd))
            except ValueError:
                continue
            if ev_date < today - timedelta(days=1):
                continue  # прошедшее — не засоряем календарь
            title = re.sub(r"<[^>]+>", " ", title_td)
            title = title.replace("&nbsp;", " ")
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            href_m = re.search(r'href="([^"]+)"', title_td)
            src_url = ("https://rosstat.gov.ru" + href_m.group(1)) if href_m else _ROSSTAT_ANNOUNCEMENTS
            out.append({
                "event_type": "macro", "event_date": ev_date, "event_time": None,
                "ticker": None, "sector": None,
                "title": title[:300], "status": "ожидается",
                "source": "rosstat", "source_url": src_url,
                "payload": {"kind": "rosstat_release"},
                "dedup_key": f"macro:rosstat:{ev_date.isoformat()}:{title[:60]}",
            })
    logger.info("Календарь Росстата: %d публикаций", len(out))
    return out


# ----------------------------- ЦБ: календарь публикации статистики (.ics) -----------------------------
_CB_INDCALENDAR_PAGE = "https://www.cbr.ru/statistics/indcalendar/"


def build_cb_indcalendar(db: Session) -> list[dict]:
    """Календарь БУДУЩИХ публикаций статистики ЦБ (платёжный баланс, денежная база,
    международные резервы и т.п.) — НЕ пересекается с macro_cb_sync.py (тот тянет
    текст решений/прогноза по ставке через LLM). Источник — .ics с cbr.ru, ссылка на
    актуальный файл берётся с html-страницы динамически (numeric id в пути меняется
    при обновлении файла на стороне ЦБ, поэтому не хардкодим URL)."""
    import re
    import httpx
    out: list[dict] = []
    today = date.today()
    try:
        page = httpx.get(_CB_INDCALENDAR_PAGE, timeout=30).text
        m = re.search(r'href="(/Queries/FileSource/\d+/vCalendar\.ics[^"]*)"', page)
        if not m:
            logger.warning("Календарь ЦБ (.ics): ссылка на файл не найдена на странице")
            return out
        ics_url = "https://www.cbr.ru" + m.group(1)
        ics = httpx.get(ics_url, timeout=30).text
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь ЦБ (.ics): недоступен: %s", type(e).__name__)
        return out
    # VEVENT-блоки; DTSTART:YYYYMMDDT... (иногда с продолжением строки через таб —
    # RFC5545 folding, склеиваем перед парсингом), SUMMARY;LANGUAGE=ru:<текст>
    ics_unfolded = re.sub(r"\r?\n[ \t]", "", ics)
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_unfolded, re.S):
        dm = re.search(r"DTSTART:(\d{4})(\d{2})(\d{2})", block)
        sm = re.search(r"SUMMARY;LANGUAGE=ru:(.+?)(?:\n\S|\Z)", block, re.S)
        if not dm or not sm:
            continue
        try:
            ev_date = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
        except ValueError:
            continue
        if ev_date < today:
            continue
        title = re.sub(r"\s+", " ", sm.group(1)).strip()
        if not title:
            continue
        out.append({
            "event_type": "macro", "event_date": ev_date, "event_time": None,
            "ticker": None, "sector": None,
            "title": title[:300], "status": "ожидается",
            "source": "cbr_indcalendar", "source_url": _CB_INDCALENDAR_PAGE,
            "payload": {"kind": "cbr_stat_release"},
            "dedup_key": f"macro:cbr_stat:{ev_date.isoformat()}:{title[:60]}",
        })
    logger.info("Календарь ЦБ (.ics): %d публикаций", len(out))
    return out[:400]  # предохранитель — 742 события в источнике на 1.5 года вперёд, не нужно всё разом


# ----------------------------- IPO (из Ленты) -----------------------------
def build_ipo(db: Session) -> list[dict]:
    """IPO/размещения из анонсов Ленты (best-effort по ключевым словам). Пусто — норма."""
    out: list[dict] = []
    try:
        from app.models.market import MarketUpdate
        kws = ("ipo", "ipo-", "первичное размещение", "выйдет на биржу", "размещение акций",
               "проведёт ipo", "планирует ipo", "spo")
        rows = (db.query(MarketUpdate)
                .filter(MarketUpdate.status == "published")
                .order_by(MarketUpdate.published_at.desc()).limit(300).all())
        for u in rows:
            text_l = f"{u.title or ''} {u.summary or ''}".lower()
            if not any(k in text_l for k in kws):
                continue
            out.append({
                "event_type": "ipo", "event_date": (u.published_at.date() if u.published_at else date.today()),
                "event_time": None, "ticker": None, "sector": None,
                "title": (u.title or "Анонс размещения")[:300], "status": "анонс",
                "source": "news", "source_url": u.source_url,
                "payload": {"summary": (u.summary or "")[:500]},
                "dedup_key": f"ipo:news:{u.id}",
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь: IPO из Ленты не собрано: %s", e)
    return out[:20]


# ----------------------------- КОРПСОБЫТИЯ (smart-lab) -----------------------------
_SMARTLAB_CAL = "https://smart-lab.ru/calendar/stocks/"
_SL_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9"}


def _classify_corp(desc: str) -> str:
    d = desc.lower()
    if ("закрыти" in d and "реестр" in d) or "последний день с дивиденд" in d:
        return "dividend"
    if "ipo" in d:
        return "ipo"
    if "собрани" in d or "госа" in d or "воса" in d or "оса акционеров" in d:
        return "meeting"
    if "совет дир" in d or "наблюдат" in d or "сд " in d:
        return "board"
    if any(k in d for k in ("отчет", "отчёт", "результат", "мсфо", "рсбу", "операционн")):
        return "report"
    return "other"


_SUBTYPE_LABEL = {"report": "отчётность", "board": "совет директоров",
                  "meeting": "собрание акционеров", "ipo": "IPO/размещение"}


def build_corporate(db: Session) -> list[dict]:
    """Будущие корпсобытия из smart-lab (календарь акций ММВБ): отчётности (МСФО/РСБУ/
    операционные), заседания СД, собрания акционеров (ГОСА/ВОСА), IPO, БУДУЩИЕ дивиденды
    (отсечки/последний день с дивидендом). e-disclosure закрыт антиботом — smart-lab
    публичный и парсится. Горизонт фида ~неделя вперёд; при суточном пересборе события
    НАКАПЛИВАЮТСЯ (дедуп не плодит) → растёт форвард-календарь. Тикер сопоставляется с
    нашими компаниями для сектора/портфеля.
    🔴 Дивиденды: изначально rates.csv (справочник) считался ОСНОВНЫМ источником
    будущих отсечек — на практике он статичный (обновляется вручную редко) и почти
    всегда не содержит объявленных сумм на горизонте недель. smart-lab же публикует
    отсечки с суммой ЖИВЬЁМ — берём её отсюда, dedup_key совпадает с build_dividends
    (dividend:{ticker}:{record_date}), поэтому обе записи корректно схлопываются
    в одну по одинаковому ключу (последняя выигрывает при апдейте)."""
    import httpx, re, hashlib
    out: list[dict] = []
    try:
        r = httpx.get(_SMARTLAB_CAL, timeout=30, headers=_SL_HTTP, follow_redirects=True)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь корпсобытий: smart-lab недоступен: %s", type(e).__name__)
        return out
    companies = {c.ticker: c for c in db.query(Company).all()}
    sectors = {t: c.sector for t, c in companies.items()}
    closes = _latest_closes(db)
    div_amount_re = re.compile(r"([\d]+[.,]\d+|\d+)\s*(?:руб|\$|USD|₽)", re.I)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        cells = [c for c in cells if c and c != "&nbsp;"]
        if len(cells) < 2 or not re.match(r"\d{2}\.\d{2}\.\d{4}", cells[0]):
            continue
        try:
            d, mo, y = cells[0].split(".")
            ev_date = date(int(y), int(mo), int(d))
        except (ValueError, IndexError):
            continue
        desc = cells[1].replace("&gt;", "").strip()
        kind = _classify_corp(desc)
        if kind == "other":
            continue  # не классифицируем — не событие для карточки
        ticker = desc.split(":")[0].strip() if ":" in desc else None
        ticker = ticker if (ticker and ticker in companies) else None
        if kind == "dividend":
            if not ticker:
                continue  # без тикера нельзя посчитать доходность/добавить в портфельный фильтр
            m = div_amount_re.search(desc)
            if not m:
                continue  # сумма не объявлена — рано показывать (не факт, не событие)
            try:
                amount = float(m.group(1).replace(",", "."))
            except ValueError:
                continue
            # «последний день с дивидендом» = buy_by (T-1); «закрытие реестра» = record_date
            is_buy_by_phrase = "последний день" in desc.lower()
            record_date = next_trading_day(ev_date) if is_buy_by_phrase else ev_date
            buy_by = ev_date if is_buy_by_phrase else prev_trading_day(ev_date)
            price = closes.get(ticker)
            dy = round(amount / price * 100, 2) if price else None
            out.append({
                "event_type": "dividend", "event_date": record_date, "event_time": None,
                "ticker": ticker, "sector": sectors.get(ticker),
                "title": f"{companies[ticker].name}: дивиденд {amount:g} ₽/акц.",
                "status": "объявлен", "source": "smartlab",
                "source_url": f"https://www.moex.com/ru/issue.aspx?code={ticker}",
                "payload": {"amount": amount, "currency": "RUB", "record_date": record_date.isoformat(),
                            "buy_by_date": buy_by.isoformat(), "dividend_yield": dy},
                "dedup_key": f"dividend:{ticker}:{record_date.isoformat()}",
            })
            continue
        # report — отдельный event_type "earnings" (свой фильтр/цвет на фронте,
        # отличный от СД/собраний, которые остаются под "corporate")
        ev_type = "ipo" if kind == "ipo" else "earnings" if kind == "report" else "corporate"
        h = hashlib.md5(desc.encode("utf-8")).hexdigest()[:10]
        out.append({
            "event_type": ev_type, "event_date": ev_date, "event_time": None,
            "ticker": ticker, "sector": sectors.get(ticker) if ticker else None,
            "title": desc[:300], "status": _SUBTYPE_LABEL.get(kind),
            "source": "smartlab", "source_url": _SMARTLAB_CAL,
            "payload": {"subtype": kind},
            "dedup_key": f"{ev_type}:{ev_date.isoformat()}:{h}",
        })
    logger.info("Календарь корпсобытий (smart-lab): %d событий", len(out))
    return out


# ----------------------------- MOEX «Центр корпоративной информации» (форвард-календарь) -----------------------------
_MOEX_IR_CALENDAR = "https://iss.moex.com/iss/cci/calendars/ir-calendar.json"
_IR_TYPE_MAP = {"Публикация отчетности": "earnings", "Собрания владельцев ценных бумаг": "corporate"}
_IR_STATUS_LABEL = {"earnings": "отчётность", "corporate": "собрание акционеров"}


def build_ir_calendar(db: Session) -> list[dict]:
    """Форвард-календарь отчётностей/ГОСА-ВОСА — MOEX ISS «Центр корпоративной информации»
    (эндпоинт не в официальном /iss/reference/, но публичный, без авторизации, проверен вручную
    2026-07-11: ?limit=max отдаёт 1984 события, включая даты на 2027-2030 год). ГЛАВНОЕ ОТЛИЧИЕ
    от build_corporate (smart-lab): горизонт МЕСЯЦЫ/ГОДЫ вперёд, а не ~неделя — MOEX сам
    агрегирует из открытых источников (IR-страницы/пресс-релизы эмитентов) и от части эмитентов
    напрямую (data_source_code public/issuer). Это ГРАФИК компании, не гарантированный факт —
    статус помечен так же, как у smart-lab-эквивалента (единый визуальный язык), точность —
    в payload.confidence на будущее.
    Покрытие частичное (~76 эмитентов из 261 на момент проверки — MOEX явно охватывает не всех) —
    ДОПОЛНЯЕТ smart-lab, не заменяет. Бонд-купоны/погашения из этого фида (event_type_name=
    "Выплаты по инструментам") НЕ берём — уже есть из таблицы Bond (build_bonds). Дивиденд-даты
    внутри той же категории (напр. «дата определения лиц, имеющих право на получение дивидендов»)
    — тоже не берём в этом заходе: в фиде нет суммы дивиденда (она есть только у smart-lab/
    rates.csv) — отдельная точка расширения, не хотим показывать «пустое» событие.
    Дедуп ПРОТИВ smart-lab: без общего dedup_key (разные источники/тексты) — чтобы не плодить
    вторую карточку на ту же дату, когда smart-lab «подхватывает» событие в свою ~недельную зону
    видимости, СНАЧАЛА исключаем (event_type, ticker, event_date), уже присутствующие в БД из
    ДРУГИХ источников (типично smart-lab ближе к дате) — на дальнем горизонте конфликтов нет.
    🔴 event_id из ЭТОГО фида НЕ глобально уникален (это счётчик ВНУТРИ эмитента — секунда
    проверка нашла 7 коллизий типа ir_calendar:9 у ZAYM И у DOMRF одновременно) — ключ
    ОБЯЗАТЕЛЬНО включает secid."""
    import httpx
    out: list[dict] = []
    try:
        r = httpx.get(_MOEX_IR_CALENDAR, params={"limit": "max"}, timeout=30)
        r.raise_for_status()
        block = (r.json() or {}).get("cci_ir_calendar") or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь ir-calendar (MOEX CCI): недоступен: %s", type(e).__name__)
        return out
    cols = block.get("columns") or []
    rows = block.get("data") or []
    if not cols or not rows:
        return out
    idx = {c: i for i, c in enumerate(cols)}
    companies = {c.ticker: c for c in db.query(Company).all()}
    today = date.today()
    existing = {
        (r.event_type, r.ticker, r.event_date)
        for r in db.query(CalendarEvent.event_type, CalendarEvent.ticker, CalendarEvent.event_date)
        .filter(CalendarEvent.event_type.in_(("earnings", "corporate")),
                CalendarEvent.source != "moex_ir_calendar",
                CalendarEvent.event_date >= today).all()
    }
    for row in rows:
        ev_type = _IR_TYPE_MAP.get(row[idx["event_type_name"]])
        if not ev_type:
            continue  # бонд-купоны/IR-звонки — не берём (см. докстринг)
        secid = row[idx["secid"]]
        c = companies.get(secid) if secid else None
        if not c:
            continue  # без сопоставления с нашей компанией — нет карточки/сектора, не показываем
        ev_date_raw = row[idx["event_date"]]
        if not ev_date_raw:
            continue
        try:
            ev_date = date.fromisoformat(ev_date_raw[:10])
        except (TypeError, ValueError):
            continue
        if ev_date < today or (ev_type, secid, ev_date) in existing:
            continue
        desc = (row[idx["event_description"]] or "").strip()
        if not desc:
            continue
        event_link = row[idx["event_link"]]
        source_code = row[idx["data_source_code"]]
        out.append({
            "event_type": ev_type, "event_date": ev_date, "event_time": None,
            "ticker": secid, "sector": c.sector,
            "title": f"{c.name}: {desc}"[:300], "status": _IR_STATUS_LABEL[ev_type],
            "source": "moex_ir_calendar",
            "source_url": event_link or f"https://www.moex.com/ru/issue.aspx?code={secid}",
            "payload": {"subtype": "report" if ev_type == "earnings" else "meeting",
                        "confidence": "issuer" if source_code == "issuer" else "public_aggregated",
                        "description": desc[:500]},
            "dedup_key": f"ir_calendar:{secid}:{row[idx['event_id']]}",
        })
    logger.info("Календарь ir-calendar (MOEX CCI): %d событий, %d эмитентов",
                len(out), len({e['ticker'] for e in out}))
    return out


# ----------------------------- ПРАЙМ (disclosure.1prime.ru) — крупная нефтянка/металлургия -----------------------------
# Аккредитованный ЦБ РФ сервер раскрытия информации (альтернатива e-disclosure/Интерфакс,
# НЕ закрыт анти-ботом — проверено вручную curl'ом 2026-07-11). Точечно закрывает дыру
# MOEX ir-calendar: крупная нефтянка (Роснефть/Лукойл/Новатэк/Газпромнефть/Сургутнефтегаз/
# Татнефть/Транснефть/Башнефть) и часть металлургии (Русал/НЛМК/ММК/Алроса/ВСМПО-Ависма) +
# ПИК — у этих компаний 0 записей в MOEX-фиде вообще (проверено), вероятно потому что они
# не ведут публичный IR-календарь (санкционная сдержанность с 2022), но раскрытие
# существенных фактов ПО ЗАКОНУ обязательно и продолжается через аккредитованные агентства.
_PRIME_BASE = "https://disclosure.1prime.ru"
_PRIME_ISSUERS = {  # ИНН проверены вручную 2026-07-11 (сверка названия через профиль СКРИН)
    "ROSN": "7706107510", "LKOH": "7708004767", "NVTK": "6316031581",
    "SIBN": "5504036333", "SNGS": "8602060555", "TATN": "1644003838",
    "RUAL": "3906394938", "NLMK": "4823006703", "MAGN": "7414003633",
    "ALRS": "1433000147", "TRNFP": "7706061801", "BANE": "0274051582",
    "PIKK": "7713011336", "VSMO": "6607000556",
}
# Только 2 типа регуляторных сообщений (стандартный шаблон Положения №714-П, поля
# пронумерованы — надёжно парсить): заседание СД (форвард-дата в поле "Дата проведения
# заседания совета директоров") и созыв ГОСА/ВОСА (дата в тексте после "проводится").
# НЕ берём "Дата, на которую определяются лица, имеющие право..." (дивиденд-отсечка) —
# в сообщении НЕТ суммы дивиденда (она в отдельном решении СД/ГОСА) — та же политика,
# что и в build_ir_calendar: не показываем «пустое» дивидендное событие без суммы.
_PRIME_TITLE_MAP = {
    "проведение заседания совета директоров": ("board", "заседание совета директоров"),
    "созыв общего собрания": ("meeting", "собрание акционеров"),
}
_RU_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
              "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}


def _parse_ru_date(s: str) -> date | None:
    """Дата словом («8 июля 2026 года») ИЛИ числом (ТАТН пишет «25.06.2026») — оба формата
    реально встречаются в разных шаблонах разных эмитентов (проверено 2026-07-11)."""
    import re
    m = re.search(r"(\d{1,2})\s+(" + "|".join(_RU_MONTHS) + r")\s+(\d{4})", s, re.IGNORECASE)
    if m:
        d, mon, y = m.groups()
        try:
            return date(int(y), _RU_MONTHS[mon.lower()], int(d))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
    return None


def build_prime_disclosure(db: Session) -> list[dict]:
    """Заседания СД + созыв ГОСА/ВОСА для 14 крупных эмитентов вне MOEX ir-calendar,
    источник — ПРАЙМ (см. докстринг блока выше). На компанию: скан таблицы сообщений
    (`portal/default.aspx?emId=ИНН`), берём последние ДО 8 совпадений по заголовку
    (экономия — не гоняем полный текст всех сотен строк), для каждого — полный текст
    (`Portal/GetMessage.aspx`), регекс на нужное пронумерованное поле. Дедуп по guid
    сообщения (реальный UUID Банка России — глобально уникален, в отличие от event_id
    MOEX ir-calendar) + против других источников тем же паттерном (event_type, ticker,
    event_date), что в build_ir_calendar.
    🔴 Паузы между запросами ОБЯЗАТЕЛЬНЫ: без них локальный тест поймал HTTPStatusError
    на 6 из 14 компаний подряд (частый анти-скрейпинг по частоте, не по IP/UA — тот же
    запрос через секунды успешно повторялся вручную)."""
    import httpx, re, time
    out: list[dict] = []
    companies = {c.ticker: c for c in db.query(Company).all()}
    today = date.today()
    existing = {
        (r.event_type, r.ticker, r.event_date)
        for r in db.query(CalendarEvent.event_type, CalendarEvent.ticker, CalendarEvent.event_date)
        .filter(CalendarEvent.event_type == "corporate",
                CalendarEvent.source != "prime_disclosure",
                CalendarEvent.ticker.in_(list(_PRIME_ISSUERS)),
                CalendarEvent.event_date >= today).all()
    }
    for ticker, inn in _PRIME_ISSUERS.items():
        c = companies.get(ticker)
        if not c:
            continue
        time.sleep(0.6)
        try:
            r = httpx.get(f"{_PRIME_BASE}/portal/default.aspx", params={"emId": inn}, timeout=30)
            r.raise_for_status()
            html = r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("Календарь prime_disclosure %s: страница недоступна: %s", ticker, type(e).__name__)
            continue
        candidates = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            if "GetMessage" not in row:
                continue
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) < 2:
                continue
            title = re.sub(r"<[^>]+>", " ", cells[1]).strip()
            title_l = title.lower()
            kind = next((v for kw, v in _PRIME_TITLE_MAP.items() if kw in title_l), None)
            if not kind:
                continue
            gm = re.search(r"guid=(\{[0-9A-Fa-f-]+\})", row)
            if not gm:
                continue
            candidates.append((title, kind, gm.group(1)))
            if len(candidates) >= 8:
                break
        for title, (subtype, label), guid in candidates:
            time.sleep(0.3)
            try:
                mr = httpx.get(f"{_PRIME_BASE}/Portal/GetMessage.aspx",
                                params={"emId": inn, "guid": guid}, timeout=30)
                mr.raise_for_status()
                msg_text = mr.text
            except Exception:  # noqa: BLE001
                continue
            if subtype == "board":
                # очное «заседание» И заочное «голосование» — оба формата решения СД
                # (проверено 2026-07-11: ЛУКОЙЛ пишет «заочного голосования», Роснефть —
                # «заседания»); регистр названия «Совета директоров» тоже плавает по эмитентам.
                fm = re.search(r"Дата проведения (?:заседания|заочного голосования) совета директоров[^:]*:\s*([^<\n]+)",
                               msg_text, re.IGNORECASE)
            else:
                fm = re.search(r"проводится\s+(\d{1,2}\s+\S+\s+\d{4}\s+года)", msg_text, re.IGNORECASE)
            ev_date = _parse_ru_date(fm.group(1)) if fm else None
            if not ev_date or ev_date < today or ("corporate", ticker, ev_date) in existing:
                continue
            out.append({
                "event_type": "corporate", "event_date": ev_date, "event_time": None,
                "ticker": ticker, "sector": c.sector,
                "title": f"{c.name}: {title}"[:300], "status": label,
                "source": "prime_disclosure",
                "source_url": f"{_PRIME_BASE}/Portal/GetMessage.aspx?emId={inn}&guid={guid}",
                "payload": {"subtype": subtype, "confidence": "issuer"},
                "dedup_key": f"corporate:{ticker}:{guid}",
            })
    logger.info("Календарь prime_disclosure: %d событий, %d эмитентов",
                len(out), len({e['ticker'] for e in out}))
    return out


# ----------------------------- ОРКЕСТРАЦИЯ -----------------------------
def refresh_all(db: Session, with_dividends: bool = True) -> dict:
    """Полный пересбор календаря (идемпотентно). Вызывать раз в сутки."""
    res = {}
    try:
        res["bonds"] = _upsert(db, build_bonds(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь bonds: %s", e); res["bonds"] = f"err:{type(e).__name__}"
    try:
        res["expiration"] = _upsert(db, build_futures(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь futures: %s", e); res["expiration"] = f"err:{type(e).__name__}"
    try:
        res["macro"] = _upsert(db, build_macro(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь macro: %s", e); res["macro"] = f"err:{type(e).__name__}"
    try:
        res["rosstat"] = _upsert(db, build_rosstat_releases(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь Росстата: %s", e); res["rosstat"] = f"err:{type(e).__name__}"
    try:
        res["cbr_indcalendar"] = _upsert(db, build_cb_indcalendar(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь ЦБ (.ics): %s", e); res["cbr_indcalendar"] = f"err:{type(e).__name__}"
    try:
        res["ipo"] = _upsert(db, build_ipo(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь ipo: %s", e); res["ipo"] = f"err:{type(e).__name__}"
    try:
        res["corporate"] = _upsert(db, build_corporate(db))
    except Exception as e:  # noqa: BLE001
        res["corporate"] = f"err:{type(e).__name__}"
    try:
        res["ir_calendar"] = _upsert(db, build_ir_calendar(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь ir_calendar: %s", e); res["ir_calendar"] = f"err:{type(e).__name__}"
    try:
        res["prime_disclosure"] = _upsert(db, build_prime_disclosure(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь prime_disclosure: %s", e); res["prime_disclosure"] = f"err:{type(e).__name__}"
    if with_dividends:
        try:
            res["dividends"] = _upsert(db, build_dividends(db))
        except Exception as e:  # noqa: BLE001
            logger.exception("Календарь dividends: %s", e); res["dividends"] = f"err:{type(e).__name__}"
    logger.info("Календарь пересобран: %s", res)
    return res
