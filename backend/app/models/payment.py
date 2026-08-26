"""Платежи интернет-эквайринга Т-Бизнеса.

Зачем таблица, если банк и так хранит платежи у себя: нам нужен СВОЙ журнал —
что именно куплено (тариф и срок), кому начислено и было ли уже начислено.
Нотификация о платеже приходит несколько раз (банк повторяет доставку, пока не
получит "OK"), и без записи о начислении подписка продлевалась бы на каждую
повторную доставку.

Жизненный цикл: created → (форма банка) → нотификация/опрос статуса →
CONFIRMED и `granted_at` проставлен. Ничего, кроме `granted_at`, не даёт права
считать оплату применённой.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Наш идентификатор заказа — он же OrderId у банка. Уникален: по нему
    # сходятся возврат пользователя с формы, нотификация и ручной опрос статуса.
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    payment_id: Mapped[str | None] = mapped_column(String(32), index=True)  # PaymentId банка
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"),
                                         nullable=False, index=True)
    # Сумма в КОПЕЙКАХ — как в API банка. Держим целым числом: рубли float'ом
    # рано или поздно дают расхождение на копейку с тем, что списал банк.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="premium")
    months: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW", index=True)
    payment_url: Mapped[str | None] = mapped_column(String(512))
    error_code: Mapped[str | None] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(String(512))
    # Момент, когда подписка РЕАЛЬНО начислена. Пусто = не начисляли, даже если
    # статус уже CONFIRMED (например, нотификация пришла раньше, чем мы успели
    # обработать). Идемпотентность держится на этом поле.
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Последний сырой ответ/нотификация банка — для разбора спорных случаев.
    raw: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False)
