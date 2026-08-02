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


class TestQuestionBackoff:
    """Неподдающийся вопрос обязан отступать, иначе очередь встаёт колом.

    Часть дыр не закрывается в принципе (Росстат режет машинный доступ, китайские ряды
    за платным терминалом). Лимит раунда — 2 вопроса; без отступа «вечные» съедают его
    каждую ночь, и решаемые дыры до агента не доходят.
    """

    def test_repeated_failures_mute_the_question(self, db):
        from app.services import macro_ingest as mi
        from app.services.macro_data_questions import _MAX_FAILS, _apply_backoff, record_attempt

        mi.seed_indicators(db)
        db.commit()
        qs = [{"code": "pmi_composite", "priority": 2, "kind": "stale_series"}]
        assert _apply_backoff(db, qs) == qs

        for _ in range(_MAX_FAILS):
            record_attempt(db, "pmi_composite", success=False)
        assert _apply_backoff(db, qs) == [], "вопрос обязан уйти из очереди"

    def test_success_clears_the_counter(self, db):
        from app.services.macro_data_questions import _MAX_FAILS, _apply_backoff, record_attempt

        qs = [{"code": "real_wage", "priority": 2, "kind": "stale_series"}]
        for _ in range(_MAX_FAILS):
            record_attempt(db, "real_wage", success=False)
        assert _apply_backoff(db, qs) == []
        record_attempt(db, "real_wage", success=True)   # источник открылся
        assert _apply_backoff(db, qs) == qs


def test_release_has_a_soft_time_budget():
    """Затянувшийся выпуск обязан отбрасывать НЕОБЯЗАТЕЛЬНОЕ, а не наползать на
    следующий крон: выпуск стоит в 07:15, agent_pilot — в 07:40, и вдвоём они уже
    вешали БД. Ревизия — замечания, а не содержание, ею и жертвуем."""
    import inspect

    from app.services import macro_interpreter as mi
    src = inspect.getsource(mi.generate)
    assert "_SOFT_BUDGET_SEC" in src
    assert mi._SOFT_BUDGET_SEC <= 25 * 60, "бюджет должен укладываться в окно до 07:40"


class TestMissingPeriodsInQuestion:
    """Вопрос обязан называть недостающие месяцы поимённо.

    Дважды подряд агент закрывал вопрос тем, что приносил РОВНО последнюю имеющуюся
    точку: она первой попадается в поиске, формально «значение найдено». Прогон
    впустую, пайплайн отвечает point_exists, счётчик отказов растёт.
    """

    def test_lists_months_after_the_last_point(self):
        from app.services.macro_data_questions import _missing_periods
        out = _missing_periods("2026-03-28", "monthly", limit=3)
        assert out == ["апрель 2026", "май 2026", "июнь 2026"]

    def test_current_month_is_never_requested(self):
        """Данные за текущий месяц выходят в следующем — просить их бессмысленно."""
        from datetime import date

        from app.services.macro_data_questions import _missing_periods
        today = date.today()
        months_ru = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль",
                     "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
        current = f"{months_ru[today.month - 1]} {today.year}"
        assert current not in _missing_periods("2020-01-31", "monthly", limit=12)

    def test_quarterly_series_steps_by_three_months(self):
        from app.services.macro_data_questions import _missing_periods
        assert _missing_periods("2025-12-31", "quarterly", limit=2) == ["март 2026", "июнь 2026"]

    def test_weekly_series_is_not_enumerated(self):
        """Недельный ряд перечислять бессмысленно — вопрос останется общим."""
        from app.services.macro_data_questions import _missing_periods
        assert _missing_periods("2026-03-28", "weekly") == []


