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
