"""Спот валюты и драгметаллов с MOEX ISS (класс «Валюта и металлы»).

Валютный рынок: engine=currency, market=selt, борд CETS.
Инструменты (курируемый набор): USD/CNY/EUR/рубль + золото/серебро/рубль.
Цена берётся из последней ДНЕВНОЙ свечи (доступна и при закрытом рынке, в отличие
от marketdata.LAST, который ночью пуст). Методика — docs/currency-metals-positioning.md.
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

# Курируемый набор: (secid, человеч. имя, kind, base_code)
SPOT_INSTRUMENTS = [
    ("USD000UTSTOM", "Доллар США / рубль", "currency", "USD"),
    ("CNYRUB_TOM", "Китайский юань / рубль", "currency", "CNY"),
    # EUR_RUB__TOM — биржевые торги евро на MOEX остановлены (санкции 2024), нет свечей.
    ("GLDRUB_TOM", "Золото / рубль (грамм)", "metal", "GLD"),
    ("SLVRUB_TOM", "Серебро / рубль (грамм)", "metal", "SLV"),
]


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=30, context=_ssl_ctx) as r:
        return json.loads(r.read())


def _last_two_closes(secid: str) -> tuple[float | None, float | None]:
    """Последняя и предпоследняя дневные цены закрытия (для цены и изменения).
    ВАЖНО: свечи MOEX идут от СТАРТА истории — берём окно последних ~40 дней
    через from=, иначе [-1] вернёт старую свечу, не свежую."""
    from datetime import date, timedelta
    try:
        frm = (date.today() - timedelta(days=40)).isoformat()
        url = (f"https://iss.moex.com/iss/engines/currency/markets/selt/securities/{secid}/candles.json"
               f"?iss.meta=off&interval=24&from={frm}&candles.columns=close,end")
        data = _get(url)
        rows = data["candles"]["data"]
        closes = [r[0] for r in rows if r[0] is not None]
        last = closes[-1] if closes else None
        prev = closes[-2] if len(closes) >= 2 else None
        return last, prev
    except Exception as e:
        logger.warning("свечи %s недоступны: %s", secid, e)
        return None, None


_UPSERT = text("""
    INSERT INTO spot_assets (secid, short_name, name, kind, base_code,
        last_price, prev_close, change_pct, updated_at)
    VALUES (:secid, :short_name, :name, :kind, :base_code,
        :last_price, :prev_close, :change_pct, :updated_at)
    ON CONFLICT (secid) DO UPDATE SET
        short_name=EXCLUDED.short_name, name=EXCLUDED.name, kind=EXCLUDED.kind,
        base_code=EXCLUDED.base_code, last_price=EXCLUDED.last_price,
        prev_close=EXCLUDED.prev_close, change_pct=EXCLUDED.change_pct,
        updated_at=EXCLUDED.updated_at
""")


def refresh_spot(db: Session) -> int:
    """Загрузить/обновить курируемый набор спот-инструментов (валюта + металлы)."""
    import time as _t
    for secid, name, kind, base in SPOT_INSTRUMENTS:
        last, prev = _last_two_closes(secid)
        change = round((last / prev - 1) * 100, 3) if last and prev else None
        db.execute(_UPSERT, {
            "secid": secid, "short_name": secid, "name": name, "kind": kind, "base_code": base,
            "last_price": last, "prev_close": prev, "change_pct": change,
            "updated_at": datetime.now(timezone.utc),
        })
        _t.sleep(0.2)
    db.commit()
    n = db.execute(text("SELECT count(*) FROM spot_assets")).scalar()
    logger.info("Спот валюта/металлы: загружено, в БД %d", n)
    return n
