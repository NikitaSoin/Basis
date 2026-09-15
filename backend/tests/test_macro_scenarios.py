"""Расчётный модуль макросценариев: арифметика по контракту docs/macro_model_contract_v1.md."""
from app.services import macro_scenarios as ms


def _cfg():
    return {
        "as_of": "2026-08-31", "display_years": [2027], "tab_years": [2027],
        "base_period": {"year": 2025, "values": {"key_rate_avg": 19.2, "usdrub_avg": 83.3, "oil_tax_price": 56, "gdp": 1.0}},
        "scenarios": [
            {"id": "base", "name": "Базовый", "years": {"2027": {"key_rate_avg": {"low": 10.5, "high": 12.5}, "oil_tax_price": 50, "gdp": {"low": 1.5, "high": 2.5}}},
             "completions": {"usdrub_avg": {"2027": {"low": 84, "high": 92}}}},
            {"id": "risk", "name": "Рисковый", "years": {"2027": {"key_rate_avg": {"low": 19, "high": 21}, "oil_tax_price": 35, "gdp": {"low": -4, "high": -3}}},
             "completions": {"usdrub_avg": {"2027": {"low": 105, "high": 125}}}},
        ],
    }


def _model():
    return {
        "base_financials": {"year": 2025, "revenue": 1000.0, "ebitda": 300.0, "net_profit_adjusted": 100.0, "net_profit_reported": 80.0},
        "coefficients": [
            {"id": "fx", "label": "Курс", "macro_var": "usdrub_avg", "per": "+1 руб./$",
             "effects": {"revenue": {"base": 5, "low": 4, "high": 6}, "net_profit": {"base": 1, "low": 0.5, "high": 1.5}},
             "asymmetry": {"up_multiplier": 1.0, "down_multiplier": 0.5}, "origin": "выведено из структуры", "credibility": 2, "derivation": "x"},
            {"id": "rate_debt", "label": "Ставка → проценты", "macro_var": "key_rate_avg", "per": "+1 п.п.",
             "effects": {"net_profit": {"base": -2, "low": -2.5, "high": -1.5}},
             "thresholds": [{"variable": "key_rate_avg", "condition": "above", "level": 18, "multiplier": 1.5}],
             "origin": "выведено из структуры", "credibility": 2, "derivation": "y"},
            {"id": "oil", "label": "Нефть", "macro_var": "oil_tax_price", "per": "+1 долл.",
             "effects": {"revenue": {"base": 10, "low": 8, "high": 12}, "net_profit": {"base": 2, "low": 1.5, "high": 2.5}},
             "origin": "раскрыто компанией", "credibility": 1, "derivation": "z"},
        ],
        "modifiers": [
            {"id": "wedge", "kind": "geo", "label": "Клин", "applies_to": "line:net_profit", "mode": "add_bn",
             "by_scenario": {"base": 0, "risk": {"low": -30, "high": -10}, "most_dangerous": -40}, "origin": "принято допущением", "credibility": 3},
            {"id": "damper", "kind": "inst", "label": "Демпфер", "applies_to": "coefficient:oil", "mode": "multiply_coef",
             "by_scenario": {"risk": 0.5}, "origin": "принято допущением", "credibility": 3},
        ],
        "valuation_link": {"required_return_pct": 20.0, "terminal_growth_pct": 4.0, "rate_to_required_return_passthrough": {"low": 0.4, "high": 0.8}},
        "most_dangerous": {"adverse_values": {"usdrub_avg": 70, "key_rate_avg": 22, "oil_tax_price": 30}, "break_points": ["ковенант"]},
    }


