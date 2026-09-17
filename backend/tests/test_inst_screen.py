"""Каркас экрана «Оценка ситуации» условий для бизнеса — без LLM и без БД.

Проверяем ровно то, что держит код, а не агент: накопление карточек между сборками (до
квартала, по id и по паре дата+заголовок), дайджест по классу масштаба, ровно шесть измерений
с переносом пропавших, ветви с отметками и нормализацией вероятностей, слова вероятностей,
словарь замен терминов и внутренние коды, следствие без адресата, причина через намерения,
требование владельца о «белых списках», сборка витрины из опубликованного снимка.
"""
from datetime import date, timedelta

from app.services import inst_screen as I

AS_OF = date(2026, 9, 18)


def _card(cid, days_ago, scale="умеренный", digest=False, series=None, title=None, cons_text=None):
    d = (AS_OF - timedelta(days=days_ago)).isoformat()
    return {
        "id": cid, "date": d, "type": "собственность", "status": "действует",
        "title": title or f"Событие {cid}",
        "fact": "Указ от такого-то числа передал актив во временное управление; орган назван.",
        "change": "Создаёт прецедент передачи актива решением правительства без суда.",
        "who": "Владельцы объектов инфраструктуры, частные и иностранные; их кредиторы.",
        "who_tags": ["инфраструктура", "иностранные владельцы"],
        "means": {"text": "Стоимость капитала выше, горизонт инвестиций короче.", "metrics": ["стоимость капитала"],
                  "scale": scale, "horizon": "годы", "reversibility": "надолго"},
        "consequences": [{"kind": "property", "text": cons_text or "защита собственности для активов инфраструктуры ослабла"}],
        "driver": "Приоритет бесперебойности инфраструктуры и потребность бюджета в доходах.",
        "series": {"key": series, "step": 1 if series else None},
        "digest": digest,
        "confidence": {"level": "высокая", "why": "указ опубликован"},
        "source": "указ от 25.08.2026",
    }


def _dim(key, cards):
    return {"key": key, "level": "низкая", "arrow": "вниз", "arrow_note": "снизилась за квартал",
            "text": "За квартал четыре передачи активов по разным основаниям.",
            "consequence": "премия за риск для рынка в целом должна быть выше", "cards": cards}


def _branch(key, p, base=False, worst=False, how="проект бюджета без новых ставок"):
    return {"key": key, "label": "ветвь словами", "geo_branch": "S3", "geo_note": "при затяжном противостоянии",
            "p": p, "base": base, "worst": worst, "how_we_get_there": how,
            "what": "что", "who": "для кого", "means": "что значит",
            "consequences": ["премия за риск для рынка в целом остаётся выше нормы"]}


def _screen():
    cards = [_card("c1", 3, "значимый", digest=True, series="s1"), _card("c2", 10, "режимный", digest=True),
             _card("c3", 20, "малый"), _card("c4", 25, "умеренный", digest=True,
                                             title="Белые списки сервисов при отключениях интернета закреплены")]
    return {
        "period": {"from": (AS_OF - timedelta(days=30)).isoformat(), "to": AS_OF.isoformat()},
        "vector": "За месяц условия ужесточились для владельцев инфраструктуры; для всех — предсказуемость снизилась, премия за риск выше.",
        "cards": cards,
        "series": [{"key": "s1", "title": "Передачи активов продолжаются", "pattern": "закономерность",
                    "events": ["17.08 — одно", "31.08 — другое"], "accumulated": "предсказуемость условий снизилась для всех",
                    "p_continue": 0.8, "stop": "пауза в два квартала", "status": "активна"}],
        "dimensions": [_dim(k, ["c1", "c2"]) for k in I.DIMENSION_KEYS],
        "economy": ["Деньги дороже дольше.", "Бюджет ищет доходы.", "Горизонт инвестиций короче."],
        "sectors": [{"who": "экспортёры", "tags": ["LKOH"], "direction": "мешает", "metric": "выручка", "measured": "1", "stability": "х"},
                    {"who": "госзаказ", "tags": [], "direction": "помогает", "metric": "выручка", "measured": "1", "stability": "х"},
                    {"who": "малый бизнес", "tags": [], "direction": "помогает", "metric": "издержки", "measured": "1", "stability": "х"}],
        "tax_target": [{"feature": "высокая рентабельность", "why": "доначисления"}, {"feature": "экспортная выручка", "why": "дефицит"},
                       {"feature": "иностранные владельцы", "why": "передачи"}],
        "direction": [{"key": k, "arrow": "вниз", "why": "серия не прерывалась"} for k in I.DIMENSION_KEYS],
        "branches": [_branch("continuation", 0.5, base=True), _branch("fiscal", 0.2, worst=True),
                     _branch("state_expansion", 0.2), _branch("normalization", 0.1)],
        "thresholds": ["проект бюджета в конце сентября", "заседание ЦБ 23 октября"],
    }


def _fresh(**kw):
    return {"as_of": AS_OF.isoformat(), "screen": _screen(), **kw}


def test_слова_вероятностей():
    assert I.p_words(0.5) == "скорее да"
    assert I.p_words(0.1) == "маловероятно"
    assert I.p_words("x") is None


