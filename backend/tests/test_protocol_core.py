"""Операционный протокол владельца — общее ядро заданий всех агентов (2026-09-14)."""
import os
from datetime import date

from app.services import protocol_core as pc


def test_ядро_извлекается_и_статично():
    a, b = pc.core_text(), pc.core_text()
    assert a == b and 8_000 < len(a) < 20_000
    for k in ("Восемь вопросов", "Матрица маршрутов", "Шаг первый", "Разбор вопроса", "Условное событие",
              "Дисциплина рассуждения", "Прогон по каталогам ошибок", "Краткие карты входа"):
        assert k in a, k
    for k in ("Журнал прогнозов", "Роль критика", "Пять слоёв", "Спуск от контуров"):
        assert k not in a, k
    assert "Регулярный снимок" in pc.core_text(pc.STATE_PARTS)
    assert len(pc.core_text(pc.ASSISTANT_PARTS)) < len(a)


def test_ядро_во_всех_заданиях():
    from app.services import lens_council as lc, probe_questions as pq, macro_state, inst_state, assistant, barometer_daily as bd
    mark = "ОПЕРАЦИОННЫЙ ПРОТОКОЛ АНАЛИТИЧЕСКОГО АГЕНТА"
    assert mark in lc.lens_system("geo_macro") and lc.lens_system("geo_macro").index(mark) < lc.lens_system("geo_macro").index("ТВОЯ МЕТОДИЧКА")
    assert mark in lc.synth_system()
    assert mark in pq._analyst_system("geo")
    assert mark in macro_state._SYSTEM and mark in inst_state._SYSTEM
    assert mark in assistant._ANSWER_FRAMEWORK
    assert mark in bd._protocol_core()


def test_старое_снято_с_полки():
    from app.services.methodology import REGISTRY
    from app.services.handoffs import ALL_SHELF
    assert "geo" not in REGISTRY and "geo" not in ALL_SHELF
    assert "geo_base" in REGISTRY and "geo_events" in REGISTRY


def test_расписание_вечерней_сборки(monkeypatch):
    from app.services.evening_pipeline import plan_for
    monkeypatch.delenv("EVENING_FORCE_ALL", raising=False)
    monkeypatch.setenv("EVENING_MACRO_EVERY_DAYS", "2"); monkeypatch.setenv("EVENING_INST_WEEKDAYS", "sat")
    sat = date(2026, 9, 19); sun = date(2026, 9, 20)
    assert plan_for(sat)["inst"] is True and plan_for(sun)["inst"] is False and plan_for(sat)["geo"] is True
    assert plan_for(sat)["macro"] != plan_for(sun)["macro"]        # через день
    monkeypatch.setenv("EVENING_FORCE_ALL", "1")
    assert plan_for(sun) == {"geo": True, "macro": True, "inst": True, "why": "EVENING_FORCE_ALL=1"}
