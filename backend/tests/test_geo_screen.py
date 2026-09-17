"""Каркас экрана «Оценка ситуации» — без LLM и без БД.

Проверяем ровно то, что держит код, а не агент: слова вероятностей по единой шкале,
перенос пропавшего очага с прошлой версии, метки базовой и опасной ветвей, пороговое
событие у каждой ветви, словарь замен терминов, лестница финансирования у очага-участника,
совпадение колонок сравнения по ветвям с ветвями геополитика, сборка из двух сводок.
"""
import json

from app.services import geo_screen as G


_LABELS = {"S1": "прорыв к миру", "S2": "перемирие или заморозка", "S3": "затяжное противостояние",
           "S4": "расширение противостояния"}


def _branch(key, p6, p18, base=False, danger=False, how="подписанное соглашение с графиком отвода"):
    # подпись без внутреннего кода: код законен только в поле key
    return {"key": key, "label": _LABELS.get(key, "ветвь"), "p6m": p6, "p18m": p18, "base": base,
            "most_dangerous": danger, "how_we_get_there": how,
            "what": "что", "why": "почему", "how_long": "долго", "for_us": "для нас"}


def _hotspot(config="участник"):
    return {
        "config": config,
        "state": {"phase": "затяжное противостояние",
                  "summary": ["один.", "два.", "три.", "четыре.", "пять."],
                  "goals": [{"side": "А", "goal": "цель", "direction": "к цели", "speed": "так же",
                             "achievable": "при сохранении нынешних условий не достигается", "status": "В"},
                            {"side": "Б", "goal": "цель", "direction": "стоит", "speed": "медленнее",
                             "achievable": "при сохранении нынешних условий достижима", "status": "В"}],
                  "time": [{"axis": "военный баланс", "side": "А", "shift": "медленно", "why": "почему"},
                           {"axis": "деньги", "side": "ничья", "shift": "—", "why": "почему"},
                           {"axis": "поддержка", "side": "Б", "shift": "—", "why": "почему"}],
                  "time_verdict": "ничья"},
        "forces": {"items": [{"who": "1", "text": "т"}, {"who": "2", "text": "т"}, {"who": "3", "text": "т"}],
                   "holds": ["x"], "change": ["y"],
                   "duration": {"label": "год и дольше", "why": "удерживающих сил больше, чем меняющих, и они структурные",
                                "shortens": "дешёвая нефть плюс санкции"},
                   "twist": None},
        "scenarios": {"branches": [_branch("S3", 0.42, 0.33, base=True), _branch("S4", 0.40, 0.39, danger=True),
                                   _branch("S2", 0.14, 0.20), _branch("S1", 0.04, 0.08)],
                      "nearest": {"event": "голосование", "what_it_triggers": "переход"},
                      "other_thresholds": ["а", "б"]},
        "map": {"kind": "контроль", "dynamics": [{"k": "площадь", "v": "112 285 км²"}], "points": []},
    }


def _screen(**kw):
    return {"screen": {h: _hotspot(G.HOTSPOT_CONFIG[h]) for h in G.HOTSPOTS}, **kw}


def test_слова_вероятностей_по_единой_шкале():
    assert G.p_words(0.04) == "крайне маловероятно"
    assert G.p_words(0.05) == "крайне маловероятно"
    assert G.p_words(0.14) == "маловероятно"
    assert G.p_words(0.20) == "маловероятно"
    assert G.p_words(0.42) == "возможно"
    assert G.p_words(0.60) == "скорее да"
    assert G.p_words(0.85) == "вероятно"
    assert G.p_words(0.95) == "почти наверняка"
    assert G.p_words("x") is None and G.p_words(None) is None


def test_пропавший_очаг_переносится_с_прошлой_версии():
    prev = _screen()
    fresh = _screen(); del fresh["screen"]["atr"]
    notes = G.geo_screen_gate(fresh, prev)
    assert fresh["screen"]["atr"].get("carried_over") is True
    assert any("screen.atr" in n and "перенесён" in n for n in notes)
    # непропавшие очаги — без пометки переноса
    assert "carried_over" not in fresh["screen"]["svo"]


def test_экран_целиком_отсутствует_и_прошлого_нет():
    fresh = {"regions": {}}
    notes = G.geo_screen_gate(fresh, None)
    assert "screen" not in fresh and any("не собран" in n for n in notes)


def test_метки_ветвей_и_слова_вероятностей():
    fresh = _screen()
    br = fresh["screen"]["svo"]["scenarios"]["branches"]
    br[0]["base"] = False                      # базовой нет — код пометит самую вероятную
    br[1]["most_dangerous"] = False            # опасной нет — заметка
    notes = G.geo_screen_gate(fresh, None)
    assert br[0]["base"] is True
    assert br[0]["p6m_words"] == "возможно" and br[3]["p6m_words"] == "крайне маловероятно"
    assert any("наиболее опасная" in n for n in notes)


def test_ветвь_без_порогового_события_и_нормализация():
    fresh = _screen()
    br = fresh["screen"]["middle_east"]["scenarios"]["branches"]
    br[2]["how_we_get_there"] = ""
    br[0]["p6m"] = 0.5  # сумма 1.08 → нормализуется
    notes = G.geo_screen_gate(fresh, None)
    assert any("S2" in n and "порогового события" in n for n in notes)
    assert abs(sum(float(b["p6m"]) for b in br) - 1.0) < 0.01
    assert any("middle_east" in n and "нормализована" in n for n in notes)


