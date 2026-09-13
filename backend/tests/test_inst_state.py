"""Гейт институционального снимка — без LLM и без БД."""
from app.services.inst_state import FORECAST_FIELDS, SECTIONS, STATUSES, _gate


def _sec(key, level="низкий", trend="деградирует", rationale="обоснование длиннее двадцати знаков, серия"):
    return {"key": key, "title": key, "level": level, "trend": trend, "status": "Д",
            "delta_rationale": rationale, "evidence": [{"what": "закон", "date": "2026-09-01"}]}


def _full(level="низкий"):
    return {"sections": [_sec(k, level) for k, _ in SECTIONS],
            "forecast_card": {f: "заполнено" for f in FORECAST_FIELDS},
            "verdict": "Формально права собственности закреплены. " * 12,
            "summary": "В 2026 году 3 закона и 5 назначений.",
            "leading_signals": [{"type": "кадровые", "observations": ["а", "б"]}],
            "handoffs": {"to_macro": {"sensitive_credit_share": "40%", "expectations_anchoring": "13,7%",
                                      "inflation_inaccessible_to_rate": "2 п.п."},
                         "to_geo": {"ruling_coalition": "x", "leadership_constraints": "y",
                                    "escalation_beneficiaries": "z"}}}


def test_пропавший_раздел_переносится():
    fresh = _full(); fresh["sections"] = [s for s in fresh["sections"] if s["key"] != "judicial"]
    out, notes = _gate(fresh, _full())
    assert [s["key"] for s in out["sections"]] == [k for k, _ in SECTIONS]
    assert next(s for s in out["sections"] if s["key"] == "judicial").get("carried_over") is True


def test_уровень_без_тренда_и_статус_вне_списка_помечаются():
    fresh = _full(); fresh["sections"][0]["trend"] = None; fresh["sections"][1]["status"] = "точно"
    out, notes = _gate(fresh, None)
    assert any("нет тренда" in n for n in notes)
    assert out["sections"][1]["status"] in STATUSES and any("статус утверждения" in n for n in notes)


def test_изменение_без_обоснования_откатывается():
    fresh = _full("высокий")
    for s in fresh["sections"]: s["delta_rationale"] = "уточнено"
    out, _ = _gate(fresh, _full("низкий"))
    assert all(s["level"] == "низкий" for s in out["sections"])


def test_карточка_прогноза_и_вердикт_проверяются():
    fresh = _full(); fresh["forecast_card"]["refutation_criteria"] = ""; fresh["verdict"] = "Среда плохая."
    _, notes = _gate(fresh, None)
    assert any("refutation_criteria" in n for n in notes)
    assert any("запрещённый формат" in n for n in notes) and any("короче 300" in n for n in notes)


def test_сигнал_из_одного_наблюдения_не_серия():
    fresh = _full(); fresh["leading_signals"] = [{"type": "судебные", "observations": ["одно"]}]
    _, notes = _gate(fresh, None)
    assert any("не серия" in n for n in notes)


def test_чистый_снимок_без_заметок():
    _, notes = _gate(_full(), _full())
    assert notes == [], notes
