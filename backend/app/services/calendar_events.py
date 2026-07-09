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
    if "закрыти" in d and "реестр" in d:
        return "dividend"   # покрыто build_dividends — пропускаем
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
    операционные), заседания СД, собрания акционеров (ГОСА/ВОСА), IPO. e-disclosure
    закрыт антиботом — smart-lab публичный и парсится. Горизонт фида ~неделя вперёд;
    при суточном пересборе события НАКАПЛИВАЮТСЯ (дедуп не плодит) → растёт форвард-
    календарь. Тикер сопоставляется с нашими компаниями для сектора/портфеля."""
    import httpx, re, hashlib
    out: list[dict] = []
    try:
        r = httpx.get(_SMARTLAB_CAL, timeout=30, headers=_SL_HTTP, follow_redirects=True)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("Календарь корпсобытий: smart-lab недоступен: %s", type(e).__name__)
        return out
    sectors = {c.ticker: c.sector for c in db.query(Company).all()}
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
        if kind in ("dividend", "other"):
            continue  # дивиденды — отдельным билдером; «other» не классифицируем
        ticker = desc.split(":")[0].strip() if ":" in desc else None
        ticker = ticker if (ticker and ticker in sectors) else None
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
        res["ipo"] = _upsert(db, build_ipo(db))
    except Exception as e:  # noqa: BLE001
        logger.exception("Календарь ipo: %s", e); res["ipo"] = f"err:{type(e).__name__}"
    try:
        res["corporate"] = _upsert(db, build_corporate(db))
    except Exception as e:  # noqa: BLE001
        res["corporate"] = f"err:{type(e).__name__}"
    if with_dividends:
        try:
            res["dividends"] = _upsert(db, build_dividends(db))
        except Exception as e:  # noqa: BLE001
            logger.exception("Календарь dividends: %s", e); res["dividends"] = f"err:{type(e).__name__}"
    logger.info("Календарь пересобран: %s", res)
    return res
