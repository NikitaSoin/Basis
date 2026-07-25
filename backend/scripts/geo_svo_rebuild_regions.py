"""Пересборка regions_geojson карты СВО по границам из OpenStreetMap.

Владелец (2026-07-25, повторно, со скриншотом): «административные границы
сейчас не ровные — на самой исходной карте пунктиром серым административная
граница проведена, а твоя жёлтая линия не по ней ровно проходит. И так везде».

🔴 ИСТОРИЯ ОШИБКИ (важно, чтобы не повторить): первая попытка брала Natural
Earth admin-1 с рассуждением «это тот же первоисточник, что у админ-линий
подложки». Рассуждение НЕВЕРНОЕ. Подложка карты — OpenFreeMap, а он собран по
схеме OpenMapTiles из данных **OpenStreetMap**. Natural Earth — совершенно
отдельный датасет с собственной генерализацией; совпасть с OSM-линиями он не
мог в принципе, и на зуме расхождение видно глазом. Единственный способ, чтобы
наша заливка легла ровно на серый пунктир подложки, — брать ТУ ЖЕ геометрию,
из которой подложка нарисована, то есть OSM.

Берём границы через Overpass API (admin_level=4 — области Украины и регионы
РФ), собираем мультиполигоны из ways вручную (Overpass отдаёт отношения
членами-линиями, а не готовыми полигонами).

СОХРАНЯЕМ из старого файла: name_ru, control_confidence, control_note
(кураторская аналитика по региону, геометрии не касается).

Запуск:  backend/venv/bin/python3 scripts/geo_svo_rebuild_regions.py
"""
from __future__ import annotations

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVO_MAP = os.path.join(BASE, "config", "geo_map_svo.json")
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".osm_admin4_cache.json")
LAND_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ne_land_cache.geojson")
# Береговая линия для обрезки. OSM-отношения admin_level=4 у приморских регионов
# включают ТЕРРИТОРИАЛЬНЫЕ ВОДЫ — замерено: Крым +59%, Севастополь +257%,
# Херсонская +18%, Запорожская +15%, Одесская +18% к реальной площади суши
# (внутренние регионы при этом сходятся в пределах 0.3%). Без обрезки заливка
# регионов расползается по Чёрному и Азовскому морям. Natural Earth land —
# public domain, точности 10m хватает: расхождение с береговой линией подложки
# в сотни метров несопоставимо с 15 тыс. км² закрашенного моря.
LAND_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
            "master/geojson/ne_10m_land.geojson")

OVERPASS = "https://overpass-api.de/api/interpreter"
QUERY = """
[out:json][timeout:600];
(
  rel["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"~"^UA-"];
  rel["boundary"="administrative"]["admin_level"="4"]["ISO3166-2"~"^RU-(BRY|KRS|BEL|KDA)$"];
);
out geom;
"""

# Упрощение контуров (град.). 0.0008° ≈ 80 м на широте Украины — на масштабе,
# где эти заливки вообще видны, это тоньше линии подложки, но вес файла режет
# в разы (сырые OSM-контуры избыточно детальны для карты страны).
SIMPLIFY_DEG = 0.0008

