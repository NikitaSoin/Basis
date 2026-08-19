"""Движок прогнозной финмодели — оживляет статичную структуру живыми входами.

Методика: docs/financial-model-methodology.md. Паттерн — live_wacc.py
(проверенный прецедент безопасной автономности): аналитик-агент строит
СТРУКТУРУ модели (драйверы/эластичности/сценарные уровни) редко, этот движок
пересчитывает ЧИСЛА от живых входов (Brent/курс/ставка/цена акции) на каждый
запрос — модель не протухает при движении рынка.

Что пересчитывается живьём:
- БАЗОВЫЙ сценарий: строки прогноза корректируются отклонением live-драйверов
  от их base_value через линейные эластичности (бык/медведь НЕ трогаются —
  они уже содержат собственные уровни драйверов в допущениях).
- Форвардные мультипликаторы и апсайд — от живой цены акции (quotes).
- weighted_fair_price — от скорректированной базы.

Барьер здравого смысла: |отклонение живого драйвера| > 40% от base_value →
эластичность линейна только локально — корректировка капируется на 40% и
ставится флаг structure_stale (модель ждёт пересборки аналитиком).
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

_MAX_DRIVER_SHIFT_PCT = 40.0  # дальше эластичности врут — капируем и флагуем


# ----------------------------- живые входы -----------------------------
def _live_brent(db: Session) -> float | None:
    """Биржевая котировка Brent (ICE/NYMEX через macro_oil_sync).

    🔴 Владелец 2026-08-02: «фьючерс с мосбиржи не годится — нужны свежие настоящие
    данные с лондонской биржи». Раньше здесь брался ближайший контракт BR Мосбиржи:
    он привязан к Brent, но это ВТОРИЧНЫЙ инструмент — своя ликвидность, свой базис и
    остановки торгов в российские праздники. Для модели, где цена нефти задаёт выручку
    экспортёра, берём саму биржевую котировку; фьючерс MOEX остался фолбэком на случай
    недоступности внешнего источника.
    """
    try:
        r = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='oil_brent' "
            "AND metric='level' ORDER BY as_of DESC LIMIT 1")).first()
        if r and r[0]:
            return float(r[0])
    except Exception:  # noqa: BLE001
        pass
    try:
        r = db.execute(text(
            "SELECT last_price FROM futures "
            "WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') AND last_price IS NOT NULL "
            "AND expiration_date >= now()::date ORDER BY expiration_date ASC LIMIT 1")).first()
        return float(r[0]) if r and r[0] else None
    except Exception:  # noqa: BLE001
        return None


def _live_usdrub(db: Session) -> float | None:
    try:
        r = db.execute(text(
            "SELECT last_price FROM spot_assets WHERE secid='USD000UTSTOM'")).first()
        if r and r[0]:
            return float(r[0])
        p = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='usdrub' "
            "AND metric='level' ORDER BY as_of DESC LIMIT 1")).first()
        return float(p[0]) if p and p[0] else None
    except Exception:  # noqa: BLE001
        return None


def _live_key_rate(db: Session) -> float | None:
    try:
        p = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='key_rate' "
            "AND metric='level' ORDER BY as_of DESC LIMIT 1")).first()
        return float(p[0]) if p and p[0] else None
    except Exception:  # noqa: BLE001
        return None


def _live_price(db: Session, ticker: str) -> float | None:
    try:
        r = db.execute(text(
            "SELECT q.close FROM quotes q JOIN companies c ON c.id = q.company_id "
            "WHERE c.ticker = :t AND q.close IS NOT NULL "
            "ORDER BY q.date DESC LIMIT 1"), {"t": ticker}).first()
        return float(r[0]) if r and r[0] else None
    except Exception:  # noqa: BLE001
        return None


_LIVE_SOURCES = {
    "futures_brent": _live_brent,
    "cbr_usdrub": _live_usdrub,
    "cbr_key_rate": _live_key_rate,
}


# ----------------------------- пересчёт -----------------------------
def _scaled(value, factor):
    if value is None:
        return None
    try:
        return round(float(value) * factor, 1)
    except (TypeError, ValueError):
        return value


def get_financial_model(db: Session, ticker: str) -> dict | None:
    """Модель с живой корректировкой. None — модели нет (не пилотная компания)."""
    path = COMPANIES_DIR / ticker.upper() / "financial_model.json"
    if not path.exists():
        return None
    try:
        model = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("financial_model.json не читается: %s", ticker)
        return None

    live_notes = []
    structure_stale = False
    # Совокупный поправочный фактор на каждую целевую строку базового сценария:
    # revenue-эластичности транслируем и в ebitda/net_profit/fcf/eps через
    # операционный рычаг НЕ пытаемся — v1 корректирует ТОЛЬКО строки, на которые
    # эластичность указывает target'ом (обычно revenue), и ПРОПОРЦИОНАЛЬНО те
    # строки ниже по P&L, для которых аналитик задал passthrough (см. методичку).
    factors: dict[str, float] = {}

    for drv in model.get("drivers", []):
        if drv.get("kind") != "live":
            continue
        fn = _LIVE_SOURCES.get(drv.get("live_source") or "")
        live_val = fn(db) if fn else None
        base = drv.get("base_value")
        drv["live_value"] = live_val
        if live_val is None or not base:
            drv["live_status"] = "нет живого значения — база"
            continue
        shift_pct = (live_val - base) / base * 100.0
        capped = max(-_MAX_DRIVER_SHIFT_PCT, min(_MAX_DRIVER_SHIFT_PCT, shift_pct))
        if capped != shift_pct:
            structure_stale = True
        drv["live_shift_pct"] = round(shift_pct, 1)
        el = drv.get("elasticity") or {}
        target = el.get("target")
        ppp = el.get("pct_per_pct")
        if target and ppp is not None:
            f = 1.0 + (ppp * capped / 100.0)
            factors[target] = factors.get(target, 1.0) * f
            drv["live_status"] = (f"живое {live_val:g} против базы {base:g} "
                                  f"({shift_pct:+.1f}%) → {target} ×{f:.3f}")
            live_notes.append(drv["live_status"])
        else:
            drv["live_status"] = "живое значение есть, эластичность не задана"

    base_fc = (model.get("forecast") or {}).get("base") or {}
    # Пропорциональная трансляция вниз по P&L: если аналитик задал в модели
    # passthrough (доля переноса Δвыручки в строку), применяем; иначе строка
    # корректируется только собственным фактором.
    passthrough = model.get("passthrough") or {}
    rev_f = factors.get("revenue", 1.0)
    adjusted = {}
    for line, series in base_fc.items():
        if not isinstance(series, dict):
            continue
        line_f = factors.get(line, 1.0)
        # 🔴 Прибыль на акцию — это чистая прибыль, делённая на число акций: если драйвер
        # двинул прибыль (у ставки целевая строка именно она — процентный расход лежит
        # ниже EBITDA), EPS обязана поехать вместе с ней. Без этого модель показывала
        # изменившуюся прибыль при неподвижной прибыли на акцию.
        if line == "eps_rub" and "net_profit" in factors and "eps_rub" not in factors:
            line_f *= factors["net_profit"]
        if line != "revenue" and line in passthrough and rev_f != 1.0:
            # Δстроки = Δвыручки × passthrough (операционный рычаг от аналитика)
            line_f *= 1.0 + (rev_f - 1.0) * float(passthrough[line])
        if line_f != 1.0:
            adjusted[line] = {k: _scaled(v, line_f) for k, v in series.items()}
    if adjusted:
        model.setdefault("live_adjusted_base", {}).update(adjusted)
        model["live_adjusted_note"] = (
            "База скорректирована живыми драйверами (см. drivers[].live_status). "
            "Бык/медведь — авторские уровни аналитика, не корректируются.")

    # Живая цена, форвардные мультипликаторы, апсайд
    price = _live_price(db, ticker)
    model["live_price_rub"] = price
    val = model.get("valuation") or {}
    horizon0 = str((model.get("meta") or {}).get("horizon_years", [date.today().year])[0])
    eps_series = (model.get("live_adjusted_base") or {}).get("eps_rub") or base_fc.get("eps_rub") or {}
    eps_next = eps_series.get(horizon0)
    if price and eps_next:
        try:
            model["forward_pe_live"] = round(price / float(eps_next), 2)
        except (TypeError, ZeroDivisionError, ValueError):
            pass
    # weighted fair price: базу двигаем на фактор выручки-эластичностей примерно
    # НЕ пытаемся — v1 честно оставляет fair_price сценариев авторскими, апсайд
    # считаем от живой цены (протухание цены — главный источник вранья, он закрыт).
    wfp = val.get("weighted_fair_price_rub")
    if price and wfp:
        try:
            model["upside_pct_live"] = round((float(wfp) / price - 1) * 100, 1)
        except (TypeError, ZeroDivisionError, ValueError):
            pass

    model["structure_stale"] = structure_stale
    if structure_stale:
        model.setdefault("data_flags", []).append(
            "Живой драйвер ушёл от базы модели больше чем на 40% — эластичности "
            "линейны только локально, корректировка капирована; структура модели "
            "ждёт пересборки аналитиком.")
    model["live_notes"] = live_notes
    model["as_of"] = date.today().isoformat()
    return model
