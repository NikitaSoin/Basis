"""Сторож цикла событий: снимок собирается на любой ОС и ничего не роняет."""
from app.services import loop_watchdog as w


def test_снимок_не_падает_без_proc():
    s = w.collect_snapshot(7.3, "example.com")
    assert s["lag_sec"] == 7.3 and "canary" in s and "python_threads" in s
    assert isinstance(s["canary"], dict)


def test_статус_до_старта():
    st = w.status()
    assert st["events"] == 0 and st["current_lag_sec"] is None and "now" in st