# ISO-код → (slug, ярус контроля). Слаги СОХРАНЕНЫ от прежнего файла: суффикс
# "_ru" = российский приграничный регион-контекст, его специально исключает
# _ukraine_boundary_from_static_map() при расчёте линии фронта.
MAPPING = {
    "UA-74": ("chernihiv", "ua"), "UA-07": ("volyn", "ua"), "UA-56": ("rivne", "ua"),
    "UA-18": ("zhytomyr", "ua"), "UA-32": ("kyiv_oblast", "ua"), "UA-30": ("kyiv_city", "ua"),
    "UA-21": ("zakarpattia", "ua"), "UA-77": ("chernivtsi", "ua"),
    "UA-26": ("ivano_frankivsk", "ua"), "UA-51": ("odesa", "ua"), "UA-05": ("vinnytsia", "ua"),
    "UA-46": ("lviv", "ua"), "UA-59": ("sumy_oblast", "ua"),
    "UA-63": ("kharkiv_oblast", "ua"),           # владелец: НЕ выделять жёлтым
    "UA-53": ("poltava", "ua"), "UA-68": ("khmelnytskyi", "ua"), "UA-61": ("ternopil", "ua"),
    "UA-71": ("cherkasy", "ua"), "UA-35": ("kirovohrad", "ua"), "UA-48": ("mykolaiv", "ua"),
    "UA-12": ("dnipropetrovsk_oblast", "ua"),
    "UA-09": ("luhansk_oblast", "ru"),
    "UA-14": ("donetsk_oblast", "dnr_disputed"),
    "UA-23": ("zaporizhzhia_oblast", "ru_claimed"),
    "UA-65": ("kherson_oblast", "ru_claimed"),
    "UA-43": ("crimea", "ru"), "UA-40": ("sevastopol", "ru"),
    "RU-BRY": ("bryansk_ru", "ru"), "RU-KRS": ("kursk_ru", "ru"),
    "RU-BEL": ("belgorod_ru", "ru"), "RU-KDA": ("krasnodar_ru", "context"),
}

NAMES_RU = {
    "crimea": "Республика Крым", "sevastopol": "Севастополь",
    "bryansk_ru": "Брянская область", "kursk_ru": "Курская область",
    "belgorod_ru": "Белгородская область", "krasnodar_ru": "Краснодарский край",
}


