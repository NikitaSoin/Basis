"""Модель геополитики (Обозреватель, Направление 7).

GeoBlock — синтез на регион×вкладку (обзор/глубокая аналитика) по geo_methodology.md.
Источники живут в конфиге config/geo_sources.json (не в БД, не в выдаче).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

GEO_REGIONS = ("svo", "middle_east", "atr")
GEO_TABS = ("overview", "deep")


class GeoBlock(Base):
    __tablename__ = "geo_blocks"
    __table_args__ = (UniqueConstraint("region", "tab", name="uq_geo_block_region_tab"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False)   # svo|middle_east|atr
    tab: Mapped[str] = mapped_column(String(16), nullable=False)      # overview|deep
    title: Mapped[str | None] = mapped_column(String(120))
    status_text: Mapped[str | None] = mapped_column(Text)            # нейтральная фактура
    channels: Mapped[list | None] = mapped_column(JSONB)            # [{channel, effect}]
    scenarios: Mapped[dict | None] = mapped_column(JSONB)          # {base,bull,bear}
    market_impact: Mapped[str | None] = mapped_column(Text)        # «что значит для рынков»
    affected_sectors: Mapped[list | None] = mapped_column(JSONB)
    affected_tickers: Mapped[list | None] = mapped_column(JSONB)
    source_count: Mapped[int | None] = mapped_column()             # сколько статей в синтезе
    model_used: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
