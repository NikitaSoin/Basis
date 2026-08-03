"""Детектор макро-дрейфа карточек и очередь на переработку вкладки.

Проверяем свойства, без которых система тихо соврёт: точка отсчёта берётся из
карточки, чужие каналы не приписываются, приоритет считается деньгами.
"""
import json
from datetime import date, timedelta

import pytest

from app.models.macro import MacroDataPoint, MacroIndicator
from app.services import macro_drift as md

# 🔴 Свои коды рядов, а не боевые key_rate/oil_brent. Сначала тесты сеяли точки прямо
# в общие ряды — и ломали СОСЕДНИЙ тест (проверка правдоподобия в gap-агенте смотрит
# историю ряда, а мы подкладывали туда 99% ставки). Падало только в полном прогоне.
_RATE, _OIL, _FX, _CPI = "t_rate", "t_oil", "t_fx", "t_cpi"


@pytest.fixture(autouse=True)
def _isolated_channels(monkeypatch):
    channels = {k: dict(v) for k, v in md._CHANNELS.items()}
    channels["rate"]["code"] = (_RATE, "level")
    channels["commodity"]["code"] = (_OIL, "level")
    channels["fx"]["code"] = (_FX, "level")
    channels["cost_inflation"]["code"] = (_CPI, "level")
    monkeypatch.setattr(md, "_CHANNELS", channels)


def _seed_macro(db, code, metric, points):
    """points: [(дата, значение)]."""
    if not db.get(MacroIndicator, code):
        db.add(MacroIndicator(code=code, title=code, unit="%", frequency="daily",
                              source_type="file", metric_types=[metric], country="ru"))
    for on, value in points:
        existing = (db.query(MacroDataPoint)
                    .filter_by(indicator_code=code, metric=metric, as_of=on).first())
        if existing:
            existing.value = value
        else:
            db.add(MacroDataPoint(indicator_code=code, metric=metric, as_of=on,
                                  value=value, ingested_via="file"))
    db.commit()


def _card(tmp_path, monkeypatch, ticker, *, as_of, snapshot, coefficients,
          financials=None):
    monkeypatch.setattr(md, "COMPANIES_DIR", tmp_path)
    from app.services import scenario_transmission as st
    monkeypatch.setattr(st, "COMPANIES_DIR", tmp_path)
    d = tmp_path / ticker
    d.mkdir(parents=True, exist_ok=True)
    (d / "macro.json").write_text(json.dumps({
        "meta": {"ticker": ticker, "as_of": as_of},
        "snapshot": snapshot,
        "quant_inputs": {"unit": "млрд_руб", "coefficients": coefficients,
                         "financials": financials or {"net_profit": 100.0}},
    }, ensure_ascii=False), encoding="utf-8")
    return ticker


class TestParsing:
    def test_reads_values_analyst_actually_saw(self):
        assert md._parse_number("14,25%") == 14.25
        assert md._parse_number("≈ 78 ₽") == 78.0
        assert md._parse_number("$55") == 55.0
        # диапазон — середина: аналитик имел в виду интервал, а не два числа
        assert md._parse_number("~$60-65") == 62.5
        assert md._parse_number("нет данных") is None

    def test_baseline_ignores_foreign_indicators(self):
        """«Чистый долг / EBITDA 2,1» не должен попасть в ставку."""
        card = {"snapshot": [{"indicator": "Чистый долг / EBITDA", "value": "2,1x"},
                             {"indicator": "Ключевая ставка ЦБ", "value": "14,25%"}]}
        assert md.baseline_from_card(card) == {"rate": 14.25}


