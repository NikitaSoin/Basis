"""Дневная история цен облигаций/фьючерсов/фондов/валюты-металлов с MOEX ISS →
instrument_history.

Один движок на четыре класса. Источник — официальная история MOEX ISS (без ключей):
эндпоинт «вся доска за дату» (?date=) отдаёт все бумаги доски одним запросом —
это на порядок дешевле, чем дёргать каждую бумагу отдельно.

  - облигации: stock/bonds, борды TQOB/TQCB/TQOY/TQOD/TQRD (CLOSE % номинала,
    YIELDCLOSE — YTM, ACCINT — НКД);
  - фонды:     stock/shares, борды TQTF/TQIF/TQBR (обычный OHLC);
  - фьючерсы:  futures/forts, весь рынок (CLOSE/SETTLEPRICE/OPENPOSITION — ОИ);
  - валюта/металлы: currency/selt, борд CETS (обычный OHLC; курируемый список
    инструментов — те же 6, что в moex_spot.SPOT_INSTRUMENTS).

Складываем ТОЛЬКО бумаги, которые есть в наших метаданных (bonds/futures/funds/
spot_assets), чтобы не засорять таблицу мёртвыми/неотслеживаемыми выпусками.
Идемпотентно (ON CONFLICT asset_class+secid+date). Метаданные НЕ дублируем —
связь по secid.
"""
import logging
import time
from datetime import date as date_type, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.moex_history import REQUEST_PAUSE, _get_json

logger = logging.getLogger(__name__)

_ISS = "https://iss.moex.com/iss/history/engines/{engine}/markets/{market}"

# asset_class → (engine, market, boards | None).  None = весь рынок (фьючерсы).
# ВАЖНО: MOEX перевёл ETF/БПИФ с борда TQTF на TQBR (общий борд «Акции и ДР»)
# 2026-06-22 (TQTF с этой даты is_traded=0, listed_till=2026-06-22 — проверено
# напрямую в ISS). TQBR отдаёт ВСЮ доску (тысячи строк акций+фондов одним
# вызовом), но load_range уже фильтрует по known_secids(fund) — фонды
# корректно вычленяются, лишнее не сохраняется. TQTF/TQIF оставлены для
# бэкафилла дат ДО перевода (там у них ещё есть история).
SOURCES: dict[str, tuple[str, str, list[str] | None]] = {
    "bond":   ("stock",    "bonds",  ["TQOB", "TQCB", "TQOY", "TQOD", "TQRD"]),
    "fund":   ("stock",    "shares", ["TQTF", "TQIF", "TQBR"]),
    "future": ("futures",  "forts",  None),
    "spot":   ("currency", "selt",   ["CETS"]),
}

_META_TABLE = {"bond": "bonds", "fund": "funds", "future": "futures", "spot": "spot_assets"}

_UPSERT = text("""
    INSERT INTO instrument_history
        (asset_class, secid, date, open, close, high, low, value, yld, accrued_int, settle, oi)
    VALUES
        (:asset_class, :secid, :date, :open, :close, :high, :low, :value, :yld, :accrued_int, :settle, :oi)
    ON CONFLICT (asset_class, secid, date) DO UPDATE SET
        open        = COALESCE(EXCLUDED.open,        instrument_history.open),
        close       = COALESCE(EXCLUDED.close,       instrument_history.close),
        high        = COALESCE(EXCLUDED.high,        instrument_history.high),
        low         = COALESCE(EXCLUDED.low,         instrument_history.low),
        value       = COALESCE(EXCLUDED.value,       instrument_history.value),
        yld         = COALESCE(EXCLUDED.yld,         instrument_history.yld),
        accrued_int = COALESCE(EXCLUDED.accrued_int, instrument_history.accrued_int),
        settle      = COALESCE(EXCLUDED.settle,      instrument_history.settle),
        oi          = COALESCE(EXCLUDED.oi,          instrument_history.oi)
""")


def _num(r: dict, *keys):
    for k in keys:
        v = r.get(k)
        if v not in (None, ""):
            return v
    return None


