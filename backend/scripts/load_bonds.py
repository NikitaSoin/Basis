"""Загрузка облигаций с MOEX ISS (класс активов «Облигации»).

Полный охват торгуемого рынка: ОФЗ + корпораты/биржевые + субфедеральные/
муниципальные + юаневые/долларовые + дефолтные (режим Д). Для каждого выпуска:
- параметры и рыночные данные (YTM/дюрация/цена) — с бордов MOEX;
- тип купона (фикс/флоатер/линкер) и метка YTM (к погашению/к оферте) — из
  описания выпуска (per-security, бережно к rate limit);
- ДВОЙНОЙ рейтинг: рыночная оценка по спреду к ОФЗ + агентский рейтинг (smart-lab).

Запросы к MOEX — ПОСЛЕДОВАТЕЛЬНО с паузой (не параллель сотнями): прошлый заход
падал на rate limit именно из-за плотного потока.

Запуск (из каталога backend):
  python -m scripts.load_bonds                 # полный охват + типы купонов + рейтинги
  python -m scripts.load_bonds --ofz-only
  python -m scripts.load_bonds --no-meta       # без описаний (быстро, без типов купонов)
  python -m scripts.load_bonds --sleep 0.4     # пауза между запросами описаний
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.db.session import SessionLocal
from app.services.moex_bonds import (
    TRADE_BOARDS, build_company_keys, fetch_board, fetch_meta_map, load_agency_ratings,
    load_ofz_curve, propagate_issuer_ratings, upsert_bond,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ofz-only", action="store_true")
    p.add_argument("--no-meta", action="store_true", help="не тянуть описания (без типов купонов)")
    p.add_argument("--no-ratings", action="store_true", help="не тянуть агентские рейтинги")
    p.add_argument("--sleep", type=float, default=0.3, help="пауза между запросами описаний, сек")
    p.add_argument("--limit", type=int, default=None, help="ограничить число выпусков (отладка)")
    args = p.parse_args()

    curve = load_ofz_curve()
    logger.info("Кривая ОФЗ: %d точек", len(curve))

    ratings = {} if args.no_ratings else load_agency_ratings()

    # 1) собрать выпуски со всех торговых бордов (дедуп по SECID)
    boards = [("TQOB", "ofz")] if args.ofz_only else TRADE_BOARDS
    recs: dict[str, dict] = {}
    for board, btype in boards:
        try:
            board_recs = fetch_board(board, btype)
        except Exception as e:
            logger.warning("борд %s недоступен: %s", board, e)
            continue
        for rec in board_recs:
            recs.setdefault(rec["s"]["SECID"], rec)
        logger.info("Борд %s: %d выпусков (всего уникальных %d)", board, len(board_recs), len(recs))

    secids = list(recs)
    if args.limit:
        secids = secids[: args.limit]
        recs = {s: recs[s] for s in secids}

    # 2) описания (тип купона / метка YTM / класс / дефолт) — последовательно
    meta = {}
    if not args.no_meta:
        logger.info("Тяну описания по %d выпускам (пауза %.2fс)…", len(secids), args.sleep)
        meta = fetch_meta_map(secids, sleep=args.sleep)

    # 3) запись батчами
    db = SessionLocal()
    try:
        build_company_keys(db)   # авто-связка выпуск → публичная компания (по именам из БД)
        bad = 0
        for i, secid in enumerate(secids):
            try:
                # SAVEPOINT на строку: откат битой НЕ теряет хорошие строки батча
                with db.begin_nested():
                    upsert_bond(db, recs[secid], curve, meta.get(secid), ratings)
            except Exception as e:
                bad += 1
                logger.warning("пропускаю %s: %s", secid, e)
                continue
            if (i + 1) % 200 == 0:
                db.commit()
                logger.info("  записано %d/%d", i + 1, len(secids))
        db.commit()
        if bad:
            logger.warning("пропущено битых строк: %d", bad)

        # рейтинг агентства — атрибут эмитента: распространяем по всем сериям +
        # засеваем голубые фишки (smart-lab покрывает не все ISIN). Идемпотентно.
        if not args.no_ratings:
            propagate_issuer_ratings(db)

        from sqlalchemy import text
        logger.info("─" * 50)
        logger.info("Всего облигаций в БД: %d", db.execute(text("SELECT count(*) FROM bonds")).scalar())
        for title, q in [
            ("по типу", "SELECT bond_type, count(*) FROM bonds GROUP BY bond_type ORDER BY 2 DESC"),
            ("по купону", "SELECT coupon_type, count(*) FROM bonds GROUP BY coupon_type ORDER BY 2 DESC"),
            ("по надёжности", "SELECT risk_tier, count(*) FROM bonds GROUP BY risk_tier ORDER BY 2 DESC"),
            ("с агентским рейтингом", "SELECT count(*) FROM bonds WHERE agency_rating IS NOT NULL"),
            ("дефолтных", "SELECT count(*) FROM bonds WHERE is_defaulted"),
        ]:
            rows = db.execute(text(q)).all()
            if len(rows) == 1 and len(rows[0]) == 1:
                logger.info("%s: %s", title, rows[0][0])
            else:
                logger.info("%s: %s", title, ", ".join(f"{t or '—'}: {n}" for t, n in rows))
    finally:
        db.close()


if __name__ == "__main__":
    main()
