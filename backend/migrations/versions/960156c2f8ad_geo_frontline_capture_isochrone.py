"""geo_frontline_sync.capture_isochrone_geojson — изохрона «когда взято» для временного ползунка

Владелец (2026-07-24): «идёшь по сообщениям МО РФ/Рыбарь/ISW — знаешь,
какие города когда взяты — отматываешь линию фронта за эти города». Вместо
восстановления точной исторической геометрии (тупиковый путь через архив
Wayback — см. work-journal) строим диаграмму Вороного вокруг датированных
населённых пунктов (источник дат — история правок статьи Wikipedia
"Territorial control during the Russo-Ukrainian war", агрегирующей ISW/
DeepState/новости с цитатами; см. config/geo_svo_dated_settlements.json,
scripts/geo_svo_wikipedia_dates.py), обрезанную по текущему
control_fill_geojson. Фронтенд фильтрует по дате слайдером без похода на
сервер.

Revision ID: 960156c2f8ad
Revises: 92b6e136e20a
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "960156c2f8ad"
down_revision = "92b6e136e20a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_frontline_sync", sa.Column("capture_isochrone_geojson", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_frontline_sync", "capture_isochrone_geojson")
