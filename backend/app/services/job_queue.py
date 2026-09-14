"""Очередь ручных запусков фоновых задач + реестр того, что воркер умеет исполнять.

ЗАЧЕМ. С 2026-09-14 фоновые задачи (кроны планировщика и ручные прогоны из
/api/debug/trigger-*) исполняет ОТДЕЛЬНЫЙ процесс app/worker.py, а не uvicorn.
Причина — инцидент того же дня: тяжёлая LLM-цепочка и стартовый залп задач в одном
интерпретаторе с веб-сервером голодом по CPU/GIL вешали ответы всем посетителям
(не отвечал даже async ping). Веб-процесс теперь только ставит задачу в очередь
(строка в job_requests) и отвечает мгновенно; воркер забирает и исполняет.

🔴 ТАБЛИЦА — ЕДИНСТВЕННЫЙ ИСТОЧНИК СТАТУСА ручных прогонов. Раньше статус жил в
памяти веб-процесса (_INST_RUNS в debug.py) и терялся при каждом рестарте —
«проверка, которая проверяет ноль».

Правила исполнения:
- очередь исполняется ПОСЛЕДОВАТЕЛЬНО (одна задача за раз): на одном ядре две
  LLM-цепочки параллельно только мешают друг другу; кроны планировщика при этом
  идут своим чередом;
- задача, которую воркер не завершил (рестарт контейнера посреди прогона), при
  следующем старте помечается error «worker restarted» и НЕ перезапускается
  сама: LLM-задачи не идемпотентны (двойные траты и двойные публикации);
  повторить — руками, той же ручкой;
- в result хранится КОРОТКАЯ сводка (id версии, статус, счётчики, усечённый
  текст), не полезные данные задачи — большие jsonb в горячей таблице нам не нужны.

Реестр REGISTRY — задачи с параметрами (то, что раньше вызывали ручки debug.py
напрямую). Задачи без параметров, известные планировщику (id из register_jobs в
main.py), воркер исполняет через ту же обёрнутую корутину, что и крон — вместе с
пульсом job_heartbeat.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Задачи, которые сейчас исполняются в ЭТОМ процессе (крон или из очереди) — читает
# страж памяти воркера: перезапускаться можно только когда множество пусто.
RUNNING_JOBS: set[str] = set()

POLL_INTERVAL_SEC = 10
RESULT_MAX_CHARS = 6000


def _flag(v: Any, default: bool = False) -> bool:
    """Булев параметр: из query приходит строкой («false» — это False, а не bool("false"))."""
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "да", "on")


# ── реестр параметризованных задач: job_id → fn(db, params) -> результат ────────
def _probe_questions(db, p):
    from app.services.probe_questions import run
    only = p.get("only")
    if isinstance(only, str):
        only = [x.strip() for x in only.split(",") if x.strip()]
    return run(db, only=only or None, mode=str(p.get("mode") or "single"))


def _forecast_review(db, p):
    """Сверка журнала прогнозов с фактом по наступившим срокам (протокол 10.3)."""
    from app.services.forecast_journal import review_due
    return review_due(db, limit=int(p.get("limit") or 40))


def _council(db, p):
    """Совет агентов-методичек на произвольный вопрос (владелец 2026-09-14)."""
    from app.services.lens_council import run_council
    task = str(p.get("task") or "").strip()
    if len(task) < 10:
        return {"error": "нужен параметр task — вопрос совету (не короче 10 знаков)"}
    lenses = p.get("lenses")
    if isinstance(lenses, str):
        lenses = [x.strip() for x in lenses.split(",") if x.strip()]
    out = run_council(db, task, lenses=lenses or None, label=str(p.get("label") or "совет:ручной")[:60],
                      mode=("route" if str(p.get("mode") or "").lower() == "route" else "all"))
    return {"version_id": out.get("version_id"), "answered": out.get("answered"), "failed": out.get("failed"),
            "seconds": out.get("seconds"), "synthesis": bool(out.get("synthesis"))}


def _evening_pipeline(db, p):
    from app.services.evening_pipeline import run
    return run(db)


def _critic(db, p):
    from app.services.critic import run_all
    return run_all(db)


def _cross_review(db, p):
    from app.services.cross_review import run
    row = run(db)
    return {"result": "сводок меньше двух"} if row is None else row


def _consistency(db, p):
    from app.services.consistency_check import run
    row = run(db)
    return {"result": "сводок меньше двух"} if row is None else row


def _inst_state(db, p):
    from app.services.inst_state import rebuild
    row = rebuild(db)
    return {"result": "нет статей и летописи — снимок не трогали"} if row is None else row


def _macro_state(db, p):
    from app.services.macro_state import rebuild
    row = rebuild(db)
    return {"result": "нет индикаторов — состояние не трогали"} if row is None else row


def _barometer_daily(db, p):
    from app.services.barometer_daily import rebuild
    row = rebuild(db)
    return {"result": "лента пуста — барометр не трогали"} if row is None else row


def _geo_profile(db, p):
    from app.services.geo_conflict_profile import rebuild
    row = rebuild(db)
    return {"result": "ни один очаг не собран (лента пуста?)"} if row is None else row


def _sector_scout(db, p):
    from app.services.sector_scout import run_scout
    return run_scout(db, only_code=p.get("code"), dry=_flag(p.get("dry")))


def _tab_rewrite(db, p):
    from app.services.card_rewriter import run_tab_rewrites
    return run_tab_rewrites(db, p["tab"], batch=int(p.get("batch", 1)), only_ticker=p.get("ticker"))


def _markets_rewrite(db, p):
    from app.services.card_rewriter import run_markets_rewrites
    return run_markets_rewrites(db, batch=int(p.get("batch", 2)), only_ticker=p.get("ticker"),
                                use_web=_flag(p.get("use_web"), default=True))


def _card_rewrite(db, p):
    from app.services.card_rewriter import run_macro_rewrites
    return run_macro_rewrites(db, batch=int(p.get("batch", 2)), only_ticker=p.get("ticker"))


def _sector_barometer(db, p):
    from app.services.sector_barometer import rebuild
    return rebuild(db)


def _institutions_domains(db, p):
    from app.services.institutions_domains import rebuild
    return rebuild(db)


def _institutions_profile(db, p):
    from app.services.institutions_profile import rebuild
    return rebuild(db)


def _env_card_interp(db, p):
    from app.services.card_prose_patcher import (
        run_geo_env_interp, run_inst_env_interp, run_macro_env_interp,
    )
    tab = p.get("tab", "both")
    batch = int(p.get("batch", 8))
    ticker = p.get("ticker")
    out: dict[str, Any] = {}
    if tab in ("geo", "both", "all"):
        out["geo"] = run_geo_env_interp(db, batch=batch, only_ticker=ticker)
    if tab in ("institutions", "both", "all"):
        out["institutions"] = run_inst_env_interp(db, batch=batch, only_ticker=ticker)
    if tab in ("macro", "all"):
        out["macro"] = run_macro_env_interp(db, batch=batch, only_ticker=ticker)
    if tab in ("markets", "all"):
        from app.services.card_prose_patcher import run_markets_env_interp
        out["markets"] = run_markets_env_interp(db, batch=batch, only_ticker=ticker)
    if tab in ("governance", "all"):
        from app.services.card_prose_patcher import run_gov_env_interp
        out["governance"] = run_gov_env_interp(db, batch=batch, only_ticker=ticker)
    return out


def _overview_synthesis(db, p):
    from app.services.overview_synthesis import run_batch
    return run_batch(db, batch=max(1, min(int(p.get("batch", 3)), 25)),
                     stale_days=int(p.get("stale_days", 30)), only_ticker=p.get("ticker"))


def _stress_interpretation(db, p):
    from app.services.stress_interpreter import run_batch
    return run_batch(db, only_key=p.get("scenario"), batch=max(1, min(int(p.get("batch", 3)), 10)),
                     stale_days=int(p.get("stale_days", 14)))


REGISTRY: dict[str, Callable[[Any, dict], Any]] = {
    "probe_questions": _probe_questions,
    "council": _council,
    "forecast_review": _forecast_review,
    "evening_pipeline": _evening_pipeline,
    "critic": _critic,
    "cross_review": _cross_review,
    "consistency": _consistency,
    "inst_state": _inst_state,
    "macro_state": _macro_state,
    "barometer_daily": _barometer_daily,
    "geo_profile": _geo_profile,
    "sector_scout": _sector_scout,
    "tab_rewrite": _tab_rewrite,
    "markets_rewrite": _markets_rewrite,
    "card_rewrite": _card_rewrite,
    "sector_barometer": _sector_barometer,
    "institutions_domains": _institutions_domains,
    "institutions_profile": _institutions_profile,
    "env_card_interp": _env_card_interp,
    "overview_synthesis": _overview_synthesis,
    "stress_interpretation": _stress_interpretation,
}


_CRON_IDS: set[str] | None = None


def cron_job_ids() -> set[str]:
    """Идентификаторы задач планировщика — сбором add_job на заглушке, без запуска.
    Кэшируется; при любой ошибке импорта возвращает пустое множество (веб-ручка не
    должна падать из-за этого)."""
    global _CRON_IDS
    if _CRON_IDS is not None:
        return _CRON_IDS
    ids: set[str] = set()

    class _Fake:
        def add_job(self, func, trigger=None, **kw):
            if kw.get("id"):
                ids.add(kw["id"])
    try:
        from app.main import register_jobs
        register_jobs(_Fake())
    except Exception as e:  # noqa: BLE001
        logger.warning("cron_job_ids: не собрал список задач (%s)", e)
    _CRON_IDS = ids
    return ids


def known_job_ids() -> set[str]:
    return set(REGISTRY) | cron_job_ids()


# ── очередь ─────────────────────────────────────────────────────────────────────
def enqueue(job_id: str, params: dict | None = None, requested_by: str | None = None) -> dict:
    """Поставить задачу в очередь. Возвращает {"queued": id, ...} или {"error": ...}."""
    if job_id not in known_job_ids():
        return {"error": f"неизвестная задача «{job_id}»",
                "known": sorted(known_job_ids())}
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rid = db.execute(text("""
            INSERT INTO job_requests (job_id, params, requested_by, status)
            VALUES (:j, CAST(:p AS jsonb), :by, 'queued') RETURNING id
        """), {"j": job_id, "p": json.dumps(params or {}, ensure_ascii=False), "by": requested_by}).scalar()
        db.commit()
    finally:
        db.close()
    return {"queued": rid, "job_id": job_id, "params": params or {},
            "hint": "исполняет процесс-воркер; ход — GET /api/debug/job-requests, "
                    "живость воркера — GET /api/debug/worker"}


def claim_next() -> dict | None:
    """Забрать следующую задачу (FOR UPDATE SKIP LOCKED) и пометить running."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT id, job_id, params FROM job_requests
            WHERE status = 'queued' ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED
        """)).first()
        if row is None:
            db.rollback()
            return None
        db.execute(text("UPDATE job_requests SET status='running', started_at=:t WHERE id=:id"),
                   {"id": row.id, "t": datetime.now(timezone.utc)})
        db.commit()
        params = row.params
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:  # noqa: BLE001
                params = {}
        return {"id": row.id, "job_id": row.job_id, "params": params or {}}
    finally:
        db.close()


def finish(request_id: int, result: Any = None, error: str | None = None) -> None:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE job_requests SET status=:s, finished_at=:t, result=CAST(:r AS jsonb), error=:e
            WHERE id=:id
        """), {"id": request_id, "s": "error" if error else "done", "t": datetime.now(timezone.utc),
               "r": json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
               "e": (error or None) and error[:4000]})
        db.commit()
    finally:
        db.close()


