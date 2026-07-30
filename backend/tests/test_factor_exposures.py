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
    assert growing < 0.40, (
        f"{growing*100:.0f}% компаний РАСТУТ в стрессовом сценарии — так не бывает; "
        f"вероятно, часть бьющих факторов не доезжает до движка"
    )
