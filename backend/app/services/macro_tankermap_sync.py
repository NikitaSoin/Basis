"""Синхронизация ДНЕВНОЙ цены нефти Urals (Направление 2).

Владелец уточнил (2026-07-12): urals нужен НЕ как одна точка в месяц (как остальные
макропоказатели), а полноценный ДНЕВНОЙ ряд для графика — как у котировок инструментов.
Официальных бесплатных дневных котировок Urals не нашлось (ЦБ не публикует, Минфин —
только помесячная цена для налоговых расчётов, ProFinance — стриминговый SSE-протокол
с одноразовыми сессионными токенами, не вскрывается простым HTTP; см. work-journal.md
2026-07-12 про попытку). Нашёлся TankerMap (tankermap.com) — агрегатор танкерных
перевозок нефти, у него ОТКРЫТЫЙ JSON API `/api/market-data/urals` (без авторизации,
без анти-бота), отдаёт дневные бары с 2024-01-09. Источник данных, по их же описанию —
«TankerMap market feed from KuzTerm daily OHLC bars»: это ОЦЕНОЧНАЯ (assessment) цена
физической нефти, не биржевые тики — open/high/low/close у них совпадают (одна дневная
оценка, не внутридневная торговля), это нормально для такого рода бенчмарка, не баг.

Не официальный первоисточник (не ЦБ/Минфин/Росстат) — ingested_via='tankermap',
приоритет как у FRED/World Bank (см. _VIA_PRIORITY в macro_ingest.py), не как у
официальных РФ-источников.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
_API = "https://tankermap.com/api/market-data/urals"


def sync_urals(db: Session, period: str = "3M") -> dict:
    """Дневные точки Urals. period='3M' в суточном кроне (догоняет пропуски за
    выходные/сбои прошлых дней, недорого); period='max' — разовый бэкфилл истории
    (582 дневных бара с 2024-01-09 на момент проверки 2026-07-12)."""
    try:
        r = httpx.get(_API, params={"period": period}, timeout=25, headers=_HTTP)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("TankerMap-Urals: API недоступен: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}
    bars = data.get("bars") or []
    if not bars:
        return {"error": "no_bars"}
    saved = 0
    for b in bars:
        try:
            d = datetime.strptime(b["time"], "%Y-%m-%d").date()
            val = float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (5 <= val <= 300):  # защита от мусора/ошибок фида
            continue
        res = upsert_point(db, "urals", d, "level", val, unit="usd",
                           source="TankerMap (KuzTerm)", source_url=_API,
                           ingested_via="tankermap", commit=False)
        if res in ("insert", "revise"):
            saved += 1
    db.commit()
    logger.info("TankerMap-Urals: %d/%d точек сохранено (период %s)", saved, len(bars), period)
    return {"period": period, "bars": len(bars), "saved": saved}
