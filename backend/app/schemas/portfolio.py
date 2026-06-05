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
    user_id: int | None = None
    name: str
    description: str | None = None


class PortfolioResponse(BaseModel):
    id: int
    user_id: int | None
    name: str
    description: str | None
    created_at: datetime
    positions: list[PositionResponse] = []

    model_config = {"from_attributes": True}


# ── Аналитические метрики портфеля (Этап 1) ──

class PositionMetrics(BaseModel):
    ticker: str
    name: str
    sector: str
    value: float | None          # текущая стоимость позиции, ₽
    weight_pct: float | None     # доля в портфеле, %
    pe_current: float | None
    pe_historical: float | None
    div_yield: float | None      # %


class WeightedMetric(BaseModel):
    """Средневзвешенное значение + честное «по n из m позиций»."""
    value: float | None
    n: int
    m: int


class PortfolioWeighted(BaseModel):
    pe_current: WeightedMetric | None = None
    pe_historical: WeightedMetric | None = None
    div_yield: WeightedMetric | None = None


class SectorSlice(BaseModel):
    sector: str
    value: float
    share_pct: float


class AssetClassSlice(BaseModel):
    name: str
    share_pct: float


class Concentration(BaseModel):
    largest_ticker: str
    largest_pct: float
    top3_pct: float


class PortfolioMetricsResponse(BaseModel):
    positions: list[PositionMetrics]
    portfolio: PortfolioWeighted
    sector_allocation: list[SectorSlice]
    asset_classes: list[AssetClassSlice]
    concentration: Concentration | None
