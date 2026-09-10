"""Кодовый слой карточки фонда: проверяем то, что легко сломать молча.

🔴 ПОЧЕМУ ТЕСТ НЕ ХОДИТ В БАЗУ. Проверять надо арифметику и поведение при нехватке
данных, а не то, что PostgreSQL умеет отдавать строки. Живая база вдобавок делает тест
недетерминированным (данные меняются кроном) и ломает параллельные прогоны — у нас уже
есть грабля с общей тестовой базой. Поэтому db здесь — заглушка, отдающая ровно те
строки, которые нужны конкретной проверке.
"""
from datetime import date, timedelta

from app.services import fund_metrics as fm


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Отдаёт заранее заданные ответы по порядку обращений."""

    def __init__(self, answers):
        self._answers = list(answers)

    def execute(self, *_args, **_kwargs):
        return _Result(self._answers.pop(0) if self._answers else [])


def _straight_series(days: int, start: float = 100.0, daily: float = 0.0):
    """Ряд с постоянным дневным приростом — предсказуемый вход для проверки формул."""
    today = date.today()
    out, val = [], start
    for i in range(days, 0, -1):
        out.append((today - timedelta(days=i), val))
        val *= (1 + daily)
    return out


def test_ter_в_деньгах_считается_сложным_процентом():
    """1% в год с суммы 100 000 ₽ за 10 лет — это НЕ 10 000 ₽: комиссия берётся с
    уменьшающегося остатка. Ошибка «ter * years» завышала бы потери, а такое число
    на карточке читается как факт."""
    db = _FakeDB([[(1.0,), (1.0,), (1.0,)]])
    res = fm._ter_block(db, {"ter": 1.0, "fund_type": "equity"})
    assert res["есть"] is True
    assert res["в_деньгах_на_100000"]["1"] == 1000
    assert 9500 < res["в_деньгах_на_100000"]["10"] < 9600  # 100000*(1-0.01^)… ≈ 9562


def test_неизвестный_ter_не_подменяется_медианой_группы():
    """Главное правило слоя: пустое место честнее правдоподобного числа."""
    db = _FakeDB([[(0.5,), (1.2,), (0.9,)]])
    res = fm._ter_block(db, {"ter": None, "fund_type": "equity"})
    assert res["есть"] is False
    assert "в_деньгах_на_100000" not in res
    assert res["медиана_группы_проц"] == 0.9
    assert res["data_flag"]


def test_короткая_история_не_даёт_ошибку_слежения():
    """На коротком ряде TE показывает шум. Лучше сказать «не знаем», чем напечатать
    красивое число, за которым ничего нет."""
    series = _straight_series(40)
    db = _FakeDB([[(d, v) for d, v in series]])
    res = fm._tracking(db, {"fund_type": "equity"}, series, date.today() - timedelta(days=60))
    assert res["есть"] is False
    assert "короче" in res["data_flag"]


def test_фонд_ровно_отстающий_на_комиссию_имеет_около_нулевую_ошибку_слежения():
    """Фонд, который каждый день проигрывает ориентиру одинаково (комиссия), следует
    ЧЕСТНО: отставание есть, ошибка слежения ≈ 0. Смешивать эти две вещи нельзя —
    иначе дешёвый и ровный фонд выглядел бы как плохой."""
    bench = _straight_series(400, daily=0.0004)
    fund = [(d, v * (1 - 0.00004) ** i) for i, (d, v) in enumerate(bench)]
    db = _FakeDB([[(d, v) for d, v in bench]])
    res = fm._tracking(db, {"fund_type": "equity"}, fund, date.today() - timedelta(days=500))
    assert res["есть"] is True
    assert res["отставание_проц"] < 0                      # отстал
    assert res["ошибка_слежения_годовых_проц"] < 0.1       # но ровно, без метаний


def test_ликвидность_говорит_что_это_значит_для_выхода():
    low = fm._liquidity({"val_today": 900_000, "num_trades": 12})
    assert low["уровень"] == "низкая" and "спред" in low["смысл"]
    high = fm._liquidity({"val_today": 250_000_000, "num_trades": 9000})
    assert high["уровень"] == "высокая"
    assert fm._liquidity({"val_today": None})["есть"] is False


def test_compute_не_падает_на_пустой_базе():
    """Блок может не собраться — карточка обязана открыться в любом случае."""
    res = fm.compute(_FakeDB([]), {"secid": "TEST", "fund_type": "equity", "ter": None})
    assert res["secid"] == "TEST"
    assert "как_читать" in res
