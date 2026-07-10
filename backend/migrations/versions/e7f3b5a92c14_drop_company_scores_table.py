"""company_scores: откат — храним как файл companies/<TICKER>/quality_scores.json,
не таблицу БД

Revision ID: e7f3b5a92c14
Revises: d5a9e1c8b346
Create Date: 2026-07-10

Раскатывающие субагенты (quality-scorer) пишут результат ЛОКАЛЬНО (файл,
коммит, деплой через git) — как и всё остальное в проекте (financials.json,
governance.json, institutions.json). У них нет доступа к прод-БД напрямую,
поэтому таблица оставалась бы вечно пустой на бою. Переиграно на файловый
паттерн (см. portfolio_quality_v2.py._llm_scores) до реальной раскатки на
компании — откатываем таблицу, которую успели создать миграцией d5a9e1c8b346.
"""
from alembic import op

revision = "e7f3b5a92c14"
down_revision = "d5a9e1c8b346"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS company_scores")


def downgrade():
    pass  # прежняя схема — см. d5a9e1c8b346.upgrade(), не воссоздаём автоматически
