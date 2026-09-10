"""Проверки пайплайна «снапшоты для SEO-страниц».

Повод (найдено сессией «SEO: свежесть», 11.09.2026): снапшоты
bonds/funds/futures/spot обновлялись руками и последний раз — 30 июля. Около
3900 страниц шесть недель отдавали данные шестинедельной давности, и при этом
ВСЁ было зелёным: сборка проходила, страницы существовали, тесты молчали.

🔴 Дефект класса «ломается не наличие данных, а их возраст». Наличие проверить
легко, поэтому его и проверяли; возраст не проверял никто. Отсюда правило: у
любого регулярно обновляемого артефакта возраст обязан быть измеряемым, а
отсутствие отметки времени — само по себе находка, а не «нет данных».
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.quality.contract import Check, CheckOutcome, Severity, fail, ok, skip

_COHORT: dict[str, int] | None = None

ROOT = Path(__file__).resolve().parents[4]
SNAPSHOT_DIR = ROOT / "frontend" / "Basis" / "scripts" / "data"

# Порог свежести в днях — по природе данных, а не единый для всех.
# Биржевой срез, простоявший неделю, показывает цену прошлой недели; решение ЦБ
# меняется раз в полтора месяца, и требовать от него ежедневности бессмысленно.
MAX_AGE_DAYS: dict[str, int] = {
    "bonds-snapshot.json": 7,
    "funds-snapshot.json": 7,
    "futures-snapshot.json": 7,
    "spot-snapshot.json": 7,
    "indices-snapshot.json": 7,
    "earnings-snapshot.json": 7,
    "fair-value-snapshot.json": 7,
    "index-composition-snapshot.json": 30,
    "news-snapshot.json": 3,
    "macro-snapshot.json": 7,
    "macro-series-snapshot.json": 7,
    "sectors-snapshot.json": 7,
    "dividend-calendar-snapshot.json": 14,
    "cb-meetings-snapshot.json": 45,
    "cb-forecast-snapshot.json": 45,
    "geo-barometer-snapshot.json": 14,
    "institutions-snapshot.json": 30,
    "report-slugs.json": 14,
}
DEFAULT_MAX_AGE_DAYS = 14

# Сколько записей снапшот обязан нести, чтобы считаться наполненным. Ноль строк
# при коде 200 — типовой отказ фида, который тоже выглядит зелёным.
MIN_ROWS: dict[str, int] = {
    "bonds-snapshot.json": 1000, "futures-snapshot.json": 100,
    "funds-snapshot.json": 50, "spot-snapshot.json": 3,
    "news-snapshot.json": 20, "earnings-snapshot.json": 20,
}
DEFAULT_MIN_ROWS = 1

# 🔴 Артефакты, которым свежесть по смыслу НЕ нужна. report-slugs.json — не
# снимок данных, а РЕЕСТР АДРЕСОВ («TICKER|дата|тип» → слаг страницы разбора):
# его назначение ровно в том, чтобы не меняться, иначе проиндексированные
# страницы начнут переезжать. Старая запись здесь — признак исправной работы,
# а не протухания. Отдельно: структура плоская, ключи верхнего уровня — сами
# записи реестра, поэтому дописать туда «fetched_at» нельзя: потребитель обойдёт
# Object.entries и примет отметку за ещё один занятый слаг.
# (Разобрано с сессией «SEO: свежесть», 11.09.2026.)
IMMUTABLE_ARTIFACTS = {"report-slugs.json"}

# Насколько субъект может отстать от МЕДИАНЫ по папке, прежде чем это станет
# находкой. Наблюдение той же сессии: у bonds/funds/futures/spot возраст был
# 45 дней, а у соседних файлов — сутки. Разброс внутри папки говорит, что сломан
# не источник, а шаг обновления, — и виден даже там, где абсолютный порог высок.
MAX_SPREAD_DAYS = 14
MIN_COHORT = 3


def snapshot_files() -> list[str]:
    return sorted(p.name for p in SNAPSHOT_DIR.glob("*.json"))


def load_snapshot(name: str) -> dict | list | None:
    path = SNAPSHOT_DIR / name
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def fetched_at(doc: Any) -> datetime | None:
    """Отметка времени: в корне или в meta — оба формата в ходу."""
    if not isinstance(doc, dict):
        return None
    raw = doc.get("fetched_at") or (doc.get("meta") or {}).get("fetched_at") \
        or doc.get("generated_at") or (doc.get("meta") or {}).get("generated_at")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def row_count(doc: Any) -> int | None:
    if isinstance(doc, list):
        return len(doc)
    if not isinstance(doc, dict):
        return None
    for key in ("rows", "series", "indices", "items"):
        node = doc.get(key)
        if isinstance(node, (list, dict)):
            return len(node)
    if doc and all(isinstance(k, str) for k in doc):   # словарь-справочник
        return len(doc)
    return None


# ─────────────────────────── проверки ───────────────────────────

def cohort_ages(exclude: set[str] | None = None) -> dict[str, int]:
    """Возраст в днях по всем снапшотам папки, у которых есть отметка времени."""
    global _COHORT
    if _COHORT is None:
        ages: dict[str, int] = {}
        now = datetime.now(timezone.utc)
        for name in snapshot_files():
            if name in IMMUTABLE_ARTIFACTS:
                continue
            stamp = fetched_at(load_snapshot(name))
            if stamp is not None:
                ages[name] = (now - stamp).days
        _COHORT = ages
    return {k: v for k, v in _COHORT.items() if not exclude or k not in exclude}


def _c_has_timestamp(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """🔴 Отсутствие отметки времени — НАХОДКА, а не «нечего проверять».
    Артефакт без возраста нельзя признать ни свежим, ни протухшим; именно в этой
    слепой зоне и прожили шесть недель страницы облигаций."""
    doc = payload["doc"]
    if doc is None:
        yield fail(C_HAS_TIMESTAMP, subject, "файл не читается как JSON")
        return
    if subject in IMMUTABLE_ARTIFACTS:
        yield skip(C_HAS_TIMESTAMP, subject,
                   "реестр адресов, а не снимок данных: отметка времени по смыслу не нужна "
                   "(и не помещается — плоская структура, ключи верхнего уровня суть записи)",
                   by_design=True)
        return
    if fetched_at(doc) is None:
        yield fail(C_HAS_TIMESTAMP, subject,
                   "нет отметки fetched_at — возраст данных измерить нечем")
    else:
        yield ok(C_HAS_TIMESTAMP, subject)


def _c_freshness(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    doc, today = payload["doc"], payload["today"]
    if subject in IMMUTABLE_ARTIFACTS:
        yield skip(C_SNAP_FRESHNESS, subject,
                   "реестр адресов: его назначение — НЕ меняться, старая запись здесь "
                   "признак исправной работы", by_design=True)
        return
    stamp = fetched_at(doc)
    if stamp is None:
        yield skip(C_SNAP_FRESHNESS, subject, "нет отметки времени (см. snap.has_timestamp)")
        return
    age = (datetime.now(timezone.utc) - stamp).days
    limit = MAX_AGE_DAYS.get(subject, DEFAULT_MAX_AGE_DAYS)
    if age > limit:
        yield fail(C_SNAP_FRESHNESS, subject,
                   f"данные собраны {stamp.date()} — {age} дн. назад при пороге {limit}",
                   age_days=age, limit=limit, fetched_at=stamp.isoformat())
    else:
        yield ok(C_SNAP_FRESHNESS, subject, age_days=age, limit=limit)


def _c_not_empty(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Ноль записей при успешном ответе — типовой тихий отказ фида."""
    doc = payload["doc"]
    count = row_count(doc)
    if count is None:
        yield skip(C_NOT_EMPTY, subject, "не удалось определить, что считать записями")
        return
    floor = MIN_ROWS.get(subject, DEFAULT_MIN_ROWS)
    if count < floor:
        yield fail(C_NOT_EMPTY, subject,
                   f"{count} записей при ожидаемых от {floor} — похоже на пустой ответ источника",
                   count=count, floor=floor)
    else:
        yield ok(C_NOT_EMPTY, subject, count=count)


