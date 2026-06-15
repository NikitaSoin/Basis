"""Движок «Анализ отчётностей» (Обозреватель, Направление 3).

Пайплайн (по образцу Конвейера 2 — детект следит, LLM осмысляет):
- ДЕТЕКТ выхода отчёта: корпсобытия smart-lab (CalendarEvent type=corporate subtype=
  report) + появление нового фискального периода в financials.json карточки.
  (e-disclosure закрыт антиботом — подтверждено; smart-lab публичный.)
- HEADLINE-ЦИФРЫ: из ВЫВЕРЕННОГО financials.json карточки (аналитик их построил;
  не выдумываем и не парсим хрупко). Берём последний фискальный период + предыдущий.
- МУЛЬТИПЛИКАТОРЫ: пересчёт с ТЕКУЩЕЙ ценой (live Tinkoff / последний close).
- РАЗБОР: LLM (DeepSeek) строго по извлечённым цифрам, по шаблону, БЕЗ таргетов/
  советов/раскрытия позиций. Дисклеймер «не ИИР».
Финблок карточки НЕ перезаписываем (он построен financial-analyst и чувствителен —
см. аудит): разбор и снимок цифр живут отдельным ознакомительным слоем рядом.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.calendar_event import CalendarEvent
from app.models.earnings import EarningsReport, EarningsFigures, EarningsDigest
from app.services import tinkoff_quotes

logger = logging.getLogger(__name__)
COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"


def _last_two(arr):
    """Последние два не-None значения массива (период и предыдущий)."""
    vals = [(i, v) for i, v in enumerate(arr or []) if v is not None]
    if not vals:
        return None, None
    last = vals[-1][1]
    prev = vals[-2][1] if len(vals) > 1 else None
    return last, prev


def _load_figures(ticker: str) -> dict | None:
    """Headline-цифры последнего фискального периода из financials.json (в млн ₽)."""
    path = COMPANIES_DIR / ticker.upper() / "financials.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    meta = d.get("meta") or {}
    years = meta.get("fiscal_years") or []
    if not years:
        return None
    inc = d.get("income_statement") or {}
    bs = d.get("balance_sheet") or {}
    adj = d.get("adjusted") or {}
    rev, rev_prev = _last_two(inc.get("revenue"))
    eb, eb_prev = _last_two(inc.get("ebitda"))
    np_, np_prev = _last_two(inc.get("net_profit"))
    nd, _ = _last_two(bs.get("net_debt"))
    eq, _ = _last_two(bs.get("total_equity"))
    adj_np, _ = _last_two(adj.get("net_profit") if isinstance(adj, dict) else None)
    return {
        "ticker": ticker, "name": meta.get("name"), "sector": meta.get("sector"),
        "period": str(years[-1]), "standard": meta.get("reporting_standard"),
        "unit": meta.get("unit", "млн"), "last_price_card": meta.get("last_price"),
        "revenue": rev, "revenue_prev": rev_prev,
        "ebitda": eb, "ebitda_prev": eb_prev,
        "net_profit": np_, "net_profit_prev": np_prev,
        "net_debt": nd, "total_equity": eq,
        "adjusted_profit": adj_np if adj_np is not None else None,
        "is_company_adjusted": bool(adj_np is not None),
    }


def _live_price(ticker: str, db: Session) -> tuple[float | None, float | None]:
    """(живая цена, последний close из БД)."""
    live = None
    try:
        if tinkoff_quotes.is_available():
            q = (tinkoff_quotes.get_all_prices() or {}).get(ticker)
            if q and q.get("price") is not None:
                live = float(q["price"])
    except Exception:  # noqa: BLE001
        pass
    row = db.execute(text("""
        SELECT q.close FROM quotes q JOIN companies c ON c.id=q.company_id
        WHERE c.ticker=:t AND q.close IS NOT NULL ORDER BY q.date DESC LIMIT 1
    """), {"t": ticker}).first()
    close = float(row.close) if row else None
    return live, close


def _multiples(fig: dict, price_now: float | None, market_cap: float | None) -> dict:
    """Пересчёт мультипликаторов с текущей ценой. market_cap в рублях → млн под financials."""
    out = {"price": price_now, "market_cap": market_cap,
           "pe_ttm": None, "pb": None, "ev_ebitda": None, "nd_ebitda": None}
    if fig.get("net_debt") is not None and fig.get("ebitda"):
        try:
            out["nd_ebitda"] = round(fig["net_debt"] / fig["ebitda"], 3)
        except ZeroDivisionError:
            pass
    if market_cap is None:
        return out
    mcap_mln = market_cap / 1e6  # рубли → млн (financials в млн)
    np_ = fig.get("net_profit"); eq = fig.get("total_equity"); eb = fig.get("ebitda")
    nd = fig.get("net_debt") or 0
    if np_ and np_ > 0:
        out["pe_ttm"] = round(mcap_mln / np_, 2)
    if eq and eq > 0:
        out["pb"] = round(mcap_mln / eq, 2)
    if eb and eb > 0:
        out["ev_ebitda"] = round((mcap_mln + nd) / eb, 2)
    return out


_SYS = (
    "Ты — финансовый редактор. Пишешь КОРОТКИЙ ознакомительный «Разбор отчёта» о выходе "
    "финансовой отчётности компании СТРОГО по предоставленным числам. ЗАПРЕЩЕНО: выдумывать "
    "числа, давать таргеты/прогноз справедливой цены, советы «купить/продать/присматриваться», "
    "раскрывать позиции. Тон фактический, нейтральный, независимый. Все цифры — только из "
    "входных данных. Верни JSON."
)
_SPEC = (
    'Формат JSON: {"one_liner": "одна строка сути (<=120 симв)", '
    '"headline": "шапка: Компания (ТИКЕР) · период, стандарт", '
    '"what_report_showed": ["маркеры с ✅/❌/❗️ — динамика YoY выручки/EBITDA/прибыли, разовые '
    'факторы, долг, дивиденд; 3-5 пунктов"], '
    '"what_changed": "что изменилось vs прошлый период (1-3 фразы, по числам)", '
    '"summary": "2-3 фразы фактического резюме без советов", '
    '"importance": "high|medium|low"}'
)


def _digest(fig: dict, mult: dict) -> dict | None:
    """LLM-разбор по шаблону, строго по цифрам. Возвращает dict или None при сбое."""
    from app.services.llm import complete, LLMError
    def chg(cur, prev):
        if cur is None or prev in (None, 0):
            return None
        return round((cur - prev) / abs(prev) * 100, 1)
    payload = {
        "company": fig.get("name"), "ticker": fig["ticker"], "period": fig["period"],
        "standard": fig.get("standard"), "unit": fig.get("unit", "млн"),
        "revenue": fig.get("revenue"), "revenue_yoy_pct": chg(fig.get("revenue"), fig.get("revenue_prev")),
        "ebitda": fig.get("ebitda"), "ebitda_yoy_pct": chg(fig.get("ebitda"), fig.get("ebitda_prev")),
        "net_profit": fig.get("net_profit"), "net_profit_yoy_pct": chg(fig.get("net_profit"), fig.get("net_profit_prev")),
        "adjusted_profit": fig.get("adjusted_profit"), "is_company_adjusted": fig.get("is_company_adjusted"),
        "net_debt": fig.get("net_debt"), "nd_ebitda": mult.get("nd_ebitda"),
        "pe_ttm": mult.get("pe_ttm"), "pb": mult.get("pb"), "ev_ebitda": mult.get("ev_ebitda"),
        "price_now": mult.get("price"),
    }
    try:
        res = complete(_SYS + "\n" + _SPEC, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=1200, temperature=0.2)
        return res if isinstance(res, dict) else None
    except LLMError as e:
        logger.warning("Разбор отчёта %s: LLM недоступен: %s", fig["ticker"], e)
        return None


def _published_at(db: Session, ticker: str) -> date | None:
    """Дата выхода отчёта — из корпсобытия smart-lab (report), если есть."""
    row = (db.query(CalendarEvent)
           .filter(CalendarEvent.event_type == "corporate", CalendarEvent.ticker == ticker)
           .order_by(CalendarEvent.event_date.desc()).first())
    return row.event_date if row else None


def process_ticker(db: Session, ticker: str, market_cap: float | None) -> str:
    """Обработать один тикер: если последний период ещё не разобран — создать отчёт+разбор."""
    fig = _load_figures(ticker)
    if not fig or fig.get("revenue") is None:
        return "no_figures"
    existing = (db.query(EarningsReport)
                .filter_by(ticker=ticker, period=fig["period"], standard=fig.get("standard"))
                .first())
    if existing:
        return "exists"
    live, close = _live_price(ticker, db)
    price_now = live or close or fig.get("last_price_card")
    # market_cap с текущей ценой: масштабируем DB-капу по (живая/последний_close)
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    mult = _multiples(fig, price_now, mcap)
    digest = _digest(fig, mult)
    rtype = "annual" if len(fig["period"]) == 4 else "quarter"
    report = EarningsReport(
        ticker=ticker, period=fig["period"], standard=fig.get("standard"),
        report_type=rtype, published_at=_published_at(db, ticker),
        source="smartlab+card", source_url=f"https://smart-lab.ru/q/{ticker}/f/",
        status="processed")
    db.add(report); db.flush()
    db.add(EarningsFigures(
        report_id=report.id, revenue_ttm=fig.get("revenue"), ebitda=fig.get("ebitda"),
        net_profit_ttm=fig.get("net_profit"), adjusted_profit=fig.get("adjusted_profit"),
        net_debt=fig.get("net_debt"), nd_ebitda=mult.get("nd_ebitda"),
        price=mult.get("price"), market_cap=mult.get("market_cap"),
        pe_ttm=mult.get("pe_ttm"), pb=mult.get("pb"), ev_ebitda=mult.get("ev_ebitda"),
        is_company_adjusted=fig.get("is_company_adjusted"),
        prev={"revenue": fig.get("revenue_prev"), "ebitda": fig.get("ebitda_prev"),
              "net_profit": fig.get("net_profit_prev")},
        extracted_fields=fig))
    if digest:
        db.add(EarningsDigest(
            report_id=report.id, headline=digest.get("headline"),
            one_liner=digest.get("one_liner"), metrics_snapshot=mult,
            what_report_showed=digest.get("what_report_showed"),
            what_changed=digest.get("what_changed"), summary=digest.get("summary"),
            importance=digest.get("importance"), model_used="deepseek"))
    else:
        report.status = "extract_failed"
    db.commit()
    return "created"


def refresh(db: Session, tickers: list[str] | None = None, limit: int | None = None) -> dict:
    """Вечерний обход: обработать новые отчёты. tickers=None → все компании."""
    caps = {c.ticker: (float(c.market_cap) if c.market_cap is not None else None)
            for c in db.query(Company).all()}
    todo = tickers if tickers is not None else list(caps.keys())
    if limit:
        todo = todo[:limit]
    res = {"created": 0, "exists": 0, "no_figures": 0, "errors": 0}
    for t in todo:
        try:
            r = process_ticker(db, t, caps.get(t))
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("Разбор отчёта %s: ошибка %s", t, type(e).__name__)
            res["errors"] += 1
            db.rollback()
    logger.info("Анализ отчётностей: %s", res)
    return res
