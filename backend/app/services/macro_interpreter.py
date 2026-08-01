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
# 🔴 v3 (владелец, 2026-08-01): методичка переписана и расширена — 960 строк против 295.
# Она сама задаёт контракт данных (Часть 1), запрет на имитацию модельных величин
# (Часть 0), прогноз ПЯТИ переменных (Часть 14) и формат вывода в два слоя (Часть 19),
# поэтому _OUTPUT_SPEC ниже приведён в соответствие с ней, а не живёт своей жизнью.
_METHODOLOGY = os.path.join(_REPO, "docs", "macro_interpreter_methodology_v3.md")
_METHODOLOGY_LEGACY = os.path.join(_REPO, "docs", "macroeconomics_methodology.md")
_SECTORS = os.path.join(_REPO, "config", "sectors.json")

# Жёсткая инструкция формата вывода (раздел 14 методички) — добавляется к методичке.
# ВАЖНО (2026-07-12, владелец раскритиковал прозу как «простыню», product-analyst-fin
# подтвердил диагноз): раньше current_picture/rate_outlook/cb_forecast_view/market_sectors
# были связным текстом-эссе — числа тонули в повествовании, глазу негде «приземлиться».
# Теперь вывод — атомарные тезисы: каждое поле самостоятельный факт/оценка, без прозы.
_OUTPUT_SPEC = (
    "\n\n================================================================\n"
    "ФОРМАТ ОТВЕТА (СТРОГО JSON, на русском) — реализация ЧАСТИ 19 методички.\n"
    "Текущие значения показателей пересказывать НЕ надо: они уже показаны пользователю в "
    "разделе «Экономическая статистика». Ценность блока — ТРАЕКТОРИЯ, ТРАНСМИССИЯ и "
    "ЧЕСТНАЯ НЕОПРЕДЕЛЁННОСТЬ.\n\n"
    "Верни {\"sections\": {\n"
    "  \"headline\": \"<главный вывод ОДНИМ предложением: что происходит и куда идёт, максимум 28 слов>\",\n"
    "  \"regime\": {\"rate\": \"<снижается|удерживается|растёт>\", \"inflation\": \"<замедляется|стоит|ускоряется>\",\n"
    "               \"economy\": \"<рост|стагнация|спад>\", \"external\": \"<внешний фон, 2-3 слова>\"},\n"
    "  \"theses\": [ // 3-5 штук — ЧАСТЬ 19.3 п.2: в каждом ВИДНА ЦЕПОЧКА\n"
    "    {\"claim\": \"<вывод простым языком, максимум 16 слов>\",\n"
    "     \"chain\": \"<фактор → механизм → следствие, живым языком: не «жёсткая ДКП давит на спрос», а «высокая ставка делает кредит дороже → меньше берут в долг → спрос охлаждается», максимум 30 слов>\",\n"
    "     \"evidence\": \"<конкретные числа-доказательство из key_facts/indicators, максимум 18 слов>\",\n"
    "     \"tag\": \"факт|оценка|суждение\"}\n"
    "  ],\n"
    "  \"event_context\": {  // ЧАСТЬ 19.3 п.3 + модуль Части 16. null, если значимого события нет\n"
    "    \"event\": \"<что случилось>\", \"macro_effect\": \"<как отражается на макро, 2-3 предложения>\",\n"
    "    \"persistence\": \"<разовый шок|устойчивый сдвиг>\", \"tag\": \"факт|оценка|суждение\"},\n"
    "  \"forecasts\": [ // ЧАСТЬ 14 — РОВНО ПЯТЬ переменных, порядок обязателен\n"
    "    {\"variable\": \"Ключевая ставка|Инфляция|Курс рубля|ВВП|Безработица\",\n"
    "     \"horizon\": \"<для ставки: ближайшее заседание / 3-6 мес / 12 мес; для прочих: квартал / год>\",\n"
    "     \"center\": \"<ЦЕНТРАЛЬНАЯ оценка одним числом с единицей — обязательна>\",\n"
    "     \"range\": \"<узкий обоснованный диапазон; вилка «60-100» = «не знаю» в обёртке числа и ЗАПРЕЩЕНА>\",\n"
    "     \"driver\": \"<1-2 фактора, определяющих исход, максимум 14 слов>\",\n"
    "     \"triggers\": \"<наблюдаемые события, при которых прогноз меняется, максимум 16 слов>\",\n"
    "     \"confidence\": \"высокая|средняя|низкая\", \"confidence_why\": \"<причина, максимум 12 слов>\",\n"
    "     \"against\": \"<САМЫЙ СИЛЬНЫЙ контраргумент против этого прогноза — обязателен, максимум 18 слов>\",\n"
    "     \"vs_anchor\": \"<что закладывает ЦБ/рынок и почему мы отличаемся, максимум 18 слов>\"}\n"
    "  ],\n"
    "  \"against_us\": [\"<1-2 сильнейших контраргумента ко всей нашей картине — ЧАСТЬ 19.3 п.5, обязательно>\"],\n"
    "  \"triggers\": [{\"signal\": \"<наблюдаемое событие/дата>\", \"why\": \"<что подтвердит или сломает, максимум 12 слов>\"}], // 2-3\n"
    "  \"sectors\": [ // 4-6 САМЫХ затронутых, ранжируй по силе влияния\n"
    "    {\"sector\": \"<из списка платформы>\", \"wind\": \"попутный|встречный|смешанный\",\n"
    "     \"channel\": \"<каким каналом, максимум 16 слов>\",\n"
    "     \"dispersion\": \"<какой признак делит внутри сектора выигравших и проигравших, максимум 18 слов>\",\n"
    "     \"winners\": [\"<ТИКЕР>\"], \"losers\": [\"<ТИКЕР>\"]}\n"
    "  ],\n"
    "  \"contradictions\": [\"<сигналы во ВХОДНЫХ данных, противоречащие нашему выводу; пусто, если их нет>\"],\n"
    "  \"data_flags\": [\"<где данных не хватило или качество сомнительно>\"],\n"
    "  \"changed_since_last\": \"<что изменилось с прошлого выпуска и пересмотрел ли ты оценку; если нет — так и скажи, максимум 22 слова>\"\n"
    "}}.\n\n"
    "ЖЁСТКИЕ ПРАВИЛА (сверх методички):\n"
    "1. 🔴 ЧАСТЬ 0 — НИКАКИХ ЧИСЕЛ, ИМИТИРУЮЩИХ МОДЕЛЬНЫЙ РАСЧЁТ. Разрыв выпуска, "
    "нейтральная ставка, r*, трендовая инфляция, равновесный курс — только КАК "
    "НАПРАВЛЕНИЕ словами («экономика скорее перегрета: загрузка высокая, безработица у "
    "минимумов»), пока расчётный сервис не отдал величину явно. Выдуманное модельное "
    "число — худший дефект для платформы «второе мнение».\n"
    "2. Прогнозов РОВНО ПЯТЬ, у каждого обязательны center И range, driver, triggers, "
    "confidence, against, vs_anchor. Точечный прогноз без диапазона, диапазон без центра "
    "и прогноз без драйвера — запрещены (Часть 14.4). Если честно сузить вилку нельзя — "
    "СОКРАТИ ГОРИЗОНТ, а не раздувай диапазон.\n"
    "3. Связность пяти прогнозов обязательна (Часть 14.3): «ставка быстро вниз И инфляция "
    "вверх», «курс резко слабеет И инфляция замедляется», «ВВП ускоряется И безработица "
    "растёт» — либо объясни механизм, либо пересмотри прогноз.\n"
    "4. against_us и forecasts[].against — НЕ формальность: сильнейший контраргумент "
    "работает на доверие сильнее, чем уверенный тон.\n"
    "5. Числа о текущем состоянии — из key_facts и indicators.current_value. Из записок, "
    "летописи и previous_issues бери СМЫСЛ, а не числа: при расхождении верь key_facts "
    "(наши ряды проходят «ОТК данных», пересказ записки — нет).\n"
    "6. previous_issues — прошлые СУЖДЕНИЯ, не данные; числа оттуда не переноси.\n"
    "7. sectors[].winners/losers — тикеры ТОЛЬКО из context.platform_tickers; не можешь "
    "назвать обоснованно — оставь списки пустыми, но dispersion объясни.\n"
    "8. Не делай разворотных выводов по одному месяцу (Часть 1): топливо, плодоовощи, "
    "тарифы волатильны. Смотри тренд 3+ месяца и устойчивые компоненты.\n"
    "9. Язык — простой, с видимой логикой. Профессиональный аппарат (Тейлор, кривая "
    "Филлипса, ULC, output gap) — внутренняя кухня, НАРУЖУ НЕ ВЫЛИВАТЬ. Тон спокойный, "
    "без «купить/продать». Никакого текста вне JSON."
)


