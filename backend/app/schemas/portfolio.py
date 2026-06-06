from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class PositionCreate(BaseModel):
    company_id: int
    # gt=0: позиция с нулём/минусом акций ломала расчёт долей и метрик —
    # такие значения отбрасываются на входе (защита в корне)
    quantity: Decimal = Field(gt=0)
    avg_buy_price: Decimal = Field(gt=0)


class PositionUpdate(BaseModel):
    """Прямое редактирование позиции (количество / средняя цена)."""
    quantity: Decimal | None = Field(default=None, gt=0)
    avg_buy_price: Decimal | None = Field(default=None, gt=0)


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
    company_id: int | None = None   # для перехода в карточку компании из портфеля
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
    # Этап 3 — полная доходность и коэффициенты на базе безрисковой ставки
    return_total_3y: float | None = None  # цена + дивиденды, % годовых (факт)
    alpha_3y: float | None = None         # альфа Дженсена, % годовых
    sortino_3y: float | None = None       # (R_total − Rf) / downside_vol
    capm_expected: float | None = None    # CAPM-ожидание (модель), % годовых


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
    return_3y: WeightedMetric | None = None     # средневзвешенный факт 3 лет (ценовая)
    return_total_3y: WeightedMetric | None = None  # полная (с дивидендами)
    volatility: WeightedMetric | None = None    # σ_p = √(wᵀΣw) — через ковариации, не среднее
    # Этап 3 — на базе безрисковой ставки (все члены годовые, %)
    sharpe: float | None = None                 # (R_total − Rf) / σ_p
    sortino: float | None = None                # (R_total − Rf) / downside-σ портфеля
    alpha: float | None = None                  # альфа Дженсена портфеля


class MarketRates(BaseModel):
    risk_free_1y: float | None = None           # ОФЗ ~1г, точка G-curve, %
    risk_free_as_of: str | None = None
    market_return_3y: float | None = None       # CAGR MCFTR за окно, %
    market_premium: float | None = None         # Rm − Rf, %


class BenchmarkSeries(BaseModel):
    dates: list[str]
    portfolio: list[float]                      # накопленная total-доходность, %
    mcftr: list[float]                          # бенчмарк полной доходности, %
    imoex: list[float]                          # ценовой индекс, для справки
    period_years: float
    limited_by: str | None = None               # тикер самой молодой бумаги
    portfolio_total_pct: float | None = None
    benchmark_total_pct: float | None = None
    note: str | None = None


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
    rates: MarketRates | None = None
    benchmark: BenchmarkSeries | None = None
