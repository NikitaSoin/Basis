"""Реестр пайплайнов измерения.

Пайплайн = что проверяем (субъекты) + чем (набор проверок) + как достать данные.
Раннер, эталонный стенд и CLI работают через этот реестр и ничего не знают про
конкретные финансы или снапшоты.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from app.services.quality import checks_financials as fin
from app.services.quality import checks_snapshots as snap
from app.services.quality.contract import Check


@dataclass(frozen=True)
class Pipeline:
    name: str
    title: str
    checks: list[Check]
    checks_version: str
    subjects: Callable[[], list[str]]
    payload: Callable[[str, date], dict | None]


def _fin_subjects() -> list[str]:
    return sorted(p.parent.name for p in fin.COMPANIES.glob("*/financials.json"))


def _fin_payload(subject: str, today: date) -> dict | None:
    import json
    path = fin.COMPANIES / subject / "financials.json"
    try:
        card = json.loads(path.read_text())
    except Exception:
        return None
    return {"card": card, "extracted": fin._load_extracted(subject), "today_year": today.year}


PIPELINES: dict[str, Pipeline] = {
    "financials": Pipeline("financials", "Финансы карточки компании",
                           fin.CHECKS, fin.CHECKS_VERSION, _fin_subjects, _fin_payload),
    "snapshots": Pipeline("snapshots", "Снапшоты данных для SEO-страниц",
                          snap.CHECKS, snap.CHECKS_VERSION, snap.subjects,
                          lambda s, today: snap.payload(s, today)),
}


def get(name: str) -> Pipeline:
    if name not in PIPELINES:
        raise KeyError(f"неизвестный пайплайн «{name}»; есть: {', '.join(PIPELINES)}")
    return PIPELINES[name]
