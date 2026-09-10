"""bonds: число сделок и оборот за день (ликвидность выпуска)

🔴 ЗАЧЕМ (владелец, 11.09.2026: «цена облигации 0,2 процента — что за бред»).
Проверка показала, что цена настоящая: MOEX отдаёт по структурной ноте СбКИБ1P286
LCURRENTPRICE = 0,2% номинала. Но бумага НЕ ТОРГУЕТСЯ — ноль сделок неделями, одна
сделка за месяц. Мы показывали эту котировку как рыночную цену и считали от неё «цену
входа 2,00 ₽»: число, честное по источнику и бессмысленное по существу.

Отличить «цена такая» от «цены фактически нет» можно только по числу сделок и обороту.
В таблице их не было вообще, поэтому ни карточка, ни SEO-страница, ни скринер не могли
об этом предупредить, даже если бы захотели.

Revision ID: e5c17a934b82
Revises: d2f4a81c6e37
"""
from alembic import op
import sqlalchemy as sa

revision = "e5c17a934b82"
down_revision = "d2f4a81c6e37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("num_trades", sa.Integer(), nullable=True))
    op.add_column("bonds", sa.Column("val_today", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("bonds", "val_today")
    op.drop_column("bonds", "num_trades")
