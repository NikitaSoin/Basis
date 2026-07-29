"""card_prose_overlays — версионный оверлей авто-патчей прозы вкладок карточки

Авто-свежесть текста разборов (владелец 2026-07-29). Файлы на Timeweb эфемерны →
патчи в БД, summary-эндпоинты читают «оверлей → фолбэк файл». См.
app/services/card_prose_patcher.py, docs/prose-freshness-plan.md,
app/models/geo.py::CardProseOverlay.

Revision ID: fa1c7b3d9e52
Revises: e7c92a1f6d34
Create Date: 2026-07-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "fa1c7b3d9e52"
down_revision = "e7c92a1f6d34"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_prose_overlays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("tab", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("patched_md", sa.Text(), nullable=True),
        sa.Column("original_md", sa.Text(), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("gate_notes", JSONB(), nullable=True),
        sa.Column("source_signal_id", sa.Integer(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("model_used", sa.String(length=64), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_card_prose_overlays_ticker", "card_prose_overlays", ["ticker"])
    # витрина: последний published на (ticker, tab)
    op.create_index("ix_card_prose_overlays_lookup", "card_prose_overlays",
                    ["ticker", "tab", "status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_card_prose_overlays_lookup", table_name="card_prose_overlays")
    op.drop_index("ix_card_prose_overlays_ticker", table_name="card_prose_overlays")
    op.drop_table("card_prose_overlays")
