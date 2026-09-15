"""Основной ряд «км²/мес» — по данным МО РФ/Рыбаря, восстановленный НА КОНЕЦ
КАЖДОГО МЕСЯЦА по датам заявлений (владелец, 2026-09-12: «мы опираемся на данные
Минобороны и Рыбаря, ISW нужен как оценка извне»).

Что именно доказывается:
  * пункт входит в ряд с МЕСЯЦА ЗАЯВЛЕНИЯ, а не с момента попадания в наш
    список — иначе ряд растёт от пополнения списка, а не от движения фронта
    (замерено на бою: +2653 км² за август против ~150 км²/мес по ISW);
  * пункт, который ISW и так подтверждает (внутри массы), ничего не добавляет;
  * ISW остаётся отдельным рядом: reported_over_isw = заявлено сверх ISW;
  * у ручных оверрайдов обязана быть дата — иначе они считались бы взятыми с
    первого месяца ряда (тест на конфиг).
Без сети и без БД: свой архив, свои кандидаты.
"""
import json
from datetime import date

import pytest
from shapely.geometry import Point, shape

from app.services import geo_isw_frontline_sync as sync
from app.services import geo_svo_capture_isochrone as iso


def _sq(lon: float, lat: float, side: float = 1.0) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + side, lat], [lon + side, lat + side], [lon, lat + side], [lon, lat],
    ]]}


