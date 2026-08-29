"""ir_pages — реестр страниц раскрытия отчётности на сайтах эмитентов

Владелец 2026-08-29 выбрал вариант 2 из развилки в журнале: центры раскрытия
рынок не покрывают (ПРАЙМ отдаёт раскрытия 2023 года, Интерфакс закрыт
JS-проверкой, АК&М рисуется скриптом), а сайты компаний с боевого сервера
доступны — неизвестен ПУТЬ. Реестр собирается один раз и живёт годами.

Почему таблица, а не файл в репозитории: собирать надо С БОЯ (сеть инстанса и
сеть разработчика видят интернет по-разному), а на Timeweb файлы эфемерны —
запись должна пережить рестарт и обновляться без выкатки.

Revision ID: d4b7e0a91c35
Revises: a3e7c9b25f41
Create Date: 2026-08-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4b7e0a91c35"
down_revision = "a3e7c9b25f41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ir_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(10), nullable=False),
        sa.Column("url", sa.String(600), nullable=False),
        sa.Column("title", sa.String(250), nullable=True),
        # Что нашли на странице при проверке — по этим числам видно, реестр
        # ведёт на список документов или на общую страницу «Акционерам».
        sa.Column("doc_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("source", sa.String(16), nullable=False, server_default="search"),
        sa.Column("examples", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ir_pages_ticker", "ir_pages", ["ticker"], unique=True)
    op.create_index("ix_ir_pages_status", "ir_pages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ir_pages_status", table_name="ir_pages")
    op.drop_index("ix_ir_pages_ticker", table_name="ir_pages")
    op.drop_table("ir_pages")
