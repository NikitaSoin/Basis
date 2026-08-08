"""Дивиденды и безрисковая ставка с MOEX ISS (Этап 3 аналитики портфеля).

Дивиденды: /iss/securities/{TICKER}/dividends.json
  колонки secid, isin, registryclosedate, value, currencyid.
  Берём только RUB-выплаты (валютные у расписок — пропуск с логом).

Безрисковая ставка: кривая бескупонной доходности ОФЗ (G-curve/ZCYC),
  /iss/engines/stock/zcyc.json — блок yearyields отдаёт ГОТОВЫЕ точки
  кривой по срокам; берём period=1.00 (1 год). Выбор обоснован: точка
  кривой не зависит от конкретного выпуска ОФЗ (не надо перебирать бумаги
  по мере погашения), короткий конец без процентного риска длинных бумаг.
  Фолбэк: при недоступности — остаётся последнее сохранённое значение
  в market_params (+ лог), не падаем.
"""
import json
import logging
import ssl
import time
import urllib.request
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

DIVIDENDS_URL = "https://iss.moex.com/iss/securities/{ticker}/dividends.json?iss.meta=off"
ZCYC_URL = "https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields"

REQUEST_PAUSE = 0.2

_UPSERT_DIV_SQL = text("""
    INSERT INTO dividends (ticker, record_date, amount, currency)
    VALUES (:ticker, :record_date, :amount, :currency)
    ON CONFLICT (ticker, record_date, amount) DO NOTHING
""")

_UPSERT_PARAM_SQL = text("""
    INSERT INTO market_params (key, value, as_of, note, updated_at)
    VALUES (:key, :value, :as_of, :note, :now)
    ON CONFLICT (key) DO UPDATE SET
        value = EXCLUDED.value, as_of = EXCLUDED.as_of,
        note = EXCLUDED.note, updated_at = EXCLUDED.updated_at
""")


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as resp:
        return json.loads(resp.read())


def fetch_dividends(ticker: str) -> list[dict]:
    """История выплат одной бумаги: [{record_date, amount, currency}]."""
    data = _get_json(DIVIDENDS_URL.format(ticker=ticker))
    cols = data["dividends"]["columns"]
    out = []
    for row in data["dividends"]["data"]:
        r = dict(zip(cols, row))
        if not r.get("registryclosedate") or r.get("value") in (None, 0):
            continue
        out.append({
            "record_date": r["registryclosedate"],
            "amount": float(r["value"]),
            "currency": (r.get("currencyid") or "RUB").upper(),
        })
    return out


def sync_dividends_for(db: Session, ticker: str) -> tuple[int, int]:
    """Заливает выплаты одной бумаги. Возвращает (записано RUB, пропущено валютных)."""
    rows = fetch_dividends(ticker)
    written = skipped_fx = 0
    for r in rows:
        if r["currency"] != "RUB":
            skipped_fx += 1
            continue
        db.execute(_UPSERT_DIV_SQL, {"ticker": ticker, **r})
        written += 1
    return written, skipped_fx


def load_dividends_map(db: Session, ticker: str) -> dict[date, float]:
    """{дата отсечки: сумма на акцию} для расчёта total return."""
    rows = db.execute(
        text("SELECT record_date, amount FROM dividends WHERE ticker = :t"), {"t": ticker}
    ).all()
    out: dict[date, float] = {}
    for r in rows:
        out[r.record_date] = out.get(r.record_date, 0.0) + float(r.amount)
    return out


