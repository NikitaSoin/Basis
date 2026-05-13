from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import get_db
from app.schemas.company import (
    CompanyCreate, CompanyResponse,
    AnalysisCreate, AnalysisResponse,
    QuoteCreate, QuoteResponse,
)
from app.services.company import (
    get_all_companies, get_company_by_id, get_company_by_ticker,
    create_company, get_analyses, add_analysis, get_quotes, add_quote,
)

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
    if tinkoff_quotes.is_available():
        tinkoff_quotes.refresh_prices()
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
    if search and len(search) >= 2:
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
