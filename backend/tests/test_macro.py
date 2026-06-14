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


def test_news_macro_extraction(db, monkeypatch):
    """Извлечение чисел из новостей: различение м/м vs г/г, предварительные,
    отбраковка значений вне диапазона."""
    from app.services import news_pipeline as np
    from app.services import llm
    mi.seed_indicators(db)
    db.query(MacroDataPoint).filter(MacroDataPoint.indicator_code.in_(
        ["inflation", "unemployment", "pmi_composite"])).delete(synchronize_session=False)
    db.commit()
    reps = [
        {"id": 0, "title": "Инфляция в РФ за май", "announce": "...", "source": "rbc", "url": "u0"},
        {"id": 1, "title": "Инфляция м/м", "announce": "...", "source": "rbc", "url": "u1"},
        {"id": 2, "title": "Безработица", "announce": "...", "source": "rbc", "url": "u2"},
        {"id": 3, "title": "PMI мусор", "announce": "...", "source": "rbc", "url": "u3"},
    ]
    monkeypatch.setattr(llm, "complete", lambda *a, **k: {"results": [
        {"id": 0, "indicator": "inflation", "metric": "yoy", "value": 9.8, "as_of": "2026-05-31", "is_preliminary": True},
        {"id": 1, "indicator": "inflation", "metric": "mom", "value": 0.5, "as_of": "2026-05-31", "is_preliminary": False},
        {"id": 2, "indicator": "unemployment", "metric": "level", "value": 2.3, "as_of": "2026-05-31", "is_preliminary": False},
        {"id": 3, "indicator": "pmi_composite", "metric": "level", "value": 999, "as_of": "2026-05-31", "is_preliminary": False},
    ]})
    res = np.extract_macro_points(reps, db)
    assert res["saved"] == 3 and res["rejected"] == 1  # PMI 999 вне диапазона
    yoy = db.query(MacroDataPoint).filter_by(indicator_code="inflation", metric="yoy").first()
    mom = db.query(MacroDataPoint).filter_by(indicator_code="inflation", metric="mom").first()
    assert float(yoy.value) == 9.8 and yoy.is_preliminary is True
    assert float(mom.value) == 0.5 and mom.metric == "mom"  # м/м и г/г не спутаны
    assert db.query(MacroDataPoint).filter_by(indicator_code="pmi_composite").count() == 0


def test_interpreter_generate(db, monkeypatch):
    """G: интерпретатор зовёт Pro reasoning и сохраняет разделы."""
    from app.services import macro_interpreter as ip
    from app.services import llm
    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    captured = {}
    def fake_complete(system, user, **k):
        captured["thinking"] = k.get("thinking"); captured["model"] = k.get("model")
        return {"sections": {"current_picture": "Картина", "rate_outlook": "Ставка",
                             "cb_forecast_view": "Прогноз", "market_sectors": "Сектора",
                             "scenarios": "Сценарии"}}
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "pro_model", lambda: "deepseek-v4-pro")
    row = ip.generate(db)
    assert row.sections["current_picture"] == "Картина"
    assert captured["thinking"] is True  # Интерпретатор — РАССУЖДЕНИЕ
    assert captured["model"] == "deepseek-v4-pro"  # Pro, не Flash
    assert ip.get_latest(db).id == row.id


def test_interpretation_endpoint_empty(client, db):
    r = client.get("/api/market/macro/interpretation")
    assert r.status_code == 200  # пусто — честно sections:null, не падаем


def test_forecast_endpoint_empty(client, db):
    r = client.get("/api/market/macro/forecast")
    assert r.status_code == 200 and r.json()["rows"] == []


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
