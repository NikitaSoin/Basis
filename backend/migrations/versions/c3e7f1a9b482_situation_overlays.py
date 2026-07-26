"""situation_overlays — оперативный слой «текущая ситуация по ленте»

Владелец (2026-07-27): у макро «Оценка ситуации» авто-обновляется
(macro_interpreter, крон), у геополитики и институтов — нет (барометры-файлы
застыли на 12-13 июля). Слой-оверлей поверх экспертного якоря, дельта по
свежим статьям geo_digest, отдельно по 3 очагам гео + блок институтов.
См. app/services/situation_overlay.py, app/models/geo.py::SituationOverlay.

Revision ID: c3e7f1a9b482
Revises: b2d4f8a1c6e3
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c3e7f1a9b482"
down_revision = "b2d4f8a1c6e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "situation_overlays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blocks", JSONB(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("source_snapshot", JSONB(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_situation_overlays_gen", "situation_overlays",
                    ["published", "generated_at"])


def downgrade() -> None:
    op.drop_index("ix_situation_overlays_gen", table_name="situation_overlays")
    op.drop_table("situation_overlays")
