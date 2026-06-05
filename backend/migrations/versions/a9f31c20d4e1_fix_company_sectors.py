"""fix_company_sectors — переносим компании в корректные секторы

Правки классификации (поле companies.sector):
  NKNC/NKNCP   Нефть и газ            → Химия            (нефтехимия, не добыча)
  CARM         IT-сектор              → Финансы          (МФО CarMoney)
  OZPH         Потребительский сектор → Здравоохранение  (фарма)
  DZRD/DZRDP   Здравоохранение        → Машиностроение   (радиодетали)
  BAZA         Прочее                 → IT-сектор
  NKSH         Химия                  → Машиностроение   (шины — автокомпоненты)
  EUTR         Транспорт и логистика  → Нефть и газ      (сеть АЗС)
  TRNFP        Нефть и газ            → Транспорт и логистика (трубопроводная монополия)
  RTGZ         Нефть и газ            → Транспорт и логистика (газораспределение)
  ELMT         IT-сектор              → Машиностроение   (микроэлектроника)
  URKZ         Металлургия            → Машиностроение   (кузнечно-прессовое пр-во)
  RBCM         IT-сектор              → Прочее           (медиа)
  PRFN         Прочее                 → Металлургия      (Теплант Восток — переработка
                                         рулонной стали/сэндвич-панели; НЕ машиностроение)
SVET/SVETP сознательно оставлены в «Потребительский сектор» (EdTech-услуги
подготовки водителей — не машиностроение).

Revision ID: a9f31c20d4e1
Revises: edc3f7b8546b
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9f31c20d4e1'
down_revision: Union[str, None] = 'edc3f7b8546b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# тикер → (новый сектор, старый сектор для downgrade)
SECTOR_FIXES: dict[str, tuple[str, str]] = {
    "NKNC": ("Химия", "Нефть и газ"),
    "NKNCP": ("Химия", "Нефть и газ"),
    "CARM": ("Финансы", "IT-сектор"),
    "OZPH": ("Здравоохранение", "Потребительский сектор"),
    "DZRD": ("Машиностроение", "Здравоохранение"),
    "DZRDP": ("Машиностроение", "Здравоохранение"),
    "BAZA": ("IT-сектор", "Прочее"),
    "NKSH": ("Машиностроение", "Химия"),
    "EUTR": ("Нефть и газ", "Транспорт и логистика"),
    "TRNFP": ("Транспорт и логистика", "Нефть и газ"),
    "RTGZ": ("Транспорт и логистика", "Нефть и газ"),
    "ELMT": ("Машиностроение", "IT-сектор"),
    "URKZ": ("Машиностроение", "Металлургия"),
    "RBCM": ("Прочее", "IT-сектор"),
    "PRFN": ("Металлургия", "Прочее"),
}


def upgrade() -> None:
    conn = op.get_bind()
    for ticker, (new_sector, _old) in SECTOR_FIXES.items():
        conn.execute(
            sa.text("UPDATE companies SET sector = :s WHERE ticker = :t"),
            {"s": new_sector, "t": ticker},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for ticker, (_new, old_sector) in SECTOR_FIXES.items():
        conn.execute(
            sa.text("UPDATE companies SET sector = :s WHERE ticker = :t"),
            {"s": old_sector, "t": ticker},
        )
