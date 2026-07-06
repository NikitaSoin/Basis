"""Пересчёт текущих мультипликаторов (multiples.current в financials.json) от
ЖИВОЙ цены/капитализации, БЕЗ переоценки аналитической нормализации прибыли/EBITDA.

Почему масштабирование, а не пересчёт с нуля: financial-analyst иногда использует
НОРМАЛИЗОВАННУЮ прибыль/EBITDA (без разовых списаний, только продолжающаяся
деятельность и т.п. — см. multiples.current.note) вместо сырых цифр отчётности.
Пересчитывать эти показатели заново — работа аналитика, не механика. Но сама ЦЕНА
устаревает ежедневно и должна быть live всегда (владелец: «недопустимо, чтобы
что-то один раз посчитано и лежит статичной цифрой»).

Метод: meta.last_price — цена, зафиксированная на момент, когда аналитик считал
multiples.current (сверено на LKOH: note цитирует именно meta.last_price и
meta.shares_outstanding). Раз P/E=MCap/прибыль и P/B=MCap/капитал и P/S=MCap/выручка
— все линейно от MCap, значит live-версия = old_value × (MCap_live / MCap_frozen).
EV/EBITDA нелинеен из-за net_debt (не зависит от цены) — пересчитываем EV явно:
EV_live = EV_frozen + (MCap_live − MCap_frozen), затем ev_ebitda_live = EV_live / (EV_frozen/ev_ebitda_frozen).
"""


def _last_num(arr):
    if not isinstance(arr, list):
        return None
    for v in reversed(arr):
        if isinstance(v, (int, float)):
            return float(v)
    return None


def live_scale_multiples(fin: dict, market_cap: float | None, shares_outstanding: float | None) -> dict:
    """Возвращает live-пересчитанный multiples.current (или исходный, если не хватает
    данных для масштабирования — цена/капа/акции). Не мутирует fin."""
    mult = fin.get("multiples") or {}
    cur = mult.get("current") or {}
    if not cur:
        return cur
    meta = fin.get("meta") or {}
    frozen_price = meta.get("last_price")
    if not (isinstance(frozen_price, (int, float)) and frozen_price > 0
            and isinstance(market_cap, (int, float)) and market_cap > 0
            and isinstance(shares_outstanding, (int, float)) and shares_outstanding > 0):
        return cur

    mcap_frozen = frozen_price * shares_outstanding
    if mcap_frozen <= 0:
        return cur

    scale = market_cap / mcap_frozen
    out = dict(cur)
    for key in ("pe", "pe_adj", "pe_reported", "pb", "ps"):
        v = cur.get(key)
        if isinstance(v, (int, float)):
            out[key] = round(v * scale, 3)

    # Дивдоходность обратно пропорциональна цене (дивиденд на акцию неизменен).
    dy = cur.get("dividend_yield_pct")
    if isinstance(dy, (int, float)) and scale:
        out["dividend_yield_pct"] = round(dy / scale, 2)

    ev_ebitda = cur.get("ev_ebitda")
    if isinstance(ev_ebitda, (int, float)) and ev_ebitda:
        unit_scale = {"млн": 1e6, "млрд": 1e9, "тыс": 1e3, "тысячи": 1e3, "тыс. руб.": 1e3}.get(meta.get("unit"), 1e6)
        net_debt = _last_num((fin.get("balance_sheet") or {}).get("net_debt"))
        if net_debt is not None:
            ev_frozen = mcap_frozen + net_debt * unit_scale
            if ev_frozen:
                ev_live = ev_frozen + (market_cap - mcap_frozen)
                out["ev_ebitda"] = round(ev_ebitda * ev_live / ev_frozen, 3)
            else:
                out["ev_ebitda"] = round(ev_ebitda * scale, 3)
        else:
            out["ev_ebitda"] = round(ev_ebitda * scale, 3)

    out["live_scaled"] = True
    out["live_price"] = round(market_cap / shares_outstanding, 2)
    out["frozen_price"] = frozen_price
    return out
