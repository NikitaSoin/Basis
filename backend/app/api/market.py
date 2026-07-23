import os
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from anthropic import Anthropic
from app.db.session import get_db
from app.auth import get_current_user_optional
from app.models.market import MarketUpdate, OverviewType
from app.models.company import Company
from app.models.portfolio import Portfolio, PortfolioPosition
from app.schemas.market import (
    MarketUpdateCreate, MarketUpdateResponse,
    MarketOverviewCreate, MarketOverviewResponse,
    NewsItemResponse,
)
from app.services.market import (
    get_all_updates, create_update,
    get_all_overviews, create_overview,
)

router = APIRouter()


def _portfolio_filter(db: Session, user) -> tuple[set[str], set[str]]:
    """Тикеры и секторы из портфелей пользователя — для тумблера «Только мой портфель»."""
    if not user:
        return set(), set()
    rows = (
        db.query(Company.ticker, Company.sector)
        .join(PortfolioPosition, PortfolioPosition.company_id == Company.id)
        .join(Portfolio, Portfolio.id == PortfolioPosition.portfolio_id)
        .filter(Portfolio.user_id == user.id)
        .all()
    )
    tickers = {r[0] for r in rows if r[0]}
    sectors = {r[1] for r in rows if r[1]}
    return tickers, sectors


@router.get("/market/indices")
def market_indices(db: Session = Depends(get_db)):
    """Live-уровень бенчмарк-индексов (IMOEX/МосБиржа ПД/РТС): текущее значение,
    изменение к закрытию, спарклайн ~30 дней. Live — MOEX ISS (без ключей),
    фолбэк — последний дневной close из index_history."""
    from app.services.indices import get_indices
    return get_indices(db)


@router.get("/market/indices/{ticker}/detail")
def market_index_detail(
    ticker: str,
    period: str = Query("3y", pattern="^(1m|6m|ytd|1y|3y)$"),
    db: Session = Depends(get_db),
):
    """Детальная страница индекса: живая шапка + историческая серия close за
    период (график с табами 1мес/6мес/YTD/1год/3года) + смена за месяц/год +
    объём. Только для бенчмарков с полной историей (IMOEX/MCFTR/RTSI) —
    404 для остальных тикеров (напр. отраслевых индексов MOEX без истории)."""
    from app.services.indices import get_index_detail
    detail = get_index_detail(db, ticker, period)
    if detail is None:
        raise HTTPException(status_code=404, detail="Индекс не найден или история недоступна")
    return detail


@router.get("/market/pulse")
def market_pulse(db: Session = Depends(get_db)):
    """Блок «Обзор рынка» Обозревателя: индексы (IMOEX/МПД/РТС/RGBI), секторальные
    индексы MOEX (10 шт.), ставки денежного рынка (RUSFAR руб./юань), нефть Brent
    (прокси — ближайший фьючерс), драгметаллы (spot_assets), индекс страха и
    жадности Basis (v0, оценка/модель)."""
    from app.services.market_pulse import get_market_overview, get_fear_greed
    overview = get_market_overview(db)
    overview["fear_greed"] = get_fear_greed(db)
    return overview


