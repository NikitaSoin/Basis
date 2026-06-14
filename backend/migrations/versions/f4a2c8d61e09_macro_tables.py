"""macro tables (Обозреватель: Макрообзор)

Revision ID: f4a2c8d61e09
Revises: e7b3c1d09a52
Create Date: 2026-06-14

Четыре таблицы Макрообзора: справочник показателей, точки числовых рядов,
заседания ЦБ по ставке, выжимки аналитики (ЦБ/ЦМАКП).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f4a2c8d61e09"
down_revision = "e7b3c1d09a52"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "macro_indicators",
        sa.Column("code", sa.String(length=48), primary_key=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("unit", sa.String(length=24)),
        sa.Column("country", sa.String(length=8), server_default="ru"),
        sa.Column("frequency", sa.String(length=16)),
        sa.Column("metric_types", postgresql.JSONB()),
        sa.Column("influence_short", sa.Text()),
        sa.Column("influence_full", sa.Text()),
        sa.Column("source_type", sa.String(length=24)),
        sa.Column("display_group", sa.String(length=16), server_default="ru"),
        sa.Column("sort_order", sa.Integer(), server_default="100"),
        sa.Column("sectors", postgresql.JSONB()),
    )
    op.create_table(
        "macro_data_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("indicator_code", sa.String(length=48), nullable=False, index=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=8), server_default="level"),
        sa.Column("value", sa.Numeric(20, 6), nullable=False),
        sa.Column("unit", sa.String(length=24)),
        sa.Column("is_preliminary", sa.Boolean(), server_default=sa.false()),
        sa.Column("source", sa.String(length=200)),
        sa.Column("source_url", sa.String(length=1000)),
        sa.Column("ingested_via", sa.String(length=16)),
        sa.Column("revised_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("indicator_code", "as_of", "metric", name="uq_macro_point"),
    )
    op.create_index("ix_macro_point_code_metric_date", "macro_data_points",
                    ["indicator_code", "metric", "as_of"])
    op.create_table(
        "rate_meetings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_date", sa.Date(), nullable=False, unique=True),
        sa.Column("rate_value", sa.Numeric(6, 2)),
        sa.Column("signal", sa.Text()),
        sa.Column("next_meeting_date", sa.Date()),
        sa.Column("consensus_forecast", sa.String(length=200)),
        sa.Column("press_summary", sa.Text()),
        sa.Column("forecast_doc_url", sa.String(length=1000)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "macro_analytics_docs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("doc_type", sa.String(length=64)),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("key_takeaways", postgresql.JSONB()),
        sa.Column("published_at", sa.Date()),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("model_used", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("source_url", name="uq_macro_doc_url"),
    )


def downgrade():
    op.drop_table("macro_analytics_docs")
    op.drop_table("rate_meetings")
    op.drop_index("ix_macro_point_code_metric_date", table_name="macro_data_points")
    op.drop_table("macro_data_points")
    op.drop_table("macro_indicators")
