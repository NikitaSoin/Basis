"""earnings_reports: колонка calendar_event_id (автопайплайн report_watch)

Revision ID: d2b22f2662ba
Revises: d4a8f13c6e29
Create Date: 2026-07-12

Автообнаружение отчётов (report_watch.py) детектит выход отчёта по
calendar_events (event_type=earnings), не по ручному обновлению
financials.json. Дедуп по (ticker, period, standard) хрупкий для этого пути
(period парсится эвристикой из заголовка календаря) — добавляем прямую
привязку к событию календаря как основной дедуп-ключ автопайплайна.
Существующие вручную созданные записи (financials.json-путь) остаются с
NULL — не трогаем.
"""
from alembic import op
import sqlalchemy as sa

revision = "d2b22f2662ba"
down_revision = "d4a8f13c6e29"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("earnings_reports",
                  sa.Column("calendar_event_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_earnings_reports_calendar_event", "earnings_reports", "calendar_events",
        ["calendar_event_id"], ["id"], ondelete="SET NULL")
    op.create_unique_constraint(
        "uq_earnings_reports_calendar_event", "earnings_reports", ["calendar_event_id"])


def downgrade():
    op.drop_constraint("uq_earnings_reports_calendar_event", "earnings_reports", type_="unique")
    op.drop_constraint("fk_earnings_reports_calendar_event", "earnings_reports", type_="foreignkey")
    op.drop_column("earnings_reports", "calendar_event_id")
