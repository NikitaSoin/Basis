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

from app.services.bfv.engine import Params, Scenario


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
    # ЛОВУШКА ЕДИНИЦ (на бою: Яндекс отсеян с ROE 0.2%): returns.roe у разных компаний
    # то в ПРОЦЕНТАХ (Сбер 22.76), то в ДОЛЯХ (Яндекс 0.206=20.6%) — один и тот же
    # ряд, разный масштаб. Нормируем по величине: |медиана|<1.5 ⇒ уже доля, иначе
    # проценты /100. (ROE-доля >150% и ROE-процент <1.5% — оба практически не
    # встречаются, порог 1.5 разделяет надёжно.) 30 компаний были ошибочно
    # «неприменимо» из-за этого.
    def _roe_frac(v):
        return None if v is None else (v if abs(v) < 1.5 else v / 100.0)
    roe0 = _roe_frac(_recent_median(fin.get("returns", {}).get("roe"), n=5))
    if roe0 is None:
        roe0 = _roe_frac(_last_valid((fin.get("bank_metrics", {}) or {}).get("roe")))
    if roe0 is None:
        g = fin.get("forecast", {}).get("roe_2026_guidance_pct")  # имя _pct ⇒ всегда проценты
        roe0 = (float(g) / 100.0) if isinstance(g, (int, float)) else None
    if roe0 is None:
        return {"params": None, "scenarios": None, "base_meta": None,
                "warnings": ["нет данных по ROE — BFV не считается"]}
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
        "bv0": round(bv0, 4), "roe0": round(roe0, 4), "roe_terminal": round(roe_terminal, 4),
        "phi": phi, "payout0": round(payout0, 4), "willingness": willingness,
        "payment_fraction": payment_fraction, "h_expropriation": h_exprop,
        "h_distress": round(h_distress, 4), "is_bank": is_bank,
        "governance_score": round(gscore, 2), "s1_property_protection": s1,
        "sector": sector, "probabilities": {k: round(v, 4) for k, v in probs.items()},
    }
    return {"params": base, "scenarios": scenarios, "base_meta": base_meta, "warnings": warn}