class TestDrift:
    def test_drift_measured_from_card_not_from_series(self, db, tmp_path, monkeypatch):
        """🔴 Точка отсчёта — снимок карточки, а не ряд из БД.

        Ряды мы задним числом чиним (в этой же сессии переписали цену Urals). Если
        считать от ряда, «дрейф» покажет нашу собственную правку данных вместо
        изменения мира.
        """
        today = date.today()
        _seed_macro(db, _RATE, "level",
                    [(today - timedelta(days=40), 99.0),   # заведомо кривая история
                     (today, 14.0)])
        _card(tmp_path, monkeypatch, "AAA", as_of=(today - timedelta(days=30)).isoformat(),
              snapshot=[{"indicator": "Ключевая ставка ЦБ", "value": "21%"}],
              coefficients={"rate": {"net_profit": -1.0}})
        out = md.company_drift(db, "AAA")
        assert out["drift"]["rate"]["was"] == 21.0, "берём то, что видел аналитик"
        assert out["drift"]["rate"]["delta"] == -7.0

    def test_small_moves_are_not_drift(self, db, tmp_path, monkeypatch):
        """Шаг ЦБ на 0,25 п.п. картину разбора не меняет — это не повод жечь прогон."""
        today = date.today()
        _seed_macro(db, _RATE, "level", [(today, 14.0)])
        _card(tmp_path, monkeypatch, "BBB", as_of=today.isoformat(),
              snapshot=[{"indicator": "Ключевая ставка ЦБ", "value": "14,25%"}],
              coefficients={"rate": {"net_profit": -1.0}})
        assert md.company_drift(db, "BBB") is None

    def test_channel_absent_in_card_is_not_invented(self, db, tmp_path, monkeypatch):
        """У телекома нет нефтяного канала — нефть ему в дрейф не приписываем."""
        today = date.today()
        _seed_macro(db, _OIL, "level", [(today, 90.0)])
        _seed_macro(db, _RATE, "level", [(today, 14.0)])
        _card(tmp_path, monkeypatch, "TELE", as_of=(today - timedelta(days=30)).isoformat(),
              snapshot=[{"indicator": "Ключевая ставка ЦБ", "value": "21%"}],
              coefficients={"rate": {"net_profit": -1.0}})
        out = md.company_drift(db, "TELE")
        assert set(out["drift"]) == {"rate"}

    def test_oil_drift_only_when_card_names_oil(self, db, tmp_path, monkeypatch):
        """🔴 Канал commodity обобщённый: у ВСМПО это титан, у Белона — уголь.

        Подставлять всем цену Brent нельзя — на этом уже стоял стресс-тест.
        """
        today = date.today()
        _seed_macro(db, _OIL, "level", [(today, 90.0)])
        _card(tmp_path, monkeypatch, "TITAN", as_of=(today - timedelta(days=30)).isoformat(),
              snapshot=[{"indicator": "Цена титана", "value": "$30000"}],
              coefficients={"commodity": {"net_profit": 1.0}})
        assert md.company_drift(db, "TITAN") is None

        _card(tmp_path, monkeypatch, "OILCO", as_of=(today - timedelta(days=30)).isoformat(),
              snapshot=[{"indicator": "Нефть Urals", "value": "$55"}],
              coefficients={"commodity": {"net_profit": 1.0}})
        assert "commodity" in md.company_drift(db, "OILCO")["drift"]


class TestQueue:
    def test_priority_is_money_not_calendar(self, db, tmp_path, monkeypatch):
        """🔴 Очередь по деньгам: у защитной компании ставка может ходить без
        последствий, а у застройщика тот же сдвиг переворачивает картину."""
        today = date.today()
        _seed_macro(db, _RATE, "level", [(today, 14.0)])
        old = (today - timedelta(days=90)).isoformat()
        fresh = (today - timedelta(days=10)).isoformat()
        snapshot = [{"indicator": "Ключевая ставка ЦБ", "value": "21%"}]
        # старый разбор, но компания к ставке почти нечувствительна
        _card(tmp_path, monkeypatch, "DEFENSIVE", as_of=old, snapshot=snapshot,
              coefficients={"rate": {"net_profit": -0.05}})
        # свежий разбор, но компания чувствительна сильно
        _card(tmp_path, monkeypatch, "LEVERED", as_of=fresh, snapshot=snapshot,
              coefficients={"rate": {"net_profit": -5.0}})
        queue = md.drift_queue(db)
        assert [r["ticker"] for r in queue] == ["LEVERED"], \
            "defensive отсеян порогом эффекта, levered — первый"

    def test_broken_base_does_not_own_the_top(self, db, tmp_path, monkeypatch):
        """Компания с околонулевой прибылью даёт тысячи процентов — это свойство
        базы, а не сила события: наверх очереди её пускать нельзя."""
        today = date.today()
        _seed_macro(db, _RATE, "level", [(today, 14.0)])
        as_of = (today - timedelta(days=30)).isoformat()
        snapshot = [{"indicator": "Ключевая ставка ЦБ", "value": "21%"}]
        _card(tmp_path, monkeypatch, "SHELL", as_of=as_of, snapshot=snapshot,
              coefficients={"rate": {"net_profit": -5.0}},
              financials={"net_profit": 0.3})
        _card(tmp_path, monkeypatch, "REAL", as_of=as_of, snapshot=snapshot,
              coefficients={"rate": {"net_profit": -5.0}},
              financials={"net_profit": 30.0})
        queue = md.drift_queue(db)
        assert queue[0]["ticker"] == "REAL"
        assert any(r["ticker"] == "SHELL" for r in queue), "из очереди не выбрасываем"
