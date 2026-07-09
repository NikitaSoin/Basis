"""Индекс качества портфеля v2.1 — ФАЗА 1 (рыночные модули, без новых LLM-задач).

Методика: docs/Basis_методика_индекса_качества_портфеля_v2.1.md (владелец,
2026-07-09). Реализована ТОЛЬКО Фаза 1 (раздел 15 методики):
  - D  (Диверсификация) — IssuerD + SectorD + CorrD, БЕЗ FactorD (факторные
    экспозиции компаний — Фаза 2, нужен код-маппер + субагент exposure-filler).
  - MR (Рыночный риск) — σ + MDD + VaR95 дневной.
  - L  (Ликвидность) — новый модуль, доля портфеля ликвидируемая ≤1 дня +
    доля в неликвидных бумагах (спред — Фаза 3, нужен стакан).
  - ERR — ТОЛЬКО исторический слой (альфа Дженсена); forward-слой требует
    сценарной библиотеки (Фаза 3) — не считается.
  FQ / V / MGI НЕ реализованы (нужны новые LLM-субагенты quality-scorer и
  exposure-filler + сценарная библиотека — Фаза 2/3, отдельная задача).

Живёт РЯДОМ со старым compute_quality_index (v1, App.js это поле "quality") —
не заменяет его. Возвращает частичный Overall (раздел 15: "Overall
помечается «частичный»", веса перенормированы на доступные модули) с явным
methodology_version и бейджем фазы.

MVP-охват — раздел 12 методики: акции + кэш. Облигации/фьючерсы/фонды пока
НЕ участвуют (не разбавляют — исключены из базы, а не считаются нулём).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Quote
from app.services.portfolio import _lin_score, _clamp01

METHODOLOGY_VERSION = "v2.1-phase1"

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

    # ── D (частично: без FactorD — Фаза 2) ──
    weights_eq = {p["ticker"]: p["value"] for p in equity}
    issuer_score = _lin_score(_n_eff(list(weights_eq.values())), best=8, worst=1)
    sector_score = _lin_score(_sector_n_eff(sector_allocation), best=5, worst=1)
    weighted_corr = _weighted_corr_normalized(correlation, weights_eq)
    corr_score = _lin_score(weighted_corr, best=0.2, worst=0.7)
    D_WEIGHTS = {"issuer": 0.30, "sector": 0.20, "corr": 0.25}
    d_parts = [(k, s) for k, s in (("issuer", issuer_score), ("sector", sector_score), ("corr", corr_score)) if s is not None]
    if d_parts:
        den = sum(D_WEIGHTS[k] for k, _ in d_parts)
        d_score = round(sum(D_WEIGHTS[k] * s for k, s in d_parts) / den)
        subindices.append({
            "key": "diversification_v2", "label": "Диверсификация", "score": d_score,
            "confidence": "факт", "coverage_note": "без факторной концентрации (FactorD) — Фаза 2 методики",
            "components": [
                c for c in [
                    {"name": "Эффективное число эмитентов", "value": f"{_n_eff(list(weights_eq.values())):.1f}" if issuer_score is not None else "—", "score": issuer_score},
                    {"name": "Эффективное число секторов", "value": f"{_sector_n_eff(sector_allocation):.1f}" if sector_score is not None else "—", "score": sector_score},
                    {"name": "Взвешенная корреляция (нормированная)", "value": f"{weighted_corr:.2f}" if weighted_corr is not None else "—", "score": corr_score},
                ] if c["score"] is not None
            ],
            "verdict": (
                "Капитал разложен по разным эмитентам и секторам, бумаги слабо коррелируют."
                if d_score >= 60 else
                "Часть капитала сконцентрирована — в узком круге эмитентов, секторе или бумагах, которые двигаются вместе."
                if d_score >= 40 else
                "Сильная концентрация: узкий круг эмитентов/секторов, высокая взаимная корреляция — просадки придут одновременно."
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

    # ── ERR: только исторический слой (альфа Дженсена к MCFTR) ──
    err_score = _lin_score(alpha, best=6, worst=-6)
    if err_score is not None:
        subindices.append({
            "key": "err_hist_v2", "label": "Доходность к риску (истор.)", "score": err_score,
            "confidence": "оценка",
            "components": [{"name": "Альфа Дженсена (к MCFTR)", "value": f"{alpha:+.1f}%", "score": err_score}],
            "verdict": (
                "Портфель исторически обгонял рынок за свой уровень риска."
                if err_score >= 60 else
                "Портфель шёл примерно вровень с рынком за свой риск."
                if err_score >= 40 else
                "За свой уровень риска портфель отставал от рынка."
            ),
            "limitation": "Только исторический слой (факт прошлого). Форвардная ожидаемая доходность к риску (сценарная премия/потеря) — Фаза 3 методики, не считается.",
        })

    # ── L: ликвидность ──
    liquidity = _compute_liquidity(db, equity, cash_value, total_value)
    if liquidity is not None:
        subindices.append(liquidity)

    if not subindices:
        return None

    # Overall — переразвешено на ДОСТУПНЫЕ Фазе-1 модули (полные веса методики:
    # D 20% / MR 15% / ERR 10% / L 5% = 50% суммы; FQ/V/MGI недоступны — Фаза 2/3)
    OVERALL_WEIGHTS = {"diversification_v2": 0.20, "market_risk_v2": 0.15, "err_hist_v2": 0.10, "liquidity": 0.05}
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
            "Фаза 1 методики v2.1 — частичный индекс: реализованы только рыночные модули "
            "(Диверсификация без факторной концентрации, Рыночный риск, Ликвидность, "
            "Доходность к риску — только исторический слой). Фундаментальное качество компаний, "
            "запас прочности к справедливой цене, сценарная устойчивость и форвардная доходность "
            "к риску требуют новых аналитических субагентов — следующая фаза, пока не реализованы."
        ),
        "note": "Якоря и веса — продуктовое решение (произвол), калибруются после первых прогонов "
                "на реальных портфелях — docs/Basis_методика_индекса_качества_портфеля_v2.1.md.",
    }
