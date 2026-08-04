"""Свод вкладки «Обзор»: гейт и сборка.

Гейт здесь — не формальность: это последний рубеж перед завершающим выводом
фундаментального анализа, который читатель воспримет как позицию платформы.
"""
import json

import pytest

from app.services import overview_synthesis as ov


@pytest.fixture
def tabs():
    return [
        {"tab": "business", "title": "Бизнес-модель",
         "text": "Выручка 4642 млрд ₽, маржа 1,8%. Сеть магазинов у дома."},
        {"tab": "finance", "title": "Финансы",
         "text": "ROE 24%, чистый долг 227 млрд ₽, дивдоходность 14,65%."},
        {"tab": "governance", "title": "Управление",
         "text": "Балл управления 4,2 из 5, payout около 50%."},
    ]


@pytest.fixture
def fair():
    return {"engine": "BFV-D", "fair_price": 426.89, "current_price": 282.78,
            "upside_pct": 51.0, "expected_return_pct": 24.17, "hurdle_pct": 18.45,
            "drivers": {"roe0": 0.2402, "payout0": 0.498, "governance_score": 4.2}}


def _result(**over):
    base = {
        "verdict": ("Крупный розничный банк с высокой рентабельностью капитала и "
                    "устойчивой депозитной базой; прибыль держится на процентной "
                    "марже, а не на разовых статьях."),
        "pillars": [
            {"tab": "business", "stance": "сила", "point": "масштаб даёт дешёвое фондирование"},
            {"tab": "finance", "stance": "сила", "point": "ROE 24% при умеренном риске"},
            {"tab": "governance", "stance": "нейтрально", "point": "дивполитика предсказуема"},
        ],
        "fair_value_story": {
            "direction": "выше рынка",
            "why": ("Ожидаемая доходность 24,17% выше барьера 18,45%, и разрыв даёт "
                    "запас прочности. Основной вклад вносит рентабельность капитала "
                    "24%, которую поддерживает дешёвое фондирование."),
            "supports": ["ROE 24% устойчив", "payout около 50% предсказуем"],
            "drags": ["чувствительность к ставке"],
            "confidence": "оценка держится на сохранении маржи",
        },
        "what_would_change": ["резкое падение процентной маржи", "смена дивполитики"],
    }
    base.update(over)
    return base


class TestGate:
    def test_clean_result_passes(self, tabs, fair):
        assert ov._gate(_result(), tabs, fair, "SBER") == []

    def test_advice_wording_is_blocked(self, tabs, fair):
        """Конституция платформы: без «купить/продать» и целевых цен."""
        bad = _result()
        bad["fair_value_story"]["why"] += " Рекомендуем покупать на снижении."
        assert "banned_wording" in ov._gate(bad, tabs, fair, "SBER")

    def test_invented_numbers_are_blocked(self, tabs, fair):
        """🔴 Модель дорисовывает правдоподобные величины — на этом горел макро-выпуск."""
        bad = _result()
        bad["fair_value_story"]["supports"] = ["рентабельность капитала 87% исключительна"]
        notes = ov._gate(bad, tabs, fair, "SBER")
        assert any(n.startswith("ungrounded_numbers") for n in notes)

    def test_rounding_is_allowed(self, tabs, fair):
        """«Около 24%» при 24,17 — живая проза, а не выдумка."""
        ok = _result()
        ok["fair_value_story"]["why"] = ("Ожидаемая доходность около 24% против барьера "
                                         "18,5%, разрыв даёт запас прочности бизнесу.")
        assert ov._gate(ok, tabs, fair, "SBER") == []

    def test_own_fair_price_is_blocked(self, tabs, fair):
        """🔴 Второе число другой методикой на той же карточке уже ломало доверие."""
        bad = _result()
        bad["fair_value_story"]["why"] = ("По нашему расчёту справедливая цена 650 ₽, "
                                          "что существенно выше рынка и отражает силу "
                                          "франшизы банка сегодня.")
        notes = ov._gate(bad, tabs, fair, "SBER")
        assert any(n.startswith("fair_price_mismatch") or n.startswith("ungrounded")
                   for n in notes)

    def test_pillar_without_source_is_blocked(self, tabs, fair):
        """Нельзя рассуждать о вкладке, разбора которой у компании нет."""
        bad = _result()
        bad["pillars"] = bad["pillars"] + [
            {"tab": "institutions", "stance": "слабость", "point": "риск изъятия высок"}]
        notes = ov._gate(bad, tabs, fair, "SBER")
        assert any(n.startswith("pillar_without_source") for n in notes)

    def test_foreign_ticker_is_blocked(self, tabs, fair):
        bad = _result()
        bad["verdict"] += " В отличие от VTBR, у банка выше рентабельность капитала."
        assert any(n.startswith("foreign_ticker") for n in ov._gate(bad, tabs, fair, "SBER"))

    def test_empty_verdict_is_blocked(self, tabs, fair):
        assert "verdict_too_short" in ov._gate(_result(verdict="Хороший банк."),
                                               tabs, fair, "SBER")


