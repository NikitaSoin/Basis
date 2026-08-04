"""Синтез вкладки «Обзор»: свод разборов карточки в один вывод

Revision ID: 0e1a7c4b9f21
Revises: 0df219dbbd46
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0e1a7c4b9f21"
down_revision = "0df219dbbd46"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_overview_synthesis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=True),
        sa.Column("pillars", postgresql.JSONB(), nullable=True),
        sa.Column("fair_value_story", postgresql.JSONB(), nullable=True),
        sa.Column("what_would_change", postgresql.JSONB(), nullable=True),
        sa.Column("inputs_used", postgresql.JSONB(), nullable=True),
        sa.Column("gate_notes", postgresql.JSONB(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_overview_synth_ticker", "card_overview_synthesis", ["ticker"])
    op.create_index("ix_overview_synth_ticker_created", "card_overview_synthesis",
                    ["ticker", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_overview_synth_ticker_created", table_name="card_overview_synthesis")
    op.drop_index("ix_overview_synth_ticker", table_name="card_overview_synthesis")
    op.drop_table("card_overview_synthesis")
