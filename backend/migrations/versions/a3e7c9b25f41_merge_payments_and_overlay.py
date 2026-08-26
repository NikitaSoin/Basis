"""merge: платежи и расширение overlay_ticker — свести две головы

Две параллельные сессии ответвились от одной ревизии (b6d41f8a2c07): одна
добавила таблицу платежей, другая расширила overlay_ticker. Формально это не
конфликт — таблицы разные, — но `alembic upgrade head` в start.sh знает только
про ОДНУ голову и на двух падает с «Multiple head revisions are present».

🔴 Найдено на бою: миграции не применялись вообще (30 попыток подряд в логах
старта), то есть ни одна новая таблица не создавалась — ни payments, ни чужие.
Сам сервис при этом отвечал 200 на healthcheck, поэтому со стороны выглядело
как «деплой прошёл».

Revision ID: a3e7c9b25f41
Revises: c8a1f4d7e920, c8a72e5d1930
Create Date: 2026-08-27

"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401

revision = "a3e7c9b25f41"
down_revision = ("c8a1f4d7e920", "c8a72e5d1930")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Слияние веток — своей схемы не несёт."""


def downgrade() -> None:
    """Слияние веток — своей схемы не несёт."""