class TestBuild:
    def test_thin_card_is_skipped(self, tmp_path, monkeypatch, db):
        """Меньше трёх разборов — свода не выйдет, честнее не делать вовсе."""
        monkeypatch.setattr(ov, "COMPANIES_DIR", tmp_path)
        d = tmp_path / "THIN"
        d.mkdir()
        (d / "business_model.md").write_text("Небольшой бизнес.", encoding="utf-8")
        assert ov.build_for_ticker(db, "THIN") is None

    def test_rejected_is_saved_not_published(self, tmp_path, monkeypatch, db):
        """Отклонённое не теряется: видно в отладке, на витрину не идёт."""
        monkeypatch.setattr(ov, "COMPANIES_DIR", tmp_path)
        d = tmp_path / "BAD"
        d.mkdir()
        for name in ("business_model.md", "financials_summary.md", "governance_summary.md"):
            (d / name).write_text("Разбор компании с числом 100.", encoding="utf-8")
        monkeypatch.setattr(ov, "_fair_value", lambda *a, **k: None)
        from app.services import llm
        monkeypatch.setattr(llm, "complete",
                            lambda *a, **k: {"verdict": "мало", "pillars": []})
        row = ov.build_for_ticker(db, "BAD")
        assert row is not None and row.status == "rejected"
        assert row.verdict is None and row.gate_notes
        assert ov.current(db, "BAD") is None, "на витрину отклонённое не попадает"

    def test_published_is_returned_by_current(self, tmp_path, monkeypatch, db):
        monkeypatch.setattr(ov, "COMPANIES_DIR", tmp_path)
        d = tmp_path / "GOOD"
        d.mkdir()
        payload = ("Выручка 4642 млрд ₽, ROE 24%, дивдоходность 14,65%, "
                   "балл управления 4,2.")
        for name in ("business_model.md", "financials_summary.md", "governance_summary.md"):
            (d / name).write_text(payload, encoding="utf-8")
        monkeypatch.setattr(ov, "_fair_value", lambda *a, **k: {
            "fair_price": 426.89, "current_price": 282.78, "upside_pct": 51.0,
            "expected_return_pct": 24.17, "hurdle_pct": 18.45,
            "drivers": {"roe0": 0.2402, "payout0": 0.498, "governance_score": 4.2}})
        from app.services import llm
        monkeypatch.setattr(llm, "complete", lambda *a, **k: _result())
        row = ov.build_for_ticker(db, "GOOD")
        assert row.status == "published", row.gate_notes
        assert ov.current(db, "GOOD").verdict.startswith("Крупный розничный банк")
        assert json.loads(json.dumps(row.fair_value_story))["direction"] == "выше рынка"


def test_endpoint_returns_204_when_no_synthesis(client):
    """🔴 Пустой свод отдаётся как 204, а не как 500.

    Боевой прогон: имя Response не было импортировано, и эндпоинт падал на каждой
    компании, у которой свода ещё нет — то есть на всех. Тест на «нет данных» ловит
    это раньше деплоя.
    """
    r = client.get("/api/companies/by-ticker/NOSUCHX/overview-synthesis")
    assert r.status_code == 204, r.text


def test_direction_must_match_upside(tabs, fair):
    """🔴 Число и объяснение под ним не имеют права противоречить друг другу."""
    bad = _result()
    bad["fair_value_story"]["direction"] = "ниже рынка"   # при апсайде +51%
    notes = ov._gate(bad, tabs, fair, "SBER")
    assert any(n.startswith("direction_vs_upside") for n in notes)
