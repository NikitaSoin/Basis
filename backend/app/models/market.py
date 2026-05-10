import enum
from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum as SAEnum, String, Text
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
