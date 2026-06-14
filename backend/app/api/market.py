import os
from fastapi import APIRouter, Depends, HTTPException, Query, status
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


@router.get("/market/calendar")
def market_calendar(days: int = 90, db: Session = Depends(get_db)):
    """Календарь событий рынка из НАШИХ данных (без внешних API): предстоящие
    оферты и погашения облигаций + экспирации фьючерсов на горизонте `days` дней.
    Оферта — точка решения держателя (выкуп по номиналу / новый купон)."""
    from datetime import date, timedelta
    from sqlalchemy import text
    today = date.today()
    horizon = today + timedelta(days=days)
    events = []

    # оферты облигаций — важнейшее: точка решения «остаться или предъявить к выкупу»
    for r in db.execute(text(
        "SELECT secid, short_name, offer_date, agency_rating, coupon_type FROM bonds "
        "WHERE offer_date >= :t AND offer_date <= :h AND bond_type <> 'ofz' "
        "ORDER BY offer_date LIMIT 120"), {"t": today, "h": horizon}).all():
        events.append({"date": str(r[2]), "type": "offer", "kind": "bond",
                       "secid": r[0], "name": r[1], "rating": r[3],
                       "label": "Оферта (пут)", "coupon_type": r[4]})

    # погашения облигаций
    for r in db.execute(text(
        "SELECT secid, short_name, maturity_date, agency_rating FROM bonds "
        "WHERE maturity_date >= :t AND maturity_date <= :h AND bond_type <> 'ofz' "
        "ORDER BY maturity_date LIMIT 120"), {"t": today, "h": horizon}).all():
        events.append({"date": str(r[2]), "type": "maturity", "kind": "bond",
                       "secid": r[0], "name": r[1], "rating": r[3], "label": "Погашение"})

    # экспирации фьючерсов
    try:
        for r in db.execute(text(
            "SELECT secid, short_name, expiration_date, asset_name FROM futures "
            "WHERE expiration_date >= :t AND expiration_date <= :h "
            "ORDER BY expiration_date LIMIT 80"), {"t": today, "h": horizon}).all():
            events.append({"date": str(r[2]), "type": "expiration", "kind": "future",
                           "secid": r[0], "name": r[1], "label": "Экспирация",
                           "asset_name": r[3]})
    except Exception:
        pass

    events.sort(key=lambda e: e["date"])
    return {"as_of": str(today), "horizon_days": days, "count": len(events), "events": events}


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
