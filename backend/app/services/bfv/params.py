"""Компилятор входов движка BFV-D из данных карточки компании.

Детерминированно выводит Params + список Scenario (§18 минимальное ядро) из уже
существующих блоков карточки — financials.json / governance.json / institutions.json —
по ЯВНЫМ маппингам методики (docs/basis_fair_price.md):
  - §5:   bv0/roe0/roe_terminal/payout0 — из отчётности; phi — секторный пресет §5.2;
  - §6.2: willingness/payment_fraction — из governance-балла (сетка §6.2);
  - §7:   h_expropriation — из institutions (S1 «защита прав собственности»);
  - §9:   банковский режим — из bank_metrics.capital_adequacy;
  - §10:  вероятности сценариев — общерыночные из geo_barometer (S1..S4 → 3 состояния
          + катастрофический хвост), per-company меняются только overrides потоков.

Это НЕ суждение аналитика: компилятор даёт воспроизводимую базовую линию по формулам.
Настоящие суждения (roe_terminal-тонкая настройка, точечные сценарные отклонения)
кладутся в ручной слой overrides отдельным ключом и здесь не перетираются — см.
compile_params(overrides=...). Тестовая версия v1: без калибровки на росс. данных
(методика §22 — КТ-2 блокер №1), числа помечаются статусом expert на витрине.
"""
from __future__ import annotations

from statistics import median
from typing import Any

from app.services.bfv.engine import Params, ParamsF, Scenario, select_engine


# ---- утилиты чтения рядов ---------------------------------------------------
def _last_valid(series: Any) -> float | None:
    if isinstance(series, (int, float)):
        return float(series)
    if not isinstance(series, list):
        return None
    for x in reversed(series):
        if isinstance(x, (int, float)):
            return float(x)
    return None


def _recent_median(series: Any, n: int = 4) -> float | None:
    """Медиана последних n НЕнулевых значений — нормализованный уровень (§5.2:
    для цикличных берётся не пиковый ROE, а нормализованный)."""
    if isinstance(series, (int, float)):
        return float(series)
    if not isinstance(series, list):
        return None
    vals = [float(x) for x in series if isinstance(x, (int, float))]
    if not vals:
        return None
    return float(median(vals[-n:]))


# ---- ROE: единый резолвер из «бардака» полей -------------------------------
# ROE хранится в РАЗНЫХ местах и под РАЗНЫМИ ключами (разные агенты собирали
# по-разному) И в РАЗНЫХ единицах (проценты у одних, доли у других) — на бою это
# давало «нет ROE» у Т-Технологий (лежит в bank_metrics.roe_rep_pct) и ROE 0.2% у
# Яндекса (returns.roe в долях). Читаем как карточка (FinanceTab.bmA), собирая все
# алиасы, и ПРЕДПОЧИТАЕМ нормализованный ROE (§5.2 — нормализованный, не пиковый;
# владелец: «относительно норм. прибыли»). Единицы приводим к доле по величине.
_ROE_NORMALIZED_KEYS = [  # (контейнер, ключ) — нормализованный/устойчивый ROE, приоритет
    ("metrics_timeseries", "roe_adj"), ("bank_metrics", "roe_adj_pct"),
    ("bank_metrics", "roe_adjusted"), ("bank_metrics", "roe_adj"),
    ("returns", "roe_adjusted"), ("returns", "roe_adj"),
]
_ROE_REPORTED_KEYS = [  # отчётный ROE, если нормализованного нет
    ("metrics_timeseries", "roe"), ("returns", "roe"),
    ("bank_metrics", "roe_rep_pct"), ("bank_metrics", "roe_reported_pct"),
    ("bank_metrics", "roe_pct"), ("bank_metrics", "roe_reported"), ("bank_metrics", "roe"),
]


def _roe_to_fraction(v):
    """Единицы ROE к доле: |v|<1.5 ⇒ уже доля (0.25); иначе проценты (25.0/100).
    Порог 1.5 надёжно разделяет (ROE-доля >150% и ROE-процент <1.5% не встречаются)."""
    return None if v is None else (v if abs(v) < 1.5 else v / 100.0)


