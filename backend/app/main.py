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
    try:
        from app.services.asset_data import refresh_all_if_stale
        await asyncio.get_event_loop().run_in_executor(None, refresh_all_if_stale)
    except Exception as e:
        logger.exception("Ошибка авто-обновления данных классов активов: %s", e)


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


async def _macro_job():
    """Макрообзор: дневной ингест мира/курсов (ЦБ+FRED+World Bank) + сид справочника.
    Числовые ряды из Ленты приходят отдельно (в news-пайплайне). В executor-потоке."""
    def _run():
        from app.services.macro_ingest import seed_indicators, ingest_all_world, check_staleness
        from app.services.macro_analytics import process as analytics_process
        from app.services.macro_cb_sync import sync_cb
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from app.services.macro_rosstat import ingest_fedstat
            seed_indicators(db)
            world = ingest_all_world(db)
            cb = sync_cb(db)  # ЦБ: ставка/прогноз/инфляция/ожидания/M2 (машинный первоисточник)
            ros = ingest_fedstat(db)  # Росстат через fedstat (безработица/ИЦП/реальная зарплата)
            analytics = analytics_process(db)
            stale = check_staleness(db)  # алерт по рядам, которые перестали обновляться
            return {"world": world, "cb": cb, "rosstat": ros, "analytics": analytics, "stale": len(stale)}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Макрообзор: ингест мира/курсов — %s", res)
    except Exception as e:
        logger.exception("Ошибка ингеста Макрообзора: %s", e)


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
                from app.services.macro_rosstat import ingest_fedstat
                ingest_fedstat(db)  # Росстат через fedstat (доступен с боя; safeguards внутри)
            except Exception as e:  # noqa: BLE001
                logger.warning("Старт: fedstat-ингест не выполнен: %s", e)
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
    # Лента новостей Обозревателя — 4 раза/сутки (07:00/13:00/19:00/01:00 МСК).
    scheduler.add_job(_news_job, "cron", hour="7,13,19,1", minute=0, id="news_feed")
    # Макрообзор — раз в сутки (мир/FRED/WB) + курсы ЦБ ежедневно утром.
    scheduler.add_job(_macro_job, "cron", hour=6, minute=30, id="macro_ingest")
    # История: раз в день после закрытия торгов (19:30 МСК) докачиваем
    # пропущенные дни и финализируем live-снапшоты официальными свечами.
    scheduler.add_job(_history_job, "cron", hour=19, minute=30, id="history_catchup")
    # Официальные беты MOEX — раз в неделю (файл обновляется нерегулярно)
    scheduler.add_job(_coefficients_job, "cron", day_of_week="mon", hour=8, minute=30, id="moex_coefficients")
    # Данные классов активов (облигации/фьючерсы/фонды) — ежедневное обновление
    # утром; плюс разовый прогон при старте (ниже) для авто-наполнения после деплоя.
    scheduler.add_job(_asset_data_job, "cron", hour=6, minute=0, id="asset_data_refresh")
    scheduler.start()
    logger.info("Планировщик котировок запущен (каждые 5 мин, умный интервал; история — 19:30 МСК)")

    asyncio.create_task(_tinkoff_warmup())
    # Авто-наполнение данных классов активов при старте (в фоне, грузит только
    # пустое/устаревшее) — чтобы после деплоя данные оказались на бою без ручной
    # команды import_data.sh.
    asyncio.create_task(_asset_data_job())
    # Разовый прогон ленты новостей при старте (в фоне): после деплоя лента
    # наполняется сразу, не дожидаясь крона. Дедуп по source_url не даёт повторной
    # обработки при рестартах.
    asyncio.create_task(_news_job())
    asyncio.create_task(_macro_startup())

    yield
    scheduler.shutdown()


app = FastAPI(title="Investment Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://inbasis.ru",
        "https://www.inbasis.ru",
        "https://nikitasoin-basis-a279.twc1.net",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/")
def root():
    return {"status": "Backend is working"}
