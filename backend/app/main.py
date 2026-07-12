from contextlib import asynccontextmanager
import asyncio
import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.auth import router as auth_router
from app.api.companies import router as companies_router
from app.api.portfolios import router as portfolios_router
from app.api.market import router as market_router
from app.api.debug import router as debug_router
from app.api.bonds import router as bonds_router
from app.api.futures import router as futures_router
from app.api.funds import router as funds_router
from app.api.spot import router as spot_router
from app.api.options import router as options_router
from app.api.screener import router as screener_router
from app.api.macro import router as macro_router
from app.api.observer import router as observer_router
from app.api.assistant import router as assistant_router

logger = logging.getLogger(__name__)


async def _quotes_job():
    try:
        from app.services.quotes_updater import update_all_quotes
        await asyncio.get_event_loop().run_in_executor(None, update_all_quotes)
    except Exception as e:
        logger.exception("Ошибка планировщика котировок: %s", e)


async def _coefficients_job():
    """Еженедельные параметры с MOEX: официальные беты (fortscoefficients),
    безрисковая ставка ОФЗ-1г (G-curve) и свежие дивиденды. Всё меняется
    нечасто — еженедельного опроса достаточно; при недоступности ISS
    остаёмся на последних сохранённых значениях."""
    def _run():
        from app.services.moex_coefficients import sync_official_betas
        from app.services.moex_dividends import sync_dividends_for, update_risk_free_rate
        from app.db.session import SessionLocal
        from app.models.company import Company
        import time as _time

        sync_official_betas()
        db = SessionLocal()
        try:
            update_risk_free_rate(db)
            for c in db.query(Company).order_by(Company.ticker).all():
                try:
                    sync_dividends_for(db, c.ticker)
                    db.commit()
                except Exception:
                    db.rollback()
                _time.sleep(0.2)
        finally:
            db.close()

    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as e:
        logger.exception("Ошибка еженедельных параметров MOEX: %s", e)


async def _history_job():
    """Ежедневное доедание ИСТОРИИ котировок (пропущенные дни + финализация
    live-снапшотов официальными дневными свечами). Отдельный cron-job в ТОМ ЖЕ
    планировщике, а не внутри 5-минутного _quotes_job: дообновление — это
    ~261 поштучный запрос к ISS (минуты работы), его место — раз в день
    вечером после закрытия торгов, а не в горячем цикле котировок."""
    try:
        from app.services.moex_history import catch_up_history
        await asyncio.get_event_loop().run_in_executor(None, catch_up_history)
    except Exception as e:
        logger.exception("Ошибка дообновления истории котировок: %s", e)
    # Бэкфилл истории под прежними тикерами (редомициляция, напр. YDEX←YNDX) —
    # идемпотентно, дёшево при повторных запусках, поэтому просто в том же
    # ежедневном слоте, без отдельного ручного шага после деплоя миграции.
    try:
        from app.services.moex_history import backfill_historical_tickers
        await asyncio.get_event_loop().run_in_executor(None, backfill_historical_tickers)
    except Exception as e:
        logger.exception("Ошибка бэкфилла прежних тикеров: %s", e)
    # история облигаций/фьючерсов/фондов (instrument_history) — тот же вечерний слот
    try:
        from app.services.instrument_history import catch_up_instrument_history
        await asyncio.get_event_loop().run_in_executor(None, catch_up_instrument_history)
    except Exception as e:
        logger.exception("Ошибка дообновления истории инструментов: %s", e)
    # Пересчёт company_metrics (бета/волатильность/доходность/Шарп/CAPM) из
    # СВЕЖЕЙ истории — раньше это была ТОЛЬКО ручная операция (scripts/
    # recalc_risk_metrics.py), поэтому метрики годами не менялись даже при
    # заметном движении рынка. ОБЯЗАТЕЛЬНО последним шагом в этом джобе —
    # зависит от уже обновлённых quotes/index_history выше.
    try:
        from app.services.risk_metrics import recalc_all_company_metrics
        await asyncio.get_event_loop().run_in_executor(None, recalc_all_company_metrics)
    except Exception as e:
        logger.exception("Ошибка пересчёта company_metrics: %s", e)


