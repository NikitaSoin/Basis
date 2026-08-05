"""users.email_verified_at — отметка подтверждения почты ссылкой из письма.

NULL = адрес не подтверждён; timestamp = когда подтвердили. Ссылка бессрочная
(решение владельца 2026-08-06: «чтобы клиент мог в любое удобное время
подтвердить аккаунт») — поэтому единственный источник истины именно колонка,
а не TTL токена.

Revision ID: b7d3e9f2c1a5
Revises: a1f4c7e93b28
"""
from alembic import op
import sqlalchemy as sa

revision = "b7d3e9f2c1a5"
down_revision = "a1f4c7e93b28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
