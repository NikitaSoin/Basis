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

    def test_broken_page_still_saves_exchange_quotes(self, db, monkeypatch):
        """Страница сломалась, но биржа доступна — Brent и WTI всё равно приходят;
        без Urals дисконт не считается (нечего вычитать)."""
        from app.services import macro_ingest as mi
        from app.services import macro_oil_sync as oil

        mi.seed_indicators(db)
        db.commit()
        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": "страница изменилась"})
        monkeypatch.setattr(oil, "_exchange_quotes", lambda: {"oil_brent": 90.5})
        out = oil.sync_oil_prices(db)
        assert out["oil_brent"]["value"] == 90.5
        assert "urals_brent_spread" not in out

    def test_nothing_available_writes_nothing(self, db, monkeypatch):
        from app.services import macro_oil_sync as oil

        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": "страница изменилась"})
        monkeypatch.setattr(oil, "_exchange_quotes", lambda: {})
        assert oil.sync_oil_prices(db) == {"error": "not_parsed"}


class TestSourcePriority:
    """🔴 Владелец: «не фьючерс — возьми спот с известной площадки, чтобы источник был
    авторитетный». Порядок: официальный спот EIA (пишется отдельно, с задержкой) →
    оперативный СПОТ со страницы → биржевой ФЬЮЧЕРС только фолбэком, чтобы цена нефти
    не исчезла с витрины совсем.
    """

    def test_spot_page_beats_futures_quote(self, db, monkeypatch):
        from app.services import macro_ingest as mi
        from app.services import macro_oil_sync as oil

        mi.seed_indicators(db)
        db.commit()
        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": PAGE})
        monkeypatch.setattr(oil, "_exchange_quotes",
                            lambda: {"oil_brent": 91.55, "oil_wti": 85.0})
        out = oil.sync_oil_prices(db)
        assert out["oil_brent"]["value"] == 90.12, "спот должен победить фьючерс"
        assert out["urals"]["value"] == 84.56

    def test_unavailable_exchange_falls_back_to_page(self, db, monkeypatch):
        from app.services import macro_oil_sync as oil

        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": PAGE})
        monkeypatch.setattr(oil, "_exchange_quotes", lambda: {})
        out = oil.sync_oil_prices(db)
        assert out["oil_brent"]["value"] == 90.12

    def test_market_pulse_prefers_exchange_over_moex_future(self, db):
        """Обзор рынка показывает саму котировку, а фьючерс MOEX — только страховка."""
        from datetime import date

        from app.services import macro_ingest as mi
        from app.services.market_pulse import _oil_snapshot

        mi.seed_indicators(db)
        mi.upsert_point(db, "oil_brent", date(2026, 8, 2), "level", 90.12,
                        ingested_via="oilprice")
        db.commit()
        snap = _oil_snapshot(db)
        assert snap["source"] == "exchange_quote"
        assert snap["level"] == 90.12


class TestEiaAnchor:
    """Официальный спот EIA — авторитетный якорь ряда."""

    def test_eia_overrides_operational_quote(self, db, monkeypatch):
        """Когда официальная цена выходит, она ПЕРЕКРЫВАЕТ оперативную оценку за тот
        же день: приоритет via 'eia' выше 'oilprice'."""
        from datetime import date

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint

        mi.seed_indicators(db)
        db.query(MacroDataPoint).filter_by(indicator_code="oil_brent").delete()
        db.commit()
        mi.upsert_point(db, "oil_brent", date(2026, 7, 27), "level", 90.0,
                        ingested_via="oilprice")
        mi.upsert_point(db, "oil_brent", date(2026, 7, 27), "level", 91.82,
                        ingested_via="eia")
        db.commit()
        row = (db.query(MacroDataPoint)
               .filter_by(indicator_code="oil_brent", as_of=date(2026, 7, 27)).first())
        assert float(row.value) == 91.82

    def test_operational_quote_does_not_overwrite_eia(self, db):
        """И наоборот: оперативная оценка не затирает официальную цифру."""
        from datetime import date

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint

        mi.upsert_point(db, "oil_brent", date(2026, 7, 27), "level", 88.0,
                        ingested_via="oilprice")
        db.commit()
        row = (db.query(MacroDataPoint)
               .filter_by(indicator_code="oil_brent", as_of=date(2026, 7, 27)).first())
        assert float(row.value) == 91.82


class TestSpreadSign:
    """🔴 Владелец 03.08: премия ВОЗМОЖНА — когда нефти не хватает, спрос на российскую
    может быть выше, чем на эталон. Знак запрещать нельзя; запрещать надо счёт из цен
    разной свежести, что и дало на бою «−0,88» (биржевой Brent против вчерашнего
    страничного Urals).
    """

    def test_premium_is_recorded_not_suppressed(self, db, monkeypatch):
        from app.services import macro_ingest as mi
        from app.services import macro_oil_sync as oil

        mi.seed_indicators(db)
        db.commit()
        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": "Brent $83.68 USD Urals $84.56 USD"})
        monkeypatch.setattr(oil, "_exchange_quotes", lambda: {})
        out = oil.sync_oil_prices(db)
        assert out["urals_brent_spread"]["value"] == -0.88, "премию нужно записывать"

    def test_spread_needs_both_prices(self, db, monkeypatch):
        """Одной цены мало — спред не считается, а не выдумывается."""
        from app.services import macro_ingest as mi
        from app.services import macro_oil_sync as oil

        mi.seed_indicators(db)
        db.commit()
        monkeypatch.setattr("app.services.agent_web.fetch_document",
                            lambda *a, **k: {"text": "Urals Россия $84.56 USD"})
        monkeypatch.setattr(oil, "_exchange_quotes", lambda: {})
        out = oil.sync_oil_prices(db)
        assert "urals_brent_spread" not in out
