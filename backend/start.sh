#!/usr/bin/env bash
# Старт backend.
# Принципы устойчивости (чтобы не уходить в крэш-луп при недоступной/медленной БД):
#  1) uvicorn поднимается СРАЗУ и отвечает на /api/health всегда, даже если БД
#     недоступна — операции с БД НЕ блокируют запуск сервера.
#  2) Миграции Alembic выполняются в ФОНЕ с повторными попытками; их неуспех
#     НЕ роняет контейнер (нет exit с ошибкой → нет перезапуска в петлю).
#  3) Импорт 262 профилей вынесен в ./import_data.sh — разовая РУЧНАЯ операция,
#     НЕ выполняется на каждом старте.

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

# Детектор устаревших/неполных финансовых данных → очередь обновления
# (companies/_refresh_queue.json). Идемпотентно, без сети/БД, в фоне; неуспех НЕ роняет
# старт. ВНИМАНИЕ: это только ДЕТЕКЦИЯ — report-fetcher/financial-analyst это AI-субагенты,
# cron их не запускает; добыча/дозаполнение выполняется в сессии Claude по очереди.
( python -m scripts.refresh_financials || python3 -m scripts.refresh_financials || true ) &

# Веб-сервер — на переднем плане. exec → uvicorn становится PID 1 и корректно
# получает сигналы остановки от платформы.
# --proxy-headers + --forwarded-allow-ips="*": корректная работа за реверс-прокси
# Timeweb (схема/IP клиента из X-Forwarded-*). Без них за прокси возможны артефакты
# доставки ответа. --timeout-keep-alive побольше — прокси держит keep-alive дольше.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips="*" --timeout-keep-alive 75
