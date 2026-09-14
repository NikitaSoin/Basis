"""Очередь ручных запусков фоновых задач (job_requests).

Зачем: планировщик и все тяжёлые задачи (LLM-цепочки, пересчёт метрик, разбор PDF)
уехали из веб-процесса uvicorn в отдельный процесс-воркер (app/worker.py) — инцидент
2026-09-14: ручной прогон аналитиков и стартовый залп задач голодом по CPU/GIL
вешали ответы сайта всем посетителям. Веб-процесс больше не исполняет задачи сам:
ручной запуск = строка в этой таблице, воркер забирает её и исполняет. Таблица —
единственный источник статуса ручных прогонов (раньше статус жил в памяти веба и
терялся при рестарте).

Revision ID: b8d4f2a6c1e7
Revises: a7c3e9d1f5b2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b8d4f2a6c1e7"
down_revision = "a7c3e9d1f5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_requests_status_id", "job_requests", ["status", "id"])


def downgrade() -> None:
    op.drop_index("ix_job_requests_status_id", table_name="job_requests")
    op.drop_table("job_requests")
