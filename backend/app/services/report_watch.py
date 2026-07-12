"""Автообнаружение и разбор вышедших отчётов (Обозреватель, Направление 3 —
автопайплайн, дополняет earnings.py).

Разрыв, который закрывает этот модуль: earnings.py умеет РАЗОБРАТЬ отчёт
(LLM-дайджест по цифрам), но детектит выход отчёта ТОЛЬКО через ручное
обновление financials.json (report-fetcher/financial-analyst — Claude-
субагенты, оператор запускает вручную) — без этого шага новый отчёт молча
не попадает в разбор, даже если событие есть в календаре.

Здесь — независимый путь, без обращения к financials.json:
  ДЕТЕКТ  → calendar_events (event_type=earnings), не обработанные ранее
            (дедуп по calendar_event_id — см. миграцию d2b22f2662ba).
  ТЕКСТ   → каскад источников, по убыванию надёжности:
            1) market_updates (Лента новостей, уже LLM-очищенная выжимка,
               тикер уже размечен news_pipeline.py) — самый общий источник,
               покрывает практически любую компанию, у которой было
               освещение в деловых СМИ;
            2) СКРИН существенные факты (id=36) за окно вокруг даты события,
               по ИНН эмитента (см. calendar_events._load_inn_ticker_map) —
               те же категории «Решения СД»/«Раскрытие... отчёта», что уже
               используются для дивидендного календаря;
            3) заголовок/описание самого календарного события — последний
               резерв, слабый (часто без цифр).
  ИЗВЛЕЧЕНИЕ → LLM (DeepSeek через app.services.llm), СТРОГО «null, если
            данных нет» — не выдумываем цифры. Финотчёт — headline-цифры +
            дайджест (переиспользует шаблон earnings.py._digest). Операционный
            релиз — короткие KPI-маркеры, без попытки впихнуть в P&L-схему.
  ХРАНЕНИЕ → earnings_reports/figures/digest — ТЕ ЖЕ таблицы, что у
            financials.json-пути (frontend не меняется); financials.json
            (вкладка «Финансы») НЕ трогаем — он остаётся выверенным аналитиком
            слоем, этот пайплайн — отдельный ознакомительный «лента событий».

Честная деградация: источник не нашёлся или в тексте нет цифр →
status="needs_source", разбор не публикуется. Не сканируем бесконечно одно и
то же событие: как только создана запись (любого статуса) с этим
calendar_event_id — повторно не трогаем (ручной ре-триггер — прямое удаление
записи, случай редкий).
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.calendar_event import CalendarEvent
from app.models.company import Company
from app.models.earnings import EarningsReport, EarningsFigures, EarningsDigest
from app.services import tinkoff_quotes
from app.services.earnings import _digest, _multiples  # переиспользуем прежний шаблон

logger = logging.getLogger(__name__)

_SKRIN_BASE = "https://disclosure.skrin.ru"
_WINDOW_DAYS = 5   # окно вокруг event_date, где ищем текст (публикация может отставать)


# ----------------------------- источник 1: Лента новостей -----------------------------
def _from_market_updates(db: Session, ticker: str, event_date: date) -> str | None:
    from app.models.market import MarketUpdate
    lo = event_date - timedelta(days=2)
    hi = event_date + timedelta(days=_WINDOW_DAYS)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.affected_tickers.contains([ticker]),
                    MarketUpdate.published_at >= lo, MarketUpdate.published_at <= hi,
                    MarketUpdate.status == "published")
            .order_by(MarketUpdate.published_at.asc()).limit(3).all())
    if not rows:
        return None
    parts = []
    for r in rows:
        parts.append(f"{r.title}\n{r.summary or ''}\n{r.impact_comment or ''}".strip())
    return "\n\n---\n\n".join(parts)


# ----------------------------- источник 2: СКРИН существенные факты -----------------------------
_SKRIN_ROW_RE = re.compile(
    r"openFirmProf\('(\d+)'\);\">([^<]+)</a></span>&nbsp;&nbsp;"
    r"<span class=\"SkrinHref\" ><a  href='javascript:ShowMessage\((\d+),(\d+)\)'>([^<]+)</a>"
)
_SKRIN_RELEVANT = ("решения совета директоров", "решения общего собрания",
                  "решения единственного акционера", "раскрытие в сети интернет",
                  "раскрытие эмитентом ежеквартального отчета")


def _from_skrin(inn: str, event_date: date) -> str | None:
    if not inn:
        return None
    for delta in range(-1, _WINDOW_DAYS + 1):
        d = event_date + timedelta(days=delta)
        if d > date.today():
            continue
        try:
            r = httpx.get(f"{_SKRIN_BASE}/EventList.asp", params={"id": 36, "dt": f"{d.year}-{d.month}-{d.day}"},
                          timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            html = r.content.decode("cp1251", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        time.sleep(0.25)
        for row_inn, _name, eid, agency, title in _SKRIN_ROW_RE.findall(html):
            if row_inn != inn or not any(k in title.strip().lower() for k in _SKRIN_RELEVANT):
                continue
            try:
                mr = httpx.get(f"{_SKRIN_BASE}/printMessage.asp", params={"eid": eid, "Agency": agency},
                               timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                mr.raise_for_status()
                msg = re.sub(r"<[^>]+>", " ", mr.content.decode("cp1251", errors="replace"))
                return re.sub(r"\s+", " ", msg)
            except Exception:  # noqa: BLE001
                continue
    return None


def _source_text(db: Session, event: CalendarEvent, inn: str | None) -> tuple[str, str] | None:
    mu = _from_market_updates(db, event.ticker, event.event_date)
    if mu:
        return mu, "market_updates"
    sk = _from_skrin(inn, event.event_date)
    if sk:
        return sk, "skrin_disclosure"
    desc = (event.payload or {}).get("description") or ""
    fallback = f"{event.title}\n{desc}".strip()
    # заголовок без описания — почти никогда не содержит цифр, не считаем источником
    if desc:
        return fallback, "calendar_title"
    return None


# ----------------------------- извлечение цифр (LLM) -----------------------------
_FIN_SYS = (
    "Ты — финансовый аналитик-экстрактор. Из текста (новость/раскрытие информации) "
    "извлекаешь ТОЛЬКО те финансовые показатели компании, которые ЯВНО названы. "
    "ЗАПРЕЩЕНО придумывать или оценивать отсутствующие числа — если показателя нет "
    "в тексте, верни null. Числа — в млн ₽ (переведи из млрд/трлн, если нужно). "
    "Верни JSON."
)
_FIN_SPEC = (
    'Формат JSON: {"revenue": число|null, "revenue_yoy_pct": число|null, '
    '"ebitda": число|null, "ebitda_yoy_pct": число|null, '
    '"net_profit": число|null, "net_profit_yoy_pct": число|null, '
    '"net_debt": число|null, "has_figures": true|false}. '
    'has_figures=false, если в тексте нет ни одного числового финансового показателя.'
)


def _extract_financial(text_blob: str) -> dict | None:
    from app.services.llm import complete, LLMError
    try:
        res = complete(_FIN_SYS + "\n" + _FIN_SPEC, text_blob[:6000], json_mode=True,
                       max_tokens=600, temperature=0.1)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (финансы) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    return res


_OPS_SYS = (
    "Ты — финансовый редактор. Из текста (операционный релиз/новость о компании) "
    "извлекаешь КЛЮЧЕВЫЕ операционные показатели (натуральные объёмы: пассажиропоток, "
    "выпуск продукции, добыча, число клиентов и т.п. — НЕ финансовые ₽-показатели). "
    "ЗАПРЕЩЕНО придумывать числа. Тон фактический, без советов «купить/продать». Верни JSON."
)
_OPS_SPEC = (
    'Формат JSON: {"has_figures": true|false, "one_liner": "суть одной строкой (<=120 симв)", '
    '"kpis": ["маркеры с ✅/❌/❗️ — 2-5 пунктов, каждый с конкретным числом/%"], '
    '"summary": "1-2 фразы фактического резюме"}. '
    'has_figures=false, если в тексте нет ни одного конкретного числа/показателя.'
)


def _extract_operational(text_blob: str) -> dict | None:
    from app.services.llm import complete, LLMError
    try:
        res = complete(_OPS_SYS + "\n" + _OPS_SPEC, text_blob[:6000], json_mode=True,
                       max_tokens=700, temperature=0.2)
    except LLMError as e:
        logger.warning("report_watch: LLM извлечение (операционка) недоступно: %s", e)
        return None
    if not isinstance(res, dict) or not res.get("has_figures"):
        return None
    return res


# ----------------------------- вспомогательное -----------------------------
def _period_label(event: CalendarEvent) -> str:
    m = re.search(r"за\s+(\d+М|\d+\s*кв(?:артал)?|\d{4}(?:\s*год)?)", event.title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return event.event_date.isoformat()


def _live_price(ticker: str, db: Session) -> tuple[float | None, float | None]:
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


def process_event(db: Session, event: CalendarEvent, company: Company, market_cap: float | None,
                  inn_map: dict[str, list[str]]) -> str:
    """Обработать одно календарное earnings-событие. Идемпотентно (см. дедуп по
    calendar_event_id — уникальный индекс earnings_reports.calendar_event_id)."""
    if db.query(EarningsReport).filter_by(calendar_event_id=event.id).first():
        return "exists"
    inn = next((i for i, tickers in inn_map.items() if event.ticker in tickers), None)
    src = _source_text(db, event, inn)
    standard = event.status  # уже нормализовано build_ir_calendar/_classify_report_kind
    is_operational = bool(standard and "операцион" in standard.lower())
    report_type = "operating" if is_operational else (
        "annual" if re.search(r"\bгод(?:а)?\b", event.title, re.IGNORECASE)
        and not re.search(r"\d+\s*(?:М|кв)", event.title, re.IGNORECASE) else "quarter")
    report = EarningsReport(
        ticker=event.ticker, period=_period_label(event), standard=standard,
        report_type=report_type, published_at=event.event_date,
        source="report_watch", source_url=event.source_url,
        status="needs_source", calendar_event_id=event.id)
    if not src:
        db.add(report); db.commit()
        return "needs_source"
    text_blob, src_label = src
    live, close = _live_price(event.ticker, db)
    price_now = live or close
    mcap = market_cap
    if market_cap and close and price_now:
        mcap = market_cap * (price_now / close)
    report.source = src_label
    if is_operational:
        opd = _extract_operational(text_blob)
        if not opd:
            db.add(report); db.commit()
            return "needs_source"
        db.add(report); db.flush()
        db.add(EarningsFigures(report_id=report.id, extracted_fields=opd))
        db.add(EarningsDigest(
            report_id=report.id, headline=f"{company.name}: {report.period}",
            one_liner=opd.get("one_liner"), what_report_showed=opd.get("kpis"),
            summary=opd.get("summary"), importance="medium", model_used="deepseek"))
        report.status = "processed"
        db.commit()
        return "created"
    fig_raw = _extract_financial(text_blob)
    if not fig_raw:
        db.add(report); db.commit()
        return "needs_source"

    def _prev(cur, yoy):
        if cur is None or yoy is None or yoy == -100:
            return None
        try:
            return round(cur / (1 + yoy / 100), 2)
        except ZeroDivisionError:
            return None
    fig = {
        "ticker": event.ticker, "name": company.name, "sector": company.sector,
        "period": report.period, "standard": standard, "unit": "млн",
        "revenue": fig_raw.get("revenue"), "revenue_prev": _prev(fig_raw.get("revenue"), fig_raw.get("revenue_yoy_pct")),
        "ebitda": fig_raw.get("ebitda"), "ebitda_prev": _prev(fig_raw.get("ebitda"), fig_raw.get("ebitda_yoy_pct")),
        "net_profit": fig_raw.get("net_profit"), "net_profit_prev": _prev(fig_raw.get("net_profit"), fig_raw.get("net_profit_yoy_pct")),
        "net_debt": fig_raw.get("net_debt"), "adjusted_profit": None, "is_company_adjusted": False,
    }
    mult = _multiples(fig, price_now, mcap)
    digest = _digest(fig, mult)
    db.add(report); db.flush()
    db.add(EarningsFigures(
        report_id=report.id, revenue_ttm=fig.get("revenue"), ebitda=fig.get("ebitda"),
        net_profit_ttm=fig.get("net_profit"), net_debt=fig.get("net_debt"),
        nd_ebitda=mult.get("nd_ebitda"), price=mult.get("price"), market_cap=mult.get("market_cap"),
        pe_ttm=mult.get("pe_ttm"), pb=mult.get("pb"), ev_ebitda=mult.get("ev_ebitda"),
        is_company_adjusted=False,
        prev={"revenue": fig.get("revenue_prev"), "ebitda": fig.get("ebitda_prev"),
              "net_profit": fig.get("net_profit_prev")},
        extracted_fields=fig_raw))
    if digest:
        db.add(EarningsDigest(
            report_id=report.id, headline=digest.get("headline"), one_liner=digest.get("one_liner"),
            metrics_snapshot=mult, what_report_showed=digest.get("what_report_showed"),
            what_changed=digest.get("what_changed"), summary=digest.get("summary"),
            importance=digest.get("importance"), model_used="deepseek"))
        report.status = "processed"
    else:
        report.status = "extract_failed"
    db.commit()
    return "created"


_MOEX_IR_CALENDAR = "https://iss.moex.com/iss/cci/calendars/ir-calendar.json"


def _due_ir_rows(companies: dict, days_back: int) -> list[dict]:
    """Прямой опрос MOEX ir-calendar (НЕ через calendar_events!) за отчётные события с
    event_date в [today-days_back, today] — уже ДОЛЖНЫ были выйти.
    🔴 calendar_events хранит ТОЛЬКО форвард (build_ir_calendar сам фильтрует
    `event_date < today: continue` — витрина календаря показывает только предстоящее,
    прошлое туда никогда не попадает). Проверено локально 2026-07-12: 0 earnings-строк
    с event_date <= today в calendar_events, при этом У САМОГО MOEX прошлые даты ЕСТЬ
    (AFLT: записи с 2024 года) — значит слепая зона именно в НАШЕЙ форвард-фильтрации,
    не в источнике. Поэтому детект report_watch идёт мимо calendar_events, напрямую
    к MOEX, с собственным окном [today-days_back, today]."""
    today = date.today()
    lo = today - timedelta(days=days_back)
    try:
        r = httpx.get(_MOEX_IR_CALENDAR, params={"limit": "max"}, timeout=30)
        r.raise_for_status()
        block = (r.json() or {}).get("cci_ir_calendar") or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("report_watch: MOEX ir-calendar недоступен: %s", type(e).__name__)
        return []
    cols = block.get("columns") or []
    rows = block.get("data") or []
    if not cols or not rows:
        return []
    idx = {c: i for i, c in enumerate(cols)}
    out = []
    for row in rows:
        if row[idx["event_type_name"]] != "Публикация отчетности":
            continue
        secid = row[idx["secid"]]
        if secid not in companies:
            continue
        raw_date = row[idx["event_date"]]
        if not raw_date:
            continue
        try:
            ev_date = date.fromisoformat(raw_date[:10])
        except (TypeError, ValueError):
            continue
        if not (lo <= ev_date <= today):
            continue
        out.append({
            "secid": secid, "event_date": ev_date, "event_id": row[idx["event_id"]],
            "description": (row[idx["event_description"]] or "").strip(),
            "event_link": row[idx["event_link"]],
        })
    return out


def _get_or_create_calendar_event(db: Session, row: dict, company: Company) -> CalendarEvent:
    """Служебная запись calendar_events под уже ПРОШЕДШЕЕ MOEX-событие (форвард-витрина
    build_ir_calendar такие не хранит — см. _due_ir_rows) — нужна только как якорь
    дедупа earnings_reports.calendar_event_id, на публичный /market/calendar не влияет
    (event_type тот же 'earnings', но дата в прошлом — витрина и так их не показывает)."""
    from app.services.calendar_events import _upsert, _classify_report_kind
    dedup_key = f"ir_calendar_past:{row['secid']}:{row['event_id']}"
    existing = db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()
    if existing:
        return existing
    status = _classify_report_kind(row["description"])
    _upsert(db, [{
        "event_type": "earnings", "event_date": row["event_date"], "event_time": None,
        "ticker": row["secid"], "sector": company.sector,
        "title": f"{company.name}: {row['description']}"[:300], "status": status,
        "source": "moex_ir_calendar", "source_url": row["event_link"] or "",
        "payload": {"subtype": "report", "confidence": "public_aggregated", "description": row["description"][:500]},
        "dedup_key": dedup_key,
    }])
    return db.query(CalendarEvent).filter_by(dedup_key=dedup_key).first()


def refresh(db: Session, days_back: int = 5) -> dict:
    """Ежедневный обход: MOEX ir-calendar события «Публикация отчетности» за days_back
    дней назад (уже вышедшие), ещё не обработанные (нет earnings_reports с этим
    calendar_event_id). Покрытие ограничено эмитентами MOEX ir-calendar (~76/261 —
    см. build_ir_calendar) — честное ограничение источника, не притворяемся, что
    покрываем весь рынок этим путём."""
    from app.services.calendar_events import _load_inn_ticker_map
    companies = {c.ticker: c for c in db.query(Company).all()}
    due_rows = _due_ir_rows(companies, days_back)
    inn_map = _load_inn_ticker_map()
    res = {"created": 0, "needs_source": 0, "exists": 0, "errors": 0, "skipped_no_company": 0}
    for row in due_rows:
        company = companies.get(row["secid"])
        if not company:
            res["skipped_no_company"] += 1
            continue
        try:
            event = _get_or_create_calendar_event(db, row, company)
            r = process_event(db, event, company, float(company.market_cap) if company.market_cap else None, inn_map)
            res[r] = res.get(r, 0) + 1
        except Exception as e:  # noqa: BLE001
            logger.warning("report_watch: ошибка по событию %s/%s: %s", row["secid"], row["event_id"], type(e).__name__)
            res["errors"] += 1
            db.rollback()
    logger.info("report_watch: %s (событий в окне: %d)", res, len(due_rows))
    return res
