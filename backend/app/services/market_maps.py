"""Карты рынка (Обозреватель, Направление 6) — чистый расчёт, без LLM.

Две карты:
- Тепловая: цвет по изменению цены за период (сутки/неделя/месяц).
- Недооценённость: цвет по апсайду к МОДЕЛЬНОЙ справедливой цене,
  upside = (fair_value − live_price)/live_price. БЕЗ сигналов.

Источники (переиспользуем готовое, без дублирования методики):
- live-цена и дневное изменение — tinkoff_quotes (как в /quotes/realtime, с кэшем);
- история закрытий (неделя/месяц) — таблица quotes (дневные close, глубина с 2016);
- справедливая цена — financials.json карточки (valuation.fair_value_range.base),
  тот же файл, что рендерит блок «Финансы»; апсайд считается ЖИВЬЁМ от текущей цены;
- сектор и капитализация — таблица companies.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.services import tinkoff_quotes

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"
_PERIOD_DAYS = {"week": 7, "month": 30}


# ----------------------------- источники -----------------------------
def _live_prices() -> dict[str, dict]:
    """Живые котировки (Tinkoff, с кэшем). {ticker: {price, change_pct, ...}}."""
    try:
        if tinkoff_quotes.is_configured():
            tinkoff_quotes.refresh_prices()
        if tinkoff_quotes.is_available():
            return tinkoff_quotes.get_all_prices() or {}
    except Exception:  # noqa: BLE001 — карты не должны падать из-за котировок
        pass
    return {}


def _fair_value(ticker: str) -> float | None:
    """Базовая модельная справедливая цена из financials.json карточки (без дублирования
    методики — тот же файл, что и блок «Финансы»)."""
    path = COMPANIES_DIR / ticker.upper() / "financials.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        fv = (d.get("valuation") or {}).get("fair_value_range") or {}
        base = fv.get("base")
        return float(base) if base is not None else None
    except Exception:  # noqa: BLE001
        return None


def _latest_closes(db: Session) -> dict[str, dict]:
    """Последний close и дневное change_pct из БД (fallback к live). {ticker: {...}}."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (q.company_id) c.ticker, q.close, q.change_pct
        FROM quotes q JOIN companies c ON c.id = q.company_id
        WHERE q.close IS NOT NULL
        ORDER BY q.company_id, q.date DESC
    """)).fetchall()
    return {r.ticker: {"close": float(r.close),
                       "change_pct": float(r.change_pct) if r.change_pct is not None else None}
            for r in rows}


def _closes_asof(db: Session, target: date) -> dict[str, float]:
    """Close на последнюю торговую дату ≤ target (для недели/месяца). {ticker: close}."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (q.company_id) c.ticker, q.close
        FROM quotes q JOIN companies c ON c.id = q.company_id
        WHERE q.close IS NOT NULL AND q.date <= :target
        ORDER BY q.company_id, q.date DESC
    """), {"target": target}).fetchall()
    return {r.ticker: float(r.close) for r in rows}


def _companies(db: Session, tickers_filter: set[str] | None) -> list[Company]:
    q = db.query(Company)
    rows = q.all()
    if tickers_filter is not None:
        rows = [c for c in rows if c.ticker in tickers_filter]
    return rows


def _now_price(ticker: str, live: dict, latest: dict) -> float | None:
    lq = live.get(ticker)
    if lq and lq.get("price") is not None:
        return float(lq["price"])
    lc = latest.get(ticker)
    return lc["close"] if lc else None


# ----------------------------- карты -----------------------------
def heatmap(db: Session, period: str = "day", tickers_filter: set[str] | None = None) -> dict:
    """Тепловая карта: цвет — изменение цены за период. Группировка по секторам."""
    period = period if period in ("day", "week", "month") else "day"
    live = _live_prices()
    latest = _latest_closes(db)
    lookback = None
    if period in _PERIOD_DAYS:
        target = date.today() - timedelta(days=_PERIOD_DAYS[period])
        lookback = _closes_asof(db, target)

    by_sector: dict[str, list] = {}
    for c in _companies(db, tickers_filter):
        change = None
        if period == "day":
            lq = live.get(c.ticker)
            if lq and lq.get("change_pct") is not None:
                change = float(lq["change_pct"])
            else:
                lc = latest.get(c.ticker)
                change = lc["change_pct"] if lc else None
        else:
            now = _now_price(c.ticker, live, latest)
            then = (lookback or {}).get(c.ticker)
            if now is not None and then:
                change = (now - then) / then * 100.0
        if change is None:
            continue
        sector = c.sector or "Прочее"
        by_sector.setdefault(sector, []).append({
            "ticker": c.ticker, "name": c.name, "sector": sector,
            "market_cap": float(c.market_cap) if c.market_cap is not None else None,
            "change_pct": round(change, 2),
        })

    sectors = _pack_sectors(by_sector)
    return {"map": "heatmap", "period": period, "sectors": sectors,
            "count": sum(len(s["tiles"]) for s in sectors)}


def valuation(db: Session, tickers_filter: set[str] | None = None) -> dict:
    """Карта недооценённости: цвет — апсайд к модельной справедливой цене (живьём).
    upside = (fair − live)/live. Непокрытые — отдельной группой «оценка недоступна»."""
    live = _live_prices()
    latest = _latest_closes(db)

    by_sector: dict[str, list] = {}
    uncovered: list = []
    for c in _companies(db, tickers_filter):
        cap = float(c.market_cap) if c.market_cap is not None else None
        fair = _fair_value(c.ticker)
        price = _now_price(c.ticker, live, latest)
        if fair is None or price is None or price <= 0:
            uncovered.append({"ticker": c.ticker, "name": c.name,
                              "sector": c.sector or "Прочее", "market_cap": cap})
            continue
        upside = (fair - price) / price * 100.0
        sector = c.sector or "Прочее"
        by_sector.setdefault(sector, []).append({
            "ticker": c.ticker, "name": c.name, "sector": sector, "market_cap": cap,
            "price": round(price, 2), "fair_value": round(fair, 2),
            "upside_pct": round(upside, 1),
        })

    sectors = _pack_sectors(by_sector)
    uncovered.sort(key=lambda t: (t.get("market_cap") or 0), reverse=True)
    return {"map": "valuation", "model_note": "модельная оценка", "sectors": sectors,
            "uncovered": uncovered,
            "count": sum(len(s["tiles"]) for s in sectors), "uncovered_count": len(uncovered)}


def _pack_sectors(by_sector: dict[str, list]) -> list:
    """Секторы → отсортированный список; тайлы внутри по капитализации (размер плитки)."""
    out = []
    for sector, tiles in by_sector.items():
        tiles.sort(key=lambda t: (t.get("market_cap") or 0), reverse=True)
        cap_sum = sum(t["market_cap"] or 0 for t in tiles)
        out.append({"sector": sector, "tiles": tiles, "market_cap": cap_sum})
    out.sort(key=lambda s: s["market_cap"], reverse=True)
    return out
