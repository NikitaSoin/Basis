"""Процесс-воркер фоновых задач: планировщик, стартовая цепочка, очередь ручных прогонов.

ЗАЧЕМ (инцидент 2026-09-14). Все ~50 кронов и ручные прогоны ИИ-аналитиков жили в
одном интерпретаторе с uvicorn на 1 CPU. Тяжёлая задача забирала GIL и ядро — и сайт
переставал отвечать всем посетителям (не отвечал даже async ping без БД и сети).
Теперь uvicorn (роль web) только отдаёт страницы и ставит задачи в очередь, а этот
процесс (роль worker) исполняет всё остальное. Запускается из start.sh под nice,
в цикле с перезапуском; выключается одной переменной WORKER_SPLIT=0 (тогда веб
снова делает всё сам — откат без рассогласования).

Что здесь:
- тот же планировщик и тот же список задач, что и раньше (register_jobs из main.py) —
  ни одна задача не переписана, изменилось только место исполнения;
- стартовая цепочка (_startup_chain) — как раньше, с отсрочкой тяжёлого;
- опрос очереди job_requests раз в 10 с, задачи из очереди — по одной;
- пульс worker_alive раз в минуту в job_heartbeats (первая строка в
  /api/debug/jobs-health): воркер не поднялся → видно за 3 минуты;
- страж памяти: RSS выше WORKER_MAX_RSS_MB и ничего не бежит → выход, bash-цикл
  поднимает свежий процесс (рост памяти 268 → 621 МБ за 7 часов раньше жил в вебе);
- лог RSS и очереди раз в 5 минут, чтобы через неделю знать, кто течёт.

Запуск: BASIS_ROLE=worker python3 -m app.worker
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time

logger = logging.getLogger("app.worker")

HEARTBEAT_SEC = 60
RSS_LOG_SEC = 300


def rss_mb() -> float | None:
    """RSS текущего процесса, МБ (Linux — /proc, иначе ru_maxrss как приближение)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(v / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)
    except Exception:  # noqa: BLE001
        return None


async def _poll_queue(scheduler) -> None:
    """Очередь ручных прогонов: по одной задаче за раз. Переживает отсутствие таблицы
    (миграции идут в фоне start.sh и могут отстать от старта воркера)."""
    from app.services import job_queue as jq
    loop = asyncio.get_running_loop()
    last_warn = 0.0
    while True:
        try:
            req = await loop.run_in_executor(None, jq.claim_next)
        except Exception as e:  # noqa: BLE001
            now = time.monotonic()
            if now - last_warn > 600:
                logger.warning("очередь задач недоступна (%s: %s) — жду", type(e).__name__, str(e)[:200])
                last_warn = now
            await asyncio.sleep(jq.POLL_INTERVAL_SEC * 3)
            continue
        if req is None:
            await asyncio.sleep(jq.POLL_INTERVAL_SEC)
            continue
        rid, job_id, params = req["id"], req["job_id"], req["params"]
        tag = f"queue:{rid}"
        jq.RUNNING_JOBS.add(tag)
        t0 = time.monotonic()
        logger.info("очередь #%s: старт %s %s", rid, job_id, params or "")
        try:
            if job_id in jq.REGISTRY:
                res = await loop.run_in_executor(None, jq.run_registry_job, job_id, params)
            else:
                job = scheduler.get_job(job_id)
                if job is None:
                    raise KeyError(f"задача «{job_id}» не известна ни реестру, ни планировщику")
                await job.func()          # та же обёрнутая корутина, что и крон (с пульсом)
                res = {"ran": job_id, "note": "результат задачи — в её логе/витрине"}
            await loop.run_in_executor(None, jq.finish, rid, res, None)
            logger.info("очередь #%s: готово %s за %.1f мин", rid, job_id, (time.monotonic() - t0) / 60)
        except Exception as e:  # noqa: BLE001
            logger.exception("очередь #%s: %s упала: %s", rid, job_id, e)
            try:
                await loop.run_in_executor(None, jq.finish, rid, None, f"{type(e).__name__}: {e}")
            except Exception as e2:  # noqa: BLE001
                logger.warning("очередь #%s: не записал ошибку (%s)", rid, e2)
        finally:
            jq.RUNNING_JOBS.discard(tag)


