"""Поиск по ВСЕМУ входящему потоку платформы — инструмент для любого агента.

🔴 ЗАЧЕМ (владелец, 2026-09-13): «у агентов есть возможность смотреть и
учитывать весь входной информационный поток? Если нет — надо сделать».
Не было. За 14 дней на платформу приходит ~1000 новостей рынка из 9 источников,
~230 статей тематического дайджеста из 17, ~430 записей летописи, отчёты
компаний, записки ЦБ/ЦМАКП — а каждый аналитик получал в задании ЗАРАНЕЕ
вырезанный кусок: макро — ключевые факты и записки, институты — 40 статей со
своей темой, геополитика — статьи по своему очагу. Спросить «а что было по
X?» за пределами своего куска агент не мог; веб-поиск у разведчика ходит
наружу, а не в наш же архив.

Два инструмента:
  search_feed(query, days, kinds, limit) — полнотекстовый поиск (русская
      морфология Postgres) по пяти таблицам потока сразу, компактные строки;
  read_feed_item(kind, id) — полный текст одной записи.

Ничего не пересказывает и не ранжирует «по важности» вместо агента — отдаёт
что нашлось, с датой и источником, чтобы агент сослался на конкретную запись.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# kind → (таблица, заголовок, краткий текст, полный текст, дата, источник, url)
_KINDS: dict[str, tuple[str, str, str, str, str, str, str]] = {
    "news":      ("market_updates",      "title",    "summary",   "content",   "published_at", "source",     "source_url"),
    "digest":    ("geo_digest_articles", "title",    "summary",   "full_text", "published_at", "source_key", "source_url"),
    "chronicle": ("chronicle_entries",   "title",    "summary",   "interpretation", "published_at", "source_key", "source_url"),
    "macro_doc": ("macro_analytics_docs","title",    "summary",   "full_text", "published_at", "source",     "source_url"),
    "earnings":  ("earnings_digests",    "headline", "one_liner", "summary",   "created_at",   "'отчёт'",    "NULL"),
}
_MAX_LIMIT = 30


def search_feed(db: Session, query: str, *, days: int = 30, kinds: list[str] | None = None,
                limit: int = 12) -> dict:
    q = (query or "").strip()
    if len(q) < 3:
        return {"error": "запрос короче трёх символов"}
    days = max(1, min(int(days or 30), 730))
    limit = max(1, min(int(limit or 12), _MAX_LIMIT))
    since = date.today() - timedelta(days=days)
    wanted = [k for k in (kinds or list(_KINDS)) if k in _KINDS] or list(_KINDS)

    parts = []
    for k in wanted:
        tbl, title, short, full, dt, src, url = _KINDS[k]
        parts.append(f"""
            SELECT '{k}' AS kind, id, {title} AS title, LEFT(COALESCE({short}, ''), 400) AS summary,
                   {dt}::date AS d, {src} AS source, {url} AS url,
                   ts_rank(to_tsvector('russian', COALESCE({title},'') || ' ' || COALESCE({short},'')
                           || ' ' || LEFT(COALESCE({full},''), 4000)), plainto_tsquery('russian', :q)) AS rank
            FROM {tbl}
            WHERE {dt} >= :since
              AND to_tsvector('russian', COALESCE({title},'') || ' ' || COALESCE({short},'')
                  || ' ' || LEFT(COALESCE({full},''), 4000)) @@ plainto_tsquery('russian', :q)""")
    sql = " UNION ALL ".join(parts) + " ORDER BY rank DESC, d DESC LIMIT :lim"
    mode = "все слова"
    try:
        rows = db.execute(text(sql), {"q": q, "since": since, "lim": limit}).fetchall()
        # 🔴 plainto_tsquery требует ВСЕ слова сразу: «назначения ФСО указ» находил
        # ноль, хотя каждое слово по отдельности есть. Второй заход — любое из
        # слов, с ранжированием по совпадениям; агент видит, какой режим сработал.
        if not rows:
            or_sql = sql.replace("plainto_tsquery('russian', :q)", "to_tsquery('russian', :qor)")
            words = [w for w in q.replace("'", " ").split() if len(w) > 2]
            qor = " | ".join(words) if words else q
            rows = db.execute(text(or_sql), {"qor": qor, "since": since, "lim": limit}).fetchall()
            mode = "любое слово"
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("search_feed: %s", e)
        return {"error": f"поиск не удался: {type(e).__name__}"}
    return {"query": q, "days": days, "found": len(rows), "match": mode,
            "items": [{"kind": r[0], "id": r[1], "title": r[2], "summary": r[3],
                       "date": r[4].isoformat() if r[4] else None, "source": r[5], "url": r[6]}
                      for r in rows],
            "hint": "полный текст — read_feed_item(kind, id)" if rows else
                    "ничего не нашлось: расширь окно days, упрости запрос или проверь другой kind"}


def read_feed_item(db: Session, kind: str, item_id: int) -> dict:
    if kind not in _KINDS:
        return {"error": f"kind должен быть одним из {sorted(_KINDS)}"}
    tbl, title, short, full, dt, src, url = _KINDS[kind]
    try:
        r = db.execute(text(f"SELECT {title}, {short}, {full}, {dt}::date, {src}, {url} FROM {tbl} WHERE id = :i"),
                       {"i": int(item_id)}).first()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"error": f"чтение не удалось: {type(e).__name__}"}
    if not r:
        return {"error": "запись не найдена"}
    return {"kind": kind, "id": int(item_id), "title": r[0], "summary": r[1],
            "text": (r[2] or "")[:20_000], "date": r[3].isoformat() if r[3] else None,
            "source": r[4], "url": r[5]}


FEED_TOOLS_SCHEMA: list[dict] = [
    {"type": "function", "function": {
        "name": "search_feed",
        "description": ("Поиск по ВСЕМУ входящему потоку платформы за период: новости рынка (news), "
                        "тематический дайджест по геополитике/институтам/макро/бизнесу (digest), "
                        "летопись важных событий с интерпретацией (chronicle), записки ЦБ и "
                        "аналитических центров (macro_doc), разборы отчётов компаний (earnings). "
                        "Русская морфология. Возвращает компактные строки с датой и источником — "
                        "ссылайся на них. Полный текст — read_feed_item."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "что искать, 2–6 слов по-русски"},
            "days": {"type": "integer", "description": "окно в днях, по умолчанию 30"},
            "kinds": {"type": "array", "items": {"type": "string",
                      "enum": ["news", "digest", "chronicle", "macro_doc", "earnings"]},
                      "description": "где искать; пусто — везде"},
            "limit": {"type": "integer", "description": "сколько строк, до 30"}},
            "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_feed_item",
        "description": "Полный текст одной записи потока по kind и id из search_feed.",
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["news", "digest", "chronicle", "macro_doc", "earnings"]},
            "id": {"type": "integer"}},
            "required": ["kind", "id"]}}},
]


def execute(db: Session, name: str, args: dict):
    """Исполнитель для analyst.run(extra_executor=...) и разведчика. None — не наш инструмент."""
    if name == "search_feed":
        return search_feed(db, args.get("query", ""), days=args.get("days") or 30,
                           kinds=args.get("kinds"), limit=args.get("limit") or 12)
    if name == "read_feed_item":
        return read_feed_item(db, args.get("kind", ""), args.get("id") or 0)
    return None