def test_чистый_экран_без_замечаний():
    fresh = _fresh()
    notes = I.inst_screen_gate(fresh, None)
    assert notes == [], notes
    sc = fresh["screen"]
    assert [d["key"] for d in sc["dimensions"]] == list(I.DIMENSION_KEYS)
    assert sc["branches"][0]["key"] == "continuation" and sc["branches"][0]["p_words"] == "скорее да"
    assert sc["series"][0]["p_continue_words"] == "вероятно"


def test_экран_не_вернулся_переносится_или_помечается():
    prev = _fresh()
    fresh = {"as_of": AS_OF.isoformat()}
    notes = I.inst_screen_gate(fresh, prev)
    assert fresh["screen"].get("carried_over") is True and any("перенесён" in n for n in notes)
    fresh2 = {"as_of": AS_OF.isoformat()}
    notes = I.inst_screen_gate(fresh2, None)
    assert "screen" not in fresh2 and any("не собран" in n for n in notes)


def test_накопление_карточек_до_квартала_и_дедупликация():
    prev = _fresh()
    prev["screen"]["cards"] = [_card("old70", 70), _card("old100", 100), _card("dup-old", 12, title="Тот же указ")]
    fresh = _fresh()
    fresh["screen"]["cards"] = [_card("new1", 1), _card("dup-new", 12, title="Тот же указ")]
    notes = I.inst_screen_gate(fresh, prev)
    ids = [c["id"] for c in fresh["screen"]["cards"]]
    assert ids == ["new1", "dup-new", "old70"], ids     # по дате вниз; 100 дней — за квартал; дубль по дате+заголовку снят
    assert any("сохранены" in n for n in notes)


def test_карточка_без_id_и_без_следствия():
    fresh = _fresh()
    c = _card("", 2); c["consequences"] = []
    fresh["screen"]["cards"] = [c]
    notes = I.inst_screen_gate(fresh, None)
    assert c["id"] and any("без id" in n for n in notes)
    assert any("без следствия" in n for n in notes)


def test_дайджест_дополняется_и_режется_по_масштабу():
    fresh = _fresh()
    for c in fresh["screen"]["cards"]:
        c["digest"] = False
    notes = I.inst_screen_gate(fresh, None)
    flagged = {c["id"] for c in fresh["screen"]["cards"] if c.get("digest")}
    assert flagged == {"c1", "c2", "c4"}, flagged            # три с наибольшим масштабом, «малый» c3 не вошёл
    assert any("дополнено кодом" in n for n in notes)

    fresh = _fresh()
    fresh["screen"]["cards"] = [_card(f"d{i}", i, "значимый", digest=True) for i in range(7)]
    notes = I.inst_screen_gate(fresh, None)
    assert sum(1 for c in fresh["screen"]["cards"] if c["digest"]) == 5
    assert any("оставлены пять" in n for n in notes)


def test_измерений_ровно_шесть_перенос_и_ссылки():
    prev = _fresh()
    fresh = _fresh()
    dims = [d for d in fresh["screen"]["dimensions"] if d["key"] != "openness"]
    dims[0]["arrow"] = "вбок"; dims[1]["cards"] = ["нет-такой"]
    dims.append({"key": "extra", "arrow": "вверх"})
    fresh["screen"]["dimensions"] = dims
    notes = I.inst_screen_gate(fresh, prev)
    out = fresh["screen"]["dimensions"]
    assert [d["key"] for d in out] == list(I.DIMENSION_KEYS)
    assert next(d for d in out if d["key"] == "openness").get("carried_over") is True
    assert out[0]["arrow"] == "смешанно" and any("не из списка" in n for n in notes)
    assert any("несуществующие карточки" in n for n in notes)
    assert any("лишние измерения" in n for n in notes)
    assert out[0]["title"] == "Предсказуемость условий"


def test_стрелка_без_карточек_помечается():
    fresh = _fresh()
    fresh["screen"]["dimensions"][2]["cards"] = []
    notes = I.inst_screen_gate(fresh, None)
    assert any("taxes" in n and "не раскрывается в карточки" in n for n in notes)


def test_ветви_нормализация_отметки_и_порог():
    fresh = _fresh()
    br = fresh["screen"]["branches"]
    br[0]["p"] = 0.6                     # сумма 1.1 → нормализуется
    br[0]["base"] = False                # базовой нет — код пометит самую вероятную
    br[1]["worst"] = False               # неблагоприятной нет — заметка
    br[2]["how_we_get_there"] = ""
    br[3]["geo_branch"] = None; br[3]["geo_note"] = None
    notes = I.inst_screen_gate(fresh, None)
    out = fresh["screen"]["branches"]
    assert abs(sum(b["p"] for b in out) - 1.0) < 0.01 and any("нормализована" in n for n in notes)
    assert out[0]["key"] == "continuation" and out[0]["base"] is True
    assert any("неблагоприятная" in n for n in notes)
    assert any("state_expansion" in n and "порогового события" in n for n in notes)
    assert any("normalization" in n and "не привязана" in n for n in notes)


