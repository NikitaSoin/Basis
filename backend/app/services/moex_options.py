"""Опционы на фьючерсы с MOEX ISS (класс «Опционы»).

Витрина УРЕЗАНА (Вариант C): по курируемым ликвидным базовым активам берём страйки
около денег (±N от центрального) ближайшей экспирации, call+put. Греки и
подразумеваемую волатильность (IV) считаем САМИ по модели Блэк-76 (опционы MOEX
маржируемые → недисконтированная форма). Методика — docs/options-methodology.md.
Запросы к MOEX — последовательно с паузами.
"""
import json
import logging
import math
import ssl
import urllib.request
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}

# Курируемые базовые активы (префикс SECID фьючерса) → человеч. имя. Урезанная
# витрина: только понятные ликвидные активы, не все 142.
UNDERLYING_NAMES = {
    "Si": "Доллар США / рубль (фьючерс)", "RI": "Индекс РТС (фьючерс)",
    "BR": "Нефть Brent (фьючерс)", "GD": "Золото (фьючерс)",
    "SR": "Сбербанк (фьючерс)", "GZ": "Газпром (фьючерс)",
    "CR": "Китайский юань (фьючерс)", "MX": "Индекс МосБиржи (фьючерс)",
}
STRIKES_EACH_SIDE = 4   # сколько страйков по каждую сторону от центрального


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=40, context=_ssl_ctx) as r:
        return json.loads(r.read())


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def black76_price(F, K, T, sigma, is_call):
    """Недисконтированная цена опциона на фьючерс (маржируемый, Блэк-76, r=0)."""
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return max(0.0, (F - K) if is_call else (K - F))
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return F * _norm_cdf(d1) - K * _norm_cdf(d2)
    return K * _norm_cdf(-d2) - F * _norm_cdf(-d1)


def implied_vol(premium, F, K, T, is_call):
    """IV бисекцией: σ такая, что модель = рыночная премия. None если не сходится."""
    if premium is None or T <= 0 or F <= 0 or K <= 0:
        return None
    intrinsic = max(0.0, (F - K) if is_call else (K - F))
    if premium <= intrinsic + 1e-9:  # нет временной стоимости → IV не извлечь
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if black76_price(F, K, T, mid, is_call) > premium:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def greeks(F, K, T, sigma, is_call):
    """delta, vega(на 1% IV), theta(в день) — Блэк-76 недисконтированный."""
    if T <= 0 or sigma <= 0 or F <= 0 or K <= 0:
        return None, None, None
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    delta = _norm_cdf(d1) if is_call else _norm_cdf(d1) - 1
    vega = F * _norm_pdf(d1) * math.sqrt(T) / 100  # на 1% изменения IV
    # тета численно: цена сегодня минус цена завтра (распад за 1 день)
    dt = 1 / 365
    theta_day = black76_price(F, K, max(T - dt, 1e-9), sigma, is_call) - black76_price(F, K, T, sigma, is_call)
    return delta, vega, theta_day


def fetch_underlying_price(sec: str) -> float | None:
    """Цена фьючерса-базового актива (LAST/SETTLE)."""
    try:
        d = _get(f"https://iss.moex.com/iss/engines/futures/markets/forts/securities/{sec}.json"
                 f"?iss.meta=off&iss.only=marketdata,securities&marketdata.columns=SECID,LAST,SETTLEPRICE"
                 f"&securities.columns=SECID,PREVSETTLEPRICE")
        md = d["marketdata"]["data"]
        if md and md[0]:
            last = md[0][1] or md[0][2]
            if last:
                return float(last)
        sc = d["securities"]["data"]
        if sc and sc[0] and sc[0][1]:
            return float(sc[0][1])
    except Exception as e:
        logger.warning("цена БА %s недоступна: %s", sec, e)
    return None


def fetch_option_chain() -> list[dict]:
    """Все опционы; фильтруем по курируемым БА в loader-е."""
    d = _get("https://iss.moex.com/iss/engines/futures/markets/options/securities.json"
             "?iss.meta=off&iss.only=securities&securities.columns="
             "SECID,SHORTNAME,STRIKE,OPTIONTYPE,UNDERLYINGASSET,LASTTRADEDATE,CENTRALSTRIKE,PREVSETTLEPRICE")
    cols = d["securities"]["columns"]
    return [dict(zip(cols, r)) for r in d["securities"]["data"]]