class TestUnknownTickersAreStripped:
    """Тикер из выпуска становится КНОПКОЙ перехода на карточку.

    Живой выпуск 2026-08-02 назвал «VTB» и «LNTE» (на бирже — VTBR и LENT): две
    ссылки в никуда прямо в тексте. Гейт их находил, но выпуск публиковался как есть.
    """

    SNAP = {"context": {"platform_tickers": ["SBER", "VTBR", "LENT"]}}

    def test_unknown_ticker_is_removed_and_reported(self):
        from app.services.macro_release_gate import strip_unknown_tickers
        sections = {"sectors": [{"sector": "Финансы", "winners": ["SBER", "VTB"],
                                 "losers": ["LNTE"]}]}
        removed = strip_unknown_tickers(sections, self.SNAP)
        assert sorted(removed) == ["LNTE", "VTB"]
        assert sections["sectors"][0]["winners"] == ["SBER"]
        assert sections["sectors"][0]["losers"] == []

    def test_no_guessing_of_similar_tickers(self):
        """VTB похоже на VTBR, но подстановка по догадке однажды подставит не ту
        компанию — убираем, а не «исправляем»."""
        from app.services.macro_release_gate import strip_unknown_tickers
        sections = {"sectors": [{"sector": "Финансы", "winners": ["VTB"]}]}
        strip_unknown_tickers(sections, self.SNAP)
        assert sections["sectors"][0]["winners"] == []

    def test_empty_coverage_changes_nothing(self):
        """Нет списка покрытия — не трогаем выпуск вовсе, иначе вычистим всё."""
        from app.services.macro_release_gate import strip_unknown_tickers
        sections = {"sectors": [{"sector": "Финансы", "winners": ["VTB"]}]}
        assert strip_unknown_tickers(sections, {}) == []
        assert sections["sectors"][0]["winners"] == ["VTB"]


class TestGateDistinguishesHistoryFromForeignNumbers:
    """Число из истории ряда — показ динамики, а не «взято из чужого источника».

    Живой выпуск 2026-08-02 дал 3 таких замечания из 5 («ожидания выросли с 13,0 до
    14,7»). Шум обесценивает гейт: на реальные ошибки перестают смотреть.
    """

    SNAP = {"indicators": [{"code": "inflation_expectations", "metric": "level",
                            "current_value": 14.7,
                            "series": [{"d": "2026-06-30", "v": 13.0},
                                       {"d": "2026-05-31", "v": 12.4}]}]}

    def test_past_value_is_flagged_softly(self):
        from app.services.macro_release_gate import _check_numbers_vs_facts
        notes = _check_numbers_vs_facts(
            "инфляционные ожидания 13,0% месяцем ранее", self.SNAP)
        assert notes == ["historical_value_cited:inflation_expectations=13.0"]

    def test_number_from_nowhere_is_still_a_mismatch(self):
        from app.services.macro_release_gate import _check_numbers_vs_facts
        notes = _check_numbers_vs_facts("инфляционные ожидания 19,5%", self.SNAP)
        assert notes == ["number_mismatch:inflation_expectations=19.5!=14.7"]

    def test_current_value_passes_clean(self):
        from app.services.macro_release_gate import _check_numbers_vs_facts
        assert _check_numbers_vs_facts("инфляционные ожидания 14,7%", self.SNAP) == []


def test_question_carries_unit_and_magnitude(db):
    """Вопрос обязан нести ЕДИНИЦУ ряда и примеры последних значений.

    Агент дважды приносил ТЕМП роста («+10,1% г/г») в ряд, который хранит УРОВЕНЬ
    (110 216 ₽), и наоборот. По единице и порядку величины ошибиться труднее, чем
    по одному названию показателя.
    """
    from app.services import macro_ingest as mi
    from app.services.macro_data_questions import collect_questions

    mi.seed_indicators(db)
    db.commit()
    for q in collect_questions(db, limit=6):
        if q.get("kind") != "stale_series":
            continue
        assert "ЕДИНИЦА РЯДА" in q["question"], q["code"]
        assert "последние известные значения" in q["question"], q["code"]


