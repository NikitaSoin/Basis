"""Пул источников: то, что агент нашёл в вебе, возвращается в постоянный поток.

🔴 Владелец, 2026-08-26: «если нашли какую-то информацию — нужно, чтобы источник, с
которого информация тянулась, так же попал в пул источников, с которых мы что-то
парсим».

Зачем это отдельная сущность. Сейчас платформа читает 13 RSS-лент. Когда ревизия
находит существенный факт (смена собственника, новая программа капвложений, суд с
регулятором), он почти всегда приходит с сайта, которого в этих тринадцати нет: у
компании свой раздел раскрытия, у отрасли своё издание, у эмитента облигаций свой
пресс-центр. Разовая находка чинит одну карточку, но источник остаётся неизвестным — и
через месяц та же дыра повторяется.

Здесь находки накапливаются: у каждого адреса считается, сколько раз он реально
пригодился и по каким темам. Домен, пригодившийся несколько раз, повышается до
постоянной ленты — если у него нашлась RSS. Повышение НЕ требует деплоя: ленту читает
тот же news_pipeline, просто список лент теперь склеивается из файла конфигурации и
одобренных находок.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DiscoveredSource(Base):
    """Источник, найденный агентом при активной ревизии.

    status: candidate — просто пригодился; approved — повышен до постоянной ленты
    (feed_url обязателен); rejected — вручную отклонён, больше не предлагать.
    """
    __tablename__ = "discovered_sources"
    __table_args__ = (UniqueConstraint("domain", name="uq_discovered_source_domain"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    domain: Mapped[str] = mapped_column(String(160), index=True)
    sample_url: Mapped[str | None] = mapped_column(String(1000))
    feed_url: Mapped[str | None] = mapped_column(String(1000))
    topics: Mapped[str | None] = mapped_column(Text)      # через запятую: вкладки/темы
    found_for: Mapped[str | None] = mapped_column(Text)   # тикеры/эмитенты, через запятую
    hits: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="candidate", index=True)
    note: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
