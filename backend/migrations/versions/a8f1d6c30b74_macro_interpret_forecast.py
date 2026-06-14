"""macro interpretation + forecast + review interpretation

Revision ID: a8f1d6c30b74
Revises: f4a2c8d61e09
Create Date: 2026-06-14

G: MacroInterpretation (ИИ-анализ макроситуации). D: MacroForecast (прогноз ЦБ).
F: колонка interpretation в macro_analytics_docs (на что влияет, Pro reasoning).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a8f1d6c30b74"
down_revision = "f4a2c8d61e09"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("macro_analytics_docs", sa.Column("interpretation", sa.Text(), nullable=True))
    op.create_table(
        "macro_forecasts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("scenario", sa.String(length=48), server_default="базовый"),
        sa.Column("indicator", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=48)),
        sa.Column("comment", sa.Text()),
        sa.Column("source_url", sa.String(length=1000)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("as_of", "scenario", "indicator", "year", name="uq_macro_forecast"),
    )
    op.create_table(
        "macro_interpretations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sections", postgresql.JSONB()),
        sa.Column("generated_at", sa.DateTime(timezone=True)),
        sa.Column("model_used", sa.String(length=64)),
        sa.Column("source_snapshot", postgresql.JSONB()),
    )


def downgrade():
    op.drop_table("macro_interpretations")
    op.drop_table("macro_forecasts")
    op.drop_column("macro_analytics_docs", "interpretation")
