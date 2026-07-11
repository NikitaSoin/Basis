"""screener_saved_filters — пользовательские сохранённые наборы фильтров скринера

Конкурентный разбор ПроФинанс 2026-07-11: «Сохранить»/«Сбросить» свой сет
фильтров — у Basis раньше были только зашитые в код пресеты.

Revision ID: d4a8f13c6e29
Revises: c9e4f2a83b15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d4a8f13c6e29"
down_revision: Union[str, None] = "c9e4f2a83b15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "screener_saved_filters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_class", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screener_saved_filters_user_id", "screener_saved_filters", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_screener_saved_filters_user_id", table_name="screener_saved_filters")
    op.drop_table("screener_saved_filters")
