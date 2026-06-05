"""add_company_metrics — таблица числовых метрик компаний (Этап 1 аналитики портфеля)

Числа-метрики (P/E, дивдоходность, справедливая цена) живут в файлах
companies/<TICKER>/financials.json — для карточки компании это нормально,
но портфель агрегирует метрики по многим позициям разом (средневзвешенный P/E,
группировки), и читать 15 JSON-файлов на каждый расчёт медленно. Решение:
ЧИСЛА сведены в одну таблицу, текст остаётся в файлах. Источник правды прежний —
файлы; таблица наполняется из них скриптом scripts/sync_company_metrics.py.

Колонки beta и volatility добавлены сразу (nullable, НЕ заполняются — Этап 2):
пустые nullable-колонки ничего не стоят, а вторая миграция ради двух полей
через неделю — лишний цикл деплоя.

Revision ID: d3a47b8e9c12
Revises: c7e91f3a5d20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a47b8e9c12'
down_revision: Union[str, None] = 'c7e91f3a5d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=10), nullable=False, unique=True, index=True),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.Column("pe_current", sa.Numeric(12, 2), nullable=True),
        sa.Column("pe_historical", sa.Numeric(12, 2), nullable=True),   # медиана P/E за 5 лет
        sa.Column("div_yield", sa.Numeric(8, 2), nullable=True),        # %, последняя/рекомендованная выплата
        sa.Column("fair_value", sa.Numeric(14, 2), nullable=True),      # базовый сценарий, ₽/акция
        sa.Column("beta", sa.Numeric(8, 4), nullable=True),             # Этап 2 — НЕ заполняется сейчас
        sa.Column("volatility", sa.Numeric(8, 4), nullable=True),       # Этап 2 — НЕ заполняется сейчас
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("company_metrics")
