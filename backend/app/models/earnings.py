"""Модели направления «Анализ отчётностей» (Обозреватель, Направление 3).

EarningsReport — факт выхода отчёта (период/стандарт/источник).
EarningsFigures — извлечённые headline-цифры (строго из источника, без выдумок).
EarningsDigest — ознакомительный «Разбор отчёта» (LLM, по шаблону, без таргетов).
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint,
)
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
    standard: Mapped[str | None] = mapped_column(String(40))          # МСФО | РСБУ | операционные результаты
    report_type: Mapped[str | None] = mapped_column(String(24))       # annual | quarter | operating
    published_at: Mapped[date_type | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(40))            # smartlab | ...
    source_url: Mapped[str | None] = mapped_column(String(1000))
    raw_file_ref: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(24), default="processed")  # processed | extracting | extract_failed | needs_source
    # Дедуп-ключ автопайплайна report_watch.py (детект по calendar_events, не по
    # financials.json) — period парсится эвристикой из заголовка, ненадёжен для
    # дедупа сам по себе. NULL у записей, созданных старым (ручным) путём.
    calendar_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("calendar_events.id", ondelete="SET NULL"), unique=True)
    # Дедуп-якорь для детекта ПРЯМО из Ленты новостей (охват НЕ ограничен ~76 тикерами
    # MOEX ir-calendar, см. _due_news_reports) — событие найдено в самой новости,
    # calendar_event_id в этом случае NULL (нет календарной даты-первоисточника).
    market_update_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_updates.id", ondelete="SET NULL"), unique=True)
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
    what_report_showed: Mapped[list | None] = mapped_column(JSONB)  # маркеры ✅/❌/❗️ (узкий путь, только цифры)
    # Богатый путь (report_watch.py, когда есть реальный текст источника, не только
    # цифры) — highlights/risks_or_caveats заменяют what_report_showed по содержанию
    # (не только динамика 3 метрик — комментарии менеджмента, сегменты, разовые факторы),
    # what_report_showed остаётся NULL в этом случае. API предпочитает highlights, если
    # заполнено, иначе деградирует на _split_markers(what_report_showed) — см. market.py.
    highlights: Mapped[list | None] = mapped_column(JSONB)
    risks_or_caveats: Mapped[list | None] = mapped_column(JSONB)
    data_gaps: Mapped[str | None] = mapped_column(Text)  # чего не хватает в источнике для полной картины
    what_changed: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[str | None] = mapped_column(String(16))  # high|medium|low
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    report: Mapped["EarningsReport"] = relationship(back_populates="digest")


class InterimFinancialsOverlay(Base):
    """Авто-довесок квартальных/полугодовых данных к `financials.json.interim`,
    построенный из `report_watch.py` (см. app/services/interim_overlay.py).

    Не подменяет ручную сверку report-fetcher'а: узкая, дозаполняющая прослойка
    (только НОВЫЕ периоды, которых нет в файле — см. interim_overlay.merge_into).
    Один тикер + один канонический период (year, start_m, end_m) — не тикер+
    период+standard, как в EarningsReport: два ряда одного квартала (МСФО/РСБУ)
    на витрине карточки были бы хуже одного слота, где standard может
    «апгрейднуться» при повторном апсерте более полным источником."""
    __tablename__ = "interim_financials_overlay"
    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "start_m", "end_m",
                          name="uq_interim_overlay_period"),
        Index("ix_interim_financials_overlay_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    start_m: Mapped[int] = mapped_column(Integer, nullable=False)   # окно от начала фингода: 0|3|6
    end_m: Mapped[int] = mapped_column(Integer, nullable=False)     # 3|6|9 — год (12) сюда не пишем
    period_label: Mapped[str] = mapped_column(String(24), nullable=False)   # "1кв2026"/"1П2026"/"9М2026"
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)    # quarter | half | 9m
    cumulative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    standard: Mapped[str | None] = mapped_column(String(40))
    end_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    # ровно 4 headline-поля (млн ₽) — то, что report_watch реально извлекает.
    # {"revenue": float|None, "ebitda": float|None, "net_profit": float|None, "net_debt": float|None}
    figures: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fields_present: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str | None] = mapped_column(String(40))
    source_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("earnings_reports.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc))
