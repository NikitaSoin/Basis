"""Реестр прогонов качества — эпизодическая память системы.

Без него нельзя ни отладить агента, ни сравнить две версии промпта: «стало
лучше» — это утверждение о ДВУХ прогонах, а не об одном. Одна строка на прогон
плюс находки.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class QualityRun(Base):
    __tablename__ = "quality_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # 🔴 Прогоны с разными версиями набора сравнивать нельзя: «качество выросло»
    # окажется «проверок стало меньше».
    checks_version: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    subjects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))    # доля не-skip
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))       # доля без грубых находок
    soft_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    invalid_reason: Mapped[str | None] = mapped_column(Text)

    golden_total: Mapped[int | None] = mapped_column(Integer)
    golden_passed: Mapped[int | None] = mapped_column(Integer)

    per_check: Mapped[dict | None] = mapped_column(JSON)
    triggered_by: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)

    findings = relationship("QualityFinding", back_populates="run",
                            cascade="all, delete-orphan")


class QualityFinding(Base):
    __tablename__ = "quality_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("quality_runs.id", ondelete="CASCADE"),
                                        nullable=False, index=True)
    check_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSON)

    run = relationship("QualityRun", back_populates="findings")


Index("ix_quality_findings_run_check", QualityFinding.run_id, QualityFinding.check_id)
Index("ix_quality_runs_pipeline_started", QualityRun.pipeline, QualityRun.started_at)
