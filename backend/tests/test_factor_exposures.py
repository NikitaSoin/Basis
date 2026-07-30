"""Контракт-тесты факторного каркаса (factor_exposures / factor_engine).

🔴 ЗАЧЕМ ЭТИ ТЕСТЫ СУЩЕСТВУЮТ (2026-07-30). Миграция geo-system v0.9 (коммит
2335f41ee1, 2026-07-12) переименовала схему geo.json: ключ `factors`, из которого
маппер брал sanctions/conflict, исчез у всех 264 компаний. Код НЕ упал — экспозиция
молча стала None, и «честная деградация» съела два фактора из шести. Полтора месяца
стрессовый сценарий, подписанный в UI как «эскалация + санкции», не содержал ни
эскалации, ни санкций: портфель банков «зарабатывал» +9.6% в стрессе, MGI = 100.
Поймал владелец глазами, а не тест.

Мораль: молчаливое падение покрытия до нуля — это НЕ деградация, а поломка. Тест
ниже поймал бы ту миграцию в день коммита.
"""
import os

import pytest

from app.services import factor_engine
from app.services.factor_exposures import (
    COMPANIES_DIR, FACTOR_KEYS, get_company_exposures,
)

# Факторы, которые реально участвуют хотя бы в одном сценарии, — только их отсутствие
# ломает расчёт (fiscal/refinancing сейчас не входят ни в один сценарий, см. §4 разбора).
SCENARIO_FACTORS = sorted({
    f for sc in factor_engine.load_scenarios() for f in (sc.get("intensities") or {})
})

# Пол покрытия — разный по природе фактора, иначе тест ложно срабатывает.
# УНИВЕРСАЛЬНЫЕ факторы применимы к любому эмитенту: ставка и спрос влияют на всех,
# санкционный/военный контур в РФ-реальности тоже есть у каждого (gre_profile
# заполнен 264/264). Их проседание = поломка схемы.
# НИШЕВЫЕ факторы по определению покрыты частично: commodity тегируется только у
# сырьевиков (~60 компаний), fx — у тех, у кого есть валютный канал. Для них низкий
# пол ловит только полный обвал, не естественную выборочность.
MIN_COVERAGE_UNIVERSAL = 80.0
MIN_COVERAGE_NICHE = 10.0
_NICHE_FACTORS = {"commodity", "fx", "fiscal"}


def _floor_for(factor: str) -> float:
    return MIN_COVERAGE_NICHE if factor in _NICHE_FACTORS else MIN_COVERAGE_UNIVERSAL


def _all_tickers() -> list[str]:
    if not COMPANIES_DIR.exists():
        return []
    return sorted(
        d for d in os.listdir(COMPANIES_DIR)
        if (COMPANIES_DIR / d).is_dir() and not d.startswith(".")
    )


@pytest.fixture(scope="module")
def exposures_by_ticker() -> dict[str, dict]:
    tickers = _all_tickers()
    if not tickers:
        pytest.skip("нет каталога companies/ — нечего проверять")
    return {t: get_company_exposures(t) for t in tickers}


@pytest.mark.parametrize("factor", SCENARIO_FACTORS)
def test_scenario_factor_has_coverage(factor, exposures_by_ticker):
    """Каждый фактор, участвующий в сценариях, покрыт не хуже пола.

    Именно этот тест поймал бы миграцию geo v0.9: sanctions/conflict дали бы 0%.
    """
    total = len(exposures_by_ticker)
    covered = sum(1 for e in exposures_by_ticker.values() if e.get(factor) is not None)
    pct = covered / total * 100
    floor = _floor_for(factor)
    assert pct >= floor, (
        f"фактор «{factor}» покрыт лишь у {covered}/{total} компаний ({pct:.0f}%) — "
        f"ниже пола {floor}%. Похоже, сменилась схема исходных карточек "
        f"(macro.json/geo.json) и маппер читает несуществующее поле."
    )


def test_exposures_in_valid_range(exposures_by_ticker):
    """Экспозиция обязана лежать в шкале методики [-2; +2] либо быть None."""
    for ticker, exp in exposures_by_ticker.items():
        for key in FACTOR_KEYS:
            v = exp.get(key)
            assert v is None or -2.0 <= v <= 2.0, f"{ticker}.{key} = {v} вне шкалы [-2;+2]"


