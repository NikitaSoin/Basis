"""Проверяющий для каждой из трёх сводок — по «типовым ошибкам» методичек и кодексу.

🔴 ЗАЧЕМ (владелец, 2026-09-13, пункт 5). В каждой методичке есть глава «типовые
ошибки» и чек-листы, в кодексе — восемь правил. До сих пор ими проверял только
геополитику red-team-критик; экономику и институты — никто. Здесь один и тот же
проверяющий для всех трёх: читает опубликованную сводку, держит перед глазами
чек-лист ИМЕННО ЭТОГО контура (разделы из методичек по номерам, ниже) и выписывает
нарушения: где, цитата, какое правило, насколько серьёзно, что исправить.

Что делает результат: (1) ложится версией kind="crit_<контур>" и читается
витриной; (2) уходит аналитику в задание на следующую сборку блоком «ЗАМЕЧАНИЯ
ПРОВЕРЯЮЩЕГО» — исправить и отчитаться в critique_resolved; (3) записывается в
реестр качества (quality_runs, pipeline="states") — «стало умнее» становится
числом: доля сводок без критичных нарушений и счёт нарушений по тяжести.

🔴 Честно про силу судьи. В проде обе роли — DeepSeek (правило владельца: прод
только DeepSeek). Независимость проверки здесь не от «более сильной модели», а от
другой роли и жёсткого чек-листа: проверяющий не пишет и не улучшает, только
сверяет с правилом. Это слабее внешнего судьи, но заметно сильнее самопроверки.

Чек-лист в задании — сознательное исключение из правила «методичка не в
промпте»: судья проверяет ПО СПИСКУ, список и есть его инструмент; разделы
короткие (0,5–2,5 тыс. знаков), берутся по номерам и обновляются вместе с
методичкой. Остальное он при желании открывает сам.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, llm, methodology

logger = logging.getLogger(__name__)

# контур → (kind версии критики, разделы чек-листа [(doc_id, раздел)], полка)
CONTOURS: dict[str, dict] = {
    "macro": {
        "kind": "crit_macro", "title": "состояние экономики",
        "checklist": [("code", "Часть 2"), ("code", "0.5"), ("macro_base", "12.4"),
                      ("macro_base", "16.5"), ("inst_macro", "10.3"), ("geo_macro", "11.1")],
        "shelf": ["code", "macro_base", "geo_macro", "inst_macro"],
    },
    "inst_state": {
        "kind": "crit_inst", "title": "институциональный снимок",
        "checklist": [("code", "Часть 2"), ("inst_env", "0.7"), ("inst_env", "9.9"),
                      ("inst_env", "12.4"), ("inst_env", "13.9"), ("macro_inst", "12.2"),
                      ("geo_inst", "8.2")],
        "shelf": ["code", "inst_env", "geo_inst", "macro_inst"],
    },
    "geo": {
        "kind": "crit_geo", "title": "сводка геополитики",
        "checklist": [("code", "Часть 2"), ("geo_base", "11.4"), ("geo_base", "11.6"),
                      ("geo_events", "1.5"), ("geo_events", "2.6"), ("geo_events", "4.6"),
                      ("macro_geo", "11.2"), ("inst_geo", "9.9")],
        "shelf": ["code", "geo_base", "geo_events", "macro_geo", "inst_geo"],
    },
}
SEVERITY = {"критично": 3, "существенно": 2, "мелочь": 1}


def checklist_text(contour: str) -> tuple[str, list[str]]:
    """Тексты разделов чек-листа по номерам + список ненайденных (честно, а не молча)."""
    parts, missing = [], []
    for doc_id, sec in CONTOURS[contour]["checklist"]:
        r = methodology.read_section(doc_id, sec)
        if r.get("error"):
            missing.append(f"{doc_id}:{sec}")
            continue
        parts.append(f"--- [{doc_id} {r.get('раздел')}] {r.get('название')} ---\n{r.get('текст')}")
    return "\n\n".join(parts), missing


def score(violations: list[dict]) -> dict:
    counts = {k: 0 for k in SEVERITY}
    for v in violations:
        s = str(v.get("severity") or "").strip().lower()
        if s in counts:
            counts[s] += 1
    return {"critical": counts["критично"], "major": counts["существенно"], "minor": counts["мелочь"],
            "weighted": sum(SEVERITY[k] * n for k, n in counts.items()),
            "clean": counts["критично"] == 0}


def review(db: Session, contour: str) -> BarometerVersion | None:
    spec = CONTOURS[contour]
    state_row = barometer_store.current_row(db, contour)
    if not state_row or not state_row.payload:
        logger.warning("critic: нет опубликованной сводки %s", contour)
        return None
    checklist, missing = checklist_text(contour)
    system = (
        f"Ты — проверяющий Basis. Перед тобой опубликованная сводка «{spec['title']}» на "
        f"{state_row.payload.get('as_of')}. Твоя единственная задача — сверить её с ЧЕК-ЛИСТОМ "
        "типовых ошибок и правил доказательности (в задании) и выписать нарушения. Ты не пишешь "
        "свою аналитику, не оцениваешь «хорошо/плохо» и не переписываешь текст.\n\n"
        "По каждому нарушению: rule — какое правило и откуда (например «code 0.2 контрфакт», "
        "«И 12.4 п.3»); where — поле/раздел сводки; quote — дословная цитата ≤200 знаков; "
        "severity — критично (вывод построен на нарушении: знак задан заранее, гипотеза выдана "
        "за факт, число без источника в основе диагноза), существенно (нарушение искажает часть "
        "вывода) или мелочь (форма); fix — что именно сделать. Если правило соблюдено — в "
        "passed, одной строкой с примером. Не придумывай нарушений ради счёта: пустой список "
        "при чистой сводке — правильный ответ.\n\n"
        "ФОРМАТ (строго JSON): {\"violations\": [ {\"rule\", \"where\", \"quote\", \"severity\", "
        "\"fix\"} ], \"passed\": [..], \"checklist_gaps\": [<правила чек-листа, которые нельзя "
        "проверить по этой сводке и почему>], \"methodology_used\": [..]}"
    )
    task = ("ЧЕК-ЛИСТ (разделы методичек по номерам):\n" + checklist
            + ("\n\n(не найдены на полке: " + ", ".join(missing) + ")" if missing else "")
            + "\n\nСВОДКА НА ПРОВЕРКУ:\n" + json.dumps(state_row.payload, ensure_ascii=False, default=str)[:80_000]
            + f"\n\nСегодня: {date.today().isoformat()}.")
    from app.services import analyst
    diag: list[str] = []
    out = analyst.run(db, system=system, task=task, shelf_docs=spec["shelf"], max_steps=6,
                      budget=400_000, final_max_tokens=10_000, web_call_cap=0,
                      final_instruction="Верни JSON с violations, passed, checklist_gaps.",
                      label=f"critic_{contour}", notes=diag)
    if not isinstance(out, dict):
        row = BarometerVersion(kind=spec["kind"], source="auto", status="rejected", payload=None,
                               gate_notes=["проверяющий не вернул JSON: " + " | ".join(diag)[:400]],
                               parent_id=state_row.id, trigger_reason="проверка сводки")
        db.add(row); db.commit(); db.refresh(row)
        return row
    violations = [v for v in (out.get("violations") or []) if isinstance(v, dict)]
    payload = {"as_of": date.today().isoformat(), "contour": contour, "state_version_id": state_row.id,
               "state_as_of": state_row.payload.get("as_of"), "violations": violations,
               "passed": out.get("passed") or [], "checklist_gaps": out.get("checklist_gaps") or [],
               "checklist_missing_sections": missing, "score": score(violations),
               "methodology_used": out.get("methodology_used") or []}
    row = BarometerVersion(kind=spec["kind"], source="auto", status="published", payload=payload,
                           parent_id=state_row.id, trigger_reason="проверка сводки",
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("critic[%s]: нарушений %d (критичных %d), версия #%d", contour, len(violations),
                payload["score"]["critical"], row.id)
    return row


def run_all(db: Session) -> dict:
    """Проверить все три сводки и записать итог в реестр качества."""
    results: dict[str, dict] = {}
    for contour in CONTOURS:
        try:
            row = review(db, contour)
            results[contour] = ({"id": row.id, "status": row.status, **((row.payload or {}).get("score") or {})}
                                if row else {"skipped": "нет сводки"})
        except Exception as e:  # noqa: BLE001
            logger.exception("critic[%s]: %s", contour, e)
            results[contour] = {"error": f"{type(e).__name__}: {e}"}
    _record_quality(db, results)
    return results


def _record_quality(db: Session, results: dict) -> None:
    """Реестр качества: одна строка прогона + находка на каждое нарушение."""
    try:
        from app.models.quality_run import QualityFinding, QualityRun
    except Exception:  # noqa: BLE001
        return
    reviewed = {k: v for k, v in results.items() if "id" in v and v.get("status") == "published"}
    if not reviewed:
        return
    subjects = len(CONTOURS)
    clean = sum(1 for v in reviewed.values() if v.get("clean"))
    with_major = sum(1 for v in reviewed.values() if v.get("clean") and (v.get("major") or v.get("minor")))
    run = QualityRun(pipeline="states", checks_version="crit-1.0",
                     started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                     subjects=subjects, coverage=len(reviewed) / subjects, score=clean / subjects,
                     soft_rate=with_major / subjects, valid=len(reviewed) >= 2,
                     invalid_reason=None if len(reviewed) >= 2 else "проверено меньше двух сводок",
                     per_check={k: v for k, v in results.items()}, triggered_by="critic", note="проверка сводок по типовым ошибкам")
    db.add(run); db.flush()
    for contour, v in reviewed.items():
        row = db.get(BarometerVersion, v["id"])
        for viol in ((row.payload or {}).get("violations") or []):
            sev = "hard" if str(viol.get("severity")) == "критично" else "soft"
            db.add(QualityFinding(run_id=run.id, check_id=f"crit.{viol.get('rule', '?')[:50]}", subject=contour,
                                  severity=sev, message=f"{viol.get('where')}: {viol.get('fix')}"[:1000],
                                  evidence={"quote": viol.get("quote"), "severity": viol.get("severity")}))
    db.commit()


def critique_for(db: Session, contour: str) -> list[dict]:
    """Замечания проверяющего к последней сводке контура — для следующей сборки."""
    spec = CONTOURS.get(contour)
    if not spec:
        return []
    row = barometer_store.current_row(db, spec["kind"])
    if not row or not row.payload:
        return []
    return row.payload.get("violations") or []


def current(db: Session, contour: str) -> dict | None:
    spec = CONTOURS.get(contour)
    return barometer_store.get_payload_with_meta(db, spec["kind"]) if spec else None
