"""Журнал прогнозов (операционный протокол владельца, части 2.5 и 10.3).

Каждый прогноз записывается В МОМЕНТ ВЫДАЧИ: сценарий/исход, вероятность (число и
слово), горизонт, механизм, пороговые события, дата пересмотра и версия знания. При
наступлении срока запись сверяется с фактом и получает статус: подтвердился /
опровергнут / частично / неясно. Журнал — единственный способ калибровки системы и
защита от переписывания прогнозов задним числом: сводки пересобираются каждый день,
а строка здесь неизменна.
"""
from __future__ import annotations

from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ForecastEntry(Base):
    __tablename__ = "forecast_journal"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, index=True)   # geo|macro|inst_state|council|probe
    version_id: Mapped[int | None] = mapped_column(Integer, index=True)         # barometer_versions.id
    scope: Mapped[str | None] = mapped_column(String(80))                        # очаг / переменная / вопрос
    outcome: Mapped[str] = mapped_column(Text, nullable=False)                   # что предсказано
    p: Mapped[float | None] = mapped_column(Numeric(5, 3))                       # вероятность числом
    p_words: Mapped[str | None] = mapped_column(String(40))                      # словами
    horizon: Mapped[str | None] = mapped_column(String(24))                      # 6m|18m|2y|...
    made_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                              default=lambda: datetime.now(timezone.utc))
    as_of: Mapped[date_type | None] = mapped_column(Date)
    review_at: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    mechanism: Mapped[str | None] = mapped_column(Text)
    triggers: Mapped[list | None] = mapped_column(JSONB)
    methodology_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    realized: Mapped[str | None] = mapped_column(Text)                           # что произошло на самом деле
    resolution_note: Mapped[str | None] = mapped_column(Text)                    # какой механизм сработал / нет
    lesson: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
