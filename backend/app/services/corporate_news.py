"""Корпоративные события (Обозреватель, вкладка «Корп. события»): единая лента —
что случилось у компании — из уже существующих таблиц, без новых пайплайнов/LLM-
вызовов. Виды события:
  report_published   — вышел отчёт (EarningsReport.status=="processed")
  report_missing      — отчёт ожидался по календарю, но за grace-период источник
                         не нашёлся (EarningsReport.status=="needs_source" либо
                         событие вовсе без EarningsReport). Self-diagnostic: если
                         тикер регулярно попадает в эту категорию — это, вероятнее,
                         неточность НАШЕГО календаря (дата-оценка), а не срыв
                         публикации компанией (см. владелец, 2026-07-14).
  dividend_announced  — объявлен дивиденд с конкретной суммой (calendar_events,
                         event_type=="dividend", payload.amount задан)
  business_ma / business_div_policy / business_management — бизнес-новости из
                         Ленты (MarketUpdate, category=="Бизнес"), классифицируются
                         лёгкой keyword-эвристикой (без LLM) по тикерам новости.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.earnings import EarningsDigest, EarningsReport
from app.models.market import MarketUpdate

_MISSING_GRACE_DAYS = 7      # ждём источник столько дней после event_date, прежде чем считать «не вышел»
_MISSING_LOOKBACK_DAYS = 45  # горизонт назад для показа «не вышел»
_MISS_STREAK_LOOKBACK_DAYS = 120  # окно для self-diagnostic по частоте промахов тикера
_MISS_STREAK_THRESHOLD = 2

_BIZ_MA_KEYWORDS = ("поглощен", "слияни", "m&a", "приобрет", "выкуп доли", "продаж",
                     "консолидац", "сделку по покупке", "сделка по покупке")
_BIZ_DIV_POLICY_KEYWORDS = ("полити", "приостанов", "отказал", "не будет платить",
                             "отмен", "не рекоменд", "прекращ выплат")
_BIZ_MGMT_KEYWORDS = ("совет директоров", "гендиректор", "генерального директора",
                       "председател", "назначил", "назначен", "покинет пост",
                       "уходит с поста", "сменил")


def _classify_business(title: str, summary: str | None) -> str | None:
    text = f"{title} {summary or ''}".lower()
    if any(k in text for k in _BIZ_MA_KEYWORDS):
        return "ma"
    if "дивиденд" in text and any(k in text for k in _BIZ_DIV_POLICY_KEYWORDS):
        return "div_policy"
    if any(k in text for k in _BIZ_MGMT_KEYWORDS):
        return "management"
    return None


def build_corporate_news(db: Session, portfolio_tickers: list[str] | None = None,
                          days_back: int = 30, limit: int = 150) -> list[dict]:
    """portfolio_tickers: None — без фильтра; [] — пустой портфель (ничего не покажет);
    list — фильтр по тикерам."""
    today = date.today()
    companies = {c.ticker: c for c in db.query(Company).all()}
    out: list[dict] = []

    def _allowed(ticker: str) -> bool:
        return portfolio_tickers is None or ticker in portfolio_tickers

    # ---- report_published ----
    reports_q = (db.query(EarningsReport, EarningsDigest)
                 .outerjoin(EarningsDigest, EarningsDigest.report_id == EarningsReport.id)
                 .filter(EarningsReport.status == "processed",
                         EarningsReport.published_at.isnot(None),
                         EarningsReport.published_at >= today - timedelta(days=days_back)))
    for r, dg in reports_q.all():
        c = companies.get(r.ticker)
        if not c or not _allowed(r.ticker):
            continue
        std = f", {r.standard}" if r.standard else ""
        out.append({
            "kind": "report_published",
            "ticker": r.ticker, "company": c.name, "sector": c.sector,
            "date": r.published_at.isoformat(),
            "title": f"{c.name}: вышел отчёт ({r.period}{std})",
            "detail": dg.one_liner if dg else None,
            "epistemic": "факт",
            "link_to": "reports",
            "likely_calendar_error": False,
        })

    # ---- report_missing (grace period прошёл, источник не найден) ----
    lo = today - timedelta(days=_MISSING_LOOKBACK_DAYS)
    hi = today - timedelta(days=_MISSING_GRACE_DAYS)
    matched_event_ids = {
        row[0] for row in db.query(EarningsReport.calendar_event_id)
        .filter(EarningsReport.status == "processed",
                EarningsReport.calendar_event_id.isnot(None)).all()
    }
    # Разные источники детекта (MOEX ir-calendar / smart-lab) могут дать 2+ CalendarEvent
    # на один и тот же (тикер, дата) — группируем ПЕРЕД оценкой "найден/не найден", иначе
    # (а) один и тот же промах считается дважды в self-diagnostic, (б) карточка дублируется,
    # (в) если совпадение нашлось у ОДНОЙ из дублирующихся записей, а не у другой, получим
    # ложный "не вышел" при реально найденном отчёте.
    streak_lo = today - timedelta(days=_MISS_STREAK_LOOKBACK_DAYS)
    streak_rows = (db.query(CalendarEvent.ticker, CalendarEvent.id, CalendarEvent.event_date)
                   .filter(CalendarEvent.event_type == "earnings",
                           CalendarEvent.event_date >= streak_lo,
                           CalendarEvent.event_date <= hi).all())
    streak_groups: dict[tuple, set] = {}
    for ticker, ev_id, ev_date in streak_rows:
        streak_groups.setdefault((ticker, ev_date), set()).add(ev_id)
    miss_counts: dict[str, int] = {}
    for (ticker, _ev_date), ev_ids in streak_groups.items():
        if not (ev_ids & matched_event_ids):
            miss_counts[ticker] = miss_counts.get(ticker, 0) + 1

    missing_rows = (db.query(CalendarEvent)
                    .filter(CalendarEvent.event_type == "earnings",
                            CalendarEvent.event_date >= lo, CalendarEvent.event_date <= hi).all())
    missing_groups: dict[tuple, list] = {}
    for ev in missing_rows:
        missing_groups.setdefault((ev.ticker, ev.event_date), []).append(ev)
    for (ticker, ev_date), evs in missing_groups.items():
        if {e.id for e in evs} & matched_event_ids:
            continue
        c = companies.get(ticker)
        if not c or not _allowed(ticker):
            continue
        ev = evs[0]
        misses = miss_counts.get(ev.ticker, 0)
        likely_calendar_error = misses >= _MISS_STREAK_THRESHOLD
        detail = ("Этот тикер регулярно попадает в «не вышел» — вероятнее, мы неточно "
                  "оцениваем дату отчёта, а не компания срывает публикацию."
                  if likely_calendar_error else
                  "Либо отчёт вышел, но мы не нашли источник, либо расчётная дата в "
                  "календаре была неточной (оценка, не подтверждённая компанией).")
        out.append({
            "kind": "report_missing",
            "ticker": ev.ticker, "company": c.name, "sector": c.sector,
            "date": ev.event_date.isoformat(),
            "title": f"{c.name}: отчёт ожидался {ev.event_date.strftime('%d.%m.%Y')} — публикация не найдена",
            "detail": detail,
            "epistemic": "оценка",
            "link_to": "company",
            "likely_calendar_error": likely_calendar_error,
        })

    # ---- dividend_announced (подтверждённая сумма) ----
    div_q = (db.query(CalendarEvent)
             .filter(CalendarEvent.event_type == "dividend",
                     CalendarEvent.created_at >= today - timedelta(days=days_back)))
    seen_div = set()
    for ev in div_q.all():
        amount = (ev.payload or {}).get("amount")
        if not amount:
            continue
        c = companies.get(ev.ticker)
        if not c or not _allowed(ev.ticker):
            continue
        key = (ev.ticker, ev.event_date)
        if key in seen_div:
            continue
        seen_div.add(key)
        dy = (ev.payload or {}).get("dividend_yield")
        yield_part = f", доходность ≈{dy:g}%" if dy is not None else ""
        out.append({
            "kind": "dividend_announced",
            "ticker": ev.ticker, "company": c.name, "sector": c.sector,
            "date": ev.event_date.isoformat(),
            "title": (f"{c.name}: дивиденд {amount:g} ₽/акц.{yield_part}, "
                     f"отсечка {ev.event_date.strftime('%d.%m.%Y')}"),
            "detail": None,
            "epistemic": "факт",
            "link_to": "company",
            "likely_calendar_error": False,
        })

    # ---- business_* (М&A / див.политика / менеджмент) из Ленты, keyword-классификация ----
    biz_q = (db.query(MarketUpdate)
             .filter(MarketUpdate.status == "published",
                     MarketUpdate.category == "Бизнес",
                     MarketUpdate.published_at >= today - timedelta(days=days_back),
                     MarketUpdate.affected_tickers.isnot(None)))
    for mu in biz_q.all():
        subtype = _classify_business(mu.title, mu.summary)
        if not subtype:
            continue
        for t in (mu.affected_tickers or []):
            c = companies.get(t)
            if not c or not _allowed(t):
                continue
            out.append({
                "kind": f"business_{subtype}",
                "ticker": t, "company": c.name, "sector": c.sector,
                "date": mu.published_at.date().isoformat(),
                "title": mu.title,
                "detail": mu.summary,
                "epistemic": "факт",
                "link_to": "company",
                "likely_calendar_error": False,
            })

    out.sort(key=lambda x: x["date"], reverse=True)
    return out[:limit]
