"""Структурный расчёт чувствительностей и сверка с карточками.

Тесты закрывают ровно те грабли, на которых расчёт ломался при разработке
(2026-08-03) — см. `docs/sensitivity_methodology.md`.
"""
import json

import pytest

from app.services import sensitivity_structural as ss


@pytest.fixture
def card(tmp_path, monkeypatch):
    """Фабрика карточек компании во временной папке."""
    monkeypatch.setattr(ss, "COMPANIES_DIR", tmp_path)

    def make(ticker: str, financials: dict, macro: dict | None = None):
        d = tmp_path / ticker
        d.mkdir(parents=True, exist_ok=True)
        (d / "financials.json").write_text(json.dumps(financials, ensure_ascii=False),
                                           encoding="utf-8")
        if macro is not None:
            (d / "macro.json").write_text(json.dumps(macro, ensure_ascii=False),
                                          encoding="utf-8")
        return ticker
    return make


def _fin(**kw):
    base = {
        "meta": {"sector": "consumer", "unit": "млрд"},
        "income_statement": {"revenue": [1000.0], "net_profit": [100.0],
                             "operating_profit": [150.0], "finance_costs": [10.0]},
        "balance_sheet": {"net_debt": [200.0]},
    }
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


class TestRateChannel:
    def test_debt_hurts_cash_pile_helps(self, card):
        """Знак работает в обе стороны — иначе не видно ошибок у компаний с кубышкой."""
        card("DEBT", _fin())
        card("CASH", _fin(balance_sheet={"net_debt": [-200.0]}))
        assert ss.structural_sensitivity("DEBT")["channels"]["rate"]["pct"] < 0
        assert ss.structural_sensitivity("CASH")["channels"]["rate"]["pct"] > 0

    def test_cheap_portfolio_reprices_less(self, card):
        """Льготный и старый фиксированный долг цикл переживает — доля переоценки ниже."""
        card("CHEAP", _fin(income_statement={"finance_costs": [4.0]}))    # ~2% при ключевой 14
        card("FLOAT", _fin(income_statement={"finance_costs": [30.0]}))   # ~15% — плавающий
        cheap = ss.structural_sensitivity("CHEAP")["channels"]["rate"]
        floating = ss.structural_sensitivity("FLOAT")["channels"]["rate"]
        assert cheap["inputs"]["repricing_share"] < floating["inputs"]["repricing_share"]
        assert abs(cheap["pct"]) < abs(floating["pct"])


class TestFxChannel:
    def test_importer_is_not_guessed(self, card):
        """🔴 При малой доле экспорта канал НЕ считается.

        Расчёт видит только экспортную сторону курса и не знает про импортные
        издержки: у Аэрофлота он давал +14,5% там, где карточка говорит −7,2%.
        Ложный флаг хуже отсутствия флага.
        """
        card("IMPORTER", _fin(geo_split=[{"region": "Россия", "pct": 95.0},
                                         {"region": "Экспорт", "pct": 5.0}]))
        assert "fx" not in ss.structural_sensitivity("IMPORTER")["channels"]

    def test_exporter_wins_from_weak_ruble(self, card):
        card("EXP", _fin(geo_split=[{"region": "Россия", "pct": 20.0},
                                    {"region": "Азия", "pct": 80.0}]))
        fx = ss.structural_sensitivity("EXP")["channels"]["fx"]
        assert fx["pct"] > 0 and fx["inputs"]["export_share_pct"] == 80.0

    def test_cis_is_not_counted_as_currency_revenue(self, card):
        """Расчёты с СНГ часто рублёвые — завысить валютную долю хуже, чем занизить."""
        card("CIS", _fin(geo_split=[{"region": "Россия", "pct": 40.0},
                                    {"region": "СНГ", "pct": 60.0}]))
        assert "fx" not in ss.structural_sensitivity("CIS")["channels"]