def _c_declared_count(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Объявленное count против фактического числа строк.

    🔴 Из памяти проекта: лог сборки печатал длину массива, а в файл уходило на 25
    записей меньше — «N URL» в отчёте не доказывало ничего про файл."""
    doc = payload["doc"]
    if not isinstance(doc, dict):
        yield skip(C_DECLARED_COUNT, subject, "нет объявленного count")
        return
    declared = doc.get("count", (doc.get("meta") or {}).get("count"))
    actual = row_count(doc)
    if not isinstance(declared, int) or actual is None:
        yield skip(C_DECLARED_COUNT, subject, "нет объявленного count")
        return
    if declared != actual:
        yield fail(C_DECLARED_COUNT, subject,
                   f"объявлено {declared} записей, в файле {actual}",
                   declared=declared, actual=actual)
    else:
        yield ok(C_DECLARED_COUNT, subject, count=actual)


def _c_age_spread(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """Отставание от соседей по папке.

    Абсолютный порог не ловит случай, когда у файла он законно высок; разброс —
    ловит. Половина папки свежая, половина месячной давности → сломан не
    источник, а шаг обновления."""
    if subject in IMMUTABLE_ARTIFACTS:
        yield skip(C_AGE_SPREAD, subject, "реестр адресов, в когорту не входит", by_design=True)
        return
    stamp = fetched_at(payload["doc"])
    if stamp is None:
        yield skip(C_AGE_SPREAD, subject, "нет отметки времени (см. snap.has_timestamp)")
        return
    # Когорта — файлы с ТЕМ ЖЕ ритмом обновления (одинаковый порог свежести), а
    # не весь каталог: в scripts/data лежат и биржевые срезы, и справочники, и
    # реестры, и медиана по каталогу смешала бы разные ритмы. Каталог целиком —
    # запасной вариант, когда своя группа слишком мала (предупреждение сессии
    # «SEO: свежесть», 11.09.2026).
    ages = cohort_ages(exclude={subject})
    limit = MAX_AGE_DAYS.get(subject, DEFAULT_MAX_AGE_DAYS)
    same_rhythm = {n: a for n, a in ages.items()
                   if MAX_AGE_DAYS.get(n, DEFAULT_MAX_AGE_DAYS) == limit}
    basis = "группе того же ритма" if len(same_rhythm) >= MIN_COHORT else "папке"
    pool = same_rhythm if len(same_rhythm) >= MIN_COHORT else ages
    others = sorted(pool.values())
    if len(others) < MIN_COHORT:
        yield skip(C_AGE_SPREAD, subject, f"соседей с отметкой времени всего {len(others)}")
        return
    median = others[len(others) // 2]
    age = (datetime.now(timezone.utc) - stamp).days
    if age - median > MAX_SPREAD_DAYS:
        yield fail(C_AGE_SPREAD, subject,
                   f"отстал от соседей по {basis}: {age} дн. против медианных {median} дн. "
                   f"— похоже, сломан шаг обновления, а не источник",
                   age_days=age, median_days=median, cohort=len(others), basis=basis)
    else:
        yield ok(C_AGE_SPREAD, subject, age_days=age, median_days=median, basis=basis)


C_HAS_TIMESTAMP = Check("snap.has_timestamp", "У снапшота есть отметка времени", Severity.HARD,
                        _c_has_timestamp,
                        "Слепая зона: без fetched_at возраст данных не измерить")
C_SNAP_FRESHNESS = Check("snap.freshness", "Снапшот не протух", Severity.HARD,
                         _c_freshness,
                         "3900 страниц шесть недель отдавали данные от 30.07 при зелёной сборке")
C_NOT_EMPTY = Check("snap.not_empty", "Снапшот наполнен", Severity.HARD,
                    _c_not_empty, "Тихий отказ фида: код 200, ноль записей")
C_DECLARED_COUNT = Check("snap.declared_count", "Объявленное count совпадает с файлом", Severity.SOFT,
                         _c_declared_count, "Лог считал массив, а не файл — расхождение на 25 записей")

C_AGE_SPREAD = Check("snap.age_spread", "Снапшот не отстал от соседей", Severity.HARD,
                     _c_age_spread,
                     "45 дней у части файлов при сутках у соседних — сломан шаг обновления")

CHECKS: list[Check] = [C_HAS_TIMESTAMP, C_SNAP_FRESHNESS, C_AGE_SPREAD,
                       C_NOT_EMPTY, C_DECLARED_COUNT]
CHECKS_VERSION = "snap-1.2"  # 1.2: пропуск-норма не режет покрытие; когорта по ритму обновления


def subjects() -> list[str]:
    return snapshot_files()


def payload(subject: str, today: date) -> dict:
    return {"doc": load_snapshot(subject), "today": today}