def test_base_scenario_contributions_and_ranges():
    res = ms.run_scenarios(_model(), _cfg())
    y = res["base"]["years"]["2027"]
    npf = y["lines"]["net_profit"]
    # курс: (88−83.3)=+4.7 × 1 = +4.7; ставка: (11.5−19.2)=−7.7 × −2 = +15.4 (порог не сработал); нефть: (50−56)=−6 × 2 = −12
    assert abs(npf["delta"]["base"] - (4.7 + 15.4 - 12.0)) < 0.2
    assert npf["delta"]["low"] <= npf["delta"]["base"] <= npf["delta"]["high"]
    assert npf["value"]["base"] == round(100.0 + npf["delta"]["base"], 1)
    ids = [c["id"] for c in npf["contributions"]]
    assert set(ids) == {"fx", "rate_debt", "oil"}  # модификатор base=0 не попадает
    assert npf["dominant_factor_id"] == "rate_debt"
    rev = y["lines"]["revenue"]
    assert abs(rev["delta"]["base"] - (4.7 * 5 - 60)) < 0.2
    assert rev["pct"]["base"] == round(rev["delta"]["base"] / 1000 * 100, 1)
    assert "ebitda" in y["lines"]  # база есть, коэффициентов нет → Δ = 0
    assert y["lines"]["ebitda"]["delta"]["base"] == 0.0


def test_risk_scenario_threshold_asymmetry_modifiers():
    res = ms.run_scenarios(_model(), _cfg())
    y = res["risk"]["years"]["2027"]
    npf = y["lines"]["net_profit"]
    by = {c["id"]: c for c in npf["contributions"]}
    # ставка 20 > порога 18 → ×1.5: (20−19.2)=0.8 × −2 × 1.5 = −2.4
    assert abs(by["rate_debt"]["base"] - (-2.4)) < 0.05
    assert any("порог" in n for n in by["rate_debt"]["notes"])
    # курс вверх (115−83.3=31.7) — множитель вверх 1.0 → +31.7
    assert abs(by["fx"]["base"] - 31.7) < 0.05
    # нефть: (35−56)=−21 × 2 × 0.5 (модификатор-множитель) = −21
    assert abs(by["oil"]["base"] - (-21.0)) < 0.05
    # аддитивный модификатор: середина диапазона −20, диапазон −30…−10
    assert by["wedge"]["is_modifier"] and abs(by["wedge"]["base"] + 20) < 0.05
    assert by["wedge"]["low"] == -30 and by["wedge"]["high"] == -10
    assert sum(c["width_share_pct"] for c in npf["contributions"]) > 99.0


def test_asymmetry_down_and_most_dangerous():
    m = _model()
    md = ms.run_most_dangerous(m, _cfg())
    by = {c["id"]: c for c in md["lines"]["net_profit"]["contributions"]}
    # курс вниз: (70−83.3)=−13.3 × 1 × 0.5 = −6.65
    assert abs(by["fx"]["base"] + 6.65) < 0.05
    # ставка 22 > 18: (22−19.2)=2.8 × −2 × 1.5 = −8.4; нефть (30−56)=−26 × 2 = −52; клин −40
    assert abs(by["rate_debt"]["base"] + 8.4) < 0.05
    assert abs(by["oil"]["base"] + 52) < 0.05
    assert abs(by["wedge"]["base"] + 40) < 0.05
    assert md["lines"]["net_profit"]["value"]["base"] < 0
    assert any("убыток" in f for f in md["flags"])
    assert md["break_points"] == ["ковенант"]


def test_anchors_and_rate_valuation():
    a = {x["anchor_id"]: x for x in ms.anchors(_model(), _cfg())}
    # курс: шаг 10% от 83.3 = 8.33 → выручка +41.65, прибыль +8.33
    assert abs(a["fx"]["effects_bn"]["revenue"]["base"] - 41.65) < 0.11
    # базовая ставка 19.2 уже выше порога 18 → привязка считается с множителем 1.5: −2 × 1.5 = −3
    assert a["rate_debt"]["step"] == 1.0 and a["rate_debt"]["effects_bn"]["net_profit"]["base"] == -3.0
    assert any("порог" in n for n in a["rate_debt"]["notes"])
    assert a["oil"]["step"] == 10.0 and a["oil"]["effects_bn"]["net_profit"]["base"] == 20.0
    rv = ms.rate_valuation(_model(), _cfg())
    # −перенос/(r−g): 0.8/16 = −5.0%; 0.4/16 = −2.5%; канал прибыли: −2/100 = −2.0%
    assert rv["valuation_channel_pct"] == {"low": -5.0, "high": -2.5, "formula": rv["valuation_channel_pct"]["formula"], "r_pct": 20.0, "g_pct": 4.0, "passthrough": {"low": 0.4, "high": 0.8}}
    assert rv["profit_channel_pct"]["base"] == -2.0
    assert rv["total_pct"] == {"low": -7.5, "high": -4.0}