def _resolve_roe(fin: dict) -> tuple[float | None, str | None]:
    """Нормализованная медиана ROE (доля) + метка источника. Сначала все
    нормализованные ключи, затем отчётные; медиана последних 5, приведённая к доле."""
    for container, key in _ROE_NORMALIZED_KEYS + _ROE_REPORTED_KEYS:
        series = (fin.get(container, {}) or {}).get(key)
        m = _recent_median(series, n=5)
        if m is not None:
            frac = _roe_to_fraction(m)
            if frac is not None and frac > 0:  # отрицательную медиану ROE не берём как база
                return frac, f"{container}.{key}"
    return None, None


# ---- секторные пресеты (§5.2 полураспад спреда) -----------------------------
# φ = 0.5**(1/полураспад). Ключ — по подстроке в meta.sector/profile (RU/EN).
_SECTOR_PHI = [
    # (маркеры сектора, полураспад лет) — сильный ров/регулирование → медленное затухание
    (("банк", "bank", "финанс", "financ"), 6.0),
    (("телеком", "telecom", "связь"), 6.5),
    (("электроэнерг", "utilit", "сеть", "генерац", "grid"), 7.0),
    (("транспорт", "инфраструктур", "logistic", "порт", "railway", "жд"), 6.0),
    (("потреб", "ритейл", "retail", "consumer", "food", "продукт"), 4.5),
    (("технолог", "it", "софт", "internet", "интернет", "tech"), 4.0),
    (("нефт", "газ", "oil", "gas", "энерг"), 2.5),  # сырьё/цикл — быстрое затухание
    (("метал", "metal", "mining", "горн", "уголь", "сталь", "steel", "золот", "gold"), 2.5),
    (("хим", "chem", "удобр", "fertiliz"), 3.0),
    (("девелоп", "недвиж", "estate", "строит", "construct"), 3.0),
]
_DEFAULT_HALFLIFE = 4.5  # нормальная конкуренция (§5.2)


def _phi_for_sector(sector: str, profile: str) -> float:
    blob = f"{sector or ''} {profile or ''}".lower()
    for markers, hl in _SECTOR_PHI:
        if any(m in blob for m in markers):
            return round(0.5 ** (1.0 / hl), 4)
    return round(0.5 ** (1.0 / _DEFAULT_HALFLIFE), 4)


def _is_cyclical(sector: str, profile: str) -> bool:
    blob = f"{sector or ''} {profile or ''}".lower()
    cyc = ("нефт", "газ", "oil", "gas", "метал", "metal", "mining", "горн", "уголь",
           "сталь", "steel", "золот", "gold", "хим", "chem", "удобр")
    return any(m in blob for m in cyc)


# ---- §6.2 governance-балл → willingness / payment_fraction ------------------
# Сетки методики (§6.2), интерполяция по непрерывному баллу 1..5.
def _interp_grid(score: float, grid: dict[int, float]) -> float:
    s = max(1.0, min(5.0, score))
    lo = int(s)
    hi = min(5, lo + 1)
    if lo == hi:
        return grid[lo]
    return grid[lo] + (grid[hi] - grid[lo]) * (s - lo)


# §6.2 даёт для балла 1 диапазон 0.70-0.80; берём нижний край и круче спускаем ниже
# балла 2 — на бою deep-value микрокапы со слабым управлением (балл 1.7) давали
# неправдоподобный апсайд (ловушки стоимости), а willingness — единственный канал,
# которым движок это давит без полной КТ-2-калибровки (§22).
_WILLINGNESS_GRID = {5: 0.98, 4: 0.96, 3: 0.93, 2: 0.83, 1: 0.60}
_PAYFRAC_GRID = {5: 1.00, 4: 0.97, 3: 0.94, 2: 0.87, 1: 0.72}


# ---- §7 institutions S1 (защита собственности) → интенсивность экспроприации -
_EXPROP_BY_S1 = {5: 0.001, 4: 0.002, 3: 0.004, 2: 0.010, 1: 0.020}


def _s1_property_protection(inst: dict) -> int | None:
    subs = (inst or {}).get("iri_scoring", {}).get("subindices", [])
    for x in subs:
        if x.get("key") == "S1" and isinstance(x.get("score"), (int, float)):
            return int(round(x["score"]))
    return None


def _governance_score(gov: dict) -> float | None:
    sc = (gov or {}).get("scoring", {})
    v = sc.get("overall_score") or sc.get("total_score") or sc.get("final_score")
    return float(v) if isinstance(v, (int, float)) else None


