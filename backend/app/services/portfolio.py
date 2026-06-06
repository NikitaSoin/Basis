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
