"""Живой прогон BFV при рыночной цене (§11-§13) с маршрутизацией движков (поправка v1.1).

Маршрутизация ДО расчёта (select_engine): банки и книга-якорные бизнесы → BFV-D
(поток от дивидендов и книги); растущие/asset-light/отр.капитал → BFV-F (поток от
выручки). Компания вне области BFV-D не помечается «ненадёжно» — она честно считается
ДРУГИМ движком (v1.1 §0.2: «для этого класса бизнеса применяется другой метод»).

Общий хвост обоих движков (§11-§13): solve_rate от живой цены → дюрация → z_dur с
живой кривой ОФЗ → порог с живой бетой → справедливая цена = pv(flows, hurdle).

«Живое» = цена (quotes), кривая ОФЗ, β (company_metrics), RequiredSpread (настройка).
Тестовая версия: параметры экспертные, без калибровки на росс. данных (§22).
"""
from __future__ import annotations

import logging

from app.services.bfv import engine as E
from app.services.bfv.params import (compile_params, compile_params_f, _resolve_roe)

logger = logging.getLogger(__name__)

# §11: RequiredSpread — заявленный порог сверх ОФЗ. Дефолт 5 п.п. (при ОФЗ ~15%
# требовать +8 чрезмерно). v1.1 §6: полоса и дефолт пересмотрены под режим ставок.
DEFAULT_REQUIRED_SPREAD = 0.05
_HOLDING_HORIZON = 10


def _ofz_at_duration(curve: list[tuple[float, float]], years: float) -> float | None:
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


def _route(fin: dict) -> tuple[str, dict]:
    """Выбор движка (v1.1 §0.2). Возвращает (engine, diag с bvps/roe/pb/is_bank)."""
    is_bank = bool(fin.get("bank_pnl") or fin.get("bank_metrics"))
    roe, _ = _resolve_roe(fin)
    pb = (fin.get("multiples", {}).get("current", {}) or {}).get("pb")
    # bvps: явный или из цена/P·B (единично-безопасно)
    from app.services.bfv.params import _last_valid
    bvps = _last_valid(fin.get("balance_sheet", {}).get("book_value_per_share"))
    if bvps is None or bvps <= 0:
        last_price = fin.get("meta", {}).get("last_price")
        if isinstance(pb, (int, float)) and pb > 0 and isinstance(last_price, (int, float)) and last_price > 0:
            bvps = last_price / pb
    engine = E.select_engine(bvps=bvps, roe=roe, pb=pb, payout=None, is_bank=is_bank)
    return engine, {"bvps": bvps, "roe": roe, "pb": pb, "is_bank": is_bank}