def _payout0(fin: dict, gov: dict) -> float:
    """Стартовый payout (доля): медиана недавних фактических выплат; иначе политика."""
    hist = (gov or {}).get("dividends", {}).get("history", [])
    pcts = [h.get("payout_pct") for h in hist if isinstance(h.get("payout_pct"), (int, float))
            and h.get("paid") is not False]
    if pcts:
        return max(0.0, min(1.0, median(pcts[-3:]) / 100.0))
    dp = _recent_median(fin.get("multiples", {}).get("dividend_payout_pct"), n=3)
    if dp is not None:
        return max(0.0, min(1.0, dp / 100.0))
    policy = (gov or {}).get("dividends", {}).get("policy_min_payout_pct")
    if isinstance(policy, (int, float)):
        return max(0.0, min(1.0, policy / 100.0))
    return 0.0


# ---- геобарометр → вероятности состояний (§10) ------------------------------
_CATASTROPHIC_TAIL = 0.05  # платформенный параметр §20 (expert): в барометре хвоста нет


def scenario_probabilities(barometer: dict) -> dict[str, float]:
    """S1..S4 барометра (18m-горизонт) → 3 состояния + катастрофический хвост.
    S1+S2 → деэскалация, S3 → статус-кво, S4 → эскалация; хвост выщипывается
    платформенным параметром с ренормировкой (§10.1: геополит. режим — общий блок)."""
    probs = (barometer or {}).get("scenario", {}).get("probabilities_18m", {})
    s1 = float(probs.get("S1_breakthrough", 0.10))
    s2 = float(probs.get("S2_ceasefire", 0.25))
    s3 = float(probs.get("S3_attrition", 0.47))
    s4 = float(probs.get("S4_escalation", 0.18))
    total = s1 + s2 + s3 + s4
    if total <= 0:
        s1, s2, s3, s4, total = 0.10, 0.25, 0.47, 0.18, 1.0
    scale = (1.0 - _CATASTROPHIC_TAIL) / total
    return {
        "деэскалация": (s1 + s2) * scale,
        "статус-кво": s3 * scale,
        "эскалация": s4 * scale,
        "катастрофический хвост": _CATASTROPHIC_TAIL,
    }


