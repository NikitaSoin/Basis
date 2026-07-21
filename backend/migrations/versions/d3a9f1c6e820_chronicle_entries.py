"""chronicle_entries — аналитическая летопись (постоянная память для агентов).

Важные новости (из market_updates) и аналитические статьи (из geo_digest_articles)
оседают сюда append-only с готовой интерпретацией. Агенты карточек/стресс-теста
получают «что это значило» по тикеру/сектору/теме через query_chronicle.
GIN-индексы по JSONB-тегам — сразу, ретрив по ним основной. Уникальность по
(source_url, kind): один и тот же URL как news И как article допустим (разные жанры),
дубль внутри жанра — нет.

Revision ID: d3a9f1c6e820
Revises: c8e2f5a3b061
Create Date: 2026-07-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d3a9f1c6e820"
down_revision = "c8e2f5a3b061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chronicle_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("interpretation", sa.Text(), nullable=True),
        sa.Column("key_takeaways", postgresql.JSONB(), nullable=True),
        sa.Column("tickers", postgresql.JSONB(), nullable=True),
        sa.Column("sectors", postgresql.JSONB(), nullable=True),
        sa.Column("themes", postgresql.JSONB(), nullable=True),
        sa.Column("importance", sa.String(length=16), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source_key", sa.String(length=64), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_table", sa.String(length=32), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_url", "kind", name="uq_chronicle_source_url_kind"),
    )
    op.create_index("ix_chronicle_published", "chronicle_entries", ["published_at"])
    op.create_index("ix_chronicle_tickers", "chronicle_entries", ["tickers"], postgresql_using="gin")
    op.create_index("ix_chronicle_sectors", "chronicle_entries", ["sectors"], postgresql_using="gin")
    op.create_index("ix_chronicle_themes", "chronicle_entries", ["themes"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chronicle_themes", table_name="chronicle_entries")
    op.drop_index("ix_chronicle_sectors", table_name="chronicle_entries")
    op.drop_index("ix_chronicle_tickers", table_name="chronicle_entries")
    op.drop_index("ix_chronicle_published", table_name="chronicle_entries")
    op.drop_table("chronicle_entries")
