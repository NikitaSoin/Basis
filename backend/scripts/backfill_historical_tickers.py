"""Ручной запуск бэкфилла истории котировок под прежними тикерами (CLI-обёртка).

Логика — в app.services.moex_history.backfill_historical_tickers() (та же
функция вызывается автоматически в ежедневном джобе, см. main.py _history_job —
этот скрипт нужен только чтобы прогнать бэкфилл сразу, не дожидаясь джоба).

Запуск (из каталога backend):
  python -m scripts.backfill_historical_tickers            # все компании с historical_tickers
  python -m scripts.backfill_historical_tickers --tickers YDEX
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.moex_history import backfill_historical_tickers

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    p = argparse.ArgumentParser(description="Бэкфилл истории котировок под старыми тикерами")
    p.add_argument("--tickers", help="через запятую: YDEX (по ТЕКУЩЕМУ тикеру компании)")
    args = p.parse_args()
    backfill_historical_tickers(
        [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    )


if __name__ == "__main__":
    main()
