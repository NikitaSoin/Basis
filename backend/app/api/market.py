import os
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy import or_
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


@router.get("/market/drivers")
def market_drivers(db: Session = Depends(get_db)):
    """«Что движет рынком сегодня» для пульса: Brent / USD-RUB / Ставка ЦБ / ОФЗ-10.
    Best-effort из имеющихся данных (фьючерсы/спот/макро/кривая ОФЗ); недоступное —
    помечается. value/dir = факт (котировка), effect = суждение Basis (не сигнал)."""
    from sqlalchemy import text as _t
    out = []

    # Нефть Brent — ближайший фьючерс BR (FORTS), $/барр
    try:
        r = db.execute(_t(
            "SELECT last_price, prev_settle FROM futures "
            "WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') AND last_price IS NOT NULL "
            "AND expiration_date >= now()::date ORDER BY expiration_date ASC LIMIT 1")).first()
        if r and r[0]:
            px = float(r[0]); prev = float(r[1]) if r[1] else None
            d = 0 if not prev else (1 if px > prev else -1 if px < prev else 0)
            out.append({"name": "Нефть Brent", "value": f"{px:.1f} $".replace(".", ","),
                        "dir": d, "effect": "поддержка нефтегазу при росте", "level": "факт"})
    except Exception:
        pass

    # Валюта — USD/RUB (спот)
    try:
        r = db.execute(_t("SELECT last_price, change_pct FROM spot_assets WHERE secid='USD000UTSTOM'")).first()
        if r and r[0]:
            px = float(r[0]); chg = float(r[1]) if r[1] is not None else 0
            d = 1 if chg > 0 else -1 if chg < 0 else 0
            out.append({"name": "USD / RUB", "value": f"{px:.2f}".replace(".", ","),
                        "dir": d, "effect": "слабее рубль — плюс экспортёрам", "level": "факт"})
    except Exception:
        pass

    # Ставка ЦБ (макро) — тот же источник, что и /market/macro/rate
    val = None
    try:
        from app.models.macro import MacroDataPoint
        p = (db.query(MacroDataPoint).filter_by(indicator_code="key_rate", metric="level")
             .order_by(MacroDataPoint.as_of.desc()).first())
        val = float(p.value) if p else None
    except Exception:
        val = None
    if val is not None:
        out.append({"name": "Ставка ЦБ", "value": f"{float(val):.1f} %".replace(".", ","),
                    "dir": 0, "effect": "выше ставка — давит на оценки акций", "level": "факт"})

    # ОФЗ 10 лет (кривая из нашей базы)
    try:
        from app.services.bond_risk import _ofz_curve_from_db, _ofz_at
        curve = _ofz_curve_from_db(db)
        y10 = _ofz_at(curve, 10)
        if y10:
            out.append({"name": "ОФЗ 10 лет", "value": f"{float(y10):.1f} %".replace(".", ","),
                        "dir": 0, "effect": "конкурент акциям за деньги", "level": "факт"})
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


@router.get("/market/geopolitics/{region}")
def market_geopolitics_region(region: str, tab: str = "deep",
                              db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    from app.models.geo import GeoBlock
    b = db.query(GeoBlock).filter_by(region=region, tab=tab).first()
    if not b:
        raise HTTPException(status_code=404, detail="Нет данных по региону/вкладке")
    return _geo_block_dict(b, set())


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
    Тап → карточка. portfolio_only — только бумаги портфеля."""
    from app.models.earnings import EarningsReport, EarningsDigest, EarningsFigures
    q = (db.query(EarningsReport, EarningsDigest, EarningsFigures, Company.sector)
         .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
         .outerjoin(EarningsFigures, EarningsFigures.report_id == EarningsReport.id)
         .outerjoin(Company, Company.ticker == EarningsReport.ticker)
         .order_by(EarningsReport.created_at.desc()))
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
            "revenue_pct": _yoy_pct(fig.revenue_ttm if fig else None, prev.get("revenue")),
            "ebitda_pct": _yoy_pct(fig.ebitda if fig else None, prev.get("ebitda")),
            "profit_pct": _yoy_pct(fig.net_profit_ttm if fig else None, prev.get("net_profit")),
        })
    return {"count": len(out), "reports": out}


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
