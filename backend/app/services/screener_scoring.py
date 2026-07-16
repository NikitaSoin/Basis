"""Скринер акций — v0 BASIS scoring engine.

ОДИН движок питает три артефакта экрана: BASIS-балл (0–100), ориентированный
перцентиль по каждой метрике (полоски), координаты карты (Оценка × Качество).

Источники: company_metrics (P/E, дивдох, fair_value, beta, volatility) + quotes
(свежая цена) + companies/<TICKER>/financials.json (EV/EBITDA, ROE, ND/EBITDA,
EBITDA-маржа, FCF, fair_value_range, meta.profile/data_quality, anomaly_flag).

ПРИНЦИП ЧЕСТНОСТИ: данные сами помечают свою ненадёжность. Тикеры с anomaly_flag
или data_quality="low" не дают своим ИСКАЖАЮЩИМ оценочным метрикам (P/E, EV/EBITDA,
ND/EBITDA) попасть ни в свой балл, ни в распределение вселенной (иначе ВТБ/Сургут/
ЛУКОЙЛ всплывут «самыми дешёвыми»). Метрика null → выкидывается из субиндекса
(не штраф нулём). Мало валидных субиндексов → BASIS помечается low-confidence.

v0 / предварительная методика: считается из ФИНАНСОВЫХ метрик. Качественные
направления (бизнес-модель, управление, рынок, макро, геополитика) — будущая ось.
"""
from __future__ import annotations
import json
import os
import threading
import time
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.live_multiples import live_scale_multiples

COMPANIES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "companies")

# ─────────── КОНФИГ (продуктовые ручки владельца — менять здесь, не по месту) ───────────
CONFIG = {
    "weights": {"quality": 0.40, "value": 0.35, "stability": 0.25},  # BASIS = Σ wᵢ·субиндекс
    "div_yield_cap": 18.0,        # кэп дивдоходности (выше — не «лучше», а риск/разовое)
    "min_subindices": 2,          # < этого валидных субиндексов → low-confidence
    "subindices": {
        "value":     ["upside", "pe", "ev_ebitda", "div_yield"],
        "quality":   ["roe", "ebitda_margin", "fcf_yield"],
        "stability": ["nd_ebitda", "beta", "volatility"],
    },
    # метрики, где МЕНЬШЕ = выгоднее → перцентиль инвертируется
    "invert": {"pe", "ev_ebitda", "nd_ebitda", "beta", "volatility"},
    # метрики, искажаемые корп-эффектами → выкидываются у anomaly/low-dq тикеров
    "distortion_prone": {"pe", "ev_ebitda", "nd_ebitda"},
}

_CACHE = {"ts": 0.0, "fin": None}
_CACHE_TTL = 600  # сек; financials.json меняются только при деплое
_RESULT_CACHE = {}   # (universe, sector) -> (ts, result) — чтобы ответ был мгновенным
_RESULT_TTL = 3600   # 1ч: пересчёт (тяжёлый, морозит 1-CPU) делаем редко; данные меняются при деплое
_bg_lock = threading.Lock()
_bg_running: set = set()   # ключи, по которым уже идёт фоновый пересчёт (single-flight)

# Эшелоны (МосБиржа официальный список «эшелонов» не публикует — это неформальная
# классификация по ликвидности). 1-й эшелон = голубые фишки = состав индекса MOEXBC
# (15 крупнейших, проверено на moex.com/smart-lab). 2-й/3-й — по капитализации/ликвидности.
BLUE_CHIPS = {"SBER", "LKOH", "GAZP", "YDEX", "T", "TATN", "GMKN", "NVTK",
              "PLZL", "OZON", "VTBR", "X5", "ROSN", "SNGS", "MOEX"}
ECHELON2_SIZE = 50  # следующие по капитализации после голубых фишек


def _last(x):
    if isinstance(x, list):
        for v in reversed(x):
            if v is not None:
                return v
        return None
    return x


def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN-guard
    except (TypeError, ValueError):
        return None


