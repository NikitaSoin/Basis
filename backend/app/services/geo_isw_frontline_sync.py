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
import math
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
_OVERRIDES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_manual_overrides.json",
)
_KM_PER_DEG_LAT = 111.0  # грубая константа для конверсии radius_km→градусы на широте Украины


def load_manual_overrides() -> list[dict]:
    """Населённые пункты, взятие которых подтверждают МО РФ/Рыбарь, а живой слой
    ISW ещё нет (владелец, 2026-07-24: «Рыбарь достаточно точно надёжный»).
    ВСЕ они вливаются в ru_control единым фронтом — деления на confirmed/
    contested больше нет (владелец, 2026-07-25: «оранжевым ничем помечать не
    будем... вся область в красный цвет»), расхождение с ISW показывается
    кружком-маркером (см. эндпоинт /market/geo-map/svo). Честная деградация —
    файла нет или он битый → пустой список, синк линии не падает."""
    if not os.path.exists(_OVERRIDES_PATH):
        return []
    try:
        with open(_OVERRIDES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("settlements"), list):
            return data["settlements"]
        # совместимость со старой схемой confirmed/contested (до 2026-07-25)
        return list(data.get("confirmed", [])) + list(data.get("contested", []))
    except Exception as e:  # noqa: BLE001
        logger.warning("geo_svo_manual_overrides.json не прочитан: %s", e)
        return []


_CLAIMED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_claimed_captures.json",
)
_TIMELINE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "geo_svo_control_timeline.json",
)


# Максимальное удаление кандидата от фактической массы ISW-контроля, при
# котором мы вообще готовы поверить во «взятие». Владелец (2026-07-26, после
# бага с пятном в глубине Запорожской и «взятым» пунктом в глубине
# Днепропетровской): «населённый пункт может быть взят, если он рядом с линией
# фронта, а не в глубине». Механика бага: деревень-тёзок много (Вольное,
# Благодатное, Новосёловка есть в нескольких областях), Wikipedia-геокодинг
# берёт не ту, и _absorb_overrides затягивает клин красной зоны к точке за
# десятки км от фронта. Порог 25 км: реальные подтверждённые Рыбарём города
# лежали в 7-17 км от массы ISW (максимум — Константиновка, 17), ложные
# тёзки — в 50-100+ км.
_MAX_FRONT_DISTANCE_KM = 25.0

# Города, которые нельзя закрасить «за компанию» (config/geo_svo_cities.json).
# Владелец (2026-09-11): «город Орехов не взят (вроде)», а на карте он был
# красным. Разбор: заявление МО РФ о взятии Новопавловки Запорожской области
# приехало из ленты с координатами 47.5677/35.7849 — это центр ОРЕХОВА (0,5 км),
# буфер 3 км + морфологическое смыкание закрасили город целиком. Ни один
# источник Орехова не заявлял, ISW его контроль не подтверждает.
_CITIES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "geo_svo_cities.json")
# Водные барьеры (Днепр, config/geo_svo_rivers.json): пункт на другом берегу к массе
# контроля не присоединяется, «крышка» через реку не рисуется (владелец, 2026-09-14:
# «взятая деревушка севернее Днепра, куда ВС РФ не заходят — ни одна сторона там не
# форсирует»). Захват через реку возможен только как плацдарм, а его ISW покажет сам.
_RIVERS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "geo_svo_rivers.json")
_BARRIER_GAP_KM = 1.0   # зазор «крышки» от русла: заливка не должна касаться другого берега
# Приграничный пункт считается правдоподобным, только если он у самой границы: наступление
# с территории РФ идёт на километры, а не на десятки (Волчанск 5 км, Казачья Лопань 3 км,
# Гоптовка 2 км). 25-километровый порог от «плацдарма» пропускал тёзок под Харьковом
# (владелец, 2026-09-14: «взятый населённый пункт практически рядом с Харьковом»).
_MAX_BORDER_DISTANCE_KM = 12.0
# Цепочка от уже принятого пункта: продвижение от границы идёт полосой сёл, каждое
# следующее в нескольких км от предыдущего.
_CHAIN_KM = 8.0
# Кружок села из ленты/хронологии/заявлений: 1,5 км — застройка села с ближней
# округой; 3 км давали 28 км² на каждое село и раздували «км²/мес» (см. _CAP_*).
_VILLAGE_RADIUS_KM = 1.5


