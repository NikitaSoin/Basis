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
from app.api.debug import router as debug_router, open_router as debug_open_router
from app.api.events import router as events_router
from app.api.bonds import router as bonds_router
from app.api.futures import router as futures_router
from app.api.funds import router as funds_router
from app.api.spot import router as spot_router
from app.api.options import router as options_router
from app.api.screener import router as screener_router
from app.api.macro import router as macro_router
from app.api.observer import router as observer_router
from app.api.assistant import router as assistant_router
from app.api.stress import router as stress_router
from app.api.agents import router as agents_router
# Мягкий импорт (timeweb-uneven-file-rollout): модуль новый, при неравномерной
# раскатке файлов его может ещё не быть — бэк не должен падать целиком.
try:
    from app.api.geo_tiles import router as geo_tiles_router
except Exception:  # noqa: BLE001
    geo_tiles_router = None

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
        from app.services.moex_dividends import (
            sync_dividends_for, sync_dividends_from_listing, update_risk_free_rate)
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
            # Мост «календарь → история». ISS перестал отдавать свежие выплаты (на
            # бою ноль записей за 200 дней, за 2026 год ни одной ни по одному
            # тикеру), а в календаре события smart-lab идут до сентября 2026.
            # Переносим прошедшие отсечки в историю, иначе дивдоходность и полная
            # доходность портфеля считаются по данным годичной давности.
            try:
                sync_dividends_from_listing(db)
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("Дивиденды из листинга: сбой")
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


def _with_heartbeat(job_id: str, fn):
    """Обёртка кронов для мониторинга (фаза 6 плана автономности, job_heartbeat.py).
    Джобы ловят свои исключения сами (logger.exception внутри) — поэтому обёртка
    фиксирует факт «прогон-функция выполнилась до конца» (liveness): молчаливо
    стоящий крон перестаёт тикать и всплывает в /api/debug/jobs-health как stale.
    Точная фиксация ошибок — точечными hb_err() внутри джобов, добавляется
    инкрементально."""
    async def _wrapped():
        from app.services.job_heartbeat import hb_ok, hb_err
        try:
            await fn()
            hb_ok(job_id)
        except Exception as e:  # джоб выбросил наружу (редкость) — тоже фиксируем
            hb_err(job_id, e)
            raise
    return _wrapped


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
        from app.services.job_heartbeat import hb_err
        hb_err("news_feed", e)
        return
    # 🔴 Найдено на бою 2026-07-29 (жалоба владельца — Сбер/Яндекс отчитались с
    # утра, разбора на платформе не было весь день): раньше report_watch ждал
    # СВОЙ следующий суточный тик крона, даже если новость о вышедшем отчёте
    # только что легла в Ленту. Теперь — сразу после каждого прогона Ленты
    # (раз в час) проверяем, не появилось ли в ЭТОМ прогоне что-то похожее на
    # новость об отчётности (тот же строгий детект-паттерн, что у report_watch),
    # и если да — запускаем report_watch НЕМЕДЛЕННО, не дожидаясь его планового
    # тика (см. также report_watch cron — теперь раз в 2 часа, а не раз в сутки,
    # как второй, независимый слой защиты от той же гонки).
    try:
        await _maybe_trigger_report_watch_now()
    except Exception as e:  # noqa: BLE001
        logger.exception("Ошибка мгновенного триггера report_watch по Ленте: %s", e)


async def _maybe_trigger_report_watch_now():
    def _check_and_run():
        from datetime import datetime, timezone, timedelta
        from app.db.session import SessionLocal
        from app.models.market import MarketUpdate
        from app.services.report_watch import _NEWS_REPORT_DETECT_RE, refresh
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=90)
            rows = (db.query(MarketUpdate)
                    .filter(MarketUpdate.status == "published", MarketUpdate.created_at >= cutoff)
                    .all())
            hit = any(_NEWS_REPORT_DETECT_RE.search(f"{r.title} {r.summary or ''}") for r in rows)
            if not hit:
                return None
            logger.info("Лента новостей: похоже на новость об отчётности — запускаю report_watch немедленно")
            return refresh(db, days_back=2)
        finally:
            db.close()
    res = await asyncio.get_event_loop().run_in_executor(None, _check_and_run)
    if res is not None:
        logger.info("report_watch (мгновенный запуск по свежей новости): %s", res)


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
        from app.services.macro_ingest import (seed_indicators, ingest_all_world,
                                               check_staleness, apply_known_corrections)
        from app.services.macro_analytics import process as analytics_process
        from app.services.macro_cb_sync import sync_cb
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            from app.services.macro_rosstat import ingest_rosstat_file, sync_ppi
            from app.services.macro_minfin_sync import sync_gov_spending
            from app.services.macro_hh_sync import sync_hh_index
            from app.services.macro_oil_sync import sync_oil_prices
            from app.services.macro_wb_commodities_sync import sync_wb_commodities
            from app.services.macro_yahoo_commodities_sync import sync_yahoo_commodities
            from app.services.macro_metaltorg_steel_sync import sync_metaltorg_steel
            from app.services.macro_idex_diamond_sync import sync_idex_diamond
            seed_indicators(db)
            # Адресные исправления точек (сверены с первоисточником) — ДО ингеста, чтобы
            # верное значение было на месте, даже если очередной источник промолчит.
            try:
                corrections = apply_known_corrections(db)
            except Exception:  # noqa: BLE001
                logger.warning("Макрообзор: исправления точек не применились", exc_info=True)
                corrections = {"applied": 0}
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
                # Brent/WTI/Urals + дисконт Urals-Brent. Раньше здесь был TankerMap,
                # но его фид давал Urals $60,7 при рыночных $84,6 (см. macro_oil_sync).
                urals = sync_oil_prices(db)
                # Официальный спот EIA (Brent/WTI) — авторитетный якорь ряда;
                # выходит с задержкой и перекрывает оперативную точку, когда доходит.
                from app.services.macro_oil_sync import sync_eia_spot
                eia_oil = sync_eia_spot(db)
            except Exception as e:  # noqa: BLE001
                logger.exception("TankerMap-Urals упал: %s", e)
                db.rollback()
                urals = {"error": f"unhandled:{type(e).__name__}"}
            try:
                wb_comm = sync_wb_commodities(db)  # WB Pink Sheet — месячные цены сырья без живого биржевого ряда
            except Exception as e:  # noqa: BLE001
                logger.exception("WB Pink Sheet-sync упал: %s", e)
                db.rollback()
                wb_comm = {"error": f"unhandled:{type(e).__name__}"}
            try:
                yahoo_comm = sync_yahoo_commodities(db)  # палладий — см. докстринг, источник неофициальный
            except Exception as e:  # noqa: BLE001
                logger.exception("Yahoo Finance-sync упал: %s", e)
                db.rollback()
                yahoo_comm = {"error": f"unhandled:{type(e).__name__}"}
            try:
                from app.services.macro_cb_monetary_sync import sync_monetary_aggregates
                monetary = sync_monetary_aggregates(db)   # M0/M1/M2/M2X из файла ЦБ
            except Exception as e:  # noqa: BLE001
                logger.exception("ЦБ денежные агрегаты-sync упал: %s", e)
                db.rollback()
                monetary = {"error": f"unhandled:{type(e).__name__}"}
            try:
                metaltorg = sync_metaltorg_steel(db)  # рос. цены стали — см. докстринг, источник неофициальный
            except Exception as e:  # noqa: BLE001
                logger.exception("metaltorg.ru-sync упал: %s", e)
                db.rollback()
                metaltorg = {"error": f"unhandled:{type(e).__name__}"}
            try:
                idex = sync_idex_diamond(db)  # алмазы АЛРОСА — см. докстринг, источник неофициальный
            except Exception as e:  # noqa: BLE001
                logger.exception("IDEX Diamond Index-sync упал: %s", e)
                db.rollback()
                idex = {"error": f"unhandled:{type(e).__name__}"}
            analytics = analytics_process(db)
            stale = check_staleness(db)  # алерт по рядам, которые перестали обновляться
            return {"corrections": corrections,
                    "world": world, "cb": cb, "rosstat": ros, "ppi": ppi, "minfin": minfin,
                    "hh": hh, "urals": urals, "wb_commodities": wb_comm, "yahoo_commodities": yahoo_comm,
                    "monetary_agg": monetary, "metaltorg_steel": metaltorg, "idex_diamond": idex,
                    "analytics": analytics, "stale": len(stale)}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Макрообзор: ингест мира/курсов — %s", res)
    except Exception as e:
        logger.exception("Ошибка ингеста Макрообзора: %s", e)


