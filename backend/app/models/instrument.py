"""История цен биржевых инструментов НЕ-акционной природы: облигации, фьючерсы, фонды.

Одна таблица на все три класса (asset_class+secid), по образцу quotes (акции) и
index_history (индексы). Метаданные инструментов уже живут в работающих таблицах
bonds / futures / funds — здесь НЕ дублируем их, только дневной ряд цен для графиков/
спарклайнов на экране «Рынок». Источник истории — MOEX ISS (рынок bonds/forts/shares),
без ключей. Связь с метаданными — по secid.
"""
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class InstrumentHistory(Base):
    __tablename__ = "instrument_history"
    __table_args__ = (
        UniqueConstraint("asset_class", "secid", "date", name="uq_instr_hist_class_secid_date"),
        Index("ix_instr_hist_class_secid", "asset_class", "secid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(8), nullable=False)   # bond|future|fund
    secid: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)

    open: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))         # облигации — % номинала
    high: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    low: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))         # оборот, руб
    prev_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))

    yld: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))           # YTM на дату (облигации)
    accrued_int: Mapped[Decimal | None] = mapped_column(Numeric(16, 4))   # НКД (облигации)
    settle: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))        # расчётная цена (фьючерсы)
    oi: Mapped[int | None] = mapped_column(BigInteger)                    # открытый интерес (фьючерсы)