def load_barriers():
    """Днепр как shapely-геометрия (MultiLineString) или None, если файла нет —
    барьер вторичен, синк обязан работать и без него."""
    try:
        from shapely.geometry import shape
        from shapely.ops import unary_union
        with open(_RIVERS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        geoms = [shape(ft["geometry"]) for ft in data.get("features", []) if ft.get("geometry")]
        return unary_union(geoms) if geoms else None
    except Exception:  # noqa: BLE001
        logger.warning("Водные барьеры не прочитаны — правило «через реку» пропущено", exc_info=True)
        return None


def _crosses_barrier(a, b, barrier) -> bool:
    """Пересекает ли отрезок a→b барьер (реку)."""
    if barrier is None or barrier.is_empty:
        return False
    from shapely.geometry import LineString
    return LineString([a, b]).intersects(barrier)


def _load_protected_cities() -> tuple[list[dict], float]:
    """[{name, aliases, lat, lon}], радиус защиты в км. Пустой список — если
    файла нет: защита вторична, синк линии обязан работать и без неё."""
    try:
        with open(_CITIES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cities", []), float(data.get("radius_km", 3.0))
    except Exception:  # noqa: BLE001
        logger.warning("Защищённые города не прочитаны — правило пропущено", exc_info=True)
        return [], 3.0


def _city_name_matches(claim_name: str, city: dict) -> bool:
    """Заявлен ли ИМЕННО этот город. Сравнение по нормализованному имени и
    алиасам — «Купянск-Узловой» не должен считаться заявкой на «Купянск».

    Имя в наших источниках часто несёт второй вариант в скобках («Красноармейск
    (Покровск)», «Артёмовск (Бахмут)») — считаем заявкой оба, иначе законный
    оверрайд владельца отвергался бы как ошибка геокодинга."""
    def norm(x: str) -> str:
        return (x or "").strip().lower().replace("ё", "е").replace("'", "").replace("’", "")

    raw = (claim_name or "").replace("(", "|").replace(")", "|")
    variants = {norm(part) for part in raw.split("|") if norm(part)}
    if not variants:
        return False
    known = {norm(city.get("name"))} | {norm(a) for a in city.get("aliases", [])}
    return bool(variants & known)


def _load_ru_border_land(ukraine_boundary=None):
    """Российские приграничные области из статической карты очага — «плацдарм»,
    от которого может идти захват. Берём регионы с control == "ru", лежащие ВНЕ
    контура Украины: так Брянская/Курская/Белгородская/Краснодарский попадают, а
    Крым, Севастополь и Луганская (они тоже помечены "ru", но находятся внутри
    Украины и в заливку входят как контроль) — нет.

    Нужно для направленного присоединения: без плацдарма приграничные взятия
    (Волчанск, Казачья Лопань, Гоптовка) не к чему привязать — наступление там
    идёт с территории России, а масса контроля внутри Украины далеко."""
    from shapely.geometry import shape
    from shapely.ops import unary_union
    try:
        with open(_SVO_MAP_PATH, encoding="utf-8") as f:
            static_map = json.load(f)
    except Exception:  # noqa: BLE001 — плацдарм вторичен, слой обязан собраться
        logger.warning("Приграничные регионы РФ не прочитаны", exc_info=True)
        return None
    polys = []
    for feat in static_map["base_map"]["regions_geojson"]["features"]:
        if (feat["properties"].get("control") or "").strip() != "ru":
            continue
        try:
            g = shape(feat["geometry"]).buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if ukraine_boundary is not None and g.intersection(ukraine_boundary).area > 0.5 * g.area:
            continue  # регион внутри Украины (Крым, Севастополь, Луганская) — не плацдарм
        polys.append(g)
    return unary_union(polys).buffer(0) if polys else None


def _load_oblast_shapes() -> list[tuple[str, object]]:
    """(первое слово name_ru, shapely-геометрия) по регионам статической карты —
    для проверки «координата лежит в заявленной области». Сортировка по длине
    слова убывающе, чтобы «Киевская» матчилась раньше «Киев» (город)."""
    from shapely.geometry import shape
    with open(_SVO_MAP_PATH, encoding="utf-8") as f:
        static_map = json.load(f)
    out = []
    for feat in static_map["base_map"]["regions_geojson"]["features"]:
        name = (feat["properties"].get("name_ru") or "").strip()
        if not name:
            continue
        try:
            out.append((name.split()[0], shape(feat["geometry"]).buffer(0.05)))
        except Exception:  # noqa: BLE001 — одна битая геометрия не рушит проверку
            continue
    out.sort(key=lambda t: -len(t[0]))
    return out


def _holder_as_of(cand: dict, day_iso: str) -> str | None:
    """Кто держит пункт на дату: по хронологии переходов (последний переход не
    позже даты) либо по одиночной дате заявления. None — пункт на эту дату
    нашими источниками за РФ не числится."""
    transitions = cand.get("transitions")
    if transitions:
        holder = None
        for when, who in transitions:
            if when > day_iso:
                break
            holder = who
        return holder
    claimed = cand.get("date")
    if claimed is None:
        # Недатированный ручной оверрайд: считаем действующим всегда. Для живой
        # заливки это верно, для помесячной реконструкции — нет (пункт «взят» с
        # первого месяца ряда), поэтому тест требует дат у всех оверрайдов.
        return "RF"
    return "RF" if claimed <= day_iso else None


def dated_candidates(ukraine_boundary=None, db=None) -> list[dict]:
    """ВСЕ пункты, которые по данным МО РФ/Рыбаря числятся (или числились) под
    контролем РФ, — С ДАТАМИ, из четырёх источников:
      1) geo_svo_manual_overrides.json — ручные оверрайды (radius_km; дата —
         claimed_date, проставленная в файле по дате заявления МО РФ);
      2) geo_svo_control_timeline.json — хронология переходов в обе стороны
         (сюда попадает, напр., Волчанск: МО заявляло освобождение в декабре
         2025, а живой слой ISW его не включает);
      3) geo_svo_claimed_captures.json — заявленные захваты (claimed_date);
      4) БД geo_territorial_claims (status=ru_control) — авто-извлечённые из
         ленты пайплайном geo_digest (claimed_date, фолбэк — дата появления).

    Даты нужны не только карте «сегодня»: по ним помесячный ряд «км²/мес»
    восстанавливается НА КОНЕЦ КАЖДОГО МЕСЯЦА как есть (пункт считается взятым
    с месяца заявления, а не с момента, когда он попал в наш список). Иначе
    ряд рос от пополнения списка, а не от движения фронта — замерено +2653 км²
    за август 2026 против ~150 км²/мес по ISW (владелец, 2026-09-12: считать
    темпы «по нашей» заливке, ISW — внешняя сверка).

    Точки ВНЕ контура Украины отбрасываются (Суджа, Юнаковка и прочее
    приграничье РФ): слой описывает контроль внутри Украины, российская
    территория в него не входит по определению. Дедупликация по координатам
    здесь НЕ делается — она зависит от даты (см. candidates_as_of)."""
    from shapely.geometry import Point

    out: list[dict] = []

    def add(name, oblast, lat, lon, radius_km, *, src, date=None, transitions=None):
        if lat is None or lon is None:
            return
        if ukraine_boundary is not None and not ukraine_boundary.contains(Point(lon, lat)):
            return
        # src — откуда пункт: override|timeline|claimed|db. Нужен правилу 0
        # (привязка по справочнику НП): координаты ручных оверрайдов и хронологии
        # выверены руками, их не трогаем; ленту и заявления — сверяем.
        cand = {"name": name, "oblast": oblast, "lat": lat, "lon": lon, "radius_km": radius_km, "src": src}
        if transitions:
            cand["transitions"] = transitions
        else:
            cand["date"] = date
        out.append(cand)

    for o in load_manual_overrides():
        add(o.get("name"), o.get("oblast"), o.get("lat"), o.get("lon"), o.get("radius_km", 3),
            src="override", date=o.get("claimed_date"))

    for path, reader in ((_TIMELINE_PATH, "timeline"), (_CLAIMED_PATH, "claimed")):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001 — побочный источник не роняет синк
            logger.warning("%s не прочитан: %s", os.path.basename(path), type(e).__name__)
            continue
        if reader == "timeline":
            for e in data.get("settlements", []):
                transitions = sorted((t["date"], t["holder"]) for t in e.get("transitions", [])
                                     if t.get("date") and t.get("holder"))
                if not transitions:
                    continue
                add(e.get("name"), e.get("oblast"), e.get("lat"), e.get("lon"), _VILLAGE_RADIUS_KM,
                    src="timeline", transitions=transitions)
        else:
            for p in data.get("points", []):
                add(p.get("name"), p.get("oblast"), p.get("lat"), p.get("lon"), _VILLAGE_RADIUS_KM,
                    src="claimed", date=p.get("claimed_date"))

    # 4-й источник — ЖИВОЙ: territorial_claims, автоматически извлечённые
    # LLM-пайплайном geo_digest из ленты (Рыбарь/МО РФ и др.). Владелец
    # (2026-07-26): «взяли войска такой город — линия фронта сдвинулась» —
    # именно это звено раньше отсутствовало: claims писались в БД, но геометрия
    # их не читала, автообновления линии не было.
    if db is not None:
        try:
            from app.models.geo import GeoTerritorialClaim
            for r in (db.query(GeoTerritorialClaim)
                      .filter(GeoTerritorialClaim.status == "ru_control",
                              GeoTerritorialClaim.lat.isnot(None)).all()):
                when = (r.claimed_date.isoformat() if r.claimed_date
                        else (r.created_at.date().isoformat() if r.created_at else None))
                add(r.settlement, r.oblast, r.lat, r.lon, _VILLAGE_RADIUS_KM, src="db", date=when)
        except Exception:  # noqa: BLE001 — живой источник не роняет синк
            logger.warning("dated_candidates: territorial_claims из БД не подмешаны", exc_info=True)
    return out


def candidates_as_of(cands: list[dict], day_iso: str) -> list[dict]:
    """Пункты, которые на дату числятся за РФ, без дублей по координатам
    (первый по порядку источников выигрывает: ручной оверрайд → хронология →
    заявления → лента). Дедуп ПОСЛЕ отбора по дате: у одной точки в двух
    источниках могут быть разные даты — берём ту, что уже наступила."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for c in cands:
        if _holder_as_of(c, day_iso) != "RF":
            continue
        key = (round(c["lat"], 3), round(c["lon"], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _gazetteer_resolve(name, oblast, near=None, hint=None, barrier=None) -> dict:
    """Тонкая обёртка над справочником НП — чтобы тесты подменяли, а отсутствие
    файла не роняло синк."""
    try:
        from app.services.geo_gazetteer import resolve
        return resolve(name, oblast, near=near, hint=hint, barrier=barrier)
    except Exception:  # noqa: BLE001
        logger.warning("Справочник НП недоступен — правило 0 пропущено", exc_info=True)
        return {"status": "no_gazetteer", "candidates": 0}


def validate_candidates(out: list[dict], control_mass=None, *, border_mass=None, barrier=None,
                        quiet: bool = False) -> list[dict]:
    """Проверки кандидата на правдоподобие — ОДНИ И ТЕ ЖЕ для живой заливки
    (absorb_candidates) и для помесячной реконструкции ряда (изохрона): иначе
    «сегодня» и «конец прошлого месяца» считались бы по разным правилам, и
    дельта текущего месяца мерила бы разницу правил, а не движение фронта.
    control_mass — масса контроля ISW, от которой считается «рядом с фронтом»
    (для прошлых месяцев — архивный срез того месяца); border_mass — приграничные
    области РФ (для них свой, короткий порог); barrier — реки, через которые
    присоединение не идёт."""
    from shapely.geometry import Point
    from shapely.ops import nearest_points, unary_union

    log = (lambda *a, **k: None) if quiet else logger.warning
    near_mass = control_mass
    if control_mass is not None and border_mass is not None and not border_mass.is_empty:
        near_mass = unary_union([control_mass, border_mass])

    # Правило 0 (владелец, 2026-09-14): координата пункта из ленты/заявлений —
    # по СПРАВОЧНИКУ населённых пунктов (имя + область; при тёзках — район и
    # близость к фронту), а не по геокодингу статьи Википедии. Боевые случаи:
    # «Новопавловка Запорожской» с координатами центра Орехова, «Красный Кут
    # Донецкой» в Саратовской области. Ручные оверрайды и хронологию не трогаем —
    # их координаты выверены руками. Не найден в справочнике — оставляем как
    # пришло, дальше работают прежние правила; тёзки не развести — отклоняем.
    resolved = []
    for o in out:
        if o.get("src") not in ("claimed", "db"):
            resolved.append(o)
            continue
        hit = _gazetteer_resolve(o.get("name"), o.get("oblast"), near=near_mass, hint=(o["lat"], o["lon"]),
                                 barrier=barrier)
        st = hit.get("status")
        if st in ("exact", "near_front", "fuzzy"):
            moved_km = Point(o["lon"], o["lat"]).distance(Point(hit["lon"], hit["lat"])) * _KM_PER_DEG_LAT
            if moved_km > 0.5 and not quiet:
                logger.info("validate_candidates: «%s» (%s) привязан по справочнику (%s): сдвиг %.1f км → %s, %s",
                            o["name"], o.get("oblast") or "—", st, moved_km, hit.get("oblast"), hit.get("raion") or "район н/д")
            resolved.append({**o, "lat": hit["lat"], "lon": hit["lon"], "geocode": st})
        elif st in ("ambiguous", "oblast_mismatch"):
            log("validate_candidates: ОТКЛОНЁН «%s» (%s) — в справочнике %d тёзок (%s), ни область, ни район, "
                "ни близость к фронту, ни прежняя координата их не разводят",
                o["name"], o.get("oblast") or "—", hit.get("candidates", 0), st)
        else:
            resolved.append(o)  # not_found / no_gazetteer — прежние правила ниже
    out = resolved

    # Правило 1: координата обязана лежать в ЗАЯВЛЕННОЙ области — ловит тёзок,
    # геокоженных не туда («Благодатное» не той области и т.п.).
    try:
        oblasts = _load_oblast_shapes()
    except Exception:  # noqa: BLE001
        logger.warning("validate_candidates: контуры областей не загрузились — проверка области пропущена")
        oblasts = []
    if oblasts:
        kept = []
        for o in out:
            stated = (o.get("oblast") or "").strip()
            region = next((g for w, g in oblasts if w and w in stated), None) if stated else None
            if region is not None and not region.contains(Point(o["lon"], o["lat"])):
                log("validate_candidates: ОТКЛОНЁН «%s» — координата (%.3f, %.3f) не в "
                    "заявленной области «%s» (вероятно, тёзка при геокодинге)",
                    o["name"], o["lat"], o["lon"], stated)
                continue
            kept.append(o)
        out = kept

    # Правило 1б: координата села в черте ЧУЖОГО города — это ошибка привязки,
    # а не взятие города. Боевой случай (2026-09-11): «Новопавловка Запорожской
    # области» из сводки МО РФ получила координаты центра ОРЕХОВА, и город
    # закрасился взятым. Проверка по имени, а не по расстоянию до фронта:
    # деревня-тёзка у самого города физически возможна, но тогда её собственная
    # координата не совпадает с центром города с точностью до полукилометра.
    cities, city_radius_km = _load_protected_cities()
    if cities:
        kept = []
        for o in out:
            hit = None
            for c in cities:
                d_km = Point(o["lon"], o["lat"]).distance(Point(c["lon"], c["lat"])) * _KM_PER_DEG_LAT
                if d_km <= city_radius_km and not _city_name_matches(o.get("name"), c):
                    hit = (c, d_km)
                    break
            if hit is not None:
                log("validate_candidates: ОТКЛОНЁН «%s» — координата (%.4f, %.4f) в %.1f км "
                    "от центра города «%s», который никто не заявлял взятым "
                    "(ошибка геокодинга заявления)",
                    o["name"], o["lat"], o["lon"], hit[1], hit[0]["name"])
                continue
            kept.append(o)
        out = kept

    # Правило 2: пункт может быть «взят», только если он РЯДОМ С ФРОНТОМ —
    # не дальше _MAX_FRONT_DISTANCE_KM от фактической массы ISW-контроля, либо
    # (приграничье) не дальше _MAX_BORDER_DISTANCE_KM от территории РФ.
    # Правило 2б: отрезок к ближайшей точке фронта/границы не пересекает реку
    # (Днепр) — иначе тёзка на другом берегу «присоединяется» через воду.
    if control_mass is not None and not control_mass.is_empty:
        has_border = border_mass is not None and not border_mass.is_empty

        def _anchor_for(o):
            """(точка опоры, км до неё) — масса ISW в пределах порога, иначе граница
            РФ в пределах своего порога, иначе None."""
            p = Point(o["lon"], o["lat"])
            d_km = control_mass.distance(p) * _KM_PER_DEG_LAT
            if d_km <= _MAX_FRONT_DISTANCE_KM:
                return nearest_points(control_mass, p)[0], d_km
            if has_border:
                d_b = border_mass.distance(p) * _KM_PER_DEG_LAT
                if d_b <= _MAX_BORDER_DISTANCE_KM:
                    return nearest_points(border_mass, p)[0], d_b
            return None, d_km

        kept, pending = [], []
        for o in out:
            p = Point(o["lon"], o["lat"])
            try:
                anchor, d_km = _anchor_for(o)
            except Exception:  # noqa: BLE001
                anchor, d_km = None, float("inf")
            if anchor is None:
                pending.append(o)
                continue
            if _crosses_barrier(anchor, p, barrier):
                log("validate_candidates: ОТКЛОНЁН «%s» (%s) — на другом берегу реки от фронта "
                    "(%.0f км), через реку не присоединяем", o["name"], o.get("oblast"), d_km)
                continue
            kept.append(o)

        # Цепочка: пункт дальше порогов, но в _CHAIN_KM от уже принятого, — тоже
        # принят (фронт от границы идёт полосой: Волчанск → Белый Колодец →
        # Бакшеевка). Повторяем, пока цепочка растёт. Через реку не тянемся.
        changed = True
        while changed and pending:
            changed = False
            still = []
            for o in pending:
                p = Point(o["lon"], o["lat"])
                link = None
                for k in kept:
                    q = Point(k["lon"], k["lat"])
                    if p.distance(q) * _KM_PER_DEG_LAT <= _CHAIN_KM and not _crosses_barrier(q, p, barrier):
                        link = k
                        break
                if link is not None:
                    kept.append(o)
                    changed = True
                else:
                    still.append(o)
            pending = still
        for o in pending:
            p = Point(o["lon"], o["lat"])
            d_km = control_mass.distance(p) * _KM_PER_DEG_LAT
            d_b = border_mass.distance(p) * _KM_PER_DEG_LAT if has_border else float("inf")
            log("validate_candidates: ОТКЛОНЁН «%s» (%s) — %.0f км от линии фронта (порог %.0f), "
                "%.0f км от границы РФ (порог %.0f), не в цепочке с принятыми (%.0f км) — взятие "
                "в глубине тыла неправдоподобно",
                o["name"], o.get("oblast"), d_km, _MAX_FRONT_DISTANCE_KM,
                d_b if d_b != float("inf") else -1, _MAX_BORDER_DISTANCE_KM, _CHAIN_KM)
        out = kept

        # Правило 3: пункт УЖЕ ВНУТРИ линии ISW → вливать нечего, выкидываем.
        # Это не только экономия: морфологическое смыкание (_absorb_overrides)
        # надувает линию в окрестности КАЖДОГО пункта, даже глубоко тылового —
        # замерено 2026-07-26: 93 кандидата (большинство — давно взятые города
        # из хронологии: Донецк, Мелитополь, Мариуполь...) раздували красную
        # зону на ~6 000 км² чистой «подушки» вдоль всей линии. Владелец увидел
        # это как «за июль +7000 км²». Остаются только пункты, которых у ISW
        # ещё НЕТ — ровно те, ради которых оверрайды и существуют.
        inside = [o["name"] for o in out if control_mass.contains(Point(o["lon"], o["lat"]))]
        if inside and not quiet:
            logger.info("validate_candidates: %d пунктов уже внутри линии ISW — в геометрию не идут (%s%s)",
                        len(inside), ", ".join(inside[:8]), "…" if len(inside) > 8 else "")
        out = [o for o in out if not control_mass.contains(Point(o["lon"], o["lat"]))]
    return out


def absorb_candidates(ukraine_boundary=None, db=None, control_mass=None, *, border_mass=None,
                      barrier=None) -> list[dict]:
    """ВСЕ пункты, которые по данным МО РФ/Рыбаря СЕГОДНЯ под контролем РФ и
    проходят проверки правдоподобия, — для живой заливки карты.

    Владелец (2026-07-25): «у тебя немало кружочков с комментариями это под
    контролем России, но не подтверждено, но линия фронта не проходит через
    них, как будто под контролем Украины». То есть карта противоречила
    собственным подписям. Теперь источник один: если наши данные говорят
    «под РФ» — пункт и в красной зоне, и с кружком «ISW не подтвердил».

    Состав: dated_candidates (четыре источника с датами) → отбор на сегодня →
    validate_candidates (область, чужой город, 25 км от фронта, не внутри ISW).
    Та же цепочка с другой датой даёт заливку на конец любого прошлого месяца
    (см. geo_svo_capture_isochrone)."""
    today = datetime.now(timezone.utc).date().isoformat()
    return validate_candidates(
        candidates_as_of(dated_candidates(ukraine_boundary, db=db), today), control_mass,
        border_mass=border_mass, barrier=barrier)


def _point_buffer_km(lat: float, lon: float, radius_km: float):
    from shapely.geometry import Point
    deg = radius_km / _KM_PER_DEG_LAT
    return Point(lon, lat).buffer(deg)


# Параметры прежнего КРУГОВОГО смыкания (closing). Сама механика заменена
# (клин 2026-09-12, затем «крышка» 2026-09-14), но константы оставлены: на них
# опирается тест, который сравнивает старое поведение с новым и тем доказывает,
# что фикс действительно что-то меняет.
_ABSORB_CLOSE_DEG = 0.20
_ABSORB_LOCAL_DEG = 0.50
# Клин (2026-09-12) — тоже оставлен для теста-сравнения.
_WEDGE_WIDTH_RATIO = 0.6
_WEDGE_MAX_WIDTH_KM = 12.0
# «Крышка» присоединения (2026-09-14): пункт закрывает участок фронта, ОБРАЩЁННЫЙ
# к нему, целиком. Радиус окна вдоль фронта = доля от зазора до фронта, но не
# меньше минимума (иначе село в 2 км от границы даёт точку, а не полосу) и не
# больше потолка (иначе один дальний пункт закрывает пол-области).
# Владелец (2026-09-16): «цифры за июль и сентябрь выглядят чересчур». Замер на
# живых данных: при радиусе села 3 км и окне 6 км каждый заявленный пункт
# добавлял ~39 км² (3,5 тыс. км² сверх ISW на 90 пунктов) — село с округой
# столько не занимает. Радиус села 1,5 км, окно от 3 км, ширина = зазор: ~20 км²
# на пункт, вдвое скромнее, при этом карман между фронтом и пунктом закрывается.
_CAP_RATIO = 1.0
_CAP_MIN_KM = 3.0
_CAP_MAX_KM = 18.0
_CAP_CITY_RATIO = 2.5             # × radius_km ГОРОДА: Константиновка (5 км) смотрит на 12,5 км фронта
_CAP_CITY_MIN_RADIUS_KM = 4.0     # сёла (3 км) под это правило не попадают — иначе полосы у границы раздуваются


def _wedge_absorb(ru_mass, overrides: list[dict], source_mass=None):
    """Клин к ближайшей точке фронта (версия 2026-09-12) — оставлена ТОЛЬКО для
    теста-сравнения со старым поведением; боевая механика — _absorb_overrides."""
    from shapely.geometry import Point
    from shapely.ops import unary_union, nearest_points

    circles = [_point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3)) for o in overrides]
    combined = unary_union([ru_mass] + circles).buffer(0)
    source = source_mass if source_mass is not None and not source_mass.is_empty else ru_mass
    wedges = []
    for o in overrides:
        p = Point(o["lon"], o["lat"])
        if ru_mass.contains(p):
            continue
        anchor = nearest_points(source, p)[0]
        gap_km = p.distance(anchor) * _KM_PER_DEG_LAT
        if gap_km <= 0.01:
            continue
        base_km = min(max(o.get("radius_km", 3), _WEDGE_WIDTH_RATIO * gap_km), _WEDGE_MAX_WIDTH_KM)
        wedges.append(unary_union([_point_buffer_km(anchor.y, anchor.x, base_km),
                                   _point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3))]).convex_hull)
    addition = unary_union(wedges).difference(combined) if wedges else combined.difference(combined)
    return unary_union([combined, addition]).buffer(0)


def _absorb_overrides(ru_mass, overrides: list[dict], source_mass=None, ukraine_boundary=None,
                      barrier=None):
    """Вливает пункты-оверрайды в массив РФ-контроля «крышкой»: взятый пункт
    закрывает участок фронта, обращённый к нему, ЦЕЛИКОМ.

    Владелец (2026-09-12): «соединяешь с тем куском фронта, откуда собственно шёл
    захват... только если линия фронта продвинулась целиком — тогда целиком и
    присоединяешь цветом». И (2026-09-14) по клину к ближайшей точке: «линия
    рисуется кругляшками, сосисками, кругляшки заходят на территорию России;
    восточнее Константиновки точно взято, а не закрашено; рывок в Харьковской
    выглядит ошибочным».

    Механика на каждый пункт P (в порядке удаления от фронта, ближние первыми):
      1. зазор = расстояние от P до фронта-источника (контроль + приграничные
         области РФ + уже присоединённые пункты — цепочка сёл идёт от предыдущего,
         а не тянется отдельной «сосиской» к далёкой массе);
      2. окно вдоль фронта радиусом R = clamp(зазор × _CAP_RATIO, min, max);
      3. «крышка» = выпуклая оболочка (участок границы источника внутри окна ∪
         кружок пункта) минус источник — закрывается весь карман между фронтом,
         обращённым к пункту, и самим пунктом (у Константиновки — и восточный
         тоже, а не только клин к ближайшей точке);
      4. всё режется по контуру Украины: наступление с российской территории
         закрашивает только украинскую сторону границы.

    Что было раньше и почему заменено:
      1) голый Point.buffer() → изолированный остров в 7-17 км от массива;
      2) буферизованный отрезок-коридор → тонкий шип;
      3) морфологическое closing (радиус ~22 км во ВСЕ стороны) → закрашивало
         незаявленное (Орехов) и спрямляло фронт;
      4) клин к ближайшей точке (2026-09-12) → карманы рядом не закрывались,
         база клина на границе наполовину лежала в России, цепочки — «сосиски».
    """
    from shapely import clip_by_rect
    from shapely.geometry import Point, GeometryCollection
    from shapely.ops import unary_union, nearest_points

    if not overrides:
        return ru_mass
    circles = [_point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3)) for o in overrides]
    combined = unary_union([ru_mass] + circles).buffer(0)
    source = source_mass if source_mass is not None and not source_mass.is_empty else ru_mass
    source_boundary = source.boundary  # один раз: граница массы большая, пунктов десятки

    # Ближние к фронту — первыми: следующие пункты цепочки опираются на уже
    # присоединённые (added), а не на далёкую массу. Массу с присоединённым не
    # объединяем на каждом шаге (это дорого: 56 месяцев × десятки пунктов) —
    # якорь и «обращённый участок» ищем в массе и в присоединённом порознь.
    def _gap(o):
        return source.distance(Point(o["lon"], o["lat"]))
    ordered = sorted((o for o in overrides if not ru_mass.contains(Point(o["lon"], o["lat"]))), key=_gap)

    added = None              # крышки + кружки уже присоединённых пунктов (малая геометрия)
    caps: list = []
    for o in ordered:
        p = Point(o["lon"], o["lat"])
        radius_km = o.get("radius_km", 3)
        circle = _point_buffer_km(o["lat"], o["lon"], radius_km)
        try:
            anchor = nearest_points(source, p)[0]
            if added is not None and not added.is_empty:
                a2 = nearest_points(added, p)[0]
                if p.distance(a2) < p.distance(anchor):
                    anchor = a2
        except Exception:  # noqa: BLE001 — один кривой кандидат не рушит слой
            added = unary_union([added, circle]) if added is not None else circle
            continue
        gap_km = p.distance(anchor) * _KM_PER_DEG_LAT
        if gap_km <= 0.01:
            added = unary_union([added, circle]) if added is not None else circle
            continue
        # Крупный пункт (город с radius_km 4-5) закрывает и более широкий карман:
        # у Константиновки масса ISW лежит и на востоке, и на юго-востоке, окно
        # по одному зазору до неё не доставало (владелец, 2026-09-14: «восточнее
        # Константиновки точно взято»).
        city_reach = _CAP_CITY_RATIO * radius_km if radius_km >= _CAP_CITY_MIN_RADIUS_KM else 0.0
        # окно обязано заходить ЗА линию фронта (gap + 1 км): ровно в зазор оно
        # лишь касается границы, обрезка даёт пустоту, и крышка не строится
        r_km = min(max(_CAP_MIN_KM, _CAP_RATIO * gap_km, gap_km + 1.0, city_reach), _CAP_MAX_KM)
        r_deg = r_km / _KM_PER_DEG_LAT
        # по долготе градус короче (cos широты ≈ 0,66 на этих широтах) — иначе окно
        # по фронту, идущему с севера на юг, было бы на треть уже заявленного
        r_lon = r_deg / max(0.3, math.cos(math.radians(p.y)))
        # окно — прямоугольник 2R (clip_by_rect в разы быстрее пересечения с кругом)
        facing_parts = [clip_by_rect(source_boundary, p.x - r_lon, p.y - r_deg, p.x + r_lon, p.y + r_deg)]
        if added is not None and not added.is_empty:
            facing_parts.append(clip_by_rect(added.boundary, p.x - r_lon, p.y - r_deg, p.x + r_lon, p.y + r_deg))
        facing = unary_union([g for g in facing_parts if not g.is_empty])
        if facing.is_empty:
            # окно не достаёт до фронта (не должно случаться после правила 25 км)
            # — хотя бы связать с якорем узкой полосой, а не оставлять остров
            facing = anchor
        cap = GeometryCollection([facing, circle]).convex_hull
        caps.append(cap)
        piece = unary_union([cap, circle])
        added = unary_union([added, piece]) if added is not None else piece

    addition = unary_union(caps).difference(combined) if caps else combined.difference(combined)
    if ukraine_boundary is not None and not addition.is_empty:
        addition = addition.intersection(ukraine_boundary)
    if barrier is not None and not barrier.is_empty and not addition.is_empty:
        # «Крышка» не переходит реку: вырезаем русло с зазором, а куски добавления,
        # оказавшиеся на другом берегу (без связи с массой), отбрасываем.
        addition = addition.difference(barrier.buffer(_BARRIER_GAP_KM / _KM_PER_DEG_LAT)).buffer(0)
        parts = list(addition.geoms) if hasattr(addition, "geoms") else [addition]
        keep = [g for g in parts if not g.is_empty and (g.intersects(combined) or g.distance(combined) < 1e-6)]
        addition = unary_union(keep) if keep else addition.difference(addition)

    # Крышка идёт по фронту на километры и может накрыть город, которого никто не
    # заявлял: так Орехов оказался красным из-за соседних сёл (владелец,
    # 2026-09-11). Вырезаем из ДОБАВЛЕНИЯ окрестности защищённых городов, кроме
    # заявленных по имени. Из массы ISW и из кружков самих кандидатов не
    # вырезаем ничего: если ISW считает город взятым — он взят.
    cities, city_radius_km = _load_protected_cities()
    if cities and not addition.is_empty:
        claimed_names = [o.get("name") for o in overrides]
        shields = [
            _point_buffer_km(c["lat"], c["lon"], city_radius_km)
            for c in cities
            if not any(_city_name_matches(n, c) for n in claimed_names)
        ]
        if shields:
            addition = addition.difference(unary_union(shields))

    result = unary_union([combined, addition]).buffer(0)
    if ukraine_boundary is not None:
        # Кружок приграничного села тоже не должен лежать в России.
        result = result.intersection(ukraine_boundary).buffer(0)
    if barrier is not None and not barrier.is_empty:
        # То же для кружков самих пунктов: всё НАШЕ (сверх массы ISW) режется по руслу,
        # а куски, оставшиеся на другом берегу без связи с массой, отбрасываются.
        ours = result.difference(ru_mass).difference(barrier.buffer(_BARRIER_GAP_KM / _KM_PER_DEG_LAT)).buffer(0)
        parts = list(ours.geoms) if hasattr(ours, "geoms") else [ours]
        anchor_mass = source if source is not None else ru_mass
        keep = [g for g in parts if not g.is_empty and (g.intersects(ru_mass) or g.intersects(anchor_mass))]
        result = unary_union([ru_mass] + keep).buffer(0)
    return result


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
    # Заделываем внутренние «дыры-воду». Полигоны областей обрезаны по контуру
    # суши (иначе заливка уходила бы в море), из-за чего Днепр, Каховское
    # водохранилище и лиманы стали дырами ВНУТРИ страны. Для расчёта контроля
    # это неверно: река — часть территории, а не пропуск в ней. Практический
    # эффект бага, на который наткнулся: Херсон стоит вплотную к Днепру, его
    # координата попадала в вырезанную «воду», ячейка города оставалась пустой
    # и город не отображался занятым ни в одном месяце весны-осени 2022.
    from shapely.geometry import Polygon as _Polygon
    merged = unary_union(polys)
    parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    filled = [_Polygon(p.exterior) for p in parts if p.geom_type == "Polygon"]
    return (unary_union(filled).buffer(0) if filled else merged), static_map


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


def _smooth_polygon(poly, dist: float = 0.0035):
    """Морфологическое сглаживание (closing → opening с круглыми стыками) —
    убирает «дёрганость»/зубчатость на границе полигонов ISW (владелец,
    2026-07-24: «местами коряво и не ровно линии проведены, вблизи видны
    дёрганости»). closing (buffer+/buffer-) сглаживает выпуклые зубцы,
    opening (buffer-/buffer+) — вогнутые зазубрины; join_style=1 (round) —
    скруглённые, не острые стыки при обоих проходах. dist ~0.0035° (~350м на
    широте Украины) — тот же порядок, что порог фильтра шума линии
    (MIN_SEGMENT_DEG), достаточно, чтобы убрать шум вершин ISW-полигонов, но
    не срезать реальные небольшие выступы/котлы величиной в насел. пункт."""
    closed = poly.buffer(dist, join_style=1).buffer(-dist, join_style=1)
    opened = closed.buffer(-dist, join_style=1).buffer(dist, join_style=1)
    return opened.buffer(0)


def _fill_new_holes(geom, isw_mass):
    """Заделывает «котлы», которых нет в самой массе ISW: замкнутые белые дыры
    внутри заливки появляются только от нашего присоединения (крышки с двух
    сторон смыкаются вокруг незанятого поля). Владелец (2026-09-14): «на карте
    как будто котлы». Дыры самой ISW (реальные очаги) не трогаем."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import unary_union

    isw_holes = [Polygon(r) for g in (isw_mass.geoms if hasattr(isw_mass, "geoms") else [isw_mass])
                 if g.geom_type == "Polygon" for r in g.interiors]
    rebuilt = []
    for g in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
        if g.geom_type != "Polygon":
            continue
        keep = [r for r in g.interiors if any(Polygon(r).intersects(h) for h in isw_holes)]
        rebuilt.append(Polygon(g.exterior, keep))
    return unary_union(rebuilt).buffer(0) if rebuilt else geom


