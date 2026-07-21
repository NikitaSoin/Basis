"""Инструменты автономных DeepSeek-агентов (пилот, фазы 2-3 «пути к автономной
платформе»). Каждый инструмент: JSON-схема (OpenAI function calling) + реализация.
Агент НЕ имеет прямого доступа к ФС/БД — только через этот белый список; всё,
что он «видит», проходит здесь, всё журналируется runner'ом в run_trace.

Белый список файлов карточки — осознанно узкий (пилот = макро-addendum): только
macro.json (в сжатом виде — факторы+quant без простыней) и meta financials.
Расширение списка = осознанное решение, не дефолт."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_macro_card",
            "description": "Прочитать сжатый макро-разбор компании из её карточки: факторы с каналами влияния, спот-ориентиры на дату разбора, коэффициенты чувствительности, дату актуальности.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Тикер компании"}},
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_macro",
            "description": "Текущие рыночные макро-условия из БД платформы: ключевая ставка ЦБ, нефть Brent (ближний фьючерс), курс USD/RUB, дата снимка.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_news",
            "description": "Свежие новости Ленты платформы, затрагивающие компанию (до 8 за последние 30 дней): заголовок, дата, краткое содержание.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Тикер компании"}},
                "required": ["ticker"],
            },
        },
    },
]


def _read_macro_card(ticker: str) -> dict:
    path = COMPANIES_DIR / ticker.upper() / "macro.json"
    if not path.exists():
        return {"error": "no_macro_card"}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"error": "unreadable"}
    qi = d.get("quant_inputs") or {}
    factors = []
    for f in (d.get("factors") or [])[:6]:
        factors.append({
            "factor": f.get("factor"),
            "type": f.get("type"),
            "effect_sign": f.get("effect_sign"),
            "channel": f.get("channel"),
            "current_state": (f.get("current_state") or {}).get("text") if isinstance(f.get("current_state"), dict) else f.get("current_state"),
        })
    return {
        "as_of": d.get("as_of") or d.get("meta", {}).get("as_of"),
        "regime_summary": d.get("regime_summary") or d.get("summary"),
        "factors": factors,
        "macro_spot_at_analysis": qi.get("macro_spot") or qi.get("macro_current"),
        "coefficients": {
            k: {m: v.get(m) for m in ("revenue", "ebitda", "net_profit", "per")}
            for k, v in (qi.get("coefficients") or {}).items() if isinstance(v, dict)
        },
        "financials_base": qi.get("financials"),
    }


def _get_live_macro(db: Session) -> dict:
    out: dict = {}
    row = db.execute(text(
        "SELECT value, as_of FROM macro_data_points WHERE indicator_code='key_rate' AND metric='level' "
        "ORDER BY as_of DESC LIMIT 1")).first()
    if row:
        out["key_rate_pct"] = float(row[0])
        out["key_rate_as_of"] = str(row[1])
    row = db.execute(text(
        "SELECT last_price FROM futures WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') "
        "AND last_price IS NOT NULL AND expiration_date >= now()::date "
        "ORDER BY expiration_date ASC LIMIT 1")).first()
    if row and row[0]:
        out["oil_brent_usd"] = float(row[0])
    row = db.execute(text("SELECT last_price FROM spot_assets WHERE secid='USD000UTSTOM'")).first()
    if row and row[0]:
        out["fx_usdrub"] = float(row[0])
    row = db.execute(text(
        "SELECT value, as_of FROM macro_data_points WHERE indicator_code='inflation' AND metric='yoy' "
        "ORDER BY as_of DESC LIMIT 1")).first()
    if row:
        out["inflation_yoy_pct"] = float(row[0])
    return out


def _get_recent_news(db: Session, ticker: str) -> dict:
    rows = db.execute(text("""
        SELECT title, published_at::date::text, summary FROM market_updates
        WHERE status='published' AND affected_tickers ? :t
          AND published_at >= now() - interval '30 days'
        ORDER BY published_at DESC LIMIT 8
    """), {"t": ticker.upper()}).fetchall()
    return {"news": [{"title": r[0], "date": r[1], "summary": (r[2] or "")[:300]} for r in rows]}


def _get_recent_earnings(db: Session, ticker: str) -> dict:
    """Разобранные отчёты по тикеру за 120 дней (что вышло из финансовых событий)."""
    rows = db.execute(text("""
        SELECT er.period, er.standard, er.published_at::date::text, ed.one_liner
        FROM earnings_reports er
        LEFT JOIN earnings_digests ed ON ed.report_id = er.id
        WHERE er.ticker = :t AND er.status = 'processed'
          AND er.published_at >= now() - interval '120 days'
        ORDER BY er.published_at DESC LIMIT 5
    """), {"t": ticker.upper()}).fetchall()
    return {"earnings": [{"period": r[0], "standard": r[1], "date": r[2], "gist": r[3]} for r in rows]}


def _get_calendar(db: Session, ticker: str) -> dict:
    """Ближайшие корпсобытия тикера (дивиденды/отчётности/СД) — что уже случилось
    или на подходе против того, что заложено в разборе."""
    rows = db.execute(text("""
        SELECT event_type, event_date::text, title, status FROM calendar_events
        WHERE ticker = :t AND event_date >= now() - interval '30 days'
          AND event_date <= now() + interval '60 days'
        ORDER BY event_date ASC LIMIT 10
    """), {"t": ticker.upper()}).fetchall()
    return {"events": [{"type": r[0], "date": r[1], "title": r[2], "status": r[3]} for r in rows]}


def _get_geo_barometer() -> dict:
    """Свежий геополитический барометр (очаги СВО/Ближний Восток/АТР + сценарий) —
    контекст для ревизии макро/гео-блоков."""
    path = Path(__file__).parent.parent.parent / "config" / "geo_barometer.json"
    if not path.exists():
        return {"error": "no_barometer"}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"error": "unreadable"}
    return {"as_of": d.get("as_of"), "scenario": d.get("scenario"),
            "regions": d.get("regions"), "sector_flags": d.get("sector_flags")}


def _query_chronicle(db: Session, ticker: str, sectors: list | None,
                     themes: list | None, days: int, limit: int) -> dict:
    """Аналитическая летопись (постоянная память): компактные однострочники по
    тикеру ИЛИ заданным секторам/темам за окно. Сорт: важное → свежее. За полной
    записью — get_chronicle_entry(id)."""
    days = max(7, min(int(days or 365), 1825))
    limit = max(1, min(int(limit or 10), 20))
    conds = ["tickers ? :tk"]
    params: dict = {"tk": ticker.upper()}
    for i, s in enumerate(sectors or []):
        if isinstance(s, str):
            conds.append(f"sectors ? :sec{i}"); params[f"sec{i}"] = s
    for i, t in enumerate(themes or []):
        if isinstance(t, str):
            conds.append(f"themes ? :thm{i}"); params[f"thm{i}"] = t
    params["lim"] = limit
    sql = text(f"""
        SELECT id, published_at::date::text, kind, importance, title, interpretation
        FROM chronicle_entries
        WHERE ({' OR '.join(conds)}) AND published_at >= now() - make_interval(days => {days})
        ORDER BY (importance='high') DESC, published_at DESC
        LIMIT :lim
    """)
    rows = db.execute(sql, params).fetchall()
    return {
        "_note": "Интерпретация — как виделось НА ДАТУ записи, не сегодняшняя истина. "
                 "За полным пересказом и тезисами вызови get_chronicle_entry(id).",
        "entries": [{"id": r[0], "date": r[1], "kind": r[2], "importance": r[3],
                     "title": r[4], "interpretation": (r[5] or "")[:200]} for r in rows],
    }


def _get_chronicle_entry(db: Session, entry_id: int) -> dict:
    """Полная запись летописи по id (пересказ + тезисы + теги + источник)."""
    r = db.execute(text("""
        SELECT id, published_at::date::text, kind, importance, title, summary,
               interpretation, key_takeaways, tickers, sectors, themes, source_key
        FROM chronicle_entries WHERE id = :id
    """), {"id": int(entry_id)}).fetchone()
    if not r:
        return {"error": "not_found"}
    return {"id": r[0], "date": r[1], "kind": r[2], "importance": r[3], "title": r[4],
            "summary": r[5], "interpretation": r[6], "key_takeaways": r[7],
            "tickers": r[8], "sectors": r[9], "themes": r[10], "source": r[11],
            "_note": "Интерпретация — как виделось на дату записи, не сегодняшняя истина."}


# Расширенная схема — для агента-ревизора карточки (card_review_agent). Пилотный
# macro_addendum использует урезанный TOOLS_SCHEMA выше (не ломаем его).
REVIEW_TOOLS_SCHEMA = TOOLS_SCHEMA + [
    {
        "type": "function",
        "function": {
            "name": "get_recent_earnings",
            "description": "Разобранные отчёты компании за 120 дней: период, стандарт, суть — вышло ли что-то, чего не было в разборе.",
            "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar",
            "description": "Корпоративные события компании (дивиденды/отчётности/СД) в окне −30..+60 дней.",
            "parameters": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_geo_barometer",
            "description": "Свежий геополитический барометр платформы: очаги (СВО/Ближний Восток/АТР), сценарий, секторные флаги. Для ревизии макро/гео-блоков.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_chronicle",
            "description": ("Аналитическая ЛЕТОПИСЬ платформы — постоянная память важных событий и статей "
                            "с готовой интерпретацией. Компактные однострочники по ЭТОЙ компании и/или "
                            "заданным секторам/темам за окно. Чтобы понять, что происходило с фоном раньше "
                            "и как это трактовали. Интерпретация — как виделось НА ДАТУ, не сегодняшняя истина. "
                            "За полной записью — get_chronicle_entry(id)."),
            "parameters": {"type": "object", "properties": {
                "ticker": {"type": "string", "description": "Тикер компании (по умолчанию — разбираемая)"},
                "sectors": {"type": "array", "items": {"type": "string"},
                            "description": "Секторы (напр. oil_gas, finance, utilities) — расширить контекст"},
                "themes": {"type": "array", "items": {"type": "string"},
                           "description": "Темы (напр. key_rate, sanctions, oil_prices, dividends, taxes)"},
                "days": {"type": "integer", "description": "Окно в днях, по умолч. 365 (память долгая)"},
                "limit": {"type": "integer", "description": "1-20, по умолч. 10"},
            }},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chronicle_entry",
            "description": "Полная запись летописи по id (из query_chronicle): пересказ, тезисы, теги, источник.",
            "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
        },
    },
]

# Полная схема для ревизора: внутренние инструменты + веб-поиск/документы.
# Определена после WEB_TOOLS_SCHEMA (ниже) — присваивается в конце модуля.


# Веб-инструменты (владелец, 2026-07-21): поиск в сети + открытие/разбор
# документов (PDF-отчётность). Тикер-агностичны — обрабатываются в диспетчере
# ДО проверки allowed_ticker. Прод-нюанс egress — см. agent_web.py.
WEB_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Поиск в интернете: свежие новости/факты, которых нет во внутренней базе платформы. Возвращает заголовки, ссылки, сниппеты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос по-русски"},
                    "max_results": {"type": "integer", "description": "1-8, по умолчанию 5"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_document",
            "description": "Открыть документ по URL и вернуть его ТЕКСТ (PDF-отчётность МСФО/РСБУ → извлечение текста; веб-страница → очищенный текст). Для анализа первоисточника.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Прямая ссылка (http/https), в т.ч. на .pdf"}},
                "required": ["url"],
            },
        },
    },
]


def execute_tool(db: Session, name: str, args: dict, allowed_ticker: str) -> dict:
    """Диспетчер. allowed_ticker — агенту разрешён ТОЛЬКО его тикер (не даём
    пилоту гулять по всей базе — бюджет и предсказуемость). Веб-инструменты
    тикеро-агностичны."""
    # веб-инструменты — до проверки тикера
    if name == "web_search":
        from app.services.agent_web import web_search
        return web_search(str(args.get("query", "")), int(args.get("max_results", 5) or 5))
    if name == "fetch_document":
        from app.services.agent_web import fetch_document
        return fetch_document(str(args.get("url", "")))
    t = str(args.get("ticker", allowed_ticker)).upper()
    if t != allowed_ticker.upper():
        return {"error": "ticker_not_allowed", "note": f"Доступен только {allowed_ticker}"}
    if name == "read_macro_card":
        return _read_macro_card(t)
    if name == "get_live_macro":
        return _get_live_macro(db)
    if name == "get_recent_news":
        return _get_recent_news(db, t)
    if name == "get_recent_earnings":
        return _get_recent_earnings(db, t)
    if name == "get_calendar":
        return _get_calendar(db, t)
    if name == "get_geo_barometer":
        return _get_geo_barometer()
    if name == "query_chronicle":
        return _query_chronicle(db, t, args.get("sectors"), args.get("themes"),
                                args.get("days", 365), args.get("limit", 10))
    if name == "get_chronicle_entry":
        return _get_chronicle_entry(db, int(args.get("id", 0) or 0))
    return {"error": "unknown_tool"}


# Ревизор с веб-доступом (поиск + документы) — предпочтительная схема для
# card_review_agent, когда внутренних данных может не хватить.
REVIEW_TOOLS_WEB_SCHEMA = REVIEW_TOOLS_SCHEMA + WEB_TOOLS_SCHEMA
