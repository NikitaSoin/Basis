"""Диагностические эндпоинты — только для отладки.

🔴 БЕЗОПАСНОСТЬ (аудит 2026-07-26, docs/audit-2026-07/02-backend-security.md):
весь этот роутер исторически был ОТКРЫТ без авторизации — аноним мог стирать
прод-данные (purge/reset), жечь LLM-бюджет (trigger-*) и читать инфраструктуру
(env/connectivity). Теперь роутер защищён опциональным токеном:

  - переменная окружения DEBUG_API_TOKEN ЗАДАНА → каждый запрос обязан нести
    заголовок `X-Debug-Token: <значение>` (иначе 403);
  - переменная НЕ задана → поведение прежнее (открыто) + громкое предупреждение
    в лог при старте. Так деплой фикса ничего не ломает, а включение защиты —
    одна переменная в панели Timeweb (действие владельца).

После включения все ручные вызовы (curl из сессий Claude) должны добавлять
`-H "X-Debug-Token: $DEBUG_API_TOKEN"`."""
import json
import logging
import re
import os
import ssl
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

_DEBUG_TOKEN = os.environ.get("DEBUG_API_TOKEN", "").strip()
if not _DEBUG_TOKEN:
    logger.warning("🔓 /api/debug/* ОТКРЫТ БЕЗ АВТОРИЗАЦИИ: задайте DEBUG_API_TOKEN "
                   "в окружении, чтобы закрыть (см. докстринг app/api/debug.py)")


async def _debug_guard(request: Request):
    if _DEBUG_TOKEN and request.headers.get("X-Debug-Token", "") != _DEBUG_TOKEN:
        raise HTTPException(status_code=403, detail="X-Debug-Token обязателен")


from fastapi import Depends as _Depends  # noqa: E402 — рядом с местом использования

router = APIRouter(dependencies=[_Depends(_debug_guard)])

# 🔴 Отдельный роутер БЕЗ токена — ровно для одной страницы: HTML-консоли SQL. Браузер
# не умеет слать заголовок X-Debug-Token при открытии адреса, поэтому под общим гардом
# страница была бы недоступна вообще. Данных на ней НЕТ: это форма, которая сама
# спрашивает токен и шлёт его в /api/debug/sql, где гард на месте. Без токена не
# выполнится ни один запрос.
open_router = APIRouter()

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
    """Проверка переменных окружения (без значений секретов).

    ВАЖНО: DATABASE_URL — connection string с паролем ВНУТРИ (postgresql://user:pass@host)
    — раньше уходил в открытом виде (маскировались только KEY/TOKEN/PASSWORD по суффиксу
    имени переменной, DATABASE_URL под этот паттерн не попадал). Теперь такие URL-секреты
    маскируются отдельно (регэксп на userinfo часть), не просто по суффиксу имени ключа."""
    import re
    keys = ["JWT_SECRET_KEY", "DEBUG_API_TOKEN",  # только «задан/не задан» — значения маскируются ниже
            "TINKOFF_API_TOKEN", "MOEX_USERNAME", "MOEX_PASSWORD", "DATABASE_URL",
            "ANTHROPIC_API_KEY", "ANTHROPIC_PROXY_URL", "DEEPSEEK_API_KEY", "FRED_API_KEY",
            "LLM_PROVIDER", "RUN_STARTUP_JOBS", "MINFIN_BASE_URL",
            # Релеи egress-заблокированных хостов (см. agent_web.py/llm.py) — добавлены
            # сюда 2026-07-25 при отладке "агентский разбор документа падает на
            # severstal.com": без них здесь нельзя было удалённо проверить, реально ли
            # применилась переменная, добавленная в панели Timeweb, без failing-теста.
            "WEB_FETCH_PROXY_URL", "DEEPSEEK_BASE_URL", "FRED_BASE_URL"]
    out = {}
    for k in keys:
        v = os.environ.get(k)
        if not v:
            out[k] = "НЕ ЗАДАН"
        elif k.endswith(("KEY", "TOKEN", "PASSWORD")):
            out[k] = f"задан ({len(v)} символов)"
        elif "://" in v and "@" in v:  # connection-string с userinfo (напр. DATABASE_URL)
            out[k] = re.sub(r"://[^@/]+@", "://***:***@", v)
        else:
            out[k] = v
    return out


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
        "cbr (cbr.ru)": "https://www.cbr.ru/",
        "minfin (minfin.gov.ru)": "https://minfin.gov.ru/ru/press-center/",
        "prime_disclosure (1prime.ru)": "https://disclosure.1prime.ru/",
        "skrin_disclosure (disclosure.skrin.ru)": "https://disclosure.skrin.ru/",
        "azipi_disclosure (e-disclosure.azipi.ru)": "https://e-disclosure.azipi.ru/",
        "girbo (bo.nalog.gov.ru)": "https://bo.nalog.gov.ru/",
        "rosneft_rss (rosneft.ru)": "https://www.rosneft.ru/press/releases/rss/",
        "gazpromneft_rss (ir.gazprom-neft.ru)": "https://ir.gazprom-neft.ru/rss-feeds/rss-ad-hoc.xml",
        "tatneft_rss (tatneft.ru)": "https://www.tatneft.ru/rss/ru",
        "mmk_rss (mmk.ru)": "https://mmk.ru/",
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
        s.settimeout(3)
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


