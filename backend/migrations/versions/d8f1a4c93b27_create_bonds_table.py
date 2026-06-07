"""create_bonds_table — класс активов Облигации (пункт 3 роадмапа)

Облигации — отдельная сущность (НЕ компания): свои параметры долга (купон,
погашение, доходность, дюрация, оферта, амортизация). Данные с MOEX ISS,
аналитика-текст — в файлах backend/bonds/<SECID>/.

Revision ID: d8f1a4c93b27
Revises: c4f81b3e6d92
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8f1a4c93b27'
down_revision: Union[str, None] = 'c4f81b3e6d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bonds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("short_name", sa.String(length=255), nullable=False),
        sa.Column("issuer_name", sa.String(length=255), nullable=True),
        sa.Column("bond_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("board", sa.String(length=12), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("face_value", sa.Numeric(16, 4), nullable=True),
        sa.Column("coupon_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("coupon_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("coupon_period", sa.Integer(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("offer_date", sa.Date(), nullable=True),
        sa.Column("has_amortization", sa.Boolean(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("listing_level", sa.Integer(), nullable=True),
        sa.Column("last_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("ytm", sa.Numeric(8, 4), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("accrued_int", sa.Numeric(14, 4), nullable=True),
        sa.Column("risk_tier", sa.String(length=20), nullable=True),
        sa.Column("spread_bp", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("bonds")
