"""Загрузка фьючерсов с MOEX ISS (класс активов «Фьючерсы», срочный рынок FORTS).

Грузит все торгуемые контракты FORTS одним запросом (securities + marketdata),
считает номинал и эффективное плечо, классифицирует базовый актив. Текстовая
аналитика (futures-analyst) — отдельно, на срезе разнотипных контрактов.

Запуск (из каталога backend):
  python -m scripts.load_futures
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.moex_futures import fetch_futures, upsert_future

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    recs = fetch_futures()
    logger.info("FORTS: получено %d контрактов", len(recs))

    db = SessionLocal()
    try:
        for i, rec in enumerate(recs):
            upsert_future(db, rec)
            if (i + 1) % 200 == 0:
                db.commit()
        db.commit()

        from sqlalchemy import text
        logger.info("─" * 50)
        logger.info("Всего фьючерсов в БД: %d", db.execute(text("SELECT count(*) FROM futures")).scalar())
        logger.info("Базовых активов: %d", db.execute(text("SELECT count(distinct asset_code) FROM futures")).scalar())
        rows = db.execute(text("SELECT asset_kind, count(*) FROM futures GROUP BY asset_kind ORDER BY 2 DESC")).all()
        logger.info("По типу: %s", ", ".join(f"{k}: {n}" for k, n in rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
