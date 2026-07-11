"""Биржевые фонды (БПИФ/ETF) с MOEX ISS (класс активов «Фонды»).

Список и параметры:
  /iss/engines/stock/markets/shares/boards/TQBR/securities.json
  securities (SECID, SHORTNAME, SECNAME, ISIN, LISTLEVEL) + marketdata
  (LAST, LCURRENTPRICE, VALTODAY — оборот/ликвидность, NUMTRADES).

ВАЖНО: MOEX перевёл все ETF/БПИФ с прежнего борда TQTF на TQBR (общий борд
«Акции и ДР») 2026-06-22 — TQTF с этой даты is_traded=0 (проверено напрямую в
ISS). TQBR отдаёт ВСЮ доску (акции + фонды одним списком, тысячи строк) —
fetch_funds() возвращает всё как есть, а refresh_funds() (asset_data.py)
ФИЛЬТРУЕТ по уже известным secid из таблицы funds перед upsert, иначе сюда бы
записались тысячи обычных акций как «фонды». Список фондов — курируемый
(добавляется вручную/скриптом), этот модуль только освежает live-метаданные
уже известных бумаг, не открывает новые сам.

Тип фонда классифицируется по имени (SECNAME). TER/состав — не на MOEX
(сайты УК), заполняются курируемо/аналитиком. Методика — docs/funds-methodology.md.
"""
import json
import logging
import ssl
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}

FUNDS_URL = ("https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
             "?iss.meta=off&iss.only=securities,marketdata"
             "&securities.columns=SECID,SHORTNAME,SECNAME,ISIN,FACEUNIT,LISTLEVEL"
             "&marketdata.columns=SECID,LAST,LCURRENTPRICE,VALTODAY,NUMTRADES")


# Курируемый TER (совокупные расходы, % годовых) — не на MOEX, по данным УК
# (приблизительно, на 2026; точное значение — на сайте фонда). Расширяется.
TER_MAP = {
    "LQDT": 0.40, "AKMM": 0.34, "SBMM": 0.33, "TMON": 0.30,   # денежный рынок
    "SBMX": 1.00, "EQMX": 0.67, "TMOS": 0.79, "AKME": 1.05,   # акции/индекс Мосбиржи
    "DIVD": 1.30, "TDIV": 1.49,                               # дивидендные смарт-бета
    "OBLG": 0.80, "SBGB": 0.82, "AKFB": 0.78,                 # облигации
    "GOLD": 0.66, "AKGD": 1.06, "SBGD": 0.69, "TGLD": 0.69,   # золото
}


def classify_fund(sec_name: str | None) -> str:
    """Тип фонда по имени: gold | money_market | bonds | currency | equity | mixed."""
    if not sec_name:
        return "mixed"
    s = sec_name.lower()
    if "золот" in s or "gold" in s:
        return "gold"
    if "ликвидн" in s or "денежн" in s or "сберег" in s or "накопит" in s:
        return "money_market"
    if "облига" in s or "бонд" in s or "долг" in s or "обл " in s or "обл." in s:
        return "bonds"
    if "валют" in s or "юан" in s or "доллар" in s or "юаней" in s:
        return "currency"
    if "акци" in s or "индекс" in s or "фишек" in s or "голуб" in s or "капитал акц" in s:
        return "equity"
    return "mixed"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=40, context=_ssl_ctx) as r:
        return json.loads(r.read())


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def fetch_funds() -> list[dict]:
    """Сырые записи ВСЕЙ доски TQBR (securities + marketdata) — акции и фонды
    вперемешку, фильтрация по известным фондам — на вызывающей стороне
    (asset_data.refresh_funds), у неё есть доступ к БД."""
    data = _get(FUNDS_URL)
    sc, md = data["securities"], data["marketdata"]
    mi = md["columns"].index("SECID")
    md_map = {r[mi]: dict(zip(md["columns"], r)) for r in md["data"]}
    out = []
    for row in sc["data"]:
        s = dict(zip(sc["columns"], row))
        out.append({"s": s, "m": md_map.get(s["SECID"], {})})
    return out


_UPSERT = text("""
    INSERT INTO funds (secid, isin, short_name, sec_name, fund_type, currency, listing_level,
        last_price, val_today, num_trades, ter, updated_at)
    VALUES (:secid, :isin, :short_name, :sec_name, :fund_type, :currency, :listing_level,
        :last_price, :val_today, :num_trades, :ter, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        isin=EXCLUDED.isin, short_name=EXCLUDED.short_name, sec_name=EXCLUDED.sec_name,
        fund_type=EXCLUDED.fund_type, currency=EXCLUDED.currency, listing_level=EXCLUDED.listing_level,
        last_price=EXCLUDED.last_price, val_today=EXCLUDED.val_today, num_trades=EXCLUDED.num_trades,
        ter=COALESCE(EXCLUDED.ter, funds.ter), updated_at=EXCLUDED.updated_at
""")


def upsert_fund(db: Session, rec: dict) -> None:
    s, m = rec["s"], rec["m"]
    db.execute(_UPSERT, {
        "secid": s["SECID"], "isin": s.get("ISIN"), "short_name": s.get("SHORTNAME") or s["SECID"],
        "sec_name": s.get("SECNAME"), "fund_type": classify_fund(s.get("SECNAME")),
        "currency": s.get("FACEUNIT"),
        "listing_level": int(s["LISTLEVEL"]) if s.get("LISTLEVEL") else None,
        "last_price": _f(m.get("LCURRENTPRICE") or m.get("LAST")),
        "val_today": int(m["VALTODAY"]) if m.get("VALTODAY") not in (None, "") else None,
        "num_trades": int(m["NUMTRADES"]) if m.get("NUMTRADES") not in (None, "") else None,
        "ter": TER_MAP.get(s["SECID"]),
        "updated_at": datetime.now(timezone.utc),
    })