def test_sanctioned_company_is_negative(exposures_by_ticker):
    """Компания под SDN не может иметь неотрицательную санкционную экспозицию."""
    for ticker in ("LKOH", "ROSN", "VTBR", "SBER"):
        exp = exposures_by_ticker.get(ticker)
        if not exp or exp.get("sanctions") is None:
            continue
        assert exp["sanctions"] < 0, f"{ticker} под санкциями, а sanctions={exp['sanctions']}"


def test_price_effect_is_monotonic_and_anchored():
    """Якоря методики §3.4 (0/7/15%) и монотонность без разрывов от округления."""
    assert factor_engine._price_effect(0) == 0.0
    assert factor_engine._price_effect(1) == pytest.approx(0.07)
    assert factor_engine._price_effect(2) == pytest.approx(0.15)
    assert factor_engine._price_effect(-1) == pytest.approx(-0.07)
    # за шкалой — кап, не экстраполяция
    assert factor_engine._price_effect(5) == pytest.approx(0.15)
    # монотонность: раньше round() давал ступеньку 0.44→0%, 0.5→7%
    prev = -1.0
    for i in range(0, 21):
        cur = factor_engine._price_effect(i / 10)
        assert cur >= prev, "эффект должен расти монотонно с экспозицией"
        prev = cur
    assert 0 < factor_engine._price_effect(0.44) < factor_engine._price_effect(0.5)


def test_stress_is_not_a_free_lunch(exposures_by_ticker):
    """Большинство рынка обязано ПАДАТЬ в стрессовом сценарии.

    До фикса медиана реакции была ровно 0.0%, а 46% компаний в стрессе росли —
    математический признак того, что бьющие факторы выпали из расчёта.
    """
    intensities = next(
        (sc.get("intensities") for sc in factor_engine.load_scenarios() if sc.get("key") == "stress"),
        None,
    )
    assert intensities, "в конфиге нет стрессового сценария"
    reactions = [
        factor_engine.company_scenario_reaction(e, intensities)
        for e in exposures_by_ticker.values()
        if any(v is not None for v in e.values())
    ]
    growing = sum(1 for r in reactions if r > 0) / len(reactions)
    assert growing < 0.15, (
        f"{growing*100:.0f}% компаний РАСТУТ в стрессовом сценарии — так не бывает; "
        f"вероятно, часть бьющих факторов не доезжает до движка"
    )


# ────────────────── структурные знаки (переход на quant_inputs, 2026-07-30) ──────────────────
# effect_sign кодировал ТЕКУЩЕЕ состояние фактора, а движок читал его как структурную
# бету — из-за чего М.Видео «рос на 15%» при обвале спроса, а ЛУКОЙЛ и ГМК имели
# противоположный знак по курсу при одинаковой экономике экспортёра. Экспозиции теперь
# считаются из quant_inputs.coefficients; тесты ниже стерегут именно знаки.

def test_demand_is_mostly_positive(exposures_by_ticker):
    """Почти все компании структурно ЛЮБЯТ спрос — это допущение записано в
    _sign_convention сценариев. На старом источнике положительных было лишь 7%."""
    vals = [e["demand"] for e in exposures_by_ticker.values() if e.get("demand")]
    positive = sum(1 for v in vals if v > 0) / len(vals)
    assert positive >= 0.80, f"положительных demand-экспозиций лишь {positive*100:.0f}%"


def test_costs_are_almost_always_negative(exposures_by_ticker):
    """Рост зарплат и инфляция издержек структурно бьют по всем."""
    vals = [e["costs"] for e in exposures_by_ticker.values() if e.get("costs")]
    negative = sum(1 for v in vals if v < 0) / len(vals)
    assert negative >= 0.90, f"отрицательных costs-экспозиций лишь {negative*100:.0f}%"


def test_exporters_share_fx_sign(exposures_by_ticker):
    """Экспортёры обязаны иметь ОДИН знак беты к ослаблению рубля.

    На effect_sign ЛУКОЙЛ был negative («крепнущий рубль»), а ГМК positive («рычаг
    экспортёра») — один тип бизнеса, разный знак, потому что описывали разное.
    """
    for ticker in ("LKOH", "ROSN", "GMKN", "PHOR"):
        exp = exposures_by_ticker.get(ticker)
        if not exp or not exp.get("fx"):
            continue
        assert exp["fx"] > 0, f"{ticker} — экспортёр, бета к слабому рублю должна быть > 0"


