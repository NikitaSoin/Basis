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

# Слово «путь» из названий убрано (владелец, 2026-08-10): читатель ждёт «сценарий».
_NAMES = {
    "base": "Базовый сценарий Банка России",
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



def _avg_rest_of_year(db: Session, year: int, annual_avg: float | None) -> float | None:
    """Средняя ключевая ставка НА ОСТАВШУЮСЯ часть года.

    🔴 Владелец, 2026-08-10: «пиши не средняя за год, а средняя с текущего момента —
    так становится понятно, чего ждать». И это правильно по существу: годовая средняя
    смешивает уже случившееся с будущим, и на фоне сегодняшних 14% она читается как
    ошибка. Выводим из тождества: годовая средняя = (среднее по прошедшим месяцам ×
    прошедшие месяцы + среднее по оставшимся × оставшиеся) / 12.
    """
    if annual_avg is None:
        return None
    from sqlalchemy import text as _sql
    rows = db.execute(_sql(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code = 'key_rate' "
        "AND metric = 'level' AND as_of >= :start ORDER BY as_of"),
        {"start": date(year, 1, 1)}).all()
    if not rows:
        return None
    today = date.today()
    # среднее по дням с начала года: ставка ступенчатая, взвешиваем по длительности
    total_days, acc = 0, 0.0
    prev_d, prev_v = None, None
    for d, v in rows:
        if prev_d is not None:
            days = (d - prev_d).days
            acc += float(prev_v) * days
            total_days += days
        prev_d, prev_v = d, float(v)
    if prev_d is not None:
        days = max(0, (today - prev_d).days)
        acc += float(prev_v) * days
        total_days += days
    if total_days <= 0:
        return None
    elapsed_avg = acc / total_days
    elapsed_share = total_days / 365.0
    if elapsed_share >= 0.98:
        return None
    rest = (annual_avg - elapsed_avg * elapsed_share) / (1 - elapsed_share)
    return round(rest, 1)



def _anchor(db: Session, year: int, cb: dict, survey: dict) -> dict:
    """Чего ждут ЦБ и аналитики — в понятной читателю форме.

    Годовые средние ставки пересчитываются в среднюю НА ОСТАВШУЮСЯ часть года: именно
    она отвечает на вопрос «чего ждать дальше», а годовая на фоне текущих 14% выглядит
    опечаткой.
    """
    cb_avg, mkt_avg = _num(cb.get("Ключевая ставка")), _num(survey.get("Ключевая ставка"))
    cb_rest = _avg_rest_of_year(db, year, cb_avg)
    mkt_rest = _avg_rest_of_year(db, year, mkt_avg)
    now = _latest(db, "key_rate", "level")
    def _p(v: float, dec: int = 1) -> str:
        return f"{v:.{dec}f}".replace(".", ",")

    parts = []
    if now is not None:
        parts.append(f"Ставка сейчас {_p(now, 0)}%.")
    if cb_rest is not None:
        rate = (f"До конца года Банк России в базовом сценарии закладывает в среднем "
                f"{_p(cb_rest)}%")
        if mkt_rest is not None:
            diff = mkt_rest - cb_rest
            how = ("жёстче" if diff > 0.2 else "мягче" if diff < -0.2 else "примерно так же")
            rate += f", аналитики — {_p(mkt_rest)}%, то есть {how}"
        parts.append(rate + ".")
    cb_i, mkt_i = _num(cb.get("Инфляция")), _num(survey.get("ИПЦ"))
    if cb_i is not None and mkt_i is not None:
        parts.append(f"Инфляцию на конец года ЦБ видит на {_p(cb_i)}%, аналитики — {_p(mkt_i)}%.")
    return {"human": " ".join(parts),
            "key_rate_now_pct": now,
            "cb_avg_rest_of_year_pct": cb_rest,
            "consensus_avg_rest_of_year_pct": mkt_rest,
            "cb_annual_avg_rate_pct": cb_avg, "consensus_annual_avg_rate_pct": mkt_avg,
            "cb_inflation_pct": cb_i, "consensus_inflation_pct": mkt_i}


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
        # 🔴 И у ЦБ, и в макроопросе это СРЕДНЯЯ ЗА ГОД, а не уровень на конец года и не
        # текущая ставка (владелец, 2026-08-09: «ставка уже 14 процентов» — подпись без
        # слова „средняя“ читается как сегодняшний уровень и выглядит бредом).
        signals.append({"signal": "консенсус аналитиков против базового пути ЦБ — "
                                  "СРЕДНЯЯ ставка за год, не текущий уровень",
                        "value": f"консенсус {mkt_rate:.1f}% против {cb_rate:.1f}% у ЦБ "
                                 f"(оба — средняя за {year} год)",
                        "reading": "рынок ждёт более жёсткой политики" if gap > 0.3
                                   else "рынок ждёт более быстрого смягчения" if gap < -0.3
                                   else "совпадает с ЦБ"})
        steps = int(abs(gap) / 0.5)
        if gap > 0.3:
            _shift("proinflation", steps,
                   f"консенсус по средней ставке на {gap:.1f} п.п. выше базового сценария ЦБ")
        elif gap < -0.3:
            _shift("disinflation", steps,
                   f"консенсус по средней ставке на {abs(gap):.1f} п.п. ниже базового сценария ЦБ")

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
                     "why": why[key] or (["базовый сценарий Банка России — точка отсчёта"]
                                         if key == "base" else
                                         ["сигналов в пользу этого пути сейчас нет"])})
    drift = 100 - sum(s["probability_pct"] for s in scen)
    if drift:
        scen[0]["probability_pct"] += drift      # округление добираем базовым

    return {
        "horizon": f"до конца {year}",
        "scenarios": scen,
        "signals": signals,
        "market_anchor": _anchor(db, year, cb, survey),
        "method": "Рамка — среднесрочный прогноз Банка России (базовый и альтернативные "
                  "пути). Вероятностей ЦБ не публикует, поэтому веса — ОЦЕНКА платформы: "
                  "стартовые доли сдвигаются наблюдаемыми сигналами (консенсус аналитиков "
                  "против базового пути, инфляционный импульс, кредит, нефть), шаг 5 п.п., "
                  "потолок альтернативы 35%. Не прогноз ЦБ и не рыночная вероятность.",
    }
