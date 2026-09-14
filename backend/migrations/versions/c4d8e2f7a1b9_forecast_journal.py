"""Журнал прогнозов (forecast_journal) — протокол владельца, части 2.5 и 10.3.

Зачем: прогнозы жили внутри сводок и переписывались каждым выпуском; сверки с фактом по
наступлении срока не было, поэтому «обучение на ошибках» шло только по замечаниям
проверяющего, а не по реальности. Здесь каждый прогноз фиксируется в момент выдачи и
получает статус при пересмотре.

Revision ID: c4d8e2f7a1b9
Revises: b8d4f2a6c1e7
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c4d8e2f7a1b9"
down_revision = "b8d4f2a6c1e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_journal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=80), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("p", sa.Numeric(5, 3), nullable=True),
        sa.Column("p_words", sa.String(length=40), nullable=True),
        sa.Column("horizon", sa.String(length=24), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("review_at", sa.Date(), nullable=False),
        sa.Column("mechanism", sa.Text(), nullable=True),
        sa.Column("triggers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("methodology_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("realized", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("lesson", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_forecast_journal_source", "forecast_journal", ["source"])
    op.create_index("ix_forecast_journal_version_id", "forecast_journal", ["version_id"])
    op.create_index("ix_forecast_journal_review_at", "forecast_journal", ["review_at"])
    op.create_index("ix_forecast_journal_status", "forecast_journal", ["status"])


def downgrade() -> None:
    op.drop_index("ix_forecast_journal_status", table_name="forecast_journal")
    op.drop_index("ix_forecast_journal_review_at", table_name="forecast_journal")
    op.drop_index("ix_forecast_journal_version_id", table_name="forecast_journal")
    op.drop_index("ix_forecast_journal_source", table_name="forecast_journal")
    op.drop_table("forecast_journal")
