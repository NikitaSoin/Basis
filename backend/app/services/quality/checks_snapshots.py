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

def _c_has_timestamp(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    """🔴 Отсутствие отметки времени — НАХОДКА, а не «нечего проверять».
    Артефакт без возраста нельзя признать ни свежим, ни протухшим; именно в этой
    слепой зоне и прожили шесть недель страницы облигаций."""
    doc = payload["doc"]
    if doc is None:
        yield fail(C_HAS_TIMESTAMP, subject, "файл не читается как JSON")
        return
    if fetched_at(doc) is None:
        yield fail(C_HAS_TIMESTAMP, subject,
                   "нет отметки fetched_at — возраст данных измерить нечем")
    else:
        yield ok(C_HAS_TIMESTAMP, subject)


def _c_freshness(subject: str, payload: dict) -> Iterable[CheckOutcome]:
    doc, today = payload["doc"], payload["today"]
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

CHECKS: list[Check] = [C_HAS_TIMESTAMP, C_SNAP_FRESHNESS, C_NOT_EMPTY, C_DECLARED_COUNT]
CHECKS_VERSION = "snap-1.0"


def subjects() -> list[str]:
    return snapshot_files()


def payload(subject: str, today: date) -> dict:
    return {"doc": load_snapshot(subject), "today": today}
