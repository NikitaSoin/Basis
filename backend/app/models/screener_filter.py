from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class SavedScreenerFilter(Base):
    """Пользовательский сохранённый набор фильтров скринера (акции/облигации).

    Конкурентный разбор ПроФинанс 2026-07-11 — «Сохранить»/«Сбросить» свой сет
    фильтров, у Basis раньше были только зашитые в код пресеты. config — весь
    клиентский стейт конструктора фильтров (ranges/sector/universe/sort/type/
    lightFilter — форма зависит от asset_class), фронт же его и формирует —
    бэк не разбирает структуру, просто хранит и отдаёт обратно."""
    __tablename__ = "screener_saved_filters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(10), nullable=False)  # stocks | bonds
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
