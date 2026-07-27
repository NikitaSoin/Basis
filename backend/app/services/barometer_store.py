"""Единый READ-PATH барометров (гео/институты).

Владелец (2026-07-27): автономный ревизор катит обновления СРАЗУ НА БОЙ (не в
черновик). Значит фронт/оверлей/эндпоинты обязаны читать ТЕКУЩУЮ published-
версию из БД — иначе агент публикует в БД, а витрина показывает старый файл
(«третий расходящийся слой», о котором предупреждал advisor). Этот модуль —
единственная точка чтения барометра для ВСЕХ потребителей (market.py,
situation_overlay, barometer_reviser). Вынесен отдельно, чтобы разорвать цикл
импортов (reviser ↔ situation_overlay).

Источник правды:
- есть published-версия в БД → она (source может быть expert или auto);
- БД пуста → импорт экспертного файла config/*.json как source=expert/published
  (паттерн asset_data: файл остаётся якорем, БД его зеркалит и версионирует).
Экспертный workflow цел: субагент пишет файл → git push → при деплое первое
чтение (или reimport_expert) апсертит новую source=expert версию.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion

logger = logging.getLogger(__name__)

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FILES = {"geo": os.path.join(_BACKEND, "config", "geo_barometer.json"),
         "inst": os.path.join(_BACKEND, "config", "institutional_barometer.json")}


def _read_file(kind: str) -> dict | None:
    path = FILES.get(kind)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("barometer_store: файл %s не прочитан: %s", kind, e)
        return None


def current_row(db: Session, kind: str) -> BarometerVersion | None:
    """Последняя published-версия из БД; если БД пуста — импорт файла как
    expert/published и возврат этой строки."""
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == kind, BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    if row is not None:
        return row
    payload = _read_file(kind)
    if payload is None:
        return None
    row = BarometerVersion(kind=kind, source="expert", status="published",
                           payload=payload, trigger_reason="import_from_file")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("barometer_store: экспертный якорь %s импортирован в БД v#%d", kind, row.id)
    return row


def last_expert(db: Session, kind: str) -> BarometerVersion | None:
    return (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == kind, BarometerVersion.source == "expert")
            .order_by(BarometerVersion.created_at.desc()).first())


def get_payload_with_meta(db: Session, kind: str) -> dict | None:
    """Payload барометра для витрины + служебный _meta про источник/свежесть —
    чтобы фронт честно пометил авто-обновление (эпистемика). Формат самого
    барометра НЕ меняется (обратная совместимость с фронтом), _meta добавочный.
    Читает файл-фолбэком, если БД/модель недоступны (никогда не роняет витрину)."""
    try:
        row = current_row(db, kind)
    except Exception:  # noqa: BLE001 — витрина важнее версионирования
        logger.warning("barometer_store: чтение из БД упало, фолбэк на файл", exc_info=True)
        row = None
    if row is None:
        payload = _read_file(kind)
        return payload  # без _meta — как было исторически
    payload = dict(row.payload or {})
    expert = last_expert(db, kind)
    payload["_meta"] = {
        "source": row.source,                       # expert | auto
        "generated_at": row.created_at.isoformat() if row.created_at else None,
        "expert_anchor_as_of": (expert.payload or {}).get("as_of") if expert else payload.get("as_of"),
        "trigger_reason": row.trigger_reason,
    }
    return payload


def reimport_expert(db: Session, kind: str) -> BarometerVersion | None:
    """Форс-переимпорт экспертного файла как новой source=expert/published
    версии (после ручного обновления барометра субагентом + git push).
    Обнуляет поводок дрейфа авторевизий. Идемпотентно по содержимому: если
    файл не менялся с последней expert-версии — не плодит дубль."""
    payload = _read_file(kind)
    if payload is None:
        return None
    exp = last_expert(db, kind)
    if exp and exp.payload == payload:
        return exp  # содержимое то же — не дублируем
    row = BarometerVersion(kind=kind, source="expert", status="published",
                           payload=payload, trigger_reason="reimport_expert",
                           created_at=datetime.now(timezone.utc))
    db.add(row); db.commit(); db.refresh(row)
    logger.info("barometer_store: переимпорт эксперта %s → v#%d", kind, row.id)
    return row
