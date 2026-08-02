#!/usr/bin/env python3
"""Яндекс.Вебмастер через программный доступ: статус индексации без ручных выгрузок.

ЗАЧЕМ: владелец 2026-08-02 — «давай добавим программный доступ, чтобы ты мог смотреть».
До этого статус индексации приходилось узнавать только из выгрузок CSV, которые владелец
делал руками, а наш собственный лог видит лишь ВИЗИТЫ робота — не его решение о том,
брать ли страницу в поиск. Разница принципиальная: 558 обойденных страниц могут дать и
500 в поиске, и 50.

ТОКЕН берётся из окружения YANDEX_WEBMASTER_TOKEN (кладём в backend/.env, он в .gitignore).
Как получить — см. docs/webmaster-api.md.

Запуск:
  python3 scripts/webmaster.py summary     — сколько страниц в поиске, динамика, ошибки
  python3 scripts/webmaster.py queries     — по каким запросам показывают, позиции, клики
  python3 scripts/webmaster.py crawl       — статистика обхода по дням
  python3 scripts/webmaster.py recrawl f.txt — отправить адреса на переобход (лимит суточный)

🔴 ЧИТАЕМ, А НЕ МЕНЯЕМ. Единственная операция, что-то меняющая, — переобход, и она
требует явного указания файла. Случайно испортить настройки сайта отсюда нельзя.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.webmaster.yandex.net/v4"
HOST_HINT = "inbasis.ru"


def _token() -> str:
    t = (os.environ.get("YANDEX_WEBMASTER_TOKEN") or "").strip()
    if not t:
        # .env читаем сами: скрипт запускается и вне приложения, где dotenv не подключён
        env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.startswith("YANDEX_WEBMASTER_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not t:
        print("Нет токена. Положите YANDEX_WEBMASTER_TOKEN в backend/.env "
              "(как получить — docs/webmaster-api.md)")
        sys.exit(1)
    return t


def call(path: str, method: str = "GET", body: dict | None = None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"OAuth {_token()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        print(f"Ошибка API {e.code}: {detail}")
        # 401/403 почти всегда означают протухший токен или нехватку прав, а не поломку
        if e.code in (401, 403):
            print("Похоже на проблему с токеном: истёк или выдан без прав Вебмастера.")
        sys.exit(1)


def host_id() -> str:
    """Идентификатор сайта. У Вебмастера он вида https:inbasis.ru:443, а не домен."""
    uid = call("/user/")["user_id"]
    hosts = call(f"/user/{uid}/hosts/")["hosts"]
    for h in hosts:
        if HOST_HINT in h.get("unicode_host_url", "") or HOST_HINT in h.get("ascii_host_url", ""):
            return uid, h["host_id"]
    print("Сайт не найден среди подтверждённых:", [h.get("unicode_host_url") for h in hosts])
    sys.exit(1)


def cmd_summary():
    uid, hid = host_id()
    s = call(f"/user/{uid}/hosts/{hid}/summary/")
    print("=== Состояние сайта в поиске")
    NAMES = {
        "sqi": "Индекс качества сайта (ИКС)",
        "searchable_pages_count": "Страниц в поиске",
        "excluded_pages_count": "Исключено из поиска",
        "site_problems": "Проблемы",
    }
    for k, v in s.items():
        print(f"  {NAMES.get(k, k)}: {v}")

    h = call(f"/user/{uid}/hosts/{hid}/search-urls/in-search/history/")
    pts = h.get("history", [])
    if pts:
        print("\n=== Страниц в поиске по датам (последние 10)")
        for p in pts[-10:]:
            print(f"  {p.get('date','')[:10]}: {p.get('value')}")
        first, last = pts[0].get("value"), pts[-1].get("value")
        if isinstance(first, int) and isinstance(last, int):
            print(f"  изменение за период: {last - first:+d}")


def cmd_crawl():
    uid, hid = host_id()
    h = call(f"/user/{uid}/hosts/{hid}/indexing/history/?"
             + urllib.parse.urlencode({"indexing_indicator": "DOWNLOADED"}))
    pts = h.get("indicators", {}).get("DOWNLOADED", [])
    print("=== Страниц скачано роботом по дням (последние 14)")
    for p in pts[-14:]:
        print(f"  {p.get('date','')[:10]}: {p.get('value')}")


def cmd_queries():
    uid, hid = host_id()
    r = call(f"/user/{uid}/hosts/{hid}/search-queries/popular/?"
             + urllib.parse.urlencode({
                 "order_by": "TOTAL_SHOWS",
                 "query_indicator": ["TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION"],
             }, doseq=True))
    qs = r.get("queries", [])
    if not qs:
        print("Запросов пока нет — сайт слишком новый или мало показов.")
        return
    print("=== Запросы, по которым нас показывают")
    print(f"  {'запрос':44s} {'показы':>7} {'клики':>6} {'позиция':>8}")
    for q in qs[:40]:
        ind = q.get("indicators", {})
        print(f"  {q.get('query_text','')[:44]:44s} {ind.get('TOTAL_SHOWS',0):>7} "
              f"{ind.get('TOTAL_CLICKS',0):>6} {ind.get('AVG_SHOW_POSITION',0):>8.1f}")


def cmd_recrawl(path: str):
    """Отправить адреса на переобход. Суточная квота у Вебмастера своя — она же видна
    в ответе, поэтому останавливаемся, когда она кончилась, а не долбим впустую."""
    uid, hid = host_id()
    q = call(f"/user/{uid}/hosts/{hid}/recrawl/quota/")
    left = q.get("quota_remainder", 0)
    print(f"Квота переобхода на сегодня: осталось {left} из {q.get('daily_quota', '?')}")
    urls = [l.strip() for l in open(path, encoding="utf-8") if l.strip().startswith("http")]
    sent = 0
    for u in urls:
        if sent >= left:
            print(f"Квота исчерпана, отправлено {sent}. Остальные — завтра.")
            break
        try:
            call(f"/user/{uid}/hosts/{hid}/recrawl/queue/", method="POST", body={"url": u})
            sent += 1
        except SystemExit:
            print(f"  остановлено на {u}")
            break
    print(f"Отправлено на переобход: {sent}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "summary": cmd_summary()
    elif cmd == "crawl": cmd_crawl()
    elif cmd == "queries": cmd_queries()
    elif cmd == "recrawl": cmd_recrawl(sys.argv[2])
    else: print(__doc__)
