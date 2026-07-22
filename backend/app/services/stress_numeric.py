"""Числовой контур «Стресс-тестирования» v2 (владелец, 2026-07-17: «+2% у акций
— это вообще про что?» — справедливо, у качественного контура не было семантики).

ЗДЕСЬ семантика ЖЁСТКАЯ и определённая:
    Пользователь задаёт целевые макро-условия (ставка X%, курс ₽Y/$, нефть $Z).
    Для каждой компании считаем Δ = coefficient × (цель − спот) по КАЖДОЙ метрике
    (выручка / EBITDA / чистая прибыль) — в млрд ₽ и в % от базы последнего
    отчётного года. Читается как: «если в среднем за год ставка будет X вместо
    текущих ~14,25 — чистая прибыль компании ориентировочно изменится на N млрд ₽
    (±M% от базы года)».

Источник коэффициентов — `macro.json → quant_inputs.coefficients` каждой компании:
их положил аналитик (Opus) с явными допущениями (поле assumption), арифметику
считает код — ровно та же философия, что в macro_quant.py («модель ненадёжна в
арифметике, числа складывает код»). НИЧЕГО не выдумываем: нет коэффициента по
фактору — компания не участвует в этом факторе (честная деградация, видна как
прочерк, а не ноль).

Нефть: ввод — Brent $/барр. У каждой нефтяной компании свой commodity-ориентир
(обычно Urals с санкционным дисконтом, у Полюса — золото, у Русала — алюминий и
т.п.), поэтому нефтяной шок применяем ТОЛЬКО к сектору «Нефть и газ» и
ОТНОСИТЕЛЬНО: Δcommodity_компании = spot_commodity_компании × (Brent_цель/Brent_спот − 1)
— Urals исторически ходит с Brent почти 1:1 по относительным изменениям
(дисконт меняется медленнее уровня). Для остальных секторов нефтяной ввод
не трогает их commodity-фактор (иначе повторим пойманный 2026-07-17 баг,
когда «обвал нефти» бил по золотодобытчикам).

ДЕМО-ОГОВОРКА наследуется: коэффициенты линейные (реальность нелинейна — демпфер,
прогрессивный НДПИ, хеджи), «полный перенос среднегодового уровня» — сильное
упрощение; см. assumption у каждого коэффициента — показываем его в UI.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Голубые фишки — тот же список, что в скринере (single source, копия осознанно:
# screener_scoring тянет тяжёлые зависимости, а нам нужен только set тикеров).
from app.services.screener_scoring import BLUE_CHIPS  # noqa: E402

_OIL_SECTOR_TOKENS = ("нефт", "газ", "oil", "gas")
_METRICS = ("revenue", "ebitda", "net_profit")
_METRIC_LABELS = {"revenue": "Выручка", "ebitda": "EBITDA", "net_profit": "Чистая прибыль"}


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _load_quant(ticker: str) -> dict | None:
    path = COMPANIES_DIR / ticker.upper() / "macro.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d.get("quant_inputs") or None
    except Exception:  # noqa: BLE001
        return None


def _company_numeric_impact(qi: dict, sector: str | None,
                            key_rate_pct: float | None,
                            fx_usdrub: float | None,
                            oil_brent_usd: float | None,
                            brent_spot: float | None) -> dict | None:
    """Δ метрик компании (млрд ₽ и % от базы) при целевых условиях. None — нет
    quant_inputs вовсе. Внутри метрик None — фактор/база не покрыты."""
    coefs = qi.get("coefficients") or {}
    spot = qi.get("macro_spot") or qi.get("macro_current") or {}
    fin = qi.get("financials") or {}
    sector_l = (sector or "").lower()

    # Δ по каждому задействованному фактору в ЕДИНИЦАХ коэффициента
    factor_deltas: dict[str, float] = {}
    applied: list[dict] = []

    if key_rate_pct is not None and _num(spot.get("key_rate_pct")) is not None and "rate" in coefs:
        d = key_rate_pct - float(spot["key_rate_pct"])
        if abs(d) > 1e-9:
            factor_deltas["rate"] = d
            applied.append({"factor": "rate", "label": "Ключевая ставка",
                            "from": float(spot["key_rate_pct"]), "to": key_rate_pct,
                            "assumption": (coefs["rate"] or {}).get("assumption")})

    if fx_usdrub is not None and _num(spot.get("fx_usdrub")) is not None and "fx" in coefs:
        d = fx_usdrub - float(spot["fx_usdrub"])
        if abs(d) > 1e-9:
            factor_deltas["fx"] = d
            applied.append({"factor": "fx", "label": "Курс USD/RUB",
                            "from": float(spot["fx_usdrub"]), "to": fx_usdrub,
                            "assumption": (coefs["fx"] or {}).get("assumption")})

    if (oil_brent_usd is not None and brent_spot and
            any(t in sector_l for t in _OIL_SECTOR_TOKENS) and
            _num(spot.get("commodity_usd")) is not None and "commodity" in coefs):
        rel = oil_brent_usd / brent_spot - 1.0
        d = float(spot["commodity_usd"]) * rel
        if abs(d) > 1e-9:
            factor_deltas["commodity"] = d
            applied.append({"factor": "commodity", "label": "Цена нефти (относительно, через сырьё компании)",
                            "from": round(float(spot["commodity_usd"]), 1),
                            "to": round(float(spot["commodity_usd"]) * (1 + rel), 1),
                            "assumption": (coefs["commodity"] or {}).get("assumption")})

    if not factor_deltas:
        return None

    out_metrics: dict[str, dict] = {}
    for m in _METRICS:
        total = 0.0
        covered = False
        for f, d in factor_deltas.items():
            c = _num((coefs.get(f) or {}).get(m))
            if c is None:
                continue
            covered = True
            total += c * d
        base = _num(fin.get(m))
        if not covered:
            out_metrics[m] = {"delta_bn": None, "pct_of_base": None, "base_bn": base}
            continue
        # % от базы вырожден при крошечной базе (у OZON прибыль ~1 млрд → «+543%»
        # ничего не говорит) — показываем % только когда |Δ| ≤ 2×|базы|, иначе
        # только млрд ₽ (число всё равно честное, некорректен только процент).
        pct = None
        if base and abs(total) <= 2 * abs(base):
            pct = round(total / abs(base) * 100, 1)
        out_metrics[m] = {"delta_bn": round(total, 1), "pct_of_base": pct, "base_bn": base}

    return {"metrics": out_metrics, "applied_factors": applied,
            "fiscal_year": (fin.get("fiscal_year") if isinstance(fin.get("fiscal_year"), str) else None)}


def numeric_impact(db: Session, key_rate_pct: float | None, fx_usdrub: float | None,
                   oil_brent_usd: float | None) -> dict:
    """По всей вселенной компаний. Сортировка: голубые фишки первыми (владелец),
    внутри группы — по |Δ чистой прибыли в % от базы|."""
    # спот Brent — живой ближний фьючерс (тот же источник, что market/drivers)
    brent_spot = None
    row = db.execute(text(
        "SELECT last_price FROM futures WHERE (asset_code ILIKE 'BR%' OR secid ILIKE 'BR%') "
        "AND last_price IS NOT NULL AND expiration_date >= now()::date "
        "ORDER BY expiration_date ASC LIMIT 1")).first()
    if row and row[0]:
        brent_spot = float(row[0])

    rows = db.execute(text("""
        SELECT c.ticker, c.name, c.sector FROM companies c
        JOIN company_metrics m ON m.ticker = c.ticker
    """)).fetchall()

    companies = []
    for r in rows:
        ticker, name, sector = r[0], r[1], r[2]
        qi = _load_quant(ticker)
        if not qi:
            continue
        impact = _company_numeric_impact(qi, sector, key_rate_pct, fx_usdrub, oil_brent_usd, brent_spot)
        if not impact:
            continue
        np_metric = impact["metrics"].get("net_profit") or {}
        np_pct, np_bn = np_metric.get("pct_of_base"), np_metric.get("delta_bn")
        if np_pct is not None:
            sort_key = abs(np_pct)
        elif np_bn is not None:
            # % подавлен НЕ потому что эффекта нет, а потому что эффект БОЛЬШЕ базы —
            # экстремальный случай, ранжируем его высоко, а не последним (было -1, из-за
            # чего компания с крупнейшим |Δ млрд ₽| (напр. Роснефть в сценарии «нефть $45»)
            # уходила в конец списка голубых фишек — прямая причина «непонятно кто
            # пострадал больше»).
            sort_key = 999 + abs(np_bn)
        else:
            sort_key = -1
        companies.append({
            "ticker": ticker, "name": name, "sector": sector,
            "is_blue_chip": ticker in BLUE_CHIPS,
            **impact,
            "_sort": sort_key,
        })

    companies.sort(key=lambda c: (not c["is_blue_chip"], -c["_sort"]))
    for c in companies:
        del c["_sort"]

    return {
        "companies": companies,
        "reference": {"brent_spot_usd": brent_spot},
        "inputs": {"key_rate_pct": key_rate_pct, "fx_usdrub": fx_usdrub, "oil_brent_usd": oil_brent_usd},
        "semantics": (
            "Δ — оценка изменения ГОДОВОЙ метрики (к базе последнего отчётного года) при условии, "
            "что заданные уровни станут СРЕДНИМИ за год, при линейном переносе по коэффициентам "
            "чувствительности из макро-разбора компании (свои у каждой компании, с допущениями). "
            "Спот-ориентиры (от чего считается Δ) у каждой компании свои — из её карточки. "
            "Не прогноз цены акции и не таргет — иллюстрация чувствительности финансовых показателей."
        ),
        "is_demo": True,
    }
