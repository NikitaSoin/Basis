from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioCreate, PortfolioMetricsResponse, PortfolioResponse,
    PositionCreate, PositionResponse,
)
from app.services.portfolio import (
    get_portfolios_by_user, get_portfolio_by_id,
    create_portfolio, add_position, delete_position,
    compute_portfolio_metrics,
)
from app.auth import get_current_user, get_current_user_optional
from app.models.user import User, SubscriptionType

FREE_POSITION_LIMIT = 5

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