def _compute_frontline(control_fc: dict, ukraine_boundary,
                        overrides: list[dict] | None = None,
                        source_mass=None, barrier=None) -> tuple[dict, dict]:
    """Возвращает (frontline_geojson, control_fill_geojson). overrides — см.
    load_manual_overrides(): пункты, взятие которых подтверждают МО РФ/Рыбарь
    раньше, чем это отразилось в живом слое ISW. Все они вливаются в
    ru_control «крышкой» (_absorb_overrides — пункт закрывает обращённый к нему
    участок фронта целиком, всё режется по контуру Украины) ДО сглаживания,
    поэтому получают то же morphological smoothing, что основной полигон, и не
    торчат ни островом, ни шипом.
    source_mass — фронт-источник (контроль + российские приграничные области),
    см. _absorb_overrides."""
    from shapely.geometry import mapping, shape, LineString, MultiLineString
    from shapely.ops import unary_union, linemerge

    ru_polys = [shape(f["geometry"]).buffer(0) for f in control_fc.get("features", [])
                if f.get("geometry")]
    if not ru_polys:
        raise ValueError("ISW control layer вернул 0 полигонов — не с чем считать линию")

    ukraine_boundary = ukraine_boundary.buffer(0)
    isw_mass = unary_union(ru_polys).buffer(0)
    ru_control = _absorb_overrides(isw_mass, overrides or [], source_mass=source_mass,
                                    ukraine_boundary=ukraine_boundary, barrier=barrier)
    ru_control = _smooth_polygon(ru_control)
    # сглаживание могло чуть выйти за границу и оставить «котлы» от смыкания крышек
    ru_control = _fill_new_holes(ru_control.intersection(ukraine_boundary).buffer(0), isw_mass)

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
    """Один прогон: тянет ISW, пересчитывает линию, апсертит geo_frontline_sync
    (последнее успешное состояние — быстрая отдача текущей карты) И
    geo_frontline_snapshot (одна запись на сегодняшний день — накопление
    истории для будущего временного ползунка, см. модель). Честная
    деградация — при любой ошибке пишет status=error с причиной, НЕ трогает
    ранее сохранённую рабочую линию (эндпоинт продолжит отдавать последнюю
    успешную)."""
    from app.models.geo import GeoFrontlineSync, GeoFrontlineSnapshot

    row = db.query(GeoFrontlineSync).filter_by(theater="svo").first()
    if row is None:
        row = GeoFrontlineSync(theater="svo", status="ok")
        db.add(row)

    try:
        control_fc, as_of = _fetch_control_polygons()
        ukraine_boundary, _static_map = _ukraine_boundary_from_static_map()
        # Масса фактического ISW-контроля — для правила «взятие только рядом с
        # фронтом» в absorb_candidates (защита от тёзок-деревень при геокодинге).
        from shapely.geometry import shape as _shape
        from shapely.ops import unary_union as _uu
        isw_mass = _uu([_shape(f["geometry"]).buffer(0)
                        for f in control_fc.get("features", []) if f.get("geometry")])
        # Фронт-источник = контроль внутри Украины ПЛЮС российские приграничные
        # области: захват в приграничье приходит оттуда, и «рядом с фронтом» для
        # такого пункта считается от границы, а не от далёкой массы внутри
        # Украины (иначе законные взятия под Волчанском отбрасывались правилом
        # 25 км и повисали без связи с тем, откуда шло продвижение).
        ru_border_land = _load_ru_border_land(ukraine_boundary)
        source_mass = _uu([isw_mass, ru_border_land]) if ru_border_land is not None else isw_mass
        barrier = load_barriers()
        overrides = absorb_candidates(ukraine_boundary, db=db, control_mass=isw_mass,
                                      border_mass=ru_border_land, barrier=barrier)
        frontline_fc, control_fill_fc = _compute_frontline(
            control_fc, ukraine_boundary, overrides=overrides, source_mass=source_mass, barrier=barrier)
        if not frontline_fc["features"]:
            raise ValueError("Пересчитанная линия фронта пуста")

        row.frontline_geojson = frontline_fc
        row.control_fill_geojson = control_fill_fc
        # Ярус «оспаривается» упразднён владельцем (2026-07-25) — оранжевой
        # штриховки больше нет, расхождение с ISW показывается кружком-маркером.
        row.contested_zone_geojson = None
        row.as_of = as_of
        row.source = "ISW Assessed Control of Terrain in Ukraine (CC BY)"
        row.status = "ok"
        row.error_note = None

        # Площадь ЧИСТОЙ ISW-массы (клип по Украине + заделка дыр) — для ряда
        # площадей истории по единой методике (см. докстринг
        # _isochrone_from_real_history: без этого дельта последнего месяца
        # мерила шов методик, а не движение фронта). Считается ДО изохроны и
        # вне её try: она же уходит в дневной снапшот, и падение побочной
        # изохроны не должно оставлять снапшот без площади (раньше это дало бы
        # ещё и NameError на записи снапшота).
        try:
            from app.services.geo_svo_capture_isochrone import (
                _spherical_km2, _fill_holes_and_drop_islands)
            pure_isw_area = round(_spherical_km2(_fill_holes_and_drop_islands(
                isw_mass.intersection(ukraine_boundary).buffer(0))))
        except Exception:  # noqa: BLE001
            pure_isw_area = None

        # Площадь «по данным МО РФ/Рыбаря» — та же ISW-масса ПЛЮС клинья
        # заявленных пунктов (ровно то, что закрашено на карте), той же
        # методикой измерения. Это основной ряд «км²/мес» (владелец,
        # 2026-09-12: темпы считать по нашей заливке, ISW — внешняя сверка);
        # разница с pure_isw_area = сколько заявлено сверх подтверждённого.
        try:
            from app.services.geo_svo_capture_isochrone import reported_addition_km2
            reported_area = (None if pure_isw_area is None else pure_isw_area + reported_addition_km2(
                isw_mass, overrides, source_mass, ukraine_boundary, barrier=barrier)[0])
        except Exception:  # noqa: BLE001
            logger.warning("Площадь по данным МО РФ/Рыбаря не посчитана", exc_info=True)
            reported_area = None

        # Изохрона «когда взято» — пересчитывается на каждом синке (дёшево,
        # чистая геометрия без сети), т.к. зависит от СВЕЖЕЙ формы
        # control_fill_fc; список дат меняется редко (см. модуль). Честная
        # деградация — при отсутствии исходных данных/сбое просто не
        # обновляем поле, не роняем весь синк линии из-за побочной фичи.
        try:
            from app.services.geo_svo_capture_isochrone import compute_isochrone
            row.capture_isochrone_geojson = compute_isochrone(
                control_fill_fc, ukraine_boundary=ukraine_boundary,
                isw_area_km2=pure_isw_area, reported_area_km2=reported_area,
                reported_points=len(overrides), db=db)
        except Exception as e:  # noqa: BLE001
            logger.warning("Изохрона СВО: пересчёт не удался (не блокирует синк линии): %s", e)

        today = datetime.now(timezone.utc).date().isoformat()
        snap = db.query(GeoFrontlineSnapshot).filter_by(theater="svo", snapshot_date=today).first()
        if snap is None:
            snap = GeoFrontlineSnapshot(theater="svo", snapshot_date=today)
            db.add(snap)
        snap.frontline_geojson = frontline_fc
        snap.control_fill_geojson = control_fill_fc
        snap.as_of = as_of
        # Чистая ISW-площадь на сегодня — единая методика с архивными месяцами.
        # Из неё изохрона строит месяцы, до которых архивный таймлапс ISW ещё не
        # дошёл (см. модель GeoFrontlineSnapshot и _months_from_own_snapshots).
        snap.isw_area_km2 = pure_isw_area
        # Площадь заливки по данным МО РФ/Рыбаря на сегодня — из неё «мост»
        # берёт основной ряд за месяцы, до которых архив ISW ещё не дошёл.
        snap.reported_area_km2 = reported_area

        db.commit()
        logger.info("ISW-синк линии фронта: %d сегментов линии, %d полигонов заливки, as_of=%s, снапшот=%s",
                     len(frontline_fc["features"]), len(control_fill_fc["features"]), as_of, today)
        return {"status": "ok", "segments": len(frontline_fc["features"]),
                "fill_polygons": len(control_fill_fc["features"]), "as_of": as_of, "snapshot_date": today}
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
