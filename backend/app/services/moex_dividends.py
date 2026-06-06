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
    """Точка «1 год» кривой бескупонной доходности ОФЗ → market_params.

    При недоступности ISS остаётся последнее сохранённое значение (фолбэк)."""
    try:
        data = _get_json(ZCYC_URL)
        cols = data["yearyields"]["columns"]
        rows = [dict(zip(cols, r)) for r in data["yearyields"]["data"]]
        point = next((r for r in rows if float(r["period"]) == 1.0), None)
        if not point or point.get("value") is None:
            raise ValueError("точка period=1.00 не найдена в yearyields")
        rate = float(point["value"])
        as_of = point.get("tradedate")
        db.execute(_UPSERT_PARAM_SQL, {
            "key": "risk_free_1y", "value": rate, "as_of": as_of,
            "note": "Доходность ОФЗ ~1 год, точка G-curve (ZCYC) MOEX",
            "now": datetime.now(timezone.utc),
        })
        db.commit()
        logger.info("Безрисковая ставка: ОФЗ-1г %.2f%% на %s (G-curve)", rate, as_of)
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
