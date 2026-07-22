"""earnings_digests rich fields — highlights/risks_or_caveats/data_gaps

Обозреватель → Отчёты давал вывод беднее, чем «Разбор документа по ссылке»
у ассистента, хотя это та же LLM (владелец, 2026-07-23): report_watch.py уже
для части источников (RSS компании/СКРИН/ПРАЙМ/АЗИПИ/Лента новостей) держит
на руках реальный текст источника, но раньше сжимал его до 4 голых чисел
(_extract_financial) до того, как отдать модели — сама richness текста
терялась. Новые поля хранят богатый разбор (см. report_watch._digest_rich)
тем же способом, что document_analyst.analyze_document уже возвращает
пользователю по ссылке — просто теперь то же самое автоматически, без
ручной вставки ссылки.

Revision ID: e1a4c7f92b35
Revises: d3a9f1c6e820
Create Date: 2026-07-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e1a4c7f92b35"
down_revision = "d3a9f1c6e820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("earnings_digests", sa.Column("highlights", postgresql.JSONB(), nullable=True))
    op.add_column("earnings_digests", sa.Column("risks_or_caveats", postgresql.JSONB(), nullable=True))
    op.add_column("earnings_digests", sa.Column("data_gaps", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("earnings_digests", "data_gaps")
    op.drop_column("earnings_digests", "risks_or_caveats")
    op.drop_column("earnings_digests", "highlights")
