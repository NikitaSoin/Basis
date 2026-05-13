"""Умное обновление котировок с MOEX.
- Торговые часы (10:00-18:50 МСК, пн-пт): каждые 5 мин
- Вне торговых часов будни:              раз в час
- Выходные:                              раз в 6 часов
- Дебаунс: пропускаем если прошло < 4 мин с последнего обновления
"""
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from app.db.session import SessionLocal
from app.models.company import Company, Quote

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
_last_update: datetime | None = None   # UTC datetime последнего реального обновления


def _in_trading_hours(now_msk: datetime) -> bool:
    if now_msk.weekday() >= 5:          # сб/вс
        return False
    t = now_msk.hour * 60 + now_msk.minute
    return 10 * 60 <= t <= 18 * 60 + 50  # 10:00 – 18:50


def _should_update() -> bool:
    global _last_update
    now_utc = datetime.now(timezone.utc)
    now_msk = datetime.now(MSK)

    # Дебаунс — защита от двойного запуска
    if _last_update is not None:
        elapsed = (now_utc - _last_update).total_seconds()
        if elapsed < 240:
            logger.debug("Котировки: пропуск (прошло %.0f с)", elapsed)
            return False

    # Определяем нужный интервал
    if _in_trading_hours(now_msk):
        required_interval = 0            # обновлять при каждом вызове в торговое время
    elif now_msk.weekday() >= 5:
        required_interval = 6 * 3600    # выходные — раз в 6 ч
    else:
        required_interval = 3600        # будни вне торгов — раз в час

    if _last_update is None:
        return True
    return (now_utc - _last_update).total_seconds() >= required_interval


def update_all_quotes() -> None:
    if not _should_update():
        return

    global _last_update
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    from fetch_quotes import fetch_moex

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
                new_chg = quote_data.get("change_pct") or 0
                if new_chg == 0 and existing.change_pct and float(existing.change_pct) != 0:
                    continue
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
        _last_update = datetime.now(timezone.utc)
        logger.info("Scheduler: обновлено %d котировок (МСК %s)",
                    updated, datetime.now(MSK).strftime("%H:%M"))
    except Exception as e:
        logger.exception("Scheduler: ошибка обновления котировок: %s", e)
        db.rollback()
    finally:
        db.close()
