"""Автономные обновления карточек (пилот DeepSeek-агентов) — см. миграцию
b7d1e4f2a950 и docs/status.md «путь к автономной платформе» (фазы 2-3)."""
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base


class AgentAddendum(Base):
    __tablename__ = "agent_addenda"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(16), nullable=False, index=True)
    kind = Column(String(32), nullable=False)          # macro_addendum
    status = Column(String(16), nullable=False)        # published | rejected
    content = Column(JSONB, nullable=True)             # то, что показывает фронт
    gate_notes = Column(JSONB, nullable=True)          # почему отклонено/предупреждения
    run_trace = Column(JSONB, nullable=True)           # шаги агента (какие инструменты звал)
    model_used = Column(String(64), nullable=True)
    tokens_used = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
