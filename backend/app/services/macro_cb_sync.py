"""Синхронизация блока ставки и среднесрочного прогноза ЦБ (Направление 2, D).

Автоматически (по расписанию) тянет с cbr.ru:
- последнее РЕШЕНИЕ по ключевой ставке: дата, значение, сигнал, дата след. заседания,
  ключевые тезисы → RateMeeting (накапливается: новое заседание добавляется, старые
  остаются); плюс точка key_rate;
- среднесрочный ПРОГНОЗ (базовый сценарий): инфляция/ставка/ВВП по годам → MacroForecast.

Извлечение структуры — LLM (Flash non-thinking, механическая задача). Сетевые ошибки/
смена вёрстки не роняют прогон (лог + пропуск).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models.macro import RateMeeting, MacroForecast, MacroExpertSurvey
from app.services import llm
from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "BasisMacroBot/1.0 (+https://inbasis.ru)"}
_RATE_PAGE = "https://www.cbr.ru/press/keypr/"
_DKP_HUB = "https://www.cbr.ru/dkp/mp_dec/"
_DECISION_PAGE = "https://www.cbr.ru/dkp/mp_dec/decision_key_rate/"  # тут ссылки на комментарии к прогнозу

_RATE_SYS = (
    "Из текста страницы Банка России о решении по ключевой ставке извлеки данные ПОСЛЕДНЕГО "
    "заседания. Верни строго JSON: {\"decision_date\":\"YYYY-MM-DD\", \"rate_value\":<число>, "
    "\"signal\":\"<сигнал/forward guidance кратко>\", \"next_meeting_date\":\"YYYY-MM-DD|null\", "
    "\"theses\":[\"<тезис про инфляцию>\",\"<про спрос>\",\"<про рынок труда>\",\"<про риски>\"]}. "
    "Только факты из текста, без выдумок. Никакого текста вне JSON."
)
_FC_SYS = (
    "Из текста Банка России о среднесрочном прогнозе извлеки таблицы ВСЕХ сценариев, "
    "которые есть в тексте: базовый и, ЕСЛИ присутствуют, альтернативные — "
    "проинфляционный, дезинфляционный, рисковый (как их называет ЦБ). Верни строго JSON: "
    "{\"as_of\":\"YYYY-MM-DD\", \"scenarios\":[{\"scenario\":\"базовый\"|\"проинфляционный\"|"
    "\"дезинфляционный\"|\"рисковый\", \"comment\":\"<1-2 ключевых тезиса этого сценария>\", "
    "\"rows\":[{\"indicator\":\"Инфляция\"|\"Ключевая ставка\"|\"Рост ВВП\", \"year\":<год>, "
    "\"value\":\"<число или диапазон, напр. 4,5–5,5>\"}]}]}. "
    "Бери показатели инфляция, ключевая ставка (средняя), рост ВВП по всем годам прогноза. "
    "Включай ТОЛЬКО сценарии, реально присутствующие в тексте (не выдумывай). "
    "Только из текста. Никакого текста вне JSON."
)


def _fetch_text(url: str, limit: int = 14000) -> str | None:
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync: страница %s недоступна: %s", url, type(e).__name__)
        return None
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _to_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def sync_rate_meeting(db: Session) -> dict:
    """Последнее решение ЦБ по ставке → RateMeeting (накопительно) + точка key_rate."""
    text = _fetch_text(_RATE_PAGE)
    if not text:
        return {"error": "rate page unavailable"}
    try:
        out = llm.complete(_RATE_SYS, text, json_mode=True, max_tokens=1500)
    except llm.LLMError as e:
        logger.warning("CB-sync: ставка не извлечена: %s", e)
        return {"error": "llm"}
    dd = _to_date(out.get("decision_date"))
    if not dd:
        return {"error": "no decision_date"}
    existing = db.query(RateMeeting).filter_by(decision_date=dd).first()
    theses = out.get("theses") or []
    press = "  ".join(f"• {t}" for t in theses if t) or None
    try:
        rate_val = float(out.get("rate_value")) if out.get("rate_value") is not None else None
    except (TypeError, ValueError):
        rate_val = None
    if existing is None:
        db.add(RateMeeting(decision_date=dd, rate_value=rate_val, signal=out.get("signal"),
                           next_meeting_date=_to_date(out.get("next_meeting_date")),
                           press_summary=press, forecast_doc_url=_DKP_HUB))
        action = "inserted"
    else:  # обновляем поля последнего (на случай уточнений), старые заседания не трогаем
        existing.rate_value = rate_val or existing.rate_value
        existing.signal = out.get("signal") or existing.signal
        existing.next_meeting_date = _to_date(out.get("next_meeting_date")) or existing.next_meeting_date
        existing.press_summary = press or existing.press_summary
        action = "updated"
    if rate_val is not None:
        upsert_point(db, "key_rate", dd, "level", rate_val, unit="%", source="ЦБ РФ",
                     source_url=_RATE_PAGE, ingested_via="cbr", commit=False)
    db.commit()
    return {"action": action, "decision_date": str(dd), "rate": rate_val}


def _latest_forecast_url(db: Session) -> str | None:
    """Найти на хабе ДКП ссылку на последний комментарий к среднесрочному прогнозу."""
    text_html = None
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(_DECISION_PAGE)
        r.raise_for_status()
        text_html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync: страница решений недоступна: %s", type(e).__name__)
        return None
    # ссылки на HTML-комментарий к прогнозу (comment_DDMMYYYY) — берём самый свежий
    links = re.findall(r'href="([^"]*comment_\d{8}/?)"', text_html)
    if not links:
        return None
    # самый свежий по дате DDMMYYYY в ссылке
    def _key(u):
        m = re.search(r"comment_(\d{8})", u)
        if not m:
            return ""
        return m.group(1)[4:8] + m.group(1)[2:4] + m.group(1)[0:2]
    best = sorted(links, key=_key)[-1]
    return best if best.startswith("http") else "https://www.cbr.ru" + best


def _save_forecast_scenarios(db: Session, out: dict, url: str) -> dict:
    """Общая логика сохранения scenarios[] (или legacy rows[] верхнего уровня) в
    MacroForecast — переиспользуется и для прогноза при заседании (базовый), и для
    годового ОНДКП (все 4 сценария)."""
    as_of = _to_date(out.get("as_of")) or date.today()
    scenarios = out.get("scenarios")
    if not scenarios:
        scenarios = [{"scenario": out.get("scenario") or "базовый",
                      "comment": out.get("comment"), "rows": out.get("rows") or []}]
    saved = 0
    seen_scen = []
    for sc in scenarios:
        scenario = (sc.get("scenario") or "базовый").strip().lower()
        comment = sc.get("comment")
        seen_scen.append(scenario)
        for r in sc.get("rows") or []:
            ind = (r.get("indicator") or "").strip()
            yr = r.get("year")
            val = r.get("value")
            if not ind or not isinstance(yr, int) or val in (None, ""):
                continue
            existing = (db.query(MacroForecast)
                        .filter_by(as_of=as_of, scenario=scenario, indicator=ind, year=yr).first())
            if existing:
                existing.value = str(val); existing.comment = comment; existing.source_url = url
            else:
                db.add(MacroForecast(as_of=as_of, scenario=scenario, indicator=ind, year=yr,
                                     value=str(val), comment=comment, source_url=url))
            saved += 1
    db.commit()
    return {"as_of": str(as_of), "rows": saved, "scenarios": seen_scen, "url": url}


def sync_forecast(db: Session) -> dict:
    """Среднесрочный прогноз ЦБ — базовый сценарий, обновляется на каждом заседании
    (комментарий к решению по ставке обычно содержит только базовый). Альтернативные
    сценарии — отдельно, см. sync_forecast_annual (публикуются раз в год в ОНДКП)."""
    url = _latest_forecast_url(db)
    if not url:
        return {"error": "forecast url not found"}
    text = _fetch_text(url)
    if not text:
        return {"error": "forecast page unavailable"}
    try:
        out = llm.complete(_FC_SYS, text, json_mode=True, max_tokens=2000)
    except llm.LLMError as e:
        logger.warning("CB-sync: прогноз не извлечён: %s", e)
        return {"error": "llm"}
    return _save_forecast_scenarios(db, out, url)


# ОНДКП — «Основные направления единой государственной денежно-кредитной политики»,
# годовой документ с полным набором сценариев (базовый + дезинфляционный +
# проинфляционный + рисковый). ВАЖНО: HTML-страница (on_2026_2028/) — только обзорная
# статья, реальные таблицы сценариев (Табл. 3.2-3.5) есть ТОЛЬКО в PDF, в разделе 3
# (проверено: страницы ~70-88 из ~180, 0-индексация pypdf). Публикуется ~раз в год
# (окт-ноя) — И URL HTML, И URL PDF меняются год от года, ОБНОВЛЯТЬ при новой версии.
_ONDKP_URL = "https://www.cbr.ru/about_br/publ/ondkp/on_2026_2028/"
_ONDKP_PDF_URL = "https://www.cbr.ru/Content/Document/File/180751/on_2026(2027-2028).pdf"
_ONDKP_PDF_PAGES = (68, 88)  # диапазон [start, end) — весь «Раздел 3. Сценарии» с запасом


def _ondkp_pdf_text() -> str | None:
    try:
        r = httpx.Client(timeout=60, headers=_HTTP, follow_redirects=True).get(_ONDKP_PDF_URL)
        r.raise_for_status()
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(r.content))
        lo, hi = _ONDKP_PDF_PAGES
        parts = [reader.pages[i].extract_text() or "" for i in range(lo, min(hi, len(reader.pages)))]
        return re.sub(r"\s+", " ", " ".join(parts)).strip() or None
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync: ОНДКП PDF недоступен/не распарсен: %s", type(e).__name__)
        return None


def _alt_scenarios_stale(db: Session, max_age_days: int = 300) -> bool:
    """Альтернативные сценарии обновляются ~раз в год — гоняем sync редко (не в
    ежедневном cron), только если давно не обновляли или их нет вовсе."""
    row = (db.query(MacroForecast)
           .filter(MacroForecast.scenario != "базовый")
           .order_by(MacroForecast.as_of.desc()).first())
    if not row:
        return True
    return (date.today() - row.as_of).days > max_age_days


def sync_forecast_annual(db: Session, force: bool = False) -> dict:
    """Альтернативные сценарии (дезинфляционный/проинфляционный/рисковый) из годового
    PDF ОНДКП (HTML-страница — не источник, см. _ONDKP_URL). Дорогой парсинг большого
    PDF + LLM — гоняем редко (staleness-gate), не на каждый ежедневный прогон."""
    if not force and not _alt_scenarios_stale(db):
        return {"skipped": "not_stale"}
    text = _ondkp_pdf_text()
    if not text:
        return {"error": "ondkp pdf unavailable"}
    try:
        out = llm.complete(_FC_SYS, text, json_mode=True, max_tokens=4000)
    except llm.LLMError as e:
        logger.warning("CB-sync: ОНДКП не извлечён: %s", e)
        return {"error": "llm"}
    result = _save_forecast_scenarios(db, out, _ONDKP_URL)
    logger.info("CB-sync: ОНДКП сценарии сохранены: %s", result)
    return result


# Макроэкономический опрос ЦБ — независимый консенсус ~30 аналитиков (не сценарии
# самого ЦБ). Публикуется ежемесячно, страница всегда отдаёт ПОСЛЕДНИЙ опрос по
# тому же URL (без даты в адресе, в отличие от ОНДКП).
_SURVEY_URL = "https://cbr.ru/statistics/ddkp/mo_br/"
_SURVEY_SYS = (
    "Это страница Банка России «Макроэкономический опрос» — медианные прогнозы "
    "профессиональных аналитиков. Извлеки дату проведения опроса (обычно указана "
    "в начале, напр. «5–9 июня 2026»), число респондентов/организаций если указано, "
    "и таблицу медианных прогнозов ПО ГОДАМ для показателей: ИПЦ (инфляция), "
    "Ключевая ставка, ВВП (рост), Курс USD/RUB, Цена нефти. Бери ТЕКУЩИЙ опрос, "
    "не значения из скобок (это предыдущий опрос для сравнения — игнорируй). "
    "Верни строго JSON: {\"as_of\":\"YYYY-MM-DD\" (последний день окна опроса), "
    "\"n_respondents\":<число или null>, \"rows\":[{\"indicator\":\"ИПЦ\"|"
    "\"Ключевая ставка\"|\"ВВП\"|\"Курс USD/RUB\"|\"Цена нефти\", \"year\":<год>, "
    "\"value\":\"<число или диапазон>\"}]}. Только факты из текста, без выдумок. "
    "Никакого текста вне JSON."
)


def _survey_stale(db: Session, max_age_days: int = 25) -> bool:
    row = db.query(MacroExpertSurvey).order_by(MacroExpertSurvey.as_of.desc()).first()
    if not row:
        return True
    return (date.today() - row.as_of).days > max_age_days


def sync_expert_survey(db: Session, force: bool = False) -> dict:
    """Макроэкономический опрос ЦБ (медианный консенсус аналитиков) → MacroExpertSurvey.
    Публикуется раз в месяц — staleness-gate, не гоняем каждый день."""
    if not force and not _survey_stale(db):
        return {"skipped": "not_stale"}
    text = _fetch_text(_SURVEY_URL, limit=20000)
    if not text:
        return {"error": "survey page unavailable"}
    try:
        out = llm.complete(_SURVEY_SYS, text, json_mode=True, max_tokens=1500)
    except llm.LLMError as e:
        logger.warning("CB-sync: опрос аналитиков не извлечён: %s", e)
        return {"error": "llm"}
    as_of = _to_date(out.get("as_of")) or date.today()
    n_resp = out.get("n_respondents") if isinstance(out.get("n_respondents"), int) else None
    saved = 0
    for r in out.get("rows") or []:
        ind = (r.get("indicator") or "").strip()
        yr = r.get("year")
        val = r.get("value")
        if not ind or not isinstance(yr, int) or val in (None, ""):
            continue
        existing = (db.query(MacroExpertSurvey)
                    .filter_by(as_of=as_of, indicator=ind, year=yr).first())
        if existing:
            existing.value = str(val); existing.n_respondents = n_resp
            existing.source_url = _SURVEY_URL
        else:
            db.add(MacroExpertSurvey(as_of=as_of, indicator=ind, year=yr, value=str(val),
                                     n_respondents=n_resp, source_url=_SURVEY_URL))
        saved += 1
    db.commit()
    result = {"as_of": str(as_of), "rows": saved, "n_respondents": n_resp}
    logger.info("CB-sync: макроопрос аналитиков сохранён: %s", result)
    return result


_INFL_PAGE = "https://www.cbr.ru/hd_base/infl/"
_INFL_SYS = (
    "Из текста страницы Банка России об инфляции извлеки ряд ГОДОВОЙ инфляции (% г/г) "
    "за последние доступные месяцы (2025-2026). Ключевая ставка НЕ нужна. Верни строго JSON "
    "{\"rows\":[{\"month\":\"YYYY-MM\", \"yoy\":<число>}]}. Только числа из текста, без выдумок. "
    "Никакого текста вне JSON."
)


def _month_end(ym: str):
    try:
        y, m = ym.split("-")
        y, m = int(y), int(m)
        nm = date(y + (m == 12), (m % 12) + 1, 1)
        from datetime import timedelta
        return nm - timedelta(days=1)
    except (ValueError, AttributeError):
        return None


def sync_inflation(db: Session) -> dict:
    """Свежая годовая инфляция РФ со страницы ЦБ → ряд inflation/yoy (авто-обновление)."""
    text = _fetch_text(_INFL_PAGE)
    if not text:
        return {"error": "infl page unavailable"}
    try:
        out = llm.complete(_INFL_SYS, text, json_mode=True, max_tokens=2000)
    except llm.LLMError as e:
        logger.warning("CB-sync: инфляция не извлечена: %s", e)
        return {"error": "llm"}
    saved = 0
    for r in out.get("rows") or []:
        d = _month_end(r.get("month", ""))
        try:
            yoy = float(r.get("yoy"))
        except (TypeError, ValueError):
            yoy = None
        # future-date guard: страница ЦБ иногда содержит прогнозную строку на
        # конец года рядом с фактическими месячными данными — LLM может её
        # спутать с историей и записать как "фактическую" инфляцию будущего
        # месяца (сломает "последнюю точку" в UI). Инфляция yoy — только факт.
        if d is None or yoy is None or not (-5 <= yoy <= 60) or d > date.today():
            continue
        res = upsert_point(db, "inflation", d, "yoy", yoy, unit="%", source="ЦБ РФ",
                           source_url=_INFL_PAGE, ingested_via="cbr", commit=False)
        if res in ("insert", "revise"):
            saved += 1
    db.commit()
    return {"saved": saved}


_EXP_INDEX = "https://www.cbr.ru/analytics/dkp/inflationary_expectations/"
_EXP_SYS = (
    "Это свежий бюллетень Банка России «Инфляционные ожидания и потребительские настроения» "
    "за указанный месяц. Извлеки ТЕКУЩЕЕ (за этот месяц, не за прошлые периоды сравнения) значение "
    "ожидаемой населением инфляции на ГОД ВПЕРЁД, % (медианная оценка). НЕ бери значения из "
    "ретроспективных сравнений/графиков за прошлые годы. Верни строго JSON {\"expectation\":<число>}. "
    "Без текста вне JSON."
)
_CREDIT_M2_HUB = "https://www.cbr.ru/statistics/macro_itm/dkfs/"
_CREDIT_M2_SYS = (
    "Это таблица «Денежные агрегаты и кредит экономике (основные показатели)» из ежемесячного "
    "бюллетеня Банка России. Извлеки ГОДОВЫЕ темпы прироста (г/г, %) за САМЫЙ ПОСЛЕДНИЙ (правый) "
    "месяц таблицы (не за предыдущий месяц-столбец) для строк: «Денежная масса М2» (НЕ М2Х и НЕ М0), "
    "«Кредит экономике», «Требования к организациям», «Требования к населению». "
    "Верни строго JSON: {\"m2_yoy\":<число>, \"credit_economy_yoy\":<число>, "
    "\"claims_organizations_yoy\":<число>, \"claims_households_yoy\":<число>}. "
    "Число через точку, не через запятую. Только из текста, без выдумок. Без текста вне JSON."
)


def sync_expectations(db: Session) -> dict:
    """Инфляционные ожидания населения (год вперёд) с бюллетеня ЦБ → inflation_expectations."""
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(_EXP_INDEX)
        r.raise_for_status()
        links = re.findall(r'href="([^"]*Infl_exp_\d{2}-\d{2}[^"]*)"', r.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync: индекс ожиданий недоступен: %s", type(e).__name__)
        return {"error": "index"}
    if not links:
        return {"error": "no links"}
    latest = sorted(links, key=lambda u: re.search(r"(\d{2}-\d{2})", u).group(1))[-1]
    url = latest if latest.startswith("http") else "https://www.cbr.ru" + latest
    mm = re.search(r"(\d{2})-(\d{2})", url)  # месяц берём из URL (надёжно)
    d = _month_end(f"20{mm.group(1)}-{mm.group(2)}") if mm else None
    text = _fetch_text(url)
    if not text or d is None:
        return {"error": "page"}
    try:
        out = llm.complete(_EXP_SYS + f"\nМесяц бюллетеня: 20{mm.group(1)}-{mm.group(2)}.",
                           text, json_mode=True, max_tokens=600)
    except llm.LLMError:
        return {"error": "llm"}
    try:
        exp = float(out.get("expectation"))
    except (TypeError, ValueError):
        exp = None
    if exp is None or not (0 <= exp <= 40):
        return {"error": "parse"}
    upsert_point(db, "inflation_expectations", d, "level", exp, unit="%", source="ЦБ РФ (инФОМ)",
                 source_url=url, ingested_via="cbr")
    return {"month": str(d), "expectation": exp}


def _all_credit_m2_pdfs() -> list[tuple[str, str]]:
    """[(url, 'YYYY-MM'), ...] ВСЕХ PDF «Денежные агрегаты и кредит экономике» на хабе
    (обычно последние ~8-12 месяцев), отсортировано по возрастанию месяца — имя файла
    публикуется предсказуемо (credit_m2x_YYYY-MM.pdf), но numeric ID в пути
    /Collection/Collection/File/{id}/ меняется при публикации — берём с хаба."""
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(_CREDIT_M2_HUB)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync credit_m2: хаб недоступен: %s", type(e).__name__)
        return []
    links = re.findall(r'href="(/Collection/Collection/File/\d+/credit_m2x_(\d{4}-\d{2})\.pdf)"', html)
    seen: dict[str, str] = {}
    for href, ym in links:
        seen[ym] = href  # на хабе может быть дубль ссылки на тот же месяц — берём любую
    return [("https://www.cbr.ru" + href, ym) for ym, href in sorted(seen.items())]


def _process_credit_m2_pdf(db: Session, url: str, ym: str) -> dict:
    """Разбор ОДНОГО PDF-бюллетеня → 4 показателя за месяц ym."""
    try:
        r = httpx.Client(timeout=30, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync credit_m2 %s: PDF недоступен: %s", ym, type(e).__name__)
        return {"error": "pdf"}
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join((p.extract_text() or "") for p in reader.pages[:2])
    except Exception as e:  # noqa: BLE001
        logger.warning("CB-sync credit_m2 %s: парсинг PDF упал: %s", ym, type(e).__name__)
        return {"error": "parse_pdf"}
    try:
        out = llm.complete(_CREDIT_M2_SYS, text[:6000], json_mode=True, max_tokens=400)
    except llm.LLMError:
        return {"error": "llm"}
    d = _month_end(ym)
    if d is None:
        return {"error": "bad_date"}
    res = {}
    for code, metric, key in (("m2", "level", "m2_yoy"),
                               ("credit_economy", "yoy", "credit_economy_yoy"),
                               ("claims_organizations", "yoy", "claims_organizations_yoy"),
                               ("claims_households", "yoy", "claims_households_yoy")):
        try:
            val = float(out.get(key))
        except (TypeError, ValueError):
            continue
        if not (-30 <= val <= 60):
            continue
        upsert_point(db, code, d, metric, val, unit="%", source="ЦБ РФ",
                     source_url=url, ingested_via="cbr")
        res[code] = val
    return res or {"error": "parse"}


def sync_credit_m2(db: Session, months_back: int = 1) -> dict:
    """M2 + кредит экономике + требования к организациям/населению — ежемесячные
    PDF-бюллетени ЦБ («Денежные агрегаты и кредит экономике», Табл. 1, страница 2).
    Чинит sync_m2 (старая страница cbr.ru/statistics/ms/ — статичная JS-заглушка с
    2021 года; материал переехал/переименован в апреле 2026, до этого молча копил
    ошибки "page"/"stale_or_parse" 105 дней подряд) + впервые даёт credit_economy/
    claims_organizations/claims_households (раньше — только разовый бэкфилл
    cb_model_big.csv БЕЗ крона, застрявший на 2026-03-28, см. work-journal).
    months_back=1 (суточный крон) — только последний месяц; >1 — бэкфилл истории
    (хаб хранит обычно ~8-12 последних месяцев, дальше история не публикуется)."""
    pdfs = _all_credit_m2_pdfs()
    if not pdfs:
        return {"error": "hub"}
    todo = pdfs[-months_back:]
    out = {}
    for url, ym in todo:
        out[ym] = _process_credit_m2_pdf(db, url, ym)
    return out if months_back > 1 else next(iter(out.values()), {"error": "empty"})


def sync_cb(db: Session) -> dict:
    """Изоляция ошибок ПО КАЖДОЙ подзадаче: раньше необработанное исключение в
    одной (напр. упавшая транзакция БД) прерывало весь словарь — остальные
    синки НИКОГДА не запускались в этом прогоне. Теперь одна упавшая задача не
    блокирует остальные (тот же паттерн, что recalc_all_company_metrics)."""
    out = {}
    for key, fn in (
        ("rate", sync_rate_meeting), ("forecast", sync_forecast),
        ("forecast_annual", sync_forecast_annual), ("expert_survey", sync_expert_survey),
        ("inflation", sync_inflation), ("expectations", sync_expectations),
        ("credit_m2", sync_credit_m2),
    ):
        try:
            out[key] = fn(db)
        except Exception as e:  # noqa: BLE001
            logger.exception("CB-sync: %s упал необработанным исключением: %s", key, e)
            db.rollback()
            out[key] = {"error": f"unhandled:{type(e).__name__}"}
    return out
