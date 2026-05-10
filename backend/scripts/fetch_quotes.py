"""
Загружает последние котировки с MOEX ISS API для всех компаний в БД.
Запуск: cd backend && python scripts/fetch_quotes.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import urllib.request
import ssl
import json
from datetime import date, datetime, timedelta

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

from app.db.session import SessionLocal
from app.models.company import Company, Quote

MOEX_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/securities/"
    "{ticker}.json?iss.meta=off&iss.only=marketdata,securities"
    "&marketdata.columns=SECID,LAST,OPEN,HIGH,LOW,VOLRUR"
    "&securities.columns=SECID,PREVPRICE,PREVDATE"
)


def fetch_moex(ticker: str) -> dict | None:
    url = MOEX_URL.format(ticker=ticker)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  [ОШИБКА] {ticker}: {e}")
        return None

    # marketdata block
    md_columns = data.get("marketdata", {}).get("columns", [])
    md_rows = data.get("marketdata", {}).get("data", [])

    # securities block (PREVPRICE, PREVDATE)
    sec_columns = data.get("securities", {}).get("columns", [])
    sec_rows = data.get("securities", {}).get("data", [])

    if not md_rows or not sec_rows:
        return None

    md = dict(zip(md_columns, md_rows[0]))
    sec = dict(zip(sec_columns, sec_rows[0]))

    # Determine price: prefer last trade price, fall back to prev close
    last_price = md.get("LAST") or sec.get("PREVPRICE")
    if not last_price:
        return None

    prev_date_str = sec.get("PREVDATE")
    try:
        quote_date = datetime.strptime(prev_date_str, "%Y-%m-%d").date() if prev_date_str else date.today()
    except ValueError:
        quote_date = date.today()

    return {
        "date": quote_date,
        "open": md.get("OPEN") or last_price,
        "close": last_price,
        "high": md.get("HIGH") or last_price,
        "low": md.get("LOW") or last_price,
        "volume": int(md.get("VOLRUR") or 0),
    }


def main():
    db = SessionLocal()
    try:
        companies = db.query(Company).order_by(Company.ticker).all()
        print(f"Компаний в БД: {len(companies)}\n")

        loaded = 0
        skipped = 0
        failed = 0

        for company in companies:
            print(f"  {company.ticker} ...", end=" ", flush=True)
            quote_data = fetch_moex(company.ticker)
            if not quote_data:
                print("нет данных")
                failed += 1
                continue

            # Upsert: update if exists for this date, else insert
            existing = (
                db.query(Quote)
                .filter(Quote.company_id == company.id, Quote.date == quote_data["date"])
                .first()
            )
            if existing:
                existing.open = quote_data["open"]
                existing.close = quote_data["close"]
                existing.high = quote_data["high"]
                existing.low = quote_data["low"]
                existing.volume = quote_data["volume"]
                skipped += 1
                print(f"обновлено ({quote_data['close']} ₽)")
            else:
                db.add(Quote(
                    company_id=company.id,
                    date=quote_data["date"],
                    open=quote_data["open"],
                    close=quote_data["close"],
                    high=quote_data["high"],
                    low=quote_data["low"],
                    volume=quote_data["volume"],
                ))
                loaded += 1
                print(f"загружено ({quote_data['close']} ₽)")

        db.commit()
        print(f"\nИтого: загружено {loaded}, обновлено {skipped}, ошибок {failed}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
