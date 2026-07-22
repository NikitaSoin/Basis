"""Синхронизация МЕСЯЧНЫХ мировых цен сырья через публичный chart-эндпоинт
Yahoo Finance (Направление: «Товар компании», commodity_exposure в market.json
компаний, см. .claude/agents/market-analyst.md ОБНОВЛЕНИЕ v6).

🔴 Источник НЕофициальный. В отличие от World Bank Pink Sheet
(macro_wb_commodities_sync.py) — официальный многосторонний источник с явным
открытым доступом — этот эндпоинт (`query1.finance.yahoo.com/v8/finance/chart`)
не документирован Yahoo как публичный API, без ключа/авторизации, широко
используется в open-source (напр. библиотека yfinance), но БЕЗ формального
соглашения об использовании и может быть заблокирован/изменён без
предупреждения. Используем ТОЛЬКО для товаров, у которых нет никакого
официального бесплатного альтернативного ряда (проверено: World Bank Pink
Sheet и FRED/IMF Global Price series палладий не покрывают вообще) —
владелец платформы одобрил этот компромисс явно (2026-07-23).

Курируем ТОЛЬКО палладий (COMEX-фьючерс PA=F, USD/тройскую унцию) — не
расширяем список без отдельного решения владельца, т.к. каждый новый тикер
здесь увеличивает юридическую/операционную хрупкость платформы.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# Yahoo-тикер → наш indicator_code. Курируемый список — см. докстринг файла.
# LBR=F ("Lumber Futures", физически поставляемый контракт CME) заменил старый
# LBS=F ("Random Length Lumber") в 2022 — LBS=F перестал обновляться (мёртвый
# тикер), поэтому история короче остальных (с сентября 2022, не с 2016) —
# ограничение самого контракта, не платформы.
_SYMBOLS = {"PA=F": "yahoo_palladium", "LBR=F": "yahoo_lumber"}
_UNITS = {"yahoo_palladium": "usd/oz", "yahoo_lumber": "usd/mbf"}
_SOURCE_URL = {"PA=F": "https://finance.yahoo.com/quote/PA=F/history",
               "LBR=F": "https://finance.yahoo.com/quote/LBR=F/history"}


def _month_end_of(ts: int) -> date:
    from calendar import monthrange
    d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def sync_yahoo_commodities(db: Session, range_: str = "10y") -> dict:
    """range_ — окно Yahoo chart API ("10y" = вся доступная история; суточный
    крон может звать с меньшим окном, но здесь фиксированный полный охват —
    ряд короткий (1 тикер), пересчитывать целиком дёшево и надёжнее частичного
    догона."""
    out: dict = {}
    for symbol, code in _SYMBOLS.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        try:
            r = httpx.get(url, params={"range": range_, "interval": "1mo"},
                          timeout=25, headers=_HTTP, follow_redirects=True)
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("Yahoo Finance: %s недоступен: %s", symbol, type(e).__name__)
            out[code] = {"error": f"fetch_failed:{type(e).__name__}"}
            continue
        try:
            result = data["chart"]["result"][0]
            timestamps = result.get("timestamp") or []
            closes = result["indicators"]["quote"][0].get("close") or []
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("Yahoo Finance: %s — неожиданный формат ответа: %s", symbol, type(e).__name__)
            out[code] = {"error": f"parse_failed:{type(e).__name__}"}
            continue

        # Yahoo иногда отдаёт два соседних бара для текущего (незакрытого) месяца
        # (частичный + пересчитанный) — оба схлопываются в один and-of месяца
        # через _month_end_of(); без схлопывания это даёт дублирующийся ключ
        # (indicator_code, as_of, metric) внутри ОДНОГО commit-батча, что не
        # ловит upsert_point (сравнивает только с уже закоммиченными строками).
        # Берём последнее по времени наблюдение на каждый месяц.
        by_month: dict[date, float] = {}
        for ts, close in zip(timestamps, closes):
            if close is None:
                continue
            by_month[_month_end_of(ts)] = float(close)

        saved, skipped = 0, 0
        for d, close in sorted(by_month.items()):
            res = upsert_point(db, code, d, "level", close, unit=_UNITS.get(code),
                               source="Yahoo Finance (COMEX, неофициальный источник)",
                               source_url=_SOURCE_URL.get(symbol), ingested_via="yahoo", commit=False)
            if res in ("insert", "revise"):
                saved += 1
            else:
                skipped += 1
        db.commit()
        out[code] = {"saved": saved, "skipped": skipped, "points": len(timestamps)}
        logger.info("Yahoo Finance: %s — %d сохранено, %d без изменений (%d точек в ответе)",
                    symbol, saved, skipped, len(timestamps))
    return out
