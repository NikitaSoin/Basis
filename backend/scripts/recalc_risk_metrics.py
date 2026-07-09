"""Ручной запуск пересчёта риск-метрик (CLI-обёртка).

Логика — в app.services.risk_metrics.recalc_all_company_metrics() (та же
функция вызывается автоматически в ежедневном джобе, см. main.py
_history_job, ПОСЛЕ обновления истории котировок — этот скрипт нужен
только чтобы прогнать пересчёт сразу, не дожидаясь джоба).

Запуск (из каталога backend):
  python -m scripts.recalc_risk_metrics
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.risk_metrics import recalc_all_company_metrics

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    result = recalc_all_company_metrics()
    print(result)


if __name__ == "__main__":
    main()
