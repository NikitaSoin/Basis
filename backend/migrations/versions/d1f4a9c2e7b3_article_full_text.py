"""Полные тексты статей для макро-интерпретатора

Владелец 2026-08-01: «отправляй в дипсик целиком статьи (ЦБ, ЦМАКП, Карнеги, Re:Russia
и все важные) — токены дешёвые, не паримся». До сих пор в промпт уходил только НАШ
пересказ (summary + key_takeaways), про который владелец же и говорил: «краткая выжимка
местами без сути». Первоисточник терялся.

Контекстное окно DeepSeek V4 Pro — 1 048 576 токенов, мы использовали 75 тыс. (7%),
так что места под полные тексты с избытком.

Поле заполняется ЛЕНИВО (при сборке снапшота, если пусто) и кэшируется, чтобы не
качать одно и то же каждый прогон.

Revision ID: d1f4a9c2e7b3
Revises: c4e18a7b2d90
"""
from alembic import op
import sqlalchemy as sa

revision = "d1f4a9c2e7b3"
down_revision = "c4e18a7b2d90"
branch_labels = None
depends_on = None

_TABLES = ("macro_analytics_docs", "geo_digest_articles", "chronicle_entries")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("full_text", sa.Text(), nullable=True))
        # когда пытались достать текст (успех или отказ) — чтобы не долбить мёртвый URL
        op.add_column(table, sa.Column("full_text_fetched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "full_text_fetched_at")
        op.drop_column(table, "full_text")
