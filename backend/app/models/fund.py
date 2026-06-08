from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class Fund(Base):
    """Биржевой фонд (БПИФ/ETF) — отдельный класс активов.

    Фонд — УПАКОВКА (корзина чужих активов в одной бумаге), НЕ бизнес и НЕ
    должник. Главный вопрос: что внутри, сколько стоит (TER), честно ли следует
    бенчмарку, нужен ли поверх портфеля. Данные с MOEX ISS (борд TQTF). TER и
    состав — не на MOEX (сайты УК), заполняются курируемо/аналитиком (nullable).
    """
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    secid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    isin: Mapped[str | None] = mapped_column(String(12))
    short_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sec_name: Mapped[str | None] = mapped_column(String(255))
    # equity | bonds | gold | money_market | currency | mixed — задаёт смысл карточки
    fund_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    benchmark: Mapped[str | None] = mapped_column(String(120))   # на какой индекс/актив (если известно)
    currency: Mapped[str | None] = mapped_column(String(10))
    listing_level: Mapped[int | None] = mapped_column(Integer)

    # ── рыночные данные (обновляемые) ──
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    val_today: Mapped[int | None] = mapped_column(BigInteger)    # оборот за день, ₽ (ликвидность)
    num_trades: Mapped[int | None] = mapped_column(Integer)      # число сделок (ликвидность)

    # ── комиссия фонда (главный тихий враг; не на MOEX — курируемо) ──
    ter: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))   # совокупные расходы, % годовых

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
