"""
Tinkoff Invest API — real-time котировки через REST gateway.

Используется как primary source если задан TINKOFF_API_TOKEN.
Fallback — MOEX ISS (fetch_quotes.py).

Получить токен:
  Т-Инвестиции → Профиль → Для разработчиков → Создать токен (только чтение)
"""
import json
import logging
import os
import ssl
import threading
import time
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

TINKOFF_TOKEN = os.environ.get("TINKOFF_API_TOKEN", "").strip()
_API = "https://invest-public-api.tinkoff.ru/rest"

_ssl_ctx = ssl.create_default_context()

# Кэш: {ticker: str → {price, change_abs, change_pct, prev_close}}
_prices: dict[str, dict] = {}

# FIGI / UID ↔ ticker
_uid_to_ticker: dict[str, str] = {}
_ticker_to_uid: dict[str, str] = {}
# ticker → URL логотипа бренда (CDN T-Инвестиций)
_ticker_to_logo: dict[str, str] = {}
# логотипы прочих классов активов — ISIN → URL (облигации), тикер Т-Инвестиций
# (=наш secid) → URL (фонды/фьючерсы/валюта). Отдельно от _ticker_to_logo:
# облигация — не компания-эмитент, это логотип самого ВЫПУСКА/инструмента у
# Т-Инвестиций (владелец: «у любой облигации/фьючерса/фонда есть своя
# картинка в Т-Инвестициях, раз мы это тянем оттуда — почему бы не подтянуть»).
_isin_to_logo: dict[str, str] = {}
_secid_to_logo: dict[str, str] = {}
_other_instruments_ts: float = 0.0

# Время последнего обновления инструментов (кэшируем на 24ч)
_instruments_ts: float = 0

# Статус последнего запроса к Tinkoff
_last_success_ts: float = 0
_last_error: str = ""


# ─── низкоуровневый HTTP ────────────────────────────────────────────────────

def _post(path: str, body: dict) -> dict:
    url = f"{_API}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {TINKOFF_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10, context=_ssl_ctx) as resp:
        return json.loads(resp.read())


def _quotation_to_float(q: dict) -> float | None:
    if not q:
        return None
    units = int(q.get("units", 0) or 0)
    nano = int(q.get("nano", 0) or 0)
    result = units + nano / 1_000_000_000
    return result if result > 0 else None


# ─── загрузка инструментов ─────────────────────────────────────────────────

def _load_instruments() -> bool:
    """Загружает FIGI/UID ↔ ticker для акций MOEX. Кэшируется на 24ч."""
    global _instruments_ts

    if _uid_to_ticker and (time.time() - _instruments_ts) < 86400:
        return True

    try:
        resp = _post(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares",
            {"instrumentStatus": "INSTRUMENT_STATUS_ALL"},
        )
        all_instruments = resp.get("instruments", [])
        print(f"[Tinkoff] Всего инструментов от API: {len(all_instruments)}", flush=True)

        count = 0
        for share in all_instruments:
            # TQBR — основной режим торгов MOEX
            class_code = share.get("classCode") or share.get("class_code", "")
            if class_code != "TQBR":
                continue
            ticker = share.get("ticker", "")
            uid = share.get("uid", "") or share.get("figi", "")
            if ticker and uid:
                _uid_to_ticker[uid] = ticker
                _ticker_to_uid[ticker] = uid
                # Логотип бренда из T-Инвестиций (надёжный машинный источник):
                # brand.logoName = "Sberbank.png" → CDN .../Sberbankx160.png
                logo_name = (share.get("brand") or {}).get("logoName") or ""
                if logo_name:
                    base = logo_name.rsplit(".", 1)[0]
                    _ticker_to_logo[ticker] = f"https://invest-brands.cdn-tinkoff.ru/{base}x160.png"
                count += 1

        _instruments_ts = time.time()
        print(f"[Tinkoff] TQBR инструментов загружено: {count}", flush=True)
        logger.info("Tinkoff: загружено %d TQBR инструментов", count)
        return count > 0

    except Exception as e:
        logger.error("Tinkoff: ошибка загрузки инструментов: %s", e)
        return False


def get_logos() -> dict[str, str]:
    """{ticker: URL логотипа} из брендов T-Инвестиций. Инструменты кэшируются 24ч."""
    try:
        if not TINKOFF_TOKEN:
            return {}
        _load_instruments()
    except Exception:  # noqa: BLE001
        pass
    return dict(_ticker_to_logo)


def _load_other_instruments() -> bool:
    """Логотипы облигаций/фондов/фьючерсов/валюты из брендов T-Инвестиций —
    тот же принцип, что _load_instruments() для акций (InstrumentsService,
    brand.logoName → CDN), но по ДРУГИМ пространствам идентификаторов:
    - Bonds: у бумаги нет тикера в привычном смысле, надёжный ключ — ISIN
      (его мы храним в своей модели Bond.isin).
    - Etfs/Futures/Currencies: у Т-Инвестиций свой ticker, который на практике
      совпадает с MOEX secid для биржевых инструментов (наши Fund.secid/
      Future.secid/SpotAsset.secid) — используем как ключ.
    Не у каждого инструмента есть brand — так же честно деградируем
    (пропускаем), как для акций."""
    global _other_instruments_ts
    if (_isin_to_logo or _secid_to_logo) and (time.time() - _other_instruments_ts) < 86400:
        return True
    endpoints = [
        ("Bonds", "isin", _isin_to_logo),
        ("Etfs", "ticker", _secid_to_logo),
        ("Futures", "ticker", _secid_to_logo),
        ("Currencies", "ticker", _secid_to_logo),
    ]
    count = 0
    ok = False
    for method, key_field, target in endpoints:
        try:
            resp = _post(
                f"tinkoff.public.invest.api.contract.v1.InstrumentsService/{method}",
                {"instrumentStatus": "INSTRUMENT_STATUS_ALL"},
            )
            for item in resp.get("instruments", []):
                key = item.get(key_field, "")
                logo_name = (item.get("brand") or {}).get("logoName") or ""
                if not key or not logo_name:
                    continue
                base = logo_name.rsplit(".", 1)[0]
                target[key] = f"https://invest-brands.cdn-tinkoff.ru/{base}x160.png"
                count += 1
            ok = True
        except Exception as e:  # noqa: BLE001
            logger.error("Tinkoff: ошибка загрузки логотипов (%s): %s", method, e)
    if ok:
        _other_instruments_ts = time.time()
        logger.info("Tinkoff: логотипов облигаций/фондов/фьючерсов/валюты загружено: %d", count)
    return ok


