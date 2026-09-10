"""Контракт-тесты слоя измерения качества.

🔴 Зачем: слой, который сам молча деградировал, хуже, чем его отсутствие —
он ещё и успокаивает. В проекте это уже случалось дважды (ревизор «успешно»
проверил ноль; маппер при смене схемы стал молча отдавать None). Поэтому у
измерения есть собственный пол, ниже которого тест падает.

БД не требуется: тесты читают карточки и снапшоты с диска.
"""
from datetime import date

import pytest

from app.services.quality import golden, runner
from app.services.quality.contract import Status
from app.services.quality.pipelines import PIPELINES, get

PIPELINE_NAMES = sorted(PIPELINES)
SAMPLES = {
    "financials": ["LKOH", "SBER", "GMKN", "MTSS", "PHOR", "MGNT", "NVTK", "CHMF"],
    "snapshots": None,          # снапшотов мало — гоняем все
}


@pytest.fixture(scope="module")
def runs():
    return {name: runner.run(name, only=SAMPLES.get(name)) for name in PIPELINE_NAMES}


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_эталонный_набор_проходит_целиком(pipeline):
    """Мутационные кейсы доказывают, что детекторы живы. Провал = проверка
    перестала ловить дефект, который заведомо есть."""
    result = golden.run_golden(pipeline)
    assert result["total"] >= 4, f"{pipeline}: эталонный набор подозрительно мал"
    assert not result["failed"], "\n".join(
        f"{r['case']}: {r['detail']}" for r in result["failed"])


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_у_каждой_мутации_есть_годный_носитель(pipeline):
    """Кейс, у которого не осталось ни одной пригодной компании, ничего не
    доказывает — но выглядит зелёным. Такой «проход» не считается."""
    for r in golden.run_golden(pipeline)["results"]:
        if r.get("kind") == "mutation":
            assert r.get("usable", 0) > 0, f"{r['case']}: не осталось годных носителей"


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_у_каждой_проверки_есть_мутационный_кейс(pipeline):
    """Проверка без искусственной поломки за спиной недоказуема: непонятно,
    ловит она что-нибудь или просто всегда возвращает «ок»."""
    covered = {c.check_id for c in golden.MUTATIONS_BY_PIPELINE.get(pipeline, [])}
    for check in get(pipeline).checks:
        assert check.check_id in covered, f"{check.check_id} нечем доказать"


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_покрытие_не_ниже_пола(pipeline, runs):
    res = runs[pipeline]
    assert res.valid, res.invalid_reason
    assert res.coverage >= runner.COVERAGE_FLOOR


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_каждая_проверка_хоть_где_то_отработала(pipeline, runs):
    """Проверка, которая на всей выборке только пропускает, — мёртвая."""
    res = runs[pipeline]
    for check in get(pipeline).checks:
        stats = res.per_check[check.check_id]
        assert stats["ok"] + stats["fail"] > 0, (
            f"{check.check_id} не отработала ни на одном субъекте выборки")


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_версия_набора_проставлена(pipeline, runs):
    assert runs[pipeline].checks_version == get(pipeline).checks_version
    assert get(pipeline).checks_version, "без версии набора прогоны нельзя сравнивать"


def test_skip_не_считается_за_ок(runs):
    """Ключевое свойство контракта: у «нечего проверять» отдельный статус."""
    outcomes = [o for res in runs.values() for o in res.outcomes]
    assert any(o.status is Status.SKIP for o in outcomes), "нет ни одного skip — не схлопнулись ли статусы"
    for outcome in outcomes:
        if outcome.status is Status.SKIP:
            assert not outcome.failed
            assert outcome.message, "skip обязан объяснять, почему проверять было нечего"


@pytest.mark.parametrize("pipeline", PIPELINE_NAMES)
def test_проверки_не_роняют_прогон_на_битом_субъекте(pipeline):
    """Упавшая проверка обязана превратиться в skip, а не убить прогон."""
    junk = {"card": {"meta": "не словарь"}, "doc": {"meta": "не словарь"},
            "extracted": None, "today_year": date.today().year, "today": date.today()}
    for check in get(pipeline).checks:
        outcomes = check.run("XXXX", junk)
        assert all(o.status in (Status.OK, Status.FAIL, Status.SKIP) for o in outcomes)
