"""company_scores — LLM-скоры BM/MP/CA (индекс качества портфеля v2.1, Фаза 2)

Revision ID: d5a9e1c8b346
Revises: c4d8f2a731eb
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d5a9e1c8b346"
down_revision = "c4d8f2a731eb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("dimension", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.String(length=2000)),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("model", sa.String(length=64)),
        sa.Column("prompt_version", sa.String(length=16)),
        sa.Column("card_version", sa.String(length=32)),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("ticker", "dimension", "as_of", name="uq_company_score"),
    )
    op.create_index("ix_company_scores_ticker", "company_scores", ["ticker"])
    op.create_index("ix_company_scores_dimension", "company_scores", ["dimension"])


def downgrade():
    op.drop_index("ix_company_scores_dimension", table_name="company_scores")
    op.drop_index("ix_company_scores_ticker", table_name="company_scores")
    op.drop_table("company_scores")
