"""create_options — класс активов Опционы (на фьючерсы FORTS)

Самый сложный/рискованный розничный инструмент. Витрина урезана (страйки около
денег). Греки/IV считаем сами (Блэк-76). Данные MOEX ISS (engine=futures/options).

Revision ID: d7f2b9c05e31
Revises: c6e0a8b14d27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd7f2b9c05e31'
down_revision: Union[str, None] = 'c6e0a8b14d27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("short_name", sa.String(length=64), nullable=True),
        sa.Column("option_type", sa.String(length=1), nullable=False),
        sa.Column("strike", sa.Numeric(18, 6), nullable=True),
        sa.Column("central_strike", sa.Numeric(18, 6), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("underlying", sa.String(length=20), nullable=False, index=True),
        sa.Column("underlying_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("asset_code", sa.String(length=20), nullable=True),
        sa.Column("asset_name", sa.String(length=120), nullable=True),
        sa.Column("premium", sa.Numeric(18, 6), nullable=True),
        sa.Column("intrinsic_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("time_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("breakeven", sa.Numeric(18, 6), nullable=True),
        sa.Column("iv", sa.Numeric(8, 4), nullable=True),
        sa.Column("delta", sa.Numeric(8, 4), nullable=True),
        sa.Column("theta_day", sa.Numeric(14, 4), nullable=True),
        sa.Column("vega", sa.Numeric(14, 4), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("options")
