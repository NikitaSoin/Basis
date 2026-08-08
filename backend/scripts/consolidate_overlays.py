"""Перенос опубликованных оверлеев прозы обратно в файлы репозитория.

🔴 ЗАЧЕМ. Патчи свежести и перезаписи выводов живут в БД: файлы на Timeweb эфемерны
(контейнер пересобирается при деплое), поэтому витрина читает «оверлей → фолбэк файл».
Побочный эффект — репозиторий отстаёт: на 2026-08-08 разошлись 250 блоков, из них 226
макро. Следующая сессия откроет файл, не увидит оверлея, поправит устаревший текст —
и молча откатит всю накопленную свежесть. Это же ломает и dev-time работу аналитиков.

ПОРЯДОК (нарушать нельзя):
  1. python scripts/consolidate_overlays.py --write   → файлы в рабочем дереве
  2. git add/commit/push, дождаться ДЕПЛОЯ
  3. python scripts/consolidate_overlays.py --mark <ids>  → оверлеи помечаются
     consolidated и перестают подменять файл
Пометить раньше деплоя — значит на время показать пользователю старый текст.

🔴 ПРЕДОХРАНИТЕЛИ (без них массовая перезапись файлов — операция с необратимым
риском): не пишем пустое; не пишем то, что КОРОЧЕ существующего файла более чем на
треть (признак обрезанного/битого текста); по умолчанию режим сухого прогона.
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPANIES = ROOT / "companies"
FUTURES_ASSETS = ROOT / "futures_assets"
BONDS = ROOT / "bonds"
FUNDS = ROOT / "funds"

# вкладка → путь файла прозы (та же таблица, что в card_prose_patcher._tab_path)
TAB_FILE = {
    "business": "business_model.md",
    "finance": "financials_summary.md",
    "governance": "governance_summary.md",
    "markets": "market_summary.md",
    "macro": "macro_summary.md",
    "geo": "geo_summary.md",
    "institutions": "institutions_summary.md",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _api() -> tuple[str, str]:
    base = os.environ.get("BASIS_API") or "https://nikitasoin-basis-a772.twc1.net"
    tok = os.environ.get("DEBUG_API_TOKEN") or ""
    if not tok:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEBUG_API_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
    return base.rstrip("/"), tok


def _get(path: str) -> dict:
    base, tok = _api()
    req = urllib.request.Request(base + path, headers={"X-Debug-Token": tok})
    with urllib.request.urlopen(req, timeout=120, context=_ctx) as r:
        return json.loads(r.read())


def _post(path: str) -> dict:
    base, tok = _api()
    req = urllib.request.Request(base + path, method="POST",
                                 headers={"X-Debug-Token": tok})
    with urllib.request.urlopen(req, timeout=120, context=_ctx) as r:
        return json.loads(r.read())


def _sections(md: str) -> int:
    """Разделы верхнего уровня — признак структурной полноты текста."""
    import re
    return len(re.findall(r"^##\s", md or "", re.M))


def target_path(ticker: str, tab: str) -> Path | None:
    if tab == "futures_asset":
        return FUTURES_ASSETS / ticker / "analysis.md"
    if tab == "bond":
        return BONDS / ticker / "analysis_summary.md"
    if tab == "fund":
        return FUNDS / ticker / "analysis_summary.md"
    fn = TAB_FILE.get(tab)
    return (COMPANIES / ticker.upper() / fn) if fn else None


def fetch_all() -> list[dict]:
    items, offset = [], 0
    while True:
        page = _get(f"/api/debug/export-overlays?limit=60&offset={offset}")
        got = page.get("items") or []
        items += got
        if len(got) < 60:
            break
        offset += 60
        if offset > 3000:      # предохранитель от бесконечной страницы
            break
    return items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="реально записать файлы")
    ap.add_argument("--mark", help="через запятую id оверлеев → пометить consolidated")
    args = ap.parse_args()

    if args.mark:
        print(_post("/api/debug/mark-overlays-consolidated?ids="
                    + urllib.parse.quote(args.mark)))
        return 0

    items = fetch_all()
    print(f"оверлеев к переносу: {len(items)}")
    written, skipped, missing, ids = 0, [], 0, []
    for it in items:
        md = (it.get("md") or "").strip()
        p = target_path(it["ticker"], it["tab"])
        if not p:
            skipped.append(f"{it['ticker']}/{it['tab']}: неизвестная вкладка")
            continue
        if not md:
            skipped.append(f"{it['ticker']}/{it['tab']}: пустой текст")
            continue
        if not p.exists():
            missing += 1          # файла нет — создавать не будем: непонятно, чей это блок
            skipped.append(f"{it['ticker']}/{it['tab']}: файла нет ({p.name})")
            continue
        old = p.read_text(encoding="utf-8")
        if len(md) < len(old) * 0.67:
            skipped.append(f"{it['ticker']}/{it['tab']}: короче существующего "
                           f"({len(md)}/{len(old)}) — не пишу")
            continue
        # 🔴 Длины мало: у NAUK оверлей держит 94% знаков файла, но разделов в нём
        # ДВА против ПЯТИ — многословность уцелевших кусков маскирует пропажу целых
        # блоков. Перенести такой оверлей значит ЗАПИСАТЬ ПОТЕРЮ В РЕПОЗИТОРИЙ, то
        # есть сделать её необратимой. Структуру проверяем отдельно.
        if _sections(md) < _sections(old):
            skipped.append(f"{it['ticker']}/{it['tab']}: разделов меньше "
                           f"({_sections(md)}/{_sections(old)}) — оверлей обеднён, не пишу")
            continue
        if md == old.strip():
            ids.append(str(it["id"]))   # уже совпадает — можно сразу помечать
            continue
        if args.write:
            p.write_text(md + "\n", encoding="utf-8")
        written += 1
        ids.append(str(it["id"]))

    print(f"{'ЗАПИСАНО' if args.write else 'БУДЕТ ЗАПИСАНО (сухой прогон)'}: {written}")
    print(f"пропущено: {len(skipped)} (из них файла нет: {missing})")
    for s in skipped[:12]:
        print("   -", s)
    if len(skipped) > 12:
        print(f"   … ещё {len(skipped) - 12}")
    Path("/tmp/claude-501/overlay_ids.txt").write_text(",".join(ids), encoding="utf-8")
    print(f"id для пометки после деплоя: {len(ids)} шт → /tmp/claude-501/overlay_ids.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
