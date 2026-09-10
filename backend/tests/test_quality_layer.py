"""Контракт-тесты слоя измерения качества.

🔴 Зачем: слой, который сам молча деградировал, хуже, чем его отсутствие —
он ещё и успокаивает. В проекте это уже случалось дважды (ревизор «успешно»
проверил ноль; маппер при смене схемы стал молча отдавать None). Поэтому у
измерения есть собственный пол, ниже которого тест падает.

БД не требуется: тесты читают карточки с диска.
"""
from datetime import date

import pytest

from app.services.quality import golden, runner
from app.services.quality.checks_financials import CHECKS, CHECKS_VERSION
from app.services.quality.contract import Status

SAMPLE = ["LKOH", "SBER", "GMKN", "MTSS", "PHOR", "MGNT", "NVTK", "CHMF"]


@pytest.fixture(scope="module")
def sample_run():
    return runner.run("financials", only=SAMPLE)


def test_эталонный_набор_проходит_целиком():
    """Мутационные кейсы доказывают, что детекторы живы. Провал = проверка
    перестала ловить дефект, который заведомо есть."""
    result = golden.run_golden(date.today().year)
    assert result["total"] >= 8, "эталонный набор подозрительно мал"
    assert not result["failed"], "\n".join(
        f"{r['case']}: {r['detail']}" for r in result["failed"])


def test_у_каждой_мутации_есть_годный_носитель():
    """Кейс, у которого не осталось ни одной пригодной компании, ничего не
    доказывает — но выглядит зелёным. Такой «проход» не считается."""
    result = golden.run_golden(date.today().year)
    for r in result["results"]:
        if r.get("kind") == "mutation":
            assert r.get("usable", 0) > 0, f"{r['case']}: не осталось годных носителей"


def test_покрытие_не_ниже_пола(sample_run):
    assert sample_run.valid, sample_run.invalid_reason
    assert sample_run.coverage >= runner.COVERAGE_FLOOR


def test_каждая_проверка_хоть_где_то_отработала(sample_run):
    """Проверка, которая на всей выборке только пропускает, — мёртвая."""
    for check in CHECKS:
        stats = sample_run.per_check[check.check_id]
        assert stats["ok"] + stats["fail"] > 0, (
            f"{check.check_id} не отработала ни на одной компании выборки")


def test_skip_не_считается_за_ок(sample_run):
    """Ключевое свойство контракта: у «нечего проверять» отдельный статус."""
    statuses = {o.status for o in sample_run.outcomes}
    assert Status.SKIP in statuses, "в выборке нет ни одного skip — проверьте, не схлопнулись ли статусы"
    for outcome in sample_run.outcomes:
        if outcome.status is Status.SKIP:
            assert not outcome.failed
            assert outcome.message, "skip обязан объяснять, почему проверять было нечего"


def test_версия_набора_проставлена(sample_run):
    assert sample_run.checks_version == CHECKS_VERSION
    assert CHECKS_VERSION, "без версии набора прогоны нельзя сравнивать между собой"


def test_проверки_не_роняют_прогон_на_битой_карточке():
    """Упавшая проверка обязана превратиться в skip, а не убить прогон."""
    for check in CHECKS:
        outcomes = check.run("XXXX", {"card": {"meta": "не словарь"}, "extracted": None,
                                      "today_year": date.today().year})
        assert all(o.status in (Status.OK, Status.FAIL, Status.SKIP) for o in outcomes)