async def _tinkoff_warmup():
    """Прогревает Tinkoff: загружает инструменты и первичные цены."""
    if not os.environ.get("TINKOFF_API_TOKEN"):
        logger.info("Tinkoff: токен не задан, используем MOEX ISS")
        return
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
        from fetch_quotes import fetch_moex_bulk
        from app.services import tinkoff_quotes
        from app.db.session import SessionLocal
        from app.models.company import Company

        loop = asyncio.get_running_loop()

        # Получаем prev_close с MOEX ISS (не time-sensitive — вчерашнее закрытие)
        def _get_prev_close():
            bulk = fetch_moex_bulk()
            bulk.pop("_moex_time", None)
            bulk.pop("_fetched_at", None)
            db = SessionLocal()
            try:
                tickers = [c.ticker for c in db.query(Company).all()]
            finally:
                db.close()
            return {t: (bulk.get(t) or {}).get("prev_close") for t in tickers}

        prev_close_map = await loop.run_in_executor(None, _get_prev_close)

        # Первичное обновление цен с Tinkoff
        ok = await loop.run_in_executor(
            None, lambda: tinkoff_quotes.refresh_prices(prev_close_map)
        )
        if ok:
            logger.info("Tinkoff: прогрев завершён, %d цен загружено", len(tinkoff_quotes.get_all_prices()))
        else:
            logger.warning("Tinkoff: прогрев не удался — fallback на MOEX ISS")
    except Exception as e:
        logger.exception("Tinkoff: ошибка прогрева: %s", e)


async def _asset_data_job():
    """Авто-обновление данных классов активов (облигации/фьючерсы/фонды) с MOEX.
    Грузит только устаревшее/пустое (идемпотентно) — поэтому после деплоя с новой
    миграцией данные подтягиваются САМИ, без ручной команды на консоли. Тяжёлая
    загрузка (облигации ~15-20 мин) идёт в executor-потоке и НЕ блокирует сервер."""
    def _refresh_assets():
        if not _wait_for_db():
            logger.error("Классы активов: БД так и не стала доступна — джоб пропущен")
            return
        from app.services.asset_data import refresh_all_if_stale
        refresh_all_if_stale()
    try:
        await asyncio.get_event_loop().run_in_executor(None, _refresh_assets)
    except Exception as e:
        logger.exception("Ошибка авто-обновления данных классов активов: %s", e)


async def _calendar_job():
    """Календарь событий (Направление 4) — НАМЕРЕННО отдельная задача/крон от
    _asset_data_job: раньше календарь обновлялся ПОСЛЕ загрузки облигаций/
    фьючерсов внутри одной последовательной задачи (~15-20+ мин); при частых
    перезапусках контейнера (Timeweb) задача обрывалась ДО календаря, и
    дивиденды/отчётность/корпсобытия месяцами не обновлялись, хотя сам билдер
    рабочий (см. debug/trigger-calendar). Разделение убирает эту зависимость —
    у календаря свой крон, не блокируемый длинной загрузкой активов."""
    def _cal():
        if not _wait_for_db():
            logger.error("Календарь: БД так и не стала доступна — джоб пропущен")
            return {"error": "db_unavailable"}
        from app.db.session import SessionLocal
        from app.services.calendar_events import refresh_all
        db = SessionLocal()
        try:
            return refresh_all(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _cal)
        logger.info("Календарь событий обновлён: %s", res)
    except Exception as e:
        logger.exception("Ошибка обновления календаря событий: %s", e)


