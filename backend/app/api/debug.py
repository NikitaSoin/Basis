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
        result["total_instruments"] = len(instruments)

        # Все ключи первого инструмента — чтобы видеть точные имена полей
        result["instrument_field_names"] = list(instruments[0].keys()) if instruments else []

        # Распределение по exchange
        exchange_dist: dict[str, int] = {}
        for ins in instruments:
            ex = str(ins.get("exchange", "<пусто>"))
            exchange_dist[ex] = exchange_dist.get(ex, 0) + 1
        result["exchange_distribution"] = dict(sorted(exchange_dist.items(), key=lambda x: -x[1])[:15])

        # Распределение по classCode (все варианты написания)
        class_dist: dict[str, int] = {}
        for ins in instruments:
            cc = str(ins.get("classCode") or ins.get("class_code") or "<пусто>")
            class_dist[cc] = class_dist.get(cc, 0) + 1
        result["class_code_distribution"] = dict(sorted(class_dist.items(), key=lambda x: -x[1])[:20])

        # Считаем TQBR по обоим вариантам имени поля
        tqbr_camel = [ins for ins in instruments if ins.get("classCode") == "TQBR"]
        tqbr_snake = [ins for ins in instruments if ins.get("class_code") == "TQBR"]
        result["tqbr_count_classCode"] = len(tqbr_camel)
        result["tqbr_count_class_code"] = len(tqbr_snake)

        # Первые 5 инструментов — все скалярные поля
        result["sample_first_5"] = [
            {k: v for k, v in ins.items() if isinstance(v, (str, int, bool, float))}
            for ins in instruments[:5]
        ]

        # Первые 5 TQBR инструментов
        tqbr_list = tqbr_camel or tqbr_snake
        result["sample_tqbr_5"] = [
            {k: v for k, v in ins.items() if isinstance(v, (str, int, bool, float))}
            for ins in tqbr_list[:5]
        ]

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
    keys = ["TINKOFF_API_TOKEN", "MOEX_USERNAME", "MOEX_PASSWORD", "DATABASE_URL",
            "ANTHROPIC_API_KEY", "ANTHROPIC_PROXY_URL", "DEEPSEEK_API_KEY", "FRED_API_KEY",
            "LLM_PROVIDER", "RUN_STARTUP_JOBS"]
    return {
        k: (f"задан ({len(os.environ.get(k, ''))} символов)" if k.endswith(("KEY", "TOKEN", "PASSWORD"))
            else os.environ.get(k)) if os.environ.get(k) else "НЕ ЗАДАН"
        for k in keys
    }


