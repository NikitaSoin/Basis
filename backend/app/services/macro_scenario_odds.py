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



def _range(raw: str | None) -> tuple[float, float] | None:
    """Границы коридора «14,5–14,6» (одно число → границы совпадают)."""
    if not raw:
        return None
    nums = [float(x.replace(",", ".")) for x in re.findall(r"-?\d+[.,]?\d*", raw)]
    if not nums:
        return None
    return min(nums), max(nums)


def _elapsed_avg_rate(db: Session, year: int) -> tuple[float, float] | None:
    """Средняя ключевая ставка с 1 января по сегодня и доля года, которую она заняла.

    🔴 Ставка ступенчатая, поэтому среднее — по ДНЯМ, а не по точкам ряда. И считать
    надо С 1 ЯНВАРЯ: первая версия стартовала с первой точки ВНУТРИ года (28 января) и
    теряла январь целиком — прошедшая доля выходила 0,53 вместо 0,61, средняя занижалась,
    а выведенная из неё «средняя до конца года» завышалась на 0,7 п.п. Владелец поймал
    это по памяти: «у ЦБ до конца года 13,5-14, о чём ты говоришь?». Значение на 1 января
    берём переносом последней точки ПРОШЛОГО года.
    """
    from sqlalchemy import text as _sql
    start = date(year, 1, 1)
    prev = db.execute(_sql(
        "SELECT value FROM macro_data_points WHERE indicator_code='key_rate' "
        "AND metric='level' AND as_of < :s ORDER BY as_of DESC LIMIT 1"), {"s": start}).first()
    rows = db.execute(_sql(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code='key_rate' "
        "AND metric='level' AND as_of >= :s ORDER BY as_of"), {"s": start}).all()
    # 🔴 ЖУРНАЛ РЕШЕНИЙ — источник истины по траектории (найдено 2026-08-10): в ряду
    # macro_data_points пропущены апрельское (14,5%) и июньское (14,25%) заседания, ряд
    # прыгает с 15,0 сразу на 14,0. Среднее по дырявому ряду завышало прошедшую среднюю
    # и занижало выведенную «среднюю до конца года» на ~0,4 п.п. — владелец заметил
    # расхождение с прогнозом ЦБ по памяти. Объединяем оба источника, решение важнее.
    meetings = db.execute(_sql(
        "SELECT decision_date, rate_value FROM rate_meetings WHERE decision_date >= :s "
        "AND rate_value IS NOT NULL ORDER BY decision_date"), {"s": start}).all()
    if prev is None and not rows and not meetings:
        return None
    today = date.today()
    by_date: dict[date, float] = {}
    for d, v in rows:
        if d <= today:
            by_date[d] = float(v)
    for d, v in meetings:                      # решение перекрывает точку ряда
        if d <= today:
            by_date[d] = float(v)
    points: list[tuple[date, float]] = []
    if prev is not None:
        points.append((start, float(prev[0])))       # ставка на 1 января — перенос
    points.extend(sorted(by_date.items()))
    if not points:
        return None
    acc, days_total = 0.0, 0
    for i, (d, v) in enumerate(points):
        end = points[i + 1][0] if i + 1 < len(points) else today
        days = max(0, (end - d).days)
        acc += v * days
        days_total += days
    if days_total <= 0:
        return None
    return acc / days_total, days_total / 365.0


def _avg_rest_of_year(db: Session, year: int, annual: tuple[float, float] | None
                      ) -> tuple[float, float] | None:
    """Средняя ключевая ставка НА ОСТАВШУЮСЯ часть года — коридором.

    🔴 Владелец, 2026-08-10: «пиши не средняя за год, а средняя с текущего момента —
    так становится понятно, чего ждать». Годовая средняя смешивает уже случившееся с
    будущим и рядом с сегодняшними 14% читается как ошибка. Выводим из тождества:
    годовая = прошедшая × доля + оставшаяся × (1 − доля). Оба конца коридора ЦБ
    пересчитываем отдельно, чтобы не выдавать точку там, где у ЦБ диапазон.
    """
    if not annual:
        return None
    got = _elapsed_avg_rate(db, year)
    if not got:
        return None
    elapsed_avg, share = got
    if share >= 0.98:
        return None
    lo, hi = annual
    rest_lo = (lo - elapsed_avg * share) / (1 - share)
    rest_hi = (hi - elapsed_avg * share) / (1 - share)
    return round(min(rest_lo, rest_hi), 1), round(max(rest_lo, rest_hi), 1)



def _anchor(db: Session, year: int, cb: dict, survey: dict) -> dict:
    """Чего ждут ЦБ и аналитики — в форме, из которой понятно, чего ждать дальше."""
    def _p(v: float, dec: int = 1) -> str:
        return f"{v:.{dec}f}".replace(".", ",")

    def _rng(r: tuple[float, float] | None) -> str | None:
        if not r:
            return None
        return _p(r[0]) if abs(r[1] - r[0]) < 0.05 else f"{_p(r[0])}–{_p(r[1])}"

    cb_rest = _avg_rest_of_year(db, year, _range(cb.get("Ключевая ставка")))
    mkt_rest = _avg_rest_of_year(db, year, _range(survey.get("Ключевая ставка")))
    now = _latest(db, "key_rate", "level")
    parts = []
    if now is not None:
        parts.append(f"Ставка сейчас {_p(now, 0)}%.")
    if cb_rest:
        rate = (f"До конца года Банк России в базовом сценарии закладывает в среднем "
                f"{_rng(cb_rest)}%")
        if mkt_rest:
            diff = sum(mkt_rest) / 2 - sum(cb_rest) / 2
            how = ("жёстче" if diff > 0.2 else "мягче" if diff < -0.2 else "примерно так же")
            rate += f", аналитики — {_rng(mkt_rest)}%, то есть {how}"
        parts.append(rate + ".")
    cb_i, mkt_i = _range(cb.get("Инфляция")), _range(survey.get("ИПЦ"))
    if cb_i and mkt_i:
        parts.append(f"Инфляцию на конец года ЦБ видит на {_rng(cb_i)}%, "
                     f"аналитики — {_rng(mkt_i)}%.")
    return {"human": " ".join(parts),
            "key_rate_now_pct": now,
            "cb_avg_rest_of_year_pct": list(cb_rest) if cb_rest else None,
            "consensus_avg_rest_of_year_pct": list(mkt_rest) if mkt_rest else None,
            "cb_annual_avg_rate": cb.get("Ключевая ставка"),
            "consensus_annual_avg_rate": survey.get("Ключевая ставка"),
            "_note": "средняя до конца года выведена из годовой средней ЦБ и фактической "
                     "траектории ставки с 1 января (ставка ступенчатая, среднее по дням)"}


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
