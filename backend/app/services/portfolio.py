import math

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from app.models.company import Company, Quote
from app.models.company_metrics import CompanyMetrics
from app.models.portfolio import Portfolio, PortfolioPosition
from app.schemas.portfolio import PortfolioCreate, PositionCreate


def get_all_portfolios(db: Session) -> list[Portfolio]:
    return db.query(Portfolio).order_by(Portfolio.created_at.desc()).all()


def get_portfolios_by_user(db: Session, user_id: int) -> list[Portfolio]:
    return (
        db.query(Portfolio)
        .filter(Portfolio.user_id == user_id)
        .order_by(Portfolio.created_at.desc())
        .all()
    )


def get_portfolio_by_id(db: Session, portfolio_id: int) -> Portfolio | None:
    return (
        db.query(Portfolio)
        .options(selectinload(Portfolio.positions))
        .filter(Portfolio.id == portfolio_id)
        .first()
    )


def create_portfolio(db: Session, data: PortfolioCreate) -> Portfolio:
    portfolio = Portfolio(**data.model_dump())
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)
    return portfolio


def add_position(db: Session, portfolio_id: int, data: PositionCreate) -> PortfolioPosition:
    position = PortfolioPosition(portfolio_id=portfolio_id, **data.model_dump())
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def _weighted_avg(items: list[tuple[float, float | None]]) -> dict:
    """Средневзвешенное с честной обработкой пропусков.

    items: [(стоимость позиции, значение метрики | None), ...]
    Позиции без метрики НЕ входят в сумму, и веса нормируются только на
    позиции с метрикой (иначе пропуски занижали бы среднее). Возвращает
    value + «рассчитано по n из m позиций», чтобы фронт показал это честно.
    """
    m = len(items)
    known = [(v, x) for v, x in items if x is not None and v > 0]
    n = len(known)
    total = sum(v for v, _ in known)
    if n == 0 or total <= 0:
        return {"value": None, "n": n, "m": m}
    return {"value": round(sum(v * x for v, x in known) / total, 2), "n": n, "m": m}