def compute_bfv(fin: dict, gov: dict, inst: dict, barometer: dict, *,
                market: dict | None = None,
                shares_outstanding: float | None, live_price: float | None,
                ofz_curve: list[tuple[float, float]] | None, beta: float | None,
                required_spread: float = DEFAULT_REQUIRED_SPREAD,
                overrides: dict | None = None) -> dict | None:
    """Полный расчёт BFV с маршрутизацией. status: ok / no_data / no_price / no_rate."""
    market = market or {}
    engine, diag = _route(fin)

    # --- компиляция под выбранный движок ---
    if engine == "BFV-F":
        comp = compile_params_f(fin, gov, inst, barometer, market, shares_outstanding, overrides)
        method = "BFV-F v1.1 (от денежного потока; тестовая, без калибровки §22)"
    else:
        comp = compile_params(fin, gov, inst, barometer, shares_outstanding, overrides)
        method = "BFV-D v1.1 (дивидендно-балансовая; тестовая, без калибровки §22)"
    params = comp["params"]
    if params is None:
        return {"status": "no_data", "engine": engine, "warnings": comp["warnings"]}
    if not live_price or live_price <= 0:
        return {"status": "no_price", "engine": engine, "warnings": comp["warnings"] + ["нет живой цены"]}

    # --- поток по движку ---
    exp_bv = None
    try:
        if engine == "BFV-F":
            flows = E.expected_flows_f(params, comp["scenarios"], price_pre_event=live_price)
        else:
            flows, exp_bv = E.expected_flows(params, comp["scenarios"])
    except Exception as e:  # noqa: BLE001
        logger.warning("BFV: ошибка расчёта потока (%s): %s", engine, e)
        return {"status": "engine_error", "engine": engine, "warnings": [f"движок: {type(e).__name__}"]}

    if any(cf < -1e-9 for cf in flows):
        return {"status": "no_data", "engine": engine,
                "warnings": ["отрицательный поток акционеру (убыточная/раздаёт из долга) — оценка неинформативна"]}
    if all(cf <= 1e-12 for cf in flows):
        return {"status": "no_data", "engine": engine,
                "warnings": ["нулевой поток к миноритарию — оценка неинформативна"]}

    # --- ожидаемая доходность при живой цене ---
    # Границы: если поток не окупает цену даже при ~0% — доходность НИЖЕ пола (бумага
    # глубоко переоценена по модели); если PV при 200% всё ещё > цены — доходность ВЫШЕ
    # потолка (глубоко недооценена/ловушка). В обоих случаях справедливая цена и апсайд
    # всё равно считаются (они не требуют r) — не теряем компанию в no_rate, а честно
    # отмечаем границу.
    _LO, _HI = 0.0005, 2.0
    r = None
    r_bound = None  # 'below' | 'above'
    try:
        r = E.solve_rate(flows, live_price, lo=_LO, hi=_HI)
    except ValueError:
        if E.pv(flows, _LO) < live_price:
            r_bound = "below"          # доходность < 0.05% — глубокая переоценка
        else:
            r_bound = "above"          # доходность > 200% — глубокая недооценка/ловушка

    # --- дюрация → z_dur → порог ---
    # Для граничных случаев r нет — берём типовую дюрацию потока (7 лет) как ориентир
    # для точки кривой ОФЗ; порог и вердикт по границе однозначны и без точного r.
    dur = E.duration(flows, r) if r is not None else 7.0
    z_dur = _ofz_at_duration(ofz_curve or [], dur)
    if z_dur is None:
        return {"status": "no_curve", "engine": engine, "warnings": comp["warnings"] + ["нет кривой ОФЗ"]}
    b = float(beta) if isinstance(beta, (int, float)) and beta > 0 else 1.0
    beta_defaulted = not (isinstance(beta, (int, float)) and beta > 0)
    hurdle = E.hurdle(z_dur, b, required_spread)

    fair_price = E.pv(flows, hurdle)
    upside_pct = (fair_price / live_price - 1.0) * 100.0

    warnings = list(comp["warnings"])
    if beta_defaulted:
        warnings.append("нет живой беты — порог по β=1.0")

    # --- ОБРАТНЫЙ РЕЖИМ для ловушек стоимости (v1.1 §5) ---
    # Вместо «справедливо +N00%» — что должно быть верно, чтобы текущая цена была
    # справедливой: поток к миноритарию ниже расчётного на X% (недоверие рынка к
    # балансу/выплатам). Честно и без калибровки. Триггер — P/B < 0.6 (любой движок:
    # рынок дисконтирует книгу/поток) ИЛИ неправдоподобно высокий апсайд BFV-F без
    # P/B-якоря (тонкий free-float / префы / искажённая выручка-на-акцию — прямой счёт
    # ненадёжен, показываем «что должно быть верно», а не «+N00%»).
    pb = diag["pb"]
    reverse = None
    pb_low = isinstance(pb, (int, float)) and 0 < pb < 0.6
    bfv_f_no_anchor = engine == "BFV-F" and pb is None and upside_pct > 200
    if fair_price > live_price and (pb_low or bfv_f_no_anchor):
        implied_haircut = (1.0 - live_price / fair_price) * 100.0
        if pb_low:
            why = (f"рынок закладывает недоверие к балансу или к готовности распределять "
                   f"(P/B {pb:.2f})")
        else:
            why = ("нет P/B-якоря (преф / тонкий free-float), прямой счёт от выручки-на-акцию "
                   "ненадёжен")
        reverse = {
            "implied_haircut_pct": round(implied_haircut, 0),
            "note": (f"Чтобы текущая цена была справедливой, поток к миноритарию должен быть "
                     f"на ~{round(implied_haircut)}% ниже расчётного — {why}. Прямая оценка — "
                     f"справочно, ниже."),
        }

    # --- надёжность / пометки ---
    reliability = "normal"
    if reverse is not None:
        reliability = "low"
    tv_share, tv_status = E.check_tv_share(flows, hurdle, params.T_forecast if hasattr(params, "T_forecast") else 15)
    if tv_share > 0.85:
        warnings.append(f"доля терминальной фазы {tv_share*100:.0f}% — оценка крайне "
                        "чувствительна к терминальным допущениям (§15)")
        reliability = "low"
    # убыточная BFV-F компания на грани — уже отсеяна выше (отриц/нулевой поток)

    # Граничные случаи: r за пределами [_LO, _HI]. Для числовых полей берём границу как
    # прокси, вердикт по границе однозначен, флаг return_bound для честной подписи
    # («доходность < 0.5%» / «> 200%»). Справедливая цена/апсайд уже посчитаны от hurdle.
    return_bound = r_bound
    if r is None:
        r = _LO if r_bound == "below" else _HI
        if r_bound == "below":
            warnings.append("поток не окупает цену даже при ~0% — глубокая переоценка по модели (доходность < 0.5%)")
        else:
            warnings.append("доходность выше 200% — глубокая недооценка/ловушка стоимости (см. обратный режим)")
        reliability = "low"

    r_hold = None
    if engine == "BFV-D" and exp_bv is not None and return_bound is None:
        try:
            r_hold = E.holding_return(flows, exp_bv, live_price, _HOLDING_HORIZON, live_price / params.bv0)
        except ValueError:
            r_hold = None

    return {
        "status": "ok",
        "engine": engine,
        "expected_return_pct": round(r * 100, 2),
        "return_bound": return_bound,
        "hurdle_pct": round(hurdle * 100, 2),
        "spread_to_hurdle_pp": round((r - hurdle) * 100, 2),
        "spread_to_ofz_pp": round((r - z_dur) * 100, 2),
        "verdict": ("проходит" if return_bound == "above" else "не проходит") if return_bound
                   else ("проходит" if r >= hurdle else "не проходит"),
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
        "reverse": reverse,
        "base_meta": comp["base_meta"],
        "warnings": warnings,
        "method": method,
    }
