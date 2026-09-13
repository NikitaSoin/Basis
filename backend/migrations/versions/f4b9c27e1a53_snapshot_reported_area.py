"""Площадь заливки по данным МО РФ/Рыбаря в дневном снапшоте линии фронта.

Ряд «км²/мес» считался только по ISW, а карта закрашена по МО РФ/Рыбарю —
число и картинка жили по разным источникам (владелец, 2026-09-12: основной
ряд — наша заливка, ISW — внешняя сверка). Копим площадь заливки той же
методикой, что isw_area_km2 (клип по Украине, заделка дыр, сферическая
площадь), — закрытый месяц, до которого архив ISW ещё не дошёл, получает
основной ряд из своего снапшота, а не ждёт архива.

Revision ID: f4b9c27e1a53
Revises: e8f3a1b7c2d9
"""
from alembic import op
import sqlalchemy as sa

revision = "f4b9c27e1a53"
down_revision = "e8f3a1b7c2d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_frontline_snapshot", sa.Column("reported_area_km2", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_frontline_snapshot", "reported_area_km2")
