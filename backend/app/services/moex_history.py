"""Историческая дневная история котировок с MOEX ISS (Этап 0 аналитики портфеля).

Единый модуль для двух режимов:
  1) массовая первичная закачка — scripts/load_quote_history.py;
  2) ежедневное дообновление пропущенных дней — job в планировщике (main.py).

Особенности ISS:
  - история отдаётся страницами ~100 строк; листаем курсором history.cursor
    (INDEX/TOTAL/PAGESIZE) через параметр start — ОБЯЗАТЕЛЬНО до конца;
  - акции берём с борда TQBR (основной режим T+2); если по TQBR пусто
    (бумага торгуется в другом режиме) — берём весь рынок shares и фильтруем
    основные TQ*-борды;
  - индексы (IMOEX/RTSI/MCFTR) живут на рынке index, ключей не требуют.

Вежливость к API: пауза между запросами + ретраи с экспоненциальным backoff.
Идемпотентность: INSERT ... ON CONFLICT (company_id, date) — повторный запуск
не плодит дубли; для прошедших дат официальная история уточняет поля через
COALESCE (живые котировки не затираются NULL'ами).
"""
import json
import logging
import ssl
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Тот же стиль, что в scripts/fetch_quotes.py (общая инфраструктура MOEX)
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

ISS_BASE = "https://iss.moex.com/iss/history/engines/stock/markets"
SHARE_COLUMNS = "TRADEDATE,OPEN,LOW,HIGH,CLOSE,LEGALCLOSEPRICE,VALUE,BOARDID"
INDEX_COLUMNS = "TRADEDATE,OPEN,LOW,HIGH,CLOSE,VALUE,BOARDID"

BENCHMARK_TICKERS = ["IMOEX", "RTSI", "MCFTR"]

REQUEST_PAUSE = 0.25       # сек между запросами — не долбим MOEX
RETRIES = 4                # попыток на один URL
BACKOFF_BASE = 2.0         # 2с → 4с → 8с между ретраями
TIMEOUT = 20


def _get_json(url: str) -> dict:
    """GET с ретраями и экспоненциальным backoff."""
    last_err: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx) as resp:
                return json.loads(resp.read())
        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                delay = BACKOFF_BASE ** attempt
                logger.warning("ISS: %s (попытка %d/%d) — повтор через %.0fс", e, attempt, RETRIES, delay)
                time.sleep(delay)
    raise RuntimeError(f"ISS: не удалось получить {url}: {last_err}")


def _fetch_paginated(base_url: str, params: dict) -> list[dict]:
    """Выкачивает ВСЕ страницы истории, листая курсором до TOTAL."""
    rows: list[dict] = []
    start = 0
    while True:
        q = dict(params, start=start)
        url = base_url + "?" + urllib.parse.urlencode(q)
        data = _get_json(url)
        cols = data["history"]["columns"]
        page = [dict(zip(cols, r)) for r in data["history"]["data"]]
        rows.extend(page)

        cursor = data.get("history.cursor", {}).get("data") or [[0, 0, 100]]
        index, total, pagesize = cursor[0]
        if index + pagesize >= total or not page:
            break
        start = index + pagesize
        time.sleep(REQUEST_PAUSE)
    return rows


def fetch_share_history(ticker: str, date_from: date, date_till: date) -> list[dict]:
    """Дневная история акции. Сначала борд TQBR; если пусто — весь рынок
    с фильтром по основным TQ*-бордам (бумаги вне TQBR, напр. иннорежимы)."""
    params = {
        "iss.meta": "off",
        "from": date_from.isoformat(),
        "till": date_till.isoformat(),
        "history.columns": SHARE_COLUMNS,
    }
    rows = _fetch_paginated(f"{ISS_BASE}/shares/boards/TQBR/securities/{ticker}.json", params)
    if not rows:
        time.sleep(REQUEST_PAUSE)
        rows = _fetch_paginated(f"{ISS_BASE}/shares/securities/{ticker}.json", params)
        rows = [r for r in rows if str(r.get("BOARDID", "")).startswith("TQ")]
    # один день мог попасть с двух бордов — оставляем первый
    seen: set[str] = set()
    out = []
    for r in rows:
        d = r["TRADEDATE"]
        if d not in seen:
            seen.add(d)
            out.append(r)
    return out


def fetch_index_history(ticker: str, date_from: date, date_till: date) -> list[dict]:
    """Дневная история индекса (IMOEX/RTSI/MCFTR) с рынка index."""
    params = {
        "iss.meta": "off",
        "from": date_from.isoformat(),
        "till": date_till.isoformat(),
        "history.columns": INDEX_COLUMNS,
    }
    rows = _fetch_paginated(f"{ISS_BASE}/index/securities/{ticker}.json", params)
    seen: set[str] = set()
    out = []
    for r in rows:
        d = r["TRADEDATE"]
        if d not in seen and r.get("CLOSE") is not None:
            seen.add(d)
            out.append(r)
    return out


# ──────────────────────────── запись в БД ────────────────────────────

_UPSERT_QUOTE_SQL = text("""
    INSERT INTO quotes (company_id, date, open, close, high, low, volume,
                        prev_close, change_abs, change_pct)
    VALUES (:company_id, :date, :open, :close, :high, :low, :volume,
            :prev_close, :change_abs, :change_pct)
    ON CONFLICT (company_id, date) DO UPDATE SET
        open       = COALESCE(EXCLUDED.open,       quotes.open),
        close      = COALESCE(EXCLUDED.close,      quotes.close),
        high       = COALESCE(EXCLUDED.high,       quotes.high),
        low        = COALESCE(EXCLUDED.low,        quotes.low),
        volume     = COALESCE(EXCLUDED.volume,     quotes.volume),
        prev_close = COALESCE(EXCLUDED.prev_close, quotes.prev_close),
        change_abs = COALESCE(EXCLUDED.change_abs, quotes.change_abs),
        change_pct = COALESCE(EXCLUDED.change_pct, quotes.change_pct)
""")

