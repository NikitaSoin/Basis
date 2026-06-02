#!/usr/bin/env bash
# Разовый РУЧНОЙ импорт профилей компаний в БД.
# Запускать вручную при необходимости (например, после обновления данных),
# а НЕ на каждом старте контейнера. Раньше это выполнялось в start.sh при
# каждом рестарте — вынесено сюда, чтобы старт сервера не зависел от тяжёлого
# импорта и не уходил в крэш-луп при недоступной БД.
#
# Использование (из каталога backend):
#   ./import_data.sh
#
# В отличие от start.sh здесь set -e: если БД недоступна или импорт упал —
# скрипт честно завершится с ошибкой, чтобы было видно, что импорт не прошёл.

set -euo pipefail

echo "[import] применяю миграции (alembic upgrade head)..."
alembic upgrade head

# 1. Таблица companies — СПИСОК компаний на сайте (/api/companies).
#    Источник: backend/data/rates.csv (263 акции MOEX). Без этого шага список
#    пустой → на сайте «Компании не найдены». Idempotent: дубли пропускаются.
echo "[import] наполняю таблицу companies из data/rates.csv..."
python -m scripts.load_all_companies data/rates.csv

# 2. Таблица company_profiles — профиль/обзор компании (вкладка «обзор»).
#    Источник: backend/data/company_profiles/*.json. Upsert по тикеру.
echo "[import] импортирую профили компаний в БД..."
python -m scripts.import_profiles_to_db --all

echo "[import] готово."
