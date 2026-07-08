from datetime import date, datetime, timezone
from decimal import Decimal
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    # Число акций (из rates.csv ISSUESIZE — НЕценовое поле). Капитализация считается
    # живьём = последний close из quotes × shares_outstanding (см. quotes_updater).
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger)
    paired_ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Прежние тикеры компании (редомициляция/переименование, напр. Yandex N.V.
    # YNDX → МКПАО «Яндекс» YDEX) — список строк. История котировок под этими
    # тикерами бэкфиллится в ТУ ЖЕ company_id (см. scripts/backfill_historical_tickers.py),
    # чтобы метрики доходности/риска не обрывались на дате смены тикера.
    historical_tickers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    analyses: Mapped[list["CompanyAnalysis"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyAnalysis(Base):
    __tablename__ = "company_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    bull_case: Mapped[list | None] = mapped_column(JSON)
    bear_case: Mapped[list | None] = mapped_column(JSON)
    risks: Mapped[list | None] = mapped_column(JSON)
    fair_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    analyst_note: Mapped[str | None] = mapped_column(Text)
    business_model: Mapped[dict | None] = mapped_column(JSON)
    financials: Mapped[dict | None] = mapped_column(JSON)
    competitors: Mapped[dict | None] = mapped_column(JSON)
    macro_economy: Mapped[dict | None] = mapped_column(JSON)
    global_economy: Mapped[dict | None] = mapped_column(JSON)
    geopolitics: Mapped[dict | None] = mapped_column(JSON)
    technical_analysis: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    company: Mapped["Company"] = relationship(back_populates="analyses")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    close: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    change_abs: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    company: Mapped["Company"] = relationship(back_populates="quotes")
