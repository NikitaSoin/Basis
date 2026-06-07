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


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _lin_score(value: float | None, best: float, worst: float) -> float | None:
    """Линейная шкала 0..100 «от максимума»: value=best → 100, value=worst → 0.
    best может быть больше или меньше worst (направление задаётся знаком)."""
    if value is None or best == worst:
        return None
    return round(_clamp01((value - worst) / (best - worst)) * 100)


def compute_quality_index(*, weights: dict, correlation: dict | None,
                          sector_allocation: list, concentration: dict | None,
                          volatility: float | None, beta: float | None,
                          var_95: float | None, sharpe: float | None,
                          sortino: float | None, alpha: float | None) -> dict | None:
    """Индекс качества портфеля и субиндексы (методика Basis — НАШ подход).

    Методика и обоснование порогов/весов — docs/portfolio-indices-methodology.md.
    Строится ТОЛЬКО из реально посчитанных метрик; чего нет — субиндекс/компонента
    выпадает с честной пометкой, не имитируется. Шкала 0–100, «от максимума».
    """
    if not weights:
        return None

    def band(score: int) -> str:
        return ("Сильный" if score >= 75 else "Умеренный" if score >= 60
                else "Ниже среднего" if score >= 40 else "Слабый")

    subindices = []

    # ── 1. Диверсификация: эффективное число позиций (HHI), сектора, корреляция ──
    w = list(weights.values())
    tot = sum(w)
    comps_div = []
    if tot > 0:
        norm = [x / tot for x in w]
        eff_n = 1.0 / sum(x * x for x in norm)         # 1/HHI — «эффективное» число бумаг
        comps_div.append(("Эффективное число позиций", f"{eff_n:.1f}", _lin_score(eff_n, best=8, worst=1)))
    n_sectors = len([s for s in sector_allocation if s.get("value")])
    if n_sectors:
        comps_div.append(("Число секторов", str(n_sectors), _lin_score(n_sectors, best=5, worst=1)))
    avg_corr = None
    if correlation and correlation.get("matrix"):
        m = correlation["matrix"]
        off = [m[i][j] for i in range(len(m)) for j in range(i + 1, len(m))
               if isinstance(m[i][j], (int, float))]
        if off:
            avg_corr = sum(off) / len(off)
            comps_div.append(("Средняя корреляция", f"{avg_corr:.2f}", _lin_score(avg_corr, best=0.2, worst=0.7)))
    div_score = _avg_scores([c[2] for c in comps_div])
    if div_score is not None:
        subindices.append({
            "key": "diversification", "label": "Диверсификация", "score": div_score,
            "confidence": "факт",   # веса и корреляции наблюдаемы, минимум допущений
            "components": [{"name": n, "value": v, "score": s} for n, v, s in comps_div if s is not None],
            "verdict": (
                "Риск распределён: бумаги из разных секторов и движутся по-разному."
                if div_score >= 60 else
                "Средняя диверсификация: часть риска сконцентрирована — в одной-двух бумагах, секторе или общем движении."
                if div_score >= 40 else
                "Слабая диверсификация: портфель завязан на узкий набор/сектор или бумаги ходят вместе — просадки приходят одновременно."
            ),
        })

    # ── 2. Доходность-к-риску: ОТНОСИТЕЛЬНО РЫНКА (регим-нейтрально) ──
    #    Якорь — альфа (фактическая доходность − ожидание CAPM за свой риск):
    #    альфа≈0 → «как рынок за такой риск» = 50 баллов. В режиме высокой ставки
    #    абсолютные Шарп/Сортино отрицательны по ВСЕМУ рынку — мапить их в лоб
    #    значило бы всем ставить «плохо». Поэтому Шарп/Сортино показываем как
    #    КОНТЕКСТ (без балла), а оценку ведём от альфы.
    rr_score = _lin_score(alpha, best=6, worst=-6) if alpha is not None else None
    if rr_score is not None:
        comps_rr = [{"name": "Альфа (к рынку за свой риск)", "value": f"{alpha:+.1f}%", "score": rr_score}]
        if sharpe is not None:
            comps_rr.append({"name": "Коэффициент Шарпа", "value": f"{sharpe:.2f}", "score": None})
        if sortino is not None:
            comps_rr.append({"name": "Коэффициент Сортино", "value": f"{sortino:.2f}", "score": None})
        subindices.append({
            "key": "return_risk", "label": "Доходность к риску", "score": rr_score,
            "confidence": "суждение",  # зависит от модели, окна и режима ставки
            "components": comps_rr,
            "verdict": (
                "Портфель обгоняет рынок за свой уровень риска — риск отрабатывает с запасом."
                if rr_score >= 60 else
                "Портфель идёт примерно вровень с рынком за свой риск. Абсолютные Шарп/Сортино сейчас низкие из-за высокой ставки ОФЗ — это режим всего рынка, оценка же сравнивает вас именно с рынком."
                if rr_score >= 40 else
                "За свой уровень риска портфель пока отстаёт от рынка. Это сравнение с рынком, оно не зависит от режима ставки — стоит посмотреть, какие бумаги тянут вниз."
            ),
        })

    # ── 3. Устойчивость к рыночному риску: волатильность, бета, VaR ──
    #    ВАЖНО: это РЫНОЧНЫЙ риск, не макро/гео (портфель не связан с макро/гео-
    #    экспозициями компаний) — ограничение зафиксировано в методике.
    comps_mr = []
    if volatility is not None:
        comps_mr.append(("Волатильность портфеля", f"{volatility:.1f}%", _lin_score(volatility, best=15, worst=45)))
    if beta is not None:
        comps_mr.append(("Бета", f"{beta:.2f}", _lin_score(beta, best=0.6, worst=1.4)))
    if var_95 is not None:
        comps_mr.append(("VaR 95% (дневной)", f"{var_95:.1f}%", _lin_score(var_95, best=1.5, worst=4)))
    mr_score = _avg_scores([c[2] for c in comps_mr])
    if mr_score is not None:
        subindices.append({
            "key": "market_resilience", "label": "Устойчивость к рынку", "score": mr_score,
            "confidence": "оценка",   # волатильность/бета/VaR на исторических данных
            "components": [{"name": n, "value": v, "score": s} for n, v, s in comps_mr if s is not None],
            "verdict": (
                "Портфель спокойнее рынка: умеренные колебания и невысокая чувствительность к общим движениям."
                if mr_score >= 60 else
                "Средняя чувствительность к рынку: колебания заметны, в просадки рынка портфель пойдёт вместе с ним."
                if mr_score >= 40 else
                "Портфель резко реагирует на рынок: высокая волатильность/бета — глубокие просадки в плохие периоды."
            ),
            "limitation": "Это рыночный риск (волатильность, бета, VaR). Устойчивость к макро- и геополитическим шокам сюда пока НЕ входит — портфель ещё не связан с макро/гео-профилями компаний.",
        })

    if not subindices:
        return None

    # ── Общий индекс качества: взвешенная композиция (веса — наш выбор) ──
    WEIGHTS = {"diversification": 0.35, "return_risk": 0.35, "market_resilience": 0.30}
    num = sum(WEIGHTS[s["key"]] * s["score"] for s in subindices)
    den = sum(WEIGHTS[s["key"]] for s in subindices)
    overall = round(num / den) if den else None

    return {
        "overall": overall,
        "label": band(overall) if overall is not None else None,
        "subindices": subindices,
        "weights": {s["key"]: WEIGHTS[s["key"]] for s in subindices},
        "note": "Индекс — наш подход к оценке качества, не объективная истина: пороги и веса выбраны нами и объяснены в методике. Он сложен только из реально посчитанных метрик; смотрите, какой субиндекс тянет его вверх или вниз.",
    }


