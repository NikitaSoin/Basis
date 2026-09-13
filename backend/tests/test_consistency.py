"""Сверка противоречий — кодовый фильтр псевдопротиворечий."""
from app.services.consistency_check import _drop_pseudo


def test_одно_число_у_обеих_сторон_это_согласие():
    items = [{"topic": "дефицит", "severity": "мелочь",
              "claim_a": {"source": "macro", "text": "дефицит 5 795 млрд ₽ (2,5% ВВП)"},
              "claim_b": {"source": "inst_state", "text": "дефицит 5 795 млрд ₽ (2,5% ВВП) за январь–август"}},
             {"topic": "инвестиции", "severity": "существенно",
              "claim_a": {"source": "macro", "text": "инвестиции −14,3% г/г в 1к26"},
              "claim_b": {"source": "inst_state", "text": "инвестиции −9,9% в первом полугодии"}}]
    keep, pseudo = _drop_pseudo(items)
    assert [k["topic"] for k in keep] == ["инвестиции"]
    assert pseudo and "дефицит" in pseudo[0]


def test_существенное_с_общим_числом_не_выбрасывается():
    items = [{"topic": "ставка", "severity": "существенно",
              "claim_a": {"source": "macro", "text": "пауза на 14% с вероятностью 0,55"},
              "claim_b": {"source": "inst_state", "text": "пауза на 14% с вероятностью 0,6"}}]
    keep, pseudo = _drop_pseudo(items)
    assert len(keep) == 1 and not pseudo
