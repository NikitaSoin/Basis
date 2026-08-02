"""Цены нефти и дисконт Urals к Brent.

🔴 Ряд Urals тянулся с tankermap и показывал $60,7 при рыночных $84,6 — расхождение
почти на четверть. Мы читали источник ВЕРНО (на их сайте та же цифра), подвёл сам фид.
Отсюда две вещи в тестах: разбор должен доставать именно нужный эталон из общей
таблицы, и должен отбрасывать величины, которые нефтью быть не могут.
"""
from app.services.macro_oil_sync import _parse

PAGE = ("Цены на нефть сегодня  Brent Мировой Эталон $90.12 USD/баррель  "
        "WTI США Эталон $84.67 USD/баррель  Urals Россия $84.56 USD/баррель  "
        "Изменение за сутки 1.2%  Объём торгов 350000 контрактов")


class TestParsing:
    def test_three_benchmarks_are_separated(self):
        """Три цены идут одной таблицей — нельзя перепутать Urals с Brent."""
        out = _parse(PAGE)
        assert out == {"oil_brent": 90.12, "oil_wti": 84.67, "urals": 84.56}

    def test_percentages_and_volumes_are_not_taken_for_prices(self):
        assert _parse("Brent 1.2% Urals 350000 контрактов") == {}

    def test_missing_benchmark_does_not_break_the_rest(self):
        out = _parse("Brent Мировой Эталон $90.12 USD/баррель")
        assert out == {"oil_brent": 90.12}

    def test_comma_decimal_is_understood(self):
        assert _parse("Urals Россия $84,56 USD") == {"urals": 84.56}


class TestSpread:
    def test_spread_is_stored_as_discount(self, db, monkeypatch):
        """🔴 Дисконт — отдельный ряд. Рост мировой цены и доходы российских
        экспортёров это РАЗНЫЕ вещи, если одновременно расширяется дисконт; без числа
        под рукой в разборе появляется «санкции съедают выгоду» без единой цифры."""
        from app.services import macro_ingest as mi
        from app.services import macro_oil_sync as oil
        from app.models.macro import MacroDataPoint

        mi.seed_indicators(db)
        db.commit()
        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": PAGE})
        out = oil.sync_oil_prices(db)
        assert out["urals_brent_spread"]["value"] == 5.56
        row = (db.query(MacroDataPoint)
               .filter_by(indicator_code="urals_brent_spread").order_by(
                   MacroDataPoint.as_of.desc()).first())
        assert row is not None and float(row.value) == 5.56

    def test_broken_page_writes_nothing(self, db, monkeypatch):
        from app.services import macro_oil_sync as oil

        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": "страница изменилась"})
        assert oil.sync_oil_prices(db) == {"error": "not_parsed"}