def known_secids(db: Session, asset_class: str) -> set[str]:
    table = _META_TABLE[asset_class]
    return {row[0] for row in db.execute(text(f"SELECT secid FROM {table}")).all()}


def _fetch_board_date(engine: str, market: str, board: str | None, d: date_type) -> list[dict]:
    """ISS отдаёт максимум 100 строк за вызов (own pagination, start=). Доски
    покрупнее (TQCB ~300+/день, весь рынок FORTS ~780+/день) молча обрезались
    до первых 100 — часть бумаг (по алфавиту/внутренней сортировке ISS дальше
    100-й) НИКОГДА не попадала в instrument_history. Отсюда «серые» плитки на
    карте рынка облигаций/фьючерсов и дыры в графиках цены — не проблема
    ликвидности бумаги, а недокачка. Долистываем start=0,100,200... до пустой
    страницы."""
    base = _ISS.format(engine=engine, market=market)
    suffix = f"/boards/{board}/securities.json" if board else "/securities.json"
    out = []
    start = 0
    while True:
        url = f"{base}{suffix}?iss.meta=off&date={d.isoformat()}&start={start}"
        data = _get_json(url)
        cols = data["history"]["columns"]
        rows = data["history"]["data"]
        if not rows:
            break
        out.extend(dict(zip(cols, r)) for r in rows)
        if len(rows) < 100:
            break
        start += 100
        time.sleep(REQUEST_PAUSE)
    return out


def _map_row(asset_class: str, r: dict) -> dict | None:
    secid = r.get("SECID")
    if not secid:
        return None
    close = _num(r, "CLOSE", "LEGALCLOSEPRICE")
    settle = _num(r, "SETTLEPRICE") if asset_class == "future" else None
    # пустой торговый день (нет сделок и нет расчётной) — пропускаем
    if (close in (None, 0) or float(close) == 0) and not settle:
        return None
    return {
        "asset_class": asset_class,
        "secid": secid,
        "date": r.get("TRADEDATE"),
        "open": _num(r, "OPEN"),
        "close": close if (close not in (None, 0) and float(close) != 0) else None,
        "high": _num(r, "HIGH"),
        "low": _num(r, "LOW"),
        "value": _num(r, "VOLRUR", "VALUE", "VALTODAY"),
        "yld": _num(r, "YIELDCLOSE", "YIELD") if asset_class == "bond" else None,
        "accrued_int": _num(r, "ACCINT") if asset_class == "bond" else None,
        "settle": settle,
        "oi": _num(r, "OPENPOSITION") if asset_class == "future" else None,
    }


def load_range(db: Session, asset_class: str, date_from: date_type, date_till: date_type,
               allowed: set[str] | None = None, sleep: float = REQUEST_PAUSE) -> int:
    """Грузит историю одного класса за период [date_from, date_till] по дням
    (по будням; выходные/праздники MOEX отдаёт пусто). allowed — белый список SECID
    (по умолчанию — все из метаданных класса)."""
    engine, market, boards = SOURCES[asset_class]
    if allowed is None:
        allowed = known_secids(db, asset_class)
    written = 0
    d = date_from
    while d <= date_till:
        if d.weekday() < 5:  # пн-пт
            for board in (boards or [None]):
                try:
                    raw_rows = _fetch_board_date(engine, market, board, d)
                except Exception as e:
                    logger.warning("instr-hist %s %s %s: %s", asset_class, board, d, e)
                    raw_rows = []
                for raw in raw_rows:
                    if raw.get("SECID") not in allowed:
                        continue
                    m = _map_row(asset_class, raw)
                    if m:
                        db.execute(_UPSERT, m)
                        written += 1
                time.sleep(sleep)
        d += timedelta(days=1)
    db.commit()
    return written


_VALID = set(SOURCES)


