"""API ИИ-обозревательского отчёта (Обозреватель, Направление 5).

Per-user: история видна только владельцу. Синтез строго по данным платформы.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user
from app.models.user import User
from app.models.observer_report import ObserverReport, REPORT_TYPES

router = APIRouter()


def _serialize(r: ObserverReport) -> dict:
    return {
        "id": r.id, "report_type": r.report_type, "horizon_days": r.horizon_days,
        "content": r.content, "source_refs": r.source_refs or [],
        "portfolio_snapshot": r.portfolio_snapshot or [], "model_used": r.model_used,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    }


@router.post("/observer/reports")
def create_report(type: str = Query("express"),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Сгенерировать сводный отчёт по типу (express|detailed|deep). Синтез по данным
    платформы (Напр.1-4,6,7 + портфель). Сохраняется в историю пользователя."""
    if type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Неизвестный тип отчёта")
    from app.services.observer_report import generate
    from app.services.llm import LLMError
    try:
        rep = generate(db, user.id, type)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"Генератор недоступен: {e}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {e}")
    return _serialize(rep)


@router.get("/observer/reports")
def list_reports(limit: int = Query(30, ge=1, le=100),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """История отчётов пользователя (только его)."""
    rows = (db.query(ObserverReport).filter(ObserverReport.user_id == user.id)
            .order_by(ObserverReport.generated_at.desc()).limit(limit).all())
    return [{"id": r.id, "report_type": r.report_type, "horizon_days": r.horizon_days,
             "generated_at": r.generated_at.isoformat() if r.generated_at else None,
             "preview": (r.content or "")[:160]} for r in rows]


@router.get("/observer/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    r = db.get(ObserverReport, report_id)
    if not r or r.user_id != user.id:
        raise HTTPException(status_code=404, detail="Отчёт не найден")
    return _serialize(r)
