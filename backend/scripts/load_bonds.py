"""Загрузка облигаций с MOEX ISS (класс активов «Облигации»).

Ночной срез: все ОФЗ (TQOB, ~60) + ликвидные корпораты (TQCB, листинг 1-2
уровня с рассчитанной доходностью). Полную раскатку на все ~3000 корпоратов —
после ОК владельца.

Запуск (из каталога backend):
  python -m scripts.load_bonds                 # ОФЗ + корпораты листинга 1-2
  python -m scripts.load_bonds --ofz-only
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.moex_bonds import fetch_board, load_ofz_curve, upsert_bond

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ofz-only", action="store_true")
    p.add_argument("--max-corp", type=int, default=400, help="лимит корпоратов (ночной срез)")
    args = p.parse_args()

    curve = load_ofz_curve()
    logger.info("Кривая ОФЗ: %d точек", len(curve))

    db = SessionLocal()
    try:
        ofz = fetch_board("TQOB", "ofz")
        for rec in ofz:
            upsert_bond(db, rec, curve)
        db.commit()
        logger.info("ОФЗ: загружено %d", len(ofz))

        n_corp = 0
        if not args.ofz_only:
            corp = fetch_board("TQCB", "corporate")
            # ночной срез: ликвидные (листинг 1-2) с рассчитанной доходностью,
            # рублёвые — чтобы спред к ОФЗ был осмыслен
            liquid = [r for r in corp
                      if (r["s"].get("LISTLEVEL") in (1, 2, "1", "2"))
                      and r["m"].get("YIELD") not in (None, "", 0)
                      and (r["s"].get("FACEUNIT") in (None, "SUR", "RUB"))]
            liquid = liquid[:args.max_corp]
            for rec in liquid:
                upsert_bond(db, rec, curve)
            db.commit()
            n_corp = len(liquid)
            logger.info("Корпораты (ликвидные): загружено %d из %d на борде", n_corp, len(corp))

        # сводка по риск-тирам
        from sqlalchemy import text
        rows = db.execute(text("SELECT risk_tier, count(*) FROM bonds GROUP BY risk_tier ORDER BY count(*) DESC")).all()
        logger.info("─" * 50)
        logger.info("Всего облигаций: %d (ОФЗ %d + корпораты %d)", len(ofz) + n_corp, len(ofz), n_corp)
        logger.info("По надёжности: %s", ", ".join(f"{t or '—'}: {n}" for t, n in rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
