"""Свечи OHLCV с MOEX ISS для графиков ChartPro (таймфреймы 1м…месяц).

Один движок на все классы активов — та же архитектура, что instrument_history
(бесключевой официальный ISS, паузы, ретраи через moex_history._get_json).

Нативные интервалы ISS candles: 1 (1м), 10 (10м), 60 (1ч), 24 (день),
7 (неделя), 31 (месяц). Запрошенные владельцем 5м/15м агрегируются из 1м,
4ч — из 60м (ISS их не отдаёт). Глубина по таймфрейму подобрана под ~500
баров на графике — больше не нужно (v1 без подгрузки прошлого скроллом).

Время: ISS отдаёт биржевое (московское) наивное время. Отдаём его фронту
как epoch «как будто UTC» — стандартный приём для lightweight-charts, чтобы
на шкале отображалось биржевое время, а не локальное время браузера.

Кэш in-memory с TTL: интрадей-свеча мутирует — короткий TTL; дневки и
старше — длинный. Ключ (asset_class, secid, tf).
"""
import logging
import time
import urllib.parse
from datetime import date, datetime, timedelta

from app.services.moex_history import _get_json, REQUEST_PAUSE

logger = logging.getLogger(__name__)

_CANDLES_URL = "https://iss.moex.com/iss/engines/{engine}/markets/{market}/securities/{secid}/candles.json"
_PAGE = 500  # ISS отдаёт свечи страницами по 500

# asset_class → (engine, market). Борд ISS выбирает сам (primary board).
_SOURCES: dict[str, tuple[str, str]] = {
    "share":  ("stock",    "shares"),
    "fund":   ("stock",    "shares"),   # ETF/БПИФ переведены MOEX на TQBR (2026-06-22)
    "index":  ("stock",    "index"),
    "bond":   ("stock",    "bonds"),
    "future": ("futures",  "forts"),
    "spot":   ("currency", "selt"),
}

# tf → (нативный интервал ISS, шаг агрегации сек | None, глубина запроса дней, TTL кэша сек)
_TF: dict[str, tuple[int, int | None, int, int]] = {
    "1m":  (1,  None,       2,    60),
    "5m":  (1,  5 * 60,     5,    90),
    "15m": (1,  15 * 60,    10,   120),
    "1h":  (60, None,       90,   180),
    "4h":  (60, 4 * 3600,   365,  300),
    "1d":  (24, None,       1100, 1800),
    "1w":  (7,  None,       3700, 3600),
    "1M":  (31, None,       7400, 3600),
}

_cache: dict[tuple[str, str, str], tuple[float, dict]] = {}
_CACHE_MAX = 400


def _parse_ts(s: str) -> int:
    """'YYYY-MM-DD HH:MM:SS' (биржевое время) → epoch «как будто UTC»."""
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    return int((dt - datetime(1970, 1, 1)).total_seconds())


def _fetch_raw(engine: str, market: str, secid: str, interval: int, frm: date) -> list[dict]:
    """Все свечи с даты frm до сейчас, с пагинацией ISS (start=N, страницы по 500)."""
    rows: list[dict] = []
    start = 0
    while True:
        params = {
            "iss.meta": "off",
            "interval": interval,
            "from": frm.isoformat(),
            "start": start,
            "candles.columns": "begin,open,high,low,close,value,volume",
        }
        url = _CANDLES_URL.format(engine=engine, market=market, secid=secid) + "?" + urllib.parse.urlencode(params)
        data = _get_json(url)
        page = data.get("candles", {}).get("data", []) or []
        for r in page:
            # columns: begin, open, high, low, close, value, volume
            if r[0] is None or r[4] is None:
                continue
            rows.append({
                "t": _parse_ts(r[0]),
                "o": r[1], "h": r[2], "l": r[3], "c": r[4],
                "v": r[6] if r[6] not in (None, 0) else r[5],
            })
        if len(page) < _PAGE:
            break
        start += len(page)
        time.sleep(REQUEST_PAUSE)
    return rows


def _aggregate(rows: list[dict], step_sec: int) -> list[dict]:
    """Схлопывает свечи в корзины по step_sec (5м/15м из 1м, 4ч из 60м).
    Корзина — floor(t/step): для внутридневных шагов это ровные интервалы
    от полуночи (биржевое время кратно шагу — совпадает с корзинами TradingView)."""
    out: list[dict] = []
    cur: dict | None = None
    cur_bucket = None
    for r in rows:
        b = r["t"] // step_sec
        if b != cur_bucket:
            if cur is not None:
                out.append(cur)
            cur = {"t": b * step_sec, "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r["v"] or 0}
            cur_bucket = b
        else:
            cur["h"] = max(cur["h"], r["h"]) if r["h"] is not None else cur["h"]
            cur["l"] = min(cur["l"], r["l"]) if r["l"] is not None else cur["l"]
            cur["c"] = r["c"]
            cur["v"] = (cur["v"] or 0) + (r["v"] or 0)
    if cur is not None:
        out.append(cur)
    return out


def get_candles(asset_class: str, secid: str, tf: str) -> dict:
    """Свечи для графика. Пустой ряд candles:[] — фронт покажет «нет данных»."""
    if asset_class not in _SOURCES or tf not in _TF:
        return {"asset_class": asset_class, "secid": secid, "tf": tf, "candles": []}

    key = (asset_class, secid.upper(), tf)
    now = time.time()
    hit = _cache.get(key)
    interval, step, depth_days, ttl = _TF[tf]
    if hit and now - hit[0] < ttl:
        return hit[1]

    engine, market = _SOURCES[asset_class]
    frm = date.today() - timedelta(days=depth_days)
    try:
        rows = _fetch_raw(engine, market, secid.upper(), interval, frm)
    except Exception as e:
        logger.warning("candles: %s/%s tf=%s — %s", asset_class, secid, tf, e)
        # протухший кэш лучше пустоты
        return hit[1] if hit else {"asset_class": asset_class, "secid": secid, "tf": tf, "candles": []}

    if step:
        rows = _aggregate(rows, step)

    last = rows[-1]["c"] if rows else None
    prev = rows[-2]["c"] if len(rows) >= 2 else None
    result = {
        "asset_class": asset_class, "secid": secid.upper(), "tf": tf,
        "last": last,
        "change_pct": round((last / prev - 1) * 100, 2) if last and prev else None,
        "candles": rows,
    }

    if len(_cache) >= _CACHE_MAX:  # примитивная защита от распухания
        _cache.pop(next(iter(_cache)))
    _cache[key] = (now, result)
    return result
