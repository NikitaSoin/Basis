"""create_funds_table — класс активов Биржевые фонды (БПИФ/ETF)

Фонд — упаковка (корзина активов в одной бумаге). Данные с MOEX ISS (борд TQTF);
TER/состав — не на MOEX, заполняются курируемо. Аналитика-текст — в файлах
backend/funds/<SECID>/.

Revision ID: b5d9e3a71c46
Revises: a4c8e1f2d9b3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b5d9e3a71c46'
down_revision: Union[str, None] = 'a4c8e1f2d9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "funds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("isin", sa.String(length=12), nullable=True),
        sa.Column("short_name", sa.String(length=255), nullable=False),
        sa.Column("sec_name", sa.String(length=255), nullable=True),
        sa.Column("fund_type", sa.String(length=20), nullable=False, index=True),
        sa.Column("benchmark", sa.String(length=120), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("listing_level", sa.Integer(), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("val_today", sa.BigInteger(), nullable=True),
        sa.Column("num_trades", sa.Integer(), nullable=True),
        sa.Column("ter", sa.Numeric(6, 3), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("funds")
