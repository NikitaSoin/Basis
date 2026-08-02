"""Проекция макро-выпуска на портфель конкретного пользователя.

🔴 Почему КОДОМ, а не отдельным прогоном модели. Выпуск один для всех и генерируется
раз в сутки, а портфель у каждого свой — персонализацию нельзя запечь в общий текст.
Считать её LLM под каждого пользователя тоже нельзя: это платный прогон на каждое
открытие экрана ради вывода, который полностью выводится из уже готовых данных —
секторных ветров выпуска и коэффициентов чувствительности из карточек компаний.

Поэтому здесь нет ни одного собственного суждения: берём то, что уже сказано в
выпуске (сектор под встречным/попутным ветром, компания названа выигравшей или
проигравшей) и то, что уже посчитано в карточке (эффект канала в % прибыли), и
показываем ТОЛЬКО пересечение с бумагами пользователя.

🔴 Владелец (2026-08-01): связка нужна, «только если у пользователя вбит портфель, но
какая-то нужна коммуникация — что если бы у вас был портфель, мы бы добавили анализ по
вашим акциям». Отсюда `empty_state`: он возвращается всегда, когда показать нечего.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_EMPTY = ("Добавьте портфель — и в этом блоке появится разбор по вашим бумагам: какие "
          "из них под попутным ветром, какие под встречным и каким каналом макро до них "
          "доходит.")

# Человекочитаемые названия каналов. Ключи — из _CHANNEL_SHOCK карты чувствительности;
# незнакомый ключ не прячем, а показываем как есть (лучше сырое имя, чем пустое место).
_CHANNEL_RU = {
    "rate": "ключевая ставка", "nim": "процентная маржа", "cost_of_risk": "стоимость риска",
    "demand": "спрос", "fx": "курс рубля", "commodity": "цены на сырьё",
    "steel_price": "цены на сталь", "oil": "цена нефти", "gas": "цена газа",
    "cost_inflation": "инфляция издержек", "food_inflation": "продовольственная инфляция",
    "labor": "стоимость труда", "tariff": "тарифы", "tax": "налоговая нагрузка",
    "logistics": "логистика",
}

# Выпуск не обязан высказываться про каждый сектор. Молчание — это не «влияния нет».
_NO_WIND = "выпуск про этот сектор не высказывался"


def _holdings(db: Session, portfolio_id: int) -> list[dict]:
    """Тикеры акций портфеля с их долей веса. Non-equity сюда не идут: секторные
    ветры выпуска сформулированы про акции, натягивать их на облигации нечестно."""
    rows = db.execute(text(
        "SELECT c.ticker, p.quantity, p.avg_buy_price "
        "FROM portfolio_positions p JOIN companies c ON c.id = p.company_id "
        "WHERE p.portfolio_id = :pid AND p.instrument_type = 'equity' AND c.ticker IS NOT NULL"
    ), {"pid": portfolio_id}).all()
    out = []
    for ticker, qty, price in rows:
        try:
            value = float(qty or 0) * float(price or 0)
        except (TypeError, ValueError):
            value = 0.0
        out.append({"ticker": str(ticker).upper(), "value": value})
    total = sum(h["value"] for h in out) or 0.0
    for h in out:
        # Вес по цене ПОКУПКИ — грубо, но здесь он нужен лишь для порядка вывода;
        # живая переоценка ради сортировки списка не стоит запроса к котировкам.
        h["weight"] = round(h["value"] / total * 100, 1) if total > 0 else None
    return out


def _sector_winds(sections: dict) -> tuple[dict, dict]:
    """Тикер → ветер, названный в выпуске. Два словаря: явные упоминания и по сектору."""
    named: dict[str, dict] = {}
    sector_wind: dict[str, dict] = {}
    for s in sections.get("sectors") or []:
        if not isinstance(s, dict):
            continue
        wind = s.get("wind")
        info = {"wind": wind, "channel": s.get("channel"), "sector": s.get("sector"),
                "dispersion": s.get("dispersion")}
        if s.get("sector"):
            sector_wind[str(s["sector"]).strip().lower()] = info
        for t in s.get("winners") or []:
            named[str(t).upper()] = {**info, "wind": "попутный", "named": True}
        for t in s.get("losers") or []:
            named[str(t).upper()] = {**info, "wind": "встречный", "named": True}
    return named, sector_wind


def _sensitivity_by_ticker(sens_map: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in (sens_map or {}).get("companies") or []:
        t = str(row.get("ticker") or "").upper()
        if t:
            out[t] = row
    return out


def _strongest_channel(row: dict) -> tuple[str, float] | None:
    """Самый сильный канал компании: по модулю эффекта в % прибыли."""
    effects = row.get("effects") or {}
    best, best_v = None, 0.0
    for ch, v in effects.items():
        if isinstance(v, (int, float)) and abs(v) > abs(best_v):
            best, best_v = ch, float(v)
    return (best, best_v) if best else None


def build_link(db: Session, portfolio_id: int | None, sections: dict,
               sens_map: dict | None = None) -> dict:
    """Что макро-выпуск означает для бумаг этого портфеля.

    Возвращает только пересечение: бумага попадает в вывод, если выпуск назвал её
    напрямую, назвал её сектор, или в карточке есть посчитанный канал влияния.
    Ничего не выдумываем: нет данных по бумаге — её просто нет в списке, и мы честно
    говорим, сколько позиций осталось без разбора.
    """
    if not portfolio_id:
        return {"available": False, "empty_state": _EMPTY}

    try:
        holdings = _holdings(db, portfolio_id)
    except Exception:  # noqa: BLE001
        logger.warning("macro_portfolio_link: позиции не прочитаны", exc_info=True)
        return {"available": False, "empty_state": _EMPTY}
    if not holdings:
        return {"available": False, "empty_state": _EMPTY}

    if sens_map is None:
        try:
            from app.services.macro_sensitivity_map import build_sensitivity_map
            sens_map = build_sensitivity_map([h["ticker"] for h in holdings])
        except Exception:  # noqa: BLE001
            logger.warning("macro_portfolio_link: карта чувствительности недоступна",
                           exc_info=True)
            sens_map = {}

    named, sector_wind = _sector_winds(sections)
    by_ticker = _sensitivity_by_ticker(sens_map)
    shocks = (sens_map or {}).get("shocks") or {}

    items, uncovered = [], []
    for h in holdings:
        t = h["ticker"]
        row = by_ticker.get(t) or {}
        hit = named.get(t)
        if not hit:
            sector = str(row.get("sector") or "").strip().lower()
            hit = sector_wind.get(sector)
        channel = _strongest_channel(row)

        if not hit and not channel:
            uncovered.append(t)
            continue

        item = {"ticker": t, "name": row.get("name"), "weight": h["weight"],
                # Отсутствие ветра отдаём ОТДЕЛЬНЫМ полем, а не строкой в поле wind:
                # иначе «выпуск не высказывался» встаёт на место «попутный» и читается
                # как значение ветра, то есть как ошибка (замечание ОТК).
                "wind": (hit or {}).get("wind"),
                "no_wind_note": None if (hit or {}).get("wind") else _NO_WIND,
                # Если выпуск не дал канал по сектору, берём хотя бы признак дисперсии —
                # иначе у одной бумаги есть объяснение, у соседней пусто, и пустота
                # выглядит недоделкой.
                "why": (hit or {}).get("channel") or (hit or {}).get("dispersion"),
                "sector": (hit or {}).get("sector") or row.get("sector"),
                "named_in_release": bool((hit or {}).get("named")),
                "dispersion": (hit or {}).get("dispersion")}
        if channel:
            ch, val = channel
            shock = shocks.get(ch)
            name_ru = _CHANNEL_RU.get(ch, ch)
            item["sensitivity"] = {
                "channel": name_ru,
                "effect_pct": round(val, 1),
                "shock": shock,
                # 🔴 Готовая фраза, а не три поля россыпью. Иначе рядом встают «ветер
                # попутный» и «−5,6%», и это читается как противоречие — хотя ветер
                # про сегодняшнюю макроситуацию, а число отвечает на ГИПОТЕТИЧЕСКИЙ
                # шок. Условие «если» должно стоять в самой фразе.
                "phrase": (f"если {shock} → прибыль {'+' if val > 0 else '−'}"
                           f"{abs(round(val, 1))}%" if shock else
                           f"{name_ru}: {'+' if val > 0 else '−'}{abs(round(val, 1))}% прибыли"),
                # 🔴 Тег «модель», а не «факт»: это расчёт чувствительности на
                # стандартный шок, а не наблюдённая величина. ОТК-персона поймала:
                # «факт карточки» читается как «так и произошло».
                "tag": "модель карточки",
            }
        items.append(item)

    # Сначала то, что выпуск назвал поимённо, затем по весу в портфеле.
    items.sort(key=lambda i: (not i["named_in_release"], -(i.get("weight") or 0)))

    headwind = [i["ticker"] for i in items if i["wind"] == "встречный"]
    tailwind = [i["ticker"] for i in items if i["wind"] == "попутный"]
    return {
        "available": True,
        "items": items,
        "summary": {"headwind": headwind, "tailwind": tailwind,
                    "covered": len(items), "positions": len(holdings)},
        # Честно говорим про непокрытое: молчание читалось бы как «влияния нет».
        "uncovered": uncovered,
        "note": ("Ветер — оценка сегодняшней макроситуации из выпуска. Числа ниже — "
                 "стресс-тест по коэффициентам из карточек компаний: шок одинаковый "
                 "для всех бумаг, чтобы их можно было сравнивать между собой. Это "
                 "не прогноз и не рекомендация."),
    }
