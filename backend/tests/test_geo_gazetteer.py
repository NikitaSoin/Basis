"""Справочник населённых пунктов: привязка заявления по имени + области (+ район,
+ близость к фронту). Без сети: маленький справочник-заготовка в tmp_path.

Что доказывается на боевых случаях:
  * «Новопавловка Запорожской области» → координата СЕЛА, а не центра Орехова;
  * «Красный Кут Донецкой» — тёзка в Саратовской не выбирается (область режет);
  * старое название из сводки МО РФ («Красноармейск») находит Покровск;
  * украинское написание без name:ru находится транслитерацией;
  * тёзки внутри области разводятся близостью к фронту, а без фронта —
    честный ambiguous без координаты;
  * опечатка в одну букву — fuzzy, но только внутри названной области.
"""
import gzip
import json

import pytest
from shapely.geometry import Point

from app.services import geo_gazetteer as gz


ITEMS = [
    {"id": 1, "n": "Новопавловка", "u": "Новопавлівка", "o": "Запорожская", "r": "Пологовский", "t": "village", "lat": 47.45, "lon": 36.05},
    {"id": 2, "n": "Новопавловка", "u": "Новопавлівка", "o": "Днепропетровская", "r": "Синельниковский", "t": "village", "lat": 48.30, "lon": 36.10},
    {"id": 3, "n": "Орехов", "u": "Оріхів", "o": "Запорожская", "r": "Пологовский", "t": "town", "lat": 47.5686, "lon": 35.7897},
    {"id": 4, "n": "Красный Кут", "u": "Красний Кут", "o": "Донецкая", "r": "Кальмиусский", "t": "village", "lat": 47.72, "lon": 38.45},
    {"id": 5, "n": "Покровск", "u": "Покровськ", "o": "Донецкая", "r": "Покровский", "t": "city", "a": ["Красноармейск", "Красноармійськ"], "lat": 48.2833, "lon": 37.1761},
    {"id": 6, "n": None, "u": "Новомиколаївка", "o": "Донецкая", "r": "Покровский", "t": "village", "lat": 48.10, "lon": 37.40},
    {"id": 7, "n": "Новосёловка", "u": "Новоселівка", "o": "Донецкая", "r": "Покровский", "t": "village", "lat": 48.20, "lon": 37.30},
    {"id": 8, "n": "Новосёловка", "u": "Новоселівка", "o": "Донецкая", "r": "Краматорский", "t": "village", "lat": 49.10, "lon": 37.90},
    {"id": 9, "n": "Терновое", "u": "Тернове", "o": "Донецкая", "r": "Покровский", "t": "village", "lat": 48.35, "lon": 37.00},
    # переименованное село: старое имя в справочнике только по-украински
    {"id": 10, "n": "Христофоровка", "u": "Христофорівка", "o": "Днепропетровская", "t": "village", "a": ["Комунарівка"], "lat": 47.93, "lon": 35.90},
    {"id": 11, "n": "Сарабаш", "u": "Сарабаш", "o": "Донецкая", "t": "village", "a": ["Коммунаровка", "Комунарівка"], "lat": 47.70, "lon": 38.50},
    # одно село двумя записями: узел и контур (центр контура в 1,5 км)
    {"id": "n12", "n": "Гоптовка", "u": "Гоптівка", "o": "Харьковская", "t": "village", "lat": 50.30, "lon": 36.20},
    {"id": "w13", "n": "Гоптовка", "u": "Гоптівка", "o": "Харьковская", "t": "village", "lat": 50.31, "lon": 36.21},
]


@pytest.fixture()
def book(tmp_path):
    p = tmp_path / "gaz.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump({"items": ITEMS}, f, ensure_ascii=False)
    return gz.load(str(p))