def test_integrity_checks_catch_bad_objects():
    m = _model()
    m["coefficients"][0]["effects"]["revenue"] = {"base": 9, "low": 4, "high": 6}
    m["coefficients"][1].pop("derivation")
    m["coefficients"][2]["credibility"] = 5
    issues = ms.integrity_checks(m)
    assert any("вне диапазона" in i for i in issues)
    assert any("derivation" in i for i in issues)
    assert any("достоверности" in i for i in issues)
    assert not ms.integrity_checks(_model())


def test_sustainable_profit_base_overrides_adjusted():
    m = _model()
    m["base_financials"]["net_profit_base"] = 200.0
    m["base_financials"]["base_bridge"] = [{"label": "резерв", "amount": 100.0}]
    res = ms.run_scenarios(m, _cfg())
    npf = res["base"]["years"]["2027"]["lines"]["net_profit"]
    assert npf["base_year_value"] == 200.0
    assert npf["value"]["base"] == round(200.0 + npf["delta"]["base"], 1)
    rv = ms.rate_valuation(m, _cfg())
    assert rv["profit_channel_pct"]["base"] == -1.0  # −2 / 200


def test_shared_variable_uses_one_value_per_set():
    """Два встречных канала одной переменной (ставка → активы +, ставка → пассивы −) не должны
    оцениваться при разных значениях ставки внутри одного набора."""
    m = _model()
    m["coefficients"] = [
        {"id": "assets", "label": "Переоценка активов", "macro_var": "key_rate_avg", "per": "+1 п.п.",
         "effects": {"net_profit": {"base": 100, "low": 100, "high": 100}}, "origin": "выведено из структуры", "credibility": 2, "derivation": "a"},
        {"id": "liabs", "label": "Переоценка пассивов", "macro_var": "key_rate_avg", "per": "+1 п.п.",
         "effects": {"net_profit": {"base": -80, "low": -80, "high": -80}}, "origin": "выведено из структуры", "credibility": 2, "derivation": "b"},
    ]
    m["modifiers"] = []
    res = ms.run_scenarios(m, _cfg())
    npf = res["base"]["years"]["2027"]["lines"]["net_profit"]
    # ставка 10.5…12.5 против базы 19.2: Δ = −8.7…−6.7; нетто 20 × Δ → −174…−134; база −154
    assert abs(npf["delta"]["base"] + 154) < 0.5
    assert abs(npf["delta"]["low"] + 174) < 0.5 and abs(npf["delta"]["high"] + 134) < 0.5
    by = {c["id"]: c for c in npf["contributions"]}
    assert by["assets"]["var_value_in_low_set"] == by["liabs"]["var_value_in_low_set"]
    assert abs(sum(c["low"] for c in npf["contributions"]) - npf["delta"]["low"]) < 0.5


def test_excluded_variables_are_held_at_base():
    cfg = _cfg(); cfg["excluded_variables"] = ["oil_tax_price"]; cfg["core_variables"] = ["key_rate_avg", "usdrub_avg"]
    m = _model()
    res = ms.run_scenarios(m, cfg)
    y = res["base"]["years"]["2027"]
    assert y["held_at_base"] == ["oil_tax_price"]
    ids = {c["id"] for c in y["lines"]["net_profit"]["contributions"]}
    assert "oil" not in ids  # Δ = 0 → вклада нет
    assert [c["var"] for c in y["conditions_core"]] == ["key_rate_avg", "usdrub_avg"]
    assert y["conditions_core"][0]["text"] == "10,5–12,5%"
    md = ms.run_most_dangerous(m, cfg)
    assert "oil" not in {c["id"] for c in md["lines"]["net_profit"]["contributions"]}