# ---- главный компилятор -----------------------------------------------------
def compile_params(fin: dict, gov: dict, inst: dict, barometer: dict,
                   shares_outstanding: float | None,
                   overrides: dict | None = None) -> dict:
    """Возвращает {params, scenarios, base_meta, warnings}. overrides — ручной слой
    суждений аналитика, накладывается поверх выведенных значений (не перетирается
    при повторной компиляции). None-выходы означают «нельзя посчитать» (нет BVPS)."""
    warn: list[str] = []
    meta = fin.get("meta", {})
    sector = meta.get("sector", "")
    profile = meta.get("profile", "")
    is_bank = bool(fin.get("bank_pnl") or fin.get("bank_metrics"))

    # --- bv0 (BVPS) — единично-безопасно ---
    # 1) явный book_value_per_share (уже ₽/акция), иначе
    # 2) обратный счёт из P/B: BVPS = last_price / P/B — оба из ОДНОГО снапшота
    #    отчётности, P/B безразмерен → ловушка масштаба shares_outstanding (у разных
    #    компаний meta.shares то в млн, то в штуках — найдено на бою) обходится.
    # total_equity/shares НЕ используется как источник: масштаб shares ненадёжен.
    bvps_series = fin.get("balance_sheet", {}).get("book_value_per_share")
    bv0 = _last_valid(bvps_series)
    if bv0 is None or bv0 <= 0:
        pb = (fin.get("multiples", {}).get("current", {}) or {}).get("pb")
        last_price = meta.get("last_price")
        if isinstance(pb, (int, float)) and pb > 0 and isinstance(last_price, (int, float)) and last_price > 0:
            bv0 = last_price / pb
    if bv0 is None or bv0 <= 0:
        return {"params": None, "scenarios": None, "base_meta": None,
                "warnings": ["нет BVPS (ни book_value_per_share, ни цена/P/B) — BFV не считается "
                             "(частая причина — отрицательный капитал)"]}

    # --- roe0 (нормализованный) ---
    roe0, roe_src = _resolve_roe(fin)
    if roe0 is None:
        g = fin.get("forecast", {}).get("roe_2026_guidance_pct")  # имя _pct ⇒ всегда проценты
        if isinstance(g, (int, float)):
            roe0, roe_src = g / 100.0, "forecast.roe_2026_guidance_pct"
    if roe0 is None:
        return {"params": None, "scenarios": None, "base_meta": None,
                "warnings": ["нет данных по ROE — BFV не считается"]}
    # Потолок ROE 45% ОТМЕНЁН (поправка v1.1 §4): он срезал прибыль высоко-ROE компаний
    # и делал оценку бессмысленной. Вместо усечения — МАРШРУТИЗАЦИЯ: компания с ROE≥45%
    # сюда (BFV-D) вообще не попадает — select_engine уводит её в BFV-F, где уровень ROE
    # не используется. Нормализованный старт даёт _resolve_roe (медиана истории, §5.2).
    g_terminal = 0.035
    # §5.1 канон g = b·ROE ⇒ должно быть g_terminal ≤ ROE_terminal ≤ ROE0. Если ROE0
    # ниже/у терминального роста — устойчивого состояния нет (payout вышел бы < 0),
    # дивидендно-ростовая модель ВЫРОЖДЕНА: раньше это давало отрицательные потоки
    # у ~42 низко-/убыточных компаний. Честно помечаем неприменимость (как отр. капитал),
    # а не выдаём мусорное число.
    if roe0 <= g_terminal + 0.01:
        return {"params": None, "scenarios": None, "base_meta": None,
                "warnings": [f"ROE {roe0:.1%} ниже терминального роста {g_terminal:.1%} — "
                             "дивидендно-ростовая модель BFV неприменима "
                             "(низкая/нестабильная прибыльность)"]}

    # --- терминальный ROE (§5.2: ≤ roe0, ≥ g_terminal, И потолок сектора) ---
    # Абсолютный потолок 20% — прокси к «≤ 1.5× медианы сектора» (§5.2): устойчивый
    # терминальный ROE выше ~20% в РФ неправдоподобен. Без него у высоко-ROE
    # (золото/IT на пике) терминальная стоимость взрывалась (на бою: PLZL +1094%,
    # ASTR +945% апсайда) — терминальный ROE намного выше порога ⇒ бесконечный ров.
    fade = 0.78 if _is_cyclical(sector, profile) else 0.87
    roe_terminal = max(g_terminal + 0.005, min(roe0, roe0 * fade, 0.20))

    # --- payout0, phi ---
    payout0 = _payout0(fin, gov)
    phi = _phi_for_sector(sector, profile)

    # --- §6.2 willingness / payment_fraction из governance-балла ---
    gscore = _governance_score(gov)
    if gscore is None:
        gscore = 3.0
        warn.append("нет governance-балла — willingness по умолчанию (3.0)")
    willingness = round(_interp_grid(gscore, _WILLINGNESS_GRID), 3)
    payment_fraction = round(_interp_grid(gscore, _PAYFRAC_GRID), 3)

    # --- §7 хазард экспроприации из institutions S1 ---
    s1 = _s1_property_protection(inst)
    if s1 is None:
        h_exprop = 0.004
        warn.append("нет institutions S1 — хазард экспроприации по умолчанию")
    else:
        h_exprop = _EXPROP_BY_S1.get(s1, 0.004)
    # хазард дистресса — по долговой нагрузке (грубо), иначе базовый
    h_distress = 0.002
    nd_ebitda = _last_valid((fin.get("balance_sheet", {}).get("ratios", {}) or {}).get("net_debt_ebitda"))
    if isinstance(nd_ebitda, (int, float)) and nd_ebitda > 3.0:
        h_distress = min(0.02, 0.002 * (1 + (nd_ebitda - 3.0)))

    # --- банковские входы (§9) ---
    cet1_ratio0, cet1_target, rwa_growth = 0.13, 0.11, 0.10
    if is_bank:
        ca = _last_valid((fin.get("bank_metrics", {}) or {}).get("capital_adequacy"))
        if isinstance(ca, (int, float)) and ca > 0:
            cet1_ratio0 = ca / 100.0
        else:
            warn.append("банк без capital_adequacy — CET1 по умолчанию 13%")

    base = Params(
        bv0=bv0, roe0=roe0, roe_terminal=roe_terminal, phi=phi,
        payout0=payout0, payout_ramp=12, g_terminal=g_terminal,
        p_willingness=willingness, payment_fraction=payment_fraction,
        h_distress=h_distress, h_expropriation=h_exprop,
        is_bank=is_bank, cet1_ratio0=cet1_ratio0, cet1_target=cet1_target,
        rwa_growth=rwa_growth,
    )

    # ручной слой суждений (§20 overrides) поверх выведенного
    if overrides:
        base_field_ov = {k: v for k, v in overrides.items() if k in Params.__dataclass_fields__}
        if base_field_ov:
            from dataclasses import replace as _replace
            base = _replace(base, **base_field_ov)

    # --- сценарии: общие вероятности + per-company overrides потоков (§10.2) ---
    probs = scenario_probabilities(barometer)
    # сдвиги по состояниям: эскалация давит willingness/хазарды/терминальный ROE
    scenarios = [
        Scenario("деэскалация", probs["деэскалация"], dict(
            roe_terminal=min(roe0, roe_terminal * 1.05),
            p_willingness=min(0.99, willingness + 0.02),
            h_distress=h_distress * 0.6, h_expropriation=h_exprop * 0.5)),
        Scenario("статус-кво", probs["статус-кво"], dict(
            roe_terminal=roe_terminal, p_willingness=willingness,
            h_distress=h_distress, h_expropriation=h_exprop)),
        Scenario("эскалация", probs["эскалация"], dict(
            roe_terminal=max(g_terminal + 0.005, roe_terminal * 0.85),
            p_willingness=max(0.70, willingness - 0.06),
            payment_fraction=max(0.80, payment_fraction - 0.05),
            h_distress=min(0.03, h_distress * 2.0),
            h_expropriation=min(0.04, h_exprop * 2.5),
            s_benign=0.40)),
        Scenario("катастрофический хвост", probs["катастрофический хвост"], {},
                 catastrophic=True, cat_recovery=round(0.05 * bv0, 4)),
    ]
    # сценарные overrides из ручного слоя (напр. точечная вероятность/willingness)
    if overrides and isinstance(overrides.get("scenarios"), list):
        for man in overrides["scenarios"]:
            for sc_i, sc in enumerate(scenarios):
                if sc.name == man.get("name"):
                    from dataclasses import replace as _replace
                    merged_ov = {**sc.overrides, **(man.get("overrides") or {})}
                    scenarios[sc_i] = _replace(sc, overrides=merged_ov,
                                               prob=man.get("prob", sc.prob))

    base_meta = {
        "bv0": round(bv0, 4), "roe0": round(roe0, 4), "roe_src": roe_src,
        "roe_terminal": round(roe_terminal, 4),
        "phi": phi, "payout0": round(payout0, 4), "willingness": willingness,
        "payment_fraction": payment_fraction, "h_expropriation": h_exprop,
        "h_distress": round(h_distress, 4), "is_bank": is_bank,
        "governance_score": round(gscore, 2), "s1_property_protection": s1,
        "sector": sector, "probabilities": {k: round(v, 4) for k, v in probs.items()},
    }
    return {"params": base, "scenarios": scenarios, "base_meta": base_meta, "warnings": warn}


