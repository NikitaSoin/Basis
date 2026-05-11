"""Вызывается APScheduler каждый час для обновления котировок с MOEX."""
import logging
from app.db.session import SessionLocal
from app.models.company import Company, Quote

logger = logging.getLogger(__name__)

# Переиспользуем логику из scripts/fetch_quotes.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from fetch_quotes import fetch_moex


def update_all_quotes() -> None:
    db = SessionLocal()
    try:
        companies = db.query(Company).order_by(Company.ticker).all()
        logger.info("Scheduler: обновляю котировки для %d компаний", len(companies))
        updated = 0
        for company in companies:
            quote_data = fetch_moex(company.ticker)
            if not quote_data:
                continue
            existing = (
                db.query(Quote)
                .filter(Quote.company_id == company.id, Quote.date == quote_data["date"])
                .first()
            )
            if existing:
                existing.close = quote_data["close"]
                existing.open = quote_data["open"]
                existing.high = quote_data["high"]
                existing.low = quote_data["low"]
                existing.volume = quote_data["volume"]
                existing.prev_close = quote_data["prev_close"]
                existing.change_abs = quote_data["change_abs"]
                existing.change_pct = quote_data["change_pct"]
            else:
                db.add(Quote(company_id=company.id, **quote_data))
            updated += 1
        db.commit()
        logger.info("Scheduler: обновлено %d котировок", updated)
    except Exception as e:
        logger.exception("Scheduler: ошибка обновления котировок: %s", e)
        db.rollback()
    finally:
        db.close()
