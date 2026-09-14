"""Заливка карты СВО не должна закрашивать город, которого никто не заявлял.

Боевой дефект (2026-09-11, владелец: «город Орехов не взят (вроде)»): сводка
МО РФ о взятии Новопавловки Запорожской области приехала из ленты с координатами
47.5677/35.7849 — это центр ОРЕХОВА (0,5 км). Буфер кандидата 3 км плюс
морфологическое смыкание закрасили город целиком, хотя ни один источник его не
заявлял и ISW его контроль не подтверждает.

Два правила, обратные друг другу по риску, поэтому проверяются вместе:
  * «чужая координата» — кандидат в черте незаявленного города отбрасывается;
  * «щит города» — добавленная смыканием площадь не накрывает такой город.
И контрольная сторона: город, заявленный ПО ИМЕНИ (решение владельца красить
Купянск/Покровск по данным МО РФ), закрашиваться обязан — иначе защита от
ложного захвата превратится в отмену осознанного выбора.
"""
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from app.services import geo_isw_frontline_sync as sync


OREKHOV = (35.7897, 47.5686)      # координаты из конфига защищённых городов
NEAR_OREKHOV_CLAIM = (35.7849, 47.5677)   # ровно тот геокод, что пришёл из ленты


def _isw_south_of(lon: float, lat: float):
    """Масса «контроля ISW» ЮЖНЕЕ города: край проходит примерно в 9 км от него.
    Расстановка не случайная — при кандидате севернее города смыкание идёт через
    городскую черту, и без щита город закрашивается (проверено: старая формула
    накрывает его при любом зазоре 0,06-0,15°). На произвольной геометрии тест
    был бы зелёным и без защиты, то есть не доказывал бы ничего."""
    return Point(lon, lat - 0.30).buffer(0.22)


def _old_absorb(isw, overrides):
    """Формула ДО фикса — нужна, чтобы тест доказывал разницу, а не совпадение."""
    circles = [sync._point_buffer_km(o["lat"], o["lon"], o.get("radius_km", 3)) for o in overrides]
    combined = unary_union([isw] + circles).buffer(0)
    closed = (combined.buffer(sync._ABSORB_CLOSE_DEG, join_style=1)
                      .buffer(-sync._ABSORB_CLOSE_DEG, join_style=1))
    local = unary_union([Point(o["lon"], o["lat"]).buffer(sync._ABSORB_LOCAL_DEG) for o in overrides])
    return unary_union([combined, closed.difference(combined).intersection(local)]).buffer(0)


def test_кандидат_севший_в_черте_чужого_города_отбрасывается(monkeypatch, tmp_path):
    cities, radius = sync._load_protected_cities()
    assert cities, "конфиг защищённых городов не прочитан — правило не работает вовсе"
    orekhov = next(c for c in cities if c["name"] == "Орехов")
    d_km = (Point(*NEAR_OREKHOV_CLAIM).distance(Point(orekhov["lon"], orekhov["lat"]))
            * sync._KM_PER_DEG_LAT)
    assert d_km <= radius, "тестовая координата обязана лежать в черте города"

    # Ровно тот вход, что пришёл с боя: заявлено село, координата — центр города.
    monkeypatch.setattr(sync, "load_manual_overrides", lambda: [
        {"name": "Новопавловка", "oblast": "Запорожская область",
         "lat": NEAR_OREKHOV_CLAIM[1], "lon": NEAR_OREKHOV_CLAIM[0], "radius_km": 3},
        {"name": "Орехов", "oblast": "Запорожская область",
         "lat": orekhov["lat"], "lon": orekhov["lon"], "radius_km": 3},
    ])
    monkeypatch.setattr(sync, "_TIMELINE_PATH", str(tmp_path / "нет.json"))
    monkeypatch.setattr(sync, "_CLAIMED_PATH", str(tmp_path / "нет2.json"))
    monkeypatch.setattr(sync, "_load_oblast_shapes", lambda: [])

    names = [c["name"] for c in sync.absorb_candidates(db=None, control_mass=None)]
    assert "Новопавловка" not in names, "заявление с чужой координатой прошло в заливку"
    assert "Орехов" in names, "заявление про сам город отброшено вместе с ошибочным"


