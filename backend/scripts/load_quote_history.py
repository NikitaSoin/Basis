"""Первичная массовая закачка ИСТОРИИ котировок с MOEX ISS (Этап 0 аналитики портфеля).

Разовая ручная операция (как import_data.sh): проходит по всем компаниям из
таблицы companies, выкачивает дневную историю до 10 лет назад (сколько есть —
молодые бумаги отдают меньше, это норма) и заливает в существующую таблицу
quotes. Идемпотентно: ON CONFLICT (company_id, date) — повторный запуск дублей
не плодит. Бенчмарк-индексы (IMOEX, RTSI, MCFTR) — в таблицу index_history.

Запуск (из каталога backend):
  python -m scripts.load_quote_history --tickers SBER,LKOH,YDEX   # тест на выборке
  python -m scripts.load_quote_history --indices                  # только бенчмарки
  python -m scripts.load_quote_history --all                      # все компании + бенчмарки
  опции: --years 10 (глубина, по умолчанию 10)
"""
import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.models.company import Company
from app.services.moex_history import (
    BENCHMARK_TICKERS,
    REQUEST_PAUSE,
    fetch_index_history,
    fetch_share_history,
    upsert_index_rows,
    upsert_share_rows,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def bucket(first: date | None, today: date) -> str:
    """Классификация глубины истории для итогового отчёта."""
    if first is None:
        return "пусто"
    years = (today - first).days / 365.25
    if years >= 5:
        return ">=5 лет"
    if years >= 1:
        return "1-5 лет"
    return "<1 года"


def load_companies(tickers: list[str] | None, years: int) -> None:
    today = date.today()
    date_from = today - timedelta(days=int(years * 365.25))

    db = SessionLocal()
    try:
        q = db.query(Company).order_by(Company.ticker)
        if tickers:
            q = q.filter(Company.ticker.in_(tickers))
        companies = q.all()
        logger.info("Закачка истории: %d бумаг, глубина с %s", len(companies), date_from)

        buckets: dict[str, list[str]] = {">=5 лет": [], "1-5 лет": [], "<1 года": [], "пусто": []}
        total_rows = 0
        t0 = time.time()

        for i, c in enumerate(companies, 1):
            try:
                rows = fetch_share_history(c.ticker, date_from, today)
                written = upsert_share_rows(db, c.id, rows)
                db.commit()
                total_rows += written
                first = date.fromisoformat(rows[0]["TRADEDATE"]) if rows else None
                b = bucket(first, today)
                buckets[b].append(c.ticker)
                logger.info("[%d/%d] %s: %d строк (с %s) — %s",
                            i, len(companies), c.ticker, written,
                            first or "—", b)
            except Exception as e:
                db.rollback()
                buckets["пусто"].append(c.ticker)
                logger.error("[%d/%d] %s: ОШИБКА %s", i, len(companies), c.ticker, e)
            time.sleep(REQUEST_PAUSE)

        elapsed = time.time() - t0
        logger.info("─" * 60)
        logger.info("ИТОГО: %d строк за %.0f сек", total_rows, elapsed)
        for b, ts in buckets.items():
            logger.info("  %-8s %3d шт.%s", b, len(ts),
                        ("  (" + ", ".join(ts[:12]) + ("…" if len(ts) > 12 else "") + ")") if ts and b != ">=5 лет" else "")
    finally:
        db.close()


def load_indices(years: int) -> None:
    today = date.today()
    date_from = today - timedelta(days=int(years * 365.25))
    db = SessionLocal()
    try:
        for t in BENCHMARK_TICKERS:
            try:
                rows = fetch_index_history(t, date_from, today)
                written = upsert_index_rows(db, t, rows)
                db.commit()
                first = rows[0]["TRADEDATE"] if rows else "—"
                logger.info("Индекс %s: %d строк (с %s)", t, written, first)
            except Exception as e:
                db.rollback()
                logger.error("Индекс %s: ОШИБКА %s", t, e)
            time.sleep(REQUEST_PAUSE)
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Массовая закачка истории котировок с MOEX ISS")
    p.add_argument("--tickers", help="через запятую: SBER,LKOH,YDEX (тестовый прогон)")
    p.add_argument("--all", action="store_true", help="все компании из БД + бенчмарки")
    p.add_argument("--indices", action="store_true", help="только бенчмарк-индексы")
    p.add_argument("--years", type=int, default=10, help="глубина в годах (по умолчанию 10)")
    args = p.parse_args()

    if args.tickers:
        load_companies([t.strip().upper() for t in args.tickers.split(",")], args.years)
    elif args.indices:
        load_indices(args.years)
    elif args.all:
        load_companies(None, args.years)
        load_indices(args.years)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
