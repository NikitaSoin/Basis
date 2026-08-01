"""Карта чувствительности компаний к макро — детерминированная секция снапшота.

🔴 ЗАЧЕМ (владелец: «агенту стоит иметь доступ к нашим карточкам — там много полезного»).
Прямой доступ к 264 карточкам инструментом-перебором давать НЕЛЬЗЯ: агент либо утонет
в обходе, либо возьмёт пять случайных компаний и выдаст «репрезентативный» вывод. Вместо
этого — обычный код собирает готовые коэффициенты чувствительности всех карточек в
компактную таблицу, и она идёт в промпт как ФАКТ. Без LLM, без перебора, копейки токенов.

Что это даёт выпуску: секторный блок перестаёт быть «сектор пострадает» и становится
арифметическим — «по карточке ЛУКОЙЛа ставка +300 б.п. → −N% прибыли».

🔴 НОРМИРОВКА В ПРОЦЕНТАХ, не в миллиардах. У Сбера «−38 млрд» и у малой компании
«−0.5 млрд» несопоставимы: в абсолюте крупные всегда будут «главными пострадавшими»
просто из-за размера. Считаем долю от годовой прибыли (а при убытке — от выручки, иначе
знак переворачивается: у Сегежи ЧП отрицательная, и деление на неё даёт «выигрывает от
роста ставки»).

Единица коэффициентов в карточках РАЗНАЯ (млрд_руб / млн_руб / млн_usd) — не привести
её к общей значит ошибиться в 1000 раз; на этих же граблях уже стояли в факторном
каркасе 2026-08-01.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Приведение единицы карточки к млрд ₽. Долларовые карточки (2 шт.) не конвертируем —
# курс подставлять нельзя без риска соврать, они честно выпадают.
_UNIT_TO_BLN = {"млрд_руб": 1.0, "млн_руб": 0.001}

# Сопоставимый шок по каналу — в тех же единицах, в которых задан коэффициент (`per`).
# Совпадает с калибровкой факторного каркаса (factor_exposures._CHANNEL_SHOCK), чтобы
# два модуля платформы не расходились в том, что считать «шоком».
_CHANNEL_SHOCK = {
    "rate": (3.0, "ставка +300 б.п."),
    "nim": (3.0, "ставка +300 б.п."),
    "cost_of_risk": (150.0, "стоимость риска +150 б.п."),
    "demand": (-2.0, "ВВП −2 п.п."),
    "labor": (3.0, "зарплаты +3 п.п."),
    "cost_inflation": (5.0, "инфляция издержек +5 п.п."),
    "food_inflation": (5.0, "инфляция издержек +5 п.п."),
    "fx": (15.0, "рубль слабее на 15 ₽/$"),
    "commodity": (-20.0, "сырьё дешевле на $20"),
    "steel_price": (-20.0, "сырьё дешевле на $20"),
    "tariff": (5.0, "тариф +5 п.п."),
}

# Каналы, которые НЕЛЬЗЯ складывать как два независимых удара: у банка эффект ставки уже
# частично сидит в стоимости риска (цикл), сложение даст двойной счёт. Помечаем явно,
# чтобы модель видела предупреждение рядом с числами.
_OVERLAPPING = {("rate", "cost_of_risk"), ("nim", "cost_of_risk")}

# Потолок правдоподобия: эффект больше 200% годовой базы на ОДИН шок означает не
# чувствительность, а несопоставимость коэффициента с базой (околонулевая прибыль у
# микрокапа, оболочка, ошибка единиц в карточке).
_MAX_PLAUSIBLE_PCT = 200.0


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _base_for_share(fin: dict) -> tuple[float | None, str]:
    """База, от которой считаем долю: прибыль, а при убытке/около нуля — выручка."""
    profit = fin.get("net_profit")
    revenue = fin.get("revenue")
    if isinstance(profit, (int, float)) and profit > 0:
        return float(profit), "прибыли"
    if isinstance(revenue, (int, float)) and revenue > 0:
        return float(revenue), "выручки"
    return None, ""


def build_sensitivity_map(tickers: list[str] | None = None, top_n: int = 120) -> dict:
    """{shock_labels, companies:[{ticker, sector, effects:{канал: %}, base, warning}]}.

    top_n ограничивает выдачу самыми чувствительными — 264 строки в промпт не нужны,
    ценность несут края распределения (кого действительно двигает макро).
    """
    if not COMPANIES_DIR.exists():
        return {}
    names = tickers or sorted(
        d.name for d in COMPANIES_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    rows = []
    for ticker in names:
        macro = _load(ticker, "macro.json")
        if not macro:
            continue
        qi = macro.get("quant_inputs") or {}
        coefs = qi.get("coefficients") or {}
        scale = _UNIT_TO_BLN.get(str(qi.get("unit") or "").strip().lower())
        if not coefs or scale is None:
            continue
        base, base_kind = _base_for_share(qi.get("financials") or {})
        if not base:
            continue
        effects: dict[str, float] = {}
        implausible = False
        for channel, spec in coefs.items():
            shock = _CHANNEL_SHOCK.get(channel)
            if not shock or not isinstance(spec, dict):
                continue
            delta = spec.get("net_profit")
            if not isinstance(delta, (int, float)):
                continue
            pct = (delta * scale * shock[0]) / (base * scale) * 100
            # 🔴 Фильтр правдоподобия. У компаний с околонулевой базой (микрокапы,
            # оболочки, убыточные) деление даёт абсурд вида −40 000 % годовой выручки —
            # это не «гиперчувствительность», а мусор данных. Такую компанию выкидываем
            # целиком: одно фантастическое число дискредитирует всю таблицу, а модель
            # процитирует его как ФАКТ карточки.
            if abs(pct) > _MAX_PLAUSIBLE_PCT:
                implausible = True
                break
            if abs(pct) < 0.05:
                continue
            effects[channel] = round(pct, 1)
        if implausible or not effects:
            continue
        warning = None
        for a, b in _OVERLAPPING:
            if a in effects and b in effects:
                warning = "каналы ставки и стоимости риска пересекаются — не складывать"
        fin_meta = (_load(ticker, "financials.json") or {}).get("meta") or {}
        rows.append({
            "ticker": ticker,
            "sector": fin_meta.get("sector"),
            "base": f"% от годовой {base_kind}",
            "effects": effects,
            **({"warning": warning} if warning else {}),
        })
    rows.sort(key=lambda r: -max(abs(v) for v in r["effects"].values()))
    return {
        "_note": "Готовые коэффициенты из карточек компаний. Эффект = % от годовой прибыли "
                 "(при убытке — от выручки) на указанный шок. Это ФАКТ карточки: ссылайся "
                 "на него, СВОИ числа по компаниям не считай.",
        "shocks": {k: v[1] for k, v in _CHANNEL_SHOCK.items()},
        "companies": rows[:top_n],
    }
