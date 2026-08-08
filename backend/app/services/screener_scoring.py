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
import logging
import os
import threading
import time
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.live_multiples import live_scale_multiples
from app.services.units import last_to_percent

logger = logging.getLogger(__name__)

COMPANIES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "companies")

# ─────────── КОНФИГ (продуктовые ручки владельца — менять здесь, не по месту) ───────────
# v1 (владелец 2026-08-08): BASIS — КОМПЛЕКСНАЯ метрика, а не чисто финансовая.
# Новая ось «Среда» (context): корпуправление + институты (IRI) + геобезопасность
# (инвертированный GRE) — «плохо, что какой-то Займер имеет высокий балл, а
# Яндекс низкий»: дешёвые мелкие бумаги больше не выигрывают на одних коэффициентах.
# Плюс рост (CAGR выручки/прибыли 3 года) и банковские метрики качества
# (NIM/CoR/CIR — пулы только из банков, т.е. пир-сравнение), размер — в устойчивость.
CONFIG = {
    "weights": {"quality": 0.30, "value": 0.25, "stability": 0.15, "context": 0.30},
    "div_yield_cap": 18.0,        # кэп дивдоходности (выше — не «лучше», а риск/разовое)
    "min_subindices": 2,          # < этого валидных субиндексов → low-confidence
    "subindices": {
        "value":     ["upside", "pe", "ev_ebitda", "div_yield"],
        "quality":   ["roe", "ebitda_margin", "fcf_yield", "growth", "nim", "cost_of_risk", "cir"],
        "stability": ["nd_ebitda", "beta", "volatility"],
        "context":   ["governance", "iri", "gre", "size", "biz_quality"],
    },
    # метрики, где МЕНЬШЕ = выгоднее → перцентиль инвертируется
    "invert": {"pe", "ev_ebitda", "nd_ebitda", "beta", "volatility", "cost_of_risk", "cir", "gre"},
    # метрики, искажаемые корп-эффектами → выкидываются у anomaly/low-dq тикеров
    "distortion_prone": {"pe", "ev_ebitda", "nd_ebitda"},
    # метрики вне BASIS-балла (v0 — финансовый), но с распределением/фильтром на фронте:
    # балл корпуправления (governance.json → scoring.overall_score, 1–5)
    "extra_metrics": {"governance"},
}

_CACHE = {"ts": 0.0, "fin": None, "gov_ts": 0.0, "gov": None}
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


_QUAL_CACHE: dict = {"ts": 0.0, "data": None}


def _load_qual_scores() -> dict:
    """{TICKER: {"governance": 1-5, "iri": 1-5, "gre": среднее 0-5}} из карточек
    (кэш 1ч). Направления: governance/IRI выше=лучше; GRE выше=БОЛЬШЕ гео-риска
    (инвертируется конфигом). Покрытие всех трёх — 264/264 (проверено 2026-08-08)."""
    now = time.time()
    if _QUAL_CACHE["data"] is not None and (now - _QUAL_CACHE["ts"]) < _CACHE_TTL:
        return _QUAL_CACHE["data"]
    out: dict = {}
    base = os.path.abspath(COMPANIES_DIR)
    if os.path.isdir(base):
        for t in os.listdir(base):
            d = os.path.join(base, t)
            if not os.path.isdir(d):
                continue
            row: dict = {}
            try:
                g = json.load(open(os.path.join(d, "governance.json"), encoding="utf-8"))
                v = _num(((g.get("scoring") or {}).get("overall_score")))
                if v is not None and 1.0 <= v <= 5.0:
                    row["governance"] = v
            except Exception:  # noqa: BLE001
                pass
            try:
                i = json.load(open(os.path.join(d, "institutions.json"), encoding="utf-8"))
                v = _num((i.get("iri_scoring") or {}).get("overall"))
                if v is not None and 1.0 <= v <= 5.0:
                    row["iri"] = v
            except Exception:  # noqa: BLE001
                pass
            try:
                geo = json.load(open(os.path.join(d, "geo.json"), encoding="utf-8"))
                scores = [_num(e.get("score")) for e in (geo.get("gre_profile") or [])
                          if isinstance(e, dict)]
                scores = [v for v in scores if v is not None]
                if scores:
                    row["gre"] = round(sum(scores) / len(scores), 2)
            except Exception:  # noqa: BLE001
                pass
            try:
                q = json.load(open(os.path.join(d, "quality_scores.json"), encoding="utf-8"))
                parts = [_num((q.get(k) or {}).get("score")) for k in ("bm", "mp", "ca")]
                parts = [v for v in parts if v is not None]
                if parts:
                    row["biz_quality"] = round(sum(parts) / len(parts), 1)  # 0–100
            except Exception:  # noqa: BLE001
                pass
            if row:
                out[t.upper()] = row
    _QUAL_CACHE["data"] = out
    _QUAL_CACHE["ts"] = now
    return out