class TestCostChannels:
    def test_cost_channels_are_a_limit_not_an_estimate(self, card):
        """Издержечные каналы — предел удара при нулевом переносе в цену."""
        card("RETAIL", _fin(cost_breakdown=[
            {"name": "Себестоимость проданных товаров", "pct": 76.0, "type": "variable"},
            {"name": "Персонал", "pct": 9.0, "type": "fixed"}]))
        ch = ss.structural_sensitivity("RETAIL")["channels"]
        assert ch["cost_inflation"]["kind"] == "граница"
        assert ch["labor"]["kind"] == "граница"
        assert ch["rate"]["kind"] == "оценка"

    def test_pct_base_detected_per_card(self, card):
        """🔴 Доли в cost_breakdown бывают и от выручки, и от издержек — не угадывать.

        Единой конвенции в карточках нет: сумма ≈100% значит «от издержек», иначе
        «от выручки». Одна гипотеза для всех — тихая ошибка на половине компаний.
        """
        of_revenue = [{"name": "Персонал", "pct": 40.0, "type": "fixed"},
                      {"name": "Сырьё", "pct": 45.0, "type": "variable"}]      # сумма 85
        of_costs = [{"name": "Персонал", "pct": 47.0, "type": "fixed"},
                    {"name": "Сырьё", "pct": 53.0, "type": "variable"}]        # сумма 100
        card("REV", _fin(cost_breakdown=of_revenue))
        card("CST", _fin(cost_breakdown=of_costs))
        # revenue=1000, costs=850: при равной доле ФОТ база отличается, значит и эффект
        rev_labor = ss.structural_sensitivity("REV")["channels"]["labor"]
        cst_labor = ss.structural_sensitivity("CST")["channels"]["labor"]
        assert rev_labor["inputs"]["labor_share_of_costs_pct"] == 40.0
        assert cst_labor["inputs"]["labor_share_of_costs_pct"] == 47.0
        # 1000×40% против 850×47% — базы разные, и это видно в результате
        assert rev_labor["pct"] == pytest.approx(-9.0, abs=0.2)
        assert cst_labor["pct"] == pytest.approx(-8.98, abs=0.2)


class TestAudit:
    def test_sign_mismatch_is_flagged(self, card, monkeypatch):
        from app.services import sensitivity_audit as sa
        monkeypatch.setattr(sa, "COMPANIES_DIR", ss.COMPANIES_DIR)
        # карточка: рост ставки бьёт по прибыли; отчётность: кубышка, значит наоборот
        card("CONFLICT", _fin(balance_sheet={"net_debt": [-300.0]}),
             macro={"quant_inputs": {"unit": "млрд_руб",
                                     "financials": {"net_profit": 100.0},
                                     "coefficients": {"rate": {"net_profit": -3.0}}}})
        flags = sa.audit_sensitivity()
        assert [f["kind"] for f in flags] == ["знак"]
        assert flags[0]["ticker"] == "CONFLICT"

    def test_softer_than_limit_is_not_flagged(self, card, monkeypatch):
        """Удар мягче предела — это перенос издержек в цену, а не ошибка карточки."""
        from app.services import sensitivity_audit as sa
        monkeypatch.setattr(sa, "COMPANIES_DIR", ss.COMPANIES_DIR)
        card("SOFT", _fin(cost_breakdown=[{"name": "Сырьё", "pct": 60.0, "type": "variable"}]),
             macro={"quant_inputs": {"unit": "млрд_руб",
                                     "financials": {"net_profit": 100.0},
                                     # предел ≈ −22,5%, карточка мягче — законно
                                     "coefficients": {"cost_inflation": {"net_profit": -1.0}}}})
        assert [f for f in sa.audit_sensitivity() if f["channel"] == "cost_inflation"] == []

    def test_harder_than_limit_is_flagged(self, card, monkeypatch):
        """А вот удар сильнее физического предела — точно ошибка."""
        from app.services import sensitivity_audit as sa
        monkeypatch.setattr(sa, "COMPANIES_DIR", ss.COMPANIES_DIR)
        card("HARD", _fin(cost_breakdown=[{"name": "Сырьё", "pct": 60.0, "type": "variable"}]),
             macro={"quant_inputs": {"unit": "млрд_руб",
                                     "financials": {"net_profit": 100.0},
                                     "coefficients": {"cost_inflation": {"net_profit": -10.0}}}})
        flags = [f for f in sa.audit_sensitivity() if f["channel"] == "cost_inflation"]
        assert len(flags) == 1 and flags[0]["kind"] == "предел"

    def test_nonsense_base_is_separated_from_real_disagreement(self, card, monkeypatch):
        """Околонулевая прибыль даёт тысячи процентов — это не спор о коэффициенте."""
        from app.services import sensitivity_audit as sa
        monkeypatch.setattr(sa, "COMPANIES_DIR", ss.COMPANIES_DIR)
        card("SHELL", _fin(income_statement={"net_profit": [0.2]}),
             macro={"quant_inputs": {"unit": "млрд_руб",
                                     "financials": {"net_profit": 0.2},
                                     "coefficients": {"rate": {"net_profit": -5.0}}}})
        flags = sa.audit_sensitivity()
        assert flags and all(f["kind"] == "база" for f in flags)
