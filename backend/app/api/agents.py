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
