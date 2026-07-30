"""Целевой ловец недельной инфляции: календарь публикации и валидация извлечения.

Контекст (владелец, 2026-07-30): публикация стабильно в среду во второй половине
дня, но ряд на бою был дырявым — единственным каналом было LLM-извлечение из общей
ленты. Эти тесты держат два инварианта: (1) ловец правильно понимает, за какую
неделю точка уже должна существовать; (2) мусор из ленты (не та неделя, не тот
диапазон) в ряд не попадает.
"""
from datetime import date, datetime

from app.services.macro_weekly_watch import _expected_week_end


def _dt(y, m, d, h):
    return datetime(y, m, d, h, 0)


def test_before_wednesday_expects_previous_week():
    # вторник: свежая среда ещё не наступила — ждём точку за прошлый понедельник
    assert _expected_week_end(_dt(2026, 7, 28, 12)) == date(2026, 7, 20)


def test_wednesday_morning_still_previous_week():
    # среда до 16:00 МСК — релиз ещё не вышел
    assert _expected_week_end(_dt(2026, 7, 29, 12)) == date(2026, 7, 20)


def test_wednesday_evening_expects_this_week():
    assert _expected_week_end(_dt(2026, 7, 29, 17)) == date(2026, 7, 27)


def test_thursday_expects_this_week():
    # именно этот случай пропускал старый критерий «age ≤ 9 дней»: в четверг после
    # невышедшей среды точке прошлой недели 10 дней — а владелец заметил в тот же день
    assert _expected_week_end(_dt(2026, 7, 30, 9)) == date(2026, 7, 27)


def test_next_monday_still_last_published_week():
    assert _expected_week_end(_dt(2026, 8, 3, 9)) == date(2026, 7, 27)


# ── валидация извлечения: два числа релиза, независимые проверки ──────────────
from app.services.macro_weekly_watch import _validate


def test_validate_extracts_both_numbers():
    out = {"found": True, "week_end": "2026-07-27", "wow": 0.04, "yoy": 5.94}
    assert _validate(out, date(2026, 7, 27)) == {"wow": 0.04, "yoy": 5.94}


def test_validate_keeps_yoy_when_wow_is_garbage():
    # класс бага «цена сахара 2,6% записана как недельная инфляция»: мусорное wow
    # отбрасывается, но годовая из того же релиза НЕ теряется
    out = {"found": True, "week_end": "2026-07-27", "wow": 2.6, "yoy": 5.94}
    assert _validate(out, date(2026, 7, 27)) == {"yoy": 5.94}


def test_validate_rejects_wrong_week_entirely():
    out = {"found": True, "week_end": "2026-07-20", "wow": 0.04, "yoy": 5.94}
    assert _validate(out, date(2026, 7, 27)) is None


def test_validate_accepts_partial_release():
    out = {"found": True, "week_end": "2026-07-27", "wow": None, "yoy": 5.94}
    assert _validate(out, date(2026, 7, 27)) == {"yoy": 5.94}
