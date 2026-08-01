"""Интерпретатор макроситуации (Направление 2, модуль G).

Берёт ВСЕ показатели платформы (РФ+мир) + аналитику ЦБ/ЦМАКП + прогноз ЦБ →
строит связную интерпретацию СТРОГО по методичке docs/macroeconomics_methodology.md
(направление МАКРО→СТАВКА→РЫНОК→СЕКТОРА). Модель — DeepSeek Pro на РАССУЖДЕНИИ
(thinking=True): это думающая задача, не выжимка. Без «купить/продать».
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.macro import (MacroIndicator, MacroDataPoint, RateMeeting,
                              MacroAnalyticsDoc, MacroForecast, MacroInterpretation)
from app.services import llm

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_METHODOLOGY = os.path.join(_REPO, "docs", "macroeconomics_methodology.md")
_SECTORS = os.path.join(_REPO, "config", "sectors.json")

# Жёсткая инструкция формата вывода (раздел 14 методички) — добавляется к методичке.
# ВАЖНО (2026-07-12, владелец раскритиковал прозу как «простыню», product-analyst-fin
# подтвердил диагноз): раньше current_picture/rate_outlook/cb_forecast_view/market_sectors
# были связным текстом-эссе — числа тонули в повествовании, глазу негде «приземлиться».
# Теперь вывод — атомарные тезисы: каждое поле самостоятельный факт/оценка, без прозы.
_OUTPUT_SPEC = (
    "\n\n================================================================\n"
    "ФОРМАТ ОТВЕТА (СТРОГО JSON, на русском). Главный вопрос блока: КУДА ИДУТ СТАВКА И "
    "ИНФЛЯЦИЯ, какие реальные развилки это сдвинут и что каждая делает с секторами и "
    "компаниями. Текущие значения показателей пересказывать НЕ надо — они уже показаны "
    "пользователю в разделе «Экономическая статистика». Твоя ценность — ТРАЕКТОРИЯ и "
    "ТРАНСМИССИЯ, а не витрина цифр.\n"
    "Никакой связной прозы: каждое поле — самостоятельный тезис, читается за 1-2 секунды. "
    "Числа живут внутри полей detail/effect, не растворяются в повествовании.\n\n"
    "Верни {\"sections\": {\n"
    "  \"headline\": \"<режим одним предложением, максимум 25 слов: куда идёт ставка/инфляция и что главный риск>\",\n"
    "  \"regime\": { // светофор режима, по одному слову-направлению\n"
    "    \"rate\": \"снижается|held|растёт\", \"inflation\": \"замедляется|стоит|ускоряется\",\n"
    "    \"economy\": \"рост|стагнация|спад\", \"external\": \"<гео/санкционный фон, 2-3 слова>\"\n"
    "  },\n"
    "  \"rate_path\": { // ТРАЕКТОРИЯ ставки — коридор, НЕ точка\n"
    "    \"base\": \"<базовый путь словами с числами и горизонтом, напр. '14% сейчас → 11-12% к концу 2026'>\",\n"
    "    \"range\": \"<нижняя-верхняя границы разумного коридора на том же горизонте>\",\n"
    "    \"anchor\": \"<на что опираешься: прогноз ЦБ/консенсус — с числом>\",\n"
    "    \"gates\": [\"<что должно случиться, чтобы путь пошёл вниз/вверх, максимум 14 слов>\"] // 2-3\n"
    "  },\n"
    "  \"inflation_path\": {\"base\": \"<...>\", \"range\": \"<...>\", \"anchor\": \"<...>\", \"gates\": [\"<...>\"]},\n"
    "  \"forks\": [ // РЕАЛЬНЫЕ развилки, которые стоят на повестке ПРЯМО СЕЙЧАС\n"
    "    {\"event\": \"<развилка, максимум 8 слов>\",\n"
    "     \"status\": \"<уже реализуется|высокая вероятность|возможно|маловероятно, но бьёт сильно>\",\n"
    "     \"to_inflation\": \"<эффект на инфляцию, с числом если можно, максимум 16 слов>\",\n"
    "     \"to_rate\": \"<что сделает ЦБ и почему, максимум 16 слов>\",\n"
    "     \"to_market\": \"<кого задевает и через какой канал, максимум 18 слов>\",\n"
    "     \"tag\": \"факт|оценка|суждение\"}\n"
    "  ],\n"
    "  \"sectors\": [ // 4-6 САМЫХ затронутых, не все подряд; ранжируй по силе влияния\n"
    "    {\"sector\": \"<имя сектора из списка платформы>\", \"wind\": \"попутный|встречный|смешанный\",\n"
    "     \"channel\": \"<механизм, максимум 16 слов>\",\n"
    "     \"dispersion\": \"<ПОЧЕМУ внутри сектора расходятся: какой признак делит выигравших и проигравших, максимум 18 слов>\",\n"
    "     \"winners\": [\"<ТИКЕР>\"], \"losers\": [\"<ТИКЕР>\"]} // 1-2 тикера с каждой стороны, ТОЛЬКО из компаний платформы\n"
    "  ],\n"
    "  \"changed_since_last\": \"<что изменилось с прошлого выпуска и пересмотрел ли ты свою оценку; если по сути ничего — так и скажи, максимум 22 слова>\",\n"
    "  \"watch\": [{\"signal\": \"<событие/дата>\", \"why\": \"<как сдвинет траекторию, максимум 12 слов>\"}] // 2-3\n"
    "}}.\n\n"
    "ЖЁСТКИЕ ПРАВИЛА:\n"
    "1. forks — ТОЛЬКО реальные развилки с повестки: бери их из context.chronicle (что "
    "реально происходит), context.geo_barometer.watchlist_30d и scenario.triggers, "
    "cb_forecast. НЕ выдумывай абстрактные «бык/база/медведь» ради симметрии. Если "
    "живых развилок три — верни три; если пять — пять. Пустой список недопустим, но "
    "набивать его вымыслом ради количества ЗАПРЕЩЕНО.\n"
    "2. Вероятность — только словом в поле status. НИКАКИХ процентов: мы их не "
    "калибруем, а цифра создаёт ложную точность.\n"
    "3. Траектория — это ОЦЕНКА, а не обещание: всегда давай коридор (range) и якорь "
    "(anchor) на публичный прогноз ЦБ или консенсус, чтобы читатель видел, что мы не "
    "выдумываем путь из воздуха.\n"
    "4. tag: 'факт' — прямо следует из переданных чисел; 'оценка' — расчёт/проекция "
    "на их основе; 'суждение' — наше мнение о вероятности или реакции ЦБ.\n"
    "5. sectors[].winners/losers — тикеры ТОЛЬКО из списка компаний платформы "
    "(context.platform_tickers). Если для сектора не можешь назвать конкретные бумаги "
    "обоснованно — верни пустые списки, но dispersion объясни всё равно. Выдумывать "
    "тикеры или ставить компанию не из списка ЗАПРЕЩЕНО.\n"
    "6. changed_since_last — сверься с previous_issues. Если поменял оценку "
    "траектории, скажи об этом прямо и назови причину. Молча переписывать прошлый "
    "прогноз нельзя: признание пересмотра — это доверие, а не слабость.\n"
    "7. Опирайся на ДИНАМИКУ рядов (series/anchors/direction_vs_previous_point), а не "
    "только на последнее значение: «инфляция замедляется третий месяц» сильнее, чем "
    "«инфляция 6%».\n"
    "8. 🔴 ЧТЕНИЕ ЧИСЕЛ — БЕЗ ОШИБОК: текущее значение показателя ВСЕГДА и ТОЛЬКО в поле "
    "current_value. Поле historical_min_max_24m — это исторические экстремумы за два "
    "года, ими НЕЛЬЗЯ называть сегодняшний уровень. Направление бери из "
    "direction_vs_previous_point ИМЕННО ТОГО показателя и ТОЙ метрики, о которой пишешь: "
    "у одного показателя бывает несколько метрик (mom и yoy у инфляции) и они могут идти "
    "в РАЗНЫЕ стороны — не переноси направление одной на другую. Прежде чем поставить "
    "тег «факт», сверь число с current_value: тег «факт» на числе, которого нет в "
    "данных, — грубейшая ошибка, она разрушает доверие к платформе сильнее, чем "
    "осторожная формулировка.\n"
    "9. 🔴 ЕДИНСТВЕННЫЙ ИСТОЧНИК ЧИСЕЛ О ТЕКУЩЕМ СОСТОЯНИИ — блок key_facts (готовые "
    "выверенные формулировки, СНАЧАЛА смотри туда) и блок indicators "
    "(поле current_value). Числа из analytics (записки ЦБ/ЦМАКП), context.chronicle и "
    "previous_issues бери как СМЫСЛ и аргумент, но НЕ как факт о сегодняшнем уровне: "
    "они могли устареть, относиться к другому периоду ИЛИ К ДРУГОМУ ПОКАЗАТЕЛЮ.\n"
    "   Частая и грубая подмена, которую надо исключить: опрос инФОМ даёт РАЗНЫЕ "
    "величины — «наблюдаемая инфляция» (как население оценивает УЖЕ ПРОШЕДШИЙ рост цен) "
    "и «ожидаемая инфляция на год вперёд». Это НЕ одно и то же, и ни одна из них не "
    "заменяет наш показатель inflation_expectations. Пишешь про инфляционные ожидания — "
    "бери current_value показателя inflation_expectations, а не первое похожее число из "
    "текста записки.\n"
    "10. previous_issues — это ТВОИ ПРОШЛЫЕ СУЖДЕНИЯ, а не данные. Никогда не переноси "
    "оттуда числа в новый выпуск: если в прошлом выпуске была ошибка, копирование "
    "закрепит её навсегда. Сверяй прошлые утверждения с текущими indicators и, если "
    "расходятся, исправляй — и скажи об этом в changed_since_last.\n"
    "Тон спокойный, без «купить/продать». Никакого текста вне JSON."
)


def _methodology() -> str:
    try:
        with open(_METHODOLOGY, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "Методичка недоступна — действуй как старший макроаналитик: МАКРО→СТАВКА→РЫНОК→СЕКТОРА."


def _sectors_list() -> list[str]:
    try:
        with open(_SECTORS, encoding="utf-8") as f:
            data = json.load(f)
        return [v.get("name", k) for k, v in (data.get("sectors") or {}).items()]
    except OSError:
        return []


# Мастер-переменные: по ним даём ПЛОТНЫЙ ряд, а не только опорные точки — именно их
# траекторию инвестор и приходит понять (продуктовая постановка 2026-08-01).
_DENSE_SERIES = {"key_rate", "inflation", "inflation_weekly", "inflation_expectations",
                 "usdrub", "urals", "gdp"}
_DENSE_POINTS = 24        # последние N точек по мастер-переменным
_ANCHOR_MONTHS = (1, 3, 6, 12, 24)   # опорные отсечки по остальным рядам


def _series_digest(db: Session, code: str, metric: str) -> dict | None:
    """Компактная ДИНАМИКА ряда вместо одной последней точки.

    🔴 Найдено 2026-08-01: интерпретатору отдавалось только последнее значение каждого
    показателя, при том что в базе 14 377 точек. Модель рассуждала про «инфляция
    застревает» по одному числу — это догадка из записок ЦБ, а не вывод из ряда.
    Отдавать ряды целиком нельзя (промпт раздуется в разы), поэтому: по мастер-
    переменным — плотный хвост, по остальным — значения на опорных отсечках плюс
    диапазон и направление. Достаточно, чтобы увидеть траекторию, дёшево по токенам.
    """
    rows = (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).limit(900).all())
    if not rows:
        return None
    last = rows[0]
    # 🔴 Имена полей САМООПИСАТЕЛЬНЫЕ (2026-08-01). Первая версия отдавала «range_24m»,
    # и модель прочла его максимум (14.7) как ТЕКУЩЕЕ значение инфляционных ожиданий —
    # написала «ожидания выросли до 14,7%» с тегом «факт», хотя фактически 12,2 и они
    # СНИЖАЮТСЯ. Это не галлютинация модели, а плохой контракт данных: короткое имя
    # поля рядом с числом читается как «ещё одно значение показателя».
    out: dict = {"current_value": float(last.value), "as_of": last.as_of.isoformat(),
                 "preliminary": last.is_preliminary}
    if len(rows) < 2:
        return out

    if code in _DENSE_SERIES:
        tail = list(reversed(rows[:_DENSE_POINTS]))
        out["series"] = [{"d": r.as_of.isoformat(), "v": round(float(r.value), 4)} for r in tail]
    else:
        anchors = {}
        for months in _ANCHOR_MONTHS:
            cutoff = last.as_of - timedelta(days=int(months * 30.44))
            past = next((r for r in rows if r.as_of <= cutoff), None)
            if past is not None:
                anchors[f"{months}m_ago"] = round(float(past.value), 4)
        if anchors:
            out["anchors"] = anchors

    window = [float(r.value) for r in rows if r.as_of >= last.as_of - timedelta(days=730)]
    if len(window) >= 3:
        # Явно «исторические экстремумы», а не просто «range» — чтобы максимум за два
        # года нельзя было спутать с актуальным значением.
        out["historical_min_max_24m"] = {"min": round(min(window), 4), "max": round(max(window), 4)}
        prev = window[1]
        if prev != 0:
            direction = ("растёт" if window[0] > prev
                         else "снижается" if window[0] < prev else "без изменений")
            # Направление всегда вместе с ДОКАЗАТЕЛЬСТВОМ (было → стало по этой же
            # метрике). Без него модель брала direction от месячной инфляции и писала
            # «инфляция растёт», хотя годовая снижалась: две метрики одного показателя
            # шли рядом, а направление выглядело общим для показателя.
            out["direction_vs_previous_point"] = f"{direction} ({round(prev, 4)} → {round(window[0], 4)})"
    return out


def gather_snapshot(db: Session) -> dict:
    """Срез текущих данных платформы для интерпретатора."""
    indicators = []
    for ind in db.query(MacroIndicator).order_by(MacroIndicator.sort_order).all():
        for m in (ind.metric_types or ["level"]):
            dig = _series_digest(db, ind.code, m)
            if dig:
                indicators.append({"code": ind.code, "title": ind.title, "country": ind.country,
                                   "metric": m, "unit": ind.unit, **dig})
    meeting = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
    rate = None
    if meeting:
        rate = {"decision_date": meeting.decision_date.isoformat(),
                "rate_value": float(meeting.rate_value) if meeting.rate_value else None,
                "signal": meeting.signal, "next_meeting_date": meeting.next_meeting_date.isoformat() if meeting.next_meeting_date else None,
                "consensus_forecast": meeting.consensus_forecast, "press_summary": meeting.press_summary}
    docs = [{"source": d.source, "doc_type": d.doc_type, "title": d.title,
             "summary": d.summary, "key_takeaways": d.key_takeaways}
            for d in db.query(MacroAnalyticsDoc).order_by(MacroAnalyticsDoc.created_at.desc()).limit(12).all()]
    forecast = [{"scenario": f.scenario, "indicator": f.indicator, "year": f.year, "value": f.value}
                for f in db.query(MacroForecast).order_by(MacroForecast.as_of.desc()).limit(40).all()]
    return {"key_facts": _key_facts(indicators),
            "indicators": indicators, "rate": rate, "analytics": docs,
            "cb_forecast": forecast, "sectors": _sectors_list(),
            "previous_issues": _previous_issues(db),
            "context": {**_context(db), "platform_tickers": _platform_tickers(db)}}


# Показатели, по которым модель чаще всего ошибается или которые несёт в headline.
# (код, метрика) → человеческая формулировка, однозначно отделяющая похожие величины.
_KEY_FACT_SPECS = (
    ("key_rate", "level", "Ключевая ставка ЦБ"),
    ("inflation", "yoy", "Инфляция год к году"),
    ("inflation_expectations", "level",
     "Инфляционные ОЖИДАНИЯ населения на год вперёд (инФОМ). "
     "НЕ путать с «наблюдаемой инфляцией» из записок — это другая величина"),
    ("usdrub", "level", "Курс USD/RUB"),
    ("urals", "level", "Нефть Urals"),
    ("gdp", "yoy", "ВВП год к году"),
)


def _key_facts(indicators: list[dict]) -> dict:
    """Готовые формулировки по самым важным показателям — первыми в снапшоте.

    🔴 Три прогона подряд (2026-08-01) модель писала «инфляционные ожидания 14,7%»,
    хотя фактически 12,2%: 14,7% — это «наблюдаемая инфляция» из текста записки ЦБ,
    другая величина того же опроса. Запреты в промпте не помогли — модель тянулась к
    первому похожему числу в прозе. Вывод: полагаться на послушание модели нельзя,
    надо дать данные в форме, где ошибиться труднее, чем сделать правильно. Здесь
    величина, дата и направление уже собраны в одну строку — её проще процитировать,
    чем выуживать число из записки.
    """
    by_key = {(i.get("code"), i.get("metric")): i for i in indicators}
    out: dict = {}
    for code, metric, label in _KEY_FACT_SPECS:
        ind = by_key.get((code, metric))
        if not ind or ind.get("current_value") is None:
            continue
        unit = ind.get("unit") or ""
        val = f"{ind['current_value']}{'%' if unit == '%' else (' ' + unit if unit else '')}"
        parts = [f"{val} (на {ind.get('as_of')})"]
        if ind.get("direction_vs_previous_point"):
            parts.append(ind["direction_vs_previous_point"])
        out[label] = ", ".join(parts)
    return out


def _platform_tickers(db: Session) -> list[str]:
    """Тикеры компаний платформы — чтобы модель называла победителей/проигравших
    ТОЛЬКО из нашего покрытия. Без этого списка она сошлётся на бумагу, которой у нас
    нет, и ссылка на карточку никуда не приведёт."""
    try:
        from sqlalchemy import text
        return [r[0] for r in db.execute(text(
            "SELECT ticker FROM companies WHERE ticker IS NOT NULL ORDER BY market_cap DESC NULLS LAST"
        )).all()]
    except Exception:  # noqa: BLE001
        logger.warning("Интерпретатор: список тикеров недоступен", exc_info=True)
        return []


# Темы летописи, релевантные макро-рассуждению (контролируемый словарь chronicle).
# Сознательно НЕ берём корпоративные (dividends/earnings_guidance/ipo_placement) — они
# про отдельные бумаги, для макрокартины шум.
_MACRO_THEMES = ("key_rate", "inflation", "budget_fiscal", "oil_prices", "ruble_fx",
                 "refinery_strikes", "global_macro", "labor_demography", "regulation",
                 "bonds_credit", "commodities", "nationalization")


def _context(db: Session, limit: int = 30) -> dict:
    """Живой контекст, в котором блок рассуждает: летопись + барометры.

    🔴 До 2026-08-01 модель видела только цифры и 12 записок ЦБ/ЦМАКП — то есть
    рассуждала о рынке, не зная, ЧТО НА ПОВЕСТКЕ. Именно из-за этого сценарии выходили
    «сценариями ради сценариев»: без ленты неоткуда узнать, что прямо сейчас реальная
    развилка — топливный кризис, а не абстрактный «бык/медведь». Летопись уже
    LLM-размечена по темам/секторам/тикерам, поэтому отбор дешёвый и точный.

    Всё в try/except: контекст — усиление, а не обязательное условие. Отсутствие
    таблицы (напр. на свежей базе) не должно ронять генерацию блока.
    """
    out: dict = {}
    try:
        from app.models.chronicle import ChronicleEntry
        rows = (db.query(ChronicleEntry)
                .filter(ChronicleEntry.themes.isnot(None))
                .order_by(ChronicleEntry.published_at.desc(), ChronicleEntry.id.desc())
                .limit(400).all())
        picked = []
        for r in rows:
            if not set(r.themes or []) & set(_MACRO_THEMES):
                continue
            picked.append({
                "date": (r.event_date or (r.published_at.date() if r.published_at else None)).isoformat()
                        if (r.event_date or r.published_at) else None,
                "kind": r.kind, "title": r.title,
                "summary": (r.summary or "")[:400],
                "why_it_mattered": (r.interpretation or "")[:300] or None,
                "themes": r.themes, "sectors": r.sectors, "tickers": r.tickers,
                "source_url": r.source_url,
            })
            if len(picked) >= limit:
                break
        if picked:
            out["chronicle"] = picked
    except Exception:  # noqa: BLE001
        logger.warning("Интерпретатор: летопись недоступна", exc_info=True)

    for key, label in (("geo", "geo_barometer"), ("inst", "institutional_barometer")):
        try:
            from app.services.barometer_store import get_payload_with_meta
            payload = get_payload_with_meta(db, key)
            if payload:
                out[label] = _compact_barometer(payload)
        except Exception:  # noqa: BLE001
            logger.warning("Интерпретатор: барометр %s недоступен", key, exc_info=True)
    return out


def _compact_barometer(payload: dict) -> dict:
    """Из барометра берём рамку: что изменилось, чем сейчас живёт повестка, какие
    переходы возможны и на что смотреть в ближайший месяц.

    Полный барометр — десятки килобайт прозы, целиком в промпт не нужен. Но именно
    здесь лежат РЕАЛЬНЫЕ развилки (а не выдуманные «бык/медведь»): триггеры переходов
    между сценариями, вотчлист на 30 дней с ожидаемым эффектом и секторные флаги с
    обоснованием. Ровно то, чего блоку не хватало, чтобы не сочинять сценарии ради
    сценариев.
    """
    out: dict = {"as_of": payload.get("as_of")}
    summary = payload.get("summary")
    if isinstance(summary, str):
        out["what_changed"] = summary[:900]

    sc = payload.get("scenario")
    if isinstance(sc, dict):
        out["scenario"] = {k: v for k, v in sc.items()
                           if k in ("current", "mix_6m", "mix_18m", "probabilities", "triggers", "label")}
    elif isinstance(sc, str):
        out["scenario"] = sc[:400]

    watch = payload.get("watchlist_30d")
    if isinstance(watch, list):
        out["watchlist_30d"] = [
            {k: w.get(k) for k in ("signal", "window", "expected_effect") if w.get(k)}
            for w in watch[:8] if isinstance(w, dict)
        ]

    flags = payload.get("sector_flags")
    if isinstance(flags, list):
        out["sector_flags"] = [
            {k: (str(f.get(k))[:260] if k == "reasoning" else f.get(k))
             for k in ("sector", "direction", "channel", "reasoning") if f.get(k)}
            for f in flags[:10] if isinstance(f, dict)
        ]

    alerts = [a.get("label") or a.get("text") or a.get("title") if isinstance(a, dict) else a
              for a in (payload.get("alerts") or [])[:6]]
    alerts = [str(a)[:200] for a in alerts if a]
    if alerts:
        out["alerts"] = alerts
    return {k: v for k, v in out.items() if v}


def _previous_issues(db: Session, limit: int = 4) -> list[dict]:
    """Прошлые выпуски этого же блока — чтобы модель видела СВОЙ трекшен.

    🔴 До 2026-08-01 каждый прогон начинался с чистого листа: модель не знала, что сама
    писала вчера, и не могла ни признать пересмотр оценки, ни сослаться на него. Для
    платформы, чья главная ценность — доверие, аналитик, молча переписывающий прогноз
    задним числом, хуже, чем аналитик, который говорит «месяц назад ждали иначе, вот
    почему поменяли». Отдаём только каркас прошлого суждения (вердикт + путь ставки +
    развилки), не весь JSON — иначе модель начнёт копировать формулировки.
    """
    rows = (db.query(MacroInterpretation)
            .order_by(MacroInterpretation.generated_at.desc()).limit(limit).all())
    out = []
    for r in rows:
        s = r.sections or {}
        out.append({
            "_note": "ПРОШЛОЕ СУЖДЕНИЕ, не данные. Числа отсюда брать нельзя.",
            "generated_at": r.generated_at.date().isoformat(),
            "headline": _strip_numbers(s.get("headline")),
            "rate_path": _strip_numbers((s.get("rate_path") or {}).get("base")
                                        if isinstance(s.get("rate_path"), dict) else None),
            "forks": [f.get("event") for f in (s.get("forks") or []) if isinstance(f, dict)][:4],
            # старый формат (до переделки) — чтобы переход не потерял историю
            "legacy_theses": [_strip_numbers(t.get("claim"))
                              for t in (s.get("theses") or []) if isinstance(t, dict)][:3],
        })
    return out


def _strip_numbers(text: str | None) -> str | None:
    """Убирает числа из прошлых формулировок, оставляя смысл.

    🔴 Найдено 2026-08-01 на первом же прогоне с памятью: прошлый выпуск содержал
    ошибочное «инфляционные ожидания 14,7%» (модель тогда спутала наблюдаемую инфляцию
    из записки ЦБ с ожиданиями), и следующий выпуск ЭТО СКОПИРОВАЛ. Память, задуманная
    как механизм доверия, начала закреплять ошибку — самовоспроизводящаяся неправда
    опаснее разового промаха. Смысл суждения («ждали паузу в снижении») для трекшена
    сохраняется, а числовые утверждения модель обязана заново взять из indicators.
    """
    if not text:
        return text
    return re.sub(r"\d+[.,]?\d*\s*%?", "…", text)


def generate(db: Session) -> MacroInterpretation:
    """Сгенерировать интерпретацию (Pro reasoning) и сохранить срез."""
    snapshot = gather_snapshot(db)
    system = _methodology() + _OUTPUT_SPEC
    user = ("Данные платформы на текущий момент (используй конкретные значения):\n\n"
            + json.dumps(snapshot, ensure_ascii=False, indent=1))
    model = llm.pro_model()
    # max_tokens поднят с 8192: новый структурированный scenarios (3 сценария × 3 поля)
    # добавил объём, и с thinking=True рассуждение тоже расходует общий бюджет —
    # раньше не хватало на последний ключ scenarios, JSON приходил валидным, но без него.
    out = llm.complete(system, user, json_mode=True, thinking=True,
                       model=model, max_tokens=16000, temperature=0.4)
    sections = out.get("sections") if isinstance(out, dict) else None
    if not sections:
        raise llm.LLMError("Интерпретатор: модель не вернула sections")
    row = MacroInterpretation(
        sections=sections, generated_at=datetime.now(timezone.utc),
        model_used=f"{llm.provider_info().get('provider')}:{model}",
        source_snapshot={"indicators_count": len(snapshot["indicators"]),
                         "has_rate": bool(snapshot["rate"]), "docs": len(snapshot["analytics"]),
                         # Наблюдаемость: по этим флагам видно, КАКОЙ версией кода
                         # сгенерирован срез. Без них при отладке нельзя отличить
                         # «фикс не сработал» от «фикс ещё не доехал на бой» —
                         # ровно на это ушло 4 лишних прогона 2026-08-01.
                         "has_key_facts": bool(snapshot.get("key_facts")),
                         "chronicle": len((snapshot.get("context") or {}).get("chronicle") or []),
                         "prev_issues": len(snapshot.get("previous_issues") or [])})
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Интерпретатор: сгенерирован срез #%d (%s)", row.id, row.model_used)
    return row


def get_latest(db: Session) -> MacroInterpretation | None:
    return db.query(MacroInterpretation).order_by(MacroInterpretation.generated_at.desc()).first()
