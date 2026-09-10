"""Расчётный слой карточки фонда: то, что считается кодом от живых данных.

🔴 ЗАЧЕМ ЭТО ПОЯВИЛОСЬ (владелец, 11.09.2026: «сделай кодовый слой»). Аналитика фондов
жила в ручных разборах fund-analyst: 4 файла на 104 фонда. Такое покрытие не
поддерживается в принципе — оно устаревает быстрее, чем пополняется. У облигаций та же
задача решена иначе: вердикт «доходность за риск» считает КОД по методичке для каждой
бумаги, а разбор аналитика ложится сверху там, где он есть. Здесь делается то же самое.

ЧТО СЧИТАЕМ (docs/funds-methodology.md, §1 — иерархия подвопросов инвестора):
  1. что внутри — тип и бенчмарк (факт, из БД);
  2. сколько стоит обёртка — TER в процентах и В ДЕНЬГАХ, плюс сравнение с медианой
     своей группы: 1% в год выглядит мелочью и не выглядит ею на горизонте 10 лет;
  3. честно ли следует — отставание от бенчмарка и ошибка слежения (ОЦЕНКА Basis:
     российские УК не обязаны раскрывать tracking error, поэтому считаем из истории
     котировок и помечаем это явно);
  4. чего стоит вход — ликвидность по обороту и числу сделок.

🔴 ЧЕСТНАЯ ДЕГРАДАЦИЯ ВМЕСТО ПРАВДОПОДОБНЫХ ЧИСЕЛ. Если у фонда неизвестен TER (87 из
104 — данные не на MOEX, а на сайтах УК), нет подходящего бенчмарка или коротка история,
блок возвращает None с `data_flag`, а не «примерно как у соседа». Пустое место читается
как незнание; правдоподобное число — как факт, и это худший из возможных исходов для
платформы, которая продаёт доверие к числам.

🔴 ЧИСЛА ИЗ NUMERIC-КОЛОНОК ПРИХОДЯТ КАК Decimal. Смешивать их с float в арифметике
нельзя (TypeError), а `isinstance(x, float)` на них тихо возвращает False — на этом у нас
уже месяцами молча висел мёртвый расчёт. Поэтому всё, что приходит из БД, проходит через
_f() ровно один раз, на входе.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Горизонты, на которых показываем стоимость обёртки. 10 лет — не «инвестгоризонт»,
# а способ увидеть, во что превращается 1% годовых, который в моменте незаметен.
TER_HORIZONS = (1, 5, 10)
TER_BASE_SUM = 100_000  # ₽, база для перевода TER в деньги

# Бенчмарк по типу фонда. Для акций берём индекс ПОЛНОЙ доходности MCFTR, а не IMOEX:
# БПИФ получает дивиденды входящих бумаг и реинвестирует их, поэтому сравнение с ценовым
# индексом систематически льстило бы фонду на величину дивидендной доходности рынка
# (это ~8-10% годовых, то есть больше самого предмета измерения).
BENCHMARKS = {
    "equity": ("index", "MCFTR", "Индекс Мосбиржи полной доходности"),
    "bonds": ("index", "RGBI", "Индекс гособлигаций РФ (RGBI)"),
    "gold": ("spot", "GLDRUB_TOM", "Золото на Мосбирже (GLDRUB_TOM)"),
    "money_market": ("rate", "key_rate", "Ключевая ставка Банка России"),
}

# Ниже этого числа торговых дней ошибку слежения не считаем: на коротком ряде она
# показывает шум, а не качество управления.
MIN_DAYS_FOR_TE = 120
TRADING_DAYS_PER_YEAR = 252


def _f(v):
    """Decimal/None → float/None. Единственная точка приведения типов из БД."""
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _series(db, secid: str, since: date) -> list[tuple[date, float]]:
    rows = db.execute(text(
        "SELECT date, close FROM instrument_history "
        "WHERE secid = :s AND asset_class = 'fund' AND close IS NOT NULL AND date >= :d "
        "ORDER BY date"
    ), {"s": secid, "d": since}).all()
    return [(r[0], _f(r[1])) for r in rows if _f(r[1])]


def _bench_series(db, kind: str, code: str, since: date) -> list[tuple[date, float]]:
    if kind == "index":
        rows = db.execute(text(
            "SELECT date, close FROM index_history WHERE ticker = :t AND close IS NOT NULL "
            "AND date >= :d ORDER BY date"), {"t": code, "d": since}).all()
    elif kind == "spot":
        rows = db.execute(text(
            "SELECT date, close FROM instrument_history WHERE secid = :s AND asset_class = 'spot' "
            "AND close IS NOT NULL AND date >= :d ORDER BY date"), {"s": code, "d": since}).all()
    elif kind == "rate":
        # Ставка — не ряд цен, а уровень, который держится до следующего заседания.
        # Превращаем её в «стоимость денежного счёта»: каждый день начисляем ставку/365.
        # Иначе сравнивать фонд денежного рынка не с чем — у него нет индекса-двойника.
        rows = db.execute(text(
            "SELECT as_of, value FROM macro_data_points "
            "WHERE indicator_code = :c AND metric = 'level' AND value IS NOT NULL "
            "ORDER BY as_of"), {"c": code}).all()
        pts = [(r[0], _f(r[1])) for r in rows if _f(r[1]) is not None]
        if not pts:
            return []
        out, level, idx, acc = [], None, 0, 100.0
        day = since
        today = date.today()
        while day <= today:
            while idx < len(pts) and pts[idx][0] <= day:
                level = pts[idx][1]
                idx += 1
            if level is not None:
                acc *= (1 + level / 100.0 / 365.0)
                out.append((day, acc))
            day += timedelta(days=1)
        return out
    else:
        return []
    return [(r[0], _f(r[1])) for r in rows if _f(r[1])]


def _pct_change(series: list[tuple[date, float]], days: int) -> float | None:
    """Доходность за последние `days` календарных дней по ближайшей доступной точке."""
    if len(series) < 2:
        return None
    last_date, last_val = series[-1]
    target = last_date - timedelta(days=days)
    prior = [p for p in series if p[0] <= target]
    if not prior:
        return None
    base = prior[-1][1]
    if not base:
        return None
    return round((last_val / base - 1) * 100, 2)


def _returns(series: list[tuple[date, float]]) -> dict | None:
    if len(series) < 2:
        return None
    out = {}
    for label, days in (("1м", 30), ("3м", 91), ("6м", 182), ("12м", 365)):
        v = _pct_change(series, days)
        if v is not None:
            out[label] = v
    if not out:
        return None
    return {
        "значения_проц": out,
        "с": series[0][0].isoformat(),
        "по": series[-1][0].isoformat(),
        "точность": "факт (цены закрытия Мосбиржи)",
    }


def _align(a: list[tuple[date, float]], b: list[tuple[date, float]]) -> list[tuple[date, float, float]]:
    bd = dict(b)
    return [(d, v, bd[d]) for d, v in a if d in bd]


def _tracking(db, fund: dict, series: list[tuple[date, float]], since: date) -> dict | None:
    """Отставание от бенчмарка и ошибка слежения.

    Считаем ДВЕ разные вещи, потому что они отвечают на разные вопросы:
      • отставание за период — сколько денег стоило владение фондом против самого
        бенчмарка (сюда попадает и комиссия, и качество управления);
      • ошибка слежения — насколько НЕРОВНО фонд повторяет бенчмарк день ото дня
        (стандартное отклонение разностей дневных доходностей, годовое).
    Фонд может стабильно отставать ровно на комиссию (низкая TE, честная работа) —
    и может метаться вокруг бенчмарка (высокая TE), не отставая в сумме.
    """
    bench = BENCHMARKS.get(fund.get("fund_type") or "")
    if not bench:
        return {"есть": False, "data_flag": "для этого типа фонда сопоставимого бенчмарка нет",
                "точность": "—"}
    kind, code, label = bench
    bs = _bench_series(db, kind, code, since)
    pairs = _align(series, bs)
    if len(pairs) < MIN_DAYS_FOR_TE:
        return {"есть": False, "бенчмарк": label,
                "data_flag": f"история короче {MIN_DAYS_FOR_TE} торговых дней "
                             f"(совпало {len(pairs)}) — на таком ряде оценка показала бы шум",
                "точность": "—"}

    f_ret = (pairs[-1][1] / pairs[0][1] - 1) * 100
    b_ret = (pairs[-1][2] / pairs[0][2] - 1) * 100
    diffs = []
    for i in range(1, len(pairs)):
        pf, pb = pairs[i - 1][1], pairs[i - 1][2]
        if not pf or not pb:
            continue
        diffs.append((pairs[i][1] / pf - 1) - (pairs[i][2] / pb - 1))
    te = None
    if len(diffs) > 30:
        mean = sum(diffs) / len(diffs)
        var = sum((d - mean) ** 2 for d in diffs) / (len(diffs) - 1)
        te = round(math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)

    years = max((pairs[-1][0] - pairs[0][0]).days / 365.25, 0.01)
    lag = round(f_ret - b_ret, 2)
    return {
        "есть": True,
        "бенчмарк": label,
        "период": f"{pairs[0][0].isoformat()} — {pairs[-1][0].isoformat()}",
        "дней_сравнения": len(pairs),
        "фонд_проц": round(f_ret, 2),
        "бенчмарк_проц": round(b_ret, 2),
        "отставание_проц": lag,
        "отставание_годовых_проц": round(lag / years, 2),
        "ошибка_слежения_годовых_проц": te,
        "точность": "оценка Basis (расчёт по котировкам; УК не раскрывают ошибку слежения)",
    }


def _ter_block(db, fund: dict) -> dict:
    ter = _f(fund.get("ter"))
    ftype = fund.get("fund_type")
    peers = db.execute(text(
        "SELECT ter FROM funds WHERE fund_type = :t AND ter IS NOT NULL"), {"t": ftype}).all()
    vals = sorted(x for x in (_f(p[0]) for p in peers) if x is not None)
    median = None
    if vals:
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        median = round(median, 2)

    if ter is None:
        return {
            "есть": False,
            "медиана_группы_проц": median,
            "фондов_в_группе_с_ter": len(vals),
            "data_flag": "УК не раскрывает комиссию машинно: TER нет ни на MOEX, ни в едином "
                         "источнике. Подставлять медиану группы вместо факта нельзя — "
                         "комиссия у соседей отличается в разы",
            "точность": "—",
        }

    money = {}
    for years in TER_HORIZONS:
        # Накопленная комиссия: каждый год она берётся с уже уменьшенной суммы.
        left = TER_BASE_SUM * ((1 - ter / 100) ** years)
        money[str(years)] = round(TER_BASE_SUM - left)
    verdict = None
    if median is not None and len(vals) >= 3:
        if ter <= median * 0.75:
            verdict = "дешевле большинства в своей группе"
        elif ter >= median * 1.25:
            verdict = "дороже большинства в своей группе"
        else:
            verdict = "примерно на уровне группы"
    return {
        "есть": True,
        "ter_проц": ter,
        "в_деньгах_на_100000": money,
        "медиана_группы_проц": median,
        "фондов_в_группе_с_ter": len(vals),
        "вердикт": verdict,
        "точность": "факт (раскрытие УК) / оценка (проекция в деньги)",
    }


def _liquidity(fund: dict) -> dict:
    val = _f(fund.get("val_today"))
    trades = fund.get("num_trades")
    if val is None:
        return {"есть": False, "data_flag": "нет данных об обороте за день", "точность": "—"}
    # Пороги — по распределению оборотов TQTF: то, что ниже ~5 млн ₽ в день, на практике
    # означает заметный спред и медленный выход, а не «чуть менее ликвидно».
    if val >= 100_000_000:
        label = "высокая"
    elif val >= 5_000_000:
        label = "средняя"
    else:
        label = "низкая"
    return {
        "есть": True,
        "оборот_за_день_руб": round(val),
        "сделок_за_день": trades,
        "уровень": label,
        "смысл": ("выйти крупной суммой можно без заметной уступки в цене" if label == "высокая"
                  else "на крупной сумме возможна уступка в цене" if label == "средняя"
                  else "выход крупной суммой упрётся в спред: считайте это частью издержек"),
        "точность": "факт (оборот, число сделок) / суждение (уровень)",
    }


def compute(db, fund: dict) -> dict:
    """Полный расчётный слой по одному фонду. Никогда не бросает: карточка важнее блока."""
    out: dict = {"secid": fund.get("secid")}
    since = date.today() - timedelta(days=800)
    try:
        series = _series(db, fund.get("secid"), since)
    except Exception as e:  # noqa: BLE001
        logger.warning("fund_metrics: история %s не прочиталась (%s)", fund.get("secid"), e)
        series = []

    try:
        out["доходность"] = _returns(series)
    except Exception as e:  # noqa: BLE001
        logger.warning("fund_metrics: доходность %s (%s)", fund.get("secid"), e)
        out["доходность"] = None
    try:
        out["слежение"] = _tracking(db, fund, series, since) if series else None
    except Exception as e:  # noqa: BLE001
        logger.warning("fund_metrics: слежение %s (%s)", fund.get("secid"), e)
        out["слежение"] = None
    try:
        out["комиссия"] = _ter_block(db, fund)
    except Exception as e:  # noqa: BLE001
        logger.warning("fund_metrics: TER %s (%s)", fund.get("secid"), e)
        out["комиссия"] = None
    try:
        out["ликвидность"] = _liquidity(fund)
    except Exception as e:  # noqa: BLE001
        logger.warning("fund_metrics: ликвидность %s (%s)", fund.get("secid"), e)
        out["ликвидность"] = None

    out["как_читать"] = (
        "Комиссия — единственное, что известно заранее и работает против вас каждый год. "
        "Отставание от бенчмарка показывает, во что владение фондом обошлось на самом деле, "
        "а ошибка слежения — насколько ровно фонд повторяет свой ориентир. Basis не "
        "советует покупать или продавать: это описание упаковки, а не сигнал."
    )
    return out
