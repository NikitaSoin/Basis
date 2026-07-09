"""historical_tickers для T/HEAD/X5 (редомициляция, подтверждена непрерывность цены)

Revision ID: f7b3c9e1a628
Revises: e4f9a6c3d215
Create Date: 2026-07-09 18:00:00.000000

Найдено при аудите после жалобы владельца: «Т-Технологии считаются за 1,6
года». Проверил вручную по MOEX ISS всех компаний с history_years < 2.9 на
предмет редомициляции/смены тикера (не просто молодых IPO):

- T (Т-Технологии) ← TCSG (TCS Group): TCSG close 2024-11-27 = 2384.8,
  T open 2024-11-28 = 2390 — непрерывно, 1:1.
- HEAD (Хэдхантер) ← HHRU: HHRU заморожен на 3905, HEAD open 2024-09-26 =
  3899 — непрерывно, 1:1.
- X5 (X5 Group) ← FIVE: FIVE заморожен на 2792.5, X5 close 2025-01-09 =
  2803 — непрерывно (близко), 1:1.
- KFBA (Инград) ← INGR: последняя реальная цена INGR ~1779-1820 (май 2024),
  KFBA открывается ~1704-1712 (июнь 2025) — непрерывно (близко), 1:1.

НЕ включены (проверены и ОТКЛОНЕНЫ — не безопасно сплайсить, разрыв
структурный, не просто движение цены за время простоя):
- RAGR (Русагро) ← AGRO: последняя реальная цена AGRO ~1433-1473
  (май 2024), RAGR стартует с 216 (февр. 2025) — разрыв ~×6.6, похоже на
  сплит/конверсию GDR→акция с коэффициентом, НЕ 1:1. Нужна отдельная
  split-adjustment логика (не просто склейка), не делаю вслепую.
- FIXR (Фикс Прайс) ← FIXP: последняя реальная цена FIXP ~276-290 (май
  2024), FIXR открывается ~0.97-1.17 (авг. 2025) — разрыв ~×300, точно
  сплит/редоминация номинала, не 1:1.
- CNRU (Циан) ← CIAN: последняя РЕАЛЬНАЯ цена CIAN 933 (май 2024, до этого
  ещё замораживалась на 575 — два разных «замороженных» значения, что само
  по себе подозрительно), CNRU стартует с 685 (апр. 2025) — расхождение
  ~19-27% в обе стороны, неоднозначно (может быть реальное падение за 11
  месяцев простоя, а может — дисконт/хэркат конкретно для Циан). Оставлено
  на честную деградацию (короткая история), не гадаю.

Остальные компании из аудита (history_years < 2.9) — проверены на предмет
старого тикера по MOEX ISS точечно там, где название вызывало подозрение;
для основной массы (Диасофт/Астра/Хэндерсон/Софтлайн/Элемент/Займер/
Делимобиль/МГКЛ/ВИ.ру/ИВА/Промомед/АПРИ/Ламбумиз/Арендата/Кристалл/
Европлан/Совкомбанк/ЕвроТранс/ЮГК/Артген) короткая история — ФАКТ (недавние
IPO 2021-2024), не баг.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7b3c9e1a628'
down_revision: Union[str, None] = 'e4f9a6c3d215'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE companies SET historical_tickers = '[\"TCSG\"]'::json WHERE ticker = 'T'")
    op.execute("UPDATE companies SET historical_tickers = '[\"HHRU\"]'::json WHERE ticker = 'HEAD'")
    op.execute("UPDATE companies SET historical_tickers = '[\"FIVE\"]'::json WHERE ticker = 'X5'")
    op.execute("UPDATE companies SET historical_tickers = '[\"INGR\"]'::json WHERE ticker = 'KFBA'")


def downgrade() -> None:
    op.execute("UPDATE companies SET historical_tickers = NULL WHERE ticker IN ('T', 'HEAD', 'X5', 'KFBA')")
