"""consents: чем человек подтвердил условия и согласия

Владелец 2026-09-06: опубликовать документы и брать акцепт при регистрации.

ЗАЧЕМ ОТДЕЛЬНАЯ ТАБЛИЦА. Галочка на форме сама по себе ничего не доказывает: если
завтра человек скажет «я не соглашался», ответить нечем. Нужна запись — кто, что
именно, какой РЕДАКЦИИ и когда. Редакция обязательна: документы меняются, и через
год «принял оферту» без номера редакции не значит ничего.

🔴 ЧТО СЮДА НЕ ПИШЕТСЯ. Согласия на обработку персональных данных при регистрации
здесь нет и быть не должно: почта, портфель и платежи обрабатываются на основании
ДОГОВОРА (п. 5 ч. 1 ст. 6 152-ФЗ), а не согласия. С 01.09.2025 согласие обязано
быть отдельным документом, и склейка «принимаю оферту и согласен на обработку»
одной галочкой прямо запрещена. Виды записей: offer_accept (акцепт оферты),
analytics (аналитика посещений), ai_transfer (передача в языковую модель за
границу), marketing (рекламные рассылки).

Гость тоже субъект: guest_token позволяет запомнить его выбор по аналитике до
регистрации, а при регистрации запись достаётся аккаунту.

Revision ID: b9e4f2a71d35
Revises: f7a2c93e1b54
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b9e4f2a71d35"
down_revision = "f7a2c93e1b54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=True, index=True),
        sa.Column("guest_token", sa.String(64), nullable=True, index=True),
        # offer_accept | analytics | ai_transfer | marketing
        sa.Column("kind", sa.String(24), nullable=False),
        # Редакция документа или текста согласия на момент подтверждения.
        sa.Column("version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("granted_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        # Отзыв не удаляет запись: «когда согласился и когда передумал» — часть
        # доказательства. Действующим считается согласие с пустым revoked_at.
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_consents_user_kind", "consents", ["user_id", "kind"])
    op.create_index("ix_consents_guest_kind", "consents", ["guest_token", "kind"])


def downgrade() -> None:
    op.drop_index("ix_consents_guest_kind", table_name="consents")
    op.drop_index("ix_consents_user_kind", table_name="consents")
    op.drop_table("consents")
