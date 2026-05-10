from sqlalchemy.orm import Session
from app.models.market import MarketUpdate, MarketOverview, OverviewType
from app.schemas.market import MarketUpdateCreate, MarketOverviewCreate


def get_all_updates(db: Session) -> list[MarketUpdate]:
    return db.query(MarketUpdate).order_by(MarketUpdate.published_at.desc()).all()


def create_update(db: Session, data: MarketUpdateCreate) -> MarketUpdate:
    update = MarketUpdate(**data.model_dump())
    db.add(update)
    db.commit()
    db.refresh(update)
    return update


def get_all_overviews(db: Session, overview_type: OverviewType | None = None) -> list[MarketOverview]:
    q = db.query(MarketOverview)
    if overview_type is not None:
        q = q.filter(MarketOverview.overview_type == overview_type)
    return q.order_by(MarketOverview.created_at.desc()).all()


def create_overview(db: Session, data: MarketOverviewCreate) -> MarketOverview:
    overview = MarketOverview(**data.model_dump())
    db.add(overview)
    db.commit()
    db.refresh(overview)
    return overview
