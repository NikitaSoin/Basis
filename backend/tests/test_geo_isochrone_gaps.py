"""Помесячный ряд «км²/мес» карты СВО: пропуск не должен раздувать соседа.

Боевой дефект (2026-09-11): архивные таймлапсы ISW заморожены на июле, код
добавлял к архиву только «живой» текущий месяц — август из ряда ВЫПАДАЛ, а его
движение молча уходило в дельту сентября («+32 км² за месяц» вместо «+32 км² за
два месяца с июля»). Арифметика при этом верна, ошибочна АТРИБУЦИЯ к периоду —
такое не ловится ни проверкой суммы, ни зелёной сборкой, только тестом на форму
ряда. Тест без сети и без БД: подставляем свой файл архива.
"""
import json
from datetime import date

import pytest

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


def _archive_month(month: str, area: int, snapshot_from: str | None = None) -> dict:
    """Запись архива: снапшот из СВОЕГО месяца, либо (snapshot_from) скопирован
    из чужого — так в файле помечены месяцы, за которые таймлапса у ISW нет."""
    end = iso._month_end(*map(int, month.split("-")))
    src = snapshot_from or month
    return {"month": month, "month_end": end,
            "snapshot_date": iso._month_end(*map(int, src.split("-"))),
            "area_km2": area, "geometry": _sq(35.0, 47.0)}


@pytest.fixture()
def archive(tmp_path, monkeypatch):
    """Архив, кончающийся ПОЗАПРОШЛЫМ месяцем: ровно один пропуск между ним и
    текущим — минимальный слепок боевой ситуации, где ISW отстаёт."""
    cur = date.today().isoformat()[:7]
    m2, m1 = _prev_month(cur, 2), _prev_month(cur, 1)
    months = [_archive_month(_prev_month(cur, 3), 100_000), _archive_month(m2, 100_150)]
    path = tmp_path / "real_history.json"
    path.write_text(json.dumps({"months": months}), encoding="utf-8")
    monkeypatch.setattr(iso, "_REAL_HISTORY_PATH", str(path))
    monkeypatch.setattr(iso, "_load_timeline_points", lambda: [])
    return {"cur": cur, "m2": m2, "m1": m1}


def _fc(features):
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": g} for g in features]}


def _by_month(result):
    return {f["properties"]["month"]: f["properties"] for f in result["features"]}


def test_месяц_без_данных_остаётся_в_ряду_и_не_отдаёт_дельту_соседу(archive):
    res = iso._isochrone_from_real_history(_fc([_sq(35.0, 47.0)]), isw_area_km2=100_400, db=None)
    props = _by_month(res)

    # Пропущенные месяцы не исчезают из ряда — иначе на графике их место
    # занимает соседний столбик и «нет данных» читается как «ничего не было».
    assert archive["m1"] in props, "месяц между концом архива и текущим выпал из ряда"
    gap = props[archive["m1"]]
    assert gap["no_data"] is True
    assert gap["area_km2"] is None and gap["delta_km2"] is None

    # Текущий месяц знает свою площадь, но месячной дельты у него быть НЕ МОЖЕТ:
    # предыдущий месяц неизвестен. Накопленное — отдельными полями, с указанием
    # базы и длины окна.
    cur = props[archive["cur"]]
    assert cur["area_km2"] == 100_400
    assert cur["delta_km2"] is None, "дельта за несколько месяцев выдана за месячную"
    assert cur["delta_since_km2"] == 100_400 - 100_150
    assert cur["delta_since_month"] == archive["m2"]
    assert cur["delta_span_months"] == 2
    assert cur["partial"] is True  # текущий месяц не закончен


def test_свой_снапшот_закрывает_дыру_настоящей_месячной_дельтой(archive):
    """Мост из наших дневных снапшотов чистой ISW-площади: месяц, до которого
    архив ISW не дошёл, получает НАСТОЯЩУЮ месячную дельту, а не пропуск."""
    m1_end = iso._month_end(*map(int, archive["m1"].split("-")))

    class _Rows(list):
        def filter(self, *a, **k): return self
        def order_by(self, *a, **k): return self
        def all(self): return list(self)

    class _DB:
        def query(self, *a, **k): return _Rows([(m1_end, 100_260)])

    res = iso._isochrone_from_real_history(_fc([_sq(35.0, 47.0)]), isw_area_km2=100_400, db=_DB())
    props = _by_month(res)

    bridged = props[archive["m1"]]
    assert bridged.get("no_data") is None
    assert bridged["history_source"] == "own_isw_snapshot"
    assert bridged["area_km2"] == 100_260
    assert bridged["delta_km2"] == 110  # 100 260 − 100 150, месяц к месяцу
    assert bridged["area_as_of"] == m1_end

    cur = props[archive["cur"]]
    assert cur["delta_km2"] == 140  # 100 400 − 100 260, теперь сосед известен
    assert "delta_since_km2" not in cur


def test_архивный_месяц_с_чужим_снапшотом_не_выдаёт_нулевую_дельту(tmp_path, monkeypatch):
    """У ISW нет таймлапса за месяц → в файле повтор снапшота соседа. Раньше это
    давало «дельта 0», а движение уезжало в следующий месяц — тот же дефект
    атрибуции, только внутри архива."""
    cur = date.today().isoformat()[:7]
    m3, m2, m1 = _prev_month(cur, 3), _prev_month(cur, 2), _prev_month(cur, 1)
    months = [
        _archive_month(m3, 100_000),
        # снапшот скопирован из предыдущего месяца — своей площади у m2 нет
        _archive_month(m2, 100_000, snapshot_from=m3),
        _archive_month(m1, 100_300),
    ]
    path = tmp_path / "real_history.json"
    path.write_text(json.dumps({"months": months}), encoding="utf-8")
    monkeypatch.setattr(iso, "_REAL_HISTORY_PATH", str(path))
    monkeypatch.setattr(iso, "_load_timeline_points", lambda: [])

    res = iso._isochrone_from_real_history(_fc([_sq(35.0, 47.0)]), isw_area_km2=100_400, db=None)
    props = _by_month(res)

    assert props[m2]["no_data"] is True
    assert props[m2]["delta_km2"] is None, "месяц с чужим снапшотом выдал собственную дельту"
    assert props[m1]["delta_km2"] is None, "движение двух месяцев подписано как месячное"
    assert props[m1]["delta_since_km2"] == 300
    assert props[m1]["delta_span_months"] == 2
