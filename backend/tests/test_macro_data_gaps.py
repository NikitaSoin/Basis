"""Видимость дыр в макро-данных: пустые ряды и молчащие фидеры.

Оба класса дыр были ТИХИМИ — ряд числится в системе, а данных нет, и никто об этом
не узнаёт. Тесты фиксируют, что теперь такие ряды попадают и в алерт, и в очередь
веб-добора.
"""
from datetime import date, timedelta

from app.models.macro import MacroDataPoint, MacroIndicator
from app.services import macro_ingest as mi
from app.services.macro_data_questions import collect_questions


def _indicator(db, code, *, source_type, frequency="monthly", title=None):
    """Завести показатель, не споткнувшись о засев соседних тестов."""
    existing = db.get(MacroIndicator, code)
    if existing:
        existing.source_type = source_type
        existing.frequency = frequency
    else:
        db.add(MacroIndicator(code=code, title=title or code, unit="%",
                              frequency=frequency, source_type=source_type,
                              metric_types=["level"], country="ru"))
    db.commit()


def _queue_codes(db):
    """Вся очередь, а не первая страница.

    Умолчание collect_questions — 8 вопросов: столько агент осилит за раунд. В общем
    прогоне соседние тесты засевают десятки рядов, и проверяемый уезжает за границу
    страницы — тест падал не на логике, а на размере выдачи.
    """
    return [q["code"] for q in collect_questions(db, limit=500)]


def test_empty_series_is_visible(db):
    """🔴 Ряд заведён, но пуст — самая тихая дыра: проверка возраста его не видела."""
    _indicator(db, "empty_one", source_type="fred")
    stale = mi.check_staleness(db)
    entry = next((s for s in stale if s["code"] == "empty_one"), None)
    assert entry and entry["empty"] is True and entry["last"] is None


def test_empty_series_reaches_the_agent_queue(db):
    """И попадает в очередь добора, несмотря на «свой» фидер: фидер пуст с рождения."""
    _indicator(db, "empty_two", source_type="fred", title="Безработица КНР")
    assert "empty_two" in _queue_codes(db)
    question = next(q for q in collect_questions(db, limit=500)
                    if q["code"] == "empty_two")
    assert "НЕТ НИ ОДНОГО значения" in question["question"]
    # у пустого ряда нет «последней точки», перечислять пропущенные месяцы нечего
    assert question["missing_periods"] == []


def test_long_silent_feeder_stops_blocking_web_search(db):
    """🔴 «Есть свой фидер» ≠ «фидер работает».

    Ряды с source_type=fred стояли мёртвыми месяцами (egress режет TLS до FRED), но
    исключались из веб-добора навсегда именно по наличию фидера — глухая зона.
    """
    _indicator(db, "silent_feed", source_type="fred")
    # молчит вдвое дольше нормы для месячного ряда
    old = date.today() - timedelta(days=200)
    db.add(MacroDataPoint(indicator_code="silent_feed", metric="level",
                          as_of=old, value=1.0, ingested_via="fred"))
    db.commit()
    assert "silent_feed" in _queue_codes(db)


def test_working_feeder_still_blocks_web_search(db):
    """А недавно замолчавший фидер очередь не занимает — он, вероятно, оживёт сам."""
    _indicator(db, "fresh_feed", source_type="fred")
    recent = date.today() - timedelta(days=80)   # чуть больше нормы, далеко до двойной
    db.add(MacroDataPoint(indicator_code="fresh_feed", metric="level",
                          as_of=recent, value=1.0, ingested_via="fred"))
    db.commit()
    assert "fresh_feed" not in _queue_codes(db)


def test_retired_series_is_not_alerted(db):
    """Выведенный из эксплуатации ряд не шумит в алерте каждый прогон."""
    _indicator(db, "budget_balance", source_type="minfin", title="Баланс бюджета")
    db.add(MacroDataPoint(indicator_code="budget_balance", metric="level",
                          as_of=date.today() - timedelta(days=300), value=1.0,
                          ingested_via="minfin"))
    db.commit()
    assert "budget_balance" not in [s["code"] for s in mi.check_staleness(db)]
