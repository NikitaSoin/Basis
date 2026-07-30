"""Целевой ловец недельной инфляции Росстата (владелец, 2026-07-30).

ПРОБЛЕМА. Недельная инфляция публикуется СТАБИЛЬНО по средам во второй половине
дня («О потребительских ценах», неделя по понедельник включительно), а на бою ряд
inflation_weekly дырявый и с опозданиями: единственным каналом было LLM-извлечение
из ОБЩЕЙ новостной ленты (news_pipeline.extract_macro_points) — если релиз не попал
в ленту или не распознался, точки просто не было, и никто этого не замечал (пришлось
даже досеивать руками — debug/seed-weekly-inflation-jul20-2026). Владелец: «её даже
не смогли спарсить — легко найти вебсёрчем; это надо исправить».

РЕШЕНИЕ — расписание вместо надежды на ленту:
1. _expected_week_end() считает, точка за какой понедельник УЖЕ ДОЛЖНА существовать
   (публикация в среду ~16:00 МСК за неделю по понедельник этой же недели).
2. watch_weekly_inflation() гоняется кроном по ср/чт/пт: точка есть → no-op;
   нет → целевая добыча из СВОЕЙ ленты (не «вся лента через общий экстрактор», а
   узкий запрос: только новости со словом «инфляц» за последние 4 дня + строгий
   системник ровно под этот показатель) с жёсткой валидацией недели и диапазона;
   фолбэк — страница «Срочных информаций» Росстата с браузерным UA (Росстат
   исторически недоступен машинно с Timeweb — честно пробуем и честно логируем).
3. Точка нормализуется К ПОНЕДЕЛЬНИКУ отчётной недели — в ряду уже есть мусорные
   as_of (2026-06-09, 2026-07-09 — даты ПУБЛИКАЦИИ новости вместо конца недели),
   этот путь таких не плодит.

Вечная пара к этому — ужесточённый _check_weekly_inflation_fresh в
macro_verification.py: «среда прошла, а точки нет» теперь warn в тот же день.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.services import llm
from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

# публикация в среду «во второй половине дня»; берём консервативно 16:00 МСК
_PUBLISH_WEEKDAY = 2   # среда
_PUBLISH_HOUR_MSK = 16
_VALUE_MIN, _VALUE_MAX = -0.5, 1.0   # недельный ИПЦ вне этого — ошибка распознавания

_EXTRACT_SYS = (
    "Ты извлекаешь ОДНО число из новостей: значение ОБЩЕЙ недельной инфляции в РФ "
    "(индекс потребительских цен Росстата за неделю, ВСЯ корзина). НЕ путать с ростом "
    "цены отдельного товара (сахар, бензин, огурцы), НЕ путать с инфляцией с начала "
    "месяца/года и с годовой. Неделя Росстата заканчивается понедельником. "
    "Верни строго JSON {\"found\": true|false, \"week_end\": \"YYYY-MM-DD\", "
    "\"wow\": <число, % за неделю>, \"source_idx\": <номер новости>}. Если общей "
    "недельной инфляции в текстах нет — {\"found\": false}. Никакого текста вне JSON."
)

_ROSSTAT_URL = "https://rosstat.gov.ru/compendium/document/50798"
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _now_msk() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=3)


def _expected_week_end(now: datetime | None = None) -> date:
    """Понедельник, точка за который уже должна быть опубликована к текущему моменту."""
    now = now or _now_msk()
    d = now.date()
    monday_this = d - timedelta(days=d.weekday())
    published_this_week = (d.weekday() > _PUBLISH_WEEKDAY
                           or (d.weekday() == _PUBLISH_WEEKDAY and now.hour >= _PUBLISH_HOUR_MSK))
    return monday_this if published_this_week else monday_this - timedelta(days=7)


def _have_point(db: Session, week_end: date) -> bool:
    from app.models.macro import MacroDataPoint
    return (db.query(MacroDataPoint)
            .filter_by(indicator_code="inflation_weekly", as_of=week_end, metric="wow")
            .first() is not None)


def _from_own_feed(db: Session, week_end: date) -> dict | None:
    """Целевая добыча из собственной Ленты: только «инфляц»-новости за 4 дня."""
    from app.models.market import MarketUpdate
    cutoff = datetime.now(timezone.utc) - timedelta(days=4)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.published_at >= cutoff,
                    or_(MarketUpdate.title.ilike("%инфляц%"),
                        MarketUpdate.summary.ilike("%инфляц%"),
                        MarketUpdate.content.ilike("%инфляц%")))
            .order_by(MarketUpdate.published_at.desc()).limit(30).all())
    if not rows:
        return None
    payload = [{"idx": i, "title": r.title, "text": ((r.summary or r.content) or "")[:600]}
               for i, r in enumerate(rows)]
    try:
        out = llm.complete(
            _EXTRACT_SYS + f"\nОжидаемая неделя: по {week_end.isoformat()} (понедельник).",
            str(payload), json_mode=True, max_tokens=400)
    except llm.LLMError as e:
        logger.warning("weekly-watch: LLM не отработал: %s", e)
        return None
    if not out.get("found"):
        return None
    try:
        wow = float(out.get("wow"))
        we = date.fromisoformat(str(out.get("week_end")))
        idx = int(out.get("source_idx") or 0)
    except (TypeError, ValueError):
        return None
    # неделя обязана совпасть с ожидаемой (±1 день на сдвиги из-за праздников);
    # значение — в правдоподобном диапазоне. Иначе точка не пишется вовсе.
    if abs((we - week_end).days) > 1 or not (_VALUE_MIN <= wow <= _VALUE_MAX):
        logger.warning("weekly-watch: извлечённое отвергнуто (week_end=%s wow=%s)", we, wow)
        return None
    src = rows[idx] if 0 <= idx < len(rows) else rows[0]
    return {"wow": wow, "source": src.source or "Лента Basis", "url": src.source_url}


def _from_rosstat(week_end: date) -> dict | None:
    """Фолбэк: «Срочные информации» Росстата напрямую. С Timeweb Росстат исторически
    недоступен машинно — пробуем с браузерным UA, при неудаче честно None."""
    try:
        r = httpx.Client(timeout=25, headers={"User-Agent": _BROWSER_UA},
                         follow_redirects=True).get(_ROSSTAT_URL)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.info("weekly-watch: Росстат недоступен (%s) — ожидаемо", type(e).__name__)
        return None
    text = re.sub(r"<[^>]+>", " ", r.text)
    text = re.sub(r"\s+", " ", text)[:12000]
    try:
        out = llm.complete(
            _EXTRACT_SYS + f"\nОжидаемая неделя: по {week_end.isoformat()} (понедельник).",
            text, json_mode=True, max_tokens=400)
        if out.get("found"):
            wow = float(out.get("wow"))
            we = date.fromisoformat(str(out.get("week_end")))
            if abs((we - week_end).days) <= 1 and _VALUE_MIN <= wow <= _VALUE_MAX:
                return {"wow": wow, "source": "Росстат", "url": _ROSSTAT_URL}
    except (llm.LLMError, TypeError, ValueError):
        pass
    return None


def watch_weekly_inflation(db: Session) -> dict:
    """Один прогон сторожа. Идемпотентен: точка уже есть → no-op."""
    week_end = _expected_week_end()
    if _have_point(db, week_end):
        return {"status": "ok", "week_end": str(week_end)}
    got = _from_own_feed(db, week_end) or _from_rosstat(week_end)
    if not got:
        return {"status": "missing", "week_end": str(week_end),
                "note": "релиза нет ни в ленте, ни на Росстате — ждём следующего прогона"}
    # as_of — ВСЕГДА нормализованный понедельник отчётной недели, не дата новости
    res = upsert_point(db, "inflation_weekly", week_end, "wow", got["wow"], unit="%",
                       source=got["source"], source_url=got.get("url"), ingested_via="news")
    logger.info("weekly-watch: недельная инфляция %s%% за неделю по %s (%s)",
                got["wow"], week_end, res)
    return {"status": "fetched", "week_end": str(week_end), "wow": got["wow"], "upsert": res}
