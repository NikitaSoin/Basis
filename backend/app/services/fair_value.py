"""Единая точка получения справедливой цены для ВСЕЙ платформы.

Владелец, 2026-07-30: «в блоке Рынок и вообще везде на платформе (аналитика портфеля,
скринер и другие места) мы должны использовать нашу справедливую цену (по новой
методике), сейчас везде ещё старая».

Почему отдельный модуль, а не «поправить вызовы в четырёх местах»: до этого каждый
потребитель (скринер, карты рынка, портфель, карточка) сам лез в
`financials.json → valuation.fair_value_range.base`, и стоило одному переехать на BFV,
как экраны начинали показывать разные числа по одной бумаге. Ровно это и случилось на
карточке 2026-07-29 (тело «Обзора» показывало BFV, рейл рядом — analyst-base; у GAZP
выходило ▼11 % против ▲89 %). Политика «BFV → фолбэк → null», санити-гейт и батч живут
ЗДЕСЬ в одном экземпляре, потребители только зовут аксессор.

Что НЕ переведено сознательно: `portfolio_quality_v2.py` (индекс качества портфеля,
измерение RAU). Там цена входит в зафиксированную методику v2.1, и подмена движком,
который сам себя объявляет некалиброванным (§22), задним числом переписала бы индексы
всех существующих портфелей. Переводить после калибровки BFV — отдельной версией
методики. Это единственное отступление от «везде», оно зафиксировано в docs/status.md.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.bfv.compute import compute_bfv, DEFAULT_REQUIRED_SPREAD
from app.services.bfv.service import _load_json, _ofz_curve

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"
_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

# Санити-гейт. Отношение справедливой цены к рыночной вне коридора — НЕ методика и не
# «подгонка»: значение никуда не зажимается, оно целиком отвергается как недостоверное
# и заменяется оценкой аналитика. Прогон всех 265 тикеров 2026-07-30 дал 9 бумаг с
# |потенциал| ≥ 300 %: URKZ +101070 %, SGZH +10929 %, BSPBP +1350 %, VGSBP +700 %,
# UWGN +599 %, KRKOP +580 %, DATA +316 %, IGST +311 %, TRNFP +302 %. Четыре из девяти —
# префы (гипотеза: метрики обычки делятся на цену префа), причина в ДАННЫХ и чинится
# отдельно (docs/status.md). До починки такие числа не должны попадать в топ скринера:
# «потенциал +101070 %» бьёт по позиционированию «не хайп» сильнее, чем отсутствие цены.
SANITY_MIN_RATIO = 0.2   # справедливая ниже рынка более чем в 5 раз
SANITY_MAX_RATIO = 4.0   # справедливая выше рынка более чем в 4 раза (= +300 %)

# Живость цены — заявленная ценность движка (пересчёт от цены/кривой/беты), но серия
# запросов к скринеру не должна пересчитывать 265 бумаг заново. Котировки в quotes не
# обновляются чаще раза в минуту, поэтому короткий TTL ничего не «замораживает».
# Прекомпьют-кроном сознательно не делаем: у проекта уже есть история, когда фоновые
# кроны вешали БД на Timeweb.
_CACHE_TTL_SEC = 90
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _analyst_base(fin: dict) -> float | None:
    """Старая справедливая цена — та, что лежит в financials.json от аналитика."""
    fv = ((fin or {}).get("valuation") or {}).get("fair_value_range") or {}
    v = fv.get("base")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _live_prices(db: Session, tickers: list[str]) -> dict[str, float]:
    """Живые цены пачкой (DISTINCT ON) — вместо запроса на каждый тикер."""
    if not tickers:
        return {}
    try:
        rows = db.execute(text(
            "SELECT DISTINCT ON (c.ticker) c.ticker, q.close "
            "FROM quotes q JOIN companies c ON c.id = q.company_id "
            "WHERE c.ticker = ANY(:ts) AND q.close IS NOT NULL "
            "ORDER BY c.ticker, q.date DESC"), {"ts": tickers}).all()
        return {t: float(p) for t, p in rows if p is not None}
    except Exception:  # noqa: BLE001
        logger.warning("fair_value: не удалось получить живые цены пачкой", exc_info=True)
        return {}


def _live_betas(db: Session, tickers: list[str]) -> dict[str, float]:
    if not tickers:
        return {}
    try:
        rows = db.execute(text(
            "SELECT DISTINCT ON (c.ticker) c.ticker, cm.beta "
            "FROM company_metrics cm JOIN companies c ON c.id = cm.company_id "
            "WHERE c.ticker = ANY(:ts) AND cm.beta IS NOT NULL "
            "ORDER BY c.ticker, cm.updated_at DESC NULLS LAST"), {"ts": tickers}).all()
        return {t: float(b) for t, b in rows if b is not None}
    except Exception:  # noqa: BLE001
        logger.warning("fair_value: не удалось получить беты пачкой", exc_info=True)
        return {}


def _entry(fair: float | None, price: float | None, source: str,
           reliability: str | None = None, status: str = "ok") -> dict:
    upside = None
    if fair is not None and price:
        try:
            upside = (fair - price) / price * 100.0
        except ZeroDivisionError:
            upside = None
    return {"fair_price": fair, "upside_pct": upside, "source": source,
            "reliability": reliability, "status": status}


def get_fair_values_batch(db: Session, tickers: list[str],
                          required_spread: float = DEFAULT_REQUIRED_SPREAD) -> dict[str, dict]:
    """Справедливая цена пачкой: {TICKER: {fair_price, upside_pct, source, reliability, status}}.

    source: "bfv" — методика Basis (движок); "analyst" — оценка из financials.json
    (BFV не посчитался либо не прошёл санити-гейт); отсутствие ключа/None fair_price —
    цены нет вообще.

    Фолбэк на analyst сознателен: 36 бумаг из 265 (13,6 %, включая MVID) не дают BFV, и
    молча выкинуть их из фильтров по потенциалу — хуже, чем показать оценку аналитика с
    честной пометкой источника. Отличать одно от другого — задача UI (чип источника).
    """
    tickers = [t.upper() for t in tickers if t]
    if not tickers:
        return {}

    now = time.time()
    out: dict[str, dict] = {}
    todo: list[str] = []
    with _cache_lock:
        for t in tickers:
            hit = _cache.get(t)
            if hit and now - hit[0] < _CACHE_TTL_SEC:
                out[t] = hit[1]
            else:
                todo.append(t)
    if not todo:
        return out

    # общие для всех тикеров входы — один раз на батч, а не на бумагу
    curve = _ofz_curve(db)
    barometer = _load_json(_CONFIG_DIR / "geo_barometer.json")
    prices = _live_prices(db, todo)
    betas = _live_betas(db, todo)

    computed: dict[str, dict] = {}
    for t in todo:
        cdir = COMPANIES_DIR / t
        fin = _load_json(cdir / "financials.json")
        if not fin:
            computed[t] = _entry(None, prices.get(t), "none", status="no_data")
            continue
        price = prices.get(t) or (fin.get("meta") or {}).get("last_price")
        base = _analyst_base(fin)
        try:
            res = compute_bfv(
                fin,
                _load_json(cdir / "governance.json"),
                _load_json(cdir / "institutions.json"),
                barometer,
                market=_load_json(cdir / "market.json"),
                shares_outstanding=(fin.get("meta") or {}).get("shares_outstanding"),
                live_price=price,
                ofz_curve=curve,
                beta=betas.get(t),
                required_spread=required_spread,
                overrides=_load_json(cdir / "bfv_overrides.json") or None,
            ) or {}
        except Exception:  # noqa: BLE001
            logger.warning("fair_value: BFV упал на %s — фолбэк на оценку аналитика", t, exc_info=True)
            res = {}

        fair = res.get("fair_price") if res.get("status") == "ok" else None
        if isinstance(fair, (int, float)) and price and fair > 0:
            ratio = fair / price
            if SANITY_MIN_RATIO <= ratio <= SANITY_MAX_RATIO:
                computed[t] = _entry(float(fair), price, "bfv", res.get("reliability"))
                continue
            logger.info("fair_value: %s отвергнут санити-гейтом (fair/price=%.1f) — фолбэк", t, ratio)
        computed[t] = (_entry(base, price, "analyst") if base is not None
                       else _entry(None, price, "none", status="no_data"))

    with _cache_lock:
        for t, v in computed.items():
            _cache[t] = (now, v)
    out.update(computed)
    return out


def get_fair_value(db: Session, ticker: str,
                   required_spread: float = DEFAULT_REQUIRED_SPREAD) -> dict:
    """Одна бумага — тот же контракт, что и батч."""
    return get_fair_values_batch(db, [ticker], required_spread).get(ticker.upper()) \
        or _entry(None, None, "none", status="no_data")