def test_словарь_терминов_и_внутренние_коды():
    fresh = _screen()
    fresh["screen"]["svo"]["forces"]["twist"] = "пространство сделки пусто, а хвостовой риск растёт; сценарий S3 базовый"
    notes = G.geo_screen_gate(fresh, None)
    assert any("пространство сделки" in n for n in notes)
    assert any("хвостовой риск" in n for n in notes)
    assert any("внутренние коды" in n and "S3" in n for n in notes)
    # ключ ветви «S3» в поле key — законен, не должен считаться кодом в тексте
    clean = _screen()
    assert not any("внутренние коды" in n for n in G.geo_screen_gate(clean, None))


def test_достижимость_без_оговорки_и_направление_не_из_списка():
    fresh = _screen()
    g = fresh["screen"]["atr"]["state"]["goals"][0]
    g["achievable"] = "не достигается"; g["direction"] = "вбок"
    notes = G.geo_screen_gate(fresh, None)
    assert any("при сохранении" in n for n in notes) and any("направление не из списка" in n for n in notes)


def _effects(with_ladder=True):
    now_txt = "ставка 14%, инфляция 6,27%, дефицит 2,5% ВВП" if with_ladder else "ставка высокая"
    chan = [{"name": "Бюджет", "scale": "значимый", "now": now_txt,
             "how": "лестница финансирования: ступень «займы и резервы», вторая ступень началась" if with_ladder else "как-то",
             "where": "куда", "who": "кто"},
            {"name": "Ставка", "scale": "значимый", "now": "14% при 6,27%", "how": "к", "where": "к", "who": "к"},
            {"name": "Топливо", "scale": "умеренный", "now": "3,8 млн барр", "how": "к", "where": "к", "who": "к"}]
    return {"hotspot_effects": {h: {
        "intro": "и", "now": [{"indicator": f"п{i}", "value": "1", "note": "д"} for i in range(6)],
        "channels": json.loads(json.dumps(chan)), "systemic": "связь",
        "institutional": [{"what": "изъятия 980 млрд", "effect": "э"}, {"what": "указ", "effect": "э"}],
        "sectors": [{"sector": "нефть", "tickers": ["LKOH"], "direction": "помогает", "metric": "м", "numbers": "1", "why": "п"},
                    {"sector": "стройка", "tickers": ["PIKK"], "direction": "мешает", "metric": "м", "numbers": "1", "why": "п"},
                    {"sector": "банки", "tickers": ["SBER"], "direction": "по-разному", "metric": "м", "numbers": "1", "why": "п"}],
        "by_branch": {"columns": [{"key": "S3", "label": "база"}, {"key": "S4", "label": "опасная"},
                                  {"key": "S2", "label": "перемирие"}, {"key": "S1", "label": "мир"}],
                      "rows": [{"indicator": "ставка", "cells": ["14", "16", "12", "11"]}]}} for h in G.HOTSPOTS}}


def test_экономист_лестница_финансирования_и_колонки_ветвей():
    geo = _screen()
    fresh = _effects(with_ladder=True)
    notes = G.macro_screen_gate(fresh, None, geo)
    assert not any("лестницы финансирования" in n for n in notes), notes
    assert not any("не совпадают с ветвями" in n for n in notes), notes

    bad = _effects(with_ladder=False)
    bad["hotspot_effects"]["svo"]["by_branch"]["columns"] = [{"key": "X1", "label": "чужая"}]
    notes = G.macro_screen_gate(bad, None, geo)
    assert any("лестницы финансирования" in n for n in notes)
    assert any("hotspot_effects.svo.by_branch" in n and "не совпадают" in n for n in notes)
    assert any("без единого числа" in n for n in notes)


def test_экономист_пропавший_очаг_и_тикеры():
    prev = _effects()
    fresh = _effects(); del fresh["hotspot_effects"]["atr"]
    fresh["hotspot_effects"]["svo"]["sectors"][0]["tickers"] = ["Лукойл", "LKOH"]
    notes = G.macro_screen_gate(fresh, prev, None)
    assert fresh["hotspot_effects"]["atr"].get("carried_over") is True
    assert any("не тикеры" in n and "Лукойл" in n for n in notes)


def test_сборка_из_двух_сводок(monkeypatch):
    class Row:
        def __init__(self, payload):
            self.payload = payload; self.created_at = None
    geo = _screen(as_of="2026-09-18")
    macro = _effects(); macro["as_of"] = "2026-09-17"
    rows = {"geo": Row(geo), "macro": Row(macro)}
    from app.services import barometer_store
    monkeypatch.setattr(barometer_store, "current_row", lambda db, kind: rows.get(kind))
    out = G.assemble(db=None)
    assert out["available"] and out["order"] == list(G.HOTSPOTS)
    svo = out["hotspots"]["svo"]
    assert svo["dates"] == {"geo": "2026-09-18", "macro": "2026-09-17", "profile": None}
    assert svo["economy"]["channels"][0]["name"] == "Бюджет"
    assert svo["scenarios"]["branches"][0]["p6m_words"] == "возможно"
    assert svo["config_label"].startswith("Россия — непосредственный участник")

    monkeypatch.setattr(barometer_store, "current_row", lambda db, kind: rows.get(kind) if kind == "geo" else None)
    out = G.assemble(db=None)
    assert out["hotspots"]["svo"]["economy"] is None and out["hotspots"]["svo"]["dates"]["macro"] is None


def test_блок_ветвей_в_задание_экономисту():
    txt = G.branches_block(_screen(as_of="2026-09-18"))
    assert "СВО (svo" in txt and "Ближний Восток" in txt and "[базовая]" in txt and "[наиболее опасная]" in txt
    assert "сводки геополитика нет" in G.branches_block(None)


def test_спецификация_на_диске_читается_по_частям():
    txt = G.spec_parts("Часть 8")
    # файл владельца может отсутствовать в чужом окружении — тогда пусто, но не падаем
    assert isinstance(txt, str)
    if txt:
        assert "Язык" in txt or "язык" in txt
