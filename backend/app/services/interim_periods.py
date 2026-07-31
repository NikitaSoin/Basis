"""Канонизация ПРОМЕЖУТОЧНЫХ периодов отчётности (interim) и корректный YoY.

🔴 ЗАЧЕМ. В `financials.json` → `interim.periods` лежит ОДИН ряд, в котором
перемешаны РАЗНЫЕ по длине периоды — так их выгружали агенты из отчётности
эмитента, и это не ошибка данных, а реальность раскрытия:

    ROSN:  6М2023 · 9М2023 · 3М2024 · 6М2024 · 9М2024 · 3М2025 · 6М2025 · 9М2025 · 3М2026
    AKRN:  1П2023 · 9М2023 · 1П2024 · 9М2024 · 1кв2025 · 2кв2025 · 3кв2025 · 1кв2026

Витрина считала динамику как «последнее значение ÷ предыдущее значение» — то есть
3М2026 делила на 9М2025 (квартал на девять месяцев). Число получалось
бессмысленным, но выглядело как «−63 % г/г». Правильное сравнение — ТОЛЬКО
период к СОПОСТАВИМОМУ периоду прошлого года: 3М к 3М, 1П к 1П, 2кв к 2кв.

Канон — ОКНО МЕСЯЦЕВ (start_m, end_m) от начала финансового года:
    1кв / 3М → (0,3)   2кв → (3,6)   3кв → (6,9)   4кв → (9,12)
    1П / 6М / H1 → (0,6)     9М → (0,9)     2П / H2 → (6,12)     12М / FY → (0,12)
Окно, а не «тип периода» из файла: поля `type`/`cumulative` агенты заполняли
вразнобой ('half'/'half_year'/'half-year'/'period_6m'/'quarterly_cumulative'),
а метка периода единообразна и однозначно читается. Бонус окна: 3М и 1кв
автоматически сопоставимы (одно окно), хотя написаны по-разному.

Модуль чистый (никакой БД/сети) — им пользуются и витрина `/financials`
(обогащение `yoy_idx`), и движок прикидки `run_rate.py`.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

# --- разбор метки периода -----------------------------------------------------

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_Q_RE = re.compile(r"(\d)\s*(?:кв|q)")          # 1кв2025, 2 кв, q1 → квартал
_Q_LAT_RE = re.compile(r"q\s*(\d)")             # Q1 2025
_HALF_RE = re.compile(r"(?:([12])\s*[пph]|[пph]\s*([12]))(?![а-яa-z])")  # 1П, 2п, H1, 1H
_MONTHS_RE = re.compile(r"(\d{1,2})\s*(?:мес|м|months?|m)(?![а-яa-z])")   # 6М, 9мес, 3M

# человеческая подпись окна (для подписи дельты на витрине)
_WINDOW_LABEL = {
    (0, 3): "1 кв.", (3, 6): "2 кв.", (6, 9): "3 кв.", (9, 12): "4 кв.",
    (0, 6): "1П", (6, 12): "2П", (0, 9): "9 мес.", (0, 12): "год",
}


def parse_period(p: dict) -> dict | None:
    """Период из `interim.periods` → канон {year, start_m, end_m, label}.

    None — метку разобрать не удалось (период выпадает из сравнений, но НЕ ломает
    остальные: fail-closed по одному элементу, а не по всему ряду)."""
    if not isinstance(p, dict):
        return None
    raw = str(p.get("label") or "").strip()
    if not raw:
        return None
    lab = raw.lower().replace("ё", "е")

    ym = _YEAR_RE.search(lab)
    year = int(ym.group(0)) if ym else None
    if year is None:
        fy = p.get("fiscal_year")
        if isinstance(fy, int):
            year = fy
        else:
            ed = str(p.get("end_date") or "")
            em = _YEAR_RE.search(ed)
            year = int(em.group(0)) if em else None
    if year is None:
        return None

    core = _YEAR_RE.sub(" ", lab)  # год убираем, иначе его цифры ловятся как номер периода

    win = None
    m = _Q_RE.search(core) or _Q_LAT_RE.search(core)
    if m:
        q = int(m.group(1))
        if 1 <= q <= 4:
            win = ((q - 1) * 3, q * 3)
    if win is None:
        m = _HALF_RE.search(core)
        if m:
            h = int(m.group(1) or m.group(2))
            win = (0, 6) if h == 1 else (6, 12) if h == 2 else None
    if win is None:
        m = _MONTHS_RE.search(core)
        if m:
            n = int(m.group(1))
            if n in (3, 6, 9, 12):
                win = (0, n)
    if win is None:
        return None

    return {"year": year, "start_m": win[0], "end_m": win[1],
            "label": _WINDOW_LABEL.get(win, raw), "raw": raw}


def canon_periods(periods: list) -> list:
    """Список периодов → список канонов (None на неразобранных, длина сохраняется)."""
    return [parse_period(p) for p in (periods or [])]


# --- адаптер: report_watch.EarningsReport.period → объект periods[] интерима ---

_REPORT_PERIOD_MAP = {
    (0, 3): ("1кв{year}", "quarter", False),
    (3, 6): ("2кв{year}", "quarter", False),
    (6, 9): ("3кв{year}", "quarter", False),
    (0, 6): ("1П{year}", "half", True),
    (6, 12): ("2П{year}", "half", False),
    (0, 9): ("9М{year}", "9m", True),
}


def report_period_to_interim(period: str, published_at=None) -> dict | None:
    """`EarningsReport.period` (напр. "1кв2026") → объект, готовый для
    `interim.periods[]`: {fiscal_year, start_m, end_m, period_label, period_type,
    cumulative, end_date}. None — период не распознан ИЛИ это ПОЛНЫЙ год
    ((0,12) — вне scope авто-довеска, годовые данные остаются ручным процессом
    report-fetcher'а); отдельное «2-е полугодие» ((6,12), start_m≠0) — валидный
    интерим-период (та же конвенция, что уже используют вручную собранные файлы,
    напр. PIKK: 2П2023/2П2024/2П2025), НЕ исключается. Переиспользует
    parse_period() как есть.

    `end_date` — фолбэк-дата: последний день месяца конца окна в рамках
    fiscal_year (report_watch не знает точную календарную дату конца периода,
    только дату публикации/детекта)."""
    canon = parse_period({
        "label": period,
        "end_date": published_at.isoformat() if published_at else None,
    })
    if canon is None or (canon["start_m"] == 0 and canon["end_m"] == 12):
        return None
    year, sm, em = canon["year"], canon["start_m"], canon["end_m"]
    spec = _REPORT_PERIOD_MAP.get((sm, em))
    if spec is None:
        return None
    label_tpl, ptype, cumulative = spec
    last_day = calendar.monthrange(year, em)[1]
    return {
        "fiscal_year": year, "start_m": sm, "end_m": em,
        "period_label": label_tpl.format(year=year), "period_type": ptype,
        "cumulative": cumulative, "end_date": date(year, em, last_day),
    }


def build_yoy_index(periods: list) -> list:
    """Для каждого периода — индекс СОПОСТАВИМОГО периода прошлого года (или None).

    Сопоставимый = то же окно месяцев, год−1. Нет такого периода в ряду → None,
    и витрина честно не показывает дельту (лучше пусто, чем ложные −63 %)."""
    canon = canon_periods(periods)
    by_key: dict[tuple, int] = {}
    for i, c in enumerate(canon):
        if c:
            by_key[(c["year"], c["start_m"], c["end_m"])] = i  # дубль метки → последний
    return [by_key.get((c["year"] - 1, c["start_m"], c["end_m"])) if c else None for c in canon]


# --- накопленный период с начала года (для прикидки run-rate) -----------------

def _val(series: list, i: int):
    v = series[i] if isinstance(series, list) and 0 <= i < len(series) else None
    return v if isinstance(v, (int, float)) else None


def ytd_for_year(periods: list, series: list, year: int, end_m: int | None = None) -> dict | None:
    """Накопленный результат года `year` с начала года по данным ряда `series`.

    Два пути, берём тот, что покрывает БОЛЬШЕ месяцев:
      1) готовый накопительный период — окно (0, M): 1П, 9М, 3М;
      2) сумма ПОСЛЕДОВАТЕЛЬНЫХ дискретных кварталов от 1-го: 1кв(+2кв(+3кв…)).
    `end_m` задан → нужен ровно такой охват (для сравнения год-к-году и для
    исторических сезонных долей — иначе сравнивали бы 1П с 9М).

    Возврат: {"end_m", "value", "source"} либо None."""
    canon = canon_periods(periods)
    cand: list[tuple[int, float, str]] = []

    for i, c in enumerate(canon):
        if not c or c["year"] != year or c["start_m"] != 0:
            continue
        v = _val(series, i)
        if v is not None:
            cand.append((c["end_m"], v, "cumulative"))

    q_by_idx = {}
    for i, c in enumerate(canon):
        if c and c["year"] == year and c["end_m"] - c["start_m"] == 3:
            v = _val(series, i)
            if v is not None:
                q_by_idx[c["start_m"] // 3] = v
    acc = 0.0
    for qi in range(4):
        if qi not in q_by_idx:
            break
        acc += q_by_idx[qi]
        cand.append(((qi + 1) * 3, acc, "quarters"))

    if end_m is not None:
        cand = [c for c in cand if c[0] == end_m]
    if not cand:
        return None
    best = max(cand, key=lambda c: (c[0], c[2] == "cumulative"))
    return {"end_m": best[0], "value": best[1], "source": best[2]}


def latest_ytd(periods: list, series: list) -> dict | None:
    """Самый свежий накопленный период: максимальный охват в максимальном году.

    Идём от последнего года вниз — свежий год, где ряд ещё пуст (агент завёл
    период, но не заполнил показатель), не должен обнулять прикидку."""
    years = sorted({c["year"] for c in canon_periods(periods) if c}, reverse=True)
    for y in years:
        r = ytd_for_year(periods, series, y)
        if r:
            return {"year": y, **r}
    return None
