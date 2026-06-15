"""earnings reports/figures/digests (Обозреватель, Направление 3)

Revision ID: d2f8b1a6c3e4
Revises: c1e7a9d4f2b0
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d2f8b1a6c3e4"
down_revision = "c1e7a9d4f2b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "earnings_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("period", sa.String(length=24), nullable=False),
        sa.Column("standard", sa.String(length=16), nullable=True),
        sa.Column("report_type", sa.String(length=24), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("raw_file_ref", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_earnings_reports_ticker", "earnings_reports", ["ticker"])
    op.create_index("ix_earnings_reports_published", "earnings_reports", ["published_at"])
    op.create_unique_constraint("uq_earnings_report", "earnings_reports", ["ticker", "period", "standard"])

    op.create_table(
        "earnings_figures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("earnings_reports.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("revenue_q", sa.Numeric(18, 4), nullable=True),
        sa.Column("revenue_ttm", sa.Numeric(18, 4), nullable=True),
        sa.Column("ebitda", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_profit_q", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_profit_ttm", sa.Numeric(18, 4), nullable=True),
        sa.Column("adjusted_profit", sa.Numeric(18, 4), nullable=True),
        sa.Column("net_debt", sa.Numeric(18, 4), nullable=True),
        sa.Column("nd_ebitda", sa.Numeric(10, 3), nullable=True),
        sa.Column("dividend_declared", sa.Numeric(14, 4), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(8, 3), nullable=True),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("market_cap", sa.Numeric(20, 2), nullable=True),
        sa.Column("pe_ttm", sa.Numeric(10, 3), nullable=True),
        sa.Column("pb", sa.Numeric(10, 3), nullable=True),
        sa.Column("ev_ebitda", sa.Numeric(10, 3), nullable=True),
        sa.Column("is_company_adjusted", sa.Boolean(), nullable=True),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extracted_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "earnings_digests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("earnings_reports.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("headline", sa.String(length=400), nullable=True),
        sa.Column("one_liner", sa.String(length=400), nullable=True),
        sa.Column("metrics_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("what_report_showed", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("what_changed", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("importance", sa.String(length=16), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("earnings_digests")
    op.drop_table("earnings_figures")
    op.drop_index("ix_earnings_reports_published", table_name="earnings_reports")
    op.drop_index("ix_earnings_reports_ticker", table_name="earnings_reports")
    op.drop_constraint("uq_earnings_report", "earnings_reports", type_="unique")
    op.drop_table("earnings_reports")
