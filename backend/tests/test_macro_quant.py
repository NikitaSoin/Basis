"""Тесты расчётного модуля макро-квантификации (macro_quant).

Опорные числа — из дизайн-эталона Macro-v3.html (Роснефть): проверяем, что модуль
воспроизводит водопад / чувствительности / сценарии и что числа СХОДЯТСЯ между блоками
(единый источник коэффициентов — методичка 14.7).
"""
from app.services import macro_quant


# Входы Роснефти по эталону: нейтраль (рубль 92, ставка 10%, Urals $70), факт (84/16/62),
# инфляция издержек опережает на 3 п.п. Коэффициенты — как в эталонной таблице чувствительности.
ROSN_QI = {
    "unit": "млрд_руб",
    "financials": {"revenue": 9500, "ebitda": 3000, "net_profit": 1100},
    "macro_current": {"fx_usdrub": 84, "key_rate_pct": 16, "commodity_usd": 62, "cost_excess_pp": 3},
    "macro_neutral": {"fx_usdrub": 92, "key_rate_pct": 10, "commodity_usd": 70, "cost_excess_pp": 0},
    "neutral_net_profit": 1450,
    "coefficients": {
        # рубль −1₽ (ослабление) в пользу экспортёра → +финансы; значит +1₽ (укрепление к росту курса)...
        # знак per +1_rub: рост курса (ослабление рубля) = +финансы → revenue +55, ebitda +30, np +22
        "fx": {"per": "1_rub", "revenue": 55, "ebitda": 30, "net_profit": 22, "source": "estimated"},
        # Urals +$1 → np ~+11 (в эталоне +$5 → +55)
        "commodity": {"per": "1_usd", "revenue": 26, "ebitda": 14, "net_profit": 11, "source": "estimated"},
        # ставка +100 б.п. → np −10 (в эталоне −100 б.п. → +10)
        "rate": {"per": "100bp", "revenue": 0, "ebitda": 0, "net_profit": -10, "source": "estimated"},
        # издержки +1 п.п. сверх нейтрали → ebitda −20, np −16
        "cost_inflation": {"per": "1pp", "revenue": 0, "ebitda": -20, "net_profit": -16, "source": "estimated"},
    },
    "one_off": {"label": "Валютная переоценка долга", "net_profit": 40, "certainty": "estimate"},
    "scenarios": {
        "base": {"fx_usdrub": 90, "key_rate_pct": 13.5, "commodity_usd": 62, "cost_excess_pp": 3, "probability": "вероятнее"},
        "hawkish": {"fx_usdrub": 82, "key_rate_pct": 16, "commodity_usd": 57, "cost_excess_pp": 4, "probability": "риск"},
        "dovish": {"fx_usdrub": 95, "key_rate_pct": 11.5, "commodity_usd": 68, "cost_excess_pp": 2, "probability": "менее вероятно"},
    },
}


def test_attribution_deltas_match_reference():
    """Водопад: дельты по факторам = coef × (текущее − нейтраль). Совпадают с эталоном."""
    a = macro_quant.compute_attribution(ROSN_QI)
    by = {b["factor_key"]: b["delta"] for b in a["bridge"]}
    assert by["fx"] == 22 * (84 - 92)            # −176 (эталон −180)
    assert by["commodity"] == 11 * (62 - 70)     # −88  (эталон −90)
    assert by["rate"] == -10 * (16 - 10)         # −60  (эталон −60)
    assert by["cost_inflation"] == -16 * (3 - 0) # −48  (эталон −50)


def test_attribution_residual_closes_waterfall():
    """Водопад сходится к ОПЕРАЦИОННОЙ прибыли; + one_off = отчётная (методичка 14.2)."""
    a = macro_quant.compute_attribution(ROSN_QI)
    total = a["neutral_net_profit"] + sum(b["delta"] for b in a["bridge"]) + a["residual"]
    assert total == a["operating_net_profit"]                          # водопад → операционная
    assert a["operating_net_profit"] + a["one_off"]["net_profit"] == a["actual_net_profit"] == 1100


def test_one_off_excluded_from_bridge():
    """Разовый эффект (переоценка долга) НЕ в водопаде, а отдельной строкой."""
    a = macro_quant.compute_attribution(ROSN_QI)
    assert all(not b["is_one_off"] for b in a["bridge"])
    assert a["one_off"]["net_profit"] == 40


