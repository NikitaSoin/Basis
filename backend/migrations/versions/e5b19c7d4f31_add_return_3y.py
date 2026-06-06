"""add_return_3y — историческая доходность в company_metrics (Этап 2)

CAGR за 3 года по истории котировок. Это ФАКТ прошлого, не прогноз —
в UI подписывается «Доходность (3г)». Колонки beta/volatility заведены
ещё миграцией d3a47b8e9c12, наполняются скриптом recalc_risk_metrics.

Revision ID: e5b19c7d4f31
Revises: d3a47b8e9c12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b19c7d4f31'
down_revision: Union[str, None] = 'd3a47b8e9c12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company_metrics", sa.Column("return_3y", sa.Numeric(10, 2), nullable=True))
    # Глубина истории (в годах) на момент пересчёта — для пометки «*» у бумаг
    # с историей короче года (значение метрик неустойчиво).
    op.add_column("company_metrics", sa.Column("history_years", sa.Numeric(6, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("company_metrics", "history_years")
    op.drop_column("company_metrics", "return_3y")
