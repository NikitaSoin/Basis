from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator

INSTRUMENT_TYPES = ("equity", "bond", "future", "fund", "cash")


class PositionCreate(BaseModel):
    company_id: int | None = None
    instrument_type: str = Field(default="equity", pattern="^(equity|bond|future|fund|cash)$")
    secid: str | None = None       # non-equity: SECID из bonds/futures/funds
    currency: str = "RUB"
    # gt=0: позиция с нулём/минусом акций ломала расчёт долей и метрик —
    # такие значения отбрасываются на входе (защита в корне)
    quantity: Decimal = Field(gt=0)
    avg_buy_price: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def _check_instrument_reference(self) -> "PositionCreate":
        if self.instrument_type == "equity":
            if not self.company_id:
                raise ValueError("equity-позиции нужен company_id")
            self.secid = None
        elif self.instrument_type == "cash":
            # денежные средства — всегда номинал, avg_buy_price не имеет
            # смысла (нет «цены покупки» у рубля), фиксируем на 1.
            self.company_id = None
            self.secid = None
            self.avg_buy_price = Decimal("1")
        else:  # bond | future | fund
            if not self.secid:
                raise ValueError(f"{self.instrument_type}-позиции нужен secid")
            self.company_id = None
        return self


class PositionUpdate(BaseModel):
    """Прямое редактирование позиции (количество / средняя цена)."""
    quantity: Decimal | None = Field(default=None, gt=0)
    avg_buy_price: Decimal | None = Field(default=None, gt=0)


class TradeCreate(BaseModel):
    """Сделка (не прямое исправление) — заводит запись в portfolio_transactions
    и пересчитывает qty/avg_buy_price позиции по методу средневзвешенной цены."""
    side: str = Field(pattern="^(buy|sell)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    trade_date: date


class TradeResponse(BaseModel):
    id: int
    position_id: int
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    trade_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    id: int
    portfolio_id: int
    company_id: int | None
    instrument_type: str = "equity"
    secid: str | None = None
    currency: str = "RUB"
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
    instrument_type: str = "equity"  # equity|bond|future|fund|cash
    data_flag: str | None = None     # non-equity: почему value=None, если не удалось оценить
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
    sharpe_3y: float | None = None        # (R_total − Rf) / volatility
    capm_expected: float | None = None    # CAPM-ожидание (модель), % годовых
    max_drawdown: float | None = None         # макс. просадка за окно, % (отрицательное)
    risk_contribution_pct: float | None = None  # доля в ОБЩЕМ РИСКЕ портфеля, % (сумма=100)


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
    capm: float | None = None                   # CAPM-ожидание портфеля (модель)
    earnings_yield: float | None = None         # 1 / P/E портфеля, %
    var_95: float | None = None                 # дневной VaR 95% портфеля, % потери
    downside_vol: float | None = None           # нисходящая σ портфеля, годовая %
    r_squared: float | None = None              # R² портфеля против IMOEX
    max_drawdown: float | None = None           # макс. просадка накопленной кривой портфеля, %


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


class CorrPair(BaseModel):
    a: str
    b: str
    value: float


class CorrelationMatrix(BaseModel):
    tickers: list[str]
    matrix: list[list[float | None]]   # None — мало совпадающих дат у пары
    low_overlap: bool = False          # есть пары с пересечением < полугода
    avg: float | None = None           # средняя попарная корреляция
    strongest_pair: CorrPair | None = None  # самая связанная (мало диверсификации)
    weakest_pair: CorrPair | None = None     # самая «разбавляющая» риск


class QualityComponent(BaseModel):
    name: str
    value: str
    score: int | None = None           # None — показатель-контекст без балла


class QualitySubindex(BaseModel):
    key: str
    label: str
    score: int
    confidence: str | None = None      # факт | оценка | суждение
    components: list[QualityComponent] = []
    verdict: str
    limitation: str | None = None


class QualityIndex(BaseModel):
    overall: int | None
    label: str | None
    subindices: list[QualitySubindex]
    weights: dict[str, float]
    note: str


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
    quality: QualityIndex | None = None
    risk_metrics_scope: str | None = None  # "equity_only" | "all" — честная граница риск-метрик
