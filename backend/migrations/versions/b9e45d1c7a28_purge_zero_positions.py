"""purge_zero_positions — чистка вырожденных позиций портфелей

Баг «продажа всех акций» оставлял позицию с количеством 0 (число с фронта
сравнивалось со строкой Decimal → ветка полной продажи не срабатывала),
и нулевая строка ломала расчёт метрик и диаграмму. Валидация на входе
теперь запрещает quantity <= 0 (Pydantic gt=0); эта миграция разово
удаляет уже застрявшие нулевые/отрицательные позиции (кейс CHMF 0 шт.).

Revision ID: b9e45d1c7a28
Revises: a7d93f2c8e54
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e45d1c7a28'
down_revision: Union[str, None] = 'a7d93f2c8e54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM portfolio_positions WHERE quantity <= 0 OR avg_buy_price <= 0"
    ))


def downgrade() -> None:
    pass  # удалённые вырожденные строки не восстанавливаются
