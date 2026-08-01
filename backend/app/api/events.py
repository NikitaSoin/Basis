"""Приём продуктовых событий с фронтенда.

Владелец 2026-08-01: «хотелось бы записывать логи по клиентам и знать, как часто они
заходят, по каким страницам ходят, что кликают».

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ МЕТРИКИ: Метрика считает ВИЗИТЫ и не знает, кто их совершил. Она
не ответит на вопрос «пользователи с портфелем из пяти и более бумаг чаще открывают
корреляции?» — а именно такие вопросы двигают продукт. Здесь события ложатся в ту же
базу, что users и portfolios, поэтому джойнятся обычным SQL. Метрику это не заменяет:
карта кликов и записи сессий остаются за ней.

🔴 БЕЗ ПЕРСОНАЛЬНЫХ ДАННЫХ. Пишем user_id (у гостей NULL) и анонимный идентификатор
устройства из localStorage. Ни почт, ни имён, ни IP: для продуктовых выводов они не
нужны, а хранить их — брать на себя обязательства по 152-ФЗ без надобности.

🔴 ЭНДПОИНТ НИКОГДА НЕ МЕШАЕТ ПОЛЬЗОВАТЕЛЮ. Любая ошибка записи проглатывается и
возвращается 200: аналитика не тот повод, чтобы у человека сломался экран. По той же
причине стоят жёсткие ограничения на размер — иначе кривой клиент может залить базу.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_BATCH = 20          # событий за один запрос
_MAX_STR = 512


class EventIn(BaseModel):
    kind: str = Field(max_length=24)              # pageview | click | action
    name: str | None = Field(default=None, max_length=120)
    path: str | None = Field(default=None, max_length=_MAX_STR)
    referrer: str | None = Field(default=None, max_length=_MAX_STR)
    meta: dict | None = None
    anon_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class EventsIn(BaseModel):
    events: list[EventIn] = Field(default_factory=list)


@router.post("/events")
def collect_events(payload: EventsIn, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(get_current_user_optional)):
    """Принять пачку событий. Всегда отвечает 200, даже при сбое записи."""
    try:
        uid = getattr(user, "id", None)
        rows = payload.events[:_MAX_BATCH]
        if not rows:
            return {"принято": 0}

        записано = 0
        for e in rows:
            kind = (e.kind or "").strip()[:24]
            if kind not in ("pageview", "click", "action"):
                continue                      # неизвестный вид не пишем, чтобы не мусорить
            meta = e.meta if isinstance(e.meta, dict) else None
            if meta and len(str(meta)) > 2000:
                meta = {"_обрезано": True}
            db.execute(text(
                "INSERT INTO user_events (user_id, anon_id, session_id, kind, name, path, referrer, meta) "
                "VALUES (:uid, :anon, :sess, :kind, :name, :path, :ref, CAST(:meta AS JSON))"
            ), {
                "uid": uid,
                "anon": (e.anon_id or None), "sess": (e.session_id or None),
                "kind": kind, "name": (e.name or None),
                "path": (e.path or None)[:_MAX_STR] if e.path else None,
                "ref": (e.referrer or None)[:_MAX_STR] if e.referrer else None,
                "meta": __import__("json").dumps(meta, ensure_ascii=False) if meta else None,
            })
            записано += 1
        db.commit()
        return {"принято": записано, "отброшено": len(rows) - записано}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("события не записаны: %s", e)
        return {"принято": 0}