def test_имя_города_сверяется_с_алиасами_и_скобками():
    cities, _ = sync._load_protected_cities()
    orekhov = next(c for c in cities if c["name"] == "Орехов")
    pokrovsk = next(c for c in cities if c["name"] == "Покровск")
    kupiansk = next(c for c in cities if c["name"] == "Купянск")
    assert not sync._city_name_matches("Новопавловка", orekhov)
    assert sync._city_name_matches("Орехов", orekhov)
    # Второе имя в скобках — тоже заявка на этот город, иначе законный оверрайд
    # владельца («Красноармейск (Покровск)») отвергался бы как ошибка геокодинга.
    assert sync._city_name_matches("Красноармейск (Покровск)", pokrovsk)
    assert sync._city_name_matches("Pokrovsk", pokrovsk)
    # А сосед с похожим именем заявкой на город НЕ является.
    assert not sync._city_name_matches("Купянск-Узловой", kupiansk)


def test_смыкание_не_накрывает_незаявленный_город():
    lon, lat = OREKHOV
    isw = _isw_south_of(lon, lat)
    # Кандидат — село ЗА городом (законное заявление, но НЕ про город).
    village = {"name": "Новоданиловка", "oblast": "Запорожская область",
               "lat": lat + 0.08, "lon": lon, "radius_km": 3}

    assert _old_absorb(isw, [village]).contains(Point(lon, lat)), (
        "сценарий не воспроизводит дефект — тест ничего не доказывал бы")

    filled = sync._absorb_overrides(isw, [village])
    assert not filled.contains(Point(lon, lat)), (
        "город, которого никто не заявлял, закрашен смыканием — вернулся дефект Орехова")
    # Само заявленное село закрашено быть обязано, иначе защита съела бы факт.
    assert filled.contains(Point(village["lon"], village["lat"]))


def test_город_заявленный_по_имени_закрашивается():
    lon, lat = OREKHOV
    isw = _isw_south_of(lon, lat)
    overrides = [{"name": "Орехов", "oblast": "Запорожская область",
                  "lat": lat, "lon": lon, "radius_km": 3}]
    filled = sync._absorb_overrides(isw, overrides)
    assert filled.contains(Point(lon, lat)), (
        "город, заявленный по имени, не закрашен — защита отменила осознанный выбор")


def test_щит_не_режет_то_что_контролирует_сам_ISW():
    """Осторожность не спорит с источником: если ISW считает город взятым,
    заливка обязана его показать даже без единого заявления."""
    lon, lat = OREKHOV
    isw = Point(lon, lat).buffer(0.3)   # ISW накрывает город целиком
    filled = sync._absorb_overrides(isw, [{"name": "Новоданиловка", "oblast": "Запорожская область",
                                           "lat": lat + 0.05, "lon": lon - 0.05, "radius_km": 3}])
    assert filled.contains(Point(lon, lat))


def test_присоединение_идёт_только_со_стороны_фронта():
    """Владелец (2026-09-12): «соединяешь с тем куском фронта, откуда шёл
    захват; ты не берёшь и полностью со всех сторон присобачиваешь».

    Проверяем буквально: территория ЗА взятым пунктом (по ту сторону от фронта)
    остаться незакрашенной обязана — именно из этого рождается форма фронта
    (клинья, охваты), которую круговое смыкание стирало в сплошное пятно."""
    lon, lat = OREKHOV
    isw = _isw_south_of(lon, lat)          # фронт ЮЖНЕЕ
    village = {"name": "Новоданиловка", "oblast": "Запорожская область",
               "lat": lat + 0.08, "lon": lon, "radius_km": 3}

    filled = sync._absorb_overrides(isw, [village])
    old = _old_absorb(isw, [village])
    behind = Point(village["lon"], village["lat"] + 0.12)   # ~13 км ЗА пунктом
    # Точка СБОКУ от линии «пункт → фронт»: круговое смыкание её захватывало
    # дугой, направленный клин — нет. Координаты взяты из замера разницы двух
    # формул, чтобы тест доказывал расхождение, а не совпадение.
    aside = Point(35.8904, 47.4653)

    assert filled.contains(Point(village["lon"], village["lat"])), "сам взятый пункт не закрашен"
    assert not filled.contains(behind), "закрашена территория ЗА пунктом — присоединение всенаправленное"
    assert not filled.contains(aside), "закрашена территория сбоку от линии присоединения"
    assert old.contains(aside), "сценарий не воспроизводит прежнее поведение — тест ничего не доказывал бы"


