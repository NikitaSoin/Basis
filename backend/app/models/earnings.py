"""Модели направления «Анализ отчётностей» (Обозреватель, Направление 3).

EarningsReport — факт выхода отчёта (период/стандарт/источник).
EarningsFigures — извлечённые headline-цифры (строго из источника, без выдумок).
EarningsDigest — ознакомительный «Разбор отчёта» (LLM, по шаблону, без таргетов).
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class EarningsReport(Base):
    __tablename__ = "earnings_reports"
    __table_args__ = (
        UniqueConstraint("ticker", "period", "standard", name="uq_earnings_report"),
        Index("ix_earnings_reports_published", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(24), nullable=False)   # "2025" | "1кв2026"
    standard: Mapped[str | None] = mapped_column(String(16))          # МСФО | РСБУ | опер.
    report_type: Mapped[str | None] = mapped_column(String(24))       # annual | quarter | operating
    published_at: Mapped[date_type | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(40))            # smartlab | ...
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_file_ref: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(24), default="processed")  # processed | extracting | extract_failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    figures: Mapped["EarningsFigures"] = relationship(back_populates="report", uselist=False,
                                                      cascade="all, delete-orphan")
    digest: Mapped["EarningsDigest"] = relationship(back_populates="report", uselist=False,
                                                    cascade="all, delete-orphan")


class EarningsFigures(Base):
    __tablename__ = "earnings_figures"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("earnings_reports.id", ondelete="CASCADE"),
                                           nullable=False, unique=True)
    # headline-набор (млрд ₽, если не указано иное); nullable — не выдумываем
    revenue_q: Mapped[float | None] = mapped_column(Numeric(18, 4))
    revenue_ttm: Mapped[float | None] = mapped_column(Numeric(18, 4))
    ebitda: Mapped[float | None] = mapped_column(Numeric(18, 4))
    net_profit_q: Mapped[float | None] = mapped_column(Numeric(18, 4))
    net_profit_ttm: Mapped[float | None] = mapped_column(Numeric(18, 4))
    adjusted_profit: Mapped[float | None] = mapped_column(Numeric(18, 4))  # только если компания раскрыла
    net_debt: Mapped[float | None] = mapped_column(Numeric(18, 4))
    nd_ebitda: Mapped[float | None] = mapped_column(Numeric(10, 3))
    dividend_declared: Mapped[float | None] = mapped_column(Numeric(14, 4))
    dividend_yield: Mapped[float | None] = mapped_column(Numeric(8, 3))
    # пересчитанные мультипликаторы (с текущей ценой)
    price: Mapped[float | None] = mapped_column(Numeric(14, 4))
    market_cap: Mapped[float | None] = mapped_column(Numeric(20, 2))
    pe_ttm: Mapped[float | None] = mapped_column(Numeric(10, 3))
    pb: Mapped[float | None] = mapped_column(Numeric(10, 3))
    ev_ebitda: Mapped[float | None] = mapped_column(Numeric(10, 3))
    is_company_adjusted: Mapped[bool] = mapped_column(default=False)
    segments: Mapped[dict | None] = mapped_column(JSONB)
    prev: Mapped[dict | None] = mapped_column(JSONB)  # предыдущий период/год для «что изменилось»
    extracted_fields: Mapped[dict | None] = mapped_column(JSONB)  # сырой снимок из источника

    report: Mapped["EarningsReport"] = relationship(back_populates="figures")


class EarningsDigest(Base):
    __tablename__ = "earnings_digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("earnings_reports.id", ondelete="CASCADE"),
                                           nullable=False, unique=True)
    headline: Mapped[str | None] = mapped_column(String(400))
    one_liner: Mapped[str | None] = mapped_column(String(400))  # одна строка сути для ленты
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    what_report_showed: Mapped[list | None] = mapped_column(JSONB)  # маркеры ✅/❌/❗️
    what_changed: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[str | None] = mapped_column(String(16))  # high|medium|low
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    report: Mapped["EarningsReport"] = relationship(back_populates="digest")
