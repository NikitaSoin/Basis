"""Что видит аналитик в задании (владелец 2026-09-13): источник и роль статьи, квоты на очаг,
новости у экономиста, мандат старшего аналитика в системном задании, заметка гейта за
пустое situation."""
from datetime import date, timedelta

from app.models.geo_digest import GeoDigestArticle
from app.services import barometer_daily as bd, handoffs, inst_state, macro_state


def _art(i, target, key, d=None):
    return GeoDigestArticle(target=target, title=f"Статья {i} {key}", summary="пересказ " * 5,
                            published_at=d or (date.today() - timedelta(days=i % 10)),
                            source_url=f"https://example.test/{target}/{key}/{i}", source_key=key)


def test_гео_квоты_по_ролям_и_источник(db):
    # 20 событийных (nyt_world) + 15 аналитических (isw) по СВО
    db.add_all([_art(i, "svo", "nyt_world") for i in range(20)] + [_art(100 + i, "svo", "isw") for i in range(15)])
    db.add_all([_art(200 + i, "middle_east", "haaretz") for i in range(3)])
    db.flush()
    arts = bd.gather_articles(db, window_days=14)
    svo = arts["svo"]
    roles = [a["role"] for a in svo]
    assert roles.count("аналитика") == min(15, bd._MAX_ANALYSIS_PER_SCOPE)
    assert roles.count("событие") == min(20, bd._MAX_EVENT_PER_SCOPE)
    assert all(a["source"] for a in svo) and any(a["source"] == "ISW" for a in svo)
    assert len(arts["middle_east"]) == 3 and arts["middle_east"][0]["source"] == "Haaretz"


def test_институты_и_экономика_видят_источник(db):
    db.add_all([_art(300 + i, "institutions", "genproc") for i in range(2)]
               + [_art(400 + i, "macro", "cbr_press") for i in range(2)]
               + [_art(500, "business", "kommersant_politics")])
    db.flush()
    inst = inst_state._articles(db)
    assert inst and all(a["source"] for a in inst)
    mac = macro_state._articles(db)
    assert len(mac) >= 3 and {a["topic"] for a in mac} >= {"macro", "business"}
    assert any(a["source"] == "Банк России" for a in mac)


def test_мандат_в_системных_заданиях_и_гейт():
    assert "МАНДАТ СТАРШЕГО АНАЛИТИКА" in bd._mandate_prompt()
    assert "МАНДАТ СТАРШЕГО АНАЛИТИКА" in inst_state._SYSTEM and "situation" in inst_state._SYSTEM
    assert "МАНДАТ СТАРШЕГО АНАЛИТИКА" in macro_state._SYSTEM and "situation" in macro_state._SYSTEM
    assert "УДАРЫ ПО ИНФРАСТРУКТУРЕ" in handoffs.mandate_block("geo")
    assert "ЭЛЕКТОРАЛЬНЫЕ ЦИКЛЫ" in handoffs.mandate_block("geo")
    assert "УКРАИНСКАЯ ЭКОНОМИКА" in handoffs.mandate_block("macro")
    notes = handoffs.situation_gate_notes({"regions": {"svo": {"situation": {}}}}, "geo")
    assert any("svo" in n and "мандат" in n for n in notes)
    ok = {"situation": {"what_is_happening": "x", "trajectory": {"most_likely": "y"}, "unknowns": [{"gap": "z"}]}}
    assert handoffs.situation_gate_notes(ok, "macro") == []
    full_svo = {"regions": {"svo": {"situation": {**ok["situation"], "strikes": {"period": "a"},
                                                  "battlefield": {"direction": "b"}}}}}
    assert handoffs.situation_gate_notes(full_svo, "geo") == []