_UPSERT_INDEX_SQL = text("""
    INSERT INTO index_history (ticker, date, open, close, high, low, value)
    VALUES (:ticker, :date, :open, :close, :high, :low, :value)
    ON CONFLICT (ticker, date) DO UPDATE SET
        open  = COALESCE(EXCLUDED.open,  index_history.open),
        close = COALESCE(EXCLUDED.close, index_history.close),
        high  = COALESCE(EXCLUDED.high,  index_history.high),
        low   = COALESCE(EXCLUDED.low,   index_history.low),
        value = COALESCE(EXCLUDED.value, index_history.value)
""")


def upsert_share_rows(db: Session, company_id: int, rows: list[dict]) -> int:
    """Пишет историю одной акции в quotes. prev_close/изменение считаем по
    цепочке соседних торговых дней внутри закачанной истории.

    Официальная история — источник истины для завершённых дней: для прошедших
    дат уточняет поля (через COALESCE, NULL ничего не затирает); сегодняшнюю
    live-котировку планировщика не трогает — history за сегодня появляется
    только после завершения торгов.
    """
    rows = sorted(rows, key=lambda r: r["TRADEDATE"])
    written = 0
    prev_close = None
    for r in rows:
        close = r.get("CLOSE") or r.get("LEGALCLOSEPRICE")
        if close is None:
            prev_close = None
            continue
        change_abs = change_pct = None
        if prev_close:
            pct = (float(close) - float(prev_close)) / float(prev_close) * 100
            # Разрыв ряда из-за корпоративного действия (сплит/консолидация,
            # как у VTBR 1:5000 в 2024): сравнение цен бессмысленно, а огромный
            # процент не влезает в Numeric(8,4) — изменение не записываем.
            if abs(pct) <= 200:
                change_abs = round(float(close) - float(prev_close), 4)
                change_pct = round(pct, 4)
        db.execute(_UPSERT_QUOTE_SQL, {
            "company_id": company_id,
            "date": r["TRADEDATE"],
            "open": r.get("OPEN"),
            "close": close,
            "high": r.get("HIGH"),
            "low": r.get("LOW"),
            # как и в quotes_updater: volume — оборот в рублях (VALUE)
            "volume": int(r["VALUE"]) if r.get("VALUE") else None,
            "prev_close": prev_close,
            "change_abs": change_abs,
            "change_pct": change_pct,
        })
        written += 1
        prev_close = close
    return written


def upsert_index_rows(db: Session, ticker: str, rows: list[dict]) -> int:
    written = 0
    for r in rows:
        db.execute(_UPSERT_INDEX_SQL, {
            "ticker": ticker,
            "date": r["TRADEDATE"],
            "open": r.get("OPEN"),
            "close": r["CLOSE"],
            "high": r.get("HIGH"),
            "low": r.get("LOW"),
            "value": r.get("VALUE"),
        })
        written += 1
    return written


# ──────────────────────── ежедневное дообновление ────────────────────────

def catch_up_history(days_back_max: int = 30) -> None:
    """Доедание пропущенных дней истории. Запускается раз в день вечером
    (job в существующем планировщике, см. main.py).

    Для каждой компании: смотрим последний день в quotes и докачиваем
    официальную историю от него до вчера (max days_back_max дней назад,
    чтобы при длительном простое не превращаться в полную перезакачку —
    для неё есть scripts/load_quote_history.py). Заодно прошедшие дни,
    записанные live-снапшотами (Tinkoff: volume=0, open=high=low=close),
    уточняются официальными дневными свечами. Бенчмарки — так же.
    """
    from app.db.session import SessionLocal
    from app.models.company import Company, Quote
    from sqlalchemy import func

    today = date.today()
    floor_date = today - timedelta(days=days_back_max)

    db = SessionLocal()
    try:
        last_by_company = dict(
            db.query(Quote.company_id, func.max(Quote.date)).group_by(Quote.company_id).all()
        )
        companies = db.query(Company).order_by(Company.ticker).all()
        total_rows = 0
        fetched = 0
        for c in companies:
            last = last_by_company.get(c.id)
            # с запасом в 5 дней назад: финализируем последние live-снапшоты
            start = max((last - timedelta(days=5)) if last else floor_date, floor_date)
            if start >= today:
                continue
            try:
                rows = fetch_share_history(c.ticker, start, today)
                total_rows += upsert_share_rows(db, c.id, rows)
                fetched += 1
            except Exception as e:
                logger.warning("История %s: %s", c.ticker, e)
            time.sleep(REQUEST_PAUSE)
        db.commit()

        idx_rows = 0
        for t in BENCHMARK_TICKERS:
            last = db.execute(
                text("SELECT max(date) FROM index_history WHERE ticker = :t"), {"t": t}
            ).scalar()
            start = max((last - timedelta(days=5)) if last else floor_date, floor_date)
            try:
                rows = fetch_index_history(t, start, today)
                idx_rows += upsert_index_rows(db, t, rows)
            except Exception as e:
                logger.warning("История индекса %s: %s", t, e)
            time.sleep(REQUEST_PAUSE)
        db.commit()
        logger.info("История: дообновление — %d бумаг, %d строк quotes, %d строк индексов",
                    fetched, total_rows, idx_rows)
    except Exception as e:
        logger.exception("История: ошибка дообновления: %s", e)
        db.rollback()
    finally:
        db.close()
