"""Изохрона «когда какой участок был взят» для карты СВО — задел под временной
ползунок (владелец, 2026-07-24: «идёшь по сообщениям, знаешь какие города
когда взяты — отматываешь линию фронта за эти города»).

Метод (диаграмма Вороного, не попытка восстановить точную историческую
геометрию — см. отклонённый путь через архив Wayback в work-journal
2026-07-24, там дыра в архиве на 14 месяцев и системная неточность именно
на "недавно взятых" точках):
  1. Датированный список «нас. пункт → дата взятия РФ» — из истории правок
     статьи Wikipedia "Territorial control during the Russo-Ukrainian war"
     (+ подстатьи по Донецкой обл.), которая сама агрегирует ISW/DeepState/
     новости построчно с цитатами — см. scripts/geo_svo_wikipedia_dates.py
     (разовый/периодический скрипт сбора, НЕ гоняется на каждый синк — это
     медленно меняющиеся исторические данные, не сегодняшняя сводка).
     Результат зафиксирован в config/geo_svo_dated_settlements.json
     (265 точек на 2026-07-24, ISW landmarks вроде Авдеевки/Бахмута/
     Мариуполя/Соледара/Марьинки/Угледара проверены вручную на корректность
     дат при сборе).
  2. Диаграмма Вороного (shapely) вокруг датированных точек, обрезанная по
     ТЕКУЩЕМУ (живому, из ISW) control_fill_geojson — у каждой ячейки
     "дата взятия" её датированного соседа. Пересчитывается заново на
     каждом ISW-синке (дёшево — чистая геометрия, без сети), т.к. сама
     форма контролируемой зоны меняется, а список дат — почти нет.
  3. Фронтенд фильтрует эту ОДНУ выданную геометрию по capture_date <=
     значение ползунка (MapLibre filter-выражение) — без обращений к
     серверу при движении ползунка.

Огрубление, а не точная историческая линия — эпистемически это "оценка"
уровня отдельных ячеек, не факт (реальная линия на дату X не была
полигоном Вороного). Особенно грубо там, где датированные точки редки
(между кластерами Крым/Донбасс/Запорожье) — ячейки там огромные и
малоинформативны, это ожидаемо и не скрывается."""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_DATED_SETTLEMENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_dated_settlements.json",
)


def compute_isochrone(control_fill_geojson: dict) -> dict | None:
    """control_fill_geojson — тот же формат, что GeoFrontlineSync.control_fill_geojson
    (FeatureCollection полигонов ISW-подтверждённого контроля). Возвращает
    FeatureCollection полигонов с properties {settlement, oblast, capture_date,
    date_precision} — ячейка Вороного датированной точки, обрезанная по
    текущей зоне контроля. None, если исходных данных нет (честная деградация,
    не 500)."""
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

    features = []
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
        d = dated[owner]
        features.append({
            "type": "Feature",
            "properties": {
                "settlement": d["name"],
                "oblast": d["oblast"],
                "capture_date": d["capture_date"],
                "date_precision": d["date_precision"],
            },
            "geometry": mapping(clipped),
        })

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}
