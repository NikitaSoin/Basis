"""Автогейт выпуска «Оценка ситуации» — проверка КОДОМ перед публикацией.

🔴 ЗАЧЕМ. Гейт написан для пилотного агента по одной компании
(`macro_addendum_agent._gate`), а самый дорогой по доверию артефакт платформы —
макро-выпуск — выходил вообще без проверки. При этом именно на нём мы уже ловили
класс ошибок «модель берёт первое похожее число из прозы» (2026-08-01, инфляционные
ожидания), и промптом он не лечится.

Философия та же, что в «ОТК данных» Макрообзора: проверяет КОД, а не LLM.

🔴 Гейт НЕ роняет выпуск. Пустой экран хуже, чем выпуск с честной пометкой, поэтому:
  - `reject` — только на грубых структурных дефектах (не тот тип, нет обязательных
    блоков): такой срез не публикуется, на витрине остаётся предыдущий;
  - `warn` — публикуем, но проблемы записываются в срез и видны в отладке.

Пороги намеренно мягкие. Слишком строгий гейт, дающий ложные срабатывания, хуже
отсутствия гейта: он либо блокирует нормальные выпуски, либо приучает игнорировать
предупреждения (проверено на себе — первая версия числовой сверки резала предложение
между показателем и его числом и ругалась на верное).
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# Конституция платформы: не брокер, никаких торговых сигналов.
_FORBIDDEN = re.compile(
    r"\b(куп(и|ить|ай|аем)|прода(й|ть|вай|ём|ем)|шорт(и|ить)?|лонг(уй|овать)?|"
    r"рекомендуем\s+(купить|продать)|таргет\s+цен)", re.I)

# Обязательные блоки выпуска (методичка v3, Часть 19.3). Без них выпуск не выпуск.
_REQUIRED = ("headline", "forecasts", "sectors")

# Пять переменных прогнозного блока (Часть 14) — ядро ценности.
_FORECAST_VARS = ("ставка", "инфляц", "курс", "ввп", "безработиц")


def check_release(sections: dict, snapshot: dict) -> tuple[str, list[str]]:
    """Вернуть ('ok'|'warn'|'reject', заметки)."""
    notes: list[str] = []
    if not isinstance(sections, dict):
        return "reject", ["not_a_dict"]

    for field in _REQUIRED:
        if not sections.get(field):
            notes.append(f"missing:{field}")
    if [n for n in notes if n.startswith("missing:")]:
        return "reject", notes

    blob = json.dumps(sections, ensure_ascii=False)
    if _FORBIDDEN.search(blob):
        notes.append("forbidden_words")

    notes += _check_forecasts(sections)
    notes += _check_numbers_vs_facts(blob, snapshot)
    notes += _check_tickers(sections, snapshot)
    notes += _check_epistemics(sections)

    return ("warn" if notes else "ok"), notes


def _check_forecasts(sections: dict) -> list[str]:
    """Часть 14: пять переменных, у каждой центр И диапазон, драйвер, контраргумент."""
    out: list[str] = []
    fc = sections.get("forecasts")
    if not isinstance(fc, list) or not fc:
        return ["forecasts_empty"]
    covered = set()
    for i, f in enumerate(fc):
        if not isinstance(f, dict):
            out.append(f"forecast_{i}_not_dict")
            continue
        var = str(f.get("variable") or "").lower()
        for key in _FORECAST_VARS:
            if key in var:
                covered.add(key)
        if not f.get("center"):
            out.append(f"forecast_{i}_no_center")     # диапазон без центра запрещён
        if not f.get("range"):
            out.append(f"forecast_{i}_no_range")      # точка без диапазона запрещена
        if not f.get("against"):
            out.append(f"forecast_{i}_no_counterargument")
    missing = [v for v in _FORECAST_VARS if v not in covered]
    if missing:
        out.append("forecast_vars_missing:" + ",".join(missing))
    return out


def _check_numbers_vs_facts(blob: str, snapshot: dict) -> list[str]:
    """Числа рядом с показателем должны совпадать с key_facts.

    Ровно та ошибка, ради которой гейт и нужен: модель берёт число из прозы записки и
    выдаёт за текущее значение показателя. Сверяем ТОЛЬКО окрестность факта (0.3x–3x),
    иначе прогнозные величины в том же предложении дают ложные срабатывания.
    """
    out: list[str] = []
    facts = {(i.get("code"), i.get("metric")): i for i in snapshot.get("indicators") or []}
    checks = (
        ("key_rate", "level", r"ключев\w*\s+ставк\w*[^0-9]{0,30}(\d{1,2}[.,]?\d{0,2})\s*%", 0.03),
        ("inflation_expectations", "level",
         r"инфляционн\w*\s+ожидани\w*[^0-9]{0,30}(\d{1,2}[.,]?\d{0,2})\s*%", 0.05),
    )
    for code, metric, pattern, tol in checks:
        ind = facts.get((code, metric))
        actual = (ind or {}).get("current_value")
        if actual is None:
            continue
        actual = float(actual)
        for m in re.findall(pattern, blob, re.I):
            try:
                v = float(str(m).replace(",", "."))
            except ValueError:
                continue
            if 0.3 * actual < v < 3 * actual and abs(v - actual) / actual > tol:
                out.append(f"number_mismatch:{code}={v}!={actual}")
    return out


def _check_tickers(sections: dict, snapshot: dict) -> list[str]:
    """Названные бумаги обязаны существовать в покрытии платформы."""
    allowed = set((snapshot.get("context") or {}).get("platform_tickers") or [])
    if not allowed:
        return []
    out: list[str] = []
    for s in sections.get("sectors") or []:
        if not isinstance(s, dict):
            continue
        for side in ("winners", "losers"):
            for t in s.get(side) or []:
                if isinstance(t, str) and t.upper() not in allowed:
                    out.append(f"unknown_ticker:{t}")
    return out


def _check_epistemics(sections: dict) -> list[str]:
    """Три уровня достоверности обязательны, и «факт» не ставится на прогноз."""
    out: list[str] = []
    for i, t in enumerate(sections.get("theses") or []):
        if isinstance(t, dict) and t.get("tag") not in ("факт", "оценка", "суждение"):
            out.append(f"thesis_{i}_bad_tag")
    if not sections.get("against_us"):
        out.append("no_counterargument_block")   # Часть 19.3 п.5 — обязателен
    return out
