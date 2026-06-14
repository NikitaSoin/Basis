"""add content-based category to market_updates (Лента новостей)

Revision ID: e7b3c1d09a52
Revises: d1a9f3c20b47
Create Date: 2026-06-14

Категория новости по СОДЕРЖАНИЮ (определяет LLM): Экономика/Рынки/Бизнес/Политика/
Геополитика — честная статистика баланса ленты вместо рубрики раздела источника.
"""
from alembic import op
import sqlalchemy as sa

revision = "e7b3c1d09a52"
down_revision = "d1a9f3c20b47"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("market_updates", sa.Column("category", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("market_updates", "category")
