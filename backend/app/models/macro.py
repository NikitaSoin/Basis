"""Модели Макрообзора (Обозреватель, Направление 2).

Четыре таблицы:
- MacroIndicator   — справочник показателей (+ авторский текст «как влияет»);
- MacroDataPoint   — точки числовых рядов (бэкфилл/ЦБ/Минфин/FRED/из Ленты);
- RateMeeting      — заседания ЦБ по ключевой ставке (спец-блок);
- MacroAnalyticsDoc — выжимки аналитики (ЦБ/ЦМАКП), конвейер мониторинга.
"""
import enum
from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


# Страны/регионы показателя
MACRO_COUNTRIES = ("ru", "us", "eu", "cn", "world")
# Частоты
MACRO_FREQ = ("daily", "weekly", "monthly", "quarterly", "yearly")
# Типы метрики точки ряда
MACRO_METRICS = ("level", "mom", "yoy", "wow")
# Каналы поступления точки
MACRO_INGEST = ("file", "cbr", "minfin", "fred", "wb", "eurostat", "news")
# Группы отображения на витрине
MACRO_GROUPS = ("rate", "ru", "world")


class MacroIndicator(Base):
    """Справочник показателей. influence_* — АВТОРСКИЙ контент (не LLM на лету)."""
    __tablename__ = "macro_indicators"

    code: Mapped[str] = mapped_column(String(48), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))  # %|пп|руб|usd|индекс|...
    country: Mapped[str] = mapped_column(String(8), default="ru")  # ru/us/eu/cn/world
    frequency: Mapped[str | None] = mapped_column(String(16))  # daily/weekly/monthly/...
    metric_types: Mapped[list | None] = mapped_column(JSONB)  # ["mom","yoy"] | ["level"]
    influence_short: Mapped[str | None] = mapped_column(Text)  # 1-2 фразы (авторский)
    influence_full: Mapped[str | None] = mapped_column(Text)   # полная механика (авторский)
    source_type: Mapped[str | None] = mapped_column(String(24))  # cbr/minfin/fred/news/...
    display_group: Mapped[str] = mapped_column(String(16), default="ru")  # rate/ru/world
    sort_order: Mapped[int] = mapped_column(default=100)
    sectors: Mapped[list | None] = mapped_column(JSONB)  # секторы, для portfolio_only подсветки


class MacroDataPoint(Base):
    """Точка числового ряда. Уникальность (code, as_of, metric); ревизия обновляет."""
    __tablename__ = "macro_data_points"
    __table_args__ = (
        UniqueConstraint("indicator_code", "as_of", "metric", name="uq_macro_point"),
        Index("ix_macro_point_code_metric_date", "indicator_code", "metric", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    indicator_code: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    as_of: Mapped[date_type] = mapped_column(Date, nullable=False)  # дата периода
    metric: Mapped[str] = mapped_column(String(8), default="level")  # level/mom/yoy/wow
    value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(24))
    is_preliminary: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    ingested_via: Mapped[str | None] = mapped_column(String(16))  # file/cbr/fred/news/...
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # если ревизия
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RateMeeting(Base):
    """Заседание ЦБ по ключевой ставке (спец-блок ставки)."""
    __tablename__ = "rate_meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_date: Mapped[date_type] = mapped_column(Date, unique=True, nullable=False)
    rate_value: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    signal: Mapped[str | None] = mapped_column(Text)  # сигнал с заседания
    next_meeting_date: Mapped[date_type | None] = mapped_column(Date)
    consensus_forecast: Mapped[str | None] = mapped_column(String(200))
    press_summary: Mapped[str | None] = mapped_column(Text)  # выжимка пресс-конф (LLM по тексту)
    forecast_doc_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MacroAnalyticsDoc(Base):
    """Выжимка аналитического документа (ЦБ/ЦМАКП). Конвейер мониторинга."""
    __tablename__ = "macro_analytics_docs"
    __table_args__ = (UniqueConstraint("source_url", name="uq_macro_doc_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False)  # cbr|cmasf
    doc_type: Mapped[str | None] = mapped_column(String(64))  # прогноз/доклад ДКП/резюме ставки/...
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    key_takeaways: Mapped[list | None] = mapped_column(JSONB)  # ["вывод1", ...]
    published_at: Mapped[date_type | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    interpretation: Mapped[str | None] = mapped_column(Text)  # F: на что влияет (Pro reasoning)
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MacroForecast(Base):
    """Среднесрочный прогноз ЦБ (D): ставка/инфляция/ВВП по годам и сценариям."""
    __tablename__ = "macro_forecasts"
    __table_args__ = (UniqueConstraint("as_of", "scenario", "indicator", "year",
                                       name="uq_macro_forecast"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date_type] = mapped_column(Date, nullable=False)  # дата публикации прогноза
    scenario: Mapped[str] = mapped_column(String(48), default="базовый")
    indicator: Mapped[str] = mapped_column(String(80), nullable=False)  # «Инфляция», «ВВП», «Ключевая ставка»
    year: Mapped[int] = mapped_column(nullable=False)
    value: Mapped[str | None] = mapped_column(String(48))  # «7,0–8,0» или «4,0»
    comment: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MacroExpertSurvey(Base):
    """Макроэкономический опрос Банка России — медианные прогнозы профессиональных
    аналитиков (~30 организаций, ежемесячно). Отдельно от MacroForecast: там —
    сценарии САМОГО ЦБ (базовый/альтернативные из ОНДКП), здесь — независимый
    консенсус рынка. Источник: cbr.ru/statistics/ddkp/mo_br/."""
    __tablename__ = "macro_expert_surveys"
    __table_args__ = (UniqueConstraint("as_of", "indicator", "year", name="uq_macro_expert_survey"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date_type] = mapped_column(Date, nullable=False)  # дата проведения опроса
    indicator: Mapped[str] = mapped_column(String(80), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    value: Mapped[str | None] = mapped_column(String(48))
    n_respondents: Mapped[int | None] = mapped_column()
    source_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MacroInterpretation(Base):
    """G: ИИ-интерпретация всей макроситуации (срез на момент, по методичке)."""
    __tablename__ = "macro_interpretations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sections: Mapped[dict | None] = mapped_column(JSONB)  # {current_picture, rate_outlook, ...}
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    model_used: Mapped[str | None] = mapped_column(String(64))
    source_snapshot: Mapped[dict | None] = mapped_column(JSONB)  # срез данных, по которым построено