def get_history(db: Session, asset_class: str, secid: str, days: int = 180) -> dict:
    """Временной ряд одной бумаги для графика: точки (date, close, +доп. поля класса)
    + дельта последнего дня. Пустой ряд — points:[] (фронт покажет «нет истории»)."""
    if asset_class not in _VALID:
        return {"asset_class": asset_class, "secid": secid, "points": []}
    start = date_type.today() - timedelta(days=days)
    rows = db.execute(text(
        "SELECT date, open, close, high, low, value, yld, accrued_int, settle, oi "
        "FROM instrument_history WHERE asset_class=:ac AND secid=:s AND date>=:d "
        "ORDER BY date ASC"), {"ac": asset_class, "s": secid, "d": start}).all()
    pts = []
    for r in rows:
        m = r._mapping
        p = {"date": str(m["date"]), "close": _flt(m["close"])}
        if asset_class == "bond":
            p["yld"] = _flt(m["yld"]); p["accrued_int"] = _flt(m["accrued_int"])
        elif asset_class == "future":
            p["settle"] = _flt(m["settle"]); p["oi"] = m["oi"]
        pts.append(p)
    # Эффективная цена точки: close, а если его нет (частый случай для
    # фьючерсов — close пуст почти везде, торгуется по settle) — settle.
    eff = [p["close"] if p["close"] is not None else p.get("settle") for p in pts]
    eff = [v for v in eff if v is not None]
    last = eff[-1] if eff else None
    prev = eff[-2] if len(eff) >= 2 else None
    change_pct = round((last / prev - 1) * 100, 2) if last and prev else None
    return {"asset_class": asset_class, "secid": secid, "last": last,
            "change_pct": change_pct, "points": pts}


def get_sparklines(db: Session, asset_class: str, secids: list[str], days: int = 30) -> dict:
    """{secid: {spark:[close...], last, change_pct}} батчем — для мини-графиков
    в таблицах/карточках экрана «Рынок» (один запрос на список бумаг)."""
    if asset_class not in _VALID or not secids:
        return {}
    start = date_type.today() - timedelta(days=days)
    rows = db.execute(text(
        "SELECT secid, date, close FROM instrument_history "
        "WHERE asset_class=:ac AND secid = ANY(:ids) AND date>=:d AND close IS NOT NULL "
        "ORDER BY secid, date ASC"),
        {"ac": asset_class, "ids": list(secids), "d": start}).all()
    by: dict[str, list[float]] = {}
    for r in rows:
        by.setdefault(r._mapping["secid"], []).append(_flt(r._mapping["close"]))
    out = {}
    for s, closes in by.items():
        last = closes[-1] if closes else None
        prev = closes[-2] if len(closes) >= 2 else None
        out[s] = {"spark": closes, "last": last,
                  "change_pct": round((last / prev - 1) * 100, 2) if last and prev else None}
    return out


def _flt(v):
    return float(v) if v is not None else None


def catch_up_instrument_history(days_back: int = 14) -> None:
    """Ежедневная докачка истории по всем классам (последние days_back дней).
    Вызывается из вечернего _history_job после акций/индексов."""
    from app.db.session import SessionLocal

    today = date_type.today()
    start = today - timedelta(days=days_back)
    db = SessionLocal()
    try:
        total = 0
        for ac in SOURCES:
            n = load_range(db, ac, start, today)
            total += n
            logger.info("instr-hist докачка %s: %d строк", ac, n)
        logger.info("instr-hist докачка завершена: %d строк за %d дн.", total, days_back)
    except Exception as e:
        logger.exception("instr-hist докачка: ошибка %s", e)
        db.rollback()
    finally:
        db.close()


def backfill_instrument_history(days_back: int = 365) -> None:
    """Первичный бэкафилл глубины для графиков (one-shot, идемпотентно).
    На бою вызывается из startup, если таблица пуста."""
    from app.db.session import SessionLocal

    today = date_type.today()
    start = today - timedelta(days=days_back)
    db = SessionLocal()
    try:
        for ac in SOURCES:
            n = load_range(db, ac, start, today)
            logger.info("instr-hist бэкафилл %s: %d строк за %d дн.", ac, n, days_back)
    except Exception as e:
        logger.exception("instr-hist бэкафилл: ошибка %s", e)
        db.rollback()
    finally:
        db.close()
