"""Дайджест отдельных статей (Обозреватель): Рыбарь / re:russia / Carnegie и др.

В отличие от geo.py (GeoBlock — слитый синтез на регион), здесь каждая статья —
отдельная карточка: пересказ + «зачем это инвестору». target определяет адресата:
региональная вкладка Геополитики (svo|middle_east|atr) или лента «Институциональная
среда» (institutions). Источник/автор/URL — только внутри БД (дедуп), в API и на
фронте не показываются (geo_methodology.md, раздел 7: без ссылок на источники).
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

GEO_DIGEST_TARGETS = ("svo", "middle_east", "atr", "institutions")


class GeoDigestArticle(Base):
    __tablename__ = "geo_digest_articles"
    __table_args__ = (UniqueConstraint("source_url", name="uq_geo_digest_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    investor_relevance: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date_type | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_key: Mapped[str | None] = mapped_column(String(32))
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
