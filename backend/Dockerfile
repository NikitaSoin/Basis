FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Миграции — в ФОНЕ, uvicorn — СРАЗУ на переднем плане (порт открывается немедленно,
# healthcheck проходит даже при медленных/падающих миграциях). $PORT — если платформа
# назначает свой порт; иначе 8000.
CMD ["sh", "-c", "(alembic upgrade head || echo '[start] alembic upgrade failed — continuing, server stays up') & exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
