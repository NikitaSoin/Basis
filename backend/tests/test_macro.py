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
    # Критик логики и агент события — отдельные платные прогоны через тот же
    # llm.complete: в этом тесте они перехватили бы мок и captured показывал бы ИХ
    # вызов, а не генерацию выпуска.
    monkeypatch.setenv("MACRO_LOGIC_CRITIC", "0")
    monkeypatch.setenv("MACRO_EVENT_AGENT", "0")
    monkeypatch.setenv("MACRO_RELEASE_REVIEW", "0")
    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    captured = {}

    # Формат выпуска задан методичкой v3 (Часть 19): пять прогнозов с центром и
    # диапазоном, контраргументы, эпистемические теги. Мок обязан ему соответствовать —
    # иначе автогейт (macro_release_gate) законно отклонит выпуск.
    def _forecast(var):
        return {"variable": var, "horizon": "12 мес", "center": "10", "range": "9-11",
                "driver": "драйвер", "triggers": "триггер", "confidence": "средняя",
                "confidence_why": "почему", "against": "контраргумент",
                "vs_anchor": "против консенсуса"}

    def fake_complete(system, user, **k):
        captured["thinking"] = k.get("thinking"); captured["model"] = k.get("model")
        return {"sections": {
            "headline": "Главный вывод",
            "regime": {"rate": "снижается", "inflation": "замедляется"},
            "theses": [{"claim": "тезис", "chain": "фактор → механизм → следствие",
                        "evidence": "числа", "tag": "оценка"}],
            "forecasts": [_forecast(v) for v in ("Ключевая ставка", "Инфляция",
                                                 "Курс рубля", "ВВП", "Безработица")],
            "against_us": ["сильнейший контраргумент"],
            "sectors": [{"sector": "Финансы", "wind": "смешанный", "channel": "канал",
                         "dispersion": "почему расходятся", "winners": [], "losers": []}],
        }}
    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "pro_model", lambda: "deepseek-v4-pro")
    row = ip.generate(db)
    assert row.sections["headline"] == "Главный вывод"
    assert captured["thinking"] is True  # Интерпретатор — РАССУЖДЕНИЕ
    assert captured["model"] == "deepseek-v4-pro"  # Pro, не Flash
    assert ip.get_latest(db).id == row.id
    # гейт отработал и записал вердикт — выпуск не уходит на витрину неотмеченным
    assert row.source_snapshot.get("gate") in ("ok", "warn")


def test_release_gate_rejects_broken_structure():
    """Гейт обязан отклонять выпуск без обязательных блоков — до публикации.

    Именно этого не хватало: проверка жила у пилотного агента по одной компании, а
    главный артефакт платформы выходил без неё.
    """
    from app.services.macro_release_gate import check_release
    verdict, notes = check_release({"headline": "есть, а остального нет"}, {})
    assert verdict == "reject"
    assert any(n.startswith("missing:") for n in notes)


def test_release_gate_flags_forecast_without_range():
    """Часть 14 методички: точечный прогноз без диапазона запрещён."""
    from app.services.macro_release_gate import check_release
    sections = {"headline": "h", "sectors": [{"sector": "Финансы"}],
                "against_us": ["контраргумент"],
                "forecasts": [{"variable": "Ключевая ставка", "center": "14%"}]}
    verdict, notes = check_release(sections, {})
    assert verdict == "warn"
    assert "forecast_0_no_range" in notes
    assert "forecast_0_no_counterargument" in notes


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


def test_rewrite_is_kept_only_if_it_improves_logic(db, monkeypatch):
    """🔴 Переписывание после критика может УХУДШИТЬ выпуск.

    На живом прогоне 2026-08-02 было 2 грубых замечания, после перегенерации стало 3:
    модель починила указанное и внесла новое. Публиковать вторую попытку молча нельзя —
    берём лучшую из двух версий.
    """
    from app.services import llm
    from app.services import macro_interpreter as ip
    from app.services import macro_logic_critic as critic

    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    db.commit()
    monkeypatch.setenv("MACRO_EVENT_AGENT", "0")
    monkeypatch.setenv("MACRO_RELEASE_REVIEW", "0")

    calls = {"n": 0}

    def fake_complete(system, user, **kw):
        calls["n"] += 1
        headline = "Первая версия" if calls["n"] == 1 else "Вторая версия"
        # Минимально валидный по гейту выпуск: без forecasts/sectors он отклоняется
        # ещё до проверки логики, и тест мерил бы не то.
        return {"sections": {
            "headline": headline,
            "theses": [{"claim": "тезис", "chain": "цепочка", "evidence": "5%",
                        "tag": "факт"}],
            "forecasts": [
                {"variable": v, "horizon": "год", "center": "1", "range": "0-2",
                 "driver": "d", "against": "a"}
                for v in ("Ключевая ставка", "Инфляция", "Курс рубля", "ВВП", "Безработица")],
            "sectors": [{"sector": "Финансы", "wind": "попутный", "channel": "ставка"}],
        }}

    # критик: у первой версии 2 грубых, у второй — 3 (стало хуже)
    seen = {"n": 0}

    def fake_review(db_, sections):
        seen["n"] += 1
        return {"issues": [{"problem": "p", "severity": "грубая"}],
                "hard_count": 2 if seen["n"] == 1 else 3}

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "pro_model", lambda: "m")
    monkeypatch.setattr(critic, "review_logic", fake_review)

    row = ip.generate(db)
    assert row.sections["headline"] == "Первая версия", "худшая версия не должна публиковаться"
    assert row.source_snapshot["logic"]["stopped"] == "worse"


