from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioDividendsResponse, PortfolioMetricsResponse, PortfolioResponse,
    PositionCreate, PositionResponse, PositionUpdate, TradeCreate, TradeResponse,
)
from app.services.portfolio import (
    get_portfolios_by_user, get_portfolio_by_id,
    create_portfolio, add_position, delete_position, update_position,
    compute_portfolio_metrics, compute_factor_profile, compute_custom_stress,
    record_trade, compute_position_pnl, compute_portfolio_dividends,
)
from app.services.portfolio_diagnosis import generate_diagnosis
from app.auth import get_current_user, get_current_user_optional
from app.models.user import User, SubscriptionType

# Подписок/оплаты на платформе пока нет (тарифы — витрина), лимит в 5 позиций
# блокировал реальное использование (баг «6-я позиция не добавляется»).
# Технический потолок оставлен; вернуть продуктовый лимит — при запуске тарифов.
FREE_POSITION_LIMIT = 50

router = APIRouter()


@router.post("/portfolios", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio_endpoint(
    data: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data.user_id = current_user.id
    return create_portfolio(db, data)


@router.get("/portfolios", response_model=list[PortfolioResponse])
def list_portfolios_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_portfolios_by_user(db, current_user.id)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return portfolio


@router.post("/portfolios/{portfolio_id}/positions", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def add_position_endpoint(
    portfolio_id: int,
    data: PositionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    if current_user.subscription_type == SubscriptionType.free:
        if len(portfolio.positions) >= FREE_POSITION_LIMIT:
            raise HTTPException(
                status_code=403,
                detail=f"Free-тариф: максимум {FREE_POSITION_LIMIT} позиций. Перейдите на Premium.",
            )

    return add_position(db, portfolio_id, data)


@router.patch("/portfolios/{portfolio_id}/positions/{position_id}", response_model=PositionResponse)
def update_position_endpoint(
    portfolio_id: int,
    position_id: int,
    data: PositionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Прямое редактирование позиции: количество и/или средняя цена покупки."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    position = update_position(
        db, portfolio_id, position_id,
        quantity=data.quantity, avg_buy_price=data.avg_buy_price,
    )
    if not position:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    return position


@router.post("/portfolios/{portfolio_id}/positions/{position_id}/trades", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def record_trade_endpoint(
    portfolio_id: int,
    position_id: int,
    data: TradeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Совершить сделку (не исправление) — заводит запись в истории и
    пересчитывает qty/среднюю по методу средневзвешенной цены."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    try:
        position = record_trade(db, portfolio_id, position_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not position:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    return position


@router.get("/portfolios/{portfolio_id}/positions/{position_id}/pnl")
def position_pnl_endpoint(
    portfolio_id: int,
    position_id: int,
    current_price: float | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Реализовано / не реализовано / дивиденды получено / комиссии уплачено —
    из истории сделок позиции (см. compute_position_pnl)."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    result = compute_position_pnl(db, portfolio_id, position_id, current_price)
    if result is None:
        raise HTTPException(status_code=404, detail="Позиция не найдена или нет истории сделок")
    return result


@router.get("/portfolios/{portfolio_id}/metrics", response_model=PortfolioMetricsResponse)
def portfolio_metrics_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Лёгкие аналитические метрики портфеля (Этап 1): P/E и дивдоходность
    позиций из company_metrics, средневзвешенные по портфелю, распределение
    по секторам/классам активов, концентрация."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return compute_portfolio_metrics(db, portfolio_id)


@router.get("/portfolios/{portfolio_id}/dividends", response_model=PortfolioDividendsResponse)
def portfolio_dividends_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Дивиденды по позициям портфеля — три сегмента по датам: upcoming
    (отсечка впереди) / pending (отсечка прошла, оценка окна зачисления) /
    history (окно прошло). См. compute_portfolio_dividends."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return compute_portfolio_dividends(db, portfolio_id)


@router.get("/portfolios/{portfolio_id}/factor-profile")
def portfolio_factor_profile_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Взвешенная чувствительность портфеля к ставке ЦБ (вкладка «ИИ-Диагноз»),
    из quant_inputs.coefficients в companies/<TICKER>/macro.json. Возвращает
    null, если ни одна позиция не покрыта макро-данными (честная деградация)."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    return compute_factor_profile(db, portfolio_id)


@router.get("/portfolios/{portfolio_id}/stress-test")
def portfolio_custom_stress_endpoint(
    portfolio_id: int,
    rate_shock_bp: float = 0.0,
    index_shock_pct: float = 0.0,
    fx_shock_pct: float = 0.0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Свой сценарий стресс-теста («Стресс-тест» → «+ Свой сценарий»): просадка
    по позиции = бета×индексный шок + ставочный канал из macro.json (где
    покрыто). Курс рубля пока НЕ применяется к расчёту (fx_applied=false)."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    result = compute_custom_stress(db, portfolio_id, rate_shock_bp, index_shock_pct, fx_shock_pct)
    if result is None:
        raise HTTPException(status_code=404, detail="Недостаточно данных для расчёта")
    return result


def _serialize_diagnosis(diag) -> dict:
    return {
        "shield": diag.shield or [],
        "vulnerabilities": diag.vulnerabilities or [],
        "summary": {"text": diag.summary, "type": diag.summary_type} if diag.summary else None,
        "portfolio_snapshot": diag.portfolio_snapshot or [],
        "generated_at": diag.generated_at.isoformat() if diag.generated_at else None,
    }


@router.get("/portfolios/{portfolio_id}/diagnosis")
def portfolio_diagnosis_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Кэшированный ИИ-Диагноз портфеля (вкладка «ИИ-Диагноз»). null, если ещё
    ни разу не сгенерирован — фронт предлагает нажать «Обновить диагноз»."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    from app.models.portfolio_diagnosis import PortfolioDiagnosis
    diag = db.query(PortfolioDiagnosis).filter_by(portfolio_id=portfolio_id).first()
    return _serialize_diagnosis(diag) if diag else None


@router.post("/portfolios/{portfolio_id}/diagnosis/refresh")
def portfolio_diagnosis_refresh_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Перегенерировать ИИ-Диагноз (LLM-вызов — по кнопке, не на каждый рендер)."""
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    if portfolio.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")
    try:
        diag = generate_diagnosis(db, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Не удалось сгенерировать диагноз: {e}")
    if diag is None:
        raise HTTPException(status_code=404, detail="Недостаточно данных портфеля для диагноза")
    return _serialize_diagnosis(diag)


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio_endpoint(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Портфель не найден")
    db.delete(portfolio)
    db.commit()


@router.delete("/portfolios/{portfolio_id}/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position_endpoint(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio or portfolio.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    if not delete_position(db, portfolio_id, position_id):
        raise HTTPException(status_code=404, detail="Позиция не найдена")