async def _heartbeat_and_guard(stop: asyncio.Event) -> None:
    from app.services import job_queue as jq
    from app.services.job_heartbeat import hb_ok
    loop = asyncio.get_running_loop()
    max_rss = float(os.environ.get("WORKER_MAX_RSS_MB", "900"))
    hard_rss = float(os.environ.get("WORKER_HARD_RSS_MB", "1500"))
    last_rss_log = 0.0
    while not stop.is_set():
        try:
            await loop.run_in_executor(None, hb_ok, "worker_alive")
        except Exception as e:  # noqa: BLE001
            logger.warning("пульс worker_alive не записан: %s", e)
        rss = rss_mb()
        now = time.monotonic()
        if now - last_rss_log >= RSS_LOG_SEC:
            depth = None
            try:
                depth = await loop.run_in_executor(None, jq.queue_depth)
            except Exception:  # noqa: BLE001
                pass
            logger.info("воркер: RSS %s МБ, бежит %s, очередь %s",
                        rss, sorted(jq.RUNNING_JOBS) or "—", depth or "?")
            last_rss_log = now
        if rss is not None and rss > max_rss:
            if jq.RUNNING_JOBS:
                if rss > hard_rss:
                    logger.error("воркер: RSS %s МБ выше аварийного порога %s, но задача бежит (%s) — "
                                 "выйду сразу после её завершения", rss, hard_rss, sorted(jq.RUNNING_JOBS))
            else:
                logger.warning("воркер: RSS %s МБ > %s МБ, задач нет — выхожу, start.sh поднимет свежий процесс",
                               rss, max_rss)
                stop.set()
                return
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SEC)
        except asyncio.TimeoutError:
            pass


async def _amain() -> int:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.main import (register_jobs, _startup_chain, _ensure_log_timestamps,
                          SCHEDULER_TZ, SCHEDULER_JOB_DEFAULTS)
    from app.services import job_queue as jq

    _ensure_log_timestamps()
    logger.info("воркер задач: старт pid=%s, RSS %s МБ, пул БД %s/%s", os.getpid(), rss_mb(),
                os.environ.get("DB_POOL_SIZE", "5"), os.environ.get("DB_MAX_OVERFLOW", "10"))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass

    scheduler = AsyncIOScheduler(timezone=SCHEDULER_TZ, job_defaults=SCHEDULER_JOB_DEFAULTS)
    register_jobs(scheduler)
    scheduler.start()
    logger.info("воркер: планировщик запущен, задач %s", len(scheduler.get_jobs()))

    try:
        n = await loop.run_in_executor(None, jq.recover_orphans)
        if n:
            logger.warning("воркер: %s задач очереди остались running после рестарта → error (не перезапускаю)", n)
    except Exception as e:  # noqa: BLE001
        logger.warning("воркер: очередь ещё недоступна на старте (%s) — миграции догонят", type(e).__name__)

    tasks = [
        asyncio.create_task(_startup_chain(), name="startup_chain"),
        asyncio.create_task(_poll_queue(scheduler), name="queue"),
        asyncio.create_task(_heartbeat_and_guard(stop), name="heartbeat"),
    ]
    await stop.wait()
    logger.info("воркер: остановка (бежит %s)", sorted(jq.RUNNING_JOBS) or "ничего")
    for t in tasks:
        t.cancel()
    try:
        scheduler.shutdown(wait=False)
    except Exception:  # noqa: BLE001
        pass
    return 0


def main() -> int:
    if os.environ.get("BASIS_ROLE", "worker") not in ("worker", "all"):
        print("app.worker: ожидается BASIS_ROLE=worker", file=sys.stderr)
        return 2
    os.environ.setdefault("BASIS_ROLE", "worker")
    logging.basicConfig(level=logging.INFO)
    try:
        return asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