def test_logic_loop_iterates_until_clean(db, monkeypatch):
    """Владелец: критик не блокирует, но гоняет выпуск по кругу, пока грубые не сняты.

    Один заход снимает не всё — здесь замечания уходят только к третьей версии, и
    цикл обязан дойти до неё сам, а не опубликовать первую с ошибками.
    """
    from app.services import llm
    from app.services import macro_interpreter as ip
    from app.services import macro_logic_critic as critic

    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    db.commit()
    monkeypatch.setenv("MACRO_EVENT_AGENT", "0")
    monkeypatch.setenv("MACRO_RELEASE_REVIEW", "0")

    calls = {"n": 0}
    fixes_seen = []

    def fake_complete(system, user, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            fixes_seen.append(user)
        return {"sections": {
            "headline": f"Версия {calls['n']}",
            "theses": [{"claim": "тезис", "chain": "цепочка", "evidence": "5%",
                        "tag": "факт"}],
            "forecasts": [
                {"variable": v, "horizon": "год", "center": "1", "range": "0-2",
                 "driver": "d", "against": "a"}
                for v in ("Ключевая ставка", "Инфляция", "Курс рубля", "ВВП", "Безработица")],
            "sectors": [{"sector": "Финансы", "wind": "попутный", "channel": "ставка"}],
        }}

    hard_by_call = [3, 1, 0]
    seen = {"n": 0}

    def fake_review(db_, sections):
        n = seen["n"]
        seen["n"] += 1
        hard = hard_by_call[min(n, len(hard_by_call) - 1)]
        return {"issues": [{"problem": "p", "severity": "грубая"}] * hard, "hard_count": hard}

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "pro_model", lambda: "m")
    monkeypatch.setattr(critic, "review_logic", fake_review)

    row = ip.generate(db)
    assert row.sections["headline"] == "Версия 3", "цикл обязан дойти до чистой версии"
    logic = row.source_snapshot["logic"]
    assert logic["hard_count"] == 0 and logic["hard_before"] == 3
    assert [p["pass"] for p in logic["passes"]] == [1, 2]
    # доработка получает СВОЙ предыдущий текст, а не пишется с нуля
    assert "ТВОЙ ПРЕДЫДУЩИЙ ВАРИАНТ" in fixes_seen[0]
    assert "Версия 1" in fixes_seen[0] and "Версия 2" in fixes_seen[1]


def test_logic_loop_stops_at_max_passes(db, monkeypatch):
    """Критик НЕ блокирует: если после предела заходов замечания остались — публикуем."""
    from app.services import llm
    from app.services import macro_interpreter as ip
    from app.services import macro_logic_critic as critic

    mi.seed_indicators(db)
    mi.upsert_point(db, "key_rate", date(2026, 3, 1), "level", 15, ingested_via="file")
    db.commit()
    monkeypatch.setenv("MACRO_EVENT_AGENT", "0")
    monkeypatch.setenv("MACRO_RELEASE_REVIEW", "0")

    calls = {"n": 0}

    def fake_complete(system, user, **kw):
        calls["n"] += 1
        return {"sections": {
            "headline": f"Версия {calls['n']}",
            "theses": [{"claim": "тезис", "chain": "цепочка", "evidence": "5%",
                        "tag": "факт"}],
            "forecasts": [
                {"variable": v, "horizon": "год", "center": "1", "range": "0-2",
                 "driver": "d", "against": "a"}
                for v in ("Ключевая ставка", "Инфляция", "Курс рубля", "ВВП", "Безработица")],
            "sectors": [{"sector": "Финансы", "wind": "попутный", "channel": "ставка"}],
        }}

    # каждый заход снимает по одному замечанию, но до нуля не доходит
    seq = [5, 4, 3, 2]
    seen = {"n": 0}

    def fake_review(db_, sections):
        n = seen["n"]
        seen["n"] += 1
        hard = seq[min(n, len(seq) - 1)]
        return {"issues": [{"problem": "p", "severity": "грубая"}] * hard, "hard_count": hard}

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "pro_model", lambda: "m")
    monkeypatch.setattr(critic, "review_logic", fake_review)

    row = ip.generate(db)
    assert row.id, "выпуск обязан выйти даже с оставшимися замечаниями"
    logic = row.source_snapshot["logic"]
    assert len(logic["passes"]) == ip._MAX_LOGIC_PASSES
    assert logic["hard_count"] == 2 and logic["hard_before"] == 5
