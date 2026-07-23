"""Автосинк линии фронта СВО из живого фида ISW (Institute for the Study of
War) — «Assessed Control of Terrain in Ukraine», публичный ArcGIS-сервис,
карты ISW лицензированы CC BY (см. config/geo_sources.json).

Владелец явно исключил украинские трекеры (DeepState, lostarmour) — риск
лицензии/комплаенса для российской платформы (DeepState прямо запрещает
редистрибуцию третьим лицам без письменного согласия правообладателя,
lostarmour не даёт открытого API вовсе). Рыбарь тоже без открытого API
(map.rybar.ru — платный продукт без документированной выдачи). ISW — открытый
эндпоинт без авторизации, регулярно (каждые ~1-2 дня) обновляется, уже
единственный источник метрики км²/мес (см. territorial_change в
geo_map_svo.json) — тот же принцип применён здесь к геометрии линии.

Метод реконструкции линии (нет отдельного слоя "line of control" у ISW —
только полигоны):
  ru_control = union(полигоны "Assessed Russian Control")   — контролируемая РФ
               территория ВНУТРИ Украины (слой уже ограничен пред-2022 границей)
  ukraine    = union(всех НЕ "_ru" фич в geo_map_svo.json regions_geojson)
               — переиспользуем уже существующий контур Украины (27 областей),
               не тянем отдельно Natural Earth
  rest       = ukraine − ru_control
  frontline  = boundary(ru_control) ∩ boundary(rest)
               — общая граница двух зон = линия боевого соприкосновения;
               сегменты вдоль границы с РФ/Белоруссией/морем в пересечение
               не попадают (это боковая, не спорная, вн. граница Украины)

Пишет НЕ в config/geo_map_svo.json (тот файл деплоится из git и был бы
затёрт следующим push), а в таблицу geo_frontline_sync — эндпоинт
`/market/geo-map/svo` накладывает живую линию поверх статики.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 25.0

# Известный рабочий эндпоинт (проверен напрямую, 2026-07-23). Если ISW снова
# перестроит бэкенд (уже случалось — старый Ukraine_Front_Line_NEW/FeatureServer/12
# сейчас мёртв), _discover_control_layer_url() ищет актуальный через sharing
# REST API того же item — не полагаемся только на хардкод.
_CONTROL_LAYER_URL = (
    "https://services5.arcgis.com/SaBe5HMtmnbqSWlu/arcgis/rest/services/"
    "VIEW_RussiaCoTinUkraine_V3/FeatureServer/49/query"
)
_ITEM_DATA_URL = "https://www.arcgis.com/sharing/rest/content/items/9f04944a2fe84edab9da31750c2b15eb/data"
_ITEM_METADATA_URL = "https://www.arcgis.com/sharing/rest/content/items/9f04944a2fe84edab9da31750c2b15eb?f=json"

_SVO_MAP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_map_svo.json",
)


def _query_geojson(url: str, params: dict) -> dict:
    r = httpx.get(url, params={**params, "f": "geojson"}, timeout=_HTTP_TIMEOUT, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def _discover_control_layer_url() -> str | None:
    """Фолбэк, если хардкоженный _CONTROL_LAYER_URL перестал отвечать (ISW уже
    один раз молча переставлял бэкенд) — ищем слой "Assessed Russian Control"
    среди operationalLayers веб-карты по её ArcGIS item id."""
    try:
        r = httpx.get(_ITEM_DATA_URL, params={"f": "json"}, timeout=_HTTP_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("ISW: не удалось прочитать item-метаданные для автопоиска слоя: %s", type(e).__name__)
        return None
    for layer in data.get("operationalLayers", []):
        title = (layer.get("title") or "").lower()
        if "russian control" in title or "control of terrain" in title:
            url = layer.get("url")
            if url:
                return url.rstrip("/") + "/query"
    logger.warning("ISW: слой контроля не найден среди operationalLayers item'а — структура карты изменилась")
    return None


def _fetch_control_polygons() -> tuple[dict, str | None]:
    """Возвращает (geojson FeatureCollection, lastEditDate ISO или None)."""
    params = {"where": "1=1", "outFields": "*"}
    try:
        fc = _query_geojson(_CONTROL_LAYER_URL, params)
        if "error" in fc:
            raise ValueError(f"ArcGIS error: {fc['error']}")
    except Exception as e:  # noqa: BLE001
        logger.warning("ISW: основной URL слоя контроля не ответил (%s), пробую автопоиск", type(e).__name__)
        discovered = _discover_control_layer_url()
        if not discovered:
            raise
        fc = _query_geojson(discovered, params)

    as_of = None
    edit_dates = [
        f["properties"].get("EditDate")
        for f in fc.get("features", [])
        if isinstance(f.get("properties", {}).get("EditDate"), (int, float))
    ]
    if edit_dates:
        as_of = datetime.fromtimestamp(max(edit_dates) / 1000, tz=timezone.utc).date().isoformat()
    return fc, as_of


def _ukraine_boundary_from_static_map():
    """Контур Украины (27 областей) — переиспользуем уже курируемый
    regions_geojson СВО-карты вместо отдельной загрузки Natural Earth.
    Фичи с slug, оканчивающимся на "_ru" — это российские приграничные
    области (Брянская/Курская/Белгородская/Краснодарский край), добавленные
    туда для контекста соседних событий, не часть Украины — исключаем."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    with open(_SVO_MAP_PATH, encoding="utf-8") as f:
        static_map = json.load(f)
    polys = []
    for feat in static_map["base_map"]["regions_geojson"]["features"]:
        slug = feat["properties"].get("slug", "")
        if slug.endswith("_ru"):
            continue
        # buffer(0) на КАЖДОМ полигоне по отдельности — ручная геометрия
        # областей местами топологически невалидна (самопересечения при
        # прошлых правках), unary_union на невалидном наборе падает с
        # TopologyException ещё до самого объединения.
        polys.append(shape(feat["geometry"]).buffer(0))
    return unary_union(polys), static_map


