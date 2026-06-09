"""Загрузка/обновление данных классов активов (облигации, фьючерсы, фонды).

Единое место оркестрации — чтобы и CLI-скрипты (scripts/load_*.py), и
АВТО-ОБНОВЛЕНИЕ при старте сервера (app.main lifespan) звали одно и то же.

Идемпотентность: всё через upsert по SECID. Свежесть: refresh_all_if_stale
грузит класс, только если таблица пуста или данные старше порога — поэтому
частые рестарты контейнера не запускают тяжёлую загрузку повторно, а после
деплоя с новой миграцией данные подтягиваются сами (без ручной команды).
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def refresh_bonds(db: Session, sleep: float = 0.3, limit: int | None = None) -> int:
    """Полный охват облигаций с MOEX + типы купонов + агентские рейтинги."""
    from app.services.moex_bonds import (
        TRADE_BOARDS, fetch_board, fetch_meta_map, load_agency_ratings,
        load_ofz_curve, upsert_bond,
    )
    curve = load_ofz_curve()
    ratings = load_agency_ratings()
    recs: dict[str, dict] = {}
    for board, btype in TRADE_BOARDS:
        try:
            for rec in fetch_board(board, btype):
                recs.setdefault(rec["s"]["SECID"], rec)
        except Exception as e:
            logger.warning("борд %s недоступен: %s", board, e)
    secids = list(recs)[:limit] if limit else list(recs)
    meta = fetch_meta_map(secids, sleep=sleep)
    bad = 0
    for i, secid in enumerate(secids):
        try:
            with db.begin_nested():
                upsert_bond(db, recs[secid], curve, meta.get(secid), ratings)
        except Exception as e:
            bad += 1
            logger.warning("пропускаю %s: %s", secid, e)
        if (i + 1) % 200 == 0:
            db.commit()
    db.commit()
    n = db.execute(text("SELECT count(*) FROM bonds")).scalar()
    logger.info("Облигации: загружено, в БД %d (битых %d)", n, bad)
    return n


def refresh_futures(db: Session) -> int:
    """Все контракты FORTS (один запрос)."""
    from app.services.moex_futures import fetch_futures, upsert_future
    recs = fetch_futures()
    for i, rec in enumerate(recs):
        try:
            with db.begin_nested():
                upsert_future(db, rec)
        except Exception as e:
            logger.warning("фьючерс пропуск: %s", e)
        if (i + 1) % 200 == 0:
            db.commit()
    db.commit()
    n = db.execute(text("SELECT count(*) FROM futures")).scalar()
    logger.info("Фьючерсы: загружено, в БД %d", n)
    return n


def refresh_funds(db: Session) -> int:
    """Все фонды борда TQTF (один запрос)."""
    from app.services.moex_funds import fetch_funds, upsert_fund
    recs = fetch_funds()
    for rec in recs:
        try:
            with db.begin_nested():
                upsert_fund(db, rec)
        except Exception as e:
            logger.warning("фонд пропуск: %s", e)
    db.commit()
    n = db.execute(text("SELECT count(*) FROM funds")).scalar()
    logger.info("Фонды: загружено, в БД %d", n)
    return n


def _table_exists(db: Session, table: str) -> bool:
    try:
        db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        return True
    except Exception:
        db.rollback()
        return False


def _stale(db: Session, table: str, max_age_hours: float) -> bool:
    """True, если таблицы нет, она пуста или данные старше порога."""
    try:
        row = db.execute(text(f"SELECT count(*), max(updated_at) FROM {table}")).first()
    except Exception:
        return False  # таблицы ещё нет (миграция не применилась) — не лезем
    cnt, last = row[0], row[1]
    if not cnt:
        return True
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > timedelta(hours=max_age_hours)


def ensure_migrations() -> None:
    """Применить миграции БД программно (alembic upgrade head). Делает пайплайн
    данных самодостаточным: после деплоя новые таблицы появляются сами, даже если
    точка входа контейнера — uvicorn напрямую, а не start.sh. Идемпотентно."""
    import os
    try:
        from alembic.config import Config
        from alembic import command
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
        command.upgrade(cfg, "head")
        logger.info("Авто-миграции: alembic upgrade head выполнен")
    except Exception as e:
        logger.warning("Авто-миграции не применились (повторим при следующем прогоне): %s", e)


def refresh_all_if_stale(bonds_max_age_hours: float = 22.0) -> None:
    """Авто-обновление данных при старте сервера. Безопасно вызывать на каждом старте.
    - Фьючерсы и фонды — ДЁШЕВО (один запрос к MOEX, секунды) → обновляем ВСЕГДА,
      чтобы цены/ликвидность были свежими и чтобы факт авто-загрузки был виден.
    - Облигации — ДОРОГО (~3100 описаний, 15-20 мин) → только если пусто/устарело,
      и в любом случае таблица должна существовать (миграция применена)."""
    ensure_migrations()
    db = SessionLocal()
    try:
        # дешёвые классы — всегда (но только если таблица уже существует)
        from app.services.moex_spot import refresh_spot
        for table, fn, name in (("futures", refresh_futures, "фьючерсы"), ("funds", refresh_funds, "фонды"),
                                ("spot_assets", refresh_spot, "валюта/металлы")):
            try:
                if _table_exists(db, table):
                    fn(db)
                    logger.info("Авто-обновление: %s обновлены", name)
            except Exception as e:
                logger.exception("Авто-обновление %s упало: %s", name, e)
                db.rollback()
        # дорогой класс — по свежести
        try:
            if _table_exists(db, "bonds") and _stale(db, "bonds", bonds_max_age_hours):
                logger.info("Авто-обновление: облигации устарели/пусты — гружу (долго)…")
                refresh_bonds(db)
            else:
                logger.info("Авто-обновление: облигации свежие — пропускаю")
        except Exception as e:
            logger.exception("Авто-обновление облигаций упало: %s", e)
            db.rollback()
        # опционы — по свежести (тянем большую доску, считаем греки; не на каждый рестарт)
        try:
            from app.services.moex_options import refresh_options
            if _table_exists(db, "options") and _stale(db, "options", bonds_max_age_hours):
                logger.info("Авто-обновление: опционы устарели/пусты — гружу…")
                refresh_options(db)
            else:
                logger.info("Авто-обновление: опционы свежие — пропускаю")
        except Exception as e:
            logger.exception("Авто-обновление опционов упало: %s", e)
            db.rollback()
    finally:
        db.close()
