"""Задание финала вечерней сборки обязано содержать ВСЕ входы, а не один черновик.

Регрессия 2026-09-13: тернарный оператор `X if draft else "" + всё_остальное`
оставлял в задании только черновик (приоритет if/else ниже, чем у +).
Проверяем по исходнику: конструкция с draft_txt, а ternary-ловушки нет.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "services"


def _src(name):
    return (SRC / name).read_text(encoding="utf-8")


def test_no_ternary_swallowing_task():
    for name in ("inst_state.py", "macro_state.py"):
        s = _src(name)
        assert not re.search(r'if draft else ""\s*\n\s*\+ peers_full', s), name
        assert "task = (draft_txt" in s, name
        assert "ЗАМЕЧАНИЯ АВТОМАТИЧЕСКОЙ ПРОВЕРКИ К ЧЕРНОВИКУ" in s, name


def test_draft_not_rejected_by_compliance():
    for name in ("inst_state.py", "macro_state.py", "barometer_daily.py"):
        s = _src(name)
        assert "КОМПЛАЕНС (черновик)" in s, name