@router.get("/market/drivers")
def market_drivers(db: Session = Depends(get_db)):
    """«Что движет рынком сегодня» для пульса: Brent / USD-RUB / Ставка ЦБ / ОФЗ-10.
    Best-effort из имеющихся данных (фьючерсы/спот/макро/кривая ОФЗ); недоступное —
    помечается. value/dir = факт (котировка), effect = суждение Basis (не сигнал)."""
    from sqlalchemy import text as _t
    out = []

    # Нефть Brent — ближайший фьючерс BR (FORTS), $/барр. chart: клик на плитке
    # («владелец: перекидывало в обзор рынка где есть графики») ведёт на
    # /market/instruments/future/{secid}/history — тот же движок, что у Рынок→Фьючерсы.
    # 🔴 Найдено на бою 2026-07-16 (владелец: «нефть весной доходила до 120$, а тут не
    # так»): этот график — история ЦЕНЫ ИМЕННО ЭТОГО КОНТРАКТА (плитка каждый раз берёт
    # ближайший НЕ ЭКСПИРИРОВАВШИЙ фьючерс — сегодня это не тот контракт, что был «ближним»
    # весной), не непрерывный ряд «цена нефти». Разные контракты одной нефти расходятся
    # (контанго/бэквордация). Честная склейка в continuous series — отдельная задача
    # (see docs/status.md): у истекших контрактов на бою вообще нет истории в
    # instrument_history, нужен re-backfill с MOEX ISS, не просто склейка имеющегося.
    # Пока — честная подпись: конкретный контракт + дата начала охвата (instrument_label),
    # не выдаём его за общий график «нефть».
    try:
        r = db.execute(_t(
            "SELECT secid, last_price, prev_settle, expiration_date FROM futures "
            "WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') AND last_price IS NOT NULL "
            "AND expiration_date >= now()::date ORDER BY expiration_date ASC LIMIT 1")).first()
        if r and r[1]:
            secid = r[0]; px = float(r[1]); prev = float(r[2]) if r[2] else None
            exp = r[3]
            d = 0 if not prev else (1 if px > prev else -1 if px < prev else 0)
            label = f"фьючерс {secid}" + (f" (эксп. {exp.strftime('%m.%Y')})" if exp else "")
            out.append({"name": "Нефть Brent", "value": f"{px:.1f} $".replace(".", ","),
                        "dir": d, "effect": "поддержка нефтегазу при росте", "level": "факт",
                        "chart": {"asset_class": "future", "secid": secid, "field": "close", "unit": "$",
                                  "instrument_label": label}})
    except Exception:
        pass

    # Валюта — USD/RUB (спот). 🔴 Найдено на бою 2026-07-16: график по спот-инструменту
    # (instrument_history) короткий (~5 мес) — у графика курса уже есть более глубокий дом,
    # официальный дневной фид ЦБ РФ (`usdrub` в /market/macro) на «Экономическая статистика»,
    # той же плитки/паттерна, что уже сделан для «Ставка ЦБ». Владелец: «я бы вообще открывал
    # не блок обзор рынка а экономическую статистику и там на графике сразу уже курс доллара».
    try:
        r = db.execute(_t("SELECT last_price, change_pct FROM spot_assets WHERE secid='USD000UTSTOM'")).first()
        if r and r[0]:
            px = float(r[0]); chg = float(r[1]) if r[1] is not None else 0
            d = 1 if chg > 0 else -1 if chg < 0 else 0
            out.append({"name": "USD / RUB", "value": f"{px:.2f}".replace(".", ","),
                        "dir": d, "effect": "слабее рубль — плюс экспортёрам", "level": "факт",
                        "nav": "economy", "nav_indicator": "usdrub"})
    except Exception:
        pass

    # Ставка ЦБ (макро) — тот же источник, что и /market/macro/rate. У графика ставки
    # уже есть дом — «Экономическая статистика» (hero-график с историей) — владелец:
    # «ключевая ставка — не в обзор, а в экономическую статистику». nav вместо chart —
    # фронт различает, куда вести клик.
    val = None
    try:
        from app.models.macro import MacroDataPoint
        p = (db.query(MacroDataPoint).filter_by(indicator_code="key_rate", metric="level")
             .order_by(MacroDataPoint.as_of.desc()).first())
        val = float(p.value) if p else None
    except Exception:
        val = None
    if val is not None:
        out.append({"name": "Ставка ЦБ", "value": f"{float(val):.2f} %".replace(".", ","),
                    "dir": 0, "effect": "выше ставка — давит на оценки акций", "level": "факт",
                    "nav": "economy"})

    # ОФЗ 10 лет (кривая из нашей базы). Реальный рынок ОФЗ сейчас не доходит до 10 лет
    # (самый длинный выпуск — ~7 лет), поэтому число — плоская экстраполяция последней
    # точки кривой; график по-честному строим по ДОХОДНОСТИ ЭТОГО САМОГО якорного
    # выпуска (ближайшего по дюрации к 10Y) — та же бумага, что формирует цифру.
    # 🔴 Найдено на бою 2026-07-16 (владелец: «ОФЗ раньше имела более высокую доходность»):
    # та же проблема, что у Brent — плитка каждый раз выбирает бумагу, чья ТЕКУЩАЯ дюрация
    # ближе к 10 годам, график — история ИМЕННО ЭТОЙ бумаги, не непрерывный ряд «доходность
    # 10-летней ОФЗ» (раньше «10-летней» была другая бумага). Плюс глубина истории в БД
    # ограничена (~13 мес, разовый бэкафилл) — пик ставки 2023-2024 за пределами окна в
    # любом случае. Честная склейка — отдельная задача (см. docs/status.md). Пока — честная
    # подпись: конкретный выпуск + погашение, не выдаём за общий «ОФЗ 10 лет».
    try:
        from app.services.bond_risk import _ofz_curve_from_db, _ofz_at
        curve = _ofz_curve_from_db(db)
        y10 = _ofz_at(curve, 10)
        if y10:
            entry = {"name": "ОФЗ 10 лет", "value": f"{float(y10):.1f} %".replace(".", ","),
                     "dir": 0, "effect": "конкурент акциям за деньги", "level": "факт"}
            anchor = db.execute(_t(
                "SELECT secid, short_name, maturity_date FROM bonds WHERE bond_type='ofz' AND ytm IS NOT NULL "
                "AND duration_days IS NOT NULL ORDER BY ABS(duration_days - 3650) ASC LIMIT 1")).first()
            if anchor:
                mat = anchor[2]
                label = f"выпуск {anchor[1] or anchor[0]}" + (f" (погашение {mat.strftime('%m.%Y')})" if mat else "")
                entry["chart"] = {"asset_class": "bond", "secid": anchor[0], "field": "yld", "unit": "%",
                                  "instrument_label": label}
            out.append(entry)
    except Exception:
        pass

    return out


@router.get("/market/instruments/{asset_class}/{secid}/history")
def instrument_history_endpoint(asset_class: str, secid: str,
                                days: int = Query(180, ge=5, le=1500),
                                db: Session = Depends(get_db)):
    """Дневной ряд цен инструмента (bond|future|fund) для графика на экране «Рынок».
    Источник — instrument_history (MOEX ISS). Для облигаций добавляет YTM/НКД,
    для фьючерсов — расчётную цену/ОИ."""
    from app.services.instrument_history import get_history
    return get_history(db, asset_class, secid, days)