def _sni_test(host: str, port: int = 443, decoy: str = "www.google.com") -> dict:
    """Тот же IP, разные имена в TLS. Различает SNI-фильтр от IP/маршрут-проблемы."""
    import socket
    import ssl as _ssl
    import time as _t
    out: dict = {"host": host}
    try:
        ip = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        out["ip"] = ip
    except Exception as e:  # noqa: BLE001
        out["dns_error"] = f"{type(e).__name__}: {e}"
        return out

    def attempt(server_name: str | None) -> dict:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        t0 = _t.monotonic()
        try:
            s.connect((ip, port))
        except Exception as e:  # noqa: BLE001
            return {"tcp": f"FAIL: {type(e).__name__}", "ms": int((_t.monotonic() - t0) * 1000)}
        try:
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            kw = {"server_hostname": server_name} if server_name else {}
            ss = ctx.wrap_socket(s, **kw)
            ss.close()
            return {"tcp": "ok", "tls": "ok", "ms": int((_t.monotonic() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001
            return {"tcp": "ok", "tls": f"FAIL: {type(e).__name__}", "ms": int((_t.monotonic() - t0) * 1000)}
        finally:
            try:
                s.close()
            except Exception:
                pass

    out["real_sni (" + host + ")"] = attempt(host)
    out["decoy_sni (" + decoy + ")"] = attempt(decoy)
    out["no_sni"] = attempt(None)
    out["verdict_hint"] = ("real виснет (TimeoutError), а decoy/no_sni отвечают быстро "
                           "(ok или TLS-alert) → режут по ИМЕНИ хоста (SNI-фильтр на пути). "
                           "Все три виснут → проблема IP/маршрут/MTU, не имя.")
    return out


@router.get("/debug/sni")
async def debug_sni(host: str = "api.deepseek.com"):
    """Решающий тест: один IP, три варианта имени в TLS (настоящее/подставное/без).
    /api/debug/sni?host=api.deepseek.com , ?host=api.stlouisfed.org"""
    import asyncio
    return await asyncio.to_thread(_sni_test, host)


def _mtu_test(host: str, port: int = 443, mss: int = 1200) -> dict:
    """Проверка гипотезы MTU: TLS к IP без клампинга MSS и с ним. Если с маленьким
    MSS рукопожатие проходит, а без — виснет → это MTU black hole на пути (наша сторона)."""
    import socket
    import ssl as _ssl
    import time as _t
    out: dict = {"host": host, "mss": mss}
    try:
        ip = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
        out["ip"] = ip
    except Exception as e:  # noqa: BLE001
        out["dns_error"] = f"{type(e).__name__}: {e}"
        return out

    def attempt(clamp: bool) -> dict:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(6)
        if clamp:
            try:
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, mss)
            except Exception as e:  # noqa: BLE001
                return {"setsockopt": f"FAIL: {type(e).__name__}"}
        t0 = _t.monotonic()
        try:
            s.connect((ip, port))
        except Exception as e:  # noqa: BLE001
            return {"tcp": f"FAIL: {type(e).__name__}", "ms": int((_t.monotonic() - t0) * 1000)}
        try:
            ctx = _ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl.CERT_NONE
            ss = ctx.wrap_socket(s, server_hostname=host)
            ss.close()
            return {"tcp": "ok", "tls": "ok", "ms": int((_t.monotonic() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001
            return {"tcp": "ok", "tls": f"FAIL: {type(e).__name__}", "ms": int((_t.monotonic() - t0) * 1000)}
        finally:
            try:
                s.close()
            except Exception:
                pass

    out["without_clamp"] = attempt(False)
    out[f"with_mss_{mss}"] = attempt(True)
    out["verdict"] = ("with_mss=ok + without_clamp=timeout → это MTU/PMTUD (наша сторона), "
                      "лечится MSS-клампингом/снижением MTU. Оба ok → MTU не при чём.")
    return out


@router.get("/debug/mtu")
async def debug_mtu(host: str = "api.deepseek.com", mss: int = 1200):
    """Тест MTU-гипотезы: /api/debug/mtu?host=api.deepseek.com&mss=1200"""
    import asyncio
    return await asyncio.to_thread(_mtu_test, host, 443, mss)


@router.get("/debug/echo")
async def debug_echo(kb: int = 10):
    """Отдаёт НЕСЖИМАЕМЫЙ ответ ровно заданного размера (КБ) — чтобы С ВНЕШНЕГО узла
    найти порог, выше которого прокси Timeweb перестаёт отдавать ответ (code=000).
    Случайные байты → GZip их не ужмёт, размер на проводе = реальный. async, без БД."""
    import os as _os
    from fastapi.responses import Response
    # Кап 256 КБ (было 5000): аудит 2026-07-26 пометил как DoS-усилитель —
    # для замера порога прокси 256 КБ хватает с запасом.
    n = max(1, min(kb, 256))
    return Response(content=_os.urandom(n * 1024), media_type="application/octet-stream")


@router.get("/debug/selftest")
async def debug_selftest():
    """Замер ИЗНУТРИ инстанса: бьём в собственный uvicorn на 127.0.0.1:8000 (в обход
    прокси Timeweb). Разделяет «виноват прокси/отдача наружу» от «виноват код»:
      - быстро 200 → uvicorn+код здоровы, проблема в прокси/доставке наружу;
      - висит/ошибка → проблема в самом коде/хендлере."""
    import time as _t
    import httpx
    base = "http://127.0.0.1:8000"
    paths = ["/api/screener/scored?universe=all", "/api/companies", "/api/market/indices"]
    out: dict = {}
    async with httpx.AsyncClient(timeout=30) as c:
        for p in paths:
            t0 = _t.monotonic()
            try:
                r = await c.get(base + p)
                out[p] = {"code": r.status_code, "time_s": round(_t.monotonic() - t0, 2),
                          "size": len(r.content),
                          "content_encoding": r.headers.get("content-encoding"),
                          "content_length": r.headers.get("content-length")}
            except Exception as e:  # noqa: BLE001
                out[p] = {"error": type(e).__name__, "time_s": round(_t.monotonic() - t0, 2)}
    return out


@router.get("/debug/jobs-health")
def debug_jobs_health():
    """Здоровье кронов (фаза 6 плана автономности): вердикт ok/stale/failing/
    never_ran по каждому джобу — сравнение возраста последнего успешного прогона
    с ожидаемым интервалом. «Успех» = джоб-функция выполнилась до конца
    (liveness); джобы глотают свои исключения сами, точные ошибки добавляются
    точечными hb_err. Главный сценарий: крон молчит сутками (прецедент
    2026-07-05, лента новостей) — тут это видно сразу как stale."""
    from app.services.job_heartbeat import jobs_health
    return jobs_health()


@router.get("/debug/ping")
async def debug_ping():
    """Чистый async-роут БЕЗ БД и сети — всегда должен отвечать, даже если пул
    потоков/соединений полностью висит. Если /debug/ping отвечает, а /debug/env
    (sync) — нет, значит блокировка именно в синхронном пути (пул потоков/БД)."""
    return {"pong": True}


@router.post("/debug/trigger-macro-data-fixes")
def debug_trigger_macro_data_fixes():
    """Применить исправления рядов немедленно, не дожидаясь дневного крона (06:30).

    Зачем эндпоинт: код с исправлением доезжает на бой за минуты, а сами ДАННЫЕ
    чинятся только в ингесте — то есть до следующего утра боевой выпуск продолжает
    строиться на неверных числах. Здесь: адресные исправления точек + перечитывание
    ряда инфляционных ожиданий из XLSX-таблицы инФОМ (с чисткой дублей и сдвига).
    Без LLM.
    """
    from app.db.session import SessionLocal
    from app.services.macro_ingest import apply_known_corrections, seed_indicators
    db = SessionLocal()
    try:
        seed_indicators(db)     # подхватить правки справочника (единицы, названия)
        db.commit()
        out = {"corrections": apply_known_corrections(db)}
        try:
            from app.services.macro_cb_sync import sync_expectations
            out["expectations"] = sync_expectations(db)
        except Exception as e:  # noqa: BLE001
            out["expectations"] = {"error": f"{type(e).__name__}: {e}"}
        try:
            # Ручные ряды Росстата лежат в репозитории (config/rosstat_manual.csv) —
            # перечитываем их здесь же: именно так восстанавливаются серии, которые
            # источник машинно не отдаёт.
            from app.services.macro_rosstat import ingest_rosstat_file
            out["rosstat_manual"] = ingest_rosstat_file(db)
        except Exception as e:  # noqa: BLE001
            out["rosstat_manual"] = {"error": f"{type(e).__name__}: {e}"}
        try:
            # World Bank: сюда переведены китайские ряды после того, как OECD прекратил
            # свои серии на FRED. Без этого вызова смена источника доедет только с
            # ночным ингестом, а до утра витрина показывает данные 2023 года.
            from app.services.macro_ingest import ingest_worldbank
            out["worldbank"] = ingest_worldbank(db)
        except Exception as e:  # noqa: BLE001
            out["worldbank"] = {"error": f"{type(e).__name__}: {e}"}
        try:
            # Цены нефти: сюда переведён Urals после того, как прежний фид показывал
            # $60,7 при рыночных $84,6. Без этого вызова новая цена и дисконт
            # Urals-Brent появятся только с ночным кроном.
            from app.services.macro_oil_sync import sync_eia_spot, sync_oil_prices
            out["oil"] = sync_oil_prices(db)
            out["oil_eia"] = sync_eia_spot(db)
        except Exception as e:  # noqa: BLE001
            out["oil"] = {"error": f"{type(e).__name__}: {e}"}
        return out
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-data-fixes: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-macro-verification")
def debug_trigger_macro_verification():
    """Ручной запуск «ОТК данных» (macro_verification.run_verification) синхронно,
    без ожидания вечернего крона (18:30) — для проверки после фикса/деплоя.
    Без LLM (детерминированные парсеры + пара сетевых запросов) — дёшево."""
    from app.db.session import SessionLocal
    from app.services.macro_verification import run_verification
    db = SessionLocal()
    try:
        return run_verification(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-verification: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/seed-fixed-capital-investment-q1-2026")
def debug_seed_fixed_capital_investment_q1_2026():
    """Разовый сид: fixed_capital_investment (новый индикатор, 2026-07-25) заведён
    ТОЛЬКО через news_extract (нет официального синка — fedstat.ru заблокирован WAF,
    XLS Росстата не льётся LLM-текстом) — без этого сида показывал бы «нет данных»
    до следующего квартального релиза (Q2, ожидается ~сентябрь), хотя Q1 2026 уже
    опубликован и известен. Значение проверено напрямую по первоисточнику
    (interfax.ru/business/1093663, 3 июня 2026): «Инвестиции в основной капитал в РФ
    в I квартале 2026 года упали на 14,3% в годовом выражении» — Росстат. Разовый вызов,
    не гонять регулярно; дальнейшие кварталы должны приходить через news_extract."""
    from datetime import date as _date
    from app.db.session import SessionLocal
    from app.services.macro_ingest import upsert_point
    db = SessionLocal()
    try:
        res = upsert_point(db, "fixed_capital_investment", _date(2026, 3, 31), "yoy", -14.3,
                           unit="%", source="Росстат", is_preliminary=True,
                           source_url="https://www.interfax.ru/business/1093663", ingested_via="rosstat")
        return {"result": res}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug seed-fixed-capital-investment-q1-2026: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/seed-weekly-inflation-jul20-2026")
def debug_seed_weekly_inflation_jul20_2026():
    """Разовый сид: недельная инфляция за 14-20 июля 2026 (0,17%). Пробел создала
    моя же чистка 2026-07-25 (purge-implausible-macro-news снёс бракованную точку
    «2,6%» с as_of=2026-07-20 — то был рост цены САХАРА, не инфляция), а корректное
    значение взамен не встало: источник-статья уже в дедупе news-пайплайна.
    ПОЙМАНО ПЕРВЫМ ЖЕ ПРОГОНОМ «ОТК данных» (calendar_weekly_inflation, warn) —
    система заработала как задумано. Значение из первоисточника (interfax.ru/
    business/1104895, 22 июля: «Инфляция в России с 14 по 20 июля составила
    0,17%») — проверено вручную при разборе исходного бага."""
    from datetime import date as _date
    from app.db.session import SessionLocal
    from app.services.macro_ingest import upsert_point
    db = SessionLocal()
    try:
        res = upsert_point(db, "inflation_weekly", _date(2026, 7, 20), "wow", 0.17,
                           unit="%", source="Росстат (via interfax)",
                           source_url="https://www.interfax.ru/business/1104895",
                           ingested_via="news")
        return {"result": res}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug seed-weekly-inflation-jul20-2026: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/fix-inflation-expectations-jun-jul-2026")
def debug_fix_inflation_expectations_jun_jul_2026():
    """Разовый фикс: инфляционные ожидания июнь=12,4% и июль=14,7% (владелец
    2026-07-30: «были 14,7 как и должны быть, а сейчас не то число опять»).
    Причина отката — sync_expectations при РАВНОМ месяце предпочитал XLSX-LLM-путь
    (стабильно выдававший 12,5) детерминированному PDF-парсеру, и ежедневный крон
    06:30 перезаписывал верную точку; приоритет исправлен в macro_cb_sync.py, этот
    эндпоинт возвращает корректные значения немедленно, не дожидаясь крона.
    Значения из бюллетеня инФОМ за июль (опрос 5–16 июля): ожидаемая инфляция на
    год вперёд 14,7% (макс. с марта 2022, +2,3 п.п. к июню 12,4%) — подтверждено
    finance.mail.ru/article/69218843, investfuture.ru (21.07.2026), msk1.ru."""
    from datetime import date as _date
    from app.db.session import SessionLocal
    from app.services.macro_ingest import upsert_point
    db = SessionLocal()
    try:
        r_jun = upsert_point(db, "inflation_expectations", _date(2026, 6, 30), "level", 12.4,
                             unit="%", source="ЦБ РФ (инФОМ)",
                             source_url="https://www.cbr.ru/analytics/dkp/inflationary_expectations/",
                             ingested_via="cbr")
        r_jul = upsert_point(db, "inflation_expectations", _date(2026, 7, 31), "level", 14.7,
                             unit="%", source="ЦБ РФ (инФОМ)",
                             source_url="https://www.cbr.ru/analytics/dkp/inflationary_expectations/",
                             ingested_via="cbr")
        return {"june": r_jun, "july": r_jul}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug fix-inflation-expectations: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/seed-inflation-yoy-jul27-2026")
def debug_seed_inflation_yoy_jul27_2026():
    """Разовый сид: годовая инфляция 5,94% на 27 июля 2026 (оценка Минэка из
    недельного релиза 29 июля; владелец 2026-07-30: «годовая тоже старая — 5,84,
    когда сейчас 5,94»). Системно закрыто расширением macro_weekly_watch (ловец
    теперь пишет оба числа релиза — wow и yoy), этот эндпоинт — немедленный фикс
    точки, если релиз уже ушёл из окна Ленты. Значение подтверждено: interfax.ru/
    business/1106356, bfm.ru/news/613610, akm.ru («годовая выросла до 5,94%»)."""
    from datetime import date as _date
    from app.db.session import SessionLocal
    from app.services.macro_ingest import upsert_point
    db = SessionLocal()
    try:
        res = upsert_point(db, "inflation", _date(2026, 7, 27), "yoy", 5.94,
                           unit="%", source="Минэкономразвития (via interfax)",
                           source_url="https://www.interfax.ru/business/1106356",
                           ingested_via="news")
        return {"result": res}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug seed-inflation-yoy-jul27-2026: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/sector-playbook")
def debug_sector_playbook(sector: str | None = None):
    """Мост «макро → сектор»: доехала ли методичка до рантайма и что из неё берут
    выпуск Обозревателя и патчер карточек.

    🔴 Нужен именно на бою: файл лежит в docs/, а в образ приложения попадает не всё —
    молчаливое «методичка не найдена» выглядело бы как «агент просто пишет хуже»."""
    from app.services.macro_sector_playbook import available, core, for_sector
    out = available()
    out["core_chars"] = len(core())
    if sector:
        block = for_sector(sector)
        out["sector"] = {"name": sector, "chars": len(block), "head": block[:400]}
    return out


@router.post("/debug/repair-macro-series")
def debug_repair_macro_series():
    """Разовый ремонт рядов с неверной метрикой (m2, госрасходы) — см.
    macro_series_repair. Идемпотентно: повторный прогон ничего не найдёт."""
    from app.db.session import SessionLocal
    from app.services.macro_series_repair import repair
    db = SessionLocal()
    try:
        return repair(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug repair-macro-series: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/probe-url")
def debug_probe_url(url: str, contains: str | None = None):
    """Посмотреть глазами боевого сервера, что отдаёт внешний источник.

    🔴 Зачем (2026-08-19). Сеть боевого инстанса и сеть разработчика — разные миры:
    rosstat.gov.ru и metaltorg.ru с моей машины не отвечают вовсе, а cbr.ru отдаёт файл.
    Без этого «источник недоступен» превращается в гадание. Инструмент читающий: только
    GET, только сводка (код, тип, размер) и ссылки на файлы данных — чтобы находить
    machine-readable источник там, где страница выглядит как дашборд без данных
    (так нашёлся monetary_agg.xlsx у ЦБ, заменивший веб-поиск по денежным агрегатам).
    """
    import re as _re
    import httpx as _httpx
    hdr = {"User-Agent": "Mozilla/5.0 (compatible; BasisBot/1.0)"}
    tls = "проверен"
    try:
        r = _httpx.get(url, timeout=30, follow_redirects=True, headers=hdr)
    except Exception as e:  # noqa: BLE001
        # 🔴 Российские госсайты подписаны сертификатом Минцифры, которого нет в
        # доверенных у контейнера: rosstat.gov.ru падает с CERTIFICATE_VERIFY_FAILED.
        # Для ПУБЛИЧНОЙ статистики это приемлемо — читаем без проверки цепочки, но
        # честно помечаем, чтобы это не выглядело как обычное защищённое соединение.
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            return {"error": f"{type(e).__name__}: {e}"}
        try:
            r = _httpx.get(url, timeout=30, follow_redirects=True, headers=hdr, verify=False)
            tls = "БЕЗ проверки сертификата"
        except Exception as e2:  # noqa: BLE001
            return {"error": f"{type(e2).__name__}: {e2}"}
    ctype = r.headers.get("content-type", "")
    out = {"status": r.status_code, "content_type": ctype, "bytes": len(r.content),
           "final_url": str(r.url), "tls": tls}
    if "html" in ctype:
        html = r.text
        links = []
        for u, title in _re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip))"[^>]*>([^<]{0,90})', html):
            title = _re.sub(r"\s+", " ", title).strip()
            if contains and contains.lower() not in (title + " " + u).lower():
                continue
            links.append({"title": title[:90], "url": u[:200]})
        out["files"] = links[:40]
        if contains:
            idx = html.lower().find(contains.lower())
            out["context"] = _re.sub(r"<[^>]+>", " ", html[max(0, idx - 200): idx + 300]) if idx >= 0 else None
    return out


@router.post("/debug/audit-gov-spending")
def debug_audit_gov_spending(year_from: int = 2016, year_to: int = 2025,
                             write: bool = True, threshold_pp: float = 1.0):
    """Сверка годовых госрасходов с исполнением федерального бюджета (Минфин).
    write=false — только показать расхождения, ничего не менять."""
    from app.db.session import SessionLocal
    from app.services.macro_gov_spending_audit import audit
    db = SessionLocal()
    try:
        return audit(db, (year_from, year_to), threshold_pp=threshold_pp, write=write)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug audit-gov-spending: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/watch-macro-levels")
def debug_watch_macro_levels(code: str | None = None, force: bool = False):
    """Добор рядов без машинного источника (M0/M2/M2X, номинальный ВВП, зарплаты Росстата,
    безработица еврозоны/Китая) и расчёт темпов кодом.
    code — только один показатель; force снимает проверку свежести."""
    from app.db.session import SessionLocal
    from app.services.macro_levels_watch import watch_levels
    db = SessionLocal()
    try:
        return watch_levels(db, [code] if code else None, force=force)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug watch-macro-levels: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-weekly-inflation-watch")
def debug_trigger_weekly_inflation_watch(force: bool = False, backfill_weeks: int = 3):
    """Ручной прогон целевого ловца недельной инфляции (macro_weekly_watch.py) —
    тот же код, что гоняет крон ср/чт/пт. Идемпотентен.

    force=1 снимает паузу между попытками по одной неделе (пауза бережёт LLM при
    почасовом кроне, но мешает отлаживать руками). В ответе поле diag: сколько
    результатов дал веб-поиск и на чём сорвалось извлечение."""
    from app.db.session import SessionLocal
    from app.services.macro_weekly_watch import watch_weekly_inflation
    db = SessionLocal()
    try:
        return watch_weekly_inflation(db, backfill_weeks=max(1, min(backfill_weeks, 6)),
                                      force=force)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-weekly-inflation-watch: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/purge-future-macro")
def debug_purge_future_macro():
    """Удаляет точки macro_data_points с as_of далеко в будущем (баг: LLM-извлечение
    иногда путает прогнозную строку на странице ЦБ с фактическим месячным
    значением — see sync_inflation / upsert_point future-date guard). Разовая очистка
    уже накопленного мусора, не гонять регулярно.

    Порог — те же +14 дней, что в upsert_point() (НЕ строго "> сегодня"): 2026-07-25
    этот эндпоинт со строгим порогом снёс заодно 3 ЛЕГИТИМНЫЕ точки (inflation_expectations
    + 2 yahoo-commodities), которые намеренно метятся концом месяца-периода, а публикуются
    за 1-2 недели до конца месяца — см. докстринг upsert_point. Держим оба порога в синхроне."""
    from datetime import date, timedelta
    from app.db.session import SessionLocal
    from app.models.macro import MacroDataPoint
    db = SessionLocal()
    try:
        cutoff = date.today() + timedelta(days=14)
        rows = db.query(MacroDataPoint).filter(MacroDataPoint.as_of > cutoff).all()
        deleted = [{"code": r.indicator_code, "metric": r.metric, "as_of": str(r.as_of), "value": float(r.value)} for r in rows]
        for r in rows:
            db.delete(r)
        db.commit()
        return {"deleted_count": len(deleted), "deleted": deleted}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug purge-future-macro: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/purge-implausible-macro-news")
def debug_purge_implausible_macro_news():
    """Разовая чистка: точки macro_data_points (ingested_via='news') вне диапазона
    min/max текущего config/macro_indicators.json → news_extract. Конфиг мог
    ужесточиться ПОСЛЕ того, как точка уже сохранена (напр. inflation_weekly
    [-2,5]→[-1,2] после бага 2026-07-25: LLM записал рост цены САХАРА за неделю
    (2,6%) как общую недельную инфляцию — реальная была 0,17%) — upsert_point не
    переоценивает уже сохранённые точки заново, только новые вставки/ревизии.
    Трогает ТОЛЬКО ingested_via='news' (официальные точки ЦБ/Росстат/Минфин через
    этот путь не идут вообще, их валидируют свои синки)."""
    from app.db.session import SessionLocal
    from app.models.macro import MacroDataPoint
    from app.services.macro_ingest import load_macro_config
    db = SessionLocal()
    try:
        targets = load_macro_config().get("news_extract", {})
        rows = db.query(MacroDataPoint).filter(MacroDataPoint.ingested_via == "news").all()
        deleted = []
        for r in rows:
            spec = targets.get(r.indicator_code)
            if not spec:
                continue
            val = float(r.value)
            if not (spec["min"] <= val <= spec["max"]):
                deleted.append({"code": r.indicator_code, "metric": r.metric,
                                "as_of": str(r.as_of), "value": val, "source": r.source})
                db.delete(r)
        db.commit()
        return {"deleted_count": len(deleted), "deleted": deleted}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug purge-implausible-macro-news: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-risk-free-rate")
def debug_trigger_risk_free_rate():
    """Ручной запуск update_risk_free_rate() (ОФЗ-1г + ОФЗ-10л → market_params)
    синхронно, без ожидания недельного крона (пн 08:30, moex_coefficients) — для
    первичного наполнения risk_free_10y (используется live_wacc.py для живого
    пересчёта DCF/P-BV×ROE в /financials) сразу после деплоя фичи."""
    from sqlalchemy import text as _text
    from app.db.session import SessionLocal
    from app.services.moex_dividends import update_risk_free_rate
    db = SessionLocal()
    try:
        rate_1y = update_risk_free_rate(db)
        row = db.execute(
            _text("SELECT value, as_of FROM market_params WHERE key = 'risk_free_10y'")
        ).first()
        return {
            "risk_free_1y_pct": rate_1y,
            "risk_free_10y_pct": float(row.value) if row else None,
            "risk_free_10y_as_of": row.as_of.isoformat() if row and row.as_of else None,
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-risk-free-rate: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-calendar")
def debug_trigger_calendar():
    """Ручной запуск refresh_all() календаря событий (Обозреватель → Календарь),
    БЕЗ ожидания фонового джоба после старта контейнера — для диагностики
    (проверить, что дивиденды/отчёты/облигации реально собираются, не гонять
    регулярно: dividends-шаг делает per-ticker запросы к MOEX ISS, минуты)."""
    from app.db.session import SessionLocal
    from app.services.calendar_events import refresh_all
    db = SessionLocal()
    try:
        return refresh_all(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-calendar: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/report-watch-trace")
def debug_report_watch_trace(ticker: str, event_date: str | None = None):
    """Пошаговая трассировка ТОЧНО того кода, что использует process_event: находит
    calendar_event (по event_date ИЛИ, если не задан/не найден, по calendar_event_id
    существующих needs_source-записей — MOEX ir-calendar мог УЖЕ укатить дату вперёд,
    та же история, что раньше была с AFLT), зовёт _source_text, затем ОБА извлечения
    (financial/operational) — чтобы увидеть, где именно рвётся цепочка на бою."""
    from datetime import date as date_cls
    from app.db.session import SessionLocal
    from app.models.calendar_event import CalendarEvent
    from app.models.company import Company
    from app.models.earnings import EarningsReport
    from app.services.report_watch import (_source_text, _extract_financial, _extract_operational)
    from app.services.calendar_events import _load_inn_ticker_map
    db = SessionLocal()
    try:
        ticker_u = ticker.upper()
        events = []
        if event_date:
            ed = date_cls.fromisoformat(event_date)
            events = (db.query(CalendarEvent)
                     .filter(CalendarEvent.ticker == ticker_u, CalendarEvent.event_type == "earnings",
                             CalendarEvent.event_date == ed)
                     .order_by(CalendarEvent.id.desc()).all())
        if not events:
            ce_ids = [r.calendar_event_id for r in
                     db.query(EarningsReport.calendar_event_id)
                     .filter(EarningsReport.ticker == ticker_u, EarningsReport.status == "needs_source",
                             EarningsReport.calendar_event_id.isnot(None)).all()]
            if ce_ids:
                events = db.query(CalendarEvent).filter(CalendarEvent.id.in_(ce_ids)).all()
        company = db.query(Company).filter_by(ticker=ticker_u).first()
        inn = next((i for i, ts in _load_inn_ticker_map().items() if ticker_u in ts), None)
        out = []
        for event in events:
            is_operational = bool(event.status and "операцион" in event.status.lower())
            src = _source_text(db, event, inn)
            entry = {"calendar_event_id": event.id, "source_field_status": event.status,
                     "is_operational_precheck": is_operational, "found_source": bool(src),
                     "source_label": src[1] if src else None,
                     "text_preview": (src[0][:300] if src else None)}
            if src:
                text_blob = src[0]
                fin = _extract_financial(text_blob)
                ops = _extract_operational(text_blob)
                entry["extract_financial_result"] = fin
                entry["extract_operational_result"] = ops
            out.append(entry)
        return {"ticker": ticker_u, "event_date": event_date, "events_found": len(events),
                "inn": inn, "traces": out}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug report-watch-trace: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-report-watch")
def debug_trigger_report_watch(days_back: int = 5, run_girbo: bool = True):
    """Ручной запуск report_watch.refresh() (автообнаружение вышедших отчётов через
    MOEX ir-calendar + Лента новостей + ГИР БО), БЕЗ ожидания дневного крона (20:45) —
    для диагностики. days_back — окно назад по уже прошедшим датам событий.
    run_girbo=False — пропустить полный обход ~261 тикеров ГИР БО (дороже путей 1-2,
    для быстрой точечной проверки MOEX/новостного путей)."""
    from app.db.session import SessionLocal
    from app.services.report_watch import refresh
    db = SessionLocal()
    try:
        return refresh(db, days_back=days_back, run_girbo=run_girbo)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-report-watch: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/backfill-interim-overlay")
def debug_backfill_interim_overlay(ticker: str | None = None, days_back: int | None = None):
    """Бэкфилл: прогнать УЖЕ сохранённые квартальные/полугодовые EarningsReport
    (report_type=quarter, уже с EarningsFigures) через interim_overlay.write() —
    для отчётов, обработанных ДО деплоя авто-довеска (2026-07-31), которые иначе
    никогда не попадут в interim_financials_overlay (write() вызывается только из
    НОВОГО прохода _store_report). Идемпотентно (апсерт «не ухудшай») — безопасно
    гонять повторно и на пересечении с уже обработанными отчётами.
    ticker — точечно один тикер (тест перед массовым прогоном); days_back —
    окно по published_at (без параметра — все квартальные отчёты в БД)."""
    from datetime import date, timedelta
    from app.db.session import SessionLocal
    from app.models.company import Company
    from app.models.earnings import EarningsFigures, EarningsReport
    from app.services import interim_overlay

    db = SessionLocal()
    try:
        q = (db.query(EarningsReport, EarningsFigures, Company)
             .join(EarningsFigures, EarningsFigures.report_id == EarningsReport.id)
             .join(Company, Company.ticker == EarningsReport.ticker)
             .filter(EarningsReport.report_type == "quarter"))
        if ticker:
            q = q.filter(EarningsReport.ticker == ticker.strip().upper())
        if days_back:
            q = q.filter(EarningsReport.published_at >= date.today() - timedelta(days=days_back))
        rows = q.order_by(EarningsReport.published_at).all()

        stats: dict[str, int] = {}
        by_ticker: dict[str, list[str]] = {}
        skipped: dict[str, list[str]] = {}
        for report, efig, company in rows:
            fig = {
                "revenue": float(efig.revenue_ttm) if efig.revenue_ttm is not None else None,
                "ebitda": float(efig.ebitda) if efig.ebitda is not None else None,
                "net_profit": float(efig.net_profit_ttm) if efig.net_profit_ttm is not None else None,
                "net_debt": float(efig.net_debt) if efig.net_debt is not None else None,
            }
            status = interim_overlay.write(db, report, fig, company.name)
            stats[status] = stats.get(status, 0) + 1
            if status in ("created", "updated"):
                by_ticker.setdefault(report.ticker, []).append(f"{report.period}:{status}")
            else:
                skipped.setdefault(status, []).append(f"{report.ticker}:{report.period!r}")
        return {"scanned": len(rows), "stats": stats, "changed_tickers": by_ticker, "skipped_detail": skipped}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug backfill-interim-overlay: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/fetch-wishlist")
def debug_fetch_wishlist(days_back: int = 2):
    """Список «что добыть» для агента-добытчика: свежие отчётные события, где
    (а) источник не найден (needs_source) или (б) разбор есть, но без выручки
    (экстракция получила обрывок). Агент проходит по списку, ищет полный релиз
    и POST-ит текст в /debug/ingest-report-source."""
    from app.db.session import SessionLocal
    from app.services.report_fetcher_job import build_wishlist
    db = SessionLocal()
    try:
        out = build_wishlist(db, days_back=days_back)
        return {"count": len(out), "items": out}
    finally:
        db.close()


@router.post("/debug/trigger-report-fetch")
def debug_trigger_report_fetch(max_tickers: int = 4):
    """Ручной прогон прод-добытчика релизов (report_fetcher_job: код + DeepSeek,
    smart-lab/Лента как источники) — тот же код, что крон. Идемпотентен."""
    from app.db.session import SessionLocal
    from app.services.report_fetcher_job import fetch_missing_reports
    db = SessionLocal()
    try:
        return fetch_missing_reports(db, max_tickers=max_tickers)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-report-fetch: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/ingest-report-source")
def debug_ingest_report_source(payload: dict):
    """Приём полного текста отчётного релиза от агента-добытчика (пилот, владелец
    2026-07-31). Тело: {"ticker", "text", "source_url"?, "period"?, "standard"?}.
    Дальше текст идёт в ТЕКУЩИЙ конвейер (экстракция цифр → богатый дайджест)."""
    from app.db.session import SessionLocal
    from app.services.report_watch import ingest_agent_source
    db = SessionLocal()
    try:
        return ingest_agent_source(
            db, str(payload.get("ticker") or ""), str(payload.get("text") or ""),
            payload.get("source_url"), payload.get("period"), payload.get("standard"))
    except Exception as e:  # noqa: BLE001
        logger.exception("debug ingest-report-source: %s", e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/fetch-article")
def debug_fetch_article(url: str):
    """Проверка фетчабельности полного текста статьи С ПРОД-СЕРВЕРА (egress Timeweb ≠
    локальная машина: анти-боты режут серверные IP-пулы). Возвращает длину и первые
    300 символов того, что реально видит _fetch_article_text."""
    from app.services.report_watch import _fetch_article_text
    t = _fetch_article_text(url)
    return {"ok": bool(t), "chars": len(t) if t else 0, "head": (t or "")[:300]}


@router.post("/debug/redo-report")
def debug_redo_report(ticker: str, days_back: int = 7):
    """Пересоздать РАЗБОР ОТЧЁТА одного или НЕСКОЛЬКИХ тикеров (через запятую,
    напр. ticker=DOMRF,RAGR,YDEX — владелец 2026-08-01: батч перебора после правки
    period-эвристики, один refresh() дешевле N последовательных). Изначально —
    владелец 2026-07-31: «пересоздай Ozon — хочу посмотреть, как будет выглядеть»
    после апгрейда конвейера: полный текст источника + extra_metrics + контекст/
    watch_next.

    Механика: удаляем СВЕЖИЕ processed/extract_failed-записи ВСЕХ перечисленных
    тикеров (дедуп report_watch держится на записях — без удаления событие «уже
    обработано» и повторно не разбирается; figures/digest уходят каскадом по FK),
    затем ОДИН раз гоним refresh() узким окном (охватывает все тикеры сразу — это
    общий проход по календарю/ленте, не ticker-scoped). ГИР БО пропускаем (дорогой
    полный обход, к свежим МСФО-разборам отношения не имеет)."""
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport
    from app.services.report_watch import refresh
    from datetime import date as _date, timedelta as _td
    db = SessionLocal()
    try:
        tickers = [t.strip().upper() for t in ticker.split(",") if t.strip()]
        cutoff = _date.today() - _td(days=days_back)
        rows = (db.query(EarningsReport)
                .filter(EarningsReport.ticker.in_(tickers),
                        EarningsReport.status.in_(("processed", "extract_failed", "needs_source")),
                        EarningsReport.published_at.isnot(None),
                        EarningsReport.published_at >= cutoff).all())
        deleted = len(rows)
        for r in rows:
            db.delete(r)   # ORM-delete → каскад figures/digest по relationship
        db.commit()
        res = refresh(db, days_back=days_back, run_girbo=False)
        return {"tickers": tickers, "deleted": deleted, "refresh": res}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug redo-report %s: %s", ticker, e)
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/reset-report-watch")
def debug_reset_report_watch(ticker: str | None = None):
    """Удаляет needs_source-записи report_watch — ЛЮБОГО пути (calendar_event_id ИЛИ
    market_update_id ИЛИ ни того ни другого, напр. company_rss) — для чистого повторного
    прогона (напр. после правки фетч-каскада/классификации). processed НЕ трогает.
    ticker — сузить до одного тикера (напр. после точечного фикса вроде keyword-ранжирования
    2026-07-14), иначе чистит needs_source по всем."""
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport
    db = SessionLocal()
    try:
        q = db.query(EarningsReport).filter(EarningsReport.status == "needs_source")
        if ticker:
            q = q.filter(EarningsReport.ticker == ticker.upper())
        n = q.delete()
        db.commit()
        return {"deleted": n}
    finally:
        db.close()


@router.post("/debug/purge-girbo-backlog")
def debug_purge_girbo_backlog(period: str | None = "2025"):
    """Удаляет ГИР БО-записи (source='girbo') за указанный период (по умолчанию 2025) —
    владелец 2026-07-14: разовый бэкфилл на ~165 компаний одним пакетом зашумил ленту
    «Отчёты» вперемешку со свежими событиями. Механизм ГИР БО остаётся включённым — новые
    годовые отчёты (2026 и далее) будут капать по одной записи, не пачкой. period=None —
    удалить ВСЕ ГИР БО-записи независимо от периода (осторожно)."""
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport
    db = SessionLocal()
    try:
        q = db.query(EarningsReport).filter(EarningsReport.source == "girbo")
        if period:
            q = q.filter(EarningsReport.period == period)
        n = q.delete()
        db.commit()
        return {"deleted": n}
    finally:
        db.close()


@router.post("/debug/purge-news-junk-reports")
def debug_purge_news_junk_reports(dry_run: bool = True, report_id: int | None = None,
                                  list_all: bool = False, ticker: str | None = None):
    """Ретроактивная чистка мусорных «отчётов», созданных news-путём report_watch до
    ужесточения детекта (2026-07-25, жалоба владельца: в «Отчётах» дивиденды/отраслевые
    новости вместо отчётности). Применяет НОВЫЙ детект (_NEWS_REPORT_DETECT_RE + порог
    ≤2 тикеров у исходной новости) к записям source='market_updates': не проходит —
    запись удаляется (figures/digest уйдут каскадом). Это разблокирует и настоящие
    отчёты: мусорная запись держала дедуп ±4 дня (кейс НОВАТЭКа). dry_run=True (дефолт)
    — только показать, что будет удалено; запускать боевое удаление с dry_run=false,
    затем POST /debug/trigger-report-watch для пересоздания реальных отчётов."""
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport
    from app.models.market import MarketUpdate
    from app.services.report_watch import _NEWS_REPORT_DETECT_RE
    db = SessionLocal()
    try:
        # report_id — точечное удаление ОДНОЙ записи по id, минуя детект-эвристику:
        # для пограничных кейсов, которые прошли и строгий детект, и LLM-гейт
        # (реальный пример: рыночный дайджест «акции Полюса +10,73%» с отчётными
        # словами в summary). ORM-delete — каскад figures/digest.
        if report_id is not None:
            rep = db.get(EarningsReport, report_id)
            if not rep:
                return {"dry_run": dry_run, "matched": 0, "reports": []}
            out = [{"id": rep.id, "ticker": rep.ticker, "period": rep.period,
                    "standard": rep.standard, "news_title": None}]
            if not dry_run:
                db.delete(rep)
                db.commit()
            return {"dry_run": dry_run, "matched": 1, "reports": out}
        # ticker — удалить ВСЕ записи одного тикера (любого source, включая
        # smartlab/ir-пути без market_update_id): для чистого ПЕРЕПРОГОНА разбора
        # после улучшения пайплайна (владелец 2026-07-26: «перепрогнать НОВАТЭК/
        # Северсталь/ММК — посмотреть, как будет выглядеть»). После удаления —
        # POST /debug/trigger-report-watch пересоздаст записи новым кодом.
        if ticker:
            reps = (db.query(EarningsReport)
                    .filter(EarningsReport.ticker == ticker.upper()).all())
            out = [{"id": r.id, "ticker": r.ticker, "period": r.period,
                    "standard": r.standard, "news_title": None} for r in reps]
            if not dry_run:
                for r in reps:
                    db.delete(r)  # ORM-delete — каскад figures/digest
                db.commit()
            return {"dry_run": dry_run, "matched": len(out), "reports": out}
        rows = (db.query(EarningsReport, MarketUpdate)
                .join(MarketUpdate, MarketUpdate.id == EarningsReport.market_update_id)
                .filter(EarningsReport.source == "market_updates").all())
        # list_all=true — показать ВСЕ market_updates-записи с id (ничего не удаляя):
        # чтобы найти id пограничной записи для точечного report_id-удаления
        # (детект её пропускает, а глазами по заголовку новости мусор виден сразу).
        if list_all:
            return {"dry_run": True, "matched": len(rows), "reports": [
                {"id": r.id, "ticker": r.ticker, "period": r.period, "standard": r.standard,
                 "news_title": (mu.title or "")[:120]} for r, mu in rows]}
        junk = []
        for rep, mu in rows:
            blob = f"{mu.title} {mu.summary or ''}"
            ok = _NEWS_REPORT_DETECT_RE.search(blob) and len(mu.affected_tickers or []) <= 2
            if not ok:
                junk.append((rep, mu.title))
        out = [{"id": r.id, "ticker": r.ticker, "period": r.period, "standard": r.standard,
                "news_title": t[:120]} for r, t in junk]
        if not dry_run:
            for r, _ in junk:
                db.delete(r)  # ORM-delete — каскад figures/digest из relationship
            db.commit()
        return {"dry_run": dry_run, "matched": len(out), "reports": out}
    finally:
        db.close()


@router.post("/debug/fix-mislabeled-operational-reports")
def debug_fix_mislabeled_operational_reports(dry_run: bool = True):
    """Ретроактивный фикс: до правки report_watch._store_report (2026-07-28,
    жалоба владельца — кейс GMKN, объёмы производства металлов сохранились с
    standard='МСФО') фоллбэк на операционный разбор МЕНЯЛ, какой экстрактор
    реально сработал, но НЕ чинил report.standard/report_type — они оставались
    такими, какими их угадали ДО того, как стал виден текст. Признак записи с
    этим багом — EarningsFigures.extracted_fields содержит ключ 'kpis'
    (уникальная сигнатура _extract_operational, у _extract_financial такого
    ключа нет вообще), но standard при этом НЕ 'операционные результаты' —
    новый код (см. report_watch.py) больше так не создаёт записи, но старые
    остаются неисправленными без этого прогона. dry_run=True (дефолт) —
    только показать, что будет исправлено."""
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport, EarningsFigures
    db = SessionLocal()
    try:
        rows = (db.query(EarningsReport, EarningsFigures)
                .join(EarningsFigures, EarningsFigures.report_id == EarningsReport.id)
                .filter(EarningsReport.standard != "операционные результаты").all())
        mismatched = [(r, f) for r, f in rows if isinstance(f.extracted_fields, dict) and "kpis" in f.extracted_fields]
        out = [{"id": r.id, "ticker": r.ticker, "period": r.period,
                "old_standard": r.standard, "old_report_type": r.report_type} for r, _ in mismatched]
        if not dry_run:
            for r, _ in mismatched:
                r.standard = "операционные результаты"
                r.report_type = "operating"
            db.commit()
        return {"dry_run": dry_run, "matched": len(out), "reports": out}
    finally:
        db.close()


@router.post("/debug/trigger-company-rss")
def debug_trigger_company_rss(days_back: int = 90, force_reset: bool = False):
    """Точечный запуск ТОЛЬКО company_rss-пути (см. _COMPANY_RSS) — в обход дорогого
    полного refresh() (тот сканирует Ленту новостей за days_back дней целиком, минуты
    на больших days_back). Быстрая проверка RSS первоисточников (ROSN/TATN).
    force_reset=True — удалить существующие company_rss-записи перед прогоном (для
    чистого повторного теста после правки классификации/экстракции)."""
    from app.db.session import SessionLocal
    from app.models.company import Company
    from app.models.earnings import EarningsReport
    from app.services.report_watch import _due_company_rss_reports, process_company_rss_item
    db = SessionLocal()
    if force_reset:
        db.query(EarningsReport).filter_by(source="company_rss").delete()
        db.commit()
    try:
        companies = {c.ticker: c for c in db.query(Company).all()}
        items = _due_company_rss_reports(days_back)
        res = {"found": len(items), "created": 0, "needs_source": 0, "exists": 0, "errors": 0}
        details = []
        for item in items:
            company = companies.get(item["ticker"])
            if not company:
                continue
            try:
                r = process_company_rss_item(db, item, company,
                                             float(company.market_cap) if company.market_cap else None)
                res[r] = res.get(r, 0) + 1
                details.append({"ticker": item["ticker"], "result": r, "text_preview": item["text"][:150]})
            except Exception as e:  # noqa: BLE001
                res["errors"] += 1
                db.rollback()
                details.append({"ticker": item["ticker"], "result": f"error:{type(e).__name__}"})
        return {"summary": res, "details": details}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-company-rss: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-smartlab-detect")
def debug_trigger_smartlab_detect(days_back: int = 60, max_pages: int = 5):
    """Точечный запуск ТОЛЬКО smart-lab-детекта дат (см. _due_smartlab_rows) — в обход
    дорогого полного refresh(). Показывает найденные строки БЕЗ записи в БД (dry-run) —
    для быстрой проверки охвата/качества детекта."""
    from app.db.session import SessionLocal
    from app.models.company import Company
    from app.services.report_watch import _due_smartlab_rows, _due_ir_rows
    db = SessionLocal()
    try:
        companies = {c.ticker: c for c in db.query(Company).all()}
        ir_covered = {(r["secid"], r["event_date"]) for r in _due_ir_rows(companies, days_back)}
        rows = _due_smartlab_rows(companies, days_back, max_pages)
        new_coverage = [r for r in rows if (r["secid"], r["event_date"]) not in ir_covered]
        return {"found_total": len(rows), "outside_moex_ir_calendar": len(new_coverage),
                "rows": [{"ticker": r["secid"], "date": r["event_date"].isoformat(),
                         "description": r["description"],
                         "already_in_moex_ir_calendar": (r["secid"], r["event_date"]) in ir_covered}
                        for r in rows]}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-smartlab-detect: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/report-watch-diag")
def debug_report_watch_diag(ticker: str, event_date: str):
    """Диагностика report_watch: показывает source/status по тикеру + живой прогон
    _from_market_updates на этот тикер/дату (не трогая БД) — понять, была ли найдена
    Лента новостей или упало извлечение LLM."""
    from datetime import date as date_cls
    from app.db.session import SessionLocal
    from app.models.earnings import EarningsReport
    from app.services.report_watch import (_from_market_updates, _from_skrin, _from_azipi,
                                           _girbo_org_id, _girbo_annual_reports, _girbo_figures)
    from app.services.calendar_events import _load_inn_ticker_map
    db = SessionLocal()
    try:
        ed = date_cls.fromisoformat(event_date)
        reports = [{"period": r.period, "standard": r.standard, "status": r.status,
                    "source": r.source, "source_url": r.source_url, "created_at": r.created_at.isoformat()}
                   for r in db.query(EarningsReport).filter_by(ticker=ticker.upper())
                   .order_by(EarningsReport.created_at.desc()).limit(5).all()]
        mu = _from_market_updates(db, ticker.upper(), ed)
        inn = next((i for i, ts in _load_inn_ticker_map().items() if ticker.upper() in ts), None)
        sk = _from_skrin(inn, ed) if inn else None
        az = _from_azipi(inn, ed) if inn else None
        girbo = None
        if inn:
            org_id = _girbo_org_id(inn)
            if org_id:
                girbo_reports = _girbo_annual_reports(org_id)
                if girbo_reports:
                    latest = max(girbo_reports, key=lambda r: r.get("period") or "")
                    girbo = {"org_id": org_id, "period": latest.get("period"),
                             "actualBfoDate": latest.get("actualBfoDate"), "figures": _girbo_figures(latest)}
        return {"stored_reports": reports, "live_market_updates_text": (mu or "")[:2000],
                "live_skrin_text": (sk or "")[:500], "live_azipi_text": (az or "")[:800],
                "live_girbo": girbo, "inn": inn}
    finally:
        db.close()


@router.post("/debug/trigger-macro-sync")
def debug_trigger_macro_sync():
    """Ручной запуск sync_cb() (ставка/прогноз ЦБ/ОНДКП-сценарии/макроопрос/
    инфляция/ожидания/M2) синхронно, БЕЗ ожидания дневного крона (06:30) — для
    разовой проверки после фикса, не гонять регулярно (несколько LLM-вызовов,
    минуты). force=True на дорогих (staleness-gated) шагах, чтобы точно
    прогнать сейчас, а не пропустить по "not_stale"."""
    from app.db.session import SessionLocal
    from app.services.macro_ingest import seed_indicators
    from app.services.macro_cb_sync import (sync_rate_meeting, sync_forecast, sync_forecast_annual,
                                             sync_expert_survey, sync_inflation, sync_expectations,
                                             sync_credit_m2, sync_business_climate)
    from app.services.macro_minfin_sync import sync_gov_spending
    from app.services.macro_rosstat import sync_ppi
    from app.services.macro_hh_sync import sync_hh_index
    from app.services.macro_tankermap_sync import sync_urals
    from app.services.macro_wb_commodities_sync import sync_wb_commodities
    from app.services.macro_yahoo_commodities_sync import sync_yahoo_commodities
    from app.services.macro_metaltorg_steel_sync import sync_metaltorg_steel
    from app.services.macro_idex_diamond_sync import sync_idex_diamond
    db = SessionLocal()
    out = {}
    try:
        # seed_indicators() штатно живёт внутри дневного _macro_job() (06:30) —
        # здесь дублируем явно, иначе новые indicator_code из macro_indicators.json
        # не попадут в справочник до завтрашнего утра, а ряды из sync_wb_commodities
        # ниже будут писаться в data-таблицу без соответствующей строки-справочника
        # (commodity-price-history отдаёт "индикатор не найден", несмотря на данные).
        try:
            out["seed_indicators"] = {"new": seed_indicators(db)}
        except Exception as e:  # noqa: BLE001
            logger.exception("debug trigger-macro-sync: seed_indicators упал: %s", e)
            db.rollback()
            out["seed_indicators"] = {"error": f"{type(e).__name__}: {e}"}
        for key, fn in (
            ("rate", lambda: sync_rate_meeting(db)), ("forecast", lambda: sync_forecast(db)),
            ("forecast_annual", lambda: sync_forecast_annual(db, force=True)),
            ("expert_survey", lambda: sync_expert_survey(db, force=True)),
            ("inflation", lambda: sync_inflation(db)), ("expectations", lambda: sync_expectations(db)),
            ("credit_m2", lambda: sync_credit_m2(db, months_back=12)),
            ("business_climate", lambda: sync_business_climate(db)),
            ("gov_spending", lambda: sync_gov_spending(db, months_back=4)),
            ("ppi", lambda: sync_ppi(db, months_back=6)),
            ("hh_index", lambda: sync_hh_index(db, months_back=18)),
            ("urals", lambda: sync_urals(db, period="max")),
            ("wb_commodities", lambda: sync_wb_commodities(db, months_back=120)),
            ("yahoo_commodities", lambda: sync_yahoo_commodities(db)),
            ("monetary_agg", lambda: __import__("app.services.macro_cb_monetary_sync",
                                                fromlist=["x"]).sync_monetary_aggregates(db)),
            ("metaltorg_steel", lambda: sync_metaltorg_steel(db)),
            ("idex_diamond", lambda: sync_idex_diamond(db)),
        ):
            try:
                out[key] = fn()
            except Exception as e:  # noqa: BLE001
                logger.exception("debug trigger-macro-sync: %s упал: %s", key, e)
                db.rollback()
                out[key] = {"error": f"{type(e).__name__}: {e}"}
        return out
    finally:
        db.close()


@router.post("/debug/trigger-macro-interpretation")
def debug_trigger_macro_interpretation():
    """Ручной запуск macro_interpreter.generate() (ИИ-«Оценка ситуации» в
    Макроэкономике) синхронно, без ожидания суточного крона (07:15,
    macro_interpretation) — для проверки/разовой перегенерации."""
    from app.db.session import SessionLocal
    from app.services.macro_interpreter import generate
    db = SessionLocal()
    try:
        row = generate(db)
        return {"generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "model_used": row.model_used}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-interpretation: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-macro-analytics")
def debug_trigger_macro_analytics():
    """Ручной запуск macro_analytics.process() (мониторинг PDF-обзоров ЦБ/ЦМАКП)
    синхронно, БЕЗ ожидания дневного крона (06:30, часть _macro_job) — для разовой
    проверки/добора после фикса или простоя (напр. если контейнер был неактивен и
    крон пропустил несколько дней). Не гонять часто — сетевые запросы + LLM на
    каждый новый документ."""
    from app.db.session import SessionLocal
    from app.services.macro_analytics import process
    db = SessionLocal()
    try:
        return process(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-analytics: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/purge-shallow-geo-digest")
def debug_purge_shallow_geo_digest():
    """Одноразовая чистка: удаляет карточки geo_digest_articles, сохранённые ДО фикса
    глубины пересказа (пустой key_takeaways — старый узкий формат на огрызке текста).
    После удаления source_url больше не в known → следующий trigger-geo-digest
    переобработает те же статьи заново уже с полным текстом и подробным промптом."""
    from app.db.session import SessionLocal
    from app.models.geo_digest import GeoDigestArticle
    from sqlalchemy import or_
    db = SessionLocal()
    try:
        removed = (db.query(GeoDigestArticle)
                  .filter(or_(GeoDigestArticle.key_takeaways.is_(None),
                              GeoDigestArticle.key_takeaways == []))
                  .delete(synchronize_session=False))
        db.commit()
        return {"removed": removed}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("debug purge-shallow-geo-digest: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/fix-cmasf-source-typo")
def debug_fix_cmasf_source_typo():
    """Одноразовая чистка: source='cmasf' (опечатка) → 'cmakp' в существующих
    записях macro_analytics_docs. Фронтенд (SOURCE_CHIPS/SOURCE_LABELS) ждёт
    ключ 'cmakp' — из-за опечатки фильтр «ЦМАКП» не находил ни одной статьи и
    ярлык показывал сырое 'cmasf'. Конфиг backend/config/macro_indicators.json
    уже исправлен — эта чистка только для уже сохранённых строк."""
    from app.db.session import SessionLocal
    from app.models.macro import MacroAnalyticsDoc
    db = SessionLocal()
    try:
        updated = (db.query(MacroAnalyticsDoc)
                  .filter(MacroAnalyticsDoc.source == "cmasf")
                  .update({"source": "cmakp"}, synchronize_session=False))
        db.commit()
        return {"updated": updated}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("debug fix-cmasf-source-typo: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-geo-digest")
def debug_trigger_geo_digest():
    """Ручной запуск geo_digest.refresh() (карточки-статьи Рыбарь/re:russia/Carnegie
    по регионам геополитики + институциональная среда) синхронно, без ожидания
    дневного крона (21:00, часть _geo_job). Для разовой проверки после деплоя/фикса."""
    from app.db.session import SessionLocal
    from app.services.geo_digest import refresh
    db = SessionLocal()
    try:
        return refresh(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-geo-digest: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-geo-frontline-sync")
def debug_trigger_geo_frontline_sync():
    """Ручной запуск geo_isw_frontline_sync.sync_isw_frontline() синхронно, без
    ожидания крона (8:15/20:15 МСК). Для разовой проверки после деплоя новых
    полей (напр. control_fill_geojson) — старт-задача сама пересинкует ТОЛЬКО
    если строки ещё нет вовсе, новое поле на уже существующей строке само не
    подхватится до следующего кронового тика без этого ручного триггера."""
    from app.db.session import SessionLocal
    from app.services.geo_isw_frontline_sync import sync_isw_frontline
    db = SessionLocal()
    try:
        return sync_isw_frontline(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-geo-frontline-sync: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-geo-digest-backfill-strikes")
def debug_trigger_geo_digest_backfill_strikes(days: int = 7):
    """Разовый догоняющий прогон geo_digest.backfill_strike_events() по уже
    сохранённым статьям последних `days` дней — закрывает пробел для статей,
    сохранённых ДО того, как основной пайплайн стал извлекать strike_events/
    territorial_claims (или пока фикс NameError ещё не был на бою), а дедуп
    по source_url не даёт им повторно пройти через refresh()."""
    from app.db.session import SessionLocal
    from app.services.geo_digest import backfill_strike_events
    db = SessionLocal()
    try:
        return backfill_strike_events(db, days=days)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-geo-digest-backfill-strikes: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/methodology-shelf")
def debug_methodology_shelf(doc: str | None = None, section: str | None = None):
    """Что лежит на полке методичек и читается ли оно из контейнера.

    Без параметров — список методичек с оглавлениями. С doc — оглавление одной.
    С doc и section — текст раздела (то же, что получит агент инструментом).
    """
    from app.services import methodology as M
    if doc and section:
        return M.read_section(doc, section)
    if doc:
        return M.outline(doc)
    return {d: {"название": M.REGISTRY[d].title,
                "когда_открывать": M.REGISTRY[d].when_to_use,
                **{k: v for k, v in M.outline(d).items() if k != "оглавление"}}
            for d in sorted(M.REGISTRY)}


@router.post("/debug/trigger-scout")
def debug_trigger_scout(kind: str = "geo"):
    """Запустить ТОЛЬКО разведку, без написания выпуска.

    🔴 Зачем отдельно. Полный прогон слоя — это разведка плюс длинный вызов
    писателя; он не укладывается в таймаут запроса, и по молчащему ответу нельзя
    понять, что именно не сработало. Разведка запускается сама по себе, быстро
    и с внятной статистикой: сколько фактов собрано, какие разделы методичек
    открыты, чего не хватило.
    """
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        if kind == "macro":
            from app.services.macro_interpreter import gather_snapshot
            from app.services import macro_scout
            d = macro_scout.run(db, gather_snapshot(db))
        else:
            from app.services.barometer_daily import gather_articles
            from app.services import geo_scout
            d = geo_scout.run(db, gather_articles(db))
        if not isinstance(d, dict):
            return {"ok": False, "note": "досье не собрано — смотри /api/debug/geo-dossier"}
        return {"ok": True, "статистика": d.get("_stats"),
                "методички": d.get("methodology_used"),
                "фактов_примеры": [f.get("claim") for f in (d.get("facts") or [])[:5]],
                "пробелы": d.get("gaps")}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-scout: %s", e)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/geo-dossier")
def debug_geo_dossier(limit: int = 3, kind: str = ""):
    """Последние досье разведки — то, что агент СОБРАЛ до написания текста.

    🔴 Зачем смотреть сюда. Когда блок на витрине выглядит бедно, надо знать,
    что случилось: разведка не нашла материал или нашла, но аналитик им не
    воспользовался. Это разные поломки, и по готовому тексту их не различить.

    kind — какой слой: geodoss (геополитика, по умолчанию), macdoss (макро).
    """
    from app.models.geo import BarometerVersion
    from app.services.geo_scout import DOSSIER_KIND
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rows = (db.query(BarometerVersion)
                .filter(BarometerVersion.kind == (kind or DOSSIER_KIND))
                .order_by(BarometerVersion.id.desc()).limit(max(1, min(limit, 10))).all())
        return {"досье": [{"id": r.id, "статус": r.status,
                           "создано": r.created_at.isoformat() if r.created_at else None,
                           "заметки": r.gate_notes,
                           "payload": r.payload} for r in rows]}
    finally:
        db.close()


@router.get("/debug/methodology-status")
def debug_methodology_status():
    """Доехали ли методички до контейнера — и какого они размера.

    🔴 Зачем отдельная проверка. Сервисы читают методички по пути от корня
    РЕПОЗИТОРИЯ (`docs/...`), а образ бэкенда собирается из папки `backend/` —
    то есть `docs/` в контейнер может не попасть вовсе. Загрузчик при этом не
    падает: он ловит OSError, пишет предупреждение в лог и возвращает пустую
    строку. Снаружи это выглядит как нормальная работа — выпуск собирается,
    эндпоинт отвечает 200, — но аналитический слой работает БЕЗ методики.
    Проверка возвращает длину: ноль здесь значит «методички нет», а не «всё ок».
    """
    import os as _os
    out = {}
    try:
        from app.services.barometer_daily import _METHODOLOGY, _load_methodology
        out["geopolitics"] = {"path": _METHODOLOGY,
                              "exists": _os.path.exists(_METHODOLOGY),
                              "chars": len(_load_methodology())}
    except Exception as e:  # noqa: BLE001
        out["geopolitics"] = {"error": str(e)}
    try:
        from app.services.macro_interpreter import _methodology
        out["macro"] = {"chars": len(_methodology() or "")}
    except Exception as e:  # noqa: BLE001
        out["macro"] = {"error": str(e)}
    out["cwd"] = _os.getcwd()
    out["есть_ли_docs_рядом"] = _os.path.isdir("docs")
    return out


@router.post("/debug/trigger-barometer-daily")
def debug_trigger_barometer_daily():
    """Ручной запуск ежедневной пересборки ГЕО-барометра (обычно крон 21:50).
    Владелец 2026-08-01: «слой 1 — ежедневный крон, где DeepSeek всё обновляет».
    Возвращает id/status/заметки гейта; при пустой ленте — сообщение, барометр
    не трогается."""
    from app.db.session import SessionLocal
    from app.services.barometer_daily import rebuild
    db = SessionLocal()
    try:
        row = rebuild(db)
        if row is None:
            return {"result": "лента пуста — барометр не трогали"}
        return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes,
                "as_of": (row.payload or {}).get("as_of")}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-barometer-daily: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-geo-profile")
def debug_trigger_geo_profile():
    """Ручной запуск НЕДЕЛЬНОГО портрета очагов (крон geo_profile, вс 22:10):
    стороны и цели, баланс сил, связки с макро и институтами в обе стороны.
    Дорогой прогон — три reasoning-вызова, по одному на очаг."""
    from app.db.session import SessionLocal
    from app.services.geo_conflict_profile import rebuild
    db = SessionLocal()
    try:
        row = rebuild(db)
        if row is None:
            return {"result": "ни один очаг не собран (лента пуста?)"}
        return {"id": row.id, "status": row.status, "gate_notes": row.gate_notes,
                "scopes": [k for k in (row.payload or {}) if not k.startswith("_")]}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-geo-profile: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


# 🔴 ФОНОВЫЙ ЗАПУСК, А НЕ ОЖИДАНИЕ В HTTP. Первая версия этих триггеров ждала
# прогон целиком и на бою не отработала ни разу: замеры направлений — это четыре
# reasoning-вызова подряд (~15-20 минут), а прокси Timeweb обрывает долгий запрос
# гораздо раньше (та же причина, по которой POST /market/macro/interpretation
# отвечает 202 и генерит в фоне — см. комментарий там). Клиент получает ответ
# сразу, результат смотрит через GET /market/institutions/domains|profile.
_INST_RUNS: dict = {}


def _inst_bg(name: str, fn) -> dict:
    import threading
    if _INST_RUNS.get(name, {}).get("running"):
        return {"running": True, "note": "уже выполняется — второй дорогой прогон не запускаю"}

    def _worker():
        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            row = fn(db)
            _INST_RUNS[name] = {"running": False,
                                "result": (f"версия {row.id} ({row.status})" if row
                                           else "не собрано — мало материалов"),
                                "gate_notes": (row.gate_notes or [])[:10] if row else []}
        except Exception as e:  # noqa: BLE001
            logger.exception("debug %s: %s", name, e)
            _INST_RUNS[name] = {"running": False, "result": f"ошибка: {type(e).__name__}: {e}"}
        finally:
            db.close()

    _INST_RUNS[name] = {"running": True, "result": None}
    threading.Thread(target=_worker, name=name, daemon=True).start()
    return {"running": True, "note": "запущено в фоне, смотри GET-эндпоинт раздела"}


@router.post("/debug/trigger-nonequity-facts")
def debug_trigger_nonequity_facts(kind: str = "bond", batch: int = 4, secid: str | None = None):
    """Свежесть разборов ОБЛИГАЦИЙ (kind=bond) или ФОНДОВ (kind=fund).
    Крон nonequity_facts, 6:35. Правит числа (YTM/цена/спред), НЕ вердикт."""
    from app.db.session import SessionLocal
    from app.services.card_prose_patcher import run_nonequity_facts
    db = SessionLocal()
    try:
        return run_nonequity_facts(db, kind, batch=batch, only_secid=secid)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-nonequity-facts: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/export-overlays")
def debug_export_overlays(tab: str | None = None, limit: int = 60, offset: int = 0):
    """Выгрузка ОПУБЛИКОВАННЫХ оверлеев прозы — для консолидации обратно в репозиторий.

    🔴 Зачем. Патчи и перезаписи живут в БД (файлы на Timeweb эфемерны), и с каждой
    публикацией репозиторий отстаёт: на 2026-08-08 разошлись уже 250 блоков (226 —
    макро). Следующая сессия открывает файл, не зная про оверлей, правит устаревший
    текст и молча откатывает всю накопленную свежесть. Лечится периодическим
    переносом оверлеев в файлы; этот эндпоинт — источник данных для переноса.

    Отдаёт ПОСЛЕДНЮЮ опубликованную версию на (тикер, вкладку)."""
    from app.db.session import SessionLocal
    from app.models.geo import CardProseOverlay
    from sqlalchemy import func
    db = SessionLocal()
    try:
        latest = (db.query(CardProseOverlay.ticker, CardProseOverlay.tab,
                           func.max(CardProseOverlay.id).label("mid"))
                  .filter(CardProseOverlay.status == "published"))
        if tab:
            latest = latest.filter(CardProseOverlay.tab == tab)
        latest = latest.group_by(CardProseOverlay.ticker, CardProseOverlay.tab).subquery()
        rows = (db.query(CardProseOverlay)
                .join(latest, CardProseOverlay.id == latest.c.mid)
                .order_by(CardProseOverlay.ticker, CardProseOverlay.tab)
                .limit(limit).offset(offset).all())
        return {"count": len(rows), "offset": offset,
                "items": [{"id": r.id, "ticker": r.ticker, "tab": r.tab,
                           "kind": r.kind, "md": r.patched_md,
                           "created_at": r.created_at.isoformat() if r.created_at else None}
                          for r in rows]}
    finally:
        db.close()


@router.get("/debug/card-claims")
def debug_card_claims(ticker: str | None = None, limit: int = 30):
    """Проверяемые утверждения карточки и их устаревание — БЕЗ LLM, кодом.

    Без тикера — очередь: чьи утверждения отстали от календаря сильнее всего.
    Меряет не «верное ли число» (этого без внешнего источника не узнать), а ГОД, на
    который утверждение ссылается: разбор говорит «в 2024 году добыто столько-то», а
    данные за 2025 уже вышли."""
    from app.services.card_claims import card_claims, stale_queue
    if ticker:
        return card_claims(ticker)
    return {"queue": stale_queue(limit=limit)}


@router.get("/debug/overlay-divergence")
def debug_overlay_divergence():
    """Сколько блоков прозы разошлось между БД и репозиторием — здоровье цикла.

    🔴 Зачем метрика. Консолидация (перенос оверлеев в файлы) — ручной трёхшаговый
    прогон, и расхождение копится снова с каждым патчем. 2026-08-08 оно доросло до
    250 блоков незамеченным, и заодно 14 карточек месяц отдавали урезанный разбор.
    Чтобы это не повторилось молча, число видно одним запросом: выросло за сотню —
    пора гонять `scripts/consolidate_overlays.py`.
    """
    from app.db.session import SessionLocal
    from app.models.geo import CardProseOverlay
    from sqlalchemy import func
    db = SessionLocal()
    try:
        rows = (db.query(CardProseOverlay.tab, func.count(func.distinct(CardProseOverlay.ticker)))
                .filter(CardProseOverlay.status == "published")
                .group_by(CardProseOverlay.tab).all())
        by_tab = {t: n for t, n in rows}
        return {"diverged_blocks": sum(by_tab.values()), "by_tab": by_tab,
                "hint": "больше ~100 — пора запускать scripts/consolidate_overlays.py"}
    finally:
        db.close()


@router.post("/debug/mark-overlays-consolidated")
def debug_mark_overlays_consolidated(ids: str, status: str = "consolidated"):
    """Пометить перенесённые оверлеи как consolidated — после того, как файлы уже
    ЗАДЕПЛОЕНЫ. Порядок важен: пометить раньше деплоя значит на время показать старый
    файл. `current_overlay` берёт только published, поэтому consolidated перестают
    подменять файл, но остаются в истории для отката."""
    from app.db.session import SessionLocal
    from app.models.geo import CardProseOverlay
    try:
        id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()][:500]
    except ValueError:
        return {"error": "bad ids"}
    if not id_list:
        return {"error": "пустой список"}
    db = SessionLocal()
    try:
        n = (db.query(CardProseOverlay)
             .filter(CardProseOverlay.id.in_(id_list),
                     CardProseOverlay.status == "published")
             # 🔴 Значение обязано влезать в колонку: status — String(16), и
             # «superseded_by_file» (18 знаков) валил запрос 500-й ошибкой. Короткое
             # «file_wins» несёт тот же смысл: файл победил, оверлей больше не активен.
             .update({CardProseOverlay.status: status if status in
                      ("consolidated", "file_wins") else "consolidated"},
                     synchronize_session=False))
        db.commit()
        return {"marked": n}
    finally:
        db.close()


@router.post("/debug/trigger-sector-scout")
def debug_trigger_sector_scout(code: str | None = None, dry: bool = False):
    """Добор отраслевых показателей, недоступных парсерам, — через агента-добытчика.
    dry=true — только показать, что нашлось, без записи в ряд."""
    from app.db.session import SessionLocal
    from app.services.sector_scout import run_scout
    db = SessionLocal()
    try:
        return run_scout(db, only_code=code, dry=dry)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-sector-scout: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-tab-rewrite")
def debug_trigger_tab_rewrite(tab: str, ticker: str | None = None, batch: int = 1):
    """Перезапись вывода для вкладок finance|geo|institutions|governance|business.
    Сигналы разные: у финансов — вышедший отчётный период, у остальных — повторные
    отказы патчера (проза структурно разошлась, точечная правка уже не помогает)."""
    from app.db.session import SessionLocal
    from app.services.card_rewriter import run_tab_rewrites
    db = SessionLocal()
    try:
        return run_tab_rewrites(db, tab, batch=batch, only_ticker=ticker)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-tab-rewrite: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-markets-rewrite")
def debug_trigger_markets_rewrite(ticker: str | None = None, batch: int = 2,
                                  use_web: bool = True):
    """Перезапись выводов «Рынков» там, где цена товара ушла в другую фазу цикла.
    Якорь — цена, записанная в самой карточке (market.json), против живого ряда."""
    from app.db.session import SessionLocal
    from app.services.card_rewriter import run_markets_rewrites
    db = SessionLocal()
    try:
        return run_markets_rewrites(db, batch=batch, only_ticker=ticker, use_web=use_web)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-markets-rewrite: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-card-rewrite")
def debug_trigger_card_rewrite(ticker: str | None = None, batch: int = 2):
    """ПЕРЕЗАПИСЬ ВЫВОДА вкладки «Макроэкономика» (третья ступень лестницы).

    Запускается на голове очереди дрейфа — там, где расхождение переворачивает
    рассуждение, а не меняет цифру. Champion/challenger: новая версия публикуется,
    только если все числа заземлены, триггер закрыт и критик не нашёл регрессий."""
    from app.db.session import SessionLocal
    from app.services.card_rewriter import run_macro_rewrites
    db = SessionLocal()
    try:
        return run_macro_rewrites(db, batch=batch, only_ticker=ticker)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-card-rewrite: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-futures-asset-facts")
def debug_trigger_futures_asset_facts(batch: int = 4, code: str | None = None):
    """Свежесть разборов БАЗОВЫХ АКТИВОВ фьючерсов (крон futures_asset_facts, 6:20).
    Приводит цены и даты в разборе к живым котировкам контрактов и спот-рядам."""
    from app.db.session import SessionLocal
    from app.services.card_prose_patcher import run_futures_asset_facts
    db = SessionLocal()
    try:
        return run_futures_asset_facts(db, batch=batch, only_code=code)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-futures-asset-facts: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


from pydantic import BaseModel


class _ProbeUrlsIn(BaseModel):
    urls: list[str]
    marker: str | None = None   # слово, которое ОБЯЗАНО быть в теле (проверка содержимого)
    snippet: int = 0            # сколько знаков ТЕКСТА вернуть (0 — не возвращать)
    links: str | None = None    # регэксп: вернуть подходящие href (напр. "\\.xlsx?$")


@router.post("/debug/probe-urls")
def debug_probe_urls(body: _ProbeUrlsIn):
    """Пакетная проверка адресов С БОЕВОГО СЕРВЕРА: прямо → через релей.

    Зачем. Реестр источников (config/source_registry_*.md) проверялся с ноутбука,
    и его вердикты неполны в обе стороны: worldsteel с ноутбука давал 000, а с боя
    работает; eia_press наоборот. Плюс у нас есть обход — Cloudflare-воркер
    (WEB_FETCH_PROXY_URL), которым реестр не пользовался вовсе.

    Возвращает по каждому адресу: код и размер при ПРЯМОМ запросе, то же через
    релей, и есть ли в теле marker (защита от «200 с заглушкой»: SPA-каркас и
    страница‑ошибка тоже отдают 200 и приличный размер).
    """
    import httpx
    from app.services.agent_web import via_proxy
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"}
    out = []
    for u in body.urls[:60]:   # потолок на вызов: 60 адресов ≈ пара минут
        rec = {"url": u}
        for mode in ("direct", "relay"):
            target = u if mode == "direct" else via_proxy(u)
            if mode == "relay" and target == u:
                rec["relay"] = "нет релея (WEB_FETCH_PROXY_URL не задан)"
                continue
            try:
                with httpx.Client(timeout=20, follow_redirects=True, verify=False) as c:
                    r = c.get(target, headers=ua)
                body_txt = r.text[:200000]
                rec[mode] = {"code": r.status_code, "size": len(r.content),
                             "marker": (body.marker.lower() in body_txt.lower())
                             if body.marker else None}
                if body.links:
                    # Ссылки на файлы данных. Без них страницу госсайта, недоступного
                    # с дев-машины, разобрать нечем: текст показывает навигацию, а
                    # числа лежат в приложенных xls/csv, и их адреса не угадываются.
                    try:
                        hrefs = re.findall(r'href=["\']([^"\']+)["\']', body_txt, re.I)
                        pat = re.compile(body.links, re.I)
                        seen, hits = set(), []
                        for h in hrefs:
                            if pat.search(h) and h not in seen:
                                seen.add(h)
                                hits.append(h)
                            if len(hits) >= 25:
                                break
                        rec[mode]["links"] = hits
                    except re.error:
                        rec[mode]["links"] = ["bad_regex"]
                if body.snippet:
                    # Текст без разметки: понять, что на странице, размер не даёт —
                    # SPA-каркас и таблица со статистикой весят одинаково.
                    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body_txt)
                    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
                    rec[mode]["text"] = re.sub(r"\s+", " ", txt).strip()[:body.snippet]
            except Exception as e:  # noqa: BLE001
                rec[mode] = {"error": type(e).__name__}
            if mode == "direct" and isinstance(rec.get("direct"), dict) \
                    and rec["direct"].get("code") == 200 and rec["direct"].get("size", 0) > 2000:
                rec["relay"] = "не понадобился"
                break
        out.append(rec)
    return {"checked": len(out), "results": out}


@router.post("/debug/trigger-dividends-from-listing")
def debug_trigger_dividends_from_listing():
    """Перенос ПРОШЕДШИХ объявленных отсечек из листинга (rates.csv) в историю выплат.
    Нужен потому, что ISS /dividends.json перестал отдавать свежие выплаты."""
    from app.db.session import SessionLocal
    from app.services.moex_dividends import sync_dividends_from_listing
    db = SessionLocal()
    try:
        return sync_dividends_from_listing(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug dividends-from-listing: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/probe-feed")
def debug_probe_feed(url: str, method: str = "rss"):
    """Проверка ленты С БОЕВОГО IP нашим же парсером — сколько записей, какая свежая.

    Зачем эндпоинт, а не curl с ноутбука. Часть источников недоступна с локальной
    машины, но открывается с сервера, и наоборот: международные (МЭА, ОПЕК) режут
    антиботом, а несколько российских (peretok.ru, np-sr.ru, portnews.ru, rosugol.ru)
    дают с ноутбука код 000 — похоже на обратный геоблок, и с Timeweb шанс есть.
    Проверять надо ИМЕННО нашим парсером: типовая ловушка — HTML-страница 404 под
    кодом 200, при которой лента выглядит рабочей и молча отдаёт пустоту.
    """
    from datetime import date as _date
    from app.services.geo_digest import _fetch_rss, _fetch_wp_json, _parse_date
    try:
        src = {"key": "probe", "url": url}
        arts = _fetch_wp_json(src) if method == "wp_json" else _fetch_rss(src)
    except Exception as e:  # noqa: BLE001
        return {"url": url, "ok": False, "error": f"{type(e).__name__}: {e}"}
    dates = sorted([d for d in (_parse_date(a.get("date_raw")) for a in arts) if d], reverse=True)
    newest = dates[0] if dates else None
    return {
        "url": url, "ok": bool(arts), "articles": len(arts),
        "newest": newest.isoformat() if newest else None,
        "age_days": (_date.today() - newest).days if newest else None,
        "no_date": sum(1 for a in arts if not _parse_date(a.get("date_raw"))),
        "sample": [{"title": a["title"][:110], "date": a.get("date_raw", "")[:30],
                    "text_len": len(a.get("text") or "")} for a in arts[:3]],
    }


@router.post("/debug/trigger-sector-digest")
def debug_trigger_sector_digest(max_new: int = 30):
    """Ручной запуск ОТРАСЛЕВОЙ ЛЕНТЫ (крон sector_digest, 8:15 и 20:15): обзоры,
    прогнозы и аналитика рынков от отраслевых источников (МЭА/ОПЕК/EIA/ассоциации).
    Синхронно — видно, сколько статей отсеяно и по каким отраслям разложено."""
    from app.db.session import SessionLocal
    from app.services.sector_digest import refresh
    db = SessionLocal()
    try:
        return refresh(db, max_new=max_new)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-sector-digest: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-sector-barometer")
def debug_trigger_sector_barometer():
    """Ручной запуск ОТРАСЛЕВОГО БАРОМЕТРА (крон sector_barometer, вс 21:30):
    состояние 12 отраслей рынка РФ. Четыре reasoning-прохода — в ФОНЕ."""
    from app.services.sector_barometer import rebuild
    return JSONResponse(status_code=202, content=_inst_bg("sector_barometer", rebuild))


@router.post("/debug/trigger-institutions-domains")
def debug_trigger_institutions_domains():
    """Замеры институтов ПО НАПРАВЛЕНИЯМ (крон institutions_domains, вс 21:55):
    собственность, суды, законотворчество, госдоля, монополизация, конкуренция,
    регуляторная нагрузка, рыночные институты, конфликты бизнеса и государства,
    лоббизм. Четыре reasoning-прохода — запускается в ФОНЕ, ответ мгновенный."""
    from app.services.institutions_domains import rebuild
    return JSONResponse(status_code=202, content=_inst_bg("institutions_domains", rebuild))


@router.post("/debug/trigger-institutions-profile")
def debug_trigger_institutions_profile():
    """Институциональный портрет (крон institutions_profile, вс 22:20) — ось
    «правила ↔ доступ», связь с ценой акций, факторы в обе стороны, кто
    выигрывает и проигрывает, зоны передела, связки с макро и гео. Запускать
    ПОСЛЕ замеров направлений: портрет использует их как вход. В ФОНЕ."""
    from app.services.institutions_profile import rebuild
    return JSONResponse(status_code=202, content=_inst_bg("institutions_profile", rebuild))


@router.post("/debug/trigger-env-card-interp")
def debug_trigger_env_card_interp(tab: str = "both", ticker: str | None = None,
                                  batch: int = 8):
    """Доводка вкладок карточек под текущее состояние Обозревателя.
    tab: geo | institutions | macro | both (гео+институты) | all (и макро тоже).
    ticker — прогнать одну компанию (полезно для проверки).
    В ФОНЕ: это партия LLM-вызовов."""
    from app.services.card_prose_patcher import (
        run_geo_env_interp, run_inst_env_interp, run_macro_env_interp,
    )

    def _run(db):
        out = {}
        if tab in ("geo", "both", "all"):
            out["geo"] = run_geo_env_interp(db, batch=batch, only_ticker=ticker)
        if tab in ("institutions", "both", "all"):
            out["institutions"] = run_inst_env_interp(db, batch=batch, only_ticker=ticker)
        if tab in ("macro", "all"):
            out["macro"] = run_macro_env_interp(db, batch=batch, only_ticker=ticker)
        if tab in ("markets", "all"):
            from app.services.card_prose_patcher import run_markets_env_interp
            out["markets"] = run_markets_env_interp(db, batch=batch, only_ticker=ticker)
        if tab in ("governance", "all"):
            from app.services.card_prose_patcher import run_gov_env_interp
            out["governance"] = run_gov_env_interp(db, batch=batch, only_ticker=ticker)
        # возвращаем объект-заглушку с полями, которые ждёт _inst_bg
        return type("R", (), {"id": "-", "status": "done", "gate_notes": [str(out)[:400]]})()

    return JSONResponse(status_code=202, content=_inst_bg("env_card_interp", _run))


@router.get("/debug/egress-check")
def debug_egress_check(url: str, timeout: int = 15, contains: str | None = None):
    """Доступен ли ИСТОЧНИК С БОЕВОГО СЕРВЕРА (а не с машины разработчика).

    🔴 Зачем: при сборке реестра источников выяснилось, что гос.сайты РФ (ФАС,
    Росстат, ФТС, Минпромторг) с дев-машины не открываются — TLS виснет до
    таймаута, похоже на гео-ограничение. С боевого сервера в РФ они, скорее
    всего, доступны. Значит доступность нельзя мерить локально: иначе рабочий
    источник попадёт в реестр как «недоступен» и мы не станем его подключать.

    Отдельно проверяется НАЛИЧИЕ КОНТЕНТА, а не только код ответа: e-disclosure
    сейчас отдаёт 200 и 372 КБ JS-заглушки без данных — по коду и размеру это
    выглядит как успех, и молчаливая пустота уходит в парсер.
    """
    import httpx
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    out: dict = {"url": url}
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout,
                          headers={"User-Agent": ua}) as c:
            r = c.get(url)
        body = r.text or ""
        out.update({
            "status": r.status_code,
            "final_url": str(r.url),
            "size": len(r.content or b""),
            "content_type": r.headers.get("content-type", ""),
        })
        low = body.lower()
        # Признаки того, что вместо данных пришёл антибот-щит
        out["looks_like_challenge"] = any(k in low for k in (
            "just a moment", "checking your browser", "cf-challenge",
            "enable javascript", "<noscript><meta http-equiv=\"refresh\""))
        if contains:
            out["contains"] = contains in body
        out["verdict"] = ("challenge" if out["looks_like_challenge"]
                          else "ok" if r.status_code == 200 and out["size"] > 2000
                          else "suspicious")
    except Exception as e:  # noqa: BLE001
        out.update({"status": None, "error": f"{type(e).__name__}: {e}", "verdict": "unreachable"})
    return out


@router.get("/debug/institutions-runs")
def debug_institutions_runs():
    """Состояние фоновых прогонов институтов: идёт / чем закончился."""
    return _INST_RUNS or {"note": "прогонов в этой сессии сервера не было"}


@router.post("/debug/trigger-geo-verification")
def debug_trigger_geo_verification():
    """Ручной прогон «ОТК данных» геополитики (крон geo_verification, 22:30).
    Без LLM и быстрый — первое, что стоит дёрнуть при жалобе «в геополитике
    данные неверные / блок пустой»."""
    from app.db.session import SessionLocal
    from app.services.geo_verification import run_verification
    db = SessionLocal()
    try:
        return run_verification(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-geo-verification: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-macro-business-split")
def debug_trigger_macro_business_split(limit: int = 200):
    """Разовый проход geo_digest.split_macro_business() — разложить уже накопленные
    target="macro" статьи на macro/business после появления раздела «Бизнес»
    (владелец, 2026-07-31). Новые статьи основной пайплайн раскладывает сам;
    этот эндпоинт нужен для ИСТОРИИ, накопленной до разделения. Идемпотентен —
    смотрит только на target="macro", повторный запуск безопасен."""
    from app.db.session import SessionLocal
    from app.services.geo_digest import split_macro_business
    db = SessionLocal()
    try:
        return split_macro_business(db, limit=limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-business-split: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/sanitize-analyst-notes")
def debug_sanitize_analyst_notes(dry_run: bool = True):
    """Комплаенс-свип (аудит 2026-07-26, персона нашла на карточке SBER
    «Базовая рекомендация — держать/покупать на просадках ниже 270 руб.»):
    вычищает из analyst_note (таблица company_analyses) ПРЕДЛОЖЕНИЯ с
    рекомендательной лексикой — конституция Basis запрещает «купить/продать»,
    это же ограничение закона об инвестсоветниках. Генератор ai_analysis.py
    уже исправлен (жёсткий запрет в промпте) — это догон по уже записанному.
    dry_run=true (дефолт) — только показать, что будет вырезано."""
    import re as _re
    from app.db.session import SessionLocal
    from app.models.company import CompanyAnalysis, Company

    # Лексика ИМЕННО рекомендаций-действий; дисклеймеры («не является
    # рекомендацией купить/продать») НЕ должны попадать — их выделяет
    # отрицание рядом, проверяем и его.
    rec = _re.compile(r"рекоменд|покупа|докупа|продава|держать|фиксир\w* прибыл|"
                       r"входить в позици|просадк", _re.IGNORECASE)
    neg = _re.compile(r"не являє|не являетс|не рекоменда|без рекоменда|нет рекоменда",
                      _re.IGNORECASE)
    db = SessionLocal()
    try:
        touched = []
        for row, ticker in (db.query(CompanyAnalysis, Company.ticker)
                            .join(Company, Company.id == CompanyAnalysis.company_id).all()):
            note = row.analyst_note or ""
            if not note or not rec.search(note):
                continue
            sentences = _re.split(r"(?<=[.!?])\s+", note)
            kept = [s for s in sentences if not (rec.search(s) and not neg.search(s))]
            new_note = " ".join(kept).strip() or None
            if new_note != note:
                touched.append({"ticker": ticker, "removed":
                                [s for s in sentences if s not in kept]})
                if not dry_run:
                    row.analyst_note = new_note
        if not dry_run:
            db.commit()
        return {"dry_run": dry_run, "touched": len(touched), "details": touched[:50]}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("sanitize-analyst-notes: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-company-signals")
def debug_trigger_company_signals():
    """Ручной прогон сигнальной шины «поток → карточки» (company_signals):
    Лента (affected_tickers) + дайджест (LLM-маппинг тикеров, вкл. инсайд-TG).
    Идемпотентно (дедуп). См. docs/observer-source-map.md."""
    from app.db.session import SessionLocal
    from app.services.company_signals import refresh
    db = SessionLocal()
    try:
        return refresh(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-company-signals: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-rating-agencies")
def debug_trigger_rating_agencies(acra_limit: int = 15, nkr_limit: int = 25,
                                  acra_dates: bool = False):
    """Ручной прогон ингестора рейтинговых действий АКРА/НКР → сигналы карточек
    (rating_action, вкладка «Облигации») + освежение официального agency_rating
    бумаг по ISIN/имени эмитента. Идемпотентно (дедуп по URL релиза).
    acra_dates=true — тянуть точные даты из релизов АКРА (медленно, ~10с/релиз)."""
    from app.db.session import SessionLocal
    from app.services.rating_agencies import refresh
    db = SessionLocal()
    try:
        return refresh(db, acra_limit=acra_limit, nkr_limit=nkr_limit, acra_dates=acra_dates)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-rating-agencies: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-card-consumer")
def debug_trigger_card_consumer(signal_id: int | None = None, sample: str | None = None):
    """Ручной прогон consumer-агента: точные сигналы (rating_action/earnings от
    официальных источников) → addendum вкладки карточки под код-гейтом. v1 белый
    список источников (не fuzzy-Лента). Публикация — по флагу CARD_CONSUMER_PUBLISH
    (иначе draft, на карточку не идёт).
    signal_id — прогнать агента на КОНКРЕТНОМ сигнале (минуя фильтр батча);
    sample=rating_action|earnings — взять СВЕЖАЙШИЙ сигнал типа (любой важности)
    для пред-полётного просмотра качества; иначе полный прогон батча."""
    from app.db.session import SessionLocal
    from app.services.card_consumer_agent import run_consumer, run_for_signal
    from app.models.geo import CompanySignal
    db = SessionLocal()
    try:
        sig = None
        if signal_id is not None:
            sig = db.query(CompanySignal).get(signal_id)
        elif sample:
            sig = (db.query(CompanySignal)
                   .filter(CompanySignal.signal_type == sample,
                           CompanySignal.trust == "official")
                   .order_by(CompanySignal.created_at.desc()).first())
        if signal_id is not None or sample:
            if not sig:
                return {"error": "signal not found"}
            row = run_for_signal(db, sig)
            if row is None:
                return {"result": "cooldown", "ticker": sig.ticker, "tab": sig.card_tab}
            return {"signal": {"id": sig.id, "ticker": sig.ticker, "title": sig.title},
                    "status": row.status, "content": row.content,
                    "gate_notes": row.gate_notes, "tokens": row.tokens_used}
        return run_consumer(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-card-consumer: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/card-consumer-addenda")
def debug_card_consumer_addenda(ticker: str | None = None, limit: int = 20):
    """Посмотреть последние addendum'ы consumer-агента (любой статус) — для
    пред-полётного просмотра выборки перед включением публикации."""
    from app.db.session import SessionLocal
    from app.models.agent_addendum import AgentAddendum
    db = SessionLocal()
    try:
        q = db.query(AgentAddendum).filter(AgentAddendum.kind == "signal_addendum")
        if ticker:
            q = q.filter(AgentAddendum.ticker == ticker.upper())
        rows = q.order_by(AgentAddendum.created_at.desc()).limit(min(limit, 50)).all()
        return {"count": len(rows), "addenda": [
            {"ticker": r.ticker, "status": r.status, "content": r.content,
             "gate_notes": r.gate_notes, "tokens": r.tokens_used,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]}
    finally:
        db.close()


@router.get("/debug/prose-overlays-status")
def debug_prose_overlays_status(days_back: int = 14, limit: int = 30):
    """Смотровое окно авто-свежести прозы (владелец 2026-07-31: «интерпретация была,
    но по-моему ничего не изменилось»): счётчики по kind/status за окно + последние
    записи с причинами гейта. Раньше единственным следом прогонов был logger.info —
    с прода его не видно, и «ok» хартбита не говорил, публиковалось ли что-то."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    from app.db.session import SessionLocal
    from app.models.geo import CardProseOverlay
    db = SessionLocal()
    try:
        since = _dt.now(_tz.utc) - _td(days=days_back)
        rows = (db.query(CardProseOverlay)
                .filter(CardProseOverlay.created_at >= since)
                .order_by(CardProseOverlay.created_at.desc()).limit(500).all())
        counters: dict = {}
        for r in rows:
            counters[f"{r.kind}/{r.status}"] = counters.get(f"{r.kind}/{r.status}", 0) + 1
        return {
            "days_back": days_back, "total": len(rows), "counters": counters,
            "recent": [{
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "ticker": r.ticker, "tab": r.tab, "kind": r.kind, "status": r.status,
                "change_note": (r.change_note or "")[:200],
                "gate_notes": (r.gate_notes or [])[:3],
            } for r in rows[:limit]],
        }
    finally:
        db.close()


@router.post("/debug/trigger-macro-facts")
def debug_trigger_macro_facts(batch: int = 12, ticker: str | None = None):
    """Ручной прогон макро-фактов карточек (run_macro_facts): устаревшие ставка/
    инфляция/ожидания в macro-прозе → факт-патч от живых рядов. Идемпотентен
    (ретрай-кулдаун 4 дня на тикер)."""
    from app.db.session import SessionLocal
    from app.services.card_prose_patcher import run_macro_facts
    db = SessionLocal()
    try:
        return run_macro_facts(db, batch=batch, only_ticker=ticker)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-facts: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-macro-interp")
def debug_trigger_macro_interp(batch: int = 8, ticker: str | None = None):
    """Ручной прогон смысловой доводки макро-вкладок (run_macro_interp)."""
    from app.db.session import SessionLocal
    from app.services.card_prose_patcher import run_macro_interp
    db = SessionLocal()
    try:
        return run_macro_interp(db, batch=batch, only_ticker=ticker)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-macro-interp: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/downgrade-legacy-high-news")
def debug_downgrade_legacy_high_news(before: str = "2026-08-02T15:30:00"):
    """Разовый чистый переход на рекалиброванную шкалу важности Ленты (владелец
    2026-08-02): записи, размеченные СТАРОЙ шкалой (инфлированный high — 16 из 40),
    опускаются high→medium, чтобы вкладка «Важное» сразу показывала только новую
    семантику (экстраординарное), а не вчерашнюю рутину с бейджем «важное».
    before — граница (UTC): момент деплоя рекалибровки; новее — не трогаем."""
    from datetime import datetime as _dt
    from app.db.session import SessionLocal
    from app.models.market import MarketUpdate
    db = SessionLocal()
    try:
        cutoff = _dt.fromisoformat(before)
        n = (db.query(MarketUpdate)
             .filter(MarketUpdate.importance == "high",
                     MarketUpdate.published_at < cutoff)
             .update({MarketUpdate.importance: "medium"}, synchronize_session=False))
        db.commit()
        return {"downgraded": n, "before": before}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("debug downgrade-legacy-high-news: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-prose-patcher")
def debug_trigger_prose_patcher(signal_id: int | None = None, kind: str = "fact",
                                weekly: bool = False, ticker: str | None = None,
                                tab: str | None = None):
    """Ручной прогон патчера прозы (авто-свежесть). Без параметров — дневной проход
    ФАКТОВ. weekly=true — недельный интерпретационный проход по входному потоку.
    signal_id — факт-патч на КОНКРЕТНОМ сигнале (пред-полёт). ticker+tab —
    интерпретация одной вкладки по её недельному потоку (пред-полёт качества)."""
    from app.db.session import SessionLocal
    from app.services.card_prose_patcher import (
        run_daily_facts, run_for_signal, run_weekly_interp,
        run_interp_for_tab, _week_flow)
    from app.models.geo import CompanySignal
    db = SessionLocal()

    def _row(row):
        if row is None:
            return {"result": "skipped/cooldown (нет прозы / уже отражено / не мапится)"}
        return {"status": row.status, "tab": row.tab, "kind": row.kind,
                "change_note": row.change_note, "gate_notes": row.gate_notes,
                "tokens": row.tokens_used, "evidence": row.evidence,
                "patched_preview": (row.patched_md or "")[:400] if row.status == "published" else None}
    try:
        if ticker and tab:
            return _row(run_interp_for_tab(db, ticker, tab, _week_flow(db, ticker, tab)))
        if signal_id is not None:
            sig = db.query(CompanySignal).get(signal_id)
            if not sig:
                return {"error": "signal not found"}
            return _row(run_for_signal(db, sig, kind=kind))
        if weekly:
            return run_weekly_interp(db)
        return run_daily_facts(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-prose-patcher: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-barometer-reviser")
def debug_trigger_barometer_reviser(force: bool = True):
    """Ручной прогон автономного ревизора барометров (SHADOW — пишет draft/
    rejected, на бой НЕ публикует; план docs/autonomous-barometer-plan.md).
    force=true игнорирует триггер-условия (для проверки), false — как крон
    (только если сработал сенсор situation_overlay)."""
    from app.db.session import SessionLocal
    from app.services.barometer_reviser import run_all
    db = SessionLocal()
    try:
        return run_all(db, force=force)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-barometer-reviser: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-situation-overlay")
def debug_trigger_situation_overlay(window_days: int = 10):
    """Ручной прогон оверлея «текущая ситуация по ленте» (гео 3 очага +
    институты). Fail-closed: результат с published=false означает, что
    комплаенс-фильтр/пустая лента заблокировали выпуск — это НЕ ошибка."""
    from app.db.session import SessionLocal
    from app.services.situation_overlay import generate
    db = SessionLocal()
    try:
        row = generate(db, window_days=window_days)
        return {"id": row.id, "published": row.published,
                "blocked_reason": row.blocked_reason,
                "scopes": list((row.blocks or {}).keys()),
                "source_snapshot": row.source_snapshot}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-situation-overlay: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-news-strikes")
def debug_trigger_news_strikes(hours: int = 48):
    """Ручной прогон extract_strikes_from_news() — извлечение ударов из ОБЩЕЙ
    Ленты новостей (market_updates) за последние `hours` часов. Основной кейс:
    догон пропущенных событий (Тюменский НПЗ, 2026-07-25 — был в ленте РБК/
    Интерфакса, но не в гео-источниках дайджеста). Дедуп на persist-слое —
    повторный вызов дубли не плодит."""
    from app.db.session import SessionLocal
    from app.services.geo_digest import extract_strikes_from_news
    db = SessionLocal()
    try:
        return extract_strikes_from_news(db, hours=hours, limit=80)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-news-strikes: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-chronicle-backfill")
def debug_trigger_chronicle_backfill():
    """Разовый/периодический бэкфилл аналитической летописи из обоих источников
    (важные новости market_updates + статьи geo_digest_articles). Идемпотентно."""
    from app.db.session import SessionLocal
    from app.services.chronicle import backfill
    db = SessionLocal()
    try:
        return backfill(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug chronicle-backfill: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/chronicle-stats")
def debug_chronicle_stats():
    """Сводка по летописи: сколько записей, разбивка по жанру/важности, топ-темы."""
    from app.db.session import SessionLocal
    from sqlalchemy import text as _t
    db = SessionLocal()
    try:
        total = db.execute(_t("SELECT count(*) FROM chronicle_entries")).scalar()
        by_kind = dict(db.execute(_t("SELECT kind, count(*) FROM chronicle_entries GROUP BY kind")).fetchall())
        by_imp = dict(db.execute(_t("SELECT coalesce(importance,'—'), count(*) FROM chronicle_entries GROUP BY 1")).fetchall())
        themes = db.execute(_t("""
            SELECT t, count(*) FROM chronicle_entries,
              jsonb_array_elements_text(CASE WHEN jsonb_typeof(themes)='array' THEN themes ELSE '[]'::jsonb END) AS t
            GROUP BY t ORDER BY 2 DESC LIMIT 12""")).fetchall()
        tagged = db.execute(_t("SELECT count(*) FROM chronicle_entries WHERE jsonb_typeof(tickers)='array'")).scalar()
        return {"total": total, "by_kind": by_kind, "by_importance": by_imp,
                "with_tickers": tagged, "top_themes": [{"theme": r[0], "n": r[1]} for r in themes]}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-lenta-cleanup")
def debug_trigger_lenta_cleanup(keep_days: int = 30):
    """Ретеншен Ленты: удалить строки market_updates старше keep_days (важное сперва
    страхуется в летопись). Разовый/ручной запуск дневной чистки."""
    from app.db.session import SessionLocal
    from app.services.news_pipeline import cleanup_market_updates
    db = SessionLocal()
    try:
        return cleanup_market_updates(db, keep_days=keep_days)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug lenta-cleanup: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.get("/debug/chronicle-preview")
def debug_chronicle_preview(ticker: str, sectors: str = "", themes: str = "",
                            days: int = 365, limit: int = 12):
    """Что видит агент через query_chronicle по тикеру (+ опц. секторы/темы через
    запятую). Read-only превью летописи для проверки/прозрачности."""
    from app.db.session import SessionLocal
    from app.services.agent_tools import _query_chronicle
    db = SessionLocal()
    try:
        sec = [s.strip() for s in sectors.split(",") if s.strip()]
        thm = [t.strip() for t in themes.split(",") if t.strip()]
        return _query_chronicle(db, ticker.upper(), sec or None, thm or None, days, limit)
    finally:
        db.close()


@router.post("/debug/trigger-instrument-history")
def debug_trigger_instrument_history(asset_class: str = Query("fund"), days_back: int = Query(25, ge=1, le=400),
                                      date_from: str | None = Query(None, description="ISO-дата — точный левый край окна (переопределяет days_back), для чанкованного бэкафилла без повторной прокачки уже загруженных дней"),
                                      date_till: str | None = Query(None, description="ISO-дата — правый край окна, по умолчанию сегодня")):
    """Ручной запуск load_range() для одного класса instrument_history синхронно —
    для разового закрытия дыры после фикса SOURCES (напр. MOEX перевёл фонды с
    борда TQTF на TQBR 2026-06-22, нужно было закрыть разрыв с даты перевода без
    ожидания следующего ночного крона с окном в 14 дней). Не гонять регулярно на
    больших days_back — по дню на запрос к MOEX ISS с паузой между вызовами."""
    from datetime import date, timedelta
    from app.db.session import SessionLocal
    from app.services.instrument_history import load_range, SOURCES
    if asset_class not in SOURCES:
        return {"error": f"unknown asset_class {asset_class!r}, expected one of {list(SOURCES)}"}
    db = SessionLocal()
    try:
        today = date.today()
        till = date.fromisoformat(date_till) if date_till else today
        frm = date.fromisoformat(date_from) if date_from else today - timedelta(days=days_back)
        n = load_range(db, asset_class, frm, till)
        return {"asset_class": asset_class, "date_from": frm.isoformat(), "date_till": till.isoformat(), "rows_written": n}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-instrument-history: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-refresh-funds")
def debug_trigger_refresh_funds():
    """Ручной запуск refresh_funds() синхронно — для разовой проверки после
    фикса борда TQTF→TQBR (см. trigger-instrument-history), не ждать до 06:00
    ночного asset_data_refresh."""
    from app.db.session import SessionLocal
    from app.services.asset_data import refresh_funds
    db = SessionLocal()
    try:
        n = refresh_funds(db)
        return {"funds_in_db": n}
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-refresh-funds: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-news")
def debug_trigger_news():
    """Ручной запуск news_pipeline.run_pipeline() синхронно, БЕЗ ожидания
    крона (7/13/19/1 МСК) — для диагностики зависшей ленты новостей.
    Возвращает счётчики (kept/rejected/undecided) — если undecided > 0 и
    kept == 0, это почти всегда сбой LLM-шага фильтрации (DeepSeek/прокси),
    не отсутствие новых новостей в RSS."""
    from app.db.session import SessionLocal
    from app.services.news_pipeline import run_pipeline
    db = SessionLocal()
    try:
        return run_pipeline(db)
    except Exception as e:  # noqa: BLE001
        logger.exception("debug trigger-news: %s", e)
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@router.post("/debug/trigger-index-backfill")
def debug_trigger_index_backfill(tickers: str = Query(..., description="через запятую, напр. RGBI,RVI,RUSFAR"),
                                  days_back: int = Query(365, ge=1, le=1500)):
    """Разовый глубокий бэкафилл index_history для НОВЫХ тикеров (напр. RGBI/RVI/
    RUSFAR*/секторальные MOEXOG..MOEXRE, добавленные в MARKET_PULSE_TICKERS 2026-07-11
    для блока «Обзор рынка» + индекса страха/жадности) — обычный ночной
    catch_up_history берёт только последние 30 дней для тикера без истории, для
    MA125/перцентилей за год нужна разовая более глубокая докачка. fetch_index_history
    отдаёт весь диапазон за один вызов к MOEX ISS (не по дню, как instrument_history) —
    дёшево, без чанкования."""
    from datetime import date, timedelta
    from app.db.session import SessionLocal
    from app.services.moex_history import fetch_index_history, upsert_index_rows
    tlist = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not tlist:
        return {"error": "tickers пуст"}
    db = SessionLocal()
    out = {}
    try:
        today = date.today()
        start = today - timedelta(days=days_back)
        for t in tlist:
            try:
                rows = fetch_index_history(t, start, today)
                n = upsert_index_rows(db, t, rows)
                db.commit()
                out[t] = {"rows_written": n}
            except Exception as e:  # noqa: BLE001
                db.rollback()
                out[t] = {"error": f"{type(e).__name__}: {e}"}
        return out
    finally:
        db.close()


@router.get("/debug/users-stats")
def users_stats():
    """Сводка по регистрациям на платформе — сколько людей завело аккаунт и что делают.

    ЗАЧЕМ: владелец 2026-08-01 спросил, как смотреть количество зарегистрированных.
    Раньше это можно было узнать ТОЛЬКО прямым запросом в базу — то есть практически
    никак без разработчика. Аналитика посещений (Метрика) на этот вопрос не отвечает:
    она считает визиты, а не аккаунты, и не знает, что человек сделал внутри.

    🔴 БЕЗ ПЕРСОНАЛЬНЫХ ДАННЫХ. Отдаются только агрегаты: почты, имена и любые поля,
    по которым можно опознать человека, сюда НЕ ПОПАДАЮТ. Эндпоинт живёт под /api/debug/,
    который закрывается заголовком X-Debug-Token — если DEBUG_API_TOKEN не задан в
    окружении, ручка открыта всем, а число клиентов — сведения не для публики.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import text
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        def scalar(sql: str, **params):
            try:
                return int(db.execute(text(sql), params).scalar() or 0)
            except Exception:  # noqa: BLE001 — таблицы может не быть на старой БД
                db.rollback()
                return None

        since = lambda d: (now - timedelta(days=d)).isoformat()  # noqa: E731

        # 🔴 СЛУЖЕБНЫЕ АККАУНТЫ СЧИТАЕМ ОТДЕЛЬНО. Владелец 2026-08-01 поймал меня на том,
        # что «20 зарегистрировано» — цифра, вводящая в заблуждение: из них 12 на
        # example.com (claude-test-*, test_bench-*, qa-*, obs_test-*, tier-prod-check —
        # следы тестовых прогонов, в том числе моих), один QA на @inbasis.ru и четыре
        # аккаунта самого владельца. Живых внешних людей — единицы.
        # Смешивать их в одном числе нельзя: на такой основе принимаются неверные
        # продуктовые выводы, что и произошло.
        SERVICE = ("email LIKE '%@example.com' OR email LIKE 'qa-%' "
                   "OR email LIKE 'test_%' OR email LIKE '%@inbasis.ru'")
        REAL = f"NOT ({SERVICE})"

        total = scalar("SELECT count(*) FROM users")
        stats = {
            "живых_аккаунтов": scalar(f"SELECT count(*) FROM users WHERE {REAL}"),
            "служебных_и_тестовых": scalar(f"SELECT count(*) FROM users WHERE {SERVICE}"),
            "всего_строк_в_таблице": total,
            "активных": scalar("SELECT count(*) FROM users WHERE is_active"),
            "по_тарифу": {},
            # Приток считаем ТОЛЬКО по живым: тестовые прогоны создают аккаунты пачками
            # (24 июля — шесть за несколько минут) и рисуют несуществующий рост.
            "новых_живых_за": {
                "сутки": scalar(f"SELECT count(*) FROM users WHERE {REAL} AND created_at >= :d", d=since(1)),
                "неделю": scalar(f"SELECT count(*) FROM users WHERE {REAL} AND created_at >= :d", d=since(7)),
                "месяц": scalar(f"SELECT count(*) FROM users WHERE {REAL} AND created_at >= :d", d=since(30)),
            },
            # Регистрация без единого действия — это не клиент, а строка в таблице.
            # Портфель и сохранённый фильтр показывают, что человек реально пользовался.
            "дошли_до_действия_живые": {
                "создали_портфель": scalar(
                    "SELECT count(DISTINCT p.user_id) FROM portfolios p JOIN users u ON u.id = p.user_id "
                    f"WHERE {REAL.replace('email', 'u.email')}"),
                "сохранили_фильтр_скрининга": scalar(
                    "SELECT count(DISTINCT f.user_id) FROM screener_saved_filters f JOIN users u ON u.id = f.user_id "
                    f"WHERE {REAL.replace('email', 'u.email')}"),
            },
            "портфелей_всего": scalar("SELECT count(*) FROM portfolios"),
            "позиций_в_портфелях": scalar("SELECT count(*) FROM portfolio_positions"),
            "на_момент_запроса": now.isoformat(timespec="seconds"),
        }

        try:
            rows = db.execute(text(
                "SELECT subscription_type, count(*) FROM users GROUP BY subscription_type"
            )).all()
            stats["по_тарифу"] = {str(r[0]): int(r[1]) for r in rows}
        except Exception:  # noqa: BLE001
            db.rollback()

        # Регистрации по дням за последний месяц — видно, есть ли приток вообще.
        try:
            rows = db.execute(text(
                "SELECT date(created_at) AS d, count(*) FROM users "
                f"WHERE {REAL} AND created_at >= :since GROUP BY d ORDER BY d DESC"
            ), {"since": since(30)}).all()
            stats["регистрации_по_дням"] = {str(r[0]): int(r[1]) for r in rows}
        except Exception:  # noqa: BLE001
            db.rollback()

        return stats
    finally:
        db.close()


_SQL_FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "copy", "vacuum", "reindex", "call", "do ",
)


@router.get("/debug/sql")
def sql_readonly(q: str = Query(..., description="SQL, только SELECT/WITH"),
                 limit: int = Query(200, ge=1, le=2000)):
    """Выполнить запрос НА ЧТЕНИЕ к боевой базе и вернуть строки.

    ЗАЧЕМ: владелец 2026-08-01 спросил, где писать SQL. Боевая база наружу НЕ выведена —
    в docker-compose у сервиса `db` нет проброса портов, доступен только фронт на 80.
    Подключить GUI-клиент с ноутбука нельзя, а выводить Postgres в интернет ради
    аналитики — плохой размен: это постоянная поверхность атаки ради разовых вопросов.

    🔴 ТРИ УРОВНЯ ЗАЩИТЫ, а не один:
    1. Транзакция объявляется READ ONLY на стороне БД — даже если фильтр ниже обойти,
       любая запись будет отклонена самим Postgres. Это единственная надёжная гарантия;
       проверка текста запроса — лишь удобная подсказка, обмануть её можно.
    2. Разрешены только запросы, начинающиеся с SELECT или WITH; запрещены ключевые
       слова изменения; запрещена точка с запятой внутри — чтобы нельзя было подклеить
       второй оператор.
    3. statement_timeout 15 секунд: тяжёлый запрос не подвесит базу, как это уже
       случалось с LLM- и FRED-кронами.

    Доступ — под общим X-Debug-Token роутера /api/debug/.
    """
    from sqlalchemy import text
    from app.db.session import SessionLocal

    s = (q or "").strip().rstrip(";").strip()
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        return {"error": "разрешены только SELECT и WITH"}
    if ";" in s:
        return {"error": "точка с запятой запрещена — только один оператор за раз"}
    # 🔴 Сверять ПО ГРАНИЦАМ СЛОВ, а не по подстроке. Проверка `kw in low` забраковала
    # совершенно законный SELECT из таблицы market_updates — в её имени есть «update».
    # Так же пострадали бы любые поля вроде updated_at, created_at, is_deleted.
    import re as _re
    for kw in _SQL_FORBIDDEN:
        if _re.search(rf"\b{_re.escape(kw.strip())}\b", low):
            return {"error": f"запрещённое слово: {kw.strip()}"}

    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        db.execute(text("SET LOCAL statement_timeout = '15s'"))
        res = db.execute(text(s))
        cols = list(res.keys())
        rows = res.fetchmany(limit)
        out = []
        for r in rows:
            # Значения приводим к JSON-совместимым: Decimal, date, datetime и прочее
            # иначе валят сериализацию ответа.
            out.append({c: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v))
                        for c, v in zip(cols, r)})
        return {"колонки": cols, "строк": len(out), "строки": out,
                "усечено": len(out) >= limit}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


@open_router.get("/debug/sql-console", response_class=HTMLResponse)
def sql_console():
    """Простая страница с полем для SQL — чтобы не собирать curl руками.

    Токен вводится один раз и хранится в localStorage браузера; на сервер он уходит
    заголовком, как и для остальных /api/debug/. Готовые запросы под рукой — потому что
    самое трудное в аналитике не написать SELECT, а вспомнить, как называются таблицы.
    """
    return HTMLResponse("""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>SQL-консоль Basis</title><meta name="robots" content="noindex">
<style>
body{font:15px/1.6 -apple-system,Inter,sans-serif;max-width:1000px;margin:0 auto;padding:24px;
background:#F7F5F0;color:#1F1B16}
h1{font-size:22px;margin:0 0 4px}p.sub{color:#5A5248;margin:0 0 20px}
textarea{width:100%;height:110px;font:14px/1.5 ui-monospace,Menlo,monospace;padding:10px;
border:1px solid #E4DFD5;border-radius:8px;background:#fff}
input{padding:8px;border:1px solid #E4DFD5;border-radius:8px;font:14px ui-monospace,monospace}
button{background:#C97A4A;color:#fff;border:0;border-radius:8px;padding:10px 18px;
font-size:15px;cursor:pointer}button:hover{opacity:.9}
table{border-collapse:collapse;width:100%;margin-top:16px;font-size:14px;background:#fff}
th,td{border:1px solid #E4DFD5;padding:6px 9px;text-align:left}th{background:#F0EBE2}
.err{color:#B4432B;background:#fff;padding:10px;border-radius:8px;border:1px solid #E4DFD5}
.ex{margin:14px 0}.ex a{display:inline-block;margin:3px 6px 3px 0;padding:5px 10px;
background:#fff;border:1px solid #E4DFD5;border-radius:14px;color:#C97A4A;text-decoration:none;
font-size:13px;cursor:pointer}
.wrap{overflow-x:auto}
</style></head><body>
<h1>SQL-консоль Basis</h1>
<p class="sub">Только чтение: транзакция объявлена READ ONLY на стороне базы, запись
отклонит сам Postgres. Ограничение — 15 секунд на запрос.</p>
<p><input id="tok" placeholder="X-Debug-Token" size="46"> <span id="saved"></span></p>
<p><input id="ask" placeholder="Спросить словами: «какие бумаги у клиентов с gmail»" size="62">
<button onclick="assist()" style="background:#5A5248">Написать запрос</button></p>
<textarea id="q">SELECT count(*) AS всего FROM users</textarea>
<p><button onclick="run()">Выполнить</button></p>
<div class="ex">Готовые запросы:
<a onclick="set('SELECT count(*) AS всего, count(*) FILTER (WHERE is_active) AS активных FROM users')">пользователи</a>
<a onclick="set('SELECT date(created_at) AS день, count(*) FROM users GROUP BY 1 ORDER BY 1 DESC')">регистрации по дням</a>
<a onclick="set('SELECT subscription_type, count(*) FROM users GROUP BY 1')">по тарифам</a>
<a onclick="set('SELECT u.id, u.created_at, count(p.id) AS портфелей FROM users u LEFT JOIN portfolios p ON p.user_id = u.id GROUP BY 1,2 ORDER BY 2 DESC')">активность по людям</a>
<a onclick="set('SELECT coalesce(c.ticker, p.secid) AS бумага, p.instrument_type AS тип, count(*) AS в_портфелях, sum(p.quantity) AS штук FROM portfolio_positions p LEFT JOIN companies c ON c.id = p.company_id GROUP BY 1,2 ORDER BY 3 DESC')">популярные бумаги</a>
<a onclick="set(&quot;SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1&quot;)">список таблиц</a>
<a onclick="set(this.dataset.q)" data-q="WITH e AS (SELECT anon_id, created_at, CASE WHEN path LIKE '/company/%%' THEN 'Карточка компании: ' || coalesce(nullif(split_part(path,'/',4),''),'обзор') WHEN path LIKE '%%view=portfolio%%' THEN 'Портфель' WHEN path LIKE '%%view=stress%%' THEN 'Стресс-тест' WHEN path LIKE '%%view=screener%%' THEN 'Скринер' WHEN path LIKE '%%view=companies%%' THEN 'Рынок' WHEN path LIKE '%%obs=%%' THEN 'Обозреватель: ' || split_part(split_part(path,'obs=',2),'&',1) WHEN path LIKE '%%view=overview%%' THEN 'Обозреватель' WHEN path LIKE '%%view=ai%%' THEN 'ИИ-помощник' WHEN path LIKE '/bonds/%%' THEN 'Облигации' WHEN path LIKE '/futures/%%' THEN 'Фьючерсы' WHEN path = '/' THEN 'Главная' ELSE coalesce(nullif(split_part(path,'/',2),''),'прочее') END AS blok, lead(created_at) OVER (PARTITION BY anon_id ORDER BY created_at) AS next_at FROM user_events WHERE is_bot IS FALSE AND kind='pageview' AND created_at >= current_date - 14) SELECT blok AS раздел, count(*) AS заходов, count(DISTINCT anon_id) AS людей, round(CAST(sum(LEAST(EXTRACT(EPOCH FROM (next_at - created_at)), 900))/60 AS numeric),1) AS всего_минут, round(CAST(avg(LEAST(EXTRACT(EPOCH FROM (next_at - created_at)), 900)) AS numeric),0) AS сек_за_заход FROM e WHERE next_at IS NOT NULL GROUP BY 1 ORDER BY 4 DESC NULLS LAST">сколько времени проводят в каждом разделе</a>
<a onclick="set(this.dataset.q)" data-q="SELECT EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Moscow')::int AS час_мск, count(DISTINCT anon_id) AS людей, count(*) AS событий FROM user_events WHERE is_bot IS FALSE AND created_at >= current_date - 14 GROUP BY 1 ORDER BY 1">когда заходят: по часам (МСК)</a>
<a onclick="set(this.dataset.q)" data-q="SELECT to_char(created_at AT TIME ZONE 'Europe/Moscow','ID') AS день_недели, EXTRACT(HOUR FROM created_at AT TIME ZONE 'Europe/Moscow')::int AS час, count(DISTINCT anon_id) AS людей FROM user_events WHERE is_bot IS FALSE AND created_at >= current_date - 30 GROUP BY 1,2 HAVING count(DISTINCT anon_id) > 0 ORDER BY 3 DESC LIMIT 25">пиковые часы по дням недели</a>
<a onclick="set(this.dataset.q)" data-q="WITH ev AS (SELECT anon_id, created_at, date(created_at) AS d, CASE WHEN created_at - lag(created_at) OVER (PARTITION BY anon_id ORDER BY created_at) > interval '30 minutes' OR lag(created_at) OVER (PARTITION BY anon_id ORDER BY created_at) IS NULL THEN 1 ELSE 0 END AS nv FROM user_events WHERE is_bot IS FALSE AND anon_id IS NOT NULL AND created_at >= current_date - 14), v AS (SELECT anon_id, d, created_at, sum(nv) OVER (PARTITION BY anon_id ORDER BY created_at) AS vn FROM ev), vis AS (SELECT d, anon_id, vn, EXTRACT(EPOCH FROM (max(created_at) - min(created_at))) AS sec, count(*) AS ev FROM v GROUP BY 1,2,3), fs AS (SELECT anon_id, min(date(created_at)) AS first_day FROM user_events WHERE is_bot IS FALSE AND anon_id IS NOT NULL GROUP BY 1) SELECT vis.d AS день, count(DISTINCT vis.anon_id) AS людей, count(*) AS визитов, count(DISTINCT vis.anon_id) FILTER (WHERE fs.first_day = vis.d) AS новых, count(DISTINCT vis.anon_id) FILTER (WHERE fs.first_day &lt; vis.d) AS вернулись, round(CAST(avg(vis.sec)/60.0 AS numeric),1) AS минут_на_визит, count(*) FILTER (WHERE vis.ev = 1) AS вошли_и_ушли, count(*) FILTER (WHERE vis.ev &gt; 1) AS пошли_дальше FROM vis JOIN fs ON fs.anon_id = vis.anon_id GROUP BY 1 ORDER BY 1 DESC">сводка по дням: люди, приток, время, воронка</a>
<a onclick="set(this.dataset.q)" data-q="SELECT date(created_at) AS день, count(DISTINCT anon_id) FILTER (WHERE name = 'tour_shown') AS показан, count(DISTINCT anon_id) FILTER (WHERE name = 'tour_started') AS начали, count(DISTINCT anon_id) FILTER (WHERE name = 'tour_completed') AS прошли, count(DISTINCT anon_id) FILTER (WHERE name = 'tour_dismissed') AS закрыли FROM user_events WHERE is_bot IS FALSE AND kind = 'action' AND name LIKE 'tour_%' GROUP BY 1 ORDER BY 1 DESC">экскурс: показан / начали / прошли</a>
<a onclick="set(this.dataset.q)" data-q="SELECT coalesce(meta-&gt;&gt;'_bot','—') AS причина, count(DISTINCT anon_id) AS устройств, count(*) AS событий FROM user_events WHERE is_bot IS TRUE AND created_at >= current_date - 7 GROUP BY 1 ORDER BY 2 DESC">кого мы считаем роботами и почему</a>
<a onclick="set(this.dataset.q)" data-q="SELECT u.email, date(u.created_at) AS регистрация, u.subscription_type AS тариф, count(DISTINCT p.id) AS портфелей, count(pos.id) AS позиций, string_agg(DISTINCT coalesce(c.ticker, pos.secid), ', ') AS бумаги FROM users u LEFT JOIN portfolios p ON p.user_id = u.id LEFT JOIN portfolio_positions pos ON pos.portfolio_id = p.id AND pos.instrument_type <> 'cash' LEFT JOIN companies c ON c.id = pos.company_id WHERE NOT (u.email LIKE '%@example.com' OR u.email LIKE '%@inbasis.ru') GROUP BY 1,2,3 ORDER BY 5 DESC">клиенты и их портфели</a>
<a onclick="set(this.dataset.q)" data-q="SELECT u.email, p.name AS портфель, coalesce(c.ticker, pos.secid) AS бумага, pos.instrument_type AS тип, pos.quantity AS количество, pos.avg_buy_price AS средняя_цена FROM portfolio_positions pos JOIN portfolios p ON p.id = pos.portfolio_id JOIN users u ON u.id = p.user_id LEFT JOIN companies c ON c.id = pos.company_id ORDER BY u.email, p.name">все позиции с почтами</a>
<a onclick="set(this.dataset.q)" data-q="SELECT u.email, count(*) AS событий, count(DISTINCT e.session_id) AS сессий, count(DISTINCT date(e.created_at)) AS дней_заходил, max(e.created_at) AS последний_раз FROM user_events e JOIN users u ON u.id = e.user_id GROUP BY 1 ORDER BY 2 DESC">активность клиентов</a>
<a onclick="set(this.dataset.q)" data-q="SELECT count(DISTINCT anon_id) AS уникальных_посетителей, count(DISTINCT session_id) AS визитов, count(*) AS просмотров, round(count(*)::numeric / nullif(count(DISTINCT anon_id),0), 1) AS страниц_на_человека FROM user_events WHERE is_bot IS FALSE AND kind = 'pageview'">сколько людей заходило</a>
<a onclick="set(this.dataset.q)" data-q="SELECT date(created_at) AS день, count(DISTINCT anon_id) AS людей, count(DISTINCT session_id) AS визитов, count(*) AS просмотров FROM user_events WHERE is_bot IS FALSE AND kind = 'pageview' GROUP BY 1 ORDER BY 1 DESC">люди по дням</a>
<a onclick="set(this.dataset.q)" data-q="SELECT anon_id AS посетитель, count(DISTINCT session_id) AS визитов, count(*) AS просмотров, count(DISTINCT path) AS разных_страниц, min(created_at) AS первый_раз, max(created_at) AS последний_раз FROM user_events WHERE is_bot IS FALSE GROUP BY 1 ORDER BY 3 DESC LIMIT 50">каждый посетитель по отдельности</a>
<a onclick="set(this.dataset.q)" data-q="SELECT CASE WHEN is_bot THEN 'роботы' WHEN is_bot IS NULL THEN 'до появления детектора' ELSE 'люди' END AS кто, count(DISTINCT anon_id) AS устройств, count(*) AS событий FROM user_events GROUP BY 1 ORDER BY 3 DESC">люди против роботов</a>
<a onclick="set(this.dataset.q)" data-q="SELECT path AS страница, count(*) AS просмотров, count(DISTINCT anon_id) AS людей FROM user_events WHERE is_bot IS FALSE AND kind = 'pageview' GROUP BY 1 ORDER BY 2 DESC LIMIT 40">какие страницы смотрят люди</a>
<a onclick="set(this.dataset.q)" data-q="SELECT name AS действие, count(*) AS раз, count(DISTINCT coalesce(anon_id, user_id::text)) AS людей FROM user_events WHERE kind IN ('click','action') GROUP BY 1 ORDER BY 2 DESC LIMIT 40">что нажимают</a>
</div>
<details style="margin:18px 0"><summary style="cursor:pointer;color:#C97A4A">
Справочник: какие есть таблицы и что в них лежит</summary>
<div id="schema" style="margin-top:12px"></div></details>
<div id="out"></div>
<script>
var SCHEMA=[{"g": "Пользователи и продукт", "t": [["users", 20, "Аккаунты. email, тариф (free/premium), дата регистрации, активен ли."], ["portfolios", 15, "Портфели пользователей: чей, название, когда создан."], ["portfolio_positions", 33, "Бумаги внутри портфелей: тикер, количество, средняя цена покупки."], ["portfolio_transactions", 50, "Сделки внутри портфеля: покупка/продажа, цена, комиссия, дата."], ["portfolio_diagnoses", 2, "Сохранённые ИИ-диагнозы портфелей."], ["screener_saved_filters", 0, "Сохранённые пользователями фильтры скрининга."], ["assistant_conversations", 22, "Диалоги с ИИ-помощником: чей, когда."], ["assistant_messages", 58, "Сообщения внутри этих диалогов."], ["verification_codes", 0, "Коды подтверждения почты."]]}, {"g": "Рыночные данные", "t": [["quotes", 581333, "🔴 ЦЕНЫ АКЦИЙ по дням. Единственный источник цены на платформе."], ["instrument_history", 260727, "История цен облигаций, фондов и фьючерсов по дням."], ["index_history", 19254, "История значений индексов (Мосбиржи, RTS, секторальные)."], ["companies", 261, "Справочник компаний: тикер, название, сектор, капитализация, число акций."], ["company_metrics", 261, "Расчётные метрики по компании: P/E, дивдоходность, справедливая цена, бета, волатильность."], ["bonds", 3281, "Справочник облигаций: купон, погашение, оферта, доходность, рейтинг, оценка риска."], ["funds", 104, "Биржевые фонды (БПИФ/ETF): состав, комиссия, ошибка слежения."], ["futures", 642, "Фьючерсы: базовый актив, ГО, экспирация."], ["options", 2432, "Опционы (раздел в проработке)."], ["spot_assets", 6, "Валюта и металлы."], ["dividends", 1413, "История и объявленные дивиденды: тикер, дата отсечки, размер."], ["company_signals", 3207, "Сигналы шины: события по компании, из которых собираются дополнения карточек."]]}, {"g": "Макроэкономика", "t": [["macro_indicators", 69, "Справочник макропоказателей: код, название, единица, источник."], ["macro_data_points", 14526, "🔴 ЗНАЧЕНИЯ макропоказателей по датам — ставка, инфляция, курсы, ВВП."], ["macro_forecasts", 66, "Прогнозы: среднесрочный прогноз ЦБ и другие."], ["macro_interpretations", 41, "Тексты-интерпретации показателей (что значит для инвестора)."], ["macro_expert_surveys", 40, "Опросы аналитиков по ожиданиям."], ["macro_analytics_docs", 31, "Аналитические документы макроблока."], ["macro_verifications", 132, "Результаты автопроверки качества макроданных (11 проверок)."], ["rate_meetings", 3, "Заседания ЦБ по ключевой ставке."], ["market_params", 4, "Параметры рынка для расчётов (безрисковая ставка и т.п.)."]]}, {"g": "Новости, гео, институты", "t": [["chronicle_entries", 4980, "Постоянная база знаний: важные новости и статьи, размеченные ИИ для агентов."], ["geo_digest_articles", 1399, "Статьи геополитического дайджеста."], ["geo_blocks", 6, "Блоки геополитики по компаниям."], ["geo_strike_events", 214, "События по инфраструктуре (удары, повреждения)."], ["geo_frontline_snapshot", 10, "Снимок линии фронта для карт."], ["geo_frontline_sync", 1, "Служебная: состояние синхронизации карт."], ["geo_territorial_claims", 51, "Территориальные данные для карт."], ["barometer_versions", 15, "Версии геополитического и институционального барометров."], ["situation_overlays", 11, "Наложения текущей ситуации на карточки."]]}, {"g": "Отчётность и контент карточек", "t": [["calendar_events", 5172, "Единый календарь: отчёты, дивиденды, оферты, заседания ЦБ, IPO."], ["earnings_reports", 380, "Вышедшие отчёты компаний: период, стандарт, ссылка на источник."], ["earnings_digests", 368, "Разборы отчётов: главное, плюсы, риски, вывод."], ["earnings_figures", 368, "Числа из отчётов, извлечённые для разбора."], ["interim_financials_overlay", 24, "Промежуточная отчётность поверх годовой."], ["card_prose_overlays", 362, "Обновлённые тексты карточек (авто-свежесть прозы)."], ["agent_addenda", 40, "Дополнения к карточкам от агентов (под код-гейтом)."], ["observer_reports", 30, "Отчёты Обозревателя."], ["company_analyses", 5, "Аналитические разборы компаний (сейчас пусто)."], ["company_profiles", 4, "Профили компаний, старая таблица (пусто)."], ["market_overviews", 4, "Обзоры рынка (пусто)."]]}, {"g": "Служебное", "t": [["job_heartbeats", 30, "Пульс фоновых задач: когда какой крон отработал."], ["alembic_version", 1, "Служебная: версия схемы БД."]]}];
(function(){
  var h='';
  SCHEMA.forEach(function(g){
    h+='<h3 style="margin:16px 0 6px;font-size:15px">'+g.g+'</h3><table>'
      +'<tr><th>Таблица</th><th>Строк</th><th>Что внутри</th></tr>';
    g.t.forEach(function(r){
      h+='<tr><td><a onclick="set(this.dataset.q)" data-q="SELECT * FROM '+r[0]+' LIMIT 50"'
        +' style="color:#C97A4A;cursor:pointer">'+r[0]+'</a></td>'
        +'<td style="text-align:right">'+(r[1]==null?'—':r[1])+'</td><td>'+r[2]+'</td></tr>';
    });
    h+='</table>';
  });
  h+='<p class="sub">Числа строк — на момент сборки справочника. Клик по названию '
    +'подставляет запрос «показать первые 50 строк». Полная версия с колонками — '
    +'docs/db-schema.md в репозитории.</p>';
  document.getElementById('schema').innerHTML=h;
})();
var t=document.getElementById('tok');
t.value=localStorage.getItem('basisDebugToken')||'';
t.onchange=function(){localStorage.setItem('basisDebugToken',t.value);
document.getElementById('saved').textContent='сохранён';};
function set(s){document.getElementById('q').value=s;}
// Запрос СОЧИНЯЕТ модель, а выполняет человек: она регулярно ошибается в названиях
// полей, и молчаливый запуск придуманного запроса дал бы правдоподобный, но неверный
// ответ — худший вид ошибки в аналитике.
function assist(){
  var a=document.getElementById('ask').value.trim();
  if(!a) return;
  var out=document.getElementById('out'); out.innerHTML='думаю…';
  fetch('/api/debug/sql-assist?ask='+encodeURIComponent(a),{headers:{'X-Debug-Token':t.value}})
   .then(function(r){return r.json();})
   .then(function(d){
     if(d.error||d.detail){out.innerHTML='<p class="err">'+esc(d.error||d.detail)+'</p>';return;}
     document.getElementById('q').value=d.запрос||'';
     out.innerHTML='<p class="sub">Запрос написан моделью — проверьте поля и нажмите «Выполнить».</p>';
   }).catch(function(e){out.innerHTML='<p class="err">'+esc(e)+'</p>';});
}
function esc(v){return String(v==null?'':v).replace(/[&<>]/g,function(m){
return {'&':'&amp;','<':'&lt;','>':'&gt;'}[m];});}
function run(){
  var out=document.getElementById('out'); out.innerHTML='считаю…';
  fetch('/api/debug/sql?limit=500&q='+encodeURIComponent(document.getElementById('q').value),
    {headers:{'X-Debug-Token':t.value}})
   .then(function(r){return r.json();})
   .then(function(d){
     if(d.error||d.detail){out.innerHTML='<p class="err">'+esc(d.error||d.detail)+'</p>';return;}
     if(!d.строки.length){out.innerHTML='<p>Пусто.</p>';return;}
     var h='<div class="wrap"><table><tr>'+d.колонки.map(function(c){return '<th>'+esc(c)+'</th>';}).join('')+'</tr>';
     d.строки.forEach(function(row){h+='<tr>'+d.колонки.map(function(c){
       return '<td>'+esc(row[c])+'</td>';}).join('')+'</tr>';});
     h+='</table></div><p class="sub">строк: '+d.строк+(d.усечено?' (показаны не все)':'')+'</p>';
     out.innerHTML=h;
   }).catch(function(e){out.innerHTML='<p class="err">'+esc(e)+'</p>';});
}
</script></body></html>""")


@router.post("/debug/purge-test-users")
def purge_test_users(confirm: str = Query("", description="передать 'да' для реального удаления")):
    """Удалить СИНТЕТИЧЕСКИЕ аккаунты (@example.com) и всё, что за ними тянется.

    ЗАЧЕМ: в боевой базе накопились аккаунты от тестовых прогонов — claude-test-*,
    test_bench-*, qa-*, obs_test-*, tier-prod-check. Они считались наравне с живыми и
    испортили продуктовые выводы (владелец поймал 2026-08-01). Разрешение на удаление
    дано явно.

    🔴 БЕЗ confirm=да НИЧЕГО НЕ УДАЛЯЕТСЯ — возвращается только план: что и сколько.
    Пересчитывать глазами перед необратимой операцией дешевле, чем восстанавливать.

    🔴 ШАБЛОН ЗАШИТ В КОД и не принимается параметром. Ручка, которой можно передать
    произвольный фильтр удаления, — это способ однажды снести живые аккаунты опечаткой.
    Здесь можно удалить ТОЛЬКО @example.com.

    🔴 ПОРТФЕЛИ ЧИСТИМ ВРУЧНУЮ. У portfolios.user_id НЕТ внешнего ключа на users (см.
    models/portfolio.py) — база не удалит их каскадом, и после удаления аккаунтов
    остались бы висячие портфели с позициями, которые попадут в любую будущую аналитику
    как ничьи. Каскад есть только у observer_reports, assistant_conversations и
    screener_saved_filters.
    """
    from sqlalchemy import text
    from app.db.session import SessionLocal

    PATTERN = "%@example.com"          # зашито намеренно, см. докстринг
    db = SessionLocal()
    try:
        ids = [r[0] for r in db.execute(
            text("SELECT id FROM users WHERE email LIKE :p"), {"p": PATTERN}).all()]
        if not ids:
            return {"итог": "подходящих аккаунтов не найдено", "удалено": 0}

        pids = [r[0] for r in db.execute(
            text("SELECT id FROM portfolios WHERE user_id = ANY(:ids)"), {"ids": ids}).all()]
        posids = [r[0] for r in db.execute(
            text("SELECT id FROM portfolio_positions WHERE portfolio_id = ANY(:p)"),
            {"p": pids or [0]}).all()]

        emails = [r[0] for r in db.execute(
            text("SELECT email FROM users WHERE id = ANY(:ids) ORDER BY id"), {"ids": ids}).all()]
        план = {
            "аккаунтов": len(ids), "портфелей": len(pids), "позиций": len(posids),
            "почты": emails,
        }
        if confirm.strip().lower() not in ("да", "yes", "true"):
            return {"режим": "ПРОВЕРКА, ничего не удалено",
                    "как_удалить": "повторить с параметром confirm=да", "план": план}

        # Порядок важен: сначала то, что ссылается, потом то, на что ссылаются.
        удалено = {}
        if posids:
            удалено["сделок"] = db.execute(
                text("DELETE FROM portfolio_transactions WHERE position_id = ANY(:p)"),
                {"p": posids}).rowcount
        if pids:
            удалено["диагнозов"] = db.execute(
                text("DELETE FROM portfolio_diagnoses WHERE portfolio_id = ANY(:p)"),
                {"p": pids}).rowcount
            удалено["позиций"] = db.execute(
                text("DELETE FROM portfolio_positions WHERE portfolio_id = ANY(:p)"),
                {"p": pids}).rowcount
            удалено["портфелей"] = db.execute(
                text("DELETE FROM portfolios WHERE id = ANY(:p)"), {"p": pids}).rowcount
        удалено["аккаунтов"] = db.execute(
            text("DELETE FROM users WHERE id = ANY(:ids)"), {"ids": ids}).rowcount
        db.commit()
        return {"режим": "УДАЛЕНО", "удалено": удалено, "почты": emails}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()


# Схема для подсказки LLM: перечень таблиц с колонками собирается ИЗ БАЗЫ на лету, а не
# пишется руками — иначе разойдётся с реальностью при первой же миграции, и модель начнёт
# уверенно сочинять несуществующие поля (как это сделал я сам с portfolio_positions.ticker).
_SQL_SYSTEM = (
    "Ты помощник аналитика инвестиционной платформы Basis. По вопросу на русском языке "
    "пишешь ОДИН SQL-запрос к PostgreSQL. Правила: только SELECT или WITH; без точки с "
    "запятой; без изменения данных; всегда ставь разумный LIMIT, если запрос может "
    "вернуть много строк; давай колонкам понятные псевдонимы на русском. "
    "Отвечай ТОЛЬКО текстом запроса, без пояснений и без markdown-разметки."
)


@router.get("/debug/sql-assist")
def sql_assist(ask: str = Query(..., description="вопрос на русском")):
    """Превратить вопрос на русском в SQL-запрос силами LLM (по конфигу — DeepSeek).

    🔴 ЗАПРОС НЕ ВЫПОЛНЯЕТСЯ. Возвращается только текст: человек читает, при желании
    правит и запускает сам. Модель регулярно ошибается в названиях полей, и молчаливое
    выполнение сочинённого запроса дало бы правдоподобный, но неверный ответ — худший
    вид ошибки в аналитике.

    Схема подкладывается из information_schema на лету, чтобы модель видела реальные
    имена таблиц и колонок, а не догадывалась.
    """
    from sqlalchemy import text
    from app.db.session import SessionLocal
    from app.services.llm import complete

    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT table_name, string_agg(column_name, ', ' ORDER BY ordinal_position) "
            "FROM information_schema.columns WHERE table_schema='public' "
            "GROUP BY table_name ORDER BY table_name"
        )).all()
        schema = "\n".join(f"{t}({c})" for t, c in rows)
    except Exception as e:  # noqa: BLE001
        db.rollback()
        return {"error": f"схему прочитать не удалось: {e}"}
    finally:
        db.close()

    hints = (
        "Важные особенности данных:\n"
        "- portfolio_positions: у АКЦИЙ колонка secid пустая, тикер берётся через "
        "company_id → companies.ticker; secid заполнен только у облигаций, фондов, "
        "фьючерсов. Сшивай через coalesce(c.ticker, pos.secid).\n"
        "- portfolio_positions.instrument_type='cash' — это денежный остаток, а не бумага; "
        "исключай его, когда речь о бумагах.\n"
        "- portfolios.user_id может быть NULL (портфели, созданные до привязки к аккаунту).\n"
        "- 🔴 user_events: ПОСЕТИТЕЛЬ ОПОЗНАЁТСЯ ПО anon_id, а НЕ по user_id. Большинство "
        "заходят без входа в аккаунт, и user_id у них NULL — считать уникальных людей "
        "через user_id НЕВЕРНО, получится ноль. Уникальные посетители = "
        "count(DISTINCT anon_id); визиты = count(DISTINCT session_id).\n"
        "- 🔴 user_events.is_bot: TRUE — поисковый робот, FALSE — человек, NULL — записи "
        "до появления детектора. Для вопросов про людей ВСЕГДА добавляй is_bot IS FALSE, "
        "иначе в ответ попадёт обход поисковика (за первые сутки это 382 «посетителя» "
        "при двух живых пользователях).\n"
        "- Служебные аккаунты: email как '%@example.com', '%@inbasis.ru', 'qa-%', 'test_%' — "
        "исключай их, когда речь о живых пользователях.\n"
        "- Цены акций: quotes (company_id, date, close). Цены прочих инструментов: "
        "instrument_history.\n"
    )
    try:
        sql = complete(_SQL_SYSTEM, f"Схема базы:\n{schema}\n\n{hints}\nВопрос: {ask}",
                       json_mode=False, max_tokens=700, temperature=0.1,
                       timeout=30, retries=1)
    except Exception as e:  # noqa: BLE001
        return {"error": f"LLM недоступна: {type(e).__name__}: {e}"}

    sql = str(sql).strip()
    for fence in ("```sql", "```"):
        sql = sql.replace(fence, "")
    return {"запрос": sql.strip(), "подсказка": "проверьте поля перед запуском"}


@router.get("/debug/macro-drift")
def debug_macro_drift(limit: int = 25, ticker: str | None = None):
    """Кого задел макро-дрейф: у чьего разбора условия ушли дальше всего.

    Считает КОД, без LLM — можно смотреть до всякой переработки: видно, из чего
    сложилась очередь и почему компания в ней оказалась.
    """
    from app.db.session import SessionLocal
    from app.services.macro_drift import company_drift, current_macro, drift_queue
    db = SessionLocal()
    try:
        if ticker:
            item = company_drift(db, ticker.upper())
            return item or {"ticker": ticker.upper(),
                            "note": "дрейфа нет: условия близки к тем, при которых "
                                    "писался разбор"}
        queue = drift_queue(db, limit=max(1, min(limit, 200)))
        return {"current": current_macro(db), "affected": len(queue), "queue": queue}
    finally:
        db.close()


@router.post("/debug/build-overview-synthesis")
def debug_build_overview_synthesis(ticker: str | None = None, batch: int = 3,
                                   stale_days: int = 30):
    """Собрать свод вкладки «Обзор». ticker — одна компания, иначе партия.

    В ФОНЕ: каждая компания — отдельный LLM-прогон по семи разборам.
    """
    from app.services.overview_synthesis import run_batch

    def _run(db):
        out = run_batch(db, batch=max(1, min(batch, 25)), stale_days=stale_days,
                        only_ticker=ticker)
        return type("R", (), {"id": "-", "status": "done",
                              "gate_notes": [str(out)[:400]]})()

    return JSONResponse(status_code=202, content=_inst_bg("overview_synthesis", _run))


@router.post("/debug/build-stress-interpretation")
def debug_build_stress_interpretation(scenario: str | None = None, batch: int = 3,
                                      stale_days: int = 14):
    """Собрать качественный разбор сценария стресс-теста. scenario — один пресет,
    иначе партия устаревших/несобранных.

    В ФОНЕ: каждый сценарий — отдельный LLM-прогон по сводам карточек и барометрам.
    """
    from app.services.stress_interpreter import run_batch

    def _run(db):
        out = run_batch(db, only_key=scenario, batch=max(1, min(batch, 10)),
                        stale_days=stale_days)
        return type("R", (), {"id": "-", "status": "done",
                              "gate_notes": [str(out)[:400]]})()

    return JSONResponse(status_code=202, content=_inst_bg("stress_interpretation", _run))


@router.get("/debug/stress-interpretation-status")
def debug_stress_interpretation_status(days_back: int = 30, limit: int = 20):
    """Состояние разборов сценариев: что опубликовано, что отклонил гейт и почему."""
    from sqlalchemy import text as _sql

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        rows = db.execute(_sql(
            "SELECT scenario_key, status, gate_notes, created_at, left(headline, 160) "
            "FROM stress_interpretations "
            "WHERE created_at >= now() - (:d || ' days')::interval "
            "ORDER BY created_at DESC LIMIT :l"), {"d": days_back, "l": limit}).all()
        published = db.execute(_sql(
            "SELECT scenario_key, max(created_at) FROM stress_interpretations "
            "WHERE status='published' GROUP BY scenario_key")).all()
        return {"days_back": days_back,
                "published": {r[0]: r[1].isoformat() for r in published},
                "recent": [{"scenario": r[0], "status": r[1], "gate_notes": r[2],
                            "created_at": r[3].isoformat(), "headline": r[4]}
                           for r in rows]}
    finally:
        db.close()


@router.get("/debug/overview-synthesis-status")
def debug_overview_synthesis_status(days_back: int = 7, limit: int = 25):
    """Состояние сводов «Обзора»: сколько собрано, что отклонил гейт и почему."""
    from sqlalchemy import text as _sql

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        counters = dict(db.execute(_sql(
            "SELECT status, count(*) FROM card_overview_synthesis "
            "WHERE created_at >= now() - (:d || ' days')::interval GROUP BY status"
        ), {"d": days_back}).all())
        rows = db.execute(_sql(
            "SELECT ticker, status, gate_notes, created_at, left(verdict, 120) "
            "FROM card_overview_synthesis "
            "WHERE created_at >= now() - (:d || ' days')::interval "
            "ORDER BY created_at DESC LIMIT :l"), {"d": days_back, "l": limit}).all()
        published = db.execute(_sql(
            "SELECT count(DISTINCT ticker) FROM card_overview_synthesis "
            "WHERE status='published'")).scalar()
        return {"days_back": days_back, "counters": counters,
                "companies_with_synthesis": published,
                "recent": [{"ticker": r[0], "status": r[1], "gate_notes": r[2],
                            "created_at": r[3].isoformat(), "verdict_head": r[4]}
                           for r in rows]}
    finally:
        db.close()


_DAILY_SQL = """
WITH ev AS (
  SELECT anon_id, created_at, date(created_at) AS d,
         CASE WHEN created_at - lag(created_at) OVER (PARTITION BY anon_id ORDER BY created_at)
                   > interval '30 minutes'
               OR lag(created_at) OVER (PARTITION BY anon_id ORDER BY created_at) IS NULL
              THEN 1 ELSE 0 END AS new_visit
  FROM user_events
  WHERE is_bot IS FALSE AND anon_id IS NOT NULL
    AND created_at >= current_date - CAST(:days AS integer)
),
v AS (
  SELECT anon_id, d, created_at,
         sum(new_visit) OVER (PARTITION BY anon_id ORDER BY created_at) AS visit_no
  FROM ev
),
vis AS (
  SELECT d, anon_id, visit_no,
         EXTRACT(EPOCH FROM (max(created_at) - min(created_at))) AS sec,
         count(*) AS events
  FROM v GROUP BY 1,2,3
),
first_seen AS (
  SELECT anon_id, min(date(created_at)) AS first_day
  FROM user_events WHERE is_bot IS FALSE AND anon_id IS NOT NULL GROUP BY 1
)
SELECT vis.d AS den,
       count(DISTINCT vis.anon_id) AS lyudey,
       count(*) AS vizitov,
       count(DISTINCT vis.anon_id) FILTER (WHERE first_seen.first_day = vis.d) AS novyh,
       count(DISTINCT vis.anon_id) FILTER (WHERE first_seen.first_day < vis.d) AS vernulis,
       round(CAST(avg(vis.sec)/60.0 AS numeric), 1) AS minut_na_vizit,
       round(CAST(avg(vis.events) AS numeric), 1) AS sobytiy_na_vizit,
       -- Ключевое разделение (владелец 2026-08-05): «зашли на платформу» против
       -- «зашли и дальше что-то нажали». Визит из ОДНОГО события — это вход без
       -- единого перехода: приложение загрузилось, человек посмотрел и ушёл.
       count(*) FILTER (WHERE vis.events = 1) AS voshli_bez_deystviy,
       count(*) FILTER (WHERE vis.events > 1) AS poshli_dalshe
FROM vis JOIN first_seen ON first_seen.anon_id = vis.anon_id
GROUP BY 1 ORDER BY 1 DESC
"""

_TOUR_SQL = """
SELECT date(created_at) AS den,
       count(DISTINCT anon_id) FILTER (WHERE name = 'tour_shown')     AS pokazan,
       count(DISTINCT anon_id) FILTER (WHERE name = 'tour_started')   AS nachali,
       count(DISTINCT anon_id) FILTER (WHERE name = 'tour_completed') AS proshli,
       count(DISTINCT anon_id) FILTER (WHERE name = 'tour_dismissed') AS otkazalis
FROM user_events
WHERE is_bot IS FALSE AND kind = 'action' AND name LIKE 'tour_%'
  AND created_at >= current_date - CAST(:days AS integer)
GROUP BY 1 ORDER BY 1 DESC
"""


@router.get("/debug/analytics-daily")
def analytics_daily(days: int = Query(14, ge=1, le=90)):   # защита — на уровне роутера (_debug_guard)
    """Сводка по дням в ОДНОМ месте: люди, визиты, новые и вернувшиеся, время на платформе,
    воронка экскурса.

    Владелец 2026-08-05: «можно сделать, чтобы было видно притоки/оттоки и время пребывания
    (и чтобы всё можно было посмотреть вместе) + сколько людей воспользовались экскурсом».

    🔴 ПОЧЕМУ НЕ СОВПАДАЕТ С МЕТРИКОЙ — и почему обе системы правы.
    Метрика считает КАЖДОЕ открытие страницы: её счётчик стоит во всех трёх HTML-каркасах,
    включая пре-рендеренные SEO-страницы, и срабатывает ДО загрузки приложения. Наш лог
    пишет из приложения: человек, который открыл статическую страницу облигации, прочитал
    и ушёл, в Метрику попадёт, а к нам — нет. Плюс личность считается по-разному: у Метрики
    свой идентификатор, у нас anon_id, и он теряется при очистке хранилища браузера.
    Поэтому наши цифры ВСЕГДА ниже и отвечают на другой вопрос: сколько людей реально
    работали с платформой, а не сколько открыли страницу.

    Визит — серия событий одного человека без перерыва больше 30 минут (та же граница,
    что у Метрики, чтобы числа были хотя бы сопоставимы по смыслу).
    """
    from sqlalchemy import text as _sql
    from app.db.session import SessionLocal
    with SessionLocal() as db:
        db.execute(_sql("SET TRANSACTION READ ONLY"))
        rows = [dict(r._mapping) for r in db.execute(_sql(_DAILY_SQL), {"days": days})]
        tour = [dict(r._mapping) for r in db.execute(_sql(_TOUR_SQL), {"days": days})]
    by_day = {str(t["den"]): t for t in tour}
    for r in rows:
        r["den"] = str(r["den"])
        t = by_day.get(r["den"], {})
        r["ekskurs_pokazan"] = t.get("pokazan", 0)
        r["ekskurs_nachali"] = t.get("nachali", 0)
        r["ekskurs_proshli"] = t.get("proshli", 0)
        v_all = (r.get("voshli_bez_deystviy") or 0) + (r.get("poshli_dalshe") or 0)
        r["dolya_poshli_dalshe_pct"] = round(100.0 * (r.get("poshli_dalshe") or 0) / v_all, 1) if v_all else None
    return {
        "пояснение": ("Метрика считает открытия страниц (её счётчик есть и на статических "
                      "SEO-страницах), наш лог — работу в приложении. Поэтому наши цифры ниже: "
                      "они отвечают на вопрос «сколько людей пользовались», а не «сколько открыли»."),
        "по_дням": rows,
        "экскурс_всего": {
            "показан": sum(t.get("pokazan", 0) or 0 for t in tour),
            "начали": sum(t.get("nachali", 0) or 0 for t in tour),
            "прошли": sum(t.get("proshli", 0) or 0 for t in tour),
            "отказались_на_приветствии": sum(t.get("otkazalis", 0) or 0 for t in tour),
        },
    }


@router.post("/debug/test-email")
def debug_test_email(data: dict):
    """Проверка SMTP-креденшелов (ящик Timeweb): шлёт тестовое письмо на `to`.
    Использовать после заполнения SMTP_* в env, до объявления фичи готовой.
    Токен-гейт — на всём роутере (_debug_guard)."""
    from app.services.email_codes import is_verification_enabled, send_mail
    if not is_verification_enabled():
        return {"status": "disabled", "detail": "SMTP_HOST/SMTP_USER/SMTP_PASSWORD не заданы в env"}
    to = (data.get("to") or "").strip()
    if "@" not in to:
        return {"status": "error", "detail": "укажите to"}
    try:
        send_mail(to, "Basis — тест отправки почты",
                  "Это тестовое письмо от inbasis.ru: SMTP настроен корректно.\n")
        return {"status": "sent", "to": to}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": str(e)[:300]}


@router.post("/debug/net-probe")
def debug_net_probe(data: dict | None = None):
    """Сетевой зонд: TCP-доступность наружу с инстанса (диагноз «timed out» у
    SMTP 2026-08-06 — egress-политика приложения, а не наши креды). Проверяет
    стандартные SMTP-порты ящика из env + HTTP-альтернативы, плюс показывает
    SMTP-конфиг с замаскированным паролем — сверить, ЧТО реально в env."""
    import socket
    import time
    host = os.environ.get("SMTP_HOST", "smtp.timeweb.ru")
    targets = [(host, 465), (host, 587), (host, 25), (host, 2525),
               ("go1.unisender.ru", 443), ("api.deepseek.com", 443), ("1.1.1.1", 443)]
    extra = (data or {}).get("targets") or []
    for t in extra[:5]:
        try:
            h, p = str(t).rsplit(":", 1)
            targets.append((h, int(p)))
        except Exception:  # noqa: BLE001
            pass
    out = []
    for h, p in targets:
        t0 = time.time()
        try:
            with socket.create_connection((h, p), timeout=6):
                out.append({"target": f"{h}:{p}", "tcp": "ok", "ms": int((time.time() - t0) * 1000)})
        except Exception as e:  # noqa: BLE001
            out.append({"target": f"{h}:{p}", "tcp": type(e).__name__, "detail": str(e)[:80]})
    pw = os.environ.get("SMTP_PASSWORD", "")
    channel = "unisender" if os.environ.get("UNISENDER_GO_API_KEY") else (
        "smtp" if os.environ.get("SMTP_HOST") else "none")
    return {"probes": out, "mail_channel": channel, "smtp_env": {
        "host": os.environ.get("SMTP_HOST"), "port": os.environ.get("SMTP_PORT"),
        "user": os.environ.get("SMTP_USER"),
        "from": os.environ.get("SMTP_FROM"),
        "password_set": bool(pw), "password_len": len(pw)}}


@router.get("/debug/assistant-index")
def assistant_index(rebuild: bool = Query(False, description="пересобрать индекс прозы"),
                    q: str = Query("", description="проверочный поиск")):
    """Состояние поискового слоя ассистента (doc_index) — сколько документов
    проиндексировано и что находится по запросу. Нужен, чтобы проверять RAG
    НА БОЮ, а не по локальной папке: в образ едет свой срез файлов."""
    from app.services import doc_index
    if rebuild:
        doc_index.ensure_index(force=True)
    out = {"stats": doc_index.stats()}
    if q:
        out["results"] = [{k: v for k, v in r.items() if k != "snippet"} | {
            "snippet": (r.get("snippet") or "")[:180]} for r in doc_index.search(q, limit=5)]
    return out


@router.post("/debug/assistant-tool")
def assistant_tool(name: str = Query(..., description="имя инструмента"),
                   args: dict | None = None):
    """Прямой вызов ОДНОГО инструмента ассистента — проверка доступа к данным
    без траты токенов LLM: видно, что именно увидит модель."""
    from app.db.session import SessionLocal
    from app.services import assistant_tools
    db = SessionLocal()
    try:
        return {"tool": name, "result": assistant_tools.execute(db, name, args or {})}
    finally:
        db.close()
