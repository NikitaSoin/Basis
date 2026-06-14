"""Тесты Макрообзора (Обозреватель, Направление 2)."""
from datetime import date

from app.models.macro import MacroIndicator, MacroDataPoint, RateMeeting
from app.services import macro_ingest as mi


def test_seed_indicators(db):
    n = mi.seed_indicators(db)
    assert db.query(MacroIndicator).count() >= 30
    assert db.get(MacroIndicator, "key_rate") is not None
    # повторный сид не плодит дубли и не падает
    mi.seed_indicators(db)
    assert db.query(MacroIndicator).filter_by(code="key_rate").count() == 1


def test_upsert_revision(db):
    r1 = mi.upsert_point(db, "key_rate", date(2026, 1, 1), "level", 16, ingested_via="file")
    assert r1 == "insert"
    same = mi.upsert_point(db, "key_rate", date(2026, 1, 1), "level", 16)
    assert same == "same"
    rev = mi.upsert_point(db, "key_rate", date(2026, 1, 1), "level", 17, is_preliminary=False)
    assert rev == "revise"
    p = db.query(MacroDataPoint).filter_by(indicator_code="key_rate", as_of=date(2026, 1, 1)).first()
    assert float(p.value) == 17.0 and p.revised_at is not None


def test_backfill_from_csv(db):
    mi.seed_indicators(db)
    res = mi.backfill_from_csv(db)
    assert res.get("rows", 0) > 100
    assert res.get("inserted", 0) > 1000
    kr = db.query(MacroDataPoint).filter_by(indicator_code="key_rate", metric="level").count()
    assert kr > 100  # месячный ряд 2016–2026
    # MoM и YoY инфляции — разные метрики, не спутаны
    assert db.query(MacroDataPoint).filter_by(indicator_code="inflation", metric="mom").count() > 50
    assert db.query(MacroDataPoint).filter_by(indicator_code="inflation", metric="yoy").count() > 50


def test_macro_summary_endpoint(client, db):
    mi.seed_indicators(db)
    db.query(MacroDataPoint).filter_by(indicator_code="key_rate").delete()
    db.commit()
    mi.upsert_point(db, "key_rate", date(2026, 2, 1), "level", 16, ingested_via="file")
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    r = client.get("/api/market/macro?country=ru")
    assert r.status_code == 200
    kr = next((x for x in r.json() if x["code"] == "key_rate"), None)
    assert kr and kr["values"]["level"]["value"] == 15.0
    assert kr["values"]["level"]["change"] == -1.0  # 15 - 16
    assert kr["influence_short"]  # авторский текст влияния отдаётся


def test_series_endpoint(client, db):
    mi.seed_indicators(db)
    db.query(MacroDataPoint).filter_by(indicator_code="key_rate").delete()
    db.commit()
    for d, v in [((2026, 1, 1), 16), ((2026, 2, 1), 16), ((2026, 3, 1), 15)]:
        mi.upsert_point(db, "key_rate", date(*d), "level", v, ingested_via="file")
    r = client.get("/api/market/macro/key_rate/series?metric=level")
    assert r.status_code == 200
    assert len(r.json()["points"]) == 3
    assert client.get("/api/market/macro/nonexistent/series").status_code == 404


def test_rate_endpoint(client, db):
    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    db.add(RateMeeting(decision_date=date(2026, 3, 14), rate_value=15,
                       signal="нейтральный", next_meeting_date=date(2026, 4, 25),
                       consensus_forecast="без изменений", press_summary="выжимка"))
    db.commit()
    r = client.get("/api/market/macro/rate")
    assert r.status_code == 200
    j = r.json()
    assert j["key_rate"]["value"] == 15.0
    assert j["meeting"]["signal"] == "нейтральный"