class TestFactCheckerGetsHumanNames:
    """Чекеру нужно ЧЕЛОВЕЧЕСКОЕ имя показателя, а не служебный код.

    🔴 В задании стояло «показатель "real_wage"» — агент шёл искать в веб буквально
    это и ничего не находил. Добытчик при этом получал нормальный вопрос с названием
    и страной, находил число за один поиск, а чекер отбраковывал его как
    неподтверждённое: контур работал вхолостую.
    """

    def test_describe_returns_title_country_unit(self, db):
        from app.services import macro_ingest as mi
        from app.services.macro_fact_checker import _describe

        mi.seed_indicators(db)
        db.commit()
        title, country, unit = _describe(db, "real_wage")
        assert title and title != "real_wage"
        assert country == "Россия"
        assert unit == "%"

    def test_unknown_code_degrades_to_the_code(self, db):
        from app.services.macro_fact_checker import _describe
        assert _describe(db, "no_such_indicator")[0] == "no_such_indicator"

    def test_task_carries_the_title_not_only_the_code(self, db, monkeypatch):
        """Проверяем сам текст задания: код в нём допустим лишь как пометка «не ищи
        по нему», а искать чекер должен по названию."""
        import app.services.macro_fact_checker as fc
        from app.services import macro_ingest as mi

        mi.seed_indicators(db)
        db.commit()
        captured = {}

        def fake_run_agent(db_, **kw):
            captured["task"] = kw.get("task")
            return {"result": {"verdict": "unverified"}, "tokens_used": 0}

        monkeypatch.setattr(fc, "run_agent", fake_run_agent)
        fc.check_finding(db, "real_wage", "2026-05-31", 4.5, "%", "https://x.ru/1")
        task = captured["task"]
        assert "Реальная зарплата" in task
        assert "Россия" in task
        assert "не по служебному коду" in task


class TestFeedSearchPrecision:
    """Поиск по ленте: подстрока вместо слова наполняла выдачу мусором.

    🔴 На запрос про зарплаты за МАЙ первым шёл «в Москве запретят МАЙнинг» — «%май%»
    совпало внутри слова. Агент принимал такую выдачу за материал по теме и не уходил
    в веб, где данные и лежат.
    """

    def test_short_word_does_not_match_inside_another(self, db):
        from app.services.macro_gap_tools import _search_our_feed
        from sqlalchemy import text

        db.execute(text(
            "INSERT INTO chronicle_entries (kind, title, summary, source_url, "
            "published_at, created_at) VALUES ('news', 'В Москве запретят майнинг', "
            "'про майнинг', 'https://x.ru/1', now(), now())"))
        db.execute(text(
            "INSERT INTO chronicle_entries (kind, title, summary, source_url, "
            "published_at, created_at) VALUES ('news', 'Зарплаты в мае выросли', "
            "'Росстат: май 2026', 'https://x.ru/2', now(), now())"))
        db.commit()
        titles = [i["title"] for i in
                  (_search_our_feed(db, "зарплаты май", 30, 5).get("items") or [])]
        assert not any("майнинг" in t for t in titles)

    def test_empty_result_says_so_explicitly(self, db):
        """Пустая выдача честнее слабых совпадений: по ней агент сразу идёт в веб."""
        from app.services.macro_gap_tools import _search_our_feed

        res = _search_our_feed(db, "предельная склонность к импорту Мадагаскара", 30, 5)
        assert res.get("items") == []
        assert "вебе" in (res.get("note") or "")

    def test_query_with_regex_chars_does_not_crash(self, db):
        """Слово из запроса идёт в шаблон регулярки: «5,84%» или «(инФОМ)» не должны
        ронять поиск целиком."""
        from app.services.macro_gap_tools import _search_our_feed

        res = _search_our_feed(db, "инфляция 5,84% (инФОМ) [июль]", 30, 5)
        assert "error" not in res or res.get("error") != "search_failed"


