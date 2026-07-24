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


def _recompute_market_caps(db) -> None:
    """Капитализация = ЖИВАЯ цена × число акций. Пересчитываем market_cap всех
    компаний от последнего close в quotes и shares_outstanding (НЕценовое поле из
    rates.csv ISSUESIZE). Вызывается после каждой записи котировок — капа всегда
    свежая, не застывший снимок rates.csv."""
    from sqlalchemy import text
    db.execute(text("""
        UPDATE companies c
           SET market_cap = q.close * c.shares_outstanding
          FROM (
            SELECT DISTINCT ON (company_id) company_id, close
              FROM quotes
             WHERE close IS NOT NULL
             ORDER BY company_id, date DESC
          ) q
         WHERE q.company_id = c.id
           AND c.shares_outstanding IS NOT NULL
    """))


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

    from app.services import tinkoff_quotes

    if tinkoff_quotes.is_available():
        _update_from_tinkoff()
    else:
        _update_from_moex()


def _update_from_tinkoff() -> None:
    """Обновляем БД ценами из Tinkoff in-memory кэша."""
    global _last_update
    from datetime import date
    from app.services import tinkoff_quotes

    # Обновляем кэш перед записью в БД
    tinkoff_quotes.refresh_prices()

    prices = tinkoff_quotes.get_all_prices()
    today = date.today()

    db = SessionLocal()
    try:
        companies = db.query(Company).all()
        updated = 0
        for company in companies:
            q = prices.get(company.ticker)
            if not q or q["price"] is None:
                continue
            existing = (
                db.query(Quote)
                .filter(Quote.company_id == company.id, Quote.date == today)
                .first()
            )
            if existing:
                existing.close = q["price"]
                existing.change_abs = q["change_abs"]
                existing.change_pct = q["change_pct"]
            else:
                db.add(Quote(
                    company_id=company.id, date=today,
                    open=q["price"], close=q["price"],
                    high=q["price"], low=q["price"],
                    volume=0,
                    prev_close=tinkoff_quotes._prices.get(company.ticker, {}).get("prev_close"),
                    change_abs=q["change_abs"],
                    change_pct=q["change_pct"],
                ))
            updated += 1
        _recompute_market_caps(db)  # капа от свежей цены × акции
        db.commit()
        _last_update = datetime.now(timezone.utc)
        logger.info("Scheduler: Tinkoff обновил %d котировок (МСК %s)",
                    updated, datetime.now(MSK).strftime("%H:%M"))
        # Живая цена облигаций — та же 5-минутка, отдельный try: сбой здесь
        # НЕ должен ронять уже успешно записанные котировки акций выше.
        try:
            from app.services.asset_data import refresh_bond_live_prices
            n_bonds = refresh_bond_live_prices(db)
            if n_bonds:
                logger.info("Scheduler: Tinkoff обновил живую цену %d облигаций", n_bonds)
        except Exception as e:
            logger.warning("Scheduler: живая цена облигаций пропущена: %s", e)
            db.rollback()
    except Exception as e:
        logger.exception("Scheduler: ошибка Tinkoff обновления: %s", e)
        db.rollback()
    finally:
        db.close()


def _update_from_moex() -> None:
    """Оригинальный MOEX ISS код — не тронут."""
    global _last_update
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
    from fetch_quotes import fetch_moex_bulk

    db = SessionLocal()
    try:
        bulk = fetch_moex_bulk()
        bulk.pop("_moex_time", None)
        bulk.pop("_fetched_at", None)
        companies = db.query(Company).order_by(Company.ticker).all()
        logger.info("Scheduler: bulk MOEX %d котировок, компаний в БД %d", len(bulk), len(companies))
        updated = 0
        for company in companies:
            quote_data = bulk.get(company.ticker)
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

        _recompute_market_caps(db)  # капа от свежей цены × акции
        db.commit()
        _last_update = datetime.now(timezone.utc)
        logger.info("Scheduler: обновлено %d котировок (МСК %s)",
                    updated, datetime.now(MSK).strftime("%H:%M"))
    except Exception as e:
        logger.exception("Scheduler: ошибка обновления котировок: %s", e)
        db.rollback()
    finally:
        db.close()
