"""Живой прогон BFV-D при рыночной цене (§11-§13).

Порядок (один проход, без итераций — потоки НЕ зависят от порога, §10.2):
  1. компилятор params.py → вектор ожидаемого потока E[CF_t] (кэшируем на компанию);
  2. solve_rate(flows, live_price) → ожидаемая доходность r (только цена, без порога);
  3. duration(flows, r) → эффективная дюрация;
  4. z_dur = кривая ОФЗ на этой дюрации (живая, ZCYC MOEX);
  5. hurdle = z_dur + β_live·RequiredSpread;
  6. справедливая цена = pv(flows, hurdle); вердикт r ≥ hurdle; доходность удержания.

«Живое» = цена (quotes), кривая ОФЗ, β (company_metrics), RequiredSpread (настройка).
«Застывшее» = параметры-суждения из params.py. Тестовая версия v1 (методика §22:
без калибровки на росс. данных) — выход помечается статусом expert.
"""
from __future__ import annotations

import logging

from app.services.bfv import engine as E
from app.services.bfv.params import compile_params

logger = logging.getLogger(__name__)

# §11: RequiredSpread — заявленный порог сверх ОФЗ, ОДНО число на платформу,
# продуктовая политика (не расчётная величина), пользователь-настраиваемая.
# Эталон методики (§17, банк ROE 30%) берёт 8 п.п., но при РОССИЙСКОЙ безрисковой
# ставке ~14% требовать +8 п.п. сверху (=22% требуемой доходности) чрезмерно жёстко:
# на такой планке почти весь рынок «переоценён» (медиана апсайда −36% на вселенной).
# Дефолт платформы — 5 п.п. (=~19% требуемой при текущей ОФЗ): сбалансированное
# распределение (медиана апсайда ~−19%, порог проходит ~39%), обоснование — уже очень
# высокая базовая ставка поглощает часть премии за риск. Пользователь может менять.
DEFAULT_REQUIRED_SPREAD = 0.05
_HOLDING_HORIZON = 10           # §12: дефолтный горизонт удержания


def _ofz_at_duration(curve: list[tuple[float, float]], years: float) -> float | None:
    """Линейная интерполяция доходности ОФЗ на сроке `years` по точкам G-кривой
    [(срок_лет, доходность_дробью), ...]. Тот же метод, что moex_dividends.py."""
    if not curve:
        return None
    c = sorted(curve)
    if years <= c[0][0]:
        return c[0][1]
    if years >= c[-1][0]:
        return c[-1][1]
    for (x0, y0), (x1, y1) in zip(c, c[1:]):
        if x0 <= years <= x1:
            return y0 + (y1 - y0) * (years - x0) / (x1 - x0)
    return c[-1][1]


