"""Тесты агентного контура починки макроданных.

Проверяем НЕ качество поиска (это работа LLM и живых источников), а барьеры, которые
защищают данные платформы: гейт находки, независимость факт-чекера, запрет перезаписи.
Именно они — причина, по которой контур вообще допущен к записи в базу без человека.
"""
import pytest

from app.services.macro_gap_agent import _gate
from app.services.macro_fact_checker import _domain, normalize_period


class TestFindingGate:
    """Гейт добытчика: число обязано быть в реально открытом тексте."""

    SEEN = 'Росстат: безработица в июне 2026 года составила 2,2% от рабочей силы'

    def test_accepts_number_present_in_source(self):
        ok, notes = _gate({"found": True, "source_url": "https://x/y",
                           "values": [{"period": "2026-06-30", "value": 2.2, "unit": "%"}]}, self.SEEN)
        assert ok and not notes

    def test_rejects_invented_number(self):
        """Главный барьер: «правдоподобное» число, которого нет в источнике."""
        ok, notes = _gate({"found": True, "source_url": "https://x/y",
                           "values": [{"period": "2026-06-30", "value": 2.7, "unit": "%"}]}, self.SEEN)
        assert not ok
        assert any("not_in_source" in n for n in notes)

    def test_rejects_period_that_is_not_a_date(self):
        ok, notes = _gate({"found": True, "source_url": "https://x/y",
                           "values": [{"period": "июнь", "value": 2.2}]}, self.SEEN)
        assert not ok
        assert any("bad_period" in n for n in notes)

    def test_honest_not_found_is_not_accepted_as_data(self):
        ok, notes = _gate({"found": False, "note": "нет публикаций"}, self.SEEN)
        assert not ok and notes == ["not_found"]

    def test_comma_and_dot_decimals_both_match(self):
        """Источники пишут «2,2», мы храним 2.2 — расхождение форматов не должно
        выглядеть как выдуманное число."""
        ok, _ = _gate({"found": True, "source_url": "https://x",
                       "values": [{"period": "2026-06-30", "value": 2.2}]}, "значение 2,2%")
        assert ok


class TestFactCheckerIndependence:
    def test_domain_extraction(self):
        assert _domain("https://www.interfax.ru/business/1") == "interfax.ru"
        assert _domain(None) == ""

    def test_period_normalized_to_month_end(self):
        """Месячные ряды хранятся датой конца месяца — «2026-06» должно стать 30-м."""
        assert normalize_period("2026-06") == "2026-06-30"
        assert normalize_period("2026-02") == "2026-02-28"
        assert normalize_period("2026-06-15") == "2026-06-15"
        assert normalize_period("июнь") is None


class TestWriteGuards:
    """Барьеры записи. Здесь цена ошибки максимальна: неверная точка живёт долго."""

    def test_existing_point_is_never_overwritten(self, db):
        from datetime import date

        from app.services import macro_ingest as mi
        from app.services.macro_gap_pipeline import process_finding

        mi.seed_indicators(db)
        mi.upsert_point(db, "key_rate", date(2026, 5, 31), "level", 14.0, ingested_via="cbr")
        db.commit()

        res = process_finding(db, "key_rate", "level",
                              {"period": "2026-05-31", "value": 99.0, "unit": "%"},
                              "https://source", dry_run=True)
        assert res["status"] == "skipped"
        assert res["reason"] == "point_exists"

    def test_implausible_value_is_rejected_before_agent_call(self, db):
        """Фильтр правдоподобия срабатывает ДО факт-чекера — не тратим прогон на мусор."""
        from datetime import date

        from app.services import macro_ingest as mi
        from app.services.macro_gap_pipeline import process_finding

        mi.seed_indicators(db)
        for i, day in enumerate((28, 27, 26, 25, 24, 23, 22, 21)):
            mi.upsert_point(db, "key_rate", date(2026, 1, day), "level", 14.0 + i * 0.05,
                            ingested_via="cbr")
        db.commit()

        res = process_finding(db, "key_rate", "level",
                              {"period": "2026-06-30", "value": 900.0, "unit": "%"},
                              "https://source", dry_run=True)
        assert res["status"] == "rejected"
        assert "implausible" in res["reason"]

    def test_bad_payload_does_not_reach_database(self, db):
        from app.services.macro_gap_pipeline import process_finding
        res = process_finding(db, "key_rate", "level", {"period": None, "value": "нет"},
                              None, dry_run=True)
        assert res["status"] == "skipped"


