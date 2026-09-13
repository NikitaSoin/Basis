"""Собранные данные по очагам доходят до аналитиков: агрегаты ударов, заявлений и площади ISW."""
from datetime import date, datetime, timedelta, timezone

from app.models.geo import GeoFrontlineSnapshot, GeoStrikeEvent, GeoTerritorialClaim
from app.services import feed_tools as ft


def _strike(theater, d, target, sig="major", loc="Тула"):
    return GeoStrikeEvent(theater=theater, location_name=loc, target_type=target, significance=sig,
                          label=f"{target} {loc}", event_date=d, source_key="rybar",
                          expires_at=datetime.now(timezone.utc) + timedelta(days=60))


def test_недельные_агрегаты_и_площадь(db):
    today = date.today()
    db.add_all([_strike("svo", today - timedelta(days=1), "НПЗ"),
                _strike("svo", today - timedelta(days=2), "НПЗ", loc="Рязань"),
                _strike("svo", today - timedelta(days=9), "склад БПЛА", sig="minor"),
                _strike("middle_east", today - timedelta(days=3), "порт", loc="Хайфа"),
                _strike("svo", today - timedelta(days=400), "старое", loc="далеко")])   # вне окна
    db.add_all([GeoTerritorialClaim(settlement="Тестовка", oblast="Донецкая", status="ru_control",
                                    claimed_date=today - timedelta(days=2), source_key="isw"),
                GeoTerritorialClaim(settlement="Спорновка", oblast="Донецкая", status="contested",
                                    claimed_date=today - timedelta(days=12), source_key="rybar")])
    d0 = today - timedelta(days=1)
    db.add_all([GeoFrontlineSnapshot(theater="svo", snapshot_date=d0.isoformat(), isw_area_km2=1000),
                GeoFrontlineSnapshot(theater="svo", snapshot_date=(d0 - timedelta(days=8)).isoformat(), isw_area_km2=900),
                GeoFrontlineSnapshot(theater="svo", snapshot_date=(d0 - timedelta(days=31)).isoformat(), isw_area_km2=850)])
    db.flush()

    b = ft.conflict_brief(db, days=56)
    svo = b["theaters"]["svo"]
    assert svo["strikes"]["total"] == 3 and svo["strikes"]["major"] == 2
    assert svo["strikes"]["top_targets"][0] == {"target": "нпз", "count": 2}
    assert sum(w["major"] + w["minor"] for w in svo["strikes"]["weeks"]) == 3
    assert svo["territorial_claims"]["ru_control"] == 1 and svo["territorial_claims"]["contested"] == 1
    fl = svo["frontline_isw"]
    assert fl["area_km2_latest"] == 1000 and fl["delta_7d_km2"] == 100 and fl["delta_30d_km2"] == 150
    assert b["theaters"]["middle_east"]["strikes"]["total"] == 1
    assert "territorial_claims" not in b["theaters"]["atr"]

    one = ft.conflict_data(db, "svo", days=56, limit=5)
    assert one["theater_ru"] == "СВО" and one["strikes"]["recent_major"][0]["target_type"] == "НПЗ"
    assert "error" in ft.conflict_data(db, "mars")

    txt = ft.conflict_brief_text(db, days=56)
    assert "СОБРАННЫЕ ДАННЫЕ ПО ОЧАГАМ" in txt and "нпз" in txt
    assert ft.execute(db, "conflict_data", {"theater": "svo"})["strikes"]["total"] == 3


def test_пустые_данные_названы_прямо(db):
    txt = ft.conflict_brief_text(db, days=7)
    assert "не собрано" in txt or "СОБРАННЫЕ ДАННЫЕ" in txt


def test_инструмент_в_схеме():
    names = [t["function"]["name"] for t in ft.FEED_TOOLS_SCHEMA]
    assert "conflict_data" in names
