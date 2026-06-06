"""implied_eps_dps — якоря для динамических мультипликаторов

P/E в financials.json статичен (записан к цене на дату файла) и устаревает
при движении котировок. Храним подразумеваемые EPS и DPS:
  eps_implied = цена_на_дату_файла / P/E_файла  (та же прибыль, что у аналитика)
  dps_implied = div_yield_файла × цена_на_дату_файла / 100
Текущие P/E, дивдоходность и earnings yield пересчитываются от СВЕЖЕЙ цены:
  P/E = цена / eps_implied;  DY = dps_implied / цена;  EY = 1 / P/E.
EPS/DPS меняются редко (отчёты/решения по дивидендам) — обновляются синком
из файлов; цена — постоянно. P/B и EV/EBITDA в портфеле не показываются,
их пересчёт не требуется (P/E исторический от цены не зависит — медиана лет).

Revision ID: c4f81b3e6d92
Revises: b9e45d1c7a28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f81b3e6d92'
down_revision: Union[str, None] = 'b9e45d1c7a28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("company_metrics", sa.Column("eps_implied", sa.Numeric(14, 4), nullable=True))
    op.add_column("company_metrics", sa.Column("dps_implied", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("company_metrics", "dps_implied")
    op.drop_column("company_metrics", "eps_implied")
