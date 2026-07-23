"""geo_frontline_sync — автосинк линии фронта СВО из живого фида ISW

Владелец попросил (2026-07-23) автоматизировать линию фронта карты СВО в
Обозревателе: раньше линия реконструировалась вручную из агрегированного
control по ЦЕЛЫМ областям (грубо, не проходит через реальную зону боевых
действий) — теперь периодический крон тянет полигоны ISW (Assessed Control
of Terrain in Ukraine, живой ArcGIS-фид, CC BY) и пересчитывает линию как
границу между зоной российского контроля и остальной Украиной (shapely).

Отдельная таблица, а не правка config/geo_map_svo.json на диске — тот файл
деплоится из git и перезаписывается каждым push, крон в проде писал бы в
файл, который тут же затирается следующим деплоем. Эндпоинт
`/market/geo-map/svo` накладывает живую линию из этой таблицы поверх
статического файла (события/классификация областей остаются ручными).

Revision ID: 7979cef146a1
Revises: e1a4c7f92b35
Create Date: 2026-07-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7979cef146a1"
down_revision = "e1a4c7f92b35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_frontline_sync",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater", sa.String(length=16), nullable=False),
        sa.Column("frontline_geojson", postgresql.JSONB(), nullable=True),
        sa.Column("as_of", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ok"),
        sa.Column("error_note", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("theater", name="uq_geo_frontline_sync_theater"),
    )


def downgrade() -> None:
    op.drop_table("geo_frontline_sync")