def test_приграничный_пункт_привязывается_к_территории_РФ():
    """Без плацдарма приграничные взятия не к чему привязать: наступление идёт
    с территории России, а масса контроля внутри Украины далеко — пункт повисал
    островом «линия не сдвинулась»."""
    from shapely.geometry import box

    # Фронт-источник: далёкая масса внутри Украины + «российская область» сверху.
    far_mass = Point(36.9, 49.0).buffer(0.2)
    ru_land = box(36.0, 50.35, 38.0, 51.0)          # севернее приграничного пункта
    source = unary_union([far_mass, ru_land])
    vovchansk = {"name": "Волчанск", "oblast": "Харьковская область",
                 "lat": 50.2897, "lon": 36.9469, "radius_km": 3}

    filled = sync._absorb_overrides(far_mass, [vovchansk], source_mass=source)
    # Клин обязан дотянуться до плацдарма, а не висеть кружком у пункта.
    assert filled.intersects(ru_land), "приграничное взятие не связано с территорией, откуда шло продвижение"
    # И при этом НЕ дотянуться до далёкой массы внутри Украины — между ними
    # остаётся незакрашенное пространство, то есть форма фронта сохраняется.
    assert not filled.contains(Point(36.95, 49.7))


# ---- «крышка» (2026-09-14): карман закрывается целиком, в Россию не заходим ----

def _front_square():
    """Масса контроля — квадрат lon 37–38, lat 48–48.5; фронт — его северный край lat=48.5."""
    from shapely.geometry import box
    return box(37.0, 48.0, 38.0, 48.5)


def test_крышка_закрывает_карман_по_всей_ширине_фронта_напротив_пункта():
    """Владелец (2026-09-14): «восточнее Константиновки точно взято, а не закрашено».
    Село в 6 км перед прямым фронтом обязано присоединиться ПОЛОСОЙ, а не иглой:
    заливка касается фронта на ширине, кратной размеру самого села, и закрывает
    карман по обе стороны от линии «пункт — ближайшая точка»."""
    isw = _front_square()
    village = {"name": "Тестовое", "oblast": "Донецкая область", "lat": 48.5 + 6 / 111.0, "lon": 37.5, "radius_km": 3}
    filled = sync._absorb_overrides(isw, [village])
    addition = filled.difference(isw)
    # точки в кармане по обе стороны от прямой к якорю, на 3 км от фронта и 4 км в сторону
    left = Point(37.5 - 4 / 111.0, 48.5 + 3 / 111.0)
    right = Point(37.5 + 4 / 111.0, 48.5 + 3 / 111.0)
    assert addition.contains(left) and addition.contains(right), "карман рядом с пунктом не закрыт"
    # а за пунктом (дальше от фронта) территория не добавляется
    behind = Point(37.5, 48.5 + 12 / 111.0)
    assert not addition.contains(behind), "закрашено ЗА пунктом, куда фронт не доходил"
    # ширина касания фронта — не игла: пересечение добавления с линией фронта ≥ 8 км
    from shapely.geometry import LineString
    touch = addition.buffer(1e-6).intersection(LineString([(37.0, 48.5), (38.0, 48.5)]))
    assert touch.length * sync._KM_PER_DEG_LAT >= 8.0


