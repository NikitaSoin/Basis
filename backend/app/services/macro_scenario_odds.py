"""Вероятности макро-сценариев — считает КОД по наблюдаемым сигналам.

🔴 ЗАЧЕМ (владелец, 2026-08-09, согласовано): сценарии внизу макро-выпуска должны быть
макроэкономические (рамка среднесрочного прогноза Банка России), а рядом с ними — вес.
Проблема в том, что **ЦБ вероятностей не публикует**: он даёт четыре пути (базовый,
дезинфляционный, проинфляционный, рисковый) без весов. Значит, любой процент на экране —
наш собственный. Ставить его «на глаз» моделью нельзя: сегодня 25%, завтра 40% на тех же
данных, и проверить нельзя.

Поэтому вес считается здесь, по наблюдаемым сигналам, а модель только объясняет словами
то, что посчитано. Каждый сдвиг веса сопровождается ПРИЧИНОЙ — вероятность становится
воспроизводимой и оспоримой: видно, из чего сложилась, и при развороте сигнала она
двигается сама.

Сигналы (каждый двигает вес на ограниченную величину, суммарно нормируется к 100%):
1. Консенсус аналитиков против базового пути ЦБ (макроопрос ЦБ, 30+ респондентов):
   ставка на конец года ниже коридора ЦБ → рынок ждёт более быстрой дезинфляции;
   выше → проинфляционный путь.
2. Инфляционный импульс: годовая инфляция против коридора базового прогноза.
3. Спрос и кредит: резкое торможение кредита экономике поднимает вес рецессии.
4. Сырьё: нефть заметно ниже ориентира бюджета поднимает рисковый сценарий.

🔴 Чего этот модуль НЕ делает: не выдаёт вероятности за прогноз ЦБ (это оценка
платформы) и не заявляет точности выше шага в 5 процентных пунктов — веса округляются,
чтобы не изображать точность, которой в методе нет.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Стартовые веса. Базовый — модальный путь по построению (ЦБ строит прогноз вокруг него),
# альтернативы делят остаток поровну с небольшим перевесом проинфляционного: в российской
# практике последних лет пересмотры чаще шли в эту сторону.
_PRIOR = {"base": 50, "proinflation": 20, "disinflation": 18, "recession": 12}

_NAMES = {
    "base": "Базовый (путь Банка России)",
    "proinflation": "Проинфляционный: спрос и издержки выше, ставка высокая дольше",
    "disinflation": "Дезинфляционный: спрос охлаждается быстрее, ставка вниз раньше",
    "recession": "Рисковый: рецессия и дешёвое сырьё",
}
# Каждой альтернативе — потолок: метод не настолько точен, чтобы объявлять не-базовый
# путь вероятнее базового.
_CAP = 35
_STEP = 5           # шаг сдвига, п.п. — мельче было бы ложной точностью
_OIL_BUDGET_REF = 60.0   # ориентир цены отсечки бюджетного правила, $/барр.


def _rows(db: Session, table: str, year: int) -> dict[str, str]:
    from sqlalchemy import text as _sql
    q = {"forecast": "SELECT indicator, value FROM macro_forecasts WHERE year = :y "
                     "ORDER BY as_of DESC",
         "survey": "SELECT indicator, value FROM macro_expert_surveys WHERE year = :y "
                   "ORDER BY as_of DESC"}[table]
    out: dict[str, str] = {}
    for ind, val in db.execute(_sql(q), {"y": year}).all():
        out.setdefault(str(ind), str(val))
    return out


def _num(raw: str | None) -> float | None:
    """Число из значения вида «14,5», «6,0–7,0» (берём середину коридора)."""
    if not raw:
        return None
    nums = [float(x.replace(",", ".")) for x in re.findall(r"-?\d+[.,]?\d*", raw)]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _latest(db: Session, code: str, metric: str) -> float | None:
    from sqlalchemy import text as _sql
    row = db.execute(_sql("SELECT value FROM macro_data_points WHERE indicator_code = :c "
                          "AND metric = :m ORDER BY as_of DESC LIMIT 1"),
                     {"c": code, "m": metric}).first()
    return float(row[0]) if row and row[0] is not None else None


def compute(db: Session, year: int | None = None) -> dict:
    """Веса сценариев на горизонт года прогноза ЦБ (по умолчанию — текущий год)."""
    year = year or date.today().year
    weights = dict(_PRIOR)
    why: dict[str, list[str]] = {k: [] for k in weights}
    signals: list[dict] = []

    cb = _rows(db, "forecast", year)
    survey = _rows(db, "survey", year)

    def _shift(key: str, steps: int, reason: str) -> None:
        if steps <= 0:
            return
        delta = min(steps * _STEP, _CAP - weights[key])
        if delta <= 0:
            return
        weights[key] += delta
        weights["base"] -= delta
        why[key].append(reason)

    # 1. Консенсус аналитиков против базового пути ЦБ по ставке
    cb_rate = _num(cb.get("Ключевая ставка"))
    mkt_rate = _num(survey.get("Ключевая ставка"))
    if cb_rate is not None and mkt_rate is not None:
        gap = mkt_rate - cb_rate
        signals.append({"signal": "консенсус аналитиков по ставке против базового пути ЦБ",
                        "value": f"{mkt_rate:.1f}% против {cb_rate:.1f}%",
                        "reading": "рынок ждёт более жёсткой политики" if gap > 0.3
                                   else "рынок ждёт более быстрого смягчения" if gap < -0.3
                                   else "совпадает с ЦБ"})
        steps = int(abs(gap) / 0.5)
        if gap > 0.3:
            _shift("proinflation", steps,
                   f"консенсус по ставке на {gap:.1f} п.п. выше базового пути ЦБ")
        elif gap < -0.3:
            _shift("disinflation", steps,
                   f"консенсус по ставке на {abs(gap):.1f} п.п. ниже базового пути ЦБ")

    # 2. Инфляционный импульс: где идёт годовая инфляция относительно коридора ЦБ
    cb_infl = _num(cb.get("Инфляция"))
    infl = _latest(db, "inflation", "yoy")
    if cb_infl is not None and infl is not None:
        gap = infl - cb_infl
        signals.append({"signal": "годовая инфляция против базового коридора ЦБ",
                        "value": f"{infl:.1f}% против {cb_infl:.1f}%",
                        "reading": "выше коридора" if gap > 0.3 else
                                   "ниже коридора" if gap < -0.3 else "в коридоре"})
        steps = int(abs(gap) / 0.5)
        if gap > 0.3:
            _shift("proinflation", steps, f"инфляция на {gap:.1f} п.п. выше базового коридора")
        elif gap < -0.3:
            _shift("disinflation", steps, f"инфляция на {abs(gap):.1f} п.п. ниже базового коридора")

    # 3. Спрос и кредит: торможение кредита экономике — ранний признак рецессии
    credit = _latest(db, "credit_economy", "yoy")
    if credit is not None:
        signals.append({"signal": "кредит экономике, г/г", "value": f"{credit:.1f}%",
                        "reading": "резкое торможение" if credit < 5 else
                                   "замедление" if credit < 10 else "рост"})
        if credit < 5:
            _shift("recession", 2, f"кредит экономике замедлился до {credit:.1f}% г/г")
        elif credit < 10:
            _shift("recession", 1, f"кредитование замедляется ({credit:.1f}% г/г)")

    # 4. Сырьё: нефть ниже ориентира бюджета — давление на доходы и рисковый сценарий
    oil = _latest(db, "urals", "level") or _latest(db, "brent", "level")
    if oil is not None:
        signals.append({"signal": "нефть против ориентира бюджета",
                        "value": f"${oil:.0f} против ${_OIL_BUDGET_REF:.0f}",
                        "reading": "ниже ориентира" if oil < _OIL_BUDGET_REF else "выше ориентира"})
        if oil < _OIL_BUDGET_REF - 5:
            _shift("recession", 1, f"нефть ${oil:.0f} ниже ориентира бюджета")

    # Нормировка: база не опускается ниже 40 — метод не претендует объявлять
    # не-базовый путь основным, а базовый по построению модальный (ЦБ строит прогноз
    # вокруг него). Ниже этого порога сдвиги перестают отниматься от базы.
    weights["base"] = max(40, weights["base"])
    total = sum(weights.values())
    scen = []
    for key in ("base", "proinflation", "disinflation", "recession"):
        pct = round(weights[key] / total * 100 / 5) * 5      # шаг 5 п.п., не мельче
        scen.append({"key": key, "name": _NAMES[key], "probability_pct": pct,
                     "why": why[key] or (["базовый путь Банка России — точка отсчёта"]
                                         if key == "base" else
                                         ["сигналов в пользу этого пути сейчас нет"])})
    drift = 100 - sum(s["probability_pct"] for s in scen)
    if drift:
        scen[0]["probability_pct"] += drift      # округление добираем базовым

    return {
        "horizon": f"до конца {year}",
        "scenarios": scen,
        "signals": signals,
        "market_anchor": {"consensus_rate_pct": _num(survey.get("Ключевая ставка")),
                          "cb_base_rate_pct": _num(cb.get("Ключевая ставка")),
                          "consensus_inflation_pct": _num(survey.get("ИПЦ")),
                          "cb_base_inflation_pct": _num(cb.get("Инфляция"))},
        "method": "Рамка — среднесрочный прогноз Банка России (базовый и альтернативные "
                  "пути). Вероятностей ЦБ не публикует, поэтому веса — ОЦЕНКА платформы: "
                  "стартовые доли сдвигаются наблюдаемыми сигналами (консенсус аналитиков "
                  "против базового пути, инфляционный импульс, кредит, нефть), шаг 5 п.п., "
                  "потолок альтернативы 35%. Не прогноз ЦБ и не рыночная вероятность.",
    }
