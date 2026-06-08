"""Загрузка биржевых фондов (БПИФ/ETF) с MOEX ISS (борд TQTF).

Один запрос, ~100 фондов. TER/состав — не на MOEX, заполняются отдельно.

Запуск (из каталога backend):
  python -m scripts.load_funds
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.moex_funds import fetch_funds, upsert_fund

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    recs = fetch_funds()
    logger.info("TQTF: получено %d фондов", len(recs))
    db = SessionLocal()
    try:
        for rec in recs:
            upsert_fund(db, rec)
        db.commit()
        from sqlalchemy import text
        logger.info("Всего фондов в БД: %d", db.execute(text("SELECT count(*) FROM funds")).scalar())
        rows = db.execute(text("SELECT fund_type, count(*) FROM funds GROUP BY fund_type ORDER BY 2 DESC")).all()
        logger.info("По типу: %s", ", ".join(f"{k}: {n}" for k, n in rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
