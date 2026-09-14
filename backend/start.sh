#!/usr/bin/env bash
# Старт backend.
# Принципы устойчивости (чтобы не уходить в крэш-луп при недоступной/медленной БД):
#  1) uvicorn поднимается СРАЗУ и отвечает на /api/health всегда, даже если БД
#     недоступна — операции с БД НЕ блокируют запуск сервера.
#  2) Миграции Alembic выполняются в ФОНЕ с повторными попытками; их неуспех
#     НЕ роняет контейнер (нет exit с ошибкой → нет перезапуска в петлю).
#  3) Импорт 262 профилей вынесен в ./import_data.sh — разовая РУЧНАЯ операция,
#     НЕ выполняется на каждом старте.
#  4) 🔴 ДВА ПРОЦЕССА (с 2026-09-14): uvicorn отдаёт страницы (роль web), а ВСЕ фоновые
#     задачи — планировщик, стартовая цепочка, очередь ручных прогонов — исполняет
#     отдельный процесс `python3 -m app.worker` (роль worker) под nice. Причина —
#     инцидент 2026-09-14: LLM-прогон и стартовый залп задач в одном интерпретаторе
#     с сайтом на 1 CPU голодом по GIL вешали ответы всем посетителям.
#     Расщепление задаёт ОДНА переменная WORKER_SPLIT (по умолчанию 1). WORKER_SPLIT=0
#     → воркер не запускается, uvicorn получает роль all и делает всё сам, как раньше;
#     это откат без риска получить два планировщика (советник 2026-09-14).

set -u

# Сколько раз пробовать применить миграции и пауза между попытками (сек).
# Можно переопределить переменными окружения.
ATTEMPTS="${MIGRATE_ATTEMPTS:-30}"
DELAY="${MIGRATE_RETRY_DELAY:-5}"

run_migrations() {
  for i in $(seq 1 "$ATTEMPTS"); do
    if alembic upgrade head; then
      echo "[start] alembic upgrade head: успешно (попытка $i)"
      return 0
    fi
    echo "[start] alembic upgrade head не удался (попытка $i/$ATTEMPTS) — БД недоступна? повтор через ${DELAY}s"
    sleep "$DELAY"
  done
  echo "[start] ВНИМАНИЕ: миграции не применились за $ATTEMPTS попыток. Сервер продолжает работать (healthcheck отвечает). Применить миграции вручную можно через ./import_data.sh (он сначала делает alembic upgrade head)."
  return 0
}

# Миграции — в фоне, чтобы НЕ блокировать старт сервера операциями с БД.
run_migrations &

# refresh_financials (детектор устаревших данных → _refresh_queue.json) УБРАН со старта:
# на 1-CPU инстансе он сканировал 264 компании и конкурировал за ядро во время старта,
# что мешало контейнеру быстро стать «здоровым». Для отдачи сайта он не нужен (это
# детектор для AI-субагентов, не рантайм). Запускать вручную при необходимости.

# ── Процесс-воркер фоновых задач ──────────────────────────────────────────────
# Пул БД делим по ролям: у managed-Postgres max_connections = 25. Веб 5+5, воркер 4+6
# → не больше 20 соединений на двоих (+ миграции/скрипты).
WORKER_SPLIT="${WORKER_SPLIT:-1}"
if [ "$WORKER_SPLIT" = "1" ]; then
  export BASIS_ROLE=web
  export DB_POOL_SIZE="${WEB_DB_POOL_SIZE:-5}"
  export DB_MAX_OVERFLOW="${WEB_DB_MAX_OVERFLOW:-5}"
  (
    export BASIS_ROLE=worker
    # Воркер держит до 12 сетевых задач разом (WORKER_THREADS), у каждой своя сессия БД:
    # 3+4 не хватало в вечернюю сборку → 4+6 (с вебом 5+5 итого ≤ 20 из 25).
    export DB_POOL_SIZE="${WORKER_DB_POOL_SIZE:-4}"
    export DB_MAX_OVERFLOW="${WORKER_DB_MAX_OVERFLOW:-6}"
    PY="$(command -v python3 || command -v python || echo python3)"
    # nice может отсутствовать в минимальном образе — тогда запускаем без него, но запускаем.
    if command -v nice >/dev/null 2>&1; then NICE="nice -n 10"; else NICE=""; fi
    # Цикл перезапуска: воркер сам выходит при росте памяти (страж RSS) и после
    # аварии; пауза — чтобы падение на импорте не крутилось без остановки.
    while true; do
      echo "[start] воркер задач: запуск ($NICE $PY -m app.worker)"
      $NICE "$PY" -m app.worker
      echo "[start] воркер задач завершился (код $?) — перезапуск через ${WORKER_RESTART_DELAY:-15} с"
      sleep "${WORKER_RESTART_DELAY:-15}"
    done
  ) &
  echo "[start] роль web: планировщик и задачи — в процессе-воркере (WORKER_SPLIT=1)"
else
  export BASIS_ROLE=all
  echo "[start] WORKER_SPLIT=0: воркер не запускается, uvicorn исполняет задачи сам (роль all)"
fi

# Веб-сервер — на переднем плане. exec → uvicorn становится PID 1 и корректно
# получает сигналы остановки от платформы.
# --proxy-headers + --forwarded-allow-ips="*": корректная работа за реверс-прокси Timeweb.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="*"
