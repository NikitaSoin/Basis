"""Сценарий → макро-шоки → показатели конкретных бумаг.

🔴 ЗАЧЕМ (владелец, 2026-08-03): «связку надо довести до конца». Геополитический
барометр даёт сценарии S1-S4 с вероятностями, карточки — чувствительности компаний,
а моста между ними не было: выпуск мог сказать «при эскалации сектор пострадает», но
не «у ЭТОЙ бумаги это −N% годовой прибыли».

Цепочка целиком:
    сценарий барометра  →  сдвиги макропеременных  →  коэффициенты карточки  →
    Δ прибыли компании  →  доля годовой прибыли и доля капитализации

Первое звено — справочник `config/scenario_shocks.json` (допущения с обоснованием,
не прогноз). Второе — `quant_inputs.coefficients` карточек. Третье — арифметика здесь.

🔴 ПОЧЕМУ НЕ ЧЕРЕЗ ФАКТОРНЫЕ БАЛЛЫ. В платформе уже есть движок сценарной реакции на
экспозициях (`factor_engine`), он считает ценовой эффект из баллов 0..1. Он остаётся —
но балл даёт АМПЛИТУДУ, а не величину в деньгах, и покрытие по сырью и курсу там
10-35%. Здесь другой инструмент: рублёвые коэффициенты, которые переводятся в прибыль
и в капитализацию. Два взгляда на одно, а не замена.

🔴 ДВЕ НОРМИРОВКИ, И ПУТАТЬ ИХ НЕЛЬЗЯ.
«% годовой прибыли» отвечает на вопрос «насколько это много для бизнеса» — но у
компании с тонкой маржой любой шок даёт сотни процентов, и в сравнении бумаг такая
шкала бесполезна. «% капитализации» отвечает на вопрос «сколько это стоит для
держателя акции» — именно она сопоставима между компаниями и переводится в ожидаемое
движение цены при неизменном мультипликаторе.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).parent.parent.parent
COMPANIES_DIR = _BACKEND / "companies"
# 🔴 Путь от backend/, НЕ от корня репозитория: корневой config/ не попадает в
# Docker-образ, и конфиг тихо не читается на бою (уже наступали).
_SHOCKS_PATH = _BACKEND / "config" / "scenario_shocks.json"

# Каналы, которые нельзя складывать как независимые удары: у банка эффект ставки уже
# частично сидит в стоимости риска. Совпадает с `macro_sensitivity_map._OVERLAPPING`.
_OVERLAPPING = {("rate", "cost_of_risk"), ("nim", "cost_of_risk")}

# Эффект больше двух годовых прибылей — не чувствительность, а несопоставимость с
# базой. Такие компании из выдачи убираем целиком.
_MAX_PLAUSIBLE_PROFIT_PCT = 200.0
# По капитализации порог жёстче: сдвиг больше половины стоимости компании от одного
# сценария означает ошибку в данных, а не силу эффекта.
_MAX_PLAUSIBLE_CAP_PCT = 50.0

_UNIT_TO_BLN = {"млрд_руб": 1.0, "млн_руб": 0.001, "млрд": 1.0, "млн": 0.001}

# 🔴 Порог капитализации для витрины (найдено на живом прогоне 2026-08-03). Без него
# края распределения занимают микрокапы: у компании стоимостью 3 млрд любой эффект
# даёт десятки процентов стоимости, и список «кого двигает сценарий» выглядит как
# MAGE / RTSBP / TUZA — бумаги, которых частный инвестор в глаза не видел, а их
# коэффициенты в карточках самые грубые. Отсечка не «мнение о качестве компании», а
# требование сопоставимости: ниже неё числитель и знаменатель одинаково шумные.
_MIN_CAP_BLN = 20.0


def load_scenario_shocks() -> dict:
    try:
        return json.loads(_SHOCKS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("scenario_transmission: не читается %s", _SHOCKS_PATH, exc_info=True)
        return {}


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _market_caps(db: Session, unit_scale: dict[str, float]) -> dict[str, float]:
    """Капитализация по тикерам в млрд ₽: живая цена из quotes × число акций.

    Цена — только из `quotes` (правило платформы: rates.csv для цены не источник).
    """
    rows = db.execute(text(
        "WITH last AS (SELECT DISTINCT ON (company_id) company_id, close "
        "              FROM quotes ORDER BY company_id, date DESC) "
        "SELECT c.ticker, last.close FROM companies c "
        "JOIN last ON last.company_id = c.id WHERE last.close > 0"
    )).fetchall()
    caps = {}
    for ticker, close in rows:
        shares = unit_scale.get(ticker)
        if shares:
            caps[ticker] = float(close) * shares / 1e9   # ₽ → млрд ₽
    return caps


def _shares_outstanding() -> dict[str, float]:
    out = {}
    if not COMPANIES_DIR.exists():
        return out
    for d in COMPANIES_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        meta = (_load(d.name, "financials.json") or {}).get("meta") or {}
        shares = meta.get("shares_outstanding")
        if isinstance(shares, (int, float)) and shares > 0:
            out[d.name] = float(shares)
    return out


def company_impact(ticker: str, shocks: dict[str, float],
                   cap_bln: float | None = None) -> dict | None:
    """Эффект набора макро-шоков на одну компанию.

    Возвращает вклад каждого канала и итог — в млрд ₽, в % годовой прибыли и, если
    известна капитализация, в % стоимости компании.
    """
    macro = _load(ticker, "macro.json")
    if not macro:
        return None
    qi = macro.get("quant_inputs") or {}
    coefs = qi.get("coefficients") or {}
    scale = _UNIT_TO_BLN.get(str(qi.get("unit") or "").strip().lower())
    if not coefs or scale is None:
        return None
    fin_q = qi.get("financials") or {}
    profit = fin_q.get("net_profit")
    revenue = fin_q.get("revenue")
    base = profit if isinstance(profit, (int, float)) and profit > 0 else revenue
    if not isinstance(base, (int, float)) or base <= 0:
        return None

    contributions, applied = {}, {}
    for channel, shock in shocks.items():
        if not shock:
            continue
        spec = coefs.get(channel)
        if not isinstance(spec, dict):
            continue
        per_unit = spec.get("net_profit")
        if not isinstance(per_unit, (int, float)):
            continue
        contributions[channel] = per_unit * scale * shock   # млрд ₽
        applied[channel] = shock
    if not contributions:
        return None

    # Пересекающиеся каналы не складываем: берём наибольший по модулю, иначе один и
    # тот же эффект посчитан дважды.
    dropped = []
    for a, b in _OVERLAPPING:
        if a in contributions and b in contributions:
            weaker = a if abs(contributions[a]) < abs(contributions[b]) else b
            dropped.append(weaker)
            contributions.pop(weaker)
    total_bln = sum(contributions.values())
    profit_pct = round(total_bln / (base * scale) * 100, 1)
    if abs(profit_pct) > _MAX_PLAUSIBLE_PROFIT_PCT:
        return None
    out = {
        "ticker": ticker,
        "total_bln": round(total_bln, 2),
        "profit_pct": profit_pct,
        "base": "прибыли" if (isinstance(profit, (int, float)) and profit > 0) else "выручки",
        "by_channel": {k: round(v, 2) for k, v in contributions.items()},
        "shocks_applied": applied,
    }
    if dropped:
        out["dropped_overlapping"] = dropped
    if cap_bln:
        cap_pct = round(total_bln / cap_bln * 100, 1)
        if abs(cap_pct) > _MAX_PLAUSIBLE_CAP_PCT:
            return None
        out["cap_pct"] = cap_pct
    return out


def _dedupe_share_classes(rows: list[dict]) -> list[dict]:
    """Обычка и преф одного эмитента — одна строка, а не две.

    Карточки у пары часто общие, поэтому эффект дублируется и занимает два места в
    топе. Оставляем более ликвидную бумагу (крупнее по капитализации).
    """
    best: dict[str, dict] = {}
    for r in rows:
        # преф отличается суффиксом P при том же корне: SNGS / SNGSP
        root = r["ticker"][:-1] if (r["ticker"].endswith("P")
                                    and len(r["ticker"]) > 4) else r["ticker"]
        kept = best.get(root)
        if not kept or (r.get("cap_bln") or 0) > (kept.get("cap_bln") or 0):
            best[root] = r
    return list(best.values())


def scenario_impacts(db: Session, scenario: str, top_n: int = 15,
                     min_cap_bln: float = _MIN_CAP_BLN) -> dict:
    """Кого и насколько двигает сценарий: победители и проигравшие с числами."""
    conf = load_scenario_shocks()
    spec = ((conf.get("scenarios") or {}).get(scenario)) or {}
    shocks = spec.get("shocks") or {}
    if not shocks or not any(shocks.values()):
        return {"scenario": scenario, "name": spec.get("name"),
                "note": "базовый сценарий — сдвигов нет, это точка отсчёта",
                "shocks": shocks, "winners": [], "losers": []}

    caps = {}
    try:
        caps = _market_caps(db, _shares_outstanding())
    except Exception:  # noqa: BLE001
        logger.warning("scenario_transmission: капитализация недоступна", exc_info=True)

    # Спорные коэффициенты помечаем — те же флаги, что в карте чувствительности.
    try:
        from app.services.sensitivity_audit import audit_sensitivity
        disputed = {(r["ticker"], r["channel"]) for r in audit_sensitivity()
                    if r.get("kind") in ("знак", "величина")}
    except Exception:  # noqa: BLE001
        disputed = set()

    rows = []
    for d in sorted(COMPANIES_DIR.iterdir()) if COMPANIES_DIR.exists() else []:
        if not d.is_dir() or d.name.startswith("."):
            continue
        cap = caps.get(d.name)
        impact = company_impact(d.name, shocks, cap)
        if not impact:
            continue
        if cap:
            impact["cap_bln"] = round(cap)
        flagged = [ch for ch in impact["by_channel"] if (d.name, ch) in disputed]
        if flagged:
            impact["warning"] = ("независимый пересчёт расходится по каналам: "
                                 + ", ".join(flagged))
        rows.append(impact)

    # Сортируем по эффекту на СТОИМОСТЬ там, где она известна: именно эта величина
    # сопоставима между компаниями. Без капитализации — по доле прибыли, но такие
    # строки идут после (их нельзя честно сравнивать с первыми).
    def _key(r):
        return (0, r["cap_pct"]) if "cap_pct" in r else (1, r["profit_pct"])

    liquid = [r for r in rows if "cap_pct" in r and (r.get("cap_bln") or 0) >= min_cap_bln]
    ranked = sorted(_dedupe_share_classes(liquid), key=lambda r: r["cap_pct"])
    return {
        "scenario": scenario,
        "name": spec.get("name"),
        "shocks": shocks,
        "why": spec.get("why"),
        "counted": len(rows),
        "with_cap": len(ranked),
        "min_cap_bln": min_cap_bln,
        "losers": ranked[:top_n],
        "winners": list(reversed(ranked[-top_n:])),
        "_note": "Эффект = сумма вкладов макро-каналов по коэффициентам карточки. "
                 "Доля капитализации — ожидаемое движение стоимости при неизменном "
                 "мультипликаторе, НЕ прогноз цены.",
    }


def scenario_board(db: Session, per_side: int = 5) -> dict:
    """Компактная сводка по всем сценариям — для промпта макро-выпуска.

    Полная выдача `scenario_impacts` для четырёх сценариев не нужна в промпте:
    ценность несут края (кого двигает сильнее всех), а не середина распределения.
    """
    conf = load_scenario_shocks()
    out = {}
    for key in (conf.get("scenarios") or {}):
        try:
            data = scenario_impacts(db, key, top_n=per_side)
        except Exception:  # noqa: BLE001
            logger.warning("scenario_board: сценарий %s не посчитан", key, exc_info=True)
            continue
        if not data.get("winners") and not data.get("losers"):
            continue
        out[key] = {
            "name": data["name"],
            "shocks": data["shocks"],
            "winners": [{"ticker": r["ticker"], "cap_pct": r.get("cap_pct"),
                         "profit_pct": r["profit_pct"],
                         **({"warning": r["warning"]} if r.get("warning") else {})}
                        for r in data["winners"]],
            "losers": [{"ticker": r["ticker"], "cap_pct": r.get("cap_pct"),
                        "profit_pct": r["profit_pct"],
                        **({"warning": r["warning"]} if r.get("warning") else {})}
                       for r in data["losers"]],
        }
    if not out:
        return {}
    return {
        "_note": "Кого двигает сценарий: суммарный эффект макро-сдвигов сценария через "
                 "коэффициенты чувствительности карточек. cap_pct — доля капитализации "
                 "(сопоставима между компаниями), profit_pct — доля годовой прибыли. "
                 "Это РАСЧЁТ ПЛАТФОРМЫ по допущениям из config/scenario_shocks.json, "
                 "не прогноз цены: ссылайся как на оценку, а не как на факт.",
        "base_scenario": conf.get("base_scenario"),
        "scenarios": out,
    }
