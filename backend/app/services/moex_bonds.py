"""Облигации с MOEX ISS (класс активов «Облигации»).

Список и параметры:
  /iss/engines/stock/markets/bonds/boards/{BOARD}/securities.json
  блоки securities (параметры выпуска) + marketdata (YTM, дюрация, цена).
Боард: TQOB — ОФЗ, TQCB — корпоративные (рынок T+, основной режим).

Оценка надёжности (НАШ подход, методика — docs/bonds-methodology.md):
  агентских рейтингов в ISS нет, поэтому за ночной срез риск-тир оцениваем по
  СПРЕДУ YTM к кривой ОФЗ (G-curve/ZCYC) той же дюрации:
    ОФЗ              → gov          (госдолг, риск дефолта минимальный)
    спред  < 250 б.п.→ high         (надёжный корпорат)
    250–600 б.п.     → medium       (средний риск)
    > 600 б.п.       → speculative  (ВДО — высокая доходность как плата за риск)
  Это ОЦЕНКА, не агентский рейтинг — помечаем в карточке. Реальные рейтинги
  АКРА/Эксперт РА — следующий шаг (ОК владельца).
"""
import json
import logging
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

BONDS_URL = ("https://iss.moex.com/iss/engines/stock/markets/bonds/boards/{board}/securities.json"
             "?iss.meta=off&iss.only=securities,marketdata"
             "&securities.columns=SECID,SHORTNAME,ISIN,MATDATE,OFFERDATE,COUPONVALUE,COUPONPERCENT,"
             "COUPONPERIOD,FACEVALUE,FACEUNIT,ACCRUEDINT,LOTSIZE,LISTLEVEL,SECTYPE,EMITENT_TITLE"
             "&marketdata.columns=SECID,LAST,LCURRENTPRICE,YIELD,DURATION")
ZCYC_URL = "https://iss.moex.com/iss/engines/stock/zcyc.json?iss.meta=off&iss.only=yearyields"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as r:
        return json.loads(r.read())


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _d(v):
    try:
        return datetime.strptime(v, "%Y-%m-%d").date() if v and v != "0000-00-00" else None
    except ValueError:
        return None


def load_ofz_curve() -> list[tuple[float, float]]:
    """Точки кривой ОФЗ (срок в годах, доходность %) — для спреда корпоратов."""
    try:
        data = _get(ZCYC_URL)
        cols = data["yearyields"]["columns"]
        rows = [dict(zip(cols, r)) for r in data["yearyields"]["data"]]
        return sorted((float(r["period"]), float(r["value"])) for r in rows if r.get("value") is not None)
    except Exception as e:
        logger.warning("ОФЗ-кривая недоступна: %s", e)
        return []


def ofz_yield_at(curve: list[tuple[float, float]], years: float) -> float | None:
    """Доходность ОФЗ на срок `years` — линейная интерполяция по кривой."""
    if not curve or years is None:
        return None
    if years <= curve[0][0]:
        return curve[0][1]
    if years >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= years <= x1:
            return y0 + (y1 - y0) * (years - x0) / (x1 - x0)
    return None


def classify_risk(bond_type: str, spread_bp: int | None) -> str:
    if bond_type == "ofz":
        return "gov"
    if spread_bp is None:
        return "medium"
    if spread_bp < 250:
        return "high"
    if spread_bp <= 600:
        return "medium"
    return "speculative"


def fetch_board(board: str, bond_type: str) -> list[dict]:
    """Сырые записи облигаций одного борда (объединяет securities + marketdata)."""
    data = _get(BONDS_URL.format(board=board))
    sc, md = data["securities"], data["marketdata"]
    md_map = {r[md["columns"].index("SECID")]: dict(zip(md["columns"], r)) for r in md["data"]}
    out = []
    for row in sc["data"]:
        s = dict(zip(sc["columns"], row))
        m = md_map.get(s["SECID"], {})
        out.append({"s": s, "m": m, "board": board, "bond_type": bond_type})
    return out


