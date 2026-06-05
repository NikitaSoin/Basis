import enum
from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Enum as SAEnum, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class OverviewType(str, enum.Enum):
    express = "express"
    detailed = "detailed"
    deep = "deep"


class MarketUpdate(Base):
    __tablename__ = "market_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MarketOverview(Base):
    __tablename__ = "market_overviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    overview_type: Mapped[OverviewType] = mapped_column(SAEnum(OverviewType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class IndexHistory(Base):
    """Дневная история бенчмарк-индексов (IMOEX, RTSI, MCFTR) с MOEX ISS.

    Отдельная таблица, а не записи в quotes: quotes привязана к companies
    через FK, а индекс — не компания (см. миграцию c7e91f3a5d20).
    """
    __tablename__ = "index_history"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_index_history_ticker_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    high: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))  # оборот, руб
