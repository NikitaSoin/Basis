"""bonds: связка выпуск → эмитент-компания (issuer_ticker)

Для оценки долговой нагрузки эмитента (сможет ли расплатиться) и подтягивания
рисков управления/гео из карточки компании-эмитента, где эмитент публичный и
есть в нашей базе. issuer_name заполняется из MOEX (поле NAME описания выпуска),
issuer_ticker — матч на тикер компании по курируемому словарю.

Revision ID: a4c8e1f2d9b3
Revises: f3b9d25e7a14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4c8e1f2d9b3'
down_revision: Union[str, None] = 'f3b9d25e7a14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("issuer_ticker", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("bonds", "issuer_ticker")
