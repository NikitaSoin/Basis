"""pair_all_prefs_drop_rhyd — полная капитализация для всех пар ао/ап + удаление дубля RHYD

1) paired_ticker раньше был проставлен только для 7 пар (миграция 3f201beb236d),
   у остальных ~36 пар ао/ап капитализация на карточках различалась:
   у обычки — только её SECURITYCAPITALIZATION, у префа — только его.
   Проставляем paired_ticker ОБОИМ сторонам для каждой пары X / XP,
   существующей в таблице (все такие пары — реальные пары ао/ап, проверено
   по именам эмитентов). Сервис get_all_companies уже умеет складывать
   капитализации по paired_ticker → combined_market_cap станет одинаковым
   на карточках обычки и префа.

2) RHYD — дублирующая запись РусГидро без капитализации и котировок
   (правильный тикер MOEX — HYDR, он в таблице есть и считается корректно).
   Удаляем дубль; в rates.csv тикера RHYD нет, при реимпорте не вернётся.

Revision ID: b4d82e91c7f3
Revises: a9f31c20d4e1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4d82e91c7f3'
down_revision: Union[str, None] = 'a9f31c20d4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Все пары ао/ап: обычке прописываем тикер префа, префу — тикер обычки.
    conn.execute(sa.text("""
        UPDATE companies c SET paired_ticker = p.ticker
        FROM companies p
        WHERE p.ticker = c.ticker || 'P' AND c.paired_ticker IS NULL
    """))
    conn.execute(sa.text("""
        UPDATE companies c SET paired_ticker = o.ticker
        FROM companies o
        WHERE c.ticker = o.ticker || 'P' AND c.paired_ticker IS NULL
    """))

    # 2. Дубль РусГидро (правильный тикер — HYDR). FK quotes/analyses/positions
    #    имеют ondelete=CASCADE, но удаляем явно — на случай старых FK без каскада.
    conn.execute(sa.text(
        "DELETE FROM quotes WHERE company_id IN (SELECT id FROM companies WHERE ticker = 'RHYD')"
    ))
    conn.execute(sa.text(
        "DELETE FROM company_analyses WHERE company_id IN (SELECT id FROM companies WHERE ticker = 'RHYD')"
    ))
    conn.execute(sa.text("DELETE FROM companies WHERE ticker = 'RHYD'"))


def downgrade() -> None:
    # paired_ticker для исходных 7 пар восстанавливает миграция 3f201beb236d;
    # здесь откатываем только массовое заполнение (обнуляем всё, кроме них).
    conn = op.get_bind()
    keep = ("SBER", "SBERP", "TATN", "TATNP", "SNGS", "SNGSP",
            "BANE", "BANEP", "RTKM", "RTKMP", "LKOH", "IRAO")
    conn.execute(
        sa.text("UPDATE companies SET paired_ticker = NULL WHERE ticker NOT IN :keep").bindparams(
            sa.bindparam("keep", expanding=True)
        ),
        {"keep": list(keep)},
    )
    # Удалённую запись RHYD не восстанавливаем (это был дубль HYDR).