@router.get("/market/commodity-price-history")
def commodity_price_history(benchmark_key: str = Query(..., description="forts:<CODE> | macro:<indicator_code>"),
                            years: int = Query(5, ge=1, le=10),
                            db: Session = Depends(get_db)):
    """Историческая цена для commodity_exposure.benchmark_key компаний
    (market.json, методичка market-analyst v6) — график «Товар компании» на
    вкладке «Рынки». Два источника, тот же формат benchmark_key, что в данных:
    - `forts:<CODE>` (BR/NG/GOLD/SILV/PLT/PLD/CU/WHEAT) — резолвит БЛИЖАЙШИЙ
      неэкспирировавший фьючерс по asset_code (та же логика, что
      market_pulse._oil_snapshot — «цена нефти» = цена ближнего фьючерса),
      затем отдаёт instrument_history для конкретного secid.
    - `macro:<indicator_code>` — срез macro_data_points (Urals/World Bank Pink
      Sheet и т.п.), metric="level".
    `benchmark_key: "none"` сюда не приходит — фронт для него график не рисует
    (честная деградация метрики, не баг)."""
    from datetime import date, timedelta
    if ":" not in benchmark_key:
        raise HTTPException(status_code=400, detail="benchmark_key должен быть в формате source:slug")
    source, slug = benchmark_key.split(":", 1)
    days = min(years * 365, 1500)  # см. instrument_history_endpoint — те же границы

    if source == "forts":
        from app.models.future import Future
        from app.services.instrument_history import get_history
        today = date.today()
        f = (db.query(Future)
             .filter(Future.asset_code == slug,
                     (Future.expiration_date.is_(None)) | (Future.expiration_date >= today))
             .order_by(Future.expiration_date.asc().nullslast())
             .first())
        if not f:
            return {"benchmark_key": benchmark_key, "points": [], "note": "контракт не найден"}
        hist = get_history(db, "future", f.secid, days)
        pts = [{"as_of": p["date"], "value": p["close"] if p["close"] is not None else p.get("settle")}
               for p in hist.get("points", [])]
        pts = [p for p in pts if p["value"] is not None]
        return {"benchmark_key": benchmark_key, "secid": f.secid,
                "note": f"ближайший фьючерс {f.secid}, эксп. {f.expiration_date}", "points": pts}

    if source == "macro":
        from app.models.macro import MacroDataPoint, MacroIndicator
        ind = db.get(MacroIndicator, slug)
        if not ind:
            return {"benchmark_key": benchmark_key, "points": [], "note": "индикатор не найден"}
        start = date.today() - timedelta(days=days)
        rows = (db.query(MacroDataPoint)
                .filter_by(indicator_code=slug, metric="level")
                .filter(MacroDataPoint.as_of >= start)
                .order_by(MacroDataPoint.as_of).all())
        pts = [{"as_of": p.as_of.isoformat(), "value": float(p.value)} for p in rows]
        return {"benchmark_key": benchmark_key, "unit": ind.unit, "points": pts}

    raise HTTPException(status_code=400, detail=f"неизвестный источник benchmark_key: {source}")


@router.get("/market/candles/{asset_class}/{secid}")
def market_candles(asset_class: str, secid: str,
                   tf: str = Query("1d", description="1m|5m|15m|1h|4h|1d|1w|1M")):
    """Свечи OHLCV для графиков ChartPro (MOEX ISS, кэш с TTL).
    Классы: share|index|bond|future|fund|spot. 5м/15м агрегируются из 1м,
    4ч — из 60м (ISS этих интервалов не отдаёт нативно)."""
    from app.services.candles import get_candles
    return get_candles(asset_class, secid, tf)


@router.get("/market/instruments/sparklines")
def instrument_sparklines_endpoint(asset_class: str = Query(...),
                                   secids: str = Query(..., description="SECID через запятую"),
                                   days: int = Query(30, ge=5, le=400),
                                   db: Session = Depends(get_db)):
    """Батч мини-графиков {secid: {spark, last, change_pct}} для таблиц/карточек
    экрана «Рынок» (один запрос на список бумаг)."""
    from app.services.instrument_history import get_sparklines
    ids = [s.strip() for s in secids.split(",") if s.strip()][:400]
    return get_sparklines(db, asset_class, ids, days)


