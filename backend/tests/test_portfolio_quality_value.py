"""Контракт-тесты модуля «Запас прочности» (portfolio_quality_v2._compute_v).

🔴 ЗАЧЕМ (2026-07-31). Владелец собрал тестовый портфель (Северсталь / Ростелеком /
Магнит) и увидел 83 балла запаса прочности при том, что средний потенциал портфеля
около нуля. Причина: балл считался одной линейной шкалой `_lin_score(rau, best=+25,
worst=−90)`, на которой НУЛЕВОЙ потенциал давал 78 баллов, а переплата в 20 % — 61.
Шкалу растянули вниз ради различимости портфелей (медиана потенциала по рынку −51 %),
но различимость купили ценой смысла: модуль перестал отвечать на свой собственный
вопрос «есть ли запас прочности».

Вторым дефектом вердикт был привязан к БАЛЛУ (v_score >= 60), поэтому портфель с
отрицательным потенциалом подписывался «куплен с запасом прочности» — текст прямо
противоречил числу рядом.

Тесты ниже стерегут СЕМАНТИКУ, а не конкретные наклоны: наклоны — продуктовый произвол
и могут меняться, но «ноль потенциала = ровно середина шкалы» и «отрицательный
потенциал не может называться запасом прочности» меняться не должны.
"""
import pytest

from app.services.portfolio_quality_v2 import _value_score


def test_zero_potential_is_exactly_middle():
    """Куплен ровно по справедливой цене → ровно 50, не 78."""
    assert _value_score(0) == 50


@pytest.mark.parametrize("rau", [-5, -10, -20, -51, -90])
def test_negative_potential_is_below_middle(rau):
    """Переплата не может давать балл выше середины."""
    assert _value_score(rau) < 50, f"потенциал {rau}% дал {_value_score(rau)} баллов"


def test_near_zero_potential_never_reads_as_good():
    """Портфель владельца (Северсталь/Ростелеком/Магнит) дал потенциал −0.6 %: на такой
    околонулевой величине округление до ровно 50 законно, но НИКАК не 78, как было."""
    assert _value_score(-0.6) <= 50
    assert _value_score(-1.8) <= 50  # число с первого скриншота владельца


@pytest.mark.parametrize("rau", [2, 10, 25, 50, 80])
def test_positive_potential_is_above_middle(rau):
    assert _value_score(rau) > 50


def test_scale_is_monotonic_and_bounded():
    prev = -1
    for x in range(-120, 121, 5):
        s = _value_score(x)
        assert 0 <= s <= 100, f"балл {s} вне [0;100] при потенциале {x}%"
        assert s >= prev, "балл обязан расти с потенциалом"
        prev = s


def test_market_median_portfolio_still_differentiates():
    """Медианный по рынку портфель (потенциал ≈ −51%) не должен упираться в 0 —
    иначе модуль перестаёт различать портфели, ради чего шкалу и растягивали."""
    assert 10 < _value_score(-51) < 40


def test_verdict_matches_the_number():
    """Вердикт обязан следовать за ПОТЕНЦИАЛОМ, а не за баллом.

    Именно это разошлось у владельца: −0.6 % потенциала и подпись «куплен с запасом
    прочности».
    """
    from app.services import portfolio_quality_v2 as m

    equity = [{"ticker": "TEST", "value": 1.0}]

    def verdict_for(upside_pct: float) -> str:
        fake = {"TEST": {"upside_pct": upside_pct, "source": "bfv", "reliability": "normal"}}
        original = m._load_company_json
        m._load_company_json = lambda ticker, name: (
            {"valuation": {"fair_value_range": {}}, "meta": {"data_quality": "normal"}}
            if name == "financials.json" else None
        )
        try:
            return (m._compute_v(equity, fake) or {}).get("verdict", "")
        finally:
            m._load_company_json = original

    assert "запаса прочности нет" in verdict_for(-25)
    assert "практически нет" in verdict_for(-0.6)
    assert "есть" in verdict_for(30)