def test_нормализация_и_ключ_области():
    assert gz.normalize("село Красный Кут") == "красныйкут"
    assert gz.normalize("Васильевка") == gz.normalize("Василевка") == "василевка"
    assert gz.normalize("Мар’їнка") == "марїнка"
    assert gz.uk_to_ru("Новопавлівка") == "новопавловка"
    assert gz.uk_to_ru("Мар’їнка") == "маринка"
    assert gz.oblast_key("Донецкая область (Покровский район)") == "донецкая"
    assert gz.oblast_key("ДНР") == "донецкая"
    assert gz.oblast_key("Республика Крым") == "крым"
    assert gz.oblast_key(None) is None
    assert gz.raion_key("Харьковская область (Волчанский район)") == "волчанский"
    assert gz.raion_key("Донецкая") is None


def test_село_а_не_центр_города_тёзки_по_области(book):
    hit = gz.resolve("Новопавловка", "Запорожская область", gz=book)
    assert hit["status"] == "exact"
    assert (hit["lat"], hit["lon"]) == (47.45, 36.05)
    # без области — две Новопавловки, развести нечем
    amb = gz.resolve("Новопавловка", None, gz=book)
    assert amb["status"] == "ambiguous" and amb["candidates"] == 2


def test_старое_название_из_сводки_находит_город(book):
    hit = gz.resolve("Красноармейск", "Донецкая", gz=book)
    assert hit["status"] == "exact" and hit["name"] == "Покровск"


def test_украинское_написание_без_русского_имени(book):
    hit = gz.resolve("Новониколаевка", "Донецкая", gz=book)
    assert hit["status"] == "exact" and hit["osm_id"] == 6


def test_тёзки_в_одной_области_разводит_фронт_или_район(book):
    front = Point(37.25, 48.15).buffer(0.05)  # масса контроля у покровской Новосёловки
    hit = gz.resolve("Новоселовка", "Донецкая", near=front, gz=book)
    assert hit["status"] == "near_front" and hit["osm_id"] == 7
    hit2 = gz.resolve("Новоселовка", "Донецкая область (Краматорский район)", gz=book)
    assert hit2["status"] == "exact" and hit2["osm_id"] == 8
    amb = gz.resolve("Новоселовка", "Донецкая", gz=book)
    assert amb["status"] == "ambiguous"


def test_опечатка_только_внутри_области(book):
    hit = gz.resolve("Терновoе".replace("o", "о"), "Донецкая", gz=book)
    assert hit["status"] == "exact"
    fuzzy = gz.resolve("Терновае", "Донецкая", gz=book)
    assert fuzzy["status"] == "fuzzy" and fuzzy["osm_id"] == 9
    assert gz.resolve("Терновае", "Запорожская", gz=book)["status"] == "not_found"


def test_нет_справочника_честная_деградация(tmp_path, monkeypatch):
    monkeypatch.setattr(gz, "_PATH", str(tmp_path / "нет.json.gz"))
    monkeypatch.setattr(gz, "_loaded", None)
    assert gz.resolve("Орехов", "Запорожская")["status"] == "no_gazetteer"


# ---- правило 0 в синке линии фронта -----------------------------------------
from app.services import geo_isw_frontline_sync as sync  # noqa: E402

OREKHOV_CENTER = (47.5677, 35.7849)   # геокод, который пришёл из ленты для Новопавловки
NOVOPAVLOVKA = (47.45, 36.05)


