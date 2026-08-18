"""Добор веб-поиском рядов, у которых нет машинного источника.

Начиналось как «уровни в триллионах» (денежные агрегаты и номинальный ВВП), сейчас сюда
же вынесены зарплаты Росстата и безработица еврозоны/Китая — по той же причине и по тому
же протоколу: узкий поиск → строгое извлечение → жёсткая валидация диапазона и даты.


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

# Реестр доборов. Ключ — код ряда, значение:
#   what      — что именно ищем, словами (уходит в промпт извлечения);
#   range     — допустимый диапазон значения В ЕДИНИЦАХ РЯДА (жёсткая валидация);
#   query     — основа поискового запроса;
#   metric    — в какую метрику писать (level / yoy / mom);
#   unit      — единица измерения точки;
#   min_age   — не ходить в сеть, если последняя точка свежее скольких-то дней;
#   derive    — считать ли темпы (г/г, кв/кв) КОДОМ по накопленным уровням.
#
# 🔴 Что здесь лежит и почему. Это ряды, у которых НЕТ машинного источника: fedstat/ЕМИСС
# отдаёт 403 даже с боевого IP, страница денежной массы ЦБ — Flash-дашборд без JSON,
# Росстат не публикует зарплаты машиночитаемо. Единственный рабочий канал — узкий
# веб-поиск + строгая валидация. Ряды с живым фидом (FRED, ЦБ, Минфин, Yahoo, WB) сюда
# НЕ добавлять: два источника под одним кодом — это ровно та болезнь, от которой лечили
# M2 («то 10 процентов, то 1»).
_TARGETS = {
    "m2_level": {"what": "денежная масса M2 (национальное определение), трлн рублей",
                 "range": (80.0, 250.0), "query": "денежная масса М2 России",
                 "unit": "трлн ₽", "min_age": 20, "derive": True},
    "m0_level": {"what": "наличные деньги вне банков M0, трлн рублей",
                 "range": (10.0, 40.0), "query": "денежный агрегат М0 наличные деньги Россия",
                 "unit": "трлн ₽", "min_age": 20, "derive": True},
    "m2x_level": {"what": "широкая денежная масса M2X (включая валютные депозиты), трлн рублей",
                  "range": (90.0, 300.0),
                  "query": "широкая денежная масса M2X ЦБ РФ трлн рублей",
                  "unit": "трлн ₽", "min_age": 20, "derive": True},
    "gdp_level": {"what": "номинальный ВВП России в текущих ценах за квартал, трлн рублей",
                  "range": (25.0, 90.0), "query": "номинальный ВВП России квартал трлн рублей",
                  "unit": "трлн ₽", "min_age": 60, "derive": True},
    # Росстат: машинного канала нет, публикация с лагом ~1,5–2 месяца
    "nominal_wage": {"what": "среднемесячная начисленная номинальная заработная плата в России, "
                             "рублей в месяц (Росстат)",
                     "range": (60_000.0, 250_000.0),
                     "query": "среднемесячная начисленная заработная плата Росстат рублей",
                     "unit": "₽", "min_age": 25, "derive": False},
    "real_wage": {"what": "реальная заработная плата в России, рост в % год к году (Росстат)",
                  "range": (-25.0, 30.0), "metric": "yoy",
                  "query": "реальная заработная плата Росстат рост процентов год к году",
                  "unit": "%", "min_age": 25, "derive": False},
    # Мир: FRED этих двух рядов не даёт, а первоисточники (Евростат/Госстат КНР) машинно
    # недоступны — до сих пор это были разовые ручные засевы, которые никто не обновлял
    "eu_unemployment": {"what": "уровень безработицы в еврозоне, % (Евростат)",
                        "range": (3.0, 15.0),
                        "query": "уровень безработицы еврозоны Евростат процентов",
                        "unit": "%", "min_age": 25, "derive": False},
    "cn_unemployment": {"what": "уровень безработицы в городах Китая, % (Госстат КНР)",
                        "range": (3.0, 12.0),
                        "query": "уровень безработицы в городах Китая процентов",
                        "unit": "%", "min_age": 25, "derive": False},
}

_SYS = (
    "Ты извлекаешь ОДНО число из материалов об экономической статистике. Верни строго JSON "
    "{\"found\": true|false, \"value\": <число В УКАЗАННЫХ ЕДИНИЦАХ>, "
    "\"as_of\": \"YYYY-MM-DD\" (конец периода, к которому относится значение), "
    "\"period\": \"<словами: на 1 июля 2026 / за 2 квартал 2026 / за июнь 2026>\", "
    "\"source_idx\": <номер>}. "
    "ВАЖНО: приведи значение к запрошенной единице (миллиарды → триллионы делением на 1000). "
    "Не путай уровень с приростом: если просят сам показатель — не давай его изменение в "
    "процентах, и наоборот. Не путай похожие показатели между собой (M0/M1/M2/M2X — разные; "
    "номинальная и реальная зарплата — разные; страна должна совпадать). "
    "Ничего надёжного не нашёл — {\"found\": false}. Никакого текста вне JSON."
)


def _latest(db: Session, code: str, metric: str = "level"):
    return db.execute(text(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code=:c AND metric=:m "
        "ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()


def _fetch_one(code: str, spec: dict) -> dict | None:
    """Один показатель: поиск → извлечение → валидация."""
    what, (lo, hi), query_base = spec["what"], spec["range"], spec["query"]
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
        out = llm.complete(_SYS + f"\nИщем: {what}. Единица ответа: {spec.get('unit')}.",
                           str(payload), json_mode=True, max_tokens=300)
    except llm.LLMError as e:
        logger.warning("levels-watch: %s — LLM не отработал: %s", code, e)
        return None
    if not isinstance(out, dict) or not out.get("found"):
        return None
    try:
        raw = out.get("value")
        if raw is None:
            raw = out.get("value_trn")      # совместимость со старым форматом ответа
        val = float(str(raw).replace(",", ".").replace(" ", "").replace(" ", ""))
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
    """Один прогон: добрать ряды без машинного источника, посчитать темпы.

    Идемпотентно по свежести: ряд, у которого последняя точка свежее `min_age`, в сеть
    не ходит вовсе (`force=True` — обойти, для ручной проверки).
    """
    report: dict = {}
    for code, spec in _TARGETS.items():
        if codes and code not in codes:
            continue
        metric = spec.get("metric", "level")
        last = _latest(db, code, metric)
        if last and not force and (date.today() - last[0]).days < spec.get("min_age", 20):
            report[code] = {"status": "свежий", "as_of": str(last[0]), "value": float(last[1])}
            continue
        got = _fetch_one(code, spec)
        if not got:
            report[code] = {"status": "не найдено"}
            continue
        # 🔴 Не откатываться назад: поиск легко приносит прошлогоднюю публикацию. Точку
        # СТАРШЕ уже имеющейся молча не пишем — это не обновление, а порча ряда.
        if last and got["as_of"] < last[0]:
            report[code] = {"status": "старее имеющейся", "as_of": str(got["as_of"]),
                            "have": str(last[0])}
            continue
        res = upsert_point(db, code, got["as_of"], metric, got["value"],
                           unit=spec.get("unit", "трлн ₽"), source="Веб-поиск",
                           source_url=got.get("url"), ingested_via="news", commit=False)
        rates = _derive_rates(db, code) if spec.get("derive") else {}
        db.commit()
        report[code] = {"status": res, "as_of": str(got["as_of"]), "value": got["value"],
                        "period": got.get("period"), **rates}
        logger.info("levels-watch: %s = %s %s на %s (%s)", code, got["value"],
                    spec.get("unit"), got["as_of"], res)
    return report