def update_risk_free_rate(db: Session) -> float | None:
    """Точки «1 год» и «10 лет» кривой бескупонной доходности ОФЗ → market_params
    (один и тот же ответ ISS, без лишнего запроса). 1г — для риск-метрик облигаций
    (короткий конец, без процентного риска длинных бумаг). 10л — для DCF/CAPM акций
    (см. live_wacc.py): именно этот тенор зашивает financial-analyst как Rf в
    config/market_params.json ("Доходность 10-летних ОФЗ").

    При недоступности ISS остаётся последнее сохранённое значение (фолбэк)."""
    try:
        data = _get_json(ZCYC_URL)
        cols = data["yearyields"]["columns"]
        rows = [dict(zip(cols, r)) for r in data["yearyields"]["data"]]
        point_1y = next((r for r in rows if float(r["period"]) == 1.0), None)
        if not point_1y or point_1y.get("value") is None:
            raise ValueError("точка period=1.00 не найдена в yearyields")
        rate = float(point_1y["value"])
        as_of = point_1y.get("tradedate")
        db.execute(_UPSERT_PARAM_SQL, {
            "key": "risk_free_1y", "value": rate, "as_of": as_of,
            "note": "Доходность ОФЗ ~1 год, точка G-curve (ZCYC) MOEX",
            "now": datetime.now(timezone.utc),
        })
        # Точка 10 лет — линейная интерполяция по той же кривой (period может не
        # быть ровно 10.0 в ответе ISS), тем же методом, что live_wacc.py/moex_bonds.py.
        curve = sorted((float(r["period"]), float(r["value"])) for r in rows if r.get("value") is not None)
        rate_10y = None
        if curve:
            years = 10.0
            if years <= curve[0][0]:
                rate_10y = curve[0][1]
            elif years >= curve[-1][0]:
                rate_10y = curve[-1][1]
            else:
                for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
                    if x0 <= years <= x1:
                        rate_10y = y0 + (y1 - y0) * (years - x0) / (x1 - x0)
                        break
        if rate_10y is not None:
            db.execute(_UPSERT_PARAM_SQL, {
                "key": "risk_free_10y", "value": rate_10y, "as_of": as_of,
                "note": "Доходность ОФЗ ~10 лет (интерполяция G-curve/ZCYC MOEX) — Rf для DCF/CAPM акций",
                "now": datetime.now(timezone.utc),
            })
        # ПОЛНАЯ G-кривая (все точки yearyields) — для BFV-D нужен z_dur на СРОКЕ
        # эффективной дюрации потока (~8-10 лет), а не механическая десятилетка
        # (методика §11). Храним весь ряд [[срок, доходность_дробью], ...] в market_params
        # как JSON-строку в note (value = число точек) — тот же кэш, что risk_free_*,
        # обновляется этим же еженедельным кроном. curve уже в долях (value ISS в %? —
        # нет, ZCYC value в процентах; здесь curve собран из float(value), это проценты).
        if curve:
            import json as _json
            curve_frac = [[round(p, 3), round(v / 100.0, 6)] for p, v in curve]
            db.execute(_UPSERT_PARAM_SQL, {
                "key": "ofz_curve", "value": float(len(curve_frac)), "as_of": as_of,
                "note": _json.dumps(curve_frac),
                "now": datetime.now(timezone.utc),
            })
        db.commit()
        logger.info("Безрисковая ставка: ОФЗ-1г %.2f%%, ОФЗ-10л %s на %s (G-curve)",
                    rate, f"{rate_10y:.2f}%" if rate_10y is not None else "н/д", as_of)
        return rate
    except Exception as e:
        prev = db.execute(
            text("SELECT value, as_of FROM market_params WHERE key='risk_free_1y'")
        ).first()
        logger.warning("Ставка ОФЗ: ISS недоступен (%s) — остаёмся на последней: %s", e,
                       f"{prev.value}% от {prev.as_of}" if prev else "значения нет")
        return float(prev.value) if prev else None


def get_market_param(db: Session, key: str) -> tuple[float, date | None] | None:
    row = db.execute(
        text("SELECT value, as_of FROM market_params WHERE key = :k"), {"k": key}
    ).first()
    return (float(row.value), row.as_of) if row else None


def sync_dividends_from_listing(db: Session) -> dict:
    """Пополнить историю выплат ОБЪЯВЛЕННЫМИ дивидендами из листинга (rates.csv).

    🔴 Зачем. Основной источник истории — ISS /securities/{T}/dividends.json — ПЕРЕСТАЛ
    отдавать свежие выплаты: на бою 2026-08-08 в таблице ноль записей за последние
    200 дней, последняя от 14.10.2025, а у LKOH ISS обрывается на 03.06.2025. При этом
    поля листинга REGISTRYCLOSEDATE + DIVIDENDVALUE (rates.csv) дату отсечки и сумму
    дают — на них уже живёт дивидендный КАЛЕНДАРЬ. То есть данные у нас были, просто
    в историю не переносились: календарь смотрит вперёд, а таблица выплат — назад,
    и между ними не было моста.

    Переносим только ПРОШЕДШИЕ отсечки: будущая — это анонс, а не выплата, ей место
    в календаре. Существующие записи не трогаем (ISS остаётся первоисточником там,
    где он ещё отдаёт данные).
    """
    from app.services.calendar_events import _rates_csv_dividends
    today = date.today()
    have = {(t, d) for t, d in db.execute(text("SELECT ticker, record_date FROM dividends"))}
    added, skipped_future = 0, 0
    for r in _rates_csv_dividends():
        try:
            rec = date.fromisoformat(r["record_date"])
        except (ValueError, TypeError):
            continue
        if rec > today:
            skipped_future += 1
            continue
        if (r["ticker"], rec) in have:
            continue
        db.execute(text("INSERT INTO dividends (ticker, record_date, amount, currency) "
                        "VALUES (:t, :d, :a, 'RUB')"),
                   {"t": r["ticker"], "d": rec, "a": r["amount"]})
        added += 1
    if added:
        db.commit()
    logger.info("Дивиденды из листинга: добавлено %d, впереди (анонсы) %d", added, skipped_future)
    return {"added": added, "announced_ahead": skipped_future}
