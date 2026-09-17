"""Структура инфляции: разбор файла Росстата, подбор долей когорт, сверка вкладов.

Проверяем ровно то, что может сломаться молча: раскладку широкой таблицы по годам,
отсечение второй секции («к декабрю предыдущего года»), пересчёт годового роста
цепочкой месячных индексов и главное — что взвешенная сумма когорт повторяет сводный
индекс. Последнее и есть защита от подмены рядов: если разбор поедет на столбец, сумма
перестанет сходиться, и тест это увидит.
"""
import io

import openpyxl
import pytest

from app.services import macro_prices_structure as mps


def _book(sheets: dict[str, dict[tuple[int, int], float]]) -> bytes:
    """Собрать файл в формате Росстата: строки — месяцы, столбцы — годы."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    years = sorted({y for s in sheets.values() for (y, _) in s})
    for title, series in sheets.items():
        ws = wb.create_sheet(title)
        ws.append(["Индексы потребительских цен"])
        ws.append(["К содержанию"])
        ws.append([])
        ws.append([None] + [str(y) for y in years])
        ws.append(["к концу предыдущего месяца"])
        for m, name in enumerate(mps._MONTHS, start=1):
            ws.append([name] + [series.get((y, m)) for y in years])
        # вторая секция — накопленный итог; разбор обязан её игнорировать
        ws.append(["к декабрю предыдущего года"])
        ws.append(["декабрь"] + [108.0 for _ in years])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def blob():
    # Когорты обязаны двигаться ПО-РАЗНОМУ, иначе доли не восстановимы в принципе:
    # при одинаковой динамике любая комбинация весов даёт тот же сводный индекс.
    food = {(y, m): round(100.4 + 0.3 * ((m * 7 + y) % 5), 3)
            for y in (2024, 2025, 2026) for m in range(1, 13)}
    nonfood = {(y, m): round(100.2 - 0.2 * ((m * 3 + y) % 4), 3)
               for y in (2024, 2025, 2026) for m in range(1, 13)}
    services = {(y, m): round(100.6 + 0.15 * ((m + y) % 6), 3)
                for y in (2024, 2025, 2026) for m in range(1, 13)}
    # сводный индекс собран из когорт с долями 0,40 / 0,30 / 0,30
    total = {k: round(0.4 * food[k] + 0.3 * nonfood[k] + 0.3 * services[k], 4) for k in food}
    return _book({"01": total, "02": food, "03": nonfood, "04": services})


def test_parse_sheet_reads_months_by_year(blob):
    series = mps._parse_sheet(blob, "02")
    assert series[(2026, 5)] == pytest.approx(100.4 + 0.3 * ((5 * 7 + 2026) % 5))
    assert len(series) == 36, "должны разобраться все месяцы трёх лет"


def test_parse_sheet_ignores_second_section(blob):
    """Секция «к декабрю предыдущего года» не должна затирать декабрьский месячный индекс."""
    series = mps._parse_sheet(blob, "02")
    assert series[(2026, 12)] == pytest.approx(100.4 + 0.3 * ((12 * 7 + 2026) % 5))


def test_yoy_chains_twelve_months(blob):
    series = mps._parse_sheet(blob, "02")
    manual = 1.0
    for m in range(1, 13):
        manual *= series[(2026, m)] / 100
    assert mps._yoy(series, 2026, 12) == pytest.approx((manual - 1) * 100, abs=0.02)


def test_weights_recover_the_mix(blob):
    parsed = {code: mps._parse_sheet(blob, sheet) for sheet, (code, _) in mps._COHORTS.items()}
    parsed["_control"] = mps._parse_sheet(blob, "01")
    w = mps._estimate_weights(parsed)
    assert w is not None
    assert w["inflation_food"] == pytest.approx(0.40, abs=0.01)
    assert w["inflation_nonfood"] == pytest.approx(0.30, abs=0.01)
    assert w["inflation_services"] == pytest.approx(0.30, abs=0.01)


def test_control_check_reports_small_error(blob):
    parsed = {code: mps._parse_sheet(blob, sheet) for sheet, (code, _) in mps._COHORTS.items()}
    control = mps._parse_sheet(blob, "01")
    res = mps._control_check(parsed, control)
    assert res["max_error_pp"] < 0.05, "сумма когорт обязана повторять сводный индекс"


def test_basket_weights_file_is_consistent():
    """Веса разделов корзины — снимок Росстата: сумма по разделам обязана давать 100%."""
    basket = mps.weights_basket()
    assert basket.get("divisions"), "файл весов корзины должен быть в backend/config"
    total = sum(d["weight_pct"] for d in basket["divisions"])
    assert total == pytest.approx(100.0, abs=0.5)
