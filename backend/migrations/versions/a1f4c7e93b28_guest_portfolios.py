"""Гостевые портфели: собрать состав и увидеть аналитику можно без регистрации

Владелец 2026-08-04: «у аналитики портфеля не надо регистрироваться базово, клиент может
зайти и потыкаться; портфель не сохранится, но если зарегистрируется — должен сохраниться
тот, что он уже составил, чтобы не слетело».

🔴 ПОЧЕМУ КОЛОНКА, А НЕ ХРАНЕНИЕ В БРАУЗЕРЕ. Вся аналитика портфеля (метрики, корреляции,
дивиденды, факторный профиль, стресс-тест, ИИ-диагноз) считается на бэкенде ПО
`portfolio_id`. Держать гостевой состав только в localStorage значило бы переписать
полтора десятка эндпоинтов на приём состава в теле запроса — то есть завести вторую
реализацию всего расчётного слоя и обречь себя на расхождение между «гостевой» и
«обычной» аналитикой. Колонка `guest_token` даёт то же самое одной строкой: портфель
живёт в той же таблице, считается тем же кодом, а при регистрации ему просто
проставляется `user_id`.

`user_id` уже был nullable — модель менять не пришлось.

Гостевой токен генерирует браузер и хранит у себя; сервер знает только сам токен и не
связывает его ни с личностью, ни с почтой, ни с IP.

Revision ID: a1f4c7e93b28
Revises: 0e1a7c4b9f21
"""
from alembic import op
import sqlalchemy as sa


revision = "a1f4c7e93b28"
down_revision = "0e1a7c4b9f21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Диалоги ассистента: гостю дают один вопрос (владелец: «ассистента тоже откроем,
    # базово один запрос лимит»). Считать этот лимит надёжно можно только на сервере —
    # счётчик в браузере обнуляется очисткой хранилища. Поэтому диалог гостя пишем в ту же
    # таблицу с его токеном: и лимит считается по фактам, и ответ не теряется при
    # перезагрузке страницы. user_id становится nullable ровно для этого случая.
    op.alter_column("assistant_conversations", "user_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("assistant_conversations", sa.Column("guest_token", sa.String(64), nullable=True))
    op.create_index("ix_assistant_conv_guest", "assistant_conversations", ["guest_token"],
                    postgresql_where=sa.text("guest_token IS NOT NULL"))

    op.add_column("portfolios", sa.Column("guest_token", sa.String(64), nullable=True))
    # Основной сценарий — «найди портфели этого гостя», поэтому индекс по токену.
    # Частичный: у зарегистрированных портфелей токена нет, и в индекс они не попадают.
    op.create_index("ix_portfolios_guest_token", "portfolios", ["guest_token"],
                    postgresql_where=sa.text("guest_token IS NOT NULL"))
    # Отметка последнего обращения — по ней чистятся брошенные гостевые портфели.
    # Без неё таблица растёт от каждого, кто зашёл потыкаться и ушёл.
    op.add_column("portfolios", sa.Column("guest_seen_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_assistant_conv_guest", table_name="assistant_conversations")
    op.drop_column("assistant_conversations", "guest_token")
    op.alter_column("assistant_conversations", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("portfolios", "guest_seen_at")
    op.drop_index("ix_portfolios_guest_token", table_name="portfolios")
    op.drop_column("portfolios", "guest_token")
