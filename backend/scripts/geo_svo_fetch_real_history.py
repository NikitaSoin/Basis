#!/usr/bin/env python3
"""Реальная помесячная история линии фронта СВО из архивных таймлапс-сервисов
ISW (Institute for the Study of War, ArcGIS, CC BY) — взамен реконструкции
диаграммой Вороного по датированным населённым пунктам (владелец забраковал:
«красные кривые пятна, как будто котлы»; 2026-07: «найди реальные карты и ход
боевых действий и по ним восстанови»).

Откуда история. Живой слой (VIEW_RussiaCoTinUkraine_V3/49) времени не хранит
(timeInfo=null — проверено), но у той же организации ISW на services5.arcgis.com
лежат ~325 сервисов, среди них таймлапсы контроля территории с полем datetime:

  * UkrainianCoTTimelapse_FEB_2022_to_DEC_2024_view/0 — ЕЖЕДНЕВНЫЕ снапшоты
    полигона «Assessed Russian Control» с 2022-02-24 по 2024-12-31 (1041 дата,
    проверено returnDistinctValues). Дневной полигон УЖЕ включает Крым и
    пред-2022 Донбасс (проверено точками Симферополь/Донецк на 2022-03-01).
  * Помесячные сервисы 2025-2026 (JAN2025Timelapse_…, March_PreppedTimelapse,
    Ukraine_COT_Timelapse_April_2025, …_2025_Timelapse, SEP2025RUCoT,
    Russo_Ukraine_War_*_2025_Timelapse, Ukraine_Time_Lapse_December_2025_WFL1,
    COT_Merge_Jan_2026_view, Ukraine_Timelapse_Feb_2026_WFL1_view,
    Ukraine_Timelapse_April_2026_WFL1, May_CoT_view) — карта источников ниже.
  * Текущий месяц — живой слой 49 (снапшот = max EditDate).

На каждый месяц берётся снапшот ближайшей доступной даты ≤ конца месяца.
Для месяцев, по которым у ISW таймлапса нет вовсе (дыры между сервисами),
честно переиспользуется последний доступный снапшот предыдущего месяца с
пометкой в note — данные НЕ выдумываются.

Каждый полигон месяца дополнительно объединяется со слоем
VIEW_Russian_controlled_Ukrainian_Territory_before_February_24_2022/36
(Крым + Донбасс) — страховка от источников, где пред-2022 зоны нет.

Обработка месяца (по постановке владельца):
  union кусков → buffer(0) → union с пред-2022 → обрезка по контуру Украины
  (_ukraine_boundary_from_static_map — уже заделывает «дыры-воду»: Днепр это
  территория) → заделка ВСЕХ внутренних дыр (Polygon(exterior); «котлы»
  неприемлемы) → отброс микро-островков < 0.0008 град² → площадь СФЕРИЧЕСКИ
  (Chamberlain–Duquette, формула сферического избытка, R=6371.0088 км) →
  упрощение 0.006° ПОСЛЕ подсчёта площади.

Результат: backend/config/geo_svo_real_history.json (схема — см. build_output).
Скрипт повторяемый: всё сырьё кэшируется в backend/scripts/.real_history_cache/
(повторный прогон не ходит в сеть, если кэш на месте).

Запуск:  cd backend && ./venv/bin/python3 scripts/geo_svo_fetch_real_history.py
Опции:   --validate-only  (не перекачивать, пересчитать валидацию по готовому
         json), --skip-live-compare (без сверки с живым фидом).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

BASE = "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".real_history_cache")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config",
                        "geo_svo_real_history.json")

HTTP_TIMEOUT = 120.0
RETRIES = 4
PAUSE = 1.0  # пауза между запросами — не долбить ArcGIS

# Карта источников: месяц → (сервис, слой, поле времени).
# 2022-02..2024-12 закрывает один ежедневный мердж-слой (добавляется кодом).
DAILY_MERGE = ("UkrainianCoTTimelapse_FEB_2022_to_DEC_2024_view", 0, "datetime")
MONTH_SOURCES: dict[str, tuple[str, int, str]] = {
    "2025-01": ("JAN2025Timelapse_Ukraine_Russia_War", 1, "datetime"),
    # 2025-02 — таймлапса у ISW нет (February_* сервисы = 2023 год) → фолбэк
    "2025-03": ("March_PreppedTimelapse", 31, "datetime"),
    "2025-04": ("Ukraine_COT_Timelapse_April_2025", 110, "datetime"),
    "2025-05": ("May_2025_Timelapse", 3, "datetime"),      # 'May Russo-Ukrainian CoT Timelapse'
    "2025-06": ("June_2025_Timelapse", 3, "datetime"),     # 'UkraineControlMapAO30J_Merge3'
    "2025-07": ("July_2025_Timelapse", 3, "datetime"),     # 'Ukraine Control Map - JULY 2025'
    "2025-08": ("August_2025_Timelapse", 2, "datetime"),   # 'AssessedRussianControl_AUG'
    "2025-09": ("SEP2025RUCoT", 5, "datetime"),
    "2025-10": ("Russo_Ukraine_War_October_2025_Timelapse", 3, "datetime"),
    "2025-11": ("Russo_Ukraine_War_November_2025_Timelapse", 33, "datetime"),
    "2025-12": ("Ukraine_Time_Lapse_December_2025_WFL1", 9, "datetime"),
    "2026-01": ("COT_Merge_Jan_2026_view", 37, "datetime"),
    "2026-02": ("Ukraine_Timelapse_Feb_2026_WFL1_view", 28, "datetime"),
    "2026-03": ("Export_March_2026_V4", 33, "datetime"),
    "2026-04": ("Ukraine_Timelapse_April_2026_WFL1", 33, "datetime"),
    "2026-05": ("May_CoT_view", 0, "pub_date"),
    # 2026-06 — отдельного таймлапса не нашлось → фолбэк на 2026-05
    # 2026-07 (текущий) — живой слой, отдельная ветка кода
}
LIVE_LAYER = ("VIEW_RussiaCoTinUkraine_V3", 49)
PRE2022_LAYER = ("VIEW_Russian_controlled_Ukrainian_Territory_before_February_24_2022", 36)

MIN_ISLAND_DEG2 = 0.0008
SIMPLIFY_DEG = 0.006
EARTH_R_KM = 6371.0088
# Морфологическое замыкание контура Украины перед клипом (~1.1 км): рукописная
# береговая линия статической карты кладёт прибрежные города «в воду» — центр
# Херсона в ~90 м ЗА контуром (замерено), и клип выбрасывал город из всех
# месяцев весны-осени 2022. closing заделывает узкие рукава/лиманы шириной до
# ~2 км (Днепровский лиман у Херсона) — река/лиман это территория, та же
# логика, что заделка внутренних «дыр-воды» в _ukraine_boundary_from_static_map.
# Подобрано перебором: 0.005 не накрывает точку Херсона, 0.01 накрывает,
# прирост контура всей страны +0.042 град² (~340 км², из них на контролируемую
# зону приходится малая часть).
UKRAINE_CLOSING_DEG = 0.01


# ---------------------------------------------------------------- сеть и кэш

def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, name)


def _get_json(url: str, params: dict, cache_name: str) -> dict:
    """GET с кэшем на диске. Кэш-файл валиден, если парсится и без 'error'."""
    path = _cache_path(cache_name)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if "error" not in d:
                return d
        except Exception:
            pass
    last_err: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = httpx.get(url, params=params, timeout=HTTP_TIMEOUT, follow_redirects=True)
            r.raise_for_status()
            d = r.json()
            if "error" in d:
                raise ValueError(f"ArcGIS error: {d['error']}")
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f)
            time.sleep(PAUSE)
            return d
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"не скачалось {url}: {last_err}")


# (svc, layer) → True, если поле времени esriFieldTypeDateOnly: значения приходят
# СТРОКАМИ 'YYYY-MM-DD', а в where нужны DATE-, а не TIMESTAMP-литералы
# (так у May_CoT_view/0 pub_date — из-за этого 2026-05 сперва молча падал в фолбэк).
_DATEONLY: dict[tuple[str, int], bool] = {}


def _distinct_dates(svc: str, layer: int, field: str) -> list[str]:
    """Все даты (UTC, YYYY-MM-DD), на которые в слое есть снапшоты."""
    d = _get_json(
        f"{BASE}/{svc}/FeatureServer/{layer}/query",
        {"where": "1=1", "outFields": field, "returnDistinctValues": "true",
         "returnGeometry": "false", "f": "json"},
        f"dates_{svc}_{layer}.json",
    )
    for fd in d.get("fields", []):
        if fd.get("name") == field:
            _DATEONLY[(svc, layer)] = fd.get("type") == "esriFieldTypeDateOnly"
    out = set()
    for feat in d.get("features", []):
        v = feat.get("attributes", {}).get(field)
        if isinstance(v, (int, float)):
            out.add(datetime.fromtimestamp(v / 1000, tz=timezone.utc).date().isoformat())
        elif isinstance(v, str) and len(v) >= 10:
            out.add(v[:10])
    return sorted(out)


def _fetch_features_on_date(svc: str, layer: int, field: str, day: str) -> list[dict]:
    """Все фичи слоя за конкретную дату (диапазон [day, day+1) — поле времени
    не всегда ровно в полночь). Пагинация через resultOffset на случай
    exceededTransferLimit (maxRecordCount 1000-2000)."""
    nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    if _DATEONLY.get((svc, layer)):
        where = f"{field} >= DATE '{day}' AND {field} < DATE '{nxt}'"
    else:
        where = (f"{field} >= TIMESTAMP '{day} 00:00:00' AND "
                 f"{field} < TIMESTAMP '{nxt} 00:00:00'")
    feats: list[dict] = []
    offset = 0
    while True:
        d = _get_json(
            f"{BASE}/{svc}/FeatureServer/{layer}/query",
            {"where": where, "outFields": field, "returnGeometry": "true",
             "outSR": "4326", "resultOffset": str(offset), "f": "geojson"},
            f"raw_{svc}_{layer}_{day}_o{offset}.json",
        )
        feats.extend(d.get("features", []))
        if d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit"):
            offset = len(feats)
            continue
        return feats


def _fetch_whole_layer(svc: str, layer: int, cache_name: str) -> list[dict]:
    feats: list[dict] = []
    offset = 0
    while True:
        d = _get_json(
            f"{BASE}/{svc}/FeatureServer/{layer}/query",
            {"where": "1=1", "outFields": "*", "returnGeometry": "true",
             "outSR": "4326", "resultOffset": str(offset), "f": "geojson"},
            f"{cache_name}_o{offset}.json",
        )
        feats.extend(d.get("features", []))
        if d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit"):
            offset = len(feats)
            continue
        return feats


# ---------------------------------------------------------------- геометрия

def _spherical_area_km2(geom) -> float:
    """Площадь по сфере (формула сферического избытка Chamberlain–Duquette,
    как в turf.js), R=6371.0088 км. Считаем ТОЛЬКО внешние кольца — дыры к
    этому моменту уже заделаны по постановке."""
    def ring_area(coords) -> float:
        n = len(coords)
        if n < 3:
            return 0.0
        s = 0.0
        for i in range(n - 1):
            lam1, phi1 = coords[i][0], coords[i][1]
            lam2, phi2 = coords[i + 1][0], coords[i + 1][1]
            s += math.radians(lam2 - lam1) * (
                2 + math.sin(math.radians(phi1)) + math.sin(math.radians(phi2)))
        return abs(s) * EARTH_R_KM * EARTH_R_KM / 2.0

    parts = geom.geoms if hasattr(geom, "geoms") else [geom]
    return sum(ring_area(list(p.exterior.coords)) for p in parts
               if p.geom_type == "Polygon" and not p.is_empty)


def _fill_holes_drop_islands(geom):
    """Внешние кольца всех частей (все внутренние дыры заделаны) + отброс
    микро-островков < MIN_ISLAND_DEG2. union заделанных частей может в теории
    снова дать дыру (кольцо из полигонов) — повторяем до чистоты (макс 3)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    for _ in range(3):
        parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
        polys = [Polygon(p.exterior) for p in parts
                 if p.geom_type == "Polygon" and not p.is_empty]
        polys = [p for p in polys if p.area >= MIN_ISLAND_DEG2]
        if not polys:
            return geom
        geom = unary_union(polys).buffer(0)
        if _count_holes(geom) == 0:
            return geom
    return geom


