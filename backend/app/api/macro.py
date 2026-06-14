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
from app.models.macro import (MacroIndicator, MacroDataPoint, RateMeeting,
                              MacroAnalyticsDoc, MacroForecast, MacroInterpretation)

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


@router.get("/market/macro/_fedstat_diag")
def fedstat_diag(id: int = 43062):
    """ВРЕМЕННЫЙ диагностический эндпоинт: бэк (с боевого сервера) идёт на fedstat и
    возвращает сырой ответ — чтобы понять, что реально отдаёт EMISS из РФ (а не из dev).
    Пробует несколько вариантов запроса. Только чтение, без записи в БД."""
    import httpx
    results = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": "https://www.fedstat.ru/",
        "Connection": "keep-alive",
    }
    gbot = dict(headers); gbot["User-Agent"] = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    probes = {
        "fedstat_home": ("GET", "https://www.fedstat.ru/", None, headers),
        "fedstat_home_googlebot": ("GET", "https://www.fedstat.ru/", None, gbot),
        "fedstat_home_noua": ("GET", "https://www.fedstat.ru/", None, {"Accept": "*/*"}),
        "sdmx_gks": ("GET", "https://sdmx.gks.ru/", None, headers),
        "showdata_gks": ("GET", "https://showdata.gks.ru/", None, headers),
        "rosstat_gov": ("GET", "https://rosstat.gov.ru/", None, headers),
        "fedstat_indicator": ("GET", f"https://www.fedstat.ru/indicator/{id}", None, headers),
    }
    for name, (method, url, params, hdr) in probes.items():
        try:
            with httpx.Client(timeout=20, headers=hdr, follow_redirects=True) as c:
                r = c.request(method, url, params=params)
            body = r.text
            results[name] = {
                "status": r.status_code,
                "content_type": r.headers.get("content-type"),
                "len": len(body),
                "snippet": body[:300],
                "server": r.headers.get("server"),
            }
        except Exception as e:  # noqa: BLE001
            results[name] = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    return results


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

    meetings = (db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).limit(8).all())
    meeting = meetings[0] if meetings else None

    def _mtg(m):
        return {
            "decision_date": m.decision_date.isoformat(),
            "rate_value": float(m.rate_value) if m.rate_value is not None else None,
            "signal": m.signal, "next_meeting_date": m.next_meeting_date.isoformat() if m.next_meeting_date else None,
            "consensus_forecast": m.consensus_forecast, "press_summary": m.press_summary,
        }
    return {
        "key_rate": _last("key_rate"),
        "inflation_yoy": _last("inflation", "yoy"),
        "inflation_expectations": _last("inflation_expectations"),
        "meeting": _mtg(meeting) if meeting else None,
        "meetings": [_mtg(m) for m in meetings],  # история (новые сверху)
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
        "interpretation": d.interpretation,
        "published_at": d.published_at.isoformat() if d.published_at else None,
        "source_url": d.source_url, "model_used": d.model_used,
    } for d in docs]


@router.get("/market/macro/forecast")
def macro_forecast(db: Session = Depends(get_db)):
    """Среднесрочный прогноз ЦБ (последняя публикация)."""
    latest = db.query(MacroForecast).order_by(MacroForecast.as_of.desc()).first()
    if not latest:
        return {"rows": [], "as_of": None}
    rows = (db.query(MacroForecast)
            .filter(MacroForecast.as_of == latest.as_of, MacroForecast.scenario == latest.scenario)
            .order_by(MacroForecast.year).all())
    return {
        "as_of": latest.as_of.isoformat(), "scenario": latest.scenario,
        "comment": next((r.comment for r in rows if r.comment), None),
        "source_url": latest.source_url,
        "rows": [{"indicator": r.indicator, "year": r.year, "value": r.value} for r in rows],
    }


@router.get("/market/macro/interpretation")
def macro_interpretation_get(db: Session = Depends(get_db)):
    from app.services.macro_interpreter import get_latest
    row = get_latest(db)
    if not row:
        return {"sections": None}
    return {"sections": row.sections, "generated_at": row.generated_at.isoformat(),
            "model_used": row.model_used}


@router.post("/market/macro/interpretation")
def macro_interpretation_post(db: Session = Depends(get_db), user=Depends(get_current_user_optional)):
    """Ручная перегенерация интерпретации (DeepSeek Pro reasoning, ~1-2 мин)."""
    from app.services.macro_interpreter import generate
    from app.services.llm import LLMError
    try:
        row = generate(db)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"Интерпретатор недоступен: {e}")
    return {"sections": row.sections, "generated_at": row.generated_at.isoformat(),
            "model_used": row.model_used}


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
