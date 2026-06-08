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


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(_quotes_job, "interval", minutes=5, id="quotes_update")
    # История: раз в день после закрытия торгов (19:30 МСК) докачиваем
    # пропущенные дни и финализируем live-снапшоты официальными свечами.
    scheduler.add_job(_history_job, "cron", hour=19, minute=30, id="history_catchup")
    # Официальные беты MOEX — раз в неделю (файл обновляется нерегулярно)
    scheduler.add_job(_coefficients_job, "cron", day_of_week="mon", hour=8, minute=30, id="moex_coefficients")
    scheduler.start()
    logger.info("Планировщик котировок запущен (каждые 5 мин, умный интервал; история — 19:30 МСК)")

    asyncio.create_task(_tinkoff_warmup())

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


@app.get("/")
def root():
    return {"status": "Backend is working"}
