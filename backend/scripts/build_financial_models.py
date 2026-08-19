#!/usr/bin/env python3
"""Сборка структуры прогнозной финмодели из УЖЕ СДЕЛАННЫХ слоёв карточки.

🔴 ЧТО ЭТО И ЧЕМ НЕ ЯВЛЯЕТСЯ. Это не «генератор моделей» и не замена аналитику. Это
ТРАНСЛЯТОР: методика (docs/financial-model-methodology.md, раздел «Связь с существующими
слоями») прямо предписывает не изобретать заново, а брать эластичности из стресс-движка,
сценарии из карточки, дивиденд из дивполитики. Всё это уже посчитано аналитиками по
каждой компании и лежит в файлах. Сборщик делает над этими суждениями арифметику —
и ничего не выдумывает сверх них.

Проверено на пилоте: механический пересчёт воспроизводит числа, которые аналитик вывел
руками для ЛУКОЙЛа. Эластичность курса (41,0 млрд ₽ на 1 ₽ при выручке 3 767,8 млрд и
курсе 78) = 0,849 — в авторской модели 0,85. Passthrough в EBITDA 12,3/41 = 0,30 — в
модели 0,30. Совпадение не случайно: аналитик СЧИТАЛ ровно это, только руками.

🔴 ЧЕГО СБОРЩИК НЕ ДЕЛАЕТ НИКОГДА (нужен человек/аналитик):
  • не нормализует прибыль — код не знает, что разовое. Где в карточке есть adjusted-ряд,
    берём его; где нет — ставим флаг «прибыль не нормализована»;
  • не строит мост прибыли — пустой блок честнее тривиальной декомпозиции;
  • не пересматривает веса сценариев и не капитализирует опционы;
  • не трогает БАНКИ: шаблон «выручка → EBITDA → passthrough» для них бессмыслен
    (у Сбера модель авторская, bespoke).

🔴 И ГЛАВНОЕ — НЕ ЗАВОДИТ ВТОРОЕ ЧИСЛО СПРАВЕДЛИВОЙ ЦЕНЫ. Если оценка модели уходит от
`valuation.fair_value_range` карточки больше чем на 15%, блок valuation НЕ ПУБЛИКУЕТСЯ:
прогноз и чувствительность остаются, цена — нет, тикер идёт в очередь аналитику.
Расхождение здесь — диагноз, а не второе мнение (тот же принцип, что у гейта правок).

Запуск:
  python3 backend/scripts/build_financial_models.py            # сухой прогон по всем
  python3 backend/scripts/build_financial_models.py --apply    # записать
  python3 backend/scripts/build_financial_models.py --ticker LKOH --shadow  # сверка с авторской
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

MODEL_VERSION = "v1-auto"
FAIR_TOLERANCE_PCT = 15.0     # дальше — valuation модели не публикуется
MIN_BASE_YEAR = 2024          # база старее — модель не строим

# коэффициент чувствительности → живой источник движка (см. _LIVE_SOURCES в
# financial_model.py). Чего нет в этом списке, становится assumption — честная
# деградация: движок такой драйвер не оживляет, и это видно на витрине.
LIVE_SOURCE = {"fx": "cbr_usdrub", "rate": "cbr_key_rate", "commodity": "futures_brent"}
DRIVER_NAME = {"fx": "Курс USD/RUB", "rate": "Ключевая ставка ЦБ", "commodity": "Цена сырья, $"}
SPOT_KEY = {"fx": "fx_usdrub", "rate": "key_rate_pct", "commodity": "commodity_usd"}
PER_UNIT = {"fx": 1.0, "rate": 1.0, "commodity": 1.0}  # шаг коэффициента в единицах драйвера
# «commodity» у нефтяников привязан к Urals/Brent — движок умеет только Brent; у
# металлургов и золотодобытчиков свой товар, живого источника нет.
COMMODITY_LIVE_SECTORS = {"oil_gas", "нефть и газ", "нефтегаз"}

# 🔴 Куда «целится» коэффициент. У ставки выручка почти никогда не задета (13 карточек из
# 258), а прибыль задета почти всегда (249) — процентный канал бьёт по прибыли, а не по
# продажам. Поэтому у rate целевая строка net_profit, а не revenue: иначе движок не
# оживлял бы ставку вообще ни у кого.
# 🔴 Порядок предпочтения целевой строки. Вторым эшелоном идёт EBITDA, а не сразу
# прибыль: у 2025 года у многих компаний ОТЧЁТНАЯ чистая прибыль отрицательна из-за
# разовых списаний (Магнит −16,7, Озон −0,9, РУСАЛ −455), и эластичность «в процентах
# от прибыли» на такой базе бессмысленна. EBITDA положительна гораздо чаще и стоит
# выше разовых статей. Для ставки EBITDA не годится по смыслу — процентный расход
# лежит НИЖЕ неё; там либо прибыль, либо драйвер остаётся без эластичности.
TARGET_PREFERENCE = {"fx": ("revenue", "ebitda", "net_profit"),
                     "commodity": ("revenue", "ebitda", "net_profit"),
                     "rate": ("net_profit",)}

# базовый уровень драйвера, когда в карточке пуст macro_spot (у X5 он null): берём
# платформенный снимок макро — тот же источник, что видит пользователь на Обозревателе
_SNAPSHOT = ROOT / "frontend" / "Basis" / "scripts" / "data" / "macro-snapshot.json"
_SNAP_CODE = {"fx": "usdrub", "rate": "key_rate", "commodity": "oil_brent"}


def _snapshot_levels() -> dict:
    try:
        rows = json.loads(_SNAPSHOT.read_text(encoding="utf-8")).get("rows") or []
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for r in rows:
        lvl = ((r.get("values") or {}).get("level") or {}).get("value")
        if r.get("code") and isinstance(lvl, (int, float)):
            out[r["code"]] = float(lvl)
    return out


_SNAP = _snapshot_levels()


def _load(ticker: str, name: str) -> dict:
    p = COMPANIES / ticker / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _last_actual(series, years) -> tuple[float | None, int | None]:
    """Последнее непустое значение ряда и его год."""
    if not isinstance(series, list):
        return None, None
    for i in range(min(len(series), len(years)) - 1, -1, -1):
        v = series[i]
        if isinstance(v, (int, float)):
            return float(v), years[i]
    return None, None


def _unit_factor(fin_meta: dict) -> float:
    """Во сколько единиц карточки укладывается 1 млн ₽ — чтобы привести
    quant_inputs (у него свои единицы) к единицам карточки."""
    return {"млн": 1.0, "тыс": 1000.0, "млрд": 0.001}.get((fin_meta.get("unit") or "").strip(), 1.0)


def _scenario_growth(sc: dict) -> dict[str, float]:
    """Средний темп роста выручки по годам из market.json. Диапазон low/high
    сводим к середине — конвенция, зафиксирована в derivation."""
    out = {}
    for row in (sc.get("revenue_growth") or []):
        per = str(row.get("period") or "").strip()
        lo, hi = row.get("low_pct"), row.get("high_pct")
        vals = [x for x in (lo, hi) if isinstance(x, (int, float))]
        if per and vals:
            out[per] = sum(vals) / len(vals)
    return out


def build(ticker: str) -> tuple[dict | None, list[str]]:
    """Возвращает (модель | None, причины отказа)."""
    reject: list[str] = []
    fin = _load(ticker, "financials.json")
    if not fin:
        return None, ["нет financials.json"]
    meta = fin.get("meta") or {}
    years = meta.get("fiscal_years") or []
    if fin.get("bank_pnl") or fin.get("bank_metrics"):
        return None, ["банк — шаблон выручка/EBITDA неприменим, только авторская модель"]

    ins = fin.get("income_statement") or {}
    rev0, base_year = _last_actual(ins.get("revenue"), years)
    ebitda0, _ = _last_actual(ins.get("ebitda"), years)
    np0, _ = _last_actual(ins.get("net_profit"), years)
    if not rev0 or rev0 <= 0:
        reject.append("нет базовой выручки")
    if base_year is None or int(base_year) < MIN_BASE_YEAR:
        reject.append(f"база устарела ({base_year})")

    macro = _load(ticker, "macro.json")
    qi = macro.get("quant_inputs") or {}
    coefs = qi.get("coefficients") or {}
    spot = qi.get("macro_spot") or qi.get("macro_current") or {}
    qfin = qi.get("financials") or {}
    if not coefs:
        reject.append("нет коэффициентов чувствительности")

    market = _load(ticker, "market.json")
    scenarios = (((market.get("valuation_inputs") or {}).get("explicit_horizon") or {})
                 .get("scenarios") or {})
    if not all(k in scenarios for k in ("base", "bull", "bear")):
        reject.append("в market.json нет трёх сценариев")
    if reject:
        return None, reject

    # --- единицы: quant_inputs живёт в своих, карточка в своих ---
    qrev = qfin.get("revenue")
    unit_note = None
    q_to_card = 1.0
    if isinstance(qrev, (int, float)) and qrev > 0:
        ratio = rev0 / qrev
        # ожидаем 1 (те же единицы), 1000 (карточка в тыс, quant в млн) либо 1000 наоборот
        # Сводим по ПОРЯДКУ ВЕЛИЧИНЫ, а не по точному совпадению: у quant_inputs своя база
        # года (бывает другой период или нормализованная величина), поэтому требовать
        # равенства выручки нельзя — иначе теряем 18 карточек на ровном месте. Важно
        # только, в каких единицах записан коэффициент.
        for cand, label in ((1.0, "те же"), (1000.0, "×1000"), (0.001, "÷1000")):
            if 0.3 <= ratio / cand <= 3.0:
                q_to_card = cand
                unit_note = f"quant_inputs → карточка: {label} (отношение баз {ratio:.3g})"
                break
        if unit_note is None:
            return None, [f"единицы quant_inputs и карточки не сводятся (отношение {ratio:.4g})"]

    horizon = sorted({p for sc in scenarios.values() for p in _scenario_growth(sc)})[:3]
    if len(horizon) < 2:
        return None, ["в сценариях нет числовых темпов роста"]

    # --- драйверы: абсолютная чувствительность → %-эластичность ---
    drivers = []
    flags: list[str] = []
    sector = (meta.get("sector") or "").lower()
    for key, c in coefs.items():
        if key not in LIVE_SOURCE:
            continue
        base_val = spot.get(SPOT_KEY[key])
        if not isinstance(base_val, (int, float)) or not base_val:
            base_val = _SNAP.get(_SNAP_CODE[key])
        if not isinstance(base_val, (int, float)) or not base_val:
            continue
        # какую строку двигает драйвер: первая из предпочтений, где коэффициент заполнен
        target = None
        for cand in TARGET_PREFERENCE[key]:
            v = c.get(cand)
            if isinstance(v, (int, float)) and v:
                target, d_val = cand, float(v)
                break
        live_ok = key != "commodity" or any(s in sector for s in COMMODITY_LIVE_SECTORS)
        drv = {
            "key": {"fx": "usd_rub", "rate": "key_rate", "commodity": "commodity_usd"}[key],
            "name": DRIVER_NAME[key],
            "kind": "live" if live_ok else "assumption",
            "base_value": round(float(base_val), 4),
            "applies_to": "revenue",
            "cross_check_stress": {k: c.get(k) for k in ("per", "revenue", "ebitda", "net_profit")},
            "derivation": (c.get("assumption") or "")[:900],
            "source_of_coefficient": c.get("source"),
        }
        if live_ok:
            drv["live_source"] = LIVE_SOURCE[key]
        else:
            flags.append(f"драйвер «{DRIVER_NAME[key]}» без живого источника — движок его не оживляет")
        base_line = {"revenue": rev0, "ebitda": ebitda0, "net_profit": np0}.get(target)
        if target and base_line and base_line > 0:
            # Δстроки на шаг драйвера → %/% на базе года и базовом уровне драйвера
            ppp = (d_val * q_to_card / base_line) * (float(base_val) / PER_UNIT[key])
            drv["applies_to"] = target
            drv["elasticity"] = {
                "target": target, "pct_per_pct": round(ppp, 3),
                "derivation": (f"из стресс-коэффициента: {c.get('per')} → {target} "
                               f"{d_val:+g} при базе {base_line:,.0f} и уровне драйвера "
                               f"{base_val:g}. Пересчёт абсолютной чувствительности в "
                               f"эластичность — арифметика, не новое суждение."),
            }
        if "elasticity" not in drv:
            drv["no_elasticity_reason"] = (
                "база строки, на которую действует драйвер, не положительна в базовом году "
                "(разовые списания) — эластичность в процентах на такой базе бессмысленна; "
                "коэффициент сохранён как справочный")
        drivers.append(drv)
    if not any(d.get("kind") == "live" and d.get("elasticity") for d in drivers):
        return None, ["ни одного живого драйвера с эластичностью"]

    # --- passthrough: нетто-ретенция из тех же коэффициентов ---
    passthrough, pt_src = {}, []
    for key in ("fx", "commodity"):
        c = coefs.get(key) or {}
        r = c.get("revenue")
        if not isinstance(r, (int, float)) or not r:
            continue
        for line, field in (("ebitda", "ebitda"), ("net_profit", "net_profit")):
            v = c.get(field)
            if isinstance(v, (int, float)):
                passthrough.setdefault(line, []).append(float(v) / float(r))
        pt_src.append(key)
    passthrough = {k: round(sum(v) / len(v), 3) for k, v in passthrough.items() if v}
    if passthrough:
        passthrough["eps_rub"] = passthrough.get("net_profit")
        passthrough["basis"] = ("Доля переноса Δвыручки в строки ниже по P&L — нетто-ретенция "
                                f"из стресс-коэффициентов (каналы: {', '.join(pt_src)}). "
                                "Разница между приростом выручки и приростом прибыли — "
                                "переменные налоги и издержки, они уже учтены в коэффициенте.")
        passthrough = {k: v for k, v in passthrough.items() if v is not None}

    # --- прогноз по сценариям: темпы из market.json, маржа базового года ---
    ebitda_margin = (ebitda0 / rev0) if (ebitda0 and rev0) else None
    np_margin = (np0 / rev0) if (np0 and rev0 and np0 > 0) else None
    shares = meta.get("shares_outstanding")
    unit_mult = _unit_factor(meta)          # 1 единица карточки = сколько млн ₽
    payout = _payout(_load(ticker, "governance.json"))
    forecast, weights = {}, {}
    for name, sc in scenarios.items():
        if name not in ("base", "bull", "bear"):
            continue
        growth = _scenario_growth(sc)
        rev, ebd, npr, eps, dps = {}, {}, {}, {}, {}
        cur = rev0
        for y in horizon:
            g = growth.get(y)
            if g is None:
                continue
            cur = cur * (1 + g / 100.0)
            rev[y] = round(cur, 1)
            if ebitda_margin is not None:
                ebd[y] = round(cur * ebitda_margin, 1)
            if np_margin is not None:
                npr[y] = round(cur * np_margin, 1)
                if shares:
                    e = cur * np_margin / unit_mult * 1e6 / float(shares)
                    eps[y] = round(e, 2)
                    if payout is not None:
                        dps[y] = round(e * payout, 2)
        if not rev:
            continue
        block = {"assumptions_text": (
            f"Темпы роста выручки — сценарий «{name}» из market.json (аналитик карточки), "
            f"середина диапазона по каждому году. Маржа EBITDA и чистая — уровня базового "
            f"{base_year} года, удержаны постоянными: сборщик их не прогнозирует."),
            "revenue": rev}
        if ebd:
            block["ebitda"] = ebd
        if npr:
            block["net_profit"] = npr
        if eps:
            block["eps_rub"] = eps
        if dps:
            block["dps_rub"] = dps
        forecast[name] = block
        p = sc.get("probability_pct")
        if isinstance(p, (int, float)):
            weights[name] = round(float(p) / 100.0, 3)
    if not all(k in forecast for k in ("base", "bull", "bear")):
        return None, ["не по всем сценариям удалось построить прогноз"]
    if abs(sum(weights.values()) - 1.0) > 0.05:
        weights = {"base": 0.5, "bull": 0.2, "bear": 0.3}
        flags.append("вероятности сценариев в market.json не дают 100% — веса по умолчанию")
    weights["basis"] = "Вероятности сценариев — из market.json (суждение аналитика карточки)."

    if np_margin is None:
        flags.append("чистая маржа базового года не положительна — прогноз прибыли не строился")
    if not _has_adjusted(fin):
        flags.append("прибыль базового года НЕ нормализована: разовые статьи не исключены — "
                     "сборщик не умеет отличать разовое, нужен аналитик")

    model = {
        "meta": {
            "ticker": ticker, "model_version": MODEL_VERSION, "built_by": "assembler",
            "built_at": date.today().isoformat(), "base_period": str(base_year),
            # У Диасофта периоды сценариев записаны не голым годом («2026-2027»), и
            # горизонт получался пустым — движок брал horizon_years[0] и падал бы на
            # индексе. Оставляем исходные подписи периодов, если год не выделяется.
            "horizon_years": [int(y) for y in horizon if str(y).isdigit()] or list(horizon),
            "sector_template": meta.get("sector"),
            "analyst_notes": (
                "Структура собрана из уже существующих слоёв карточки: эластичности — из "
                "стресс-коэффициентов macro.json, сценарные темпы и вероятности — из "
                "market.json, дивиденд — из дивполитики governance.json. Новых суждений "
                "сборщик не вносит. Мост прибыли и нормализация прибыли требуют аналитика "
                "и здесь НЕ строятся."),
            "unit_check": unit_note,
        },
        "drivers": drivers,
        "forecast": forecast,
        "scenario_weights": weights,
        "bridge": None,
        "sensitivity": _sensitivity(coefs, rev0, np0, q_to_card),
        "track_record": [],
        "data_flags": flags,
    }
    if passthrough:
        model["passthrough"] = passthrough
    val, vflags = _valuation(fin, model, shares, unit_mult)
    model["valuation"] = val
    model["data_flags"] += vflags
    ok, why = _invariants(model)
    if not ok:
        return None, [f"инвариант не выполнен: {why}"]
    return model, []


def _payout(gov: dict) -> float | None:
    """Доля прибыли на дивиденды из дивполитики. None — политики нет/не платит."""
    blob = json.dumps(gov, ensure_ascii=False).lower()
    if "не выплач" in blob or "дивиденды не" in blob:
        return 0.0
    import re
    m = re.search(r"(\d{2,3})\s*%\s*(?:от\s*)?(?:чистой\s*приб|прибыли|fcf|ЧП)", blob)
    if m:
        v = int(m.group(1))
        if 5 <= v <= 100:
            return v / 100.0
    return None


def _has_adjusted(fin: dict) -> bool:
    ins = fin.get("income_statement") or {}
    adj = ins.get("net_profit_adj") or ins.get("adjusted_net_profit")
    return isinstance(adj, list) and any(isinstance(x, (int, float)) for x in adj)


def _sensitivity(coefs: dict, rev0: float, np0: float | None, q_to_card: float) -> list:
    out = []
    label = {"fx": "Курс USD/RUB", "rate": "Ключевая ставка", "commodity": "Цена сырья"}
    for key, c in coefs.items():
        if key not in label:
            continue
        d_np = c.get("net_profit")
        if not isinstance(d_np, (int, float)) or not d_np or not np0 or np0 <= 0:
            continue
        out.append({
            "driver": key, "shift": c.get("per"),
            "net_profit_pct": f"{float(d_np) * q_to_card / np0 * 100:+.1f}%",
            "basis": "стресс-коэффициент карточки, пересчитан в % от прибыли базового года",
        })
    return out


def _valuation(fin: dict, model: dict, shares, unit_mult: float) -> tuple[dict | None, list[str]]:
    """Оценка модели — ТОЛЬКО как кросс-чек к цене карточки, никогда как вторая цена.

    🔴 Измерено теневым прогоном по 203 компаниям: механический форвардный P/E
    (маржа базового года × исторический мультипликатор) попадает в оценку карточки
    ±15% лишь у 33. Это не повод «подкрутить» — это ответ: у авто-модели НЕТ права
    на собственный вердикт цены. Карточка считает справедливую цену секторными
    методами (DCF, peer, NAV, P/BV×ROE), которые кодом не воспроизводятся.

    Поэтому блок всегда говорит одно: вердикт — цена карточки. Своё число модель
    показывает лишь когда оно СОШЛОСЬ с карточкой, и подписано как сверка. Разошлось —
    сверки нет и тикер идёт в очередь аналитику. Так на карточке не появляется второго
    числа справедливой цены (главная поломка платформы — расхождения на стыках)."""
    card = ((fin.get("valuation") or {}).get("fair_value_range") or {})
    card_base = card.get("base")
    block = {
        "verdict_source": "карточка",
        "verdict_note": ("Справедливую цену на карточке считает слой оценки (секторные методы). "
                         "Прогнозная модель её НЕ заменяет: она показывает, что будет с выручкой "
                         "и прибылью при разных ставке, курсе и цене сырья."),
        "card_fair_price_rub": card_base if isinstance(card_base, (int, float)) else None,
        "cross_check": None,
    }
    mult = (fin.get("multiples") or {}).get("historical_avg") or {}
    pe = next((mult[k] for k in ("pe_adj_5y_median", "pe_5y_median", "pe_5y_avg",
                                 "pe_adj_value", "pe_value") if isinstance(mult.get(k), (int, float))), None)
    if not isinstance(pe, (int, float)) or pe <= 0 or not shares or not isinstance(card_base, (int, float)) or card_base <= 0:
        block["cross_check_note"] = "сверка не считалась: нет исторического P/E или цены карточки"
        return block, []
    horizon0 = str((model["meta"]["horizon_years"] or [None])[0])
    per_scen = {}
    for name, b in model["forecast"].items():
        eps = (b.get("eps_rub") or {}).get(horizon0)
        if isinstance(eps, (int, float)):
            per_scen[name] = round(eps * float(pe), 1)
    if "base" not in per_scen:
        block["cross_check_note"] = "сверка не считалась: нет прогнозной прибыли на акцию"
        return block, []
    w = {k: v for k, v in model["scenario_weights"].items() if isinstance(v, (int, float))}
    denom = sum(w.get(k, 0) for k in per_scen if k in w) or 1e-9
    weighted = round(sum(per_scen[k] * w.get(k, 0) for k in per_scen if k in w) / denom, 1)
    diff = (weighted / float(card_base) - 1) * 100
    if abs(diff) > FAIR_TOLERANCE_PCT:
        block["cross_check_note"] = (
            f"сверка НЕ сошлась: форвардный P/E модели даёт {weighted:,.0f} ₽ против "
            f"{card_base:,.0f} ₽ у карточки ({diff:+.0f}%). Своё число модель не показывает — "
            f"тикер в очередь аналитику.")
        return block, ["оценка модели разошлась с карточкой — сверка не публикуется"]
    block["cross_check"] = {
        "method": "forward_pe",
        "target_multiple": {"value": pe, "basis": (
            "исторический P/E карточки (multiples.historical_avg" +
            (f", {mult.get('pe_basis')}" if mult.get("pe_basis") else "") + ")")},
        "per_scenario_rub": per_scen,
        "weighted_rub": weighted,
        "divergence_from_card_pct": round(diff, 1),
        "note": ("Независимая сверка: прогнозная прибыль модели × исторический мультипликатор. "
                 "Совпала с оценкой карточки в пределах допуска — это подтверждение, "
                 "а не второе мнение."),
    }
    return block, []


def _invariants(model: dict) -> tuple[bool, str]:
    """Модель, провалившая любой инвариант, НЕ пишется — не «пишется с флагом»."""
    fc = model["forecast"]
    h = str((model["meta"]["horizon_years"] or [None])[0])
    rev = {k: (fc[k].get("revenue") or {}).get(h) for k in ("bear", "base", "bull")}
    if all(isinstance(v, (int, float)) for v in rev.values()):
        if not (rev["bear"] <= rev["base"] <= rev["bull"]):
            return False, f"выручка не упорядочена bear≤base≤bull: {rev}"
    cc = ((model.get("valuation") or {}).get("cross_check") or {}).get("per_scenario_rub") or {}
    if all(k in cc for k in ("bear", "base", "bull")):
        order = [cc[k] for k in ("bear", "base", "bull")]
        if not (order[0] <= order[1] <= order[2]):
            return False, f"сверочная цена не упорядочена: {order}"
    for name, block in fc.items():
        eps = block.get("eps_rub") or {}
        dps = block.get("dps_rub") or {}
        for y, d in dps.items():
            e = eps.get(y)
            if isinstance(e, (int, float)) and isinstance(d, (int, float)) and e > 0 and d > e * 1.05:
                return False, f"дивиденд больше прибыли на акцию ({name} {y}: {d} > {e})"
    return True, ""


def main():
    apply = "--apply" in sys.argv
    shadow = "--shadow" in sys.argv
    only = None
    if "--ticker" in sys.argv:
        only = sys.argv[sys.argv.index("--ticker") + 1].upper()
    have = sorted(p.parent.name for p in COMPANIES.glob("*/financials.json"))
    if only:
        have = [only]
    built = rejected = 0
    skipped_handmade: list[str] = []
    reasons: dict[str, int] = {}
    no_valuation = []
    for t in have:
        model, why = build(t)
        if model is None:
            rejected += 1
            key = why[0].split("(")[0].strip() if why else "?"
            reasons[key] = reasons.get(key, 0) + 1
            if only or shadow:
                print(f"  ✕ {t}: {'; '.join(why)}")
            continue
        built += 1
        if "valuation" not in model:
            no_valuation.append(t)
        if shadow:
            _shadow_diff(t, model)
        # 🔴 НИКОГДА не затирать авторскую модель. При первом же прогоне сборщик снёс
        # ручные модели ЛУКОЙЛа и X5 — восстановлены из git. Авторская модель дороже
        # авто по определению: в ней нормализованная прибыль, режимная логика драйверов
        # и мост прибыли, которых сборщик не умеет.
        out = COMPANIES / t / "financial_model.json"
        if out.exists():
            try:
                cur = json.loads(out.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cur = {}
            if (cur.get("meta") or {}).get("built_by") not in (None, "assembler") or \
               ((cur.get("meta") or {}).get("model_version") or "").startswith("v1") and \
               (cur.get("meta") or {}).get("built_by") is None:
                skipped_handmade.append(t)
                continue
        if apply:
            out.write_text(json.dumps(model, ensure_ascii=False, indent=2))
    if skipped_handmade:
        print(f"не тронуты авторские модели: {', '.join(skipped_handmade)}")
    print(f"\nсобрано: {built}, отклонено: {rejected}"
          f"{'' if apply else '  (сухой прогон)'}")
    print(f"из собранных без блока оценки (расхождение с карточкой): {len(no_valuation)}")
    if no_valuation[:15]:
        print("   ", ", ".join(no_valuation[:15]), "…" if len(no_valuation) > 15 else "")
    for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"   отклонено — {k}: {v}")


def _shadow_diff(ticker: str, auto: dict):
    """Сверка авто-сборки с авторской моделью — единственный способ ИЗМЕРИТЬ,
    что теряется без аналитика."""
    p = COMPANIES / ticker / "financial_model.json"
    if not p.exists():
        return
    hand = json.loads(p.read_text(encoding="utf-8"))
    if (hand.get("meta") or {}).get("built_by") == "assembler":
        return
    print(f"\n=== СВЕРКА {ticker}: авто против авторской")
    hd = {d["key"]: d for d in hand.get("drivers", [])}
    for d in auto.get("drivers", []):
        h = hd.get(d["key"])
        a_e = (d.get("elasticity") or {}).get("pct_per_pct")
        h_e = (h or {}).get("elasticity", {}).get("pct_per_pct")
        print(f"   драйвер {d['key']:14} авто {a_e} | автор {h_e}")
    print(f"   passthrough  авто {auto.get('passthrough', {}).get('ebitda')}/"
          f"{auto.get('passthrough', {}).get('net_profit')} | "
          f"автор {hand.get('passthrough', {}).get('ebitda')}/{hand.get('passthrough', {}).get('net_profit')}")
    print(f"   веса         авто {[(k, v) for k, v in auto['scenario_weights'].items() if isinstance(v, float)]} | "
          f"автор {[(k, v) for k, v in hand.get('scenario_weights', {}).items() if isinstance(v, float)]}")
    av = (auto.get("valuation") or {}).get("weighted_fair_price_rub")
    hv = (hand.get("valuation") or {}).get("weighted_fair_price_rub")
    print(f"   справедливая авто {av} | автор {hv}")


if __name__ == "__main__":
    main()
