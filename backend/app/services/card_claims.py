"""Проверяемые утверждения карточки и их устаревание — БЕЗ LLM, кодом.

🔴 ЗАЧЕМ. Детектор дрейфа есть только у макро: там аналитик оставил в карточке снимок
значений и коэффициенты чувствительности. Для остальных вкладок советник предложил не
изобретать коэффициенты, а извлечь из прозы ПРОВЕРЯЕМЫЕ УТВЕРЖДЕНИЯ и дальше сверять
их кодом. Оказалось, что извлекать почти нечего: у «Рынков» структура уже есть.

В `market.json` лежит:
  current.size.value  — «516 млн т нефти добыто в РФ в 2024 году (−2,8% г/г)»
  current.size_metric — «объём добычи нефти, млн т в год»   ← ЕДИНИЦА, явно
  current.size.certainty — fact | estimate                   ← уровень достоверности
  market_cycle.phases[].period — «2024–2025», «2026–2028»
Покрытие на 2026-08-08: размер рынка есть у 260 карточек из 264, единица — у 263.

🔴 ЧТО ИМЕННО ПРОВЕРЯЕМ. Не «правильное ли число» — этого без внешнего источника не
узнать. Проверяем ГОД, на который утверждение ссылается: если разбор говорит «в 2024
году добыто столько-то», а на дворе 2026-й, то данные за 2025 уже вышли, и утверждение
устарело независимо от того, верным ли оно было. Это тот самый честный код-сигнал:
он не оценивает содержание, а измеряет отставание от календаря.

🔴 ЧЕМ ЭТО ЛУЧШЕ РАЗБОРА ЦЕНЫ РЕГУЛЯРКОЙ (что я пробовал сначала). Там строка «около
$47–57/барр (июль 2026)… к 20 июля ~$57» давала среднее по датам и дням, «$4 073»
распадалось на «4», а у ЧМК цена вообще записана «~37 тыс. руб./т» словом. Год же
записан однозначно, а единица лежит отдельным полем и её не надо угадывать.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_COMPANIES = Path(__file__).parent.parent.parent / "companies"

# Сколько лет отставания считаем устареванием. Год — не порог «плохо/хорошо», а срок
# появления НОВЫХ данных: годовая статистика за прошлый год выходит в первой половине
# текущего, поэтому ссылка на позапрошлый год означает, что свежая цифра уже есть.
_STALE_YEARS = 2


def _load(ticker: str, name: str) -> dict | None:
    p = _COMPANIES / ticker.upper() / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _years(text: str) -> list[int]:
    """Годы, на которые ссылается утверждение. Отсекаем будущее: «прогноз до 2030»
    это не устаревание, а горизонт."""
    now = date.today().year
    return sorted({int(y) for y in re.findall(r"\b(19\d\d|20\d\d)\b", text or "")
                   if int(y) <= now})


def market_claims(ticker: str) -> list[dict]:
    """Утверждения вкладки «Рынки» с годом, единицей и уровнем достоверности."""
    card = _load(ticker, "market.json")
    if not card:
        return []
    now = date.today().year
    out: list[dict] = []
    for m in (card.get("markets") or []):
        cur = (m or {}).get("current") or {}
        size = cur.get("size") or {}
        val = str(size.get("value") or "").strip()
        if val:
            ys = _years(val)
            latest = max(ys) if ys else None
            out.append({
                "market": (m.get("name") or "")[:80],
                "type": "market_size",
                "claim": val[:220],
                "unit": cur.get("size_metric"),
                "certainty": size.get("certainty"),
                "year": latest,
                "lag_years": (now - latest) if latest else None,
                "stale": bool(latest and (now - latest) >= _STALE_YEARS),
            })
        # Фаза цикла: если последний названный период уже закончился, описание
        # «где мы в цикле» говорит о прошлом.
        phases = ((m.get("market_cycle") or {}).get("phases") or [])
        if phases:
            last = phases[-1]
            ys = _years(str(last.get("period") or ""))
            end = max(ys) if ys else None
            out.append({
                "market": (m.get("name") or "")[:80],
                "type": "cycle_phase",
                "claim": f"{last.get('label')} ({last.get('period')})",
                "unit": None, "certainty": "judgement",
                "year": end,
                "lag_years": (now - end) if end else None,
                "stale": bool(end and end < now),
            })
    return out


def finance_claims(ticker: str) -> list[dict]:
    """Утверждение вкладки «Финансы»: за какой период последние отчётные числа."""
    fin = _load(ticker, "financials.json")
    if not fin:
        return []
    years = [int(y) for y in (fin.get("fiscal_years") or [])
             if str(y).isdigit()]
    if not years:
        return []
    now = date.today().year
    last = max(years)
    return [{
        "market": None, "type": "last_reported_year",
        "claim": f"последний отчётный год в карточке — {last}",
        "unit": "год", "certainty": "fact",
        "year": last, "lag_years": now - last,
        "stale": (now - last) >= _STALE_YEARS,
    }]


def card_claims(ticker: str) -> dict:
    """Все проверяемые утверждения карточки + сводка устаревания."""
    claims = market_claims(ticker) + finance_claims(ticker)
    stale = [c for c in claims if c.get("stale")]
    worst = max((c.get("lag_years") or 0) for c in claims) if claims else 0
    return {"ticker": ticker.upper(), "claims": claims,
            "stale_count": len(stale), "max_lag_years": worst}


def stale_queue(limit: int = 30, min_lag: int = _STALE_YEARS) -> list[dict]:
    """Кому из карточек утверждения устарели сильнее всего.

    Очередь строится по ОТСТАВАНИЮ ОТ КАЛЕНДАРЯ, а не по важности компании: цель —
    показать, где разбор ссылается на позапрошлогодние данные, независимо от размера
    эмитента. Приоритизация по деньгам — задача макро-детектора, здесь другая ось.
    """
    rows = []
    for d in sorted(_COMPANIES.iterdir()):
        if not d.is_dir():
            continue
        res = card_claims(d.name)
        if res["stale_count"] and res["max_lag_years"] >= min_lag:
            rows.append({"ticker": d.name, "stale": res["stale_count"],
                         "max_lag_years": res["max_lag_years"],
                         "examples": [c["claim"][:110] for c in res["claims"]
                                      if c.get("stale")][:2]})
    rows.sort(key=lambda r: (-r["max_lag_years"], -r["stale"]))
    return rows[:limit]