@router.get("/debug/connectivity")
async def debug_connectivity():
    """Замер исходящей сети С САМОГО ИНСТАНСА: кто доступен, кто режется.

    Отвечает на вопрос «зарубеж блокируется целиком или конкретные сервисы?» и
    «жив ли Cloudflare-Worker-прокси». TCP+TLS установились (любой HTTP-код, даже
    401/403/404) = ХОСТ ДОСТУПЕН. ConnectTimeout/ConnectError = НЕДОСТУПЕН.
    """
    import asyncio
    import time as _t
    import httpx

    proxy = os.environ.get("ANTHROPIC_PROXY_URL")
    targets = {
        # рабочая LLM и макро — то, что висит в логах
        "deepseek (api.deepseek.com)": "https://api.deepseek.com",
        "fred (api.stlouisfed.org)": "https://api.stlouisfed.org/fred/",
        # Claude напрямую и через CF-Worker — сравнить
        "anthropic_direct (api.anthropic.com)": "https://api.anthropic.com",
        "cf_worker (ANTHROPIC_PROXY_URL)": proxy,
        # нейтральная зарубежка — общий вердикт «зарубеж режется или нет»
        "google.com": "https://www.google.com",
        "cloudflare 1.1.1.1": "https://1.1.1.1",
        "github.com": "https://github.com",
        # русские хосты — контроль (должны работать)
        "moex (iss.moex.com)": "https://iss.moex.com/iss/index.json",
        "tinkoff": "https://invest-public-api.tinkoff.ru/rest/",
    }

    async def probe(name: str, url: str | None) -> dict:
        if not url:
            return {"target": name, "result": "НЕ ЗАДАН (env пуст)"}
        t0 = _t.monotonic()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, connect=7),
                                         follow_redirects=True, verify=False) as c:
                r = await c.get(url)
            ms = int((_t.monotonic() - t0) * 1000)
            return {"target": name, "reachable": True, "http_status": r.status_code, "ms": ms}
        except Exception as e:  # noqa: BLE001
            ms = int((_t.monotonic() - t0) * 1000)
            return {"target": name, "reachable": False, "error": type(e).__name__, "ms": ms}

    net = await asyncio.gather(*(probe(n, u) for n, u in targets.items()))

    # БД — отдельным короткоживущим соединением (НЕ через общий пул: он мог быть
    # исчерпан фоновыми задачами, тогда обычный /health/db висит).
    db_res: dict = {}
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        url = os.environ.get("DATABASE_URL")
        ca = {}
        if url and "localhost" not in url and "127.0.0.1" not in url:
            if "sslmode" not in url:
                ca["sslmode"] = "require"
            ca["connect_timeout"] = 7
        t0 = _t.monotonic()
        eng = create_engine(url, connect_args=ca, poolclass=NullPool)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        db_res = {"reachable": True, "ms": int((_t.monotonic() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        db_res = {"reachable": False, "error": type(e).__name__, "detail": str(e)[:200]}

    # Статус пула соединений общего engine (НЕ создаёт соединение — читает счётчики).
    # Если checked_out == size+overflow → пул ИСЧЕРПАН (фоновые задачи держат всё) —
    # это и есть причина зависания всех синхронных роутов.
    pool_res: dict = {}
    try:
        from app.db.session import engine as _eng
        p = _eng.pool
        pool_res = {
            "status": p.status(),
            "checked_out": p.checkedout(),
            "checked_in": p.checkedin(),
            "overflow": p.overflow(),
            "size": p.size(),
        }
    except Exception as e:  # noqa: BLE001
        pool_res = {"error": type(e).__name__, "detail": str(e)[:200]}

    return {
        "llm_provider": os.environ.get("LLM_PROVIDER") or "deepseek (default)",
        "cf_worker_configured": bool(proxy),
        "network": net,
        "database_fresh_connection": db_res,
        "db_pool": pool_res,
        "note": "reachable=true даже при http_status 401/403/404 — значит TCP+TLS прошли, хост ДОСТУПЕН. db_pool.checked_out близко к size+overflow → пул исчерпан фоновыми задачами (причина зависания sync-роутов).",
    }


def _trace_host(host: str, port: int = 443) -> dict:
    import socket
    import ssl as _ssl
    import time as _t
    out: dict = {"host": host, "port": port}
    # 1) DNS — какие адреса (и IPv4/IPv6)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        addrs, seen = [], set()
        for fam, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            ver = "IPv6" if fam == socket.AF_INET6 else "IPv4"
            if (ip, ver) in seen:
                continue
            seen.add((ip, ver))
            addrs.append({"ip": ip, "family": ver})
        out["dns"] = addrs
    except Exception as e:  # noqa: BLE001
        out["dns_error"] = f"{type(e).__name__}: {e}"
        return out
    # 2) Сырой TCP-connect к каждому IP на :443 — пускает ли вообще пакеты
    tcp = []
    for a in out["dns"]:
        fam = socket.AF_INET6 if a["family"] == "IPv6" else socket.AF_INET
        s = socket.socket(fam, socket.SOCK_STREAM)
        s.settimeout(6)
        t0 = _t.monotonic()
        rec = {"ip": a["ip"], "family": a["family"]}
        try:
            s.connect((a["ip"], port))
            rec["tcp"] = "ok"
            rec["ms"] = int((_t.monotonic() - t0) * 1000)
            # 3) TLS-хендшейк с SNI — режет ли DPI по имени хоста
            try:
                ctx = _ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                ss = ctx.wrap_socket(s, server_hostname=host)
                ss.settimeout(6)
                rec["tls"] = "ok"
                ss.close()
            except Exception as e:  # noqa: BLE001
                rec["tls"] = f"FAIL: {type(e).__name__}"
        except Exception as e:  # noqa: BLE001
            rec["tcp"] = f"FAIL: {type(e).__name__}"
            rec["ms"] = int((_t.monotonic() - t0) * 1000)
        finally:
            try:
                s.close()
            except Exception:
                pass
        tcp.append(rec)
    out["tcp_connect"] = tcp
    return out


@router.get("/debug/trace")
async def debug_trace(host: str = "api.deepseek.com"):
    """Послойная трассировка до хоста: DNS (IPv4/IPv6) → сырой TCP :443 → TLS+SNI.
    Показывает ТОЧНО, где рвётся связь с DeepSeek/FRED:
      - dns_error → не резолвится;
      - tcp FAIL → пакеты не доходят (IP/маршрут режется);
      - tcp ok + tls FAIL → режет DPI по имени хоста (SNI);
      - всё ok → дело не в сети, а в httpx/таймауте.
    Примеры: /api/debug/trace?host=api.deepseek.com , ?host=api.stlouisfed.org"""
    import asyncio
    return await asyncio.to_thread(_trace_host, host)


@router.get("/debug/ping")
async def debug_ping():
    """Чистый async-роут БЕЗ БД и сети — всегда должен отвечать, даже если пул
    потоков/соединений полностью висит. Если /debug/ping отвечает, а /debug/env
    (sync) — нет, значит блокировка именно в синхронном пути (пул потоков/БД)."""
    return {"pong": True}
