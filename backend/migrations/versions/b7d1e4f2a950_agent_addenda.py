"""agent_addenda — автономные обновления карточек (пилот DeepSeek-агентов).

Фазы 2-3 «пути к автономной платформе» (docs/status.md): агент на прод-LLM
дописывает addendum «что изменилось с последнего разбора» ПОВЕРХ карточки
(не переписывая анализ), через автогейт качества. Отдельная таблица, а не
запись в companies/<TICKER>/*.json: файлы карточек принадлежат аналитикам и
пересоздаются из git при каждом деплое — рантайм-записи в ФС были бы потеряны.

Revision ID: b7d1e4f2a950
Revises: a49ec24e0133
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7d1e4f2a950"
down_revision = "a49ec24e0133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_addenda",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),  # macro_addendum
        sa.Column("status", sa.String(length=16), nullable=False),  # published | rejected
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gate_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("run_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_agent_addenda_ticker_kind", "agent_addenda", ["ticker", "kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_addenda_ticker_kind", table_name="agent_addenda")
    op.drop_table("agent_addenda")
