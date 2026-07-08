"""add portfolio_diagnoses table (ИИ-Диагноз портфеля)

Revision ID: d3e8f5a2b104
Revises: c2d7e4f8a913
Create Date: 2026-07-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd3e8f5a2b104'
down_revision: Union[str, None] = 'c2d7e4f8a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_diagnoses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("portfolio_id", sa.Integer(),
                  sa.ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shield", postgresql.JSONB(), nullable=True),
        sa.Column("vulnerabilities", postgresql.JSONB(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_type", sa.String(16), nullable=True),
        sa.Column("portfolio_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_portfolio_diagnoses_portfolio_id", "portfolio_diagnoses", ["portfolio_id"])
    op.create_unique_constraint("uq_portfolio_diagnoses_portfolio_id", "portfolio_diagnoses", ["portfolio_id"])


def downgrade() -> None:
    op.drop_table("portfolio_diagnoses")
