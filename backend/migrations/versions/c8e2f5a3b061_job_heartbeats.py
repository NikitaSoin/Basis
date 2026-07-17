"""job_heartbeats — мониторинг кронов (фаза 6 «пути к автономной платформе»).

Боль: сбои кронов замечались только вручную (лента новостей стояла сутками,
2026-07-05). Таблица переживает рестарты контейнера (in-memory реестр обнулялся
бы каждым деплоем и давал ложные «всё молчит»).

Revision ID: c8e2f5a3b061
Revises: c8e2f5a71d43
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa

revision = "c8e2f5a3b061"
down_revision = "c8e2f5a71d43"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_heartbeats",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_text", sa.Text(), nullable=True),
        sa.Column("runs_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("job_heartbeats")
