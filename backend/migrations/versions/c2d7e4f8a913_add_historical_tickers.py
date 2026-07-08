"""add companies.historical_tickers (редомициляция/смена тикера)

Revision ID: c2d7e4f8a913
Revises: b1c3a7e5f9d2
Create Date: 2026-07-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2d7e4f8a913'
down_revision: Union[str, None] = 'b1c3a7e5f9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("historical_tickers", sa.JSON(), nullable=True),
    )
    # Яндекс: редомициляция Yandex N.V. (YNDX, торги на MOEX до 2024-06-14,
    # после — заморожен) → МКПАО «Яндекс» (YDEX, торги с 2024-07-24). Метрики
    # доходности/риска считались только по YDEX (~2 года истории вместо 3+) —
    # баг, не намеренное ограничение. Бэкфилл истории YNDX в ту же company_id
    # делает scripts/backfill_historical_tickers.py (использует это поле).
    op.execute(
        "UPDATE companies SET historical_tickers = '[\"YNDX\"]'::json "
        "WHERE ticker = 'YDEX'"
    )


def downgrade() -> None:
    op.drop_column("companies", "historical_tickers")