# =====================================================================
# BFV-F: компилятор от денежного потока (поправка v1.1 §3) — для
# растущих/asset-light, куда роутер уводит из BFV-D.
# =====================================================================

# sales_to_capital по архетипу (market.json valuation_inputs.archetype) / сектору:
# ₽ прироста выручки на ₽ нового капитала. Asset-light высоко, тяжёлая промышленность низко.
_S2C_BY_ARCHETYPE = {
    "tech_growth": 7.0, "platform": 7.0, "software": 8.0, "internet": 7.0,
    "consumer_growth": 4.0, "retail": 3.0, "telecom": 1.5, "healthcare": 4.0,
    "financials": 5.0, "industrial": 1.5, "materials": 1.0, "energy": 1.0,
    "oil_gas": 1.0, "utilities": 1.0, "real_estate": 1.2, "transport": 1.5,
}
_S2C_BY_SECTOR = [
    (("нефт", "газ", "oil", "gas", "метал", "metal", "mining", "горн", "уголь", "сталь", "хим"), 1.0),
    (("электроэнерг", "utilit", "сеть", "генерац", "транспорт", "инфраструктур", "девелоп", "недвиж"), 1.4),
    (("телеком", "telecom", "связь"), 1.5),
    (("потреб", "ритейл", "retail", "consumer", "food", "продукт"), 3.0),
    (("технолог", "it", "софт", "internet", "интернет", "tech", "финанс", "financ"), 6.0),
]


