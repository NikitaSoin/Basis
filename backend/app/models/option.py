from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Option(Base):
    """Опцион на фьючерс (срочный рынок MOEX) — отдельный класс активов.

    САМЫЙ сложный/рискованный розничный инструмент: право (не обязанность) по
    страйку до экспирации, нелинейная выплата, тета-распад. Главный вопрос — «что
    будет с моими деньгами и оправдан ли риск», НЕ «справедливая цена». Витрина
    УРЕЗАНА (страйки около денег + ближняя экспирация), не вся доска. Греки/IV
    считаем сами (Блэк-76 от цены фьючерса) — методика Basis. Без «купить/продать».
    """
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    secid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(64))
    option_type: Mapped[str] = mapped_column(String(1), nullable=False)   # C (call) | P (put)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    central_strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))  # ATM-страйк (≈ цена фьючерса)
    expiration_date: Mapped[date_type | None] = mapped_column(Date)

    # базовый актив — ФЬЮЧЕРС
    underlying: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # SECID фьючерса
    underlying_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    asset_code: Mapped[str | None] = mapped_column(String(20))   # код базового актива (Si, SBRF…)
    asset_name: Mapped[str | None] = mapped_column(String(120))

    # премия и её разложение
    premium: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))         # расчётная цена опциона
    intrinsic_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))  # внутренняя стоимость
    time_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))       # временная стоимость
    breakeven: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))        # точка безубытка

    # модельные оценки (Блэк-76) — помечаются как оценка
    iv: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))               # подразумеваемая волатильность, %
    delta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    theta_day: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))        # распад в день, ₽
    vega: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
