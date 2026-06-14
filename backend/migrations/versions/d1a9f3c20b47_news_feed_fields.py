"""extend market_updates with news-feed fields (Обозреватель: Лента новостей)

Revision ID: d1a9f3c20b47
Revises: c2e7a4f10b93
Create Date: 2026-06-14

Расширяет market_updates под Направление 1 Обозревателя: выжимка + ИИ-коммент
«на что влияет» + теги бумаг/секторов + дедуп-кластеры. content/source делаются
гибкими (полные тексты не храним). Поля переиспользуют направления 2/3/7.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d1a9f3c20b47"
down_revision = "c2e7a4f10b93"
branch_labels = None
depends_on = None


def upgrade():
    # content больше не обязателен (храним summary, а не полный текст)
    op.alter_column("market_updates", "content", existing_type=sa.Text(), nullable=True)
    # source суживаем до короткого кода источника
    op.alter_column("market_updates", "source", existing_type=sa.String(length=255),
                    type_=sa.String(length=64), existing_nullable=True)

    op.add_column("market_updates", sa.Column("source_url", sa.String(length=1000), nullable=True))
    op.add_column("market_updates", sa.Column("original_title", sa.String(length=500), nullable=True))
    op.add_column("market_updates", sa.Column("rubric", sa.String(length=32), nullable=True))
    op.add_column("market_updates", sa.Column("importance", sa.String(length=16), nullable=True))
    op.add_column("market_updates", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("market_updates", sa.Column("impact_comment", sa.Text(), nullable=True))
    op.add_column("market_updates", sa.Column("affected_tickers", postgresql.JSONB(), nullable=True))
    op.add_column("market_updates", sa.Column("affected_sectors", postgresql.JSONB(), nullable=True))
    op.add_column("market_updates", sa.Column("cluster_id", sa.String(length=64), nullable=True))
    op.add_column("market_updates", sa.Column("sources_json", postgresql.JSONB(), nullable=True))
    op.add_column("market_updates", sa.Column("model_used", sa.String(length=64), nullable=True))
    op.add_column("market_updates", sa.Column("status", sa.String(length=16),
                                             server_default="published", nullable=False))
    op.add_column("market_updates", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_updates", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_market_updates_source_url", "market_updates", ["source_url"])
    op.create_index("ix_market_updates_cluster_id", "market_updates", ["cluster_id"])
    op.create_index("ix_market_updates_status_published", "market_updates", ["status", "published_at"])


def downgrade():
    op.drop_index("ix_market_updates_status_published", table_name="market_updates")
    op.drop_index("ix_market_updates_cluster_id", table_name="market_updates")
    op.drop_index("ix_market_updates_source_url", table_name="market_updates")
    for col in ("updated_at", "fetched_at", "status", "model_used", "sources_json",
                "cluster_id", "affected_sectors", "affected_tickers", "impact_comment",
                "summary", "importance", "rubric", "original_title", "source_url"):
        op.drop_column("market_updates", col)
    op.alter_column("market_updates", "source", existing_type=sa.String(length=64),
                    type_=sa.String(length=255), existing_nullable=True)
    op.alter_column("market_updates", "content", existing_type=sa.Text(), nullable=False)