def _count_holes(geom) -> int:
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return sum(len(p.interiors) for p in parts if p.geom_type == "Polygon")


def _round_geojson(g: dict, nd: int = 4) -> dict:
    def rec(x):
        if isinstance(x, list):
            return [rec(v) for v in x]
        if isinstance(x, float):
            return round(x, nd)
        return x
    return {"type": g["type"], "coordinates": rec(g["coordinates"])}


def _process_month(raw_geoms, pre2022, ukraine):
    """union → +пред-2022 → клип по Украине → заделка дыр/островков →
    (площадь, полная геометрия, упрощённая геометрия)."""
    from shapely.geometry import mapping
    from shapely.geometry.polygon import orient
    from shapely.ops import unary_union

    u = unary_union(raw_geoms).buffer(0)
    u = unary_union([u, pre2022]).buffer(0)
    u = u.intersection(ukraine).buffer(0)
    u = _fill_holes_drop_islands(u)
    area_km2 = _spherical_area_km2(u)

    simplified = u.simplify(SIMPLIFY_DEG, preserve_topology=True).buffer(0)
    simplified = _fill_holes_drop_islands(simplified)  # simplify мог занести мелочь
    parts = list(simplified.geoms) if hasattr(simplified, "geoms") else [simplified]
    parts = [orient(p, sign=1.0) for p in parts if p.geom_type == "Polygon" and not p.is_empty]
    geom = unary_union(parts)
    return area_km2, u, _round_geojson(mapping(geom))


