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

Поддержаны 3 метода (имя метода нормализуется — "P/BV_ROE"/"PBV_ROE"/"pbv_roe"
у разных прогонов аналитика считаются одним и тем же):
- DCF (одностадийный Gordon от FCF1):
    EV = FCF1/(r−g); equity = EV + net_cash; price = equity/shares
- pbv_roe:
    fair_P/BV = (ROE−g)/(Ke−g); price = fair_P/BV × BVPS
- dividend / dividend_DDM (простой "дивиденд/доходность" ИЛИ Гордон-DDM):
    price = numerator/(rate) либо numerator/(rate−g). "numerator" НЕ пересчитывается
    из dps заново (конвенция "текущий/форвардный дивиденд" несогласована между
    компаниями — где-то дивиденд домножается на (1+g), где-то уже форвардный) —
    вместо этого он восстанавливается из УЖЕ ДОВЕРЕННОЙ frozen fair_value_per_share:
    numerator = frozen_price × (rate_frozen [− g]); live_price = numerator/(rate_live [− g]).
    Так пересчёт не зависит от того, как именно был получен numerator.

НЕ пересчитываются: historical_pb/pe и relative_peers (цена строится от
исторических/секторных МУЛЬТИПЛИКАТОРОВ, не от ставки дисконтирования — формулы
для пересчёта попросту нет, а не "не реализовано"); SOTP (сумма частей с холдинг-
дисконтами — слишком разнородная структура между компаниями); CAPM (проверено на
4 компаниях: формула генуинно РАЗНАЯ и иногда НЕОДНОЗНАЧНАЯ даже в одной карточке
— у VTBR key_assumptions одновременно содержит "обоснованный P/E" 208,9₽ и
альтернативный total-return-таргет 84,9₽, и именно ПЕРВЫЙ, менее подходящий по
мнению самого аналитика, оказывается тем fair_value_per_share, что записан —
без ручной проверки по каждой компании легко получить тихо неверное число, тот
же класс риска, что уже дважды ловился на этой фиче на DCF). Деградация graceful
везде — при нехватке/неоднозначности входа метод остаётся frozen без ошибки.
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


def _last_num(arr):
    """Последнее числовое значение временного ряда balance_sheet.* (тот же
    хелпер, что в live_multiples.py — там же и обоснование Decimal-NaN-guard)."""
    if not isinstance(arr, list):
        return None
    for v in reversed(arr):
        f = _as_float(v)
        if f is not None:
            return f
    return None


def _pct(v):
    """Нормализует ставку/темп роста к процентным пунктам (23.6, не 0.236).
    Схема key_assumptions НЕСОГЛАСОВАНА между методами разных прогонов: у SBER
    pbv_roe "ke"/"g" хранятся как проценты (23.6, 3.5), у LKOH DCF "r"/"g" —
    как доли (0.241, 0.035). r/g/ke/roe в этой предметной области всегда в
    диапазоне ~2-40%, поэтому |v|<1 однозначно означает долю (0.241 → 24.1),
    иначе значение уже в процентах. Без этой нормализации формула молча
    получает число в 100 раз меньше знаменателя и цену в разы завышает
    (проверено на LKOH: DCF live улетал в 56 628 ₽ вместо ожидаемых ~5 264 ₽)."""
    f = _as_float(v)
    if f is None:
        return None
    return f * 100 if abs(f) < 1 else f


def _normalize_method(name) -> str:
    """"DCF"/"P/BV_ROE"/"PBV_ROE"/"pbv_roe"/"dividend_DDM" → канонический ключ.
    Разные прогоны financial-analyst называли методы по-разному (регистр,
    слэши, подчёркивания) — без нормализации часть методов молча выпадала из
    пересчёта просто по имени, не по нехватке данных (найдено на бою: VTBR/MOEX
    используют "P/BV_ROE"/"PBV_ROE", а не "pbv_roe")."""
    n = "".join(ch for ch in str(name or "").lower() if ch.isalnum())
    if n == "dcf":
        return "dcf"
    if n in ("pbvroe",):
        return "pbvroe"
    if "dividend" in n:
        return "dividend"
    return n


def _live_rate_pct(ka: dict, rf_live_pct: float, rf_frozen_pct: float, erp_pct: float,
                    rate_fields: tuple[str, ...]) -> tuple[float | None, float | None]:
    """Ищет ставку дисконтирования/требуемую доходность по списку возможных имён
    полей (порядок = приоритет). Если рядом есть beta — восстанавливает остаточную
    надбавку (governance и т.п.) через тот же приём, что DCF/pbv_roe: extra =
    rate_frozen − (Rf_frozen + β×ERP), rate_live = Rf_live + β×ERP + extra. Если
    beta не задана (напр. required_yield — рыночное суждение, не CAPM-формула) —
    параллельный сдвиг на дельту живой ставки: rate_live = rate_frozen + (Rf_live
    − Rf_frozen). Возвращает (rate_live_pct, rate_frozen_pct) либо (None, None)."""
    for field in rate_fields:
        if field not in ka:
            continue
        rate_frozen_pct = _pct(ka.get(field))
        if rate_frozen_pct is None:
            continue
        beta = _as_float(ka.get("beta"))
        if beta is not None:
            extra_pct = rate_frozen_pct - (rf_frozen_pct + beta * erp_pct)
            rate_live_pct = rf_live_pct + beta * erp_pct + extra_pct
        else:
            rate_live_pct = rate_frozen_pct + (rf_live_pct - rf_frozen_pct)
        return rate_live_pct, rate_frozen_pct
    return None, None


