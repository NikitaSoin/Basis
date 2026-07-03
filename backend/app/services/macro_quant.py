"""Детерминированный расчётный модуль макро-квантификации (методичка §14).

Проблема, которую решает: модель ненадёжна в арифметике. Поэтому macro-analyst
кладёт в macro.json ТОЛЬКО числовые входы и коэффициенты (`quant_inputs`), а
ВСЮ арифметику — водопад атрибуции, таблицу чувствительности, сценарные дельты —
считает ЭТОТ код и складывает в `macro.json["computed"]`. Так числа между тремя
блоками СХОДЯТСЯ (один источник коэффициентов), ничего не «галлюцинируется».

Единая формула по каждому фактору-драйверу:
    delta_metric = coefficient[metric] × (значение_фактора − ориентир)
где ориентир — нейтральный уровень (для атрибуции) или текущий (для сценариев).

Единицы: все финансовые величины — в `quant_inputs.unit` (по умолчанию млрд ₽).
Коэффициент задан «на +1 единицу фактора» (per): fx=+1₽, commodity=+1$,
rate=+100 б.п.(=1 п.п.), cost_inflation=+1 п.п. Значения макро выражены в тех же
единицах, поэтому масштаб = 1: delta = coef × (Δ значения в этих единицах).
"""
from __future__ import annotations

# Фактор → ключ его драйвера в macro_current / macro_neutral / scenarios.
# ВАЖНО (системность ставки): ставка НЕ только «проценты по долгу». Её эффект раскладывается
# на ОТДЕЛЬНЫЕ каналы-факторы, чтобы не сводить к линейному «ставка→проценты»:
#   rate    — прямой процентный канал (долг × ставка);
#   demand  — ставка → ВВП/совокупный спрос → объём продаж → выручка (для циклических);
#   labor   — ставка → рынок труда/зарплаты → база издержек (или инфляция ФОТ);
#   fx      — ставка → курс (эндогенно): в сценариях курс двигается СОГЛАСОВАННО со ставкой,
#             но текущий эффект курса живёт в отдельном fx-факторе (без двойного счёта).
# Агент (Opus) раскладывает ставку по каналам системно; модуль лишь перемножает коэффициенты.
_FACTOR_DRIVER = {
    "fx": "fx_usdrub",
    "commodity": "commodity_usd",
    "rate": "key_rate_pct",
    "demand": "gdp_growth_pct",
    "labor": "wage_growth_pp",
    "cost_inflation": "cost_excess_pp",
}

# Человекочитаемые подписи по умолчанию (фронт может переопределить из factors[]).
_FACTOR_LABEL = {
    "fx": "Курс рубля",
    "commodity": "Цена сырья",
    "rate": "Ставка (процентный канал)",
    "demand": "Спрос / ВВП (канал ставки)",
    "labor": "Рынок труда / зарплаты",
    "cost_inflation": "Инфляция издержек",
}

_METRICS = ("revenue", "ebitda", "net_profit")


