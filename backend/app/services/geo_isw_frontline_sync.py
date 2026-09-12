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


def absorb_candidates(ukraine_boundary=None, db=None, control_mass=None) -> list[dict]:
    """ВСЕ пункты, которые по данным МО РФ/Рыбаря сейчас под контролем РФ, —
    из трёх источников сразу:
      1) geo_svo_manual_overrides.json — ручные оверрайды (с явным radius_km);
      2) geo_svo_control_timeline.json — пункты, чей ПОСЛЕДНИЙ переход = RF
         (сюда попадает, напр., Волчанск: МО заявляло освобождение в декабре
         2025, а живой слой ISW его не включает);
      3) geo_svo_claimed_captures.json — заявленные захваты.

    Владелец (2026-07-25): «у тебя немало кружочков с комментариями это под
    контролем России, но не подтверждено, но линия фронта не проходит через
    них, как будто под контролем Украины». То есть карта противоречила
    собственным подписям. Теперь источник один: если наши данные говорят
    «под РФ» — пункт и в красной зоне, и с кружком «ISW не подтвердил».

    Точки ВНЕ контура Украины отбрасываются (Суджа, Юнаковка и прочее
    приграничье РФ): слой описывает контроль внутри Украины, российская
    территория в него не входит по определению."""
    from shapely.geometry import Point

    seen: set[tuple] = set()
    out: list[dict] = []

    def add(name, oblast, lat, lon, radius_km):
        if lat is None or lon is None:
            return
        key = (round(lat, 3), round(lon, 3))
        if key in seen:
            return
        if ukraine_boundary is not None and not ukraine_boundary.contains(Point(lon, lat)):
            return
        seen.add(key)
        out.append({"name": name, "oblast": oblast, "lat": lat, "lon": lon,
                    "radius_km": radius_km})

    for o in load_manual_overrides():
        add(o.get("name"), o.get("oblast"), o.get("lat"), o.get("lon"), o.get("radius_km", 3))

    today = datetime.now(timezone.utc).date().isoformat()
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
                holder = None
                for t in sorted(e.get("transitions", []), key=lambda t: t["date"]):
                    if t["date"] <= today:
                        holder = t["holder"]
                if holder == "RF":
                    add(e.get("name"), e.get("oblast"), e.get("lat"), e.get("lon"), 3)
        else:
            for p in data.get("points", []):
                add(p.get("name"), p.get("oblast"), p.get("lat"), p.get("lon"), 3)

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
                add(r.settlement, r.oblast, r.lat, r.lon, 3)
        except Exception:  # noqa: BLE001 — живой источник не роняет синк
            logger.warning("absorb_candidates: territorial_claims из БД не подмешаны", exc_info=True)

    # --- ВАЛИДАЦИЯ КАНДИДАТОВ (владелец, 2026-07-26; см. _MAX_FRONT_DISTANCE_KM) ---
    from shapely.geometry import Point

    # Правило 1: координата обязана лежать в ЗАЯВЛЕННОЙ области — ловит тёзок,
    # геокоженных не туда («Благодатное» не той области и т.п.).
    try:
        oblasts = _load_oblast_shapes()
    except Exception:  # noqa: BLE001
        logger.warning("absorb_candidates: контуры областей не загрузились — проверка области пропущена")
        oblasts = []
    if oblasts:
        kept = []
        for o in out:
            stated = (o.get("oblast") or "").strip()
            region = next((g for w, g in oblasts if w and w in stated), None) if stated else None
            if region is not None and not region.contains(Point(o["lon"], o["lat"])):
                logger.warning("absorb_candidates: ОТКЛОНЁН «%s» — координата (%.3f, %.3f) не в "
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
                logger.warning("absorb_candidates: ОТКЛОНЁН «%s» — координата (%.4f, %.4f) в %.1f км "
                               "от центра города «%s», который никто не заявлял взятым "
                               "(ошибка геокодинга заявления)",
                               o["name"], o["lat"], o["lon"], hit[1], hit[0]["name"])
                continue
            kept.append(o)
        out = kept

    # Правило 2: пункт может быть «взят», только если он РЯДОМ С ФРОНТОМ —
    # не дальше _MAX_FRONT_DISTANCE_KM от фактической массы ISW-контроля.
    if control_mass is not None and not control_mass.is_empty:
        kept = []
        for o in out:
            d_km = control_mass.distance(Point(o["lon"], o["lat"])) * _KM_PER_DEG_LAT
            if d_km > _MAX_FRONT_DISTANCE_KM:
                logger.warning("absorb_candidates: ОТКЛОНЁН «%s» (%s) — %.0f км от линии фронта "
                               "(порог %.0f), взятие в глубине тыла неправдоподобно",
                               o["name"], o.get("oblast"), d_km, _MAX_FRONT_DISTANCE_KM)
                continue
            kept.append(o)
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
        if inside:
            logger.info("absorb_candidates: %d пунктов уже внутри линии ISW — в геометрию не идут (%s%s)",
                        len(inside), ", ".join(inside[:8]), "…" if len(inside) > 8 else "")
            out = [o for o in out if not control_mass.contains(Point(o["lon"], o["lat"]))]
    return out


def _point_buffer_km(lat: float, lon: float, radius_km: float):
    from shapely.geometry import Point
    deg = radius_km / _KM_PER_DEG_LAT
    return Point(lon, lat).buffer(deg)


# Параметры прежнего КРУГОВОГО смыкания (closing). Сама механика заменена
# направленным клином (см. _absorb_overrides, 2026-09-12), но константы
# оставлены: на них опирается тест, который сравнивает старое поведение с новым
# и тем доказывает, что фикс действительно что-то меняет.
_ABSORB_CLOSE_DEG = 0.20
_ABSORB_LOCAL_DEG = 0.50
# Клин присоединения: ширина у основания = доля от длины клина, но не больше
# потолка. 0.6 и 12 км подобраны на живых данных сентября-2026: связь с фронтом
# читается полосой (а не иглой, на которую владелец жаловался 2026-07-25), при
# этом лишняя площадь против прежнего кругового смыкания меньше на ~1.4 тыс. км².
_WEDGE_WIDTH_RATIO = 0.6
_WEDGE_MAX_WIDTH_KM = 12.0


def _absorb_overrides(ru_mass, overrides: list[dict], source_mass=None):
    """Вливает пункты-оверрайды в массив РФ-контроля — НАПРАВЛЕННО, со стороны,
    откуда шло продвижение.

    Владелец (2026-09-12): «ты же отрисовываешь взятые участки фронта /
    населённые пункты и соединяешь с тем куском фронта, откуда собственно шёл
    захват; ты не берёшь и полностью со всех сторон присобачиваешь, а откуда
    пришли исходно, и только если линия фронта продвинулась целиком — тогда
    целиком и присоединяешь цветом».

    Поэтому каждый взятый пункт связывается с БЛИЖАЙШЕЙ точкой фронта-источника
    клином: широкий у основания (там, откуда шли), сходящийся к пункту. Во все
    остальные стороны от пункта территория НЕ добавляется. Когда рядом взято
    несколько пунктов, их клинья сливаются сами — получается то самое сплошное
    продвижение широкой линией, но только там, где оно действительно заявлено.

    Что было раньше и почему заменено:
      1) голый Point.buffer() → изолированный остров в 7-17 км от массива
         (визуально «линия вообще не сдвинулась»);
      2) буферизованный отрезок-коридор (~2.6 км) → тонкий шип;
      3) морфологическое closing (dilate→erode, радиус ~22 км) → смыкало
         ШИРОКОЙ дугой во ВСЕ стороны: заодно закрашивало то, чего никто не
         заявлял (так стал красным Орехов), и спрямляло реальную форму фронта,
         из-за чего охваты и полукольца на карте исчезали.

    source_mass — «откуда мог прийти захват»: сам РФ-контроль ПЛЮС российские
    приграничные области. Без последних приграничные взятия (Волчанск, Казачья
    Лопань, Гоптовка) не к чему привязать: наступление там идёт с территории
    России, а масса контроля внутри Украины далеко, и пункт повисал островом.
    """
    from shapely.geometry import Point
    from shapely.ops import unary_union, nearest_points

    if not overrides:
        return ru_mass
    circles = [_point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3)) for o in overrides]
    combined = unary_union([ru_mass] + circles).buffer(0)
    source = source_mass if source_mass is not None and not source_mass.is_empty else ru_mass

    wedges = []
    for o in overrides:
        p = Point(o["lon"], o["lat"])
        if ru_mass.contains(p):
            continue  # уже внутри контроля — соединять не с чем
        try:
            anchor = nearest_points(source, p)[0]
        except Exception:  # noqa: BLE001 — один кривой кандидат не рушит слой
            continue
        gap_km = p.distance(anchor) * _KM_PER_DEG_LAT
        if gap_km <= 0.01:
            continue
        # Ширина у основания растёт с длиной клина (фронт двигается полосой, а
        # не иглой), но ограничена сверху: иначе один дальний пункт раздувал бы
        # присоединение на пол-области.
        base_km = min(max(o.get("radius_km", 3), _WEDGE_WIDTH_RATIO * gap_km), _WEDGE_MAX_WIDTH_KM)
        wedges.append(unary_union([
            _point_buffer_km(anchor.y, anchor.x, base_km),
            _point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3)),
        ]).convex_hull)

    addition = unary_union(wedges).difference(combined) if wedges else combined.difference(combined)

    # Смыкание идёт дугой в десятки километров и по дороге накрывает города,
    # которых никто не заявлял: так Орехов оказался красным из-за соседних сёл
    # (владелец, 2026-09-11). Вырезаем из ДОБАВЛЕНИЯ окрестности защищённых
    # городов, кроме тех, что заявлены по имени сами. Из массы ISW и из кругов
    # самих кандидатов не вырезаем ничего: если ISW считает город взятым — он
    # взят, наша осторожность не может спорить с источником.
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

    return unary_union([combined, addition]).buffer(0)


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


