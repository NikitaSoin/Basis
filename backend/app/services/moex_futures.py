"""Фьючерсы с MOEX ISS (класс активов «Фьючерсы», срочный рынок FORTS).

Список и параметры:
  /iss/engines/futures/markets/forts/securities.json
  блоки securities (SECID, ASSETCODE — базовый актив, LASTTRADEDATE — экспирация,
  INITIALMARGIN — ГО, MINSTEP/STEPPRICE — для номинала, LOTVOLUME) + marketdata
  (LAST, SETTLEPRICE — расчётная цена, OPENPOSITION — открытые позиции/ликвидность).

Методика — docs/futures-methodology.md. Главное, что считаем кодом:
  номинал контракта = settle / MINSTEP × STEPPRICE;
  эффективное плечо = номинал / ГО (главная метрика риска деривати­ва).
Запросы к MOEX — ПОСЛЕДОВАТЕЛЬНО с паузой (бережно к rate limit).
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

FORTS_URL = ("https://iss.moex.com/iss/engines/futures/markets/forts/securities.json"
             "?iss.meta=off&iss.only=securities,marketdata"
             "&securities.columns=SECID,SHORTNAME,SECNAME,BOARDID,ASSETCODE,LASTTRADEDATE,"
             "INITIALMARGIN,MINSTEP,STEPPRICE,LOTVOLUME,PREVSETTLEPRICE"
             "&marketdata.columns=SECID,LAST,SETTLEPRICE,OPENPOSITION")

# Курируемый маппинг популярных базовых активов FORTS → (тип, человеч. имя,
# тикер связанной акции в нашей БД). Остальное → other. Расширяется по мере
# раскатки (после ОК владельца). Тип задаёт смысл карточки и расчёт базиса.
ASSET_MAP = {
    # валюта
    "Si":   ("currency", "Доллар США / рубль", None),
    "Eu":   ("currency", "Евро / рубль", None),
    "CNY":  ("currency", "Китайский юань / рубль", None),
    "ED":   ("currency", "Евро / доллар", None),
    "GBPRUB": ("currency", "Фунт / рубль", None),
    # индексы
    "RTS":  ("index", "Индекс РТС", None),
    "MIX":  ("index", "Индекс МосБиржи", None),
    "MXI":  ("index", "Индекс МосБиржи (мини)", None),
    "RGBI": ("index", "Индекс гособлигаций RGBI", None),
    # сырьё
    "BR":   ("commodity", "Нефть Brent", None),
    "NG":   ("commodity", "Природный газ", None),
    "GOLD": ("commodity", "Золото", None),
    "SILV": ("commodity", "Серебро", None),
    "PLT":  ("commodity", "Платина", None),
    "PLD":  ("commodity", "Палладий", None),
    "CU":   ("commodity", "Медь", None),
    "WHEAT": ("commodity", "Пшеница", None),
    # фьючерсы на акции (связь с карточкой компании)
    "SBRF": ("stock", "Сбербанк (ао)", "SBER"),
    "SBPR": ("stock", "Сбербанк (ап)", "SBERP"),
    "GAZR": ("stock", "Газпром", "GAZP"),
    "LKOH": ("stock", "Лукойл", "LKOH"),
    "GMKN": ("stock", "Норникель", "GMKN"),
    "ROSN": ("stock", "Роснефть", "ROSN"),
    "VTBR": ("stock", "ВТБ", "VTBR"),
    "YDEX": ("stock", "Яндекс", "YDEX"),
    "TATN": ("stock", "Татнефть", "TATN"),
    "MGNT": ("stock", "Магнит", "MGNT"),
    "MTSI": ("stock", "МТС", "MTSS"),
    "NLMK": ("stock", "НЛМК", "NLMK"),
    "ALRS": ("stock", "АЛРОСА", "ALRS"),
    "MOEX": ("stock", "Московская биржа", "MOEX"),
    # ставки
    "RUON": ("rate", "Ставка RUONIA", None),
    "RUONIA": ("rate", "Ставка RUONIA", None),
    "1MFR": ("rate", "Ставка RUSFAR 1M", None),
}


def classify_asset(asset_code: str) -> tuple[str, str, str | None]:
    """(asset_kind, asset_name, linked_ticker) по коду базового актива."""
    if asset_code in ASSET_MAP:
        return ASSET_MAP[asset_code]
    return ("other", asset_code, None)


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=40, context=_ssl_ctx) as r:
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


def fetch_futures() -> list[dict]:
    """Сырые записи всех контрактов FORTS (securities + marketdata)."""
    data = _get(FORTS_URL)
    sc, md = data["securities"], data["marketdata"]
    mi = md["columns"].index("SECID")
    md_map = {r[mi]: dict(zip(md["columns"], r)) for r in md["data"]}
    out = []
    for row in sc["data"]:
        s = dict(zip(sc["columns"], row))
        out.append({"s": s, "m": md_map.get(s["SECID"], {})})
    return out


def compute_contract_value(settle: float | None, min_step: float | None, step_price: float | None) -> float | None:
    """Номинал контракта, ₽ = цена / шаг × стоимость шага."""
    if settle is None or not min_step or step_price is None:
        return None
    return settle / min_step * step_price


_UPSERT = text("""
    INSERT INTO futures (secid, short_name, sec_name, board, asset_code, asset_name, asset_kind,
        linked_ticker, expiration_date, min_step, step_price, lot_volume, last_price, settle_price,
        prev_settle, open_position, initial_margin, contract_value, leverage, updated_at)
    VALUES (:secid, :short_name, :sec_name, :board, :asset_code, :asset_name, :asset_kind,
        :linked_ticker, :expiration_date, :min_step, :step_price, :lot_volume, :last_price, :settle_price,
        :prev_settle, :open_position, :initial_margin, :contract_value, :leverage, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        short_name=EXCLUDED.short_name, sec_name=EXCLUDED.sec_name, board=EXCLUDED.board,
        asset_code=EXCLUDED.asset_code, asset_name=EXCLUDED.asset_name, asset_kind=EXCLUDED.asset_kind,
        linked_ticker=EXCLUDED.linked_ticker, expiration_date=EXCLUDED.expiration_date,
        min_step=EXCLUDED.min_step, step_price=EXCLUDED.step_price, lot_volume=EXCLUDED.lot_volume,
        last_price=EXCLUDED.last_price, settle_price=EXCLUDED.settle_price, prev_settle=EXCLUDED.prev_settle,
        open_position=EXCLUDED.open_position, initial_margin=EXCLUDED.initial_margin,
        contract_value=EXCLUDED.contract_value, leverage=EXCLUDED.leverage, updated_at=EXCLUDED.updated_at
""")


def upsert_future(db: Session, rec: dict) -> None:
    s, m = rec["s"], rec["m"]
    kind, name, ticker = classify_asset(s.get("ASSETCODE") or "")
    settle = _f(m.get("SETTLEPRICE")) or _f(s.get("PREVSETTLEPRICE"))
    min_step = _f(s.get("MINSTEP"))
    step_price = _f(s.get("STEPPRICE"))
    margin = _f(s.get("INITIALMARGIN"))
    notional = compute_contract_value(settle, min_step, step_price)
    leverage = round(notional / margin, 2) if notional and margin else None
    db.execute(_UPSERT, {
        "secid": s["SECID"], "short_name": s.get("SHORTNAME") or s["SECID"],
        "sec_name": s.get("SECNAME"), "board": s.get("BOARDID"),
        "asset_code": s.get("ASSETCODE") or "?", "asset_name": name, "asset_kind": kind,
        "linked_ticker": ticker, "expiration_date": _d(s.get("LASTTRADEDATE")),
        "min_step": min_step, "step_price": step_price,
        "lot_volume": int(s["LOTVOLUME"]) if s.get("LOTVOLUME") else None,
        "last_price": _f(m.get("LAST")), "settle_price": settle, "prev_settle": _f(s.get("PREVSETTLEPRICE")),
        "open_position": int(m["OPENPOSITION"]) if m.get("OPENPOSITION") not in (None, "") else None,
        "initial_margin": margin, "contract_value": round(notional, 2) if notional else None,
        "leverage": leverage, "updated_at": datetime.now(timezone.utc),
    })
