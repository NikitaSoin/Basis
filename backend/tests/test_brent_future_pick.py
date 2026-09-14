"""Выбор «ближайшего фьючерса Brent» из таблицы futures.

🔴 Инцидент 2026-09-14 (владелец: «Brent 37 долларов, что за бред»). Пять запросов
искали нефть маской `asset_code ILIKE 'BR%' OR secid ILIKE 'BR%'`, под которую попадают
BRAZIL (фьючерс на бразильский индекс, ≈$37) и BRM (мини-Brent). Квартальный BRAZIL
истекает в 3-ю пятницу марта/июня/сентября/декабря — раньше ближайшего месячного BR,
который истекает 1-го числа. С 1 сентября плитка «Нефть Brent» в «Что движет рынком»,
стресс-сценарии, ИИ-инструменты и стресс портфеля брали цену Бразилии за нефть.
"""
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.models.future import Future


def _seed(db):
    today = date.today()
    rows = [
        # ловушка №1: BRAZIL истекает раньше всех и стоит «как нефть за 37»
        ("BZU6T", "BRAZIL", "other", today + timedelta(days=4), Decimal("38.58")),
        # ловушка №2: BR с нулевой ценой (нет сделок) — ближе, чем ликвидный
        ("BRT6T", "BR", "commodity", today + timedelta(days=2), Decimal("0")),
        # истёкший BR — не должен учитываться
        ("BRU6T", "BR", "commodity", today - timedelta(days=13), Decimal("100.00")),
        # правильный ответ — ближайший ликвидный BR
        ("BRV6T", "BR", "commodity", today + timedelta(days=17), Decimal("104.51")),
        # мини-Brent того же срока — не нефтяной эталон плитки
        ("BMV6T", "BRM", "other", today + timedelta(days=17), Decimal("104.45")),
        ("BRX6T", "BR", "commodity", today + timedelta(days=48), Decimal("99.80")),
    ]
    for secid, code, kind, exp, px in rows:
        db.add(Future(secid=secid, short_name=secid, asset_code=code, asset_kind=kind,
                      expiration_date=exp, last_price=px, prev_settle=px))
    db.flush()


class TestNearestBrentFuture:
    def test_drivers_tile_ignores_brazil_and_zero_price(self, client, db):
        _seed(db)
        r = client.get("/api/market/drivers")
        assert r.status_code == 200, r.text
        oil = next((x for x in r.json() if x["name"] == "Нефть Brent"), None)
        assert oil is not None, "плитка нефти пропала"
        assert oil["chart"]["secid"] == "BRV6T"
        assert oil["value"] == "104,5 $"

    def test_stress_scenarios_reference_oil(self, db):
        from app.services.stress_scenarios import _live_refs
        _seed(db)
        oil, _rub = _live_refs(db)
        assert oil == 104.51

    def test_agent_tools_live_macro(self, db):
        from app.services.agent_tools import _get_live_macro
        _seed(db)
        assert _get_live_macro(db).get("oil_brent_usd") == 104.51

    def test_financial_model_fallback_to_future(self, db):
        from app.services.financial_model import _live_brent
        _seed(db)
        # Основной источник модели — макроряд; здесь проверяем именно фолбэк на фьючерс.
        db.execute(text("DELETE FROM macro_data_points WHERE indicator_code = 'oil_brent'"))
        assert _live_brent(db) == 104.51

    def test_prefix_mask_is_gone_from_sources(self):
        """Маска по префиксу не должна вернуться ни в один запрос к futures."""
        app_dir = Path(__file__).resolve().parents[1] / "app"
        def _code(path: Path) -> str:  # комментарии (в т.ч. описание инцидента) не считаются
            return "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                             if not l.lstrip().startswith("#"))
        hits = [p for p in app_dir.rglob("*.py") if "ILIKE 'BR" in _code(p)]
        assert not hits, [str(p) for p in hits]
