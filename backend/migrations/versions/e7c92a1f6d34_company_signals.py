"""company_signals — сигнальная шина «поток Обозревателя → карточка компании»

Владелец (2026-07-27): входящий поток должен системно дообновлять карточки, а
не гоняться агентами в веб-серч. См. app/services/company_signals.py,
docs/observer-source-map.md, app/models/geo.py::CompanySignal.

Revision ID: e7c92a1f6d34
Revises: d5a8c2f14b90
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "e7c92a1f6d34"
down_revision = "d5a8c2f14b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("signal_type", sa.String(length=32), nullable=False),
        sa.Column("card_tab", sa.String(length=20), nullable=True),
        sa.Column("importance", sa.String(length=8), nullable=True),
        sa.Column("trust", sa.String(length=12), nullable=True),
        sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("title", sa.String(length=400), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_key", sa.String(length=48), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("dedup_key", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ticker", "signal_type", "dedup_key", name="uq_company_signal"),
    )
    op.create_index("ix_company_signals_ticker", "company_signals", ["ticker"])
    op.create_index("ix_company_signals_pub", "company_signals", ["published_at"])
    op.create_index("ix_company_signals_feed", "company_signals",
                    ["internal", "importance", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_company_signals_feed", table_name="company_signals")
    op.drop_index("ix_company_signals_pub", table_name="company_signals")
    op.drop_index("ix_company_signals_ticker", table_name="company_signals")
    op.drop_table("company_signals")
