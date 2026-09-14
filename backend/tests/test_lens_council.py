"""Совет агентов-методичек — без LLM: состав, статичность задания, маршрутизация вопросов,
сведение с подменёнными агентами, чтение."""
from app.models.geo import BarometerVersion
from app.services import lens_council as lc
from app.services.methodology import REGISTRY


def test_состав_совета_на_полке():
    assert set(lc.LENSES) <= set(REGISTRY) and "geo" not in lc.LENSES and "code" not in lc.LENSES
    assert set(lc.CONTOUR_OF) == set(lc.LENSES)


def test_задание_агента_содержит_методичку_целиком_и_статично():
    s1 = lc.lens_system("inst_env"); s2 = lc.lens_system("inst_env")
    assert s1 == s2                                        # иначе префикс не кэшируется
    doc = lc._doc_text("inst_env")
    assert len(doc) > 100_000 and doc[:2000] in s1
    assert "ОБЩИЙ КОДЕКС АНАЛИЗА" in s1 and "ФОРМА ОТВЕТА" in s1 and "blind_spots" in s1
    assert "СЕГОДНЯ" not in s1                              # ничего динамического в системном задании


def test_маршрутизация_вопросов():
    results = {"geo_macro": {"questions_to": [{"lens": "inst_macro", "question": "льготный кредит?"},
                                              {"lens": "geo_macro", "question": "сам себе"},
                                              {"lens": "nope", "question": "нет такого"}]},
               "inst_env": {"questions_to": [{"lens": "inst_macro", "question": "доминирование?"}]}}
    inbox = lc.route_questions(results)
    assert set(inbox) == {"inst_macro"} and len(inbox["inst_macro"]) == 2
    assert inbox["inst_macro"][0]["from"] == "geo_macro"


def test_совет_с_подменёнными_агентами_сохраняет_версию(db, monkeypatch):
    def fake_lens(db_, doc_id, task, packet, questions=None, notes=None):
        if doc_id == "macro_geo":
            return None
        if questions:
            return {"lens": doc_id, "answers": [{"to": q["from"], "question": q["question"], "answer": "ок", "status": "Д"}
                                                for q in questions]}
        return {"lens": doc_id, "sees": f"взгляд {doc_id}", "mechanisms": [], "blind_spots": "не вижу денег",
                "questions_to": [{"lens": "inst_macro", "question": "льготный контур?"}] if doc_id == "geo_macro" else [],
                "sections_used": [f"{doc_id}:1.1"]}

    def fake_synth(db_, task, results, replies, packet, notes=None):
        return {"answer": "Главный вывод. " * 20, "causal_map": [{"chain": "а → б", "lenses": list(results)[:2], "status": "В"}],
                "forecast": {"most_likely": "x", "most_dangerous": "y", "probabilities": [{"outcome": "x", "p": 0.6, "horizon": "6 мес", "owner_lens": "geo_base"}]},
                "unknowns": ["экономика противника"], "lens_coverage": {k: "использован" for k in results}}

    monkeypatch.setattr(lc, "run_lens", fake_lens)
    monkeypatch.setattr(lc, "synthesize", fake_synth)
    monkeypatch.setattr(lc, "build_packet", lambda db_: "ПАЧКА")
    # параллельная волна открывает свои сессии; под тестом подменяем на переданную
    monkeypatch.setattr(lc, "_run_lens_own_session",
                        lambda doc_id, task, packet, questions=None: (doc_id, fake_lens(db, doc_id, task, packet, questions), []))
    out = lc.run_council(db, "Что означают удары по НПЗ для экономики?", lenses=["geo_macro", "inst_macro", "macro_geo"], persist=True)
    assert out["answered"] == ["geo_macro", "inst_macro"] and out["failed"] == ["macro_geo"]
    assert "inst_macro" in out["replies"] and out["synthesis"]["answer"]
    row = db.get(BarometerVersion, out["version_id"])
    assert row.kind == lc.KIND and row.status == "published"
    md = lc.render_md(out)
    assert "Главный вывод" in md and "geo_macro" in md and "экономика противника" in md


def test_экзамен_в_режиме_совета(db, monkeypatch):
    from app.services import probe_questions as pq
    monkeypatch.setattr(pq, "states_context", lambda db_: "нет сводок")
    monkeypatch.setattr(pq, "_conflict_text", lambda db_: "нет данных")
    monkeypatch.setattr(lc, "run_council", lambda db_, task, **kw: {
        "version_id": 1, "answered": ["geo_base"], "seconds": 1, "notes": [],
        "synthesis": {"answer": "Ответ совета. " * 30, "causal_map": [{"chain": "a → b", "lenses": ["geo_base"], "status": "В"}],
                      "forecast": {"probabilities": [{"outcome": "x", "p": 0.5, "horizon": "6 мес"}]}, "unknowns": ["u"]},
        "lens_answers": {"geo_base": {"sections_used": ["geo_base:8.30"]}}})
    monkeypatch.setattr(pq, "judge", lambda db_, q, answer, notes=None: {"scores": {k: 3 for k in pq.RUBRIC}, "missing": [], "wrong": [], "verdict": "ок"})
    row = pq.run(db, only=["strikes_outlook"], mode="council")
    item = row.payload["items"][0]
    assert row.payload["mode"] == "council" and item["mode"] == "council"
    assert item["answer"]["mode"] == "council" and "geo_base:8.30" in item["answer"]["methodology_used"]
    assert row.payload["summary"]["judged"] == 1


def test_маршрут_ступенями_видит_предыдущие(db, monkeypatch):
    seen: list[tuple[str, bool]] = []

    def fake_lens(db_, doc_id, task, packet, questions=None, prior="", notes=None):
        if questions:
            return {"lens": doc_id, "answers": []}
        seen.append((doc_id, bool(prior)))
        return {"lens": doc_id, "sees": f"взгляд {doc_id}", "mechanisms": [{"chain": "a → b"}], "blind_spots": "-", "questions_to": []}

    monkeypatch.setattr(lc, "run_lens", fake_lens)
    monkeypatch.setattr(lc, "synthesize", lambda db_, task, results, replies, packet, notes=None: {"answer": "ок " * 10})
    monkeypatch.setattr(lc, "build_packet", lambda db_: "ПАЧКА")
    monkeypatch.setattr(lc, "classify_task", lambda db_, task: {"type": "событие", "entry": "geo", "why": "тест", "how": "тест"})
    monkeypatch.setattr(lc, "_run_lens_own_session",
                        lambda doc_id, task, packet, questions=None, prior="": (doc_id, fake_lens(db, doc_id, task, packet, questions, prior), []))
    out = lc.run_council(db, "Продолжатся ли удары по НПЗ?", mode="route", persist=False)
    order = [d for d, _ in seen]
    assert order[:2] == ["geo_events", "geo_base"] and set(order[2:4]) == {"geo_macro", "geo_inst"}
    assert all(not p for d, p in seen[:2]) and all(p for d, p in seen[2:])   # первая ступень без prior, дальше — с
    assert out["mode"] == "route" and out["route"]["entry"] == "geo"


def test_классификация_эвристикой_без_модели(db, monkeypatch):
    monkeypatch.setattr(lc.llm, "complete", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("нет сети")))
    assert lc.classify_task(db, "Как изменится ключевая ставка и инфляция?")["entry"] == "macro"
    assert lc.classify_task(db, "Чего ждать от переговоров и санкций?")["entry"] == "geo"
    assert lc.classify_task(db, "Как назначения и иски Генпрокуратуры двигают дрейф институтов?")["entry"] == "inst"