def test_bank_rate_sensitivity_is_differentiated(exposures_by_ticker):
    """Движок обязан различать банки: у ВТБ фондирование дорогое (liability-sensitive,
    страдает от роста ставки), у Сбера дешёвое розничное (NIM помогает). Если оба
    окажутся одного знака — источник знака потерян."""
    sber, vtbr = exposures_by_ticker.get("SBER"), exposures_by_ticker.get("VTBR")
    if not sber or not vtbr:
        pytest.skip("нет карточек SBER/VTBR")
    assert vtbr["rate"] < 0, "ВТБ liability-sensitive — рост ставки обязан бить"
    # И при этом ни один банк не должен «зарабатывать» на стрессе целиком:
    stress = next(sc["intensities"] for sc in factor_engine.load_scenarios() if sc["key"] == "stress")
    for name, exp in (("SBER", sber), ("VTBR", vtbr)):
        r = factor_engine.company_scenario_reaction(exp, stress)
        assert r < 0, f"{name} растёт в стрессовом сценарии ({r*100:+.1f}%)"


def test_discretionary_retail_collapses_on_demand_shock(exposures_by_ticker):
    """М.Видео — дискреционный ритейл: обвал спроса обязан бить сильно.
    До фикса модель показывала +15% РОСТА."""
    exp = exposures_by_ticker.get("MVID")
    if not exp:
        pytest.skip("нет карточки MVID")
    stress = next(sc["intensities"] for sc in factor_engine.load_scenarios() if sc["key"] == "stress")
    r = factor_engine.company_scenario_reaction(exp, stress) * 100
    assert r <= -25, f"М.Видео в стрессе {r:+.1f}% — дискреционный ритейл обязан падать сильнее"


def test_tax_hike_hits_donors_harder():
    """Налоговый сценарий (заказ владельца): фискальные доноры получают больше всех."""
    sc = next((s for s in factor_engine.load_scenarios() if s.get("tax_shock")), None)
    assert sc, "в конфиге нет налогового сценария"
    donor = factor_engine.tax_hike_reaction("GAZP", sc["tax_shock"])
    other = factor_engine.tax_hike_reaction("OZON", sc["tax_shock"])
    assert donor < other < 0, f"донор {donor*100:.1f}% должен страдать сильнее прочих {other*100:.1f}%"


def test_conditional_scenarios_excluded_from_probabilities():
    """Условные сценарии не входят в распределение — иначе сумма > 1 и forward-ERR врёт."""
    total = sum(sc.get("probability") or 0
                for sc in factor_engine.load_scenarios() if not sc.get("conditional"))
    assert abs(total - 1.0) < 1e-6, f"сумма вероятностей основных сценариев = {total}"


# ────────────────────────── секторные полы ──────────────────────────
# Страховка от ЧЕТВЁРТОГО повторения тихой деградации. Отсутствие канала при
# заполненных quant_inputs трактуется как «канал нематериален» (экспозиция 0) — это
# удобно, но ровно этим механизмом нас уже дважды кусало. Поэтому: там, где канал
# обязан быть по природе бизнеса, его пропажа должна ронять тест, а не тихо давать 0.
_SECTOR_REQUIRED_FACTORS = {
    "Нефть и газ": ("fx", "commodity"),   # экспортёр валютной выручки и сырья
    "Металлургия": ("fx",),
    "Финансы": ("rate",),                 # банк без ставочного канала — нонсенс
}


@pytest.mark.parametrize("sector,required", sorted(_SECTOR_REQUIRED_FACTORS.items()))
def test_sector_required_factors_present(sector, required, exposures_by_ticker):
    """У сектора обязаны быть заполнены профильные факторы хотя бы у большинства."""
    from app.services.sector_norm import sector_for

    members = [t for t in exposures_by_ticker if sector_for(t) == sector]
    if len(members) < 3:
        pytest.skip(f"в секторе «{sector}» слишком мало компаний для статистики")
    for factor in required:
        filled = [t for t in members if exposures_by_ticker[t].get(factor)]
        share = len(filled) / len(members)
        assert share >= 0.30, (
            f"в секторе «{sector}» фактор «{factor}» заполнен лишь у {len(filled)}/"
            f"{len(members)} компаний ({share*100:.0f}%) — для этого сектора он профильный, "
            f"похоже на потерю канала, а не на «нематериально»"
        )
