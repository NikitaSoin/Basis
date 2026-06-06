"""hybrid_beta_extra_metrics — гибридная бета (MOEX + свой расчёт) и доп. коэффициенты

Этап 2.2. Колонки company_metrics:
  beta_moex      — официальная бета MOEX (fortscoefficients, base=MIX)
  beta_calc      — наш расчёт (Диммсон −1..+1 против IMOEX)
  beta_source    — 'moex' | 'calc' (что показывается в beta)
  beta_moex_date — дата файла коэффициентов
  r_squared      — доля движения, объяснённая рынком (corr²; MOEX kff_korr²
                   где есть, иначе наш расчёт); r_squared_moex — официальная
  downside_vol   — нисходящая волатильность (σ по доходностям <0, ×√252), %
                   (полный Сортино — Этап 3, когда появится ОФЗ-ставка)
  var_95         — исторический VaR 95%, дневной, % (положительное число —
                   величина потери)
  earnings_yield — 1 / P/E текущий, %

Существующая колонка beta становится «итоговой показываемой»
(= beta_moex, если есть, иначе beta_calc).

Revision ID: f8c24a6e1b07
Revises: e5b19c7d4f31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8c24a6e1b07'
down_revision: Union[str, None] = 'e5b19c7d4f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLS = [
    ("beta_moex", sa.Numeric(8, 4)),
    ("beta_calc", sa.Numeric(8, 4)),
    ("beta_source", sa.String(10)),
    ("beta_moex_date", sa.Date()),
    ("r_squared", sa.Numeric(6, 4)),
    ("r_squared_moex", sa.Numeric(6, 4)),
    ("downside_vol", sa.Numeric(8, 4)),
    ("var_95", sa.Numeric(8, 4)),
    ("earnings_yield", sa.Numeric(8, 2)),
]


def upgrade() -> None:
    for name, type_ in COLS:
        op.add_column("company_metrics", sa.Column(name, type_, nullable=True))
    # текущие беты считались старым методом (без Диммсона) — переносим их
    # в beta_calc как стартовое значение до пересчёта
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE company_metrics SET beta_calc = beta, beta_source = 'calc' WHERE beta IS NOT NULL"
    ))


def downgrade() -> None:
    for name, _ in reversed(COLS):
        op.drop_column("company_metrics", name)
