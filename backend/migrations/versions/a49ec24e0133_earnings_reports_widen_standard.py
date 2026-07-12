"""earnings_reports: расширить standard до String(40)

Revision ID: a49ec24e0133
Revises: 9b64887fc58d
Create Date: 2026-07-13

report_watch.py переиспользует статус календарного события (build_ir_calendar/
_classify_report_kind) как standard — там встречается «операционные результаты»
(23 симв.), не влезающее в прежний String(16) (был рассчитан только на «МСФО»/
«РСБУ»). Упало на бою DataError (StringDataRightTruncation) на AFLT.
"""
from alembic import op
import sqlalchemy as sa

revision = "a49ec24e0133"
down_revision = "9b64887fc58d"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("earnings_reports", "standard", type_=sa.String(40))


def downgrade():
    op.alter_column("earnings_reports", "standard", type_=sa.String(16))
