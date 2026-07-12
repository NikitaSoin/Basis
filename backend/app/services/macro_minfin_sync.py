"""Синхронизация госрасходов с пресс-релизов Минфина (Направление 2).

gov_spending_growth — ЕДИНСТВЕННЫЙ показатель отсюда с реальным пайплайном: Минфин
ежемесячно публикует пресс-релиз «Предварительная оценка исполнения федерального
бюджета за <период> <год> года» с ГОТОВЫМ темпом роста расходов г/г прямо в тексте —
вычислять ничего не нужно, только извлечь число (LLM). Раньше показатель имел только
разовый бэкфилл cb_model_big.csv БЕЗ крона, застрявший на 2026-03-28 навсегда.

budget_balance (%ВВП) СОЗНАТЕЛЬНО НЕ реализован здесь: ни в этом пресс-релизе, ни в
ежемесячном XLSX Минфина (minfin.gov.ru/ru/statistics/conbud/, Приложение 8) нет
готового %ВВП — только абсолютный дефицит в млрд руб. Чтобы получить %ВВП, нужен
официальный ГОДОВОЙ НОМИНАЛЬНЫЙ ВВП-знаменатель, которого в конвейере сейчас нет
(FRED даёт только РЕАЛЬНЫЙ ВВП г/г, не номинальный уровень в рублях) — пересчитывать
самим означало бы гадать масштаб и метод не совпадающий с историческими точками CSV
(-1.6%/-2.6%) — риск тихо исказить ряд. Точка расширения на будущее, не выдумываем.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session

from app.services import llm
from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}  # minfin.gov.ru
# 🔴 Прод-IP Timeweb получает 503 от minfin.gov.ru ДАЖЕ с этим UA (проверено 2026-07-12,
# reachable=true в /api/debug/connectivity, но http_status=503, стабильно, не транзиентно —
# похоже на бан по IP/ASN дата-центра WAF'ом, не на UA-фильтр — с домашней сети тот же
# запрос отдаёт 200). MINFIN_BASE_URL — опциональный релей через Cloudflare Worker (тот же
# паттерн, что DEEPSEEK_BASE_URL/FRED_BASE_URL в llm.py/macro_ingest.py) — если владелец
# поднимет Worker, достаточно задать переменную окружения, код подхватит сам, без деплоя.
_BASE = (os.environ.get("MINFIN_BASE_URL") or "https://minfin.gov.ru").rstrip("/")
_PRESS_CENTER = _BASE + "/ru/press-center/"
_SLUG_RE = re.compile(
    r'href="(/ru/press-center/\?id_4=(\d+)-predvaritelnaya_otsenka_ispolneniya_federalnogo_byudzheta_za_'
    r'([a-z]+)-([a-z]+)_(\d{4})_goda)"'
)
_TRANSLIT_MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "mai": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentyabr": 9, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
}

_SYS = (
    "Это пресс-релиз Минфина России «Предварительная оценка исполнения федерального "
    "бюджета». Извлеки темп роста РАСХОДОВ федерального бюджета год-к-году (%, "
    "накопленным итогом с начала года) — фраза вида «...объём расходов федерального "
    "бюджета... составил ... что выше показателей предыдущего года на X% г/г». "
    "Верни строго JSON: {\"spending_growth_yoy\":<число>}. Число может быть отрицательным. "
    "Только из текста, без выдумок. Без текста вне JSON."
)


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return nxt - timedelta(days=1)


def _latest_release() -> tuple[str, date] | str:
    """(url, as_of=конец периода из URL-слага — надёжнее, чем просить LLM угадать дату)
    ЛИБО строка с причиной сбоя (для диагностики через debug-эндпоинт)."""
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(_PRESS_CENTER)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("Минфин-sync: пресс-центр недоступен: %s", type(e).__name__)
        return f"fetch_failed:{type(e).__name__}"
    matches = _SLUG_RE.findall(html)
    if not matches:
        return f"no_matches (html_len={len(html)})"
    href, _id, _start_mon, end_mon, year = sorted(matches, key=lambda m: int(m[1]))[-1]
    month_num = _TRANSLIT_MONTHS.get(end_mon)
    if not month_num:
        return f"bad_month:{end_mon}"
    return _BASE + href, _month_end(int(year), month_num)


def sync_gov_spending(db: Session) -> dict:
    found = _latest_release()
    if isinstance(found, str):
        return {"error": "index", "reason": found}
    url, d = found
    try:
        r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("Минфин-sync: релиз недоступен: %s", type(e).__name__)
        return {"error": "page", "reason": f"{type(e).__name__}: {e}"[:200], "url": url}
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    i = text.find("Пресс-центр", text.find("Пресс-центр") + 1)  # 2-е вхождение — начало статьи, не меню
    text = text[i:i + 4000] if i >= 0 else text[:4000]
    try:
        out = llm.complete(_SYS, text, json_mode=True, max_tokens=300)
    except llm.LLMError:
        return {"error": "llm"}
    try:
        val = float(out.get("spending_growth_yoy"))
    except (TypeError, ValueError):
        val = None
    if val is None or not (-30 <= val <= 60) or d < (date.today() - timedelta(days=60)):
        return {"error": "stale_or_parse"}
    upsert_point(db, "gov_spending_growth", d, "level", val, unit="%", source="Минфин России",
                 source_url=url, ingested_via="minfin")
    return {"date": str(d), "spending_growth_yoy": val}
