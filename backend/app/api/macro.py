"""API Макрообзора (Обозреватель, Направление 2).

GET /api/market/macro            — сводка показателей (фильтры country, portfolio_only)
GET /api/market/macro/{code}/series — ряд для графика (metric, from, to)
GET /api/market/macro/rate       — спец-блок ключевой ставки
GET /api/market/macro/analytics  — выжимки ЦБ/ЦМАКП
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user_optional
from app.models.company import Company
from app.models.portfolio import Portfolio, PortfolioPosition
from app.models.macro import MacroIndicator, MacroDataPoint, RateMeeting, MacroAnalyticsDoc

router = APIRouter()


def _latest_two(db: Session, code: str, metric: str):
    rows = (db.query(MacroDataPoint)
            .filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).limit(2).all())
    return rows


def _point_dict(p: MacroDataPoint, prev: MacroDataPoint | None):
    change = None
    if prev is not None and p is not None:
        try:
            change = float(p.value) - float(prev.value)
        except (TypeError, ValueError):
            change = None
    return {
        "metric": p.metric,
        "value": float(p.value),
        "as_of": p.as_of.isoformat(),
        "unit": p.unit,
        "is_preliminary": p.is_preliminary,
        "change": round(change, 4) if change is not None else None,
        "source": p.source,
        "source_url": p.source_url,
    }


def _portfolio_sectors(db: Session, user) -> set[str]:
    if not user:
        return set()
    rows = (db.query(Company.sector)
            .join(PortfolioPosition, PortfolioPosition.company_id == Company.id)
            .join(Portfolio, Portfolio.id == PortfolioPosition.portfolio_id)
            .filter(Portfolio.user_id == user.id).all())
    return {r[0] for r in rows if r[0]}


@router.get("/market/macro")
def macro_summary(country: str | None = None, portfolio_only: bool = False,
                  db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Сводка показателей с последним значением (по каждой метрике) и изменением."""
    q = db.query(MacroIndicator)
    if country:
        q = q.filter(MacroIndicator.country == country)
    indicators = q.order_by(MacroIndicator.sort_order).all()
    pf_sectors = _portfolio_sectors(db, user) if portfolio_only else set()

    out = []
    for ind in indicators:
        metrics = ind.metric_types or ["level"]
        values = {}
        for m in metrics:
            rows = _latest_two(db, ind.code, m)
            if rows:
                values[m] = _point_dict(rows[0], rows[1] if len(rows) > 1 else None)
        # ЛЁГКАЯ персонализация (по ТЗ): макропоказатели глобальны и влияют на всё,
        # поэтому portfolio_only НЕ фильтрует жёстко, а лишь ПОДСВЕЧИВАЕТ релевантные
        # секторам портфеля (in_portfolio → выделение на фронте).
        in_portfolio = bool(ind.sectors) and bool(pf_sectors & set(ind.sectors or []))
        out.append({
            "code": ind.code, "title": ind.title, "unit": ind.unit,
            "country": ind.country, "frequency": ind.frequency,
            "display_group": ind.display_group, "metric_types": ind.metric_types,
            "influence_short": ind.influence_short, "influence_full": ind.influence_full,
            "values": values, "has_data": bool(values), "in_portfolio": in_portfolio,
        })
    return out


@router.get("/market/macro/rate")
def macro_rate(db: Session = Depends(get_db)):
    """Спец-блок ставки: текущая ставка + последнее заседание + инфляция/ожидания."""
    def _last(code, metric="level"):
        p = (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
             .order_by(MacroDataPoint.as_of.desc()).first())
        return {"value": float(p.value), "as_of": p.as_of.isoformat()} if p else None

    meeting = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
    return {
        "key_rate": _last("key_rate"),
        "inflation_yoy": _last("inflation", "yoy"),
        "inflation_expectations": _last("inflation_expectations"),
        "meeting": {
            "decision_date": meeting.decision_date.isoformat() if meeting else None,
            "rate_value": float(meeting.rate_value) if meeting and meeting.rate_value else None,
            "signal": meeting.signal if meeting else None,
            "next_meeting_date": meeting.next_meeting_date.isoformat() if meeting and meeting.next_meeting_date else None,
            "consensus_forecast": meeting.consensus_forecast if meeting else None,
            "press_summary": meeting.press_summary if meeting else None,
        } if meeting else None,
    }


@router.get("/market/macro/analytics")
def macro_analytics(limit: int = Query(20, ge=1, le=100), source: str | None = None,
                    db: Session = Depends(get_db)):
    q = db.query(MacroAnalyticsDoc)
    if source:
        q = q.filter(MacroAnalyticsDoc.source == source)
    docs = q.order_by(MacroAnalyticsDoc.published_at.desc().nullslast(),
                      MacroAnalyticsDoc.created_at.desc()).limit(limit).all()
    return [{
        "id": d.id, "source": d.source, "doc_type": d.doc_type, "title": d.title,
        "summary": d.summary, "key_takeaways": d.key_takeaways,
        "published_at": d.published_at.isoformat() if d.published_at else None,
        "source_url": d.source_url, "model_used": d.model_used,
    } for d in docs]


@router.get("/market/macro/{code}/series")
def macro_series(code: str, metric: str = "level",
                 from_: str | None = Query(None, alias="from"), to: str | None = None,
                 db: Session = Depends(get_db)):
    ind = db.get(MacroIndicator, code)
    if not ind:
        raise HTTPException(status_code=404, detail="Показатель не найден")
    q = db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
    if from_:
        try:
            q = q.filter(MacroDataPoint.as_of >= date.fromisoformat(from_))
        except ValueError:
            pass
    if to:
        try:
            q = q.filter(MacroDataPoint.as_of <= date.fromisoformat(to))
        except ValueError:
            pass
    pts = q.order_by(MacroDataPoint.as_of).all()
    return {
        "code": code, "title": ind.title, "unit": ind.unit, "metric": metric,
        "points": [{"as_of": p.as_of.isoformat(), "value": float(p.value),
                    "is_preliminary": p.is_preliminary} for p in pts],
    }
