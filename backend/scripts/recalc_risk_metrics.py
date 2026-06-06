"""Пересчёт риск-метрик в company_metrics из истории котировок (Этап 2).

Наполняет beta / volatility / return_3y / history_years для всех компаний:
  - волатильность: СКО дневных лог-доходностей за 3 года × √252, годовая %
  - бета: против IMOEX (index_history), на пересечении торговых дат
  - return_3y: CAGR по цене за период (факт прошлого, не прогноз)
  - history_years: фактическая глубина истории (для пометки «*» при <1 года)

Идемпотентно (UPDATE по тикеру). Запуск вручную в консоли (как остальные):
  cd backend && python -m scripts.recalc_risk_metrics
Метрики устаревают по мере набегания истории — пересчитывать периодически
(можно завести в cron позже; пока ручной запуск).
"""
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.company import Company
from app.services.risk_metrics import (
    compute_for_company, load_index_series, log_returns, window_start,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_UPDATE_SQL = text("""
    UPDATE company_metrics
    SET beta = :beta, volatility = :volatility, return_3y = :return_3y,
        history_years = :history_years, updated_at = :updated_at
    WHERE ticker = :ticker
""")


def main() -> None:
    db = SessionLocal()
    try:
        since = window_start()
        index_series = load_index_series(db, "IMOEX", since)
        if len(index_series) < 100:
            logger.error("IMOEX: в index_history мало данных (%d строк) — сначала "
                         "запусти scripts.load_quote_history --indices", len(index_series))
            sys.exit(1)
        index_returns = log_returns(index_series)
        logger.info("IMOEX: %d торговых дней с %s", len(index_returns), since)

        companies = db.query(Company).order_by(Company.ticker).all()
        now = datetime.now(timezone.utc)
        filled = {"volatility": 0, "beta": 0, "return_3y": 0}
        short_history, empty = [], []

        for c in companies:
            m = compute_for_company(db, c.id, index_returns, since)
            db.execute(_UPDATE_SQL, {"ticker": c.ticker, "updated_at": now, **m})
            for k in filled:
                if m[k] is not None:
                    filled[k] += 1
            if m["history_years"] is None:
                empty.append(c.ticker)
            elif m["history_years"] < 1:
                short_history.append(c.ticker)
        db.commit()

        total = len(companies)
        logger.info("─" * 60)
        logger.info("Готово: %d компаний", total)
        for k, v in filled.items():
            logger.info("  %-12s заполнено %3d / %d", k, v, total)
        logger.info("  история <1 года (в UI «*»): %d — %s", len(short_history), ", ".join(short_history) or "—")
        logger.info("  без истории (NULL): %d — %s", len(empty), ", ".join(empty) or "—")
    finally:
        db.close()


if __name__ == "__main__":
    main()
