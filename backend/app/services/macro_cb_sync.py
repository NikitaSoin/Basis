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
from datetime import date, datetime

import httpx
from sqlalchemy.orm import Session

from app.models.macro import RateMeeting, MacroForecast
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
    "Из текста комментария Банка России к среднесрочному прогнозу извлеки таблицу БАЗОВОГО "
    "сценария. Верни строго JSON: {\"as_of\":\"YYYY-MM-DD\", \"scenario\":\"базовый\", "
    "\"comment\":\"<1-2 ключевых тезиса прогноза>\", \"rows\":[{\"indicator\":\"Инфляция\"|"
    "\"Ключевая ставка\"|\"Рост ВВП\", \"year\":<год>, \"value\":\"<число или диапазон, напр. 4,5–5,5>\"}]}. "
    "Бери показатели инфляция, ключевая ставка (средняя), рост ВВП по всем годам прогноза. "
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


def sync_forecast(db: Session) -> dict:
    """Среднесрочный прогноз ЦБ (базовый сценарий) → MacroForecast (по году/показателю)."""
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
    as_of = _to_date(out.get("as_of")) or date.today()
    scenario = out.get("scenario") or "базовый"
    comment = out.get("comment")
    saved = 0
    for r in out.get("rows") or []:
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
    return {"as_of": str(as_of), "rows": saved, "url": url}


def sync_cb(db: Session) -> dict:
    return {"rate": sync_rate_meeting(db), "forecast": sync_forecast(db)}
