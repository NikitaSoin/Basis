"""Методика «Доходность vs риск» (docs/bond_analys.md) — расчёт КОДОМ.

3 шага: (1) фактический G-spread → (2) требуемый спред = медиана группы из нашей
базы + надбавки + Risk Score → (3) вердикт-светофор + проверка ожидаемыми потерями
+ стоп-правила. Risk Score (1–5) — синтез доступных сигналов: агентский рейтинг
(якорь), долговая нагрузка эмитента из financials.json (блок A, для публичных),
рыночный сигнал (спред vs группа), стоп-флаги (дефолт, аномалия). Где данных нет —
честная деградация (помечается). Без «купить/продать».
"""
import json
from pathlib import Path

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# рейтинговая группа по букве (нац. шкала)
def rating_group(rating: str | None) -> str | None:
    if not rating:
        return None
    b = rating.rstrip("+-").upper()
    if b in ("AAA", "AA"):
        return "AAA-AA"
    if b == "A":
        return "A"
    if b == "BBB":
        return "BBB"
    if b == "BB":
        return "BB"
    if b == "B":
        return "B"
    return "CCC-"  # CCC/CC/C/RD/D

# годовая вероятность дефолта по группе (ориентиры из методики, верификация — на ОК)
PD_BY_GROUP = {"AAA-AA": 0.001, "A": 0.005, "BBB": 0.01, "BB": 0.03, "B": 0.07, "CCC-": 0.22}
LGD = 0.70  # консервативно для необеспеченных ВДО
# базовый Risk Score (1–5) по агентскому рейтингу
SCORE_BY_GROUP = {"AAA-AA": 1.4, "A": 2.2, "BBB": 3.0, "BB": 3.8, "B": 4.3, "CCC-": 4.8}
# Risk Score → подразумеваемая группа (для «оценки Basis»)
SCORE_TO_GROUP = [(1.8, "AAA-AA"), (2.6, "A"), (3.4, "BBB"), (3.8, "BB"), (4.2, "B"), (5.1, "CCC-")]
# порядок групп по росту риска (для выбора худшей и требуемого спреда)
GROUP_RANK = {"AAA-AA": 0, "A": 1, "BBB": 2, "BB": 3, "BB-B": 3, "B": 4, "CCC-": 5}


def worse_group(g1: str | None, g2: str | None) -> str | None:
    cands = [g for g in (g1, g2) if g]
    if not cands:
        return None
    return max(cands, key=lambda g: GROUP_RANK.get(g, 3))


def score_to_group(score: float) -> str:
    for hi, g in SCORE_TO_GROUP:
        if score < hi:
            return g
    return "CCC-"


def _last(seq):
    if not isinstance(seq, list):
        return None
    for v in reversed(seq):
        if v is not None:
            return v
    return None


def issuer_debt_adjustment(ticker: str | None) -> tuple[float, str | None]:
    """Поправка к Risk Score из financials.json эмитента (блок A). (Δscore, факт)."""
    if not ticker:
        return 0.0, None
    p = COMPANIES_DIR / ticker / "financials.json"
    if not p.exists():
        return 0.0, None
    try:
        fin = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0.0, None
    ratios = (fin.get("balance_sheet", {}) or {}).get("ratios", {}) or {}
    inc = fin.get("income_statement", {}) or {}
    nd = _last(ratios.get("net_debt_ebitda"))
    ebitda, fin_costs = _last(inc.get("ebitda")), _last(inc.get("finance_costs"))
    icr = (abs(ebitda) / abs(fin_costs)) if (ebitda and fin_costs) else None
    adj, facts = 0.0, []
    if nd is not None:
        if nd > 6: adj += 0.8; facts.append(f"Долг/EBITDA {nd:.1f}× — критическая нагрузка")
        elif nd > 4: adj += 0.5; facts.append(f"Долг/EBITDA {nd:.1f}× — высокая нагрузка")
        elif nd > 3: adj += 0.2; facts.append(f"Долг/EBITDA {nd:.1f}× — повышенная")
        elif nd < 1.5: adj -= 0.3; facts.append(f"Долг/EBITDA {nd:.1f}× — низкая нагрузка")
    if icr is not None:
        if icr < 1: adj += 0.6; facts.append(f"Покрытие процентов {icr:.1f}× — проедает себя")
        elif icr < 1.5: adj += 0.3; facts.append(f"Покрытие процентов {icr:.1f}× — напряжённо")
        elif icr > 4: adj -= 0.2; facts.append(f"Покрытие процентов {icr:.1f}× — комфортно")
    return adj, ("; ".join(facts) if facts else None)


