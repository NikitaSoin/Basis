"""Отраслевые показатели, которых нет у парсеров — через агента-добытчика.

🔴 ЗАЧЕМ, ЕСЛИ ЕСТЬ ПАРСЕРЫ. Часть источников открылась с боевого IP (Росавиация,
ФАС, ФТС, СПбМТСБ — проверено 2026-08-08), но числа с них ПАРСЕРОМ не берутся: в
HTML одна навигация, данные подгружаются скриптом, у биржи готовый xls отдаёт 403.
Писать парсер под каждый такой сайт дорого и хрупко — он ломается от смены вёрстки,
о чём в этом же модуле уже есть предупреждение по СО ЕЭС.

Добытчику всё равно, где лежит число: он ищет и приносит факт со ссылкой и периодом.

🔴 НО ЧИСЛО ИЗ ВЕБА СЛАБЕЕ ЧИСЛА С ОФИЦИАЛЬНОЙ СТРАНИЦЫ, и ряды — основа всех
расчётов платформы. Поэтому здесь три ограничения, которых нет у парсеров:
  1. пишем ТОЛЬКО в показатели, у которых нет живого парсера (не конкурируем с ним);
  2. помечаем происхождение отдельно — `ingested_via='scout'`, чтобы такое значение
     было видно в ряду и его можно было отозвать одним запросом;
  3. НЕ переписываем существующие точки (общее правило `_upsert_point`) и не трогаем
     ряды, которые участвуют в расчёте справедливой цены.
Это осознанный размен: лучше отмеченное как менее надёжное число, чем дыра в ряду —
но не ценой того, чтобы оно молча притворялось официальным.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Показатель → что искать. Только те, где парсер молчит: сюда НЕ входят ряды СО ЕЭС,
# ЕРЗ и ЦБ — их берут парсеры, и добытчик им не конкурент.
SCOUT_TARGETS: list[dict] = [
    {"code": "sec_air_passengers", "title": "Пассажиропоток авиакомпаний России",
     "unit": "млн человек", "unit_words": ["млн", "миллион"], "sane": (1, 200),
     "need": "Пассажиропоток российских авиакомпаний за последний завершённый период "
             "(месяц или год) по данным Росавиации: сколько миллионов пассажиров "
             "перевезено и за какой именно период."},
    {"code": "sec_steel_excise_price", "title": "Цена сляба для акциза на сталь (ФАС)",
     # 🔴 ФАС публикует этот показатель в ДОЛЛАРАХ за тонну. Сухой прогон принёс
     # 489.8 — при «руб/т» это абсурд (сляб стоит десятки тысяч рублей), то есть
     # чужая единица под верным названием: ровно тот способ, которым ряд врёт
     # незаметно. Единицу фиксируем правильную и проверяем диапазоном.
     "unit": "$/т", "unit_words": ["долл", "usd", "$"], "sane": (200, 2000),
     "need": "Показатель для расчёта акциза на жидкую сталь по данным ФАС России: "
             "среднемесячная цена сляба за последний опубликованный месяц."},
    {"code": "sec_fuel_exchange_price", "title": "Биржевая цена бензина АИ-92 (СПбМТСБ)",
     "unit": "руб/т", "unit_words": ["руб", "₽"], "sane": (20000, 150000),
     "need": "Биржевая цена бензина АИ-92 на СПбМТСБ (европейская часть России) на "
             "последнюю дату торгов."},
]

_PERIOD_RE = re.compile(r"(20\d\d)[-.\s]*(\d{1,2})?")


def _parse_period(raw: str) -> date | None:
    """Дата точки ряда из человеческого описания периода. Без даты значение не
    записываем: ряд без времени бесполезен и опасен (см. фикс macro_analytics, где
    документу неизвестного возраста подставляли случайную дату)."""
    m = _PERIOD_RE.search(raw or "")
    if not m:
        return None
    year = int(m.group(1))
    if year < 2015 or year > date.today().year:
        return None
    month = int(m.group(2)) if m.group(2) and 1 <= int(m.group(2)) <= 12 else 0
    if not month:
        # месяц СЛОВОМ («июль 2026») — самый частый способ записи периода в русских
        # источниках. Без него всё сваливалось в декабрь, то есть точка ряда вставала
        # не туда: значение верное, дата выдуманная — худший вид ошибки в ряду.
        from app.services.geo_digest import _MONTHS
        low = (raw or "").lower()
        for name, idx in _MONTHS.items():
            if name in low:
                month = idx
                break
    month = month or 12
    day = 28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31
    return date(year, month, min(day, 31))


def _parse_value(raw: str) -> float | None:
    """Число из строки вида «102,4 млн человек». Разряды пробелом, запятая-разделитель."""
    m = re.search(r"(\d{1,3}(?:[\s ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)", raw or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _has_fresh(db: Session, code: str, days: int = 45) -> bool:
    row = db.execute(text("""
        SELECT max(as_of) FROM macro_data_points WHERE indicator_code = :c
    """), {"c": code}).fetchone()
    return bool(row and row[0] and (date.today() - row[0]).days <= days)


def run_scout(db: Session, only_code: str | None = None, dry: bool = False) -> dict:
    """Добрать показатели, которых нет у парсеров. Молчит честно, если не нашлось."""
    from app.services.card_rewriter import scout_dossier
    from app.services.sector_data_sync import _upsert_point

    stats = {"checked": 0, "written": 0, "skipped_fresh": 0, "not_found": 0,
             "details": []}
    for t in SCOUT_TARGETS:
        if only_code and t["code"] != only_code:
            continue
        stats["checked"] += 1
        if _has_fresh(db, t["code"]):
            stats["skipped_fresh"] += 1
            continue
        d = scout_dossier(db, "", t["need"], web_calls=3)
        facts = d.get("facts") or []
        if not facts:
            stats["not_found"] += 1
            stats["details"].append(f"{t['code']}: добытчик ничего не принёс")
            continue
        f = facts[0]
        val = _parse_value(str(f.get("value")))
        when = _parse_period(str(f.get("period")))
        raw_val = str(f.get("value") or "")

        # 🔴 Дата из БУДУЩЕГО. Конвенция «конец месяца» на текущем месяце даёт
        # 31 августа при сегодняшнем 9-м — точка ряда, которой ещё не существует.
        # Сухой прогон это и показал (АИ-92 «на 2026-08-31»). Подрезаем до сегодня.
        if when and when > date.today():
            when = date.today()

        # 🔴 ЕДИНИЦА. Самый незаметный способ соврать — верное название и чужая
        # единица: ФАС даёт цену сляба в ДОЛЛАРАХ, и «489.8 руб/т» выглядело бы
        # правдоподобно в таблице. Проверяем двумя независимыми способами: слово
        # единицы в ответе добытчика и диапазон правдоподобия.
        lo, hi = t.get("sane", (None, None))
        words = t.get("unit_words") or []
        low_raw = raw_val.lower()
        if words and not any(w in low_raw for w in words):
            stats["not_found"] += 1
            stats["details"].append(
                f"{t['code']}: единица не подтверждена в ответе ({raw_val!r}, "
                f"ждём {words}) — не записываю")
            continue
        if val is not None and lo is not None and not (lo <= val <= hi):
            stats["not_found"] += 1
            stats["details"].append(
                f"{t['code']}: значение {val} вне правдоподобного диапазона "
                f"{lo}–{hi} {t['unit']} — похоже на чужую единицу, не записываю")
            continue

        if val is None or when is None:
            stats["not_found"] += 1
            stats["details"].append(
                f"{t['code']}: факт есть, но не разобран (value={f.get('value')!r}, "
                f"period={f.get('period')!r}) — записывать не буду")
            continue
        stats["details"].append(f"{t['code']}: {val} на {when} ({f.get('source')})")
        if dry:
            continue
        db.execute(text("""
            INSERT INTO macro_indicators (code, title, unit)
            VALUES (:c, :t, :u) ON CONFLICT (code) DO NOTHING
        """), {"c": t["code"], "t": t["title"], "u": t["unit"]})
        if _upsert_point(db, t["code"], val, when):
            # происхождение помечаем явно: значение найдено агентом в вебе, а не
            # снято с официальной страницы — это видно в ряду и отзывается запросом
            db.execute(text("""
                UPDATE macro_data_points SET ingested_via = 'scout'
                WHERE indicator_code = :c AND as_of = :d AND metric = 'level'
            """), {"c": t["code"], "d": when})
            stats["written"] += 1
        db.commit()
    logger.info("sector_scout: %s", stats)
    return stats
