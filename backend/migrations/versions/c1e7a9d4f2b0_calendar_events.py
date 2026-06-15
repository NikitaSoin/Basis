"""calendar events table (Обозреватель, Направление 4)

Revision ID: c1e7a9d4f2b0
Revises: a8f1d6c30b74
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1e7a9d4f2b0"
down_revision = "a8f1d6c30b74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.String(length=8), nullable=True),
        sa.Column("ticker", sa.String(length=20), nullable=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint("uq_calendar_events_dedup", "calendar_events", ["dedup_key"])
    op.create_index("ix_calendar_events_event_date", "calendar_events", ["event_date"])
    op.create_index("ix_calendar_events_type_date", "calendar_events", ["event_type", "event_date"])
    op.create_index("ix_calendar_events_ticker", "calendar_events", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_ticker", table_name="calendar_events")
    op.drop_index("ix_calendar_events_type_date", table_name="calendar_events")
    op.drop_index("ix_calendar_events_event_date", table_name="calendar_events")
    op.drop_constraint("uq_calendar_events_dedup", "calendar_events", type_="unique")
    op.drop_table("calendar_events")
