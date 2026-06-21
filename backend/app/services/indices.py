"""Live-уровень бенчмарк-индексов (IMOEX/МосБиржа ПД/РТС) для блока «Рынок · пульс».

Live-значение — MOEX ISS (рынок index, без ключей; см. moex_history.fetch_index_live).
Спарклайн и фолбэк уровня — из index_history (наполняется дневным джобом
catch_up_history). Лёгкий TTL-кэш, чтобы не дёргать ISS на каждый рендер страницы.
"""
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.moex_history import BENCHMARK_TICKERS, fetch_index_live

INDEX_NAMES = {
    "IMOEX": "Индекс МосБиржи",
    "MCFTR": "МосБиржа полной доходности",
    "RTSI": "Индекс РТС",
}
INDEX_ORDER = ["IMOEX", "MCFTR", "RTSI"]
SPARK_DAYS = 30

_LIVE_TTL = 120  # сек — live дёргаем не чаще, чем раз в 2 минуты
_live_cache: dict = {"ts": 0.0, "data": {}}


def _live_all() -> dict:
    """Live-значения всех бенчмарков с TTL-кэшем (ISS — сетевой вызов)."""
    now = time.time()
    if now - _live_cache["ts"] < _LIVE_TTL and _live_cache["data"]:
        return _live_cache["data"]
    out = {t: fetch_index_live(t) for t in BENCHMARK_TICKERS}
    _live_cache.update(ts=now, data=out)
    return out


def get_indices(db: Session) -> list[dict]:
    """[{ticker, name, level, change_abs, change_pct, spark[], source, updated}]
    для IMOEX/MCFTR/RTSI. Live — MOEX ISS; при недоступности — последний дневной
    close из index_history с изменением к предыдущему торговому дню."""
    live = _live_all()
    result = []
    for t in INDEX_ORDER:
        rows = db.execute(text(
            "SELECT date, close FROM index_history WHERE ticker = :t "
            "ORDER BY date DESC LIMIT :n"), {"t": t, "n": SPARK_DAYS}).all()
        rows = list(reversed(rows))  # старые → новые
        spark = [float(r[1]) for r in rows]
        last_date = rows[-1][0] if rows else None
        last_close = float(rows[-1][1]) if rows else None
        prev_close = float(rows[-2][1]) if len(rows) >= 2 else None

        lv = live.get(t)
        if lv:
            level = lv["value"]
            change_abs = lv["change_abs"]
            change_pct = lv["change_pct"]
            source = "moex_iss_live"
            updated = lv.get("updatetime")
            # дорисовываем спарклайн до текущего уровня
            if spark:
                if str(lv.get("tradedate")) == str(last_date):
                    spark[-1] = level          # тот же день — уточняем хвост
                else:
                    spark.append(level)        # новый торговый день — добавляем
            else:
                spark = [level]
        elif last_close is not None:
            level = last_close
            change_abs = round(last_close - prev_close, 2) if prev_close else None
            change_pct = round((last_close / prev_close - 1) * 100, 2) if prev_close else None
            source = "index_history"
            updated = str(last_date)
        else:
            continue

        result.append({
            "ticker": t,
            "name": INDEX_NAMES.get(t, t),
            "level": round(level, 2) if level is not None else None,
            "change_abs": change_abs,
            "change_pct": change_pct,
            "spark": spark,
            "source": source,
            "updated": updated,
        })
    return result
