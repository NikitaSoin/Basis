"""interim_financials_overlay — авто-довесок квартальных/полугодовых данных

Замыкает цепочку «отчёт вышел → карточка обновилась» (владелец 2026-07-31):
report_watch.py пишет структурированные headline-цифры сюда при детекте
квартального/полугодового отчёта, companies.py::get_financials_json домешивает
их в fin["interim"] на чтении (файл financials.json остаётся выверенным годовым
слоем, не трогается). См. app/services/interim_overlay.py,
app/models/earnings.py::InterimFinancialsOverlay.

Revision ID: b9d3f6a1c284
Revises: fa1c7b3d9e52
Create Date: 2026-07-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "b9d3f6a1c284"
down_revision = "fa1c7b3d9e52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interim_financials_overlay",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("start_m", sa.Integer(), nullable=False),
        sa.Column("end_m", sa.Integer(), nullable=False),
        sa.Column("period_label", sa.String(length=24), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("cumulative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("standard", sa.String(length=40), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("figures", JSONB(), nullable=False),
        sa.Column("fields_present", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("source_report_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_report_id"], ["earnings_reports.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("ticker", "fiscal_year", "start_m", "end_m",
                            name="uq_interim_overlay_period"),
    )
    op.create_index("ix_interim_financials_overlay_ticker", "interim_financials_overlay", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_interim_financials_overlay_ticker", table_name="interim_financials_overlay")
    op.drop_table("interim_financials_overlay")
