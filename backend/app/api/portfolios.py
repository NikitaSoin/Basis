from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse, PositionCreate, PositionResponse
from app.services.portfolio import (
    get_all_portfolios, get_portfolio_by_id,
    create_portfolio, add_position, delete_position,
)

router = APIRouter()


@router.post("/portfolios", response_model=PortfolioResponse, status_code=status.HTTP_201_CREATED)
def create_portfolio_endpoint(data: PortfolioCreate, db: Session = Depends(get_db)):
    return create_portfolio(db, data)


@router.get("/portfolios", response_model=list[PortfolioResponse])
def list_portfolios_endpoint(db: Session = Depends(get_db)):
    return get_all_portfolios(db)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
def get_portfolio_endpoint(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = get_portfolio_by_id(db, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.post("/portfolios/{portfolio_id}/positions", response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
def add_position_endpoint(portfolio_id: int, data: PositionCreate, db: Session = Depends(get_db)):
    if not get_portfolio_by_id(db, portfolio_id):
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return add_position(db, portfolio_id, data)


@router.delete("/portfolios/{portfolio_id}/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_position_endpoint(portfolio_id: int, position_id: int, db: Session = Depends(get_db)):
    if not delete_position(db, portfolio_id, position_id):
        raise HTTPException(status_code=404, detail="Position not found")
