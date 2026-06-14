from datetime import datetime
from pydantic import BaseModel
from app.models.market import OverviewType


class MarketUpdateCreate(BaseModel):
    title: str
    content: str
    source: str | None = None
    published_at: datetime


class MarketUpdateResponse(BaseModel):
    id: int
    title: str
    content: str | None = None
    source: str | None
    published_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class NewsItemResponse(BaseModel):
    id: int
    source: str | None
    source_url: str | None
    title: str
    rubric: str | None
    importance: str | None
    summary: str | None
    impact_comment: str | None
    affected_tickers: list[str] | None = None
    affected_sectors: list[str] | None = None
    sources_json: list | None = None
    cluster_id: str | None
    published_at: datetime
    model_config = {"from_attributes": True}


class MarketOverviewCreate(BaseModel):
    overview_type: OverviewType
    content: str
    period: str


class MarketOverviewResponse(BaseModel):
    id: int
    overview_type: OverviewType
    content: str
    period: str
    created_at: datetime

    model_config = {"from_attributes": True}
