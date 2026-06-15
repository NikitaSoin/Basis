"""Модель ИИ-обозревательского отчёта (Обозреватель, Направление 5).

Синтез-слой: пересобирает данные направлений 1-4,6,7 + портфель в сводный дайджест
трёх глубин. Сохраняется per-user (история видна только владельцу).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

REPORT_TYPES = ("express", "detailed", "deep")
HORIZON_DAYS = {"express": 2, "detailed": 7, "deep": 30}


class ObserverReport(Base):
    __tablename__ = "observer_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)  # express|detailed|deep
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)            # markdown-текст отчёта
    source_refs: Mapped[list | None] = mapped_column(JSONB)      # [{ref,kind,id/ticker,title,url}]
    portfolio_snapshot: Mapped[list | None] = mapped_column(JSONB)  # тикеры портфеля на момент
    model_used: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
