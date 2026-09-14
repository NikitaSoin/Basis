"""Журнал прогнозов: извлечение из выпусков, запись без дублей, сверка с подменённым судьёй, калибровка."""
from datetime import date, timedelta

from app.models.forecast_journal import ForecastEntry
from app.services import forecast_journal as fj


def test_извлечение_из_выпусков():
    geo = {"as_of": "2026-09-14", "regions": {"svo": {"scenarios": {"items": [
        {"key": "S3", "label": "затяжной конфликт", "p6m": 0.6, "p18m": 0.5, "note": "механизм"},
        {"key": "S2", "label": "перемирие", "p6m": 0.25, "p18m": 0.3}], "triggers": ["энергоперемирие"]}}}}
    g = fj.extract("geo", geo)
    assert len(g) == 4 and {x["horizon"] for x in g} == {"6m", "18m"} and g[0]["triggers"] == ["энергоперемирие"]
    macro = {"as_of": "2026-09-14", "forecast": {"variables": {"key_rate": {"base": "14% до декабря", "adverse": "рост до 16%",
             "probabilities": {"base": 0.6, "adverse": 0.25}, "mechanism": "инфляция издержек"}}},
             "revision_triggers": [{"condition": "инфляция выше 9%"}]}
    m = fj.extract("macro", macro)
    assert len(m) == 2 and m[0]["scope"] == "key_rate" and m[0]["p"] == 0.6 and m[0]["triggers"] == ["инфляция выше 9%"]
    inst = {"as_of": "2026-09-14", "forecast_card": {"forecast_6m": "дрейф продолжится", "forecast_2y": "закрепление",
            "scenarios_5y": [{"name": "ловушка", "probability": 0.5}], "refutation_criteria": ["отмена указа"]}}
    i = fj.extract("inst_state", inst)
    assert [x["horizon"] for x in i] == ["6m", "2y", "5y"] and i[2]["p"] == 0.5
    council = {"label": "экзамен:strikes", "synthesis": {"forecast": {"most_dangerous": "удары по газу",
               "probabilities": [{"outcome": "сохранение", "p": 0.5, "horizon": "3 мес", "basis": "плато"}]}}}
    c = fj.extract("council", council)
    assert len(c) == 2 and c[0]["horizon"] == "3m" and c[1]["outcome"].startswith("наиболее опасный")
    assert fj.p_words(0.5) == "скорее да" and fj.p_words(0.1) == "маловероятно" and fj.p_words(None) is None


def test_запись_без_дублей_и_сверка(db, monkeypatch):
    geo = {"as_of": "2026-01-10", "regions": {"svo": {"scenarios": {"items": [
        {"key": "S3", "label": "тестовый затяжной конфликт", "p6m": 0.6, "p18m": 0.5}]}}}}
    n1 = fj.record(db, "geo", geo, version_id=1)
    n2 = fj.record(db, "geo", geo, version_id=2)
    assert n1 == 2 and n2 == 0
    rows = db.query(ForecastEntry).filter(ForecastEntry.outcome == "тестовый затяжной конфликт").all()
    assert len(rows) == 2 and all(r.status == "open" and r.methodology_version for r in rows)
    six = next(r for r in rows if r.horizon == "6m")
    assert six.review_at == date(2026, 1, 10) + timedelta(days=182) and six.p_words == "скорее да"

    monkeypatch.setattr(fj, "judge_entry", lambda db_, e: {"status": "refuted" if e.horizon == "6m" else "confirmed",
                                                          "realized": "перемирие с 01.05", "mechanism_note": "истощение",
                                                          "lesson": "учитывать ресурсный потолок"})
    stats = fj.review_due(db, today=date(2027, 9, 1))
    assert stats["confirmed"] >= 1 and stats["refuted"] >= 1
    six = db.get(ForecastEntry, six.id)
    assert six.status == "refuted" and six.lesson and six.resolved_at
    cal = fj.calibration(db)
    assert "geo" in cal and cal["geo"]["n"] >= 2
    lst = fj.listing(db, source="geo")
    assert lst["count"] >= 2 and "calibration" in lst
