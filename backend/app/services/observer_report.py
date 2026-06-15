"""ИИ-обозревательский отчёт (Обозреватель, Направление 5) — СИНТЕЗ-слой.

Сам никуда не ходит: пересобирает уже собранные данные направлений 1-4,6,7 + портфель
в сводный дайджест трёх глубин. LLM ТОЛЬКО синтезирует переданный контекст (без
внешних источников и выдумок), каждый тезис ссылается на элемент контекста (id/ref),
без «купить/продать».
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.observer_report import ObserverReport, HORIZON_DAYS
from app.models.company import Company
from app.models.portfolio import Portfolio, PortfolioPosition

logger = logging.getLogger(__name__)


def _portfolio(db: Session, user_id: int) -> tuple[set[str], set[str]]:
    rows = (db.query(Company.ticker, Company.sector)
            .join(PortfolioPosition, PortfolioPosition.company_id == Company.id)
            .join(Portfolio, Portfolio.id == PortfolioPosition.portfolio_id)
            .filter(Portfolio.user_id == user_id).all())
    return {r[0] for r in rows if r[0]}, {r[1] for r in rows if r[1]}


# ----------------------------- СБОР КОНТЕКСТА -----------------------------
def _gather(db: Session, rtype: str, pf_tickers: set[str], pf_sectors: set[str]) -> tuple[dict, list]:
    """Контекст обозревателя по горизонту/охвату типа + список source_refs (ref→элемент)."""
    today = date.today()
    days = HORIZON_DAYS[rtype]
    ctx: dict = {"today": today.isoformat(), "report_type": rtype, "horizon_days": days,
                 "portfolio_tickers": sorted(pf_tickers), "portfolio_sectors": sorted(pf_sectors)}
    refs: list = []

    n_news = {"express": 4, "detailed": 12, "deep": 30}[rtype]
    from app.models.market import MarketUpdate
    news = (db.query(MarketUpdate).filter(MarketUpdate.status == "published")
            .order_by(MarketUpdate.published_at.desc()).limit(n_news).all())
    ctx["news"] = []
    for i, u in enumerate(news, 1):
        ref = f"N{i}"
        tickers = u.affected_tickers or []
        ctx["news"].append({"ref": ref, "title": u.title,
                            "impact": (u.impact_comment or "")[:200], "category": u.category,
                            "tickers": tickers, "in_portfolio": bool(set(tickers) & pf_tickers)})
        refs.append({"ref": ref, "kind": "news", "id": u.id, "title": u.title, "url": u.source_url})

    # Отчёты (Напр.3) — портфель + крупные
    from app.models.earnings import EarningsReport, EarningsDigest
    er = (db.query(EarningsReport, EarningsDigest)
          .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
          .order_by(EarningsReport.created_at.desc())
          .limit({"express": 6, "detailed": 14, "deep": 30}[rtype]).all())
    ctx["earnings"] = []
    for i, (r, dg) in enumerate(er, 1):
        ref = f"E{i}"
        ctx["earnings"].append({"ref": ref, "ticker": r.ticker, "period": r.period,
                               "standard": r.standard, "one_liner": dg.one_liner if dg else None,
                               "in_portfolio": r.ticker in pf_tickers})
        refs.append({"ref": ref, "kind": "earnings", "ticker": r.ticker, "title": f"{r.ticker} {r.period}"})

    # Календарь (Напр.4) — будущие события в горизонте
    from app.models.calendar_event import CalendarEvent
    horizon = today + timedelta(days=days)
    ce = (db.query(CalendarEvent)
          .filter(CalendarEvent.event_date >= today, CalendarEvent.event_date <= horizon)
          .order_by(CalendarEvent.event_date.asc())
          .limit({"express": 8, "detailed": 25, "deep": 60}[rtype]).all())
    ctx["calendar"] = []
    for i, e in enumerate(ce, 1):
        ref = f"C{i}"
        ctx["calendar"].append({"ref": ref, "type": e.event_type, "date": e.event_date.isoformat(),
                               "title": e.title, "ticker": e.ticker,
                               "in_portfolio": bool(e.ticker and e.ticker in pf_tickers)})
        refs.append({"ref": ref, "kind": "calendar", "id": e.id, "title": e.title})

    # Макро (Напр.2) — для detailed/deep
    if rtype in ("detailed", "deep"):
        ctx["macro"] = _macro_snapshot(db, today, horizon)

    # Геополитика (Напр.7) + Карты (Напр.6) — только deep
    if rtype == "deep":
        ctx["geopolitics"] = _geo_snapshot(db)
        ctx["valuation_map"] = _maps_snapshot(db, pf_tickers)

    return ctx, refs


def _macro_snapshot(db: Session, today: date, horizon: date) -> dict:
    out = {}
    def last(code, metric="level"):
        r = db.execute(text("SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
                            "AND metric=:m ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()
        return {"value": float(r.value), "as_of": r.as_of.isoformat()} if r else None
    out["key_rate"] = last("key_rate")
    out["inflation_yoy"] = last("inflation", "yoy")
    out["usdrub"] = last("usdrub")
    try:
        from app.models.macro import RateMeeting
        m = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
        if m and m.next_meeting_date and today <= m.next_meeting_date <= horizon:
            out["rate_meeting_in_horizon"] = m.next_meeting_date.isoformat()
    except Exception:  # noqa: BLE001
        pass
    return out


def _geo_snapshot(db: Session) -> list:
    from app.models.geo import GeoBlock
    rows = db.query(GeoBlock).filter_by(tab="overview").all()
    return [{"region": b.title, "status": (b.status_text or "")[:300],
             "market_impact": (b.market_impact or "")[:200]} for b in rows]


def _maps_snapshot(db: Session, pf_tickers: set[str]) -> dict:
    """Топ недо/переоценённых по модельной справедливой цене (Напр.6)."""
    try:
        from app.services import market_maps
        data = market_maps.valuation(db, tickers_filter=None)
    except Exception:  # noqa: BLE001
        return {}
    tiles = [t for s in data.get("sectors", []) for t in s["tiles"]]
    tiles.sort(key=lambda t: t.get("upside_pct", 0))
    over = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles[:5]]
    under = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles[-5:][::-1]]
    pf = [{"ticker": t["ticker"], "upside_pct": t["upside_pct"]} for t in tiles if t["ticker"] in pf_tickers]
    return {"note": "Апсайд к МОДЕЛЬНОЙ справедливой цене (оценка Basis), не сигнал",
            "most_overvalued": over, "most_undervalued": under, "portfolio": pf[:8]}


# ----------------------------- ПРОМПТ -----------------------------
_FRAMEWORK = (
    "Ты составляешь сводный обзор рынка для частного инвестора на основе ПЕРЕДАННЫХ "
    "данных платформы. Используй ТОЛЬКО переданный контекст — ничего не добавляй от "
    "себя, не выдумывай факты и цифры. НЕ давай рекомендаций покупать/продавать и НЕ "
    "называй целевые цены. Каждый ключевой тезис помечай ссылкой на источник из "
    "контекста в квадратных скобках (например [N1], [E2], [C3]). Тон спокойный, "
    "аналитический. Персонализируй под портфель (portfolio_tickers): что КАСАЕТСЯ "
    "бумаг инвестора — выделяй. Если значимых событий мало — скажи честно. "
    "Выведи markdown."
)
_LEVEL = {
    "express": ("ЭКСПРЕСС (горизонт ±2 дня, кратко ~1 экран). Дай: 2-3 ключевые новости; "
                "1-2 ближайших события (приоритет — портфель и крупнейшие фишки на носу); "
                "краткий итог по свежим отчётам портфеля. Ставку ЦБ упоминай ТОЛЬКО если "
                "заседание в горизонте. Без воды."),
    "detailed": ("ПОДРОБНЫЙ (±7 дней). Разделы: Главные новости недели (со связкой влияния "
                 "«и поэтому»); Макрокартина (инфляция/ставка/курс + что значит); Разбор "
                 "вышедших отчётов (портфель + крупные); Календарь следующей недели; 1-2 "
                 "сквозные темы."),
    "deep": ("ГЛУБОКИЙ (±30 дней). Разделы: Новостной фон месяца; Полная макродинамика; "
             "Значимые отчёты; Геополитика (по каналам, нейтрально); Карты рынка "
             "(перегрето/недооценено — модельная оценка, не сигнал); Темы месяца и связки "
             "между направлениями; Полный календарь вперёд. Персональный месячный обзор."),
}


def generate(db: Session, user_id: int, rtype: str) -> ObserverReport:
    from app.services.llm import complete, pro_model
    pf_t, pf_s = _portfolio(db, user_id)
    ctx, refs = _gather(db, rtype, pf_t, pf_s)
    system = _FRAMEWORK + "\n\nУРОВЕНЬ: " + _LEVEL[rtype]
    thinking = rtype in ("detailed", "deep")
    max_tokens = {"express": 1500, "detailed": 4000, "deep": 8000}[rtype]
    content = complete(system, json.dumps(ctx, ensure_ascii=False), json_mode=False,
                       thinking=thinking, model=pro_model(), max_tokens=max_tokens,
                       temperature=0.3)
    if not isinstance(content, str):
        content = str(content)
    rep = ObserverReport(user_id=user_id, report_type=rtype, horizon_days=HORIZON_DAYS[rtype],
                         content=content.strip(), source_refs=refs,
                         portfolio_snapshot=sorted(pf_t), model_used="deepseek-pro",
                         generated_at=datetime.now(timezone.utc))
    db.add(rep); db.commit(); db.refresh(rep)
    logger.info("Обозревательский отчёт %s сгенерирован для user=%s (refs=%d)", rtype, user_id, len(refs))
    return rep
