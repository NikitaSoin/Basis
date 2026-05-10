from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.db.session import get_db
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