def get_instrument_logos() -> dict[str, str]:
    """{ISIN или secid: URL логотипа} для облигаций/фондов/фьючерсов/валюты —
    отдельно от get_logos() (акции, по тикеру компании), другое пространство
    идентификаторов. Инструменты кэшируются 24ч."""
    try:
        if not TINKOFF_TOKEN:
            return {}
        _load_other_instruments()
    except Exception:  # noqa: BLE001
        pass
    merged = dict(_isin_to_logo)
    merged.update(_secid_to_logo)
    return merged


# ─── обновление цен ────────────────────────────────────────────────────────

def refresh_prices(prev_close_map: dict[str, float | None] | None = None) -> bool:
    """
    Получает актуальные цены с Tinkoff REST API.
    prev_close_map: {ticker: prev_close} — для расчёта изменения.
    Если None — используются уже сохранённые prev_close.
    """
    global _last_success_ts, _last_error

    if not TINKOFF_TOKEN:
        return False

    if not _load_instruments():
        return False

    uids = list(_uid_to_ticker.keys())
    if not uids:
        return False

    try:
        # Получаем последние цены (~500 инструментов за раз)
        resp = _post(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
            {"instrumentId": uids},
        )

        updated = 0
        for lp in resp.get("lastPrices", []):
            uid = lp.get("instrumentUid", "") or lp.get("figi", "")
            ticker = _uid_to_ticker.get(uid)
            if not ticker:
                continue

            price = _quotation_to_float(lp.get("price"))
            if price is None:
                continue

            # prev_close: из переданного map → из кэша → из существующей записи
            if prev_close_map is not None:
                prev_close = prev_close_map.get(ticker)
            else:
                prev_close = _prices.get(ticker, {}).get("prev_close")

            if prev_close and prev_close > 0:
                change_abs = round(price - prev_close, 4)
                change_pct = round((price / prev_close - 1) * 100, 4)
            else:
                change_abs = None
                change_pct = None

            _prices[ticker] = {
                "price": price,
                "change_abs": change_abs,
                "change_pct": change_pct,
                "prev_close": prev_close,
            }
            updated += 1

        _last_success_ts = time.time()
        _last_error = ""
        logger.debug("Tinkoff: обновлено %d цен", updated)
        return updated > 0

    except Exception as e:
        _last_error = str(e)
        logger.warning("Tinkoff: ошибка получения цен: %s", e)
        return False


# Неблокирующее обновление: запрос НИКОГДА не ждёт сетевой вызов к Tinkoff.
_refresh_lock = threading.Lock()
_refreshing = False
_REFRESH_THROTTLE = 15  # сек: не чаще одного фонового обновления


def maybe_refresh_async() -> None:
    """Если кэш устарел (>throttle) — обновить цены В ФОНЕ (single-flight), НЕ блокируя
    вызывающий запрос. Эндпоинт realtime отдаёт кэш мгновенно, а сеть к Tinkoff
    дёргается отдельным потоком максимум раз в 15с. Это убирает синхронный сетевой
    вызов из каждого HTTP-запроса (иначе частый поллинг фронта забивает воркер)."""
    global _refreshing
    if not TINKOFF_TOKEN:
        return
    if time.time() - _last_success_ts < _REFRESH_THROTTLE:
        return
    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True

    def _run():
        global _refreshing
        try:
            refresh_prices()
        except Exception:  # noqa: BLE001
            pass
        finally:
            _refreshing = False

    threading.Thread(target=_run, daemon=True).start()


# ─── публичный интерфейс ───────────────────────────────────────────────────

def is_configured() -> bool:
    return bool(TINKOFF_TOKEN)


def is_available() -> bool:
    """True если токен задан и в кэше есть цены (>100 инструментов)."""
    return bool(TINKOFF_TOKEN) and len(_prices) > 100


def get_all_prices() -> dict[str, dict]:
    """Возвращает {ticker: {price, change_abs, change_pct}}."""
    return {
        ticker: {
            "price": v["price"],
            "change_abs": v["change_abs"],
            "change_pct": v["change_pct"],
        }
        for ticker, v in _prices.items()
        if v.get("price") is not None
    }


def status() -> dict:
    return {
        "configured": is_configured(),
        "available": is_available(),
        "instruments_loaded": len(_uid_to_ticker),
        "prices_cached": len(_prices),
        "last_success": datetime.fromtimestamp(_last_success_ts).isoformat() if _last_success_ts else None,
        "last_error": _last_error or None,
    }
