#!/usr/bin/env python3
"""Google Search Console через API: показы, клики, позиции и страницы — как у Вебмастера.

ЗАЧЕМ: по Яндексу мы видим всё (webmaster.py), по Google — только пришедших, через Метрику
(2 визита за 30 дней против 44 у Яндекса). Не видно главного: сколько страниц Google взял в
индекс и по каким запросам ПОКАЗЫВАЕТ без кликов. Именно показы говорят, где мы близко к
первой странице.

🔴 БЕЗ БИБЛИОТЕК GOOGLE. google-auth и google-api-python-client тянут за собой десяток
зависимостей, а нам нужен один подписанный запрос. Подписываем JWT сами через cryptography
(она уже в requirements) и ходим обычным urllib. Меньше зависимостей — меньше поводов
упасть сборке на билд-окружении Timeweb.

КЛЮЧ: backend/secrets/google-search-console.json (в .gitignore; репозиторий публичный,
ключ туда попадать не должен ни при каких обстоятельствах).

Запуск:
  python3 scripts/gsc.py queries   — запросы: показы, клики, CTR, позиция
  python3 scripts/gsc.py pages     — страницы: показы, клики, позиция
  python3 scripts/gsc.py summary   — итоги за период и динамика по дням
  python3 scripts/gsc.py sitemaps  — что Google знает о наших картах сайта

🔴 ТОЛЬКО ЧТЕНИЕ.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "secrets", "google-search-console.json")
SITE = os.environ.get("GSC_SITE", "https://inbasis.ru/")
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
API = "https://searchconsole.googleapis.com/webmasters/v3"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _access_token() -> str:
    """Сервисный аккаунт → токен доступа. Подписываем JWT сами (RS256)."""
    if not os.path.exists(KEY_PATH):
        sys.exit(f"Нет ключа: {KEY_PATH}\nПоложите туда JSON сервисного аккаунта "
                 "(см. докстринг) — и НЕ кладите его в docs/, репозиторий публичный.")
    key = json.load(open(KEY_PATH, encoding="utf-8"))
    now = int(time.time())
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64(json.dumps({
        "iss": key["client_email"], "scope": SCOPE,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{claims}".encode()

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    private = serialization.load_pem_private_key(key["private_key"].encode(), password=None)
    signature = private.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{header}.{claims}.{_b64(signature)}"

    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"Не удалось получить токен ({e.code}): {e.read().decode('utf-8','replace')[:300]}")


def call(path: str, body: dict | None = None):
    token = _access_token()
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code == 403:
            sys.exit("Ошибка 403: сервисный аккаунт не добавлен в Search Console.\n"
                     "Search Console → Настройки → Пользователи и разрешения → Добавить "
                     "пользователя → адрес client_email из ключа, право «Полный».\n" + detail)
        sys.exit(f"Ошибка API {e.code}: {detail}")


def _period(days: int = 28):
    from datetime import date, timedelta
    end = date.today() - timedelta(days=2)      # Google отдаёт данные с задержкой ~2 дня
    return str(end - timedelta(days=days)), str(end)


def _query(dimension: str, limit: int = 30, days: int = 28):
    d1, d2 = _period(days)
    return call(f"/sites/{urllib.parse.quote(SITE, safe='')}/searchAnalytics/query",
                {"startDate": d1, "endDate": d2, "dimensions": [dimension],
                 "rowLimit": limit, "dataState": "all"})


def _show(rows, title, label_w=52):
    if not rows:
        print("  данных пока нет — Google ещё не показывал сайт по этому срезу")
        return
    print(f"=== {title}")
    print(f"  {'':<{label_w}}{'показы':>8}{'клики':>7}{'CTR':>8}{'позиция':>9}")
    for r in rows:
        k = (r.get("keys") or ["—"])[0]
        print(f"  {str(k)[:label_w - 1]:<{label_w}}{r.get('impressions',0):>8.0f}"
              f"{r.get('clicks',0):>7.0f}{r.get('ctr',0)*100:>7.1f}%{r.get('position',0):>9.1f}")


def cmd_queries():
    _show(_query("query", 40).get("rows", []), "Запросы, по которым Google нас ПОКАЗЫВАЕТ", 46)


def cmd_pages():
    _show(_query("page", 40).get("rows", []), "Страницы в выдаче Google")


def cmd_summary():
    d1, d2 = _period(28)
    tot = call(f"/sites/{urllib.parse.quote(SITE, safe='')}/searchAnalytics/query",
               {"startDate": d1, "endDate": d2, "rowLimit": 1, "dataState": "all"})
    rows = tot.get("rows", [])
    if rows:
        r = rows[0]
        print(f"=== За {d1} — {d2}: показов {r.get('impressions',0):.0f}, "
              f"кликов {r.get('clicks',0):.0f}, CTR {r.get('ctr',0)*100:.2f}%, "
              f"средняя позиция {r.get('position',0):.1f}")
    else:
        print("=== Показов пока нет: Google ещё не начал показывать сайт в выдаче")
    _show(_query("date", 14).get("rows", []), "По дням", 14)


def cmd_sitemaps():
    r = call(f"/sites/{urllib.parse.quote(SITE, safe='')}/sitemaps")
    sm = r.get("sitemap", [])
    if not sm:
        print("Карты сайта не отправлены или Google их ещё не обработал.")
        return
    print("=== Карты сайта")
    for s in sm:
        c = (s.get("contents") or [{}])[0]
        print(f"  {s.get('path','')}\n     обработана: {str(s.get('lastDownloaded'))[:19]} | "
              f"адресов: {c.get('submitted','—')} | проиндексировано: {c.get('indexed','—')} | "
              f"ошибок: {s.get('errors','0')}, предупреждений: {s.get('warnings','0')}")

def cmd_inspect():
    """Что Google думает о КОНКРЕТНЫХ страницах: в индексе ли, когда обходил, какая карта.

    🔴 Отправить страницы на переобход, как у Яндекса, у Google НЕЛЬЗЯ. Indexing API
    официально работает только для вакансий и трансляций — для аналитики применять его
    против правил. Остаётся: карта сайта (уже отправлена и читается), внутренние ссылки
    и ручной «Запросить индексирование» в интерфейсе, поштучно.
    Поэтому здесь — не отправка, а ЧТЕНИЕ статуса: понять, дошёл ли Google до страницы.

    Квота проверки — 2000 адресов в сутки, этого более чем достаточно.
    """
    urls = sys.argv[2:] or [
        f"{SITE}company/SBER/dividends/", f"{SITE}company/SBER/finance/",
        f"{SITE}company/ROSN/grafik/", f"{SITE}company/ROSN/prognoz/",
        f"{SITE}company/GAZP/spravedlivaya-tsena/", f"{SITE}razbor-otchetnosti-kompaniy/",
        f"{SITE}dividendnyy-kalendar/", f"{SITE}indeks/imoex/",
    ]
    VERDICT = {"PASS": "в индексе", "NEUTRAL": "не в индексе", "FAIL": "ошибка",
               "PARTIAL": "частично", "VERDICT_UNSPECIFIED": "нет вердикта"}
    STATE = {"INDEXING_ALLOWED": "индексирование разрешено",
             "BLOCKED_BY_META_TAG": "закрыто мета-тегом", "BLOCKED_BY_ROBOTS_TXT": "закрыто robots.txt"}
    print("=== Что Google знает о наших страницах")
    for u in urls:
        r = call("", None) if False else None
        import urllib.request as ur, urllib.error as ue
        token = _access_token()
        body = json.dumps({"inspectionUrl": u, "siteUrl": SITE}).encode()
        req = ur.Request("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                         data=body, headers={"Authorization": f"Bearer {token}",
                                             "Content-Type": "application/json"})
        try:
            with ur.urlopen(req, timeout=60) as resp:
                d = json.loads(resp.read().decode()).get("inspectionResult", {})
        except ue.HTTPError as e:
            print(f"  {u.replace(SITE,'/')}: ошибка {e.code} {e.read().decode('utf-8','replace')[:120]}")
            continue
        idx = d.get("indexStatusResult", {})
        print(f"  {u.replace(SITE, '/'):<44} {VERDICT.get(idx.get('verdict'), idx.get('verdict','—')):<14}"
              f" {STATE.get(idx.get('robotsTxtState'), '')}"
              f" | обход: {str(idx.get('lastCrawlTime'))[:10]}"
              f" | карта: {'есть' if idx.get('sitemap') else 'нет'}")
        if idx.get("coverageState"):
            print(f"      {idx['coverageState']}")



if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    fn = {"queries": cmd_queries, "pages": cmd_pages,
          "summary": cmd_summary, "sitemaps": cmd_sitemaps, "inspect": cmd_inspect}.get(cmd)
    if fn:
        fn()
    else:
        print(__doc__)