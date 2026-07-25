"""macro_verifications — таблица результатов «ОТК данных» Макрообзора

Владелец (2026-07-25), после серии багов данных (ставка не обновилась после
заседания, дата «31 декабря» из прогноза-как-факта, недельная инфляция 2,6% из
цены сахара, инфл.ожидания 13,0 вместо 14,7 из перепутанных рядов графика):
«надо чтобы не я вручную замечал баги — автоматическая подгрузка из правильных
мест и отдельная проверка, правильно ли данные загрузились». См.
app/services/macro_verification.py.

Revision ID: b2d4f8a1c6e3
Revises: 9e5c10b0c99c
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2d4f8a1c6e3"
down_revision = "9e5c10b0c99c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "macro_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_key", sa.String(length=64), nullable=False),
        sa.Column("check_type", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_macro_verifications_run_at", "macro_verifications", ["run_at"])


def downgrade() -> None:
    op.drop_index("ix_macro_verifications_run_at", table_name="macro_verifications")
    op.drop_table("macro_verifications")
