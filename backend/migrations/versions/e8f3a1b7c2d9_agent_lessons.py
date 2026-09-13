"""agent_lessons — уроки из замечаний проверяющего (петля обучения без дообучения)

Revision ID: e8f3a1b7c2d9
Revises: d7e2f91a4c3b
"""
import sqlalchemy as sa
from alembic import op

revision = "e8f3a1b7c2d9"
down_revision = "d7e2f91a4c3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(300), nullable=False),
        sa.Column("contour", sa.String(16), nullable=False),
        sa.Column("rule", sa.String(200), nullable=False),
        sa.Column("where", sa.String(300)),
        sa.Column("example", sa.Text()),
        sa.Column("fix", sa.Text()),
        sa.Column("severity", sa.String(20)),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("clean_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review_id", sa.Integer()),
    )
    op.create_index("ix_agent_lessons_key", "agent_lessons", ["key"], unique=True)
    op.create_index("ix_agent_lessons_contour", "agent_lessons", ["contour"])
    op.create_index("ix_agent_lessons_status", "agent_lessons", ["status"])


def downgrade() -> None:
    op.drop_table("agent_lessons")