def test_заливка_не_заходит_на_территорию_России():
    """Наступление с российской территории: плацдарм — прямоугольник СЕВЕРНЕЕ
    границы lat=50.3, Украина — южнее. Село в 4 км южнее границы присоединяется к
    плацдарму, но красным становится ТОЛЬКО украинская сторона (владелец,
    2026-09-14: «кругляшки заходят на территорию России»)."""
    from shapely.geometry import box
    ukraine = box(36.0, 49.0, 38.0, 50.3)
    ru_land = box(36.0, 50.3, 38.0, 51.0)
    far_isw = box(37.6, 49.0, 38.0, 49.4)  # масса контроля далеко на юге
    source = far_isw.union(ru_land)
    # село в 2 км от границы: его собственный кружок (3 км) без обрезки лёг бы в Россию
    village = {"name": "Приграничное", "oblast": "Харьковская область", "lat": 50.3 - 2 / 111.0, "lon": 37.0, "radius_km": 3}
    filled = sync._absorb_overrides(far_isw, [village], source_mass=source, ukraine_boundary=ukraine)
    addition = filled.difference(far_isw)
    assert addition.contains(Point(37.0, 50.3 - 1.5 / 111.0)), "село не связано с границей"
    assert addition.intersection(ru_land).area < 1e-9, "заливка зашла на территорию России"
    # и без контура Украины кружок/крышка легли бы за границу — контроль, что тест что-то проверяет
    unclipped = sync._absorb_overrides(far_isw, [village], source_mass=source).difference(far_isw)
    assert unclipped.intersection(ru_land).area > 0


def test_цепочка_сёл_опирается_на_уже_присоединённое_а_не_тянется_к_массе():
    """Два села по одной линии от фронта: 5 км и 11 км. Дальнее обязано
    присоединиться к ближнему (полоса продолжается), а не отдельной «сосиской»
    от самой массы — площадь добавления при цепочке меньше, чем у двух
    независимых клиньев к массе."""
    isw = _front_square()
    near = {"name": "Ближнее", "oblast": "Донецкая область", "lat": 48.5 + 5 / 111.0, "lon": 37.5, "radius_km": 3}
    far = {"name": "Дальнее", "oblast": "Донецкая область", "lat": 48.5 + 11 / 111.0, "lon": 37.5, "radius_km": 3}
    chained = sync._absorb_overrides(isw, [near, far]).difference(isw)
    assert chained.contains(Point(37.5, 48.5 + 8 / 111.0)), "между сёлами разрыв"
    # каждое по отдельности — сумма шире, чем цепочка (дальнее тянулось бы к массе широким окном)
    separate = sync._absorb_overrides(isw, [near]).difference(isw).union(sync._absorb_overrides(isw, [far]).difference(isw))
    assert chained.area < separate.area


# ---- 2026-09-14, вторая волна: река-барьер, порог у границы, «котлы» ----------

def test_пункт_на_другом_берегу_реки_не_присоединяется_и_крышка_не_переходит_реку():
    """Владелец: «взятая деревушка севернее Днепра, куда ВС РФ не заходят — ни одна
    сторона там не форсирует». Река — вертикальная линия lon=35.0; масса контроля
    восточнее, пункт в 6 км западнее реки."""
    from shapely.geometry import box, LineString
    river = LineString([(35.0, 46.0), (35.0, 49.0)])
    isw = box(35.05, 47.0, 36.0, 48.0)
    west = {"name": "Заречное", "oblast": "Запорожская область", "lat": 47.5, "lon": 35.0 - 6 / 111.0, "radius_km": 3, "src": "db"}
    east = {"name": "Береговое", "oblast": "Запорожская область", "lat": 47.5, "lon": 35.05 - 4 / 111.0, "radius_km": 3, "src": "db"}
    kept = sync.validate_candidates([west, east], isw, barrier=river, quiet=True)
    assert [c["name"] for c in kept] == ["Береговое"], "пункт за рекой прошёл проверку"
    # и даже если бы прошёл — крышка не пересекает русло
    filled = sync._absorb_overrides(isw, [west, east], barrier=river)
    addition = filled.difference(isw)
    assert not addition.intersects(river.buffer(0.5 / 111.0)), "заливка легла на русло / другой берег"


