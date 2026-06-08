"""bonds: тип купона, метка YTM, дефолт, агентский рейтинг (двойной рейтинг)

Полный охват облигаций + двойной рейтинг (рынок по спреду vs агентство) +
типы купонов (фикс / флоатер / линкер) + муниципальные/субфедеральные.

- coupon_type: fixed | floater | linker | other (из MOEX BOND_TYPE) —
  у флоатера процентного риска почти нет, блок чувствительности меняет смысл.
- ytm_kind: «к погашению» | «к оферте» (из MOEX BOND_SUBTYPE) — оферта
  маскирует реальный срок, помечаем явно.
- is_defaulted: бумага в режиме Д (борд TQRD) или с отметкой дефолта.
- agency_rating / agency_rating_source: агентский кредитный рейтинг (вторая,
  независимая от спреда оценка надёжности) — агрегат АКРА/Эксперт РА/НКР/НРА.

Revision ID: e2a7c1f44b80
Revises: d8f1a4c93b27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2a7c1f44b80'
down_revision: Union[str, None] = 'd8f1a4c93b27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("coupon_type", sa.String(length=12), nullable=True))
    op.add_column("bonds", sa.Column("ytm_kind", sa.String(length=16), nullable=True))
    op.add_column("bonds", sa.Column("is_defaulted", sa.Boolean(), nullable=True))
    op.add_column("bonds", sa.Column("agency_rating", sa.String(length=16), nullable=True))
    op.add_column("bonds", sa.Column("agency_rating_source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("bonds", "agency_rating_source")
    op.drop_column("bonds", "agency_rating")
    op.drop_column("bonds", "is_defaulted")
    op.drop_column("bonds", "ytm_kind")
    op.drop_column("bonds", "coupon_type")
