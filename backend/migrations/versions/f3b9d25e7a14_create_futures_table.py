"""create_futures_table — класс активов Фьючерсы (срочный рынок FORTS)

Фьючерс — отдельная сущность (НЕ компания, НЕ облигация): контракт с датой
экспирации, гарантийным обеспечением (ГО) и встроенным плечом. Данные с MOEX ISS
(engine=futures, market=forts), аналитика-текст — в файлах backend/futures/<SECID>/.

Revision ID: f3b9d25e7a14
Revises: e2a7c1f44b80
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b9d25e7a14'
down_revision: Union[str, None] = 'e2a7c1f44b80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "futures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("secid", sa.String(length=36), nullable=False, unique=True, index=True),
        sa.Column("short_name", sa.String(length=255), nullable=False),
        sa.Column("sec_name", sa.String(length=255), nullable=True),
        sa.Column("board", sa.String(length=12), nullable=True),
        sa.Column("asset_code", sa.String(length=20), nullable=False, index=True),
        sa.Column("asset_name", sa.String(length=120), nullable=True),
        sa.Column("asset_kind", sa.String(length=16), nullable=False, index=True),
        sa.Column("linked_ticker", sa.String(length=20), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("min_step", sa.Numeric(16, 8), nullable=True),
        sa.Column("step_price", sa.Numeric(16, 8), nullable=True),
        sa.Column("lot_volume", sa.Integer(), nullable=True),
        sa.Column("last_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("settle_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("prev_settle", sa.Numeric(18, 6), nullable=True),
        sa.Column("open_position", sa.Integer(), nullable=True),
        sa.Column("initial_margin", sa.Numeric(16, 4), nullable=True),
        sa.Column("contract_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("leverage", sa.Numeric(8, 2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("futures")
