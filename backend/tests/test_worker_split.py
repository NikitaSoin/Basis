"""Расщепление процессов (2026-09-14): uvicorn отдаёт страницы, задачи исполняет
app/worker.py. Проверяем поведением, не регексами по исходнику (советник): реестр
задач собирается на заглушке без запуска, роль читается из окружения, каждый
job_id, который ставят в очередь ручки debug.py, известен воркеру, очередь
переживает claim/finish/сироту на тестовой БД.
"""
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


class _FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, tuple] = {}

    def add_job(self, func, trigger=None, **kw):
        assert kw.get("id"), "у каждой задачи должен быть id"
        assert kw["id"] not in self.jobs, f"дубль id {kw['id']}"
        self.jobs[kw["id"]] = (trigger, kw)


def test_register_jobs_собирает_все_кроны_без_запуска(monkeypatch):
    monkeypatch.delenv("DISABLE_EXTERNAL_JOBS", raising=False)
    from app.main import register_jobs
    fake = _FakeScheduler()
    register_jobs(fake)
    for jid in ("quotes_update", "history_catchup", "company_metrics_sync", "asset_data_refresh",
                "calendar_refresh", "news_feed", "evening_pipeline", "probe_questions",
                "geo_digest", "bots_reclassify", "pd_retention"):
        assert jid in fake.jobs, jid
    assert len(fake.jobs) >= 45
    assert fake.jobs["quotes_update"][0] == "interval"
    trig, kw = fake.jobs["evening_pipeline"]
    assert trig == "cron" and kw["hour"] == 21 and kw["minute"] == 50


def test_внешние_задачи_отключаются_флагом(monkeypatch):
    monkeypatch.setenv("DISABLE_EXTERNAL_JOBS", "1")
    from app.main import register_jobs
    fake = _FakeScheduler()
    register_jobs(fake)
    assert "quotes_update" in fake.jobs and "pd_retention" in fake.jobs
    assert "news_feed" not in fake.jobs and "evening_pipeline" not in fake.jobs


def test_роль_процесса_из_окружения(monkeypatch):
    from app.main import basis_role
    monkeypatch.delenv("BASIS_ROLE", raising=False)
    assert basis_role() == "all"
    monkeypatch.setenv("BASIS_ROLE", " Web ")
    assert basis_role() == "web"
    monkeypatch.setenv("BASIS_ROLE", "worker")
    assert basis_role() == "worker"


def test_в_роли_web_нет_планировщика_и_старт_цепочки():
    src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    life = src[src.index("async def lifespan("):src.index("app = FastAPI(")]
    assert "scheduler.add_job(" not in life, "add_job внутри lifespan — список задач живёт в register_jobs"
    web = life[life.index('if role == "web":'):life.index("scheduler = AsyncIOScheduler(")]
    assert "register_jobs" not in web and "_startup_chain" not in web
    assert "yield" in web and "return" in web
    assert "@asynccontextmanager\nasync def lifespan(" in src, "декоратор должен стоять над lifespan (промах 03f8e9f2f1)"
    # старт-цепочка и сторож: цепочка — там, где задачи; сторож — в веб-процессе
    assert "_watchdog_start()" in life[:life.index('if role == "web":')]
    assert "asyncio.create_task(_startup_chain())" in life[life.index("scheduler = AsyncIOScheduler("):]


def test_реестр_покрывает_все_enqueue_из_debug():
    from app.services.job_queue import REGISTRY, cron_job_ids
    src = (BACKEND / "app" / "api" / "debug.py").read_text(encoding="utf-8")
    ids = set(re.findall(r'_enqueue\("([a-z_]+)"', src))
    assert ids, "в debug.py нет ни одного _enqueue"
    known = set(REGISTRY) | cron_job_ids()
    assert ids <= known, f"ручки ставят в очередь неизвестное: {ids - known}"
    for must in ("evening_pipeline", "probe_questions", "critic", "stress_interpretation"):
        assert must in ids
    assert "_inst_bg(" not in src and "app.state.scheduler" not in src, \
        "статус и запуск — только через очередь job_requests"


def test_summarize_короткая_сводка():
    from app.services.job_queue import summarize, RESULT_MAX_CHARS, _flag

    class Row:
        id = 7
        status = "published"
        gate_notes = ["a"] * 20
        payload = {"as_of": "2026-09-14"}

    d = summarize(Row())
    assert d["id"] == 7 and d["status"] == "published" and len(d["gate_notes"]) == 10
    assert d["as_of"] == "2026-09-14"
    big = summarize({"x": "y" * 10000})
    assert "truncated" in big and len(big["truncated"]) <= RESULT_MAX_CHARS
    assert summarize(None) is None and summarize({"ok": 1}) == {"ok": 1}
    assert _flag("false") is False and _flag("true") is True and _flag(None, default=True) is True


def test_очередь_на_тестовой_бд(db, monkeypatch):
    """enqueue → claim → finish → сирота после рестарта. Таблица — из миграции."""
    import os
    from app.services import job_queue as jq
    # job_queue ходит через app.db.session.SessionLocal → подменяем на тестовую сессию
    from tests.conftest import TestingSessionLocal
    import app.db.session as sess
    monkeypatch.setattr(sess, "SessionLocal", TestingSessionLocal)
    db.execute(__import__("sqlalchemy").text("DELETE FROM job_requests"))
    db.commit()

    bad = jq.enqueue("no_such_job")
    assert "error" in bad and "known" in bad
    out = jq.enqueue("critic", {"x": 1}, requested_by="test")
    assert "queued" in out and out["job_id"] == "critic"

    req = jq.claim_next()
    assert req and req["job_id"] == "critic" and req["params"] == {"x": 1}
    assert jq.claim_next() is None, "вторая выдача той же задачи"
    jq.finish(req["id"], {"ok": True})
    rec = jq.list_recent(5)
    assert rec[0]["id"] == req["id"] and rec[0]["status"] == "done" and rec[0]["result"] == {"ok": True}
    assert rec[0]["minutes"] is not None

    jq.enqueue("critic")
    req2 = jq.claim_next()
    assert req2 and jq.queue_depth() == {"queued": 0, "running": 1}
    assert jq.recover_orphans() == 1
    rec = jq.list_recent(1)
    assert rec[0]["status"] == "error" and "restarted" in rec[0]["error"]

    jq.enqueue("critic")
    req3 = jq.claim_next()
    jq.finish(req3["id"], None, "RuntimeError: boom")
    rec = jq.list_recent(1)
    assert rec[0]["status"] == "error" and rec[0]["error"] == "RuntimeError: boom"
    assert jq.queue_depth() == {"queued": 0, "running": 0}