def test_синк_берёт_координату_из_справочника_только_для_ленты_и_заявлений(monkeypatch):
    def fake_resolve(name, oblast, near=None, hint=None):
        if name == "Новопавловка":
            return {"status": "exact", "lat": NOVOPAVLOVKA[0], "lon": NOVOPAVLOVKA[1],
                    "oblast": "Запорожская", "raion": "Пологовский", "candidates": 1}
        if name == "Новосёловка":
            return {"status": "ambiguous", "candidates": 2}
        return {"status": "not_found", "candidates": 0}
    monkeypatch.setattr(sync, "_gazetteer_resolve", fake_resolve)
    monkeypatch.setattr(sync, "_load_oblast_shapes", lambda: [])
    monkeypatch.setattr(sync, "_load_protected_cities", lambda: ([], 3.0))

    got = sync.validate_candidates([
        {"name": "Новопавловка", "oblast": "Запорожская область", "lat": OREKHOV_CENTER[0], "lon": OREKHOV_CENTER[1], "radius_km": 3, "src": "db"},
        {"name": "Новосёловка", "oblast": "Донецкая", "lat": 48.2, "lon": 37.3, "radius_km": 3, "src": "db"},
        {"name": "Купянск", "oblast": "Харьковская область", "lat": 49.714, "lon": 37.616, "radius_km": 4, "src": "override"},
        {"name": "Неизвестное", "oblast": "Донецкая", "lat": 48.0, "lon": 37.9, "radius_km": 3, "src": "claimed"},
    ], control_mass=None, quiet=True)
    by = {c["name"]: c for c in got}
    # село встало на своё место, а не в центр города
    assert (by["Новопавловка"]["lat"], by["Новопавловка"]["lon"]) == NOVOPAVLOVKA
    assert by["Новопавловка"]["geocode"] == "exact"
    # тёзки, которых не развести, — вон
    assert "Новосёловка" not in by
    # ручной оверрайд справочник не трогает, даже если бы тот «знал лучше»
    assert (by["Купянск"]["lat"], by["Купянск"]["lon"]) == (49.714, 37.616)
    # не найден в справочнике — остаётся как пришёл (дальше прежние правила)
    assert (by["Неизвестное"]["lat"], by["Неизвестное"]["lon"]) == (48.0, 37.9)


def test_живая_заливка_помечает_источник_пункта():
    """dated_candidates обязан проставлять src — иначе правило 0 не отличит
    ручной оверрайд от строки ленты и перепишет выверенные координаты."""
    cands = sync.dated_candidates(None, db=None)
    assert cands, "кандидаты из конфигов не собрались"
    assert all(c.get("src") in ("override", "timeline", "claimed", "db") for c in cands)
    assert any(c["src"] == "override" for c in cands)


def test_подсказка_прежней_координаты_разводит_тёзок_и_держит_опечатку_рядом(book):
    # две Новосёловки в Донецкой; прежняя координата в 3 км от покровской → она
    hit = gz.resolve("Новоселовка", "Донецкая", hint=(48.22, 37.31), gz=book)
    assert hit["status"] == "exact" and hit["osm_id"] == 7
    # опечатка принимается только рядом с прежней координатой: Терновое в 100 км от подсказки — не оно
    assert gz.resolve("Терновае", "Донецкая", hint=(49.2, 38.4), gz=book)["status"] == "not_found"
    assert gz.resolve("Терновае", "Донецкая", hint=(48.36, 37.02), gz=book)["status"] == "fuzzy"


def test_точное_имя_вне_названной_области_без_подтверждения_не_принимается(book):
    # «Новопавловка Харьковской» — таких нет; тёзки в Запорожской и Днепропетровской
    miss = gz.resolve("Новопавловка", "Харьковская", gz=book)
    assert miss["status"] == "oblast_mismatch" and "lat" not in miss
    # но если прежняя координата указывает на одну из них — берём её
    ok = gz.resolve("Новопавловка", "Харьковская", hint=(47.44, 36.06), gz=book)
    assert ok["status"] == "near_front" and ok["osm_id"] == 1


def test_старое_имя_по_украински_в_своей_области_важнее_точной_тёзки_в_чужой(book):
    """«Коммунаровка Днепропетровской области»: точное имя есть только у донецкого
    Сарабаша (старое русское), а в Днепропетровской село уже Христофоровка со
    старым именем по-украински. Берём своё село, а не тёзку за 200 км."""
    front = Point(38.4, 47.7).buffer(0.1)  # фронт рядом с донецкой тёзкой — и всё равно
    hit = gz.resolve("Коммунаровка", "Днепропетровская область", near=front, hint=(47.94, 35.91), gz=book)
    assert hit["status"] == "fuzzy" and hit["osm_id"] == 10


def test_узел_и_контур_одного_села_не_тёзки(book):
    hit = gz.resolve("Гоптовка", "Харьковская область", gz=book)
    assert hit["status"] == "exact" and hit["osm_id"] == "n12"