def test_questions_are_concrete_and_bounded(db):
    """Список вопросов — закрытый и самодостаточный: агент закрывает тикеты, а не
    решает сам, куда идти (иначе перебирает всё подряд и жжёт бюджет)."""
    from app.services import macro_ingest as mi
    from app.services.macro_data_questions import collect_questions

    mi.seed_indicators(db)
    db.commit()
    questions = collect_questions(db, limit=5)
    assert len(questions) <= 5
    for q in questions:
        assert q.get("code") and q.get("question")
        assert q.get("priority") in (1, 2, 3, 4)
        # в тексте вопроса должно быть видно, что именно у нас есть сейчас
        assert len(q["question"]) > 40


class TestSearchAndCountryGuards:
    """Барьеры, найденные на живых прогонах 2026-08-02."""

    def test_feed_search_ranks_by_relevance(self, db):
        """Поиск по ленте не должен отдавать «любое совпавшее слово».

        Было: запрос «PMI России индекс деловой активности» первыми возвращал
        «Трамп допустил захват Гренландии» — совпало слово «России». Агент решал,
        что в ленте пусто, и уходил в веб, сжигая шаги.
        """
        from app.services.macro_gap_tools import _search_our_feed
        res = _search_our_feed(db, "PMI индекс деловой активности", 90, 5)
        # на пустой тестовой базе результатов нет — проверяем контракт, не данные
        assert "error" not in res or res.get("error") != "search_failed"
        for item in res.get("items") or []:
            assert "relevance" in item, "результаты обязаны нести оценку релевантности"

    def test_series_state_carries_country(self, db):
        """Показатель без страны — не показатель.

        Агент нашёл КИТАЙСКИЙ композитный PMI и предложил его в российский ряд:
        число в тексте было, гейт пропустил. Страна должна приходить явно.
        """
        from app.services import macro_ingest as mi
        from app.services.macro_gap_tools import _get_series_state
        mi.seed_indicators(db)
        db.commit()
        state = _get_series_state(db, "pmi_composite")
        assert state.get("country"), "в состоянии ряда обязана быть страна"
        assert "warning" in state


def test_search_budget_is_enforced_on_execution():
    """Лимит поисков должен запрещать ИСПОЛНЕНИЕ, а не только убирать инструмент.

    Модель продолжает вызывать инструмент по памяти из прошлых сообщений: с лимитом 4
    агент сделал ~12 поисков и ушёл искать PMI по Китаю, Японии и Австралии.
    """
    import inspect

    from app.services import agent_runner
    src = inspect.getsource(agent_runner.run_agent)
    assert "search_budget_exhausted" in src, "кап должен отказывать в исполнении"
    assert "_SEARCH_TOOLS" in src


