"""Прогон набора проверок и запись в реестр.

Одно число качества — недостаточно. У прогона их ТРИ, и они не взаимозаменяемы:

  coverage  — доля субъектов, где проверка реально отработала (не skip);
  score     — доля субъектов без ГРУБЫХ находок;
  soft_rate — доля субъектов с мягкими находками.

🔴 При coverage ниже пола прогон помечается invalid, и score не публикуется:
зелёное число при пустой выборке хуже красного — оно ещё и успокаивает.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.services.quality.contract import Check, CheckOutcome, Severity, Status
from app.services.quality.pipelines import get as get_pipeline

COVERAGE_FLOOR = 0.5


@dataclass
class RunResult:
    pipeline: str
    checks_version: str
    started_at: datetime
    subjects: int = 0
    coverage: float = 0.0
    score: float = 0.0
    soft_rate: float = 0.0
    valid: bool = True
    invalid_reason: str = ""
    per_check: dict[str, dict[str, Any]] = field(default_factory=dict)
    outcomes: list[CheckOutcome] = field(default_factory=list)
    golden: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        return {"pipeline": self.pipeline, "checks_version": self.checks_version,
                "subjects": self.subjects, "coverage": round(self.coverage, 4),
                "score": round(self.score, 4), "soft_rate": round(self.soft_rate, 4),
                "valid": self.valid, "invalid_reason": self.invalid_reason,
                "per_check": self.per_check,
                "golden": {k: v for k, v in (self.golden or {}).items() if k != "results"}}


def list_subjects(pipeline: str = "financials", limit: int | None = None,
                  only: list[str] | None = None) -> list[str]:
    items = get_pipeline(pipeline).subjects()
    if only:
        want = {o.upper() for o in only}
        items = [i for i in items if i.upper() in want]
    return items[:limit] if limit else items


def run(pipeline: str = "financials", *, limit: int | None = None,
        only: list[str] | None = None, checks: list[Check] | None = None,
        today: date | None = None) -> RunResult:
    pl = get_pipeline(pipeline)
    checks = checks or pl.checks
    today = today or date.today()
    res = RunResult(pipeline=pipeline, checks_version=pl.checks_version,
                    started_at=datetime.now(timezone.utc))

    subjects = list_subjects(pipeline, limit=limit, only=only)
    stats = {c.check_id: {"title": c.title, "severity": c.severity.value,
                          "ok": 0, "fail": 0, "skip": 0} for c in checks}
    hard_hit: set[str] = set()
    soft_hit: set[str] = set()
    unreadable = 0

    for subject in subjects:
        payload = pl.payload(subject, today)
        if payload is None:
            unreadable += 1
            hard_hit.add(subject)
            continue
        for check in checks:
            for outcome in check.run(subject, payload):
                res.outcomes.append(outcome)
                stats[check.check_id][outcome.status.value] += 1
                if outcome.status is Status.FAIL:
                    (hard_hit if check.severity is Severity.HARD else soft_hit).add(subject)

    res.subjects = len(subjects)
    if not subjects:
        res.valid, res.invalid_reason = False, "не найдено ни одного субъекта"
        return res

    covered_total = 0
    for check in checks:
        s = stats[check.check_id]
        ran = s["ok"] + s["fail"]
        s["coverage"] = round(ran / len(subjects), 4)
        s["fail_rate"] = round(s["fail"] / ran, 4) if ran else None
        covered_total += s["coverage"]
    res.per_check = stats
    res.coverage = covered_total / len(checks)
    res.score = 1 - len(hard_hit) / len(subjects)
    res.soft_rate = len(soft_hit - hard_hit) / len(subjects)
    if unreadable:
        res.per_check["_unreadable_subjects"] = {"count": unreadable}

    if res.coverage < COVERAGE_FLOOR:
        res.valid = False
        res.invalid_reason = (f"покрытие {res.coverage:.0%} ниже пола {COVERAGE_FLOOR:.0%} — "
                              f"score не публикуется")
    return res


# ─────────────────────────── запись в реестр ───────────────────────────

def persist(res: RunResult, *, triggered_by: str = "cli", note: str = "",
            max_findings: int = 500) -> int | None:
    """Пишет прогон в БД. Возвращает id прогона или None, если БД недоступна.

    Недоступность БД — не повод потерять прогон: JSON-артефакт пишется всегда
    (см. write_artifact), реестр — сверх того.
    """
    try:
        from app.db.session import SessionLocal
        from app.models.quality_run import QualityFinding, QualityRun
    except Exception:
        return None
    db = None
    try:
        db = SessionLocal()
        row = QualityRun(
            pipeline=res.pipeline, checks_version=res.checks_version,
            started_at=res.started_at, finished_at=datetime.now(timezone.utc),
            subjects=res.subjects, coverage=res.coverage, score=res.score,
            soft_rate=res.soft_rate, valid=res.valid, invalid_reason=res.invalid_reason or None,
            golden_total=(res.golden or {}).get("total"),
            golden_passed=(res.golden or {}).get("passed"),
            per_check=res.per_check, triggered_by=triggered_by, note=note or None,
        )
        db.add(row)
        db.flush()
        failed = [o for o in res.outcomes if o.status is Status.FAIL][:max_findings]
        for o in failed:
            db.add(QualityFinding(run_id=row.id, check_id=o.check_id, subject=o.subject,
                                  severity=o.severity.value, message=o.message[:1000],
                                  evidence=o.evidence))
        db.commit()
        return row.id
    except Exception:
        if db is not None:
            db.rollback()
        return None
    finally:
        if db is not None:
            db.close()


def write_artifact(res: RunResult, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = res.started_at.strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{res.pipeline}-{stamp}.json"
    path.write_text(json.dumps({
        "summary": res.summary(),
        "golden": res.golden,
        "findings": [o.as_dict() for o in res.outcomes if o.status is Status.FAIL],
        "skips": [o.as_dict() for o in res.outcomes if o.status is Status.SKIP][:200],
    }, ensure_ascii=False, indent=1))
    return path
