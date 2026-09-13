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


# ─────────────────────────── память сводок и уроков ───────────────────────────
# 🔴 Владелец (2026-09-13): «десять строк хронологии — не вариант, нужен доступ ко
# ВСЕМ прошлым версиям, чтобы агент мог прочитать, как было несколько месяцев
# назад». Хронология в задании остаётся ориентиром; полный архив — инструментами.

_STATE_KINDS = ("macro", "inst_state", "geo", "inst")


def list_state_versions(db: Session, kind: str, *, date_from: str | None = None,
                        date_to: str | None = None, limit: int = 60) -> dict:
    if kind not in _STATE_KINDS:
        return {"error": f"kind должен быть одним из {_STATE_KINDS}"}
    from app.models.geo import BarometerVersion
    q = (db.query(BarometerVersion)
         .filter(BarometerVersion.kind == kind, BarometerVersion.status == "published"))
    if date_from:
        q = q.filter(BarometerVersion.created_at >= date_from)
    if date_to:
        q = q.filter(BarometerVersion.created_at <= date_to + " 23:59:59")
    rows = q.order_by(BarometerVersion.created_at.desc()).limit(max(1, min(int(limit or 60), 400))).all()
    out = []
    for v in rows:
        p = v.payload or {}
        out.append({"version_id": v.id, "as_of": p.get("as_of"),
                    "created_at": v.created_at.date().isoformat() if v.created_at else None,
                    "source": v.source, "headline": str(p.get("summary") or "")[:220]})
    return {"kind": kind, "versions": out, "hint": "полный текст — read_state_version(kind, version_id)"}


def read_state_version(db: Session, kind: str, version_id: int | None = None,
                       as_of: str | None = None, max_chars: int = 60_000) -> dict:
    if kind not in _STATE_KINDS:
        return {"error": f"kind должен быть одним из {_STATE_KINDS}"}
    from app.models.geo import BarometerVersion
    q = db.query(BarometerVersion).filter(BarometerVersion.kind == kind, BarometerVersion.status == "published")
    if version_id:
        row = q.filter(BarometerVersion.id == int(version_id)).first()
    elif as_of:
        # ближайшая версия НЕ ПОЗЖЕ указанной даты — «как это виделось тогда»
        row = q.filter(BarometerVersion.created_at <= as_of + " 23:59:59").order_by(BarometerVersion.created_at.desc()).first()
    else:
        return {"error": "укажи version_id или as_of (YYYY-MM-DD)"}
    if not row:
        return {"error": "версия не найдена"}
    import json as _json
    text_ = _json.dumps(row.payload or {}, ensure_ascii=False, default=str)
    return {"kind": kind, "version_id": row.id, "as_of": (row.payload or {}).get("as_of"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "gate_notes": row.gate_notes, "payload": text_[:max_chars],
            "truncated": len(text_) > max_chars}


def read_lessons(db: Session, contour: str | None = None, include_settled: bool = False) -> dict:
    """Вся база уроков (не только верхние пятнадцать из задания). Методички этим
    НЕ затрагиваются — уроки живут отдельно, в agent_lessons."""
    from app.services.lessons import snapshot
    snap = snapshot(db, contour)
    items = snap["lessons"] if include_settled else [l for l in snap["lessons"] if l["status"] == "active"]
    return {"contour": contour, "count": len(items), "lessons": items}


FEED_TOOLS_SCHEMA: list[dict] = [
    {"type": "function", "function": {
        "name": "list_state_versions",
        "description": ("Список ВСЕХ прошлых версий сводки (macro — состояние экономики, inst_state — "
                        "институциональный снимок, geo — сводка геополитики, inst — прежняя месячная "
                        "сводка институтов) за любой период: id, дата, заголовок. Чтобы посмотреть, "
                        "как ситуация виделась месяц или полгода назад."),
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(_STATE_KINDS)},
            "date_from": {"type": "string", "description": "YYYY-MM-DD"},
            "date_to": {"type": "string", "description": "YYYY-MM-DD"},
            "limit": {"type": "integer"}}, "required": ["kind"]}}},
    {"type": "function", "function": {
        "name": "read_state_version",
        "description": ("Полный текст одной прошлой версии сводки: по version_id из list_state_versions "
                        "или по дате as_of (берётся ближайшая версия не позже даты — «как виделось тогда»)."),
        "parameters": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": list(_STATE_KINDS)},
            "version_id": {"type": "integer"}, "as_of": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["kind"]}}},
    {"type": "function", "function": {
        "name": "read_lessons",
        "description": ("Вся база уроков прошлых проверок (ошибки, которые уже ловили, и как надо): "
                        "по контуру или целиком, при желании с усвоенными. В задании лежат только "
                        "самые повторяющиеся — здесь все."),
        "parameters": {"type": "object", "properties": {
            "contour": {"type": "string", "enum": ["macro", "inst_state", "geo"]},
            "include_settled": {"type": "boolean"}}}}},
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
    if name == "list_state_versions":
        return list_state_versions(db, args.get("kind", ""), date_from=args.get("date_from"),
                                   date_to=args.get("date_to"), limit=args.get("limit") or 60)
    if name == "read_state_version":
        return read_state_version(db, args.get("kind", ""), version_id=args.get("version_id"), as_of=args.get("as_of"))
    if name == "read_lessons":
        return read_lessons(db, args.get("contour"), bool(args.get("include_settled")))
    if name == "search_feed":
        return search_feed(db, args.get("query", ""), days=args.get("days") or 30,
                           kinds=args.get("kinds"), limit=args.get("limit") or 12)
    if name == "read_feed_item":
        return read_feed_item(db, args.get("kind", ""), args.get("id") or 0)
    return None