def compute_portfolio_metrics(db: Session, portfolio_id: int) -> dict | None:
    """Аналитика портфеля из company_metrics одним запросом (Этап 1).

    Лёгкие метрики: P/E тек./ист. и дивдоходность по позициям, средневзвешенные
    по портфелю, распределение по секторам и классам активов, концентрация.
    Стоимость позиции = количество × последняя цена закрытия из quotes.
    Риск-метрики (beta/volatility) — Этап 2, здесь не считаются.
    """
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        return None

    company_ids = [p.company_id for p in portfolio.positions]
    if not company_ids:
        return {
            "positions": [], "portfolio": {}, "sector_allocation": [],
            "asset_classes": [{"name": "Акции", "share_pct": 100.0}],
            "concentration": None, "correlation": None,
            "rates": {}, "benchmark": None,
        }

    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}

    # Последняя цена закрытия по каждой компании портфеля
    latest_sq = (
        db.query(Quote.company_id, func.max(Quote.date).label("max_date"))
        .filter(Quote.company_id.in_(company_ids))
        .group_by(Quote.company_id)
        .subquery()
    )
    price_rows = (
        db.query(Quote.company_id, Quote.close)
        .join(latest_sq, (Quote.company_id == latest_sq.c.company_id) & (Quote.date == latest_sq.c.max_date))
        .all()
    )
    prices = {r.company_id: float(r.close) for r in price_rows if r.close is not None}

    # Метрики — ОДНИМ запросом по тикерам портфеля (не из файлов)
    tickers = [companies[cid].ticker for cid in company_ids if cid in companies]
    metrics = {
        m.ticker: m
        for m in db.query(CompanyMetrics).filter(CompanyMetrics.ticker.in_(tickers)).all()
    }

    positions = []
    for p in portfolio.positions:
        c = companies.get(p.company_id)
        if not c:
            continue
        price = prices.get(p.company_id)
        value = float(p.quantity) * price if price is not None else None
        m = metrics.get(c.ticker)
        hy = float(m.history_years) if m and m.history_years is not None else None
        positions.append({
            "ticker": c.ticker,
            "name": c.name,
            "sector": c.sector or "Прочее",
            "value": round(value, 2) if value is not None else None,
            "pe_current": float(m.pe_current) if m and m.pe_current is not None else None,
            "pe_historical": float(m.pe_historical) if m and m.pe_historical is not None else None,
            "div_yield": float(m.div_yield) if m and m.div_yield is not None else None,
            # Этап 2 — риск-метрики из company_metrics (предрасчёт recalc_risk_metrics)
            "volatility": float(m.volatility) if m and m.volatility is not None else None,
            "beta": float(m.beta) if m and m.beta is not None else None,
            "return_3y": float(m.return_3y) if m and m.return_3y is not None else None,
            "history_years": hy,
            "short_history": hy is not None and hy < 1.0,  # «*» в UI
            # Этап 2.2 — источник беты, R² и доп. коэффициенты
            "beta_source": m.beta_source if m else None,
            "r_squared": float(m.r_squared) if m and m.r_squared is not None else None,
            "downside_vol": float(m.downside_vol) if m and m.downside_vol is not None else None,
            "var_95": float(m.var_95) if m and m.var_95 is not None else None,
            "earnings_yield": float(m.earnings_yield) if m and m.earnings_yield is not None else None,
            # Этап 3 — полная доходность и коэффициенты на базе Rf
            "return_total_3y": float(m.return_total_3y) if m and m.return_total_3y is not None else None,
            "alpha_3y": float(m.alpha_3y) if m and m.alpha_3y is not None else None,
            "sortino_3y": float(m.sortino_3y) if m and m.sortino_3y is not None else None,
            "capm_expected": float(m.capm_expected) if m and m.capm_expected is not None else None,
        })

    total_value = sum(p["value"] for p in positions if p["value"] is not None)
    for p in positions:
        p["weight_pct"] = round(p["value"] / total_value * 100, 2) if p["value"] and total_value > 0 else None

    # Средневзвешенные по портфелю (нормировка только на позиции с метрикой)
    valued = [p for p in positions if p["value"] is not None]
    portfolio_row = {
        "pe_current": _weighted_avg([(p["value"], p["pe_current"]) for p in valued]),
        "pe_historical": _weighted_avg([(p["value"], p["pe_historical"]) for p in valued]),
        "div_yield": _weighted_avg([(p["value"], p["div_yield"]) for p in valued]),
        # бета и доходность портфеля линейны по весам → честное средневзвешенное
        "beta": _weighted_avg([(p["value"], p["beta"]) for p in valued]),
        "return_3y": _weighted_avg([(p["value"], p["return_3y"]) for p in valued]),
    }

    # Этап 2: корреляции и волатильность портфеля — НА ЛЕТУ (зависят от состава).
    # σ_p = √(wᵀΣw): НЕ среднее волатильностей — ковариация учитывает корреляции,
    # поэтому портфельная σ ниже за счёт диверсификации.
    from app.services.risk_metrics import (
        load_price_series, log_returns, pairwise_correlation,
        portfolio_volatility, window_start,
    )
    since = window_start()
    returns_by_ticker = {}
    for p in valued:
        cid = next((i for i, c in companies.items() if c.ticker == p["ticker"]), None)
        if cid is None:
            continue
        series = load_price_series(db, cid, since)
        rets = log_returns(series)
        if rets:
            returns_by_ticker[p["ticker"]] = rets

    correlation = None
    if len(returns_by_ticker) >= 2:
        corr_tickers, matrix, min_overlap = pairwise_correlation(returns_by_ticker)
        correlation = {
            "tickers": corr_tickers,
            "matrix": matrix,
            # мало пересечения дат (молодые бумаги) — честно предупреждаем
            "low_overlap": 0 < min_overlap < 126,   # < полугода совпадающих дней
        }

    weights = {p["ticker"]: p["value"] for p in valued if p["value"]}
    pf_volatility = portfolio_volatility(returns_by_ticker, weights) if returns_by_ticker else None
    portfolio_row["volatility"] = {"value": pf_volatility,
                                   "n": len(returns_by_ticker), "m": len(valued)}
    portfolio_row["return_total_3y"] = _weighted_avg([(p["value"], p["return_total_3y"]) for p in valued])

    # ── Этап 3: Шарп/Сортино/альфа портфеля + сравнение с бенчмарком ──
    from app.services.moex_dividends import get_market_param, load_dividends_map
    from app.services.risk_metrics import load_index_series
    rf_row = get_market_param(db, "risk_free_1y")
    rm_row = get_market_param(db, "market_return_3y")
    rates = {
        "risk_free_1y": rf_row[0] if rf_row else None,
        "risk_free_as_of": rf_row[1].isoformat() if rf_row and rf_row[1] else None,
        "market_return_3y": rm_row[0] if rm_row else None,
        "market_premium": round(rm_row[0] - rf_row[0], 2) if rf_row and rm_row else None,
    }

    r_total_p = portfolio_row["return_total_3y"]["value"]
    beta_p = portfolio_row["beta"]["value"]
    rf = rates["risk_free_1y"]
    rm = rates["market_return_3y"]
    portfolio_row["sharpe"] = (
        round((r_total_p - rf) / pf_volatility, 2)
        if None not in (r_total_p, rf) and pf_volatility else None
    )
    portfolio_row["alpha"] = (
        round(r_total_p - (rf + beta_p * (rm - rf)), 2)
        if None not in (r_total_p, rf, rm, beta_p) else None
    )

    # портфельная downside-σ и кривая «если бы держал» — из взвешенного
    # дневного ряда на общем пересечении дат (период честно ограничен
    # самой молодой бумагой)
    benchmark = None
    sortino_p = None
    if returns_by_ticker and total_value > 0:
        import numpy as np
        common_dates = None
        for rets in returns_by_ticker.values():
            ds = set(rets)
            common_dates = ds if common_dates is None else (common_dates & ds)
        common_dates = sorted(common_dates or [])
        if len(common_dates) >= 60:
            w = {t: weights[t] / sum(weights[t2] for t2 in returns_by_ticker) for t in returns_by_ticker}
            # дневной лог-ряд портфеля + дивидендные добавки D/P на датах отсечек
            div_addon: dict = {}
            for p in valued:
                t = p["ticker"]
                if t not in returns_by_ticker:
                    continue
                cid = next((i for i, c in companies.items() if c.ticker == t), None)
                series = load_price_series(db, cid, since) if cid else {}
                sdates = sorted(series)
                for d, amount in load_dividends_map(db, t).items():
                    if not sdates or d < sdates[0] or d > sdates[-1]:
                        continue
                    pd_ = [x for x in sdates if x <= d]
                    price = series[pd_[-1]] if pd_ else None
                    if price and 0 < amount / price < 1:
                        div_addon[(t, pd_[-1])] = div_addon.get((t, pd_[-1]), 0.0) + amount / price
            pf_daily = []
            for d in common_dates:
                r = sum(w[t] * (math.exp(returns_by_ticker[t][d]) - 1 + div_addon.get((t, d), 0.0))
                        for t in returns_by_ticker)
                pf_daily.append(r)
            # портфельный Сортино: годовая downside-σ взвешенного ряда
            neg = [r for r in pf_daily if r < 0]
            if len(neg) >= 30 and None not in (r_total_p, rf):
                dvol = float(np.std(neg, ddof=1)) * (252 ** 0.5) * 100
                sortino_p = round((r_total_p - rf) / dvol, 2) if dvol > 0 else None

            # накопленные кривые: портфель vs MCFTR (обе с дивидендами) + IMOEX
            mcftr = load_index_series(db, "MCFTR", since)
            imoex = load_index_series(db, "IMOEX", since)
            chart_dates, pf_curve, mc_curve, im_curve = [], [], [], []
            acc = 1.0
            mc0 = im0 = None
            for d, r in zip(common_dates, pf_daily):
                acc *= (1 + r)
                if d in mcftr and d in imoex:
                    if mc0 is None:
                        mc0, im0 = mcftr[d], imoex[d]
                    chart_dates.append(d.isoformat())
                    pf_curve.append(round((acc - 1) * 100, 2))
                    mc_curve.append(round((mcftr[d] / mc0 - 1) * 100, 2))
                    im_curve.append(round((imoex[d] / im0 - 1) * 100, 2))
            step = max(1, len(chart_dates) // 260)   # прореживание для фронта
            youngest = min(valued, key=lambda p: p["history_years"] or 99)
            benchmark = {
                "dates": chart_dates[::step],
                "portfolio": pf_curve[::step],
                "mcftr": mc_curve[::step],
                "imoex": im_curve[::step],
                "period_years": round(len(common_dates) / 252, 2),
                "limited_by": youngest["ticker"] if (youngest.get("history_years") or 9) < 2.9 else None,
                "portfolio_total_pct": pf_curve[-1] if pf_curve else None,
                "benchmark_total_pct": mc_curve[-1] if mc_curve else None,
                "note": "веса позиций зафиксированы текущими долями (приближение)",
            }
    portfolio_row["sortino"] = sortino_p

    # Распределение по секторам — по текущей стоимости
    by_sector: dict[str, float] = {}
    for p in valued:
        by_sector[p["sector"]] = by_sector.get(p["sector"], 0.0) + p["value"]
    sector_allocation = sorted(
        (
            {"sector": s, "value": round(v, 2), "share_pct": round(v / total_value * 100, 2)}
            for s, v in by_sector.items()
        ),
        key=lambda x: -x["value"],
    ) if total_value > 0 else []

    # Концентрация: крупнейшая позиция и топ-3 по стоимости
    concentration = None
    if total_value > 0 and valued:
        top = sorted(valued, key=lambda p: -p["value"])
        concentration = {
            "largest_ticker": top[0]["ticker"],
            "largest_pct": round(top[0]["value"] / total_value * 100, 2),
            "top3_pct": round(sum(p["value"] for p in top[:3]) / total_value * 100, 2),
        }

    return {
        "positions": positions,
        "portfolio": portfolio_row,
        "sector_allocation": sector_allocation,
        # Пока в модели только акции; блок готов принять облигации/фонды,
        # когда позиции получат класс актива (отдельный трек).
        "asset_classes": [{"name": "Акции", "share_pct": 100.0}],
        "concentration": concentration,
        "correlation": correlation,
        "rates": rates,
        "benchmark": benchmark,
    }


def delete_position(db: Session, portfolio_id: int, position_id: int) -> bool:
    position = (
        db.query(PortfolioPosition)
        .filter(
            PortfolioPosition.id == position_id,
            PortfolioPosition.portfolio_id == portfolio_id,
        )
        .first()
    )
    if not position:
        return False
    db.delete(position)
    db.commit()
    return True
