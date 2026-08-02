"""Инфляционные ожидания: детерминированный разбор XLSX инФОМ и починка ряда.

🔴 Почему на это есть тесты. Значение извлекала МОДЕЛЬ из «текста» файла, но
`_fetch_text` написан под HTML: для XLSX он декодировал ZIP-архив как строку и отдавал
в LLM бинарный мусор. Модель возвращала правдоподобное число из шума — и на разных
прогонах разное: локальная база получила за июль 2026 значение 12,2, боевая 14,7
(верное — 14,70 стоит в самом файле). Ключевой показатель ДКП заполнялся случайно.
"""
import datetime
import io

import openpyxl
import pytest

from app.services.macro_cb_sync import (_EXP_ROW_LABEL, _EXP_SHEET, _HIST_FIXED_SRC,
                                        _dedupe_and_fix_history, _expectations_from_xlsx)


def _book(rows: list[tuple[str, list]]) -> bytes:
    """Мини-книга той же формы, что бюллетень: строка дат, под ней строки рядов."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _EXP_SHEET
    ws.append(["Прямые оценки годовой инфляции: медианные значения"])
    ws.append([None, datetime.datetime(2026, 5, 1), datetime.datetime(2026, 6, 1),
               datetime.datetime(2026, 7, 1)])
    for label, values in rows:
        ws.append([label] + values)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestXlsxParsing:
    def test_takes_expected_not_observed_inflation(self):
        """Рядом лежит «наблюдаемая инфляция» — она систематически ВЫШЕ на 2-3 п.п.
        Взять её вместо ожидаемой значит завысить ключевой показатель ДКП."""
        content = _book([("годовая наблюдаемая инфляция", [14.2, 15.1, 16.0]),
                         (_EXP_ROW_LABEL, [13.02, 12.45, 14.7]),
                         ("годовая инфляция, ожидаемая через пять лет", [10.3, 11.2, 11.5])])
        series = _expectations_from_xlsx(content)
        assert [v for _, v in series] == [13.02, 12.45, 14.7]

    def test_periods_are_month_ends(self):
        content = _book([(_EXP_ROW_LABEL, [13.02, 12.45, 14.7])])
        series = _expectations_from_xlsx(content)
        assert [str(d) for d, _ in series] == ["2026-05-31", "2026-06-30", "2026-07-31"]

    def test_missing_row_returns_empty_not_garbage(self):
        """Не нашли ряд — честно пусто. Иначе вернём случайное число из соседней строки."""
        assert _expectations_from_xlsx(_book([("что-то другое", [1, 2, 3])])) == []

    def test_broken_file_does_not_crash(self):
        with pytest.raises(Exception):
            _expectations_from_xlsx(b"not a workbook at all")


class TestSeriesTidyUp:
    """Дубли и сдвиг: в ряд писали три источника с разными конвенциями дат."""

    def _seed(self, db, hist_year: int):
        """Историческую точку каждый тест кладёт в СВОЙ год.

        Тестовая база одна на сессию и не откатывается между тестами: с общей датой
        второй тест видел уже сдвинутую точку первого и мерил не то, что проверяет.
        """
        from datetime import date

        from app.models.macro import MacroDataPoint
        from app.services import macro_ingest as mi
        mi.seed_indicators(db)
        # Чистим ряд начисто: тестовая база одна на сессию, и соседние тесты сеют в
        # тот же показатель — без этого проверяем чужие точки, а не свои.
        db.query(MacroDataPoint).filter_by(indicator_code="inflation_expectations").delete()
        db.commit()
        # официальная точка (конец месяца) и дубль бэкфилла (28-е) за тот же месяц
        mi.upsert_point(db, "inflation_expectations", date(2026, 7, 31), "level", 14.7,
                        ingested_via="cbr")
        mi.upsert_point(db, "inflation_expectations", date(2026, 7, 28), "level", 12.2,
                        ingested_via="file")
        # историческая точка вне зоны покрытия — сдвинута на месяц вперёд
        mi.upsert_point(db, "inflation_expectations", date(hist_year, 5, 28), "level", 11.5,
                        ingested_via="file")
        db.commit()

    def test_duplicate_in_covered_zone_is_removed(self, db):
        from datetime import date
        from app.models.macro import MacroDataPoint

        self._seed(db, 2021)
        _dedupe_and_fix_history(db, date(2026, 1, 1))
        # Проверяем КОНКРЕТНЫЕ точки, а не счётчик: тестовая база общая на сессию и
        # накапливает данные соседних тестов — счётчик тогда меряет чужое.
        assert db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_expectations", as_of=date(2026, 7, 28)).first() is None
        left = db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_expectations", as_of=date(2026, 7, 31)).all()
        assert len(left) == 1 and float(left[0].value) == 14.7

    def test_history_is_shifted_back_one_month(self, db):
        from datetime import date
        from app.models.macro import MacroDataPoint

        self._seed(db, 2022)
        _dedupe_and_fix_history(db, date(2026, 1, 1))
        moved = db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_expectations", as_of=date(2022, 4, 30)).first()
        assert moved is not None and float(moved.value) == 11.5

    def test_second_run_does_not_shift_twice(self, db):
        """🔴 Идемпотентность: без метки исправленной точки повторный прогон сдвинул бы
        её ещё на месяц, и ряд уползал бы с каждым запуском крона."""
        from datetime import date
        from app.models.macro import MacroDataPoint

        self._seed(db, 2023)
        _dedupe_and_fix_history(db, date(2026, 1, 1))
        _dedupe_and_fix_history(db, date(2026, 1, 1))
        still = db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_expectations", as_of=date(2023, 4, 30)).first()
        assert still is not None and still.source == _HIST_FIXED_SRC
        # уехала бы на 2023-03-31, если бы метка не защищала от повторного сдвига
        assert db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_expectations", as_of=date(2023, 3, 31)).first() is None
