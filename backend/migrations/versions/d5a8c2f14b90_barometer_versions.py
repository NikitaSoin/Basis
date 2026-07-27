"""barometer_versions — версии барометров для автономного обслуживания калибровки

Владелец (2026-07-27): автономные агенты сами обновляют барометры по новостям.
План docs/autonomous-barometer-plan.md (ревью advisor). Барометр переезжает из
config/*.json в БД (сервер Timeweb не пишет в git). См.
app/models/geo.py::BarometerVersion, app/services/barometer_reviser.py.

Revision ID: d5a8c2f14b90
Revises: c3e7f1a9b482
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d5a8c2f14b90"
down_revision = "c3e7f1a9b482"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "barometer_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("payload", JSONB(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("trigger_reason", sa.String(length=120), nullable=True),
        sa.Column("gate_notes", JSONB(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_barometer_versions_lookup", "barometer_versions",
                    ["kind", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_barometer_versions_lookup", table_name="barometer_versions")
    op.drop_table("barometer_versions")