def test_main_driver_is_fx():
    """Главный драйвер атрибуции — самый дорогой канал (курс, −176)."""
    a = macro_quant.compute_attribution(ROSN_QI)
    assert a["main_driver"] == "fx"


def test_sensitivities_are_coefficients():
    """Таблица чувствительности = коэффициенты напрямую (тот же источник, что водопад)."""
    rows = {r["factor_key"]: r for r in macro_quant.compute_sensitivities(ROSN_QI)}
    assert rows["fx"]["net_profit"] == 22
    assert rows["commodity"]["net_profit"] == 11
    assert rows["rate"]["net_profit"] == -10
    assert rows["cost_inflation"]["ebitda"] == -20


def test_scenario_base_matches_reference():
    """Сценарий База: Σ coef × (сценарий − текущее). Прибыль ~+150 (эталон +120…180)."""
    s = macro_quant.compute_scenarios(ROSN_QI)["base"]
    # fx: 22×(90−84)=+132 ; rate: −10×(13.5−16)=+25 ; commodity: 11×(62−62)=0 ; cost: −16×(3−3)=0
    assert s["net_profit_delta"] == 132 + 25  # +157
    assert s["net_profit_delta"] > 0


def test_scenario_hawkish_is_negative():
    """Ястребиный: крепкий рубль + слабый Urals + высокая ставка → прибыль вниз."""
    s = macro_quant.compute_scenarios(ROSN_QI)["hawkish"]
    assert s["net_profit_delta"] < 0


def test_consistency_waterfall_vs_sensitivity():
    """КЛЮЧЕВОЕ: водопадная дельта курса = чувствительность × сдвиг (один коэффициент)."""
    a = macro_quant.compute_attribution(ROSN_QI)
    sens = {r["factor_key"]: r for r in macro_quant.compute_sensitivities(ROSN_QI)}
    fx_delta = next(b["delta"] for b in a["bridge"] if b["factor_key"] == "fx")
    assert fx_delta == sens["fx"]["net_profit"] * (84 - 92)


def test_enrich_populates_computed():
    """enrich кладёт результат в macro['computed'] идемпотентно."""
    macro = {"quant_inputs": ROSN_QI}
    macro_quant.enrich(macro)
    assert "computed" in macro
    assert macro["computed"]["attribution"]["actual_net_profit"] == 1100
    assert macro["computed"]["checks"]["factors_count"] == 4


def test_missing_factor_degrades_not_crashes():
    """Нет коэффициента фактора → он выпадает, модуль не падает (частичные данные)."""
    qi = {**ROSN_QI, "coefficients": {"fx": ROSN_QI["coefficients"]["fx"]}}
    out = macro_quant.compute(qi)
    assert out["checks"]["factors_count"] == 1
    assert len(out["sensitivities"]) == 1


def test_empty_input_degrades_gracefully():
    """Пустой вход → пустой computed, без исключений (вкладка не падает)."""
    out = macro_quant.compute({})
    assert out["sensitivities"] == []
    assert out["attribution"]["bridge"] == []
    assert out["scenarios"] == {}


def test_explicit_driver_overrides_fixed_map():
    """Явный coef['driver'] на СТАНДАРТНОМ факторе (demand) бьёт фиксированную карту
    (регресс ALRS: 'demand' завязан на lux_demand_pp, не на gdp_growth_pct)."""
    qi = {
        "unit": "млрд_руб",
        "financials": {"net_profit": 10.0},
        "neutral_net_profit": 20.0,
        "coefficients": {
            "demand": {"net_profit": 5.0, "driver": "lux_demand_pp", "per": "1pp"},
        },
        # фиксированная карта дала бы gdp_growth_pct; проверяем, что берётся lux_demand_pp
        "macro_current": {"lux_demand_pp": -2.0, "gdp_growth_pct": 1.0},
        "macro_neutral": {"lux_demand_pp": 0.0, "gdp_growth_pct": 1.5},
    }
    out = macro_quant.compute(qi)
    b = out["attribution"]["bridge"][0]
    assert b["factor_key"] == "demand"
    # 5.0 × (−2 − 0) = −10 по lux_demand_pp; НЕ 5.0 × (1 − 1.5) = −2.5 по ВВП
    assert b["delta"] == -10.0
    assert b["calc"]["to"] == -2.0 and b["calc"]["from"] == 0.0
