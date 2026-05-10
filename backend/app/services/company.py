from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.company import Company, CompanyAnalysis, Quote
from app.schemas.company import CompanyCreate, AnalysisCreate, QuoteCreate


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    company = db.get(Company, company_id)
    if company:
        _attach_last_price(db, company)
    return company


def get_company_by_ticker(db: Session, ticker: str) -> Company | None:
    return db.query(Company).filter(Company.ticker == ticker).first()


def _attach_last_price(db: Session, company: Company) -> None:
    latest = (
        db.query(Quote.close)
        .filter(Quote.company_id == company.id)
        .order_by(Quote.date.desc())
        .limit(1)
        .scalar()
    )
    company.last_price = latest


def get_all_companies(db: Session) -> list[Company]:
    companies = db.query(Company).order_by(Company.ticker).all()
    if not companies:
        return companies

    latest_sq = (
        db.query(Quote.company_id, func.max(Quote.date).label("max_date"))
        .group_by(Quote.company_id)
        .subquery()
    )
    price_rows = (
        db.query(Quote.company_id, Quote.close)
        .join(latest_sq, (Quote.company_id == latest_sq.c.company_id) & (Quote.date == latest_sq.c.max_date))
        .all()
    )
    price_map = {row.company_id: row.close for row in price_rows}
    for c in companies:
        c.last_price = price_map.get(c.id)
    return companies


def create_company(db: Session, data: CompanyCreate) -> Company:
    company = Company(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def get_analyses(db: Session, company_id: int) -> list[CompanyAnalysis]:
    return (
        db.query(CompanyAnalysis)
        .filter(CompanyAnalysis.company_id == company_id)
        .order_by(CompanyAnalysis.created_at.desc())
        .all()
    )


def add_analysis(db: Session, company_id: int, data: AnalysisCreate) -> CompanyAnalysis:
    analysis = CompanyAnalysis(company_id=company_id, **data.model_dump())
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


def get_quotes(db: Session, company_id: int) -> list[Quote]:
    return (
        db.query(Quote)
        .filter(Quote.company_id == company_id)
        .order_by(Quote.date.desc())
        .all()
    )


def add_quote(db: Session, company_id: int, data: QuoteCreate) -> Quote:
    quote = Quote(company_id=company_id, **data.model_dump())
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote
