"""Контракты передач между аналитиками — без LLM."""
from app.services import handoffs as H


def test_шесть_передач_замыкают_три_пары():
    codes = sorted(H.HANDOFFS)
    assert codes == ["ГИ", "ГМ", "ИГ", "ИМ", "МГ", "МИ"]
    for h in H.HANDOFFS.values():
        assert h.required and set(h.required) <= set(h.fields), h.code
    # у каждого производителя два исходящих, у каждого потребителя два входящих
    for kind in ("geo", "macro", "inst_state"):
        assert len(H.outgoing(kind)) == 2 and len(H.incoming(kind)) == 2, kind


def test_пустое_обязательное_поле_видно_механически():
    payload = {"handoffs": {"to_geo": {"fiscal_capacity": "дефицит 2,5% ВВП", "exhaustion_points": [],
                                       "endurance_horizon_months": None},
                            "to_inst": {"fiscal_origin": "рента 30%", "crisis_proximity": "далеко",
                                        "inflation_as_destroyer": "6,3%"}}}
    notes = H.gate_notes(payload, "macro")
    assert any("exhaustion_points" in n for n in notes)
    assert any("endurance_horizon_months" in n for n in notes)
    assert not any("to_inst" in n for n in notes), notes


def test_отсутствующий_блок_целиком():
    notes = H.gate_notes({}, "inst_state")
    assert len(notes) == 2 and all("отсутствует целиком" in n for n in notes)


def test_потребитель_получает_только_свой_блок_и_видит_пробелы():
    geo = {"as_of": "2026-09-13", "handoffs": {"to_macro": {"shocks": ["x"], "scenario_probabilities": {},
                                                             "threshold_events": ["y"]},
                                                "to_inst": {"events": ["e"]}}}
    block = H.incoming_block("macro", {"geo": geo, "inst_state": None})
    assert "Геополитика → макроэкономика" in block and '"shocks"' in block
    assert "Институты → макроэкономика" in block and "НЕ ЗАПОЛНЕНА" in block
    assert "to_inst" not in block, "макро не должен видеть блок, адресованный институтам"
    assert "scenario_probabilities" in block and "пустые обязательные поля" in block


def test_роль_перечисляет_обязательные_поля():
    txt = H.prompt_block("geo")
    assert "handoffs.to_macro" in txt and "handoffs.to_inst" in txt and "[обязательно]" in txt
