"""Качественный разбор сценария стресс-теста (версионно, в БД)

Revision ID: f3b8c1d75a20
Revises: b7d3e9f2c1a5
Create Date: 2026-08-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f3b8c1d75a20"
down_revision = "b7d3e9f2c1a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stress_interpretations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scenario_key", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("sections", postgresql.JSONB(), nullable=True),
        sa.Column("inputs_used", postgresql.JSONB(), nullable=True),
        sa.Column("gate_notes", postgresql.JSONB(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_stress_interpretations_scenario_key",
                    "stress_interpretations", ["scenario_key"])
    op.create_index("ix_stress_interp_key_created",
                    "stress_interpretations", ["scenario_key", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_stress_interp_key_created", table_name="stress_interpretations")
    op.drop_index("ix_stress_interpretations_scenario_key", table_name="stress_interpretations")
    op.drop_table("stress_interpretations")
