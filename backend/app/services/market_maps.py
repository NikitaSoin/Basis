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


_FUTURES_KIND_LABEL = {
    "currency": "Валютные", "index": "Индексные", "commodity": "Сырьевые",
    "stock": "На акции", "rate": "Процентные", "other": "Прочие",
}
_FUND_TYPE_LABEL = {
    "equity": "Акции", "bonds": "Облигации", "gold": "Золото",
    "money_market": "Денежный рынок", "currency": "Валютные", "mixed": "Смешанные",
}


def heatmap_futures(db: Session) -> dict:
    """Тепловая карта фьючерсов. Вес плитки — условная стоимость открытых позиций
    (open_position × contract_value, аналог капитализации: размер интереса рынка к
    контракту). Цвет — изменение расчётной цены к предыдущему клирингу.
    Группировка — по asset_kind (валютные/индексные/сырьевые/на акции/процентные)."""
    from app.models.future import Future
    rows = db.query(Future).all()
    by_kind: dict[str, list] = {}
    for f in rows:
        last = float(f.last_price) if f.last_price is not None else None
        prev = float(f.prev_settle) if f.prev_settle is not None else None
        change = round((last / prev - 1) * 100, 2) if last and prev else None
        oi = float(f.open_position) if f.open_position is not None else 0.0
        cv = float(f.contract_value) if f.contract_value is not None else 1.0
        weight = oi * cv if oi and cv else oi or 0.0
        kind = _FUTURES_KIND_LABEL.get(f.asset_kind, f.asset_kind or "Прочие")
        by_kind.setdefault(kind, []).append({
            "ticker": f.secid, "name": f.asset_name or f.short_name, "sector": kind,
            "market_cap": weight, "change_pct": change,
        })
    sectors = _pack_sectors(by_kind)
    return {"map": "heatmap", "asset_class": "futures", "sectors": sectors,
            "count": sum(len(s["tiles"]) for s in sectors)}


def heatmap_funds(db: Session) -> dict:
    """Тепловая карта фондов (БПИФ/ETF). Вес плитки — дневной торговый оборот
    (val_today, ₽) — прокси ликвидности вместо капитализации (СЧА фонда на MOEX не
    публикуется по каждой бумаге). Цвет — дневное изменение цены пая из
    instrument_history (там уже посчитан change_pct). Группировка — по fund_type."""
    from app.models.fund import Fund
    from app.services.instrument_history import get_sparklines
    rows = db.query(Fund).all()
    secids = [f.secid for f in rows]
    sparks = get_sparklines(db, "fund", secids, days=2) if secids else {}
    by_type: dict[str, list] = {}
    for f in rows:
        change = (sparks.get(f.secid) or {}).get("change_pct")
        weight = float(f.val_today) if f.val_today else 0.0
        ftype = _FUND_TYPE_LABEL.get(f.fund_type, f.fund_type or "Прочие")
        by_type.setdefault(ftype, []).append({
            "ticker": f.secid, "name": f.sec_name or f.short_name, "sector": ftype,
            "market_cap": weight, "change_pct": round(change, 2) if change is not None else None,
        })
    sectors = _pack_sectors(by_type)
    return {"map": "heatmap", "asset_class": "funds", "sectors": sectors,
            "count": sum(len(s["tiles"]) for s in sectors)}


def heatmap_bonds(db: Session) -> dict:
    """Тепловая карта облигаций. Вес плитки — дневной торговый оборот
    (instrument_history.value, ₽, последнее известное значение за 30 дней) — прокси
    ликвидности, как у фондов/фьючерсов. Цвет — изменение цены (% от номинала) к
    предыдущему торговому дню. ЧЕСТНОЕ ПОКРЫТИЕ: показываем только бумаги, у которых
    реально есть данные хотя бы за один день из последних 30 (российский рынок
    корпоративных облигаций объективно неоднородно ликвиден — многие выпуски не
    торгуются каждый день, это не пробел загрузки, а свойство рынка); остальные — не
    считаются нулём, просто не попадают на карту. Растёт по мере накопления истории
    (ежедневный крон подхватывает РАЗНЫЕ бумаги в разные дни)."""
    from app.models.bond import Bond
    from app.models.company import Company
    rows = (
        db.query(Bond, Company.sector)
        .outerjoin(Company, Company.ticker == Bond.issuer_ticker)
        .all()
    )
    total_bonds = len(rows)
    secids = [b.secid for b, _ in rows]
    if not secids:
        return {"map": "heatmap", "asset_class": "bonds", "sectors": [], "count": 0,
                "coverage_pct": 0.0, "total_universe": 0}
    hist = db.execute(text("""
        SELECT DISTINCT ON (secid) secid, close, value,
               LAG(close) OVER (PARTITION BY secid ORDER BY date) AS prev_close
        FROM instrument_history
        WHERE asset_class='bond' AND secid = ANY(:ids) AND date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY secid, date DESC
    """), {"ids": secids}).all()
    by_secid = {r.secid: r for r in hist}

    by_sector: dict[str, list] = {}
    for b, company_sector in rows:
        h = by_secid.get(b.secid)
        if h is None or h.value is None:
            continue  # нет реальных данных об обороте — честно не рисуем плитку
        change = None
        if h.close is not None and h.prev_close:
            change = round((float(h.close) / float(h.prev_close) - 1) * 100, 2)
        if b.bond_type == "ofz":
            sector = "Госдолг (ОФЗ)"
        elif b.bond_type == "muni":
            sector = "Муниципальные"
        elif company_sector:
            sector = company_sector
        else:
            sector = "Корпораты — прочие"
        by_sector.setdefault(sector, []).append({
            "ticker": b.secid, "name": b.short_name, "sector": sector,
            "market_cap": float(h.value), "change_pct": change,
        })
    sectors = _pack_sectors(by_sector)
    covered = sum(len(s["tiles"]) for s in sectors)
    return {"map": "heatmap", "asset_class": "bonds", "sectors": sectors, "count": covered,
            "coverage_pct": round(covered / total_bonds * 100, 1) if total_bonds else 0.0,
            "total_universe": total_bonds}


def spot_grid(db: Session) -> dict:
    """Валюта/металлы — курируемый набор из 6 инструментов, без treemap (слишком мало
    бумаг для осмысленной карты): плоский список с ценой и дневным изменением."""
    from app.models.spot import SpotAsset
    rows = db.query(SpotAsset).all()
    kind_label = {"currency": "Валюта", "metal": "Металл"}
    items = [{
        "ticker": r.secid, "name": r.name, "kind": kind_label.get(r.kind, r.kind),
        "last_price": float(r.last_price) if r.last_price is not None else None,
        "change_pct": float(r.change_pct) if r.change_pct is not None else None,
    } for r in rows]
    items.sort(key=lambda x: (x["kind"] != "Валюта", x["ticker"]))
    return {"map": "heatmap", "asset_class": "currency", "items": items, "count": len(items)}
