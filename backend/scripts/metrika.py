#!/usr/bin/env python3
"""Яндекс.Метрика через API: поведение посетителей и — главное — поисковые фразы.

ЗАЧЕМ: наш собственный лог (`user_events`) видит адрес страницы и источник перехода, но
НЕ видит, по какому запросу человек пришёл, сколько пробыл и ушёл ли сразу. Вебмастер
показывает запросы, по которым нас ПОКАЗЫВАЮТ, а Метрика — по каким реально ПРИШЛИ.
Разница принципиальная: 250 показов у фьючерсов дали ноль кликов, и без Метрики не
отличить «показали не тем» от «показали тем, но сниппет не выбрали».

ТОКЕН — в backend/.env, ключ YANDEX_METRIKA_TOKEN. Получается тем же способом, что и
токен Вебмастера (docs/webmaster-api.md), но в правах приложения нужно отметить
«Яндекс.Метрика → получение статистики».

Запуск:
  python3 scripts/metrika.py summary   — посетители, визиты, отказы, глубина по дням
  python3 scripts/metrika.py pages     — популярные страницы: визиты, время, отказы
  python3 scripts/metrika.py sources   — источники трафика
  python3 scripts/metrika.py queries   — ПОИСКОВЫЕ ФРАЗЫ, по которым пришли
  python3 scripts/metrika.py devices   — устройства и разрешения экрана

🔴 ТОЛЬКО ЧТЕНИЕ. Скрипт не меняет ни настройки счётчика, ни цели, ни фильтры.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api-metrika.yandex.net/stat/v1/data"
COUNTER = os.environ.get("YANDEX_METRIKA_COUNTER", "111213378")
DAYS = "30daysAgo"


def _token() -> str:
    t = (os.environ.get("YANDEX_METRIKA_TOKEN") or "").strip()
    if not t:
        env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.startswith("YANDEX_METRIKA_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not t:
        sys.exit("Нет токена. Положите YANDEX_METRIKA_TOKEN в backend/.env "
                 "(как получить — тем же способом, что токен Вебмастера, но с правом на Метрику).")
    return t


def call(**params):
    params.setdefault("ids", COUNTER)
    params.setdefault("date1", DAYS)
    params.setdefault("date2", "today")
    params.setdefault("accuracy", "full")
    url = f"{API}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {_token()}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        if e.code in (401, 403):
            sys.exit(f"Ошибка {e.code}: токен не подошёл — истёк либо выдан без права на Метрику.\n{detail}")
        sys.exit(f"Ошибка API {e.code}: {detail}")


def _rows(r):
    """Плоский вид: [(подписи…), (числа…)] — у Метрики они лежат раздельно."""
    out = []
    for item in r.get("data", []):
        names = [d.get("name") or d.get("id") or "—" for d in item.get("dimensions", [])]
        out.append((names, item.get("metrics", [])))
    return out


def _print(rows, headers, widths, fmts):
    print("  " + "".join(h.ljust(w) for h, w in zip(headers, widths)))
    for names, mets in rows:
        cells = list(names) + [f(m) for f, m in zip(fmts, mets)]
        print("  " + "".join(str(c)[:w - 1].ljust(w) for c, w in zip(cells, widths)))


def cmd_summary():
    r = call(metrics="ym:s:users,ym:s:visits,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds",
             dimensions="ym:s:date", sort="ym:s:date", limit=40)
    t = r.get("totals", [])
    if t:
        print(f"=== За период: {t[0]:.0f} посетителей, {t[1]:.0f} визитов, "
              f"отказы {t[2]:.1f}%, глубина {t[3]:.1f} стр., в среднем {t[4]/60:.1f} мин")
    print("\n=== По дням")
    _print(_rows(r), ["дата", "люди", "визиты", "отказы", "глубина", "минуты"],
           [14, 8, 9, 9, 10, 8],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.0f}", lambda v: f"{v:.0f}%",
            lambda v: f"{v:.1f}", lambda v: f"{v/60:.1f}"])


def cmd_pages():
    r = call(metrics="ym:pv:pageviews,ym:pv:users", dimensions="ym:pv:URLPathFull",
             sort="-ym:pv:pageviews", limit=30)
    print("=== Популярные страницы")
    _print(_rows(r), ["страница", "просмотры", "люди"], [52, 12, 8],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.0f}"])


def cmd_sources():
    r = call(metrics="ym:s:visits,ym:s:users,ym:s:bounceRate",
             dimensions="ym:s:lastTrafficSource", sort="-ym:s:visits", limit=20)
    print("=== Источники трафика")
    _print(_rows(r), ["источник", "визиты", "люди", "отказы"], [34, 10, 8, 9],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.0f}", lambda v: f"{v:.1f}%"])


def cmd_queries():
    """Главное, чего нет ни в нашем логе, ни в Вебмастере: с каким запросом ПРИШЛИ."""
    r = call(metrics="ym:s:visits,ym:s:users,ym:s:bounceRate",
             dimensions="ym:s:searchPhrase", sort="-ym:s:visits", limit=50)
    rows = _rows(r)
    if not rows:
        print("Поисковых фраз пока нет — мало переходов из поиска либо Метрика их ещё не отдаёт "
              "(часть запросов Яндекс скрывает).")
        return
    print("=== Поисковые фразы, по которым РЕАЛЬНО пришли")
    _print(rows, ["фраза", "визиты", "люди", "отказы"], [46, 9, 8, 9],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.0f}", lambda v: f"{v:.1f}%"])


def cmd_devices():
    r = call(metrics="ym:s:visits,ym:s:bounceRate", dimensions="ym:s:deviceCategory",
             sort="-ym:s:visits", limit=10)
    print("=== Устройства")
    _print(_rows(r), ["устройство", "визиты", "отказы"], [22, 10, 9],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.1f}%"])

def cmd_landings():
    """Страницы, НА КОТОРЫЕ приходят из поиска, — «по каким страницам нас находят».

    🔴 Позиции ПО СТРАНИЦАМ ни Метрика, ни API Вебмастера не отдают: Вебмастер даёт среднюю
    позицию по ЗАПРОСУ (см. webmaster.py queries), Метрика — страницу входа. Сопоставить
    их можно только вручную и приблизительно; выдумывать точную позицию страницы нельзя.
    """
    r = call(metrics="ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth",
             dimensions="ym:s:startURL", filters="ym:s:lastTrafficSource=='organic'",
             sort="-ym:s:visits", limit=40)
    rows = _rows(r)
    if not rows:
        print("Переходов из поиска пока нет.")
        return
    print("=== Страницы входа ИЗ ПОИСКА")
    _print(rows, ["страница", "визиты", "люди", "отказы", "глубина"], [50, 9, 7, 9, 9],
           [lambda v: f"{v:.0f}", lambda v: f"{v:.0f}", lambda v: f"{v:.1f}%", lambda v: f"{v:.1f}"])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    fn = {"summary": cmd_summary, "pages": cmd_pages, "sources": cmd_sources,
          "queries": cmd_queries, "devices": cmd_devices, "landings": cmd_landings}.get(cmd)
    if fn:
        fn()
    else:
        print(__doc__)
