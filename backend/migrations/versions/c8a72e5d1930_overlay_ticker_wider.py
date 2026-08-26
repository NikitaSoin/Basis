"""card_prose_overlays.ticker → 80 символов (профили эмитентов облигаций)

Тем же оверлеем теперь обновляются профили эмитентов облигаций, а их слаги длиннее
тикера: «суэк-securities-dac» и подобные, до 52 знаков.

Revision ID: c8a72e5d1930
Revises: b6d41f8a2c07
Create Date: 2026-08-27

"""
from alembic import op
import sqlalchemy as sa

revision = "c8a72e5d1930"
down_revision = "b6d41f8a2c07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("card_prose_overlays", "ticker",
                    existing_type=sa.String(length=20), type_=sa.String(length=80),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column("card_prose_overlays", "ticker",
                    existing_type=sa.String(length=80), type_=sa.String(length=20),
                    existing_nullable=False)
