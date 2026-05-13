from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.company import Company, CompanyAnalysis, Quote
from app.schemas.company import CompanyCreate, AnalysisCreate, QuoteCreate


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    company = db.get(Company, company_id)
    if company:
        _attach_last_price(db, company)
        _attach_combined_cap(db, company)
    return company


def _attach_combined_cap(db: Session, company: Company) -> None:
    if company.paired_ticker and company.market_cap is not None:
        partner = db.query(Company).filter(Company.ticker == company.paired_ticker).first()
        if partner and partner.market_cap is not None:
            company.combined_market_cap = company.market_cap + partner.market_cap
            return
    company.combined_market_cap = company.market_cap


def get_company_by_ticker(db: Session, ticker: str) -> Company | None:
    return db.query(Company).filter(Company.ticker == ticker).first()


def _attach_last_price(db: Session, company: Company) -> None:
    latest = (
        db.query(Quote)
        .filter(Quote.company_id == company.id)
        .order_by(Quote.date.desc())
        .limit(1)
        .first()
    )
    if latest:
        company.last_price = latest.close
        company.change_pct = latest.change_pct
        company.change_abs = latest.change_abs
    else:
        company.last_price = None
        company.change_pct = None
        company.change_abs = None


def get_all_companies(db: Session) -> list[Company]:
    companies = db.query(Company).order_by(Company.market_cap.desc().nulls_last()).all()
    if not companies:
        return companies

    latest_sq = (
        db.query(Quote.company_id, func.max(Quote.date).label("max_date"))
        .group_by(Quote.company_id)
        .subquery()
    )
    quote_rows = (
        db.query(Quote.company_id, Quote.close, Quote.change_pct, Quote.change_abs)
        .join(latest_sq, (Quote.company_id == latest_sq.c.company_id) & (Quote.date == latest_sq.c.max_date))
        .all()
    )
    quote_map = {r.company_id: r for r in quote_rows}

    cap_by_ticker = {c.ticker: c.market_cap for c in companies if c.market_cap is not None}

    for c in companies:
        row = quote_map.get(c.id)
        c.last_price = row.close if row else None
        c.change_pct = row.change_pct if row else None
        c.change_abs = row.change_abs if row else None

        if c.paired_ticker and c.market_cap is not None:
            partner_cap = cap_by_ticker.get(c.paired_ticker)
            c.combined_market_cap = c.market_cap + partner_cap if partner_cap is not None else c.market_cap
        else:
            c.combined_market_cap = c.market_cap

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