def fetch_osm() -> dict:
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    import httpx  # httpx, а не urllib: у urllib здесь нет локального CA-бандла
    print("качаю границы из OpenStreetMap через Overpass (может занять 1-3 мин)…")
    # Тело — СЫРОЙ текст запроса, не form-поле: form-кодирование Overpass
    # отвергает с 406. User-Agent обязателен, анонимные клиенты режутся.
    r = httpx.post(OVERPASS, content=QUERY.encode("utf-8"), timeout=600,
                   headers={"User-Agent": "BasisPlatform/1.0 (https://inbasis.ru) geo-admin-boundaries",
                            "Content-Type": "text/plain; charset=utf-8"})
    r.raise_for_status()
    data = r.json()
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def fetch_land():
    """Суша (Natural Earth 10m) в районе интереса — для обрезки приморских
    регионов. Возвращает shapely-геометрию или None (честная деградация:
    без обрезки регионы будут с морем, но карта не сломается)."""
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    try:
        if os.path.exists(LAND_CACHE):
            with open(LAND_CACHE, encoding="utf-8") as f:
                data = json.load(f)
        else:
            import httpx
            print("качаю контур суши (Natural Earth land)…")
            r = httpx.get(LAND_URL, timeout=300, follow_redirects=True)
            r.raise_for_status()
            data = r.json()
            with open(LAND_CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        aoi = box(21.0, 41.0, 45.0, 57.0)  # Украина + юг России с запасом
        parts = []
        for ft in data.get("features", []):
            g = shape(ft["geometry"]).buffer(0)
            if g.intersects(aoi):
                parts.append(g.intersection(aoi))
        return unary_union(parts).buffer(0) if parts else None
    except Exception as e:  # noqa: BLE001
        print(f"ВНИМАНИЕ: контур суши не получен ({type(e).__name__}) — "
              f"регионы останутся с территориальными водами", file=sys.stderr)
        return None


def stitch_rings(ways: list[list[tuple]]) -> list[list[tuple]]:
    """Склеивает разрозненные ways отношения в замкнутые кольца по совпадающим
    концам. Overpass отдаёт границу как набор линий в произвольном порядке и
    произвольном направлении — готовых колец там нет."""
    pending = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while pending:
        ring = pending.pop(0)
        changed = True
        while changed and ring[0] != ring[-1]:
            changed = False
            for i, w in enumerate(pending):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += list(reversed(w))[1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = list(reversed(w))[:-1] + ring
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def build_geometry(rel: dict):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    outer_ways, inner_ways = [], []
    for m in rel.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        coords = [(round(p["lon"], 7), round(p["lat"], 7)) for p in m["geometry"]]
        (inner_ways if m.get("role") == "inner" else outer_ways).append(coords)

    outers = [Polygon(r).buffer(0) for r in stitch_rings(outer_ways) if len(r) >= 4]
    inners = [Polygon(r).buffer(0) for r in stitch_rings(inner_ways) if len(r) >= 4]
    if not outers:
        return None
    geom = unary_union(outers)
    if inners:
        geom = geom.difference(unary_union(inners))
    return geom.buffer(0)


def main() -> int:
    from shapely.geometry import mapping
    from shapely.geometry.polygon import orient

    osm = fetch_osm()
    by_iso = {}
    for el in osm.get("elements", []):
        iso = (el.get("tags") or {}).get("ISO3166-2")
        if iso in MAPPING:
            by_iso[iso] = el

    missing = [iso for iso in MAPPING if iso not in by_iso]
    if missing:
        print(f"ОШИБКА: не пришли из OSM: {missing}", file=sys.stderr)
        return 1

    with open(SVO_MAP, encoding="utf-8") as f:
        svo = json.load(f)
    old_by_slug = {ft["properties"].get("slug"): ft["properties"]
                   for ft in svo["base_map"]["regions_geojson"]["features"]}

    land = fetch_land()

    features = []
    for iso, (slug, control) in MAPPING.items():
        geom = build_geometry(by_iso[iso])
        if geom is None or geom.is_empty:
            print(f"ОШИБКА: пустая геометрия у {slug} ({iso})", file=sys.stderr)
            return 1
        if land is not None:
            clipped = geom.intersection(land)
            if not clipped.is_empty:
                geom = clipped
        geom = geom.simplify(SIMPLIFY_DEG, preserve_topology=True)
        geoms = [orient(g, sign=1.0) for g in
                 (list(geom.geoms) if hasattr(geom, "geoms") else [geom])
                 if not g.is_empty and g.area > 0]
        out_geom = (mapping(geoms[0]) if len(geoms) == 1 else
                    {"type": "MultiPolygon",
                     "coordinates": [mapping(g)["coordinates"] for g in geoms]})

        old = old_by_slug.get(slug, {})
        props = {
            "name_ru": NAMES_RU.get(slug) or old.get("name_ru")
                        or (by_iso[iso].get("tags") or {}).get("name:ru"),
            "control": control,
            "slug": slug,
        }
        for k in ("control_confidence", "control_note"):
            if old.get(k) is not None:
                props[k] = old[k]
        features.append({"type": "Feature", "properties": props, "geometry": out_geom})

    svo["base_map"]["regions_geojson"] = {"type": "FeatureCollection", "features": features}
    svo["base_map"]["regions_source"] = (
        "OpenStreetMap (Overpass, admin_level=4, ODbL) — ТОТ ЖЕ первоисточник, "
        "из которого построена подложка OpenFreeMap/OpenMapTiles, поэтому заливка "
        f"ложится ровно на её админ-линии; упрощение {SIMPLIFY_DEG}° (~80 м)"
    )
    svo["base_map"]["control_legend"] = {
        "ru": "под контролем России",
        "dnr_disputed": "основной территориальный спор сейчас",
        "ru_claimed": "территория России, не находящаяся под её контролем",
        "ua": "под контролем Украины",
    }
    svo["base_map"]["control_paint_opacity"] = {"ua": 0, "context": 0}

    with open(SVO_MAP, "w", encoding="utf-8") as f:
        json.dump(svo, f, ensure_ascii=False, indent=2)

    print(f"готово: {len(features)} регионов, "
          f"geo_map_svo.json = {os.path.getsize(SVO_MAP) / 1024 / 1024:.2f} МБ")
    by_tier: dict[str, list[str]] = {}
    for ft in features:
        by_tier.setdefault(ft["properties"]["control"], []).append(ft["properties"]["slug"])
    for tier, slugs in sorted(by_tier.items()):
        print(f"  {tier:14s} ({len(slugs)}): {', '.join(sorted(slugs))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