@router.get("/market/maps/heatmap")
def market_heatmap(period: str = Query("day"), portfolio_only: bool = False,
                   db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Тепловая карта: цвет — изменение цены за период (day|week|month).
    portfolio_only — только бумаги из портфелей пользователя."""
    from app.services import market_maps
    tickers = None
    if portfolio_only:
        tickers, _ = _portfolio_filter(db, user)  # пустой набор → пустая карта (так и нужно)
    return market_maps.heatmap(db, period=period, tickers_filter=tickers)


@router.get("/market/maps/valuation")
def market_valuation(portfolio_only: bool = False,
                     db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Карта недооценённости: апсайд к МОДЕЛЬНОЙ справедливой цене (живьём от текущей
    цены). Покрытые — раскрашены; непокрытые — группа «оценка недоступна». Без сигналов."""
    from app.services import market_maps
    tickers = None
    if portfolio_only:
        tickers, _ = _portfolio_filter(db, user)
    return market_maps.valuation(db, tickers_filter=tickers)


@router.get("/market/maps/heatmap/bonds")
def market_heatmap_bonds(db: Session = Depends(get_db)):
    """Тепловая карта облигаций: вес — дневной торговый оборот, цвет — изменение
    цены. Честное покрытие — только бумаги с реальными данными об обороте за
    последние 30 дней (см. coverage_pct/total_universe в ответе)."""
    from app.services import market_maps
    return market_maps.heatmap_bonds(db)


@router.get("/market/maps/heatmap/futures")
def market_heatmap_futures(db: Session = Depends(get_db)):
    """Тепловая карта фьючерсов: вес — условная стоимость открытых позиций
    (ликвидность/интерес рынка), цвет — изменение расчётной цены к клирингу."""
    from app.services import market_maps
    return market_maps.heatmap_futures(db)


@router.get("/market/maps/heatmap/funds")
def market_heatmap_funds(db: Session = Depends(get_db)):
    """Тепловая карта фондов (БПИФ/ETF): вес — дневной торговый оборот, цвет —
    изменение цены пая."""
    from app.services import market_maps
    return market_maps.heatmap_funds(db)


@router.get("/market/maps/spot")
def market_spot_grid(db: Session = Depends(get_db)):
    """Валюта/металлы — плоская сетка (6 инструментов, курируемый набор), без treemap."""
    from app.services import market_maps
    return market_maps.spot_grid(db)


@router.get("/market/news", response_model=list[NewsItemResponse])
def list_news_endpoint(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    importance: str | None = Query(None, pattern="^(high|medium|low)$"),
    rubric: str | None = None,
    ticker: str | None = None,
    sector: str | None = None,
    portfolio_only: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user_optional),
):
    """Лента рыночно-значимых новостей (только опубликованные, свежие сверху)."""
    q = db.query(MarketUpdate).filter(MarketUpdate.status == "published")
    if importance:
        q = q.filter(MarketUpdate.importance == importance)
    if rubric:
        q = q.filter(MarketUpdate.rubric == rubric)
    if ticker:
        q = q.filter(MarketUpdate.affected_tickers.contains([ticker.upper()]))
    if sector:
        q = q.filter(MarketUpdate.affected_sectors.contains([sector]))
    if portfolio_only:
        tickers, sectors = _portfolio_filter(db, user)
        if not tickers and not sectors:
            return []
        conds = []
        for t in tickers:
            conds.append(MarketUpdate.affected_tickers.contains([t]))
        for s in sectors:
            conds.append(MarketUpdate.affected_sectors.contains([s]))
        q = q.filter(or_(*conds))
    return (q.order_by(MarketUpdate.published_at.desc())
              .offset(offset).limit(limit).all())


