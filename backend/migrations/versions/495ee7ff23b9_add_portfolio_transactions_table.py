"""add portfolio transactions table

Revision ID: 495ee7ff23b9
Revises: d2f4a6b8c1e0
Create Date: 2026-07-05 23:27:35.200155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '495ee7ff23b9'
down_revision: Union[str, None] = 'd2f4a6b8c1e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolio_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(length=4), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=16, scale=4), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('fee', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['position_id'], ['portfolio_positions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_portfolio_transactions_position_id'), 'portfolio_transactions', ['position_id'], unique=False
    )

    # Backfill: у существующих позиций нет истории сделок — заводим ОДНУ
    # синтетическую «открывающую» сделку на дату создания позиции с текущими
    # qty/avg_price (согласовано с владельцем: реализовано/дивиденды/комиссии
    # будут честно отсчитываться от этой даты, не от реальной даты покупки,
    # которая не сохранялась).
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO portfolio_transactions (position_id, side, quantity, price, fee, trade_date, created_at)
        SELECT id, 'buy', quantity, avg_buy_price, 0, created_at::date, created_at
        FROM portfolio_positions
    """))


def downgrade() -> None:
    op.drop_index(op.f('ix_portfolio_transactions_position_id'), table_name='portfolio_transactions')
    op.drop_table('portfolio_transactions')
