import math
from datetime import date as date_cls, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
from app.models.company import Company, Quote
from app.models.company_metrics import CompanyMetrics
from app.models.portfolio import Portfolio, PortfolioPosition, PortfolioTransaction
from app.schemas.portfolio import PortfolioCreate, PositionCreate, TradeCreate


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
    db.flush()
    # Открывающая сделка — чтобы у новых позиций СРАЗУ была история (реализовано/
    # дивиденды/комиссии считаются от неё, не от бэкфилла задним числом).
    db.add(PortfolioTransaction(
        position_id=position.id, side="buy", quantity=position.quantity,
        price=position.avg_buy_price, fee=Decimal("0"), trade_date=date_cls.today(),
    ))
    db.commit()
    db.refresh(position)
    return position


def _credit_cash(db: Session, portfolio_id: int, currency: str, amount: Decimal) -> None:
    """Зачисляет/списывает amount на денежную позицию портфеля (currency) —
    заводит позицию, если её ещё нет. amount может быть отрицательным
    (защита от ухода в минус — клампим на 0, не показываем отрицательный кэш,
    которого физически не может быть)."""
    if amount == 0:
        return
    cash = (
        db.query(PortfolioPosition)
        .filter(PortfolioPosition.portfolio_id == portfolio_id,
                PortfolioPosition.instrument_type == "cash",
                PortfolioPosition.currency == currency)
        .first()
    )
    if cash:
        cash.quantity = max(cash.quantity + amount, Decimal("0"))
    elif amount > 0:
        db.add(PortfolioPosition(
            portfolio_id=portfolio_id, instrument_type="cash", currency=currency,
            quantity=amount, avg_buy_price=Decimal("1"),
        ))


def record_trade(db: Session, portfolio_id: int, position_id: int, data: TradeCreate) -> PortfolioPosition | None:
    """Совершить сделку (buy/sell) — средневзвешенная цена на покупке,
    средняя НЕ меняется на продаже (реализованный P&L считается отдельно,
    из истории сделок, см. compute_position_pnl).

    Продажа ЗАЧИСЛЯЕТ выручку (quantity×price − fee) на денежную позицию
    портфеля той же валюты (заводит её, если нет) — без этого проданный актив
    просто исчезал из «Состава» без следа, и суммарная стоимость портфеля
    молча «проседала» на всю стоимость проданного (владелец, 2026-07-25).
    Покупка НАМЕРЕННО не списывает кэш симметрично — портфель часто заводят
    задним числом («у меня уже есть эти акции»), автосписание несуществующего
    кэша создало бы более странное поведение (уход в минус/непрошеная кэш-
    позиция), чем то, что чинится здесь. Если нужно «купил на вырученные
    деньги» — пользователь уменьшает кэш вручную (уже есть в UI: правка
    денежной позиции)."""
    position = (
        db.query(PortfolioPosition)
        .filter(PortfolioPosition.id == position_id, PortfolioPosition.portfolio_id == portfolio_id)
        .first()
    )
    if not position:
        return None

    old_qty, old_avg = position.quantity, position.avg_buy_price
    if data.side == "buy":
        new_qty = old_qty + data.quantity
        position.avg_buy_price = (old_qty * old_avg + data.quantity * data.price) / new_qty
        position.quantity = new_qty
    else:
        if data.quantity > old_qty:
            raise ValueError(f"Нельзя продать {data.quantity} — в позиции только {old_qty}")
        position.quantity = old_qty - data.quantity
        # avg_buy_price не меняется при продаже
        if position.instrument_type != "cash":
            proceeds = data.quantity * data.price - data.fee
            _credit_cash(db, portfolio_id, position.currency, proceeds)

    db.add(PortfolioTransaction(
        position_id=position.id, side=data.side, quantity=data.quantity,
        price=data.price, fee=data.fee, trade_date=data.trade_date,
    ))
    db.commit()
    db.refresh(position)
    return position


def compute_position_pnl(db: Session, portfolio_id: int, position_id: int, current_price: float | None) -> dict | None:
    """Реализовано / не реализовано / дивиденды получено / комиссии уплачено —
    из истории сделок (portfolio_transactions), реплеем в хронологическом
    порядке (средневзвешенная цена на покупках, реализация на продажах).
    Дивиденды — по факту владения на дату отсечки (CalendarEvent), не по
    текущему кол-ву, чтобы не завышать/занижать при частичных продажах."""
    from app.models.calendar_event import CalendarEvent

    position = (
        db.query(PortfolioPosition)
        .filter(PortfolioPosition.id == position_id, PortfolioPosition.portfolio_id == portfolio_id)
        .first()
    )
    if not position:
        return None
    trades = (
        db.query(PortfolioTransaction)
        .filter(PortfolioTransaction.position_id == position_id)
        .order_by(PortfolioTransaction.trade_date, PortfolioTransaction.id)
        .all()
    )
    if not trades:
        return None

    company = db.query(Company).filter(Company.id == position.company_id).first() if position.company_id else None
    ticker = company.ticker if company else None

    # Реплей: держим (дата → кол-во после сделки) для дивидендов + realized/комиссии
    qty = Decimal("0")
    avg = Decimal("0")
    realized = Decimal("0")
    fees_paid = Decimal("0")
    holdings_by_date: list[tuple[date_cls, Decimal]] = []  # (дата сделки, кол-во ПОСЛЕ неё)
    first_trade_date = trades[0].trade_date
    for t in trades:
        fees_paid += t.fee
        if t.side == "buy":
            new_qty = qty + t.quantity
            avg = (qty * avg + t.quantity * t.price) / new_qty if new_qty else t.price
            qty = new_qty
        else:
            realized += t.quantity * (t.price - avg) - t.fee
            qty -= t.quantity
        holdings_by_date.append((t.trade_date, qty))

    def qty_held_on(d: date_cls) -> Decimal:
        held = Decimal("0")
        for td, q in holdings_by_date:
            if td <= d:
                held = q
            else:
                break
        return held

    dividends_received = Decimal("0")
    if ticker:
        events = (
            db.query(CalendarEvent)
            .filter(CalendarEvent.event_type == "dividend", CalendarEvent.ticker == ticker,
                    CalendarEvent.event_date >= first_trade_date, CalendarEvent.event_date <= date_cls.today())
            .all()
        )
        for e in events:
            amount = (e.payload or {}).get("amount")
            record_date_str = (e.payload or {}).get("record_date")
            if amount is None or not record_date_str:
                continue
            record_date = date_cls.fromisoformat(record_date_str)
            held = qty_held_on(record_date)
            if held > 0:
                dividends_received += held * Decimal(str(amount))

    unrealized = None
    if current_price is not None and qty > 0:
        unrealized = qty * (Decimal(str(current_price)) - position.avg_buy_price)
    elif position.instrument_type != "equity" and qty > 0:
        # Non-equity: цену не запрашивают с фронта (там её взять неоткуда для
        # облигации/фьючерса) — считаем сами по формуле класса актива.
        from app.services.portfolio_instruments import compute_non_equity_pnl
        pnl = compute_non_equity_pnl(db, position)
        if pnl is not None:
            unrealized = Decimal(str(pnl["unrealized_pnl"]))

    return {
        "realized": round(float(realized), 2),
        "unrealized": round(float(unrealized), 2) if unrealized is not None else None,
        "dividends_received": round(float(dividends_received), 2),
        "commissions_paid": round(float(fees_paid), 2),
        "trade_count": len(trades),
        "first_trade_date": first_trade_date.isoformat(),
    }