def _methodology() -> str:
    for path in (_METHODOLOGY, _METHODOLOGY_LEGACY):
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    logger.error("Интерпретатор: методичка НЕ НАЙДЕНА — работаем на голом фолбэке")
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
    # 🔴 ЦЕЛИКОМ, а не пересказом (владелец 2026-08-01). Записки ЦБ/ЦМАКП — первый по
    # ценности источник, и до сих пор модель видела только НАШУ выжимку, сделанную
    # другой LLM и ничем не проверенную. Контекстное окно 1M токенов — места хватает.
    doc_rows = (db.query(MacroAnalyticsDoc)
                .order_by(MacroAnalyticsDoc.created_at.desc()).limit(_DOCS_LIMIT).all())
    try:
        from app.services.article_texts import ensure_full_texts
        ensure_full_texts(db, doc_rows)
    except Exception:  # noqa: BLE001
        logger.warning("Интерпретатор: дозагрузка текстов записок не отработала", exc_info=True)
    docs = [{"source": d.source, "doc_type": d.doc_type, "title": d.title,
             "published_at": d.published_at.isoformat() if d.published_at else None,
             "summary": d.summary, "key_takeaways": d.key_takeaways,
             "source_url": d.source_url,
             # full_text — ПЕРВОИСТОЧНИК; summary оставляем рядом как быстрый ориентир
             "full_text": d.full_text}
            for d in doc_rows]
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
                 "bonds_credit", "commodities", "nationalization", "taxes",
                 "trade_logistics", "sanctions")