async def _news_job():
    """Лента новостей Обозревателя: RSS → дедуп → фильтр важности → выжимка +
    «на что влияет» → маппинг тикеров → запись в БД. Сетевые и LLM-вызовы идут в
    executor-потоке, чтобы не блокировать сервер."""
    def _run():
        from app.services.news_pipeline import run_pipeline
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            return run_pipeline(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Лента новостей: прогон завершён — %s", res)
    except Exception as e:
        logger.exception("Ошибка прогона ленты новостей: %s", e)


def _wait_for_db(max_attempts: int = 6, delay_seconds: float = 5.0) -> bool:
    """Ждать готовности БД перед джобом, который НЕ ретраит сам (в отличие от
    alembic upgrade в start.sh, который умеет). Найдено по логам: контейнер
    иногда стартует/крон срабатывает раньше, чем Postgres принимает соединения
    ("Connection refused" на первой попытке) — без ретрая вся дневная синхронизация
    (напр. sync_cb — сценарии ЦБ/макроопрос) молча теряется до следующего крона."""
    import time
    from sqlalchemy import text as _sql_text
    from app.db.session import SessionLocal
    for attempt in range(1, max_attempts + 1):
        db = SessionLocal()
        try:
            db.execute(_sql_text("SELECT 1"))
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Ожидание БД: попытка %d/%d не удалась: %s", attempt, max_attempts, type(e).__name__)
            if attempt < max_attempts:
                time.sleep(delay_seconds)
        finally:
            db.close()
    return False


async def _macro_job():
    """Макрообзор: дневной ингест мира/курсов (ЦБ+FRED+World Bank) + сид справочника.
    Числовые ряды из Ленты приходят отдельно (в news-пайплайне). В executor-потоке."""
    def _run():
        if not _wait_for_db():
            logger.error("Макрообзор: БД так и не стала доступна за отведённые попытки — джоб пропущен")
            return {"error": "db_unavailable"}
        from app.services.macro_ingest import seed_indicators, ingest_all_world, check_staleness
        from app.services.macro_analytics import process as analytics_process
        from app.services.macro_cb_sync import sync_cb
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from app.services.macro_rosstat import ingest_rosstat_file, sync_ppi
            from app.services.macro_minfin_sync import sync_gov_spending
            from app.services.macro_hh_sync import sync_hh_index
            from app.services.macro_tankermap_sync import sync_urals
            seed_indicators(db)
            world = ingest_all_world(db)
            cb = sync_cb(db)  # ЦБ: ставка/прогноз/инфляция/ожидания/M2+кредит экономике (машинный первоисточник)
            ros = ingest_rosstat_file(db)  # Росстат: ручная выгрузка из fedstat (WAF блокирует машину)
            try:
                ppi = sync_ppi(db)  # Росстат ИЦП — реальный бюллетень rosstat.gov.ru (не fedstat)
            except Exception as e:  # noqa: BLE001
                logger.exception("Росстат-ИЦП упал: %s", e)
                db.rollback()
                ppi = {"error": f"unhandled:{type(e).__name__}"}
            try:
                minfin = sync_gov_spending(db)
            except Exception as e:  # noqa: BLE001 — не роняем весь джоб из-за одного источника
                logger.exception("Минфин-sync (госрасходы) упал: %s", e)
                db.rollback()
                minfin = {"error": f"unhandled:{type(e).__name__}"}
            try:
                hh = sync_hh_index(db)  # hh.индекс — открытый PDF-отчёт hh.ru (не dedicated API)
            except Exception as e:  # noqa: BLE001
                logger.exception("hh-sync упал: %s", e)
                db.rollback()
                hh = {"error": f"unhandled:{type(e).__name__}"}
            try:
                urals = sync_urals(db)  # Urals дневной ряд — TankerMap (не офиц. источник, см. докстринг)
            except Exception as e:  # noqa: BLE001
                logger.exception("TankerMap-Urals упал: %s", e)
                db.rollback()
                urals = {"error": f"unhandled:{type(e).__name__}"}
            analytics = analytics_process(db)
            stale = check_staleness(db)  # алерт по рядам, которые перестали обновляться
            return {"world": world, "cb": cb, "rosstat": ros, "ppi": ppi, "minfin": minfin,
                    "hh": hh, "urals": urals, "analytics": analytics, "stale": len(stale)}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Макрообзор: ингест мира/курсов — %s", res)
    except Exception as e:
        logger.exception("Ошибка ингеста Макрообзора: %s", e)


_EARNINGS_SEED = ["LKOH", "ROSN", "GAZP", "NVTK", "TATN", "SIBN", "PHOR", "GMKN",
                  "MGNT", "MTSS", "YDEX", "PLZL", "CHMF", "NLMK", "MOEX", "AFLT",
                  "RTKM", "MAGN", "SNGS", "ALRS"]


async def _earnings_job(seed_only: bool = False):
    """Анализ отчётностей: вечерний обход (новые периоды). seed_only — стартовый сид
    курируемого ликвидного набора (для контента после деплоя), без перебора всех."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.earnings import refresh
        db = SessionLocal()
        try:
            return refresh(db, tickers=_EARNINGS_SEED if seed_only else None,
                           limit=None if seed_only else 30)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Анализ отчётностей (%s): %s", "сид" if seed_only else "обход", res)
    except Exception as e:
        logger.exception("Ошибка анализа отчётностей: %s", e)


async def _earnings_startup():
    """Стартовый сид разборов отчётов курируемого набора — чтобы лента/карточки имели
    контент сразу после деплоя. Идемпотентно (существующие периоды не пересоздаются)."""
    await _earnings_job(seed_only=True)


async def _report_watch_job():
    """Автообнаружение вышедших отчётов (report_watch.py) — НЕЗАВИСИМО от _earnings_job:
    тот видит новый период только после РУЧНОГО обновления financials.json, этот детектит
    сам факт выхода отчёта по MOEX ir-calendar и разбирает по тексту из Ленты/СКРИН, без
    ожидания аналитика. Раз в сутки, после Ленты новостей (19:30) и календаря (06:45) —
    нужен свежий market_updates для фетча текста отчёта."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.report_watch import refresh
        db = SessionLocal()
        try:
            return refresh(db, days_back=5)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("report_watch (автообнаружение отчётов): %s", res)
    except Exception as e:
        logger.exception("Ошибка report_watch: %s", e)


async def _risk_metrics_startup():
    """Разовый прогон при старте (в дополнение к ежедневному джобу в 19:30 МСК):
    бэкфилл истории под прежними тикерами + пересчёт company_metrics. Без
    этого свежедеплоенный фикс (напр. YDEX←YNDX) не подействует до вечера —
    а пересчёт МЕСЯЦАМИ не запускался вообще (была только ручная команда),
    поэтому бета/волатильность/доходность в UI могли быть стухшим снапшотом
    независимо от реального движения рынка. Обе операции идемпотентны и
    дёшевы (~10с локально на 261 компанию) — безопасно гонять при каждом
    рестарте, не только руками."""
    try:
        from app.services.moex_history import backfill_historical_tickers
        await asyncio.get_event_loop().run_in_executor(None, backfill_historical_tickers)
    except Exception as e:
        logger.exception("Старт: ошибка бэкфилла прежних тикеров: %s", e)
    try:
        from app.services.risk_metrics import recalc_all_company_metrics
        res = await asyncio.get_event_loop().run_in_executor(None, recalc_all_company_metrics)
        logger.info("Старт: пересчёт company_metrics — %s", res)
    except Exception as e:
        logger.exception("Старт: ошибка пересчёта company_metrics: %s", e)


async def _screener_warm():
    """Прогрев кеша скринера акций (BASIS-скоринг). Облигации не греем — stale-while-revalidate."""
    await asyncio.sleep(30)  # даём серверу принять первые запросы перед тяжёлым расчётом
    try:
        from app.services.screener_scoring import warm_cache
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, warm_cache)
    except Exception as e:
        logger.exception("Ошибка прогрева скринера: %s", e)


