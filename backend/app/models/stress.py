"""Модели широкого «Стресс-тестирования» (не портфельного бета×шок)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class StressInterpretation(Base):
    """Качественный разбор ГОТОВОГО сценария стресс-теста.

    🔴 ЗАЧЕМ (владелец, 2026-08-08): «когда выбираешь конкретный сценарий — там нет
    никакого ответа от ЛЛМ… качественная интерпретация могла бы идти от агентов по
    политике/экономике/институтам, на основе карточек и данных прикинуть кому хреново,
    а кому нет». Числовой компас («кто вверх, кто вниз») отвечает на «что», но не на
    «почему» — а без «почему» список тикеров нечитаем.

    Хранится ВЕРСИОННО в БД, а не считается на запрос: сценарии меняются редко (набор
    пресетов фиксирован, экспозиции компаний — тоже), а прогон LLM платный и небыстрый.
    Файл не годится по той же причине, что у оверлеев прозы: на Timeweb файлы эфемерны,
    а пересборка идёт кроном на бою.

    status: published — прошло гейт, показывается; rejected — не прошло, лежит для
    отладки и НА ВИТРИНУ НЕ ИДЁТ (лучше без разбора, чем с выдуманным).
    """
    __tablename__ = "stress_interpretations"
    __table_args__ = (
        Index("ix_stress_interp_key_created", "scenario_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_key: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16))          # published | rejected
    headline: Mapped[str | None] = mapped_column(Text)       # одна фраза — суть сценария
    sections: Mapped[dict | None] = mapped_column(JSONB)     # economy/channels/hit_hard/...
    inputs_used: Mapped[dict | None] = mapped_column(JSONB)  # из чего собрано (аудит)
    gate_notes: Mapped[list | None] = mapped_column(JSONB)   # почему rejected
    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
