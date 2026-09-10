"""реестр прогонов качества: quality_runs + quality_findings

Написана вручную, а не autogenerate: автогенерация тянет за собой посторонний
дрейф схемы (чужие индексы и ограничения), который к этой задаче отношения не
имеет и в одной миграции с ней быть не должен.

Revision ID: c1a7e93b5d40
Revises: b9e4f2a71d35
"""
import sqlalchemy as sa
from alembic import op

revision = "c1a7e93b5d40"
down_revision = "b9e4f2a71d35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline", sa.String(length=40), nullable=False),
        sa.Column("checks_version", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subjects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage", sa.Numeric(6, 4), nullable=True),
        sa.Column("score", sa.Numeric(6, 4), nullable=True),
        sa.Column("soft_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("golden_total", sa.Integer(), nullable=True),
        sa.Column("golden_passed", sa.Integer(), nullable=True),
        sa.Column("per_check", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sa.String(length=40), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_quality_runs_pipeline", "quality_runs", ["pipeline"])
    op.create_index("ix_quality_runs_pipeline_started", "quality_runs",
                    ["pipeline", "started_at"])

    op.create_table(
        "quality_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(),
                  sa.ForeignKey("quality_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_id", sa.String(length=60), nullable=False),
        sa.Column("subject", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
    )
    op.create_index("ix_quality_findings_run_id", "quality_findings", ["run_id"])
    op.create_index("ix_quality_findings_check_id", "quality_findings", ["check_id"])
    op.create_index("ix_quality_findings_subject", "quality_findings", ["subject"])
    op.create_index("ix_quality_findings_run_check", "quality_findings",
                    ["run_id", "check_id"])


def downgrade() -> None:
    op.drop_table("quality_findings")
    op.drop_table("quality_runs")