def _load_gov_scores() -> dict:
    """{TICKER: overall_score 1–5} из companies/<T>/governance.json (кэш по TTL).
    Читаем только scoring.overall_score — файл большой, остальное скринеру не нужно."""
    now = time.time()
    if _CACHE["gov"] is not None and (now - _CACHE["gov_ts"]) < _CACHE_TTL:
        return _CACHE["gov"]
    out = {}
    base = os.path.abspath(COMPANIES_DIR)
    if os.path.isdir(base):
        for t in os.listdir(base):
            fp = os.path.join(base, t, "governance.json")
            if not os.path.isfile(fp):
                continue
            try:
                score = ((json.load(open(fp, encoding="utf-8")) or {})
                         .get("scoring") or {}).get("overall_score")
                v = _num(score)
                if v is not None and 1.0 <= v <= 5.0:
                    out[t.upper()] = v
            except Exception:  # noqa: BLE001
                continue
    _CACHE["gov"] = out
    _CACHE["gov_ts"] = now
    return out


def _cagr_pct(seq, points: int = 3):
    """CAGR по последним `points` годовым значениям, %. Только по положительным
    крайним точкам (отрицательная выручка/прибыль в крайней точке — не CAGR)."""
    if not isinstance(seq, list):
        return None
    vals = [v for v in seq[-points:] if isinstance(v, (int, float))]
    if len(vals) < 2 or vals[0] is None or vals[-1] is None:
        return None
    if vals[0] <= 0 or vals[-1] <= 0:
        return None
    n = len(vals) - 1
    try:
        return round(((vals[-1] / vals[0]) ** (1.0 / n) - 1.0) * 100.0, 2)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


# алиасы банковских метрик — имена в файлах разнятся (SBER: nim; T: nim_pct)
_BANK_METRIC_ALIASES = {
    "nim": ("nim", "nim_pct"),
    "cost_of_risk": ("cost_of_risk", "cor_pct"),
    "cir": ("cir", "cir_pct"),
}


