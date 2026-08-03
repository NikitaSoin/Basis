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
        assert abs(cheap["pct"]) < abs(floating["pct"])
        assert "льготные" in cheap["how"] and "плавающий" in floating["how"]


class TestFxChannel:
    def test_importer_is_not_guessed(self, card):
        """🔴 При малой доле экспорта канал НЕ считается.

        Расчёт видит только экспортную сторону курса и не знает про импортные
        издержки: у Аэрофлота он давал +14,5% там, где карточка говорит −7,2%.
        Ложный флаг хуже отсутствия флага.
        """
        card("IMPORTER", _fin(geo_split=[{"region": "Россия", "pct": 95.0},
                                         {"region": "Экспорт", "pct": 5.0}]))
        assert "fx" not in (ss.structural_sensitivity("IMPORTER").get("channels") or {})

    def test_exporter_wins_from_weak_ruble(self, card):
        card("EXP", _fin(geo_split=[{"region": "Россия", "pct": 20.0},
                                    {"region": "Азия", "pct": 80.0}]))
        fx = ss.structural_sensitivity("EXP")["channels"]["fx"]
        assert fx["pct"] > 0 and fx["inputs"]["export_share_pct"] == 80.0

    def test_cis_is_not_counted_as_currency_revenue(self, card):
        """Расчёты с СНГ часто рублёвые — завысить валютную долю хуже, чем занизить."""
        card("CIS", _fin(geo_split=[{"region": "Россия", "pct": 40.0},
                                    {"region": "СНГ", "pct": 60.0}]))
        assert "fx" not in (ss.structural_sensitivity("CIS").get("channels") or {})


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


class TestRateChannelDisagreement:
    """Разбор расхождений 2026-08-03: все пять «ошибок карточек» были ошибками модели."""

    def test_cash_pile_does_not_override_interest_paid(self, card):
        """🔴 ТНС энерго: чистый долг отрицательный, а процентов платит вдвое больше.

        Деньги на балансе сбыта транзитные (собраны с потребителей), долг короткий и
        дорогой. Способ «по чистому долгу» объявлял такую компанию выигравшей от роста
        ставки и обвинял верную карточку в ошибке знака. Способы расходятся — молчим.
        """
        card("SBYT", _fin(balance_sheet={"net_debt": [-2865.0]},
                          income_statement={"finance_costs": [4850.0],
                                            "finance_income": [2003.0]}))
        assert "rate" not in (ss.structural_sensitivity("SBYT").get("channels") or {})

    def test_interest_income_does_not_override_real_debt(self, card):
        """Обратный случай (Аэрофлот): доходы выше расходов, но долг реальный."""
        card("AIR", _fin(balance_sheet={"net_debt": [143582.0]},
                         income_statement={"finance_costs": [60467.0],
                                           "finance_income": [63416.0]}))
        assert "rate" not in (ss.structural_sensitivity("AIR").get("channels") or {})

    def test_agreeing_methods_are_averaged(self, card):
        """Когда способы согласны — канал считается, оценка усредняется."""
        card("OK", _fin(balance_sheet={"net_debt": [200.0]},
                        income_statement={"finance_costs": [30.0], "finance_income": [5.0]}))
        rate = ss.structural_sensitivity("OK")["channels"]["rate"]
        assert rate["pct"] < 0 and rate["inputs"]["methods_agree"] is True

    def test_negative_finance_costs_do_not_flip_the_sign(self, card):
        """🔴 Знак процентных статей в карточках непоследователен — те же грабли, что с capex."""
        card("NEG", _fin(balance_sheet={"net_debt": [200.0]},
                         income_statement={"finance_costs": [-30.0], "finance_income": [5.0]}))
        card("POS", _fin(balance_sheet={"net_debt": [200.0]},
                         income_statement={"finance_costs": [30.0], "finance_income": [5.0]}))
        assert (ss.structural_sensitivity("NEG")["channels"]["rate"]["pct"]
                == ss.structural_sensitivity("POS")["channels"]["rate"]["pct"])

    def test_banks_are_excluded(self, card):
        """🔴 У банка проценты — основной бизнес, а не обслуживание долга.

        Формула «платит больше, чем получает» на банке даёт обратный знак: у МКБ
        нетто-проценты естественно положительные, и модель объявляла, что рост ставки
        ему на пользу, тогда как ставка сжимает процентную маржу.
        """
        card("BANKX", _fin(meta={"profile": "bank", "sector": "Банки"},
                           balance_sheet={"net_debt": [500.0]},
                           income_statement={"finance_costs": [100.0],
                                             "finance_income": [205.0]}))
        assert "rate" not in (ss.structural_sensitivity("BANKX").get("channels") or {})


class TestFxRegionRecognition:
    def test_domestic_regions_are_not_export(self, card):
        """🔴 «Москва и Московская область» — не экспорт.

        Чёрный список внутренних регионов всегда неполон: клиника «Мать и дитя»
        получала 59% «валютной» выручки и +16,8% по курсу там, где карточка честно
        говорит −2,2% (импортное оборудование).
        """
        card("CLINIC", _fin(geo_split=[{"region": "Москва и Московская область", "pct": 59.0},
                                       {"region": "Регионы РФ", "pct": 41.0}]))
        assert "fx" not in (ss.structural_sensitivity("CLINIC").get("channels") or {})

    def test_explicit_export_is_recognised(self, card):
        card("EXPX", _fin(geo_split=[{"region": "Россия", "pct": 30.0},
                                     {"region": "Экспорт (Азия, Латинская Америка)", "pct": 70.0}]))
        fx = ss.structural_sensitivity("EXPX")["channels"]["fx"]
        assert fx["pct"] > 0 and fx["inputs"]["export_share_pct"] == 70.0

    def test_unknown_region_counts_as_domestic(self, card):
        """Неизвестное — внутреннее: завысить валютную долю хуже, чем занизить."""
        card("VAGUE", _fin(geo_split=[{"region": "Прочие", "pct": 60.0},
                                      {"region": "Россия", "pct": 40.0}]))
        assert "fx" not in (ss.structural_sensitivity("VAGUE").get("channels") or {})
