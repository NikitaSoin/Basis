from datetime import date as date_type, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Future(Base):
    """Фьючерс — отдельный класс активов (дериватив, НЕ компания и НЕ облигация).

    Своя модель: контракт с ДАТОЙ ЭКСПИРАЦИИ, гарантийным обеспечением (ГО) и
    встроенным ПЛЕЧОМ. У фьючерса нет «справедливой цены через фундаментал» и
    нет «эмитента с отчётностью» — единица анализа это КОНТРАКТ на базовый актив.
    Данные с MOEX ISS, срочный рынок FORTS (engine=futures, market=forts).
    Аналитика-текст — в файлах backend/futures/<SECID>/, как у компаний/облигаций.
    """
    __tablename__ = "futures"

    id: Mapped[int] = mapped_column(primary_key=True)
    secid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    short_name: Mapped[str] = mapped_column(String(255), nullable=False)   # Si-6.26
    sec_name: Mapped[str | None] = mapped_column(String(255))              # Фьючерсный контракт Si-6.26
    board: Mapped[str | None] = mapped_column(String(12))                  # RFUD / ...

    # ── базовый актив (то, на что контракт) ──
    asset_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # Si, RTS, BR…
    asset_name: Mapped[str | None] = mapped_column(String(120))            # человеч. имя: «Доллар США / рубль»
    # currency | index | commodity | stock | rate | other — задаёт смысл карточки и расчёт базиса
    asset_kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    linked_ticker: Mapped[str | None] = mapped_column(String(20))          # для фьючерса на акцию → тикер в БД

    # ── параметры контракта (факты) ──
    expiration_date: Mapped[date_type | None] = mapped_column(Date)        # последний торговый день
    min_step: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))       # шаг цены
    step_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 8))     # стоимость шага, ₽
    lot_volume: Mapped[int | None] = mapped_column(Integer)                # единиц БА в контракте

    # ── рыночные данные (обновляемые) ──
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    settle_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))   # расчётная цена клиринга
    prev_settle: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    open_position: Mapped[int | None] = mapped_column(Integer)             # открытые позиции (ликвидность)

    # ── ГО и плечо (риск-профиль деривати­ва) ──
    initial_margin: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))  # ГО, ₽
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))  # номинал контракта, ₽ (расчёт)
    leverage: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))         # эффективное плечо = номинал/ГО

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
