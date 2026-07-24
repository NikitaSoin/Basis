"""Изохрона «когда какой участок был взят» для карты СВО — задел под временной
ползунок (владелец, 2026-07-24: «идёшь по сообщениям, знаешь какие города
когда взяты — отматываешь линию фронта за эти города»).

Источник дат — история правок статьи Wikipedia "Territorial control during
the Russo-Ukrainian war" (+ подстатья по Донецкой обл.), которая сама
агрегирует ISW/DeepState/новости построчно с цитатами — см.
scripts/geo_svo_wikipedia_dates.py (разовый/периодический скрипт сбора, НЕ
гоняется на каждый синк — это медленно меняющиеся исторические данные).
Результат — config/geo_svo_dated_settlements.json (265 точек на 2026-07-24).

Метод построения геометрии — ГИБРИД Вороного + помесячная сборка (первая
версия — чистый Вороной без объединения соседних ячеек — давала несвязные
"котлы"/"полукотлы", владелец забраковал как недостоверную; версия на
фиксированных буферах вокруг точек — недооценивала area там, где точки
редкие относительно площади, напр. интерьер Крыма почти без покрытия
между немногими датированными городами; см. work-journal 2026-07-24 про
оба пивота):
  1. Диаграмма Вороного (shapely) вокруг ВСЕХ датированных точек, обрезанная
     по ТЕКУЩЕМУ control_fill_geojson — гарантирует ПОЛНОЕ покрытие площади
     (у каждой точки территории control_fill есть "ближайший датированный
     сосед"), в отличие от буферов фиксированного радиуса.
  2. Для каждого месяца M — берём ячейки, чей сосед датирован <= конец M,
     СЛИВАЕМ их в одно тело (unary_union — внутренние швы между соседними
     ячейками одного статуса исчезают), затем closing→opening сглаживание
     убирает рваные Вороного-грани и мелкие дыры-артефакты (единичная
     "не по времени" ячейка внутри уже взятого массива), микро-островки-
     шум отсеиваются по площади.
  3. Дискретные помесячные снапшоты (не continuous filter по точке) —
     фронтенд снэпит слайдер к ближайшему <= выбранной дате месяцу, без
     похода на сервер (все месяцы в одном ответе).

Пересчитывается заново на каждом ISW-синке (дёшево — Вороной строится один
раз, дальше на каждый месяц только union+buffer, без сети), т.к. форма
control_fill меняется, а список дат — почти нет.

Огрубление, а не точная историческая линия — эпистемически это "оценка".
Особенно грубо там, где датированные точки редки (между кластерами Крым/
Донбасс/Запорожье) — это ожидаемо и не скрывается (дисклеймер на фронте)."""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_DATED_SETTLEMENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_dated_settlements.json",
)
_SVO_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_map_svo.json",
)

# Сглаживание помесячного среза (град.) — крупнее, чем у самой ISW-линии
# (geo_isw_frontline_sync._smooth_polygon, ~0.0035°): здесь изначально
# грубая/оценочная реконструкция по Вороного-ячейкам, нужно заметно сильнее
# сгладить рваные грани и залатать единичные "не по времени" дыры-ячейки.
_SMOOTH_DEG = 0.03
# Порог отсева микро-островков после сглаживания (град.²).
_MIN_ISLAND_AREA_DEG2 = 0.0008
_MONTH_START = (2022, 2)


def _month_end(year: int, month: int) -> str:
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def _iter_months(start_year: int, start_month: int, end_iso: str):
    y, m = start_year, start_month
    while True:
        me = _month_end(y, m)
        yield y, m, me
        if me >= end_iso:
            break
        m += 1
        if m > 12:
            m = 1
            y += 1


def _smooth_and_clean(poly):
    """closing→opening (сглаживание рваных Вороного-граней + латание мелких
    дыр-артефактов) + отсев микро-островков-шума."""
    from shapely.geometry import MultiPolygon
    from shapely.ops import unary_union

    if poly.is_empty:
        return poly
    closed = poly.buffer(_SMOOTH_DEG, join_style=1).buffer(-_SMOOTH_DEG, join_style=1)
    opened = closed.buffer(-_SMOOTH_DEG, join_style=1).buffer(_SMOOTH_DEG, join_style=1)
    opened = opened.buffer(0)
    if opened.is_empty:
        return opened
    parts = list(opened.geoms) if isinstance(opened, MultiPolygon) else [opened]
    kept = [p for p in parts if p.area >= _MIN_ISLAND_AREA_DEG2]
    if not kept:
        kept = parts  # если ВСЁ мельче порога — честнее показать как есть, чем стереть целиком
    return unary_union(kept)


