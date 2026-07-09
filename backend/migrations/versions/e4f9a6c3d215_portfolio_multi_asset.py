"""portfolio_positions: multi-asset (bond/future/fund/cash), не только акции

Revision ID: e4f9a6c3d215
Revises: d3e8f5a2b104
Create Date: 2026-07-09 15:00:00.000000

Схема по совету advisor-субагента (Fable): nullable company_id +
instrument_type + secid НА САМОЙ таблице позиций (не отдельная полиморфная
сущность) — ложится на уже существующий ключ instrument_history
(asset_class+secid), тривиально обратима (company_id никогда не удаляется),
и никто кроме портфеля не потребляет "любой инструмент" как абстракцию —
заводить её ради этого over-engineering.

expand→migrate→contract: эта миграция только РАСШИРЯЕТ схему (DROP NOT NULL +
новые nullable-колонки со статичным дефолтом — metadata-only в Postgres 11+,
без rewrite таблицы). Существующие строки бэкфиллятся instrument_type='equity'
в этой же миграции. Код с веткованием по instrument_type деплоится ПОСЛЕ.
CHECK-инвариант добавлен NOT VALID → VALIDATE отдельным шагом (не блокирует
конкурентные INSERT/UPDATE на боевой таблице во время миграции).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e4f9a6c3d215'
down_revision: Union[str, None] = 'd3e8f5a2b104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # varchar+CHECK вместо нативного Postgres ENUM — расширять список типов
    # потом (ALTER TYPE ... ADD VALUE не работает внутри транзакции и может
    # быть болезненным на боевой БД), новый тип = просто новое значение варчара.
    op.add_column(
        "portfolio_positions",
        sa.Column("instrument_type", sa.String(10), nullable=False, server_default="equity"),
    )
    op.add_column("portfolio_positions", sa.Column("secid", sa.String(40), nullable=True))
    op.add_column(
        "portfolio_positions",
        sa.Column("currency", sa.String(10), nullable=False, server_default="RUB"),
    )
    op.alter_column("portfolio_positions", "company_id", nullable=True)

    op.create_check_constraint(
        "ck_portfolio_positions_instrument_type",
        "portfolio_positions",
        "instrument_type IN ('equity','bond','future','fund','cash')",
    )
    # NOT VALID: не сканирует существующие строки сразу (не блокирует запись
    # на боевой таблице во время создания констрейнта), VALIDATE — отдельный
    # быстрый шаг сразу следом (данные уже все instrument_type='equity' с
    # company_id NOT NULL до этой миграции, инвариант заведомо верен).
    op.execute(
        "ALTER TABLE portfolio_positions ADD CONSTRAINT ck_portfolio_positions_type_ref "
        "CHECK ("
        "  (instrument_type = 'equity' AND company_id IS NOT NULL) OR "
        "  (instrument_type = 'cash' AND secid IS NULL) OR "
        "  (instrument_type IN ('bond','future','fund') AND secid IS NOT NULL)"
        ") NOT VALID"
    )
    op.execute("ALTER TABLE portfolio_positions VALIDATE CONSTRAINT ck_portfolio_positions_type_ref")

    # server_default только для бэкфилла существующих строк при ALTER —
    # дальше приложение всегда передаёт instrument_type явно, дефолт снимаем,
    # чтобы будущие ошибочные INSERT без instrument_type падали, а не тихо
    # становились equity.
    op.alter_column("portfolio_positions", "instrument_type", server_default=None)
    op.alter_column("portfolio_positions", "currency", server_default=None)


def downgrade() -> None:
    op.execute("ALTER TABLE portfolio_positions DROP CONSTRAINT ck_portfolio_positions_type_ref")
    op.drop_constraint("ck_portfolio_positions_instrument_type", "portfolio_positions", type_="check")
    op.alter_column("portfolio_positions", "company_id", nullable=False)
    op.drop_column("portfolio_positions", "currency")
    op.drop_column("portfolio_positions", "secid")
    op.drop_column("portfolio_positions", "instrument_type")