def _extract_raw(ticker, fin, cm, price, market_cap, shares_outstanding, fv_entry=None,
                 db=None, prices=None, gov_scores=None, qual_scores=None):
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
    # 🔴 Капитализация — по ВСЕМ классам акций эмитента (share_capital.py), иначе в
    # скрининге у TRNFP/VTBR/BSPBP стоят P/E ~1 и они всплывают в топ «дешёвых» по
    # чисто счётной причине. Кэш _load_financials общий на все тикеры, поэтому НЕ
    # мутируем j: берём поправку и отдаём её в live_scale_multiples отдельным числом.
    cap = None
    if db is not None:
        try:
            from app.services.share_capital import issuer_capital
            cap = issuer_capital(db, ticker, j, prices=prices)
        except Exception:  # noqa: BLE001 — скринер не должен падать из-за поправки
            cap = None
    if cap:
        cur = live_scale_multiples(j, cap["mcap_live"], cap["shares_used"])
        market_cap = cap["mcap_live"]
    else:
        cur = live_scale_multiples(j, market_cap, shares_outstanding)
    ret = j.get("returns") or {}
    rat = ((j.get("balance_sheet") or {}).get("ratios") or {})
    marg = ((j.get("income_statement") or {}).get("margins") or {})
    cf = j.get("cash_flow") or {}
    bank_m = j.get("bank_metrics") or {}

    # Справедливая цена — из единого аксессора (app/services/fair_value.py): методика
    # Basis (BFV), с фолбэком на оценку аналитика, когда движок не посчитал или не прошёл
    # санити-гейт. Владелец 2026-07-30: «везде на платформе — наша новая методика».
    # fr.get("base") остаётся страховкой, если аксессор почему-то не отдал запись.
    fair_base = _num((fv_entry or {}).get("fair_price"))
    fair_source = (fv_entry or {}).get("source")
    if fair_base is None:
        fair_base = _num(fr.get("base"))
        fair_source = "analyst" if fair_base is not None else None
    upside = _num((fv_entry or {}).get("upside_pct"))
    if upside is None:
        upside = ((fair_base - price) / price * 100.0) if (fair_base and price) else None
    fcf = _num(_last(cf.get("fcf")))
    # financials в млн → в рубли; market_cap в рублях
    fcf_yield = (fcf * 1e6 / market_cap * 100.0) if (fcf is not None and market_cap) else None

    # ROE: у банков (profile=bank) свой блок статей — bank_pnl/bank_balance/
    # bank_metrics, СОВСЕМ другая форма, без стандартного returns.roe (там пусто).
    # Реальный ROE у части банков лежит в bank_metrics.roe_adj_pct/roe_rep_pct —
    # без этого фолбэка банки со свежим форматом (T, MBNK, PRMB) молча выпадали
    # из ROE-фильтров скринера, хотя в их же карточке ROE показан.
    # 🔴 2026-07-31: единицы ROE в financials.json СМЕШАНЫ — у 31 компании доли
    # (0.0577), у 185 проценты (11.19). Без приведения «Качество» видело у них ROE
    # ≈ 0 и роняло в самый низ рейтинга при реальных 5,77 %. Тот же класс дефекта,
    # что margins.ebitda_margin строкой ниже: не падает, просто молча врёт.
    roe = last_to_percent(j, "roe", ret.get("roe"))
    if roe is None:
        roe = _num(_last(bank_m.get("roe_adj_pct")))   # у банков поле уже в процентах (_pct)
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
        "governance": (gov_scores or {}).get(ticker.upper()),
    }
    # v1: рост — CAGR выручки за 3 года (банки: чистая прибыль из bank_pnl —
    # стандартной выручки у них нет)
    inc = j.get("income_statement") or {}
    bp = j.get("bank_pnl") or {}
    raw["growth"] = _cagr_pct(inc.get("revenue")) if profile != "bank" else _cagr_pct(bp.get("net_profit"))
    # v1: банковское качество — пулы формируются только из банков (пир-сравнение);
    # у небанков None → метрика просто выпадает из их субиндекса
    bm_ = j.get("bank_metrics") or {}
    for canon, names in _BANK_METRIC_ALIASES.items():
        v = None
        if profile == "bank" or bm_:
            for nm in names:
                v = _num(_last(bm_.get(nm)))
                if v is not None:
                    break
        raw[canon] = v
    # v1: размер (капитализация) — в устойчивость: перцентиль по рангу, сами
    # рубли в балл не попадают
    raw["size"] = _num(market_cap)
    # v1: качественная ось «Среда» — корпуправление уже в raw, добавляем
    # институты (IRI, выше=лучше) и гео-экспозицию (GRE, выше=риск, инверсия конфигом)
    qrow = (qual_scores or {}).get(ticker.upper()) or {}
    raw["iri"] = qrow.get("iri")
    raw["gre"] = qrow.get("gre")
    # качество бизнеса (BM/MP/CA, 0–100) — покрытие пока частичное (раскатка
    # quality-scorer идёт), у остальных метрика честно выпадает из оси
    raw["biz_quality"] = qrow.get("biz_quality")
    if raw["div_yield"] is not None:
        raw["div_yield"] = min(raw["div_yield"], CONFIG["div_yield_cap"])
    # market_cap возвращаем ПОПРАВЛЕННЫЙ: по нему строятся эшелоны и он же
    # показывается в таблице — иначе TRNFP попал бы в третий эшелон
    return raw, profile, dq, anomaly, suspect, fair_base, fair_source, market_cap


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
    gov_scores = _load_gov_scores()
    qual_scores = _load_qual_scores()

    # компании + свежая цена + капитализация + число акций (для live-пересчёта мультипликаторов)
    rows = db.execute(text("""
        WITH latest AS (SELECT DISTINCT ON (company_id) company_id, close FROM quotes ORDER BY company_id, date DESC)
        SELECT c.ticker, c.name, c.sector, c.market_cap, c.shares_outstanding, l.close AS price
        FROM companies c LEFT JOIN latest l ON l.company_id = c.id
    """)).fetchall()
    metrics_rows = {r._mapping["ticker"]: dict(r._mapping)
                    for r in db.execute(text("SELECT * FROM company_metrics"))}
    # цены всей вселенной уже загружены выше — отдаём их в поправку капитализации,
    # чтобы она не ходила в БД по каждому тикеру отдельно
    price_map = {dict(r._mapping)["ticker"]: float(dict(r._mapping)["price"])
                 for r in rows if dict(r._mapping).get("price") is not None}

    # Справедливые цены пачкой ОДИН раз на всю вселенную: наивный вызов на тикер дал бы
    # ~265×(5 файлов + 3 SQL) на пересчёт и положил бы бэк. Внутри аксессора кривая ОФЗ,
    # барометр, цены и беты берутся по разу (app/services/fair_value.py).
    from app.services.fair_value import get_fair_values_batch
    fair_map = {}
    try:
        fair_map = get_fair_values_batch(db, [dict(r._mapping)["ticker"] for r in rows])
    except Exception:  # noqa: BLE001
        # скринер не должен падать целиком из-за движка оценки — деградируем к
        # оценкам аналитика внутри _extract_raw
        logger.warning("screener: батч справедливых цен не удался — фолбэк на analyst", exc_info=True)

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
        raw, profile, dq, anomaly, suspect, fair, fair_src, mcap = _extract_raw(
            t, fin, cm, price, mcap, shares, fair_map.get(t), db=db, prices=price_map,
            gov_scores=gov_scores, qual_scores=qual_scores)
        base.append({"ticker": t, "name": d.get("name"), "sector": d.get("sector"),
                     "profile": profile, "data_quality": dq, "anomaly": anomaly,
                     "suspect": suspect, "price": price, "market_cap": mcap,
                     "fair_value": fair, "fair_value_source": fair_src, "raw": raw})

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

    # + extra_metrics: распределение и перцентиль нужны фильтру/гистограмме на фронте,
    # в субиндексы BASIS они не входят (циклы ниже идут по CONFIG["subindices"])
    all_metrics = set().union(*CONFIG["subindices"].values()) | CONFIG["extra_metrics"]

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
            # чем посчитана цена: "bfv" — методика Basis, "analyst" — оценка аналитика
            # (движок не дал числа или оно не прошло санити-гейт). Без этого сортировка
            # по потенциалу молча смешивала бы две методики.
            "fair_value_source": b.get("fair_value_source"),
            "raw": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in b["raw"].items()},
            "percentiles": b["percentiles"], "subindices": b["subindices"],
            "basis": b["basis"], "low_confidence": b["low_confidence"],
            "reduced_set": b["reduced_set"], "map": b["map"],
        })

    result = {
        "universe": {"key": universe, "sector": sector, "count": len(out_rows), "total": len(base)},
        "config": {"weights": W, "div_yield_cap": CONFIG["div_yield_cap"],
                   "subindices": CONFIG["subindices"], "version": "v1"},
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
