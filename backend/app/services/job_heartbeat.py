"""Heartbeat-мониторинг кронов (фаза 6 «пути к автономной платформе»).

Проблема: молчаливый сбой крона не виден никому (прецедент 2026-07-05 — лента
новостей стояла сутками до ручной диагностики). Решение минимальное и прочное:
каждый джоб отмечает успех/ошибку в таблице job_heartbeats (переживает
рестарты), /api/debug/jobs-health сравнивает возраст последнего успеха с
ОЖИДАЕМЫМ интервалом джоба и выносит вердикт ok / stale / failing / never_ran.

Использование в джобе (2 строки):
    from app.services.job_heartbeat import hb_ok, hb_err
    ... в конце успешного прогона:  hb_ok("news_feed")
    ... в except:                   hb_err("news_feed", e)

Запись — отдельной короткой сессией БД (не смешиваемся с сессией джоба: его
rollback не должен терять heartbeat, а наш сбой не должен ронять джоб — все
исключения здесь глотаются с логом)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Ожидаемые интервалы успешных прогонов (сек) — по расписанию в main.py, с
# запасом ×2.5 на ретраи/паузы. Джоб не в списке → показываем без вердикта.
EXPECTED_INTERVAL_SEC: dict[str, int] = {
    "quotes_update": 30 * 60,            # каждые 5 мин (запас на выходные — нет)
    "news_feed": 3 * 3600,               # каждый час
    "geo_digest": 3 * 3600,              # каждый час
    "macro_ingest": 60 * 3600,           # ежедневно
    "macro_interpretation": 60 * 3600,
    "earnings_digest": 60 * 3600,
    "report_watch": 60 * 3600,
    "geopolitics": 60 * 3600,
    "calendar_refresh": 60 * 3600,
    "agent_pilot": 60 * 3600,
    "history_catchup": 60 * 3600,
}


def _write(job_id: str, ok: bool, err_text: str | None) -> None:
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            if ok:
                db.execute(text("""
                    INSERT INTO job_heartbeats (job_id, last_success, runs_total, updated_at)
                    VALUES (:j, :t, 1, :t)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_success = :t, runs_total = job_heartbeats.runs_total + 1, updated_at = :t
                """), {"j": job_id, "t": now})
            else:
                db.execute(text("""
                    INSERT INTO job_heartbeats (job_id, last_error, last_error_text, errors_total, updated_at)
                    VALUES (:j, :t, :e, 1, :t)
                    ON CONFLICT (job_id) DO UPDATE SET
                        last_error = :t, last_error_text = :e,
                        errors_total = job_heartbeats.errors_total + 1, updated_at = :t
                """), {"j": job_id, "t": now, "e": (err_text or "")[:2000]})
            db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001 — heartbeat не должен ронять джоб
        logger.warning("heartbeat %s: не записан (%s)", job_id, type(e).__name__)


def hb_ok(job_id: str) -> None:
    _write(job_id, True, None)


def hb_err(job_id: str, err: Exception | str) -> None:
    _write(job_id, False, str(err))


def jobs_health() -> dict:
    """Снапшот для /api/debug/jobs-health: вердикт по каждому джобу."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT job_id, last_success, last_error, last_error_text, runs_total, errors_total "
            "FROM job_heartbeats")).fetchall()
    finally:
        db.close()
    now = datetime.now(timezone.utc)
    seen: dict[str, dict] = {}
    for r in rows:
        job_id, last_success, last_error, err_text, runs, errors = r
        expected = EXPECTED_INTERVAL_SEC.get(job_id)
        age = (now - last_success).total_seconds() if last_success else None
        if last_success is None:
            verdict = "failing" if last_error else "never_ran"
        elif expected and age is not None and age > expected:
            verdict = "stale"
        elif last_error and last_success and last_error > last_success:
            verdict = "failing"
        else:
            verdict = "ok"
        seen[job_id] = {
            "verdict": verdict,
            "last_success": last_success.isoformat() if last_success else None,
            "age_min": round(age / 60) if age is not None else None,
            "expected_max_min": round(expected / 60) if expected else None,
            "last_error": last_error.isoformat() if last_error else None,
            "last_error_text": (err_text or None),
            "runs_total": runs, "errors_total": errors,
        }
    # известные по расписанию, но ни разу не отметившиеся — тоже проблема
    for job_id in EXPECTED_INTERVAL_SEC:
        if job_id not in seen:
            seen[job_id] = {"verdict": "no_heartbeat_yet", "note": "джоб ещё ни разу не отчитался (после внедрения мониторинга это норма до первого прогона)"}
    problems = [j for j, v in seen.items() if v["verdict"] in ("stale", "failing", "never_ran")]
    return {"ok": not problems, "problems": problems, "jobs": seen}
