# 🔴 Кодовое имя Debian ЗАКРЕПЛЕНО (-bookworm), не голый -slim: тег -slim
# алиасится на новейший стабильный Debian, и после выхода Debian 13 (Trixie)
# сборка на билдере Timeweb стала падать — репозитории Trixie оттуда
# недоступны (apt-get update: Network is unreachable → exit code 100;
# инцидент 2026-07-26, диагноз саппорта Timeweb). Bookworm (Debian 12) —
# стабильный и доступный; при будущем апгрейде Python тоже сохранять суффикс.
FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Миграции — в ФОНЕ, uvicorn — СРАЗУ на переднем плане (порт открывается немедленно,
# healthcheck проходит даже при медленных/падающих миграциях). $PORT — если платформа
# назначает свой порт; иначе 8000.
CMD ["sh", "-c", "(alembic upgrade head || echo '[start] alembic upgrade failed — continuing, server stays up') & exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