def _control_fill_geojson(ru_control) -> dict:
    """Сам полигон РФ-контроля (не только его граница-линия) — для точной
    закраски карты, которая идёт ВНУТРИ «спорных» областей (владелец,
    2026-07-24: «Часов Яр/Константиновка/Гуляйполе/Волчанск/Мирноград/
    Покровск/Родинское/Лиман фактически уже под РФ, а на карте область
    целиком помечена «contested» — не видно, что конкретно взято»).
    Область/район как объекты выбора региона (клик → подпись) остаются
    прежними (regions_geojson, ручная классификация по областям) — этот
    полигон рисуется ПОВЕРХ них отдельным слоем, тем же цветом, что
    коренные регионы РФ, показывая фактические контуры внутри области."""
    from shapely.geometry import mapping
    from shapely.geometry.polygon import orient

    simplified = ru_control.simplify(0.0015, preserve_topology=True)
    geoms = list(simplified.geoms) if hasattr(simplified, "geoms") else [simplified]
    # orient() — консистентная обмотка колец (GeoJSON RFC 7946: внешнее
    # кольцо против часовой) — simplify() иногда её нарушает, MapLibre не
    # всегда прощает "дырки", натянутые как основной контур.
    geoms = [orient(g, sign=1.0) for g in geoms if not g.is_empty and g.area > 0]
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in geoms],
    }


