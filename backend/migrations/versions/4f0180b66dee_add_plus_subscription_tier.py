"""add_plus_subscription_tier

Revision ID: 4f0180b66dee
Revises: 495ee7ff23b9
Create Date: 2026-07-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '4f0180b66dee'
down_revision: Union[str, None] = '495ee7ff23b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Третий тариф между free и premium (390 ₽/мес) — «Плюс». Postgres не даёт
    # удалить значение enum (downgrade — best-effort: сначала перевести пользователей
    # с plus обратно на free, потом попытаться DROP VALUE — недоступно до PG 15+
    # без пересоздания типа, поэтому downgrade НЕ пытается физически убрать 'plus'
    # из типа, только мигрирует данные).
    op.execute("ALTER TYPE subscriptiontype ADD VALUE IF NOT EXISTS 'plus'")


def downgrade() -> None:
    op.execute("UPDATE users SET subscription_type = 'free' WHERE subscription_type = 'plus'")