def _prev_month(month: str, back: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    for _ in range(back):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{y}-{m:02d}"


def _archive_month(month: str, area: int) -> dict:
    end = iso._month_end(*map(int, month.split("-")))
    return {"month": month, "month_end": end, "snapshot_date": end,
            "area_km2": area, "geometry": _sq(35.0, 47.0)}


def _fc(features):
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": g} for g in features]}


def _by_month(result):
    return {f["properties"]["month"]: f["properties"] for f in result["features"]}


# Квадрат ISW: lon 35–36, lat 47–48. Пункт в 6 км восточнее восточного края —
# «рядом с фронтом», вне массы, клин к краю добавит площадь.
OUTSIDE = {"name": "Тестовое", "oblast": None, "lat": 47.5, "lon": 36.0 + 6 / 111.0, "radius_km": 3}
INSIDE = {"name": "Внутреннее", "oblast": None, "lat": 47.5, "lon": 35.5, "radius_km": 3}


@pytest.fixture()
def archive(tmp_path, monkeypatch):
    """Три закрытых месяца подряд с одинаковой ISW-площадью (фронт по ISW стоит)."""
    cur = date.today().isoformat()[:7]
    m3, m2, m1 = _prev_month(cur, 3), _prev_month(cur, 2), _prev_month(cur, 1)
    months = [_archive_month(m3, 100_000), _archive_month(m2, 100_000), _archive_month(m1, 100_000)]
    path = tmp_path / "real_history.json"
    path.write_text(json.dumps({"months": months}), encoding="utf-8")
    monkeypatch.setattr(iso, "_REAL_HISTORY_PATH", str(path))
    monkeypatch.setattr(iso, "_load_timeline_points", lambda: [])
    monkeypatch.setattr(iso, "_DETECT_ARCHIVE_COPIES", False)  # плоский фронт в заготовке — не копия
    # Проверки области/города — на реальных конфигах, но тестовые координаты
    # лежат вне любых защищённых городов; область не заявлена → правило 1 молчит.
    return {"cur": cur, "m3": m3, "m2": m2, "m1": m1}


def _run(monkeypatch, cands, **kw):
    monkeypatch.setattr(sync, "dated_candidates", lambda *a, **k: cands)
    monkeypatch.setattr(sync, "_load_ru_border_land", lambda *a, **k: None)
    return _by_month(iso._isochrone_from_real_history(
        _fc([_sq(35.0, 47.0)]), isw_area_km2=100_000, reported_area_km2=kw.get("live", 100_000),
        db=None, ukraine_boundary=shape(_sq(30.0, 44.0, 10.0))))


def test_пункт_входит_с_месяца_заявления_а_не_с_попадания_в_список(archive, monkeypatch):
    m2_end = iso._month_end(*map(int, archive["m2"].split("-")))
    props = _run(monkeypatch, [{**OUTSIDE, "date": m2_end}])

    before, month_of, after = props[archive["m3"]], props[archive["m2"]], props[archive["m1"]]
    # До заявления — наш ряд равен ISW.
    assert before["reported_area_km2"] == before["area_km2"] == 100_000
    assert before["reported_over_isw_km2"] == 0
    # В месяц заявления площадь по МО РФ/Рыбарю выросла, ISW — нет.
    assert month_of["reported_over_isw_km2"] > 0
    assert month_of["reported_delta_km2"] == month_of["reported_over_isw_km2"]
    assert month_of["delta_km2"] == 0, "ISW-ряд не должен реагировать на заявление"
    assert month_of["reported_points"] == 1
    # В следующем месяце пункт всё ещё в заливке, но нового прироста не даёт.
    assert after["reported_area_km2"] == month_of["reported_area_km2"]
    assert after["reported_delta_km2"] == 0


def test_заявление_после_конца_месяца_в_этот_месяц_не_попадает(archive, monkeypatch):
    m1_end = iso._month_end(*map(int, archive["m1"].split("-")))
    props = _run(monkeypatch, [{**OUTSIDE, "date": m1_end}])
    assert props[archive["m2"]]["reported_over_isw_km2"] == 0
    assert props[archive["m1"]]["reported_over_isw_km2"] > 0


def test_пункт_внутри_массы_ISW_ничего_не_добавляет(archive, monkeypatch):
    m3_end = iso._month_end(*map(int, archive["m3"].split("-")))
    props = _run(monkeypatch, [{**INSIDE, "date": m3_end}])
    for m in (archive["m3"], archive["m2"], archive["m1"]):
        assert props[m]["reported_over_isw_km2"] == 0
        assert props[m].get("reported_points", 0) == 0


def test_хронология_с_откатом_убирает_пункт_из_ряда(archive, monkeypatch):
    m3_end = iso._month_end(*map(int, archive["m3"].split("-")))
    m2_end = iso._month_end(*map(int, archive["m2"].split("-")))
    props = _run(monkeypatch, [{**OUTSIDE, "transitions": [(m3_end, "RF"), (m2_end, "UA")]}])
    assert props[archive["m3"]]["reported_over_isw_km2"] > 0
    assert props[archive["m2"]]["reported_over_isw_km2"] == 0
    assert props[archive["m2"]]["reported_delta_km2"] < 0, "отступ обязан дать отрицательную дельту"


def test_геометрия_месяца_включает_клин_заявленного_пункта(archive, monkeypatch):
    m2_end = iso._month_end(*map(int, archive["m2"].split("-")))
    monkeypatch.setattr(sync, "dated_candidates", lambda *a, **k: [{**OUTSIDE, "date": m2_end}])
    monkeypatch.setattr(sync, "_load_ru_border_land", lambda *a, **k: None)
    res = iso._isochrone_from_real_history(
        _fc([_sq(35.0, 47.0)]), isw_area_km2=100_000, reported_area_km2=100_000,
        db=None, ukraine_boundary=shape(_sq(30.0, 44.0, 10.0)))
    geoms = {f["properties"]["month"]: shape(f["geometry"]) for f in res["features"]}
    p = Point(OUTSIDE["lon"], OUTSIDE["lat"])
    assert not geoms[archive["m3"]].contains(p), "до заявления пункт не в заливке"
    assert geoms[archive["m2"]].contains(p), "ползунок на месяц заявления обязан показать пункт взятым"


def test_живой_месяц_берёт_площадь_по_МО_от_синка(archive, monkeypatch):
    props = _run(monkeypatch, [], live=100_450)
    cur = props[archive["cur"]]
    assert cur["reported_area_km2"] == 100_450
    assert cur["reported_delta_km2"] == 450
    assert cur["reported_over_isw_km2"] == 450


def test_у_всех_ручных_оверрайдов_есть_дата_заявления():
    """Без даты оверрайд считался бы взятым с первого месяца ряда (см.
    _holder_as_of) — ряд «по МО РФ/Рыбарю» за 2022 год получил бы Покровск."""
    for o in sync.load_manual_overrides():
        assert o.get("claimed_date"), f"у оверрайда «{o.get('name')}» нет claimed_date"


def test_живая_заливка_и_реконструкция_идут_одной_цепочкой(monkeypatch):
    """absorb_candidates = dated_candidates → отбор на сегодня → validate_candidates.
    Если цепочки разойдутся, «сегодня» и «конец прошлого месяца» будут считаться по
    разным правилам, и дельта текущего месяца измерит разницу правил."""
    calls = []
    monkeypatch.setattr(sync, "dated_candidates", lambda *a, **k: [{**OUTSIDE, "date": "2026-01-01"},
                                                                     {**OUTSIDE, "date": "2099-01-01", "name": "Будущее"}])
    monkeypatch.setattr(sync, "validate_candidates", lambda out, cm, **k: (calls.append(list(out)) or out))
    got = sync.absorb_candidates(None, db=None, control_mass=None)
    assert [c["name"] for c in got] == ["Тестовое"], "заявление из будущего попало в живую заливку"
    assert calls and calls[0] == got
