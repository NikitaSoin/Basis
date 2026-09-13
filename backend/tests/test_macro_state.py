"""Гейт макро-состояния — без LLM и без БД.

Проверяем ровно те свойства, ради которых состояние отличается от выпуска:
каркас из тринадцати блоков не худеет, изменение без обоснования откатывается,
прогноз без пусковых условий помечается, диагноз обязателен.
"""
from app.services.macro_state import BLOCKS, MARKS, _gate


def _block(key, level="высокий", rationale="убедительное обоснование длиннее двадцати знаков"):
    return {"key": key, "title": key, "level": level, "mark": "факт",
            "delta_rationale": rationale, "evidence": [{"indicator_code": "x", "value": 1}]}


def _full(level="высокий"):
    return {"blocks": [_block(k, level) for k, _ in BLOCKS],
            "diagnosis": {"current_state": "рост", "mechanism": "спрос", "regime": "перегрев",
                          "main_constraint": "труд"},
            "forecast": {"variables": {"inflation": {"probabilities": {"base": 0.5, "favorable": 0.2, "adverse": 0.4},
                                                     "most_likely": "base", "most_dangerous": "adverse"}}},
            "revision_triggers": [{"condition": "базовая инфляция выше 8%"}],
            "handoffs": {"to_geo": {"fiscal_capacity": "дефицит 2,5% ВВП", "exhaustion_points": ["x"],
                                    "endurance_horizon_months": "18–24, В"},
                         "to_inst": {"fiscal_origin": "рента 30%", "crisis_proximity": "далеко",
                                     "inflation_as_destroyer": "6,3%"}}}


def test_пропавший_блок_переносится_с_прошлой_версии():
    prev = _full()
    fresh = _full(); fresh["blocks"] = [b for b in fresh["blocks"] if b["key"] != "labor"]
    out, notes = _gate(fresh, prev)
    keys = [b["key"] for b in out["blocks"]]
    assert keys == [k for k, _ in BLOCKS], "порядок и полнота тринадцати блоков обязаны сохраниться"
    labor = next(b for b in out["blocks"] if b["key"] == "labor")
    assert labor.get("carried_over") is True
    assert any("labor" in n and "перенесён" in n for n in notes)


def test_изменение_уровня_без_обоснования_откатывается():
    prev = _full("высокий")
    fresh = _full("низкий")
    for b in fresh["blocks"]:
        b["delta_rationale"] = "уточнено"          # отписка короче 20 знаков
    out, notes = _gate(fresh, prev)
    assert all(b["level"] == "высокий" for b in out["blocks"])
    assert sum("без обоснования" in n for n in notes) == len(BLOCKS)


def test_изменение_с_обоснованием_проходит():
    out, notes = _gate(_full("низкий"), _full("высокий"))
    assert all(b["level"] == "низкий" for b in out["blocks"])
    assert not any("без обоснования" in n for n in notes)


def test_вероятности_нормализуются_и_маркировка_чинится():
    fresh = _full(); fresh["blocks"][0]["mark"] = "по ощущениям"
    out, notes = _gate(fresh, None)
    probs = out["forecast"]["variables"]["inflation"]["probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 0.01
    assert out["blocks"][0]["mark"] in MARKS
    assert any("маркировка" in n for n in notes)


def test_без_пусковых_условий_и_диагноза_есть_заметки():
    fresh = _full(); fresh["revision_triggers"] = []; fresh["diagnosis"]["regime"] = ""
    _, notes = _gate(fresh, None)
    assert any("revision_triggers" in n for n in notes)
    assert any("diagnosis.regime" in n for n in notes)


def test_первая_сборка_без_прошлой_версии():
    out, notes = _gate(_full(), None)
    assert len(out["blocks"]) == len(BLOCKS)
    assert not any("перенесён" in n for n in notes)
