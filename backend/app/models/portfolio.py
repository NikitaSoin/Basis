from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    positions: Mapped[list["PortfolioPosition"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioPosition(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    avg_buy_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")
    company: Mapped["Company"] = relationship()
    transactions: Mapped[list["PortfolioTransaction"]] = relationship(
        back_populates="position", cascade="all, delete-orphan", order_by="PortfolioTransaction.trade_date"
    )


class PortfolioTransaction(Base):
    """История сделок по позиции — заводится ПРИ КАЖДОЙ покупке/продаже (не при
    прямом исправлении количества/средней). Источник для разбивки «Реализовано /
    Не реализовано / Дивиденды получено / Комиссии уплачено» на вкладке «Состав»
    (раньше позиция хранила только текущий агрегат quantity+avg_buy_price без
    истории — добавлено 2026-07-05, старые позиции backfill'нуты одной
    синтетической сделкой на дату создания позиции, см. миграция)."""
    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("portfolio_positions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # 'buy' | 'sell'
    quantity: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    position: Mapped["PortfolioPosition"] = relationship(back_populates="transactions")
