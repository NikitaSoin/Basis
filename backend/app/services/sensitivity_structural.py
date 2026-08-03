"""Структурная чувствительность компании к макро — независимый расчёт КОДОМ.

🔴 ЗАЧЕМ (владелец, 2026-08-03): «нам нужно построить зависимости финансовых
показателей от макропоказателей — чувствительности сейчас есть в карточках, но могут
быть криво посчитаны».

Коэффициенты в карточках ставит аналитик-LLM: он читает отчётность и оценивает
«ослабление рубля на +1 ₽/$ даёт +41 млрд выручки». Оценка бывает хорошей, но она
непроверяема и невоспроизводима: два прогона по одной компании дадут разные числа, а
ошибка в единицах или в базе не видна никому. Этот модуль считает ТО ЖЕ САМОЕ из
структуры отчётности — арифметикой, без модели. Совпало — коэффициент карточки
подтверждён вторым способом. Разошлось в разы — флаг «посмотреть глазами».

🔴 ЧТО ЭТО НЕ ЕСТЬ. Не «правильный ответ», который заменяет карточку. Структурный
расчёт груб по построению: он не знает про хеджирование, долгосрочные контракты с
фиксированной ценой, переносимость издержек в цену и налоговые тонкости (НДПИ,
демпфер). Он знает ровно то, что видно в отчётности. Поэтому его роль — ВТОРОЕ
независимое мнение и заполнение пустот, а не приговор.

Методика целиком, с разбором альтернатив (регрессия, рыночные беты, отраслевые
эластичности) и обоснованием выбора — `docs/sensitivity_methodology.md`.

🔴 ДВА ТИПА ВЕЛИЧИН — не путать (найдено на данных 2026-08-03).
«оценка» (ставка, курс) — ожидаемый эффект, сравнивается с карточкой в обе стороны.
«граница» (зарплаты, инфляция издержек) — ПРЕДЕЛ удара при нулевом переносе в цену.
Считать её ожидаемым эффектом нельзя: у X5 переменные издержки — это закупка товара,
которая идёт в цену полки, а формула «без переноса» дала бы −151% годовой прибыли на
инфляцию 5 п.п., то есть мгновенный вечный убыток. У сетей с процентной наценкой
инфляция закупки прибыль вообще УВЕЛИЧИВАЕТ. Переносимость из отчётности не видна,
поэтому по этим каналам проверяем только одностороннее: карточка не имеет права
показывать удар СИЛЬНЕЕ физического предела.

🔴 СЧИТАЕМ СРАЗУ В ПРОЦЕНТАХ ОТ БАЗЫ. Единица карточек разная (млрд_руб / млн_руб /
млн_usd), и приведение — известные грабли: ошибка в 1000 раз в факторном каркасе
2026-08-01. Внутри одной карточки числитель и знаменатель в одной единице, она
сокращается — ошибиться негде.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

_TAX = 0.25                    # налог на прибыль с 2025 года
_DEFAULT_KEY_RATE = 14.0       # запасное значение, если ставку не передали

# Доля долга, которая переоценивается за год. Зависит от того, насколько дорого
# компания уже обслуживает долг: если ставка по портфелю близка к ключевой — долг
# плавающий или короткий и переоценится почти весь; если сильно ниже — это льготные
# и старые фиксированные кредиты, они переживут цикл без переоценки.
_REPRICING_HIGH, _REPRICING_MID, _REPRICING_LOW = 0.70, 0.45, 0.25

# Сколько из прироста рублёвой экспортной выручки доходит до чистой прибыли.
# У сырьевиков прогрессивные НДПИ/пошлины и демпфер изымают бо́льшую часть выигрыша,
# у остальных экспортёров рублёвые издержки просто не растут вслед за курсом.
_FX_RETENTION_RESOURCE, _FX_RETENTION_OTHER = 0.30, 0.50
_RESOURCE_SECTORS = {"oil_gas", "metals", "mining", "chemicals", "нефтегаз", "металлургия"}

_LABOR_RE = re.compile(r"персонал|оплат\w* труда|фот\b|зарплат|вознагражд|сотрудник", re.I)
# Регионы, выручка от которых валютная. «СНГ» намеренно НЕ считаем экспортом: расчёты
# там часто рублёвые, и завысить долю валютной выручки хуже, чем занизить.
_DOMESTIC_RE = re.compile(r"росси|рф\b|внутренн|снг|домашн", re.I)


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _last(series) -> float | None:
    """Последнее заполненное значение ряда (в карточках это списки по годам)."""
    if isinstance(series, (int, float)):
        return float(series)
    if isinstance(series, list):
        for v in reversed(series):
            if isinstance(v, (int, float)):
                return float(v)
    return None


def _base(pl: dict) -> tuple[float | None, str]:
    """База для доли: прибыль, а при убытке — выручка (иначе знак переворачивается)."""
    profit = _last(pl.get("net_profit"))
    revenue = _last(pl.get("revenue"))
    if profit and profit > 0:
        return profit, "прибыли"
    if revenue and revenue > 0:
        return revenue, "выручки"
    return None, ""


def _pct(effect: float, base: float) -> float:
    return round(effect / base * 100, 1)


def _rate_channel(fin: dict, base: float, key_rate: float) -> dict | None:
    """Ставка +300 б.п. → % базы. Долг дорожает, денежная позиция — наоборот.

    🔴 Считаем ОБА направления. Прежняя проверка отбрасывала компании с отрицательным
    чистым долгом (`net_debt <= 0 → None`), то есть все «кубышки» — а это как раз тот
    случай, где карточка чаще всего ошибается со знаком: у ЛУКОЙЛа рост ставки прибыль
    увеличивает, а не уменьшает.
    """
    bs = fin.get("balance_sheet") or {}
    pl = fin.get("income_statement") or {}
    net_debt = _last(bs.get("net_debt"))
    if net_debt is None:
        return None
    finance_costs = _last(pl.get("finance_costs"))
    # Доля переоценки — по тому, насколько дорог уже обслуживаемый долг.
    share, why = _REPRICING_MID, "долг переоценивается частично (оценка по умолчанию)"
    if finance_costs and net_debt > 0:
        implied = finance_costs / net_debt * 100
        if implied >= key_rate * 0.8:
            share, why = _REPRICING_HIGH, (
                f"ставка по портфелю ~{implied:.0f}% при ключевой {key_rate:.0f}% — "
                "долг плавающий или короткий, переоценится почти весь")
        elif implied <= key_rate * 0.4:
            share, why = _REPRICING_LOW, (
                f"ставка по портфелю ~{implied:.0f}% при ключевой {key_rate:.0f}% — "
                "льготные и старые фиксированные кредиты, цикл переживут")
    # Знак: положительный чистый долг → рост ставки бьёт по прибыли; отрицательный
    # (денег больше долга) → прибыль растёт вместе со ставкой.
    effect = -net_debt * share * 0.03 * (1 - _TAX)
    return {
        "pct": _pct(effect, base),
        "kind": "оценка",
        "inputs": {"net_debt": round(net_debt), "repricing_share": share},
        "how": f"чистый долг {net_debt:,.0f} × {share:.0%} переоценки × 3 п.п. × "
               f"(1−налог) — {why}".replace(",", " "),
    }


# Ниже этой доли валютной выручки курсовой канал НЕ считаем. Причина найдена на
# данных (2026-08-03): модель видит только ЭКСПОРТНУЮ сторону курса и не знает про
# импортные издержки — лизинг, оборудование, сырьё в валютном паритете. У Аэрофлота
# (карточка −7,2%) она давала +14,5%, у Абрау-Дюрсо (−13,0%) → +3,8%: знак наоборот.
# При доле валютной выручки от половины экспортный эффект почти наверняка перевешивает
# импортный, ниже — гадание. Ложный флаг хуже отсутствия флага.
_FX_MIN_EXPORT_SHARE = 50.0


def _fx_channel(fin: dict, base: float, sector: str | None, usd_rate: float) -> dict | None:
    """Рубль слабее на 15 ₽/$ → % базы, через долю валютной выручки."""
    pl = fin.get("income_statement") or {}
    revenue = _last(pl.get("revenue"))
    geo = fin.get("geo_split")
    if not revenue or not isinstance(geo, list) or not geo:
        return None
    export_pct = 0.0
    for item in geo:
        if not isinstance(item, dict):
            continue
        pct = item.get("pct")
        if not isinstance(pct, (int, float)):
            continue
        if not _DOMESTIC_RE.search(str(item.get("region") or "")):
            export_pct += float(pct)
    if export_pct < _FX_MIN_EXPORT_SHARE:
        return None
    retention = (_FX_RETENTION_RESOURCE if (sector or "").lower() in _RESOURCE_SECTORS
                 else _FX_RETENTION_OTHER)
    # Рублёвая экспортная выручка растёт пропорционально курсу: +15 ₽ при курсе
    # usd_rate — это +15/usd_rate процентов к рублёвой цене того же объёма.
    effect = revenue * (export_pct / 100) * (15.0 / usd_rate) * retention * (1 - _TAX)
    return {
        "pct": _pct(effect, base),
        "kind": "оценка",
        "inputs": {"export_share_pct": round(export_pct, 1), "retention": retention},
        "how": f"валютная выручка {export_pct:.0f}% × рост рублёвой цены "
               f"{15.0 / usd_rate:.0%} × ретенция {retention:.0%} × (1−налог); "
               "импортные издержки не учтены — оценка сверху",
    }


def _cost_pct_base(cb: list, revenue: float, op_profit: float) -> float | None:
    """От чего берутся проценты в `cost_breakdown` — от выручки или от издержек.

    🔴 Единой конвенции в карточках НЕТ (проверено на 208 карточках 2026-08-03):
    у 21 сумма долей ≈ 100% (значит, доли от суммы издержек), у остальных медиана
    84,5% (значит, от выручки — остаток и есть операционная маржа). Взять одну
    гипотезу для всех — систематически ошибиться в разы на половине компаний, а
    ошибка тихая: числа выглядят правдоподобно. Поэтому определяем по каждой карточке.
    """
    total = sum(float(i.get("pct") or 0) for i in cb if isinstance(i, dict))
    if total <= 0:
        return None
    costs = revenue - op_profit
    if 97.0 <= total <= 103.0:
        return costs if costs > 0 else None
    return revenue


def _labor_channel(fin: dict, base: float) -> dict | None:
    """Зарплаты +3 п.п. → % базы, через долю ФОТ в издержках."""
    pl = fin.get("income_statement") or {}
    cb = fin.get("cost_breakdown")
    revenue = _last(pl.get("revenue"))
    op_profit = _last(pl.get("operating_profit"))
    if not revenue or op_profit is None or not isinstance(cb, list):
        return None
    labor_pct = sum(float(i.get("pct") or 0) for i in cb
                    if isinstance(i, dict) and _LABOR_RE.search(str(i.get("name") or "")))
    pct_base = _cost_pct_base(cb, revenue, op_profit)
    if labor_pct <= 0 or not pct_base:
        return None
    effect = -pct_base * (labor_pct / 100) * 0.03 * (1 - _TAX)
    return {
        "pct": _pct(effect, base),
        "kind": "граница",
        "inputs": {"labor_share_of_costs_pct": round(labor_pct, 1)},
        "how": f"база {pct_base:,.0f} × доля ФОТ {labor_pct:.0f}% × 3 п.п. × "
               "(1−налог), при НУЛЕВОМ переносе в цену — это предел удара, "
               "а не ожидаемый эффект".replace(",", " "),
    }


def _cost_inflation_channel(fin: dict, base: float) -> dict | None:
    """Инфляция издержек +5 п.п. → % базы, через переменную часть себестоимости."""
    pl = fin.get("income_statement") or {}
    cb = fin.get("cost_breakdown")
    revenue = _last(pl.get("revenue"))
    op_profit = _last(pl.get("operating_profit"))
    if not revenue or op_profit is None or not isinstance(cb, list):
        return None
    var_pct = sum(float(i.get("pct") or 0) for i in cb
                  if isinstance(i, dict) and i.get("type") == "variable")
    pct_base = _cost_pct_base(cb, revenue, op_profit)
    if var_pct <= 0 or not pct_base:
        return None
    effect = -pct_base * (var_pct / 100) * 0.05 * (1 - _TAX)
    return {
        "pct": _pct(effect, base),
        "kind": "граница",
        "inputs": {"variable_share_of_costs_pct": round(var_pct, 1)},
        "how": f"база {pct_base:,.0f} × переменная часть {var_pct:.0f}% × 5 п.п. × "
               "(1−налог), при НУЛЕВОМ переносе в цену — это предел удара, "
               "а не ожидаемый эффект".replace(",", " "),
    }


def structural_sensitivity(ticker: str, key_rate: float = _DEFAULT_KEY_RATE,
                           usd_rate: float = 80.0) -> dict:
    """Все считаемые каналы по компании: {канал: {pct, inputs, how}}.

    Шоки те же, что в карте чувствительности (`macro_sensitivity_map._CHANNEL_SHOCK`),
    иначе два модуля платформы будут говорить о разном под одним словом «чувствительность».
    """
    fin = _load(ticker, "financials.json")
    if not fin:
        return {}
    pl = fin.get("income_statement") or {}
    base, base_kind = _base(pl)
    if not base:
        return {}
    sector = ((fin.get("meta") or {}).get("sector") or "")
    channels = {}
    for name, value in (
        ("rate", _rate_channel(fin, base, key_rate)),
        ("fx", _fx_channel(fin, base, sector, usd_rate)),
        ("labor", _labor_channel(fin, base)),
        ("cost_inflation", _cost_inflation_channel(fin, base)),
    ):
        if value and abs(value["pct"]) >= 0.05:
            channels[name] = value
    if not channels:
        return {}
    return {"ticker": ticker, "base": f"% от годовой {base_kind}", "channels": channels}