def _recompute_dividend(m: dict, rf_live_pct: float, rf_frozen_pct: float, erp_pct: float) -> float | None:
    ka = m.get("key_assumptions") or {}
    frozen_price = _as_float(m.get("fair_value_per_share"))
    if frozen_price is None or frozen_price <= 0:
        return None

    # Неоднозначность IRAO-класса: если "ke"/"r" (Гордон) И "required_yield"
    # (прямая доходность) присутствуют ОДНОВРЕМЕННО как отдельные числа — это
    # два конкурирующих подхода в одном методе, и по какому из них на самом деле
    # взят fair_value_per_share, надёжно не определить без ручной проверки
    # (см. модуль docstring, VTBR-кейс в CAPM — тот же класс риска). Пропускаем.
    has_gordon_rate = any(f in ka for f in ("ke", "r"))
    has_required_yield = "required_yield" in ka
    if has_gordon_rate and has_required_yield:
        return None

    g_pct = _pct(ka.get("g_div") if "g_div" in ka else ka.get("g"))

    rate_live_pct, rate_frozen_pct = _live_rate_pct(
        ka, rf_live_pct, rf_frozen_pct, erp_pct, rate_fields=("ke", "r", "required_yield"))
    if rate_live_pct is None or rate_frozen_pct is None:
        return None

    if g_pct is not None:
        denom_frozen = rate_frozen_pct / 100 - g_pct / 100
        denom_live = rate_live_pct / 100 - g_pct / 100
    else:
        denom_frozen = rate_frozen_pct / 100
        denom_live = rate_live_pct / 100
    if denom_frozen <= 0 or denom_live <= 0:
        return None

    numerator = frozen_price * denom_frozen
    return round(numerator / denom_live, 2)


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


def _recompute_dcf_gordon(ka: dict, fin: dict, rf_live_pct: float, rf_frozen_pct: float, erp_pct: float,
                           shares_outstanding: float | None) -> float | None:
    # method_form — необязательная аннотация; часть прогонов её не проставляла
    # (напр. ROSN), хотя структура key_assumptions та же самая одностадийная
    # Gordon-модель. Явно исключаем только СЛУЧАИ С ДРУГОЙ формой (если поле
    # присутствует и говорит "не Gordon"), не требуем его наличия.
    method_form = ka.get("method_form")
    if method_form is not None and method_form != "Gordon_from_FCF1":
        return None
    fcf1 = _as_float(ka.get("fcf1_mln"))
    g_pct = _pct(ka.get("g"))
    r_frozen_pct = _pct(ka.get("r"))
    beta = _as_float(ka.get("beta")) or 1.0
    if fcf1 is None or g_pct is None or r_frozen_pct is None:
        return None
    # net_cash: приоритет — точное число, которое использовал аналитик в
    # key_assumptions (как у LKOH); если его нет (большинство компаний — поле
    # необязательное), берём balance_sheet.net_debt (тот же общий источник,
    # что live_multiples.py уже использует для EV/EBITDA) — последнее известное
    # значение временного ряда, знак инвертирован (net_debt>0 вычитается из EV,
    # net_debt<0 = чистая денежная позиция прибавляется). Если ни того, ни
    # другого нет — НЕ рискуем игнорировать долг молча, метод остаётся frozen.
    if "net_cash_added_mln" in ka:
        net_cash = _as_float(ka.get("net_cash_added_mln"))
        if net_cash is None:
            return None
    else:
        net_debt = _last_num((fin.get("balance_sheet") or {}).get("net_debt"))
        if net_debt is None:
            return None
        net_cash = -net_debt
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
    roe_pct = _pct(ka.get("roe_sustainable"))
    g_pct = _pct(ka.get("g"))
    ke_frozen_pct = _pct(ka.get("ke"))
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
        # Никогда не пересчитываем метод, который сам аналитик пометил ненадёжным
        # (insufficient_data/not_applicable) — у таких методов часто fair_value_
        # per_share=null именно потому, что формула даёт мусор (напр. GAZP DCF:
        # equity отрицателен при полной структуре капитала с долгом).
        if m.get("status") == "ok":
            method_key = _normalize_method(m.get("method"))
            if method_key == "dcf":
                live_price = _recompute_dcf_gordon(ka, fin, rf_live_pct, rf_frozen_pct, erp_pct, shares_outstanding)
            elif method_key == "pbvroe":
                live_price = _recompute_pbv_roe(ka, rf_live_pct, rf_frozen_pct, erp_pct)
            elif method_key == "dividend":
                live_price = _recompute_dividend(m, rf_live_pct, rf_frozen_pct, erp_pct)

        # Барьер здравого смысла: для сильно закредитованных компаний equity =
        # EV − net_debt ставит equity на "плечо" к ставке — малое движение Rf
        # даёт непропорциональный скачок (вплоть до отрицательной цены), формула
        # технически верна, но результат бесполезен/пугающий для пользователя.
        # Обнаружено на бою: MTSS/MGNT/OZON ушли в минус, MOEX — в 3,4× frozen.
        # Не публикуем live вне разумного диапазона относительно frozen — лучше
        # молча остаться на frozen, чем показать инвестору отрицательную "справедливую
        # стоимость".
        if live_price is not None:
            frozen_price = _as_float(m.get("fair_value_per_share"))
            if live_price <= 0 or not frozen_price or frozen_price <= 0:
                live_price = None
            else:
                ratio = live_price / frozen_price
                if ratio < 0.3 or ratio > 3.0:
                    live_price = None

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
