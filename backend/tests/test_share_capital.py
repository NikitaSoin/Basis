"""Капитализация эмитента по всем классам акций.

Главная ловушка, ради которой эти тесты и написаны: первая версия поправки
масштабировала мультипликаторы по числу акций из `meta` и превратила P/B БСПБ-преф
из 0,11 в 15,4 — потому что там P/B был записан как «цена ÷ BVPS», где число акций
уже сократилось, и множитель применился повторно. Поэтому база аналитика теперь
ВОССТАНАВЛИВАЕТСЯ через P/B × капитал, а поправка применяется, только если эта база
опознана (совпала с полным выпуском или с выпуском конкретного класса).
"""
import pytest

from app.services import share_capital
from app.services.share_capital import apply_issuer_capital, issuer_capital


class _NoDB:
    """Живых котировок нет — сервис откатывается на цены снапшота из реестра."""

    def execute(self, *a, **k):
        raise RuntimeError("нет БД")


@pytest.fixture
def registry(monkeypatch):
    reg = {
        # два класса, оба торгуются (как SBER/SBERP)
        "AAA": {"total_shares": 1_100_000_000, "classes": [
            {"ticker": "AAA", "count": 1_000_000_000, "listed": True, "snapshot_price": 100.0},
            {"ticker": "AAAP", "count": 100_000_000, "listed": True, "snapshot_price": 90.0}]},
        "AAAP": {"total_shares": 1_100_000_000, "classes": [
            {"ticker": "AAA", "count": 1_000_000_000, "listed": True, "snapshot_price": 100.0},
            {"ticker": "AAAP", "count": 100_000_000, "listed": True, "snapshot_price": 90.0}]},
        # торгуется только преф, обыкновенные вне биржи (как TRNFP)
        "BBBP": {"total_shares": 1_000_000_000, "classes": [
            {"ticker": "BBBP", "count": 200_000_000, "listed": True, "snapshot_price": 50.0},
            {"class": "обыкновенные", "count": 800_000_000, "listed": False,
             "how_priced": "reference_class", "holder": "государство"}]},
    }
    monkeypatch.setattr(share_capital, "_CACHE", {"data": reg})
    return reg


def _fin(price, pb, equity_mln, **extra):
    return {"meta": {"last_price": price, "unit": "млн", **extra},
            "multiples": {"current": {"pe": 10.0, "pb": pb, "ps": 2.0}},
            "balance_sheet": {"total_equity": [equity_mln]}}


def test_correct_basis_is_left_alone(registry):
    """P/B уже посчитан от капитализации всех классов → трогать нечего (k≈1)."""
    # капитал 1 000 000 млн ₽; капитализация = 1 млрд×100 + 100 млн×90 = 109 млрд ⇒ P/B 0,109
    cap = issuer_capital(_NoDB(), "AAA", _fin(100.0, 0.109, 1_000_000))
    assert cap and 0.98 < cap["k"] < 1.02


def test_per_share_pb_is_not_scaled_by_class_count(registry):
    """P/B префа как «цена ÷ BVPS» правится к P/B ЭМИТЕНТА, а не умножается на 11×.

    Это тот самый случай BSPBP: число акций внутри «цена ÷ BVPS» уже сократилось,
    и множитель по классам применился бы повторно (было P/B 0,11 → 15,4)."""
    fin = _fin(90.0, 0.099, 1_000_000)   # BVPS = 1e12/1,1 млрд = 909 ₽; 90/909 = 0,099
    cap = issuer_capital(_NoDB(), "AAAP", fin)
    assert cap and cap["k"] == pytest.approx(1.10, rel=0.02)   # а НЕ ×11
    apply_issuer_capital(_NoDB(), "AAAP", fin)
    ord_fin = _fin(100.0, 0.109, 1_000_000)
    apply_issuer_capital(_NoDB(), "AAA", ord_fin)
    # обе бумаги одного эмитента обязаны показать ОДИН P/B
    assert fin["multiples"]["current"]["pb"] == pytest.approx(
        ord_fin["multiples"]["current"]["pb"], rel=0.01)


def test_unlisted_class_lifts_capitalisation(registry):
    """Торгуется только преф: капитализация должна вырасти в 5 раз (200 → 1 000 акций)."""
    fin = _fin(50.0, 0.1, 100_000)      # аналитик считал по 200 акциям: 10 000/100 000
    cap = issuer_capital(_NoDB(), "BBBP", fin)
    assert cap and cap["k"] == pytest.approx(5.0, rel=0.02)
    apply_issuer_capital(_NoDB(), "BBBP", fin)
    assert fin["multiples"]["current"]["pb"] == pytest.approx(0.5, rel=0.02)
    assert fin["multiples"]["current"]["pe"] == pytest.approx(50.0, rel=0.02)
    assert any("не обращается" in w for w in fin["multiples"]["capital_basis"]["warnings"])


def test_unrecognised_basis_is_not_touched(registry):
    """База аналитика не бьётся ни с одним классом → молчим, а не «поправляем»."""
    # P/B 0,17 ⇒ база 340 млн акций: не совпадает ни с классом (200/800 млн),
    # ни с полным выпуском (1 млрд) — значит разъехалось что-то ещё, не классы
    assert issuer_capital(_NoDB(), "BBBP", _fin(50.0, 0.17, 100_000)) is None


def test_applying_twice_changes_nothing(registry):
    """Идемпотентность: скринер и витрина могут вызвать поправку по одному объекту."""
    fin = _fin(50.0, 0.1, 100_000)
    apply_issuer_capital(_NoDB(), "BBBP", fin)
    once = dict(fin["multiples"]["current"])
    apply_issuer_capital(_NoDB(), "BBBP", fin)
    assert fin["multiples"]["current"]["pb"] == pytest.approx(once["pb"], rel=1e-6)


def test_bvps_recomputed_on_full_share_count(registry):
    """BVPS тоже на полное число акций — иначе поправка не доедет до BFV."""
    fin = _fin(50.0, 0.1, 100_000)
    fin["balance_sheet"]["book_value_per_share"] = [500.0]   # 100 000 млн / 200 акций
    apply_issuer_capital(_NoDB(), "BBBP", fin)
    assert fin["balance_sheet"]["book_value_per_share"][0] == pytest.approx(100.0, rel=0.01)


def test_unknown_ticker_is_ignored(registry):
    assert issuer_capital(_NoDB(), "ZZZZ", _fin(10.0, 1.0, 1_000)) is None
