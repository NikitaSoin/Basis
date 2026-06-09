from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class SpotAsset(Base):
    """Спот-инструмент валютного рынка MOEX: валюта (USD/CNY/EUR за рубль) или
    драгметалл (золото/серебро за рубль). Отдельный класс активов.

    Главный вопрос — НЕ «справедливая цена» (её нет), а «что дальше с курсом/
    ценой и какова роль в портфеле» (валюта → макро/ДКП; металл → защитный актив).
    Данные с MOEX ISS (engine=currency/selt). Аналитика-текст — в файлах
    backend/spot/<SECID>/.
    """
    __tablename__ = "spot_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    secid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    short_name: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))        # человеч.: «Доллар США / рубль»
    kind: Mapped[str] = mapped_column(String(12), nullable=False, index=True)  # currency | metal
    base_code: Mapped[str | None] = mapped_column(String(10))    # USD/CNY/EUR/GLD/SLV

    last_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))   # ₽ за единицу
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))    # % к пред. закрытию

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
