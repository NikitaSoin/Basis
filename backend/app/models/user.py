import enum
from sqlalchemy import String, Boolean, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base


class SubscriptionType(str, enum.Enum):
    """Тарифы: free («Бесплатный») и premium («Max» в UI).

    "plus" удалён 2026-08-01 (владелец: «клиентов нет, записей никаких нет,
    поэтому удалить можно») — миграция c4e18a7b2d90, она же на всякий случай
    переводит возможные plus-строки в premium перед удалением значения."""

    free = "free"
    premium = "premium"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    subscription_type: Mapped[SubscriptionType] = mapped_column(
        Enum(SubscriptionType), default=SubscriptionType.free, nullable=False
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
