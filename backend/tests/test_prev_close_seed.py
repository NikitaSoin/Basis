"""«За день» на Рынке: prev_close сеется раз в торговый день в КАЖДОМ процессе (бой
2026-09-16: после расщепления процессов веб отдавал цены без изменения — prev_close
приходил только из прогрева при старте, который уехал в воркер)."""
import threading
import time


def test_seed_prev_close_пересчитывает_изменение_по_известной_цене():
    from app.services import tinkoff_quotes as tq
    tq._prices.clear()
    tq._prices["SBER"] = {"price": 284.91, "change_abs": None, "change_pct": None, "prev_close": None}
    n = tq.seed_prev_close({"SBER": "287.50", "NEW": 10.0, "BAD": 0, "NONE": None})
    assert n == 2
    assert tq._prices["SBER"]["prev_close"] == 287.5
    assert tq._prices["SBER"]["change_pct"] == round((284.91 / 287.5 - 1) * 100, 4)
    assert tq._prices["NEW"]["price"] is None and "NEW" not in tq.get_all_prices()
    assert tq.prev_close_coverage() == 1.0
    tq._prices.clear()


def test_ensure_prev_close_раз_в_день_и_single_flight(monkeypatch):
    from app.services import tinkoff_quotes as tq
    tq._prices.clear()
    tq._prices["ROSN"] = {"price": 372.65, "change_abs": None, "change_pct": None, "prev_close": None}
    calls = []
    monkeypatch.setattr(tq, "_prev_close_from_moex", lambda: (calls.append(1), {"ROSN": 351.15})[1])
    monkeypatch.setattr(tq, "_prev_close_day", None)
    monkeypatch.setattr(tq, "_prev_close_attempt_ts", 0.0)
    monkeypatch.setattr(tq, "_prev_close_seeding", False)
    tq.ensure_prev_close()
    for _ in range(50):
        if tq._prev_close_day is not None:
            break
        time.sleep(0.05)
    assert tq._prev_close_day == tq._msk_today()
    assert tq._prices["ROSN"]["change_pct"] == round((372.65 / 351.15 - 1) * 100, 4)
    assert calls == [1]
    tq.ensure_prev_close()          # тот же день — no-op
    time.sleep(0.1)
    assert calls == [1]
    # сбой MOEX: день не помечен, повтор не чаще _PREV_CLOSE_RETRY_SEC
    monkeypatch.setattr(tq, "_prev_close_day", None)
    monkeypatch.setattr(tq, "_prev_close_attempt_ts", 0.0)
    monkeypatch.setattr(tq, "_prev_close_from_moex", lambda: (calls.append(2), {})[1])
    tq.ensure_prev_close()
    for _ in range(50):
        if not tq._prev_close_seeding:
            break
        time.sleep(0.05)
    assert tq._prev_close_day is None and calls == [1, 2]
    tq.ensure_prev_close()
    time.sleep(0.1)
    assert calls == [1, 2], "повторная попытка раньше таймаута"
    tq._prices.clear()
