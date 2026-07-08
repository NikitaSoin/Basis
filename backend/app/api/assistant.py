"""API ИИ-ассистента (глобальный чат, авторизованный).

Отдельно от observer_report.py (тот — периодический дайджест по расписанию);
здесь — интерактивный диалог: пользователь спрашивает, ассистент ищет ответ в
реальных данных платформы (function-calling к company/screener/macro/новости)
и отвечает, сохраняя историю per-user."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.assistant import Conversation

router = APIRouter()


class AskRequest(BaseModel):
    message: str
    conversation_id: int | None = None


def _serialize_conversation(c: Conversation, full: bool) -> dict:
    out = {
        "id": c.id, "title": c.title,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if full:
        out["messages"] = [
            {"id": m.id, "role": m.role, "content": m.content,
             "source_refs": m.source_refs or [],
             "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in c.messages
        ]
    return out


@router.post("/assistant/ask")
def ask(data: AskRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not data.message or not data.message.strip():
        raise HTTPException(status_code=400, detail="Пустой вопрос")
    if len(data.message) > 2000:
        raise HTTPException(status_code=400, detail="Слишком длинный вопрос (макс. 2000 символов)")
    from app.services.assistant import ask as ask_service
    from app.services.llm import LLMError
    try:
        conv = ask_service(db, user.id, data.message.strip(), data.conversation_id)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"Ассистент временно недоступен: {e}")
    return _serialize_conversation(conv, full=True)


@router.get("/assistant/conversations")
def list_conversations(limit: int = Query(30, ge=1, le=100),
                       db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (db.query(Conversation).filter(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc()).limit(limit).all())
    return [_serialize_conversation(c, full=False) for c in rows]


@router.get("/assistant/conversations/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    c = db.get(Conversation, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    return _serialize_conversation(c, full=True)


@router.delete("/assistant/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    c = db.get(Conversation, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status_code=404, detail="Диалог не найден")
    db.delete(c)
    db.commit()
    return {"ok": True}
