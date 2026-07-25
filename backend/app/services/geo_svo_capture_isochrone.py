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
# Хронология контроля с ОБРАТНЫМИ переходами (см. scripts/geo_svo_build_control_timeline.py
# и docs/svo-conflict-history.md). Перекрывает одиночные даты старого датасета.
_CONTROL_TIMELINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_control_timeline.json",
)

# Ограничитель «радиуса влияния» одной точки (град.). Нужен, чтобы ячейка
# Вороного редкой точки не расползалась на сотни км по территории, которую РФ
# в тот момент не держала (в первую очередь — в зонах, оставленных позже:
# именно там огибающая месяца шире сегодняшнего контроля, см. lost_since).
# 0.70° ≈ 78 км подобран калибровкой по покрытию ФАКТИЧЕСКОЙ площади контроля
# последним месяцем: 0.3°→76%, 0.5°→92%, 0.7°→96%, 1.0°→97% (дальше плато, а
# разлёт ячеек в оставленных зонах растёт) — берём 0.7° как точку насыщения.
_POINT_INFLUENCE_DEG = 0.70
# Упрощение выходной геометрии месяца (град.). ~0.006° ≈ 600 м — заведомо ниже
# уровня сглаживания самой реконструкции (_SMOOTH_DEG, ~3 км), поэтому вида не
# меняет, но режет вес ответа карты в разы.
_OUTPUT_SIMPLIFY_DEG = 0.006
_KM2_PER_DEG2 = 111.0 * 111.0 * 0.67  # грубо, для широты Украины

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


