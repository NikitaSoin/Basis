"""Модель геополитики (Обозреватель, Направление 7).

GeoBlock — синтез на регион×вкладку (обзор/глубокая аналитика) по geo_methodology.md.
Источники живут в конфиге config/geo_sources.json (не в БД, не в выдаче).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

GEO_REGIONS = ("svo", "middle_east", "atr")
GEO_TABS = ("overview", "deep")


class GeoBlock(Base):
    __tablename__ = "geo_blocks"
    __table_args__ = (UniqueConstraint("region", "tab", name="uq_geo_block_region_tab"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(16), nullable=False)   # svo|middle_east|atr
    tab: Mapped[str] = mapped_column(String(16), nullable=False)      # overview|deep
    title: Mapped[str | None] = mapped_column(String(120))
    status_text: Mapped[str | None] = mapped_column(Text)            # нейтральная фактура
    channels: Mapped[list | None] = mapped_column(JSONB)            # [{channel, effect}]
    scenarios: Mapped[dict | None] = mapped_column(JSONB)          # {base,bull,bear}
    market_impact: Mapped[str | None] = mapped_column(Text)        # «что значит для рынков»
    affected_sectors: Mapped[list | None] = mapped_column(JSONB)
    affected_tickers: Mapped[list | None] = mapped_column(JSONB)
    source_count: Mapped[int | None] = mapped_column()             # сколько статей в синтезе
    model_used: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GeoFrontlineSync(Base):
    """Автосинк линии фронта СВО из живого ArcGIS-фида ISW (Assessed Control of
    Terrain in Ukraine, CC BY) — см. .claude/agents (geo_isw_frontline_sync.py).
    Отдельная таблица, а не правка config/geo_map_svo.json на живом диске: файл
    деплоится из git и переписывается КАЖДЫМ деплоем, крон в проде писал бы в
    файл, который тут же затирается следующим push — поэтому живой слой линии
    хранится в БД и накладывается эндпоинтом `/market/geo-map/svo` поверх
    статического файла (события/область-контекст остаются ручными в JSON)."""
    __tablename__ = "geo_frontline_sync"

    id: Mapped[int] = mapped_column(primary_key=True)
    theater: Mapped[str] = mapped_column(String(16), unique=True)  # пока только "svo"
    frontline_geojson: Mapped[dict | None] = mapped_column(JSONB)
    control_fill_geojson: Mapped[dict | None] = mapped_column(JSONB)  # сам полигон РФ-контроля (не только граница)
    capture_isochrone_geojson: Mapped[dict | None] = mapped_column(JSONB)  # ячейки Вороного «когда взято» — см. geo_svo_capture_isochrone.py
    contested_zone_geojson: Mapped[dict | None] = mapped_column(JSONB)  # «оспаривается» (Рыбарь: штриховка) — НЕ в control_fill
    as_of: Mapped[str | None] = mapped_column(String(32))          # дата данных ISW (lastEditDate)
    source: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | stale | error
    error_note: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


class GeoFrontlineSnapshot(Base):
    """Дневные снапшоты линии фронта — накопление ВПЕРЁД для будущего
    временного ползунка (владелец, 2026-07-24: «посмотреть как менялась
    линия фронта»). У ISW НЕТ штатного API истории по датам (проверено:
    нет timeInfo/archivingInfo/supportsQueryWithHistoricMoment), слой
    Advances хранит только ~2.5 мес роллинга — глубокую историю назад не
    достать через их живой API. Практичный путь — копить свои снапшоты
    с этого дня: глубина растёт естественно (через полгода будет полгода
    истории). Отдельная таблица от geo_frontline_sync (та — только
    «последнее успешное» для быстрой отдачи текущей карты), эта — one row
    per (theater, date), не перезаписывается. Ретеншен/чистка старых
    записей — не реализовано, при годах ежедневных JSONB-строк может
    понадобиться (несколько сотен строк на театр за год, JSONB ~50-100KB
    каждая — не критично на обозримый срок, отслеживать)."""
    __tablename__ = "geo_frontline_snapshot"
    __table_args__ = (UniqueConstraint("theater", "snapshot_date", name="uq_geo_frontline_snapshot_theater_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    theater: Mapped[str] = mapped_column(String(16))
    snapshot_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, дата СНЯТИЯ снапшота (не as_of источника)
    frontline_geojson: Mapped[dict | None] = mapped_column(JSONB)
    control_fill_geojson: Mapped[dict | None] = mapped_column(JSONB)
    as_of: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
