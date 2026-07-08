"""ИИ-ассистент — диалоговый слой поверх контура Basis.

Двухшаговый пайплайн (по образцу observer_report.py):
  1. РАСПОЗНАВАНИЕ — LLM извлекает из вопроса пользователя тикеры (из реального
     списка компаний платформы) и намерения (скринер/макро/новости).
  2. СБОР КОНТЕКСТА — детерминированный код читает РЕАЛЬНЫЕ данные (те же файлы
     и таблицы, что отдают company-эндпоинты): *_summary.md, company_metrics,
     котировки, лента новостей.
  3. СИНТЕЗ — LLM формулирует ответ СТРОГО по переданному контексту, с ссылками
     на источники, без «купить/продать» и без чисел из памяти модели.

Если распознавание не нашло ни одного тикера/намерения — синтез идёт с пустым
контекстом и явной инструкцией не выдумывать (честно отвечает «нет данных» /
просит уточнить компанию).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.assistant import Conversation, Message

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

_MAX_HISTORY_MESSAGES = 8  # сколько последних сообщений диалога подмешиваем в контекст
_MAX_TICKERS_PER_TURN = 4  # не даём одному вопросу утянуть контекст на пол-рынка


# ----------------------------- Список компаний (кэш) -----------------------------
_TICKER_LIST_CACHE: dict = {"text": None, "ts": 0.0}
_TICKER_LIST_TTL = 3600.0


def _ticker_list_text(db: Session) -> str:
    """Стабильный (кэшируемый провайдером) список 'TICKER: Имя' — по одному на
    строку, отсортирован. Меняется редко (только когда добавляются компании),
    поэтому системный промпт распознавания остаётся стабильным между вызовами
    (см. заметку про DeepSeek prefix-cache в llm.py)."""
    now = time.time()
    if _TICKER_LIST_CACHE["text"] and now - _TICKER_LIST_CACHE["ts"] < _TICKER_LIST_TTL:
        return _TICKER_LIST_CACHE["text"]
    rows = db.execute(text("SELECT ticker, name FROM companies ORDER BY ticker")).all()
    txt = "\n".join(f"{r.ticker}: {r.name}" for r in rows)
    _TICKER_LIST_CACHE["text"] = txt
    _TICKER_LIST_CACHE["ts"] = now
    return txt


# ----------------------------- Шаг 1: распознавание -----------------------------
_EXTRACT_SYSTEM_PREFIX = (
    "Ты — диспетчер вопросов инвестора об российском фондовом рынке для платформы "
    "Basis. Твоя ЕДИНСТВЕННАЯ задача — понять, какие данные нужны, чтобы ответить, "
    "а НЕ отвечать самому. Извлеки из вопроса пользователя:\n"
    "- tickers: список тикеров компаний из СПИСКА НИЖЕ, которые упоминаются в вопросе "
    "(по названию, отрасли-намёку или тикеру напрямую). Пусто, если компания не "
    "упомянута. Бери ТОЛЬКО тикеры из списка, не выдумывай.\n"
    "- wants_screener: true, если вопрос просит найти/отфильтровать/отсортировать "
    "список компаний по критерию (P/E, дивдоходность, апсайд и т.п.).\n"
    "- wants_macro: true, если вопрос про макроэкономику РФ в целом (ставка, инфляция, "
    "курс) без привязки к конкретной компании.\n"
    "- wants_news: true, если вопрос про свежие новости/события.\n"
    "Верни строго JSON: {\"tickers\": [...], \"wants_screener\": bool, "
    "\"wants_macro\": bool, \"wants_news\": bool}\n\n"
    "СПИСОК КОМПАНИЙ ПЛАТФОРМЫ (тикер: имя):\n"
)


def _extract_entities(db: Session, user_message: str, history_text: str) -> dict:
    from app.services.llm import complete, LLMError
    system = _EXTRACT_SYSTEM_PREFIX + _ticker_list_text(db)
    user_content = (f"Недавний диалог (для контекста, если вопрос ссылается на "
                    f"предыдущий):\n{history_text}\n\nВопрос: {user_message}") if history_text else \
                   f"Вопрос: {user_message}"
    try:
        result = complete(system, user_content, json_mode=True, thinking=False,
                          max_tokens=400, temperature=0.0)
    except LLMError:
        logger.exception("Ассистент: распознавание намерения не удалось")
        return {"tickers": [], "wants_screener": False, "wants_macro": False, "wants_news": False}
    if not isinstance(result, dict):
        return {"tickers": [], "wants_screener": False, "wants_macro": False, "wants_news": False}
    tickers = result.get("tickers") or []
    if not isinstance(tickers, list):
        tickers = []
    return {
        "tickers": [str(t).upper() for t in tickers[:_MAX_TICKERS_PER_TURN] if t],
        "wants_screener": bool(result.get("wants_screener")),
        "wants_macro": bool(result.get("wants_macro")),
        "wants_news": bool(result.get("wants_news")),
    }


# ----------------------------- Шаг 2: сбор контекста -----------------------------
def _read_md(ticker: str, filename: str, max_chars: int) -> str | None:
    p = COMPANIES_DIR / ticker.upper() / filename
    if not p.exists():
        return None
    try:
        txt = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return txt[:max_chars] if txt else None


def _company_context(db: Session, ticker: str) -> dict | None:
    ticker = ticker.upper()
    row = db.execute(text("SELECT ticker, name, sector FROM companies WHERE ticker = :t"),
                     {"t": ticker}).first()
    if not row:
        return None
    price_row = db.execute(text(
        "SELECT q.close, q.date FROM quotes q JOIN companies c ON c.id = q.company_id "
        "WHERE c.ticker = :t ORDER BY q.date DESC LIMIT 1"
    ), {"t": ticker}).first()
    return {
        "ticker": row.ticker, "name": row.name, "sector": row.sector,
        "price": float(price_row.close) if price_row and price_row.close is not None else None,
        "price_date": price_row.date.isoformat() if price_row else None,
        "business_model": _read_md(ticker, "business_model.md", 2500),
        "financials_summary": _read_md(ticker, "financials_summary.md", 2500),
        "macro_summary": _read_md(ticker, "macro_summary.md", 1800),
        "market_summary": _read_md(ticker, "market_summary.md", 1500),
        "governance_summary": _read_md(ticker, "governance_summary.md", 1200),
    }


def _screener_context(db: Session, limit: int = 15) -> list[dict]:
    """Лёгкий срез по готовым метрикам (company_metrics) — не полный BASIS-скоринг
    (он тяжелее и заточен под UI-конструктор), для чата достаточно сырых метрик:
    модель сама отсортирует/отфильтрует по вопросу пользователя из переданных строк."""
    rows = db.execute(text(
        "SELECT c.ticker, c.name, c.sector, m.pe_current, m.div_yield, m.fair_value, "
        "m.beta, m.return_total_3y, l.close AS price "
        "FROM companies c JOIN company_metrics m ON m.ticker = c.ticker "
        "LEFT JOIN LATERAL (SELECT close FROM quotes q WHERE q.company_id = c.id "
        "ORDER BY q.date DESC LIMIT 1) l ON true "
        "WHERE m.pe_current IS NOT NULL ORDER BY c.ticker"
    )).all()
    out = []
    for r in rows:
        upside = None
        if r.fair_value and r.price:
            try:
                upside = round((float(r.fair_value) / float(r.price) - 1) * 100, 1)
            except (TypeError, ZeroDivisionError):
                pass
        out.append({"ticker": r.ticker, "name": r.name, "sector": r.sector,
                    "pe": float(r.pe_current) if r.pe_current is not None else None,
                    "div_yield_pct": float(r.div_yield) if r.div_yield is not None else None,
                    "price": float(r.price) if r.price is not None else None,
                    "fair_value": float(r.fair_value) if r.fair_value is not None else None,
                    "upside_pct": upside,
                    "beta": float(r.beta) if r.beta is not None else None,
                    "return_3y_pct": float(r.return_total_3y) if r.return_total_3y is not None else None})
    return out


def _macro_context(db: Session) -> dict:
    def last(code, metric="level"):
        r = db.execute(text(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
            "AND metric=:m ORDER BY as_of DESC LIMIT 1"
        ), {"c": code, "m": metric}).first()
        return {"value": float(r.value), "as_of": r.as_of.isoformat()} if r else None
    return {
        "key_rate": last("key_rate"),
        "inflation_yoy": last("inflation", "yoy"),
        "usdrub": last("usdrub"),
    }


def _news_context(db: Session, tickers: list[str] | None, limit: int = 8) -> list[dict]:
    from app.models.market import MarketUpdate
    q = db.query(MarketUpdate).filter(MarketUpdate.status == "published")
    rows = q.order_by(MarketUpdate.published_at.desc()).limit(60).all()
    if tickers:
        tset = set(tickers)
        filtered = [u for u in rows if set(u.affected_tickers or []) & tset]
        rows = (filtered or rows)[:limit]
    else:
        rows = rows[:limit]
    return [{"title": u.title, "impact": (u.impact_comment or "")[:200],
            "tickers": u.affected_tickers or [], "published_at": u.published_at.isoformat(),
            "url": u.source_url} for u in rows]


# ----------------------------- Шаг 3: синтез ответа -----------------------------
_ANSWER_FRAMEWORK = (
    "Ты — ИИ-ассистент инвестиционной платформы Basis для частного инвестора на "
    "российском рынке. Отвечай на вопрос ТОЛЬКО на основе данных в переданном "
    "контексте (JSON ниже) — НИКОГДА не используй цифры из своей памяти, даже если "
    "уверен в них: если нужного числа нет в контексте, честно скажи «этих данных "
    "нет на платформе», не досочиняй. Если контекст пустой или не по теме — прямо "
    "скажи, что не нашёл в контуре Basis данных по этому вопросу, и предложи "
    "переформулировать (например, назвать тикер/компанию).\n\n"
    "СТРОГО ЗАПРЕЩЕНО: рекомендации «покупать/продавать», целевые цены как совет, "
    "прогнозы будущей цены. Справедливую цену/апсайд из контекста подавай как "
    "оценку/модель Basis, а не факт и не сигнал.\n\n"
    "Каждое численное утверждение — с явной пометкой (факт с датой / оценка Basis / "
    "суждение), коротко в скобках. Тон — спокойный, по делу, как у грамотного "
    "аналитика, а не рекламный. Отвечай на русском, markdown, без воды."
)


def _build_context(db: Session, entities: dict) -> tuple[dict, list[dict]]:
    ctx: dict = {}
    refs: list[dict] = []
    companies = []
    for t in entities["tickers"]:
        c = _company_context(db, t)
        if c:
            companies.append(c)
            refs.append({"kind": "company", "ticker": t,
                        "as_of": c.get("price_date"), "title": c.get("name")})
    if companies:
        ctx["companies"] = companies
    if entities["wants_screener"]:
        ctx["screener"] = _screener_context(db)
        refs.append({"kind": "screener", "title": "Скринер акций — метрики company_metrics"})
    if entities["wants_macro"]:
        ctx["macro"] = _macro_context(db)
        refs.append({"kind": "macro", "title": "Макропоказатели РФ"})
    if entities["wants_news"] or companies:
        news = _news_context(db, entities["tickers"] or None)
        if news:
            ctx["news"] = news
            refs.append({"kind": "news", "title": f"Лента новостей ({len(news)})"})
    return ctx, refs


def _history_text(messages: list[Message]) -> str:
    tail = messages[-_MAX_HISTORY_MESSAGES:]
    lines = []
    for m in tail:
        prefix = "Пользователь" if m.role == "user" else "Ассистент"
        lines.append(f"{prefix}: {m.content[:500]}")
    return "\n".join(lines)


def ask(db: Session, user_id: int, user_message: str, conversation_id: int | None) -> Conversation:
    """Главная точка входа. Создаёт диалог при conversation_id=None, иначе
    дописывает в существующий (с проверкой владельца). Возвращает Conversation
    со свежими messages (включая только что добавленные user+assistant)."""
    from app.services.llm import complete, LLMError

    if conversation_id is not None:
        conv = db.get(Conversation, conversation_id)
        if not conv or conv.user_id != user_id:
            conv = None
    else:
        conv = None
    if conv is None:
        conv = Conversation(user_id=user_id, title=user_message[:120])
        db.add(conv)
        db.flush()

    history_text = _history_text(conv.messages) if conv.messages else ""

    user_msg = Message(conversation_id=conv.id, role="user", content=user_message)
    db.add(user_msg)

    entities = _extract_entities(db, user_message, history_text)
    ctx, refs = _build_context(db, entities)

    user_content = ((f"Недавний диалог:\n{history_text}\n\n" if history_text else "") +
                    f"Вопрос: {user_message}\n\nКонтекст (JSON):\n{json.dumps(ctx, ensure_ascii=False)}")
    try:
        answer_text = complete(_ANSWER_FRAMEWORK, user_content, json_mode=False,
                               thinking=False, max_tokens=1800, temperature=0.3)
        if not isinstance(answer_text, str):
            answer_text = str(answer_text)
        answer_text = answer_text.strip() or "Не удалось сформировать ответ — попробуйте переформулировать вопрос."
    except LLMError:
        logger.exception("Ассистент: синтез ответа не удался")
        answer_text = "Сервис временно недоступен, попробуйте ещё раз через минуту."
        refs = []

    assistant_msg = Message(conversation_id=conv.id, role="assistant",
                            content=answer_text, source_refs=refs)
    db.add(assistant_msg)
    conv.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conv)
    return conv