def compute_bfv(fin: dict, gov: dict, inst: dict, barometer: dict, *,
                shares_outstanding: float | None, live_price: float | None,
                ofz_curve: list[tuple[float, float]] | None, beta: float | None,
                required_spread: float = DEFAULT_REQUIRED_SPREAD,
                overrides: dict | None = None) -> dict | None:
    """Полный расчёт BFV для компании. None — если нет данных для расчёта
    (нет BVPS/ROE/цены/кривой). Возвращает словарь для карточки/скрининга."""
    comp = compile_params(fin, gov, inst, barometer, shares_outstanding, overrides)
    params = comp["params"]
    scenarios = comp["scenarios"]
    if params is None:
        return {"status": "no_data", "warnings": comp["warnings"]}
    if not live_price or live_price <= 0:
        return {"status": "no_price", "warnings": comp["warnings"] + ["нет живой цены"]}

    # 1. поток
    try:
        flows, exp_bv = E.expected_flows(params, scenarios)
    except Exception as e:  # noqa: BLE001
        logger.warning("BFV: ошибка расчёта потока: %s", e)
        return {"status": "engine_error", "warnings": [f"движок: {type(e).__name__}"]}

    if any(cf < -1e-9 for cf in flows):
        return {"status": "engine_error", "warnings": ["отрицательный поток акционеру"]}

    # 2. ожидаемая доходность при живой цене
    try:
        r = E.solve_rate(flows, live_price)
    except ValueError as e:
        # поток не окупает цену ни при какой ставке (катастрофический профиль) или
        # доходность вне диапазона поиска — честно сообщаем, не выдумываем число
        return {"status": "no_rate", "reason": str(e),
                "fair_price": round(E.pv(flows, DEFAULT_REQUIRED_SPREAD + 0.10), 2),
                "warnings": comp["warnings"]}

    # 3-5. дюрация → z_dur → порог
    dur = E.duration(flows, r)
    z_dur = _ofz_at_duration(ofz_curve or [], dur)
    if z_dur is None:
        return {"status": "no_curve", "warnings": comp["warnings"] + ["нет кривой ОФЗ"]}
    b = float(beta) if isinstance(beta, (int, float)) and beta > 0 else 1.0
    beta_defaulted = not (isinstance(beta, (int, float)) and beta > 0)
    hurdle = E.hurdle(z_dur, b, required_spread)

    # 6. выходы
    fair_price = E.pv(flows, hurdle)
    try:
        r_hold = E.holding_return(flows, exp_bv, live_price, _HOLDING_HORIZON, live_price / params.bv0)
    except ValueError:
        r_hold = None
    tv_share, tv_status = E.check_tv_share(flows, hurdle, params.T_forecast)

    warnings = list(comp["warnings"])
    if beta_defaulted:
        warnings.append("нет живой беты — порог по β=1.0")

    upside_pct = (fair_price / live_price - 1.0) * 100.0
    # Экстремальный апсайд у бумаг с глубоким дисконтом к балансу — как правило
    # «ловушка стоимости»: рынок закладывает, что балансовая ценность не дойдёт до
    # миноритария (размытие, госконтроль, вывод). Дивидендный движок этого полностью
    # не видит (willingness-калибровка требует КТ-2, §22) — честно помечаем.
    # reliability=low → фронт приглушает число и показывает оговорку вместо чистого
    # «+1000%» (§15/§23: относительное сравнение важнее абсолютного вердикта).
    reliability = "normal"
    if upside_pct > 100:
        warnings.append("глубокий дисконт к балансу — возможна ловушка стоимости; "
                        "оценка чувствительна к willingness (без калибровки, §22)")
        reliability = "low"
    if tv_share > 0.85:
        warnings.append(f"доля терминальной фазы {tv_share*100:.0f}% — оценка крайне "
                        "чувствительна к терминальным допущениям (§15)")
        reliability = "low"
    return {
        "status": "ok",
        "expected_return_pct": round(r * 100, 2),
        "hurdle_pct": round(hurdle * 100, 2),
        "spread_to_hurdle_pp": round((r - hurdle) * 100, 2),
        "spread_to_ofz_pp": round((r - z_dur) * 100, 2),
        "verdict": "проходит" if r >= hurdle else "не проходит",
        "fair_price": round(fair_price, 2),
        "current_price": round(live_price, 2),
        "upside_pct": round(upside_pct, 1),
        "holding_return_pct": round(r_hold * 100, 2) if r_hold is not None else None,
        "revaluation_component_pp": round((r - r_hold) * 100, 2) if r_hold is not None else None,
        "div_yield_y1_pct": round(flows[0] / live_price * 100, 2),
        "effective_duration_y": round(dur, 2),
        "z_dur_pct": round(z_dur * 100, 2),
        "beta_used": round(b, 3),
        "required_spread_pp": round(required_spread * 100, 1),
        "terminal_share_pct": round(tv_share * 100, 1),
        "terminal_status": tv_status,
        "reliability": reliability,
        "base_meta": comp["base_meta"],
        "warnings": warnings,
        "method": "BFV-D v1 (тестовая, экспертные параметры без калибровки)",
    }