async def _instrument_history_startup():
    """Стартовый бэкафилл истории облигаций/фьючерсов/фондов (instrument_history),
    если таблица пуста — чтобы после деплоя на бою сразу была глубина для графиков/
    спарклайнов на экране «Рынок». Идемпотентно; при наличии данных — пропуск (дальше
    докачивает вечерний _history_job)."""
    def _run():
        from app.db.session import SessionLocal
        from sqlalchemy import text
        from app.services.instrument_history import backfill_instrument_history
        db = SessionLocal()
        try:
            exists = db.execute(text("SELECT 1 FROM instrument_history LIMIT 1")).first()
        finally:
            db.close()
        if exists:
            logger.info("instr-hist: история уже есть — бэкафилл пропущен")
            return
        backfill_instrument_history(days_back=365)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as e:
        logger.exception("Ошибка стартового бэкафилла instrument_history: %s", e)


async def _seed_shares_startup():
    """После деплоя: проставить companies.shares_outstanding из data/rates.csv
    (ISSUESIZE — НЕценовое справочное поле) тем компаниям, у кого пусто, и сразу
    пересчитать капитализацию от СВЕЖЕЙ цены (quotes). Идемпотентно: трогаем только
    NULL. Капитализация = живая цена × число акций, не застывший снимок rates.csv."""
    def _run():
        import csv, io, os
        from app.db.session import SessionLocal
        from app.models.company import Company
        path = os.path.join(os.path.dirname(__file__), "..", "data", "rates.csv")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(__file__), "..", "..", "rates.csv")
        if not os.path.exists(path):
            return 0
        with open(path, encoding="cp1251") as f:
            lines = f.readlines()
        hi = next((i for i, l in enumerate(lines) if l.startswith("SECID")), None)
        if hi is None:
            return 0
        rows = list(csv.DictReader(io.StringIO("".join(lines[hi:])), delimiter=";"))

        def _int(s):
            try:
                return int(float(str(s).replace("\xa0", "").replace(" ", "").replace(",", ".")))
            except (ValueError, TypeError):
                return None

        shares = {(r.get("SECID") or "").strip(): _int(r.get("ISSUESIZE")) for r in rows}
        db = SessionLocal()
        n = 0
        try:
            for c in db.query(Company).filter(Company.shares_outstanding.is_(None)).all():
                sh = shares.get(c.ticker)
                if sh:
                    c.shares_outstanding = sh
                    n += 1
            db.commit()
        finally:
            db.close()
        # Сразу пересчитать капитализацию от свежей цены (пишет quotes + market_cap).
        from app.services.quotes_updater import update_all_quotes
        update_all_quotes()
        return n
    try:
        n = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Старт: число акций проставлено для %s компаний, капитализация пересчитана от свежей цены", n)
    except Exception as e:
        logger.exception("Ошибка стартового сида акций/капитализации: %s", e)


