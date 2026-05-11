import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from anthropic import Anthropic
from app.db.session import get_db
from app.auth import get_current_user_optional
from app.models.market import OverviewType
from app.schemas.market import (
    MarketUpdateCreate, MarketUpdateResponse,
    MarketOverviewCreate, MarketOverviewResponse,
)
from app.services.market import (
    get_all_updates, create_update,
    get_all_overviews, create_overview,
)

router = APIRouter()


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
    if type != OverviewType.express:
        from app.models.user import SubscriptionType
        if not current_user or current_user.subscription_type != SubscriptionType.premium:
            raise HTTPException(
                status_code=403,
                detail="Детальный и глубокий обзор доступен только на Premium-тарифе",
            )
    try:
        from app.services.market_overview import generate_market_overview
        return generate_market_overview(type.value)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {e}")


@router.get("/market/health/anthropic")
def anthropic_health_endpoint():
    from app.services.market_overview import check_anthropic_connectivity
    return check_anthropic_connectivity()


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
