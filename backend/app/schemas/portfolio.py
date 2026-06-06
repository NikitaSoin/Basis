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
    # Этап 2 — риск-метрики из истории котировок
    volatility: float | None = None    # годовая, %
    beta: float | None = None          # итоговая (MOEX, иначе расчёт)
    return_3y: float | None = None     # CAGR, % годовых (факт, не прогноз)
    history_years: float | None = None
    short_history: bool = False        # история <1 года → «*» в UI
    # Этап 2.2 — источник беты и доп. коэффициенты
    beta_source: str | None = None     # 'moex' | 'calc'
    r_squared: float | None = None     # доля движения, объяснённая рынком (0..1)
    downside_vol: float | None = None  # нисходящая σ (порог 0), годовая %
    var_95: float | None = None        # ист. VaR 95%, дневной, % потери
    earnings_yield: float | None = None  # 1/PE, %


class WeightedMetric(BaseModel):
    """Средневзвешенное значение + честное «по n из m позиций»."""
    value: float | None
    n: int
    m: int


class PortfolioWeighted(BaseModel):
    pe_current: WeightedMetric | None = None
    pe_historical: WeightedMetric | None = None
    div_yield: WeightedMetric | None = None
    beta: WeightedMetric | None = None          # средневзвешенная (бета линейна по весам)
    return_3y: WeightedMetric | None = None     # средневзвешенный факт 3 лет
    volatility: WeightedMetric | None = None    # σ_p = √(wᵀΣw) — через ковариации, не среднее


class CorrelationMatrix(BaseModel):
    tickers: list[str]
    matrix: list[list[float | None]]   # None — мало совпадающих дат у пары
    low_overlap: bool = False          # есть пары с пересечением < полугода


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
    correlation: CorrelationMatrix | None = None
