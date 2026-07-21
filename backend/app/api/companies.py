import json
import re
from datetime import date, timedelta
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"
SECTORS_DIR = Path(__file__).parent.parent.parent.parent / "sectors"

# Разрешаем только безопасные имена (тикеры/ключи секторов) — защита от path traversal.
_SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")


def _safe(name: str) -> str:
    if not _SAFE_NAME.fullmatch(name or ""):
        raise HTTPException(status_code=404, detail="Not found")
    return name
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.schemas.company import (
    CompanyCreate, CompanyResponse,
    AnalysisCreate, AnalysisResponse,
    QuoteCreate, QuoteResponse,
)
from app.services.company import (
    get_all_companies, get_company_by_id, get_company_by_ticker,
    create_company, get_analyses, add_analysis, get_quotes, add_quote,
)
from app.services.live_multiples import live_scale_multiples
from app.services.live_wacc import live_recompute_valuation

router = APIRouter()


@router.get("/debug/tinkoff")
def debug_tinkoff_endpoint():
    """Диагностика Tinkoff API — показывает raw ответ и распределение полей."""
    import os, json, ssl, urllib.request
    token = os.environ.get("TINKOFF_API_TOKEN", "")
    if not token:
        return {"error": "TINKOFF_API_TOKEN не задан"}

    ctx = ssl.create_default_context()
    base = "https://invest-public-api.tinkoff.ru/rest"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    def post(path, body=None):
        url = f"{base}/{path}"
        data = json.dumps(body or {}).encode()
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return json.loads(r.read()), None
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.read().decode()[:500]}"
        except Exception as e:
            return None, str(e)

    # 1. Попробуем получить инструменты
    resp, err = post(
        "tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares",
        {"instrumentStatus": "INSTRUMENT_STATUS_ALL"},
    )
    if err:
        # Попробуем с числовым enum
        resp, err2 = post(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares",
            {"instrumentStatus": 2},
        )
        if err2:
            return {"error_string_enum": err, "error_int_enum": err2}

    instruments = resp.get("instruments", []) if resp else []

    # Статистика по exchange полю
    exchange_counts: dict[str, int] = {}
    for ins in instruments:
        ex = ins.get("exchange", "<empty>")
        exchange_counts[ex] = exchange_counts.get(ex, 0) + 1

    # Первые 3 с любым exchange
    sample_all = [
        {k: v for k, v in ins.items()
         if k in ("figi", "ticker", "exchange", "name", "uid", "classCode", "class_code")}
        for ins in instruments[:3]
    ]

    # Первые 3 где MOEX в exchange
    sample_moex = [
        {k: v for k, v in ins.items()
         if k in ("figi", "ticker", "exchange", "name", "uid", "classCode")}
        for ins in instruments
        if "MOEX" in (ins.get("exchange", "").upper())
    ][:3]

    # 2. Проверим GetLastPrices с одним FIGI (Сбер)
    sber_figi = "BBG004730N88"
    prices_resp, prices_err = post(
        "tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
        {"figi": [sber_figi]},
    )
    if prices_err:
        prices_resp, prices_err = post(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
            {"instrumentId": [sber_figi]},
        )

    return {
        "token_length": len(token),
        "total_instruments": len(instruments),
        "exchange_distribution": exchange_counts,
        "sample_first_3": sample_all,
        "sample_moex_3": sample_moex,
        "sber_price_test": {
            "response": prices_resp,
            "error": prices_err,
        },
    }


@router.get("/quotes/latest")
def latest_quotes_endpoint(db: Session = Depends(get_db)):
    """Последняя цена закрытия из БД: {ticker: close}"""
    rows = db.execute(text("""
        SELECT DISTINCT ON (q.company_id)
            c.ticker,
            q.close
        FROM quotes q
        JOIN companies c ON c.id = q.company_id
        WHERE q.close IS NOT NULL
        ORDER BY q.company_id, q.date DESC
    """)).fetchall()
    return {row.ticker: float(row.close) for row in rows}


