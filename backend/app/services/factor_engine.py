"""Движок «экспозиция → ценовой эффект» (методика §3.4) — общий источник для
MGI (сценарная устойчивость), forward-ERR (сценарная ожидаемая доходность) и
вкладки «Стресс-тест» (не реализована в этом батче, задел на будущее).

Один расчёт, несколько потребителей — принцип №2 методики (единый факторный
каркас, чтобы три модуля не поддерживали три расходящихся набора суждений).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.factor_exposures import FACTOR_KEYS, get_company_exposures

_SCENARIOS_PATH = Path(__file__).parent.parent.parent / "config" / "quality_scenarios.json"

# При полном стресс-движении фактора (интенсивность=1): |Exp|=2 → ±15% цены,
# |Exp|=1 → ±7%, 0 → 0 (методика §3.4, произвол).
_EFFECT_BY_ABS_EXP = {0: 0.0, 1: 0.07, 2: 0.15}
_REACTION_CAP = (-0.70, 0.60)


def load_scenarios() -> list[dict]:
    try:
        data = json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))
        return data.get("scenarios") or []
    except Exception:  # noqa: BLE001
        return []


def _price_effect(exp: float) -> float:
    sign = 1 if exp >= 0 else -1
    a = min(round(abs(exp)), 2)
    return sign * _EFFECT_BY_ABS_EXP[a]


def company_scenario_reaction(exposures: dict[str, float | None], intensities: dict[str, float]) -> float:
    """R(i, сценарий) = Σₖ интенсивность(k)×эффект(Exp(i,k)), кап [-70%;+60%]."""
    total = 0.0
    for factor, intensity in intensities.items():
        exp = exposures.get(factor)
        if exp is None or intensity == 0:
            continue
        total += intensity * _price_effect(exp)
    return max(_REACTION_CAP[0], min(_REACTION_CAP[1], total))


def portfolio_scenario_losses(tickers_weights: dict[str, float]) -> dict:
    """Для каждого сценария — Loss = -Σ wᵢ·R(i,сценарий), только по компаниям с
    хотя бы одной покрытой экспозицией (честная деградация, доля покрытия
    видна отдельно через factor_exposures.get_portfolio_exposures)."""
    scenarios = load_scenarios()
    if not scenarios or not tickers_weights:
        return {}
    tot_w = sum(tickers_weights.values())
    if tot_w <= 0:
        return {}
    per_company_exp = {t: get_company_exposures(t) for t in tickers_weights}
    out = {}
    for sc in scenarios:
        key = sc["key"]
        intensities = sc.get("intensities") or {}
        if not intensities:  # базовый — по определению без потерь
            out[key] = {"loss_pct": 0.0, "reaction_by_company": {}}
            continue
        num = 0.0
        covered_w = 0.0
        reactions = {}
        for t, w in tickers_weights.items():
            exp = per_company_exp.get(t, {})
            if not any(v is not None for k, v in exp.items() if k in intensities):
                continue  # компания не покрыта ни по одному фактору сценария
            r = company_scenario_reaction(exp, intensities)
            reactions[t] = round(r * 100, 1)
            num += w * r
            covered_w += w
        loss_pct = round(-num / tot_w * 100, 1) if tot_w else None
        out[key] = {"loss_pct": loss_pct, "reaction_by_company": reactions,
                     "coverage_pct": round(covered_w / tot_w * 100, 1) if tot_w else 0.0}
    return out


def expected_scenario_return(tickers_weights: dict[str, float], upside_by_ticker: dict[str, float | None],
                             div_yield_by_ticker: dict[str, float | None], horizon_years: float = 3.0) -> dict:
    """Форвардная сценарная ожидаемая доходность (методика §9, forward-ERR).
    R(i,base) — конвергенция к FV за horizon_years + форвардная дивдоходность;
    bear/stress — из факторного движка (тот же, что MGI); bull — от base+10пп
    произвольно (упрощение MVP: optimistic-FV bull не считаем отдельно)."""
    scenarios = load_scenarios()
    if not scenarios or not tickers_weights:
        return {}
    per_company_exp = {t: get_company_exposures(t) for t in tickers_weights}
    tot_w = sum(tickers_weights.values())
    if tot_w <= 0:
        return {}
    e_r_by_scenario = {}
    for sc in scenarios:
        key = sc["key"]
        intensities = sc.get("intensities") or {}
        num = 0.0
        for t, w in tickers_weights.items():
            upside = upside_by_ticker.get(t)
            div = div_yield_by_ticker.get(t) or 0.0
            if upside is None:
                continue
            base_r = (1 + upside) ** (1 / horizon_years) - 1 + div
            if key == "base":
                r = base_r
            elif key == "bull":
                r = base_r + 0.10
            else:
                r = base_r + company_scenario_reaction(per_company_exp.get(t, {}), intensities)
            num += w * r
        e_r_by_scenario[key] = num / tot_w if tot_w else None
    e_r = sum(sc["probability"] * (e_r_by_scenario.get(sc["key"]) or 0) for sc in scenarios)
    return {"by_scenario": e_r_by_scenario, "expected": e_r}