def compute_risk_score(bond: dict, debt_adj: float = 0.0) -> float:
    """Risk Score (1–5): якорь по рейтингу/спред-тиру + блок A + стоп-флаги."""
    if bond.get("is_defaulted"):
        return 5.0
    g = rating_group(bond.get("agency_rating"))
    if g:
        base = SCORE_BY_GROUP[g]
    else:  # нет рейтинга → по рыночному тиру
        base = {"gov": 1.2, "high": 2.2, "medium": 3.2, "speculative": 4.2}.get(bond.get("risk_tier"), 3.5)
    score = base + debt_adj
    if bond.get("yield_anomaly"):
        score = max(score, 4.6)
    return round(min(max(score, 1.0), 5.0), 2)


def group_median_spreads(rows: list[dict]) -> dict:
    """Медианный G-spread по рейтинговой группе из нашей базы (требуемый спред-базис)."""
    from statistics import median
    buckets: dict[str, list] = {}
    for b in rows:
        if b.get("bond_type") == "ofz" or b.get("spread_bp") is None or b.get("is_defaulted"):
            continue
        g = rating_group(b.get("agency_rating")) or _tier_group(b.get("risk_tier"))
        if g:
            buckets.setdefault(g, []).append(b["spread_bp"])
    return {g: round(median(v)) for g, v in buckets.items() if v}


def _tier_group(tier: str | None) -> str | None:
    return {"high": "A", "medium": "BBB", "speculative": "B"}.get(tier)


