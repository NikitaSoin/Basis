"""Индекс качества портфеля v2.1 — ФАЗА 1 + частичная ФАЗА 2 (методика
docs/Basis_методика_индекса_качества_портфеля_v2.1.md, владелец, 2026-07-09).

Реализовано:
  - D   (Диверсификация) — IssuerD + SectorD + CorrD + FactorD (код-маппер
    экспозиций из macro.json/geo.json effect_sign, §3.1-3.2).
  - MR  (Рыночный риск) — σ + MDD + VaR95 дневной.
  - FQ  (Фундаментальное качество) — ЧАСТИЧНО: FS (код из financials.json) +
    Gov (governance.json scoring.overall_score). BM/MP/CA (бизнес-модель/
    рыночная позиция/capital allocation) требуют нового LLM-субагента
    quality-scorer — НЕ реализованы, FQ_p считается на доступных FS+Gov с
    перенормировкой весов (честная деградация, не молчаливый ноль).
  - V   (Запас прочности) — Confidence кодом (ширина коридора/расхождение
    методов/data_quality) × Upside к fair_value_range.base → RAU.
  - MGI (Сценарная устойчивость) — через общий факторный движок
    (factor_engine.py): StressLoss + BearLoss по 4 сценариям (§3.3-3.4).
  - ERR — исторический слой (альфа Дженсена) + форвардный слой (сценарная
    ожидаемая доходность через тот же факторный движок, что MGI).
  - L   (Ликвидность) — доля портфеля ликвидируемая ≤1 дня + доля в
    неликвидных бумагах (спред — Фаза 3, нужен стакан).

Живёт РЯДОМ со старым compute_quality_index (v1, App.js поле "quality") —
не заменяет его. Overall помечается частичным там, где модуль недоступен
(веса перенормируются на доступные — раздел 15 методики).

MVP-охват — раздел 12 методики: акции + кэш. Облигации/фьючерсы/фонды пока
НЕ участвуют (не разбавляют — исключены из базы, а не считаются нулём).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Quote
from app.services.portfolio import _lin_score, _clamp01
from app.services import factor_exposures, factor_engine

METHODOLOGY_VERSION = "v2.1-phase2-partial"

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"


def _load_company_json(ticker: str, filename: str) -> dict | None:
    path = COMPANIES_DIR / ticker.upper() / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

# Не-эмитентские "секторы", которые батч мульти-класса добавил в
# sector_allocation (Денежные средства/Облигации/Фонды/Фьючерсы) — для
# SectorD (в MVP-охвате только акции+кэш) участвуют только реальные секторы.
_NON_EQUITY_SECTOR_LABELS = {"Облигации", "Фьючерсы", "Фонды", "Денежные средства"}

ADV_WINDOW_DAYS = 90     # календарных, чтобы получить ~60 торговых дней
PARTICIPATION_RATE = 0.10
ILLIQUID_ADV_THRESHOLD = 5_000_000  # ₽/день (раздел 11 методики)


def _n_eff(weights: list[float]) -> float | None:
    """Эффективное число позиций = 1/HHI (Herfindahl)."""
    tot = sum(weights)
    if tot <= 0:
        return None
    norm = [w / tot for w in weights]
    return 1.0 / sum(x * x for x in norm)


def _sector_n_eff(sector_allocation: list[dict]) -> float | None:
    """N_sector_eff = 1/Σsⱼ² по РЕАЛЬНЫМ секторам (без синтетич. классов активов)."""
    real = [s for s in (sector_allocation or []) if s.get("sector") not in _NON_EQUITY_SECTOR_LABELS and s.get("value")]
    tot = sum(s["value"] for s in real)
    if tot <= 0:
        return None
    norm = [s["value"] / tot for s in real]
    return 1.0 / sum(x * x for x in norm)


def _weighted_corr_normalized(correlation: dict | None, weights_by_ticker: dict[str, float]) -> float | None:
    """WeightedAvgCorr = Σ_{i≠j} wᵢwⱼρᵢⱼ / Σ_{i≠j} wᵢwⱼ — нормировано (методика
    §4, челлендж №6: без нормировки максимум зависит от весов, число
    несопоставимо между портфелями)."""
    if not correlation or not correlation.get("matrix"):
        return None
    tickers = correlation["tickers"]
    matrix = correlation["matrix"]
    num, den = 0.0, 0.0
    for i in range(len(tickers)):
        for j in range(len(tickers)):
            if i == j:
                continue
            rho = matrix[i][j]
            if not isinstance(rho, (int, float)):
                continue
            wi = weights_by_ticker.get(tickers[i], 0.0)
            wj = weights_by_ticker.get(tickers[j], 0.0)
            num += wi * wj * rho
            den += wi * wj
    if den <= 0:
        return None
    return num / den


def _compute_liquidity(db: Session, equity_positions: list[dict], cash_value: float, total_value: float) -> dict | None:
    """L = 70%·D2L + 30%·Illiq (спред — Фаза 3, нужен стакан, честно пропущен
    — раздел 10 методики допускает эту деградацию явно)."""
    if total_value <= 0:
        return None
    since = date.today() - timedelta(days=ADV_WINDOW_DAYS)
    company_ids = [p["company_id"] for p in equity_positions if p.get("company_id")]
    adv_by_company: dict[int, float] = {}
    if company_ids:
        rows = (
            db.query(Quote.company_id, func.avg(Quote.volume).label("adv"))
            .filter(Quote.company_id.in_(company_ids), Quote.date >= since, Quote.volume.isnot(None))
            .group_by(Quote.company_id)
            .all()
        )
        adv_by_company = {r.company_id: float(r.adv) for r in rows if r.adv}

    liquid_le_1d = cash_value  # кэш — мгновенная ликвидность
    illiquid_value = 0.0
    covered_value = cash_value
    for p in equity_positions:
        adv = adv_by_company.get(p.get("company_id"))
        if adv is None or adv <= 0:
            continue  # нет данных об обороте — не в базе (честная деградация)
        covered_value += p["value"]
        days_to_liquidate = p["value"] / (adv * PARTICIPATION_RATE)
        if days_to_liquidate <= 1:
            liquid_le_1d += p["value"]
        if adv < ILLIQUID_ADV_THRESHOLD:
            illiquid_value += p["value"]

    if covered_value <= 0:
        return None

    share_liquid_1d = liquid_le_1d / covered_value * 100
    share_illiquid = illiquid_value / covered_value * 100

    d2l_score = _lin_score(share_liquid_1d, best=90, worst=40)
    illiq_score = _lin_score(share_illiquid, best=0, worst=30)
    scores = [s for s in (d2l_score, illiq_score) if s is not None]
    if not scores:
        return None
    l_score = round(0.7 * (d2l_score or 0) + 0.3 * (illiq_score or 0)) if d2l_score is not None and illiq_score is not None else round(sum(scores) / len(scores))

    return {
        "key": "liquidity", "label": "Ликвидность", "score": l_score,
        "confidence": "факт / оценка",
        "components": [
            {"name": "Доля портфеля, ликвидируемая ≤1 дня (10% от дневного оборота)", "value": f"{share_liquid_1d:.0f}%", "score": d2l_score},
            {"name": "Доля в бумагах с низким оборотом (<5 млн ₽/день)", "value": f"{share_illiquid:.0f}%", "score": illiq_score},
        ],
        "verdict": (
            "Портфель можно выйти быстро без давления на цену."
            if l_score >= 60 else
            "Часть портфеля потребует времени на выход без потерь в цене."
            if l_score >= 40 else
            "Заметная доля портфеля — в низколиквидных бумагах: быстрый выход обвалит цену исполнения."
        ),
        "limitation": "Биржевой спред (bid-ask) не учтён — нужен стакан, следующая фаза методики. Покрытие: "
                      f"{round(covered_value / total_value * 100)}% стоимости портфеля (кэш + бумаги с данными об обороте).",
    }


def _last(series: list | None):
    if not series:
        return None
    return next((v for v in reversed(series) if v is not None), None)


def _fs_score(ticker: str) -> float | None:
    """FS — финансовая устойчивость, кодом из financials.json (методика §6.1).
    Банки/страховые (ND/EBITDA неприменим) — не считается, «открытый пункт»
    методики (раздел 18.7), честно исключается из FQ_p для этих компаний."""
    fin = _load_company_json(ticker, "financials.json")
    if not fin:
        return None
    if (fin.get("meta") or {}).get("profile") == "bank":
        return None
    bal = fin.get("balance_sheet") or {}
    ratios = bal.get("ratios") or {}
    inc = fin.get("income_statement") or {}
    adj = fin.get("adjusted") or {}

    nd_ebitda = _last(ratios.get("net_debt_ebitda"))
    ebitda = _last(inc.get("ebitda"))
    finance_costs = _last(inc.get("finance_costs"))
    icr = (ebitda / finance_costs) if (ebitda is not None and finance_costs) else None
    fcf = _last(adj.get("fcf_normalized"))
    revenue = _last(inc.get("revenue"))
    fcf_margin = (fcf / revenue * 100) if (fcf is not None and revenue) else None
    st = _last(bal.get("short_term_debt"))
    lt = _last(bal.get("long_term_debt"))
    short_ratio = (st / (st + lt) * 100) if (st is not None and lt is not None and (st + lt) > 0) else None

    parts = [
        _lin_score(nd_ebitda, best=0.5, worst=4),
        _lin_score(icr, best=8, worst=1.5),
        _lin_score(fcf_margin, best=12, worst=0),
        _lin_score(short_ratio, best=15, worst=60),
    ]
    parts = [p for p in parts if p is not None]
    return round(sum(parts) / len(parts)) if parts else None


def _gov_score(ticker: str) -> float | None:
    gov = _load_company_json(ticker, "governance.json")
    if not gov:
        return None
    overall = ((gov.get("scoring") or {}).get("overall_score"))
    if overall is None:
        return None
    return _lin_score(overall, best=5, worst=1)  # шкала governance 1-5 → 0-100


def _compute_fq(equity: list[dict]) -> dict | None:
    """FQ_p — ЧАСТИЧНЫЙ (только FS 25% + Gov 20% из полных весов методики,
    BM/MP/CA нужен quality-scorer — не реализован). Перенормировка на
    доступные компоненты, штраф MultiWeakShare пока не считается (нужны
    red_flags по ВСЕМ компонентам, часть которых недоступна)."""
    FQ_SUB_WEIGHTS = {"fs": 0.25, "gov": 0.20}
    total_w = sum(p["value"] for p in equity)
    if total_w <= 0:
        return None
    num, covered_w = 0.0, 0.0
    per_company = []
    for p in equity:
        fs = _fs_score(p["ticker"])
        gov = _gov_score(p["ticker"])
        parts = [(k, s) for k, s in (("fs", fs), ("gov", gov)) if s is not None]
        if not parts:
            continue
        den = sum(FQ_SUB_WEIGHTS[k] for k, _ in parts)
        company_fq = sum(FQ_SUB_WEIGHTS[k] * s for k, s in parts) / den
        num += p["value"] * company_fq
        covered_w += p["value"]
        per_company.append({"ticker": p["ticker"], "fs": fs, "gov": gov, "fq": round(company_fq)})
    if covered_w <= 0:
        return None
    fq_p = round(num / covered_w)
    coverage_pct = round(covered_w / total_w * 100)
    fs_vals = [c["fs"] for c in per_company if c.get("fs") is not None]
    gov_vals = [c["gov"] for c in per_company if c.get("gov") is not None]
    fs_avg = round(sum(fs_vals) / len(fs_vals)) if fs_vals else None
    gov_avg = round(sum(gov_vals) / len(gov_vals)) if gov_vals else None
    return {
        "key": "fundamental_quality_v2", "label": "Фундаментальное качество", "score": fq_p,
        "confidence": "оценка + суждение",
        "coverage_note": f"ЧАСТИЧНЫЙ: только финансовая устойчивость (FS) и управление (Gov) — "
                         f"25%+20% из полных весов методики. Бизнес-модель/рыночная позиция/"
                         f"capital allocation (BM/MP/CA, 55% веса FQ) требуют LLM-субагента "
                         f"quality-scorer — не реализованы. Покрытие: {coverage_pct}% стоимости акций.",
        "components": [
            {"name": "Финансовая устойчивость (ND/EBITDA, покрытие процентов, FCF-маржа, срочность долга)",
             "value": f"{fs_avg}" if fs_avg is not None else "—", "score": fs_avg},
            {"name": "Корпоративное управление (governance-балл)",
             "value": f"{gov_avg}" if gov_avg is not None else "—", "score": gov_avg},
        ],
        "verdict": (
            "По доступным данным (устойчивость баланса + управление) портфель держит качественные компании."
            if fq_p >= 60 else
            "Смешанная картина по устойчивости баланса и управлению — не все компании одинаково крепки."
            if fq_p >= 40 else
            "По доступным данным заметная доля портфеля — компании с повышенным долговым риском и/или слабым управлением."
        ),
        "per_company": per_company,
    }


def _v_confidence(fv: dict, divergence_pct: float | None, data_quality: str | None) -> float:
    """Confidence кодом (методика §7, произвол): старт 0.9, штрафы за ширину
    коридора/расхождение методов/data_quality, пол 0.2."""
    conf = 0.9
    cons, base = fv.get("conservative"), fv.get("base")
    if cons is not None and base:
        width_pct = abs(base - cons) / abs(base) * 100
        if width_pct > 50:
            conf -= 0.45
        elif width_pct > 30:
            conf -= 0.30
        elif width_pct > 15:
            conf -= 0.15
    if divergence_pct is not None and divergence_pct > 30:
        conf -= 0.15
    dq_penalty = {"high": 0.0, "medium": 0.10, "low": 0.25}.get((data_quality or "").lower(), 0.10)
    conf -= dq_penalty
    return max(0.2, conf)


def _compute_v(equity: list[dict]) -> dict | None:
    """V — запас прочности. RAU(i) = Upside_base × Confidence; PortfolioRAU —
    взвешенное среднее по покрытым (методика §7)."""
    total_w = sum(p["value"] for p in equity)
    if total_w <= 0:
        return None
    num, covered_w = 0.0, 0.0
    for p in equity:
        fin = _load_company_json(p["ticker"], "financials.json")
        if not fin:
            continue
        fv = (fin.get("valuation") or {}).get("fair_value_range") or {}
        base, price = fv.get("base"), fv.get("current_price")
        if base is None or not price:
            continue
        upside = (base - price) / price
        methods = (fin.get("valuation") or {}).get("methods") or []
        vals = [m.get("fair_value_per_share") for m in methods if isinstance(m.get("fair_value_per_share"), (int, float))]
        divergence_pct = ((max(vals) - min(vals)) / base * 100) if len(vals) >= 2 and base else None
        data_quality = (fin.get("meta") or {}).get("data_quality")
        confidence = _v_confidence(fv, divergence_pct, data_quality)
        rau = upside * confidence
        num += p["value"] * rau
        covered_w += p["value"]
    if covered_w <= 0:
        return None
    portfolio_rau = num / covered_w
    v_score = _lin_score(portfolio_rau * 100, best=25, worst=-10)
    if v_score is None:
        return None
    coverage_pct = round(covered_w / total_w * 100)
    return {
        "key": "value_v2", "label": "Запас прочности", "score": v_score,
        "confidence": "суждение",
        "coverage_note": f"Покрытие: {coverage_pct}% стоимости акций (модельная справедливая цена доступна не по всем компаниям).",
        "components": [
            {"name": "Взвешенный апсайд к справедливой цене × уверенность в оценке",
             "value": f"{portfolio_rau*100:+.1f}%", "score": v_score},
        ],
        "verdict": (
            "В среднем портфель куплен с запасом прочности к модельной справедливой цене."
            if v_score >= 60 else
            "Портфель в среднем близок к справедливой цене — запас прочности умеренный."
            if v_score >= 40 else
            "В среднем портфель куплен дороже модельной справедливой цены — запаса прочности нет."
        ),
        "limitation": "Модельная оценка Basis (не факт, не таргет аналитиков). Апсайд — не годовая доходность "
                      "сама по себе (см. ERR — там премия соотнесена со сроком и риском).",
    }


def _compute_mgi(weights_eq: dict[str, float]) -> dict | None:
    """MGI — сценарная устойчивость через общий факторный движок (методика §8)."""
    losses = factor_engine.portfolio_scenario_losses(weights_eq)
    if not losses:
        return None
    stress_loss = (losses.get("stress") or {}).get("loss_pct")
    bear_loss = (losses.get("bear") or {}).get("loss_pct")
    stress_score = _lin_score(stress_loss, best=10, worst=40)
    bear_score = _lin_score(bear_loss, best=5, worst=25)
    parts = [(0.60, stress_score), (0.40, bear_score)]
    parts = [(w, s) for w, s in parts if s is not None]
    if not parts:
        return None
    den = sum(w for w, _ in parts)
    mgi_score = round(sum(w * s for w, s in parts) / den)
    coverage_pct = (losses.get("stress") or {}).get("coverage_pct")
    return {
        "key": "mgi_v2", "label": "Сценарная устойчивость", "score": mgi_score,
        "confidence": "суждение",
        "coverage_note": f"Сценарная библиотека Basis (§3.3 методики): база 55% / бычий 15% / медвежий 25% / "
                         f"стрессовый 5%. Покрытие факторными данными: {coverage_pct}% стоимости акций.",
        "components": [
            c for c in [
                {"name": "Потери в стрессовом сценарии (эскалация + санкции + просадка сырья/ставки)",
                 "value": f"{stress_loss:.1f}%" if stress_loss is not None else "—", "score": stress_score},
                {"name": "Потери в медвежьем сценарии (ставка выше дольше, слабый спрос/сырьё)",
                 "value": f"{bear_loss:.1f}%" if bear_loss is not None else "—", "score": bear_score},
            ] if c["score"] is not None
        ],
        "verdict": (
            "Портфель относительно устойчив к плохим макро/гео-сценариям."
            if mgi_score >= 60 else
            "Заметные потери в плохих сценариях — портфель чувствителен к ставке/санкциям/сырью."
            if mgi_score >= 40 else
            "Портфель тяжело переносит стрессовые сценарии — концентрация в уязвимых к ставке/санкциям/сырью факторах."
        ),
        "limitation": "Грубая линейная модель (сценарная реакция = экспозиция × интенсивность), явно помечена "
                      "методикой как суждение, не прогноз. Экспозиции берутся из карточек компаний (macro.json/"
                      "geo.json) — это снимок ТЕКУЩЕГО тренда фактора («цена сырья сейчас давит»/«помогает»), "
                      "не всегда чистая структурная бета к уровню фактора; для части компаний может расходиться "
                      "со здравым смыслом («сырьевик страдает от низкой цены» — это верно только если фактор "
                      "интерпретируется как «текущее давление», не «структурная любовь к высокой цене»). "
                      "Вероятности сценариев — центральный домашний взгляд Basis, не консенсус рынка.",
    }


def compute_quality_index_v2(
    db: Session, *,
    positions: list[dict], total_value: float,
    correlation: dict | None, sector_allocation: list[dict],
    volatility: float | None, var_95: float | None, max_drawdown: float | None,
    alpha: float | None,
) -> dict | None:
    """Индекс качества v2.1, Фаза 1. positions — ПОЛНЫЙ список позиций
    (compute_portfolio_metrics 'valued'), включая non-equity — здесь
    фильтруются под MVP-охват (акции+кэш, раздел 12 методики)."""
    if total_value <= 0:
        return None

    equity = [p for p in positions if p.get("instrument_type", "equity") == "equity" and p.get("company_id")]
    cash_value = sum(p["value"] for p in positions if p.get("instrument_type") == "cash" and p.get("value"))
    if not equity:
        return None

    def band(score: int) -> str:
        return ("Сильный" if score >= 75 else "Умеренный" if score >= 60
                else "Ниже среднего" if score >= 40 else "Слабый")

    subindices = []

    # ── D: IssuerD + SectorD + CorrD + FactorD ──
    weights_eq = {p["ticker"]: p["value"] for p in equity}
    issuer_score = _lin_score(_n_eff(list(weights_eq.values())), best=8, worst=1)
    sector_score = _lin_score(_sector_n_eff(sector_allocation), best=5, worst=1)
    weighted_corr = _weighted_corr_normalized(correlation, weights_eq)
    corr_score = _lin_score(weighted_corr, best=0.2, worst=0.7)

    exp_data = factor_exposures.get_portfolio_exposures(weights_eq)
    factor_conc_score, factor_conc_pct, factor_conc_label = None, None, None
    if exp_data.get("per_company"):
        tot_eq = sum(weights_eq.values())
        neg_shares = {}
        for k in factor_exposures.FACTOR_KEYS:
            neg_w = sum(w for t, w in weights_eq.items()
                       if (exp_data["per_company"].get(t, {}).get(k) or 0) <= -1)
            neg_shares[k] = neg_w / tot_eq if tot_eq else 0
        if neg_shares:
            factor_conc_label = max(neg_shares, key=neg_shares.get)
            factor_conc_pct = neg_shares[factor_conc_label] * 100
            factor_conc_score = _lin_score(factor_conc_pct, best=25, worst=75)

    D_WEIGHTS = {"issuer": 0.30, "sector": 0.20, "corr": 0.25, "factor": 0.25}
    d_parts = [(k, s) for k, s in (("issuer", issuer_score), ("sector", sector_score),
                                    ("corr", corr_score), ("factor", factor_conc_score)) if s is not None]
    if d_parts:
        den = sum(D_WEIGHTS[k] for k, _ in d_parts)
        d_score = round(sum(D_WEIGHTS[k] * s for k, s in d_parts) / den)
        d_components = [
            c for c in [
                {"name": "Эффективное число эмитентов", "value": f"{_n_eff(list(weights_eq.values())):.1f}" if issuer_score is not None else "—", "score": issuer_score},
                {"name": "Эффективное число секторов", "value": f"{_sector_n_eff(sector_allocation):.1f}" if sector_score is not None else "—", "score": sector_score},
                {"name": "Взвешенная корреляция (нормированная)", "value": f"{weighted_corr:.2f}" if weighted_corr is not None else "—", "score": corr_score},
            ] if c["score"] is not None
        ]
        if factor_conc_score is not None:
            d_components.append({
                "name": f"Концентрация по фактору «{factor_exposures.FACTOR_LABELS.get(factor_conc_label, factor_conc_label)}» (доля с выраженной негативной чувствительностью)",
                "value": f"{factor_conc_pct:.0f}%", "score": factor_conc_score,
            })
        subindices.append({
            "key": "diversification_v2", "label": "Диверсификация", "score": d_score,
            "confidence": "факт (+суждение в факторной концентрации)",
            "components": d_components,
            "verdict": (
                "Капитал разложен по разным эмитентам, секторам и факторам риска, бумаги слабо коррелируют."
                if d_score >= 60 else
                "Часть капитала сконцентрирована — в узком круге эмитентов, секторе, факторе риска или бумагах, которые двигаются вместе."
                if d_score >= 40 else
                "Сильная концентрация: узкий круг эмитентов/секторов/факторов риска, высокая взаимная корреляция — просадки придут одновременно."
            ),
        })

    # ── MR: σ + MDD + VaR95 (без беты — не входит в v2.1) ──
    mdd_abs = abs(max_drawdown) if max_drawdown is not None else None
    sigma_score = _lin_score(volatility, best=15, worst=45)
    mdd_score = _lin_score(mdd_abs, best=15, worst=55)
    var_score = _lin_score(var_95, best=1.5, worst=4)
    MR_WEIGHTS = {"sigma": 0.40, "mdd": 0.35, "var": 0.25}
    mr_parts = [(k, s) for k, s in (("sigma", sigma_score), ("mdd", mdd_score), ("var", var_score)) if s is not None]
    if mr_parts:
        den = sum(MR_WEIGHTS[k] for k, _ in mr_parts)
        mr_score = round(sum(MR_WEIGHTS[k] * s for k, s in mr_parts) / den)
        subindices.append({
            "key": "market_risk_v2", "label": "Рыночный риск", "score": mr_score,
            "confidence": "оценка",
            "components": [
                c for c in [
                    {"name": "Волатильность портфеля", "value": f"{volatility:.1f}%" if volatility is not None else "—", "score": sigma_score},
                    {"name": "Макс. просадка (до 5 лет)", "value": f"{mdd_abs:.1f}%" if mdd_abs is not None else "—", "score": mdd_score},
                    {"name": "VaR 95% (дневной)", "value": f"{var_95:.1f}%" if var_95 is not None else "—", "score": var_score},
                ] if c["score"] is not None
            ],
            "verdict": (
                "Портфель исторически падал умеренно даже в плохие периоды."
                if mr_score >= 60 else
                "Заметные колебания и просадки в плохие периоды рынка."
                if mr_score >= 40 else
                "Портфель исторически проседал глубоко — высокая чувствительность к рыночным обвалам."
            ),
            "limitation": "Рыночный риск (волатильность/просадка/VaR). Сценарный «хвостовой» риск (макро/гео-шоки) сюда не входит — модуль MGI методики, Фаза 3.",
        })

    # ── ERR: исторический слой (альфа Дженсена) + форвардный (сценарная премия/StressLoss) ──
    hist_score = _lin_score(alpha, best=6, worst=-6)

    fwd_score, fwd_note = None, None
    from app.services.moex_dividends import get_market_param
    rf_row = get_market_param(db, "risk_free_1y")
    rf = rf_row[0] / 100 if rf_row else None
    upside_by_ticker, div_by_ticker = {}, {}
    for p in equity:
        fin = _load_company_json(p["ticker"], "financials.json")
        if fin:
            fv = (fin.get("valuation") or {}).get("fair_value_range") or {}
            base, price = fv.get("base"), fv.get("current_price")
            if base is not None and price:
                upside_by_ticker[p["ticker"]] = (base - price) / price
        gov = _load_company_json(p["ticker"], "governance.json")
        if gov:
            hist_div = ((gov.get("dividends") or {}).get("history") or [])
            last = hist_div[-1] if hist_div else None
            if last and last.get("yield_pct") is not None:
                div_by_ticker[p["ticker"]] = last["yield_pct"] / 100
    if rf is not None and upside_by_ticker:
        fwd = factor_engine.expected_scenario_return(weights_eq, upside_by_ticker, div_by_ticker)
        losses = factor_engine.portfolio_scenario_losses(weights_eq)
        stress_loss_frac = ((losses.get("stress") or {}).get("loss_pct") or 0) / 100
        if fwd.get("expected") is not None and stress_loss_frac > 0:
            risk_premium = fwd["expected"] - rf
            reward_to_risk = risk_premium / stress_loss_frac
            fwd_score = _lin_score(reward_to_risk, best=0.6, worst=0)
            fwd_note = {"expected_return": fwd["expected"], "risk_premium": risk_premium,
                       "reward_to_risk": reward_to_risk, "stress_loss": stress_loss_frac}

    ERR_WEIGHTS = {"hist": 0.30, "fwd": 0.70}
    err_parts = [(k, s) for k, s in (("hist", hist_score), ("fwd", fwd_score)) if s is not None]
    if err_parts:
        den = sum(ERR_WEIGHTS[k] for k, _ in err_parts)
        err_score = round(sum(ERR_WEIGHTS[k] * s for k, s in err_parts) / den)
        err_components = [{"name": "Альфа Дженсена (к MCFTR, истор.)", "value": f"{alpha:+.1f}%", "score": hist_score}] if hist_score is not None else []
        if fwd_score is not None and fwd_note:
            err_components.append({
                "name": "Сценарная премия к риск-фри / стресс-потеря (форвард)",
                "value": f"{fwd_note['risk_premium']*100:+.1f}пп / {fwd_note['stress_loss']*100:.1f}%",
                "score": fwd_score,
            })
        subindices.append({
            "key": "err_v2", "label": "Доходность к риску", "score": err_score,
            "confidence": "оценка + суждение",
            "coverage_note": None if fwd_score is not None else "только исторический слой — нет данных по справедливой цене/риск-фри ставке для форвардного слоя",
            "components": err_components,
            "verdict": (
                "Ожидаемая премия за риск оправдывает потенциальный ущерб в плохих сценариях."
                if err_score >= 60 else
                "Премия за риск умеренная относительно возможного ущерба в плохих сценариях."
                if err_score >= 40 else
                "Премия за риск не компенсирует возможный ущерб в плохих сценариях."
            ),
            "limitation": "Форвардный слой — грубая линейная сценарная модель (тот же движок, что MGI), явно суждение, не прогноз.",
        })

    # ── FQ, V, MGI ──
    fq = _compute_fq(equity)
    if fq is not None:
        subindices.append(fq)
    v = _compute_v(equity)
    if v is not None:
        subindices.append(v)
    mgi = _compute_mgi(weights_eq)
    if mgi is not None:
        subindices.append(mgi)

    # ── L: ликвидность ──
    liquidity = _compute_liquidity(db, equity, cash_value, total_value)
    if liquidity is not None:
        subindices.append(liquidity)

    if not subindices:
        return None

    # Overall — переразвешено на ДОСТУПНЫЕ модули (полные веса методики §2:
    # D 20% / MR 15% / FQ 20% / V 15% / MGI 15% / ERR 10% / L 5%)
    OVERALL_WEIGHTS = {
        "diversification_v2": 0.20, "market_risk_v2": 0.15, "fundamental_quality_v2": 0.20,
        "value_v2": 0.15, "mgi_v2": 0.15, "err_v2": 0.10, "liquidity": 0.05,
    }
    num = sum(OVERALL_WEIGHTS[s["key"]] * s["score"] for s in subindices)
    den = sum(OVERALL_WEIGHTS[s["key"]] for s in subindices)
    overall = round(num / den) if den else None

    return {
        "overall": overall,
        "label": band(overall) if overall is not None else None,
        "subindices": subindices,
        "weights": {s["key"]: OVERALL_WEIGHTS[s["key"]] for s in subindices},
        "methodology_version": METHODOLOGY_VERSION,
        "phase_note": (
            "Все 7 модулей методики v2.1 считаются, но «Фундаментальное качество» — ЧАСТИЧНО: "
            "реализованы только финансовая устойчивость (код) и корпоративное управление "
            "(уже готовый governance-балл) — 45% из полного веса модуля. Бизнес-модель, "
            "рыночная позиция и capital allocation (BM/MP/CA, 55% веса) требуют нового "
            "LLM-субагента quality-scorer с откалиброванными эталонами — не реализованы, "
            "следующая фаза. Сценарная устойчивость и форвардная доходность — по грубой "
            "линейной факторной модели (явно суждение, не прогноз), см. лимитации модулей."
        ),
        "note": "Якоря и веса — продуктовое решение (произвол), калибруются после первых прогонов "
                "на реальных портфелях — docs/Basis_методика_индекса_качества_портфеля_v2.1.md.",
    }