def _crimea_landmass(control_union):
    """Крым фактически под контролем РФ с аннексии 2014 — ДО начала войны
    2022, которую описывает вся эта временная реконструкция (датированные
    точки — из статьи Wikipedia про войну 2022+, там лишь горстка крымских
    городов с датой "2014-02-27" для контекста, без плотного покрытия).
    Без спецкейса редкая датированная точка у Керченского перешейка с
    ПОЗДНЕЙ (2024+) датой образует Вороного-клин, который на карте
    искусственно ОТРЕЗАЕТ Крым от остального массива на годы, пока её
    собственная дата не наступит — придуманный "котёл", которого не было
    (владелец, 2026-07-25, живая проверка: «странные котлы, которых не
    было» — проверено: именно так и было видно на скриншоте от 2024 года,
    который владелец прикладывал как пример бага в прошлый раз). Честная
    деградация — не нашли регион в статике/geometry невалидна → None,
    просто не подмешиваем спецкейс, остальная реконструкция не падает."""
    try:
        with open(_SVO_MAP_PATH, encoding="utf-8") as f:
            static_map = json.load(f)
        from shapely.geometry import shape as _shape
        from shapely.ops import unary_union as _unary_union
        polys = [_shape(feat["geometry"]).buffer(0)
                 for feat in static_map["base_map"]["regions_geojson"]["features"]
                 if feat["properties"].get("slug") in ("crimea", "sevastopol")]
        if not polys:
            return None
        crimea = _unary_union(polys).buffer(0)
        return crimea.intersection(control_union)
    except Exception as e:  # noqa: BLE001
        logger.warning("Изохрона СВО: спецкейс Крыма не применён (%s)", type(e).__name__)
        return None


def compute_isochrone(control_fill_geojson: dict) -> dict | None:
    """control_fill_geojson — тот же формат, что GeoFrontlineSync.control_fill_geojson.
    Возвращает FeatureCollection полигонов, ОДИН на месяц, с properties
    {month: "YYYY-MM", month_end: "YYYY-MM-DD", settlements_count: N} — N
    накопленных датированных точек к концу месяца (для подписи "N пунктов
    взято к этой дате"). None при отсутствии исходных данных — честная
    деградация, не 500."""
    if not os.path.exists(_DATED_SETTLEMENTS_PATH):
        return None
    with open(_DATED_SETTLEMENTS_PATH, encoding="utf-8") as f:
        dated = json.load(f)
    if not dated:
        return None

    from shapely.geometry import shape, mapping, MultiPoint, Point
    from shapely.ops import voronoi_diagram, unary_union

    control_polys = [shape(f["geometry"]) for f in control_fill_geojson.get("features", [])]
    if not control_polys:
        return None
    control_union = unary_union(control_polys).buffer(0)

    pts = [Point(d["lon"], d["lat"]) for d in dated]
    mp = MultiPoint(pts)
    try:
        vd = voronoi_diagram(mp, envelope=control_union.buffer(2.0))
    except Exception as e:  # noqa: BLE001
        logger.warning("Изохрона СВО: voronoi_diagram упал: %s", e)
        return None

    # Каждой ячейке — её датированный сосед (владелец cell), обрезка по control_fill
    # СРАЗУ (не при каждом месяце — дорогая операция intersection делается один раз).
    cell_owner_date: list[tuple] = []  # (clipped_geom, capture_date)
    for cell in vd.geoms:
        owner = None
        for i, p in enumerate(pts):
            if cell.contains(p) or cell.distance(p) < 1e-9:
                owner = i
                break
        if owner is None:
            continue
        clipped = cell.intersection(control_union)
        if clipped.is_empty:
            continue
        cell_owner_date.append((clipped, dated[owner]["capture_date"]))

    if not cell_owner_date:
        return None

    cell_owner_date.sort(key=lambda t: t[1])
    dated_sorted_dates = [t[1] for t in cell_owner_date]
    today_iso = date.today().isoformat()
    crimea_mass = _crimea_landmass(control_union)

    features = []
    idx = 0  # сколько ячеек (по возрастанию даты) уже включено
    for y, m, month_end_iso in _iter_months(_MONTH_START[0], _MONTH_START[1], today_iso):
        while idx < len(cell_owner_date) and dated_sorted_dates[idx] <= month_end_iso:
            idx += 1
        parts = [g for g, _ in cell_owner_date[:idx]]
        if crimea_mass is not None and not crimea_mass.is_empty:
            parts.append(crimea_mass)
        if not parts:
            continue
        region = unary_union(parts)
        region = _smooth_and_clean(region)
        # финальная обрезка по control_fill — сглаживание могло чуть "вылезти" за край
        region = region.intersection(control_union)
        if region.is_empty:
            continue
        features.append({
            "type": "Feature",
            "properties": {
                "month": f"{y:04d}-{m:02d}",
                "month_end": month_end_iso,
                "settlements_count": idx,
            },
            "geometry": mapping(region),
        })

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}