@router.get("/companies/logos")
def company_logos_endpoint():
    """{ticker: URL логотипа} — бренды T-Инвестиций (надёжный машинный источник).
    Фронт берёт карту один раз и кэширует; картинки кэшируются браузером/CDN."""
    from app.services import tinkoff_quotes
    return tinkoff_quotes.get_logos()


@router.get("/companies/instrument-logos")
def instrument_logos_endpoint():
    """{ISIN или secid: URL логотипа} для облигаций (по ISIN)/фондов/
    фьючерсов/валюты (по тикеру Т-Инвестиций = наш secid) — логотип самого
    инструмента у брокера, не обязательно компании-эмитента (владелец: «у
    любой облигации/фьючерса/фонда есть своя картинка в Т-Инвестициях»)."""
    from app.services import tinkoff_quotes
    return tinkoff_quotes.get_instrument_logos()


@router.get("/quotes/source")
def quotes_source_endpoint():
    """Диагностика: какой источник котировок активен."""
    from app.services import tinkoff_quotes
    return tinkoff_quotes.status() | {
        "active_source": "tinkoff" if tinkoff_quotes.is_available() else "moex_iss",
    }


@router.get("/quotes/realtime")
def realtime_quotes_endpoint():
    """Котировки в реальном времени. Primary: Tinkoff. Fallback: MOEX ISS."""
    no_cache = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    # ── Tinkoff (primary) ───────────────────────────────────────────────────
    from app.services import tinkoff_quotes
    # НЕ блокируем запрос сетевым вызовом: отдаём кэш, обновляем в фоне (throttle 15с).
    # Раньше refresh_prices() звался синхронно на КАЖДЫЙ запрос → частый поллинг фронта
    # копил занятые потоки воркера и весь бэк вставал.
    if tinkoff_quotes.is_configured():
        tinkoff_quotes.maybe_refresh_async()
    if tinkoff_quotes.is_available():
        prices = tinkoff_quotes.get_all_prices()
        payload = {ticker: q for ticker, q in prices.items()}
        payload["_source"] = "tinkoff"
        payload["_fetched_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
        return JSONResponse(content=payload, headers=no_cache)

    # ── MOEX ISS (fallback) ─────────────────────────────────────────────────
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
        from fetch_quotes import fetch_moex_bulk
        bulk = fetch_moex_bulk()
        moex_time = bulk.pop("_moex_time", None)
        fetched_at = bulk.pop("_fetched_at", None)
        payload = {
            ticker: {
                "price": q["close"],
                "change_abs": q["change_abs"],
                "change_pct": q["change_pct"],
            }
            for ticker, q in bulk.items()
        }
        payload["_source"] = "moex_iss"
        payload["_moex_time"] = moex_time
        payload["_fetched_at"] = fetched_at
        return JSONResponse(content=payload, headers=no_cache)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Котировки недоступны: {e}")


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company_endpoint(data: CompanyCreate, db: Session = Depends(get_db)):
    if get_company_by_ticker(db, data.ticker):
        raise HTTPException(status_code=409, detail="Ticker already exists")
    return create_company(db, data)


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies_endpoint(search: str | None = None, db: Session = Depends(get_db)):
    companies = get_all_companies(db)
    if search:
        q = search.upper()
        companies = [c for c in companies if q in c.ticker.upper() or q in c.name.upper()]
    return companies


@router.get("/companies/{company_id}", response_model=CompanyResponse)
def get_company_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("/companies/{company_id}/analysis", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
def add_analysis_endpoint(company_id: int, data: AnalysisCreate, db: Session = Depends(get_db)):
    if not get_company_by_id(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return add_analysis(db, company_id, data)


@router.get("/companies/{company_id}/analysis", response_model=list[AnalysisResponse])
def list_analyses_endpoint(company_id: int, db: Session = Depends(get_db)):
    if not get_company_by_id(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return get_analyses(db, company_id)


@router.post("/companies/{company_id}/quotes", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
def add_quote_endpoint(company_id: int, data: QuoteCreate, db: Session = Depends(get_db)):
    if not get_company_by_id(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return add_quote(db, company_id, data)


@router.get("/companies/{company_id}/quotes", response_model=list[QuoteResponse])
def list_quotes_endpoint(company_id: int, db: Session = Depends(get_db)):
    if not get_company_by_id(db, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return get_quotes(db, company_id)


@router.get("/companies/by-ticker/{ticker}/quotes/history")
def quotes_history_endpoint(ticker: str, days: int = Query(180, ge=5, le=4000),
                            db: Session = Depends(get_db)):
    """Дневной ряд цены акции для графика (вкладка «Обзор» карточки компании,
    период по выбору). Источник — quotes (та же таблица, что живая цена).
    Формат ответа зеркалит /market/instruments/{asset_class}/{secid}/history
    (облигации/фьючерсы/фонды) — на фронте один общий компонент графика для
    всех классов активов."""
    company = get_company_by_ticker(db, _safe(ticker).upper())
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    start = date.today() - timedelta(days=days)
    rows = db.execute(text(
        "SELECT date, close FROM quotes WHERE company_id=:cid AND date>=:d "
        "ORDER BY date ASC"), {"cid": company.id, "d": start}).all()
    # Сплит/консолидация (кейс T, ~1:10, 2026-04-17) даёт разрыв цены в разы —
    # без корректировки график читается как обвал, хотя де-факто акция не
    # подешевела. normalize_splits — та же логика, что уже используется для
    # доходности/риска (risk_metrics.py), здесь впервые применена к самому
    # графику цены.
    from app.services.risk_metrics import normalize_splits
    raw_series = {r.date: float(r.close) for r in rows if r.close is not None and float(r.close) > 0}
    adj_series = normalize_splits(raw_series)
    pts = [{"date": str(r.date), "close": adj_series.get(r.date, float(r.close) if r.close is not None else None)} for r in rows]
    last = pts[-1]["close"] if pts else None
    prev = pts[-2]["close"] if len(pts) >= 2 else None
    change_pct = round((last / prev - 1) * 100, 2) if last and prev else None
    return {"asset_class": "stock", "ticker": ticker.upper(), "last": last,
            "change_pct": change_pct, "points": pts}


@router.get("/companies/by-ticker/{ticker}/profile")
async def get_company_profile(ticker: str, db: Session = Depends(get_db)):
    profile = db.query(CompanyProfile).filter(
        CompanyProfile.ticker == ticker.upper()
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile.profile_json


@router.get("/companies/by-ticker/{ticker}/business-model", response_class=PlainTextResponse)
async def get_business_model_md(ticker: str):
    path = COMPANIES_DIR / ticker.upper() / "business_model.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Business model not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


def _flat_ok(te) -> bool:
    return (isinstance(te, list) and any(x is not None for x in te)) or isinstance(te, (int, float))


def _normalize_financials(fin: dict) -> dict:
    """Нормализация на отдаче — чтобы не латать руками после каждого прогона агента.
    total_equity витрина читает ПЛОСКИМ полем balance_sheet.total_equity; агент кладёт
    его по-разному: вложенным в equity.total_equity (обычный профиль) или в
    bank_balance.total_equity (банк). Восстанавливаем плоское из любого источника,
    создавая balance_sheet при необходимости. Идемпотентно, без записи на диск."""
    bs = fin.get("balance_sheet")
    if not isinstance(bs, dict):
        bs = {}
    te = bs.get("total_equity")
    if not _flat_ok(te):
        # источники по приоритету: equity.total_equity → bank_balance.total_equity
        src = None
        eq = bs.get("equity")
        if isinstance(eq, dict) and _flat_ok(eq.get("total_equity")):
            src = eq.get("total_equity")
        if src is None:
            bb = fin.get("bank_balance")
            if isinstance(bb, dict) and _flat_ok(bb.get("total_equity")):
                src = bb.get("total_equity")
        if src is not None:
            bs["total_equity"] = src
            fin["balance_sheet"] = bs
    return fin


@router.get("/companies/by-ticker/{ticker}/financials")
async def get_financials_json(ticker: str, db: Session = Depends(get_db)):
    """Блок «Финансы и оценка» в виде JSON (его рисует фронтенд). multiples.current
    пересчитывается от ЖИВОЙ капитализации (см. live_scale_multiples) — цена не
    застывает на дату последнего прогона аналитика."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "financials.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Financials not found")
    fin = _normalize_financials(json.loads(path.read_text(encoding="utf-8")))
    row = db.execute(
        text("SELECT market_cap, shares_outstanding FROM companies WHERE ticker = :t"),
        {"t": _safe(ticker).upper()},
    ).first()
    if row is not None and fin.get("multiples", {}).get("current"):
        live_cur = live_scale_multiples(fin, row[0], row[1])
        fin.setdefault("multiples", {})["current"] = live_cur
    if fin.get("valuation", {}).get("methods"):
        shares_outstanding = row[1] if row is not None else None
        live_price = None
        if row is not None and row[0] and row[1]:
            live_price = float(row[0]) / float(row[1])
        fin["valuation"] = live_recompute_valuation(fin, db, shares_outstanding, live_price, _safe(ticker).upper())
    return JSONResponse(content=fin)


@router.get("/companies/by-ticker/{ticker}/earnings/latest")
def get_latest_earnings(ticker: str, db: Session = Depends(get_db)):
    """Разбор последнего отчёта для карточки (Направление 3): метрики + блок «Разбор отчёта».
    Состояния: нет отчёта (404), отчёт без разбора (status=extract_failed)."""
    from app.models.earnings import EarningsReport, EarningsFigures, EarningsDigest
    r = (db.query(EarningsReport).filter(EarningsReport.ticker == _safe(ticker).upper())
         .order_by(EarningsReport.created_at.desc()).first())
    if not r:
        raise HTTPException(status_code=404, detail="Нет разобранных отчётов")
    fig = db.query(EarningsFigures).filter_by(report_id=r.id).first()
    dg = db.query(EarningsDigest).filter_by(report_id=r.id).first()
    def f(v):
        return float(v) if v is not None else None
    return {
        "ticker": r.ticker, "period": r.period, "standard": r.standard,
        "report_type": r.report_type, "status": r.status,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "source_url": r.source_url,
        "figures": {
            "unit": "млн ₽", "revenue_ttm": f(fig.revenue_ttm), "ebitda": f(fig.ebitda),
            "net_profit_ttm": f(fig.net_profit_ttm), "adjusted_profit": f(fig.adjusted_profit),
            "is_company_adjusted": fig.is_company_adjusted, "net_debt": f(fig.net_debt),
            "nd_ebitda": f(fig.nd_ebitda), "price": f(fig.price), "pe_ttm": f(fig.pe_ttm),
            "pb": f(fig.pb), "ev_ebitda": f(fig.ev_ebitda), "prev": fig.prev,
        } if fig else None,
        "digest": {
            "headline": dg.headline, "one_liner": dg.one_liner,
            "what_report_showed": dg.what_report_showed, "what_changed": dg.what_changed,
            "summary": dg.summary, "importance": dg.importance, "model_used": dg.model_used,
        } if dg else None,
        "disclaimer": "Ознакомительный разбор события «вышел отчёт». Не является ИИР.",
    }


@router.get("/companies/by-ticker/{ticker}/financials-summary", response_class=PlainTextResponse)
async def get_financials_summary_md(ticker: str):
    """Текстовая интерпретация блока «Финансы и оценка» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "financials_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Financials summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


_GOV_MAPPING_PATH = Path(__file__).parent.parent.parent.parent / "config" / "governance_mapping.json"
_GOV_MAPPING_CACHE: dict = {"ts": 0.0, "data": None}


def _gov_mapping() -> dict:
    """config/governance_mapping.json с лёгким кэшем (60с) — горячая правка контура без рестарта."""
    import time
    now = time.time()
    if _GOV_MAPPING_CACHE["data"] is not None and now - _GOV_MAPPING_CACHE["ts"] < 60:
        return _GOV_MAPPING_CACHE["data"]
    try:
        data = json.loads(_GOV_MAPPING_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    _GOV_MAPPING_CACHE.update(ts=now, data=data)
    return data


def compute_governance_premium(overall_score, red_flags, cfg=None):
    """Балл governance (1..5) + красные флаги → премия к ставке дисконтирования (п.п.)
    по активному контуру config/governance_mapping.json. Интерполяция по опорным точкам;
    override красными флагами; потолок cap_pp. None при отсутствии балла. Это ФИНАНС-СЛОЙ
    (а не субагент): число считается здесь, контуры a/b переключаются полем active_contour."""
    cfg = cfg or _gov_mapping()
    if not cfg:
        return None
    try:
        score = float(overall_score)
    except (TypeError, ValueError):
        return None
    contour = cfg.get(cfg.get("active_contour") or "", {})
    anchors = contour.get("anchors") or {}
    pts = sorted((float(k), float(v)) for k, v in anchors.items())
    if not pts:
        return None
    # линейная интерполяция; за пределами опорных — берём крайнюю точку (плато)
    if score <= pts[0][0]:
        pp = pts[0][1]
    elif score >= pts[-1][0]:
        pp = pts[-1][1]
    else:
        pp = pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= score <= x1:
                pp = y0 + (y1 - y0) * (score - x0) / (x1 - x0) if x1 != x0 else y0
                break
    # override красными флагами
    ov = cfg.get("overrides") or {}
    flags = [f for f in (red_flags or []) if isinstance(f, dict) and f.get("active")]
    if flags:
        severe = any((f.get("severity") in ("high", "severe")) for f in flags)
        floor = ov.get("severe_red_flag_pp") if severe else ov.get("any_red_flag_min_pp")
        if isinstance(floor, (int, float)):
            pp = max(pp, floor)
    cap = cfg.get("cap_pp")
    if isinstance(cap, (int, float)):
        pp = min(pp, cap)
    return round(pp, 2)


@router.get("/companies/by-ticker/{ticker}/governance")
async def get_governance_json(ticker: str):
    """Блок «Корпоративное управление» в виде JSON (его рисует фронтенд). Премию к ставке
    (governance_discount) считаем ЗДЕСЬ по config/governance_mapping.json от scoring.overall_score
    + red_flags — единый источник числа для фронта и DCF (субагент число не зашивает)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "governance.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Governance not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    scoring = data.get("scoring") or {}
    overall = scoring.get("overall_score")
    if overall is not None:
        cfg = _gov_mapping()
        pp = compute_governance_premium(overall, scoring.get("red_flags"), cfg)
        gd = data.get("governance_discount")
        if not isinstance(gd, dict):
            gd = {}
        gd["premium_to_wacc_pp_computed"] = pp
        gd["contour"] = cfg.get("active_contour")
        data["governance_discount"] = gd
    return JSONResponse(content=data)


@router.get("/companies/by-ticker/{ticker}/governance-summary", response_class=PlainTextResponse)
async def get_governance_summary_md(ticker: str):
    """Текстовая интерпретация блока «Корпоративное управление» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "governance_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Governance summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/companies/by-ticker/{ticker}/market")
async def get_market_json(ticker: str):
    """Блок «Рынки» в виде JSON (его рисует фронтенд: доли, динамика, прогноз)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "market.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Market not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.get("/companies/by-ticker/{ticker}/market-summary", response_class=PlainTextResponse)
async def get_market_summary_md(ticker: str):
    """Текстовая интерпретация блока «Рынки» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "market_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Market summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/companies/by-ticker/{ticker}/macro")
async def get_macro_json(ticker: str):
    """Блок «Макро» в виде JSON (его рисует фронтенд: факторы, знаки эффекта)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "macro.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Macro not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Подстраховка: есть числовые входы, но computed не посчитан (файл запечён без enrich
    # или устарел) → досчитать детерминированно на лету. Расчёт мгновенный, старые файлы
    # без quant_inputs не трогаются (computed остаётся пустым, фронт деградирует грациозно).
    if data.get("quant_inputs") and not (data.get("computed") or {}).get("attribution"):
        from app.services import macro_quant
        macro_quant.enrich(data)
    return JSONResponse(content=data)


@router.get("/companies/by-ticker/{ticker}/macro-summary", response_class=PlainTextResponse)
async def get_macro_summary_md(ticker: str):
    """Текстовая интерпретация блока «Макро» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "macro_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Macro summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/companies/by-ticker/{ticker}/geo")
async def get_geo_json(ticker: str):
    """Блок «Геополитика» в виде JSON (его рисует фронтенд: факторы, сценарии, знаки)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "geo.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Geo not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.get("/companies/by-ticker/{ticker}/geo-summary", response_class=PlainTextResponse)
async def get_geo_summary_md(ticker: str):
    """Текстовая интерпретация блока «Геополитика» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "geo_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Geo summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/companies/by-ticker/{ticker}/institutions")
async def get_institutions_json(ticker: str):
    """Блок «Институты» (IRI): клановый патронаж, S1-S15, трёхканальная
    институциональная поправка к оценке. Методика — docs/Институты_агенты.md,
    docs/Институты_дополнение.md; заполняет institutional-company-analyst."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "institutions.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Institutions not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


@router.get("/companies/by-ticker/{ticker}/institutions-summary", response_class=PlainTextResponse)
async def get_institutions_summary_md(ticker: str):
    """Текстовая интерпретация блока «Институты» (markdown)."""
    path = COMPANIES_DIR / _safe(ticker).upper() / "institutions_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Institutions summary not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/sectors/{sector_key}/peers")
async def get_sector_peers(sector_key: str):
    """Сравнение конкурентов по сектору + данные для карт-координат."""
    path = SECTORS_DIR / _safe(sector_key).lower() / "peers.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sector peers not found")
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))


_SECTOR_MULT_CACHE: dict = {"ts": 0.0, "data": None}
_SECTOR_PEERS_CACHE: dict = {"ts": 0.0, "data": None}


@router.get("/sectors/multiples")
def sector_multiples(db: Session = Depends(get_db)):
    """Медианы мультипликаторов по секторам — для контекста карточек на вкладке «Финансы»
    («дешевле/дороже сектора»). Считается из financials.json всех компаний (текущие
    pe/ps/pb/ev_ebitda + ND/EBITDA + ROE), исключая аномальные. Кэш 1ч."""
    import time
    now = time.time()
    if _SECTOR_MULT_CACHE["data"] is not None and now - _SECTOR_MULT_CACHE["ts"] < 3600:
        return _SECTOR_MULT_CACHE["data"]

    def _med(xs):
        xs = sorted(v for v in xs if v is not None)
        n = len(xs)
        if not n:
            return None
        return round(xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2, 2)

    sectors = {r[0]: (r[1], r[2], r[3]) for r in db.execute(
        text("SELECT ticker, sector, market_cap, shares_outstanding FROM companies")
    ).all()}
    buckets: dict = {}
    for tk, (sec, mcap, so) in sectors.items():
        if not sec:
            continue
        fp = COMPANIES_DIR / tk / "financials.json"
        if not fp.exists():
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("anomaly_flag"):
            continue
        cur = live_scale_multiples(d, mcap, so)
        mt = d.get("metrics_timeseries") or {}
        rs = d.get("returns") or {}

        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        last = lambda a: _f(a[-1]) if isinstance(a, list) and a else None
        row = {
            "pe": _f(cur.get("pe")), "ps": _f(cur.get("ps")), "pb": _f(cur.get("pb")),
            "ev_ebitda": _f(cur.get("ev_ebitda")),
            "nd_ebitda": last(mt.get("net_debt_ebitda")),
            "roe": last(rs.get("roe")) if rs.get("roe") else last(mt.get("roe")),
        }
        b = buckets.setdefault(sec, {k: [] for k in row})
        b["_n"] = b.get("_n", 0)
        for k, v in row.items():
            # отсекаем явные искажения (отрицательный/гигантский P/E и т.п.)
            if v is None:
                continue
            if k in ("pe", "ev_ebitda") and (v <= 0 or v > 60):
                continue
            if k == "pb" and (v <= 0 or v > 30):
                continue
            b[k].append(v)
    out = {}
    for sec, b in buckets.items():
        out[sec] = {k: _med(b[k]) for k in ("pe", "ps", "pb", "ev_ebitda", "nd_ebitda", "roe")}
        out[sec]["n"] = max(len(b["pe"]), len(b["ev_ebitda"]))
    _SECTOR_MULT_CACHE.update(ts=now, data=out)
    return out


@router.get("/sectors/peers-multiples")
def sector_peers_multiples(db: Session = Depends(get_db)):
    """Мультипликаторы конкурентов ПО ГОДАМ для блока «Позиционирование в секторе»
    вкладки «Финансы» (таблица сравнения с годовым переключателем + карты сектора).
    По каждой компании сектора — ряд pe/ps/pb/ev_ebitda/nd_ebitda/roe по фискальным
    годам из её financials.json (metrics_timeseries + returns.roe). Кэш 1ч."""
    import time
    now = time.time()
    if _SECTOR_PEERS_CACHE["data"] is not None and now - _SECTOR_PEERS_CACHE["ts"] < 3600:
        return _SECTOR_PEERS_CACHE["data"]

    def _f(v):
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None

    sectors = {r[0]: (r[1], r[2], r[3], r[4]) for r in db.execute(
        text("SELECT ticker, sector, name, market_cap, shares_outstanding FROM companies")
    ).all()}
    out: dict = {}
    for tk, (sec, nm, mcap, so) in sectors.items():
        if not sec:
            continue
        fp = COMPANIES_DIR / tk / "financials.json"
        if not fp.exists():
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta = d.get("meta") or {}
        years = [str(y) for y in (meta.get("fiscal_years") or [])]
        if not years:
            continue
        mt = d.get("metrics_timeseries") or {}
        rs = d.get("returns") or {}
        src = {
            "pe": mt.get("pe"), "ps": mt.get("ps"), "pb": mt.get("pb"),
            "ev_ebitda": mt.get("ev_ebitda"), "nd_ebitda": mt.get("net_debt_ebitda"),
            "roe": rs.get("roe") or mt.get("roe"),
        }
        by_year: dict = {}
        for i, y in enumerate(years):
            row = {}
            for k, arr in src.items():
                v = _f(arr[i]) if isinstance(arr, list) and i < len(arr) else None
                if v is not None:
                    row[k] = v
            if row:
                by_year[y] = row
        # Последний год в ряду = «текущий» снимок (совпадает с multiples.current) —
        # он устаревает так же, как и сам current; пересчитываем от живой капы.
        if years and years[-1] in by_year:
            live_cur = live_scale_multiples(d, mcap, so)
            for k in ("pe", "ps", "pb", "ev_ebitda"):
                v = live_cur.get(k)
                if isinstance(v, (int, float)):
                    by_year[years[-1]][k] = round(v, 2)
        if not by_year:
            continue
        out.setdefault(sec, {"years": [], "peers": []})
        for y in years:
            if y not in out[sec]["years"]:
                out[sec]["years"].append(y)
        out[sec]["peers"].append({
            "ticker": tk,
            "name": nm or tk,
            "anomaly": bool(d.get("anomaly_flag")),
            "by_year": by_year,
        })
    for sec in out:
        out[sec]["years"].sort()
    _SECTOR_PEERS_CACHE.update(ts=now, data=out)
    return out
