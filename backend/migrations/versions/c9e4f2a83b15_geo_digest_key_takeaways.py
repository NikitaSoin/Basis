"""geo digest articles: key_takeaways column

Revision ID: c9e4f2a83b15
Revises: b7c2e5f91a34
Create Date: 2026-07-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9e4f2a83b15"
down_revision = "b7c2e5f91a34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "geo_digest_articles",
        sa.Column("key_takeaways", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("geo_digest_articles", "key_takeaways")
