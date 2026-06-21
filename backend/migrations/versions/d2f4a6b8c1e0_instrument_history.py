"""instrument_history — единая дневная история облигаций/фьючерсов/фондов

Одна таблица на три класса (asset_class+secid+date), по образцу quotes (акции) и
index_history (индексы). Метаданные уже живут в bonds/futures/funds — НЕ дублируем,
связь по secid. Источник истории — MOEX ISS (без ключей).

Revision ID: d2f4a6b8c1e0
Revises: a1c5e8b740d3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f4a6b8c1e0"
down_revision: Union[str, None] = "a1c5e8b740d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_class", sa.String(length=8), nullable=False),   # bond|future|fund
        sa.Column("secid", sa.String(length=40), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(20, 6), nullable=True),
        sa.Column("close", sa.Numeric(20, 6), nullable=True),
        sa.Column("high", sa.Numeric(20, 6), nullable=True),
        sa.Column("low", sa.Numeric(20, 6), nullable=True),
        sa.Column("value", sa.Numeric(20, 2), nullable=True),
        sa.Column("prev_close", sa.Numeric(20, 6), nullable=True),
        sa.Column("change_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("yld", sa.Numeric(10, 4), nullable=True),          # YTM (облигации)
        sa.Column("accrued_int", sa.Numeric(16, 4), nullable=True),  # НКД (облигации)
        sa.Column("settle", sa.Numeric(20, 6), nullable=True),       # расч. цена (фьючерсы)
        sa.Column("oi", sa.BigInteger(), nullable=True),             # ОИ (фьючерсы)
        sa.UniqueConstraint("asset_class", "secid", "date", name="uq_instr_hist_class_secid_date"),
    )
    op.create_index("ix_instr_hist_class_secid", "instrument_history", ["asset_class", "secid"])


def downgrade() -> None:
    op.drop_index("ix_instr_hist_class_secid", table_name="instrument_history")
    op.drop_table("instrument_history")