# ---------------------------------------------------------------- сбор месяцев

def month_ends(first: str, last: str) -> list[tuple[str, str]]:
    """[(YYYY-MM, YYYY-MM-DD конец месяца)] от first до last включительно."""
    out = []
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    while (y, m) <= (ly, lm):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end = (date(ny, nm, 1) - timedelta(days=1)).isoformat()
        out.append((f"{y:04d}-{m:02d}", end))
        y, m = ny, nm
    return out


def build_source_map(last_month: str) -> dict[str, tuple[str, int, str]]:
    src: dict[str, tuple[str, int, str]] = {}
    for month, _end in month_ends("2022-02", "2024-12"):
        src[month] = DAILY_MERGE
    src.update(MONTH_SOURCES)
    return {m: s for m, s in src.items() if m <= last_month}


def collect_months(pre2022, ukraine, today: date):
    from shapely.geometry import shape

    cur_month = f"{today.year:04d}-{today.month:02d}"
    months_out = []
    prev_entry = None  # для фолбэка на дырах покрытия

    for month, end in month_ends("2022-02", cur_month):
        is_current = (month == cur_month)
        note = None

        if is_current:
            feats = _fetch_whole_layer(*LIVE_LAYER, cache_name="live_current")
            snap = None
            eds = [f["properties"].get("EditDate") for f in feats
                   if isinstance(f["properties"].get("EditDate"), (int, float))]
            if eds:
                snap = datetime.fromtimestamp(max(eds) / 1000, tz=timezone.utc).date().isoformat()
            note = "текущий месяц: живой слой ISW (не архив), месяц ещё не закончен"
        elif month in build_source_map(cur_month):
            svc, layer, field = build_source_map(cur_month)[month]
            dates = _distinct_dates(svc, layer, field)
            usable = [d for d in dates if d <= end]
            if not usable:
                # источник есть, но все его даты позже конца месяца — дыра
                svc = None
            else:
                snap = usable[-1]
                if snap < f"{month}-01":
                    note = f"в слое {svc} нет дат внутри {month}, взят ближайший снапшот ≤ конца месяца"
                feats = _fetch_features_on_date(svc, layer, field, snap)
        else:
            svc = None

        if not is_current and (month not in build_source_map(cur_month) or svc is None):
            if prev_entry is None:
                print(f"  {month}: данных нет и фолбэка нет — пропуск")
                continue
            months_out.append({
                "month": month, "month_end": end,
                "snapshot_date": prev_entry["snapshot_date"],
                "area_km2": prev_entry["area_km2"],
                "note": ("у ISW нет архивного таймлапса за этот месяц — повтор "
                         "последнего доступного снапшота предыдущего месяца"),
                "geometry": prev_entry["geometry"],
                "_full": prev_entry["_full"],
            })
            print(f"  {month}: НЕТ ИСТОЧНИКА → повтор снапшота {prev_entry['snapshot_date']}")
            prev_entry = months_out[-1]
            continue

        geoms = [shape(f["geometry"]).buffer(0) for f in feats if f.get("geometry")]
        if not geoms:
            raise RuntimeError(f"{month}: источник вернул 0 полигонов")
        area, full, gj = _process_month(geoms, pre2022, ukraine)
        entry = {"month": month, "month_end": end, "snapshot_date": snap,
                 "area_km2": round(area), "geometry": gj, "_full": full}
        if note:
            entry["note"] = note
        months_out.append(entry)
        prev_entry = entry
        print(f"  {month}: снапшот {snap}, {len(geoms)} фич, {round(area):,} км², "
              f"дыр {_count_holes(full)}")
    return months_out


