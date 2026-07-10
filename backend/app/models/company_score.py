"""LLM-скоры компаний по измерениям, которые нельзя посчитать кодом (методика
индекса качества портфеля v2.1, §14: BM/MP/CA — субагент quality-scorer;
FS/Gov считаются кодом/уже есть в других файлах, здесь не хранятся).

Одна строка = один прогон одного измерения одной компании. При повторном
прогоне — новая строка (as_of), старые не удаляются (история версий скоров).
Портфельный сервис берёт последнюю по as_of.
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

DIMENSIONS = ("bm", "mp", "ca")  # бизнес-модель | рыночная позиция | capital allocation


class CompanyScore(Base):
    __tablename__ = "company_scores"
    __table_args__ = (
        UniqueConstraint("ticker", "dimension", "as_of", name="uq_company_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # bm|mp|ca
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    rationale: Mapped[str | None] = mapped_column(String(2000))
    evidence: Mapped[list | None] = mapped_column(JSONB)  # ["факт 1 из карточки", "факт 2", ...]
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    card_version: Mapped[str | None] = mapped_column(String(32))  # meta.as_of исходной карточки
    as_of: Mapped[date_type] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