@router.get("/market/news/{item_id}", response_model=NewsItemResponse)
def get_news_endpoint(item_id: int, db: Session = Depends(get_db)):
    row = db.query(MarketUpdate).filter(
        MarketUpdate.id == item_id, MarketUpdate.status == "published"
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Новость не найдена")
    return row


@router.post("/market/updates", response_model=MarketUpdateResponse, status_code=status.HTTP_201_CREATED)
def create_update_endpoint(data: MarketUpdateCreate, db: Session = Depends(get_db)):
    return create_update(db, data)


@router.get("/market/updates", response_model=list[MarketUpdateResponse])
def list_updates_endpoint(db: Session = Depends(get_db)):
    return get_all_updates(db)


@router.post("/market/overviews", response_model=MarketOverviewResponse, status_code=status.HTTP_201_CREATED)
def create_overview_endpoint(data: MarketOverviewCreate, db: Session = Depends(get_db)):
    return create_overview(db, data)


@router.get("/market/overviews", response_model=list[MarketOverviewResponse])
def list_overviews_endpoint(type: OverviewType | None = None, db: Session = Depends(get_db)):
    return get_all_overviews(db, overview_type=type)


@router.post("/market/overviews/generate", response_model=MarketOverviewResponse, status_code=status.HTTP_201_CREATED)
def generate_overview_endpoint(
    type: OverviewType = OverviewType.express,
    current_user=Depends(get_current_user_optional),
):
    try:
        from app.services.market_overview import generate_market_overview
        return generate_market_overview(type.value)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {e}")


def _compare_index_series(ticker: str, db: Session) -> dict:
    """Фолбэк compare-asset для бенчмарк-индексов (IMOEX/MCFTR — ценовой vs
    дивидендный; RTSI — долларовый) — для «своего конструктора» отношений
    (напр. MCFTR ÷ LQDT), не только акции/фонды портфеля."""
    from app.services.risk_metrics import window_start
    from app.models.market import IndexHistory

    since = window_start()
    rows = (
        db.query(IndexHistory.date, IndexHistory.close)
        .filter(IndexHistory.ticker == ticker.upper(), IndexHistory.date >= since)
        .order_by(IndexHistory.date)
        .all()
    )
    if len(rows) < 2:
        return {"ticker": ticker.upper(), "dates": [], "cum_pct": [], "total_pct": None,
                "note": "недостаточно истории индекса"}
    p0 = float(rows[0].close)
    out_dates = [r.date.isoformat() for r in rows]
    out_curve = [round((float(r.close) / p0 - 1) * 100, 2) for r in rows]
    return {
        "ticker": ticker.upper(), "name": ticker.upper(),
        "dates": out_dates, "cum_pct": out_curve, "total_pct": out_curve[-1] if out_curve else None,
    }


def _compare_fund_series(ticker: str, db: Session) -> dict:
    """Фолбэк compare-asset для фондов (SECID, не тикер компании) — по
    instrument_history, цена пая без реконструкции дивидендов/распределений."""
    from app.models.fund import Fund
    from app.models.instrument import InstrumentHistory
    from app.services.risk_metrics import window_start

    fund = db.query(Fund).filter(Fund.secid == ticker.upper()).first()
    if not fund:
        raise HTTPException(status_code=404, detail=f"Тикер {ticker} не найден")

    since = window_start()
    rows = (
        db.query(InstrumentHistory.date, InstrumentHistory.close)
        .filter(InstrumentHistory.asset_class == "fund", InstrumentHistory.secid == ticker.upper(),
                InstrumentHistory.date >= since, InstrumentHistory.close.isnot(None))
        .order_by(InstrumentHistory.date)
        .all()
    )
    if len(rows) < 2:
        return {"ticker": ticker.upper(), "dates": [], "cum_pct": [], "total_pct": None,
                "note": "недостаточно истории котировок"}
    p0 = float(rows[0].close)
    out_dates = [r.date.isoformat() for r in rows]
    out_curve = [round((float(r.close) / p0 - 1) * 100, 2) for r in rows]
    return {
        "ticker": ticker.upper(), "name": fund.short_name,
        "dates": out_dates, "cum_pct": out_curve, "total_pct": out_curve[-1] if out_curve else None,
        "note": "цена пая, без учёта распределений — фонд как правило накопительный",
    }


@router.get("/market/compare-asset")
def compare_asset_series(ticker: str, db: Session = Depends(get_db)):
    """Накопленная полная доходность (цена+дивиденды) произвольного тикера за
    стандартное окно (3 года) — для конструктора «+ Добавить сравнение» на
    вкладке «Сравнение» портфеля. Независим от портфеля: любая бумага с рынка,
    как в прототипе ("не только из вашего портфеля"). Акции — из quotes (с
    дивидендами); если тикер не акция, пробуем фонд (SECID) — по цене пая из
    instrument_history (без реконструкции распределений — фонды почти все
    накопительные, NAV уже отражает реинвест)."""
    from app.services.risk_metrics import load_price_series, normalize_splits, window_start
    from app.services.moex_dividends import load_dividends_map

    company = db.query(Company).filter(Company.ticker == ticker.upper()).first()
    if not company:
        if ticker.upper() in ("IMOEX", "RTSI", "MCFTR"):
            return _compare_index_series(ticker, db)
        return _compare_fund_series(ticker, db)

    since = window_start()
    series = load_price_series(db, company.id, since)
    if len(series) < 2:
        return {"ticker": ticker.upper(), "dates": [], "cum_pct": [], "total_pct": None,
                "note": "недостаточно истории котировок"}

    norm = normalize_splits(series)
    dates = sorted(norm)
    dividends = load_dividends_map(db, ticker.upper())
    p0 = norm[dates[0]]
    div_factor = 1.0
    out_dates, out_curve = [], []
    for d in dates:
        # дивиденд на дату отсечки (или ближайшую предыдущую торговую) —
        # тот же метод накопления, что и у бенчмарк-кривой портфеля
        if d in dividends:
            amount = dividends[d]
            p = norm[d]
            if p > 0 and 0 < amount / p < 1:
                div_factor *= 1 + amount / p
        cum = (norm[d] / p0) * div_factor
        out_dates.append(d.isoformat())
        out_curve.append(round((cum - 1) * 100, 2))

    return {
        "ticker": ticker.upper(),
        "name": company.name,
        "dates": out_dates,
        "cum_pct": out_curve,
        "total_pct": out_curve[-1] if out_curve else None,
    }


@router.get("/market/calendar")
def market_calendar(event_type: str | None = None, sector: str | None = None,
                    portfolio_only: bool = False, scope: str = "upcoming",
                    days: int = 120, limit: int = 400,
                    db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Унифицированный календарь событий (Направление 4): дивиденды, облигации
    (оферты/погашения), макрорелизы, IPO, экспирации. Фильтры: event_type, sector,
    portfolio_only; scope=upcoming|past|all; горизонт days."""
    from datetime import date, timedelta
    from app.models.calendar_event import CalendarEvent
    today = date.today()
    q = db.query(CalendarEvent)
    if event_type:
        q = q.filter(CalendarEvent.event_type == event_type)
    if sector:
        q = q.filter(CalendarEvent.sector == sector)
    if portfolio_only:
        tickers, _ = _portfolio_filter(db, user)
        q = q.filter(CalendarEvent.ticker.in_(tickers) if tickers else False)
    if scope == "upcoming":
        q = q.filter(CalendarEvent.event_date >= today,
                     CalendarEvent.event_date <= today + timedelta(days=days))
        q = q.order_by(CalendarEvent.event_date.asc())
    elif scope == "past":
        q = q.filter(CalendarEvent.event_date < today,
                     CalendarEvent.event_date >= today - timedelta(days=days))
        q = q.order_by(CalendarEvent.event_date.desc())
    else:
        q = q.order_by(CalendarEvent.event_date.asc())
    rows = q.limit(limit).all()
    events = [{
        "id": e.id, "type": e.event_type, "date": e.event_date.isoformat(),
        "time": e.event_time, "ticker": e.ticker, "sector": e.sector,
        "title": e.title, "status": e.status, "source": e.source,
        "source_url": e.source_url, "payload": e.payload or {},
    } for e in rows]
    return {"as_of": str(today), "scope": scope, "count": len(events), "events": events}


def _geo_block_dict(b, pf_tickers: set[str]) -> dict:
    tk = b.affected_tickers or []
    return {
        "region": b.region, "tab": b.tab, "title": b.title,
        "status_text": b.status_text, "channels": b.channels or [],
        "scenarios": b.scenarios, "market_impact": b.market_impact,
        "affected_sectors": b.affected_sectors or [],
        "affected_tickers": tk,
        "in_portfolio": bool(pf_tickers & set(tk)),
        "model_used": b.model_used,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


@router.get("/market/geopolitics")
def market_geopolitics(portfolio_only: bool = False,
                       db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Геополитика (Направление 7): обе вкладки (overview/deep), все регионы.
    Источники в выдаче не раскрываются (geo_methodology.md, раздел 7)."""
    from app.models.geo import GeoBlock
    pf, _ = _portfolio_filter(db, user) if portfolio_only else (set(), set())
    blocks = db.query(GeoBlock).all()
    out = {"overview": [], "deep": []}
    for b in blocks:
        if b.tab in out:
            d = _geo_block_dict(b, pf)
            if portfolio_only and not d["in_portfolio"]:
                continue
            out[b.tab].append(d)
    order = {"svo": 0, "middle_east": 1, "atr": 2}
    for tab in out:
        out[tab].sort(key=lambda x: order.get(x["region"], 9))
    return {"tabs": out, "disclaimer": "Прогнозы — оценка Basis (сценарные, условные). Не является ИИР."}


@router.get("/market/institutions")
def market_institutions():
    """Институциональная среда (Обозреватель): барометр M1-M13, карта власти/
    кланов, активные сценарии и алерты. Методика — docs/Институты_агенты.md,
    docs/Институты_дополнение.md; заполняет institutional-macro-analyst,
    файл config/institutional_barometer.json (не пилотный per-company блок —
    единый рыночный документ, обновляется отдельным прогоном)."""
    import json as _json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config", "institutional_barometer.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Барометр ещё не сформирован")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=_json.load(f))


@router.get("/market/geo-barometer")
def market_geo_barometer():
    """Геополитический барометр (Обозреватель, «Оценка ситуации»): 13 субиндексов
    G1-G13, сценарная рамка S1-S4, имплайд-рынок, секторные флаги. Методика —
    docs/geo-system/; заполняет geo-macro-analyst, файл config/geo_barometer.json
    (единый рыночный документ, не per-регион — заменяет geo_blocks tab=deep синтез)."""
    import json as _json
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config", "geo_barometer.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Барометр ещё не сформирован")
    with open(path, encoding="utf-8") as f:
        return JSONResponse(content=_json.load(f))


@router.get("/market/geo-map/{theater}")
def market_geo_map(theater: str, db: Session = Depends(get_db)):
    """Интерактивная карта очага (Обозреватель, «Оценка ситуации» → карта): линия
    фронта, удары, критическая инфраструктура, военные базы, флот — координатный
    слой поверх барометра (geo_barometer.json.regions остаётся текстовым описанием).
    Файл config/geo_map_<theater>.json, theater из фиксированного списка очагов.
    Источники — ISW (карты CC BY, можно переиспользовать с атрибуцией) + Рыбарь
    (пересказ фактов, не копирование картинок).

    Для СВО линия фронта (base_map.frontline_geojson) накладывается живой из
    geo_frontline_sync (см. app/services/geo_isw_frontline_sync.py) поверх
    статического файла, если синк когда-либо успешно отработал — статический
    файл при этом остаётся источником правды для событий/классификации
    областей и фолбэком, если синк ещё не запускался или последний прогон
    упал (status="error" в БД не подменяет ранее сохранённую рабочую линию)."""
    import json as _json
    if theater not in ("svo", "middle_east", "atr"):
        raise HTTPException(status_code=404, detail="Неизвестный очаг")
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "config", f"geo_map_{theater}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Карта очага ещё не сформирована")
    with open(path, encoding="utf-8") as f:
        payload = _json.load(f)

    if theater == "svo":
        from app.models.geo import GeoFrontlineSync
        row = db.query(GeoFrontlineSync).filter_by(theater="svo").first()
        if row is not None and row.frontline_geojson:
            payload["base_map"]["frontline_geojson"] = row.frontline_geojson
            payload["base_map"]["frontline_source"] = row.source
            payload["base_map"]["frontline_as_of"] = row.as_of
            payload["base_map"]["frontline_synced_at"] = row.synced_at.isoformat() if row.synced_at else None
            if row.control_fill_geojson:
                payload["base_map"]["control_fill_geojson"] = row.control_fill_geojson

    return JSONResponse(content=payload)


@router.get("/market/geo-map/svo/history")
def market_geo_map_svo_history(db: Session = Depends(get_db)):
    """Список дат, на которые есть накопленный снапшот линии фронта СВО —
    для временного ползунка (Обозреватель, карта СВО). Снапшоты копятся
    ВПЕРЁД с 2026-07-24 (у ISW нет штатного API истории по датам назад —
    см. докстринг geo_isw_frontline_sync.GeoFrontlineSnapshot), глубина
    растёт естественно. Пусто до накопления первых записей — фронт должен
    прятать ползунок при пустом/однодневном списке."""
    from app.models.geo import GeoFrontlineSnapshot
    rows = (db.query(GeoFrontlineSnapshot.snapshot_date, GeoFrontlineSnapshot.as_of)
            .filter_by(theater="svo").order_by(GeoFrontlineSnapshot.snapshot_date.asc()).all())
    return {"dates": [{"date": d, "as_of": a} for d, a in rows]}


@router.get("/market/geo-map/svo/history/{date}")
def market_geo_map_svo_history_date(date: str, db: Session = Depends(get_db)):
    """Снапшот линии фронта СВО на конкретную накопленную дату (YYYY-MM-DD,
    из /market/geo-map/svo/history)."""
    from app.models.geo import GeoFrontlineSnapshot
    row = db.query(GeoFrontlineSnapshot).filter_by(theater="svo", snapshot_date=date).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Снапшот на эту дату не найден")
    return {"date": row.snapshot_date, "as_of": row.as_of,
            "frontline_geojson": row.frontline_geojson, "control_fill_geojson": row.control_fill_geojson}


@router.get("/market/geopolitics/{region}")
def market_geopolitics_region(region: str, tab: str = "deep",
                              db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    from app.models.geo import GeoBlock
    b = db.query(GeoBlock).filter_by(region=region, tab=tab).first()
    if not b:
        raise HTTPException(status_code=404, detail="Нет данных по региону/вкладке")
    return _geo_block_dict(b, set())


def _digest_dict(a) -> dict:
    from app.services.geo_digest import SOURCE_LABELS
    return {"id": a.id, "title": a.title, "summary": a.summary,
            "key_takeaways": a.key_takeaways or [],
            "investor_relevance": a.investor_relevance,
            "source_label": SOURCE_LABELS.get(a.source_key, a.source_key),
            "published_at": a.published_at.isoformat() if a.published_at else None}


@router.get("/market/geopolitics/{region}/digest")
def market_geopolitics_digest(region: str, limit: int = 15, db: Session = Depends(get_db)):
    """Отдельные статьи-карточки по региону (не слитый синтез geo_blocks) — подробный
    пересказ + тезисы. source_label показывается (временно, обкатка пайплайна —
    geo_digest.py). Сортировка по created_at (когда МЫ сохранили), не published_at:
    у re:russia (no_pubdate) published_at — синтетическая метка "сегодня" для всего
    бэклога, будь сортировка по ней — свежие статьи других источников тонут за старым
    бэклогом re:russia с той же датой."""
    from app.models.geo_digest import GeoDigestArticle, GEO_DIGEST_TARGETS
    if region not in GEO_DIGEST_TARGETS or region in ("institutions", "macro"):
        raise HTTPException(status_code=404, detail="Неизвестный регион")
    rows = (db.query(GeoDigestArticle).filter_by(target=region)
           .order_by(GeoDigestArticle.created_at.desc()).limit(limit).all())
    return {"region": region, "articles": [_digest_dict(a) for a in rows]}


@router.get("/market/institutions/digest")
def market_institutions_digest(limit: int = 15, db: Session = Depends(get_db)):
    """Дайджест статей институциональной среды с экономической проекцией —
    дополняет статичный барометр (market_institutions) живой лентой."""
    from app.models.geo_digest import GeoDigestArticle
    rows = (db.query(GeoDigestArticle).filter_by(target="institutions")
           .order_by(GeoDigestArticle.created_at.desc()).limit(limit).all())
    return {"articles": [_digest_dict(a) for a in rows]}


@router.get("/market/macro/digest")
def market_macro_digest(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    """Дайджест статей с макроэкономическим уклоном из внешних источников
    (Economist Finance, ISW, Carnegie (телеграм-каналы — geo_digest.py уже
    классифицирует их посты по target, сюда попадают только макро-тезисы, не
    геополитика/институты), MarketTwits и др. — geo_digest.py, target=macro) —
    дополняет записки ЦБ/ЦМАКП (market_macro_analytics) живой лентой внешнего
    взгляда. Сортировка по published_at (дата публикации), не created_at (когда
    МЫ сохранили) — фронт показывает статьи вперемешку с записками ЦБ/ЦМАКП в
    одной ленте, отсортированной по дате, и created_at ломал бы порядок."""
    from app.models.geo_digest import GeoDigestArticle
    rows = (db.query(GeoDigestArticle).filter_by(target="macro")
           .order_by(GeoDigestArticle.published_at.desc().nullslast(),
                     GeoDigestArticle.created_at.desc())
           .limit(limit).all())
    return {"articles": [_digest_dict(a) for a in rows]}


def _split_markers(markers) -> tuple[list, list]:
    """Разбивает what_report_showed на positives (✅) и risks (❌/❗)."""
    if not markers:
        return [], []
    pos, neg = [], []
    for m in markers:
        s = str(m).strip()
        if s.startswith("✅"):
            pos.append(s)
        elif s.startswith("❌") or s.startswith("❗"):
            neg.append(s)
        else:
            pos.append(s)   # нейтральные → в позитив
    return pos, neg


@router.get("/market/earnings")
def market_earnings(portfolio_only: bool = False, limit: int = 60,
                    db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Лента вышедших отчётов (Направление 3): тикер, период, одна строка сути, важность.
    Тап → карточка. portfolio_only — только бумаги портфеля.
    🔴 Только status=="processed" — реально разобранные отчёты. Кейсы "не нашли источник"
    (needs_source) сюда не попадают (раньше давали пустые карточки без цифр/анализа —
    жалоба владельца 2026-07-14): они всплывают в /market/corporate-news как report_missing.
    🔴 Найдено на бою 2026-07-16: сортировка была по created_at (когда МЫ обнаружили отчёт),
    не по published_at (когда отчёт реально вышел) — путь ГИР БО (годовая РСБУ) единоразово
    прогнался по ~165 компаниям и создал записи с created_at="сейчас", но published_at
    Feb-Apr 2026 (реальные даты сдачи годовой отчётности) — вся эта старая пачка легла
    поверх ленты, вытеснив свежие отчёты. Сортировка по реальной дате события чинит это:
    записи без published_at (часть ручного financials.json-пути) деградируют на created_at."""
    from app.models.earnings import EarningsReport, EarningsDigest, EarningsFigures
    q = (db.query(EarningsReport, EarningsDigest, EarningsFigures, Company.sector)
         .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
         .outerjoin(EarningsFigures, EarningsFigures.report_id == EarningsReport.id)
         .outerjoin(Company, Company.ticker == EarningsReport.ticker)
         .filter(EarningsReport.status == "processed")
         .order_by(func.coalesce(EarningsReport.published_at, EarningsReport.created_at).desc()))
    if portfolio_only:
        tickers, _ = _portfolio_filter(db, user)
        q = q.filter(EarningsReport.ticker.in_(tickers) if tickers else False)
    rows = q.limit(limit).all()

    def _yoy_pct(now, prev):
        if now is None or prev is None or float(prev) == 0:
            return None
        return round((float(now) / float(prev) - 1) * 100, 1)

    out = []
    for r, dg, fig, sector in rows:
        # Богатый разбор (report_watch._digest_rich, реальный текст источника) —
        # предпочитаем, если есть; иначе деградируем на узкий путь (маркеры ✅/❌/❗️
        # только по 3 цифрам — Path A из financials.json, или LLM-сбой богатого пути).
        if dg and dg.highlights is not None:
            positives, risks = dg.highlights, (dg.risks_or_caveats or [])
        else:
            positives, risks = _split_markers(dg.what_report_showed if dg else None)
        prev = (fig.prev or {}) if fig else {}
        out.append({
            "ticker": r.ticker, "period": r.period, "standard": r.standard,
            "report_type": r.report_type, "status": r.status,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "sector": sector,
            "one_liner": dg.one_liner if dg else None,
            "importance": dg.importance if dg else None,
            "positives": positives,
            "risks": risks,
            "conclusion": (dg.summary if dg else None),
            "data_gaps": (dg.data_gaps if dg else None),
            "revenue_pct": _yoy_pct(fig.revenue_ttm if fig else None, prev.get("revenue")),
            "ebitda_pct": _yoy_pct(fig.ebitda if fig else None, prev.get("ebitda")),
            "profit_pct": _yoy_pct(fig.net_profit_ttm if fig else None, prev.get("net_profit")),
        })
    return {"count": len(out), "reports": out}


@router.get("/market/corporate-news")
def market_corporate_news(portfolio_only: bool = False, days_back: int = 30, limit: int = 150,
                          db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Корпоративные события (Обозреватель) — лента НОВОСТЕЙ по компаниям, не календарь:
    вышедшие/ожидавшиеся-но-не-найденные отчёты, дивиденд по стадиям (объявлен/T-1 до
    отсечки), IPO/SPO, keyword-новости Ленты (M&A/менеджмент/див.решения/эмиссии/байбэк/
    смена акционеров/делистинг/обещанная дата отчётности) — см. app/services/corporate_news.py."""
    from app.services.corporate_news import build_corporate_news
    tickers = None
    if portfolio_only:
        t, _ = _portfolio_filter(db, user)
        tickers = list(t)
    items = build_corporate_news(db, portfolio_tickers=tickers, days_back=days_back, limit=limit)
    return {"count": len(items), "items": items}


@router.get("/market/calendar/bonds")
def market_calendar_bonds(sector: str | None = None, limit: int = 300,
                          db: Session = Depends(get_db)):
    """Справочные параметры облигаций (не скринер): тип купона, ставка, YTM, срок,
    оферта, номинал. Доходность флоатеров и бумаг с близкой офертой — ИНДИКАТИВНА."""
    from datetime import date
    from sqlalchemy import text
    today = date.today().isoformat()
    rows = db.execute(text("""
        SELECT secid, short_name, issuer_ticker, coupon_type, coupon_percent, ytm, ytm_kind,
               maturity_date, offer_date, face_value, agency_rating, currency
        FROM bonds
        WHERE is_defaulted IS NOT TRUE AND (maturity_date IS NULL OR maturity_date >= :t)
        ORDER BY maturity_date NULLS LAST LIMIT :lim
    """), {"t": today, "lim": limit}).all()
    out = []
    for r in rows:
        indicative = bool(r.coupon_type == "floater" or r.offer_date)
        out.append({
            "secid": r.secid, "name": r.short_name, "issuer_ticker": r.issuer_ticker,
            "coupon_type": r.coupon_type,
            "coupon_percent": float(r.coupon_percent) if r.coupon_percent is not None else None,
            "ytm": float(r.ytm) if r.ytm is not None else None, "ytm_kind": r.ytm_kind,
            "maturity_date": r.maturity_date.isoformat() if r.maturity_date else None,
            "offer_date": r.offer_date.isoformat() if r.offer_date else None,
            "face_value": float(r.face_value) if r.face_value is not None else None,
            "rating": r.agency_rating, "currency": r.currency,
            "yield_indicative": indicative,
        })
    return {"count": len(out), "bonds": out}


@router.get("/market/health/anthropic")
def anthropic_health_endpoint():
    from app.services.market_overview import check_anthropic_connectivity
    return check_anthropic_connectivity()


@router.get("/market/health/llm")
def health_llm():
    """Диагностика LLM-прослойки (провайдер/модель/наличие ключа) — без секретов."""
    from app.services import llm
    return llm.provider_info()


@router.get("/health/anthropic")
async def health_anthropic():
    """Проверить соединение с Anthropic через прокси"""
    try:
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=10,
            messages=[{"role": "user", "content": "test"}]
        )
        return {"status": "ok", "model": response.model}
    except Exception as e:
        return {"status": "error", "error": str(e)}