class TestPeriodMustBeNewer:
    """Значение за БОЛЕЕ РАННИЙ период дыру не закрывает — оно её имитирует.

    🔴 Прецедент: по композитному PMI первые ссылки выдачи дают «47,8 в июле» — это
    июль ПРОШЛОГО года. Рядом с апрельскими 49,1 число выглядит совершенно
    правдоподобно, и ни гейт цитаты, ни проверка правдоподобия его не остановят.
    """

    def test_last_year_value_is_rejected(self, db):
        from datetime import date

        from app.services import macro_ingest as mi
        from app.services.macro_gap_pipeline import process_finding

        from app.models.macro import MacroDataPoint

        mi.seed_indicators(db)
        db.query(MacroDataPoint).filter_by(indicator_code="pmi_composite").delete()
        db.commit()
        mi.upsert_point(db, "pmi_composite", date(2026, 4, 28), "level", 49.1,
                        ingested_via="file")
        db.commit()
        res = process_finding(db, "pmi_composite", "level",
                              {"period": "2025-07-31", "value": 47.8, "unit": "ед"},
                              "https://source", dry_run=True)
        assert res["status"] == "rejected"
        assert "period_not_newer" in res["reason"]

    def test_fresh_period_passes_the_check(self, db, monkeypatch):
        from datetime import date

        from app.models.macro import MacroDataPoint
        from app.services import macro_ingest as mi
        from app.services import macro_gap_pipeline as gp
        from app.services.macro_gap_pipeline import process_finding

        mi.seed_indicators(db)
        # Тестовая база общая на сессию: соседние тесты (и apply_known_corrections)
        # кладут в этот же ряд более свежие точки — проверяли бы не то.
        db.query(MacroDataPoint).filter_by(indicator_code="pmi_composite").delete()
        db.commit()
        mi.upsert_point(db, "pmi_composite", date(2026, 4, 28), "level", 49.1,
                        ingested_via="file")
        db.commit()
        monkeypatch.setattr(gp, "_plausible", lambda *a, **k: (True, "тест"))
        monkeypatch.setattr("app.services.macro_fact_checker.check_finding",
                            lambda *a, **k: {"verdict": "confirmed", "source_url": "https://y"})
        res = process_finding(db, "pmi_composite", "level",
                              {"period": "2026-05-31", "value": 48.2, "unit": "ед"},
                              "https://source", dry_run=True)
        assert res["status"] == "would_write"


class TestWebSearchResilience:
    """Веб-поиск — единственный канал для всех агентов: ключа Tavily нет, работает
    только парсинг DuckDuckGo. Его разовый ConnectTimeout без повтора равен «в вебе
    ничего нет», и агент отказывается от вопроса, который на самом деле решается.
    """

    def test_retries_before_giving_up(self, monkeypatch):
        from app.services import agent_web

        calls = {"n": 0}

        class _Resp:
            text = '<a class="result__a" href="https://x.ru/1">Заголовок</a>'
            def raise_for_status(self): pass

        class _C:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get(self, *a, **kw):
                calls["n"] += 1
                if calls["n"] < 3:
                    raise TimeoutError("ConnectTimeout")
                return _Resp()

        monkeypatch.setattr(agent_web, "_client", lambda: _C())
        monkeypatch.setattr(agent_web.time, "sleep", lambda *_: None)
        res = agent_web._search_ddg("что угодно", 3)
        assert calls["n"] == 3, "должен повторить, а не сдаться с первой ошибки"
        assert res.get("results"), "после успешной попытки результаты обязаны вернуться"

    def test_gives_up_honestly_after_all_attempts(self, monkeypatch):
        from app.services import agent_web

        class _C:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get(self, *a, **kw): raise TimeoutError("ConnectTimeout")

        monkeypatch.setattr(agent_web, "_client", lambda: _C())
        monkeypatch.setattr(agent_web.time, "sleep", lambda *_: None)
        res = agent_web._search_ddg("что угодно", 3)
        assert res.get("error") == "search_unavailable"


class TestOnlyAgentSolvableQuestions:
    """Агенту не поручаем ряды, у которых есть СВОЙ машинный загрузчик.

    🔴 Проверено на живых случаях: сводный индекс чёрных металлов завис на 02.07 —
    наш синк исправен, товарные позиции с ТОЙ ЖЕ страницы приходят ежедневно, а график
    композитного индекса источник просто не обновляет. Ряды КНР — прекращённые серии
    OECD. В обоих случаях агент жёг бы прогоны на том, чего нет.
    """

    def test_series_with_a_feeder_is_not_queued(self, db):
        from app.services import macro_ingest as mi
        from app.services.macro_data_questions import _has_own_feeder

        mi.seed_indicators(db)
        db.commit()
        assert _has_own_feeder(db, "metaltorg_steel_index") is True
        assert _has_own_feeder(db, "cn_gdp") is True

    def test_rosstat_stays_in_the_queue(self, db):
        """Росстат закрыт машинно (WAF) — там поиск реально помогает, и агент уже
        закрывал этим безработицу и реальную зарплату."""
        from app.services import macro_ingest as mi
        from app.services.macro_data_questions import _has_own_feeder

        mi.seed_indicators(db)
        db.commit()
        assert _has_own_feeder(db, "real_wage") is False
        assert _has_own_feeder(db, "pmi_composite") is False
