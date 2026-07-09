"""RAGR (Русагро) historical_tickers со split_ratio=7 (сплит при редомициляции)

Revision ID: a8d4f2c7b391
Revises: f7b3c9e1a628
Create Date: 2026-07-09 20:00:00.000000

Ранее RAGR←AGRO был сознательно ИСКЛЮЧЁН из бэкфилла (см. f7b3c9e1a628) —
разрыв цены на стыке ×6.6 выглядел как структурная нестыковка, а не 1:1
конверсия. Владелец подтвердил: при редомициляции Русагро был сплит акций
1:7 (цена ~1450₽ → ~210₽), что согласуется с наблюдённым разрывом
(1450/7 ≈ 207, близко к фактическим ~210-220₽ открытия RAGR). Теперь
поддержан split-adjustment (moex_history._apply_split_ratio) — цены AGRO
делятся на 7 перед склейкой с RAGR.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8d4f2c7b391'
down_revision: Union[str, None] = 'f7b3c9e1a628'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        'UPDATE companies SET historical_tickers = '
        '\'[{"ticker": "AGRO", "split_ratio": 7}]\'::json '
        "WHERE ticker = 'RAGR'"
    )


def downgrade() -> None:
    op.execute("UPDATE companies SET historical_tickers = NULL WHERE ticker = 'RAGR'")
