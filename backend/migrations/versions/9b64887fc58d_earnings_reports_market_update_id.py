"""earnings_reports: колонка market_update_id (детект отчётов прямо из Ленты новостей)

Revision ID: 9b64887fc58d
Revises: d2b22f2662ba
Create Date: 2026-07-13

report_watch.py раньше детектил ТОЛЬКО по MOEX ir-calendar (~76/261 эмитентов
с публичным IR-календарём). Расширение: сканировать саму Ленту новостей
(market_updates) на ключевые слова отчётности — покрывает любую компанию,
у которой есть новостное освещение, не только те 76. Нужен свой дедуп-якорь
(эта запись НЕ привязана к calendar_events — событие обнаружено ПРЯМО в
новости, calendar_event_id остаётся NULL).
"""
from alembic import op
import sqlalchemy as sa

revision = "9b64887fc58d"
down_revision = "d2b22f2662ba"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("earnings_reports",
                  sa.Column("market_update_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_earnings_reports_market_update", "earnings_reports", "market_updates",
        ["market_update_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint(
        "uq_earnings_reports_market_update", "earnings_reports", ["market_update_id"])


def downgrade():
    op.drop_constraint("uq_earnings_reports_market_update", "earnings_reports", type_="unique")
    op.drop_constraint("fk_earnings_reports_market_update", "earnings_reports", type_="foreignkey")
    op.drop_column("earnings_reports", "market_update_id")
