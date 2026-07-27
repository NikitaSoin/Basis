"""Историческая хронология барометров (гео/институты) — READ-ONLY слой поверх
УЖЕ существующей версионированной истории `BarometerVersion` (barometer_reviser.py
пишет её на каждый прогон). Не новая база данных и не отдельный лог, который
кто-то должен не забыть заполнить — чистая производная от того, что система и так
сохраняет: экспертные калибровки (source=expert) + опубликованные авторевизии
(source=auto, status=published, каждый сдвинутый субиндекс уже обязан иметь
delta_rationale со ссылкой на статьи-основания, это гейт revise() требует).

Владелец (2026-07-27, после дизайн-разговора об «Обзоре рынка»/статьях): «хочу,
чтобы важные вещи запоминались и агенты видели готовый исторический контекст,
не начинали каждый раз с нуля». Выбрал (2026-07-28) начать с ВНУТРЕННЕГО слоя для
агентов, не с пользовательской фичи. Это и есть тот слой: get_revision_timeline()
даёт агенту (сначала — самому ревизору, barometer_reviser.py; позже — субагентам
geo-macro-analyst/institutional-macro-analyst при ручном перепрогоне) хронологию
«что менялось и почему» вместо голого текущего снапшота барометра.

rejected-версии сюда НЕ попадают — они не прошли гейт и ничего не изменили
на бою, включать их в «историю важного» значило бы путать черновик с фактом.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion

_KIND_LABEL = {"geo": "геополитический барометр", "inst": "институциональный барометр"}


def _subindex_events(version: BarometerVersion) -> list[dict]:
    """Сдвинутые субиндексы этой версии (delta_rationale — маркер движения,
    гейт revise() не пропускает сдвиг без него)."""
    payload = version.payload or {}
    out = []
    for s in payload.get("subindices") or []:
        dr = (s.get("delta_rationale") or "").strip()
        if not dr:
            continue
        out.append({
            "occurred_at": version.created_at.isoformat() if version.created_at else None,
            "kind": version.kind,
            "type": "auto_revision",
            "subindex": s.get("key"),
            "score_now": s.get("score"),
            "headline": dr,
            "evidence_ids": s.get("evidence_ids") or [],
        })
    return out


def get_revision_timeline(db: Session, kind: str, limit: int = 20) -> list[dict]:
    """Хронология значимых событий барометра kind, самые свежие первыми.
    limit — по ИТОГОВЫМ событиям (не по версиям — одна auto-версия может дать
    несколько событий, по одному на сдвинутый субиндекс)."""
    rows = (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == kind, BarometerVersion.status == "published")
            .order_by(BarometerVersion.created_at.desc())
            .limit(max(limit * 3, 30)).all())
    events: list[dict] = []
    for v in rows:
        if v.source == "expert":
            as_of = (v.payload or {}).get("as_of")
            events.append({
                "occurred_at": v.created_at.isoformat() if v.created_at else None,
                "kind": v.kind,
                "type": "expert_calibration",
                "subindex": None,
                "headline": f"Экспертная перекалибровка {_KIND_LABEL.get(kind, kind)}"
                            + (f" (якорь на {as_of})" if as_of else ""),
                "evidence_ids": [],
            })
        else:
            events.extend(_subindex_events(v))
        if len(events) >= limit:
            break
    return events[:limit]


def format_timeline_for_prompt(events: list[dict]) -> str:
    """Хронология → компактный текст для промпта LLM (ревизор/субагент), не JSON —
    агенту нужно ЧИТАТЬ трек-рекорд, не парсить его."""
    if not events:
        return "(истории предыдущих ревизий пока нет — это первый содержательный прогон.)"
    lines = []
    for e in events:
        date_str = (e["occurred_at"] or "")[:10]
        if e["type"] == "expert_calibration":
            lines.append(f"- {date_str}: {e['headline']}")
        else:
            lines.append(f"- {date_str} [{e['subindex']}]: {e['headline']}")
    return "\n".join(lines)
