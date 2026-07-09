"""Единый факторный каркас — код-маппер экспозиций Ф1-Ф8 (методика §3.1-3.2,
docs/Basis_методика_индекса_качества_портфеля_v2.1.md).

Восемь факторов, экспозиция Exp(i,k) ∈ {-2,-1,0,+1,+2}, маппится из
effect_sign существующих карточек (macro.json/geo.json) — LLM НЕ вызывается,
только чтение уже посчитанных субагентами полей. Ф8 (рефинансирование)
считается кодом из financials.json.

Потребители: FactorD (D-модуль), MGI (сценарная устойчивость), forward-ERR —
все три через один и тот же движок (app/services/factor_engine.py), чтобы не
плодить расходящиеся суждения об одних и тех же экспозициях (принцип №2
методики).
"""
from __future__ import annotations

import json
from pathlib import Path

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Восемь факторов методики (§3.1). Ф2 объединяет три типа карточки (demand/
# inflation/labor) — на шкале -2..+2 они неразличимы, методика сама это
# отмечает («19 факторов черновика неразличимы»).
FACTOR_KEYS = ["rate", "demand", "fx", "commodity", "sanctions", "conflict", "fiscal", "refinancing"]
FACTOR_LABELS = {
    "rate": "Ключевая ставка", "demand": "Внутренний спрос и инфляция",
    "fx": "Курс рубля", "commodity": "Цены экспортного сырья",
    "sanctions": "Санкции и внешние ограничения", "conflict": "Военная эскалация",
    "fiscal": "Регуляторно-налоговое давление", "refinancing": "Рефинансирование и кредитный цикл",
}
# type в macro.json/geo.json → наш факторный ключ
_MACRO_TYPE_MAP = {"rate": "rate", "demand": "demand", "inflation": "demand", "labor": "demand",
                    "fx": "fx", "commodity": "commodity", "fiscal": "fiscal"}
_GEO_TYPE_MAP = {"sanctions": "sanctions", "conflict": "conflict"}

_SIGN_MAP = {"strong_negative": -2, "negative": -1, "mixed": 0, "neutral": 0,
             "positive": 1, "strong_positive": 2}


def _load_json(ticker: str, filename: str) -> dict | None:
    path = COMPANIES_DIR / ticker.upper() / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _refinancing_exposure(fin: dict) -> int | None:
    """Ф8 кодом (методика §3.2, произвол): ND/EBITDA>3 и короткий долг>30%→-2;
    ND/EBITDA>2 или короткий долг>30%→-1; иначе 0; чистый кэш→+1."""
    bal = fin.get("balance_sheet") or {}
    ratios = bal.get("ratios") or {}
    nd_ebitda_series = ratios.get("net_debt_ebitda") or []
    nd_ebitda = next((v for v in reversed(nd_ebitda_series) if v is not None), None)
    st = bal.get("short_term_debt") or []
    lt = bal.get("long_term_debt") or []
    st_last = next((v for v in reversed(st) if v is not None), None)
    lt_last = next((v for v in reversed(lt) if v is not None), None)
    short_ratio = None
    if st_last is not None and lt_last is not None and (st_last + lt_last) > 0:
        short_ratio = st_last / (st_last + lt_last)
    if nd_ebitda is None and short_ratio is None:
        return None
    nd_ebitda = nd_ebitda if nd_ebitda is not None else 0
    short_ratio = short_ratio if short_ratio is not None else 0
    if nd_ebitda < 0:  # чистый кэш
        return 1
    if nd_ebitda > 3 and short_ratio > 0.30:
        return -2
    if nd_ebitda > 2 or short_ratio > 0.30:
        return -1
    return 0


def get_company_exposures(ticker: str) -> dict:
    """{factor_key: exposure(-2..2) или None (дыра — компания непокрыта по фактору)}."""
    exposures: dict[str, list[int]] = {k: [] for k in FACTOR_KEYS}

    macro = _load_json(ticker, "macro.json")
    if macro:
        for f in macro.get("factors") or []:
            key = _MACRO_TYPE_MAP.get(f.get("type"))
            sign = _SIGN_MAP.get(f.get("effect_sign"))
            if key and sign is not None:
                exposures[key].append(sign)

    geo = _load_json(ticker, "geo.json")
    if geo:
        for f in geo.get("factors") or []:
            key = _GEO_TYPE_MAP.get(f.get("type"))
            sign = _SIGN_MAP.get(f.get("effect_sign"))
            if key and sign is not None:
                exposures[key].append(sign)

    fin = _load_json(ticker, "financials.json")
    refinancing = _refinancing_exposure(fin) if fin else None

    out: dict[str, float | None] = {}
    for k in FACTOR_KEYS:
        if k == "refinancing":
            out[k] = refinancing
            continue
        vals = exposures[k]
        out[k] = round(sum(vals) / len(vals), 2) if vals else None
    return out


def get_portfolio_exposures(tickers_weights: dict[str, float]) -> dict:
    """Exp(p,k) = Σ wᵢ·Exp(i,k). Дыры (компания не покрыта по фактору) не
    участвуют в сумме для ЭТОГО фактора — вес перенормируется на покрытую
    часть (честная деградация, а не молчаливый ноль)."""
    tot_w = sum(tickers_weights.values())
    if tot_w <= 0:
        return {k: None for k in FACTOR_KEYS}
    per_company = {t: get_company_exposures(t) for t in tickers_weights}
    out: dict[str, float | None] = {}
    coverage: dict[str, float] = {}
    for k in FACTOR_KEYS:
        num, den = 0.0, 0.0
        for t, w in tickers_weights.items():
            exp = per_company.get(t, {}).get(k)
            if exp is None:
                continue
            num += w * exp
            den += w
        out[k] = round(num / den, 3) if den > 0 else None
        coverage[k] = round(den / tot_w * 100, 1) if tot_w else 0.0
    return {"exposures": out, "coverage_pct": coverage, "per_company": per_company}