def recover_orphans() -> int:
    """Задачи, оставшиеся running после рестарта воркера → error, без перезапуска."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        n = db.execute(text("""
            UPDATE job_requests SET status='error', finished_at=:t,
                   error='worker restarted — задача не завершена; повторить вручную'
            WHERE status='running'
        """), {"t": datetime.now(timezone.utc)}).rowcount
        db.commit()
        return int(n or 0)
    finally:
        db.close()


def list_recent(limit: int = 30, job_id: str | None = None) -> list[dict]:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        cond = "WHERE job_id = :j" if job_id else ""
        rows = db.execute(text(f"""
            SELECT id, job_id, params, status, requested_by, requested_at, started_at, finished_at, result, error
            FROM job_requests {cond} ORDER BY id DESC LIMIT :n
        """), {"n": limit, "j": job_id}).mappings().all()
    finally:
        db.close()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("requested_at", "started_at", "finished_at"):
            if d.get(k) is not None:
                d[k] = d[k].isoformat()
        if d.get("started_at") and d.get("finished_at"):
            d["minutes"] = round((r["finished_at"] - r["started_at"]).total_seconds() / 60, 1)
        out.append(d)
    return out


def queue_depth() -> dict:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT status, count(*) FROM job_requests WHERE status IN ('queued','running') GROUP BY status"
        )).all()
    finally:
        db.close()
    d = {"queued": 0, "running": 0}
    for s, n in rows:
        d[s] = int(n)
    return d


# ── исполнение (в воркере) ──────────────────────────────────────────────────────
def summarize(res: Any) -> Any:
    """Короткая сводка результата для хранения в таблице."""
    if res is None:
        return None
    if isinstance(res, (dict, list, str, int, float, bool)):
        s = json.dumps(res, ensure_ascii=False, default=str)
        if len(s) <= RESULT_MAX_CHARS:
            return res
        return {"truncated": s[:RESULT_MAX_CHARS]}
    # ORM-строка версии: id / status / заметки гейта — то, что раньше отдавали ручки
    if hasattr(res, "id") or hasattr(res, "status"):
        d = {"id": getattr(res, "id", None), "status": getattr(res, "status", None)}
        notes = getattr(res, "gate_notes", None)
        if notes:
            d["gate_notes"] = list(notes)[:10]
        payload = getattr(res, "payload", None)
        if isinstance(payload, dict) and payload.get("as_of"):
            d["as_of"] = payload.get("as_of")
        return d
    return str(res)[:1000]


def run_registry_job(job_id: str, params: dict) -> Any:
    """Синхронно исполнить задачу реестра со своей сессией БД; пульс — только для
    задач, известных планировщику (ручной tab_rewrite не должен красить jobs-health)."""
    from app.db.session import SessionLocal
    from app.services.job_heartbeat import hb_ok, hb_err
    fn = REGISTRY[job_id]
    hb = job_id in cron_job_ids()
    db = SessionLocal()
    try:
        res = summarize(fn(db, params or {}))
        if hb:
            hb_ok(job_id)
        return res
    except Exception as e:
        if hb:
            hb_err(job_id, e)
        raise
    finally:
        db.close()
