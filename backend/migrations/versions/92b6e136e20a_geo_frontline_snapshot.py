"""geo_frontline_snapshot — дневные снапшоты линии фронта (накопление для будущего временного ползунка)

Владелец (2026-07-24) попросил временной ползунок «как менялась линия
фронта за последний год-два». У ISW нет штатного API истории по датам —
единственный практичный путь без большого инженерного спайка (парсинг
архивных Esri PBF-тайлов Wayback Machine, отдельная задача) — копить
собственные снапшоты с этого дня вперёд. Отдельная таблица от
geo_frontline_sync (та — только «последнее успешное» для быстрой отдачи
текущей карты).

Revision ID: 92b6e136e20a
Revises: bdff3fdbac24
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "92b6e136e20a"
down_revision = "bdff3fdbac24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_frontline_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("theater", sa.String(length=16), nullable=False),
        sa.Column("snapshot_date", sa.String(length=10), nullable=False),
        sa.Column("frontline_geojson", postgresql.JSONB(), nullable=True),
        sa.Column("control_fill_geojson", postgresql.JSONB(), nullable=True),
        sa.Column("as_of", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("theater", "snapshot_date", name="uq_geo_frontline_snapshot_theater_date"),
    )
    op.create_index("ix_geo_frontline_snapshot_theater_date", "geo_frontline_snapshot",
                     ["theater", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_geo_frontline_snapshot_theater_date", table_name="geo_frontline_snapshot")
    op.drop_table("geo_frontline_snapshot")
