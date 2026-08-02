#!/usr/bin/env python3
"""Timeweb Cloud через API: смотреть деплои и ЛОГИ СБОРКИ своими глазами.

ЗАЧЕМ: 2026-08-03 деплой фронта встал, и вся диагностика шла через пересказ — владелец
копировал вывод авто-помощника панели, тот сочинял правдоподобные, но ложные причины
(«detached HEAD», «команда build:prebuilt») без доступа к логам. Час ушёл на опровержение
догадок. С этим скриптом лог сборки читается напрямую: причина видна, а не выводится.

ТОКЕН — в backend/.env, ключ TIMEWEB_TOKEN. Берётся в панели Timeweb Cloud:
  Настройки аккаунта → «API и Terraform» → создать токен (права на чтение достаточно,
  если не нужен запуск деплоя).

Запуск:
  python3 scripts/timeweb.py apps            — список приложений и их id
  python3 scripts/timeweb.py deploys <id>    — последние деплои: статус, время, коммит
  python3 scripts/timeweb.py log <id>        — лог сборки ПОСЛЕДНЕГО деплоя
  python3 scripts/timeweb.py log <id> <dep>  — лог конкретного деплоя
  python3 scripts/timeweb.py deploy <id>     — ЗАПУСТИТЬ деплой (единственное действие,
                                               что-то меняющее; всё остальное — чтение)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.timeweb.cloud/api/v1"


def _token() -> str:
    t = (os.environ.get("TIMEWEB_TOKEN") or "").strip()
    if not t:
        env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.startswith("TIMEWEB_TOKEN="):
                    t = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not t:
        sys.exit("Нет токена. Положите TIMEWEB_TOKEN в backend/.env "
                 "(панель → Настройки аккаунта → «API и Terraform»).")
    return t


def call(path: str, method: str = "GET", body: dict | None = None, quiet: bool = False):
    """Запрос к API. quiet=True — не падать на 404: у разных версий API пути к логам
    называются по-разному, и мы честно перебираем варианты, а не гадаем один."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers={
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_text": raw}
    except urllib.error.HTTPError as e:
        if quiet:
            return None
        detail = e.read().decode("utf-8", "replace")[:500]
        if e.code in (401, 403):
            sys.exit(f"Ошибка {e.code}: токен не подошёл (истёк или без нужных прав).\n{detail}")
        sys.exit(f"Ошибка API {e.code}: {detail}")


def cmd_apps():
    r = call("/apps")
    apps = r.get("apps", r.get("app", []))
    if not apps:
        print("Приложений не найдено. Ответ:", json.dumps(r, ensure_ascii=False)[:400])
        return
    print(f"{'id':<12} {'имя':<28} {'тип':<12} статус")
    for a in apps:
        print(f"{str(a.get('id','')):<12} {str(a.get('name',''))[:28]:<28} "
              f"{str(a.get('type',''))[:12]:<12} {a.get('status','')}")
        # Настройки сборки — то, что я трижды просил снять руками с экрана панели
        for k in ("framework", "build_cmd", "run_cmd", "index_dir", "commit_sha", "branch_name",
                  "repository", "is_auto_deploy"):
            if a.get(k) not in (None, ""):
                print(f"    {k}: {a[k]}")


def cmd_deploys(app_id: str):
    r = call(f"/apps/{app_id}/deploys")
    deps = r.get("deploys", [])
    if not deps:
        print("Деплоев нет. Ответ:", json.dumps(r, ensure_ascii=False)[:400])
        return
    print(f"{'id':<12} {'статус':<14} {'начат':<22} коммит")
    for d in deps[:15]:
        print(f"{str(d.get('id','')):<12} {str(d.get('status',''))[:14]:<14} "
              f"{str(d.get('created_at',''))[:19]:<22} {str(d.get('commit_sha',''))[:10]}")


def cmd_log(app_id: str, deploy_id: str | None = None):
    if deploy_id is None:
        deps = call(f"/apps/{app_id}/deploys").get("deploys", [])
        if not deps:
            sys.exit("Деплоев нет.")
        deploy_id = str(deps[0].get("id"))
        print(f"(последний деплой: {deploy_id}, статус {deps[0].get('status')})\n")
    # Пути к логам у API отличались между версиями — перебираем, а не гадаем
    for path in (f"/apps/{app_id}/deploys/{deploy_id}/build-logs",
                 f"/apps/{app_id}/deploys/{deploy_id}/logs",
                 f"/apps/{app_id}/deploy/{deploy_id}/build-logs"):
        r = call(path, quiet=True)
        if r is None:
            continue
        items = r.get("build_logs") or r.get("logs") or r.get("_text") or r
        if isinstance(items, str):
            print(items)
        elif isinstance(items, list):
            for it in items:
                print(it.get("message", it) if isinstance(it, dict) else it)
        else:
            print(json.dumps(items, ensure_ascii=False, indent=2)[:8000])
        return
    print("Лог по известным путям не отдался — возможно, деплой ещё не начинался "
          "(тогда и логов нет) либо API изменил адрес. Проверь: python3 scripts/timeweb.py deploys <id>")


def cmd_deploy(app_id: str):
    r = call(f"/apps/{app_id}/deploy", method="POST", body={})
    print("Деплой запущен:", json.dumps(r, ensure_ascii=False)[:300])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "apps"
    if cmd == "apps": cmd_apps()
    elif cmd == "deploys": cmd_deploys(sys.argv[2])
    elif cmd == "log": cmd_log(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "deploy": cmd_deploy(sys.argv[2])
    else: print(__doc__)
