"""Справочник населённых пунктов Украины с координатами — для привязки
заявлений о взятии (владелец, 2026-09-14: «сделай» — полный справочник вместо
защиты по 64 городам; см. work-journal).

Источник — OpenStreetMap через Overpass (ODbL, тот же первоисточник, что и
контуры областей карты СВО). Почему не Википедия: геокодер по статьям находит
тёзок («Красный Кут» Донецкой области уехал в Саратовскую), а у сёл статья
часто называется иначе или без координат. Почему не GeoNames: у сёл там редко
есть русское написание, а наши источники (МО РФ, Рыбарь) пишут по-русски и
нередко СТАРЫМИ названиями («Красноармейск», «Димитров») — в OSM для этого есть
old_name/alt_name.

Как собирается (все запросы кэшируются в scripts/.gazetteer_cache/, повтор
не ходит в сеть):
  1. Узлы place=city|town|village|hamlet по 9 плиткам-прямоугольникам,
     покрывающим Украину (запрос по bbox — самый дешёвый для Overpass; запрос
     «по площади области/района» на публичных зеркалах падает по таймауту).
  2. Область — точка-в-полигоне по нашим контурам областей
     (config/geo_map_svo.json, regions_geojson, те же OSM-границы). Узлы вне
     Украины (плитки задевают соседей) отбрасываются.
  3. Район — ТОЛЬКО для прифронтовых областей и только если Overpass отдаст
     узлы по площади района (map_to_area); иначе район пустой — честная
     деградация, район у нас лишь подсказка при тёзках, а не ключ.
Результат — config/geo_ua_settlements.json.gz (сжат: ~30 тыс. записей).

Запуск: cd backend && ./venv/bin/python scripts/geo_ua_gazetteer_build.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CACHE = os.path.join(HERE, ".gazetteer_cache")
OUT = os.path.join(BACKEND, "config", "geo_ua_settlements.json.gz")
SVO_MAP = os.path.join(BACKEND, "config", "geo_map_svo.json")

MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
UA = {"User-Agent": "BasisPlatform/1.0 (https://inbasis.ru) geo-gazetteer"}
PLACES = "^(city|town|village|hamlet)$"

# Плитки (S, W, N, E) — Украина целиком с запасом; соседи отсеются по контурам.
LAT_BANDS = [(44.0, 47.0), (47.0, 49.5), (49.5, 52.5)]
LON_BANDS = [(22.0, 28.0), (28.0, 34.0), (34.0, 40.5)]
# Прифронтовые области, где тёзки внутри области реально мешают: для них
# пробуем узнать район. ISO-коды OSM (ISO3166-2).
FRONT_OBLASTS = {"UA-14": "Донецкая", "UA-09": "Луганская", "UA-23": "Запорожская",
                 "UA-65": "Херсонская", "UA-63": "Харьковская", "UA-12": "Днепропетровская",
                 "UA-59": "Сумская", "UA-48": "Николаевская"}


def _cached(key: str):
    path = os.path.join(CACHE, key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


def _store(key: str, data) -> None:
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, key + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def overpass(key: str, query: str, timeout: float = 300.0, attempts: int = 2):
    """Запрос с кэшем, перебором зеркал и паузами (публичные зеркала режут
    частые запросы; MOEX-правило «последовательно с паузами» и здесь)."""
    hit = _cached(key)
    if hit is not None:
        return hit
    last = None
    for _ in range(attempts):
        for m in MIRRORS:
            t = time.time()
            try:
                r = httpx.post(m, data={"data": query}, timeout=timeout, headers=UA)
                if r.status_code == 200:
                    data = r.json()
                    if "elements" in data:
                        _store(key, data)
                        print(f"  {key}: {len(data['elements'])} эл., {round(time.time() - t, 1)} с, {m.split('/')[2]}")
                        time.sleep(2.0)
                        return data
                last = f"{m}: HTTP {r.status_code}"
            except Exception as e:  # noqa: BLE001
                last = f"{m}: {type(e).__name__}"
            print(f"  {key}: не вышло ({last}), следующее зеркало", flush=True)
            time.sleep(3.0)
    print(f"  {key}: ВСЕ зеркала отказали ({last})", flush=True)
    return None


def _oblast_key(name_ru: str | None) -> str | None:
    """Первое слово названия области как ключ: «Донецкая область» → «Донецкая».
    Исключения — регионы, у которых первое слово не имя: «Республика Крым» →
    «Крым», «Киев (город)» → «Киев»."""
    if not name_ru:
        return None
    if "Крым" in name_ru:
        return "Крым"
    return name_ru.split()[0].strip("(),")


def load_oblasts():
    """[(name_ru-первое слово, shapely-полигон)] — области Украины из нашей карты
    (регионы с slug без суффикса _ru — те внутри Украины, включая Крым/Севастополь)."""
    from shapely.geometry import shape
    with open(SVO_MAP, encoding="utf-8") as f:
        feats = json.load(f)["base_map"]["regions_geojson"]["features"]
    out = []
    for ft in feats:
        slug = ft["properties"].get("slug", "")
        if slug.endswith("_ru"):
            continue
        name = (ft["properties"].get("name_ru") or "").strip()
        try:
            out.append((name, shape(ft["geometry"]).buffer(0)))
        except Exception:  # noqa: BLE001
            continue
    return out


def main() -> int:
    from shapely.geometry import Point
    from shapely.strtree import STRtree

    oblasts = load_oblasts()
    print(f"областей в контурах: {len(oblasts)}")
    polys = [g for _, g in oblasts]
    tree = STRtree(polys)

    # ---- 1. узлы по плиткам --------------------------------------------
    # Плотную плитку (Донбасс + приграничье РФ) публичные зеркала не отдают —
    # 504 на всех. Тогда делим её на четыре и спрашиваем по частям (рекурсивно,
    # до 0.5°): маленький запрос проходит там, где большой падает.
    nodes: dict[int, dict] = {}

    def fetch_tile(s, w, n, e) -> bool:
        key = f"tile2_{s}_{w}_{n}_{e}"
        # nwr: часть сёл в OSM обозначена не точкой, а контуром (way/relation) без
        # узла place — без них тёзка из другой области выглядела бы единственной.
        # body — теги + координаты узлов (out tags координат НЕ отдаёт), center —
        # центр для контуров.
        q = (f'[out:json][timeout:300][maxsize:536870912];\n'
             f'nwr["place"~"{PLACES}"]({s},{w},{n},{e});\nout body center qt;')
        data = overpass(key, q, attempts=1)
        if data is not None:
            for el in data["elements"]:
                if el.get("type") != "node" and el.get("center"):
                    el = {**el, "lat": el["center"]["lat"], "lon": el["center"]["lon"]}
                if el.get("lat") is not None and el.get("tags", {}).get("name"):
                    # id уникален только внутри типа: узел и контур могут совпасть по числу
                    nodes[f"{el.get('type', 'node')[0]}{el['id']}"] = el
            return True
        if (n - s) <= 0.5 or (e - w) <= 0.5:
            return False
        ms, mw = round((s + n) / 2, 3), round((w + e) / 2, 3)
        print(f"  {key}: делю на четыре", flush=True)
        return all([fetch_tile(s, w, ms, mw), fetch_tile(s, mw, ms, e),
                    fetch_tile(ms, w, n, mw), fetch_tile(ms, mw, n, e)])

    for (s, n) in LAT_BANDS:
        for (w, e) in LON_BANDS:
            if not fetch_tile(s, w, n, e):
                print("плитка не получена даже по частям — справочник будет неполным, прерываю", file=sys.stderr)
                return 2
    print(f"узлов в плитках (с соседями): {len(nodes)}")

    # ---- 2. область по контуру -----------------------------------------
    records: dict = {}
    for nid, el in nodes.items():
        pt = Point(el["lon"], el["lat"])
        idx = tree.query(pt, predicate="within")
        if len(idx) == 0:
            continue
        name_obl = oblasts[int(idx[0])][0]
        tags = el.get("tags", {})
        rec = {
            "id": nid, "lat": round(el["lat"], 5), "lon": round(el["lon"], 5),  # id: n<узел>|w<линия>|r<отношение>
            "t": tags.get("place"),
            "n": tags.get("name:ru") or None,           # русское название
            "u": tags.get("name:uk") or tags.get("name") or None,  # украинское
            "o": _oblast_key(name_obl),
        }
        alts = []
        for k in ("old_name:ru", "old_name", "alt_name:ru", "alt_name", "official_name:ru", "name:ru-Latn"):
            v = tags.get(k)
            if v:
                alts.extend(x.strip() for x in v.split(";") if x.strip())
        if alts:
            rec["a"] = sorted(set(alts))
        records[nid] = rec
    # Село и точкой, и контуром — одна запись: контур выбрасываем, если в 2 км есть
    # узел с тем же именем (иначе каждое такое село стало бы «тёзкой» самому себе).
    by_name: dict[str, list] = {}
    for nid, rec in records.items():
        by_name.setdefault((rec.get("n") or rec.get("u") or "").lower(), []).append(nid)
    dropped = 0
    for name, ids_ in by_name.items():
        nodes_ = [i for i in ids_ if str(i).startswith("n")]
        for i in ids_:
            if str(i).startswith("n"):
                continue
            r = records[i]
            if any(abs(records[j]["lat"] - r["lat"]) < 0.045 and abs(records[j]["lon"] - r["lon"]) < 0.07 for j in nodes_):  # ~5 км
                records.pop(i, None)
                dropped += 1
    print(f"внутри Украины: {len(records)} (контуров-дублей убрано {dropped}); "
          f"с name:ru: {sum(1 for r in records.values() if r['n'])}")

    # ---- 3. район для прифронтовых областей (необязательно) ------------
    # Запросы «по площади района» на публичных зеркалах идут по минуте и чаще
    # падают, чем проходят; район — лишь подсказка при тёзках. Поэтому шаг
    # можно пропустить (GAZETTEER_SKIP_RAIONS=1) и добрать позже: кэш
    # запросов сохраняется, повторный прогон дописывает районы к тем же записям.
    raion_hits = 0
    for iso, obl_ru in ({} if os.environ.get("GAZETTEER_SKIP_RAIONS") else FRONT_OBLASTS).items():
        q_r = (f'[out:json][timeout:120];\narea["ISO3166-2"="{iso}"]->.a;\n'
               f'rel["boundary"="administrative"]["admin_level"="6"](area.a);\nout tags;')
        rels = overpass(f"raions_{iso}", q_r, timeout=150)
        if not rels:
            continue
        for rel in rels["elements"]:
            rname = (rel.get("tags", {}).get("name:ru") or rel.get("tags", {}).get("name") or "").strip()
            if not rname:
                continue
            q_n = (f'[out:json][timeout:240];\nrel({rel["id"]}); map_to_area->.a;\n'
                   f'node["place"~"{PLACES}"](area.a);\nout ids qt;')
            data = overpass(f"raion_nodes_{rel['id']}", q_n, timeout=260, attempts=1)
            if not data:
                continue
            for el in data["elements"]:
                rec = records.get(f"{el.get('type', 'node')[0]}{el.get('id')}")
                if rec is not None and not rec.get("r"):
                    rec["r"] = rname.split()[0]
                    raion_hits += 1
    if os.environ.get("GAZETTEER_SKIP_RAIONS"):
        # что уже лежит в кэше от прошлых прогонов — применяем без сети
        import glob
        for path in glob.glob(os.path.join(CACHE, "raions_*.json")):
            with open(path, encoding="utf-8") as f:
                for rel in json.load(f).get("elements", []):
                    rname = (rel.get("tags", {}).get("name:ru") or rel.get("tags", {}).get("name") or "").strip()
                    data = _cached(f"raion_nodes_{rel['id']}")
                    if not rname or not data:
                        continue
                    for el in data["elements"]:
                        rec = records.get(f"{el.get('type', 'node')[0]}{el.get('id')}")
                        if rec is not None and not rec.get("r"):
                            rec["r"] = rname.split()[0]
                            raion_hits += 1
    print(f"район проставлен у {raion_hits} записей")

    payload = {
        "source": "OpenStreetMap via Overpass (ODbL) — place=city|town|village|hamlet; область — по контурам "
                  "regions_geojson карты СВО (те же OSM-границы); район — OSM admin_level=6, только прифронтовые области",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields": {"id": "osm node id", "n": "name:ru", "u": "name:uk/name", "a": "old/alt names",
                   "o": "область (первое слово, рус.)", "r": "район (первое слово, рус.) или нет", "t": "place"},
        "count": len(records),
        "items": sorted(records.values(), key=lambda r: (r["o"] or "", r["n"] or r["u"] or "")),
    }
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print(f"записано {OUT}: {len(records)} записей, {os.path.getsize(OUT) // 1024} КБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
