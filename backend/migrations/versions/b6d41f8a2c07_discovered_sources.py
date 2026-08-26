"""discovered_sources — пул источников, найденных активной ревизией

Владелец 2026-08-26: «если нашли какую-то информацию — источник, с которого она
тянулась, должен попасть в пул источников, с которых мы парсим». См.
app/models/source_pool.py и app/services/source_pool.py.

Revision ID: b6d41f8a2c07
Revises: f3b8c1d75a20
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa

revision = "b6d41f8a2c07"
down_revision = "f3b8c1d75a20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovered_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain", sa.String(length=160), nullable=False),
        sa.Column("sample_url", sa.String(length=1000)),
        sa.Column("feed_url", sa.String(length=1000)),
        sa.Column("topics", sa.Text()),
        sa.Column("found_for", sa.Text()),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="candidate"),
        sa.Column("note", sa.Text()),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("domain", name="uq_discovered_source_domain"),
    )
    op.create_index("ix_discovered_sources_domain", "discovered_sources", ["domain"])
    op.create_index("ix_discovered_sources_status", "discovered_sources", ["status"])


def downgrade() -> None:
    op.drop_index("ix_discovered_sources_status", table_name="discovered_sources")
    op.drop_index("ix_discovered_sources_domain", table_name="discovered_sources")
    op.drop_table("discovered_sources")