# ---------------------------------------------------------------- валидация

CHECKPOINTS = [
    # (имя, lon, lat, месяцы-вне, месяцы-внутри) — описание в отчёте
    ("Бахмут", 37.9999, 48.5956,
     lambda m: m <= "2023-04", lambda m: m >= "2023-05"),
    ("Авдеевка", 37.7433, 48.1391,
     lambda m: m <= "2024-01", lambda m: m >= "2024-02"),
    ("Изюм", 37.2569, 49.2128,
     lambda m: m >= "2022-09", lambda m: "2022-04" <= m <= "2022-08"),
    ("Херсон", 32.625, 46.642,
     lambda m: m >= "2022-11", lambda m: "2022-03" <= m <= "2022-10"),
    ("Мариуполь", 37.549, 47.096,
     lambda m: False, lambda m: m >= "2022-05"),
    ("Симферополь (Крым)", 34.10, 44.95, lambda m: False, lambda m: True),
    ("Донецк", 37.803, 48.015, lambda m: False, lambda m: True),
]


def validate(months: list[dict]) -> list[str]:
    from shapely.geometry import Point, shape

    lines = []
    geoms = {e["month"]: (e.get("_full") or shape(e["geometry"])) for e in months}

    lines.append("Точечные проверки (месяц: ожидание → факт; только расхождения):")
    all_ok = True
    for name, lon, lat, expect_out, expect_in in CHECKPOINTS:
        pt = Point(lon, lat)
        bad = []
        for m, g in geoms.items():
            inside = g.contains(pt)
            if expect_in(m) and not inside:
                bad.append(f"{m}: должен быть ВНУТРИ, а он вне")
            elif expect_out(m) and inside:
                bad.append(f"{m}: должен быть ВНЕ, а он внутри")
        status = "OK" if not bad else "FAIL " + "; ".join(bad[:6])
        if bad:
            all_ok = False
        lines.append(f"  {name}: {status}")
    if all_ok:
        lines.append("  все точечные проверки пройдены")

    holes = {m: _count_holes(g) for m, g in geoms.items() if _count_holes(g)}
    lines.append(f"Внутренние дыры: {holes if holes else '0 во всех месяцах'}")

    lines.append("Отрицательные дельты площади (месяц: изменение км²):")
    prev = None
    for e in months:
        if prev is not None and e["area_km2"] < prev["area_km2"]:
            lines.append(f"  {e['month']}: {e['area_km2'] - prev['area_km2']:+,}")
        prev = e
    return lines