class TestReleaseReviewer:
    """Ревизор выпуска. Главный риск здесь — не ошибиться, а МОЛЧА НЕ СРАБОТАТЬ."""

    def test_claims_survive_schema_change(self):
        """Отбор утверждений не должен зависеть от имён полей тезиса.

        Прецедент 2026-08-02: схема сменилась («detail» → «chain»/«evidence»), ревизор
        с белым списком ключей отработал «успешно», проверив НОЛЬ утверждений. Такой
        отказ не виден ни в логах, ни в срезе.
        """
        from app.services.macro_release_reviewer import _claims_to_check

        for field in ("detail", "evidence", "chain", "полностью_новое_поле"):
            claims = _claims_to_check({"theses": [
                {"claim": "Инфляция повышенная", "tag": "факт",
                 field: "годовая 5,9%, ядро 4-5% SAAR"}]})
            assert claims, f"утверждение потеряно при поле {field!r}"
            assert "5,9%" in claims[0]

    def test_numbers_under_a_judgement_are_still_checked(self):
        """Тег относится к ВЫВОДУ, а не к числам под ним.

        В выпуске #7 тезис с тегом «суждение» опирался на «дефицит 5731 млрд руб.» —
        фактическое число. При отборе «только тег факт» его не проверил бы никто.
        """
        from app.services.macro_release_reviewer import _claims_to_check

        claims = _claims_to_check({"theses": [
            {"claim": "Бюджетный импульс подогревает спрос", "tag": "суждение",
             "evidence": "сальдо −5731 млрд руб., расходы +16,1% г/г"}]})
        assert claims and "5731" in claims[0]

    def test_declared_facts_are_checked_first(self):
        """Бюджет ревизии мал — заявленные факты идут раньше оценок."""
        from app.services.macro_release_reviewer import _claims_to_check

        claims = _claims_to_check({"theses": [
            {"claim": "оценка", "tag": "оценка", "evidence": "рост 7,7% г/г"},
            {"claim": "факт", "tag": "факт", "evidence": "инфляция 5,9%"}]}, limit=1)
        assert claims == ["факт инфляция 5,9%"]

    def test_facts_without_numbers_are_skipped(self):
        from app.services.macro_release_reviewer import _claims_to_check

        assert _claims_to_check({"theses": [
            {"claim": "Экономика охлаждается", "tag": "факт", "chain": "спрос слабеет"}]}) == []


    def test_own_data_is_not_sent_to_external_review(self):
        """Числа из наших рядов не отправляем во внешнюю ревизию.

        Первый живой прогон 2026-08-02 дал два «unsupported» на числах из НАШЕЙ базы:
        внешний источник не повторял их дословно. Это не дефект выпуска, а шум, и он
        стоил платного прогона за штуку.
        """
        from app.services.macro_release_reviewer import _foreign_numbers, _our_numbers

        snap = {"indicators": [{"code": "inflation", "current_value": 5.9}],
                "key_facts": {"Розница": "+9.8% (на 2026-06-30), ускоряется"}}
        ours = _our_numbers(snap)
        assert _foreign_numbers("инфляция 5,9%, розница +9.8% г/г", ours) == []
        # порядковые номера и годы — не данные: «2кв2026» не должен стать «чужим числом»
        assert _foreign_numbers("ВВП вырос в 2кв2026, PMI 50.8 пункта", ours) == ["50.8"]
        # знак в прозе несёт направление, а не арифметику: −14,3% и 14.3 — одна величина
        assert _foreign_numbers("инвестиции -14,3% г/г", ours) == ["-14,3"]
        assert _foreign_numbers("инвестиции -14,3% г/г", ours | {14.3}) == []
        # «4-5%» — диапазон, а не величина −5: дефис не знак
        assert _foreign_numbers("устойчивое ядро 4-5% SAAR", ours) == []
        # 🔴 Цена нефти и курс — самые чувствительные числа выпуска. Без валютных
        # единиц тезис «Urals $60,7/барр.» не попадал в отбор вообще.
        assert _foreign_numbers("Urals подскочил до $60,7/барр.", ours) == ["60,7"]
        assert _foreign_numbers("курс 92 ₽/$", ours) == ["92"]


class TestEventAgent:
    def test_only_methodology_channels_survive(self):
        """Канал входа — закрытый список Части 16.2. Свободная формулировка
        превращает разбор события в пересказ."""
        from app.services.macro_event_agent import _CHANNELS

        assert "логистика" in _CHANNELS and "курс" in _CHANNELS
        assert len(_CHANNELS) == 7

    def test_step_limit_is_configurable(self):
        """Финал event-агента объёмный (факты с цитатами). На потолке пилота (1600)
        ответ обрывался на середине JSON и давал unparseable_final."""
        import inspect

        from app.services import agent_runner, macro_event_agent

        assert "step_max_tokens" in inspect.signature(agent_runner.run_agent).parameters
        assert "step_max_tokens" in inspect.getsource(macro_event_agent.research_event)
