"""Перекрёстный опрос: каждый аналитик читает сводку соседа ПО СВОЕЙ методичке
и задаёт ему вопросы.

🔴 ЗАЧЕМ (владелец, 2026-09-13, пункт 3). «Подсветить упущенное» — но с
экспертизой, а не с высоты: экономист, читая институциональный снимок по
макро-методичке, спросит «вы пишете, что ставка не работает из-за льготного
кредита — какая доля кредита льготная и откуда число». Это не критик и не
начальник: вопросы уходят соседу в ЗАДАНИЕ на следующую сборку, и он обязан
ответить в answers_to_peers — с фактом и источником. Пары:
    macro → inst_state, macro → geo, inst_state → macro, inst_state → geo,
    geo → macro, geo → inst_state.
Результат хранится версией kind="cross_review"; сборки читают последнюю.
"""
from __future__ import annotations

import json
import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, handoffs, llm

logger = logging.getLogger(__name__)

KIND = "cross_review"
_ROLE = {
    "macro": ("макроэкономист", ["code", "macro_base", "geo_macro", "inst_macro"]),
    "inst_state": ("институциональный аналитик", ["code", "inst_env", "geo_inst", "macro_inst"]),
    "geo": ("геополитический аналитик", ["code", "geo_base", "macro_geo", "inst_geo"]),
}
_TITLE = {"macro": "состояние экономики", "inst_state": "институциональный снимок",
          "geo": "сводка геополитики"}
MAX_QUESTIONS = 5


def _payloads(db: Session) -> dict[str, dict | None]:
    return {k: (r.payload if (r := barometer_store.current_row(db, k)) and r.payload else None)
            for k in _ROLE}


def _ask(db: Session, reviewer: str, target: str, target_payload: dict) -> list[dict]:
    role, shelf = _ROLE[reviewer]
    from app.services import analyst
    system = (f"Ты — {role} Basis. Перед тобой {_TITLE[target]} твоего коллеги. Прочитай его "
              f"ПО СВОЕЙ методичке и задай до {MAX_QUESTIONS} вопросов, без которых ТВОЙ "
              "следующий вывод будет слабее: где нет числа, где утверждение без источника, "
              "где механизм назван, но не показан, где пропущена передача по контракту "
              "(handoffs) тебе. Не оценивай и не переписывай — спрашивай. Каждый вопрос: "
              "конкретный, с указанием места в сводке, и почему тебе это нужно.\n\n"
              "ФОРМАТ (строго JSON): {\"questions\": [ {\"about\": <поле/раздел сводки>, "
              "\"question\": <вопрос с ожидаемым видом ответа: число, дата, источник>, "
              "\"why_it_matters\": <для какого твоего вывода>} ], \"methodology_used\": [..]}")
    task = (f"СВОДКА КОЛЛЕГИ ({_TITLE[target]}, от {target_payload.get('as_of')}):\n"
            + json.dumps(target_payload, ensure_ascii=False, default=str)[:70_000]
            + f"\n\nСегодня: {date.today().isoformat()}.")
    diag: list[str] = []
    out = analyst.run(db, system=system, task=task, shelf_docs=shelf, max_steps=6,
                      budget=300_000, final_max_tokens=6_000,
                      final_instruction="Верни JSON с questions.", label=f"xq_{reviewer}_to_{target}",
                      notes=diag)
    qs = (out or {}).get("questions") or []
    return [{"from": reviewer, "to": target, **q} for q in qs if isinstance(q, dict)][:MAX_QUESTIONS]


def run(db: Session) -> BarometerVersion | None:
    payloads = _payloads(db)
    present = [k for k, v in payloads.items() if v]
    if len(present) < 2:
        logger.warning("cross_review: сводок меньше двух — опрашивать некого")
        return None
    questions: list[dict] = []
    failures: list[str] = []
    for reviewer in present:
        for target in present:
            if reviewer == target:
                continue
            try:
                questions += _ask(db, reviewer, target, payloads[target])
            except Exception as e:  # noqa: BLE001
                failures.append(f"{reviewer}→{target}: {type(e).__name__}")
    payload = {"as_of": date.today().isoformat(), "questions": questions,
               "pairs": [f"{a}→{b}" for a in present for b in present if a != b],
               "failures": failures,
               "sources": {k: (payloads[k] or {}).get("as_of") for k in present}}
    row = BarometerVersion(kind=KIND, source="auto", status="published" if questions else "rejected",
                           payload=payload, gate_notes=failures or None,
                           trigger_reason="перекрёстный опрос",
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("cross_review: вопросов %d, версия #%d", len(questions), row.id)
    return row


def questions_for(db: Session, target: str) -> list[dict]:
    row = barometer_store.current_row(db, KIND)
    if not row or not row.payload:
        return []
    return [q for q in (row.payload.get("questions") or []) if q.get("to") == target]


def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)
