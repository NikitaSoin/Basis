"""Стартовый залп после деплоя — последовательно и с отсрочкой (советник 2026-09-14).

Проверяем по исходнику: десять параллельных create_task при старте больше не
возвращаются, дубль пересчёта метрик убран, самопроверка не дёргает тяжёлый скоринг,
в логе есть время, пульс кронов пишется вне потока цикла событий.
"""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")


def test_старт_через_цепочку_а_не_залпом():
    assert "asyncio.create_task(_startup_chain())" in SRC
    burst = re.findall(r"^\s*asyncio\.create_task\(_(\w+)\(\)\)", SRC, flags=re.M)
    assert "risk_metrics_startup" not in burst and "company_metrics_job" not in burst
    assert "asset_data_job" not in burst and "instrument_history_startup" not in burst


def test_цепочка_содержит_все_задачи_и_отсрочку():
    chain = SRC[SRC.index("async def _startup_chain"):SRC.index("async def lifespan")]
    for name in ("_tinkoff_warmup", "_seed_shares_startup", "_selftest_startup", "_barometer_expert_reimport_startup",
                 "_geo_frontline_sync_startup", "_instrument_history_startup", "_asset_data_job",
                 "_sector_tr_backfill_startup", "_risk_metrics_startup"):
        assert name in chain, name
    assert "_company_metrics_job" not in chain          # дубль полного пересчёта метрик
    assert "STARTUP_DELAY_SEC" in chain and "await asyncio.sleep(delay)" in chain


def test_самопроверка_без_тяжёлого_скоринга_и_лог_со_временем():
    selftest = SRC[SRC.index("async def _selftest_startup"):SRC.index("async def _selftest_startup") + 2500]
    assert '("/api/screener/scored?universe=all"' not in selftest and 'for p in ("/api/health"' in selftest
    assert "%(asctime)s" in SRC and "_ensure_log_timestamps()" in SRC
    hb = SRC[SRC.index("def _with_heartbeat"):SRC.index("def _with_heartbeat") + 1200]
    assert "run_in_executor(None, hb_ok" in hb and "run_in_executor(None, hb_err" in hb
    assert "app.state.scheduler = scheduler" in SRC
