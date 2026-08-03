"""Связка «сценарий → макро-сдвиги → конкретные бумаги».

Проверяем не арифметику ради арифметики, а те свойства, без которых витрина соврёт:
разнонаправленность каналов, отсутствие двойного счёта, нормировку на капитализацию
и защиту от несопоставимых баз.
"""
import json

import pytest

from app.services import scenario_transmission as st


@pytest.fixture
def cards(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "COMPANIES_DIR", tmp_path)

    def make(ticker, coefficients, financials, unit="млрд_руб"):
        d = tmp_path / ticker
        d.mkdir(parents=True, exist_ok=True)
        (d / "macro.json").write_text(json.dumps({"quant_inputs": {
            "unit": unit, "financials": financials, "coefficients": coefficients}},
            ensure_ascii=False), encoding="utf-8")
        return ticker
    return make


class TestCompanyImpact:
    def test_channels_net_out_not_pile_up(self, cards):
        """Экспортёр при эскалации: цена реализации падает, но рубль слабеет.

        Смысл связки в том, что каналы работают в РАЗНЫЕ стороны и сальдируются, а не
        суммируются по модулю в «всё плохо».
        """
        cards("EXPORTER",
              {"commodity": {"net_profit": 10.0}, "fx": {"net_profit": 8.0}},
              {"net_profit": 300.0})
        r = st.company_impact("EXPORTER", {"commodity": -5.0, "fx": 10.0})
        assert r["by_channel"] == {"commodity": -50.0, "fx": 80.0}
        assert r["total_bln"] == 30.0 and r["profit_pct"] == 10.0

    def test_overlapping_channels_are_not_double_counted(self, cards):
        """У банка эффект ставки уже частично сидит в стоимости риска."""
        cards("BANK", {"rate": {"net_profit": -5.0}, "cost_of_risk": {"net_profit": -20.0}},
              {"net_profit": 1000.0})
        r = st.company_impact("BANK", {"rate": 2.0, "cost_of_risk": 1.0})
        assert "rate" in r["dropped_overlapping"]
        assert set(r["by_channel"]) == {"cost_of_risk"}

    def test_cap_normalisation_is_comparable(self, cards):
        """Доля капитализации — то, что сопоставимо между компаниями."""
        cards("THIN", {"rate": {"net_profit": -1.0}}, {"net_profit": 2.0})
        r = st.company_impact("THIN", {"rate": 3.0}, cap_bln=100.0)
        assert r["profit_pct"] == -150.0    # для бизнеса — катастрофа
        assert r["cap_pct"] == -3.0         # для держателя акции — умеренно

    def test_absurd_effect_is_dropped(self, cards):
        """Эффект больше двух годовых прибылей — мусор данных, а не чувствительность."""
        cards("SHELL", {"rate": {"net_profit": -50.0}}, {"net_profit": 1.0})
        assert st.company_impact("SHELL", {"rate": 3.0}) is None

    def test_loss_making_falls_back_to_revenue(self, cards):
        """При убытке база — выручка, иначе знак эффекта переворачивается."""
        cards("LOSS", {"fx": {"net_profit": 5.0}},
              {"net_profit": -100.0, "revenue": 1000.0})
        r = st.company_impact("LOSS", {"fx": 10.0})
        assert r["base"] == "выручки" and r["profit_pct"] > 0

    def test_zero_shocks_produce_nothing(self, cards):
        """Базовый сценарий — точка отсчёта, а не «нулевой эффект по всем каналам»."""
        cards("ANY", {"rate": {"net_profit": -5.0}}, {"net_profit": 100.0})
        assert st.company_impact("ANY", {"rate": 0.0, "fx": 0.0}) is None


class TestScenarioConfig:
    def test_shipped_config_is_usable(self):
        """Справочник сценариев читается и покрывает четыре сценария барометра."""
        conf = st.load_scenario_shocks()
        scenarios = conf.get("scenarios") or {}
        assert set(scenarios) == {"S1_breakthrough", "S2_ceasefire",
                                  "S3_attrition", "S4_escalation"}
        assert conf.get("base_scenario") == "S3_attrition"
        # у базового сценария сдвигов нет — от него считаются остальные
        assert not any((scenarios["S3_attrition"]["shocks"] or {}).values())
        for key, spec in scenarios.items():
            assert spec.get("name") and spec.get("why"), key
            # каждое допущение обязано быть объяснено — это не прогноз, а произвол,
            # и он должен быть виден
            for channel in spec["shocks"]:
                assert spec["why"].get(channel), f"{key}/{channel} без обоснования"

    def test_escalation_hits_realisation_price_not_brent(self):
        """🔴 При эскалации мировой Brent растёт, а цена РЕАЛИЗАЦИИ падает.

        Это главная тонкость сценария: дисконт расширяется сильнее, чем растёт
        эталон. Если знак здесь перепутать, вся витрина назовёт экспортёров
        выигравшими по неверной причине.
        """
        shocks = st.load_scenario_shocks()["scenarios"]["S4_escalation"]["shocks"]
        assert shocks["commodity"] < 0 and shocks["fx"] > 0


class TestShowcaseFilters:
    def test_micro_caps_do_not_own_the_extremes(self, cards, monkeypatch):
        """🔴 Без порога капитализации края занимают бумаги по 3 млрд.

        У микрокапа любой эффект даёт десятки процентов стоимости, а коэффициенты в
        его карточке самые грубые — список «кого двигает сценарий» превращался в
        MAGE / RTSBP / TUZA. Отсечка не про качество компании, а про сопоставимость.
        """
        cards("BIG", {"rate": {"net_profit": -10.0}}, {"net_profit": 100.0})
        cards("TINY", {"rate": {"net_profit": -1.0}}, {"net_profit": 5.0})
        monkeypatch.setattr(st, "_market_caps", lambda db, shares: {"BIG": 500.0, "TINY": 3.0})
        monkeypatch.setattr(st, "_shares_outstanding", lambda: {})
        monkeypatch.setattr(st, "load_scenario_shocks", lambda: {
            "scenarios": {"S": {"name": "тест", "shocks": {"rate": 2.0}}}})
        out = st.scenario_impacts(None, "S")
        assert [r["ticker"] for r in out["losers"]] == ["BIG"]

    def test_preferred_and_common_collapse_to_one_row(self, cards, monkeypatch):
        """Обычка и преф одного эмитента — одна строка, а не два места в топе."""
        cards("SNGS", {"rate": {"net_profit": -10.0}}, {"net_profit": 100.0})
        cards("SNGSP", {"rate": {"net_profit": -10.0}}, {"net_profit": 100.0})
        monkeypatch.setattr(st, "_market_caps", lambda db, shares: {"SNGS": 900.0, "SNGSP": 400.0})
        monkeypatch.setattr(st, "_shares_outstanding", lambda: {})
        monkeypatch.setattr(st, "load_scenario_shocks", lambda: {
            "scenarios": {"S": {"name": "тест", "shocks": {"rate": 2.0}}}})
        out = st.scenario_impacts(None, "S")
        assert [r["ticker"] for r in out["losers"]] == ["SNGS"], "оставляем более ликвидную"