def test_приграничный_пункт_принимается_только_у_самой_границы():
    """Порог 25 км от «плацдарма» пропускал тёзок под Харьковом (владелец: «взятый
    населённый пункт практически рядом с Харьковом»). От территории РФ — 12 км."""
    from shapely.geometry import box
    isw = box(37.6, 49.0, 38.0, 49.4)          # масса контроля далеко
    ru_land = box(36.0, 50.3, 38.0, 51.0)      # плацдарм — Россия севернее lat 50.3
    near_border = {"name": "Гоптовка", "oblast": "Харьковская область", "lat": 50.3 - 3 / 111.0, "lon": 36.3, "radius_km": 3, "src": "override"}
    suburb = {"name": "Циркуны", "oblast": "Харьковская область", "lat": 50.3 - 20 / 111.0, "lon": 36.3, "radius_km": 3, "src": "override"}
    kept = sync.validate_candidates([near_border, suburb], isw, border_mass=ru_land, quiet=True)
    assert [c["name"] for c in kept] == ["Гоптовка"]


def test_котлы_от_смыкания_крышек_заделываются_а_дыры_ISW_остаются():
    from shapely.geometry import box, Polygon
    # масса ISW с собственной дырой (реальный очаг) — остаётся
    isw = Polygon(box(37.0, 48.0, 38.0, 48.5).exterior.coords, [list(box(37.4, 48.2, 37.5, 48.3).exterior.coords)])
    # два села по бокам незанятого поля перед фронтом — их крышки смыкаются и
    # оставляют внутри белый «котёл»
    left = {"name": "Левое", "oblast": "Донецкая область", "lat": 48.5 + 7 / 111.0, "lon": 37.30, "radius_km": 3}
    right = {"name": "Правое", "oblast": "Донецкая область", "lat": 48.5 + 7 / 111.0, "lon": 37.60, "radius_km": 3}
    top = {"name": "Верхнее", "oblast": "Донецкая область", "lat": 48.5 + 14 / 111.0, "lon": 37.45, "radius_km": 3}
    merged = sync._absorb_overrides(isw, [left, right, top])
    holes_before = sum(len(g.interiors) for g in (merged.geoms if hasattr(merged, "geoms") else [merged]))
    fixed = sync._fill_new_holes(merged, isw)
    holes_after = [Polygon(r) for g in (fixed.geoms if hasattr(fixed, "geoms") else [fixed]) for r in g.interiors]
    assert len(holes_after) == 1, f"ожидалась одна (ISW-шная) дыра, осталось {len(holes_after)} из {holes_before}"
    assert holes_after[0].intersects(box(37.4, 48.2, 37.5, 48.3)), "заделали дыру самого ISW"


def test_цепочка_сёл_от_границы_принимается_а_одиночка_в_тылу_нет():
    """Волчанск → Белый Колодец → Бакшеевка: каждое следующее село в 6 км от
    предыдущего, последнее — в 17 км от границы. Цепочка принимается; одиночное
    село в 17 км от границы без соседей — нет."""
    from shapely.geometry import box
    isw = box(37.6, 49.0, 38.0, 49.4)
    ru_land = box(36.0, 50.3, 38.0, 51.0)
    chain = [
        {"name": "Первое", "oblast": "Харьковская область", "lat": 50.3 - 5 / 111.0, "lon": 37.0, "radius_km": 3, "src": "override"},
        {"name": "Второе", "oblast": "Харьковская область", "lat": 50.3 - 11 / 111.0, "lon": 37.0, "radius_km": 3, "src": "override"},
        {"name": "Третье", "oblast": "Харьковская область", "lat": 50.3 - 17 / 111.0, "lon": 37.0, "radius_km": 3, "src": "override"},
    ]
    lone = {"name": "Одиночка", "oblast": "Харьковская область", "lat": 50.3 - 17 / 111.0, "lon": 37.5, "radius_km": 3, "src": "override"}
    kept = sync.validate_candidates(chain + [lone], isw, border_mass=ru_land, quiet=True)
    assert [c["name"] for c in kept] == ["Первое", "Второе", "Третье"]
