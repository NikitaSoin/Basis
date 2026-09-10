"""Чистая ISW-площадь в дневном снапшоте линии фронта.

Без неё помесячный ряд «км²/мес» рвётся, как только архивные таймлапсы ISW
отстают от календаря: архив кончался июлем 2026, а движение августа молча
приписывалось сентябрю (дельта за два месяца под подписью одного). Свой
control_fill для этого не годится — он растёт ещё и от вливания заявленных
взятий МО РФ/Рыбаря, то есть НЕ однородный ряд. Копим площадь ровно той же
методики, что у архивных месяцев (чистая ISW-масса, клип по Украине,
заделка дыр), — с этого дня каждый закрытый месяц строится из своего
снапшота, без ожидания архива ISW.

Revision ID: d2f4a81c6e37
Revises: c1a7e93b5d40
"""
from alembic import op
import sqlalchemy as sa

revision = "d2f4a81c6e37"
down_revision = "c1a7e93b5d40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_frontline_snapshot", sa.Column("isw_area_km2", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_frontline_snapshot", "isw_area_km2")
