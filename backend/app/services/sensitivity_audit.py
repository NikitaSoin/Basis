"""Независимая проверка коэффициентов чувствительности из карточек.

🔴 ЗАЧЕМ (владелец, 2026-08-02): «чувствительности я бы считал отдельно и где-то это
помечал — в карточках могут быть плохо посчитанные числа с точки зрения методички».

Претензия подтверждается данными: разброс чувствительности к ставке ВНУТРИ сектора
доходит до −57…+17 % (utilities) и −2…+55 % (металлургия). Часть — законная (банк с
дешёвым фондированием против liability-sensitive), часть — явные ошибки карточек.

Что делает модуль: считает ГРУБУЮ независимую оценку из отчётности (баланс + P&L) и
сравнивает с тем, что записано в карточке. Расхождение — не приговор карточке (наша
оценка тоже груба), а ФЛАГ: сюда стоит посмотреть глазами.

🔴 Осознанное ограничение (методичка v3, Часть 0 — агент не вычислитель, а модели
живут в коде): независимая оценка считается ТОЛЬКО там, где механизм прямой и
проверяемый — процентный канал по долгу. Для банков (NIM, стоимость риска) и для
курсовых/сырьевых каналов честной формулы из общей отчётности нет, поэтому там
проверка не делается вовсе, а не делается кое-как: ложный флаг хуже отсутствия флага.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

_RATE_SHOCK_PP = 3.0          # тот же шок, что в карте чувствительности: +300 б.п.
_MISMATCH_FACTOR = 3.0        # расхождение в разы, после которого поднимаем флаг
_UNIT_TO_BLN = {"млрд_руб": 1.0, "млн_руб": 0.001}
# Доля долга, которая реально переоценивается за год (плавающая ставка + рефинансируемая
# часть). Произвол, но осознанный: считать, что вся задолженность мгновенно
# переоценивается по новой ставке, — завышение в разы.
_REPRICING_SHARE = 0.45


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _last(series) -> float | None:
    if isinstance(series, (int, float)):
        return float(series)
    if isinstance(series, list):
        for v in reversed(series):
            if isinstance(v, (int, float)):
                return float(v)
    return None


def independent_rate_sensitivity(ticker: str) -> dict | None:
    """Грубая оценка «ставка +300 б.п. → % годовой прибыли» из отчётности.

    Механизм прямой: рост ставки удорожает обслуживание чистого долга. Считаем
    чистый эффект после налога на переоцениваемую часть долга.
    """
    fin = _load(ticker, "financials.json")
    if not fin:
        return None
    bs = fin.get("balance_sheet") or {}
    pl = fin.get("income_statement") or {}
    net_debt = _last(bs.get("net_debt")) or _last(bs.get("total_financial_debt"))
    profit = _last(pl.get("net_profit"))
    revenue = _last(pl.get("revenue"))
    if net_debt is None or net_debt <= 0:
        return None
    base = profit if (profit and profit > 0) else revenue
    if not base or base <= 0:
        return None
    # эффект до налога → после налога (25% с 2025)
    extra_cost = net_debt * _REPRICING_SHARE * (_RATE_SHOCK_PP / 100.0) * 0.75
    return {"pct": round(-extra_cost / base * 100, 1),
            "base": "прибыли" if (profit and profit > 0) else "выручки",
            "net_debt": round(net_debt)}


def audit_rate_sensitivity(limit: int | None = None) -> list[dict]:
    """Сверка карточка ↔ независимая оценка по процентному каналу.

    Возвращает только СПОРНЫЕ случаи (расхождение в разы или разный знак) — это
    рабочий список «посмотреть глазами», а не отчёт по всем 264.
    """
    if not COMPANIES_DIR.exists():
        return []
    out = []
    for d in sorted(COMPANIES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        ticker = d.name
        macro = _load(ticker, "macro.json")
        if not macro:
            continue
        qi = macro.get("quant_inputs") or {}
        scale = _UNIT_TO_BLN.get(str(qi.get("unit") or "").strip().lower())
        coefs = qi.get("coefficients") or {}
        spec = coefs.get("rate")
        if scale is None or not isinstance(spec, dict):
            continue  # банковский nim и валютные карточки не проверяем — см. докстринг
        delta = spec.get("net_profit")
        fin_q = qi.get("financials") or {}
        card_base = fin_q.get("net_profit") if (fin_q.get("net_profit") or 0) > 0 else fin_q.get("revenue")
        if not isinstance(delta, (int, float)) or not card_base:
            continue
        card_pct = round((delta * scale * _RATE_SHOCK_PP) / (float(card_base) * scale) * 100, 1)
        ind = independent_rate_sensitivity(ticker)
        if not ind:
            continue
        own_pct = ind["pct"]
        verdict = None
        if card_pct > 0 and own_pct < -1:
            verdict = "знак: карточка говорит «выигрывает от роста ставки», а долг говорит обратное"
        elif abs(own_pct) > 1 and abs(card_pct) > 1:
            ratio = abs(card_pct) / abs(own_pct)
            if ratio > _MISMATCH_FACTOR or ratio < 1 / _MISMATCH_FACTOR:
                verdict = f"величина: расхождение в {ratio:.1f} раза"
        elif abs(card_pct) < 0.5 <= abs(own_pct):
            verdict = "карточка почти не видит процентного канала, хотя долг заметный"
        if verdict:
            out.append({"ticker": ticker, "card_pct": card_pct, "independent_pct": own_pct,
                        "net_debt": ind["net_debt"], "base": ind["base"], "issue": verdict})
    out.sort(key=lambda r: -abs(r["card_pct"] - r["independent_pct"]))
    return out[:limit] if limit else out
