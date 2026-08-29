"""ir_pages: поля самолечения реестра

Владелец 2026-08-29: «если название страницы/сайта поменяется (агент пришёл, а
там пусто или старое) — чтобы он нашёл новую страницу и извлёк; процесс должен
заканчиваться добычей и извлечением, а новый адрес писаться в реестр».

Без этого реестр — разовый снимок, который тихо умирает на первом редизайне
сайта эмитента: страница отвечает 404 или отдаёт архив 2023 года, а платформа
считает, что источник есть. Поля ниже дают перепривязке след: видно, что адрес
менялся, когда страница в последний раз реально отдавала документы и почему её
признали устаревшей.

Revision ID: e1c9a7b34d68
Revises: d4b7e0a91c35
Create Date: 2026-08-29

"""
from alembic import op
import sqlalchemy as sa

revision = "e1c9a7b34d68"
down_revision = "d4b7e0a91c35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ir_pages", sa.Column("rebound_count", sa.Integer(),
                                        nullable=False, server_default="0"))
    op.add_column("ir_pages", sa.Column("previous_url", sa.String(600), nullable=True))
    op.add_column("ir_pages", sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ir_pages", sa.Column("stale_reason", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("ir_pages", "stale_reason")
    op.drop_column("ir_pages", "last_ok_at")
    op.drop_column("ir_pages", "previous_url")
    op.drop_column("ir_pages", "rebound_count")
