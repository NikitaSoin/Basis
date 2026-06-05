"""quotes_unique_index_history — фундамент под историю котировок (Этап 0 аналитики портфеля)

1) Уникальность quotes по (company_id, date): история закачивается идемпотентно
   через INSERT ... ON CONFLICT, повторный запуск не плодит дубли.
   Перед созданием ограничения вычищаем уже существующие дубли (оставляем
   самую свежую запись — max(id)).

2) Таблица index_history — дневная история бенчмарк-индексов (IMOEX, RTSI,
   MCFTR). Отдельная таблица, а НЕ записи в quotes, потому что quotes привязана
   к companies через FK company_id, а индекс — не компания: фиктивные строки
   в companies загрязнили бы список компаний на сайте и все выборки по нему.

Revision ID: c7e91f3a5d20
Revises: b4d82e91c7f3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e91f3a5d20'
down_revision: Union[str, None] = 'b4d82e91c7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1а. Дубли (company_id, date) — оставляем самую свежую запись (max id).
    conn.execute(sa.text("""
        DELETE FROM quotes q
        USING quotes q2
        WHERE q.company_id = q2.company_id
          AND q.date = q2.date
          AND q.id < q2.id
    """))

    # 1б. Уникальность — опора для ON CONFLICT при закачке истории.
    op.create_unique_constraint("uq_quotes_company_date", "quotes", ["company_id", "date"])

    # 2. История бенчмарк-индексов.
    op.create_table(
        "index_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=20), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(16, 4), nullable=True),
        sa.Column("close", sa.Numeric(16, 4), nullable=False),
        sa.Column("high", sa.Numeric(16, 4), nullable=True),
        sa.Column("low", sa.Numeric(16, 4), nullable=True),
        sa.Column("value", sa.Numeric(20, 2), nullable=True),  # оборот, руб (у MCFTR отсутствует)
        sa.UniqueConstraint("ticker", "date", name="uq_index_history_ticker_date"),
    )


def downgrade() -> None:
    op.drop_table("index_history")
    op.drop_constraint("uq_quotes_company_date", "quotes", type_="unique")
