"""Цены нефти: Brent, WTI, Urals и спред Urals-Brent (дисконт российской нефти).

🔴 Зачем написан. Ряд Urals тянулся с tankermap.com (оценка KuzTerm) и показывал
$60,7 при рыночных $84,6 — расхождение почти на четверть, причём не разовое: их фид
скачет на ±15% за четыре дня, что для физической нефти нереалистично. Проверено, что
мы читали источник ВЕРНО: на самом tankermap.com стоит та же цифра. То есть подвёл не
парсер, а сам источник. Владелец поймал это, сверив с ProFinance.

Почему oilpriceapi.com: их страница /ru/oil-price отдаёт СРАЗУ три эталона одной
таблицей, совпадает с рынком (Brent 90,12 / WTI 84,67 / Urals 84,56 на 02.08.2026) и
парсится без ключа. API у них платный, но публичная страница открыта.

🔴 Спред Urals-Brent считаем и храним ОТДЕЛЬНЫМ показателем. Это ровно та величина,
которую путают в разборах: рост мировой цены и доходы российских экспортёров — разные
вещи, если одновременно расширяется дисконт. Без явного ряда модель пишет «нефть
выросла, но санкции съедают выгоду», не имея под этим ни одного числа.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_URL = "https://www.oilpriceapi.com/ru/oil-price"

# На странице величины идут подписанными строками таблицы: «Brent Мировой Эталон $90.12».
# Ловим по имени эталона + ближайшую цену, чтобы не поймать соседнее число из текста.
_PATTERNS = {
    "oil_brent": r"Brent[^\d$]{0,40}\$?(\d{2,3}[.,]\d{1,2})",
    "oil_wti": r"WTI[^\d$]{0,40}\$?(\d{2,3}[.,]\d{1,2})",
    "urals": r"Urals[^\d$]{0,40}\$?(\d{2,3}[.,]\d{1,2})",
}
# Коридор правдоподобия: нефть вне этих границ — почти наверняка не та величина
# (проценты, объёмы, цена в рублях), а не исторический экстремум.
_MIN, _MAX = 20.0, 200.0


def _parse(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for code, pat in _PATTERNS.items():
        m = re.search(pat, text)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        if _MIN <= val <= _MAX:
            out[code] = val
    return out


def sync_oil_prices(db: Session) -> dict:
    """Дневные Brent/WTI/Urals + спред. Возвращает, что записано."""
    from app.services.agent_web import fetch_document

    try:
        text = (fetch_document(_URL) or {}).get("text") or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("oil-sync: страница недоступна: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}
    prices = _parse(text)
    if not prices:
        logger.warning("oil-sync: цены не распознаны (изменилась вёрстка?)")
        return {"error": "not_parsed"}

    today = date.today()
    saved = {}
    for code, val in prices.items():
        res = upsert_point(db, code, today, "level", val, unit="usd/bbl",
                           source="OilPriceAPI (публичная страница)", source_url=_URL,
                           ingested_via="oilprice", commit=False)
        saved[code] = {"value": val, "res": res}

    # Дисконт российской нефти: положительное число = Urals ДЕШЕВЛЕ Brent.
    if "oil_brent" in prices and "urals" in prices:
        spread = round(prices["oil_brent"] - prices["urals"], 2)
        upsert_point(db, "urals_brent_spread", today, "level", spread, unit="usd/bbl",
                     source="OilPriceAPI (расчёт: Brent − Urals)", source_url=_URL,
                     ingested_via="oilprice", commit=False)
        saved["urals_brent_spread"] = {"value": spread}
    db.commit()
    logger.info("oil-sync: %s", {k: v.get("value") for k, v in saved.items()})
    return saved