_UPSERT = text("""
    INSERT INTO bonds (secid, isin, short_name, issuer_name, bond_type, board, currency,
        face_value, coupon_percent, coupon_value, coupon_period, maturity_date, offer_date,
        has_amortization, lot_size, listing_level, last_price, ytm, duration_days, accrued_int,
        risk_tier, spread_bp, updated_at)
    VALUES (:secid, :isin, :short_name, :issuer_name, :bond_type, :board, :currency,
        :face_value, :coupon_percent, :coupon_value, :coupon_period, :maturity_date, :offer_date,
        :has_amortization, :lot_size, :listing_level, :last_price, :ytm, :duration_days, :accrued_int,
        :risk_tier, :spread_bp, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        short_name=EXCLUDED.short_name, issuer_name=EXCLUDED.issuer_name, bond_type=EXCLUDED.bond_type,
        board=EXCLUDED.board, currency=EXCLUDED.currency, face_value=EXCLUDED.face_value,
        coupon_percent=EXCLUDED.coupon_percent, coupon_value=EXCLUDED.coupon_value,
        coupon_period=EXCLUDED.coupon_period, maturity_date=EXCLUDED.maturity_date,
        offer_date=EXCLUDED.offer_date, lot_size=EXCLUDED.lot_size, listing_level=EXCLUDED.listing_level,
        last_price=EXCLUDED.last_price, ytm=EXCLUDED.ytm, duration_days=EXCLUDED.duration_days,
        accrued_int=EXCLUDED.accrued_int, risk_tier=EXCLUDED.risk_tier, spread_bp=EXCLUDED.spread_bp,
        updated_at=EXCLUDED.updated_at
""")


def upsert_bond(db: Session, rec: dict, curve: list) -> None:
    s, m = rec["s"], rec["m"]
    ytm = _f(m.get("YIELD"))
    dur_days = int(m.get("DURATION")) if m.get("DURATION") not in (None, "", 0) else None
    dur_years = dur_days / 365 if dur_days else None
    spread_bp = None
    if rec["bond_type"] != "ofz" and ytm is not None and dur_years:
        base = ofz_yield_at(curve, dur_years)
        if base is not None:
            spread_bp = round((ytm - base) * 100)   # п.п. → б.п.
    db.execute(_UPSERT, {
        "secid": s["SECID"], "isin": s.get("ISIN"), "short_name": s.get("SHORTNAME") or s["SECID"],
        "issuer_name": s.get("EMITENT_TITLE"), "bond_type": rec["bond_type"], "board": rec["board"],
        "currency": s.get("FACEUNIT"), "face_value": _f(s.get("FACEVALUE")),
        "coupon_percent": _f(s.get("COUPONPERCENT")), "coupon_value": _f(s.get("COUPONVALUE")),
        "coupon_period": int(s["COUPONPERIOD"]) if s.get("COUPONPERIOD") else None,
        "maturity_date": _d(s.get("MATDATE")), "offer_date": _d(s.get("OFFERDATE")),
        "has_amortization": False, "lot_size": int(s["LOTSIZE"]) if s.get("LOTSIZE") else None,
        "listing_level": int(s["LISTLEVEL"]) if s.get("LISTLEVEL") else None,
        "last_price": _f(m.get("LCURRENTPRICE") or m.get("LAST")), "ytm": ytm,
        "duration_days": dur_days, "accrued_int": _f(s.get("ACCRUEDINT")),
        "risk_tier": classify_risk(rec["bond_type"], spread_bp), "spread_bp": spread_bp,
        "updated_at": datetime.now(timezone.utc),
    })


def fetch_cashflow(secid: str) -> dict:
    """Календарь купонов/амортизаций/оферт одной облигации (для блока денежного потока)."""
    data = _get(f"https://iss.moex.com/iss/securities/{secid}/bondization.json?iss.meta=off&limit=100")
    out = {"coupons": [], "amortizations": [], "offers": []}
    for block in ("coupons", "amortizations", "offers"):
        b = data.get(block)
        if not b:
            continue
        cols = b["columns"]
        out[block] = [dict(zip(cols, r)) for r in b["data"]]
    return out