def _num(v):
    """Число или None. Пустые строки/нечисловое → None (фактор деградирует, не падаем)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _round(v):
    """Адаптивное округление: крупные компании — целые млрд (дробь = шум), малые (POSI,
    неликвид) — с десятыми, иначе коэффициенты <1 млрд занулялись бы в 0 и вкладка пустела."""
    if v is None:
        return None
    av = abs(v)
    if av >= 10:
        return round(v)
    if av >= 1:
        return round(v, 1)
    return round(v, 2)


def _delta(coef_metric, cur, ref):
    """delta = coef × (значение − ориентир). None-безопасно."""
    c, x, r = _num(coef_metric), _num(cur), _num(ref)
    if c is None or x is None or r is None:
        return None
    return c * (x - r)


def _driver_of(factor_key: str, coef: dict) -> str | None:
    """Ключ драйвера фактора: ЯВНЫЙ coef['driver'] приоритетнее фиксированной карты.
    Это позволяет переопределить драйвер даже у стандартного фактора (напр. фактор
    'demand' у ALRS завязан не на ВВП РФ, а на мировой люкс-спрос lux_demand_pp;
    у нефтяников commodity может ссылаться на Urals-специфичный ключ). Явное намерение
    агента (driver) всегда бьёт дефолт; если driver не задан — берём фиксированную карту
    (fx→fx_usdrub, rate→key_rate_pct, ...); для произвольных ключей (cost_of_risk и т.п.)
    работает только driver."""
    return (coef or {}).get("driver") or _FACTOR_DRIVER.get(factor_key)


def _label_of(factor_key: str, coef: dict) -> str:
    # явная подпись агента приоритетнее дефолта (напр. commodity → «Цена золота»/«Цена удобрений»)
    return (coef or {}).get("label") or _FACTOR_LABEL.get(factor_key) or factor_key


def _active_factors(coefficients: dict) -> list[str]:
    """Факторы с заданными коэффициентами. Помимо фиксированных (fx/rate/...) поддержаны
    ПРОИЗВОЛЬНЫЕ каналы: если у коэффициента задан свой 'driver' (ключ в macro_current/
    neutral) — фактор активен (напр. cost_of_risk у банка, metals_price у металлурга)."""
    out = []
    for key, coef in (coefficients or {}).items():
        if not isinstance(coef, dict):
            continue
        if _driver_of(key, coef) is None:
            continue  # нет драйвера — не считаем
        if any(_num(coef.get(m)) is not None for m in _METRICS):
            out.append(key)
    # стабильный порядок: сначала фиксированные (как в _FACTOR_DRIVER), потом прочие
    fixed = [k for k in _FACTOR_DRIVER if k in out]
    extra = [k for k in out if k not in _FACTOR_DRIVER]
    return fixed + extra


def compute_attribution(qi: dict) -> dict:
    """Слой A — водопад от нейтрального макро к факту (методичка 14.3).

    bridge: по каждому фактору delta_np = coef.net_profit × (текущее − нейтраль).
    residual = факт − (нейтраль + Σ delta) — показываем ЧЕСТНО, не подгоняем.
    Разовый эффект (one_off) в водопад НЕ входит — отдельной строкой.
    """
    coefficients = qi.get("coefficients") or {}
    cur = qi.get("macro_current") or {}
    neu = qi.get("macro_neutral") or {}
    fin = qi.get("financials") or {}
    neutral_np = _num(qi.get("neutral_net_profit"))
    actual_np = _num(fin.get("net_profit"))

    bridge = []
    sum_delta = 0.0
    for f in _active_factors(coefficients):
        coef = coefficients[f]
        driver = _driver_of(f, coef)
        cf, x, r = _num(coef.get("net_profit")), _num(cur.get(driver)), _num(neu.get(driver))
        d = _delta(coef.get("net_profit"), cur.get(driver), neu.get(driver))
        if d is None:
            continue
        sum_delta += d
        bridge.append({
            "factor_key": f,
            "label": _label_of(f, coefficients[f]),
            "delta": _round(d),
            "is_one_off": False,
            "source": coef.get("source", "estimated"),
            "assumption": coef.get("assumption", ""),
            # раскладка «как посчитано» (для блока прозрачности на фронте, как в Финансах):
            # коэффициент × сдвиг фактора (текущее − нейтраль) = дельта
            "calc": {
                "coef": _round(cf), "per": coef.get("per", ""),
                "from": r, "to": x, "shift": _round((x - r)) if (x is not None and r is not None) else None,
            },
        })

    one_off = qi.get("one_off") or {}
    one_off_np = _num(one_off.get("net_profit"))

    # Разовое (one_off, напр. курсовая переоценка долга) НЕ входит в операционный водопад
    # (методичка 14.2). Водопад ведёт к ОПЕРАЦИОННОЙ прибыли = отчётная − разовое; one_off —
    # отдельный мост к отчётной. Так residual не раздувается на бумажную переоценку.
    operating_np = None
    if actual_np is not None:
        operating_np = actual_np - (one_off_np or 0.0)

    residual = None
    if neutral_np is not None and operating_np is not None:
        residual = operating_np - (neutral_np + sum_delta)

    # главный драйвер — фактор с максимальным по модулю вкладом
    main = None
    if bridge:
        main = max(bridge, key=lambda b: abs(b["delta"] or 0))["factor_key"]

    return {
        "neutral_net_profit": _round(neutral_np),
        "bridge": bridge,
        "residual": _round(residual),
        "operating_net_profit": _round(operating_np),   # итог операционного водопада
        "actual_net_profit": _round(actual_np),          # отчётная (операционная + one_off)
        "one_off": ({
            "label": one_off.get("label", "Разовый эффект"),
            "net_profit": _round(one_off_np),
            "note": one_off.get("note", ""),
            "certainty": one_off.get("certainty", "estimate"),
        } if one_off_np is not None else None),
        "main_driver": main,
        "unit": qi.get("unit", "млрд_руб"),
    }


def compute_sensitivities(qi: dict) -> list[dict]:
    """Слой B — таблица «± единица фактора → ± финансы» напрямую из коэффициентов.

    Те же coefficients, что в водопаде и сценариях → значения гарантированно согласованы.
    """
    coefficients = qi.get("coefficients") or {}
    rows = []
    for f in _active_factors(coefficients):
        coef = coefficients[f]
        rows.append({
            "factor_key": f,
            "label": _label_of(f, coefficients[f]),
            "per": coef.get("per", ""),
            "revenue": _round(_num(coef.get("revenue"))),
            "ebitda": _round(_num(coef.get("ebitda"))),
            "net_profit": _round(_num(coef.get("net_profit"))),
            "source": coef.get("source", "estimated"),
            "assumption": coef.get("assumption", ""),
        })
    return rows


def compute_scenarios(qi: dict) -> dict:
    """Слой C — дельта финансов к текущему факту по сценариям (методичка 14.5).

    В каждом сценарии: delta_metric = Σ_факторов coef[metric] × (сценарий_драйвер − текущий_драйвер).
    """
    coefficients = qi.get("coefficients") or {}
    cur = qi.get("macro_current") or {}
    scenarios = qi.get("scenarios") or {}
    factors = _active_factors(coefficients)

    out = {}
    for name in ("base", "hawkish", "dovish"):
        sc = scenarios.get(name)
        if not isinstance(sc, dict):
            continue
        deltas = {m: 0.0 for m in _METRICS}
        contributions = {}
        any_metric = False
        for f in factors:
            coef = coefficients[f]
            driver = _driver_of(f, coef)
            contrib = {}
            for m in _METRICS:
                d = _delta(coef.get(m), sc.get(driver), cur.get(driver))
                if d is not None:
                    deltas[m] += d
                    contrib[m] = _round(d)
                    any_metric = True
            if contrib:
                contributions[f] = contrib
        out[name] = {
            "probability": sc.get("probability", ""),
            "macro": {k: sc.get(k) for k in ("fx_usdrub", "key_rate_pct", "commodity_usd", "cost_excess_pp") if sc.get(k) is not None},
            "revenue_delta": _round(deltas["revenue"]) if any_metric else None,
            "ebitda_delta": _round(deltas["ebitda"]) if any_metric else None,
            "net_profit_delta": _round(deltas["net_profit"]) if any_metric else None,
            "contributions": contributions,
        }
    return out


def compute(quant_inputs: dict) -> dict:
    """Полный расчёт computed-блока из quant_inputs. Пустой вход → пустой (деградация)."""
    qi = quant_inputs or {}
    attribution = compute_attribution(qi)
    sensitivities = compute_sensitivities(qi)
    scenarios = compute_scenarios(qi)

    # Диагностика сходимости водопада (для ОТК/тестов): насколько остаток велик.
    residual = attribution.get("residual")
    neutral = attribution.get("neutral_net_profit")
    residual_pct = None
    if residual is not None and neutral:
        residual_pct = round(100.0 * residual / neutral, 1)

    return {
        "attribution": attribution,
        "sensitivities": sensitivities,
        "scenarios": scenarios,
        "checks": {
            "waterfall_has_residual": residual is not None,
            "residual": residual,
            "residual_pct_of_neutral": residual_pct,
            "factors_count": len(sensitivities),
        },
        "_note": "computed by backend/app/services/macro_quant.py",
    }


def enrich(macro: dict) -> dict:
    """Идемпотентно: берёт macro['quant_inputs'], считает и кладёт в macro['computed'].
    Возвращает тот же dict (мутирует). Нет quant_inputs → computed с пустыми секциями."""
    if not isinstance(macro, dict):
        return macro
    macro["computed"] = compute(macro.get("quant_inputs") or {})
    return macro