# 🔴 Лимиты подняты 2026-08-01 (владелец: «токены дешёвые, не паримся»). Окно модели
# 1 048 576 токенов, использовали 7% — экономить было не на чем.
_DOCS_LIMIT = 16          # записок ЦБ/ЦМАКП с полными текстами (было 12 выжимок)
_CHRONICLE_LIMIT = 60     # записей летописи (было 30)

# Источники-ШУМ: поток заголовков без аналитической ценности. Владелец прямо:
# «все новости с MarketTwits нет смысла». Ценность несут разборы (ЦБ, ЦМАКП, Economist,
# Carnegie, Re:Russia, отраслевые материалы, аналитические телеграм-каналы), а не лента
# однострочных сообщений — она бы просто вытеснила их из выборки объёмом.
_NOISE_SOURCES = {"markettwits", "market twits", "marketwits"}


def _context(db: Session, limit: int | None = None) -> dict:
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
        limit = limit or _CHRONICLE_LIMIT
        rows = (db.query(ChronicleEntry)
                .filter(ChronicleEntry.themes.isnot(None))
                .order_by(ChronicleEntry.published_at.desc(), ChronicleEntry.id.desc())
                .limit(1200).all())
        selected = []
        for r in rows:
            if not set(r.themes or []) & set(_MACRO_THEMES):
                continue
            # Отсеиваем поток заголовков без аналитики (владелец: «все новости с
            # MarketTwits нет смысла») — иначе объёмом вытеснит содержательные разборы.
            src = f"{r.source_key or ''} {r.source_url or ''}".lower()
            if any(n in src for n in _NOISE_SOURCES):
                continue
            selected.append(r)
            if len(selected) >= limit:
                break
        # Первоисточники целиком — для содержательных материалов (разборы, статьи,
        # отраслевые обзоры). Для коротких новостных записей текста и так достаточно.
        try:
            from app.services.article_texts import ensure_full_texts
            deep = [r for r in selected if r.kind in ("article", "report")]
            ensure_full_texts(db, deep, limit=10)
        except Exception:  # noqa: BLE001
            logger.warning("Интерпретатор: дозагрузка текстов летописи не отработала", exc_info=True)
        picked = []
        for r in selected:
            picked.append({
                "date": (r.event_date or (r.published_at.date() if r.published_at else None)).isoformat()
                        if (r.event_date or r.published_at) else None,
                "kind": r.kind, "title": r.title,
                "summary": r.summary,
                "why_it_mattered": r.interpretation or None,
                "themes": r.themes, "sectors": r.sectors, "tickers": r.tickers,
                "source_url": r.source_url,
                "full_text": getattr(r, "full_text", None),
            })
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


