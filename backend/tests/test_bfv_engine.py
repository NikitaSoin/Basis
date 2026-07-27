"""Тесты движка BFV-D (§17 золотой, §19 свойственные и негативные).

Золотой тест — регрессионный якорь: воспроизводит эталонные выходы §17 методики
с допуском ±0.05 п.п. для ставок и ±0.1 для стоимостных величин. Если он краснеет
после правки engine.py — расчётная логика изменилась, это НЕ должно происходить
незаметно."""
from dataclasses import replace

import pytest

from app.services.bfv.engine import (
    Params, bank_capacity, project_flows, expected_flows, solve_rate, pv,
    check_ri_equivalence, average_rates_forbidden, check_hazard_mode,
    golden_case, run_golden,
)


def test_golden():
    got = run_golden()
    expect = {
        "ожидаемая доходность, %": 23.50,
        "эффективная дюрация, лет": 8.56,
        "порог, %": 23.20,
        "справедливая цена при пороге": 97.03,
        "див. доходность 1-го года, %": 9.18,
        "доходность удержания 10 лет, %": 24.70,
        "компонента переоценки, п.п.": -1.19,
        "доля терминальной фазы, %": 13.07,
        "стоимость рва": -7.86,
    }
    for k, v in expect.items():
        tol = 0.05 if "%" in k or "п.п." in k else 0.1
        assert abs(got[k] - v) <= tol, f"{k}: получено {got[k]:.3f}, ожидалось {v} (допуск {tol})"
    assert got["вердикт"] == "проходит"


def test_property_terminal_identity():
    """payout_L = 1 − g/ROE выполняется, рост на выходе сходится к g_terminal."""
    p = Params()
    flows, _bvps, _eps = project_flows(replace(p, h_distress=0, h_expropriation=0,
                                               p_willingness=1.0, payment_fraction=1.0))
    g_late = flows[-1] / flows[-2] - 1.0
    assert abs(g_late - p.g_terminal) < 1e-4, f"терминальный рост {g_late:.5f} ≠ {p.g_terminal}"


def test_property_ri_equivalence():
    """Дивидендный и остаточно-доходный расчёты совпадают на бессобытийной траектории."""
    diff = check_ri_equivalence(Params(), 0.232)
    assert diff < 1e-6, f"расхождение DDM/RI = {diff:.9f}"


def test_property_unique_root():
    base, scen, price, *_ = golden_case()
    cf, _ = expected_flows(base, scen)
    r = solve_rate(cf, price)
    assert abs(pv(cf, r) - price) < 1e-6
    assert pv(cf, r - 0.01) > price and pv(cf, r + 0.01) < price, "PV не монотонна"


def test_negative_rate_averaging():
    with pytest.raises(NotImplementedError):
        average_rates_forbidden()


def test_negative_hazard_sum():
    with pytest.raises(ValueError):
        check_hazard_mode([0.10, 0.15, 0.05], approx=True)


def test_negative_bad_probabilities():
    base, scen, *_ = golden_case()
    bad = [replace(scen[0], prob=0.5)] + scen[1:]
    with pytest.raises(ValueError):
        expected_flows(base, bad)


def test_negative_catastrophic_irr():
    """В катастрофическом состоянии ставка не существует — solve_rate обязан отказать."""
    cf = [5.0] + [0.0] * 49
    with pytest.raises(ValueError):
        solve_rate(cf, 95.0)


def test_bank_capacity_no_double_count():
    cet1_pre = 13.0 + 3.0     # капитал прошлого года + прибыль
    cap = bank_capacity(cet1_pre, rwa=110.0, target_ratio=0.11)
    assert abs(cap - (16.0 - 12.1)) < 1e-9
