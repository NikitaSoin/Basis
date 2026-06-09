"""create_spot_assets — класс активов Валюта и металлы (спот MOEX)

Валюта (USD/CNY/EUR за рубль) и драгметаллы (золото/серебро за рубль) — отдельный
класс. Данные с MOEX ISS (engine=currency/selt). Аналитика — в backend/spot/<SECID>/.

Revision ID: c6e0a8b14d27
Revises: b5d9e3a71c46
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6e0a8b14d27'
down_revision: Union[str, None] = 'b5d9e3a71c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spot_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("short_name", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("kind", sa.String(length=12), nullable=False, index=True),
        sa.Column("base_code", sa.String(length=10), nullable=True),
        sa.Column("last_price", sa.Numeric(16, 4), nullable=True),
        sa.Column("prev_close", sa.Numeric(16, 4), nullable=True),
        sa.Column("change_pct", sa.Numeric(8, 3), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("spot_assets")
