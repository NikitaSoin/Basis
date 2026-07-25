"""Пересборка regions_geojson карты СВО на РЕАЛЬНЫХ административных границах.

Владелец (2026-07-25, после живой проверки): «твои оранжевые и розовые линии
проведены не ровно по административным границам регионов, а примерно (просто
набор кривых), из-за чего все это выглядит супер криво и некрасиво — ты можешь
провести ровно по административным границам (у нас вот сама карта которая
выводится — на ней сереньким административные линии проведены)».

Раньше regions_geojson рисовался вручную (грубые многоугольники «на глаз»),
поэтому наши заливки не совпадали с админ-линиями подложки OpenFreeMap.
Здесь берём Natural Earth admin-1 (10m, PUBLIC DOMAIN — можно свободно
переиспользовать, в отличие от GADM/OSM-производных с их лицензиями) — тот же
первоисточник, из которого сделаны админ-линии большинства подложек, поэтому
границы совпадают с серыми линиями тайлов.

СОХРАНЯЕМ из старого файла: name_ru, control_confidence, control_note
(кураторская аналитика по каждому региону — её геометрия не касается).
ЗАМЕНЯЕМ: geometry (реальные границы) + control (новые ярусы, см. ниже).

Ярусы (владелец, там же):
  ru           — под контролем России
  ru_claimed   — «территория России, не находящаяся под её контролем»
                 (Запорожская, Херсонская: конституционно РФ, контроль частичный)
  dnr_disputed — «основной территориальный спор сейчас» (Донецкая область целиком)
  ua           — под контролем Украины (Харьковская/Сумская/Днепропетровская
                 ТОЖЕ здесь: «Харьковскую область не надо вообще как регион
                 желтым выделять»)

Запуск разовый/по мере надобности:
    backend/venv/bin/python3 scripts/geo_svo_rebuild_regions.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVO_MAP = os.path.join(BASE, "config", "geo_map_svo.json")
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          "master/geojson/ne_10m_admin_1_states_provinces.geojson")
NE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ne_admin1_cache.geojson")

# Упрощение границ: 0.003° ≈ 300 м на широте Украины. На масштабе «страна/
# область» (единственный, где эти заливки вообще видны) это ниже толщины линии,
# но режет вес файла в разы — 10m-контуры Natural Earth избыточно детальны.
SIMPLIFY_DEG = 0.003

# NE-имя (admin, name) → (slug, control). Слаги СОХРАНЕНЫ от старого файла:
# суффикс "_ru" = российский приграничный регион-контекст, его специально
# исключает _ukraine_boundary_from_static_map() при расчёте линии фронта.
MAPPING = {
    ("Ukraine", "Chernihiv"): ("chernihiv", "ua"),
    ("Ukraine", "Volyn"): ("volyn", "ua"),
    ("Ukraine", "Rivne"): ("rivne", "ua"),
    ("Ukraine", "Zhytomyr"): ("zhytomyr", "ua"),
    ("Ukraine", "Kiev"): ("kyiv_oblast", "ua"),
    ("Ukraine", "Kiev City"): ("kyiv_city", "ua"),
    ("Ukraine", "Transcarpathia"): ("zakarpattia", "ua"),
    ("Ukraine", "Chernivtsi"): ("chernivtsi", "ua"),
    ("Ukraine", "Ivano-Frankivs'k"): ("ivano_frankivsk", "ua"),
    ("Ukraine", "Odessa"): ("odesa", "ua"),
    ("Ukraine", "Vinnytsya"): ("vinnytsia", "ua"),
    ("Ukraine", "L'viv"): ("lviv", "ua"),
    ("Ukraine", "Sumy"): ("sumy_oblast", "ua"),
    ("Ukraine", "Kharkiv"): ("kharkiv_oblast", "ua"),          # владелец: НЕ жёлтым
    ("Ukraine", "Poltava"): ("poltava", "ua"),
    ("Ukraine", "Khmel'nyts'kyy"): ("khmelnytskyi", "ua"),
    ("Ukraine", "Ternopil'"): ("ternopil", "ua"),
    ("Ukraine", "Cherkasy"): ("cherkasy", "ua"),
    ("Ukraine", "Kirovohrad"): ("kirovohrad", "ua"),
    ("Ukraine", "Mykolayiv"): ("mykolaiv", "ua"),
    ("Ukraine", "Dnipropetrovs'k"): ("dnipropetrovsk_oblast", "ua"),
    ("Ukraine", "Luhans'k"): ("luhansk_oblast", "ru"),
    ("Ukraine", "Donets'k"): ("donetsk_oblast", "dnr_disputed"),
    ("Ukraine", "Zaporizhzhya"): ("zaporizhzhia_oblast", "ru_claimed"),
    ("Ukraine", "Kherson"): ("kherson_oblast", "ru_claimed"),
    # Natural Earth 10m относит Крым и Севастополь к admin="Russia"
    ("Russia", "Crimea"): ("crimea", "ru"),
    ("Russia", "Sevastopol"): ("sevastopol", "ru"),
    # Российские приграничные регионы — контекст соседних событий
    ("Russia", "Bryansk"): ("bryansk_ru", "ru"),
    ("Russia", "Kursk"): ("kursk_ru", "ru"),
    ("Russia", "Belgorod"): ("belgorod_ru", "ru"),
    ("Russia", "Krasnodar"): ("krasnodar_ru", "context"),
}

# Явные русские названия — NE даёт «Автономная Республика Крым», для российской
# платформы это устаревшая форма; остальные названия NE корректны, но задаём
# все явно, чтобы вид не зависел от правок вышестоящего датасета.
NAMES_RU = {
    "crimea": "Республика Крым", "sevastopol": "Севастополь",
    "bryansk_ru": "Брянская область", "kursk_ru": "Курская область",
    "belgorod_ru": "Белгородская область", "krasnodar_ru": "Краснодарский край",
}


def load_ne() -> dict:
    if os.path.exists(NE_CACHE):
        with open(NE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    print(f"качаю Natural Earth admin-1 (~39 МБ): {NE_URL}")
    with urllib.request.urlopen(NE_URL, timeout=300) as r:
        data = json.loads(r.read().decode("utf-8"))
    with open(NE_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def main() -> int:
    from shapely.geometry import shape, mapping
    from shapely.geometry.polygon import orient

    ne = load_ne()
    with open(SVO_MAP, encoding="utf-8") as f:
        svo = json.load(f)

    old_by_slug = {ft["properties"].get("slug"): ft["properties"]
                   for ft in svo["base_map"]["regions_geojson"]["features"]}

    found: dict[str, dict] = {}
    for ft in ne["features"]:
        key = (ft["properties"].get("admin"), ft["properties"].get("name"))
        if key in MAPPING:
            found[MAPPING[key][0]] = ft

    missing = [s for (_, (s, _c)) in MAPPING.items() if s not in found]
    if missing:
        print(f"ОШИБКА: не нашлись в Natural Earth: {missing}", file=sys.stderr)
        return 1

    features = []
    for (admin, ne_name), (slug, control) in MAPPING.items():
        ft = found[slug]
        geom = shape(ft["geometry"]).buffer(0).simplify(SIMPLIFY_DEG, preserve_topology=True)
        if geom.is_empty:
            print(f"ОШИБКА: пустая геометрия после упрощения: {slug}", file=sys.stderr)
            return 1
        geoms = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        geoms = [orient(g, sign=1.0) for g in geoms if not g.is_empty and g.area > 0]
        if len(geoms) == 1:
            out_geom = mapping(geoms[0])
        else:
            out_geom = {"type": "MultiPolygon", "coordinates": [mapping(g)["coordinates"] for g in geoms]}

        old = old_by_slug.get(slug, {})
        props = {
            "name_ru": NAMES_RU.get(slug) or old.get("name_ru") or ft["properties"].get("name_ru"),
            "control": control,
            "slug": slug,
        }
        # Кураторская аналитика по региону геометрии не касается — переносим как есть.
        for k in ("control_confidence", "control_note"):
            if old.get(k) is not None:
                props[k] = old[k]
        features.append({"type": "Feature", "properties": props, "geometry": out_geom})

    svo["base_map"]["regions_geojson"] = {"type": "FeatureCollection", "features": features}
    svo["base_map"]["regions_source"] = (
        "Natural Earth admin-1 (10m, public domain) — реальные административные "
        "границы, совпадают с админ-линиями подложки; упрощение "
        f"{SIMPLIFY_DEG}° (~300 м)"
    )
    svo["base_map"]["control_legend"] = {
        "ru": "под контролем России",
        "dnr_disputed": "основной территориальный спор сейчас",
        "ru_claimed": "территория России, не находящаяся под её контролем",
        "ua": "под контролем Украины",
    }
    # "ua" не красим (юр./редакционное решение владельца, было и раньше);
    # "context" (Краснодарский край) — фон соседа, тоже без заливки.
    svo["base_map"]["control_paint_opacity"] = {"ua": 0, "context": 0}

    with open(SVO_MAP, "w", encoding="utf-8") as f:
        json.dump(svo, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(SVO_MAP) / 1024 / 1024
    print(f"готово: {len(features)} регионов, geo_map_svo.json = {size_mb:.2f} МБ")
    by_tier: dict[str, list[str]] = {}
    for ft in features:
        by_tier.setdefault(ft["properties"]["control"], []).append(ft["properties"]["slug"])
    for tier, slugs in sorted(by_tier.items()):
        print(f"  {tier:14s} ({len(slugs)}): {', '.join(sorted(slugs))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
