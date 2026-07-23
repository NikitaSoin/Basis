"""Диагностические эндпоинты — только для отладки."""
import json
import logging
import os
import ssl
import urllib.request
import urllib.error

from fastapi import APIRouter, Query

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
    """Проверка переменных окружения (без значений секретов).

    ВАЖНО: DATABASE_URL — connection string с паролем ВНУТРИ (postgresql://user:pass@host)
    — раньше уходил в открытом виде (маскировались только KEY/TOKEN/PASSWORD по суффиксу
    имени переменной, DATABASE_URL под этот паттерн не попадал). Теперь такие URL-секреты
    маскируются отдельно (регэксп на userinfo часть), не просто по суффиксу имени ключа."""
    import re
    keys = ["TINKOFF_API_TOKEN", "MOEX_USERNAME", "MOEX_PASSWORD", "DATABASE_URL",
            "ANTHROPIC_API_KEY", "ANTHROPIC_PROXY_URL", "DEEPSEEK_API_KEY", "FRED_API_KEY",
            "LLM_PROVIDER", "RUN_STARTUP_JOBS", "MINFIN_BASE_URL"]
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
    n = max(1, min(kb, 5000))
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


@router.post("/debug/purge-future-macro")
def debug_purge_future_macro():
    """Удаляет точки macro_data_points с as_of в будущем (баг: LLM-извлечение
    иногда путает прогнозную строку на странице ЦБ с фактическим месячным
    значением — see sync_inflation future-date guard). Разовая очистка уже
    накопленного мусора, не гонять регулярно."""
    from datetime import date
    from app.db.session import SessionLocal
    from app.models.macro import MacroDataPoint
    db = SessionLocal()
    try:
        rows = db.query(MacroDataPoint).filter(MacroDataPoint.as_of > date.today()).all()
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
                                             sync_credit_m2)
    from app.services.macro_minfin_sync import sync_gov_spending
    from app.services.macro_rosstat import sync_ppi
    from app.services.macro_hh_sync import sync_hh_index
    from app.services.macro_tankermap_sync import sync_urals
    from app.services.macro_wb_commodities_sync import sync_wb_commodities
    from app.services.macro_yahoo_commodities_sync import sync_yahoo_commodities
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
            ("gov_spending", lambda: sync_gov_spending(db, months_back=4)),
            ("ppi", lambda: sync_ppi(db, months_back=6)),
            ("hh_index", lambda: sync_hh_index(db, months_back=18)),
            ("urals", lambda: sync_urals(db, period="max")),
            ("wb_commodities", lambda: sync_wb_commodities(db, months_back=120)),
            ("yahoo_commodities", lambda: sync_yahoo_commodities(db)),
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
