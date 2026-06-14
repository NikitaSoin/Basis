import enum
from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Enum as SAEnum, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class OverviewType(str, enum.Enum):
    express = "express"
    detailed = "detailed"
    deep = "deep"


# Допустимые значения (валидация на уровне приложения; в БД — String для простоты
# миграций, принцип «простые решения»). Переиспользуются направлениями Обозревателя.
NEWS_SOURCES = ("interfax", "rbc", "kommersant")
NEWS_RUBRICS = ("economy", "investments", "politics_world")
NEWS_IMPORTANCE = ("high", "medium", "low")
NEWS_STATUS = ("published", "filtered_out")


class MarketUpdate(Base):
    """Единица Ленты новостей Обозревателя (Направление 1).

    Исходно простая таблица расширена под конвейер новостей: выжимка + ИИ-коммент
    «на что влияет» + теги бумаг/секторов. title/content сохранены для обратной
    совместимости (title = заголовок; content — анонс/опционально, полные тексты
    статей НЕ храним: только summary + ссылка source_url).
    """
    __tablename__ = "market_updates"
    __table_args__ = (
        Index("ix_market_updates_status_published", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)  # legacy/анонс, опционально
    source: Mapped[str | None] = mapped_column(String(64))  # interfax|rbc|kommersant
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # --- поля Ленты новостей ---
    source_url: Mapped[str | None] = mapped_column(String(1000), index=True)  # дедуп «новых»
    original_title: Mapped[str | None] = mapped_column(String(500))
    rubric: Mapped[str | None] = mapped_column(String(32))
    importance: Mapped[str | None] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(Text)
    impact_comment: Mapped[str | None] = mapped_column(Text)
    affected_tickers: Mapped[list | None] = mapped_column(JSONB)  # ["SBER", ...]
    affected_sectors: Mapped[list | None] = mapped_column(JSONB)  # ["banks", ...]
    cluster_id: Mapped[str | None] = mapped_column(String(64), index=True)  # группа дублей
    sources_json: Mapped[list | None] = mapped_column(JSONB)  # [{source,url}] все источники события
    model_used: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="published")  # published|filtered_out
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
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
