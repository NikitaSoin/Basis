"""Модель ИИ-Диагноза портфеля (вкладка «ИИ-Диагноз» в аналитике портфеля).

Синтез-слой по образцу ObserverReport: пересобирает уже посчитанные метрики
портфеля + сигналы держаний (governance/макро карточек компаний) + рыночный
контекст Обозревателя в «щит портфеля / уязвимости / резюме». Один диагноз
на портфель (перегенерируется по кнопке «Обновить диагноз», не на каждый рендер).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class PortfolioDiagnosis(Base):
    __tablename__ = "portfolio_diagnoses"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    # [{text, type}] — type ∈ факт|оценка|модель|суждение (эпистемический тег)
    shield: Mapped[list | None] = mapped_column(JSONB)
    vulnerabilities: Mapped[list | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    summary_type: Mapped[str | None] = mapped_column(String(16))
    portfolio_snapshot: Mapped[list | None] = mapped_column(JSONB)  # тикеры на момент генерации
    model_used: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
