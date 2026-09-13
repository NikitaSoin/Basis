"""Петля уроков: замечания проверяющего → база «не повторять» → задание аналитика.

🔴 ЗАЧЕМ (владелец, 2026-09-13): «когда критик говорит "вот тут ты ошибся" —
собирать такие кейсы в базу знаний, чтобы агенты перед публикацией опирались
на неё и не ошибались больше». Это и есть самообучение в его единственной
честной форме без дообучения модели: не веса, а память об ошибках, которая
читается перед работой и проверяется после.

Как устроено:
  harvest()   — после проверяющего: каждое нарушение → урок (контур, правило,
                где, образец, что делать). Повтор того же правила в том же
                месте — не новый урок, а +1 к occurrences: так видно, что
                ошибка ЗАКРЕПИЛАСЬ, а не случилась.
  for_prompt()— перед сборкой: активные уроки контура, самые повторяющиеся
                первыми, в задание блоком «УРОКИ ПРОШЛЫХ ПРОВЕРОК».
  settle()    — урок, чьё правило не нарушалось три проверки подряд, помечается
                «усвоен» и из задания уходит (иначе список растёт вечно и
                перестаёт читаться).

Что здесь НЕ делается: правила не переписываются автоматически в методички и
не «уговаривают» модель — урок это данные в задании, и его действие
проверяется тем же проверяющим на следующий день. Не помог — occurrences
растёт, и это видно.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.lessons import AgentLesson

logger = logging.getLogger(__name__)

SETTLE_AFTER = 3          # чистых проверок подряд, чтобы считать урок усвоенным
PROMPT_LIMIT = 15


def _norm(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip().lower()
    return s[:120]


def lesson_key(contour: str, rule: str, where: str) -> str:
    """Ключ урока: правило + место (без цитаты — цитата меняется, ошибка та же)."""
    where_core = _norm(where).split(",")[0].split(";")[0][:60]
    return f"{contour}|{_norm(rule)[:60]}|{where_core}"


def harvest(db: Session, contour: str, violations: list[dict], review_id: int | None = None) -> dict:
    now = datetime.now(timezone.utc)
    seen_keys: set[str] = set()
    pending: dict[str, AgentLesson] = {}   # уроки, созданные в ЭТОМ же вызове
    created = repeated = 0
    for v in violations:
        if not isinstance(v, dict) or not v.get("rule"):
            continue
        key = lesson_key(contour, v.get("rule", ""), v.get("where", ""))
        # 🔴 Два одинаковых нарушения в одной проверке (то же правило, то же
        # место) — один урок: второе не должно стать новой строкой до записи
        # первой (ловилось UniqueViolation на геосводке).
        if key in seen_keys:
            row = pending.get(key) or db.query(AgentLesson).filter(AgentLesson.key == key).first()
            if row is not None:
                row.occurrences += 1
            continue
        seen_keys.add(key)
        row = db.query(AgentLesson).filter(AgentLesson.key == key).first()
        if row is None:
            row = AgentLesson(key=key, contour=contour, rule=str(v.get("rule"))[:200],
                              where=str(v.get("where"))[:300], example=str(v.get("quote"))[:600],
                              fix=str(v.get("fix"))[:800], severity=str(v.get("severity"))[:20],
                              occurrences=1, clean_streak=0, status="active",
                              first_seen=now, last_seen=now, last_review_id=review_id)
            db.add(row); pending[key] = row
            created += 1
        else:
            row.occurrences += 1; row.clean_streak = 0; row.last_seen = now
            row.last_review_id = review_id; row.status = "active"
            row.example = str(v.get("quote"))[:600] or row.example
            row.fix = str(v.get("fix"))[:800] or row.fix
            repeated += 1
    # уроки контура, которые в этой проверке НЕ повторились, — шаг к «усвоен»
    settled = 0
    for row in db.query(AgentLesson).filter(AgentLesson.contour == contour, AgentLesson.status == "active").all():
        if row.key not in seen_keys:
            row.clean_streak += 1
            if row.clean_streak >= SETTLE_AFTER:
                row.status = "settled"; settled += 1
    db.commit()
    logger.info("lessons[%s]: новых %d, повторов %d, усвоено %d", contour, created, repeated, settled)
    return {"created": created, "repeated": repeated, "settled": settled}


def active(db: Session, contour: str, limit: int = PROMPT_LIMIT) -> list[AgentLesson]:
    return (db.query(AgentLesson)
            .filter(AgentLesson.contour == contour, AgentLesson.status == "active")
            .order_by(AgentLesson.occurrences.desc(), AgentLesson.last_seen.desc())
            .limit(limit).all())


def for_prompt(db: Session, contour: str, limit: int = PROMPT_LIMIT) -> str:
    rows = active(db, contour, limit)
    if not rows:
        return "УРОКИ ПРОШЛЫХ ПРОВЕРОК: — пока нет —"
    lines = ["УРОКИ ПРОШЛЫХ ПРОВЕРОК — самые повторяющиеся (не повторять; по каждому в "
             "lessons_applied скажи, как учёл). Вся база уроков — инструментом read_lessons. "
             "Методичек это не касается: уроки живут отдельно."]
    for r in rows:
        rep = f" — ПОВТОРЯЛОСЬ {r.occurrences}×" if r.occurrences > 1 else ""
        lines.append(f"• [{r.severity}] {r.rule} @ {r.where}{rep}\n    было: «{(r.example or '')[:160]}»\n    надо: {(r.fix or '')[:220]}")
    return "\n".join(lines)


def snapshot(db: Session, contour: str | None = None) -> dict:
    q = db.query(AgentLesson)
    if contour:
        q = q.filter(AgentLesson.contour == contour)
    rows = q.order_by(AgentLesson.status, AgentLesson.occurrences.desc()).limit(300).all()
    return {"lessons": [{"contour": r.contour, "rule": r.rule, "where": r.where, "example": r.example,
                         "fix": r.fix, "severity": r.severity, "occurrences": r.occurrences,
                         "clean_streak": r.clean_streak, "status": r.status,
                         "first_seen": r.first_seen.date().isoformat() if r.first_seen else None,
                         "last_seen": r.last_seen.date().isoformat() if r.last_seen else None}
                        for r in rows]}
