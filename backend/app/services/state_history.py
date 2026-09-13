"""Хронология прошлых версий сводки — для аналитика, который сейчас видит
только вчерашнюю.

🔴 ЗАЧЕМ (владелец, 2026-09-13): «агенты при формировании нового разбора
опираются на старый — стоит ли делать хронологию?». Да: по одной вчерашней
версии не видно ТРАЕКТОРИИ — ускоряется ли инфляция третий день или это
первый скачок, менялся ли режим на прошлой неделе, сколько раз проверяющий
ловил одно и то же. Здесь версия за версией сворачивается в короткую строку
(дата, главное, что изменилось, замечания проверки), и аналитик получает
последние N строк — трек-рекорд, а не архив.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion


def timeline(db: Session, kind: str, limit: int = 10) -> list[dict]:
    rows = (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == kind, BarometerVersion.status == "published")
            .order_by(BarometerVersion.created_at.desc()).limit(limit).all())
    out = []
    for v in rows:
        p = v.payload or {}
        changes = []
        for b in (p.get("blocks") or p.get("sections") or []):
            if isinstance(b, dict) and b.get("delta_vs_prev") and "не изменил" not in str(b.get("delta_vs_prev")).lower():
                changes.append(f"{b.get('key')}: {str(b.get('delta_vs_prev'))[:120]}")
        diag = p.get("diagnosis") or p.get("regime") or {}
        out.append({
            "version_id": v.id, "as_of": p.get("as_of"),
            "created_at": v.created_at.date().isoformat() if v.created_at else None,
            "headline": str(p.get("summary") or "")[:260],
            "regime": str((diag.get("regime") if isinstance(diag, dict) else diag) or (diag.get("type") if isinstance(diag, dict) else ""))[:140],
            "changes": changes[:6],
            "gate_notes": (v.gate_notes or [])[:4],
        })
    return out


def for_prompt(db: Session, kind: str, limit: int = 10) -> str:
    events = timeline(db, kind, limit)
    if not events:
        return "ХРОНОЛОГИЯ ПРОШЛЫХ ВЕРСИЙ: — это первая версия —"
    lines = ["ХРОНОЛОГИЯ ПРОШЛЫХ ВЕРСИЙ — последние " + str(len(events)) + " как ориентир (свежие сверху; "
             "смотри ТРАЕКТОРИЮ, а не только вчерашний день). 🔴 ПОЛНЫЙ АРХИВ ЗА ЛЮБОЙ ПЕРИОД — "
             "инструментами list_state_versions / read_state_version: если нужно, как ситуация "
             "виделась месяц или полгода назад, — открой ту версию."]
    for e in events:
        lines.append(f"• {e['as_of']} (v{e['version_id']}): {e['headline']}")
        if e["regime"]:
            lines.append(f"    режим: {e['regime']}")
        for c in e["changes"]:
            lines.append(f"    Δ {c}")
        if e["gate_notes"]:
            lines.append(f"    замечания проверки: {'; '.join(str(n)[:80] for n in e['gate_notes'])}")
    return "\n".join(lines)