async def _macro_interpretation_job():
    """Макро «Оценка ситуации» (ИИ-интерпретация: текущая картина/ставка/прогноз ЦБ/
    рынок-сектора/сценарии) — раньше генерировалась ТОЛЬКО вручную кнопкой «Обновить
    анализ» на сайте, поэтому годами показывала один и тот же устаревший срез. Раз в
    сутки, после _macro_job (данные должны успеть посвежеть)."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_interpreter import generate
        db = SessionLocal()
        try:
            return generate(db)
        finally:
            db.close()
    try:
        row = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Макро-интерпретация обновлена: as_of=%s", getattr(row, "generated_at", None))
    except Exception as e:
        logger.exception("Ошибка обновления макро-интерпретации: %s", e)


async def _geo_job():
    """Геополитика: пересбор слитого синтеза по методичке (DeepSeek Pro, дорогой
    reasoning-вызов). Раз в сутки. Дайджест отдельных статей — отдельный, более
    частый job (_geo_digest_job), не завязан на этот."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geopolitics import refresh
        db = SessionLocal()
        try:
            return refresh(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Геополитика (синтез) обновлена: %s", res)
    except Exception as e:
        logger.exception("Ошибка обновления геополитики: %s", e)


async def _geo_digest_job():
    """Дайджест отдельных статей (Рыбарь/re:russia/Economist → карточки по региону
    геополитики + институциональная среда). Часто (в отличие от _geo_job) —
    источники вроде Рыбаря публикуют постоянно, редкий крон вытесняет старые
    статьи новыми до синтеза."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geo_digest import refresh
        db = SessionLocal()
        try:
            return refresh(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Гео-дайджест обновлён: %s", res)
    except Exception as e:
        logger.exception("Ошибка обновления гео-дайджеста: %s", e)


async def _geo_startup():
    """Стартовый прогон геополитики (синтез + дайджест) — чтобы вкладки имели
    контент после деплоя. Только если данных ещё нет (не гоняем Pro на рестарте)."""
    def _has():
        from app.db.session import SessionLocal
        from app.models.geo import GeoBlock
        from app.models.geo_digest import GeoDigestArticle
        db = SessionLocal()
        try:
            return db.query(GeoBlock).count() > 0, db.query(GeoDigestArticle).count() > 0
        finally:
            db.close()
    try:
        has_blocks, has_digest = await asyncio.get_event_loop().run_in_executor(None, _has)
        if not has_blocks:
            await _geo_job()
        if not has_digest:
            await _geo_digest_job()
    except Exception as e:  # noqa: BLE001
        logger.warning("Геополитика старт: %s", e)


async def _macro_startup():
    """При старте: сид справочника + идемпотентный бэкфилл CSV + первичный ингест мира."""
    def _run():
        from app.services.macro_ingest import (seed_indicators, backfill_from_csv,
                                               ingest_all_world, backfill_cbr_currency_history)
        from app.services.macro_analytics import process as analytics_process
        from app.services.macro_interpreter import get_latest, generate
        from app.services.macro_cb_sync import sync_cb
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from app.models.macro import MacroDataPoint
            seed_indicators(db)
            backfill_from_csv(db)
            sync_cb(db)  # ставка + прогноз ЦБ + свежая инфляция — РАНО (видимо владельцу)
            try:
                from app.services.macro_rosstat import ingest_rosstat_file
                ingest_rosstat_file(db)  # Росстат: ручная выгрузка из fedstat (machine-путь за WAF)
            except Exception as e:  # noqa: BLE001
                logger.warning("Старт: Росстат файл-ингест не выполнен: %s", e)
            ingest_all_world(db)
            # история курсов — только если ещё не залита (3000 точек, не гонять каждый старт)
            if db.query(MacroDataPoint).filter_by(indicator_code="usdrub").count() < 300:
                backfill_cbr_currency_history(db)
            analytics_process(db)
            # Первичная интерпретация (G) — только если ещё нет (Pro reasoning дорогой;
            # дальше обновляется по кнопке/расписанию, не на каждом старте).
            if get_latest(db) is None:
                try:
                    generate(db)
                except Exception as e:  # noqa: BLE001
                    logger.warning("Старт: интерпретация не сгенерирована: %s", e)
        finally:
            db.close()
    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Макрообзор: старт-наполнение завершено")
    except Exception as e:
        logger.exception("Ошибка старт-наполнения Макрообзора: %s", e)


async def _selftest_startup():
    """Через 25с после старта бьём в собственный uvicorn (localhost) и пишем результат
    в ЛОГ — чтобы факт «отдаёт ли бэк ответ изнутри» пришёл сам, без ручной проверки.
    Если localhost быстро 200 → код здоров, виновата отдача наружу (прокси Timeweb)."""
    await asyncio.sleep(25)
    import time as _t
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as c:
            for p in ("/api/screener/scored?universe=all", "/api/companies", "/api/market/indices"):
                t0 = _t.monotonic()
                try:
                    r = await c.get(f"http://127.0.0.1:8000{p}")
                    logger.info("SELFTEST %s → code=%s time=%.2fs size=%d enc=%s",
                                p, r.status_code, _t.monotonic() - t0, len(r.content),
                                r.headers.get("content-encoding"))
                except Exception as e:  # noqa: BLE001
                    logger.warning("SELFTEST %s → %s после %.2fs", p, type(e).__name__, _t.monotonic() - t0)
    except Exception as e:  # noqa: BLE001
        logger.warning("SELFTEST не выполнен: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Под тестами (pytest) НЕ запускаем планировщик и старт-задачи: они ходят в сеть
    # и зовут LLM (ингест/новости/аналитика), что недопустимо в тестовом прогоне.
    import sys
    if "pytest" in sys.modules or os.environ.get("DISABLE_SCHEDULER"):
        logger.info("Планировщик/старт-задачи отключены (тест/флаг)")
        yield
        return
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(_quotes_job, "interval", minutes=5, id="quotes_update")
    # История: раз в день после закрытия торгов (19:30 МСК) докачиваем
    # пропущенные дни и финализируем live-снапшоты официальными свечами.
    scheduler.add_job(_history_job, "cron", hour=19, minute=30, id="history_catchup")
    # Официальные беты MOEX — раз в неделю (файл обновляется нерегулярно)
    scheduler.add_job(_coefficients_job, "cron", day_of_week="mon", hour=8, minute=30, id="moex_coefficients")
    # Данные классов активов (облигации/фьючерсы/фонды) — ежедневное обновление
    # утром; плюс разовый прогон при старте (ниже) для авто-наполнения после деплоя.
    scheduler.add_job(_asset_data_job, "cron", hour=6, minute=0, id="asset_data_refresh")
    # Календарь событий — НАМЕРЕННО отдельный крон от asset_data_refresh (см.
    # docstring _calendar_job): раньше был хвостом asset_data_job и часто не
    # успевал выполниться при рестартах контейнера — дивиденды/отчётность/
    # корпсобытия месяцами не обновлялись. Отдельное время (после asset_data,
    # но не зависит от его завершения).
    scheduler.add_job(_calendar_job, "cron", hour=6, minute=45, id="calendar_refresh")

    # LLM/FRED-задачи (новости, макро-мир, отчёты, геополитика) ходят в DeepSeek и FRED.
    # ИСТОРИЧЕСКИ были выключены по умолчанию — на момент внедрения DeepSeek/FRED были
    # недоступны с этого инстанса (ConnectTimeout), задача висела ~24с, держа соединение
    # БД, и витринные запросы подвисали. С тех пор внешняя связность ВОССТАНОВИЛАСЬ
    # (подтверждено /api/debug/connectivity: deepseek/fred reachable=true) — держать их
    # выключенными означает, что лента новостей/отчёты/геополитика НИКОГДА не обновляются
    # сами, вопреки принципу самоподдерживающейся системы. Поэтому теперь ВКЛЮЧЕНЫ по
    # умолчанию; если внешняя связность снова пропадёт — выключить явно DISABLE_EXTERNAL_JOBS=1.
    if os.environ.get("DISABLE_EXTERNAL_JOBS") == "1":
        logger.info("Внешние LLM/FRED-задачи (news/macro/earnings/geo) ОТКЛючены явно (DISABLE_EXTERNAL_JOBS=1)")
    else:
        scheduler.add_job(_news_job, "cron", hour="7,13,19,1", minute=0, id="news_feed")
        scheduler.add_job(_macro_job, "cron", hour=6, minute=30, id="macro_ingest")
        scheduler.add_job(_macro_interpretation_job, "cron", hour=7, minute=15, id="macro_interpretation")
        scheduler.add_job(_earnings_job, "cron", hour=20, minute=30, id="earnings_digest")
        scheduler.add_job(_report_watch_job, "cron", hour=20, minute=45, id="report_watch")
        scheduler.add_job(_geo_job, "cron", hour=21, minute=0, id="geopolitics")
        scheduler.add_job(_geo_digest_job, "cron", minute=10, id="geo_digest")  # каждый час
        logger.info("Внешние LLM/FRED-задачи планировщика включены (news/macro/earnings/geo/geo_digest)")
    scheduler.start()
    logger.info("Планировщик котировок запущен (каждые 5 мин, умный интервал; история — 19:30 МСК)")

    # Лёгкие/локальные старт-задачи (быстро освобождают соединение БД) — всегда.
    asyncio.create_task(_tinkoff_warmup())
    asyncio.create_task(_seed_shares_startup())
    asyncio.create_task(_instrument_history_startup())
    asyncio.create_task(_risk_metrics_startup())
    asyncio.create_task(_selftest_startup())
    # _screener_warm НЕ запускаем при старте: расчёт скоринга 262 компаний на 1-CPU
    # инстансе захватывает ядро (GIL) и морозит весь процесс на десятки секунд →
    # health-check Timeweb не отвечает → перезапуск → снова warm → петля, при которой
    # сайт никогда не грузится. Скоринг считается ЛЕНИВО при первом запросе и кэшируется
    # надолго (_RESULT_TTL), дальше stale-while-revalidate отдаёт мгновенно.
    if os.environ.get("RUN_SCREENER_WARM") == "1":
        asyncio.create_task(_screener_warm())

    # Тяжёлые задачи с ВНЕШНИМИ API (DeepSeek/FRED/массовый MOEX). На инстансе без
    # внешнего доступа они ВИСЯТ на таймаутах, УДЕРЖИВАЯ соединение БД → пул
    # исчерпывается → ВСЕ вкладки виснут на «загружаем». Данные уже в БД; их
    # обновление идёт по КРОНУ (scheduler выше), поэтому при старте их НЕ дёргаем.
    # Включить разовый прогон при старте можно флагом RUN_STARTUP_JOBS=1.
    if os.environ.get("RUN_STARTUP_JOBS") == "1":
        asyncio.create_task(_asset_data_job())
        asyncio.create_task(_news_job())
        asyncio.create_task(_macro_startup())
        asyncio.create_task(_earnings_startup())
        asyncio.create_task(_geo_startup())

    yield
    scheduler.shutdown()


app = FastAPI(title="Investment Platform API", lifespan=lifespan)


# Корень '/' — для ДЕФОЛТНОГО liveness-пинга платформы (Timeweb шлёт HEAD/GET на '/'
# даже без настроенного health-path). Без этого роута '/' → 404/405, платформа считает
# контейнер нездоровым и УБИВАЕТ его → бесконечная петля перезапусков, при которой
# сайт не грузится. async + без БД — отвечает мгновенно всегда.
@app.get("/")
@app.head("/")
async def _root():
    return {"status": "ok", "service": "basis-api"}


# GZip ВКЛЮЧЁН (по умолчанию). Замер с внешнего узла показал: прокси Timeweb не отдаёт
# наружу БОЛЬШИЕ ответы (code=000, таймаут), а мелкие (/api/health) отдаёт → лимит/
# буферизация прокси по размеру. Сжатие держит ответы мелкими (companies ~150КБ→~20КБ,
# scored ~1МБ→~150КБ) → проходят через прокси. minimum_size=500 — сжимать почти всё.
# Отключить при необходимости: DISABLE_GZIP=1.
if os.environ.get("DISABLE_GZIP") != "1":
    from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
    app.add_middleware(GZipMiddleware, minimum_size=500)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://inbasis.ru",
        "https://www.inbasis.ru",
    ],
    # Разрешаем любой поддомен inbasis.ru и twc1.net (фронт + домены бэка) — на случай
    # рассогласования origin после пересоздания приложения и preflight-проблем.
    allow_origin_regex=r"https://([a-z0-9-]+\.)*(inbasis\.ru|twc1\.net)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(portfolios_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(debug_router, prefix="/api")
app.include_router(bonds_router, prefix="/api")
app.include_router(futures_router, prefix="/api")
app.include_router(funds_router, prefix="/api")
app.include_router(spot_router, prefix="/api")
app.include_router(options_router, prefix="/api")
app.include_router(screener_router, prefix="/api")
app.include_router(macro_router, prefix="/api")
app.include_router(observer_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "Backend is working"}
