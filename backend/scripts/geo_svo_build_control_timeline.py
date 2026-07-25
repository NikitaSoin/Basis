"""Сборка ХРОНОЛОГИИ КОНТРОЛЯ населённых пунктов из docs/svo-conflict-history.md.

Зачем: старый config/geo_svo_dated_settlements.json (265 точек из Wikipedia)
содержит ТОЛЬКО переходы к РФ — ни одного отката. Из-за этого историческая
реконструкция линии фронта математически не могла показать ни харьковский
откат сентября-2022 (~12 тыс. км²), ни оставление правобережья Херсона, а
кривая «км²/месяц» не могла стать отрицательной ни в одном месяце. Владелец
(2026-07-25): «надо прям копнуть и восстановить ход конфликта по настоящему...
заодно кстати сделай отдельный файл для базы знаний с историей конфликта».

Здесь парсим таблицы Части 2 базы знаний (docs/svo-conflict-history.md), где
переходы записаны В ОБЕ СТОРОНЫ, склеиваем с уже геокодированными точками
старого датасета, недостающие координаты добираем через Wikipedia API, и
выдаём config/geo_svo_control_timeline.json — по каждому пункту СПИСОК
переходов (дата → владелец), а не одну дату.

Запуск:  backend/venv/bin/python3 scripts/geo_svo_build_control_timeline.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_MD = os.path.join(os.path.dirname(BASE), "docs", "svo-conflict-history.md")
OLD_DATASET = os.path.join(BASE, "config", "geo_svo_dated_settlements.json")
OUT_PATH = os.path.join(BASE, "config", "geo_svo_control_timeline.json")

UA = "BasisPlatform/1.0 (https://inbasis.ru) geo-timeline-builder"

# Строки-агрегаты («Киевская обл. (север, целиком)») — это не населённый пункт,
# точечная геометрия для них бессмысленна; фиксируем отдельно как областные
# события, в геометрию не идут.
AGGREGATE_RE = re.compile(r"\bобл\.|\bобласть\b", re.IGNORECASE)


def parse_history_tables(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Часть 2 — от заголовка до следующей Части
    m = re.search(r"^## Часть 2\..*?(?=^## Часть 3\.)", text, re.S | re.M)
    if not m:
        print("ОШИБКА: не нашёл Часть 2 в базе знаний", file=sys.stderr)
        return []
    rows = []
    for line in m.group(0).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 7:
            continue
        if cells[0] in ("название_рус",) or set(cells[0]) <= set("-: "):
            continue
        name_ru, name_lat, oblast, date, holder, precision, source = cells
        if not re.match(r"^\d{4}(-\d{2}){0,2}$", date):
            continue
        rows.append({
            "name": name_ru, "name_lat": name_lat, "oblast": oblast,
            "date": date, "holder": "RF" if holder.strip() == "РФ" else "UA",
            "precision": precision, "source": source,
            "is_aggregate": bool(AGGREGATE_RE.search(name_ru)),
        })
    return rows


def normalize_date(d: str) -> str:
    """YYYY / YYYY-MM → конец периода (реконструкция помесячная, точнее не нужно)."""
    if len(d) == 4:
        return f"{d}-12-31"
    if len(d) == 7:
        return f"{d}-28"
    return d


def geocode(name_lat: str, name_ru: str, oblast: str = "") -> tuple[float, float] | None:
    """Wikipedia API. httpx, НЕ urllib: urllib на этой машине падает с
    CERTIFICATE_VERIFY_FAILED (нет локального CA-бандла), httpx несёт свой
    через certifi — та же связка уже работает в app/services/geo_digest.py."""
    import httpx

    # Тёзок много (Александровка/Новосёловка и т.п.) — уточняем областью, где
    # можем; см. «4.5. Тёзки и двойные названия» в базе знаний.
    region_hint = oblast.replace(" (РФ)", "").strip()
    variants = [("en", name_lat), ("ru", name_ru)]
    if region_hint:
        variants += [("ru", f"{name_ru} ({region_hint.replace('ая', 'ой')} области)")]
    for lang, title in variants:
        if not title:
            continue
        try:
            r = httpx.get(f"https://{lang}.wikipedia.org/w/api.php", params={
                "action": "query", "titles": title, "prop": "coordinates",
                "format": "json", "redirects": 1,
            }, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                co = page.get("coordinates")
                if co:
                    return co[0]["lat"], co[0]["lon"]
        except Exception:  # noqa: BLE001 — недостающая координата не фатальна
            pass
        time.sleep(0.15)
    return None


def main() -> int:
    rows = parse_history_tables(HISTORY_MD)
    if not rows:
        return 1
    aggregates = [r for r in rows if r["is_aggregate"]]
    points = [r for r in rows if not r["is_aggregate"]]
    print(f"из базы знаний: {len(rows)} переходов "
          f"({len(points)} по НП, {len(aggregates)} областных агрегатов), "
          f"из них откатов к Украине: {sum(1 for r in rows if r['holder'] == 'UA')}")

    # Координаты из уже геокодированного старого датасета (по латинскому имени)
    with open(OLD_DATASET, encoding="utf-8") as f:
        old = json.load(f)
    coords_by_lat = {}
    for d in old:
        key = (d.get("name") or "").strip().lower()
        if key and d.get("lat") is not None:
            coords_by_lat[key] = (d["lat"], d["lon"])

    by_settlement: dict[tuple[str, str], dict] = {}
    for r in points:
        key = (r["name"], r["oblast"])
        entry = by_settlement.setdefault(key, {
            "name": r["name"], "name_lat": r["name_lat"], "oblast": r["oblast"],
            "lat": None, "lon": None, "transitions": [],
        })
        entry["transitions"].append({
            "date": normalize_date(r["date"]), "holder": r["holder"],
            "precision": r["precision"], "source": r["source"],
        })

    hit_cache = hit_geo = missed = 0
    for entry in by_settlement.values():
        c = coords_by_lat.get((entry["name_lat"] or "").strip().lower())
        if c:
            entry["lat"], entry["lon"] = c
            hit_cache += 1
            continue
        c = geocode(entry["name_lat"], entry["name"], entry["oblast"])
        if c:
            entry["lat"], entry["lon"] = c
            hit_geo += 1
        else:
            missed += 1
            print(f"  без координат: {entry['name']} ({entry['name_lat']}, {entry['oblast']})")

    for entry in by_settlement.values():
        entry["transitions"].sort(key=lambda t: t["date"])

    settlements = [e for e in by_settlement.values() if e["lat"] is not None]
    multi = [e for e in settlements if len(e["transitions"]) > 1]
    out = {
        "note": (
            "Хронология контроля населённых пунктов: по каждому — СПИСОК переходов "
            "(дата → владелец RF/UA), а не одна дата. Собрано скриптом "
            "scripts/geo_svo_build_control_timeline.py из docs/svo-conflict-history.md "
            "(Часть 2). В отличие от geo_svo_dated_settlements.json (265 точек Wikipedia, "
            "ТОЛЬКО переходы к РФ), здесь есть ОБРАТНЫЕ переходы — без них историческая "
            "реконструкция не могла показать откат сентября-2022 и оставление правобережья "
            "Херсона, а «км²/месяц» не могла быть отрицательной."
        ),
        "aggregate_events": [
            {"name": r["name"], "oblast": r["oblast"], "date": normalize_date(r["date"]),
             "holder": r["holder"], "precision": r["precision"], "source": r["source"]}
            for r in aggregates
        ],
        "settlements": sorted(settlements, key=lambda e: e["name"]),
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"\nготово: {len(settlements)} НП с координатами "
          f"(из кэша {hit_cache}, геокодировано {hit_geo}, без координат {missed})")
    print(f"  из них с НЕСКОЛЬКИМИ переходами (переходили из рук в руки): {len(multi)}")
    for e in multi:
        chain = " → ".join(f"{t['date']}:{t['holder']}" for t in e["transitions"])
        print(f"    {e['name']:22s} {chain}")
    print(f"  областных агрегатов (в геометрию не идут): {len(out['aggregate_events'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