async def _macro_rate_watch_job():
    """Лёгкая ПОЧАСОВАЯ проверка ставки/прогноза ЦБ — отдельно от тяжёлого _macro_job
    (06:30, раз в сутки). Заседания ЦБ проходят днём (пресс-конференция обычно
    ~13:30 МСК) — суточный крон в 06:30 УЖЕ ПРОШЁЛ к этому моменту, следующий только
    через сутки. Найдено на бою 2026-07-25: заседание 24 июля, решение и на следующий
    день не подтянулось — карточка ставки показывала предыдущее заседание (19 июня)
    целые сутки. sync_rate_meeting/sync_forecast — один лёгкий фетч страницы + один
    LLM-вызов (Flash) каждая, дёшево гонять почасово весь день (не только в окно
    заседания — точный час пресс-конференции от заседания к заседанию плавает)."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_cb_sync import sync_rate_meeting, sync_forecast
        db = SessionLocal()
        try:
            rate = sync_rate_meeting(db)
            forecast = sync_forecast(db)
            return {"rate": rate, "forecast": forecast}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Почасовая проверка ставки ЦБ: %s", res)
        # 🔴 Перепрогон «Оценки ситуации» по НОВОМУ решению ЦБ (заказ владельца
        # 2026-08-01): «не пересчёт, а перепрогон просто с учётом новых вводных —
        # может, что-то изменилось, а может, ничего». Суточный крон стоит в 07:15, а
        # заседание проходит днём — без этого блок сутки рассуждал бы о ставке,
        # которой уже нет. Триггер узкий: только когда появилось НОВОЕ заседание
        # (action=inserted), не на каждое почасовое уточнение полей.
        if (res or {}).get("rate", {}).get("action") == "inserted":
            logger.info("Новое решение ЦБ — перепрогоняю макро-интерпретацию")
            await _macro_interpretation_job()
    except Exception as e:
        logger.exception("Ошибка почасовой проверки ставки ЦБ: %s", e)


async def _report_fetch_job():
    """Прод-добытчик отчётных релизов (report_fetcher_job: код + DeepSeek, источники
    smart-lab/Лента; владелец 2026-07-31 — «только на дипсик», облачная Claude-рутина
    отключена). Идёт ПОСЛЕ каскадного report_watch: добирает то, что осталось без
    источника или без выручки."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.report_fetcher_job import fetch_missing_reports
        db = SessionLocal()
        try:
            return fetch_missing_reports(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        if res.get("status") != "empty":
            logger.info("Добытчик релизов: %s", res)
    except Exception as e:
        logger.exception("Ошибка добытчика релизов: %s", e)


async def _macro_levels_job():
    """Уровни в триллионах (денежные агрегаты, ВВП в текущих ценах) и темпы по ним.

    Раз в сутки: показатели месячные и квартальные, внутри стоит проверка свежести —
    в обычный день прогон стоит пары SELECT.
    """
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_levels_watch import watch_levels
        db = SessionLocal()
        try:
            return watch_levels(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Уровни макро: %s", res)
    except Exception as e:
        logger.exception("Ошибка добора уровней макро: %s", e)


async def _weekly_inflation_watch_job():
    """Целевой ловец недельной инфляции (macro_weekly_watch.py). Идемпотентен:
    точка за ожидаемый понедельник уже есть → один SELECT и выход; нет → узкая
    добыча из своей Ленты (только «инфляц»-новости) с жёсткой валидацией недели
    и диапазона + фолбэк на Росстат с браузерным UA."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_weekly_watch import watch_weekly_inflation
        db = SessionLocal()
        try:
            return watch_weekly_inflation(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        if res.get("status") != "ok":
            logger.info("Ловец недельной инфляции: %s", res)
    except Exception as e:
        logger.exception("Ошибка ловца недельной инфляции: %s", e)


async def _macro_verification_job():
    """«ОТК данных» Макрообзора (владелец, 2026-07-25): ежедневная проверка, что
    данные верные и свежие — календарь заседаний ЦБ, кросс-сверка с независимыми
    источниками (hd_base-таблицы ЦБ, MOEX ISS, пресс-релиз, PDF инФОМ), лимиты
    скачков. Только сигналит (пишет macro_verifications → плашка в Обозревателе),
    данные НЕ правит. Вечером — после всех дневных синков (06:30 macro_ingest,
    почасовой macro_rate_watch). Без LLM — дёшево."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_verification import run_verification
        db = SessionLocal()
        try:
            return run_verification(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("ОТК данных: %s", res)
    except Exception as e:
        logger.exception("Ошибка ОТК данных: %s", e)
        from app.services.job_heartbeat import hb_err
        hb_err("macro_verification", e)


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


async def _agent_pilot_job():
    """Пилот автономных агентов (фазы 2-4 «пути к автономной платформе»):
    ежедневный макро-addendum для тикеров из AGENT_PILOT_TICKERS (по умолчанию
    KLSB — малая капитализация, владелец 2026-07-18). Один прогон = один вызов
    tool-loop с закодированными лимитами (max_steps/токен-бюджет) + автогейт
    перед публикацией — см. app/services/macro_addendum_agent.py."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_addendum_agent import run_macro_addendum
        tickers = [t.strip().upper() for t in
                   os.environ.get("AGENT_PILOT_TICKERS", "KLSB").split(",") if t.strip()]
        out = []
        db = SessionLocal()
        try:
            for t in tickers[:5]:  # жёсткий потолок пилота
                row = run_macro_addendum(db, t)
                out.append(f"{t}:{row.status}")
        finally:
            db.close()
        return out
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Агент-пилот (macro_addendum): %s", res)
    except Exception as e:
        logger.exception("Ошибка агент-пилота: %s", e)
        from app.services.job_heartbeat import hb_err
        hb_err("agent_pilot", e)


async def _chronicle_maintenance_job():
    """Дневное обслуживание аналитической летописи: (1) ретеншен Ленты (удалить
    market_updates старше окна, важное сперва страхуется в летопись), (2) идемпотентный
    catch-up бэкфилл (подобрать то, что могло не долететь в летопись из живых кронов)."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.news_pipeline import cleanup_market_updates
        from app.services.chronicle import backfill
        db = SessionLocal()
        try:
            bf = backfill(db)          # сначала гарантируем полноту летописи
            cl = cleanup_market_updates(db)  # затем безопасно чистим Ленту
            return {"backfill": bf, "cleanup": cl}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Летопись/обслуживание: %s", res)
    except Exception as e:
        logger.exception("Ошибка обслуживания летописи: %s", e)
        from app.services.job_heartbeat import hb_err
        hb_err("chronicle_maintenance", e)


async def _report_watch_job():
    """Автообнаружение вышедших отчётов (report_watch.py) — НЕЗАВИСИМО от _earnings_job:
    тот видит новый период только после РУЧНОГО обновления financials.json, этот детектит
    сам факт выхода отчёта по MOEX ir-calendar и разбирает по тексту из Ленты/СКРИН, без
    ожидания аналитика. Раз в 2 часа (было раз в сутки — владелец 2026-07-29, см.
    _maybe_trigger_report_watch_now для мгновенного триггера по свежей новости) —
    второй, независимый слой защиты от гонки «новость об отчёте вышла позже, чем
    успел проверить крон» для путей, которые не идут через Ленту (MOEX ir-calendar,
    ГИР БО)."""
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


async def _sector_tr_backfill_startup():
    """Первичный бэкфилл отраслевых TR-индексов (см. moex_history.SECTOR_TR_TICKERS,
    смешанный бенчмарк «по весам портфеля» в portfolio.py) — идемпотентно, только
    для тикеров, которых ещё нет в index_history. Тот же паттерн безопасности, что
    _instrument_history_startup: дальше докачивает ежедневный _history_job."""
    def _run():
        from app.services.moex_history import backfill_sector_tr_indices
        backfill_sector_tr_indices(years_back=3)
    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as e:
        logger.exception("Ошибка бэкфилла отраслевых TR-индексов: %s", e)


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


async def _macro_gap_agent_job():
    """Агент-добытчик чинит дыры в макро-рядах ДО утреннего выпуска.

    🔴 Порядок в расписании важен: 06:30 ингест → 06:50 агент → 07:15 интерпретация.
    Чинить данные после генерации бессмысленно — выпуск уже посчитан по устаревшим
    рядам (безработица уходила в прогноз с задержкой в 94 дня).

    Контур: код находит дыру → добытчик ищет (сначала наша лента, потом веб) →
    факт-чекер подтверждает НЕЗАВИСИМЫМ источником → точка пишется. Существующие
    точки не перезаписываются никогда. Лимит на раунд маленький: это регулярная
    чистка по чуть-чуть, каждая дыра — два агентских прогона.
    """
    def _run():
        from app.db.session import SessionLocal
        from app.services.macro_gap_pipeline import run_round
        db = SessionLocal()
        try:
            return run_round(db, limit=int(os.environ.get("MACRO_GAP_LIMIT", "3")))
        finally:
            db.close()
    try:
        out = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Агент-добытчик: закрыто дыр %s из %s вопросов",
                    (out or {}).get("written"), (out or {}).get("questions"))
    except Exception as e:
        logger.exception("Ошибка агента-добытчика макроданных: %s", e)


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


async def _geo_profile_job():
    """Портрет очагов (стороны/цели/баланс сил/связки с макро и институтами) —
    НЕДЕЛЬНЫЙ слой. Раз в неделю, а не ежедневно, намеренно: состав сторон и
    структурные связки меняются месяцами, ежедневная перегенерация давала бы
    шевеление текста без событий — см. докстринг geo_conflict_profile."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geo_conflict_profile import rebuild
        db = SessionLocal()
        try:
            row = rebuild(db)
            return f"версия {row.id} ({row.status})" if row else "не собрано"
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Портрет очагов: %s", res)
    except Exception as e:
        logger.exception("Ошибка портрета очагов: %s", e)


async def _overview_synthesis_job():
    """Свод вкладки «Обзор»: общий вывод по всем разборам + объяснение цены.

    🔴 Партиями по чуть-чуть, а не «собрать все 264 разом». Каждая компания — это
    отдельный прогон модели по семи разборам; очередь сама двигается (сначала те, у
    кого свода нет вовсе, потом самые старые), поэтому за неделю круг закрывается без
    единого тяжёлого прогона. Идёт ПОСЛЕ ночных доводок вкладок, чтобы свод собирался
    по уже освежённым разборам, а не по вчерашним.
    """
    def _run():
        from app.db.session import SessionLocal
        from app.services.overview_synthesis import run_batch
        db = SessionLocal()
        try:
            return run_batch(db, batch=8)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Свод «Обзора»: %s", res)
    except Exception as e:
        logger.exception("Ошибка свода «Обзора»: %s", e)


async def _stress_interpretation_job():
    """Качественный разбор сценариев стресс-теста (что значит для экономики, какие
    каналы включаются, кому тяжелее и чего расчёт не видит).

    Раз в неделю и партиями: набор пресетов фиксирован, экспозиции компаний меняются
    медленно, а вход разбора — своды карточек и барометры, которые тоже обновляются
    не ежедневно. Гонять модель на каждый заход пользователя на экран незачем: текст
    лежит в БД версиями, витрина читает последнюю опубликованную.
    """
    def _run():
        from app.db.session import SessionLocal
        from app.services.stress_interpreter import run_batch
        db = SessionLocal()
        try:
            return run_batch(db, batch=3)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Разбор сценариев стресс-теста: %s", res)
    except Exception as e:
        logger.exception("Ошибка разбора сценариев стресс-теста: %s", e)


async def _env_card_interp_job():
    """Доводка вкладок «Геополитика», «Институты» и «Макроэкономика» КАРТОЧЕК
    КОМПАНИЙ под текущее состояние Обозревателя (владелец 2026-08-04: «вкладка
    карточки должна обновляться с учётом оценки ситуации в Обозревателе и новых
    вводных»).

    Отдельно от run_weekly_interp: тот триггерится новостью ПРО КОМПАНИЮ, а
    среда меняется без таких новостей — сместился балл очага, поехали замеры
    направлений. Вкладки при этом молча устаревают.
    Идёт ПОСЛЕ недельных слоёв (портреты, замеры), чтобы править по свежему.

    🔴 Макро идёт здесь же, но с ДРУГОЙ очередью. Гео и институты берут кандидатов
    по кулдауну, а макро — из детектора дрейфа: наверх попадает тот, чей разбор
    разошёлся с реальностью ДОРОЖЕ ВСЕГО по его же коэффициентам чувствительности.
    Отдельно от run_macro_interp: тот правит вкладку под решение ЦБ, а нефть и курс
    (Brent с ~$69 к ~$90 за месяц) мимо той очереди проходили целиком."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import (
            run_geo_env_interp, run_inst_env_interp, run_macro_env_interp,
            run_markets_env_interp, run_gov_env_interp,
        )
        db = SessionLocal()
        try:
            return {"geo": run_geo_env_interp(db), "inst": run_inst_env_interp(db),
                    "macro": run_macro_env_interp(db),
                    # «Рынки» — четвёртая вкладка контура. Очередь у неё строится
                    # не «кого задевает среда», а «чья отрасль сдвинулась»:
                    # у сталеваров и золотодобытчиков среда РАЗНАЯ (в барометре
                    # 1.5/5 против 4.5/5), общей рамки для них не существует.
                    "markets": run_markets_env_interp(db),
                    # «Корпуправление» — пятая вкладка контура (владелец 2026-08-08).
                    # Среда правит здесь ТОЛЬКО оценку риска: структура собственности,
                    # дивполитика и совет — факты компании, замеры их не меняют.
                    "governance": run_gov_env_interp(db)}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Доводка вкладок карточек по среде: %s", res)
    except Exception as e:
        logger.exception("Ошибка доводки вкладок по среде: %s", e)


async def _institutions_profile_job():
    """«Институциональный портрет» — человеческий слой поверх барометра
    институтов (что происходит простыми словами, что это значит для денег,
    факторы в обе стороны, кто выигрывает и проигрывает, связки с макро и гео).
    НЕДЕЛЬНЫЙ, как и портрет очага: институциональная среда меняется медленно,
    ежедневная перегенерация давала бы шум вместо опоры."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.institutions_profile import rebuild
        db = SessionLocal()
        try:
            row = rebuild(db)
            return f"версия {row.id} ({row.status})" if row else "не собрано"
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Портрет институтов: %s", res)
    except Exception as e:
        logger.exception("Ошибка портрета институтов: %s", e)


async def _sector_data_job():
    """Сбор ОТРАСЛЕВЫХ показателей из источников реестра (СО ЕЭС, ЕРЗ, ФНС и др.).
    Ежедневно и ДО барометра: тот читает эти ряды как вход. Падение коллектора
    не роняет остальные — ряд просто останется без свежей точки, и барометр
    честно поставит «мало данных» вместо балла из воздуха."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.sector_data_sync import refresh_all
        db = SessionLocal()
        try:
            return refresh_all(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Отраслевые данные: %s", res)
    except Exception as e:
        logger.exception("Ошибка сбора отраслевых данных: %s", e)


async def _nonequity_facts_job():
    """Свежесть разборов ОБЛИГАЦИЙ и ФОНДОВ — та же болезнь, что у фьючерсов:
    разборы датированы началом июня и называют июньские числа текущими (ЦР БО-03:
    в тексте «YTM ~53%, цена ~78%», в базе 55.9% и 77.25). Для облигации доходность
    и есть предмет разбора, поэтому расхождение критично. Правим ЧИСЛА, не вердикт:
    вердикт «доходность за риск» считается по методике, а не из свежей цены."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_nonequity_facts
        db = SessionLocal()
        try:
            return {"bonds": run_nonequity_facts(db, "bond", batch=4),
                    "funds": run_nonequity_facts(db, "fund", batch=2)}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Свежесть облигаций и фондов: %s", res)
    except Exception as e:
        logger.exception("Ошибка свежести облигаций и фондов: %s", e)


async def _sector_scout_job():
    """Показатели, которых нет у парсеров, — через агента-добытчика.

    Раз в неделю и по чуть-чуть: у этих рядов данные месячные, чаще смысла нет. Числа
    помечаются `ingested_via='scout'` — они найдены в вебе, а не сняты с официальной
    страницы, и это видно в ряду."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.sector_scout import run_scout
        db = SessionLocal()
        try:
            # 🔴 ТОЛЬКО СУХОЙ ПРОГОН. Два прогона подряд по одному показателю дали
            # РАЗНЫЕ числа: пассажиропоток 30,8 (со ссылкой на AVIA.RU) и 39,5 (со
            # ссылкой на TKS.RU). Для ряда это дисквалифицирующий признак: значение,
            # которое меняется от прогона к прогону, нельзя писать в историю — оно
            # станет «фактом» и переживёт того, кто его добыл.
            # Пока нет ПОДТВЕРЖДЕНИЯ ВТОРЫМ ИСТОЧНИКОМ, крон только логирует, что
            # нашлось. Включать запись — отдельным решением, когда добавится сверка.
            return run_scout(db, dry=True)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Добор отраслевых показателей: %s", res)
    except Exception as e:
        logger.exception("Ошибка добора отраслевых показателей: %s", e)


async def _card_rewrite_job():
    """ТРЕТЬЯ СТУПЕНЬ: перезапись ВЫВОДА там, где цифра перевернула рассуждение.

    🔴 Батч намеренно крошечный (2 макро + 2 рынка за прогон, раз в неделю). Это не
    экономия, а осознанный темп: перезапись меняет СУЖДЕНИЕ на витрине, и её качество
    мы пока меряем поштучно. Советник прямо предупредил — расширять только когда
    challenger побеждает в 2/3 случаев при выборочной сверке; до тех пор больше
    правок в неделю означает больше непроверенного текста, а не больше пользы.

    Идёт ПОСЛЕ доводки патчером (env_card_interp, пн 6:40): сначала дешёвая ступень
    закрывает, что может, и её отказы становятся сигналом эскалации для этой.
    """
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_rewriter import run_macro_rewrites, run_markets_rewrites
        db = SessionLocal()
        try:
            from app.services.card_rewriter import run_tab_rewrites
            out = {"macro": run_macro_rewrites(db, batch=2),
                   "markets": run_markets_rewrites(db, batch=2)}
            # Остальные вкладки — тем же движком, но по своим сигналам. Батчи по
            # единице: у этих вкладок сигнал редкий (отчётный период или повторные
            # отказы патчера), и большой батч там просто нечем наполнить.
            for tab in ("finance", "geo", "institutions", "governance", "business"):
                try:
                    out[tab] = run_tab_rewrites(db, tab, batch=1)
                except Exception as e:  # noqa: BLE001 — одна вкладка не роняет прогон
                    out[tab] = {"error": f"{type(e).__name__}"}
            return out
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Перезапись выводов карточек: %s", res)
    except Exception as e:
        logger.exception("Ошибка перезаписи выводов: %s", e)


async def _futures_asset_facts_job():
    """Свежесть разборов базовых активов фьючерсов (владелец 2026-08-07: «чтобы в
    карточках по облигациям/фьючерсам/фондам информация обновлялась, а не была
    статичным json»). На бою 2026-08-08 разборы держали июньские цены как текущие —
    «Brent около $94» при фактических $82. Ежедневно утром: цена меняется каждый
    день, а разбор один на все контракты по активу."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_futures_asset_facts
        db = SessionLocal()
        try:
            return run_futures_asset_facts(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Свежесть активов фьючерсов: %s", res)
    except Exception as e:
        logger.exception("Ошибка свежести активов фьючерсов: %s", e)


async def _sector_digest_job():
    """Отраслевая лента: обзоры/прогнозы рынков от отраслевых источников (МЭА, ОПЕК,
    EIA, ассоциации). Владелец 2026-08-08: «нефть и газ — мировые рынки, источников
    накопать можно много; по этим обзорам, анализам, прогнозам должна собираться
    информация и карточки постоянно обновляться». Дважды в сутки: отраслевые обзоры
    выходят реже новостей, но ленту надо наполнить ДО недельной сборки барометра."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.sector_digest import refresh
        db = SessionLocal()
        try:
            return refresh(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Отраслевая лента: %s", res)
    except Exception as e:
        logger.exception("Ошибка отраслевой ленты: %s", e)


async def _sector_barometer_job():
    """Отраслевой барометр — состояние каждого сектора рынка РФ (владелец
    2026-08-07: «в бизнесе сделать оценку текущей ситуации: в каком состоянии
    банковский сектор, нефтегаз, металлургия чёрная и цветная и все остальные»).
    Недельный: отраслевой цикл не разворачивается за сутки. Идёт ПОСЛЕ замеров
    институтов и до портретов — он их потребитель по макро-рамке."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.sector_barometer import rebuild
        db = SessionLocal()
        try:
            row = rebuild(db)
            return f"версия {row.id}" if row else "не собрано"
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Отраслевой барометр: %s", res)
    except Exception as e:
        logger.exception("Ошибка отраслевого барометра: %s", e)


async def _institutions_domains_job():
    """Замеры качества институтов ПО НАПРАВЛЕНИЯМ (собственность, суды, госдоля,
    монополизация, конкуренция, регулирование, рыночные институты, конфликты
    бизнеса и государства, лоббизм). Владелец 2026-08-02: «нужны детальные
    отдельные проходы, чтобы видеть, есть ли институциональные изменения».
    Недельный: институт за неделю меняется редко, чаще гонять — ловить шум."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.institutions_domains import rebuild
        db = SessionLocal()
        try:
            row = rebuild(db)
            return f"версия {row.id}" if row else "не собрано"
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Замеры институтов по направлениям: %s", res)
    except Exception as e:
        logger.exception("Ошибка замеров институтов: %s", e)


async def _geo_verification_job():
    """«ОТК данных» геополитики — проверки БЕЗ LLM (живость конвейера,
    согласованность вероятностей, полнота секций). Вечером, ПОСЛЕ всей гео-цепочки,
    чтобы мерить то, что реально уехало на витрину."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geo_verification import run_verification
        db = SessionLocal()
        try:
            return run_verification(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("ОТК геополитики: %s %s", res.get("overall"), res.get("counts"))
    except Exception as e:
        logger.exception("Ошибка ОТК геополитики: %s", e)


async def _company_signals_job():
    """Сигнальная шина «поток Обозревателя → карточка компании» (владелец
    2026-07-27). Конвертирует Ленту (affected_tickers, без LLM) + дайджест
    (LLM-маппинг тикеров, вкл. инсайд-TG с internal-флагом) в company_signals.
    После news+geo_digest (их выход = вход шины)."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.company_signals import refresh
        db = SessionLocal()
        try:
            return refresh(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Сигнальная шина компаний: %s", res)
    except Exception as e:
        logger.exception("Ошибка сигнальной шины: %s", e)


async def _rating_agencies_job():
    """Ингестор рейтинговых действий АКРА/НКР → сигналы карточек + освежение
    официального рейтинга бумаг (владелец 2026-07-28: «рейтинговые агентства —
    первыми»). Официальное сырьё по облигациям: присвоение/подтверждение/
    повышение/понижение/дефолт по конкретному эмитенту. Внешние HTTP — в
    guarded-блоке, как news/report_watch."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.rating_agencies import refresh
        db = SessionLocal()
        try:
            return refresh(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Рейтинговые агентства: %s", res)
    except Exception as e:
        logger.exception("Ошибка ингестора рейтинговых агентств: %s", e)


async def _card_consumer_job():
    """Consumer-агент: точные сигналы (rating_action/earnings от офиц. источников)
    → датированный addendum на вкладке карточки под код-гейтом (владелец
    2026-07-28, дизайн ревью advisor). v1 БЕЛЫЙ СПИСОК источников, не importance —
    fuzzy-Лента в карточку не идёт. Публикация — по флагу CARD_CONSUMER_PUBLISH
    (по умолчанию draft/пред-полёт). После rating_agencies+company_signals."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_consumer_agent import run_consumer
        db = SessionLocal()
        try:
            return run_consumer(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Consumer-агент карточек: %s", res)
    except Exception as e:
        logger.exception("Ошибка consumer-агента карточек: %s", e)


async def _prose_patcher_job():
    """Авто-свежесть ПРОЗЫ вкладок — дневной проход ФАКТОВ (владелец 2026-07-29,
    docs/prose-freshness-plan.md). Очередь из входного потока (значимые офиц.
    сигналы) → точечный факт-патч прозы под код-гейтом (find/replace, число из
    источника), пишет в БД-оверлей (сразу published, без черновика). НЕ слепой
    прогон всех карточек. После company_signals/rating_agencies/card_consumer."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_daily_facts
        db = SessionLocal()
        try:
            return run_daily_facts(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Патчер прозы (факты): %s", res)
    except Exception as e:
        logger.exception("Ошибка патчера прозы: %s", e)


async def _macro_facts_job():
    """Мост «рынок → карточки»: устаревшие ставка/инфляция/ожидания в макро-прозе
    карточек → факт-патч от живых макро-рядов (card_prose_patcher.run_macro_facts;
    владелец 2026-07-31, кейс SBER/macro со ставкой 14,25 от 19 июня)."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_macro_facts
        db = SessionLocal()
        try:
            return run_macro_facts(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        if res.get("queued"):
            logger.info("Макро-факты карточек: %s", res)
    except Exception as e:
        logger.exception("Ошибка макро-фактов карточек: %s", e)


async def _macro_interp_job():
    """Смысловая доводка макро-вкладок (run_macro_interp): обороты, устаревшие по
    смыслу («может взять паузу», прошедшие заседания как будущие) → точечные правки
    от контекста решения ЦБ. Очередь — тикеры со свежим факт-патчем macro."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_macro_interp
        db = SessionLocal()
        try:
            return run_macro_interp(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        if res.get("queued"):
            logger.info("Макро-интерпретация карточек: %s", res)
    except Exception as e:
        logger.exception("Ошибка макро-интерпретации карточек: %s", e)


async def _prose_interp_job():
    """Авто-свежесть ПРОЗЫ — НЕДЕЛЬНЫЙ интерпретационный проход (владелец
    2026-07-29). По входному потоку недели дельта-правит интерпретацию ТОЛЬКО там,
    где поток изменил картину (не перегенерация), под гейтом → БД-оверлей."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.card_prose_patcher import run_weekly_interp
        db = SessionLocal()
        try:
            return run_weekly_interp(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Патчер прозы (интерпретация, недельный): %s", res)
    except Exception as e:
        logger.exception("Ошибка недельного патчера прозы: %s", e)


async def _barometer_expert_reimport_startup():
    """При старте: если экспертный файл барометра обновился (субагент + git push
    + деплой), апсертить его как новую source=expert/published версию в БД —
    так витрина (читающая published из БД) подхватывает ручное обновление, а
    поводок дрейфа авторевизий обнуляется. Идемпотентно по содержимому."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.barometer_store import reimport_expert
        db = SessionLocal()
        try:
            for kind in ("geo", "inst"):
                reimport_expert(db, kind)
        finally:
            db.close()
    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
    except Exception as e:
        logger.warning("Переимпорт экспертных барометров при старте не удался: %s", e)


async def _barometer_reviser_job():
    """Автономный ревизор барометров (гео/институты) — SHADOW-режим (владелец
    2026-07-27, план docs/autonomous-barometer-plan.md). Пишет draft/rejected,
    на бой НЕ публикует. Событийный: внутри run_all → should_revise проверяет
    триггеры от situation_overlay (сенсор), cooldown 5 дней. После оверлея
    (21:20) — читает его свежий вердикт как триггер."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.barometer_reviser import run_all
        db = SessionLocal()
        try:
            return run_all(db, force=False)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Ревизор барометров (shadow): %s", res)
    except Exception as e:
        logger.exception("Ошибка ревизора барометров: %s", e)


async def _barometer_daily_job():
    """ЕЖЕДНЕВНАЯ полная пересборка ГЕО-барометра (владелец 2026-08-01: «слой 1
    перестроить так же, как в макроэкономике — ежедневный крон, где DeepSeek всё
    обновляет»). Заменяет для гео событийный ревизор с поводком: модель каждый
    день пересобирает все 13 субиндексов, сценарии и вероятности целиком, опираясь
    на вчерашнюю версию и свежую ленту. Стоит ПОСЛЕ geo_digest/geopolitics — им
    нужен собранный за день поток. Fail-closed внутри rebuild()."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.barometer_daily import rebuild
        db = SessionLocal()
        try:
            row = rebuild(db)
            if row is None:
                return "лента пуста — барометр не трогали"
            return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Ежедневная пересборка гео-барометра: %s", res)
    except Exception as e:
        logger.exception("Ошибка ежедневной пересборки гео-барометра: %s", e)


async def _situation_overlay_job():
    """Оверлей «текущая ситуация по ленте» (гео 3 очага + институты). После
    _geo_job (21:00): тот же новостной поток digest, что уже собран за день,
    один вход → согласованный выход (advisor 2026-07-27 — не плодить третий
    расходящийся слой). Fail-closed внутри generate()."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.situation_overlay import generate
        db = SessionLocal()
        try:
            row = generate(db)
            return {"id": row.id, "published": row.published, "scopes": list((row.blocks or {}).keys())}
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Оверлей ситуации обновлён: %s", res)
    except Exception as e:
        logger.exception("Ошибка оверлея ситуации: %s", e)


async def _company_metrics_job():
    """company_metrics (скринер) ← файлы financials.json. Идемпотентно
    (ON CONFLICT DO UPDATE), чистое чтение файлов + upsert, без сети."""
    def _run():
        from scripts.sync_company_metrics import main as _sync
        _sync()
        return {"status": "ok"}
    try:
        await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("company_metrics синхронизированы из файлов аналитики")
    except Exception as e:
        logger.exception("Ошибка синка company_metrics: %s", e)


async def _geo_digest_job():
    """Дайджест отдельных статей (Рыбарь/re:russia/Economist → карточки по региону
    геополитики + институциональная среда). Часто (в отличие от _geo_job) —
    источники вроде Рыбаря публикуют постоянно, редкий крон вытесняет старые
    статьи новыми до синтеза."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geo_digest import refresh, extract_strikes_from_news
        db = SessionLocal()
        try:
            out = refresh(db)
            # Удары из ОБЩЕЙ ленты новостей (РБК/Интерфакс/Коммерсант) — гео-
            # источники дайджеста их не покрывают (кейс Тюменского НПЗ,
            # владелец 2026-07-26). Дедуп на persist-слое.
            try:
                out["news_strikes"] = extract_strikes_from_news(db, hours=3)
            except Exception:  # noqa: BLE001
                logger.warning("news-strikes проход не удался", exc_info=True)
            # «Взяли город — линия фронта сдвинулась»: если дайджест извлёк
            # новые territorial_claims, сразу пересинк линии, не ждём кронового
            # тика 8:15/20:15 (absorb_candidates читает claims из БД).
            if out.get("claims_saved"):
                try:
                    from app.services.geo_isw_frontline_sync import sync_isw_frontline
                    out["frontline_resync"] = sync_isw_frontline(db).get("status")
                except Exception:  # noqa: BLE001
                    logger.warning("пересинк линии после новых claims не удался", exc_info=True)
            return out
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Гео-дайджест обновлён: %s", res)
    except Exception as e:
        logger.exception("Ошибка обновления гео-дайджеста: %s", e)


async def _geo_frontline_sync_job():
    """Линия фронта СВО — живой пересчёт из ArcGIS-фида ISW (не LLM, чистая
    геометрия: shapely, без стоимости токенов). См. geo_isw_frontline_sync.py
    докстринг — почему ISW, а не DeepState/lostarmour/Рыбарь. Дважды в сутки:
    ISW публикует свою дневную оценку ~раз в сутки, запас на случай, если
    первый прогон дня попадёт до их публикации."""
    def _run():
        from app.db.session import SessionLocal
        from app.services.geo_isw_frontline_sync import sync_isw_frontline
        db = SessionLocal()
        try:
            return sync_isw_frontline(db)
        finally:
            db.close()
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, _run)
        logger.info("Линия фронта СВО (ISW-синк): %s", res)
    except Exception as e:
        logger.exception("Ошибка синка линии фронта СВО: %s", e)


async def _geo_frontline_sync_startup():
    """Разовый прогон при старте, только если ещё нет ни одной успешной
    записи — чтобы линия фронта была живой сразу после этого деплоя, не
    дожидаясь первого кронового окна (до 12 часов). НЕ гоняем при каждом
    рестарте контейнера (лишняя нагрузка на публичный эндпоинт ISW)."""
    def _has_data() -> bool:
        from app.db.session import SessionLocal
        from app.models.geo import GeoFrontlineSync
        db = SessionLocal()
        try:
            row = db.query(GeoFrontlineSync).filter_by(theater="svo").first()
            return bool(row and row.frontline_geojson)
        finally:
            db.close()
    try:
        if not await asyncio.get_event_loop().run_in_executor(None, _has_data):
            await _geo_frontline_sync_job()
    except Exception as e:  # noqa: BLE001
        logger.warning("Старт-проверка линии фронта СВО не выполнена: %s", e)


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
    scheduler.add_job(_with_heartbeat("quotes_update", _quotes_job), "interval", minutes=5, id="quotes_update")
    # История: раз в день после закрытия торгов (19:30 МСК) докачиваем
    # пропущенные дни и финализируем live-снапшоты официальными свечами.
    scheduler.add_job(_with_heartbeat("history_catchup", _history_job), "cron", hour=19, minute=30, id="history_catchup")
    # Синк company_metrics (скринер) из файлов financials.json — аудит
    # 2026-07-26 нашёл, что скрипт существовал ТОЛЬКО в ручном запуске и не
    # вызывался никем с июня: скринер расходился с карточкой по справедливой
    # цене у 95% компаний (медиана 32%). Раз в сутки после history_catchup +
    # прогон при старте (файлы аналитики приезжают с каждым деплоем).
    scheduler.add_job(_with_heartbeat("company_metrics_sync", _company_metrics_job),
                      "cron", hour=19, minute=50, id="company_metrics_sync")
    # Официальные беты MOEX — раз в неделю (файл обновляется нерегулярно)
    scheduler.add_job(_with_heartbeat("moex_coefficients", _coefficients_job), "cron", day_of_week="mon", hour=8, minute=30, id="moex_coefficients")
    # Данные классов активов (облигации/фьючерсы/фонды) — ежедневное обновление
    # утром; плюс разовый прогон при старте (ниже) для авто-наполнения после деплоя.
    scheduler.add_job(_with_heartbeat("asset_data_refresh", _asset_data_job), "cron", hour=6, minute=0, id="asset_data_refresh")
    # Календарь событий — НАМЕРЕННО отдельный крон от asset_data_refresh (см.
    # docstring _calendar_job): раньше был хвостом asset_data_job и часто не
    # успевал выполниться при рестартах контейнера — дивиденды/отчётность/
    # корпсобытия месяцами не обновлялись. Отдельное время (после asset_data,
    # но не зависит от его завершения).
    scheduler.add_job(_with_heartbeat("calendar_refresh", _calendar_job), "cron", hour=6, minute=45, id="calendar_refresh")
    # Линия фронта СВО из живого фида ISW — чистая геометрия (httpx+shapely),
    # НЕ LLM/DeepSeek, поэтому вне блока DISABLE_EXTERNAL_JOBS ниже. Дважды в
    # сутки — см. докстринг _geo_frontline_sync_job.
    scheduler.add_job(_with_heartbeat("geo_frontline_sync", _geo_frontline_sync_job), "cron", hour="8,20", minute=15, id="geo_frontline_sync")

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
        scheduler.add_job(_with_heartbeat("news_feed", _news_job), "cron", minute=5, id="news_feed")  # каждый час
        scheduler.add_job(_with_heartbeat("macro_ingest", _macro_job), "cron", hour=6, minute=30, id="macro_ingest")
        scheduler.add_job(_with_heartbeat("macro_rate_watch", _macro_rate_watch_job), "cron", minute=20, id="macro_rate_watch")  # почасово — ловит заседание ЦБ в тот же день
        # Целевой ловец недельной инфляции (владелец 2026-07-30: публикация стабильно в
        # среду во второй половине дня, а ряд дырявый — общая лента её пропускала).
        # ср 16-23 + чт/пт утро-день; внутри идемпотентный guard «точка есть → no-op»,
        # так что лишние прогоны бесплатны (один SELECT).
        scheduler.add_job(_with_heartbeat("macro_levels", _macro_levels_job),
                          "cron", hour=9, minute=15, id="macro_levels")
        scheduler.add_job(_with_heartbeat("weekly_inflation_watch", _weekly_inflation_watch_job),
                          "cron", day_of_week="wed,thu,fri", hour="8-23", minute=35,
                          id="weekly_inflation_watch")
        # Добытчик релизов — после каскадного report_watch (:45), в сезон отчётностей
        # добирает пропуски; вне сезона wishlist пуст и прогон = один SELECT.
        scheduler.add_job(_with_heartbeat("report_fetch", _report_fetch_job),
                          "cron", day_of_week="mon-fri", hour="10,17", minute=15,
                          id="report_fetch")
        scheduler.add_job(_with_heartbeat("macro_verification", _macro_verification_job), "cron", hour=18, minute=30, id="macro_verification")  # «ОТК данных» — вечером, после всех синков
        # 06:50 — между ингестом (06:30) и интерпретацией (07:15): данные чинятся ДО того,
        # как выпуск на них посчитается.
        scheduler.add_job(_with_heartbeat("macro_gap_agent", _macro_gap_agent_job), "cron", hour=6, minute=50, id="macro_gap_agent")
        scheduler.add_job(_with_heartbeat("macro_interpretation", _macro_interpretation_job), "cron", hour=7, minute=15, id="macro_interpretation")
        scheduler.add_job(_with_heartbeat("earnings_digest", _earnings_job), "cron", hour=20, minute=30, id="earnings_digest")
        # 🔴 Было раз в сутки (20:45) — владелец 2026-07-29: Сбер/Яндекс отчитались с
        # утра, разбора не было весь день (не считая мгновенного триггера по Ленте,
        # см. _maybe_trigger_report_watch_now). Раз в 2 часа — второй, независимый
        # слой защиты от той же гонки (напр. если новость пришла НЕ через Ленту, а
        # только через MOEX ir-calendar/ГИР БО, которые этот триггер не покрывает).
        scheduler.add_job(_with_heartbeat("report_watch", _report_watch_job), "cron", hour="*/2", minute=45, id="report_watch")
        # 🔴 Крон `geopolitics` (ежедневный слитый синтез в geo_blocks, Pro +
        # thinking) ВЫКЛЮЧЕН 2026-08-02. Его результат витрина не рисует с
        # 2026-08-01: карточка «Обзор · факты» удалена по просьбе владельца
        # («обобщённая проза модели, одинаковая по тону для всех трёх очагов»),
        # а список очагов фронт с этого коммита берёт из константы
        # GEO_REGION_META, а не из geo_blocks. То есть дорогой reasoning-прогон
        # каждый вечер уходил в никуда. Его бюджет занял недельный geo_profile,
        # результат которого на экране виден.
        # Сам сервис geopolitics.py и эндпоинт /market/geopolitics оставлены:
        # данные в geo_blocks лежат, ручной триггер работает — если формат
        # понадобится, достаточно вернуть строку ниже.
        # scheduler.add_job(_with_heartbeat("geopolitics", _geo_job), "cron", hour=21, minute=0, id="geopolitics")
        scheduler.add_job(_with_heartbeat("situation_overlay", _situation_overlay_job), "cron", hour=21, minute=20, id="situation_overlay")  # оверлей ситуации гео/институты — после geopolitics (тот же дневной digest)
        scheduler.add_job(_with_heartbeat("barometer_reviser", _barometer_reviser_job), "cron", hour=21, minute=40, id="barometer_reviser")  # ревизор ИНСТИТУТОВ (гео ушёл на barometer_daily) — после оверлея (его вердикт = триггер); cooldown 5 дней внутри
        scheduler.add_job(_with_heartbeat("barometer_daily", _barometer_daily_job), "cron", hour=21, minute=50, id="barometer_daily")  # ЕЖЕДНЕВНАЯ полная пересборка гео-барометра DeepSeek (владелец 2026-08-01) — последней в цепочке гео: digest(:10 ежечасно) → geopolitics(21:00) → overlay(21:20) → reviser inst(21:40) → сюда
        scheduler.add_job(_with_heartbeat("geo_profile", _geo_profile_job), "cron", day_of_week="sun", hour=22, minute=10, id="geo_profile")  # портрет очагов — НЕДЕЛЬНЫЙ слой (медленные данные: стороны/цели/баланс/связки), воскресенье после суточной цепочки
        scheduler.add_job(_with_heartbeat("sector_data", _sector_data_job), "cron", hour=7, minute=5, id="sector_data")  # отраслевые ряды — ежедневно утром, до всех недельных слоёв
        scheduler.add_job(_with_heartbeat("sector_digest", _sector_digest_job), "cron", hour="8,20", minute=15, id="sector_digest")
        scheduler.add_job(_with_heartbeat("futures_asset_facts", _futures_asset_facts_job), "cron", hour=6, minute=20, id="futures_asset_facts")
        scheduler.add_job(_with_heartbeat("nonequity_facts", _nonequity_facts_job), "cron", hour=6, minute=35, id="nonequity_facts")  # свежесть разборов облигаций и фондов — следом за фьючерсами, по тем же ночным котировкам  # свежесть разборов базовых активов фьючерсов — ежедневно, ПОСЛЕ ночной загрузки котировок  # отраслевая лента (обзоры/прогнозы рынков) — дважды в сутки, наполняет ленту к воскресной сборке барометра
        scheduler.add_job(_with_heartbeat("sector_barometer", _sector_barometer_job), "cron", day_of_week="sun", hour=21, minute=30, id="sector_barometer")  # отраслевой барометр — первым в недельной цепочке: его выход читают портреты и карточки
        scheduler.add_job(_with_heartbeat("institutions_domains", _institutions_domains_job), "cron", day_of_week="sun", hour=21, minute=55, id="institutions_domains")  # замеры направлений — ДО портрета институтов: портрет использует их как вход
        scheduler.add_job(_with_heartbeat("institutions_profile", _institutions_profile_job), "cron", day_of_week="sun", hour=22, minute=20, id="institutions_profile")  # портрет институтов — недельный, после portrait очагов (22:10) и до ОТК (22:30)
        scheduler.add_job(_with_heartbeat("geo_verification", _geo_verification_job), "cron", hour=22, minute=30, id="geo_verification")
        scheduler.add_job(_with_heartbeat("env_card_interp", _env_card_interp_job), "cron", day_of_week="mon", hour=6, minute=40, id="env_card_interp")
        scheduler.add_job(_with_heartbeat("card_rewrite", _card_rewrite_job), "cron", day_of_week="mon", hour=7, minute=30, id="card_rewrite")
        scheduler.add_job(_with_heartbeat("sector_scout", _sector_scout_job), "cron", day_of_week="wed", hour=7, minute=10, id="sector_scout")  # добор показателей, недоступных парсерам; значения помечаются как найденные в вебе  # третья ступень — перезапись ВЫВОДА, крошечный батч; идёт ПОСЛЕ патчера: его отказы служат сигналом эскалации  # доводка вкладок гео/институты карточек — утро понедельника, по свежим воскресным слоям  # «ОТК данных» гео без LLM — последним, меряет то, что реально уехало на витрину
        scheduler.add_job(_with_heartbeat("geo_digest", _geo_digest_job), "cron", minute=10, id="geo_digest")  # каждый час
        scheduler.add_job(_with_heartbeat("company_signals", _company_signals_job), "cron", minute=35, id="company_signals")  # шина: после news(5)+geo_digest(10), их выход = вход
        scheduler.add_job(_with_heartbeat("rating_agencies", _rating_agencies_job), "cron", hour=20, minute=55, id="rating_agencies")  # рейтинговые действия АКРА/НКР → сигналы + освежение agency_rating бумаг
        scheduler.add_job(_with_heartbeat("card_consumer", _card_consumer_job), "cron", hour=21, minute=15, id="card_consumer")  # consumer-агент: точные сигналы → addendum вкладки (гейт); после rating_agencies(20:55)+company_signals(:35)
        scheduler.add_job(_with_heartbeat("prose_patcher", _prose_patcher_job), "cron", hour=21, minute=35, id="prose_patcher")  # авто-свежесть прозы: дневной факт-патч из входного потока (гейт, БД-оверлей)
        # Недельная интерпретация прозы по потоку недели (дельта, гейт). День недели
        # смещён с воскресенья на ЧЕТВЕРГ (владелец, 2026-07-30): нужно было прогнать
        # актуализацию сразу, а не ждать выходных, дальше — тот же недельный ритм от
        # этой точки. Время 22:10 МСК оставлено (планировщик в Europe/Moscow), чтобы
        # проход шёл после дневных синков и факт-патча в 21:35.
        scheduler.add_job(_with_heartbeat("prose_interp", _prose_interp_job), "cron", day_of_week="thu", hour=22, minute=10, id="prose_interp")
        # дважды в день: после решения ЦБ волна из ~264 карточек проходит за считанные
        # дни (батч 12), в спокойное время детектор пуст и прогон дёшев
        scheduler.add_job(_with_heartbeat("macro_facts", _macro_facts_job), "cron", hour="9,20", minute=50, id="macro_facts")
        # смысловая доводка макро-вкладок после чисел (владелец 2026-08-01: «нужно
        # чтобы содержание прям менялось») — раз в день, очередь = свежие факт-патчи
        scheduler.add_job(_with_heartbeat("macro_interp", _macro_interp_job), "cron", hour=21, minute=5, id="macro_interp")
        scheduler.add_job(_with_heartbeat("overview_synthesis", _overview_synthesis_job), "cron", hour=23, minute=20, id="overview_synthesis")  # свод «Обзора» партиями: общий вывод по всем разборам + объяснение цены
        # разбор сценариев стресс-теста — по субботам, ПОСЛЕ недельного круга сводов
        # «Обзора» (они его вход) и до воскресных барометров, партиями по 3 из 6
        scheduler.add_job(_with_heartbeat("stress_interpretation", _stress_interpretation_job), "cron", day_of_week="sat", hour=4, minute=30, id="stress_interpretation")
        # 🔴 Крон макро-пилота ОТКЛЮЧЁН (владелец, 2026-08-04). Пилот дописывал на
        # боевую карточку плашки «🤖 Автономное обновление ИИ (демо)» вида
        # «дивидендная отсечка делает все мультипликаторы и апсайд неактуальными,
        # требуется пересчёт всей оценки» — тревога о том, что платформа и так
        # пересчитывает живьём, да ещё с пометкой «демо» на бою. Рендер убран с
        # витрины, генерация остановлена: копить в БД то, что никто не показывает,
        # значит жечь бюджет молча. Роль пилота закрыта — его задачу делают
        # card_prose_patcher (доводка вкладок) и card_consumer_agent (сигналы).
        # Запустить вручную по-прежнему можно: app/services/macro_addendum_agent.py.
        scheduler.add_job(_with_heartbeat("chronicle_maintenance", _chronicle_maintenance_job), "cron", hour=5, minute=20, id="chronicle_maintenance")  # летопись: бэкфилл + ретеншен Ленты
        logger.info("Внешние LLM/FRED-задачи планировщика включены (news/macro/earnings/geo/geo_digest)")
    scheduler.start()
    logger.info("Планировщик котировок запущен (каждые 5 мин, умный интервал; история — 19:30 МСК)")

    # Лёгкие/локальные старт-задачи (быстро освобождают соединение БД) — всегда.
    asyncio.create_task(_tinkoff_warmup())
    asyncio.create_task(_seed_shares_startup())
    asyncio.create_task(_instrument_history_startup())
    asyncio.create_task(_sector_tr_backfill_startup())
    asyncio.create_task(_risk_metrics_startup())
    asyncio.create_task(_selftest_startup())
    asyncio.create_task(_geo_frontline_sync_startup())
    asyncio.create_task(_company_metrics_job())  # файлы приезжают с деплоем — скринер сразу в ногу с карточками
    asyncio.create_task(_barometer_expert_reimport_startup())  # файл барометра мог обновиться экспертом → освежить якорь в БД

    # Облигации/фьючерсы/фонды — БЕЗ страховки на рестарт (в отличие от акций
    # выше) молча отставали на T+1..T+N: их крон (asset_data_refresh, 06:00 МСК)
    # раньше запускался ТОЛЬКО по расписанию, а сам _asset_data_job был ошибочно
    # сгруппирован с ДЕЙСТВИТЕЛЬНО рискованными задачами под RUN_STARTUP_JOBS
    # (news/macro/earnings/geo — те реально виснут на таймаутах внешних LLM/FRED
    # без egress, см. DEEPSEEK_BASE_URL-релей). _asset_data_job ходит ТОЛЬКО в
    # MOEX ISS (тот же источник, что _tinkoff_warmup уже дёргает выше безусловно)
    # и внутри сам себя ограничивает — refresh_all_if_stale() docstring прямо
    # заявляет «безопасно вызывать на каждом старте»: фьючерсы/фонды дёшевы и
    # обновляются всегда, облигации (~15-20 мин) — только если старше 22ч.
    # Каждый пропущенный рестартом день пусть теперь ловится здесь, а не ждёт
    # следующего попадания в окно 06:00 МСК.
    asyncio.create_task(_asset_data_job())
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
    # (_asset_data_job вынесен выше в безусловный блок — см. пояснение там.)
    if os.environ.get("RUN_STARTUP_JOBS") == "1":
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
if geo_tiles_router is not None:
    app.include_router(geo_tiles_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(portfolios_router, prefix="/api")
app.include_router(market_router, prefix="/api")
app.include_router(debug_router, prefix="/api")
app.include_router(debug_open_router, prefix="/api")
app.include_router(bonds_router, prefix="/api")
app.include_router(futures_router, prefix="/api")
app.include_router(funds_router, prefix="/api")
app.include_router(spot_router, prefix="/api")
app.include_router(options_router, prefix="/api")
app.include_router(screener_router, prefix="/api")
app.include_router(macro_router, prefix="/api")
app.include_router(observer_router, prefix="/api")
app.include_router(assistant_router, prefix="/api")
app.include_router(stress_router, prefix="/api")
app.include_router(agents_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "Backend is working"}
