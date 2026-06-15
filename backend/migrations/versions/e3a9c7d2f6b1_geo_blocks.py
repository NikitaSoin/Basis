"""geo blocks (Обозреватель, Направление 7)

Revision ID: e3a9c7d2f6b1
Revises: d2f8b1a6c3e4
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3a9c7d2f6b1"
down_revision = "d2f8b1a6c3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("region", sa.String(length=16), nullable=False),
        sa.Column("tab", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("status_text", sa.Text(), nullable=True),
        sa.Column("channels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scenarios", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("market_impact", sa.Text(), nullable=True),
        sa.Column("affected_sectors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("affected_tickers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_geo_block_region_tab", "geo_blocks", ["region", "tab"])


def downgrade() -> None:
    op.drop_constraint("uq_geo_block_region_tab", "geo_blocks", type_="unique")
    op.drop_table("geo_blocks")
