"""API автономных агентов (пилот). Чтение addenda — публичное (фронт карточки);
ручной запуск — только для тикеров из AGENT_PILOT_TICKERS (не даём жечь LLM-бюджет
по всем 264 тикерам произвольными запросами)."""
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()


def _pilot_tickers() -> set[str]:
    raw = os.environ.get("AGENT_PILOT_TICKERS", "KLSB")
    return {t.strip().upper() for t in raw.split(",") if t.strip()}


@router.get("/companies/by-ticker/{ticker}/agent-addenda")
def list_agent_addenda(ticker: str, db: Session = Depends(get_db)):
    """Опубликованные автономные обновления карточки (новые сверху, до 5)."""
    from app.models.agent_addendum import AgentAddendum
    rows = (db.query(AgentAddendum)
            .filter(AgentAddendum.ticker == ticker.upper(),
                    AgentAddendum.status == "published")
            .order_by(AgentAddendum.created_at.desc()).limit(5).all())
    return {"addenda": [
        {"id": r.id, "kind": r.kind, "content": r.content,
         "created_at": r.created_at.isoformat(), "model_used": r.model_used}
        for r in rows
    ]}


@router.post("/agents/run-macro-addendum/{ticker}")
def trigger_macro_addendum(ticker: str, db: Session = Depends(get_db)):
    """Ручной запуск пилотного агента (отладка/демо владельцу). Только пилотные тикеры."""
    t = ticker.upper()
    if t not in _pilot_tickers():
        raise HTTPException(status_code=403, detail=f"Тикер не в пилоте (AGENT_PILOT_TICKERS={','.join(sorted(_pilot_tickers()))})")
    from app.services.macro_addendum_agent import run_macro_addendum
    row = run_macro_addendum(db, t)
    return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes,
            "tokens_used": row.tokens_used, "content": row.content}


# ─────────── Агент-ревизор актуальности блоков (все вкладки + облигации) ───────────

_REVIEW_FRESH_HOURS = 12  # свежую ревизию не перезапускаем (кэш = экономия токенов)


def _latest_review(db, ticker: str, kind: str):
    from app.models.agent_addendum import AgentAddendum
    return (db.query(AgentAddendum)
            .filter(AgentAddendum.ticker == ticker.upper(),
                    AgentAddendum.kind == kind,
                    AgentAddendum.status == "published")
            .order_by(AgentAddendum.created_at.desc()).first())


def _review_payload(row):
    return {"id": row.id, "kind": row.kind, "content": row.content,
            "created_at": row.created_at.isoformat(), "model_used": row.model_used}


@router.get("/companies/by-ticker/{ticker}/reviews")
def list_card_reviews(ticker: str, db: Session = Depends(get_db)):
    """Все кэшированные ревизии актуальности блоков компании (последняя published
    по каждой вкладке) — фронт показывает на соответствующей вкладке."""
    from app.models.agent_addendum import AgentAddendum
    from app.services.card_review_agent import TAB_CONFIG
    out = {}
    for tab in TAB_CONFIG:
        row = _latest_review(db, ticker, f"review:{tab}")
        if row:
            out[tab] = _review_payload(row)
    return {"reviews": out}


@router.post("/agents/review/{ticker}/{tab}")
def trigger_card_review(ticker: str, tab: str, force: bool = False, db: Session = Depends(get_db)):
    """Запустить ревизию актуальности вкладки. Свежую (<12ч) не перезапускаем —
    отдаём кэш (force=true обходит). Работает для любой компании (демо по
    требованию + кэш, не крон по всем)."""
    from datetime import datetime, timezone, timedelta
    from app.services.card_review_agent import TAB_CONFIG, run_card_review
    if tab not in TAB_CONFIG:
        raise HTTPException(status_code=404, detail=f"Неизвестная вкладка: {tab}")
    if not force:
        cached = _latest_review(db, ticker, f"review:{tab}")
        if cached and (datetime.now(timezone.utc) - cached.created_at) < timedelta(hours=_REVIEW_FRESH_HOURS):
            return {**_review_payload(cached), "from_cache": True}
    row = run_card_review(db, ticker, tab)
    return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes,
            "tokens_used": row.tokens_used, "content": row.content, "from_cache": False}


@router.get("/bonds/{secid}/review")
def get_bond_review(secid: str, db: Session = Depends(get_db)):
    row = _latest_review(db, secid, "review:bond")
    return {"review": _review_payload(row) if row else None}


@router.post("/agents/review-bond/{secid}")
def trigger_bond_review(secid: str, force: bool = False, db: Session = Depends(get_db)):
    from datetime import datetime, timezone, timedelta
    from app.services.card_review_agent import run_bond_review
    if not force:
        cached = _latest_review(db, secid, "review:bond")
        if cached and (datetime.now(timezone.utc) - cached.created_at) < timedelta(hours=_REVIEW_FRESH_HOURS):
            return {**_review_payload(cached), "from_cache": True}
    row = run_bond_review(db, secid)
    return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes,
            "tokens_used": row.tokens_used, "content": row.content, "from_cache": False}


# ─────────── Разбор документа по ссылке (PDF/HTML) + веб-поиск ───────────

@router.post("/agents/analyze-document")
def analyze_document_endpoint(payload: dict):
    """Открыть документ по URL (PDF-отчётность МСФО/РСБУ или веб-страница) и
    вернуть структурный разбор — демонстрация «файл приходит агенту, он его
    анализирует». Egress-нюанс: на проде внешний хост может быть недоступен без
    релея (см. agent_web.py) — тогда честная ошибка, не падение."""
    from app.services.document_analyst import analyze_document
    url = str(payload.get("url", "")).strip()
    if not url:
        return {"error": "no_url"}
    return analyze_document(url, question=(payload.get("question") or None))


@router.get("/agents/web-search")
def web_search_endpoint(q: str):
    """Демо веб-поиска (для отладки/проверки, что поиск с сервера вообще
    проходит). Возвращает провайдера и результаты либо ошибку egress."""
    from app.services.agent_web import web_search
    if not q or len(q) < 3:
        return {"error": "query_too_short"}
    return web_search(q, 5)
