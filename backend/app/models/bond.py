from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Bond(Base):
    """Облигация — отдельный класс активов (НЕ компания).

    Своя модель: у облигации параметры долга (купон, погашение, доходность,
    дюрация, оферта, амортизация), которых нет у акции. Данные с MOEX ISS
    (рынок bonds). Аналитика-текст — в файлах backend/bonds/<SECID>/, как
    у компаний.
    """
    __tablename__ = "bonds"

    id: Mapped[int] = mapped_column(primary_key=True)
    secid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    isin: Mapped[str | None] = mapped_column(String(12))
    short_name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer_name: Mapped[str | None] = mapped_column(String(255))
    issuer_ticker: Mapped[str | None] = mapped_column(String(20))  # тикер компании-эмитента в нашей базе
    # ofz | corporate | muni | other — определяет главный вопрос инвестора
    bond_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    board: Mapped[str | None] = mapped_column(String(12))      # TQOB / TQCB / TQIR …
    currency: Mapped[str | None] = mapped_column(String(10))   # RUB / CNY …

    # ── параметры выпуска (факты эмиссии) ──
    face_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))      # номинал
    coupon_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))   # годовая ставка купона, %
    coupon_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))    # купон на бумагу, ₽
    coupon_period: Mapped[int | None] = mapped_column(Integer)              # дней между купонами
    maturity_date: Mapped[date_type | None] = mapped_column(Date)          # дата погашения
    offer_date: Mapped[date_type | None] = mapped_column(Date)             # ближайшая оферта (put/call)
    has_amortization: Mapped[bool] = mapped_column(Boolean, default=False)  # амортизация номинала
    lot_size: Mapped[int | None] = mapped_column(Integer)
    listing_level: Mapped[int | None] = mapped_column(Integer)

    # ── рыночные данные (обновляемые) ──
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))      # % от номинала
    ytm: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))             # доходность к погашению, %
    duration_days: Mapped[int | None] = mapped_column(Integer)            # дюрация, дней
    accrued_int: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))    # НКД, ₽

    # ── тип купона (определяет смысл блока чувствительности к ставке) ──
    coupon_type: Mapped[str | None] = mapped_column(String(12))            # fixed | floater | linker | other
    ytm_kind: Mapped[str | None] = mapped_column(String(16))               # «к погашению» | «к оферте»
    is_defaulted: Mapped[bool | None] = mapped_column(Boolean)             # режим Д / отметка дефолта

    # ── двойной рейтинг надёжности ──
    # (1) рыночная оценка по спреду — risk_tier (НАШ подход; ОФЗ=госдолг)
    risk_tier: Mapped[str | None] = mapped_column(String(20))             # gov | high | medium | speculative
    spread_bp: Mapped[int | None] = mapped_column(Integer)                # спред YTM к ОФЗ той же дюрации, б.п.
    # (2) агентский рейтинг — независимая от спреда оценка (АКРА/ЭкспертРА/НКР/НРА)
    agency_rating: Mapped[str | None] = mapped_column(String(16))          # AAA … D (нац. шкала)
    agency_rating_source: Mapped[str | None] = mapped_column(String(32))   # источник рейтинга

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
