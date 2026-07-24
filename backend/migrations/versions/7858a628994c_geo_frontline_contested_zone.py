"""geo_frontline_sync.contested_zone_geojson — «оспаривается» (Рыбарь-штриховка), ручные оверрайды

Владелец (2026-07-25): «Рыбарь достаточно точно надёжный» — политика
источника расширена с «только ISW» на «ISW + ручные/Рыбарь-подтверждённые
оверрайды». Спорные территории (Константиновка, Купянск — Рыбарь держит их
штриховкой «территория боевых действий», не сплошной заливкой) получают
ОТДЕЛЬНЫЙ третий эпистемический ярус — не «подтверждённый контроль»
(control_fill), не «заявлено, не подтверждено ISW» (claimed_captures), а
именно «оспаривается прямо сейчас». См. config/geo_svo_manual_overrides.json.

Revision ID: 7858a628994c
Revises: 960156c2f8ad
Create Date: 2026-07-25

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7858a628994c"
down_revision = "960156c2f8ad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_frontline_sync", sa.Column("contested_zone_geojson", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_frontline_sync", "contested_zone_geojson")