def _sales_to_capital(archetype: str, sector: str, profile: str) -> float:
    if archetype and archetype.lower() in _S2C_BY_ARCHETYPE:
        return _S2C_BY_ARCHETYPE[archetype.lower()]
    blob = f"{sector or ''} {profile or ''}".lower()
    for markers, v in _S2C_BY_SECTOR:
        if any(m in blob for m in markers):
            return v
    return 3.0


def _revenue_per_share(fin: dict) -> float | None:
    """Выручка на акцию, единично-безопасно: last_price / P/S (P/S безразмерен — та же
    защита от разного масштаба shares_outstanding, что BVPS через P/B). Фолбэк —
    revenue_total(млн)·1e6 / shares, но масштаб shares ненадёжен, поэтому вторично."""
    ps = (fin.get("multiples", {}).get("current", {}) or {}).get("ps")
    last_price = fin.get("meta", {}).get("last_price")
    if isinstance(ps, (int, float)) and ps > 0 and isinstance(last_price, (int, float)) and last_price > 0:
        return last_price / ps
    return None


def _net_margin(fin: dict) -> float | None:
    """Медиана недавней чистой маржи (net_profit/revenue) — нормализованный уровень."""
    is_ = fin.get("income_statement", {}) or {}
    rev = is_.get("revenue")
    ni = is_.get("net_profit") or is_.get("net_income")
    if not isinstance(rev, list) or not isinstance(ni, list):
        return None
    margins = [ni[i] / rev[i] for i in range(min(len(rev), len(ni)))
               if isinstance(rev[i], (int, float)) and rev[i] > 0 and isinstance(ni[i], (int, float))]
    if not margins:
        return None
    return float(median(margins[-4:]))


def _revenue_growth0(fin: dict) -> float | None:
    """Стартовый рост выручки: медиана недавних темпов (metrics_timeseries.revenue_growth,
    единицы нормализованы к доле), иначе CAGR по ряду выручки. Кап [0; 0.5]."""
    g = _recent_median((fin.get("metrics_timeseries", {}) or {}).get("revenue_growth"), n=3)
    if g is not None:
        g = g if abs(g) < 1.5 else g / 100.0   # единицы: доля vs проценты
    if g is None:
        rev = (fin.get("income_statement", {}) or {}).get("revenue")
        if isinstance(rev, list):
            vals = [x for x in rev if isinstance(x, (int, float)) and x > 0]
            if len(vals) >= 2 and vals[0] > 0:
                g = (vals[-1] / vals[0]) ** (1.0 / (len(vals) - 1)) - 1.0
    if g is None:
        return None
    return max(0.0, min(0.50, g))


def _terminal_growth(fin: dict, market: dict) -> float:
    tg = (market.get("valuation_inputs", {}) or {}).get("terminal_growth")
    if isinstance(tg, dict):
        lo, hi = tg.get("nominal_low_pct"), tg.get("nominal_high_pct")
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return (lo + hi) / 2.0 / 100.0
    return 0.045