def _fill_holes_and_drop_islands(geom):
    """Убирает НЕФИЗИЧНЫЕ артефакты реконструкции: внутренние дыры («котлы») и
    мелкие оторванные островки.

    Владелец (2026-07-25, повторно, со скриншотом за 2024 год): «у ЛНР на
    юго-западе типо котел, в запорожской и днр тоже типа какие котлы — это
    бред». Замерено на реальных данных до фикса: дыра 3219 км² держалась с
    марта-2022 по октябрь-2024, вторая 935 км² — с декабря-2023 по ноябрь-2024,
    плюс мелочь 188-644 км².

    Природа дыры — чисто алгоритмическая: ячейка Вороного, чей «владелец»
    датирован ПОЗЖЕ окружения, остаётся невключённой и выглядит окружённым
    котлом, хотя никакого котла в реальности не было. Реальных долгоживущих
    окружений такого размера в этой войне не было ни у одной из сторон,
    поэтому дыры закрываем ВСЕ (реконструкция и так честно помечена как
    «оценка»/огрубление, точная линия ISW доступна в положении «сегодня»).

    Крупные ОТДЕЛЬНЫЕ массивы, наоборот, оставляем: до открытия сухопутного
    коридора (весна 2022) Крым физически не был связан с донбасской группой —
    это исторический факт, а не артефакт. Режем только мелочь-шум."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union

    if geom.is_empty:
        return geom
    parts = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    rebuilt = []
    for p in parts:
        if p.geom_type != "Polygon":
            continue
        if p.area < _MIN_ISLAND_AREA_DEG2:
            continue  # микро-островок — шум Вороного, не территория
        rebuilt.append(Polygon(p.exterior))  # внешнее кольцо без дыр
    if not rebuilt:
        return geom  # честнее показать как есть, чем стереть целиком
    return unary_union(rebuilt).buffer(0)


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


def _load_timeline_points() -> list[dict]:
    """Единый список точек с ХРОНОЛОГИЕЙ владения: [{lat, lon, transitions:
    [(date, "RF"|"UA")]}]. Склейка двух датасетов, хронология ПЕРЕКРЫВАЕТ
    одиночную дату по совпадению координат.

    Зачем перекрывать: geo_svo_dated_settlements.json (265 точек Wikipedia)
    содержит ТОЛЬКО переходы к РФ — ни одного отката. Пока источник был
    единственным, реконструкция была математически ОБЯЗАНА расти монотонно:
    ни харьковский откат сентября-2022, ни оставление правобережья Херсона
    показать было нечем, а «км²/месяц» не могла стать отрицательной ни разу.
    geo_svo_control_timeline.json (из docs/svo-conflict-history.md) даёт
    переходы в обе стороны — см. scripts/geo_svo_build_control_timeline.py."""
    points: dict[tuple, dict] = {}
    if os.path.exists(_DATED_SETTLEMENTS_PATH):
        with open(_DATED_SETTLEMENTS_PATH, encoding="utf-8") as f:
            for d in json.load(f):
                if d.get("lat") is None or not d.get("capture_date"):
                    continue
                points[(round(d["lat"], 4), round(d["lon"], 4))] = {
                    "lat": d["lat"], "lon": d["lon"],
                    "transitions": [(d["capture_date"], "RF")],
                }
    if os.path.exists(_CONTROL_TIMELINE_PATH):
        try:
            with open(_CONTROL_TIMELINE_PATH, encoding="utf-8") as f:
                for e in json.load(f).get("settlements", []):
                    if e.get("lat") is None or not e.get("transitions"):
                        continue
                    points[(round(e["lat"], 4), round(e["lon"], 4))] = {
                        "lat": e["lat"], "lon": e["lon"],
                        "transitions": sorted((t["date"], t["holder"]) for t in e["transitions"]),
                    }
        except Exception as e:  # noqa: BLE001 — без хронологии работаем на старом датасете
            logger.warning("Изохрона СВО: хронология контроля не прочитана (%s)", type(e).__name__)
    return list(points.values())


def _holder_at(point: dict, month_end_iso: str) -> str | None:
    """Владелец пункта на конец месяца — по ПОСЛЕДНЕМУ переходу не позже даты.
    None = пункта ещё не касалась война (считаем украинским)."""
    holder = None
    for when, who in point["transitions"]:
        if when > month_end_iso:
            break
        holder = who
    return holder


def compute_isochrone(control_fill_geojson: dict, ukraine_boundary=None) -> dict | None:
    """Помесячная реконструкция линии фронта. Возвращает FeatureCollection —
    ОДИН полигон на месяц, properties {month, month_end, settlements_count,
    area_km2, delta_km2}. None при отсутствии исходных данных (честная
    деградация, не 500).

    ukraine_boundary — контур Украины; если передан, ячейки обрезаются по нему,
    а НЕ по сегодняшнему control_fill. Это принципиально: обрезка по
    сегодняшнему контролю физически не давала показать территории, которые РФ
    держала в 2022-м и оставила (Харьковская область, правобережье Херсона) —
    их просто нет в сегодняшнем контуре. Без параметра поведение прежнее."""
    from shapely.geometry import shape, mapping, MultiPoint, Point
    from shapely.ops import voronoi_diagram, unary_union

    points = _load_timeline_points()
    if not points:
        return None

    control_polys = [shape(f["geometry"]) for f in control_fill_geojson.get("features", [])]
    if not control_polys:
        return None
    control_union = unary_union(control_polys).buffer(0)
    clip_to = ukraine_boundary.buffer(0) if ukraine_boundary is not None else control_union

    geom_pts = [Point(p["lon"], p["lat"]) for p in points]
    try:
        vd = voronoi_diagram(MultiPoint(geom_pts), envelope=clip_to.buffer(2.0))
    except Exception as e:  # noqa: BLE001
        logger.warning("Изохрона СВО: voronoi_diagram упал: %s", e)
        return None

    # ВАЖНО: vd.geoms отдаёт НОВЫЕ объекты на каждом обращении — материализуем
    # список один раз и работаем по индексу. Иначе любая попытка запомнить
    # соответствие «ячейка → точка» по id() рассыпается (проверено: соответствие
    # находилось для ~1% ячеек, реконструкция вырождалась в пару пятен).
    vcells = list(vd.geoms)
    cells: list[tuple[int, object]] = []  # (индекс точки, обрезанная ячейка)
    for cell in vcells:
        owner = None
        for i, gp in enumerate(geom_pts):
            if cell.contains(gp) or cell.distance(gp) < 1e-9:
                owner = i
                break
        if owner is None:
            continue
        # Ограничитель влияния действует ТОЛЬКО за пределами сегодняшнего
        # контроля. Внутри него ячейки Вороного покрывают площадь без остатка —
        # если резать их и там, внутри контролируемой зоны остаются НЕПОКРЫТЫЕ
        # пустоты (владелец, 2026-07-25: «какие пустоты появляются в ЛНР, ДНР и
        # везде — это бред»; замерено до фикса: 4024 км², крупнейшая 1927 км²
        # в Луганской области). Снаружи ограничитель нужен: там он не даёт
        # ячейке редкой точки расползтись по территории, которой РФ не держала.
        in_control = cell.intersection(control_union)
        outside = (cell.intersection(clip_to).difference(control_union)
                       .intersection(geom_pts[owner].buffer(_POINT_INFLUENCE_DEG)))
        clipped = unary_union([g for g in (in_control, outside) if not g.is_empty])
        if not clipped.is_empty:
            cells.append((owner, clipped))
    if not cells:
        return None

    today_iso = date.today().isoformat()
    crimea_mass = _crimea_landmass(control_union)
    rf_today = {i for i in range(len(points)) if _holder_at(points[i], today_iso) == "RF"}

    # «Необъяснённый» остаток: части СЕГОДНЯШНЕЙ зоны контроля, которые не
    # покрывает ни одна ячейка пункта, удерживаемого РФ сегодня. Данных о том,
    # когда они перешли, у нас нет вовсе — по составу это долго удерживаемая
    # территория и захваты первых суток, отсутствующие в источниках. Показывать
    # их незакрашенными во ВСЕХ месяцах нельзя: получаются ровно те «пустоты в
    # ЛНР/ДНР и везде», которые владелец забраковал (2026-07-25) — площадь
    # годами не меняется, что само по себе выдаёт артефакт, а не движение
    # фронта. Поэтому относим их к удерживаемым с начала окна — как Крым.
    today_cells = [c for i, c in cells if i in rf_today]
    unexplained = (control_union.difference(unary_union(today_cells)).buffer(0)
                   if today_cells else None)
    if unexplained is not None and unexplained.is_empty:
        unexplained = None

    features = []
    prev_area_km2 = None
    for y, m, month_end_iso in _iter_months(_MONTH_START[0], _MONTH_START[1], today_iso):
        rf_idx = {i for i in range(len(points)) if _holder_at(points[i], month_end_iso) == "RF"}
        parts = [c for i, c in cells if i in rf_idx]
        if crimea_mass is not None and not crimea_mass.is_empty:
            parts.append(crimea_mass)
        if unexplained is not None:
            parts.append(unexplained)
        if not parts:
            continue
        # Огибающая месяца: сегодняшний контроль ПЛЮС то, что РФ держала тогда,
        # но уже не держит (Харьковская область, правобережье Херсона). Так
        # «сегодня» совпадает с фактической линией ISW (реконструкция не толще
        # правды), а прошлые месяцы всё равно могут выйти за её пределы —
        # ровно там, где это исторически и было.
        lost_since = [c for i, c in cells if i in rf_idx and i not in rf_today]
        envelope = unary_union([control_union, *lost_since]) if lost_since else control_union
        region = _smooth_and_clean(unary_union(parts))
        region = region.intersection(envelope)
        # Заделка «котлов» — ПОСЛЕ обрезки: сам контур обрезки содержит дыры,
        # и они бы вернулись в реконструкцию после любой более ранней очистки.
        region = _fill_holes_and_drop_islands(region)
        if region.is_empty:
            continue
        area_km2 = round(region.area * _KM2_PER_DEG2)
        # Упрощение ПОСЛЕ подсчёта площади (чтобы цифра считалась по полной
        # геометрии). 54 месяца по контуру ISW дают 227 тыс. вершин и 3.6 МБ
        # gzip в ответе — при том, что реконструкция и так сглажена на 3 км и
        # честно помечена как огрубление, детализация ниже полукилометра в ней
        # не несёт смысла, только вес.
        simplified = region.simplify(_OUTPUT_SIMPLIFY_DEG, preserve_topology=True)
        if not simplified.is_empty:
            region = simplified
        features.append({
            "type": "Feature",
            "properties": {
                "month": f"{y:04d}-{m:02d}",
                "month_end": month_end_iso,
                "settlements_count": len(rf_idx),
                "area_km2": area_km2,
                # Может быть ОТРИЦАТЕЛЬНОЙ — это не баг: осень-2022 РФ оставила
                # Харьковскую область и правобережье Херсона.
                "delta_km2": None if prev_area_km2 is None else area_km2 - prev_area_km2,
            },
            "geometry": mapping(region),
        })
        prev_area_km2 = area_km2

    if not features:
        return None
    return {"type": "FeatureCollection", "features": features}