def _load_financials() -> dict:
    """Парсит все companies/<T>/financials.json (с кэшем по TTL)."""
    now = time.time()
    if _CACHE["fin"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["fin"]
    out = {}
    base = os.path.abspath(COMPANIES_DIR)
    if os.path.isdir(base):
        for t in os.listdir(base):
            fp = os.path.join(base, t, "financials.json")
            if not os.path.isfile(fp):
                continue
            try:
                out[t.upper()] = json.load(open(fp, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
    _CACHE["fin"] = out
    _CACHE["ts"] = now
    return out


def _extract_raw(ticker, fin, cm, price, market_cap, shares_outstanding):
    """Сырые метрики тикера + флаги достоверности. cm — строка company_metrics (dict)."""
    j = fin.get(ticker.upper()) or {}
    meta = j.get("meta") or {}
    profile = meta.get("profile") or "standard"
    dq = meta.get("data_quality")
    anomaly = bool(j.get("anomaly_flag"))
    suspect = anomaly or dq == "low"   # искажающие оценочные метрики не учитываем

    fr = ((j.get("valuation") or {}).get("fair_value_range") or {})
    # P/E и EV/EBITDA — от ЖИВОЙ капы (тот же live_scale_multiples, что и карточка
    # компании), а не застывший снимок аналитика на дату его прогона.
    cur = live_scale_multiples(j, market_cap, shares_outstanding)
    ret = j.get("returns") or {}
    rat = ((j.get("balance_sheet") or {}).get("ratios") or {})
    marg = ((j.get("income_statement") or {}).get("margins") or {})
    cf = j.get("cash_flow") or {}
    bank_m = j.get("bank_metrics") or {}

    fair_base = _num(fr.get("base"))
    upside = ((fair_base - price) / price * 100.0) if (fair_base and price) else None
    fcf = _num(_last(cf.get("fcf")))
    # financials в млн → в рубли; market_cap в рублях
    fcf_yield = (fcf * 1e6 / market_cap * 100.0) if (fcf is not None and market_cap) else None

    # ROE: у банков (profile=bank) свой блок статей — bank_pnl/bank_balance/
    # bank_metrics, СОВСЕМ другая форма, без стандартного returns.roe (там пусто).
    # Реальный ROE у части банков лежит в bank_metrics.roe_adj_pct/roe_rep_pct —
    # без этого фолбэка банки со свежим форматом (T, MBNK, PRMB) молча выпадали
    # из ROE-фильтров скринера, хотя в их же карточке ROE показан.
    roe = _num(_last(ret.get("roe")))
    if roe is None:
        roe = _num(_last(bank_m.get("roe_adj_pct")))
    if roe is None:
        roe = _num(_last(bank_m.get("roe_rep_pct")))

    raw = {
        "upside": upside,
        "pe": _num(cur.get("pe")) or _num(cm.get("pe_current")),
        "ev_ebitda": _num(cur.get("ev_ebitda")),
        "div_yield": _num(cm.get("div_yield")),
        "roe": roe,
        # 🔴 2026-07-17: было marg.get("ebitda") — реальное поле в financials.json
        # называется margins.ebitda_margin (проверено на LKOH/SBER), не margins.ebitda.
        # Метрика молча была None у ВСЕХ 261 компаний — субиндекс «Качество» (roe+
        # ebitda_margin+fcf_yield) считался только по 2 из 3 метрик с момента запуска
        # скринера. Найдено при сборке «Подборки портфелей», не тронуто по касательной —
        # это реальный баг в уже боевом BASIS-скоринге, не только в новой фиче.
        "ebitda_margin": _num(_last(marg.get("ebitda_margin"))),
        "fcf_yield": fcf_yield,
        "nd_ebitda": _num(_last(rat.get("net_debt_ebitda"))),
        "beta": _num(cm.get("beta")),
        "volatility": _num(cm.get("volatility")),
    }
    if raw["div_yield"] is not None:
        raw["div_yield"] = min(raw["div_yield"], CONFIG["div_yield_cap"])
    return raw, profile, dq, anomaly, suspect, fair_base


def _valid_for_pool(metric, raw, suspect):
    """Значение метрики, допустимое в распределение вселенной (или None — выкинуть)."""
    v = raw.get(metric)
    if v is None:
        return None
    if suspect and metric in CONFIG["distortion_prone"]:
        return None  # искажённое оценочное число не пускаем ни в пул, ни в свой балл
    return v


def _percentiles(values_by_ticker, invert):
    """{ticker: percentile 0–100}, ориентированный «выше=выгоднее»."""
    pairs = [(t, v) for t, v in values_by_ticker.items() if v is not None]
    if len(pairs) < 2:
        return {t: 50.0 for t, _ in pairs}
    pairs.sort(key=lambda p: p[1])  # по возрастанию value
    n = len(pairs)
    out = {}
    for i, (t, _) in enumerate(pairs):
        pct = i / (n - 1) * 100.0           # низкое value → низкий перцентиль
        out[t] = (100.0 - pct) if invert else pct
    return out


def score_universe(db: Session, universe: str = "all", sector: str | None = None) -> dict:
    """Отдаёт кэш мгновенно. Свежий → сразу; устаревший → старое + пересчёт в ФОНЕ
    (single-flight), чтобы запрос НИКОГДА не упирался в таймаут воркера/шлюза;
    холодный кэш → синхронный расчёт (старт прогревается warm_cache)."""
    key = (universe, sector or "")
    cached = _RESULT_CACHE.get(key)
    if cached:
        if (time.time() - cached[0]) < _RESULT_TTL:
            return cached[1]
        _spawn_bg_recompute(key, universe, sector)  # stale-while-revalidate
        return cached[1]
    return _compute_universe(db, universe, sector)


def _spawn_bg_recompute(key, universe: str, sector: str | None) -> None:
    with _bg_lock:
        if key in _bg_running:
            return
        _bg_running.add(key)

    def _run():
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            _compute_universe(db, universe, sector)
        except Exception:  # noqa: BLE001
            pass
        finally:
            db.close()
            with _bg_lock:
                _bg_running.discard(key)

    threading.Thread(target=_run, daemon=True).start()


def _compute_universe(db: Session, universe: str = "all", sector: str | None = None) -> dict:
    """Тяжёлый расчёт набора (без кэш-логики). Пишет результат в _RESULT_CACHE."""
    key = (universe, sector or "")
    now = time.time()
    fin = _load_financials()

    # компании + свежая цена + капитализация + число акций (для live-пересчёта мультипликаторов)
    rows = db.execute(text("""
        WITH latest AS (SELECT DISTINCT ON (company_id) company_id, close FROM quotes ORDER BY company_id, date DESC)
        SELECT c.ticker, c.name, c.sector, c.market_cap, c.shares_outstanding, l.close AS price
        FROM companies c LEFT JOIN latest l ON l.company_id = c.id
    """)).fetchall()
    metrics_rows = {r._mapping["ticker"]: dict(r._mapping)
                    for r in db.execute(text("SELECT * FROM company_metrics"))}

    base = []
    for r in rows:
        d = dict(r._mapping)
        t = d["ticker"]
        price = _num(d.get("price"))
        mcap = _num(d.get("market_cap"))
        shares = _num(d.get("shares_outstanding"))
        cm = metrics_rows.get(t, {})
        # только акции с метриками (есть строка company_metrics) и ценой
        if t not in metrics_rows or price is None:
            continue
        raw, profile, dq, anomaly, suspect, fair = _extract_raw(t, fin, cm, price, mcap, shares)
        base.append({"ticker": t, "name": d.get("name"), "sector": d.get("sector"),
                     "profile": profile, "data_quality": dq, "anomaly": anomaly,
                     "suspect": suspect, "price": price, "market_cap": mcap,
                     "fair_value": fair, "raw": raw})

    # ── фильтр вселенной ──
    if sector:
        base = [b for b in base if b["sector"] == sector]
    # Эшелоны: 1-й = голубые фишки (MOEXBC); 2-й = следующие по капитализации; 3-й = остальные.
    ranked = sorted([b for b in base if b["market_cap"]], key=lambda b: -b["market_cap"])
    rest = [b for b in ranked if b["ticker"] not in BLUE_CHIPS]
    if universe in ("blue", "echelon1"):
        sel = set(b["ticker"] for b in base if b["ticker"] in BLUE_CHIPS)
    elif universe == "echelon2":
        sel = set(b["ticker"] for b in rest[:ECHELON2_SIZE])
    elif universe == "echelon3":
        sel = set(b["ticker"] for b in rest[ECHELON2_SIZE:])
    elif universe in ("liquid", "midcap"):  # legacy-совместимость со старым фронтом
        n = 5 if universe == "liquid" else 45
        sel = {b["ticker"] for b in base if b["ticker"] in BLUE_CHIPS} | {b["ticker"] for b in rest[:n]}
    else:  # all (по умолчанию)
        sel = set(b["ticker"] for b in base)
    uni = [b for b in base if b["ticker"] in sel]

    all_metrics = set().union(*CONFIG["subindices"].values())

    # ── распределения по метрикам (чистый пул) + перцентили ──
    distributions = {}
    pct_by_metric = {}
    for m in all_metrics:
        pool = {b["ticker"]: _valid_for_pool(m, b["raw"], b["suspect"]) for b in uni}
        distributions[m] = sorted([v for v in pool.values() if v is not None])
        pct_by_metric[m] = _percentiles(pool, invert=(m in CONFIG["invert"]))

    # ── субиндексы + BASIS ──
    W = CONFIG["weights"]
    for b in uni:
        pcts = {}
        sub = {}
        for sname, mlist in CONFIG["subindices"].items():
            vals = [pct_by_metric[m].get(b["ticker"]) for m in mlist]
            vals = [v for v in vals if v is not None]
            for m in mlist:
                p = pct_by_metric[m].get(b["ticker"])
                if p is not None:
                    pcts[m] = round(p, 1)
            sub[sname] = round(sum(vals) / len(vals), 1) if vals else None
        avail = {k: v for k, v in sub.items() if v is not None}
        if avail:
            wsum = sum(W[k] for k in avail)
            basis = round(sum(W[k] * v for k, v in avail.items()) / wsum)
        else:
            basis = None
        low_conf = (len(avail) < CONFIG["min_subindices"]) or b["suspect"] or basis is None
        b["percentiles"] = pcts
        b["subindices"] = sub
        b["basis"] = basis
        b["low_confidence"] = bool(low_conf)
        b["reduced_set"] = b["profile"] == "bank"
        b["map"] = {"x": sub.get("value"), "y": sub.get("quality")}

    out_rows = []
    for b in sorted(uni, key=lambda b: (b["basis"] is None, -(b["basis"] or 0))):
        out_rows.append({
            "ticker": b["ticker"], "name": b["name"], "sector": b["sector"],
            "profile": b["profile"], "data_quality": b["data_quality"], "anomaly": b["anomaly"],
            "price": round(b["price"], 4) if b["price"] else None,
            "market_cap": b["market_cap"], "fair_value": b["fair_value"],
            "raw": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in b["raw"].items()},
            "percentiles": b["percentiles"], "subindices": b["subindices"],
            "basis": b["basis"], "low_confidence": b["low_confidence"],
            "reduced_set": b["reduced_set"], "map": b["map"],
        })

    result = {
        "universe": {"key": universe, "sector": sector, "count": len(out_rows), "total": len(base)},
        "config": {"weights": W, "div_yield_cap": CONFIG["div_yield_cap"],
                   "subindices": CONFIG["subindices"], "version": "v0"},
        "rows": out_rows,
        "distributions": distributions,
    }
    _RESULT_CACHE[key] = (now, result)
    return result


def warm_cache():
    """Прогрев кеша скоринга для основных наборов (фоном при старте), чтобы первый
    пользовательский запрос не упирался в тяжёлый расчёт/таймаут воркера."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        for u in ("all", "blue", "echelon2", "echelon3"):
            try:
                score_universe(db, universe=u)
            except Exception:  # noqa: BLE001
                pass
    finally:
        db.close()