def _compute_frontline(control_fc: dict, ukraine_boundary) -> tuple[dict, dict]:
    """Возвращает (frontline_geojson, control_fill_geojson)."""
    from shapely.geometry import mapping, shape, LineString, MultiLineString
    from shapely.ops import unary_union, linemerge

    ru_polys = [shape(f["geometry"]).buffer(0) for f in control_fc.get("features", [])
                if f.get("geometry")]
    if not ru_polys:
        raise ValueError("ISW control layer вернул 0 полигонов — не с чем считать линию")
    ru_control = unary_union(ru_polys).buffer(0)
    ukraine_boundary = ukraine_boundary.buffer(0)

    control_fill = _control_fill_geojson(ru_control)

    rest_of_ukraine = ukraine_boundary.difference(ru_control)
    raw = ru_control.boundary.intersection(rest_of_ukraine.boundary)

    raw_lines: list[LineString] = []
    if isinstance(raw, LineString):
        raw_lines = [raw]
    elif isinstance(raw, MultiLineString):
        raw_lines = list(raw.geoms)
    elif hasattr(raw, "geoms"):  # GeometryCollection — точки/линии вперемешку
        for g in raw.geoms:
            if isinstance(g, LineString):
                raw_lines.append(g)
            elif isinstance(g, MultiLineString):
                raw_lines.extend(g.geoms)
    raw_lines = [ln for ln in raw_lines if ln.length > 0]
    if not raw_lines:
        raise ValueError("Пересечение границ дало 0 линий — геометрия ISW/Украины не пересекается")

    # Сырое пересечение границ полигонов детализации поселений даёт десятки
    # тысяч крошечных сегментов (проверено: 35044 сегмента на реальном фиде,
    # медиана ~30м) — артефакт точности вершин полигонов, не реальные отрезки
    # линии фронта. linemerge СНАЧАЛА (по общим концам) схлопывает их в ~300
    # непрерывных линий, ТОЛЬКО ПОТОМ фильтр по длине и упрощение — если
    # сначала упростить/отфильтровать сырые сегменты, их конечные точки
    # разъедутся и linemerge перестанет их склеивать.
    merged = linemerge(raw_lines)
    merged_lines = list(merged.geoms) if hasattr(merged, "geoms") else [merged]

    # Порог ~300м (0.003°) — проверено на реальных данных: отсекает ~19% ПО
    # КОЛИЧЕСТВУ линий (шум — обрывки в десятки метров), но <0.3% ОТ СУММЫ
    # ДЛИНЫ (реальная линия фронта почти не теряется).
    MIN_SEGMENT_DEG = 0.003
    kept = [ln for ln in merged_lines if ln.length >= MIN_SEGMENT_DEG]
    if not kept:
        raise ValueError("После фильтра шума не осталось ни одного сегмента линии фронта")

    # Упрощение — полигоны ISW детализированы на уровне поселений, для
    # отображения на карте страны такая плотность вершин избыточна (~0.0008°
    # ≈ 80-90 м на широте Украины — ниже разрешения тайла на масштабе карты).
    simplified = [ln.simplify(0.0008, preserve_topology=True) for ln in kept]

    frontline_fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(ln)} for ln in simplified],
    }
    return frontline_fc, control_fill


def sync_isw_frontline(db: Session) -> dict:
    """Один прогон: тянет ISW, пересчитывает линию, апсертит geo_frontline_sync.
    Честная деградация — при любой ошибке пишет status=error с причиной,
    НЕ трогает ранее сохранённую рабочую линию (эндпоинт продолжит отдавать
    последнюю успешную)."""
    from app.models.geo import GeoFrontlineSync

    row = db.query(GeoFrontlineSync).filter_by(theater="svo").first()
    if row is None:
        row = GeoFrontlineSync(theater="svo", status="ok")
        db.add(row)

    try:
        control_fc, as_of = _fetch_control_polygons()
        ukraine_boundary, _static_map = _ukraine_boundary_from_static_map()
        frontline_fc, control_fill_fc = _compute_frontline(control_fc, ukraine_boundary)
        if not frontline_fc["features"]:
            raise ValueError("Пересчитанная линия фронта пуста")

        row.frontline_geojson = frontline_fc
        row.control_fill_geojson = control_fill_fc
        row.as_of = as_of
        row.source = "ISW Assessed Control of Terrain in Ukraine (CC BY)"
        row.status = "ok"
        row.error_note = None
        db.commit()
        logger.info("ISW-синк линии фронта: %d сегментов линии, %d полигонов заливки, as_of=%s",
                     len(frontline_fc["features"]), len(control_fill_fc["features"]), as_of)
        return {"status": "ok", "segments": len(frontline_fc["features"]),
                "fill_polygons": len(control_fill_fc["features"]), "as_of": as_of}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        row = db.query(GeoFrontlineSync).filter_by(theater="svo").first()
        if row is None:
            row = GeoFrontlineSync(theater="svo")
            db.add(row)
        row.status = "error"
        row.error_note = f"{type(e).__name__}: {e}"
        db.commit()
        logger.exception("ISW-синк линии фронта не удался: %s", e)
        return {"status": "error", "error": str(e)}
