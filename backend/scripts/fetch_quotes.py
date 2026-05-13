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

import urllib.request
import ssl
import json
from datetime import date

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

# Один запрос — все акции основного режима TQBR
BULK_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    "?iss.meta=off&iss.only=marketdata,securities"
    "&marketdata.columns=SECID,LAST,CHANGE,LASTTOPREVPRICE,OPEN,HIGH,LOW,VOLRUR"
    "&securities.columns=SECID,PREVPRICE,PREVDATE"
)


def fetch_moex_bulk() -> dict[str, dict]:
    """Возвращает {ticker: {price, change_abs, change_pct, open, high, low, prev_close, date}}"""
    req = urllib.request.Request(BULK_URL, headers={"User-Agent": "Mozilla/5.0"})
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
