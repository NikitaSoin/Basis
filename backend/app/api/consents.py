"""Согласия и акцепт условий: запись, чтение, отзыв.

Что здесь принципиально: акцепт оферты фиксируется В МОМЕНТ РЕГИСТРАЦИИ самим
эндпоинтом регистрации (см. api/auth.py), а не отдельным запросом с фронта. Иначе
возможен разрыв — аккаунт создан, а подтверждения нет, — и именно он всплывёт в
споре. Здесь остаются согласия, которые человек даёт ПОЗЖЕ и может отозвать:
аналитика, передача в языковую модель, рассылки.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user_optional
from app.db.session import get_db
from app.models.consent import KINDS, Consent

router = APIRouter(prefix="/consents", tags=["consents"])

GUEST_HEADER = "X-Guest-Token"


def _guest(request: Request) -> str | None:
    raw = (request.headers.get(GUEST_HEADER) or "").strip()
    return raw if 16 <= len(raw) <= 64 and raw.isalnum() else None


class ConsentIn(BaseModel):
    kind: str = Field(max_length=24)
    version: str = Field(default="1.0", max_length=16)
    granted: bool = True
    meta: dict | None = None


def _active(db: Session, kind: str, uid: int | None, guest: str | None) -> Consent | None:
    q = select(Consent).where(Consent.kind == kind, Consent.revoked_at.is_(None))
    q = q.where(Consent.user_id == uid) if uid else q.where(Consent.guest_token == guest)
    return db.execute(q.order_by(Consent.granted_at.desc()).limit(1)).scalar_one_or_none()


@router.post("")
def set_consent(payload: ConsentIn, request: Request, db: Session = Depends(get_db),
                user=Depends(get_current_user_optional)):
    """Дать или отозвать согласие. Повторное «да» не плодит записи, а отзыв не
    удаляет прежнюю: история решений — часть доказательства."""
    if payload.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"Неизвестный вид согласия: {payload.kind}")
    uid = getattr(user, "id", None)
    guest = _guest(request)
    if not uid and not guest:
        raise HTTPException(status_code=400, detail="Нужен токен аккаунта или гостя")

    current = _active(db, payload.kind, uid, guest)
    if payload.granted:
        if current and current.version == payload.version:
            return {"kind": payload.kind, "version": current.version, "granted": True,
                    "granted_at": current.granted_at.isoformat(), "новая_запись": False}
        if current:                      # согласие на новую редакцию заменяет прежнее
            current.revoked_at = datetime.now(timezone.utc)
        row = Consent(user_id=uid, guest_token=None if uid else guest, kind=payload.kind,
                      version=payload.version, meta=payload.meta)
        db.add(row)
        db.commit()
        return {"kind": row.kind, "version": row.version, "granted": True,
                "granted_at": row.granted_at.isoformat(), "новая_запись": True}

    if current:
        current.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"kind": payload.kind, "granted": False}


@router.get("/me")
def my_consents(request: Request, db: Session = Depends(get_db),
                user=Depends(get_current_user_optional)):
    """Что действует прямо сейчас — для интерфейса настроек."""
    uid = getattr(user, "id", None)
    guest = _guest(request)
    out = {}
    for kind in KINDS:
        row = _active(db, kind, uid, guest) if (uid or guest) else None
        out[kind] = {"granted": bool(row),
                     "version": row.version if row else None,
                     "granted_at": row.granted_at.isoformat() if row else None}
    return out
