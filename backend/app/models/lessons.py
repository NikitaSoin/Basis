"""Уроки агентов — процедурная память: что проверяющий уже ловил и что делать."""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AgentLesson(Base):
    __tablename__ = "agent_lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False, index=True)
    contour: Mapped[str] = mapped_column(String(16), nullable=False, index=True)   # macro | inst_state | geo
    rule: Mapped[str] = mapped_column(String(200), nullable=False)
    where: Mapped[str | None] = mapped_column(String(300))
    example: Mapped[str | None] = mapped_column(Text)
    fix: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str | None] = mapped_column(String(20))
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    clean_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active", index=True)  # active | settled
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_review_id: Mapped[int | None] = mapped_column(Integer)
