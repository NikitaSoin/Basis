"""Контрольные вопросы владельца — еженедельный экзамен агентской системы.

🔴 ЗАЧЕМ (владелец, 2026-09-13): «я пытаюсь воссоздать реального старшего аналитика,
уровня первого лица — агент умеет серьёзно анализировать все системные взаимосвязи и
понимать, куда всё движется. Когда я задаю такие вопросы — задача проверить, насколько
мы к этой цели приблизились, как её достичь и чего не хватает». Вечерняя сборка отвечает
на вопросы МЕТОДИЧКИ по фиксированной схеме; вопросы владельца — произвольные и
системные. Здесь они становятся ПОСТОЯННЫМ ТЕСТОМ: тот же список раз в неделю, тот же
экзаменатор, счёт в реестре качества — «стало умнее» видно числом, а не ощущением.

Как устроено:
  1. вопросы — config/analyst_probe_questions.json (id, контур, текст); добавляются без кода;
  2. на каждый вопрос — аналитик нужного контура (тот же analyst.run, что в сводках: все
     методички, поиск по потоку, conflict_data, прошлые версии, веб с потолком) получает
     ОПУБЛИКОВАННЫЕ сводки трёх контуров и собранные данные по очагам и отвечает как
     советник: ответ прозой, ключевые суждения со статусом Ф/Д/В/Г, вероятности,
     пробелы, источники;
  3. экзаменатор (другая роль, без веба) оценивает ответ по рубрике 0–5 по шести
     критериям и выписывает, чего не хватает до уровня старшего аналитика и что неверно;
  4. итог — версия kind="probe" (история сохраняется, читается витриной и владельцем:
     /api/market/probe-questions?format=md) + QualityRun pipeline="probe".

🔴 Честно про силу судьи — как у проверяющего: обе роли DeepSeek, независимость от роли и
рубрики, не от модели. Экзамен меряет ДИНАМИКУ (стало ли лучше при том же судье), а не
абсолютную истину.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, llm

logger = logging.getLogger(__name__)

KIND = "probe"
CHECKS_VERSION = "probe-1.0"
_CFG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "config", "analyst_probe_questions.json")
CONTOURS = ("geo", "macro", "inst_state")
_CONTOUR_RU = {"geo": "геополитика", "macro": "экономика", "inst_state": "институты"}

# Рубрика экзаменатора: 0–5 по каждому критерию
RUBRIC: dict[str, str] = {
    "systemic": "системность — все стороны и внешние игроки, их интересы и ограничения, связи с соседними "
                "контурами (геополитика ↔ экономика ↔ институты), а не один срез",
    "mechanisms": "механизмы — как именно событие доходит до результата, шаг за шагом; не «риски растут»",
    "evidence": "доказательность — даты, числа, источники; факт / оценка / гипотеза размечены; числа не выдуманы",
    "forecast": "прогноз — направление и темп, вероятности с основанием, наиболее вероятное отдельно от наиболее "
                "опасного, пусковые условия и что наблюдать",
    "honesty": "честность — пробелы названы прямо, видно, что искал; нет заполнения общими словами",
    "language": "язык — понятно человеку без образования в теме, конкретно, без жаргона и эпитетов",
}
MAX_TOTAL = 5 * len(RUBRIC)


def load_questions() -> list[dict]:
    with open(_CFG, encoding="utf-8") as f:
        qs = json.load(f).get("questions") or []
    return [q for q in qs if q.get("id") and q.get("question") and q.get("contour") in CONTOURS]


# ─────────────────────────── контекст для аналитика ───────────────────────────

def _pick(d: dict | None, keys: tuple[str, ...]) -> dict:
    return {k: d.get(k) for k in keys if isinstance(d, dict) and d.get(k) is not None}


def states_context(db: Session) -> str:
    """Опубликованные сводки трёх контуров — сжато: вердикты, сценарии, situation."""
    parts = []
    geo = barometer_store.current_row(db, "geo")
    if geo and geo.payload:
        p = geo.payload
        regions = {k: _pick(v, ("label", "summary", "direction", "barometer", "scenarios", "situation"))
                   for k, v in (p.get("regions") or {}).items() if isinstance(v, dict)}
        parts.append("СВОДКА ГЕОПОЛИТИКИ (опубликована, as_of " + str(p.get("as_of")) + "):\n"
                     + json.dumps({**_pick(p, ("summary", "scenario", "watchlist_30d")), "regions": regions},
                                  ensure_ascii=False, default=str)[:16_000])
    macro = barometer_store.current_row(db, "macro")
    if macro and macro.payload:
        p = macro.payload
        parts.append("СОСТОЯНИЕ ЭКОНОМИКИ (опубликовано, as_of " + str(p.get("as_of")) + "):\n"
                     + json.dumps(_pick(p, ("summary", "diagnosis", "forecast", "situation", "revision_triggers")),
                                  ensure_ascii=False, default=str)[:12_000])
    inst = barometer_store.current_row(db, "inst_state")
    if inst and inst.payload:
        p = inst.payload
        parts.append("ИНСТИТУЦИОНАЛЬНЫЙ СНИМОК (опубликован, as_of " + str(p.get("as_of")) + "):\n"
                     + json.dumps(_pick(p, ("summary", "verdict", "forecast_card", "situation", "drift_file")),
                                  ensure_ascii=False, default=str)[:12_000])
    return "\n\n".join(parts) if parts else "ОПУБЛИКОВАННЫХ СВОДОК НЕТ — отвечай по потоку и вебу, так и скажи."


def _conflict_text(db: Session) -> str:
    try:
        from app.services.feed_tools import conflict_brief_text
        return conflict_brief_text(db, days=56)
    except Exception as e:  # noqa: BLE001
        return f"СОБРАННЫЕ ДАННЫЕ ПО ОЧАГАМ: недоступны ({type(e).__name__})"


def _feed_tools():
    try:
        from app.services.feed_tools import FEED_TOOLS_SCHEMA, execute
        return list(FEED_TOOLS_SCHEMA), execute
    except ImportError:  # pragma: no cover
        return [], (lambda *_: None)


def _analyst_system(contour: str) -> str:
    try:
        from app.services.handoffs import SENIOR_MANDATE, MANDATES
        mandate = SENIOR_MANDATE + MANDATES.get(contour, "")
    except Exception:  # noqa: BLE001
        mandate = ""
    return (
        f"Ты — старший аналитик Basis по контуру «{_CONTOUR_RU.get(contour, contour)}» (независимая "
        "аналитика для частного инвестора в РФ). Владелец платформы задаёт тебе вопрос как советнику: "
        "ему нужен не пересказ ленты, а системный разбор — что происходит на самом деле, кто участники "
        "и чего хотят, куда движется, что это значит для экономики и рынка, чего ты не знаешь. "
        "Тебе даны опубликованные сводки трёх контуров, собранные данные по очагам, поиск по потоку "
        "платформы (search_feed, conflict_data, прошлые версии сводок), полка методичек и веб. "
        "Сначала наш архив, потом веб; числа — только с источником; чего не нашёл — так и пиши.\n"
        + mandate +
        "\n\nЮридические рамки: нейтральный тон, РФ-топонимика («перешёл под контроль», не «оккупирован»), "
        "никаких «купить/продать/рекомендуем», источники из серой зоны не называть.\n"
        "🔴 ЯЗЫК: обычные слова, конкретные даты и числа, без жаргона и эпитетов; поймёт человек без "
        "образования в теме.\n\n"
        "ФОРМАТ (строго JSON): {\n"
        "  \"answer\": \"<развёрнутый ответ владельцу, 500–1000 слов, абзацами; сначала главный вывод, "
        "потом разбор по пунктам вопроса, в конце — куда движется и что наблюдать>\",\n"
        "  \"key_judgements\": [ {\"claim\", \"status\": \"Ф|Д|В|Г\", \"evidence\": \"<дата, число, источник>\"} ],\n"
        "  \"probabilities\": [ {\"outcome\", \"p\": <0..1>, \"horizon\", \"basis\"} ],\n"
        "  \"mechanisms\": [ \"<событие → звено → звено → результат для экономики/рынка>\" ],\n"
        "  \"gaps\": [ {\"gap\", \"why_it_matters\", \"what_i_did\"} ],\n"
        "  \"sources\": [..], \"methodology_used\": [..]\n}"
    )


def ask(db: Session, q: dict, states_txt: str, conflict_txt: str, notes: list[str] | None = None) -> dict | None:
    from app.services import analyst
    try:
        from app.services.handoffs import ALL_SHELF
    except Exception:  # noqa: BLE001
        ALL_SHELF = ["code"]
    tools, executor = _feed_tools()
    task = ("ВОПРОС ВЛАДЕЛЬЦА:\n" + q["question"]
            + "\n\n" + states_txt
            + "\n\n" + conflict_txt
            + f"\n\nСегодня: {date.today().isoformat()}.")
    return analyst.run(db, system=_analyst_system(q["contour"]), task=task, shelf_docs=ALL_SHELF,
                       extra_tools=tools, extra_executor=executor,
                       max_steps=12, budget=1_500_000, final_max_tokens=16_000, web_call_cap=8,
                       final_instruction="Верни JSON строго по формату из роли: answer, key_judgements, "
                                         "probabilities, mechanisms, gaps, sources, methodology_used.",
                       label=f"probe_{q['id']}", notes=notes)


# ─────────────────────────── экзаменатор ───────────────────────────

def _judge_system() -> str:
    rub = "\n".join(f"  • {k} — {v}" for k, v in RUBRIC.items())
    return (
        "Ты — экзаменатор Basis. Перед тобой вопрос владельца платформы и ответ старшего аналитика. "
        "Твоя единственная задача — оценить ответ по рубрике и сказать, чего не хватает до уровня "
        "старшего аналитика (советника первого лица). Ты не отвечаешь на вопрос сам и не переписываешь "
        "ответ. Оценка 0–5 по каждому критерию (5 — уровень сильного старшего аналитика, 3 — "
        "добросовестный обзор без глубины, 1 — общие слова, 0 — критерий не выполнен):\n" + rub +
        "\n\nПроверяй придирчиво: числа без источника, гипотезы под видом фактов, «все стороны» без "
        "интересов и ограничений, прогноз без вероятностей и пусковых условий, пробелы не названы. "
        "Не завышай за объём. Если видишь фактическую ошибку или выдуманное число — в wrong.\n\n"
        "ФОРМАТ (строго JSON): {\"scores\": {" + ", ".join(f"\"{k}\": <0..5>" for k in RUBRIC) + "}, "
        "\"missing\": [\"<чего не хватает, конкретно>\", ...], \"wrong\": [\"<что неверно или выдумано>\", ...], "
        "\"verdict\": \"<одна фраза>\"}"
    )


def judge(db: Session, q: dict, answer: dict, notes: list[str] | None = None) -> dict | None:
    from app.services import analyst
    tools, executor = _feed_tools()
    task = ("ВОПРОС:\n" + q["question"] + "\n\nОТВЕТ АНАЛИТИКА:\n"
            + json.dumps(answer, ensure_ascii=False, default=str)[:40_000]
            + f"\n\nСегодня: {date.today().isoformat()}.")
    return analyst.run(db, system=_judge_system(), task=task, shelf_docs=["code"],
                       extra_tools=tools, extra_executor=executor,
                       max_steps=5, budget=400_000, final_max_tokens=6_000, web_call_cap=0,
                       final_instruction="Верни JSON с scores, missing, wrong, verdict.",
                       label=f"probe_judge_{q['id']}", notes=notes)


def _clip(x) -> int:
    try:
        return max(0, min(5, int(round(float(x)))))
    except (TypeError, ValueError):
        return 0


def aggregate(items: list[dict]) -> dict:
    """Итог по всем вопросам: сумма баллов по рубрике на вопрос, средняя, доля от максимума."""
    per: dict[str, dict] = {}
    totals: list[int] = []
    for it in items:
        j = it.get("judge") or {}
        scores = {k: _clip((j.get("scores") or {}).get(k)) for k in RUBRIC}
        total = sum(scores.values()) if it.get("answer") and j.get("scores") else None
        per[it["id"]] = {"total": total, "scores": scores if total is not None else None,
                         "answered": bool(it.get("answer")), "judged": bool(j.get("scores"))}
        if total is not None:
            totals.append(total)
    avg = (sum(totals) / len(totals)) if totals else None
    return {"questions": len(items), "answered": sum(1 for it in items if it.get("answer")),
            "judged": len(totals), "avg_total": round(avg, 2) if avg is not None else None,
            "max_total": MAX_TOTAL, "pct": round(avg / MAX_TOTAL, 3) if avg is not None else None,
            "per_question": per}


# ─────────────────────────── прогон ───────────────────────────

def run(db: Session, only: list[str] | None = None) -> BarometerVersion:
    qs = load_questions()
    if only:
        qs = [q for q in qs if q["id"] in set(only)]
    states_txt = states_context(db)
    conflict_txt = _conflict_text(db)
    try:
        from app.services.barometer_daily import compliance_ok
    except Exception:  # noqa: BLE001
        compliance_ok = lambda _p: (True, None)   # noqa: E731
    items: list[dict] = []
    for q in qs:
        diag: list[str] = []
        item = {"id": q["id"], "contour": q["contour"], "question": q["question"], "answer": None,
                "judge": None, "notes": diag}
        try:
            ans = ask(db, q, states_txt, conflict_txt, notes=diag)
        except Exception as e:  # noqa: BLE001
            logger.exception("probe[%s]: %s", q["id"], e); ans = None
            diag.append(f"аналитик упал: {type(e).__name__}: {e}")
        if isinstance(ans, dict) and ans.get("answer"):
            ok, why = compliance_ok(ans)
            if not ok:
                # ответ хранится, но помечен: витрина и md его не показывают
                item["compliance_blocked"] = why
            item["answer"] = ans
            try:
                item["judge"] = judge(db, q, ans, notes=diag)
            except Exception as e:  # noqa: BLE001
                logger.exception("probe judge[%s]: %s", q["id"], e)
                diag.append(f"экзаменатор упал: {type(e).__name__}: {e}")
        else:
            diag.append("ответа нет")
        logger.info("probe[%s]: ответ %s, оценка %s", q["id"], bool(item["answer"]),
                    ((item.get("judge") or {}).get("scores")))
        items.append(item)
    payload = {"as_of": date.today().isoformat(), "checks_version": CHECKS_VERSION, "rubric": RUBRIC,
               "items": items, "summary": aggregate(items)}
    row = BarometerVersion(kind=KIND, source="auto", status="published", payload=payload,
                           trigger_reason="контрольные вопросы владельца",
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    _record_quality(db, payload)
    logger.info("probe: версия #%d, %s", row.id, payload["summary"])
    return row


def _record_quality(db: Session, payload: dict) -> None:
    try:
        from app.models.quality_run import QualityFinding, QualityRun
    except Exception:  # noqa: BLE001
        return
    s = payload["summary"]
    try:
        run_row = QualityRun(pipeline="probe", checks_version=CHECKS_VERSION,
                             started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
                             subjects=s["questions"], coverage=(s["judged"] / s["questions"]) if s["questions"] else 0,
                             score=s["pct"], soft_rate=None, valid=s["judged"] >= 3,
                             invalid_reason=None if s["judged"] >= 3 else "оценено меньше трёх вопросов",
                             per_check=s["per_question"], triggered_by="probe_questions",
                             note="контрольные вопросы владельца: средний балл по рубрике 0–30")
        db.add(run_row); db.flush()
        for it in payload["items"]:
            j = it.get("judge") or {}
            for m in (j.get("missing") or [])[:8]:
                db.add(QualityFinding(run_id=run_row.id, check_id=f"probe.{it['id']}"[:60], subject=it["contour"],
                                      severity="soft", message=str(m)[:1000], evidence={"kind": "missing"}))
            for w in (j.get("wrong") or [])[:8]:
                db.add(QualityFinding(run_id=run_row.id, check_id=f"probe.{it['id']}"[:60], subject=it["contour"],
                                      severity="hard", message=str(w)[:1000], evidence={"kind": "wrong"}))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback(); logger.warning("probe: реестр качества не записан (%s)", e)


def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)


def history(db: Session, limit: int = 12) -> list[dict]:
    rows = (db.query(BarometerVersion).filter(BarometerVersion.kind == KIND, BarometerVersion.status == "published")
            .order_by(BarometerVersion.created_at.desc()).limit(limit).all())
    return [{"version_id": r.id, "as_of": (r.payload or {}).get("as_of"),
             **{k: (r.payload or {}).get("summary", {}).get(k) for k in ("avg_total", "pct", "judged")}}
            for r in rows]


# ─────────────────────────── чтение владельцем ───────────────────────────

def render_md(payload: dict) -> str:
    s = payload.get("summary") or {}
    out = [f"# Контрольные вопросы владельца — {payload.get('as_of')}",
           f"Средний балл: **{s.get('avg_total')} из {s.get('max_total')}** "
           f"(оценено {s.get('judged')} из {s.get('questions')}). Рубрика: " + ", ".join(RUBRIC.keys()) + ".", ""]
    for it in payload.get("items") or []:
        j = it.get("judge") or {}
        pq = (s.get("per_question") or {}).get(it["id"]) or {}
        out.append(f"## {it['id']} · {_CONTOUR_RU.get(it['contour'], it['contour'])} · балл {pq.get('total')}")
        out.append(f"**Вопрос.** {it['question']}")
        out.append("")
        ans = it.get("answer") or {}
        if it.get("compliance_blocked"):
            out.append(f"_Ответ скрыт автопроверкой: {it['compliance_blocked']}_")
        elif ans.get("answer"):
            out.append(str(ans["answer"]))
            if ans.get("probabilities"):
                out.append("")
                out.append("**Вероятности.** " + "; ".join(
                    f"{p.get('outcome')}: {p.get('p')} ({p.get('horizon')})" for p in ans["probabilities"]
                    if isinstance(p, dict)))
            if ans.get("gaps"):
                out.append("**Пробелы.** " + "; ".join(
                    str(g.get("gap")) if isinstance(g, dict) else str(g) for g in ans["gaps"]))
        else:
            out.append("_Ответа нет: " + "; ".join(it.get("notes") or []) + "_")
        if j:
            out.append("")
            out.append(f"**Экзаменатор.** {j.get('verdict')} Баллы: " + ", ".join(
                f"{k} {v}" for k, v in ((pq.get("scores") or {}).items())) + ".")
            if j.get("missing"):
                out.append("Чего не хватает: " + "; ".join(str(m) for m in j["missing"]))
            if j.get("wrong"):
                out.append("Неверно/выдумано: " + "; ".join(str(w) for w in j["wrong"]))
        out.append("")
    return "\n".join(out)
