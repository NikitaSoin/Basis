"""Возврат находок в поток: найденный источник становится постоянной лентой.

🔴 Владелец, 2026-08-26: «если нашли какую-то информацию — нужно, чтобы источник, с
которого информация тянулась, так же попал в пул источников, с которых мы парсим».

Как это работает по шагам:
1. Ревизия (`card_revision_scout`) находит факт и запоминает адрес, откуда он взят, —
   `record_find()`. Домен считается один раз: важно не количество ссылок, а сколько раз
   этот сайт реально пригодился.
2. Домен, пригодившийся `_PROMOTE_HITS` раз, проверяется на RSS: у большинства
   отраслевых изданий и корпоративных пресс-центров лента есть, просто мы её не знали.
   Нашлась — источник повышается в `approved` и с этого момента читается ежечасно
   вместе с остальными.
3. Домен без ленты остаётся кандидатом с накопленной статистикой: его видно в
   отладочном эндпоинте, и решение по нему принимает человек.

Почему пул живёт в БД, а не в `config/news_sources.json`: конфигурация едет только с
деплоем, а находки появляются ежедневно. Файл остаётся ядром (13 проверенных лент),
БД — растущей периферией; `news_pipeline.load_config()` склеивает оба списка.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.source_pool import DiscoveredSource

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "BasisNewsBot/1.0 (+https://inbasis.ru)"}
_PROMOTE_HITS = 3          # сколько раз домен должен пригодиться до проверки на ленту

# Домены, которые повышать бессмысленно: агрегаторы, соцсети, поисковики и наши же
# ленты. Они и так в потоке или не являются первоисточником.
_SKIP = re.compile(
    r"(^|\.)(google\.|yandex\.|bing\.|duckduckgo\.|t\.me|telegram\.|vk\.com|"
    r"facebook\.|twitter\.|x\.com|youtube\.|wikipedia\.|inbasis\.ru)", re.I)


def _domain(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return None
    if not host or _SKIP.search(host):
        return None
    return host[4:] if host.startswith("www.") else host


def _ensure_table(db: Session) -> None:
    """Таблица могла не доехать миграцией (у alembic в проекте несколько веток).

    Молчаливое падение здесь стоит дорого: ревизия работает, а находки теряются —
    именно тот класс дефекта, от которого мы уходим. Поэтому создаём при первом
    обращении, если её нет.
    """
    try:
        db.execute(text("SELECT 1 FROM discovered_sources LIMIT 1"))
    except Exception:  # noqa: BLE001
        db.rollback()
        DiscoveredSource.__table__.create(bind=db.get_bind(), checkfirst=True)
        db.commit()


def record_find(db: Session, url: str, *, topic: str | None = None,
                found_for: str | None = None, note: str | None = None) -> str | None:
    """Запомнить, что источник пригодился. Возвращает домен или None (пропуск)."""
    domain = _domain(url or "")
    if not domain:
        return None
    _ensure_table(db)
    row = db.query(DiscoveredSource).filter(DiscoveredSource.domain == domain).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = DiscoveredSource(domain=domain, sample_url=url[:1000], hits=1,
                               topics=topic, found_for=found_for, note=note,
                               first_seen=now, last_seen=now)
        db.add(row)
    else:
        row.hits = (row.hits or 0) + 1
        row.last_seen = now
        row.sample_url = url[:1000]
        for field, value in (("topics", topic), ("found_for", found_for)):
            if not value:
                continue
            have = [x for x in (getattr(row, field) or "").split(",") if x]
            if value not in have:
                setattr(row, field, ",".join(have + [value])[:2000])
    db.commit()
    return domain


def discover_feed(domain: str) -> str | None:
    """Есть ли у домена RSS: сначала <link rel=alternate>, потом типовые адреса."""
    base = f"https://{domain}/"
    try:
        r = httpx.get(base, timeout=20, headers=_HTTP, follow_redirects=True)
        if r.status_code < 400 and "html" in r.headers.get("content-type", ""):
            m = re.search(
                r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>', r.text, re.I)
            if m:
                href = re.search(r'href=["\']([^"\']+)["\']', m.group(0))
                if href:
                    return urljoin(base, href.group(1))
    except Exception:  # noqa: BLE001
        pass
    for path in ("rss", "rss.xml", "feed", "feed/", "news/rss", "export/rss.xml"):
        try:
            u = urljoin(base, path)
            r = httpx.get(u, timeout=15, headers=_HTTP, follow_redirects=True)
            if r.status_code < 400 and "<rss" in r.text[:600].lower():
                return u
        except Exception:  # noqa: BLE001
            continue
    return None


def promote_candidates(db: Session, min_hits: int = _PROMOTE_HITS, limit: int = 5) -> dict:
    """Повысить кандидатов, у которых нашлась лента. Идемпотентно."""
    _ensure_table(db)
    rows = (db.query(DiscoveredSource)
            .filter(DiscoveredSource.status == "candidate",
                    DiscoveredSource.hits >= min_hits)
            .order_by(DiscoveredSource.hits.desc()).limit(limit).all())
    out = {"checked": 0, "promoted": []}
    for row in rows:
        out["checked"] += 1
        feed = discover_feed(row.domain)
        if not feed:
            row.note = ((row.note or "") + " | ленты не нашлось")[:2000]
            continue
        row.feed_url = feed
        row.status = "approved"
        row.promoted_at = datetime.now(timezone.utc)
        out["promoted"].append({"domain": row.domain, "feed": feed, "hits": row.hits})
        logger.info("source_pool: домен %s повышен до постоянной ленты (%s)", row.domain, feed)
    db.commit()
    return out


def extra_feeds(db: Session) -> list[dict]:
    """Одобренные находки в формате лент news_pipeline."""
    try:
        _ensure_table(db)
        rows = (db.query(DiscoveredSource)
                .filter(DiscoveredSource.status == "approved",
                        DiscoveredSource.feed_url.isnot(None)).all())
    except Exception:  # noqa: BLE001
        logger.warning("source_pool: пул источников недоступен", exc_info=True)
        return []
    return [{"source": r.domain, "rubric": "discovered", "url": r.feed_url,
             "enabled": True, "discovered": True} for r in rows]
