"""Сторож цикла событий: видит, КОГДА и ПОЧЕМУ процесс перестал отвечать.

🔴 ЗАЧЕМ (инцидент 2026-09-14): 14:51–14:58 МСК не отвечал даже чисто асинхронный
`/api/debug/ping`, при этом процесс жил и писал в лог (21 попытка соединения с
DeepSeek). В логе Timeweb нет времени, тела ошибок не пишутся, метрик нет — причину
(ядро занято потоком под GIL / память / сеть контейнера / пул БД) было не отличить.
Советник (Fable, 2026-09-14): нужен watchdog-ПОТОК, не задача asyncio — задача сама
встанет вместе с циклом.

Как работает: задача в цикле событий раз в секунду обновляет отметку времени; отдельный
daemon-поток раз в секунду сравнивает. Отставание больше порога — «зависание цикла»:
поток собирает снимок (лаг, RSS, число потоков, loadavg, троттлинг cgroup, OOM-события,
сокеты, канарейка DNS/TCP) и стек всех потоков (faulthandler → stderr) — по стеку
главного потока видно, где он стоит: selectors.select = цикл жив (виновата сеть);
psycopg2/_write = ждёт БД; всё остальное = ядро отдано другому потоку под GIL.
События копятся в кольце (последние 50) и отдаются `/api/debug/watchdog` — без логов.

Всё через try/except: на macOS нет /proc и cgroup, сторож обязан молча отдавать None.
"""
from __future__ import annotations

import asyncio
import faulthandler
import logging
import os
import socket
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

LAG_THRESHOLD_SEC = float(os.environ.get("WATCHDOG_LAG_SEC", "5"))
_DUMP_COOLDOWN_SEC = 60.0
_RING: deque[dict] = deque(maxlen=50)
_STATE = {"last_tick": None, "started": None, "thread": None, "task": None, "events": 0}


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return None


def _kv(text: str | None, key: str) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        if line.startswith(key):
            return line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
    return None


def _canary(host: str | None) -> dict:
    out: dict = {}
    t0 = time.monotonic()
    if host:
        try:
            socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
            out["dns_ms"] = round((time.monotonic() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            out["dns_error"] = f"{type(e).__name__}: {getattr(e, 'errno', '') or str(e)[:80]}"
    t1 = time.monotonic()
    try:
        s = socket.create_connection(("1.1.1.1", 443), timeout=2.0)
        s.close()
        out["tcp_1111_ms"] = round((time.monotonic() - t1) * 1000)
    except Exception as e:  # noqa: BLE001
        out["tcp_1111_error"] = f"{type(e).__name__}: {getattr(e, 'errno', '') or str(e)[:80]}"
    return out


def collect_snapshot(lag: float | None = None, canary_host: str | None = None) -> dict:
    """Снимок состояния процесса и контейнера. Любое поле может быть None (macOS/нет cgroup)."""
    status = _read("/proc/self/status")
    snap: dict = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lag_sec": round(lag, 2) if lag is not None else None,
        "rss": _kv(status, "VmRSS:"), "threads": _kv(status, "Threads:"),
        "loadavg": (_read("/proc/loadavg") or "").strip() or None,
        "cpu_stat": {k: v for k, v in
                     (line.split(None, 1) for line in (_read("/sys/fs/cgroup/cpu.stat") or "").splitlines() if " " in line)
                     if k in ("nr_throttled", "throttled_usec", "usage_usec")} or None,
        "memory_current": (_read("/sys/fs/cgroup/memory.current") or "").strip() or None,
        "memory_max": (_read("/sys/fs/cgroup/memory.max") or "").strip() or None,
        "oom_kill": _kv(_read("/sys/fs/cgroup/memory.events"), "oom_kill"),
        "sockstat": ((_read("/proc/net/sockstat") or "").replace("\n", " | ").strip() or None),
        "python_threads": threading.active_count(),
    }
    try:
        snap["canary"] = _canary(canary_host)
    except Exception as e:  # noqa: BLE001
        snap["canary"] = {"error": type(e).__name__}
    return snap


def _relay_host() -> str | None:
    raw = (os.environ.get("DEEPSEEK_BASE_URL") or "").strip()
    if not raw:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(raw).hostname
    except Exception:  # noqa: BLE001
        return None


def _watch():
    last_dump = 0.0
    host = _relay_host()
    while True:
        time.sleep(1.0)
        tick = _STATE["last_tick"]
        if tick is None:
            continue
        lag = time.monotonic() - tick
        if lag < LAG_THRESHOLD_SEC:
            continue
        now = time.monotonic()
        if now - last_dump < _DUMP_COOLDOWN_SEC:
            continue
        last_dump = now
        try:
            snap = collect_snapshot(lag, host)
            _RING.append(snap)
            _STATE["events"] += 1
            logger.warning("WATCHDOG: цикл событий не отвечает %.1f с — rss=%s threads=%s load=%s throttle=%s mem=%s/%s oom=%s canary=%s",
                           lag, snap.get("rss"), snap.get("threads"), snap.get("loadavg"),
                           (snap.get("cpu_stat") or {}).get("nr_throttled"), snap.get("memory_current"),
                           snap.get("memory_max"), snap.get("oom_kill"), snap.get("canary"))
            # стек всех потоков → stderr (Timeweb собирает stderr вместе с stdout)
            try:
                sys.stderr.write(f"WATCHDOG traceback dump, lag {lag:.1f}s\n")
                faulthandler.dump_traceback(all_threads=True)
                sys.stderr.flush()
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            logger.warning("WATCHDOG: снимок не собран (%s)", type(e).__name__)


async def _ticker():
    while True:
        _STATE["last_tick"] = time.monotonic()
        await asyncio.sleep(1.0)


def start() -> None:
    """Запустить сторож из работающего цикла событий. Повторный вызов — no-op."""
    if _STATE["thread"] is not None:
        return
    try:
        loop = asyncio.get_running_loop()
        _STATE["task"] = loop.create_task(_ticker())
        t = threading.Thread(target=_watch, name="loop-watchdog", daemon=True)
        t.start()
        _STATE["thread"] = t
        _STATE["started"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        logger.info("Сторож цикла событий запущен (порог %.0f с)", LAG_THRESHOLD_SEC)
    except Exception as e:  # noqa: BLE001
        logger.warning("Сторож цикла событий не запущен: %s", e)


def status() -> dict:
    tick = _STATE["last_tick"]
    return {"started": _STATE["started"], "threshold_sec": LAG_THRESHOLD_SEC,
            "current_lag_sec": round(time.monotonic() - tick, 2) if tick else None,
            "events": _STATE["events"], "last_events": list(_RING)[-10:],
            "now": collect_snapshot(None, _relay_host())}
