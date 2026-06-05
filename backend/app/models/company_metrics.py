from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, Numeric, String
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
    beta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    volatility: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
