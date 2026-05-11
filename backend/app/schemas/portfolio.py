from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class PositionCreate(BaseModel):
    company_id: int
    quantity: Decimal
    avg_buy_price: Decimal


class PositionResponse(BaseModel):
    id: int
    portfolio_id: int
    company_id: int
    quantity: Decimal
    avg_buy_price: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class PortfolioCreate(BaseModel):
    user_id: int = 1
    name: str
    description: str | None = None


class PortfolioResponse(BaseModel):
    id: int
    user_id: int
    name: str
    description: str | None
    created_at: datetime
    positions: list[PositionResponse] = []

    model_config = {"from_attributes": True}
