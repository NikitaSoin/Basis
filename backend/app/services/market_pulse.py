"""Блок «Обзор рынка» Обозревателя (2026-07-11) — индексы, ставки, сырьё,
драгметаллы + индекс страха и жадности Basis.

Индексы/ставки — тот же live+index_history паттерн, что уже отработан в
indices.py (для маленького пульс-чипа раздела «Рынок»), но шире по набору
тикеров (MARKET_PULSE_TICKERS в moex_history.py) и с явным разделением
семантики: ценовые индексы (уровень, изменение в %) vs ставки денежного рынка
(RUSFAR — годовая ставка в %, "изменение" — не то же самое, что у индекса).
Нефть — нет спот-индекса на MOEX (физическая нефть не торгуется на бирже),
используем ближайший неэкспирировавший фьючерс Brent (тот же прокси, что
обычно используют финансовые медиа — «цена нефти» = цена ближнего фьючерса).
Драгметаллы — переиспользуем spot_assets (moex_spot.py), отдельный пайплайн
уже есть.
"""
import time
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.moex_history import fetch_index_live

SECTOR_INDEX_NAMES = {
    "MOEXOG": "Нефть и газ",
    "MOEXEU": "Электроэнергетика",
    "MOEXTL": "Телекоммуникации",
    "MOEXCH": "Химия и нефтехимия",
    "MOEXMM": "Металлы и добыча",
    "MOEXFN": "Финансы",
    "MOEXCN": "Потребительский сектор",
    "MOEXIT": "Информационные технологии",
    "MOEXTN": "Транспорт",
    "MOEXRE": "Строительные компании",
}
SECTOR_ORDER = list(SECTOR_INDEX_NAMES)

PULSE_INDEX_NAMES = {
    "IMOEX": "Индекс МосБиржи",
    "MCFTR": "МосБиржа полной доходности",
    "RTSI": "Индекс РТС",
    "RGBI": "Индекс гособлигаций (RGBI)",
}
PULSE_INDEX_ORDER = list(PULSE_INDEX_NAMES)

RATE_NAMES = {
    "RUSFAR": "RUSFAR · руб. (o/n)",
    "RUSFARCNY": "RUSFAR CNY · юань (o/n)",
}
RATE_ORDER = list(RATE_NAMES)

SPARK_DAYS = 30
_LIVE_TTL = 120  # сек
_live_cache: dict = {}


def _live(ticker: str) -> dict | None:
    now = time.time()
    c = _live_cache.get(ticker)
    if c and now - c["ts"] < _LIVE_TTL:
        return c["data"]
    data = fetch_index_live(ticker)
    _live_cache[ticker] = {"ts": now, "data": data}
    return data


def _snapshot(db: Session, ticker: str, name: str, days: int = SPARK_DAYS) -> dict | None:
    """Live-уровень (MOEX ISS) + спарклайн из index_history; фолбэк на последний
    дневной close, если live недоступен (та же логика, что indices.get_indices)."""
    rows = db.execute(text(
        "SELECT date, close FROM index_history WHERE ticker=:t ORDER BY date DESC LIMIT :n"),
        {"t": ticker, "n": days}).all()
    rows = list(reversed(rows))
    spark = [float(r[1]) for r in rows]
    last_date = rows[-1][0] if rows else None
    last_close = float(rows[-1][1]) if rows else None
    prev_close = float(rows[-2][1]) if len(rows) >= 2 else None

    lv = _live(ticker)
    if lv:
        level = lv["value"]
        change_abs = lv["change_abs"]
        change_pct = lv["change_pct"]
        source = "moex_iss_live"
        updated = lv.get("updatetime")
        if spark:
            if str(lv.get("tradedate")) == str(last_date):
                spark[-1] = level
            else:
                spark.append(level)
        else:
            spark = [level]
    elif last_close is not None:
        level = last_close
        change_abs = round(last_close - prev_close, 4) if prev_close else None
        change_pct = round((last_close / prev_close - 1) * 100, 2) if prev_close else None
        source = "index_history"
        updated = str(last_date)
    else:
        return None

    return {
        "ticker": ticker, "name": name,
        "level": round(level, 4) if level is not None else None,
        "change_abs": change_abs, "change_pct": change_pct,
        "spark": spark, "source": source, "updated": updated,
    }


