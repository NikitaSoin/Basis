"""Вечерняя сборка трёх сводок — ОДНИМ прогоном, публикация в конце.

🔴 ЗАЧЕМ (владелец, 2026-09-13): «вначале геополитик, макроэкономист,
институционалист формируют сводки, отдают всё нужное друг другу, задают вопросы,
дальше сверка, проверяющий — и только после этого публикация. Не отдаём на завтра
комментарии, а заранее всё сводим вместе».

Порядок (всё в один вечер):
  1. ЧЕРНОВИКИ  — гео → макро → институты (каждый следующий уже видит черновики
                  предыдущих; статус draft, витрина их не показывает);
  2. ОПРОС      — каждый читает черновики соседей по своей методичке, вопросы;
  3. СВЕРКА     — противоречия и оборванные цепочки между черновиками;
  4. ПРОВЕРКА   — проверяющий по чек-листам методичек и кодексу — по черновикам;
  5. ФИНАЛ      — каждый дорабатывает СВОЙ черновик: отвечает на вопросы, снимает
                  противоречия, исправляет замечания, разбирает цепочки через два
                  ребра и обратные петли (полные черновики соседей + все методички)
                  → проверка перед публикацией → published;
  6. ИТОГ       — проверяющий по опубликованному: реестр качества + уроки.

Один крон 21:50 на всю цепочку — порядок гарантирован; черновики хранятся
версиями и открываются инструментом read_state_version. Любой шаг падает —
цепочка продолжается: лучше опубликовать без опроса, чем не опубликовать ничего;
пропущенное — в отчёте.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _safe(label: str, fn, report: dict):
    t0 = time.time()
    try:
        out = fn()
        summary = out if isinstance(out, (dict, str, int)) or out is None else \
            {"id": getattr(out, "id", None), "status": getattr(out, "status", None),
             "gate_notes": getattr(out, "gate_notes", None)}
        report[label] = {"ok": True, "минут": round((time.time() - t0) / 60, 1), "result": summary}
    except Exception as e:  # noqa: BLE001
        logger.exception("evening[%s]: %s", label, e)
        report[label] = {"ok": False, "минут": round((time.time() - t0) / 60, 1),
                         "error": f"{type(e).__name__}: {e}"}


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def plan_for(today: date | None = None) -> dict:
    """Расписание по контурам (владелец 2026-09-14: «на самых мощных моделях, просто реже —
    экономику через день, институциональную среду раз в неделю по выходным»). Геополитика —
    ежедневно. Переключатели env: EVENING_MACRO_EVERY_DAYS (по умолчанию 2),
    EVENING_INST_WEEKDAYS (по умолчанию «sat»), EVENING_FORCE_ALL=1 — всё каждый день."""
    today = today or date.today()
    if os.environ.get("EVENING_FORCE_ALL") == "1":
        return {"geo": True, "macro": True, "inst": True, "why": "EVENING_FORCE_ALL=1"}
    try:
        every = max(1, int(os.environ.get("EVENING_MACRO_EVERY_DAYS", "2") or 2))
    except ValueError:
        every = 2
    inst_days = {d.strip().lower()[:3] for d in (os.environ.get("EVENING_INST_WEEKDAYS", "sat") or "sat").split(",")}
    wd = _WEEKDAYS[today.weekday()]
    return {"geo": True, "macro": today.toordinal() % every == 0, "inst": wd in inst_days,
            "why": f"экономика каждые {every} дн., институты по {', '.join(sorted(inst_days))}; сегодня {wd}"}


def run(db: Session) -> dict:
    from app.services import barometer_daily, macro_state, inst_state, cross_review, consistency_check, critic
    report: dict = {}
    plan = plan_for()
    report["_plan"] = plan
    skipped = {"ok": True, "минут": 0, "result": "пропущено по расписанию: " + plan["why"]}
    _safe("1_draft_geo", lambda: barometer_daily.rebuild(db, mode="draft"), report)
    if plan["macro"]:
        _safe("1_draft_macro", lambda: macro_state.rebuild(db, mode="draft"), report)
    else:
        report["1_draft_macro"] = skipped
    if plan["inst"]:
        _safe("1_draft_inst", lambda: inst_state.rebuild(db, mode="draft"), report)
    else:
        report["1_draft_inst"] = skipped
    _safe("2_cross_review", lambda: cross_review.run(db), report)
    _safe("3_consistency", lambda: consistency_check.run(db), report)
    _safe("4_critic_draft", lambda: critic.run_all(db, stage="draft", record=False), report)
    _safe("5_final_geo", lambda: barometer_daily.rebuild(db, mode="final"), report)
    if plan["macro"]:
        _safe("5_final_macro", lambda: macro_state.rebuild(db, mode="final"), report)
    else:
        report["5_final_macro"] = skipped
    if plan["inst"]:
        _safe("5_final_inst", lambda: inst_state.rebuild(db, mode="final"), report)
    else:
        report["5_final_inst"] = skipped
    _safe("6_critic_final", lambda: critic.run_all(db, stage="final", record=True), report)
    report["_summary"] = {k: ("✓" if v.get("ok") else "✕") + f" {v.get('минут')}м" for k, v in report.items() if k != "_plan"}
    logger.info("evening pipeline: %s", report["_summary"])
    return report