# Модельная оценка окна «отсечка → обычно приходят деньги» (депозитарная
# цепочка РФ: НРД → номинальный держатель → брокер, ориентир ~2-4 недели).
# Это ОЦЕНКА, не факт — Basis не брокер и не видит реальных зачислений на
# счёт; после этого окна событие просто уходит в историю выплат (без
# подтверждения «пришло», честно as-if-paid по модели).
DIVIDEND_PENDING_WINDOW_DAYS = 25


def compute_portfolio_dividends(db: Session, portfolio_id: int) -> dict:
    """Дивиденды по позициям портфеля — три сегмента ПО ДАТАМ (без нового
    persisted-статуса, целиком derived от record_date из CalendarEvent):
    upcoming (отсечка ещё впереди) / pending (отсечка прошла, но в пределах
    типового окна зачисления — оценка) / history (окно прошло, показываем
    как уже выплаченное). Держим на позицию (лот), как остальной портфель,
    а не на тикер — у одной компании может быть несколько лотов с разной
    историей сделок."""
    from datetime import timedelta
    from app.models.calendar_event import CalendarEvent

    today = date_cls.today()
    empty = {"as_of": today.isoformat(), "upcoming": [], "pending": [], "history": [],
              "pending_window_days": DIVIDEND_PENDING_WINDOW_DAYS}

    positions = (
        db.query(PortfolioPosition)
        .filter(PortfolioPosition.portfolio_id == portfolio_id, PortfolioPosition.instrument_type == "equity")
        .all()
    )
    if not positions:
        return empty

    company_ids = {p.company_id for p in positions if p.company_id}
    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}

    by_ticker: dict[str, list[PortfolioPosition]] = {}
    for p in positions:
        company = companies.get(p.company_id)
        if company:
            by_ticker.setdefault(company.ticker, []).append(p)
    if not by_ticker:
        return empty

    # Реплей сделок ОДИН РАЗ на позицию (не на событие) — держим (дата
    # сделки → кол-во ПОСЛЕ неё), тот же принцип, что compute_position_pnl.
    position_holdings: dict[int, list[tuple[date_cls, Decimal]]] = {}
    for p in positions:
        trades = (
            db.query(PortfolioTransaction)
            .filter(PortfolioTransaction.position_id == p.id)
            .order_by(PortfolioTransaction.trade_date, PortfolioTransaction.id)
            .all()
        )
        qty = Decimal("0")
        rows: list[tuple[date_cls, Decimal]] = []
        for t in trades:
            qty = qty + t.quantity if t.side == "buy" else qty - t.quantity
            rows.append((t.trade_date, qty))
        position_holdings[p.id] = rows

    def qty_held_on(position_id: int, d: date_cls) -> Decimal:
        held = Decimal("0")
        for td, q in position_holdings.get(position_id, []):
            if td <= d:
                held = q
            else:
                break
        return held

    events = (
        db.query(CalendarEvent)
        .filter(CalendarEvent.event_type == "dividend", CalendarEvent.ticker.in_(list(by_ticker.keys())))
        .all()
    )

    upcoming, pending, history = [], [], []
    for e in events:
        payload = e.payload or {}
        amount = payload.get("amount")
        record_date_str = payload.get("record_date")
        if amount is None or not record_date_str:
            continue
        record_date = date_cls.fromisoformat(record_date_str)
        days_since = (today - record_date).days

        for p in by_ticker.get(e.ticker, []):
            company = companies.get(p.company_id)
            shares = float(p.quantity) if days_since < 0 else float(qty_held_on(p.id, record_date))
            if shares <= 0:
                continue
            item = {
                "position_id": p.id, "ticker": e.ticker, "name": company.name if company else e.ticker,
                "amount": float(amount), "shares": shares, "total": round(shares * float(amount), 2),
                "record_date": record_date.isoformat(), "buy_by_date": payload.get("buy_by_date"),
                "dividend_yield": payload.get("dividend_yield"),
            }
            if days_since < 0:
                upcoming.append(item)
            elif days_since <= DIVIDEND_PENDING_WINDOW_DAYS:
                item["estimated_payment_by"] = (record_date + timedelta(days=DIVIDEND_PENDING_WINDOW_DAYS)).isoformat()
                pending.append(item)
            else:
                history.append(item)

    upcoming.sort(key=lambda x: x["record_date"])
    pending.sort(key=lambda x: x["record_date"])
    history.sort(key=lambda x: x["record_date"], reverse=True)
    return {"as_of": today.isoformat(), "upcoming": upcoming, "pending": pending, "history": history,
            "pending_window_days": DIVIDEND_PENDING_WINDOW_DAYS}


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
                "Портфель обгоняет рынок за свой уровень риска — риск отрабатывает с запасом. Балл ведётся от альфы (сравнение с рынком), поэтому он высокий, хотя абсолютные Шарп/Сортино сейчас низкие у всего рынка из-за высокой ставки ОФЗ."
                if rr_score >= 60 else
                "Портфель идёт примерно вровень с рынком за свой риск. Абсолютные Шарп/Сортино сейчас низкие из-за высокой ставки ОФЗ — это режим всего рынка; балл же ведётся от альфы и сравнивает вас именно с рынком."
                if rr_score >= 40 else
                "За свой уровень риска портфель пока отстаёт от рынка. Это сравнение с рынком (альфа), оно не зависит от режима ставки — стоит посмотреть, какие бумаги тянут вниз."
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


