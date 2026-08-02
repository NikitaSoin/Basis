"""Шаг 1 агентного контура: КОД находит проблемы в данных и формулирует вопросы.

🔴 Принцип (план советника, 2026-08-02): агент НЕ решает, куда идти, — он закрывает
тикеты. Свободно блуждающий агент перебирает 264 компании и жжёт бюджет ($1.5–3 и
40–70 минут против 21 цента), а с закрытым списком вопросов каждый исполнитель
отрабатывает за копейки и завершается.

Здесь LLM НЕ участвует вовсе. Обычный код проходит по данным и выписывает, что не так:
- ряд перестал обновляться (месячный показатель молчит 94 дня — это дыра, а не природа);
- «ОТК данных» (11 автопроверок) поднял флаг;
- значение выглядит аномально на фоне собственной истории.

Результат идёт в двух направлениях:
1) в снапшот интерпретатора — модель видит, где данные слабые, и обязана это оговорить
   (методичка v3 требует блок data_flags, а не молчание);
2) в очередь мини-агентам (шаг 2) — каждый вопрос закрывается отдельным дешёвым
   прогоном.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Показатели, ради которых стоит гонять агента. Прогнозный блок методички (Часть 14)
# держится на первых пяти — их протухание бьёт по выпуску напрямую.
_PRIORITY = {
    "key_rate": 1, "inflation": 1, "unemployment": 1, "gdp": 1, "usdrub": 1,
    "inflation_expectations": 2, "budget_balance_ytd": 2, "pmi_composite": 2,
    "nominal_wage": 2, "real_wage": 2, "urals": 2,
}
_DEFAULT_PRIORITY = 3
# Иностранные ряды: полезны для фона, но их протухание не ломает выпуск про РФ.
_LOW_PRIORITY_PREFIX = ("cn_", "us_", "eu_")

# Ряды, которые НАМЕРЕННО заморожены и заменены другими — гонять агента за ними незачем.
# budget_balance (%ВВП) заменён на budget_balance_ytd (млрд ₽, Минфин): пересчитать
# в % ВВП нечем, номинального ВВП в конвейере нет.
_RETIRED = {"budget_balance"}


def _priority(code: str) -> int:
    if code.startswith(_LOW_PRIORITY_PREFIX):
        return 4
    return _PRIORITY.get(code, _DEFAULT_PRIORITY)


def collect_questions(db: Session, limit: int = 8) -> list[dict]:
    """Закрытый список конкретных вопросов к данным, отсортированный по важности.

    Каждый вопрос самодостаточен: что за показатель, что у нас есть сейчас, что именно
    нужно найти. Без этого агент начнёт «улучшать данные вообще».
    """
    questions: list[dict] = []
    questions += _stale_series(db)
    questions += _failed_quality_checks(db)
    questions = _apply_backoff(db, questions)
    questions.sort(key=lambda q: (q["priority"], -q.get("age_days", 0)))
    return questions[:limit]


# Сколько раундов подряд вопрос может не давать результата, прежде чем отступит,
# и на сколько дней он тогда уходит из очереди.
_MAX_FAILS, _BACKOFF_DAYS = 3, 14


def _missing_periods(last: str, frequency: str | None, limit: int = 4) -> list[str]:
    """Каких периодов не хватает после последней точки — списком, до limit штук.

    🔴 Зачем. Вопрос «ряд обновлялся 2026-03-28, найди за пропущенные периоды» агент
    дважды закрыл тем, что принёс РОВНО эту же точку: она первой попадается в поиске,
    формально «значение показателя» найдено. Прогон впустую, а пайплайн отвечает
    point_exists. Названные вслух месяцы («нужны апрель, май, июнь») убирают эту
    неоднозначность.
    """
    try:
        d = date.fromisoformat(str(last))
    except (TypeError, ValueError):
        return []
    freq = (frequency or "monthly").lower()
    step_months = {"quarterly": 3, "monthly": 1}.get(freq)
    if not step_months:
        return []           # недельные/дневные ряды перечислять бессмысленно
    months_ru = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль",
                 "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
    out, today = [], date.today()
    y, m = d.year, d.month
    while len(out) < limit:
        m += step_months
        while m > 12:
            m -= 12
            y += 1
        # Текущий месяц отсекаем: данные за него ещё не опубликованы (выходят в
        # следующем). Просить их — гарантированно отправить агента за несуществующим.
        if (y, m) >= (today.year, today.month):
            break
        out.append(f"{months_ru[m - 1]} {y}")
    return out


def _apply_backoff(db: Session, questions: list[dict]) -> list[dict]:
    """Убрать из очереди вопросы, которые раз за разом не закрываются.

    🔴 Иначе очередь встаёт колом. Часть дыр не закрывается в принципе: Росстат режет
    машинный доступ, китайские ряды — за платным терминалом. Без отступа агент каждую
    ночь тратит прогоны на те же три нерешаемых вопроса, а решаемые до него не доходят:
    лимит раунда маленький намеренно (2 вопроса), и «вечные» съедают его целиком.

    Отступ ВРЕМЕННЫЙ, не отказ: через две недели вопрос вернётся — источник мог
    открыться, ряд мог возобновиться.
    """
    try:
        rows = db.execute(text(
            "SELECT code, fails, last_try FROM macro_question_attempts")).all()
    except Exception:  # noqa: BLE001
        db.rollback()
        return questions        # таблицы ещё нет — работаем как раньше
    now = datetime.now(timezone.utc)
    muted = set()
    for code, fails, last_try in rows:
        if (fails or 0) < _MAX_FAILS or not last_try:
            continue
        if (now - last_try).days < _BACKOFF_DAYS:
            muted.add(code)
    if muted:
        logger.info("data_questions: отложены как неподдающиеся: %s", sorted(muted))
    return [q for q in questions if q["code"] not in muted]


def record_attempt(db: Session, code: str, *, success: bool) -> None:
    """Отметить исход попытки закрыть вопрос. Успех обнуляет счётчик отказов."""
    try:
        db.execute(text(
            "INSERT INTO macro_question_attempts (code, fails, last_try) "
            "VALUES (:c, :f, :t) ON CONFLICT (code) DO UPDATE SET "
            "fails = CASE WHEN :f = 0 THEN 0 ELSE macro_question_attempts.fails + 1 END, "
            "last_try = :t"),
            {"c": code, "f": 0 if success else 1, "t": datetime.now(timezone.utc)})
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.warning("data_questions: попытка не записана (%s)", code, exc_info=True)


def _stale_series(db: Session) -> list[dict]:
    """Ряды, переставшие обновляться. Основной поставщик работы для агента."""
    try:
        from app.services.macro_ingest import check_staleness
    except Exception:  # noqa: BLE001
        return []
    try:
        stale = check_staleness(db)
    except Exception:  # noqa: BLE001
        logger.warning("data_questions: staleness не посчитан", exc_info=True)
        return []
    from app.models.macro import MacroIndicator
    out = []
    for s in stale:
        if s["code"] in _RETIRED:
            continue
        ind = db.get(MacroIndicator, s["code"])
        title = ind.title if ind else s["code"]
        unit = (ind.unit if ind else "") or ""
        country = {"ru": "Россия", "cn": "Китай", "us": "США", "eu": "Еврозона",
                   "world": "мир"}.get(getattr(ind, "country", None),
                                       getattr(ind, "country", None) or "не указана")
        missing = _missing_periods(s["last"], getattr(ind, "frequency", None))
        missing_hint = (f"Нужны периоды: {', '.join(missing)}. " if missing else "")
        out.append({
            "kind": "stale_series",
            "code": s["code"], "metric": s["metric"],
            "missing_periods": missing,
            "priority": _priority(s["code"]),
            "age_days": s["age_days"],
            "have": f"последняя точка {s['last']} ({s['age_days']} дн. назад)",
            "question": (
                f"Показатель «{title}» ({s['code']}, {unit}) ПО СТРАНЕ: {country}. "
                f"У нас обновлялся последний раз {s['last']} — это {s['age_days']} дней "
                f"назад, хотя ряд регулярный. {missing_hint}Значение за {s['last']} у "
                f"нас УЖЕ ЕСТЬ — приносить его повторно бесполезно. Ищи ИМЕННО по этой "
                f"стране и именно этот показатель (похожие названия — другие величины). "
                f"Верни число, дату периода (не дату публикации) и ссылку на источник."
            ),
        })
    return out


def _failed_quality_checks(db: Session) -> list[dict]:
    """Флаги «ОТК данных» — 11 автопроверок, которые уже работают."""
    try:
        from app.services.macro_verification import latest_results
        res = latest_results(db) or {}
    except Exception:  # noqa: BLE001
        return []
    out = []
    for c in res.get("checks") or []:
        if c.get("status") in ("ok", None):
            continue
        # Поля витрины ОТК: key/title/status/message/details (НЕ code/detail —
        # на этом первая версия молча давала пустые строки).
        msg = c.get("message") or c.get("details") or ""
        out.append({
            "kind": "quality_check",
            "code": c.get("key") or "quality",
            "priority": 1 if c.get("status") == "fail" else 2,
            "have": f"{c.get('title')}: {msg}"[:200],
            "question": (
                f"Автопроверка данных «{c.get('title')}» в статусе {c.get('status')}: "
                f"{msg or 'без деталей'}. Проверь по первоисточнику, какое значение "
                f"верное, и приложи ссылку."
            ),
        })
    return out


def anomaly_flags(db: Session, code: str, metric: str = "level", window: int = 24) -> str | None:
    """Резкий выброс относительно собственной истории ряда.

    Отдельно от collect_questions: используется точечно, чтобы не поднимать шум по
    волатильным по природе рядам (недельная инфляция, курс).
    """
    from app.models.macro import MacroDataPoint
    rows = (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).limit(window).all())
    vals = [float(r.value) for r in rows if r.value is not None]
    if len(vals) < 8:
        return None
    last, hist = vals[0], vals[1:]
    med = statistics.median(hist)
    try:
        spread = statistics.pstdev(hist)
    except statistics.StatisticsError:
        return None
    if spread <= 0:
        return None
    z = abs(last - med) / spread
    if z > 4:
        return (f"последнее значение {last} отклоняется от медианы истории {round(med, 2)} "
                f"более чем на 4 стандартных отклонения — проверить, не ошибка ли ввода")
    return None


def summarize_for_prompt(questions: list[dict]) -> list[str]:
    """Короткие строки для секции снапшота — чтобы модель ЗНАЛА о слабых местах."""
    out = []
    for q in questions:
        if q["kind"] == "stale_series":
            out.append(f"{q['code']}: данные устарели — {q['have']}")
        else:
            out.append(f"{q['code']}: {q['have'][:160]}")
    return out


def today() -> date:
    return date.today()
