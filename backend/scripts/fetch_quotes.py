"""
Загружает котировки с MOEX ISS API (bulk TQBR endpoint) для всех компаний в БД.
Один запрос = все акции. Работает и во время торгов, и после закрытия.
Запуск: cd backend && python -m scripts.fetch_quotes

Авторизация:
  Для real-time данных (без 15-мин задержки) задай MOEX_USERNAME и MOEX_PASSWORD в .env.
  Аккаунт бесплатный: https://www.moex.com/ru/registration/
  После регистрации нужно принять соглашение об использовании данных в профиле.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import base64
import http.cookiejar
import logging
import time
import urllib.request
import ssl
import json
from datetime import date, datetime

logger = logging.getLogger(__name__)

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

BULK_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities.json"
    "?iss.meta=off&iss.only=marketdata,securities"
    "&marketdata.columns=SECID,LAST,CHANGE,LASTTOPREVPRICE,OPEN,HIGH,LOW,VOLRUR,SYSTIME"
    "&securities.columns=SECID,PREVPRICE,PREVDATE"
)

AUTH_URL = "https://passport.moex.com/authenticate"

# Кэшируем сессионную куку — переаутентифицируемся раз в 6 часов
_session_cookie: str | None = None
_session_ts: float = 0


def _get_moex_cookie() -> str | None:
    """Авторизуется в MOEX Passport и возвращает значение куки MicexPassportCert."""
    global _session_cookie, _session_ts

    if _session_cookie and (time.time() - _session_ts) < 6 * 3600:
        return _session_cookie

    username = os.environ.get("MOEX_USERNAME", "").strip()
    password = os.environ.get("MOEX_PASSWORD", "").strip()
    if not username or not password:
        return None

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_ctx),
        urllib.request.HTTPCookieProcessor(cookie_jar),
    )
    req = urllib.request.Request(
        AUTH_URL,
        headers={
            "Authorization": f"Basic {auth}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    try:
        with opener.open(req, timeout=10):
            pass
        for cookie in cookie_jar:
            if cookie.name == "MicexPassportCert":
                _session_cookie = cookie.value
                _session_ts = time.time()
                logger.info("MOEX: авторизация успешна (real-time режим)")
                return _session_cookie
        logger.warning("MOEX: авторизация не вернула куку — проверь логин/пароль")
    except Exception as e:
        logger.warning("MOEX: ошибка авторизации: %s", e)
    return None


def fetch_moex_bulk() -> dict[str, dict]:
    """Возвращает {ticker: {...}, '_moex_time': str, '_fetched_at': str}"""
    url = BULK_URL + f"&_ts={int(time.time())}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Cache-Control": "no-cache",
    }
    cookie = _get_moex_cookie()
    if cookie:
        headers["Cookie"] = f"MicexPassportCert={cookie}"

    req = urllib.request.Request(url, headers=headers)
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

    moex_systime = None
    if md_rows and "SYSTIME" in md_cols:
        sample = dict(zip(md_cols, md_rows[0]))
        moex_systime = sample.get("SYSTIME")
        if moex_systime:
            try:
                moex_time = datetime.fromisoformat(moex_systime)
                delay_sec = (datetime.now() - moex_time).total_seconds()
                logger.info("MOEX SYSTIME=%s  delay=%.0fs  auth=%s",
                            moex_systime, delay_sec, "yes" if cookie else "no")
            except Exception:
                pass

    result: dict[str, dict] = {}
    today = date.today()

    for row in md_rows:
        md = dict(zip(md_cols, row))
        ticker = md["SECID"]
        sec = sec_map.get(ticker, {})

        price = md.get("LAST") or sec.get("PREVPRICE")
        if not price:
            continue

        prev_close = sec.get("PREVPRICE")
        change_abs = md.get("CHANGE")
        change_pct = md.get("LASTTOPREVPRICE")

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
        bulk.pop("_moex_time", None)
        bulk.pop("_fetched_at", None)
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
