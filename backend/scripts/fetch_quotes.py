"""
Загружает котировки с MOEX ISS API (bulk TQBR endpoint) для всех компаний в БД.
Один запрос = все акции. Работает и во время торгов, и после закрытия.
Запуск: cd backend && python -m scripts.fetch_quotes
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import logging
import urllib.request
import ssl
import json
from datetime import date, datetime

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

# Один запрос — все акции основного режима TQBR
BULK_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    "?iss.meta=off&iss.only=marketdata,securities"
    "&marketdata.columns=SECID,LAST,CHANGE,LASTTOPREVPRICE,OPEN,HIGH,LOW,VOLRUR,SYSTIME"
    "&securities.columns=SECID,PREVPRICE,PREVDATE"
)


def fetch_moex_bulk() -> dict[str, dict]:
    """Возвращает {ticker: {...}, '_moex_time': str, '_fetched_at': str}"""
    import time as _time
    # _ts cache-buster — исключает кэширование на прокси/CDN
    url = BULK_URL + f"&_ts={int(_time.time())}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
        data = json.loads(resp.read())

    md_cols = data["marketdata"]["columns"]
    md_rows = data["marketdata"]["data"]
    sec_cols = data["securities"]["columns"]
    sec_rows = data["securities"]["data"]

    sec_map: dict[str, dict] = {
        r[sec_cols.index("SECID")]: dict(zip(sec_cols, r))
        for r in sec_rows
    }

    # Извлекаем SYSTIME — метка времени данных на сервере MOEX
    moex_systime = None
    if md_rows and "SYSTIME" in md_cols:
        sample = dict(zip(md_cols, md_rows[0]))
        moex_systime = sample.get("SYSTIME")
        if moex_systime:
            try:
                from datetime import datetime as _dt
                moex_time = _dt.fromisoformat(moex_systime)
                delay_sec = (_dt.now() - moex_time).total_seconds()
                logger.info("[MOEX] SYSTIME=%s  delay=%.0fs", moex_systime, delay_sec)
            except Exception:
                logger.info("[MOEX] SYSTIME=%s", moex_systime)

    result: dict[str, dict] = {}
    today = date.today()

    for row in md_rows:
        md = dict(zip(md_cols, row))
        ticker = md["SECID"]
        sec = sec_map.get(ticker, {})

        # Берём LAST (внутри дня) или PREVPRICE (последняя цена закрытия)
        price = md.get("LAST") or sec.get("PREVPRICE")
        if not price:
            continue

        prev_close = sec.get("PREVPRICE")
        change_abs = md.get("CHANGE")
        change_pct = md.get("LASTTOPREVPRICE")

        # Если LAST=None (после закрытия), изменение = 0 (относительно самого себя)
        if md.get("LAST") is None:
            change_abs = 0.0
            change_pct = 0.0

        result[ticker] = {
            "date": today,
            "open": md.get("OPEN") or price,
            "close": price,
            "high": md.get("HIGH") or price,
            "low": md.get("LOW") or price,
            "volume": int(md.get("VOLRUR") or 0) if md.get("VOLRUR") else 0,
            "prev_close": prev_close,
            "change_abs": round(float(change_abs), 4) if change_abs is not None else None,
            "change_pct": round(float(change_pct), 4) if change_pct is not None else None,
        }

    result["_moex_time"] = moex_systime
    result["_fetched_at"] = datetime.now().isoformat(timespec="seconds")
    return result


# Для обратной совместимости с quotes_updater.py
def fetch_moex(ticker: str) -> dict | None:
    """Устаревший поштучный вызов — используйте fetch_moex_bulk()."""
    try:
        bulk = fetch_moex_bulk()
        return bulk.get(ticker)
    except Exception as e:
        print(f"  [ОШИБКА] {ticker}: {e}")
        return None


def main():
    from app.db.session import SessionLocal
    from app.models.company import Company, Quote

    db = SessionLocal()
    try:
        print("Загружаем bulk-данные с MOEX...")
        bulk = fetch_moex_bulk()
        print(f"  Получено котировок: {len(bulk)}")

        companies = db.query(Company).order_by(Company.ticker).all()
        print(f"  Компаний в БД: {len(companies)}\n")

        loaded = updated = skipped = 0

        for company in companies:
            quote_data = bulk.get(company.ticker)
            if not quote_data:
                skipped += 1
                continue

            existing = (
                db.query(Quote)
                .filter(Quote.company_id == company.id, Quote.date == quote_data["date"])
                .first()
            )
            chg = f"{quote_data['change_pct']:+.2f}%" if quote_data["change_pct"] else ""

            if existing:
                existing.open = quote_data["open"]
                existing.close = quote_data["close"]
                existing.high = quote_data["high"]
                existing.low = quote_data["low"]
                existing.volume = quote_data["volume"]
                existing.prev_close = quote_data["prev_close"]
                existing.change_abs = quote_data["change_abs"]
                existing.change_pct = quote_data["change_pct"]
                updated += 1
                print(f"  {company.ticker:<8} обновлено  {quote_data['close']} ₽  {chg}")
            else:
                db.add(Quote(company_id=company.id, **quote_data))
                loaded += 1
                print(f"  {company.ticker:<8} загружено  {quote_data['close']} ₽  {chg}")

        db.commit()
        print(f"\nИтого: загружено {loaded}, обновлено {updated}, пропущено {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
