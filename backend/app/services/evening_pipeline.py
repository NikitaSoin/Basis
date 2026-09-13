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
import time

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


def run(db: Session) -> dict:
    from app.services import barometer_daily, macro_state, inst_state, cross_review, consistency_check, critic
    report: dict = {}
    _safe("1_draft_geo", lambda: barometer_daily.rebuild(db, mode="draft"), report)
    _safe("1_draft_macro", lambda: macro_state.rebuild(db, mode="draft"), report)
    _safe("1_draft_inst", lambda: inst_state.rebuild(db, mode="draft"), report)
    _safe("2_cross_review", lambda: cross_review.run(db), report)
    _safe("3_consistency", lambda: consistency_check.run(db), report)
    _safe("4_critic_draft", lambda: critic.run_all(db, stage="draft", record=False), report)
    _safe("5_final_geo", lambda: barometer_daily.rebuild(db, mode="final"), report)
    _safe("5_final_macro", lambda: macro_state.rebuild(db, mode="final"), report)
    _safe("5_final_inst", lambda: inst_state.rebuild(db, mode="final"), report)
    _safe("6_critic_final", lambda: critic.run_all(db, stage="final", record=True), report)
    report["_summary"] = {k: ("✓" if v.get("ok") else "✕") + f" {v.get('минут')}м" for k, v in report.items()}
    logger.info("evening pipeline: %s", report["_summary"])
    return report
