"""Целевой ловец недельной инфляции Росстата (владелец, 2026-07-30).

ПРОБЛЕМА. Недельная инфляция публикуется СТАБИЛЬНО по средам во второй половине
дня («О потребительских ценах», неделя по понедельник включительно), а на бою ряд
inflation_weekly дырявый и с опозданиями: единственным каналом было LLM-извлечение
из ОБЩЕЙ новостной ленты (news_pipeline.extract_macro_points) — если релиз не попал
в ленту или не распознался, точки просто не было, и никто этого не замечал (пришлось
даже досеивать руками — debug/seed-weekly-inflation-jul20-2026). Владелец: «её даже
не смогли спарсить — легко найти вебсёрчем; это надо исправить».

Тем же средовым релизом Минэк публикует и оценку ГОДОВОЙ инфляции на ту же дату
(«с 21 по 27 июля 0,04%, годовая 5,94%») — владелец 2026-07-30 поймал и её
отставание (5,84 за 20 июля при уже вышедших 5,94). Ловец добывает ОБА числа:
wow → inflation_weekly и yoy → inflation (метрика yoy, as_of тот же понедельник).

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
_YOY_MIN, _YOY_MAX = 0.0, 30.0       # годовая оценка из того же релиза

_EXTRACT_SYS = (
    "Ты извлекаешь из новостей значения из недельного релиза Росстата/Минэка о "
    "потребительских ценах: (1) ОБЩАЯ недельная инфляция в РФ (ИПЦ за неделю, ВСЯ "
    "корзина) и (2) оценка ГОДОВОЙ инфляции на конец той же недели («в годовом "
    "выражении»). НЕ путать с ростом цены отдельного товара (сахар, бензин, огурцы) "
    "и с инфляцией с начала месяца/года. Неделя Росстата заканчивается понедельником. "
    "Верни строго JSON {\"found\": true|false, \"week_end\": \"YYYY-MM-DD\", "
    "\"wow\": <число, % за неделю | null>, \"yoy\": <число, % год к году | null>, "
    "\"source_idx\": <номер новости>}. Чего в текстах нет — null; нет ничего — "
    "{\"found\": false}. Никакого текста вне JSON."
)

_ROSSTAT_URL = "https://rosstat.gov.ru/compendium/document/50798"
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря")

# Сколько недель назад добираем пропуски. Сторож смотрел ТОЛЬКО текущую ожидаемую
# неделю: не нашёл в среду-пятницу — точка терялась навсегда, ряд молча оставался с
# дырой (владелец 2026-08-08: «инфляция опять не обновилась» — последняя точка была
# от 27 июля при вышедшей за 3 августа).
_BACKFILL_WEEKS = 3
# Между попытками по ОДНОЙ И ТОЙ ЖЕ неделе: крон гоняется почасово ср-пт, а релиз
# выходит один раз — без паузы каждая попытка стоила бы двух LLM-вызовов на ветер.
# Живёт в памяти процесса: после деплоя обнуляется, и это правильно (свежий процесс
# должен попробовать сразу).
_RETRY_COOLDOWN_H = {"current": 3, "backfill": 12}
_LAST_TRY: dict[date, datetime] = {}

# Почему не нашли — видно только по логам Timeweb, а туда за каждым прогоном не
# полезешь. Дешёвый след последнего прогона: сколько результатов дал поиск и на чём
# сорвалось извлечение. Возвращается в ответе ручного триггера.
_DIAG: dict = {}


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


def _have_point(db: Session, code: str, week_end: date, metric: str) -> bool:
    from app.models.macro import MacroDataPoint
    return (db.query(MacroDataPoint)
            .filter_by(indicator_code=code, as_of=week_end, metric=metric)
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
    got = _validate(out, week_end)
    if not got:
        return None
    try:
        idx = int(out.get("source_idx") or 0)
    except (TypeError, ValueError):
        idx = 0
    src = rows[idx] if 0 <= idx < len(rows) else rows[0]
    got.update(source=src.source or "Лента Basis", url=src.source_url)
    return got


def _validate(out: dict, week_end: date) -> dict | None:
    """Разбор и валидация ответа экстрактора. Каждое из двух чисел проверяется
    НЕЗАВИСИМО: релиз в пересказе СМИ может содержать только одно из них, и
    отвергать годовую из-за отсутствия недельной (или наоборот) — терять данные.
    Неделя обязана совпасть с ожидаемой (±1 день на праздничные сдвиги)."""
    if not out.get("found"):
        return None
    try:
        we = date.fromisoformat(str(out.get("week_end")))
    except (TypeError, ValueError):
        return None
    if abs((we - week_end).days) > 1:
        logger.warning("weekly-watch: отвергнуто — не та неделя (%s вместо %s)", we, week_end)
        return None
    got: dict = {}
    for key, lo, hi in (("wow", _VALUE_MIN, _VALUE_MAX), ("yoy", _YOY_MIN, _YOY_MAX)):
        v = out.get(key)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if lo <= v <= hi:
            got[key] = v
        else:
            logger.warning("weekly-watch: %s=%s вне диапазона [%s, %s] — отброшено", key, v, lo, hi)
    return got or None


def _week_phrase(week_end: date) -> str:
    """«с 28 июля по 3 августа» — ровно та формулировка, которой релиз и новости о нём
    называют неделю. Поиск по ней попадает в цель, поиск по «инфляция за неделю» —
    в прошлогодние материалы."""
    start = week_end - timedelta(days=6)
    return (f"с {start.day} {_MONTHS_GEN[start.month - 1]} "
            f"по {week_end.day} {_MONTHS_GEN[week_end.month - 1]}")


def _from_web_search(week_end: date) -> dict | None:
    """Целевой веб-поиск (владелец, 2026-08-08: «легко найти вебсёрчем»).

    Появился третьим каналом, потому что первые два пересохли одновременно: в нашей
    Ленте недельного релиза не бывает вовсе (источники — деловые СМИ общего профиля,
    статрелиз до них не доходит), а rosstat.gov.ru не открывается ни с боя, ни с
    ноутбука. Веб-поиск с боевого инстанса при этом работает (проверено).

    Сначала пробуем ВЫЖИМКИ результатов — в них число обычно уже есть («инфляция
    с 28 июля по 3 августа составила −0,02%»), и это бесплатно по трафику; только
    если из выжимок не собралось — открываем пару страниц целиком.
    """
    from app.services.agent_web import fetch_document, web_search

    phrase = _week_phrase(week_end)
    queries = [f"Росстат недельная инфляция {phrase} {week_end.year}",
               f"инфляция в России за неделю {phrase} {week_end.year} потребительские цены"]
    results: list[dict] = []
    for q in queries:
        try:
            out = web_search(q, 6)
        except Exception as e:  # noqa: BLE001
            logger.warning("weekly-watch: веб-поиск упал (%s)", type(e).__name__)
            _DIAG["search_error"] = type(e).__name__
            continue
        if isinstance(out, dict) and out.get("error"):
            logger.info("weekly-watch: веб-поиск недоступен: %s", out["error"])
            _DIAG["search_error"] = str(out["error"])[:120]
            continue
        for r in (out or {}).get("results") or []:
            if isinstance(r, dict) and r.get("url"):
                results.append(r)
        if len(results) >= 8:
            break
    _DIAG["search_results"] = len(results)
    _DIAG["search_titles"] = [str(r.get("title") or "")[:90] for r in results[:3]]
    if not results:
        return None

    payload = [{"idx": i, "title": r.get("title"), "text": str(r.get("snippet") or "")[:600],
                "url": r.get("url")} for i, r in enumerate(results[:10])]
    got = _extract(payload, week_end)
    if got:
        src = results[int(got.pop("_idx", 0))] if results else {}
        got.update(source="Веб-поиск", url=src.get("url"))
        return got

    # Выжимок не хватило — открываем страницы, где вообще упомянута инфляция.
    pages = [r for r in results if "нфляц" in ((r.get("title") or "") + (r.get("snippet") or ""))][:2]
    docs = []
    for i, r in enumerate(pages or results[:2]):
        try:
            doc = fetch_document(r["url"], max_chars=8000)
        except Exception:  # noqa: BLE001
            continue
        text = (doc or {}).get("text") if isinstance(doc, dict) else None
        if text:
            docs.append({"idx": i, "title": r.get("title"), "text": text[:6000],
                         "url": r["url"]})
    _DIAG["docs_fetched"] = len(docs)
    if not docs:
        return None
    got = _extract(docs, week_end)
    if not got:
        return None
    src = docs[int(got.pop("_idx", 0))] if docs else {}
    got.update(source="Веб-поиск", url=src.get("url"))
    return got


def _extract(payload: list[dict], week_end: date) -> dict | None:
    """Один вызов экстрактора по подготовленным материалам + валидация."""
    if not payload:
        return None
    try:
        out = llm.complete(
            _EXTRACT_SYS + f"\nОжидаемая неделя: по {week_end.isoformat()} (понедельник).",
            str(payload), json_mode=True, max_tokens=400)
    except llm.LLMError as e:
        logger.warning("weekly-watch: LLM не отработал: %s", e)
        _DIAG["extract"] = f"llm_error: {type(e).__name__}"
        return None
    got = _validate(out, week_end)
    if not got:
        _DIAG["extract"] = "не прошло валидацию: " + str(out)[:200]
        return None
    try:
        got["_idx"] = int(out.get("source_idx") or 0)
    except (TypeError, ValueError):
        got["_idx"] = 0
    if not 0 <= got["_idx"] < len(payload):
        got["_idx"] = 0
    return got


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
    except llm.LLMError:
        return None
    got = _validate(out, week_end)
    if got:
        got.update(source="Росстат", url=_ROSSTAT_URL)
    return got


def _cooldown_ok(week_end: date, kind: str) -> bool:
    last = _LAST_TRY.get(week_end)
    if last is None:
        return True
    return (_now_msk() - last) >= timedelta(hours=_RETRY_COOLDOWN_H[kind])


def _fetch_week(db: Session, week_end: date, kind: str) -> dict:
    """Добыть и записать одну неделю. Каналы по возрастанию цены: своя Лента (SQL,
    бесплатно) → веб-поиск (внешний, но с боя работает) → Росстат напрямую."""
    need_wow = not _have_point(db, "inflation_weekly", week_end, "wow")
    need_yoy = not _have_point(db, "inflation", week_end, "yoy")
    if not need_wow and not need_yoy:
        return {"status": "ok", "week_end": str(week_end)}
    if not _cooldown_ok(week_end, kind):
        return {"status": "cooldown", "week_end": str(week_end)}
    _LAST_TRY[week_end] = _now_msk()

    # Лента ищет по последним 4 дням — для добора старых недель она бесполезна.
    got = (_from_own_feed(db, week_end) if kind == "current" else None) \
        or _from_web_search(week_end) or _from_rosstat(week_end)
    if not got:
        return {"status": "missing", "week_end": str(week_end),
                "missing": [k for k, need in (("wow", need_wow), ("yoy", need_yoy)) if need],
                "note": "релиза нет ни в ленте, ни в вебе, ни на Росстате — ждём следующего прогона"}
    # as_of — ВСЕГДА нормализованный понедельник отчётной недели, не дата новости
    saved = {}
    if need_wow and "wow" in got:
        saved["wow"] = upsert_point(db, "inflation_weekly", week_end, "wow", got["wow"],
                                    unit="%", source=got["source"], source_url=got.get("url"),
                                    ingested_via="news")
    if need_yoy and "yoy" in got:
        saved["yoy"] = upsert_point(db, "inflation", week_end, "yoy", got["yoy"],
                                    unit="%", source=got["source"], source_url=got.get("url"),
                                    ingested_via="news")
    if not saved:
        return {"status": "partial", "week_end": str(week_end),
                "note": "релиз найден, но нужных чисел в нём не оказалось"}
    logger.info("weekly-watch: неделя по %s — записано %s (%s)", week_end,
                {k: got[k] for k in saved}, got.get("source"))
    return {"status": "fetched", "week_end": str(week_end),
            **{k: got[k] for k in saved}, "source": got.get("source"), "upsert": saved}


def watch_weekly_inflation(db: Session, backfill_weeks: int = _BACKFILL_WEEKS,
                           force: bool = False) -> dict:
    """Один прогон сторожа. Идемпотентен: все точки на месте → no-op (пара SELECT).

    Смотрит НЕ ТОЛЬКО текущую ожидаемую неделю, но и предыдущие (по умолчанию три):
    если релиз не удалось поймать в свои среду-пятницу, дыра в ряду закрывается позже,
    а не остаётся навсегда. Из одного релиза пишутся ДВЕ точки: wow →
    inflation_weekly и годовая оценка Минэка → inflation (metric=yoy, тот же
    as_of-понедельник). Существующие точки не трогаются.
    """
    current = _expected_week_end()
    if force:
        _LAST_TRY.clear()      # ручной прогон обязан идти сразу, а не ждать паузу
    _DIAG.clear()
    weeks = [current - timedelta(days=7 * i) for i in range(max(1, backfill_weeks))]
    results = []
    for i, wk in enumerate(weeks):
        res = _fetch_week(db, wk, "current" if i == 0 else "backfill")
        results.append(res)
        # За один прогон добываем максимум одну недостающую неделю: крон частый,
        # спешить некуда, а каждая добыча — это внешний поиск плюс LLM.
        if res["status"] in ("fetched", "partial"):
            break
    head = results[0]
    filled = [r for r in results if r["status"] == "fetched"]
    return {**head, "weeks_checked": [str(w) for w in weeks],
            "filled": filled or None, "diag": dict(_DIAG) or None}