_UPSERT = text("""
    INSERT INTO options (secid, short_name, option_type, strike, central_strike, expiration_date,
        underlying, underlying_price, asset_code, asset_name, premium, intrinsic_value, time_value,
        breakeven, iv, delta, theta_day, vega, updated_at)
    VALUES (:secid, :short_name, :option_type, :strike, :central_strike, :expiration_date,
        :underlying, :underlying_price, :asset_code, :asset_name, :premium, :intrinsic_value, :time_value,
        :breakeven, :iv, :delta, :theta_day, :vega, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        short_name=EXCLUDED.short_name, strike=EXCLUDED.strike, central_strike=EXCLUDED.central_strike,
        expiration_date=EXCLUDED.expiration_date, underlying=EXCLUDED.underlying,
        underlying_price=EXCLUDED.underlying_price, asset_code=EXCLUDED.asset_code,
        asset_name=EXCLUDED.asset_name, premium=EXCLUDED.premium, intrinsic_value=EXCLUDED.intrinsic_value,
        time_value=EXCLUDED.time_value, breakeven=EXCLUDED.breakeven, iv=EXCLUDED.iv, delta=EXCLUDED.delta,
        theta_day=EXCLUDED.theta_day, vega=EXCLUDED.vega, updated_at=EXCLUDED.updated_at
""")


def _asset_prefix(underlying: str) -> str | None:
    """Префикс кода базового актива из SECID фьючерса (Si из SiU6, RI из RIU6)."""
    for p in UNDERLYING_NAMES:
        if underlying.startswith(p):
            return p
    return None


def refresh_options(db: Session) -> int:
    """Урезанная витрина опционов: курируемые БА, ближняя экспирация, страйки около денег."""
    import time as _t
    chain = fetch_option_chain()
    today = date.today()
    # сгруппировать по базовому фьючерсу, оставив только курируемые
    by_und: dict[str, list] = {}
    for o in chain:
        und = o.get("UNDERLYINGASSET") or ""
        if _asset_prefix(und):
            by_und.setdefault(und, []).append(o)

    n = 0
    for und, opts in by_und.items():
        # ближайшая будущая экспирация
        exps = sorted({o["LASTTRADEDATE"] for o in opts if o.get("LASTTRADEDATE") and o["LASTTRADEDATE"] >= today.isoformat()})
        if not exps:
            continue
        near_exp = exps[0]
        opts = [o for o in opts if o["LASTTRADEDATE"] == near_exp and o.get("STRIKE") and o.get("CENTRALSTRIKE")]
        if not opts:
            continue
        F = fetch_underlying_price(und)
        _t.sleep(0.2)
        central = opts[0]["CENTRALSTRIKE"]
        strikes = sorted({o["STRIKE"] for o in opts})
        # ближайшие к центральному ±STRIKES_EACH_SIDE
        strikes.sort(key=lambda s: abs(s - central))
        keep = set(strikes[: STRIKES_EACH_SIDE * 2 + 1])
        prefix = _asset_prefix(und)
        T = (datetime.strptime(near_exp, "%Y-%m-%d").date() - today).days / 365
        for o in opts:
            if o["STRIKE"] not in keep:
                continue
            is_call = o.get("OPTIONTYPE") == "C"
            K = float(o["STRIKE"]); premium = float(o["PREVSETTLEPRICE"]) if o.get("PREVSETTLEPRICE") not in (None, "") else None
            iv = delta = vega = theta = intrinsic = tv = breakeven = None
            if F and premium is not None:
                intrinsic = max(0.0, (F - K) if is_call else (K - F))
                tv = premium - intrinsic
                breakeven = K + premium if is_call else K - premium
                sigma = implied_vol(premium, F, K, T, is_call)
                if sigma:
                    iv = round(sigma * 100, 2)
                    delta, vega, theta = greeks(F, K, T, sigma, is_call)
            db.execute(_UPSERT, {
                "secid": o["SECID"], "short_name": o.get("SHORTNAME"), "option_type": o.get("OPTIONTYPE"),
                "strike": K, "central_strike": central, "expiration_date": near_exp,
                "underlying": und, "underlying_price": F, "asset_code": prefix,
                "asset_name": UNDERLYING_NAMES.get(prefix),
                "premium": premium, "intrinsic_value": intrinsic, "time_value": tv, "breakeven": breakeven,
                "iv": iv, "delta": round(delta, 4) if delta is not None else None,
                "theta_day": round(theta, 4) if theta is not None else None,
                "vega": round(vega, 4) if vega is not None else None,
                "updated_at": datetime.now(timezone.utc),
            })
            n += 1
        db.commit()
    logger.info("Опционы: загружено %d (урезанная витрина, курируемые БА)", n)
    return n
