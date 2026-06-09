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

# 3. Таблица bonds — класс активов «Облигации» (полный охват ~3100 выпусков).
#    Источник: MOEX ISS (борды TQOB/TQCB/TQOY/TQOD/TQRD) + типы купонов из
#    описаний выпусков + агентские рейтинги (smart-lab). Запросы последовательные
#    с паузой — операция идёт ~15-20 мин (бережно к rate limit MOEX). Idempotent
#    (upsert по SECID). Чтобы пропустить: SKIP_BONDS=1 ./import_data.sh
if [ "${SKIP_BONDS:-0}" != "1" ]; then
  echo "[import] загружаю облигации с MOEX (полный охват, ~15-20 мин)..."
  python -m scripts.load_bonds
fi

# 4. Таблица futures — класс активов «Фьючерсы» (срочный рынок FORTS, ~560
#    контрактов). Источник: MOEX ISS (engine=futures). Один запрос, быстро.
#    Idempotent (upsert по SECID). Чтобы пропустить: SKIP_FUTURES=1 ./import_data.sh
if [ "${SKIP_FUTURES:-0}" != "1" ]; then
  echo "[import] загружаю фьючерсы с MOEX (FORTS)..."
  python -m scripts.load_futures
fi

# 5. Таблица funds — биржевые фонды (БПИФ/ETF, борд TQTF, ~100). Один запрос.
if [ "${SKIP_FUNDS:-0}" != "1" ]; then
  echo "[import] загружаю фонды с MOEX (TQTF)..."
  python -m scripts.load_funds
fi

# 6. Таблица spot_assets — валюта и металлы (USD/CNY + золото/серебро). Быстро.
if [ "${SKIP_SPOT:-0}" != "1" ]; then
  echo "[import] загружаю спот валюту/металлы с MOEX..."
  python -m scripts.load_spot
fi

# 7. Таблица options — опционы (урезанная витрина, греки Блэк-76). ~1-2 мин.
if [ "${SKIP_OPTIONS:-0}" != "1" ]; then
  echo "[import] загружаю опционы с MOEX..."
  python -m scripts.load_options
fi

echo "[import] готово."
