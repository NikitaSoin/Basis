"""observer_reports: колонка topic (Направление 5, темы ИИ-обзора)

Revision ID: c4d8f2a731eb
Revises: b3e7a1f9c204
Create Date: 2026-07-10

Фронт уже отправлял topic (biz|macro|geo|institutions|mixed) в POST
/observer/reports — бэкенд его полностью игнорировал (не было ни колонки,
ни параметра, ни использования в промпте). Добавляет реальную поддержку.
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d8f2a731eb"
down_revision = "b3e7a1f9c204"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("observer_reports",
                  sa.Column("topic", sa.String(length=16), nullable=False, server_default="mixed"))


def downgrade():
    op.drop_column("observer_reports", "topic")
