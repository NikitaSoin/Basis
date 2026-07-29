"""Прикидка «если темп удержится» — форвардные мультипликаторы от ТЕКУЩЕГО темпа.

Владелец (2026-07-29): «Сбер идёт +20% г/г по прибыли; мы не знаем, чем кончится
год, но можно аккуратно прикинуть — если во втором полугодии темп сохранится,
какие выйдут P/E, P/B, дивиденд».

🔴 ЭТО НЕ ПРОГНОЗ, А АРИФМЕТИКА ПРОДОЛЖЕНИЯ ТРЕНДА. Мы не утверждаем, что будет —
считаем, что получится ПРИ УСЛОВИИ сохранения темпа. Отсюда три правила:
1. Никакой своей справедливой цены. Единственная цена карточки — BFV
   (`services/bfv/`). Здесь только мультипликаторы, дивиденд и доходность —
   иначе на карточке появится третья цена и мы своими руками сделаем то самое
   расхождение методик, от которого лечимся.
2. Коридор — не «±5 п.п. с потолка», а ФАКТИЧЕСКИЙ разброс сезонной доли этого
   периода в году за прошлые годы. Данные, а не допущение аналитика.
3. Fail-closed. Убыток, закрытый год, протухший интерим, нет истории для
   сезонности — блок НЕ показывается (status ≠ ok). Лучше пусто, чем красивое
   бессмысленное число.

🔴 ЕДИНИЦЫ. `meta.shares_outstanding` НЕНАДЁЖЕН по масштабу (у разных компаний то
млн, то штуки — грабли, задокументированные в bfv/params.py). Поэтому число акций
здесь ВЫВОДИТСЯ из мультипликатора снапшота: shares = P/B × капитал / цена (или
через P/E / P/S). Оно получается сразу в единицах файла, те же, что у прибыли —
и все per-share величины сходятся без знания «млн это или тыс».

Сезонность берётся из истории самой компании (доля закрытого периода в годовом
итоге за прошлые годы), а не из допущения «×2» — у ретейла второе полугодие
сильнее, у нефтянки нет, и мы это не угадываем, а считаем.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.interim_periods import latest_ytd, parse_period, ytd_for_year

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# доля периода в годовом итоге вне этого коридора = перепутанные единицы или
# кривой ряд, а не сезонность (1П не может дать 3% или 99% годовой прибыли)
_SHARE_MIN, _SHARE_MAX = 0.05, 0.98
_PERIOD_WORD = {3: "I квартал", 6: "первое полугодие", 9: "девять месяцев"}


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _last(series):
    """Последнее непустое значение ряда (или само число, если это скаляр)."""
    if isinstance(series, list):
        for x in reversed(series):
            if _num(x) is not None:
                return float(x)
        return None
    return _num(series)


def _last_idx(series) -> int | None:
    if not isinstance(series, list):
        return None
    for i in range(len(series) - 1, -1, -1):
        if _num(series[i]) is not None:
            return i
    return None


def _live_price(db: Session, ticker: str) -> float | None:
    try:
        r = db.execute(text(
            "SELECT q.close FROM quotes q JOIN companies c ON c.id = q.company_id "
            "WHERE c.ticker = :t AND q.close IS NOT NULL "
            "ORDER BY q.date DESC LIMIT 1"), {"t": ticker}).first()
        return float(r[0]) if r and r[0] else None
    except Exception:  # noqa: BLE001
        return None


# --- ряды показателей (банк отчитывается иначе, чем производство) --------------

def _equity_series(fin: dict):
    bs = fin.get("balance_sheet") or {}
    return (bs.get("total_equity") or (bs.get("equity") or {}).get("total_equity")
            or (fin.get("bank_balance") or {}).get("total_equity"))


def _series(fin: dict, block: dict, is_bank: bool) -> dict:
    """Ряды прибыли и «верхней строки» из блока (годового или interim)."""
    bp = block.get("bank_pnl") or {}
    is_ = block.get("income_statement") or {}
    if is_bank:
        profit = bp.get("net_profit") or is_.get("net_profit")
        top = bp.get("operating_income") or bp.get("net_interest_income") or is_.get("revenue")
        top_label = ("Операционные доходы" if bp.get("operating_income")
                     else "Чистый процентный доход" if bp.get("net_interest_income") else "Выручка")
    else:
        profit = is_.get("net_profit")
        top = is_.get("revenue")
        top_label = "Выручка"
    return {"profit": profit, "top": top, "top_label": top_label}


def _implied_shares(fin: dict) -> tuple[float | None, str, bool]:
    """Число акций В ЕДИНИЦАХ ФАЙЛА, выведенное из мультипликатора снапшота.

    shares = мультипликатор × знаменатель / цена снапшота. Приоритет P/B: капитал
    устойчивее прибыли и существует в убыточный год (P/E тогда null или мусор).
    Третий флаг — сошлось ли с meta.shares_outstanding с точностью до масштаба
    (это проверка, а не источник: сам масштаб meta ненадёжен)."""
    meta = fin.get("meta") or {}
    price = _num(meta.get("last_price"))
    cur = ((fin.get("multiples") or {}).get("current")) or {}
    if not price or price <= 0:
        return None, "", False

    shares = src = None
    for mult_key, series, label in (
        ("pb", _equity_series(fin), "P/B × капитал"),
        ("pe", (fin.get("bank_pnl") or {}).get("net_profit") or (fin.get("income_statement") or {}).get("net_profit"), "P/E × прибыль"),
        ("ps", (fin.get("income_statement") or {}).get("revenue"), "P/S × выручка"),
    ):
        m = _num(cur.get(mult_key))
        base = _last(series)
        if m and m > 0 and base and base > 0:
            shares, src = m * base / price, label
            break
    if shares is None or shares <= 0:
        return None, "", False

    declared = _num(meta.get("shares_outstanding"))
    agrees = False
    if declared and declared > 0:
        agrees = any(abs(shares / (declared * f) - 1.0) < 0.08
                     for f in (1.0, 1e3, 1e-3, 1e6, 1e-6, 1e9, 1e-9))
    return shares, src, agrees


def _payout(gov: dict) -> tuple[float | None, str]:
    """Доля прибыли на дивиденд — ТОЛЬКО когда политика привязана к ПРИБЫЛИ.

    Политика от FCF (LKOH, CHMF) или без формулы (MGNT) через прибыль не считается:
    прикидка дивиденда была бы выдумкой. Тогда возвращаем None и честно молчим."""
    dv = gov.get("dividends") or {}
    pct = _num(dv.get("policy_min_payout_pct"))
    base = str(dv.get("policy_base") or "").lower()
    if pct is None or not 0 < pct <= 100:
        return None, "дивполитика без числового ориентира"
    if "fcf" in base or "поток" in base:
        return None, "дивполитика привязана к денежному потоку, не к прибыли"
    if "прибыл" not in base and "profit" not in base and "мсфо" not in base:
        return None, "база дивполитики не привязана к прибыли"
    return pct / 100.0, ""


def _fy_estimate(periods, interim_series, annual_series, fiscal_years, year, end_m):
    """Годовой итог из закрытой части года через историческую сезонную долю.

    mid — по медианной доле прошлых лет; коридор — по МИНИМАЛЬНОЙ и МАКСИМАЛЬНОЙ
    доле (большая доля ⇒ меньше остаётся на год ⇒ нижняя граница)."""
    ytd = ytd_for_year(periods, interim_series, year, end_m)
    if not ytd:
        return None
    shares: list[float] = []
    annual = annual_series if isinstance(annual_series, list) else []
    for i, fy in enumerate(fiscal_years or []):
        fy_val = _num(annual[i]) if i < len(annual) else None
        if not fy_val or fy_val <= 0 or fy >= year:
            continue
        past = ytd_for_year(periods, interim_series, fy, end_m)
        if not past or past["value"] <= 0:
            continue
        s = past["value"] / fy_val
        if _SHARE_MIN < s < _SHARE_MAX:
            shares.append(s)
    if not shares:
        return None
    shares = shares[-4:]
    med = statistics.median(shares)
    out = {"ytd": ytd["value"], "mid": ytd["value"] / med,
           "share_median_pct": round(med * 100, 1), "share_years": len(shares)}
    if len(shares) >= 2:
        out["low"] = ytd["value"] / max(shares)
        out["high"] = ytd["value"] / min(shares)
    return out


def get_run_rate(db: Session, ticker: str) -> dict:
    """Прикидка по тикеру. Всегда словарь со `status`; ok — есть что показывать."""
    ticker = ticker.upper()
    cdir = COMPANIES_DIR / ticker
    fin = _load(cdir / "financials.json")
    if not fin:
        return {"status": "no_company"}
    # число акций тут выводится из мультипликатора снапшота (см. _implied_shares),
    # поэтому капитализацию сперва приводим к ЭМИТЕНТУ по всем классам — иначе у
    # TRNFP/VTBR прикидка наследует заниженный P/B и рисует P/E ~1
    try:
        from app.services.share_capital import apply_issuer_capital
        apply_issuer_capital(db, ticker, fin)
    except Exception:  # noqa: BLE001
        pass

    meta = fin.get("meta") or {}
    interim = fin.get("interim") or {}
    periods = interim.get("periods") or []
    if not periods:
        return {"status": "no_interim"}

    is_bank = bool(meta.get("profile") == "bank" or fin.get("bank_pnl") or fin.get("bank_metrics"))
    i_ser = _series(fin, interim, is_bank)
    a_ser = _series(fin, fin, is_bank)
    fiscal_years = meta.get("fiscal_years") or []

    ytd = latest_ytd(periods, i_ser["profit"])
    if not ytd:
        return {"status": "no_interim_profit"}
    year, end_m = ytd["year"], ytd["end_m"]

    if end_m >= 12:
        return {"status": "year_closed"}
    if ytd["value"] <= 0:
        return {"status": "loss", "year": year}

    # год интерима должен быть ЕЩЁ НЕ ЗАКРЫТ годовой отчётностью, иначе мы
    # «прогнозируем» год, который давно посчитан (и лежит в годовом ряду)
    li = _last_idx(a_ser["profit"])
    last_annual_year = fiscal_years[li] if li is not None and li < len(fiscal_years) else None
    if last_annual_year is not None and year <= last_annual_year:
        return {"status": "year_closed", "year": year}
    # прикидка имеет смысл только про ИДУЩИЙ год. Прошлый год допускаем лишь до
    # апреля (годовая отчётность ещё не вышла — интерим прошлого года остаётся
    # свежайшим, что у нас есть); позже это уже «прогноз» года, который прожит.
    today = date.today()
    if not (year == today.year or (year == today.year - 1 and today.month <= 4)):
        return {"status": "stale", "year": year}

    prof = _fy_estimate(periods, i_ser["profit"], a_ser["profit"], fiscal_years, year, end_m)
    if not prof:
        return {"status": "no_seasonality", "year": year}
    top = _fy_estimate(periods, i_ser["top"], a_ser["top"], fiscal_years, year, end_m)

    # темп: закрытый период к ТОМУ ЖЕ периоду прошлого года (не к предыдущему
    # периоду ряда — там перемешаны 3М/6М/9М, см. interim_periods.py)
    def _yoy(interim_series):
        cur = ytd_for_year(periods, interim_series, year, end_m)
        prev = ytd_for_year(periods, interim_series, year - 1, end_m)
        if not cur or not prev or prev["value"] == 0:
            return None
        return (cur["value"] / abs(prev["value"]) - 1.0) * 100.0

    growth_profit, growth_top = _yoy(i_ser["profit"]), _yoy(i_ser["top"])

    price = _live_price(db, ticker) or _num(meta.get("last_price"))
    if not price or price <= 0:
        return {"status": "no_price", "year": year}

    # 🔴 Если поправка капитализации отработала, число акций берём ТОЧНОЕ — из реестра
    # классов, а не выводим из мультипликатора. Вывод через P/B тут уже НЕЛЬЗЯ: после
    # поправки P/B пересчитан на ЖИВУЮ цену, а _implied_shares делит на цену снапшота
    # (meta.last_price) — базы разъезжаются на всё движение цены, и forward P/E выходит
    # заниженным (у ВТБ на бою было 1,24 вместо ~2,0).
    cap_basis = (fin.get("multiples") or {}).get("capital_basis") or {}
    total_pieces = _num(cap_basis.get("total_shares"))
    unit_factor = {"млн": 1e6, "млрд": 1e9, "тыс": 1e3, "тысячи": 1e3, "тыс. руб.": 1e3}.get(
        meta.get("unit"), 1e6)
    if total_pieces:
        # в единицах файла: EPS = прибыль_файла / (штуки / множитель единиц)
        shares, shares_src, shares_ok = total_pieces / unit_factor, "реестр классов акций", True
    else:
        shares, shares_src, shares_ok = _implied_shares(fin)
    if not shares:
        return {"status": "no_anchor", "year": year}

    payout, payout_note = _payout(_load(cdir / "governance.json"))
    equity_prev = _last(_equity_series(fin))
    bvps_prev = equity_prev / shares if equity_prev and equity_prev > 0 else None

    warnings: list[str] = []
    if prof.get("share_years", 0) < 2:
        warnings.append("сезонная доля — по одному прошлому году, коридор не строится")
    if not shares_ok:
        warnings.append("число акций выведено из мультипликатора снапшота — сверка с meta не сошлась")
    if payout is None and payout_note:
        warnings.append(payout_note)
    # перекрёстная проверка: «прошлый год × (1+темп)» должно быть близко к сезонному
    prev_fy = None
    if li is not None and isinstance(a_ser["profit"], list):
        prev_fy = _num(a_ser["profit"][li])
    if prev_fy and prev_fy > 0 and growth_profit is not None:
        alt = prev_fy * (1 + growth_profit / 100.0)
        if alt > 0 and abs(prof["mid"] / alt - 1.0) > 0.20:
            warnings.append("сезонный метод и «прошлый год × темп» расходятся более чем на 20 % — "
                            "год идёт непохоже на прошлые")
    if is_bank:
        warnings.append("у банка результат сильно зависит от стоимости риска и резервов — "
                        "они меняются быстрее, чем процентный доход")

    def _per_share(profit_level: float | None) -> dict | None:
        if profit_level is None or profit_level <= 0:
            return None
        eps = profit_level / shares
        row = {"eps": round(eps, 2), "pe": round(price / eps, 2)}
        # Дивиденд по политике неправдоподобен (>30% к цене) — верный признак, что
        # в мультипликаторе учтены НЕ ВСЕ классы акций: у TRNFP/VTBR торгуются
        # только префы, капитализация занижена, P/E выходит ~1 и payout 50% даёт
        # «доходность 49%». Считать это дивидендом нельзя — молчим и объясняем.
        if payout is not None:
            dy = eps * payout / price * 100
            if dy <= 30:
                row["dps"] = round(eps * payout, 2)
                row["div_yield_pct"] = round(dy, 2)
            else:
                row["div_yield_suppressed"] = True
        if bvps_prev:
            retained = eps * (1 - (payout if payout is not None else 0.0))
            bvps_fwd = bvps_prev + retained
            if bvps_fwd > 0:
                row["bvps"] = round(bvps_fwd, 2)
                row["pb"] = round(price / bvps_fwd, 2)
        return row

    scenarios = {}
    for key, src in (("low", prof.get("low")), ("mid", prof.get("mid")), ("high", prof.get("high"))):
        r = _per_share(src)
        if r:
            scenarios[key] = {"profit": round(src, 1), **r,
                              "revenue": round(top[key], 1) if top and top.get(key) else None}
    if scenarios.get("mid", {}).pop("div_yield_suppressed", None):
        for s in scenarios.values():
            s.pop("div_yield_suppressed", None)
        warnings.append("дивиденд по политике выходит неправдоподобно высоким к цене — "
                        "в мультипликаторах учтены не все классы акций (торгуются только "
                        "префы), прикидка дивиденда не показывается")

    return {
        "status": "ok",
        "ticker": ticker,
        "year": year,
        "period": {"end_m": end_m, "word": _PERIOD_WORD.get(end_m, f"{end_m} мес."),
                   "closed_share_pct": prof["share_median_pct"], "share_years": prof["share_years"]},
        "unit": meta.get("unit") or "млн",
        "top_label": i_ser["top_label"],
        "growth": {"profit_pct": round(growth_profit, 1) if growth_profit is not None else None,
                   "top_pct": round(growth_top, 1) if growth_top is not None else None},
        "ytd": {"profit": round(prof["ytd"], 1), "revenue": round(top["ytd"], 1) if top else None},
        "prev_fy": {"year": last_annual_year, "profit": round(prev_fy, 1) if prev_fy else None},
        "scenarios": scenarios,
        "payout_pct": round(payout * 100, 1) if payout is not None else None,
        "price": round(price, 4),
        "shares_source": shares_src,
        "warnings": warnings,
        "disclaimer": "Арифметика продолжения темпа, не прогноз аналитика: разовые статьи не "
                      "вычищены, сезонность взята по прошлым годам.",
    }
