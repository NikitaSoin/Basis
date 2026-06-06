"""dividends_rate_total_return — дивиденды, безрисковая ставка, total return и коэффициенты Этапа 3

1) dividends — история дивидендных выплат с MOEX ISS
   (/iss/securities/{T}/dividends): тикер, дата отсечки, размер на акцию.
2) market_params — параметры рынка с датой актуальности (безрисковая ставка
   ОФЗ-1г с G-curve, доходность рынка MCFTR): не хардкод, обновляются
   планировщиком/скриптом.
3) company_metrics:
   return_total_3y — ПОЛНАЯ доходность (цена + дивиденды), % годовых.
     Отдельная колонка, а не замена return_3y: ценовая остаётся для
     прозрачности и sanity-сравнения, в UI показывается полная.
   alpha_3y / sortino_3y / capm_expected — предрасчёт на бумагу: зависят
     только от самой бумаги и глобальных Rf/Rm → считаются один раз в
     recalc_risk_metrics и переиспользуются (портфель, карточка, сортировки).

Revision ID: a7d93f2c8e54
Revises: f8c24a6e1b07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d93f2c8e54'
down_revision: Union[str, None] = 'f8c24a6e1b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dividends",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticker", sa.String(length=10), nullable=False, index=True),
        sa.Column("record_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),  # на акцию, в валюте выплаты
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.UniqueConstraint("ticker", "record_date", "amount", name="uq_dividends_ticker_date_amount"),
    )

    op.create_table(
        "market_params",
        sa.Column("key", sa.String(length=40), primary_key=True),   # risk_free_1y, market_return_3y
        sa.Column("value", sa.Numeric(10, 4), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    for name, type_ in [
        ("return_total_3y", sa.Numeric(10, 2)),
        ("alpha_3y", sa.Numeric(10, 2)),
        ("sortino_3y", sa.Numeric(8, 2)),
        ("capm_expected", sa.Numeric(10, 2)),
    ]:
        op.add_column("company_metrics", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name in ["capm_expected", "sortino_3y", "alpha_3y", "return_total_3y"]:
        op.drop_column("company_metrics", name)
    op.drop_table("market_params")
    op.drop_table("dividends")
