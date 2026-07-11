"""geo digest articles (Обозреватель: Рыбарь/re:russia/Carnegie дайджест)

Заодно сливает две независимые головы миграций (a1c5e8b740d3, e7f3b5a92c14).

Revision ID: b7c2e5f91a34
Revises: a1c5e8b740d3, e7f3b5a92c14
Create Date: 2026-07-11

"""
from alembic import op
import sqlalchemy as sa

revision = "b7c2e5f91a34"
down_revision = ("a1c5e8b740d3", "e7f3b5a92c14")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "geo_digest_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("investor_relevance", sa.Text(), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_key", sa.String(length=32), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_geo_digest_source_url", "geo_digest_articles", ["source_url"])
    op.create_index("ix_geo_digest_target", "geo_digest_articles", ["target"])


def downgrade() -> None:
    op.drop_index("ix_geo_digest_target", table_name="geo_digest_articles")
    op.drop_constraint("uq_geo_digest_source_url", "geo_digest_articles", type_="unique")
    op.drop_table("geo_digest_articles")