# Показатели, чьё числовое значение проверяем в тексте вывода: (код, метрика,
# регулярка-триггер «о чём идёт речь», допуск). Проверяем только те, где ошибка
# критична и распознаётся однозначно.
_NUMBER_CHECKS = (
    ("inflation_expectations", "level", r"инфляционн\w*\s+ожидани\w*|ожидани\w*\s+населени", 0.35),
    ("key_rate", "level", r"ключев\w*\s+ставк|ставка\s+ЦБ", 0.30),
)


def _check_numbers(sections: dict, snapshot: dict) -> list[str]:
    """Ищет в тексте вывода числа, приписанные показателю, но не совпадающие с данными.

    Логика намеренно узкая: берём предложение, где упомянут показатель, вытаскиваем
    из него проценты и сверяем с фактическим значением. Если НИ ОДНО число рядом не
    похоже на факт — это подмена (модель взяла величину из чужого контекста).
    Прогнозные фразы («до 11-12% к концу года») законно содержат другие числа,
    поэтому нарушением считаем только случай, когда фактического значения рядом нет
    вовсе, а какое-то число есть.
    """
    facts = {(i.get("code"), i.get("metric")): i for i in snapshot.get("indicators") or []}
    text = json.dumps(sections, ensure_ascii=False)
    # Режем по ГРАНИЦАМ ПОЛЕЙ JSON, а не по знакам препинания: в одном предложении
    # штатно соседствуют несколько показателей («ставка 14%, но ожидания 14,7%»), и
    # разрез по точке отрывал число от его показателя — на этом валидатор дал ложное
    # срабатывание в первом же прогоне (2026-08-01).
    chunks = re.split(r"\",\s*\"|\":\s*\"", text)
    out: list[str] = []
    for code, metric, trigger, tol in _NUMBER_CHECKS:
        ind = facts.get((code, metric))
        if not ind or ind.get("current_value") is None:
            continue
        actual = float(ind["current_value"])
        for chunk in chunks:
            if not re.search(trigger, chunk, re.I):
                continue
            nums = [float(n.replace(",", ".")) for n in re.findall(r"\d+[.,]?\d*(?=\s*%)", chunk)]
            if not nums:
                continue
            if any(abs(n - actual) <= tol for n in nums):
                continue  # факт рядом есть — прогнозные числа в том же предложении ок
            out.append(
                f"«{ind.get('title') or code}» сейчас {actual}{ind.get('unit') or ''} "
                f"(на {ind.get('as_of')}), а в тексте рядом стоят {nums} — "
                f"похоже, число взято из чужого источника"
            )
            break
    return out


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

    # 🔴 Код-проверка чисел с ОДНОЙ автопоправкой (2026-08-01). История вопроса:
    # модель четыре прогона подряд писала «инфляционные ожидания 14,7%» при
    # фактических 12,2% — брала первое похожее число из прозы записки ЦБ (там 14,7 —
    # это «наблюдаемая инфляция», другая величина того же опроса). Не помогли ни
    # самоописательные имена полей, ни два прямых запрета в промпте, ни блок key_facts
    # с готовыми формулировками первым в снапшоте. Вывод: уговорами класс ошибки не
    # лечится, нужна проверка кодом — тот же принцип, что в «ОТК данных» Макрообзора.
    # Код-проверка чисел — пока в режиме НАБЛЮДЕНИЯ (только лог), без авто-повтора.
    # История: 2026-08-01 я принял за ошибку модели верное значение (ожидания 14,7%),
    # потому что сверял с ЛОКАЛЬНОЙ базой, где лежала испорченная точка 12,2% — тот
    # самый дефект XLSX-LLM-пути, который владелец уже дважды ловил (см. macro_cb_sync,
    # first-write-wins). Правило простое: пока проверка даёт ложные срабатывания,
    # она НЕ должна ни тратить повторный платный вызов, ни клеить предупреждения в
    # публикуемый срез — только сигналить в лог, чтобы её можно было доотладить на
    # реальном потоке.
    try:
        violations = _check_numbers(sections, snapshot)
        if violations:
            logger.warning("Интерпретатор: возможное расхождение чисел (наблюдение): %s", violations)
    except Exception:  # noqa: BLE001
        logger.warning("Интерпретатор: проверка чисел не отработала", exc_info=True)
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
