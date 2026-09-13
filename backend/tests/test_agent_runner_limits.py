"""Цикл агента не теряет работу на лимитах: обрезанный ответ → повтор с бóльшим потолком."""
from app.services import agent_runner


def test_обрезанный_финал_повторяется_с_большим_потолком(monkeypatch):
    calls = []

    def fake_complete(messages, **kw):
        calls.append(kw.get("max_tokens"))
        if len(calls) == 1:
            return {"message": {"role": "assistant", "content": '{"x": 1, "y": '},
                    "total_tokens": 100, "finish_reason": "length", "completion_tokens": 8000}
        return {"message": {"role": "assistant", "content": '{"x": 1, "y": 2}'},
                "total_tokens": 100, "finish_reason": "stop"}

    monkeypatch.setattr(agent_runner, "complete_messages", fake_complete)
    out = agent_runner.run_agent(None, system_prompt="s", task="t", tools_schema=[], max_steps=4,
                                 max_tokens_total=1_000_000, step_max_tokens=8_000, final_max_tokens=8_000)
    assert out["result"] == {"x": 1, "y": 2}
    assert calls[0] == 8_000 and calls[1] == 16_000, "после обрезки потолок удваивается"
    assert any(e.get("event") == "truncated" for e in out["trace"])


def test_обрезка_на_максимуме_просит_сократить(monkeypatch):
    calls = []

    def fake_complete(messages, **kw):
        calls.append(kw.get("max_tokens"))
        if len(calls) == 1:
            return {"message": {"role": "assistant", "content": "{"},
                    "total_tokens": 1, "finish_reason": "length"}
        assert any("Сократи" in (m.get("content") or "") for m in messages if m.get("role") == "user")
        return {"message": {"role": "assistant", "content": '{"ok": true}'}, "total_tokens": 1, "finish_reason": "stop"}

    monkeypatch.setattr(agent_runner, "complete_messages", fake_complete)
    out = agent_runner.run_agent(None, system_prompt="s", task="t", tools_schema=[], max_steps=4,
                                 max_tokens_total=10_000_000, step_max_tokens=128_000, final_max_tokens=128_000)
    assert out["result"] == {"ok": True}
