"""Сервис аналитической летописи (chronicle) — постоянная память платформы.

Пишет в неё оба конвейера Обозревателя:
  - news_pipeline → важные новости (kind=news): все поля (importance/тикеры/
    секторы/summary/impact) уже извлечены — чистая запись, нулевая LLM-стоимость.
  - geo_digest   → аналитические статьи (kind=article): темы/importance извлекаются
    в дайджест-вызове, тикеры — переиспользованием map_tickers поверх summary.

Читают её агенты через query_chronicle / get_chronicle_entry (agent_tools.py).

Инварианты (советник 2026-07-22):
  - дедуп ТОЛЬКО внутри жанра по (source_url, kind);
  - теги валидируются: tickers по companies, sectors/themes по контролируемому
    словарю config/chronicle_themes.json (свободные теги дрейфуют → ретрив ломается);
  - запись летописи — в ТОМ ЖЕ commit, что и строка-первоисточник (caller коммитит).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, time as dtime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chronicle import CHRONICLE_IMPORTANCE, ChronicleEntry
from app.models.company import Company

logger = logging.getLogger(__name__)

_THEMES_PATH = Path(__file__).parent.parent.parent / "config" / "chronicle_themes.json"


@lru_cache(maxsize=1)
def _vocab() -> tuple[frozenset, frozenset]:
    """Контролируемые словари тем и секторов (ключи chronicle_themes.json)."""
    try:
        d = json.loads(_THEMES_PATH.read_text(encoding="utf-8"))
        return (frozenset(d.get("themes", {})), frozenset(d.get("canonical_sectors", {})))
    except Exception as e:  # noqa: BLE001
        logger.warning("chronicle: не прочитан словарь тем: %s", type(e).__name__)
        return (frozenset(), frozenset())


def theme_keys() -> list[str]:
    return sorted(_vocab()[0])


def sector_keys() -> list[str]:
    return sorted(_vocab()[1])


def _valid_tickers(db: Session) -> set[str]:
    return {t for (t,) in db.execute(select(Company.ticker)).all()}


def _clean_tags(tickers, sectors, themes, valid_tickers: set[str]) -> tuple[list, list, list]:
    """Отбрасываем невалидные теги (как map_tickers отбрасывает чужие тикеры)."""
    themes_ok, sectors_ok = _vocab()
    tk = [t.upper() for t in (tickers or []) if isinstance(t, str) and t.upper() in valid_tickers]
    sc = [s for s in (sectors or []) if isinstance(s, str) and s in sectors_ok]
    th = [t for t in (themes or []) if isinstance(t, str) and t in themes_ok]
    # уникализируем, сохраняя порядок появления
    return (list(dict.fromkeys(tk)), list(dict.fromkeys(sc)), list(dict.fromkeys(th)))


def _exists(db: Session, source_url: str, kind: str) -> bool:
    return db.query(ChronicleEntry.id).filter_by(source_url=source_url, kind=kind).first() is not None


def record(db: Session, *, kind: str, title: str, summary: str, source_url: str,
           published_at, interpretation: str | None = None, key_takeaways=None,
           tickers=None, sectors=None, themes=None, importance: str | None = None,
           event_date=None, source_key: str | None = None,
           source_table: str | None = None, source_id: int | None = None,
           model_used: str | None = None) -> ChronicleEntry | None:
    """Добавляет запись в летопись (db.add, БЕЗ commit — коммитит caller, чтобы
    запись была в одной транзакции с первоисточником). Дедуп внутри жанра.
    Возвращает объект или None (если дубль/пусто)."""
    if not source_url or not summary or not title:
        return None
    if _exists(db, source_url, kind):
        return None
    tk, sc, th = _clean_tags(tickers, sectors, themes, _valid_tickers(db))
    imp = importance if importance in CHRONICLE_IMPORTANCE else None
    entry = ChronicleEntry(
        kind=kind, title=title[:500], summary=summary,
        interpretation=(interpretation or None), key_takeaways=key_takeaways or None,
        tickers=tk or None, sectors=sc or None, themes=th or None,
        importance=imp, published_at=published_at, event_date=event_date,
        source_key=source_key, source_url=source_url[:1000],
        source_table=source_table, source_id=source_id, model_used=model_used,
    )
    db.add(entry)
    return entry


# ─────────────────────── ingestion из Ленты (news) ───────────────────────

def ingest_market_update(db: Session, mu) -> ChronicleEntry | None:
    """Промоут строки market_updates в летопись. Гейт: importance=high ИЛИ
    medium с привязкой к тикерам (иначе шум). Поля уже готовы — нулевая LLM-стоимость."""
    imp = (mu.importance or "").lower()
    tickers = mu.affected_tickers or []
    if imp not in ("high", "medium"):
        return None
    if imp == "medium" and not tickers:
        return None
    return record(
        db, kind="news",
        title=mu.title, summary=(mu.summary or mu.content or mu.title),
        interpretation=mu.impact_comment, tickers=tickers, sectors=mu.affected_sectors,
        importance=imp, published_at=mu.published_at, source_key=mu.source,
        source_url=mu.source_url or f"mu:{mu.id}",
        source_table="market_updates", source_id=mu.id, model_used=mu.model_used,
    )


# ─────────────────────── ingestion из дайджеста (article) ───────────────────────

_EXTRACT_SYS = (
    "Ты размечаешь аналитические статьи для инвестиционной ЛЕТОПИСИ платформы Basis "
    "(рынок РФ). Для КАЖДОЙ статьи (заголовок + пересказ) верни теги для быстрого "
    "поиска агентами:\n"
    "1. tickers — тикеры компаний из СПРАВОЧНИКА (ниже), которых статья касается "
    "ПРЯМО и по существу. Нет уверенной привязки — пустой список, НЕ выдумывай.\n"
    "2. sectors — секторы ТОЛЬКО из списка допустимых (ключи), затронутые статьёй.\n"
    "3. themes — темы ТОЛЬКО из списка допустимых (ключи), раскрытые в статье (1-4).\n"
    "4. importance — \"high\" (крупный сдвиг рыночного фона/сектора) или \"medium\".\n"
    'Формат строго JSON {"results":[{"i":<индекс>,"tickers":["SBER"],"sectors":["oil_gas"],'
    '"themes":["key_rate"],"importance":"high"|"medium"}]}. Никакого текста вне JSON. '
    "Ровно один элемент на каждую входную статью."
)


def _extract_article_tags(db: Session, articles: list[dict]) -> dict[int, dict]:
    """Один батч-вызов LLM: теги (тикеры/секторы/темы/важность) для статей.
    articles: [{i, title, summary}]. Валидация — как map_tickers (чужое отбрасываем)."""
    from app.services.llm import complete, LLMError
    ref = [{"ticker": c.ticker, "name": c.name, "sector": c.sector or ""}
           for c in db.query(Company).order_by(Company.ticker).all()]
    payload = {"allowed_sectors": sector_keys(), "allowed_themes": theme_keys(),
               "directory": ref, "articles": articles}
    try:
        res = complete(_EXTRACT_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=4000, temperature=0.2)
    except LLMError as e:
        logger.warning("chronicle: извлечение тегов статей не удалось (%s)", e)
        return {}
    out: dict[int, dict] = {}
    for it in (res.get("results") or []) if isinstance(res, dict) else []:
        i = it.get("i")
        if isinstance(i, int):
            out[i] = it
    return out


def ingest_geo_articles(db: Session, rows: list) -> int:
    """Промоут свежих GeoDigestArticle в летопись (kind=article). Гейт мягкий —
    статьи уже прошли фильтр target≠null в дайджесте (аналитика ценна). Теги —
    одним батч-вызовом. Отдельный commit (не роняем дайджест)."""
    rows = [r for r in rows if r is not None]
    if not rows:
        return 0
    articles = [{"i": i, "title": r.title, "summary": (r.summary or "")[:1500]}
                for i, r in enumerate(rows)]
    tags = _extract_article_tags(db, articles)
    n = 0
    try:
        for i, r in enumerate(rows):
            t = tags.get(i, {})
            # якорь ленты времени — дата ПУБЛИКАЦИИ статьи (Date→datetime UTC полдень),
            # а не момент нашего сохранения; если даты нет — created_at (когда увидели).
            published_at = (datetime.combine(r.published_at, dtime(12, 0), tzinfo=timezone.utc)
                            if r.published_at else r.created_at)
            entry = record(
                db, kind="article", title=r.title, summary=r.summary,
                interpretation=r.investor_relevance, key_takeaways=r.key_takeaways,
                tickers=t.get("tickers"), sectors=t.get("sectors"), themes=t.get("themes"),
                importance=t.get("importance"), published_at=published_at,
                event_date=r.published_at, source_key=r.source_key, source_url=r.source_url,
                source_table="geo_digest_articles", source_id=r.id, model_used=r.model_used,
            )
            if entry is not None:
                n += 1
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("Digest→chronicle: пропущено из-за %s (подхватит бэкфилл)", type(e).__name__)
    return n


# ─────────────────────── бэкфилл / идемпотентный catch-up ───────────────────────

def backfill_news(db: Session, max_rows: int = 6000) -> dict:
    """Промоут накопленных важных новостей market_updates в летопись (нулевая
    LLM-стоимость). Идемпотентно — record() дедупит по (source_url, kind).
    Свежее вперёд. Ограничение max_rows — чтобы не жечь память на разовом прогоне."""
    from app.models.market import MarketUpdate
    q = (db.query(MarketUpdate)
         .filter(MarketUpdate.status == "published",
                 MarketUpdate.importance.in_(("high", "medium")))
         .order_by(MarketUpdate.published_at.desc())
         .limit(max_rows))
    scanned = made = 0
    for mu in q.all():
        scanned += 1
        if ingest_market_update(db, mu) is not None:
            made += 1
            if made % 300 == 0:
                db.commit()
    db.commit()
    return {"scanned_news": scanned, "chronicled_news": made}


def backfill_articles(db: Session, max_rows: int = 400, batch: int = 15) -> dict:
    """Промоут статей geo_digest_articles в летопись. LLM-теги — только по
    ещё-не-зачроникленным (не жжём токены повторно)."""
    from app.models.geo_digest import GeoDigestArticle
    existing = {u for (u,) in db.query(ChronicleEntry.source_url).filter_by(kind="article").all()}
    rows = [r for r in (db.query(GeoDigestArticle)
                        .order_by(GeoDigestArticle.created_at.desc()).limit(max_rows).all())
            if r.source_url not in existing]
    made = 0
    for i in range(0, len(rows), batch):
        made += ingest_geo_articles(db, rows[i:i + batch])
    return {"candidates_articles": len(rows), "chronicled_articles": made}


def backfill(db: Session) -> dict:
    """Разовый/периодический полный бэкфилл летописи из обоих источников."""
    res = {}
    res.update(backfill_news(db))
    res.update(backfill_articles(db))
    logger.info("chronicle backfill: %s", res)
    return res