def compile_params_f(fin: dict, gov: dict, inst: dict, barometer: dict, market: dict,
                     shares_outstanding: float | None,
                     overrides: dict | None = None) -> dict:
    """Входы BFV-F из карточки. None-выход — нет выручки/маржи. Права/хазарды/сценарии —
    те же источники, что BFV-D (governance/institutions/geo_barometer)."""
    warn: list[str] = []
    meta = fin.get("meta", {})
    sector = meta.get("sector", "")
    profile = meta.get("profile", "")
    vi = market.get("valuation_inputs", {}) or {}
    archetype = vi.get("archetype", "")

    revenue0 = _revenue_per_share(fin)
    if revenue0 is None or revenue0 <= 0:
        return {"params": None, "scenarios": None, "base_meta": None, "engine": "BFV-F",
                "warnings": ["нет выручки/P·S для BFV-F"]}
    margin0 = _net_margin(fin)
    if margin0 is None:
        return {"params": None, "scenarios": None, "base_meta": None, "engine": "BFV-F",
                "warnings": ["нет чистой маржи для BFV-F"]}
    if margin0 <= 0:
        warn.append(f"чистая маржа ≤ 0 ({margin0:.1%}) — компания убыточна, поток отрицателен")
    g_rev0 = _revenue_growth0(fin)
    if g_rev0 is None:
        g_rev0 = 0.08
        warn.append("нет темпа роста выручки — по умолчанию 8%")
    g_terminal = _terminal_growth(fin, market)

    # маржа_терминал: направление из margin_trajectory (EBITDA from→to), масштаб к чистой
    margin_terminal = margin0
    mt = vi.get("margin_trajectory")
    if isinstance(mt, dict) and isinstance(mt.get("from_pct"), (int, float)) and isinstance(mt.get("to_pct"), (int, float)) and mt["from_pct"] > 0:
        ratio = mt["to_pct"] / mt["from_pct"]
        margin_terminal = max(margin0 * 0.7, min(margin0 * 1.6, margin0 * ratio))
    margin_terminal = max(0.02, margin_terminal)  # не даём уйти в ноль

    s2c = _sales_to_capital(archetype, sector, profile)

    # права и хазарды — те же источники, что BFV-D
    gscore = _governance_score(gov)
    if gscore is None:
        gscore = 3.0
        warn.append("нет governance-балла — willingness по умолчанию")
    willingness = round(_interp_grid(gscore, _WILLINGNESS_GRID), 3)
    payment_fraction = round(_interp_grid(gscore, _PAYFRAC_GRID), 3)
    s1 = _s1_property_protection(inst)
    h_exprop = _EXPROP_BY_S1.get(s1, 0.004) if s1 is not None else 0.004
    h_distress = 0.002

    base = ParamsF(
        revenue0=revenue0, g_revenue0=g_rev0, g_terminal=g_terminal, fade_years=10,
        margin0=max(0.0, margin0), margin_terminal=margin_terminal, sales_to_capital=s2c,
        p_willingness=willingness, payment_fraction=payment_fraction,
        h_distress=h_distress, h_expropriation=h_exprop,
        recovery_share_of_price=0.10,   # якорь возврата — доля цены (книга не якорь у asset-light)
    )
    if overrides:
        ov = {k: v for k, v in overrides.items() if k in ParamsF.__dataclass_fields__}
        if ov:
            from dataclasses import replace as _replace
            base = _replace(base, **ov)

    # сценарии: те же вероятности из барометра; overrides — на поля ParamsF
    probs = scenario_probabilities(barometer)
    scenarios = [
        Scenario("деэскалация", probs["деэскалация"], dict(
            g_revenue0=min(0.50, g_rev0 * 1.10), p_willingness=min(0.99, willingness + 0.02),
            h_distress=h_distress * 0.6, h_expropriation=h_exprop * 0.5)),
        Scenario("статус-кво", probs["статус-кво"], dict(
            g_revenue0=g_rev0, p_willingness=willingness,
            h_distress=h_distress, h_expropriation=h_exprop)),
        Scenario("эскалация", probs["эскалация"], dict(
            g_revenue0=max(0.0, g_rev0 * 0.75), margin_terminal=margin_terminal * 0.85,
            p_willingness=max(0.70, willingness - 0.06),
            payment_fraction=max(0.80, payment_fraction - 0.05),
            h_distress=min(0.03, h_distress * 2.0), h_expropriation=min(0.04, h_exprop * 2.5))),
        Scenario("катастрофический хвост", probs["катастрофический хвост"], {},
                 catastrophic=True, cat_recovery=round(0.05 * revenue0, 4)),
    ]

    base_meta = {
        "revenue0": round(revenue0, 2), "g_revenue0": round(g_rev0, 4),
        "g_terminal": round(g_terminal, 4), "margin0": round(margin0, 4),
        "margin_terminal": round(margin_terminal, 4), "sales_to_capital": s2c,
        "willingness": willingness, "payment_fraction": payment_fraction,
        "h_expropriation": h_exprop, "archetype": archetype, "sector": sector,
        "governance_score": round(gscore, 2),
        "probabilities": {k: round(v, 4) for k, v in probs.items()},
    }
    return {"params": base, "scenarios": scenarios, "base_meta": base_meta,
            "engine": "BFV-F", "warnings": warn}