def compare_with_live(months: list[dict]) -> str:
    """Площадь последнего архивного месяца против живого прод-пайплайна
    (_fetch_control_polygons + absorb_candidates + _absorb_overrides +
    _smooth_polygon), обработанного той же пост-обработкой."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    from app.services.geo_isw_frontline_sync import (
        _absorb_overrides, _fetch_control_polygons, _smooth_polygon,
        _ukraine_boundary_from_static_map, absorb_candidates)

    control_fc, as_of = _fetch_control_polygons()
    ukraine, _ = _ukraine_boundary_from_static_map()
    ukraine = (ukraine.buffer(UKRAINE_CLOSING_DEG, join_style=1)
                      .buffer(-UKRAINE_CLOSING_DEG, join_style=1).buffer(0))
    overrides = absorb_candidates(ukraine)
    ru = unary_union([shape(f["geometry"]).buffer(0)
                      for f in control_fc.get("features", []) if f.get("geometry")]).buffer(0)
    ru = _smooth_polygon(_absorb_overrides(ru, overrides))
    ru = _fill_holes_drop_islands(ru.intersection(ukraine).buffer(0))
    live_area = _spherical_area_km2(ru)

    last = months[-1]
    diff = abs(last["area_km2"] - live_area) / live_area * 100
    return (f"Живой контроль (прод-пайплайн с оверрайдами, as_of={as_of}): "
            f"{round(live_area):,} км²; последний месяц истории {last['month']}: "
            f"{last['area_km2']:,} км²; расхождение {diff:.1f}% "
            f"({'OK ≤10%' if diff <= 10 else 'ПРЕВЫШЕНО'})")


# ---------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate-only", action="store_true",
                    help="не качать: перечитать готовый json и прогнать валидацию")
    ap.add_argument("--skip-live-compare", action="store_true")
    args = ap.parse_args()

    from app.services.geo_isw_frontline_sync import _ukraine_boundary_from_static_map
    from shapely.geometry import shape
    from shapely.ops import unary_union

    if args.validate_only:
        with open(OUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        months = data["months"]
    else:
        today = datetime.now(timezone.utc).date()
        ukraine, _ = _ukraine_boundary_from_static_map()
        ukraine = (ukraine.buffer(UKRAINE_CLOSING_DEG, join_style=1)
                          .buffer(-UKRAINE_CLOSING_DEG, join_style=1).buffer(0))
        pre_feats = _fetch_whole_layer(*PRE2022_LAYER, cache_name="pre2022_control")
        pre2022 = unary_union([shape(f["geometry"]).buffer(0)
                               for f in pre_feats if f.get("geometry")]).buffer(0)
        print(f"Пред-2022 слой: {len(pre_feats)} фич. Собираю месяцы…")
        months = collect_months(pre2022, ukraine, today)

        real = [e for e in months if "нет архивного таймлапса" not in (e.get("note") or "")
                and "живой слой" not in (e.get("note") or "")]
        data = {
            "note": ("Реальная помесячная история территории под контролем РФ внутри "
                     "Украины (конец месяца) из архивных таймлапс-слоёв ISW; каждый "
                     "месяц = union(assessed control, пред-2022 Крым+Донбасс), обрезан "
                     "по контуру Украины, внутренние дыры заделаны, микро-островки "
                     "<0.0008 град² отброшены, площадь сферическая, геометрия "
                     "упрощена 0.006° после подсчёта площади. Месяцы с note про "
                     "отсутствие таймлапса — повтор предыдущего снапшота."),
            "source": ("ISW Assessed Control of Terrain in Ukraine — архивные "
                       "таймлапс-сервисы services5.arcgis.com/SaBe5HMtmnbqSWlu (CC BY); "
                       "текущий месяц — живой слой VIEW_RussiaCoTinUkraine_V3/49"),
            "generated_at": today.isoformat(),
            "coverage_end": real[-1]["month"] if real else None,
            "months": [{k: v for k, v in e.items() if k != "_full"} for e in months],
        }
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print(f"\nЗаписан {os.path.normpath(OUT_PATH)} "
              f"({os.path.getsize(OUT_PATH) / 1e6:.1f} МБ), "
              f"coverage_end={data['coverage_end']}")

    print("\n=== ВАЛИДАЦИЯ ===")
    for line in validate(months):
        print(line)

    print("\nРяд площадей (конец года + последние месяцы):")
    for e in months:
        if e["month"].endswith("-12") or e["month"] >= months[-1]["month"][:5]:
            print(f"  {e['month']}: {e['area_km2']:,} км²")

    if not args.skip_live_compare:
        print("\n" + compare_with_live(months))


if __name__ == "__main__":
    main()
