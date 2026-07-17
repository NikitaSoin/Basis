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


def execute_tool(db: Session, name: str, args: dict, allowed_ticker: str) -> dict:
    """Диспетчер. allowed_ticker — агенту разрешён ТОЛЬКО его тикер (не даём
    пилоту гулять по всей базе — бюджет и предсказуемость)."""
    t = str(args.get("ticker", allowed_ticker)).upper()
    if t != allowed_ticker.upper():
        return {"error": "ticker_not_allowed", "note": f"Доступен только {allowed_ticker}"}
    if name == "read_macro_card":
        return _read_macro_card(t)
    if name == "get_live_macro":
        return _get_live_macro(db)
    if name == "get_recent_news":
        return _get_recent_news(db, t)
    return {"error": "unknown_tool"}
