"""Препроцессор привилегированных акций (фикс 1 аудита, docs/cards_audit_systemic.md 1.1).

Чинит financials.json префа, который был КОПИЕЙ обыкновенной: рыночные параметры и
оценку приводит к ТИКЕРУ ПРЕФА. Финансовая отчётность (выручка/EBITDA/прибыль/капитал)
— общая по компании, НЕ трогаем.

Что правит (детерминированно, без LLM):
- meta.last_price / shares_outstanding / market_cap → из rates.csv по тикеру префа;
- multiples.current.pe/pb (от цены префа и общего числа акций) и ev_ebitda (общая капа);
- valuation: ДИВИДЕНДНЫЙ метод — ОСНОВНОЙ. Формула устава в governance не
  структурирована (свободный текст) → оценка по фактическому дивиденду префа
  (rates.csv DIVIDENDVALUE) / требуемая доходность (ключевая ставка), с честным флагом;
- fair_value_range.current_price → цена префа, upside — живьём от цены префа;
- data_flag о пересборке под преф.

Запуск: python -m scripts.fix_pref_financials SNGSP TATNP TORSP ...   (пилот)
        python -m scripts.fix_pref_financials --all                   (все из списка)
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
RATES = os.path.join(BACKEND, "..", "rates.csv")
COMPANIES = os.path.join(BACKEND, "companies")
KEY_RATE = 14.5  # ключевая ставка ЦБ (требуемая доходность-бенчмарк для префа), %; обновляемо

# Полный список префов из аудита (1.1).
ALL_PREFS = ["SBERP", "SNGSP", "TATNP", "NNSBP", "YRSBP", "VGSBP", "KRKNP", "MFGSP",
             "MISBP", "VRSBP", "VSYDP", "IGSTP", "KGKCP", "TASBP", "STSBP", "SAREP",
             "MTLRP", "RTKMP", "NKNCP", "WTCMP", "TORSP", "MGTSP", "DZRDP", "BSPBP",
             "KROTP", "RTSBP", "SAGOP", "BISVP", "KCHEP", "GAZAP", "LSNGP", "PMSBP",
             "KZOSP", "JNOSP", "KRKOP", "RTKMP"]


def _load_rates() -> dict:
    f = open(RATES, encoding="cp1251"); f.readline(); f.readline()
    return {r["SECID"]: r for r in csv.DictReader(f, delimiter=";")}


def _num(s):
    if s is None:
        return None
    s = str(s).replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _last(arr):
    for v in reversed(arr or []):
        if v is not None:
            return v
    return None


def _ordinary(pref: str, rates: dict) -> str | None:
    """Тикер обыкновенной для префа (обычно без хвостовой P; проверяем по rates)."""
    if pref.endswith("P") and pref[:-1] in rates:
        return pref[:-1]
    return None


def fix_pref(pref: str, rates: dict) -> str:
    pr = rates.get(pref)
    if not pr:
        return f"{pref}: НЕТ в rates.csv"
    path = os.path.join(COMPANIES, pref, "financials.json")
    if not os.path.exists(path):
        return f"{pref}: нет financials.json"
    d = json.load(open(path, encoding="utf-8"))
    meta = d.setdefault("meta", {})
    inc = d.get("income_statement") or {}
    bs = d.get("balance_sheet") or {}

    pref_price = _num(pr.get("PRICE_RUB"))
    pref_shares = _num(pr.get("ISSUESIZE"))
    pref_cap = _num(pr.get("SECURITYCAPITALIZATION"))
    pref_div = _num(pr.get("DIVIDENDVALUE"))
    pref_yield = _num(pr.get("DIVIDENDYIELD"))
    ord_t = _ordinary(pref, rates)
    ord_cap = _num(rates[ord_t].get("SECURITYCAPITALIZATION")) if ord_t else None
    ord_shares = _num(rates[ord_t].get("ISSUESIZE")) if ord_t else None
    total_shares = (pref_shares or 0) + (ord_shares or 0) or pref_shares
    total_cap = (pref_cap or 0) + (ord_cap or 0) or pref_cap

    if not pref_price:
        return f"{pref}: нет цены префа в rates.csv"

    # --- meta (рыночные параметры префа) ---
    meta["last_price"] = round(pref_price, 4)
    meta["shares_outstanding"] = pref_shares
    meta["market_cap_pref"] = pref_cap
    meta["is_pref"] = True

    # --- мультипликаторы от цены префа ---
    np_ = _last(inc.get("net_profit")); eq = _last(bs.get("total_equity")); eb = _last(inc.get("ebitda"))
    nd = _last(bs.get("net_debt"))
    mult = d.setdefault("multiples", {}); cur = mult.setdefault("current", {})
    if np_ and total_shares:
        eps = np_ * 1e6 / total_shares
        cur["pe"] = round(pref_price / eps, 2) if eps else None
    if eq and total_shares:
        bvps = eq * 1e6 / total_shares
        cur["pb"] = round(pref_price / bvps, 3) if bvps else None
    if eb and total_cap is not None:
        ev = total_cap + (nd or 0) * 1e6
        cur["ev_ebitda"] = round(ev / (eb * 1e6), 2)

    # --- дивидендный метод — ОСНОВНОЙ ---
    req = KEY_RATE / 100.0
    flags = d.setdefault("data_flags", [])
    div_fair = None
    if pref_div:
        div_fair = round(pref_div / req, 2)
        cons = round(pref_div / (req + 0.03), 2)
        opt = round(pref_div / max(req - 0.03, 0.05), 2)
        val = d.setdefault("valuation", {})
        methods = val.setdefault("methods", [])
        methods[:] = [m for m in methods if m.get("method") != "dividend"]
        methods.insert(0, {
            "method": "dividend", "fair_value_per_share": div_fair, "horizon": "intrinsic_now",
            "key_assumptions": {"dps_actual": pref_div, "required_yield_pct": KEY_RATE,
                                "model": "actual_dps_target_yield", "primary_for_pref": True},
            "status": "ok",
            "explain": {"inputs": {
                "DPS_факт": f"{pref_div:g} ₽ — фактический дивиденд префа {pref} (rates.csv/листинг MOEX)",
                "требуемая_дивдоходность": f"{KEY_RATE}% — ориентир по ключевой ставке ЦБ",
                "текущая_дивдоходность": f"{round((pref_yield or 0)*100,2)}% к цене префа {pref_price:g} ₽"},
                "steps": [f"Преф — квази-облигация: оценка = дивиденд / требуемая доходность.",
                          f"Цена = {pref_div:g} / {req:.3f} = {div_fair} ₽.",
                          "Коридор — по полосе требуемой доходности ±3 п.п."],
                "caveats": ["Уставная формула дивиденда префа НЕ структурирована в данных — "
                            "оценка по ФАКТИЧЕСКОМУ последнему дивиденду, формула не подтверждена.",
                            "Дивиденд префа может колебаться с прибылью/политикой эмитента."]},
        })
        val["fair_value_range"] = {"conservative": cons, "base": div_fair, "optimistic": opt,
                                   "current_price": round(pref_price, 4),
                                   "upside_downside_pct": round((div_fair - pref_price) / pref_price * 100, 1),
                                   "downside_note": None, "primary_method": "dividend"}
        flags.append(f"Пересобрано под преф {pref}: цена/число акций/капитализация/мультипликаторы "
                     f"и дивидендная оценка — по тикеру префа. Дивидендный метод основной "
                     f"(DPS факт {pref_div:g} ₽ / требуемая {KEY_RATE}%). Формула устава не подтверждена.")
    else:
        # дивиденд не раскрыт — честный флаг, оценку не подменяем
        meta_fvr = (d.get("valuation") or {}).get("fair_value_range") or {}
        if "current_price" in meta_fvr:
            old = meta_fvr.get("current_price")
            meta_fvr["current_price"] = round(pref_price, 4)
            base = meta_fvr.get("base")
            if base:
                meta_fvr["upside_downside_pct"] = round((base - pref_price) / pref_price * 100, 1)
        flags.append(f"Преф {pref}: цена/число акций приведены к тикеру префа. Дивиденд префа "
                     f"в rates.csv не раскрыт — уставная формула не подтверждена, дивидендная "
                     f"оценка не построена (честный пробел).")

    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return (f"{pref}: цена {pref_price:g} (было?), P/E {cur.get('pe')}, P/B {cur.get('pb')}, "
            f"EV/EBITDA {cur.get('ev_ebitda')}, дивметод fair {div_fair}, "
            f"upside {round((div_fair-pref_price)/pref_price*100,1) if div_fair else '—'}%")


def main(argv):
    rates = _load_rates()
    tickers = ALL_PREFS if (argv and argv[0] == "--all") else (argv or [])
    seen = set()
    for t in tickers:
        if t in seen:
            continue
        seen.add(t)
        print(fix_pref(t, rates))


if __name__ == "__main__":
    main(sys.argv[1:])
