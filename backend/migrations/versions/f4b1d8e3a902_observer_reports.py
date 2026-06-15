"""observer reports (Обозреватель, Направление 5)

Revision ID: f4b1d8e3a902
Revises: e3a9c7d2f6b1
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f4b1d8e3a902"
down_revision = "e3a9c7d2f6b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observer_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("portfolio_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_observer_reports_user_id", "observer_reports", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_observer_reports_user_id", table_name="observer_reports")
    op.drop_table("observer_reports")
