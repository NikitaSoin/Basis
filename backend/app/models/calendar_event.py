"""Унифицированная модель событий календаря (Обозреватель, Направление 4).

Одна таблица под все типы: дивиденды, облигации (оферты/погашения), макрорелизы
(ЦБ/ФРС/инфляция), корпсобытия (отчётности/СД/собрания), IPO/размещения.
Специфика типа — в payload (JSON). Дедуп — по dedup_key.
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Типы событий (валидация на уровне приложения; в БД String — принцип «простые решения»).
EVENT_TYPES = ("dividend", "bond_offer", "bond_maturity", "macro", "corporate", "earnings", "ipo", "expiration")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uq_calendar_events_dedup"),
        Index("ix_calendar_events_type_date", "event_type", "event_date"),
        Index("ix_calendar_events_ticker", "ticker"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    event_date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    event_time: Mapped[str | None] = mapped_column(String(8))  # "13:30" МСК, если известно
    ticker: Mapped[str | None] = mapped_column(String(20))     # тикер/secid, если применимо
    sector: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str | None] = mapped_column(String(40))     # рекомендован/утверждён/ожидается/вышло...
    source: Mapped[str | None] = mapped_column(String(40))     # moex_iss | cbr | fred | e-disclosure | news
    source_url: Mapped[str | None] = mapped_column(String(1000))
    payload: Mapped[dict | None] = mapped_column(JSONB)        # поля под тип
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
