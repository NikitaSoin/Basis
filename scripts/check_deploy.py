#!/usr/bin/env python3
"""Проверка, доехал ли фронт на бой: ищет маркеры правки в ЖИВЫХ бандлах.

🔴 Зачем инструмент, а не команда на месте. Ручные проверки давали ЛОЖНЫЕ вердикты
трижды за день, каждый раз по-новому:
  1. `grep -q … && echo` в цикле — на первом ненайденном маркере цепочка возвращала
     код 1, цикл обрывался, и вывод читался как «не доехало», хотя проверены были не
     все файлы;
  2. `asset-manifest.json` отдавался из кэша — сравнивался СТАРЫЙ бандл;
  3. маркер брался неуникальный: строка «не факт и не рекомендация» живёт и в другом
     компоненте, поэтому «старый код ещё здесь» срабатывало после удачной выкатки.

Инструмент закрывает все три: обходит кэш, скачивает ВСЕ js/css из манифеста, считает
вхождения по каждому файлу и печатает итог, а не обрывается на первом промахе.

Использование:
    python3 scripts/check_deploy.py --have "obs-macro-hero" --have "Главный вывод" \
                                    --absent "СтараяСтрока"
    python3 scripts/check_deploy.py --url https://inbasis.ru --have "стресс-тест"

Коды возврата: 0 — все условия выполнены; 1 — что-то не сошлось; 2 — сайт недоступен.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import ssl
import time
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
       "Cache-Control": "no-cache", "Pragma": "no-cache"}


# Проверка деплоя — не канал доверия к содержимому, а сверка «доехал ли наш код»,
# поэтому системное хранилище сертификатов (на маках Python часто без него) не должно
# ронять инструмент. Данные отсюда никуда не записываются.
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def _get(url: str, timeout: int = 90) -> str:
    # Метка времени в query — сервер и промежуточные кэши отдают свежую копию.
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(f"{url}{sep}_={int(time.time())}", headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return r.read().decode("utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://inbasis.ru", help="боевой адрес фронта")
    ap.add_argument("--have", action="append", default=[],
                    help="строка, которая ДОЛЖНА быть в бандле (можно повторять)")
    ap.add_argument("--absent", action="append", default=[],
                    help="строка, которой БЫТЬ НЕ ДОЛЖНО (можно повторять)")
    args = ap.parse_args()
    if not args.have and not args.absent:
        print("нечего проверять: задайте --have и/или --absent")
        return 1

    base = args.url.rstrip("/")
    try:
        manifest = json.loads(_get(f"{base}/asset-manifest.json", timeout=30))
    except Exception as e:  # noqa: BLE001
        print(f"манифест недоступен: {type(e).__name__}: {e}")
        return 2

    files = [v for v in (manifest.get("files") or {}).values()
             if isinstance(v, str) and re.search(r"\.(js|css)$", v)]
    if not files:
        print("в манифесте нет js/css — структура изменилась?")
        return 2
    main_js = (manifest.get("files") or {}).get("main.js", "?")
    print(f"бой: {base} | main.js: {main_js} | файлов к проверке: {len(files)}")

    bodies: dict[str, str] = {}
    for f in files:
        url = f if f.startswith("http") else base + f
        try:
            bodies[f] = _get(url)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {f}: не скачался ({type(e).__name__})")
            bodies[f] = ""

    ok = True
    for needle in args.have:
        hits = {f: b.count(needle) for f, b in bodies.items() if needle in b}
        total = sum(hits.values())
        mark = "✓" if total else "✗"
        where = ", ".join(f.rsplit('/', 1)[-1] for f in hits) or "нигде"
        print(f"  {mark} ЕСТЬ «{needle[:52]}»: {total} — {where}")
        ok = ok and bool(total)
    for needle in args.absent:
        hits = {f: b.count(needle) for f, b in bodies.items() if needle in b}
        total = sum(hits.values())
        mark = "✓" if not total else "✗"
        where = ", ".join(f.rsplit('/', 1)[-1] for f in hits) or "—"
        # 🔴 Ненулевой результат ещё не значит «старый код»: строка может жить в другом
        # компоненте. Поэтому печатаем ГДЕ именно, а не просто «найдено».
        print(f"  {mark} НЕТ «{needle[:52]}»: найдено {total} — {where}"
              + ("  (проверь, не из другого ли это компонента)" if total else ""))
        ok = ok and not total

    print("ИТОГ:", "деплой доехал" if ok else "условия НЕ выполнены")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
