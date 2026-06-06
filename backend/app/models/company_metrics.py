from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class CompanyMetrics(Base):
    """Числовые метрики компании для агрегаций по портфелю.

    Источник правды — файлы companies/<TICKER>/financials.json (и история
    дивидендов из governance.json); таблица наполняется из них скриптом
    scripts/sync_company_metrics.py. Карточка компании продолжает читать файлы.

    beta / volatility — задел под Этап 2 (история котировок), сейчас NULL.
    """
    __tablename__ = "company_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    sector: Mapped[str | None] = mapped_column(String(100))
    pe_current: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pe_historical: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    div_yield: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fair_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    beta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))           # итоговая показываемая (= moex || calc)
    volatility: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))      # годовая, %
    return_3y: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))     # CAGR за окно, % (факт, не прогноз)
    history_years: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # глубина истории для пометки «*»
    # ── Этап 2.2: гибридная бета и доп. коэффициенты ──
    beta_moex: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))      # официальная (fortscoefficients, MIX)
    beta_calc: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))      # наш расчёт (Диммсон −1..+1)
    beta_source: Mapped[str | None] = mapped_column(String(10))           # 'moex' | 'calc'
    beta_moex_date = mapped_column(Date, nullable=True)                   # дата файла коэффициентов
    r_squared: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))      # corr² — итоговый (moex || calc)
    r_squared_moex: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    downside_vol: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))   # σ доходностей <0, ×√252, %
    var_95: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))         # ист. VaR 95%, дневной, % потери
    earnings_yield: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # 1/PE, %
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