_PERIOD_DAYS = {"1m": 30, "3m": 91, "6m": 182, "1y": 365, "3y": None, "max": None}


def compute_portfolio_metrics(db: Session, portfolio_id: int, compare_period: str = "3y") -> dict | None:
    """Аналитика портфеля из company_metrics одним запросом (Этап 1).

    Лёгкие метрики: P/E тек./ист. и дивдоходность по позициям, средневзвешенные
    по портфелю, распределение по секторам и классам активов, концентрация.
    Стоимость позиции = количество × последняя цена закрытия из quotes.
    Риск-метрики (beta/volatility) — Этап 2, здесь не считаются.

    compare_period — окно ТОЛЬКО для графика «Сравнение» (см. benchmark ниже);
    волатильность/бета/VaR/корреляции всегда считаются на фиксированном 3-летнем
    окне (since = window_start()) независимо от выбора пользователя — иначе
    короткий интервал (1М) тихо занизил бы риск-метрики, которые должны отражать
    устойчивую историю, а не текущий вид графика.
    """
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        return None

    equity_positions_raw = [p for p in portfolio.positions if p.instrument_type == "equity"]
    non_equity_raw = [p for p in portfolio.positions if p.instrument_type != "equity"]
    company_ids = [p.company_id for p in equity_positions_raw]
    if not company_ids and not non_equity_raw:
        return {
            "positions": [], "portfolio": {}, "sector_allocation": [],
            "asset_classes": [], "concentration": None, "correlation": None,
            "rates": {}, "benchmark": None,
        }

    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()} if company_ids else {}

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
    for p in equity_positions_raw:
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
            "price": round(price, 2) if price is not None else None,
            "quantity": float(p.quantity),
            "avg_buy_price": float(p.avg_buy_price),
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
            "instrument_type": "equity",
        })

    # Non-equity позиции (bond/future/fund/cash) — только текущая стоимость,
    # БЕЗ риск-метрик (бета/волатильность/корреляции честно null — не
    # посчитано, не «риска нет»). См. app/services/portfolio_instruments.py.
    if non_equity_raw:
        from app.services.portfolio_instruments import value_non_equity_positions
        for row in value_non_equity_positions(db, non_equity_raw):
            positions.append({
                **{k: None for k in (
                    "pe_current", "pe_historical", "div_yield", "volatility", "beta", "return_3y",
                    "history_years", "beta_source", "r_squared", "downside_vol", "var_95",
                    "earnings_yield", "return_total_3y", "alpha_3y", "sortino_3y", "capm_expected",
                )},
                "short_history": False,
                **row,
            })

    total_value = sum(p["value"] for p in positions if p["value"] is not None)
    for p in positions:
        p["weight_pct"] = round(p["value"] / total_value * 100, 2) if p["value"] and total_value > 0 else None

    # Апсайд к справедливой цене — ТОЛЬКО акции («справедливая цена» не применяется
    # к облигациям/фондам/фьючерсам, см. bond-analyst/fund-analyst). base — синтез
    # методов оценки из financials.json (валидированное суждение аналитика, тег
    # "суждение" — тот же, что на карточке компании во вкладке «Финансы», см.
    # FinanceTab.jsx "Справедливая стоимость — как сходятся методы"); цена — ЖИВАЯ
    # (quotes), а не замороженная на дату анализа meta.price_date — апсайд отражает
    # СЕГОДНЯШНЕЕ соотношение, дата анализа справедливой цены раскрыта отдельно
    # (fair_value_as_of), чтобы честно показать, насколько давно считался base.
    # Светофор недооценена/справедливо/переоценена — НАШ порог (не поле из файла:
    # verdict_word/confidence заполнены менее чем в 1% карточек), поэтому тоже
    # помечен "суждение".
    for p in positions:
        if p["instrument_type"] != "equity" or not p.get("price"):
            p["upside_to_fair_pct"] = None
            p["valuation_flag"] = None
            p["fair_value_as_of"] = None
            continue
        fin = _load_financials_json(p["ticker"])
        base = ((fin or {}).get("valuation") or {}).get("fair_value_range", {}).get("base") if fin else None
        if base is None:
            p["upside_to_fair_pct"] = None
            p["valuation_flag"] = None
            p["fair_value_as_of"] = None
            continue
        upside = round((base - p["price"]) / p["price"] * 100, 1)
        p["upside_to_fair_pct"] = upside
        p["valuation_flag"] = (
            "undervalued" if upside > 15 else "overvalued" if upside < -15 else "fair"
        )
        p["fair_value_as_of"] = (fin.get("meta") or {}).get("price_date")

    # Средневзвешенные по портфелю (нормировка только на позиции с метрикой).
    # Вырожденные случаи не валят расчёт: позиции с нулевой стоимостью
    # (0 шт. — застрявшие до фикса валидации) исключаются из весов; пустой
    # портфель и портфель из одной бумаги обрабатываются штатно.
    valued = [p for p in positions if p["value"]]
    portfolio_row = {
        # Грандтотал ПО ВСЕМ классам (акции+облигации+фьючерсы+фонды+кэш) —
        # фронт использует его для заголовочной суммы «Стоимость портфеля» и
        # для веса equity-строк в общей таблице, а не total_value одних акций.
        "total_value": round(total_value, 2),
        "pe_current": _weighted_avg([(p["value"], p["pe_current"]) for p in valued]),
        "pe_historical": _weighted_avg([(p["value"], p["pe_historical"]) for p in valued]),
        "div_yield": _weighted_avg([(p["value"], p["div_yield"]) for p in valued]),
        # бета и доходность портфеля линейны по весам → честное средневзвешенное
        "beta": _weighted_avg([(p["value"], p["beta"]) for p in valued]),
        "return_3y": _weighted_avg([(p["value"], p["return_3y"]) for p in valued]),
        "upside_to_fair_pct": _weighted_avg([(p["value"], p["upside_to_fair_pct"]) for p in valued]),
    }

    # Этап 2: корреляции и волатильность портфеля — НА ЛЕТУ (зависят от состава).
    # σ_p = √(wᵀΣw): НЕ среднее волатильностей — ковариация учитывает корреляции,
    # поэтому портфельная σ ниже за счёт диверсификации.
    from app.services.risk_metrics import (
        load_price_series, log_returns, pairwise_correlation,
        portfolio_volatility, risk_contributions, max_drawdown_pct, window_start,
        var_cvar_pct, daily_returns_ordered, rolling_window_returns, TRADING_DAYS,
    )
    since = window_start()
    returns_by_ticker = {}
    max_dd_by_ticker = {}
    tail_risk_by_ticker = {}   # VaR99/CVaR95/CVaR99 дневные + годовые (перекрывающиеся окна)
    for p in valued:
        cid = next((i for i, c in companies.items() if c.ticker == p["ticker"]), None)
        if cid is None:
            continue
        series = load_price_series(db, cid, since)
        max_dd_by_ticker[p["ticker"]] = max_drawdown_pct(series)
        rets = log_returns(series)
        if rets:
            returns_by_ticker[p["ticker"]] = rets
            daily_vals = list(rets.values())
            _, cvar95 = var_cvar_pct(daily_vals, 95.0)
            var99, cvar99 = var_cvar_pct(daily_vals, 99.0)
            annual_samples = rolling_window_returns(daily_returns_ordered(rets), TRADING_DAYS)
            var95_a, cvar95_a = var_cvar_pct(annual_samples, 95.0)
            var99_a, cvar99_a = var_cvar_pct(annual_samples, 99.0)
            tail_risk_by_ticker[p["ticker"]] = {
                "var_99": var99, "cvar_95": cvar95, "cvar_99": cvar99,
                "var_95_annual": var95_a, "cvar_95_annual": cvar95_a,
                "var_99_annual": var99_a, "cvar_99_annual": cvar99_a,
            }

    _TAIL_RISK_KEYS = ("var_99", "cvar_95", "cvar_99", "var_95_annual", "cvar_95_annual",
                       "var_99_annual", "cvar_99_annual")
    for p in positions:
        p["max_drawdown"] = max_dd_by_ticker.get(p["ticker"])
        tail = tail_risk_by_ticker.get(p["ticker"], {})
        for k in _TAIL_RISK_KEYS:
            p[k] = tail.get(k)

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

    risk_contrib = risk_contributions(returns_by_ticker, weights) if returns_by_ticker else None
    if risk_contrib:
        for p in positions:
            p["risk_contribution_pct"] = risk_contrib.get(p["ticker"])
    portfolio_row["return_total_3y"] = _weighted_avg([(p["value"], p["return_total_3y"]) for p in valued])

    # ── Этап 3: Шарп/Сортино/альфа портфеля + сравнение с бенчмарком ──
    # Rf/ERP — ЕДИНЫЙ источник с картой компании (live_wacc.py): ОФЗ-10л (тенор,
    # согласованный с длинным горизонтом акции) + ERP Дамодарана (mature market ERP
    # + country risk premium РФ) из config/market_params.json, а не историческая
    # доходность MCFTR за 3 года (шумный backward-looking прокси — храним отдельно
    # как факт-контекст, см. market_return_3y ниже, но CAPM/альфа/Шарп её больше
    # не используют).
    from app.services.moex_dividends import get_market_param, load_dividends_map
    from app.services.risk_metrics import load_index_series, load_erp_pct
    rf_1y_row = get_market_param(db, "risk_free_1y")
    rf_10y_row = get_market_param(db, "risk_free_10y")
    rm_row = get_market_param(db, "market_return_3y")
    erp = load_erp_pct()
    rates = {
        "risk_free_1y": rf_1y_row[0] if rf_1y_row else None,
        "risk_free_10y": rf_10y_row[0] if rf_10y_row else None,
        "risk_free_as_of": rf_10y_row[1].isoformat() if rf_10y_row and rf_10y_row[1] else None,
        "erp_pct": erp,   # ERP Дамодарана — реальный вход в CAPM ниже
        "market_return_3y": rm_row[0] if rm_row else None,   # факт-контекст, НЕ вход в CAPM
        "market_premium": (
            round(rm_row[0] - rf_1y_row[0], 2) if rf_1y_row and rm_row else None
        ),   # факт-контекст: фактическая премия рынка за 3 года минус Rf(1г)
    }

    # Шарп на бумагу (для группы «Риск»): (полная доходность − Rf) / её волатильность
    _rf = rates["risk_free_10y"]
    for p in positions:
        p["sharpe_3y"] = (
            round((p["return_total_3y"] - _rf) / p["volatility"], 2)
            if _rf is not None and p.get("return_total_3y") is not None
            and p.get("volatility") else None
        )

    r_total_p = portfolio_row["return_total_3y"]["value"]
    beta_p = portfolio_row["beta"]["value"]
    rf = rates["risk_free_10y"]
    portfolio_row["sharpe"] = (
        round((r_total_p - rf) / pf_volatility, 2)
        if None not in (r_total_p, rf) and pf_volatility else None
    )
    portfolio_row["alpha"] = (
        round(r_total_p - (rf + beta_p * erp), 2)
        if None not in (r_total_p, rf, erp, beta_p) else None
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

            # портфельный VaR/CVaR 95%/99% — дневной (историческая симуляция) и
            # годовой (перекрывающиеся 252-дневные окна того же дневного ряда,
            # УЖЕ с дивидендами через div_addon — см. rolling_window_returns).
            # CVaR (Expected Shortfall) — среднее ЗА порогом VaR: отвечает на
            # «а если попал в тот самый хвост — насколько плохо внутри», а не
            # только где проходит граница.
            from app.services.risk_metrics import var_cvar_pct, rolling_window_returns, TRADING_DAYS
            if len(pf_daily) >= 30:
                v95, c95 = var_cvar_pct(pf_daily, 95.0)
                v99, c99 = var_cvar_pct(pf_daily, 99.0)
                portfolio_row["var_95"] = v95
                portfolio_row["cvar_95"] = c95
                portfolio_row["var_99"] = v99
                portfolio_row["cvar_99"] = c99
                annual_samples = rolling_window_returns(pf_daily, TRADING_DAYS)
                v95a, c95a = var_cvar_pct(annual_samples, 95.0)
                v99a, c99a = var_cvar_pct(annual_samples, 99.0)
                portfolio_row["var_95_annual"] = v95a
                portfolio_row["cvar_95_annual"] = c95a
                portfolio_row["var_99_annual"] = v99a
                portfolio_row["cvar_99_annual"] = c99a

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

            # накопленные кривые (ПОЛНАЯ история, since=3г): портфель vs MCFTR
            # (обе с дивидендами) + IMOEX. max_drawdown — риск-метрика, всегда на
            # полном окне; для графика «Сравнение» ниже НАРЕЗАЕМ хвост по
            # compare_period и ПЕРЕБАЗИРУЕМ на 0% от начала выбранного окна —
            # так интервал-селектор не искажает волатильность/VaR/просадку выше
            # (те считаются один раз, на полном 3-летнем ряду).
            mcftr = load_index_series(db, "MCFTR", since)
            imoex = load_index_series(db, "IMOEX", since)
            full_dates, full_acc, full_mc, full_im = [], [], [], []
            acc = 1.0
            peak = 1.0
            max_dd = 0.0
            for d, r in zip(common_dates, pf_daily):
                acc *= (1 + r)
                if acc > peak:
                    peak = acc
                dd = (acc - peak) / peak
                if dd < max_dd:
                    max_dd = dd
                if d in mcftr and d in imoex:
                    full_dates.append(d)
                    full_acc.append(acc)
                    full_mc.append(mcftr[d])
                    full_im.append(imoex[d])
            portfolio_row["max_drawdown"] = round(max_dd * 100, 2)

            # ── Смешанный бенчмарк «по весам портфеля» (секторный, Brinson-style) ──
            # Изолирует эффект выбора БУМАГ от эффекта выбора СЕКТОРОВ: "портфель
            # vs MCFTR" не отвечает, обогнал ли портфель рынок из-за удачных бумаг
            # или просто из-за перевеса в растущем секторе. Строим как средневзвешенную
            # (по текущим долям equity-стоимости) кривую отраслевых TR-индексов MOEX
            # (SECTOR_TR_TICKERS), каждый rebased к 0% от НАЧАЛА full_dates. Секторы
            # без индекса (Машиностроение/Здравоохранение/Прочее) или с покрытием дат
            # <90% (обнаружено на METLTR/Телеком — MOEX перестал публиковать с марта
            # 2026) честно исключаются, веса перенормированы на покрытые, доля
            # покрытия раскрыта в ответе, не скрыта.
            from app.services.moex_history import SECTOR_TR_TICKERS
            sector_equity_value: dict[str, float] = {}
            for p in valued:
                if p["instrument_type"] == "equity":
                    sector_equity_value[p["sector"]] = sector_equity_value.get(p["sector"], 0.0) + p["value"]
            total_equity_value = sum(sector_equity_value.values())
            usable_sectors: dict[str, tuple[float, dict]] = {}
            if total_equity_value > 0 and full_dates:
                for s, v in sector_equity_value.items():
                    ticker = SECTOR_TR_TICKERS.get(s)
                    if not ticker:
                        continue
                    series = load_index_series(db, ticker, since)
                    coverage = len(set(series) & set(full_dates)) / len(full_dates)
                    if coverage >= 0.9:
                        usable_sectors[s] = (v, series)
            usable_value = sum(v for v, _ in usable_sectors.values())
            full_sb: list[float | None] = []
            if usable_value > 0:
                w_sector = {s: v / usable_value for s, (v, _) in usable_sectors.items()}
                last_known: dict[str, float] = {}
                for d in full_dates:
                    level = 0.0
                    wsum = 0.0
                    for s, (_, series) in usable_sectors.items():
                        if d in series:
                            last_known[s] = series[d]
                        if s in last_known:
                            level += w_sector[s] * last_known[s]
                            wsum += w_sector[s]
                    full_sb.append(level / wsum if wsum > 0 else None)

            if full_dates:
                cutoff_days = _PERIOD_DAYS.get(compare_period)
                if cutoff_days:
                    cutoff = date_cls.today() - timedelta(days=cutoff_days)
                    start_idx = next((i for i, d in enumerate(full_dates) if d >= cutoff), len(full_dates) - 1)
                else:
                    start_idx = 0
                sl_dates = full_dates[start_idx:]
                a0, m0, i0 = full_acc[start_idx], full_mc[start_idx], full_im[start_idx]
                pf_curve = [round((full_acc[k] / a0 - 1) * 100, 2) for k in range(start_idx, len(full_dates))]
                mc_curve = [round((full_mc[k] / m0 - 1) * 100, 2) for k in range(start_idx, len(full_dates))]
                im_curve = [round((full_im[k] / i0 - 1) * 100, 2) for k in range(start_idx, len(full_dates))]
                sb_curve = None
                if full_sb and full_sb[start_idx] is not None:
                    sb0 = full_sb[start_idx]
                    sb_curve = [
                        round((full_sb[k] / sb0 - 1) * 100, 2) if full_sb[k] is not None else None
                        for k in range(start_idx, len(full_dates))
                    ]
                step = max(1, len(sl_dates) // 260)   # прореживание для фронта
                youngest = min(valued, key=lambda p: p["history_years"] or 99)
                benchmark = {
                    "dates": [d.isoformat() for d in sl_dates[::step]],
                    "portfolio": pf_curve[::step],
                    "mcftr": mc_curve[::step],
                    "imoex": im_curve[::step],
                    "sector_blend": sb_curve[::step] if sb_curve else None,
                    "sector_blend_coverage_pct": (
                        round(usable_value / total_equity_value * 100, 1) if total_equity_value > 0 else None
                    ),
                    "sector_blend_covered_sectors": sorted(usable_sectors) if usable_sectors else [],
                    "sector_blend_excluded_sectors": sorted(set(sector_equity_value) - set(usable_sectors)),
                    "period": compare_period,
                    "period_years": round(len(sl_dates) / 252, 2),
                    "limited_by": youngest["ticker"] if (youngest.get("history_years") or 9) < 2.9 else None,
                    "portfolio_total_pct": pf_curve[-1] if pf_curve else None,
                    "benchmark_total_pct": mc_curve[-1] if mc_curve else None,
                    "sector_blend_total_pct": sb_curve[-1] if sb_curve else None,
                    "note": "веса позиций зафиксированы текущими долями (приближение)",
                }
    portfolio_row["sortino"] = sortino_p

    # CAPM-ожидание портфеля (модель) и earnings yield от портфельного P/E
    portfolio_row["capm"] = (
        round(rf + beta_p * erp, 2)
        if None not in (rf, erp, beta_p) else None
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

    # Классы активов — по факту instrument_type (акции/облигации/фьючерсы/
    # фонды/денежные средства), не хардкод «100% акции».
    ASSET_CLASS_NAME = {"equity": "Акции", "bond": "Облигации", "future": "Фьючерсы",
                        "fund": "Фонды", "cash": "Денежные средства"}
    by_class: dict[str, float] = {}
    for p in valued:
        by_class[p["instrument_type"]] = by_class.get(p["instrument_type"], 0.0) + p["value"]
    asset_classes = sorted(
        (
            {"name": ASSET_CLASS_NAME.get(k, k), "share_pct": round(v / total_value * 100, 2)}
            for k, v in by_class.items()
        ),
        key=lambda x: -x["share_pct"],
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

    # v2.1 (Фаза 1) — живёт РЯДОМ со старым quality (см. app/services/
    # portfolio_quality_v2.py), не заменяет его до приёмки методики владельцем.
    from app.services.portfolio_quality_v2 import compute_quality_index_v2
    quality_v2 = compute_quality_index_v2(
        db, positions=positions, total_value=total_value,
        correlation=correlation, sector_allocation=sector_allocation,
        volatility=portfolio_row["volatility"]["value"],
        var_95=portfolio_row.get("var_95"),
        max_drawdown=portfolio_row.get("max_drawdown"),
        alpha=portfolio_row.get("alpha"),
    )

    return {
        "positions": positions,
        "portfolio": portfolio_row,
        "sector_allocation": sector_allocation,
        "asset_classes": asset_classes,
        "concentration": concentration,
        "correlation": correlation,
        "rates": rates,
        "benchmark": benchmark,
        "quality": quality,
        "quality_v2": quality_v2,
        # Риск-метрики (волатильность/бета/Шарп/корреляции/кривая "если бы
        # держали") считаются ТОЛЬКО по equity-подпортфелю, честно перевзвешенному
        # среди самих акций — не по всему портфелю. Non-equity классы (облигации/
        # фьючерсы/фонды/кэш) входят в стоимость/веса/секторное распределение
        # выше, но не в эти цифры (для них пока нет истории доходности в модели).
        "risk_metrics_scope": "equity_only" if non_equity_raw else "all",
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


# ─────────────────────────────────────────────────────────────────────────
# Факторный профиль портфеля (чувствительность к ставке ЦБ) — читает
# quant_inputs.coefficients из companies/<TICKER>/macro.json (заполнено
# macro-analyst, ~сектор/голубые фишки + второй эшелон в раскатке).
# Честно: только канал "ставка" (per == "100bp", устойчивый маркер во всех
# файлах — driver не всегда заполнен). Курс рубля НЕ агрегируем: единицы
# в файлах несопоставимы (per=1_rub у одних компаний, per=1_usd у других,
# без единого нормирующего допущения) — раскатка честной агрегации фикса
# отдельная задача, не выдумываем число сейчас.
# ─────────────────────────────────────────────────────────────────────────
from pathlib import Path as _Path
import json as _json

_COMPANIES_DIR = _Path(__file__).parent.parent.parent / "companies"


def _load_macro_json(ticker: str) -> dict | None:
    path = _COMPANIES_DIR / ticker.upper() / "macro.json"
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_financials_json(ticker: str) -> dict | None:
    path = _COMPANIES_DIR / ticker.upper() / "financials.json"
    if not path.exists():
        return None
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def compute_factor_profile(db: Session, portfolio_id: int) -> dict | None:
    """Взвешенная чувствительность портфеля к ставке ЦБ (+100 б.п.), % от
    чистой прибыли покрытых бумаг. Возвращает None, если ни одна позиция не
    покрыта макро-данными (честная деградация — не выдуманное число)."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or not portfolio.positions:
        return None

    company_ids = [p.company_id for p in portfolio.positions]
    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}
    latest_by_company = {
        c.id: db.query(Quote.close).filter(Quote.company_id == c.id).order_by(Quote.date.desc()).first()
        for c in companies.values()
    }

    rows = []
    total_value = 0.0
    covered_value = 0.0
    for pos in portfolio.positions:
        company = companies.get(pos.company_id)
        if not company:
            continue
        price_row = latest_by_company.get(company.id)
        price = float(price_row[0]) if price_row and price_row[0] else float(pos.avg_buy_price)
        value = float(pos.quantity) * price
        total_value += value

        macro = _load_macro_json(company.ticker)
        if not macro:
            rows.append({"ticker": company.ticker, "value": value, "covered": False})
            continue
        coeffs = (macro.get("quant_inputs") or {}).get("coefficients") or {}
        rate_np_per_100bp = sum(
            c["net_profit"] for c in coeffs.values()
            if c.get("per") == "100bp" and c.get("net_profit") is not None
        )
        baseline_np = ((macro.get("quant_inputs") or {}).get("financials") or {}).get("net_profit")
        if not baseline_np:
            rows.append({"ticker": company.ticker, "value": value, "covered": False})
            continue
        pct_per_100bp = round(rate_np_per_100bp / baseline_np * 100, 1)
        rows.append({"ticker": company.ticker, "value": value, "covered": True, "pct_per_100bp": pct_per_100bp})
        covered_value += value

    if total_value <= 0 or covered_value <= 0:
        return None

    weighted = sum(r["pct_per_100bp"] * r["value"] for r in rows if r["covered"]) / covered_value
    return {
        "rate_pct_per_100bp": round(weighted, 1),
        "coverage_pct": round(covered_value / total_value * 100, 1),
        "covered_tickers": [r["ticker"] for r in rows if r["covered"]],
        "uncovered_tickers": [r["ticker"] for r in rows if not r["covered"]],
        "fx_available": False,
        "note": "Чувствительность к курсу рубля пока не агрегируется — единицы измерения в"
                " карточках компаний ещё не приведены к общему знаменателю по всем секторам.",
    }


# ─────────────────────────────────────────────────────────────────────────
# Свой сценарий стресс-теста: пользователь задаёт сдвиг ставки (б.п.) и/или
# индекса МосБиржи (%); просадка по позиции = бета × индексный шок (стандартная
# линейная аппроксимация CAPM) + ставочный канал из macro.json (net_profit на
# 100 б.п. как % от чистой прибыли компании, тот же метод, что и в
# compute_factor_profile, — допущение «P/E не меняется» ⇒ % прибыли ≈ % цены).
# Курс рубля НЕ применяется к расчёту (см. compute_factor_profile) — честно
# отражено в ответе, а не тихо игнорируется.
# ─────────────────────────────────────────────────────────────────────────
def compute_custom_stress(db: Session, portfolio_id: int, rate_shock_bp: float = 0.0,
                          index_shock_pct: float = 0.0, fx_shock_pct: float = 0.0) -> dict | None:
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or not portfolio.positions:
        return None

    company_ids = [p.company_id for p in portfolio.positions]
    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}
    metrics_by_ticker = {
        m.ticker: m for m in db.query(CompanyMetrics)
        .filter(CompanyMetrics.ticker.in_([c.ticker for c in companies.values()])).all()
    }
    latest_by_company = {
        c.id: db.query(Quote.close).filter(Quote.company_id == c.id).order_by(Quote.date.desc()).first()
        for c in companies.values()
    }

    rows = []
    total_value = 0.0
    for pos in portfolio.positions:
        company = companies.get(pos.company_id)
        if not company:
            continue
        price_row = latest_by_company.get(company.id)
        price = float(price_row[0]) if price_row and price_row[0] else float(pos.avg_buy_price)
        value = float(pos.quantity) * price
        total_value += value

        m = metrics_by_ticker.get(company.ticker)
        beta = float(m.beta) if m and m.beta is not None else 1.0  # честный рыночный дефолт
        index_component = beta * index_shock_pct

        macro = _load_macro_json(company.ticker)
        rate_component = 0.0
        rate_covered = False
        if macro and rate_shock_bp:
            coeffs = (macro.get("quant_inputs") or {}).get("coefficients") or {}
            rate_np_per_100bp = sum(
                c["net_profit"] for c in coeffs.values()
                if c.get("per") == "100bp" and c.get("net_profit") is not None
            )
            baseline_np = ((macro.get("quant_inputs") or {}).get("financials") or {}).get("net_profit")
            if baseline_np:
                rate_component = (rate_np_per_100bp / baseline_np * 100) * (rate_shock_bp / 100)
                rate_covered = True

        drop_pct = index_component + rate_component
        rows.append({
            "ticker": company.ticker, "name": company.name, "value": value,
            "drop_pct": round(drop_pct, 1), "value_loss": round(value * drop_pct / 100, 0),
            "beta": round(beta, 2), "rate_covered": rate_covered,
        })

    if total_value <= 0:
        return None

    portfolio_drop = sum(r["drop_pct"] * r["value"] for r in rows) / total_value
    portfolio_loss = total_value * portfolio_drop / 100
    return {
        "rate_shock_bp": rate_shock_bp, "index_shock_pct": index_shock_pct, "fx_shock_pct": fx_shock_pct,
        "fx_applied": False,
        "drop_pct": round(portfolio_drop, 1),
        "value_loss": round(portfolio_loss, 0),
        "positions": rows,
        "note": ("Ставочный канал учтён только для покрытых macro.json бумаг" if rate_shock_bp else None),
    }


# ─────────────────────────────────────────────────────────────────────────
# Стресс-тест портфеля v2 — ЕДИНЫЙ движок с общерыночным «Стресс-тестированием»
# (app/services/stress_numeric.py: _load_quant/_company_numeric_impact — те же
# коэффициенты чувствительности, тот же расчёт), взвешенный по РЕАЛЬНЫМ
# позициям пользователя (не по капитализации/весу голубых фишек, как на карте
# рынка). Владелец, 2026-07-24, дважды прямо попросил заменить старый расчёт
# (compute_custom_stress выше — beta×индекс + узкий rate-канал) на движок,
# СООТВЕТСТВУЮЩИЙ текущему блоку Стресс-тестирование: та же арифметика, те же
# числа по той же компании в обоих местах платформы (иначе «стык», CLAUDE.md).
#
# Побочная находка при разборе (не выдумано, видно в старом коде выше): пресеты
# «Ставка ЦБ +5%» (drop=11.8) и «Крах нефти» (drop=8.6) во фронте были
# ЗАХАРДКОЖЕНЫ константами, НЕ считались от реальных позиций портфеля вовсе —
# эта функция даёт им реальный расчёт.
#
# Допущение (то же, что было в compute_factor_profile/compute_custom_stress
# для ставочного канала): при неизменном P/E % изменения чистой прибыли ≈ %
# изменения цены акции — упрощение, явно раскрыто в ответе.
# ─────────────────────────────────────────────────────────────────────────
def compute_portfolio_stress_v2(db: Session, portfolio_id: int,
                                key_rate_pct: float | None = None,
                                fx_usdrub: float | None = None,
                                oil_brent_usd: float | None = None) -> dict | None:
    from sqlalchemy import text
    from app.services.stress_numeric import _load_quant, _company_numeric_impact

    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or not portfolio.positions:
        return None

    company_ids = [p.company_id for p in portfolio.positions]
    companies = {c.id: c for c in db.query(Company).filter(Company.id.in_(company_ids)).all()}
    latest_by_company = {
        c.id: db.query(Quote.close).filter(Quote.company_id == c.id).order_by(Quote.date.desc()).first()
        for c in companies.values()
    }

    brent_spot = None
    row = db.execute(text(
        "SELECT last_price FROM futures WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') "
        "AND last_price IS NOT NULL AND expiration_date >= now()::date "
        "ORDER BY expiration_date ASC LIMIT 1")).first()
    if row and row[0]:
        brent_spot = float(row[0])

    rows = []
    total_value = 0.0
    covered_value = 0.0
    for pos in portfolio.positions:
        company = companies.get(pos.company_id)
        if not company:
            continue
        price_row = latest_by_company.get(company.id)
        price = float(price_row[0]) if price_row and price_row[0] else float(pos.avg_buy_price)
        value = float(pos.quantity) * price
        total_value += value

        qi = _load_quant(company.ticker)
        if not qi or not (qi.get("coefficients") or {}):
            rows.append({"ticker": company.ticker, "name": company.name, "value": value, "covered": False})
            continue
        impact = _company_numeric_impact(qi, company.sector, key_rate_pct, fx_usdrub, oil_brent_usd, brent_spot)
        np_metric = impact["metrics"].get("net_profit") or {}
        pct, delta_bn, base_bn = np_metric.get("pct_of_base"), np_metric.get("delta_bn"), np_metric.get("base_bn")
        if pct is None and delta_bn is not None and base_bn:
            # backend честно подавляет % при |Δ|>2×база (вырожденный случай) —
            # для стресс-теста портфеля (не таблица точных чисел) считаем сами,
            # не подставляем плоскую константу (та же логика, что в
            # StressTestView.jsx: tilePct()).
            pct = round(delta_bn / abs(base_bn) * 100, 1)
        if pct is None:
            rows.append({"ticker": company.ticker, "name": company.name, "value": value, "covered": False})
            continue
        rows.append({
            "ticker": company.ticker, "name": company.name, "value": value, "covered": True,
            "drop_pct": round(pct, 1), "value_loss": round(value * pct / 100, 0),
        })
        covered_value += value

    if total_value <= 0:
        return None
    covered_rows = [r for r in rows if r["covered"]]
    if not covered_rows:
        return None

    covered_rows.sort(key=lambda r: -abs(r["drop_pct"]))
    portfolio_drop = sum(r["drop_pct"] * r["value"] for r in covered_rows) / covered_value
    portfolio_loss = total_value * portfolio_drop / 100
    return {
        "drop_pct": round(portfolio_drop, 1),
        "value_loss": round(portfolio_loss, 0),
        "coverage_pct": round(covered_value / total_value * 100, 1),
        "positions": covered_rows,
        "uncovered_tickers": [r["ticker"] for r in rows if not r["covered"]],
        "inputs": {"key_rate_pct": key_rate_pct, "fx_usdrub": fx_usdrub, "oil_brent_usd": oil_brent_usd},
        "assumption": "При неизменном P/E % изменения чистой прибыли ≈ % изменения цены акции.",
        "is_demo": True,
    }
