"""Справедливая цена привилегированных акций.

Модель оценивает БИЗНЕС: балансовая стоимость и рентабельность считаются на весь
капитал. Цена берётся по конкретному тикеру. Пока классы торгуются близко — это
незаметно; когда расходятся — выходит бессмыслица.
"""
from app.services.bfv import service as svc


def _stub(monkeypatch, prices: dict, common_result: dict):
    monkeypatch.setattr(svc, "_live_price", lambda db, t: prices.get(t))
    real = svc.get_bfv

    def fake_get_bfv(db, ticker, required_spread=0.05):
        if ticker.endswith("P"):
            return real(db, ticker, required_spread)
        return common_result
    monkeypatch.setattr(svc, "get_bfv", fake_get_bfv)


def test_diverged_pref_is_rebased_from_common(monkeypatch, tmp_path):
    """🔴 Балансовая стоимость 466 ₽ на акцию не применима к бумаге за 37 ₽.

    Так преф Банка «Санкт-Петербург» получал апсайд +1030% при +102% у обычки.
    """
    monkeypatch.setattr(svc, "COMPANIES_DIR", tmp_path)
    for t in ("BSPB", "BSPBP"):
        (tmp_path / t).mkdir()
        (tmp_path / t / "financials.json").write_text("{}", encoding="utf-8")
    _stub(monkeypatch, {"BSPB": 269.47, "BSPBP": 37.15},
          {"status": "ok", "fair_price": 544.29, "upside_pct": 102.0})
    res = svc._rebase_preferred(None, "BSPBP",
                                {"status": "ok", "fair_price": 419.82,
                                 "upside_pct": 1030.1, "current_price": 37.15}, 0.05)
    assert res["fair_price"] == 75.04
    assert res["upside_pct"] == 102.0, "апсайд префа равен апсайду обычки"
    assert res["pref_rebased_from"] == "BSPB"
    assert any("рыночному соотношению" in w for w in res["warnings"])


def test_pref_trading_alongside_common_is_left_alone(monkeypatch, tmp_path):
    """Классы торгуются вровень — общая база пригодна, не трогаем."""
    monkeypatch.setattr(svc, "COMPANIES_DIR", tmp_path)
    for t in ("TATN", "TATNP"):
        (tmp_path / t).mkdir()
        (tmp_path / t / "financials.json").write_text("{}", encoding="utf-8")
    _stub(monkeypatch, {"TATN": 527.4, "TATNP": 512.1},
          {"status": "ok", "fair_price": 456.0, "upside_pct": -13.5})
    original = {"status": "ok", "fair_price": 470.43, "upside_pct": -8.1,
                "current_price": 512.1}
    assert svc._rebase_preferred(None, "TATNP", original, 0.05) == original


def test_common_share_is_never_touched(monkeypatch, tmp_path):
    original = {"status": "ok", "fair_price": 100.0, "upside_pct": 10.0,
                "current_price": 90.0}
    assert svc._rebase_preferred(None, "SBER", original, 0.05) == original
