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


# 🔴 Brent берём БИРЖЕВОЙ котировкой, а не страничной оценкой и не фьючерсом Мосбиржи.
# Владелец 2026-08-02: «фьючерс с мосбиржи не годится — нужны свежие настоящие данные
# с лондонской биржи». BZ=F — контракт на Brent, расчётный по котировкам ICE Futures
# Europe (Лондон); цена совпадает с лондонской с точностью до центов и обновляется в
# течение торгового дня. Прямого бесплатного API у самой ICE нет.
_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_YAHOO_SYMBOLS = {"BZ=F": "oil_brent", "CL=F": "oil_wti"}
_YAHOO_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}


def _exchange_quotes() -> dict[str, float]:
    """Живые биржевые котировки Brent и WTI. Пусто — если биржа недоступна."""
    import httpx

    out: dict[str, float] = {}
    for sym, code in _YAHOO_SYMBOLS.items():
        try:
            r = httpx.get(_YAHOO_CHART.format(sym=sym), params={"range": "5d", "interval": "1d"},
                          timeout=25, headers=_YAHOO_HTTP, follow_redirects=True)
            r.raise_for_status()
            meta = (((r.json().get("chart") or {}).get("result") or [{}])[0].get("meta") or {})
            price = meta.get("regularMarketPrice")
            if isinstance(price, (int, float)) and _MIN <= float(price) <= _MAX:
                out[code] = round(float(price), 2)
        except Exception as e:  # noqa: BLE001
            logger.warning("oil-sync: биржевая котировка %s недоступна: %s", sym, type(e).__name__)
    return out


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
    # 🔴 Порядок источников по смыслу, а не по «свежести любой ценой». Владелец:
    # «не фьючерс — нужен спот». Поэтому: официальный спот EIA (пишется отдельно,
    # с задержкой в несколько дней) → оперативный СПОТ со страницы → и только если
    # спота нет, биржевой ФЬЮЧЕРС BZ=F как последний фолбэк, чтобы цена нефти не
    # исчезла с витрины совсем.
    exchange = _exchange_quotes() if not prices else {}
    for code, val in exchange.items():
        prices.setdefault(code, val)
    if not prices:
        logger.warning("oil-sync: цены не распознаны (изменилась вёрстка?)")
        return {"error": "not_parsed"}

    today = date.today()
    saved = {}
    for code, val in prices.items():
        on_exchange = code in exchange and code not in _parse(text)
        res = upsert_point(
            db, code, today, "level", val, unit="usd/bbl",
            source=("ICE/NYMEX (биржевая котировка)" if on_exchange
                    else "OilPriceAPI (публичная страница)"),
            source_url=(f"https://finance.yahoo.com/quote/{'BZ=F' if code == 'oil_brent' else 'CL=F'}"
                        if on_exchange else _URL),
            ingested_via="oilprice", commit=False)
        saved[code] = {"value": val, "res": res}

    # Скидка на российскую нефть: положительное число = Urals ДЕШЕВЛЕ Brent,
    # отрицательное = ПРЕМИЯ.
    # 🔴 Знак не ограничиваем. Премия физически возможна: когда нефти на рынке не
    # хватает, спрос на российскую может быть выше, чем на эталон (владелец, 03.08).
    # Обе цены берутся из ОДНОГО прогона и одного источника, поэтому разность —
    # настоящий спред, а не следствие разной свежести.
    if "oil_brent" in prices and "urals" in prices:
        spread = round(prices["oil_brent"] - prices["urals"], 2)
        upsert_point(db, "urals_brent_spread", today, "level", spread, unit="usd/bbl",
                     source="OilPriceAPI (расчёт: Brent − Urals)", source_url=_URL,
                     ingested_via="oilprice", commit=False)
        saved["urals_brent_spread"] = {"value": spread}
        if spread < 0:
            logger.info("oil-sync: ПРЕМИЯ к Brent (%.2f) — редкий, но возможный режим",
                        spread)
    db.commit()
    logger.info("oil-sync: %s", {k: v.get("value") for k, v in saved.items()})
    return saved

# 🔴 Официальный якорь ряда — EIA (U.S. Energy Information Administration), серия
# «Europe Brent Spot Price FOB» через FRED. Владелец: «возьми спот с известной
# площадки — чтобы авторитетный источник был». Это СПОТ, а не фьючерс, и это
# госстатистика, а не оценка агрегатора. Минус один: EIA публикует с задержкой в
# несколько дней, поэтому сегодняшнюю цену закрывает оперативная котировка, а когда
# EIA выходит — она эту точку ПЕРЕКРЫВАЕТ (приоритет via 'eia' выше 'oilprice').
_EIA_SERIES = {"DCOILBRENTEU": "oil_brent", "DCOILWTICO": "oil_wti"}


def sync_eia_spot(db: Session, recent: int = 30) -> dict:
    """Официальный спот EIA за последние `recent` наблюдений."""
    import os

    import httpx

    key = os.environ.get("FRED_API_KEY")
    if not key:
        return {"error": "no_fred_key"}
    base = (os.environ.get("FRED_BASE_URL") or "https://api.stlouisfed.org").rstrip("/")
    out: dict = {}
    for sid, code in _EIA_SERIES.items():
        try:
            r = httpx.get(f"{base}/fred/series/observations",
                          params={"series_id": sid, "api_key": key, "file_type": "json",
                                  "sort_order": "desc", "limit": recent}, timeout=25)
            r.raise_for_status()
            obs = r.json().get("observations") or []
        except Exception as e:  # noqa: BLE001
            logger.warning("oil-sync: EIA %s недоступен: %s", sid, type(e).__name__)
            out[code] = {"error": type(e).__name__}
            continue
        saved = 0
        for o in obs:
            val = o.get("value")
            if val in (".", None, ""):
                continue
            try:
                v = float(val)
                d = date.fromisoformat(o["date"])
            except (ValueError, KeyError):
                continue
            if not (_MIN <= v <= _MAX):
                continue
            res = upsert_point(db, code, d, "level", v, unit="usd/bbl",
                               source="EIA (Europe Brent Spot FOB)",
                               source_url=f"https://fred.stlouisfed.org/series/{sid}",
                               ingested_via="eia", commit=False)
            if res in ("insert", "revise"):
                saved += 1
        out[code] = {"saved": saved, "points": len(obs)}
    db.commit()
    return out
