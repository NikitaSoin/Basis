"""Пересчёт справедливой стоимости (valuation.methods[].fair_value_per_share) от
ЖИВОЙ безрисковой ставки (доходность 10-летних ОФЗ, MOEX ISS), БЕЗ переоценки
качественных суждений аналитика (нормализация FCF, устойчивый ROE, governance-
дисконт и т.п. остаются как зафиксировал financial-analyst).

Почему пересчёт формулой, а не масштабирование (как в live_multiples.py): цена
справедливой стоимости НЕЛИНЕЙНА от ставки — Gordon growth EV=FCF/(r-g),
P/BV=(ROE-g)/(Ke-g) — линейное масштабирование даст неверный результат при
изменении знаменателя. Поэтому пересчитываем ту же формулу теми же входами,
что зафиксировал аналитик (FCF1, ROE, g, beta, net_cash), заменяя в ставке
дисконтирования только Rf на live-значение.

Метод разделения "заморожен-Rf vs остальная надбавка": financial-analyst
считает r/ke = Rf_frozen + β×ERP + доп.дисконт (governance и т.п., не всегда
отдельным числовым полем). Вместо парсинга текста explain.inputs берём Rf_frozen
и ERP из того же config/market_params.json, который использовал аналитик на
момент прогона (там же и написано "Обновлять раз в квартал — тогда пересчёт у
всех согласован" — то есть это заведомо тот же вход), и восстанавливаем
"остаточную надбавку" вычитанием:
    extra = r_frozen − (Rf_frozen + β×ERP)
    r_live = Rf_live + β×ERP + extra
Это устойчиво к любым доп.корректировкам аналитика (governance-дисконт, ручные
поправки) — они переносятся as-is, меняется только Rf.

Живой Rf берётся из market_params (обновляется еженедельным кроном moex_coefficients
→ update_risk_free_rate, ключ "risk_free_10y") — не HTTP-запрос к MOEX ISS на
каждый рендер карточки (см. get_market_param).

Поддержаны 2 метода (наиболее чувствительные к ставке и наиболее частые):
- DCF (key_assumptions.method_form == "Gordon_from_FCF1"):
    EV = FCF1/(r−g); equity = EV + net_cash; price = equity/shares
- pbv_roe:
    fair_P/BV = (ROE−g)/(Ke−g); price = fair_P/BV × BVPS

Остальные методы (historical_pb/pe, dividend_yield, relative_peers, CAPM) либо не
зависят от Rf по формуле, либо их структурированные key_assumptions не содержат
всех нужных чисел (напр. CAPM.eps_forward живёт только текстом в explain.inputs) —
оставлены статичными: лучше НЕ пересчитывать, чем выдумывать логику поверх
неполных данных. Деградация graceful — при нехватке любого входа метод остаётся
frozen без ошибки.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "market_params.json"


def _as_float(v):
    try:
        f = float(v)
        return f if f == f else None  # NaN-guard
    except (TypeError, ValueError):
        return None


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("live_wacc: config/market_params.json недоступен: %s", e)
        return {}


def get_live_risk_free_10y_pct(db: Session) -> tuple[float | None, str | None]:
    """Живая доходность ОФЗ-10л из market_params (обновляется еженедельным кроном).
    Возвращает (значение, as_of) либо (None, None) при отсутствии — вызывающий
    код должен деградировать на frozen-значение, не падать."""
    row = db.execute(
        text("SELECT value, as_of FROM market_params WHERE key = 'risk_free_10y'")
    ).first()
    if row is None:
        return None, None
    return float(row.value), (row.as_of.isoformat() if row.as_of else None)


def _recompute_dcf_gordon(ka: dict, rf_live_pct: float, rf_frozen_pct: float, erp_pct: float,
                           shares_outstanding: float | None) -> float | None:
    if ka.get("method_form") != "Gordon_from_FCF1":
        return None
    fcf1 = _as_float(ka.get("fcf1_mln"))
    g_pct = _as_float(ka.get("g"))
    r_frozen_pct = _as_float(ka.get("r"))
    net_cash = _as_float(ka.get("net_cash_added_mln")) or 0.0
    beta = _as_float(ka.get("beta")) or 1.0
    if fcf1 is None or g_pct is None or r_frozen_pct is None:
        return None
    if not shares_outstanding or shares_outstanding <= 0:
        return None

    extra_pct = r_frozen_pct - (rf_frozen_pct + beta * erp_pct)
    r_live_pct = rf_live_pct + beta * erp_pct + extra_pct
    denom = r_live_pct / 100 - g_pct / 100
    if denom <= 0:
        return None  # ставка live упала ниже темпа роста — формула Гордона не определена
    ev_live_mln = fcf1 / denom
    equity_live_mln = ev_live_mln + net_cash
    shares_mln = shares_outstanding / 1_000_000
    if shares_mln <= 0:
        return None
    return round(equity_live_mln / shares_mln, 2)


def _recompute_pbv_roe(ka: dict, rf_live_pct: float, rf_frozen_pct: float, erp_pct: float) -> float | None:
    roe_pct = _as_float(ka.get("roe_sustainable"))
    g_pct = _as_float(ka.get("g"))
    ke_frozen_pct = _as_float(ka.get("ke"))
    bvps = _as_float(ka.get("bvps_2025")) or _as_float(ka.get("bvps"))
    beta = _as_float(ka.get("beta")) or 1.0
    if roe_pct is None or g_pct is None or ke_frozen_pct is None or bvps is None:
        return None

    extra_pct = ke_frozen_pct - (rf_frozen_pct + beta * erp_pct)
    ke_live_pct = rf_live_pct + beta * erp_pct + extra_pct
    denom = ke_live_pct / 100 - g_pct / 100
    if denom <= 0:
        return None
    fair_pbv_live = (roe_pct / 100 - g_pct / 100) / denom
    if fair_pbv_live <= 0:
        return None
    return round(fair_pbv_live * bvps, 2)


def live_recompute_valuation(fin: dict, db: Session, shares_outstanding: float | None) -> dict:
    """Возвращает live-пересчитанный fin["valuation"] (или исходный при нехватке
    данных для пересчёта хотя бы одного метода). Не мутирует fin — копирует только
    затронутые методы. Добавляет valuation.live_rf_note с диагностикой для фронта."""
    val = fin.get("valuation") or {}
    methods = val.get("methods")
    if not isinstance(methods, list) or not methods:
        return val

    rf_live_pct, rf_live_as_of = get_live_risk_free_10y_pct(db)
    cfg = _load_config()
    rf_frozen_pct = _as_float(cfg.get("risk_free_rate_pct"))
    erp_pct = _as_float(cfg.get("equity_risk_premium_pct"))

    if rf_live_pct is None or rf_frozen_pct is None or erp_pct is None:
        # Живой Rf ещё не наполнен кроном (первый деплой) или config не читается —
        # отдаём как есть, без пересчёта. Не ошибка, просто "пока нечем пересчитать".
        return val

    new_methods = []
    any_recomputed = False
    for m in methods:
        ka = m.get("key_assumptions") or {}
        live_price = None
        if m.get("method") == "DCF":
            live_price = _recompute_dcf_gordon(ka, rf_live_pct, rf_frozen_pct, erp_pct, shares_outstanding)
        elif m.get("method") == "pbv_roe":
            live_price = _recompute_pbv_roe(ka, rf_live_pct, rf_frozen_pct, erp_pct)

        if live_price is not None:
            m2 = dict(m)
            m2["fair_value_per_share_live"] = live_price
            m2["fair_value_per_share_frozen"] = m.get("fair_value_per_share")
            m2["live_rf_used_pct"] = round(rf_live_pct, 2)
            new_methods.append(m2)
            any_recomputed = True
        else:
            new_methods.append(m)

    if not any_recomputed:
        return val

    out = dict(val)
    out["methods"] = new_methods
    out["live_rf_note"] = {
        "risk_free_10y_live_pct": round(rf_live_pct, 2),
        "risk_free_10y_live_as_of": rf_live_as_of,
        "risk_free_rate_frozen_pct": rf_frozen_pct,
        "erp_pct": erp_pct,
        "explain": ("fair_value_per_share_live пересчитан по формуле метода от живой "
                    "доходности ОФЗ-10л вместо замороженной на дату анализа "
                    "(config/market_params.json); остальные качественные допущения "
                    "(нормализация FCF, устойчивый ROE, доп.дисконты) не меняются. "
                    "fair_value_per_share остаётся исходным для сопоставимости с "
                    "fair_value_range/synthesis_verdict, не пересчитанными этим шагом."),
    }
    return out