def _avg_scores(scores: list) -> int | None:
    vals = [s for s in scores if s is not None]
    return round(sum(vals) / len(vals)) if vals else None


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

        # Динамические мультипликаторы: P/E, дивдоходность и earnings yield
        # пересчитываются от СВЕЖЕЙ цены через подразумеваемые EPS/DPS
        # (цена меняется постоянно, прибыль/дивиденд — редко). Округление до
        # десятых: сотые дёргались бы шумом цены. Без якоря — статика из файла.
        eps = float(m.eps_implied) if m and m.eps_implied is not None else None
        dps = float(m.dps_implied) if m and m.dps_implied is not None else None
        pe_dynamic = round(price / eps, 1) if price and eps and eps > 0 else (
            round(float(m.pe_current), 1) if m and m.pe_current is not None else None)
        dy_dynamic = round(dps / price * 100, 1) if price and dps else (
            round(float(m.div_yield), 1) if m and m.div_yield is not None else None)
        ey_dynamic = round(100 / pe_dynamic, 1) if pe_dynamic and pe_dynamic > 0 else None

        positions.append({
            "ticker": c.ticker,
            "name": c.name,
            "company_id": p.company_id,
            "sector": c.sector or "Прочее",
            "value": round(value, 2) if value is not None else None,
            "pe_current": pe_dynamic,
            "pe_historical": float(m.pe_historical) if m and m.pe_historical is not None else None,
            "div_yield": dy_dynamic,
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
            "earnings_yield": ey_dynamic,
            # Этап 3 — полная доходность и коэффициенты на базе Rf
            "return_total_3y": float(m.return_total_3y) if m and m.return_total_3y is not None else None,
            "alpha_3y": float(m.alpha_3y) if m and m.alpha_3y is not None else None,
            "sortino_3y": float(m.sortino_3y) if m and m.sortino_3y is not None else None,
            "capm_expected": float(m.capm_expected) if m and m.capm_expected is not None else None,
        })

    total_value = sum(p["value"] for p in positions if p["value"] is not None)
    for p in positions:
        p["weight_pct"] = round(p["value"] / total_value * 100, 2) if p["value"] and total_value > 0 else None

    # Средневзвешенные по портфелю (нормировка только на позиции с метрикой).
    # Вырожденные случаи не валят расчёт: позиции с нулевой стоимостью
    # (0 шт. — застрявшие до фикса валидации) исключаются из весов; пустой
    # портфель и портфель из одной бумаги обрабатываются штатно.
    valued = [p for p in positions if p["value"]]
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
        # Интерпретация: средняя корреляция + самая связанная и самая
        # «разбавляющая» пары (для человеческого вывода о диверсификации)
        pairs = [(corr_tickers[i], corr_tickers[j], matrix[i][j])
                 for i in range(len(matrix)) for j in range(i + 1, len(matrix))
                 if isinstance(matrix[i][j], (int, float))]
        avg_corr = round(sum(p[2] for p in pairs) / len(pairs), 2) if pairs else None
        strongest = max(pairs, key=lambda p: p[2]) if pairs else None
        weakest = min(pairs, key=lambda p: p[2]) if pairs else None
        correlation = {
            "tickers": corr_tickers,
            "matrix": matrix,
            # мало пересечения дат (молодые бумаги) — честно предупреждаем
            "low_overlap": 0 < min_overlap < 126,   # < полугода совпадающих дней
            "avg": avg_corr,
            "strongest_pair": {"a": strongest[0], "b": strongest[1], "value": round(strongest[2], 2)} if strongest else None,
            "weakest_pair": {"a": weakest[0], "b": weakest[1], "value": round(weakest[2], 2)} if weakest else None,
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

    # Шарп на бумагу (для группы «Риск»): (полная доходность − Rf) / её волатильность
    _rf = rates["risk_free_1y"]
    for p in positions:
        p["sharpe_3y"] = (
            round((p["return_total_3y"] - _rf) / p["volatility"], 2)
            if _rf is not None and p.get("return_total_3y") is not None
            and p.get("volatility") else None
        )

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
            if len(neg) >= 30:
                dvol = float(np.std(neg, ddof=1)) * (252 ** 0.5) * 100
                portfolio_row["downside_vol"] = round(dvol, 2)
                if r_total_p is not None and rf is not None and dvol > 0:
                    sortino_p = round((r_total_p - rf) / dvol, 2)

            # портфельный VaR 95% (дневной): −5-й перцентиль дневных доходностей
            if len(pf_daily) >= 30:
                portfolio_row["var_95"] = round(-float(np.percentile(pf_daily, 5)) * 100, 2)

            # портфельный R²: corr² дневного ряда портфеля с рынком (IMOEX)
            imoex_s = load_index_series(db, "IMOEX", since)
            idx_dates = sorted(imoex_s)
            idx_ret = {idx_dates[k]: math.log(imoex_s[idx_dates[k]] / imoex_s[idx_dates[k - 1]])
                       for k in range(1, len(idx_dates))}
            pf_by_date = dict(zip(common_dates, pf_daily))
            common_idx = sorted(set(pf_by_date) & set(idx_ret))
            if len(common_idx) >= 30:
                a = np.array([pf_by_date[d] for d in common_idx])
                b = np.array([idx_ret[d] for d in common_idx])
                if float(np.std(a)) > 0 and float(np.std(b)) > 0:
                    corr = float(np.corrcoef(a, b)[0][1])
                    if not math.isnan(corr):
                        portfolio_row["r_squared"] = round(corr * corr, 4)

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

    # CAPM-ожидание портфеля (модель) и earnings yield от портфельного P/E
    portfolio_row["capm"] = (
        round(rf + beta_p * (rm - rf), 2)
        if None not in (rf, rm, beta_p) else None
    )
    pe_p = portfolio_row["pe_current"]["value"]
    portfolio_row["earnings_yield"] = round(100 / pe_p, 1) if pe_p and pe_p > 0 else None

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

    quality = compute_quality_index(
        weights=weights, correlation=correlation, sector_allocation=sector_allocation,
        concentration=concentration,
        volatility=portfolio_row["volatility"]["value"],
        beta=portfolio_row["beta"]["value"],
        var_95=portfolio_row.get("var_95"),
        sharpe=portfolio_row.get("sharpe"),
        sortino=portfolio_row.get("sortino"),
        alpha=portfolio_row.get("alpha"),
    )

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
        "quality": quality,
    }


def update_position(db: Session, portfolio_id: int, position_id: int,
                    quantity=None, avg_buy_price=None) -> PortfolioPosition | None:
    """Прямое редактирование позиции (UX: клик по строке → правка)."""
    position = (
        db.query(PortfolioPosition)
        .filter(
            PortfolioPosition.id == position_id,
            PortfolioPosition.portfolio_id == portfolio_id,
        )
        .first()
    )
    if not position:
        return None
    if quantity is not None:
        position.quantity = quantity
    if avg_buy_price is not None:
        position.avg_buy_price = avg_buy_price
    db.commit()
    db.refresh(position)
    return position


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