def _oil_snapshot(db) -> dict | None:
    """Ближайший неэкспирировавший фьючерс на нефть Brent (asset_code='BR') как
    прокси спот-цены — на MOEX физическая нефть не торгуется, это стандартная
    практика (та же логика, что «цена нефти» в финансовых медиа = цена ближнего
    фьючерса)."""
    from app.models.future import Future
    today = date.today()
    f = (db.query(Future)
         .filter(Future.asset_code == "BR", (Future.expiration_date.is_(None)) | (Future.expiration_date >= today))
         .order_by(Future.expiration_date.asc().nullslast())
         .first())
    if not f or f.last_price is None:
        return None
    last = float(f.last_price)
    prev = float(f.prev_settle) if f.prev_settle is not None else None
    change_pct = round((last / prev - 1) * 100, 2) if prev else None
    return {
        "ticker": f.secid, "name": "Нефть Brent",
        "level": last, "change_pct": change_pct,
        "unit": "$", "note": f"ближайший фьючерс {f.secid}, эксп. {f.expiration_date}",
        "source": "futures_proxy",
    }


def _metals_snapshot(db) -> list[dict]:
    """Драгметаллы — переиспользуем spot_assets (уже собирается moex_spot.py)."""
    rows = db.execute(text(
        "SELECT secid, name, last_price, change_pct FROM spot_assets WHERE kind='metal' ORDER BY secid")).all()
    return [{"ticker": r[0], "name": r[1], "level": float(r[2]) if r[2] is not None else None,
             "change_pct": float(r[3]) if r[3] is not None else None, "unit": "₽/г"} for r in rows]


def get_market_overview(db: Session) -> dict:
    indices = [s for t in PULSE_INDEX_ORDER if (s := _snapshot(db, t, PULSE_INDEX_NAMES[t]))]
    sectors = [s for t in SECTOR_ORDER if (s := _snapshot(db, t, SECTOR_INDEX_NAMES[t]))]
    rates = [s for t in RATE_ORDER if (s := _snapshot(db, t, RATE_NAMES[t]))]
    return {
        "indices": indices,
        "sectors": sectors,
        "rates": rates,
        "oil": _oil_snapshot(db),
        "metals": _metals_snapshot(db),
    }


# ────────────────────── индекс страха и жадности (v0) ──────────────────────
# Методика — по образцу конкурента (Инвестминт), конкурентный разбор 2026-07-11:
# композит 0-100 из 4 равновесных компонент, только открытые данные MOEX. Это
# ОЦЕНКА/МОДЕЛЬ Basis (не факт) — нормировка v0 линейная по разумным диапазонам
# (не полный перцентиль по годовой истории, как у образца — для этого нужен
# отдельный тяжёлый батч-расчёт по каждому дню года; тот же подход, что уже
# используется в «Композитная оценка Basis v0» скринера — предварительная
# методика, уточняется). Индикатор настроений, НЕ торговый сигнал.
_BLUE_CHIPS = ["SBER", "LKOH", "GAZP", "YDEX", "T", "TATN", "GMKN", "NVTK",
               "PLZL", "OZON", "VTBR", "X5", "ROSN", "SNGS", "MOEX"]


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def _series(db, ticker: str, days: int) -> list[float]:
    rows = db.execute(text(
        "SELECT close FROM index_history WHERE ticker=:t ORDER BY date DESC LIMIT :n"),
        {"t": ticker, "n": days}).all()
    return [float(r[0]) for r in reversed(rows)]


def _momentum_score(db) -> tuple[float | None, dict]:
    """IMOEX относительно своей MA125 — импульс рынка. >MA = аппетит к риску."""
    closes = _series(db, "IMOEX", 130)
    if len(closes) < 30:
        return None, {"note": "недостаточно истории IMOEX для MA125"}
    window = closes[-125:] if len(closes) >= 125 else closes
    ma = sum(window) / len(window)
    last = closes[-1]
    ratio_pct = (last / ma - 1) * 100 if ma else 0
    score = _clamp(50 + (ratio_pct / 10) * 50)
    return score, {"imoex": round(last, 1), "ma": round(ma, 1), "vs_ma_pct": round(ratio_pct, 2),
                    "window_days": len(window)}