def _compute_frontline(control_fc: dict, ukraine_boundary,
                        overrides: list[dict] | None = None,
                        source_mass=None) -> tuple[dict, dict]:
    """Возвращает (frontline_geojson, control_fill_geojson). overrides — см.
    load_manual_overrides(): пункты, взятие которых подтверждают МО РФ/Рыбарь
    раньше, чем это отразилось в живом слое ISW. Все они вливаются в
    ru_control НАПРАВЛЕННО (_absorb_overrides — клин со стороны, откуда шло
    продвижение) ДО сглаживания, поэтому получают то же morphological
    smoothing, что основной полигон, и не торчат ни островом, ни шипом.
    source_mass — фронт-источник (контроль + российские приграничные области),
    см. _absorb_overrides."""
    from shapely.geometry import mapping, shape, LineString, MultiLineString
    from shapely.ops import unary_union, linemerge

    ru_polys = [shape(f["geometry"]).buffer(0) for f in control_fc.get("features", [])
                if f.get("geometry")]
    if not ru_polys:
        raise ValueError("ISW control layer вернул 0 полигонов — не с чем считать линию")

    ru_control = _absorb_overrides(unary_union(ru_polys).buffer(0), overrides or [],
                                    source_mass=source_mass)
    ru_control = _smooth_polygon(ru_control)
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
        overrides = absorb_candidates(ukraine_boundary, db=db, control_mass=source_mass)
        frontline_fc, control_fill_fc = _compute_frontline(
            control_fc, ukraine_boundary, overrides=overrides, source_mass=source_mass)
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

        # Изохрона «когда взято» — пересчитывается на каждом синке (дёшево,
        # чистая геометрия без сети), т.к. зависит от СВЕЖЕЙ формы
        # control_fill_fc; список дат меняется редко (см. модуль). Честная
        # деградация — при отсутствии исходных данных/сбое просто не
        # обновляем поле, не роняем весь синк линии из-за побочной фичи.
        try:
            from app.services.geo_svo_capture_isochrone import compute_isochrone
            row.capture_isochrone_geojson = compute_isochrone(
                control_fill_fc, ukraine_boundary=ukraine_boundary,
                isw_area_km2=pure_isw_area, db=db)
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
