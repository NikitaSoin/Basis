from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class CompanyCreate(BaseModel):
    ticker: str
    name: str
    sector: str | None = None
    description: str | None = None
    market_cap: Decimal | None = None


class CompanyResponse(BaseModel):
    id: int
    ticker: str
    name: str
    sector: str | None
    description: str | None
    market_cap: Decimal | None = None
    created_at: datetime
    last_price: Decimal | None = None
    change_pct: Decimal | None = None
    change_abs: Decimal | None = None

    model_config = {"from_attributes": True}


class AnalysisCreate(BaseModel):
    bull_case: list[str] | None = None
    bear_case: list[str] | None = None
    risks: list[str] | None = None
    fair_price: Decimal | None = None
    analyst_note: str | None = None
    business_model: dict | None = None
    financials: dict | None = None
    competitors: dict | None = None
    macro_economy: dict | None = None
    global_economy: dict | None = None
    geopolitics: dict | None = None
    technical_analysis: dict | None = None


class AnalysisResponse(BaseModel):
    id: int
    company_id: int
    bull_case: list[str] | None
    bear_case: list[str] | None
    risks: list[str] | None
    fair_price: Decimal | None
    analyst_note: str | None
    business_model: dict | None
    financials: dict | None
    competitors: dict | None
    macro_economy: dict | None
    global_economy: dict | None
    geopolitics: dict | None
    technical_analysis: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuoteCreate(BaseModel):
    date: date
    open: Decimal | None = None
    close: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: int | None = None


class QuoteResponse(BaseModel):
    id: int
    company_id: int
    date: date
    open: Decimal | None
    close: Decimal | None
    high: Decimal | None
    low: Decimal | None
    volume: int | None

    model_config = {"from_attributes": True}