def test_мало_ветвей_переносятся_с_прошлой_версии():
    prev = _fresh()
    fresh = _fresh(); fresh["screen"]["branches"] = fresh["screen"]["branches"][:1]
    notes = I.inst_screen_gate(fresh, prev)
    assert len(fresh["screen"]["branches"]) == 4 and all(b.get("carried_over") for b in fresh["screen"]["branches"])
    assert any("перенесены" in n for n in notes)


def test_словарь_терминов_и_коды():
    fresh = _fresh()
    fresh["screen"]["vector"] = "Институты ослабли: режим санкций и рента госкомпаний; сигнал M3 и рентабельность выше, масштаб режимный."
    notes = I.inst_screen_gate(fresh, None)
    assert any("«Институты»" in n and "условия для бизнеса" in n for n in notes)
    assert any("«режим»" in n for n in notes)
    assert any("«рента»" in n for n in notes)
    assert any("внутренние коды" in n and "M3" in n for n in notes)
    # «рентабельность» и «режимный» словарём не ловятся
    clean = _fresh()
    clean["screen"]["vector"] = "Рентабельность экспортёров под давлением; класс масштаба режимный; премия за риск для всех выше."
    assert not any("язык" in n for n in I.inst_screen_gate(clean, None))


def test_следствие_без_адресата_и_причина_через_намерения():
    fresh = _fresh()
    fresh["screen"]["cards"][0]["consequences"] = [{"kind": "equity", "text": "риски выше"}]
    fresh["screen"]["cards"][1]["consequences"] = [{"kind": "equity", "text": "премия за риск для экспортёров должна быть выше"}]
    fresh["screen"]["cards"][1]["driver"] = "Правительство хочет наказать владельца."
    notes = I.inst_screen_gate(fresh, None)
    assert any("c1" in n and "без адресата" in n for n in notes)
    assert not any("c2" in n and "без адресата" in n for n in notes)
    assert any("c2" in n and "намерения" in n for n in notes)


def test_белые_списки_обязательны():
    fresh = _fresh()
    fresh["screen"]["cards"][3]["title"] = "Обычное событие"
    notes = I.inst_screen_gate(fresh, None)
    assert any("белых списков" in n for n in notes)
    fresh = _fresh()
    assert not any("белых списков" in n for n in I.inst_screen_gate(fresh, None))


def test_серия_переносится_и_ссылка_на_чужую_серию():
    prev = _fresh()
    fresh = _fresh(); fresh["screen"]["series"] = []
    fresh["screen"]["cards"][1]["series"] = {"key": "нет-такой", "step": 2}
    notes = I.inst_screen_gate(fresh, prev)
    assert fresh["screen"]["series"][0].get("carried_over") is True
    assert any("нет-такой" in n for n in notes)


def test_сборка_витрины(monkeypatch):
    class Row:
        def __init__(self, payload):
            self.payload = payload; self.created_at = None
    snap = _fresh()
    snap["screen"]["cards"].append(_card("q1", 60, "значимый", digest=True))   # квартал, в дайджест не входит
    snap["screen"]["cards"].append(_card("o1", 120, "значимый"))               # старше квартала
    I.inst_screen_gate(snap, None)
    rows = {"inst_state": Row(snap), "geo": Row({"as_of": "2026-09-17"})}
    from app.services import barometer_store
    monkeypatch.setattr(barometer_store, "current_row", lambda db, kind: rows.get(kind))
    out = I.assemble(db=None)
    assert out["available"] and out["dates"] == {"inst": AS_OF.isoformat(), "geo": "2026-09-17"}
    periods = {c["id"]: c["period"] for c in out["cards"]}
    assert periods["c1"] == "month" and periods["q1"] == "quarter" and periods["o1"] == "older"
    assert [c["id"] for c in out["digest"]] == ["c2", "c1", "c4"]          # по масштабу: режимный → значимый → умеренный
    assert out["counts"] == {"month": 4, "quarter": 5, "series": 1}
    assert out["dimensions"][0]["cards"][0] == {"id": "c1", "date": snap["screen"]["cards"][0]["date"], "title": "Событие c1"}
    assert out["series"][0]["cards"][0]["id"] == "c1"
    assert out["branches"][0]["p_words"] == "скорее да"
    assert out["labels"]["dimensions"]["taxes"] == "Налоговая нагрузка и её стабильность"

    monkeypatch.setattr(barometer_store, "current_row", lambda db, kind: None)
    assert I.assemble(db=None)["available"] is False


def test_блоки_в_задание(monkeypatch):
    txt = I.prev_screen_block(_fresh())
    assert "карточка c1" in txt and "серия s1" in txt and "ветви:" in txt
    assert "первая сборка" in I.prev_screen_block(None)
    from app.services import barometer_store
    monkeypatch.setattr(barometer_store, "current_row", lambda db, kind: None)
    txt = I.geo_branches_block(db=None, peers=None)
    assert "geo_branch" in txt


def test_спецификация_на_диске_читается_по_частям():
    txt = I.spec_parts("Часть 5")
    assert isinstance(txt, str)
    if txt:
        assert "следств" in txt.lower()
