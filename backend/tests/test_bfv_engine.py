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


def test_engine_router():
    """Маршрутизатор уводит непригодные для BFV-D профили в BFV-F (поправка v1.1 §0.2)."""
    from app.services.bfv.engine import select_engine
    assert select_engine(bvps=-50, roe=0.20, pb=None, payout=0.9) == "BFV-F"       # отриц. капитал
    assert select_engine(bvps=279, roe=1.11, pb=10.0, payout=1.0) == "BFV-F"       # asset-light
    assert select_engine(bvps=100, roe=0.02, pb=0.5, payout=0.0) == "BFV-F"        # ROE ниже роста
    assert select_engine(bvps=100, roe=0.22, pb=1.0, payout=0.5) == "BFV-D"        # ядро
    assert select_engine(bvps=100, roe=0.24, pb=0.9, payout=0.5, is_bank=True) == "BFV-D"


def test_bank_golden():
    """Банк с достаточностью выше целевой ОБЯЗАН иметь ненулевую ёмкость (закрывает
    ошибку инициализации CET1: Сбер давал 0.4% дивдоходности)."""
    from app.services.bfv.engine import Params, project_flows
    p = Params(is_bank=True, cet1_ratio0=0.13, cet1_target=0.11, rwa_growth=0.10,
               roe0=0.24, roe_terminal=0.20, payout0=0.50)
    flows, _bvps, _ = project_flows(p)
    assert flows[0] / p.bv0 > 0.03, "ёмкость банка обнулена — проверьте мост CET1"
    assert flows[0] > 0 and flows[5] > 0


def test_bfv_f_grows_with_full_payout():
    """BFV-F: компания со 100% payout может расти (в BFV-D это невозможно) — поток
    должен возрастать при положительном росте выручки (поправка v1.1 §3)."""
    from app.services.bfv.engine import ParamsF, project_flows_fcfe
    f = ParamsF(revenue0=560.0, g_revenue0=0.28, margin0=0.33, margin_terminal=0.22,
                sales_to_capital=7.0, payment_fraction=1.0, p_willingness=1.0,
                h_distress=0.0, h_expropriation=0.0)
    flows = project_flows_fcfe(f)
    assert flows[3] > flows[0], "поток BFV-F должен расти при росте выручки"
