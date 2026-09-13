"""Источник координаты заявления о взятии (geo_territorial_claims.geocode_source).

Координаты заявлений теперь идут через справочник населённых пунктов
(config/geo_ua_settlements.json.gz), Википедия — запасной путь. Колонка нужна,
чтобы на бою видеть, какая доля точек привязана справочником.

Revision ID: a7c3e9d1f5b2
Revises: f4b9c27e1a53
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c3e9d1f5b2"
down_revision = "f4b9c27e1a53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("geo_territorial_claims", sa.Column("geocode_source", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("geo_territorial_claims", "geocode_source")
