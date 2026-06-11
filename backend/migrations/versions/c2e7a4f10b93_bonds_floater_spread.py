"""bonds: спред флоатера к ключевой ставке (floater_spread_bp)

У флоатера купон привязан к КС/RUONIA, поэтому G-spread к фиксированной ОФЗ
бессмыслен (spread_bp у таких бумаг должен быть NULL). Реальная плата за риск
флоатера = надбавка купона к ключевой ставке. Храним её отдельно, чтобы
показывать «спред к КС» вместо ложного G-спреда.

Revision ID: c2e7a4f10b93
Revises: d7f2b9c05e31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2e7a4f10b93'
down_revision: Union[str, None] = 'd7f2b9c05e31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("floater_spread_bp", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("bonds", "floater_spread_bp")
