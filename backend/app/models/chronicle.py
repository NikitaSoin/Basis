"""Аналитическая летопись (chronicle) — ПОСТОЯННАЯ память платформы для агентов.

В отличие от Ленты (`market_updates`) и дайджеста (`geo_digest_articles`) —
эфемерных display-слоёв с ретеншеном — летопись append-only: важные события и
аналитические статьи оседают надолго с готовой интерпретацией, чтобы LLM-агенты
карточек/стресс-теста могли быстро получить «что это значило» по тикеру/сектору/
теме, не переанализируя первоисточник заново.

Дизайн (валидирован советником 2026-07-22):
- `kind` — ЖАНР: news (факт) vs article (интерпретация). НЕ дедупим между жанрами
  (новость «ЦБ поднял ставку» и статья «что означает подъём» ценны обе); дедуп
  только ВНУТРИ жанра по source_url.
- `importance` — та же шкала, что Лента (high|medium), нулевая трансляция.
- `tickers` валидируются по таблице companies; `sectors`/`themes` — по
  контролируемому словарю (config/chronicle_themes.json), иначе теги дрейфуют и
  структурный SQL-ретрив ломается за месяц.
- `source_table`/`source_id` — обратная ссылка на строку-первоисточник
  (ревизуемость, пересчёт задним числом).
- `interpretation` — POINT-IN-TIME: как виделось НА ДАТУ записи, не сегодняшняя
  истина (агент обязан это учитывать — см. описание инструмента query_chronicle).
"""
from datetime import date as date_type, datetime, timezone

from sqlalchemy import Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

CHRONICLE_KINDS = ("news", "article", "report", "macro")
CHRONICLE_IMPORTANCE = ("high", "medium")


class ChronicleEntry(Base):
    __tablename__ = "chronicle_entries"
    __table_args__ = (
        UniqueConstraint("source_url", "kind", name="uq_chronicle_source_url_kind"),
        # GIN по JSONB-тегам — быстрый ретрив агентов «по тикеру/сектору/теме».
        Index("ix_chronicle_tickers", "tickers", postgresql_using="gin"),
        Index("ix_chronicle_sectors", "sectors", postgresql_using="gin"),
        Index("ix_chronicle_themes", "themes", postgresql_using="gin"),
        Index("ix_chronicle_published", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # news|article|report|macro
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)  # пересказ с ключевой инфой
    interpretation: Mapped[str | None] = mapped_column(Text)  # «что это значило/значит» (point-in-time)
    key_takeaways: Mapped[list | None] = mapped_column(JSONB)

    # теги для ретрива (контролируемые словари)
    tickers: Mapped[list | None] = mapped_column(JSONB)   # ["SBER", ...] валид. по companies
    sectors: Mapped[list | None] = mapped_column(JSONB)   # ["oil_gas", ...] canonical
    themes: Mapped[list | None] = mapped_column(JSONB)    # ["key_rate", ...] controlled vocab

    importance: Mapped[str | None] = mapped_column(String(16))  # high|medium
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_date: Mapped[date_type | None] = mapped_column(Date)  # на будущее (дата события ≠ публикации)

    source_key: Mapped[str | None] = mapped_column(String(64))   # метка источника (Carnegie/interfax/...)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_table: Mapped[str | None] = mapped_column(String(32))  # market_updates|geo_digest_articles
    source_id: Mapped[int | None] = mapped_column(Integer)

    model_used: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
