"""Уровни в триллионах: денежные агрегаты и ВВП в текущих ценах.

🔴 Владелец, 2026-08-18: «сделай, чтобы ВВП можно было посмотреть в цифрах в триллионах,
и денежную массу тоже; плюс другие агрегаты, если найдёшь».

Почему так, а не «загрузить из источника». Первичные держатели этих рядов машинно
недоступны: fedstat/ЕМИСС отдаёт 403 даже с боевого IP (антибот-WAF), страница денежной
массы ЦБ рисуется устаревшим Flash-дашбордом без JSON-эндпоинта, файла .xlsx по прямой
ссылке нет. Поэтому используем тот же путь, который уже работает для недельной инфляции:
узкий веб-поиск → строгое извлечение → жёсткая валидация диапазона и даты. Это честный
рабочий канал, а не «данных нет».

Что здесь есть и чего нет:
- ЕСТЬ уровни (M0, M2, M2X, номинальный ВВП) и производные от них темпы, которые
  считает КОД (год к году, квартал к кварталу) — производные никогда не берутся у
  модели: их арифметика однозначна, а ошибка в ней незаметна;
- НЕТ попыток восстановить историю: добываем последнее опубликованное значение, история
  накапливается прогонами. Выдумывать прошлые точки нельзя.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import llm
from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря")

# код → (что ищем, диапазон допустимых значений в трлн ₽, как назвать в запросе)
_TARGETS = {
    "m2_level": ("денежная масса M2 (национальное определение), трлн рублей", (80.0, 250.0),
                 "денежная масса М2 России"),
    "m0_level": ("наличные деньги вне банков M0, трлн рублей", (10.0, 40.0),
                 "денежный агрегат М0 наличные деньги Россия"),
    "m2x_level": ("широкая денежная масса M2X, трлн рублей", (90.0, 300.0),
                  "широкая денежная масса М2X Россия"),
    "gdp_level": ("номинальный ВВП России в текущих ценах за квартал, трлн рублей",
                  (25.0, 90.0), "номинальный ВВП России квартал трлн рублей"),
}

_SYS = (
    "Ты извлекаешь ОДНО число из материалов о российской статистике. Верни строго JSON "
    "{\"found\": true|false, \"value_trn\": <число в ТРИЛЛИОНАХ рублей>, "
    "\"as_of\": \"YYYY-MM-DD\" (конец периода, к которому относится значение), "
    "\"period\": \"<словами: на 1 июля 2026 / за 2 квартал 2026>\", \"source_idx\": <номер>}. "
    "ВАЖНО: если в источнике значение в миллиардах — переведи в триллионы (раздели на 1000). "
    "Не путай уровень с приростом: нужен САМ показатель, а не его изменение в процентах. "
    "Не путай агрегаты между собой (M0, M1, M2, M2X — разные показатели). "
    "Ничего не нашёл — {\"found\": false}. Никакого текста вне JSON."
)


def _latest(db: Session, code: str, metric: str = "level"):
    return db.execute(text(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code=:c AND metric=:m "
        "ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()


def _fetch_one(code: str, spec: tuple) -> dict | None:
    """Один показатель: поиск → извлечение → валидация."""
    what, (lo, hi), query_base = spec
    from app.services.agent_web import web_search

    today = date.today()
    month_hint = f"{_MONTHS[today.month - 1]} {today.year}"
    results = []
    for q in (f"{query_base} {month_hint}", f"{query_base} последние данные {today.year}"):
        try:
            out = web_search(q, 6)
        except Exception as e:  # noqa: BLE001
            logger.warning("levels-watch: поиск упал (%s)", type(e).__name__)
            continue
        if isinstance(out, dict) and not out.get("error"):
            results.extend(r for r in (out.get("results") or []) if isinstance(r, dict))
        if len(results) >= 8:
            break
    if not results:
        return None

    payload = [{"idx": i, "title": r.get("title"), "text": str(r.get("snippet") or "")[:400],
                "url": r.get("url")} for i, r in enumerate(results[:10])]
    try:
        out = llm.complete(_SYS + f"\nИщем: {what}.", str(payload), json_mode=True,
                           max_tokens=300)
    except llm.LLMError as e:
        logger.warning("levels-watch: %s — LLM не отработал: %s", code, e)
        return None
    if not isinstance(out, dict) or not out.get("found"):
        return None
    try:
        val = float(str(out.get("value_trn")).replace(",", "."))
        as_of = date.fromisoformat(str(out.get("as_of"))[:10])
    except (TypeError, ValueError):
        return None
    # 🔴 Валидация — обязательна: поиск легко приносит миллиарды вместо триллионов,
    # чужую страну или прирост вместо уровня. Диапазон отсекает всё это разом.
    if not (lo <= val <= hi):
        logger.warning("levels-watch: %s = %s вне диапазона [%s, %s] — отброшено",
                       code, val, lo, hi)
        return None
    if as_of > today + timedelta(days=5) or as_of < today - timedelta(days=400):
        logger.warning("levels-watch: %s — дата %s неправдоподобна", code, as_of)
        return None
    idx = int(out.get("source_idx") or 0)
    src = results[idx] if 0 <= idx < len(results) else results[0]
    return {"value": val, "as_of": as_of, "period": out.get("period"),
            "url": src.get("url"), "title": src.get("title")}


def _derive_rates(db: Session, code: str) -> dict:
    """Темпы считает КОД по уровням: год к году и квартал к кварталу.

    У модели их не спрашиваем принципиально — арифметика однозначна, а ошибка в ней
    незаметна на витрине (ровно так «то 10%, то 1%» и появилось в M2)."""
    rows = db.execute(text(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code=:c AND metric='level' "
        "ORDER BY as_of"), {"c": code}).fetchall()
    pts = [(r[0], float(r[1])) for r in rows]
    out = {}
    if len(pts) < 2:
        return out
    last_d, last_v = pts[-1]
    # год к году: ближайшая точка примерно на год раньше (окно ±45 дней)
    year_ago = [(d, v) for d, v in pts if abs((last_d - d).days - 365) <= 45]
    if year_ago and year_ago[-1][1]:
        yoy = (last_v / year_ago[-1][1] - 1) * 100
        upsert_point(db, code, last_d, "yoy", round(yoy, 1), unit="%",
                     source="расчёт Basis по уровням", ingested_via="derived", commit=False)
        out["yoy"] = round(yoy, 1)
    prev_d, prev_v = pts[-2]
    if prev_v and (last_d - prev_d).days <= 130:
        qoq = (last_v / prev_v - 1) * 100
        upsert_point(db, code, last_d, "qoq", round(qoq, 1), unit="%",
                     source="расчёт Basis по уровням", ingested_via="derived", commit=False)
        out["qoq"] = round(qoq, 1)
    return out


def watch_levels(db: Session, codes: list[str] | None = None, force: bool = False) -> dict:
    """Один прогон: добрать уровни, посчитать темпы. Идемпотентно по свежести."""
    report: dict = {}
    for code, spec in _TARGETS.items():
        if codes and code not in codes:
            continue
        last = _latest(db, code)
        # месячные показатели обновляем не чаще раза в 20 дней, квартальные — в 60
        min_age = 60 if code == "gdp_level" else 20
        if last and not force and (date.today() - last[0]).days < min_age:
            report[code] = {"status": "свежий", "as_of": str(last[0]), "value": float(last[1])}
            continue
        got = _fetch_one(code, spec)
        if not got:
            report[code] = {"status": "не найдено"}
            continue
        res = upsert_point(db, code, got["as_of"], "level", got["value"], unit="трлн ₽",
                           source="Веб-поиск", source_url=got.get("url"),
                           ingested_via="news", commit=False)
        rates = _derive_rates(db, code)
        db.commit()
        report[code] = {"status": res, "as_of": str(got["as_of"]), "value": got["value"],
                        "period": got.get("period"), **rates}
        logger.info("levels-watch: %s = %s трлн на %s (%s)", code, got["value"],
                    got["as_of"], res)
    return report
