"""Канон промежуточных периодов и YoY-пары.

Баг, который эти тесты закрывают (владелец, 2026-07-30): в interim.periods
перемешаны 3М/6М/9М и кварталы, а витрина считала динамику «последнее ÷
предыдущее» — то есть квартал делила на девять месяцев прошлого года.
"""
from app.services.interim_periods import (
    build_yoy_index, latest_ytd, parse_period, ytd_for_year,
)


def _p(label, **kw):
    return {"label": label, **kw}


def test_labels_of_every_shape_parse():
    cases = {
        "1кв2025": (2025, 0, 3), "4кв2024": (2024, 9, 12),
        "1П2023": (2023, 0, 6), "2П2025": (2025, 6, 12), "1п2024": (2024, 0, 6),
        "6М2023": (2023, 0, 6), "6мес2024": (2024, 0, 6), "9М2025": (2025, 0, 9),
        "9мес2023": (2023, 0, 9), "3М2026": (2026, 0, 3),
        "H1 2024": (2024, 0, 6), "H2 2023": (2023, 6, 12),
    }
    for label, (y, a, b) in cases.items():
        c = parse_period(_p(label))
        assert c, f"не разобрано: {label}"
        assert (c["year"], c["start_m"], c["end_m"]) == (y, a, b), label


def test_year_from_end_date_when_label_has_none():
    c = parse_period(_p("1 квартал", fiscal_year=2026))
    assert c is None or c["year"] == 2026  # без номера периода метка нечитаема
    c = parse_period(_p("2кв", end_date="2025-06-30"))
    assert c and c["year"] == 2025 and c["end_m"] == 6


def test_yoy_pairs_only_same_window():
    # реальный ряд ROSN: накопительные периоды вперемешку
    ps = [_p(x) for x in ["6М2023", "9М2023", "3М2024", "6М2024", "9М2024",
                          "3М2025", "6М2025", "9М2025", "3М2026"]]
    idx = build_yoy_index(ps)
    assert idx[0] is None and idx[1] is None and idx[2] is None  # первого года пары нет
    assert ps[idx[3]]["label"] == "6М2023"   # 6М2024 → 6М2023
    assert ps[idx[4]]["label"] == "9М2023"
    assert ps[idx[5]]["label"] == "3М2024"   # 3М2025 → 3М2024, а НЕ 9М2024
    assert ps[idx[8]]["label"] == "3М2025"   # 3М2026 → 3М2025


def test_quarter_and_cumulative_three_months_are_comparable():
    ps = [_p("1кв2025"), _p("3М2026")]
    assert build_yoy_index(ps)[1] == 0


def test_ytd_sums_consecutive_quarters():
    ps = [_p("1кв2025"), _p("2кв2025"), _p("3кв2025")]
    r = ytd_for_year(ps, [10, 20, 30], 2025)
    assert r["end_m"] == 9 and r["value"] == 60 and r["source"] == "quarters"


def test_ytd_stops_at_gap_in_quarters():
    ps = [_p("1кв2025"), _p("3кв2025")]  # второго квартала нет
    r = ytd_for_year(ps, [10, 30], 2025)
    assert r["end_m"] == 3 and r["value"] == 10


def test_ytd_prefers_wider_coverage_and_exact_window_when_asked():
    ps = [_p("1кв2025"), _p("1П2025")]
    assert ytd_for_year(ps, [10, 25], 2025)["end_m"] == 6
    assert ytd_for_year(ps, [10, 25], 2025, end_m=3)["value"] == 10


def test_latest_ytd_skips_year_without_values():
    ps = [_p("1кв2025"), _p("1кв2026")]
    r = latest_ytd(ps, [10, None])  # период 2026 заведён, но показатель пуст
    assert r["year"] == 2025 and r["value"] == 10
