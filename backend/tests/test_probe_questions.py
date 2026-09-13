"""Контрольные вопросы владельца — конфиг, агрегат, чтение (без LLM и БД)."""
from app.services import probe_questions as pq
from app.services.situation_overlay import _BLOCKLIST


def test_вопросы_загружаются_и_корректны():
    qs = pq.load_questions()
    ids = [q["id"] for q in qs]
    assert len(qs) >= 7 and len(ids) == len(set(ids))
    assert {q["contour"] for q in qs} <= set(pq.CONTOURS)
    for q in qs:
        assert len(q["question"]) > 40
        assert not _BLOCKLIST.search(q["question"]), q["id"]


def test_агрегат_баллов():
    items = [{"id": "a", "answer": {"answer": "x"}, "judge": {"scores": {k: 4 for k in pq.RUBRIC}}},
             {"id": "b", "answer": {"answer": "y"}, "judge": {"scores": {k: 2 for k in pq.RUBRIC}}},
             {"id": "c", "answer": None, "judge": None}]
    s = pq.aggregate(items)
    assert s["questions"] == 3 and s["answered"] == 2 and s["judged"] == 2
    assert s["avg_total"] == 18.0 and s["max_total"] == 30 and s["pct"] == 0.6
    assert s["per_question"]["c"]["total"] is None


def test_чтение_владельцем():
    items = [{"id": "q1", "contour": "geo", "question": "Что будет?", "notes": [],
              "answer": {"answer": "Главный вывод. Разбор.", "probabilities": [{"outcome": "сохранится", "p": 0.6, "horizon": "3 мес"}],
                         "gaps": [{"gap": "нет данных по ущербу"}]},
              "judge": {"scores": {k: 3 for k in pq.RUBRIC}, "missing": ["интересы сторон"], "wrong": [], "verdict": "обзорно"}}]
    payload = {"as_of": "2026-09-14", "items": items, "summary": pq.aggregate(items)}
    md = pq.render_md(payload)
    assert "Что будет?" in md and "Главный вывод" in md and "интересы сторон" in md and "балл 18" in md


def test_системные_задания_собираются():
    for c in pq.CONTOURS:
        s = pq._analyst_system(c)
        assert "МАНДАТ" in s and "answer" in s
    assert all(k in pq._judge_system() for k in pq.RUBRIC)


def test_прогон_сохраняется_по_ходу(db, monkeypatch):
    """Версия создаётся черновиком сразу и растёт после каждого вопроса; в конце — published."""
    from app.models.geo import BarometerVersion
    seen = []

    def fake_ask(db_, q, states_txt, conflict_txt, notes=None):
        seen.append(q["id"])
        if len(seen) == 2:
            raise RuntimeError("модель упала")
        return {"answer": "Главный вывод. " * 10, "key_judgements": [], "gaps": []}

    def fake_judge(db_, q, answer, notes=None):
        return {"scores": {k: 4 for k in pq.RUBRIC}, "missing": ["x"], "wrong": [], "verdict": "ок"}

    monkeypatch.setattr(pq, "ask", fake_ask)
    monkeypatch.setattr(pq, "judge", fake_judge)
    monkeypatch.setattr(pq, "states_context", lambda db_: "нет сводок")
    monkeypatch.setattr(pq, "_conflict_text", lambda db_: "нет данных")
    row = pq.run(db, only=["strikes_outlook", "russia_response", "ukraine_economy"])
    assert row.status == "published" and len(seen) == 3
    items = row.payload["items"]
    assert len(items) == 3 and items[0]["answer"] and items[1]["answer"] is None
    assert any("упала" in n for n in items[1]["notes"])
    assert row.payload["summary"]["judged"] == 2 and row.payload["summary"]["avg_total"] == 24.0
    assert row.payload.get("started_at") and row.payload.get("finished_at")
    assert db.query(BarometerVersion).filter(BarometerVersion.kind == "probe").count() >= 1
