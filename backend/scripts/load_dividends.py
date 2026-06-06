"""Первичная закачка истории дивидендов с MOEX ISS (Этап 3).

Проходит по всем компаниям, качает /iss/securities/{T}/dividends и заливает
в таблицу dividends (идемпотентно, ON CONFLICT DO NOTHING). RUB-выплаты;
валютные пропускаются с подсчётом. Заодно обновляет безрисковую ставку
ОФЗ-1г (G-curve). Еженедельное дообновление — в планировщике (main.py).

Запуск (из каталога backend):
  python -m scripts.load_dividends            # все компании + ставка
  python -m scripts.load_dividends --tickers SBER,LKOH
"""
import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.company import Company
from app.services.moex_dividends import REQUEST_PAUSE, sync_dividends_for, update_risk_free_rate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", help="через запятую (по умолчанию — все)")
    args = p.parse_args()

    db = SessionLocal()
    try:
        q = db.query(Company).order_by(Company.ticker)
        if args.tickers:
            q = q.filter(Company.ticker.in_([t.strip().upper() for t in args.tickers.split(",")]))
        companies = q.all()
        logger.info("Дивиденды: %d бумаг", len(companies))

        total = fx_total = 0
        with_divs = no_divs = errors = 0
        for i, c in enumerate(companies, 1):
            try:
                written, fx = sync_dividends_for(db, c.ticker)
                db.commit()
                total += written
                fx_total += fx
                if written:
                    with_divs += 1
                else:
                    no_divs += 1
                if i % 25 == 0:
                    logger.info("[%d/%d] … всего выплат: %d", i, len(companies), total)
            except Exception as e:
                db.rollback()
                errors += 1
                logger.warning("%s: %s", c.ticker, e)
            time.sleep(REQUEST_PAUSE)

        logger.info("─" * 60)
        logger.info("Выплат записано: %d | бумаг с дивидендами: %d | без: %d | валютных пропущено: %d | ошибок: %d",
                    total, with_divs, no_divs, fx_total, errors)

        rate = update_risk_free_rate(db)
        logger.info("Безрисковая ставка ОФЗ-1г: %s", f"{rate:.2f}%" if rate else "недоступна")
    finally:
        db.close()


if __name__ == "__main__":
    main()
