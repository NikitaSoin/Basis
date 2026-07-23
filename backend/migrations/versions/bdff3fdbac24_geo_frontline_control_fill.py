"""geo_frontline_sync.control_fill_geojson — точная закраска РФ-контроля

Владелец (2026-07-24): область-уровневая choropleth не показывает, что
конкретные населённые пункты (Часов Яр, Константиновка, Гуляйполе, Волчанск,
Мирноград, Покровск, Родинское, Лиман) внутри «спорных» областей фактически
уже под контролем России — карта «ощущается устаревшей». Решение — отдельный
полигон-слой (сам ISW control-полигон, не только его граница-линия из
frontline_geojson), закрашенный тем же цветом, что коренные регионы РФ,
поверх областной choropleth.

Revision ID: bdff3fdbac24
Revises: 7979cef146a1
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "bdff3fdbac24"
down_revision = "7979cef146a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_frontline_sync", sa.Column("control_fill_geojson", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_frontline_sync", "control_fill_geojson")
