"""Якорный блок чисел (единый источник истины, связность субагентов v3).

Детерминированно извлекает якорные числа из financials.json (+ rates.csv для
рыночных параметров, особенно префов) и отдаёт их JSON-ом. Орк перепрогона подаёт
этот блок КАЖДОМУ субагенту, чтобы все вкладки использовали РОВНО эти числа и не
пересчитывали свои.

Использование:
  python -m scripts.anchor_block SBER          # печатает якорный блок тикера
  from scripts.anchor_block import anchor_block # anchor_block("SBER") -> dict
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
RATES = os.path.join(BACKEND, "..", "rates.csv")
COMPANIES = os.path.join(BACKEND, "companies")

_RATES_CACHE = None


def _rates() -> dict:
    global _RATES_CACHE
    if _RATES_CACHE is None:
        f = open(RATES, encoding="cp1251"); f.readline(); f.readline()
        _RATES_CACHE = {r["SECID"]: r for r in csv.DictReader(f, delimiter=";")}
    return _RATES_CACHE


def _num(s):
    if s in (None, "", "-"):
        return None
    s = str(s).replace(" ", "").replace("\xa0", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def anchor_block(ticker: str) -> dict:
    """Якорный блок: рыночные параметры (rates.csv, по СВОЕМУ тикеру) + финансовые
    ряды (financials.json). Для префа цена/число акций/капа/дивиденд — по тикеру префа."""
    t = ticker.upper()
    rates = _rates()
    rr = rates.get(t, {})
    is_pref = t.endswith("P") and (t[:-1] in rates)
    ord_t = t[:-1] if is_pref else None

    blk = {
        "ticker": t,
        "is_pref": is_pref,
        "ordinary_ticker": ord_t,
        # рыночные параметры — строго по СВОЕМУ тикеру
        "price": _num(rr.get("PRICE_RUB")),
        "shares_outstanding": _num(rr.get("ISSUESIZE")),
        "market_cap": _num(rr.get("SECURITYCAPITALIZATION")),
        "dividend_last": _num(rr.get("DIVIDENDVALUE")),
        "dividend_yield_last_pct": (lambda v: round(v * 100, 2) if v is not None else None)(_num(rr.get("DIVIDENDYIELD"))),
    }
    if is_pref:
        oo = rates.get(ord_t, {})
        blk["ordinary_shares"] = _num(oo.get("ISSUESIZE"))
        blk["ordinary_market_cap"] = _num(oo.get("SECURITYCAPITALIZATION"))
        blk["total_shares"] = (blk["shares_outstanding"] or 0) + (blk["ordinary_shares"] or 0) or blk["shares_outstanding"]
        blk["total_market_cap"] = (blk["market_cap"] or 0) + (blk["ordinary_market_cap"] or 0) or blk["market_cap"]

    fpath = os.path.join(COMPANIES, t, "financials.json")
    if os.path.exists(fpath):
        try:
            d = json.load(open(fpath, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            d = {}
        meta = d.get("meta") or {}
        inc = d.get("income_statement") or {}
        bs = d.get("balance_sheet") or {}
        cf = d.get("cash_flow") or {}
        adj = d.get("adjusted") or {}
        blk["fiscal_years"] = meta.get("fiscal_years")
        blk["reporting_standard"] = meta.get("reporting_standard")
        blk["unit"] = meta.get("unit", "млн")
        blk["revenue"] = inc.get("revenue")
        blk["ebitda"] = inc.get("ebitda")
        blk["net_profit_reported"] = inc.get("net_profit")
        blk["net_profit_adjusted"] = adj.get("net_profit") if isinstance(adj, dict) else None
        blk["net_debt"] = bs.get("net_debt")
        blk["total_equity"] = bs.get("total_equity")
        blk["fcf"] = cf.get("fcf") if isinstance(cf, dict) else None
        # ND/EBITDA последнего года
        def _last(a):
            for v in reversed(a or []):
                if v is not None:
                    return v
            return None
        nd, eb = _last(bs.get("net_debt")), _last(inc.get("ebitda"))
        blk["nd_ebitda_latest"] = round(nd / eb, 3) if (nd is not None and eb) else None
    return blk


def main(argv):
    for t in argv:
        print(json.dumps(anchor_block(t), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
