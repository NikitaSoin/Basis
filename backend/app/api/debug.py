"""Диагностические эндпоинты — только для отладки."""
import json
import logging
import os
import ssl
import urllib.request
import urllib.error

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

TINKOFF_TOKEN = os.environ.get("TINKOFF_API_TOKEN", "").strip()
_API = "https://invest-public-api.tinkoff.ru/rest"
_ssl_ctx = ssl.create_default_context()


def _post(path: str, body: dict) -> tuple[dict | None, str | None]:
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
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_ctx) as resp:
            return json.loads(resp.read()), None
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:600]
        except Exception:
            pass
        return None, f"HTTP {e.code}: {body_text}"
    except Exception as e:
        return None, str(e)


@router.get("/debug/tinkoff")
def debug_tinkoff():
    """Диагностика Tinkoff API без SDK — показывает что реально возвращает API."""
    if not TINKOFF_TOKEN:
        return {"error": "TINKOFF_API_TOKEN не задан в переменных окружения"}

    result: dict = {"token_length": len(TINKOFF_TOKEN)}

    # ── 1. Попытка загрузить акции (разные варианты параметра) ──────────────
    shares_attempts = []
    instruments = []

    for body in [
        {"instrumentStatus": "INSTRUMENT_STATUS_ALL"},
        {"instrumentStatus": 2},
        {"instrumentStatus": "INSTRUMENT_STATUS_BASE"},
        {},
    ]:
        resp, err = _post(
            "tinkoff.public.invest.api.contract.v1.InstrumentsService/Shares",
            body,
        )
        attempt = {"body": body, "error": err}
        if resp is not None:
            # Покажем ключи верхнего уровня ответа
            attempt["response_keys"] = list(resp.keys())
            attempt["total"] = sum(len(v) if isinstance(v, list) else 0 for v in resp.values())
            # Берём список инструментов из первого подходящего ключа
            for key in ("instruments", "Instruments", "items", "shares"):
                if key in resp and isinstance(resp[key], list):
                    instruments = resp[key]
                    attempt["instruments_key"] = key
                    attempt["instruments_count"] = len(instruments)
                    break
        shares_attempts.append(attempt)
        if instruments:
            break

    result["shares_attempts"] = shares_attempts

    # ── 2. Анализ загруженных инструментов ──────────────────────────────────
    if instruments:
        # Распределение по exchange (без фильтра)
        exchange_dist: dict[str, int] = {}
        for ins in instruments:
            ex = str(ins.get("exchange", "<пусто>"))
            exchange_dist[ex] = exchange_dist.get(ex, 0) + 1

        result["exchange_distribution"] = exchange_dist
        result["total_instruments"] = len(instruments)

        # Первые 5 инструментов — все строковые поля
        result["sample_first_5"] = [
            {k: v for k, v in ins.items() if isinstance(v, (str, int, bool, float))}
            for ins in instruments[:5]
        ]

        # Первые 5 где exchange содержит MOEX
        moex_sample = [
            {k: v for k, v in ins.items() if isinstance(v, (str, int, bool, float))}
            for ins in instruments
            if "MOEX" in str(ins.get("exchange", "")).upper()
        ][:5]
        result["sample_moex_5"] = moex_sample
        result["moex_count"] = sum(1 for ins in instruments if "MOEX" in str(ins.get("exchange", "")).upper())

    # ── 3. Тест цены Сбера (FIGI известен) ──────────────────────────────────
    sber_figi = "BBG004730N88"
    for body in [{"figi": [sber_figi]}, {"instrumentId": [sber_figi]}]:
        resp, err = _post(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices",
            body,
        )
        if resp is not None:
            result["sber_price_raw"] = resp
            lp = (resp.get("lastPrices") or resp.get("last_prices") or [{}])[0]
            price_obj = lp.get("price", {})
            units = int(price_obj.get("units", 0) or 0)
            nano = int(price_obj.get("nano", 0) or 0)
            result["sber_price_computed"] = units + nano / 1_000_000_000
            break
        else:
            result[f"sber_price_error_{list(body.keys())[0]}"] = err

    return result


@router.get("/debug/env")
def debug_env():
    """Проверка переменных окружения (без значений секретов)."""
    keys = ["TINKOFF_API_TOKEN", "MOEX_USERNAME", "MOEX_PASSWORD", "DATABASE_URL", "ANTHROPIC_API_KEY"]
    return {
        k: f"задан ({len(os.environ.get(k, ''))} символов)" if os.environ.get(k) else "НЕ ЗАДАН"
        for k in keys
    }