def yield_vs_risk(bond: dict, group_medians: dict) -> dict | None:
    """Полный вердикт «доходность vs риск» по методике для одной бумаги."""
    if bond.get("bond_type") == "ofz":
        return {"verdict": "ОФЗ — госдолг, кредитного риска практически нет; доходность = безрисковая ставка.", "light": "green", "is_ofz": True}
    spread = bond.get("spread_bp")
    if spread is None:
        return {"verdict": "Нет рыночной оценки (неликвид / нет YTM) — соответствие доходности риску оценить нельзя.", "light": "gray", "no_data": True}

    debt_adj, debt_facts = issuer_debt_adjustment(bond.get("issuer_ticker"))
    score = compute_risk_score(bond, debt_adj)
    implied = score_to_group(score)
    agency_g = rating_group(bond.get("agency_rating"))
    rgroup = agency_g or _tier_group(bond.get("risk_tier")) or implied
    # требуемый спред — по ХУДШЕЙ из (агентский рейтинг, оценка Basis): если наш
    # анализ видит риск выше рейтинга, не занижаем требуемую премию (методика 3.1)
    req_group = worse_group(rgroup, implied)
    base_req = group_medians.get(req_group) or group_medians.get(rgroup) or spread
    req = base_req
    adj_notes = []
    if not bond.get("agency_rating"):
        req += 100; adj_notes.append("+100 б.п. за отсутствие рейтинга")
    divergence_note = None
    if agency_g and GROUP_RANK.get(implied, 3) - GROUP_RANK.get(agency_g, 3) >= 2:
        divergence_note = f"Наш анализ видит риск ВЫШЕ рейтинга: оценка Basis ~{implied} против {agency_g} у агентства."
    elif agency_g and GROUP_RANK.get(agency_g, 3) - GROUP_RANK.get(implied, 3) >= 2:
        divergence_note = f"Наш анализ видит риск НИЖЕ рейтинга: оценка Basis ~{implied} против {agency_g} у агентства."
    required = round(req)

    premium = spread - required  # >0 = риск оплачен
    # светофор по методике
    if premium > 200: light, label = "green", "Риск оплачен с запасом"
    elif premium >= 50: light, label = "green", "Риск оплачен"
    elif premium >= -50: light, label = "amber", "Справедливо"
    elif premium >= -200: light, label = "orange", "Риск недоплачен"
    else: light, label = "red", "Риск существенно недоплачен"

    # стоп-правила
    stops = []
    if bond.get("is_defaulted"):
        light, label = "red", "Дефолт — доходность нерелевантна"; stops.append("дефолт/режим Д")
    if bond.get("yield_anomaly"):
        if light in ("green", "amber"): light = "orange"
        stops.append("аномальная доходность (>40%) — вероятен дистресс/неликвид")
    if premium > 400 and (score >= 4.2):
        stops.append("очень большая премия при высоком риске — спросите «что знает рынок?»")

    # проверка ожидаемыми потерями — по худшей группе (консервативно)
    pd = PD_BY_GROUP.get(req_group, PD_BY_GROUP.get(implied, 0.05))
    min_spread_el = round(pd * LGD * 10000)
    el_note = (f"При вероятности дефолта ~{pd*100:.0f}%/год и потере ~{int(LGD*100)}% при дефолте "
               f"минимально нужно ~{min_spread_el} б.п. только за ожидаемые потери. "
               f"Бумага платит {spread} б.п.")

    # Прозрачная деривация Risk Score — «за прозрачность»: показываем, КАК получили
    # оценку (методика docs/bond_analys.md), а не отдаём число «из чёрного ящика».
    derivation = []
    if bond.get("is_defaulted"):
        derivation.append("Эмитент в дефолте (режим Д / отметка MOEX) → Risk Score = 5,0 из 5 (максимум). Доходность к погашению нерелевантна — вопрос в проценте возврата тела.")
    else:
        if bond.get("agency_rating"):
            derivation.append(f"Якорь — агентский рейтинг {bond.get('agency_rating')} (группа {agency_g}): базовый Risk Score {SCORE_BY_GROUP.get(agency_g, '—')} из 5.")
        else:
            tier_base = {"gov": 1.2, "high": 2.2, "medium": 3.2, "speculative": 4.2}.get(bond.get("risk_tier"), 3.5)
            derivation.append(f"Рейтинга агентств нет → якорь по рыночному тиру «{bond.get('risk_tier') or 'н/д'}» (спред к ОФЗ): базовый Risk Score {tier_base} из 5.")
        if debt_facts:
            derivation.append(f"Блок A — платёжеспособность (из отчётности эмитента): {debt_facts}. Поправка к Score {debt_adj:+.1f}.")
        elif bond.get("issuer_ticker"):
            derivation.append("Блок A — платёжеспособность: в отчётности эмитента нет ключевых метрик долга, поправка не применена.")
        else:
            derivation.append("Блок A — платёжеспособность: эмитент непубличный, выверенной отчётности в базе нет (нужен глубокий разбор для оценки долга из РСБУ).")
        if bond.get("yield_anomaly"):
            derivation.append("Стоп-флаг: аномальная доходность (>40% годовых) → Risk Score поднят минимум до 4,6 (маркер дистресса/неликвида).")
        derivation.append(f"Итог: Risk Score {str(score).replace('.', ',')} из 5 → оценка Basis ~{implied}.")

    score_method = ("Систематическая оценка по методике Basis: рейтинг-якорь + блок A "
                    "(долговая нагрузка из отчётности, для публичных) + стоп-флаги. "
                    "Блоки бизнеса, собственников, макро/PESTEL и параметров выпуска "
                    "учитываются в полном объёме в «Разборе аналитика» (если он есть по бумаге).")

    return {
        "spread_bp": spread, "required_bp": required, "premium_bp": premium,
        "light": light, "label": label,
        "risk_score": score, "implied_group": implied, "agency_group": agency_g,
        "rating_group": req_group, "group_median_bp": base_req,
        "divergence_note": divergence_note,
        "adjustments": adj_notes, "debt_facts": debt_facts,
        "expected_loss_note": el_note, "min_spread_el_bp": min_spread_el,
        "stops": stops,
        "derivation": derivation, "score_method": score_method,
        "certainty": "оценка (методика Basis по нашей базе)",
    }
