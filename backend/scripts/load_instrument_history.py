"""Первичная массовая закачка ИСТОРИИ облигаций/фьючерсов/фондов с MOEX ISS.

Разовая ручная операция (как load_quote_history). На бою глубина наполняется
автоматически стартовым бэкафиллом (_instrument_history_startup, если таблица
пуста) и ежедневно докачивается вечерним _history_job — этот скрипт нужен для
ручного догруза/переезда/увеличения глубины. Идемпотентно (ON CONFLICT
asset_class+secid+date). Грузит только бумаги из метаданных bonds/futures/funds.

Запуск (из каталога backend):
  python -m scripts.load_instrument_history --days 365            # все классы
  python -m scripts.load_instrument_history --class bond --days 730
"""
import argparse
import logging
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.instrument_history import SOURCES, load_range

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("load_instrument_history")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=365, help="глубина истории, дней")
    ap.add_argument("--class", dest="cls", choices=list(SOURCES), default=None,
                    help="только один класс (по умолчанию все)")
    args = ap.parse_args()

    classes = [args.cls] if args.cls else list(SOURCES)
    till = date.today()
    frm = till - timedelta(days=args.days)
    db = SessionLocal()
    try:
        for ac in classes:
            n = load_range(db, ac, frm, till)
            logger.info("%s: загружено %d строк за %d дн.", ac, n, args.days)
    finally:
        db.close()


if __name__ == "__main__":
    main()