def _volatility_score(db) -> tuple[float | None, dict]:
    """RVI (индекс волатильности РФ) — выше волатильность = больше страха."""
    closes = _series(db, "RVI", 5)
    if not closes:
        return None, {"note": "нет данных RVI"}
    rvi = closes[-1]
    # РИапазон типичных значений RVI (спокойный рынок ~20, паника 60+) —
    # эмпирическая калибровка v0, не перцентиль по истории.
    score = _clamp(100 - (rvi - 20) / 40 * 100)
    return score, {"rvi": round(rvi, 2)}


def _breadth_score(db) -> tuple[float | None, dict]:
    """Доля голубых фишек с положительной доходностью за 20 торговых дней —
    прокси «ширины рынка» (сколько бумаг участвует в движении, не только
    индекс-тяжеловесы)."""
    from app.models.company import Company, Quote
    up = 0
    total = 0
    for ticker in _BLUE_CHIPS:
        c = db.query(Company).filter(Company.ticker == ticker).first()
        if not c:
            continue
        rows = db.execute(text(
            "SELECT close FROM quotes WHERE company_id=:cid ORDER BY date DESC LIMIT 21"),
            {"cid": c.id}).all()
        if len(rows) < 21:
            continue
        last = float(rows[0][0])
        prior = float(rows[20][0])
        total += 1
        if last > prior:
            up += 1
    if total == 0:
        return None, {"note": "нет данных по голубым фишкам"}
    pct = up / total * 100
    return pct, {"up": up, "total": total, "pct": round(pct, 1)}


def _risk_appetite_score(db) -> tuple[float | None, dict]:
    """МосБиржа полной доходности (акции) vs RGBI (гособлигации) за 20 торговых
    дней — куда идут деньги: в риск (акции) или в защиту (госдолг)."""
    mcftr = _series(db, "MCFTR", 21)
    rgbi = _series(db, "RGBI", 21)
    if len(mcftr) < 21 or len(rgbi) < 21:
        return None, {"note": "недостаточно истории MCFTR/RGBI за 20 дней"}
    mc_ret = (mcftr[-1] / mcftr[0] - 1) * 100
    rg_ret = (rgbi[-1] / rgbi[0] - 1) * 100
    spread = mc_ret - rg_ret
    score = _clamp(50 + spread * 10)
    return score, {"mcftr_20d_pct": round(mc_ret, 2), "rgbi_20d_pct": round(rg_ret, 2), "spread_pp": round(spread, 2)}


_LEVELS = [
    (20, "Крайний страх"), (40, "Страх"), (60, "Нейтрально"), (80, "Жадность"), (101, "Крайняя жадность"),
]


def _level_label(score: float) -> str:
    for threshold, label in _LEVELS:
        if score < threshold:
            return label
    return "Крайняя жадность"


def get_fear_greed(db: Session) -> dict:
    parts = {
        "momentum": _momentum_score(db),
        "volatility": _volatility_score(db),
        "breadth": _breadth_score(db),
        "risk_appetite": _risk_appetite_score(db),
    }
    valid = {k: v[0] for k, v in parts.items() if v[0] is not None}
    if not valid:
        return {"score": None, "label": None, "components": {}, "note": "недостаточно данных"}
    score = round(sum(valid.values()) / len(valid), 1)
    return {
        "score": score,
        "label": _level_label(score),
        "components": {k: {"score": round(v[0], 1) if v[0] is not None else None, "detail": v[1]} for k, v in parts.items()},
        "coverage": f"{len(valid)}/4 компонент",
        "methodology_note": "Индикатор настроений рынка Basis (v0, оценка/модель, не торговый сигнал) — среднее 4 компонент: импульс IMOEX к MA125, волатильность RVI, ширина рынка (доля голубых фишек в плюсе за 20 дней), спрос на риск (МосБиржа ПД vs RGBI за 20 дней). Нормировка v0 — эмпирические диапазоны, не полный перцентиль по годовой истории; уточняется.",
    }
