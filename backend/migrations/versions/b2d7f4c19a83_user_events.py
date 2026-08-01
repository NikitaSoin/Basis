"""user_events: продуктовый лог действий пользователей

Владелец 2026-08-01: «хотелось бы записывать/учитывать логи по клиентам и знать, как
часто они заходят, по каким страницам ходят, что кликают».

ЗАЧЕМ СВОЯ ТАБЛИЦА, ЕСЛИ ЕСТЬ МЕТРИКА: Метрика считает ВИЗИТЫ и не знает, кто их
совершил. Она не ответит на вопросы вида «пользователи, у которых портфель больше пяти
бумаг, чаще открывают корреляции?» — а именно такие вопросы и двигают продукт. Свой лог
кладётся рядом с users и portfolios в одной базе, поэтому джойнится обычным SQL.
Метрику при этом не заменяет: карты кликов и записи сессий остаются за ней.

🔴 БЕЗ ПЕРСОНАЛЬНЫХ ДАННЫХ В СОБЫТИЯХ. Пишем user_id (у гостей — NULL) и анонимный
идентификатор устройства. Ни почт, ни имён, ни IP: они не нужны для продуктовых выводов,
а хранить их — принимать на себя обязательства по 152-ФЗ без надобности.

Revision ID: b2d7f4c19a83
Revises: d1f4a9c2e7b3
"""
from alembic import op
import sqlalchemy as sa


revision = "b2d7f4c19a83"
down_revision = "d1f4a9c2e7b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("id", sa.BigInteger, primary_key=True),
        # NULL — незалогиненный посетитель: его путь тоже важен, именно на нём видно,
        # доходит ли человек до регистрации вообще.
        sa.Column("user_id", sa.Integer, nullable=True, index=True),
        # Анонимный идентификатор устройства из localStorage: связывает шаги одного
        # человека до входа в аккаунт и после.
        sa.Column("anon_id", sa.String(64), nullable=True, index=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        # Что произошло: pageview | click | action.
        sa.Column("kind", sa.String(24), nullable=False),
        # Имя события для click/action: "открыл вкладку", "применил фильтр" и т.п.
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column("path", sa.String(512), nullable=True),
        sa.Column("referrer", sa.String(512), nullable=True),
        # Произвольные детали: тикер, вкладка, параметры фильтра.
        sa.Column("meta", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    # Основной сценарий чтения — «что делал этот человек» и «что было за период»,
    # поэтому индексы по (user_id, времени) и по времени.
    op.create_index("ix_user_events_user_time", "user_events", ["user_id", "created_at"])
    op.create_index("ix_user_events_time", "user_events", ["created_at"])
    op.create_index("ix_user_events_kind_time", "user_events", ["kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_events_kind_time", table_name="user_events")
    op.drop_index("ix_user_events_time", table_name="user_events")
    op.drop_index("ix_user_events_user_time", table_name="user_events")
    op.drop_table("user_events")
