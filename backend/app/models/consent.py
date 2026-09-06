"""Записи о принятых условиях и данных согласиях.

Смысл таблицы — доказательство: кто, ЧТО именно и КАКОЙ РЕДАКЦИИ подтвердил и когда.
Галочка на форме без такой записи не доказывает ничего.

🔴 Согласия на обработку персональных данных здесь нет намеренно: почта, портфель и
платежи обрабатываются на основании ДОГОВОРА (п. 5 ч. 1 ст. 6 152-ФЗ). Согласие
собирается только там, где договор не годится: аналитика посещений, передача данных
в языковую модель за границу, рекламные рассылки.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

# Виды записей. Держим списком, чтобы опечатка в строке не создавала тихо новый вид.
OFFER_ACCEPT = "offer_accept"     # акцепт публичной оферты
ANALYTICS = "analytics"           # аналитика посещений (Метрика + собственная статистика)
AI_TRANSFER = "ai_transfer"       # передача данных в языковую модель за пределы РФ
MARKETING = "marketing"           # рекламные рассылки
KINDS = (OFFER_ACCEPT, ANALYTICS, AI_TRANSFER, MARKETING)


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    # Гость подтверждает выбор по аналитике до регистрации — его тоже надо помнить.
    guest_token: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    # Редакция документа. Через год «принял оферту» без редакции не значит ничего.
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    # Отзыв не удаляет запись: «когда согласился и когда передумал» — часть доказательства.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
