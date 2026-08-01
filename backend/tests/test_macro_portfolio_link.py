"""Проекция макро-выпуска на портфель пользователя.

Главный риск блока — НЕ ошибиться в расчёте (своих расчётов здесь нет вовсе), а
показать влияние там, где его никто не устанавливал. Поэтому тесты про то, что
попадает в вывод и что честно остаётся за его пределами.
"""
from app.services.macro_portfolio_link import build_link, _sector_winds, _strongest_channel

SECTIONS = {"sectors": [
    {"sector": "Нефть и газ", "wind": "встречный", "channel": "крепкий рубль режет выручку",
     "winners": [], "losers": ["ROSN"], "dispersion": "доля экспорта"},
    {"sector": "Финансы", "wind": "попутный", "channel": "снижение ставки оживляет кредит",
     "winners": ["SBER"], "losers": []},
]}

SENS = {"shocks": {"rate": "−3 п.п.", "oil": "нефть дешевле на $20",
                   "demand": "ВВП −2 п.п."}, "companies": [
    {"ticker": "ROSN", "name": "Роснефть", "sector": "Нефть и газ",
     "effects": {"oil": -12.0, "rate": 3.0}},
    {"ticker": "SBER", "name": "Сбербанк", "sector": "Финансы",
     "effects": {"rate": 8.5}},
    {"ticker": "MGNT", "name": "Магнит", "sector": "Ритейл", "effects": {"demand": 4.0}},
]}


class TestEmptyState:
    """Владелец: связку показываем, только если портфель вбит, но сказать об этом надо."""

    def test_no_portfolio_returns_invitation(self, db):
        res = build_link(db, None, SECTIONS)
        assert res["available"] is False
        assert "портфель" in res["empty_state"].lower()

    def test_missing_portfolio_does_not_raise(self, db):
        assert build_link(db, 999999, SECTIONS)["available"] is False


class TestNoInventedInfluence:
    def test_ticker_without_data_is_reported_as_uncovered(self, db, monkeypatch):
        """Бумага, о которой выпуск молчит и в карточке нет коэффициентов, не должна
        получить «ветер» — она обязана попасть в uncovered. Молчание читалось бы как
        «влияния нет», а это разные вещи."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "ROSN", "value": 100.0, "weight": 50.0},
            {"ticker": "XXXX", "value": 100.0, "weight": 50.0}])
        res = build_link(db, 1, SECTIONS, sens_map=SENS)
        assert res["uncovered"] == ["XXXX"]
        assert [i["ticker"] for i in res["items"]] == ["ROSN"]
        assert res["summary"]["positions"] == 2 and res["summary"]["covered"] == 1

    def test_sensitivity_is_tagged_as_card_fact(self, db, monkeypatch):
        """Коэффициент — ФАКТ карточки компании, а не новая оценка этого блока."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "ROSN", "value": 100.0, "weight": 100.0}])
        item = build_link(db, 1, SECTIONS, sens_map=SENS)["items"][0]
        assert item["sensitivity"]["tag"] == "факт карточки"
        assert item["sensitivity"]["channel"] == "цена нефти"   # сильнейший по модулю
        assert item["sensitivity"]["effect_pct"] == -12.0


class TestWindAttribution:
    def test_named_ticker_beats_sector_default(self):
        named, by_sector = _sector_winds(SECTIONS)
        assert named["ROSN"]["wind"] == "встречный" and named["ROSN"]["named"] is True
        assert by_sector["финансы"]["wind"] == "попутный"

    def test_sector_wind_applies_to_unnamed_holding(self, db, monkeypatch):
        """Выпуск назвал сектор, но не бумагу — ветер применяем, пометив, что
        поимённо её не называли."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "MGNT", "value": 100.0, "weight": 100.0}])
        res = build_link(db, 1, {"sectors": [
            {"sector": "Ритейл", "wind": "попутный", "channel": "спрос"}]}, sens_map=SENS)
        item = res["items"][0]
        assert item["wind"] == "попутный" and item["named_in_release"] is False

    def test_strongest_channel_is_by_absolute_effect(self):
        assert _strongest_channel({"effects": {"rate": 3.0, "oil": -12.0}}) == ("oil", -12.0)
        assert _strongest_channel({"effects": {}}) is None


class TestReadability:
    """Дефекты, видимые только на живом портфеле."""

    def test_shock_condition_is_inside_the_phrase(self, db, monkeypatch):
        """Рядом стояли «ветер попутный» и «−5,6%» — читается как противоречие.
        Ветер про сегодняшнюю макроситуацию, число — ответ на ГИПОТЕТИЧЕСКИЙ шок,
        поэтому «если» обязано быть в самой фразе."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "ROSN", "value": 1.0, "weight": 100.0}])
        item = build_link(db, 1, SECTIONS, sens_map=SENS)["items"][0]
        assert item["sensitivity"]["phrase"] == "если нефть дешевле на $20 → прибыль −12.0%"

    def test_phrase_falls_back_when_shock_is_unknown(self, db, monkeypatch):
        """Шока для канала нет — фраза всё равно должна быть читаемой, без «None»."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "ROSN", "value": 1.0, "weight": 100.0}])
        sens = {"shocks": {}, "companies": [
            {"ticker": "ROSN", "sector": "Нефть и газ", "effects": {"oil": -12.0}}]}
        phrase = build_link(db, 1, SECTIONS, sens_map=sens)["items"][0]["sensitivity"]["phrase"]
        assert phrase == "цена нефти: −12.0% прибыли" and "None" not in phrase

    def test_unknown_sector_says_so_instead_of_empty(self, db, monkeypatch):
        """Пустой ветер выглядел как «влияния нет». Молчание выпуска — другое."""
        import app.services.macro_portfolio_link as m
        monkeypatch.setattr(m, "_holdings", lambda db_, pid: [
            {"ticker": "MGNT", "value": 1.0, "weight": 100.0}])
        item = build_link(db, 1, SECTIONS, sens_map=SENS)["items"][0]
        assert item["wind"] == m._NO_WIND

    def test_all_shock_channels_have_russian_names(self):
        """Канал из карты чувствительности не должен вылезать латиницей."""
        from app.services.macro_portfolio_link import _CHANNEL_RU
        from app.services.macro_sensitivity_map import _CHANNEL_SHOCK
        missing = [k for k in _CHANNEL_SHOCK if k not in _CHANNEL_RU]
        assert not missing, f"без перевода: {missing}"
