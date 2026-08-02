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


class TestKnownCorrections:
    """Адресные исправления точек, сверенных с первоисточником.

    Точка ВВП за 2кв2026 пришла из пересказа новости как +0,4% г/г. Это число не
    соответствовало НИ ОДНОМУ периоду: квартал +0,9, июнь +1,1, май +0,3, полугодие
    +0,3 (МЭР). Обычный ингест такую точку не трогает — first-write-wins защищает
    верные значения от затирания, поэтому исправление должно быть адресным.
    """

    def test_correction_overwrites_wrong_point(self, db):
        from datetime import date

        from app.services import macro_ingest as mi

        mi.seed_indicators(db)
        # Точка стояла на конце квартала — чужая для ряда конвенция (ряд ведётся по
        # началу квартала), поэтому исправление её удаляет и пишет на 2026-04-01.
        mi.upsert_point(db, "gdp", date(2026, 6, 30), "yoy", 0.4, ingested_via="news")
        db.commit()

        mi.apply_known_corrections(db)
        # Счётчик не проверяем: список исправлений растёт, а тест — про конкретную точку.
        from app.models.macro import MacroDataPoint
        p = db.query(MacroDataPoint).filter_by(
            indicator_code="gdp", metric="yoy", as_of=date(2026, 4, 1)).first()
        assert float(p.value) == 0.9
        assert db.query(MacroDataPoint).filter_by(
            indicator_code="gdp", metric="yoy", as_of=date(2026, 6, 30)).first() is None

    def test_second_run_is_a_no_op(self, db):
        from app.services import macro_ingest as mi
        mi.apply_known_corrections(db)
        assert mi.apply_known_corrections(db)["applied"] == 0

    def test_regular_ingest_cannot_undo_a_correction(self, db):
        """🔴 Иначе следующий же прогон новостного канала вернёт ошибку на место."""
        from datetime import date

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint

        mi.apply_known_corrections(db)
        # Новостной канал снова кладёт своё число на чужую для ряда дату
        mi.upsert_point(db, "gdp", date(2026, 6, 30), "yoy", 0.4, ingested_via="news")
        db.commit()
        p = db.query(MacroDataPoint).filter_by(
            indicator_code="gdp", metric="yoy", as_of=date(2026, 4, 1)).first()
        assert float(p.value) == 0.9, "исправление не должно откатываться"
        # следующий прогон снова убирает чужеродную точку
        mi.apply_known_corrections(db)
        assert db.query(MacroDataPoint).filter_by(
            indicator_code="gdp", metric="yoy", as_of=date(2026, 6, 30)).first() is None

    def test_every_correction_carries_a_source_and_reason(self):
        """Без проверяемой ссылки и причины это ручная подгонка чисел."""
        from app.services.macro_ingest import _KNOWN_CORRECTIONS

        for c in _KNOWN_CORRECTIONS:
            assert c.get("source_url", "").startswith("http"), c
            assert len(c.get("why", "")) > 15, c


class TestNewsPlausibilityGate:
    """Новостной канал берёт числа из ПЕРЕСКАЗОВ — и трижды за сессию дал мусор:
    ВВП 0,4% (не соответствовало ни одному периоду), недельная инфляция 2,6% (это
    годовая под 200%), ожидания 12,2 вместо 14,7. Чинить точки по одной бесполезно,
    пока канал может писать что угодно."""

    def _history(self, db, code="inflation_weekly", metric="wow"):
        from datetime import date, timedelta

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint
        mi.seed_indicators(db)
        db.query(MacroDataPoint).filter_by(indicator_code=code).delete()
        db.commit()
        base = date(2026, 1, 5)
        for i, v in enumerate([0.11, 0.17, 0.23, 0.09, 0.14, 0.2, 0.16, 0.12]):
            mi.upsert_point(db, code, base + timedelta(days=7 * i), metric, v,
                            ingested_via="rosstat")
        db.commit()

    def test_absurd_weekly_inflation_is_rejected(self, db):
        from datetime import date

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint

        self._history(db)
        assert mi.upsert_point(db, "inflation_weekly", date(2026, 3, 9), "wow", 2.6,
                               ingested_via="news") == "skip"
        assert db.query(MacroDataPoint).filter_by(
            indicator_code="inflation_weekly", as_of=date(2026, 3, 9)).first() is None

    def test_normal_value_from_news_still_passes(self, db):
        """Гейт ловит порядок величины, а не спорит с экономикой."""
        from datetime import date

        from app.services import macro_ingest as mi

        self._history(db)
        assert mi.upsert_point(db, "inflation_weekly", date(2026, 3, 9), "wow", 0.31,
                               ingested_via="news") == "insert"

    def test_official_channel_is_not_gated(self, db):
        """У официального источника настоящий скачок — это данные, а не ошибка."""
        from datetime import date

        from app.services import macro_ingest as mi

        self._history(db)
        assert mi.upsert_point(db, "inflation_weekly", date(2026, 3, 9), "wow", 2.6,
                               ingested_via="rosstat") == "insert"

    def test_short_history_does_not_invent_limits(self, db):
        from datetime import date

        from app.services import macro_ingest as mi
        from app.models.macro import MacroDataPoint

        mi.seed_indicators(db)
        db.query(MacroDataPoint).filter_by(indicator_code="inflation_weekly").delete()
        db.commit()
        assert mi.upsert_point(db, "inflation_weekly", date(2026, 3, 9), "wow", 2.6,
                               ingested_via="news") == "insert"


class TestDeadSeriesAreLabelled:
    """Ряд, который источник перестал вести, обязан быть помечен для модели.

    🔴 Иначе выпуск принимает последнюю точку за текущее состояние: китайский ВВП стоял
    на 2023 годе, инфляция КНР — на 2025-м. А ряд «Ставка НБК» на деле тянется из FRED
    IR3TIB01CNM156N — это 3-месячная МЕЖБАНКОВСКАЯ ставка (1,5%), тогда как ставка НБК
    (LPR 1Y) равна 3,0%: разница вдвое, и вывод про ДКП Китая был бы обратным.
    """

    def test_dead_and_mislabelled_series_carry_a_note(self):
        from app.services.macro_interpreter import _DEPRECATED_SERIES

        for code in ("cn_gdp", "cn_inflation", "cn_rate"):
            assert code in _DEPRECATED_SERIES, code
            assert len(_DEPRECATED_SERIES[code]) > 20

    def test_note_reaches_the_snapshot(self):
        from app.services.macro_interpreter import _key_facts

        indicators = [{"code": "cn_rate", "metric": "level", "current_value": 1.51,
                       "unit": "%", "as_of": "2026-05-01"}]
        _key_facts(indicators)
        assert "МЕЖБАНКОВСКАЯ" in indicators[0]["deprecated"]

    def test_interbank_series_is_not_called_a_central_bank_rate(self):
        import json
        import os

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = json.load(open(os.path.join(base, "config", "macro_indicators.json"),
                             encoding="utf-8"))
        items = cfg["indicators"] if isinstance(cfg, dict) and "indicators" in cfg else cfg
        title = next(i["title"] for i in items if i.get("code") == "cn_rate")
        assert "НБК" not in title or "Межбанк" in title
