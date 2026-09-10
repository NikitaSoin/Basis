"""Эталонный набор пайплайна «Финансы».

Две разные вещи под одной крышей:

  mutation — берём заведомо чистую карточку, вносим В ПАМЯТИ известный дефект и
             требуем, чтобы сработала КОНКРЕТНАЯ проверка. Доказывает, что
             детектор жив. Не циркулярно: проверка не соглашается сама с собой,
             а обязана заметить искусственную поломку.
  live     — реальный тикер с вручную подтверждённым вердиктом. Доказывает, что
             верны данные (а не только детектор).

🔴 Мутационные кейсы — не украшение. Именно они отвечают на вопрос «а работает
ли ревизор вообще», который в проекте уже был решён неправильно (проверка
успешно возвращала checked: 0).
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.services.quality.checks_financials import CHECKS, COMPANIES
from app.services.quality.contract import Check, Status

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "backend" / "quality" / "golden"


@dataclass
class MutationCase:
    case_id: str
    check_id: str                     # какая проверка ОБЯЗАНА сработать
    title: str                        # что именно ломаем
    mutate: Callable[[dict], dict]    # карточка -> испорченная карточка


@dataclass
class LiveCase:
    case_id: str
    ticker: str
    check_id: str
    expect: str                       # 'ok' | 'fail'
    why: str                          # чем подтверждён вердикт


# ─────────────────── мутации: по одной на каждый дефект ───────────────────

def _last_filled(node: Any) -> int | None:
    """Индекс последнего ЗАПОЛНЕННОГО года ряда.

    🔴 Ломать данные надо там, где они есть. Первая версия портила строго
    последний год — а у части карточек он пустой, мутация не меняла ничего, и
    эталонный набор винил в этом детектор (MTSS «пропустил» несломанный баланс)."""
    if not isinstance(node, list):
        return None
    for i in range(len(node) - 1, -1, -1):
        if isinstance(node[i], (int, float)) and not isinstance(node[i], bool):
            return i
    return None


def _bump(card: dict, group: str, key: str, factor: float) -> dict:
    node = (card.get(group) or {}).get(key)
    i = _last_filled(node)
    if i is not None:
        node[i] = node[i] * factor
    return card


def m_balance(card: dict) -> dict:
    """Баланс перестаёт сходиться: капитал разошёлся на 2% валюты баланса.

    🔴 Мутация меряется в тех же единицах, что и проверка. Первая версия
    прибавляла 20% К КАПИТАЛУ — у МТС капитал около 1% активов, и такая порча
    укладывалась в допуск 0,3% от валюты баланса: детектор был прав, негодной
    была мутация."""
    bs = card.get("balance_sheet") or {}
    ta, tl, te = bs.get("total_assets"), bs.get("total_liabilities"), bs.get("total_equity")
    if not all(isinstance(x, list) for x in (ta, tl, te)):
        return card
    for i in range(min(len(ta), len(tl), len(te)) - 1, -1, -1):
        if all(isinstance(x[i], (int, float)) for x in (ta, tl, te)) and ta[i]:
            te[i] = te[i] + abs(ta[i]) * 0.02
            return card
    return card


def m_scale_x1000(card: dict) -> dict:
    """Классика: одна ячейка вписана в других единицах."""
    return _bump(card, "balance_sheet", "total_assets", 1000.0)


def m_copied_year(card: dict) -> dict:
    """Скопированная история: последний год повторяет позапрошлый."""
    for group in ("income_statement", "balance_sheet"):
        for key, node in (card.get(group) or {}).items():
            if isinstance(node, list) and len(node) >= 3 and isinstance(node[-3], (int, float)):
                node[-1] = node[-3]
    return card


def m_profit_over_revenue(card: dict) -> dict:
    """Прибыль отдана в млрд там, где карточка в млн."""
    return _bump(card, "income_statement", "net_profit", 1000.0)


def m_source_drift(card: dict) -> dict:
    """Витрина разъехалась с первичкой на 30%."""
    return _bump(card, "income_statement", "revenue", 1.3)


def m_alien_source(card: dict) -> dict:
    """В источники попал документ чужого эмитента."""
    meta = card.setdefault("meta", {})
    src = meta.setdefault("source", {})
    src.setdefault("supplementary_docs", []).append(
        {"type": "company_ir",
         "doc_title": "Консолидированная финансовая отчётность ПАО «РуссНефть» по МСФО за 2025 год",
         "url": "https://example.org/russneft-msfo-2025.pdf"})
    return card


def m_stale(card: dict) -> dict:
    """Карточка отстала на два года."""
    meta = card.setdefault("meta", {})
    years = meta.get("fiscal_years") or []
    meta["fiscal_years"] = [y - 3 for y in years]
    return card


def m_returns_as_fraction(card: dict) -> dict:
    """Рентабельности записаны в долях вместо процентов."""
    returns = card.setdefault("returns", {})
    for key in ("roe", "roa", "ros"):
        node = returns.get(key)
        if isinstance(node, list):
            returns[key] = [v / 100.0 if isinstance(v, (int, float)) else v for v in node]
    return card


MUTATIONS: list[MutationCase] = [
    MutationCase("m.balance", "fin.arithmetic", "капитал +2% валюты баланса — не сходится", m_balance),
    MutationCase("m.scale", "fin.arithmetic", "активы ×1000 — разъехались единицы", m_scale_x1000),
    MutationCase("m.copy", "fin.arithmetic", "последний год скопирован с позапрошлого", m_copied_year),
    MutationCase("m.profit", "fin.profit_vs_revenue", "прибыль ×1000 — масштаб строки", m_profit_over_revenue),
    MutationCase("m.source", "fin.source_match", "выручка +30% против первички", m_source_drift),
    MutationCase("m.alien", "fin.source_issuer", "документ чужого эмитента в источниках", m_alien_source),
    MutationCase("m.stale", "fin.freshness", "отчётность отстала на 3 года", m_stale),
    MutationCase("m.units", "fin.return_units", "рентабельности в долях", m_returns_as_fraction),
]


def load_live_cases() -> list[LiveCase]:
    p = GOLDEN_DIR / "financials_live.json"
    if not p.exists():
        return []
    raw = json.loads(p.read_text())
    return [LiveCase(**c) for c in raw.get("cases", [])]


def load_base_tickers() -> list[str]:
    """Тикеры-носители мутаций: заведомо чистые карточки, по одной на мутацию мало —
    берём несколько, чтобы результат не зависел от особенностей одной компании."""
    p = GOLDEN_DIR / "financials_base.json"
    if p.exists():
        return json.loads(p.read_text()).get("tickers", [])
    return []


def _check_by_id(check_id: str) -> Check | None:
    return next((c for c in CHECKS if c.check_id == check_id), None)


def _payload_for(ticker: str, card: dict, today_year: int) -> dict:
    from app.services.quality.checks_financials import _load_extracted
    return {"card": card, "extracted": _load_extracted(ticker), "today_year": today_year}


def run_golden(today_year: int) -> dict[str, Any]:
    """Прогон эталонного набора. Возвращает сводку и список провалов."""
    results: list[dict[str, Any]] = []
    bases = load_base_tickers()

    for case in MUTATIONS:
        check = _check_by_id(case.check_id)
        if check is None:
            results.append({"case": case.case_id, "kind": "mutation", "passed": False,
                            "detail": f"проверки {case.check_id} нет в наборе"})
            continue
        detected_on, silent_on, unusable = [], [], {}
        for ticker in bases:
            path = COMPANIES / ticker / "financials.json"
            if not path.exists():
                unusable[ticker] = "нет карточки"
                continue
            clean = json.loads(path.read_text())
            # 1. на чистой карточке проверка обязана молчать — иначе носитель негоден.
            #    SKIP тоже негоден: проверке нечего смотреть у этой компании
            #    (напр. «выручка против прибыли» у банка), и мутация ничего не докажет.
            before = check.run(ticker, _payload_for(ticker, copy.deepcopy(clean), today_year))
            if any(o.status is Status.FAIL for o in before):
                unusable[ticker] = "уже красная до мутации"
                continue
            if before and all(o.status is Status.SKIP for o in before):
                unusable[ticker] = "проверке нечего смотреть"
                continue
            # 2. на испорченной — обязана сработать
            broken = case.mutate(copy.deepcopy(clean))
            after = check.run(ticker, _payload_for(ticker, broken, today_year))
            (detected_on if any(o.status is Status.FAIL for o in after) else silent_on).append(ticker)
        usable = len(detected_on) + len(silent_on)
        results.append({
            "case": case.case_id, "kind": "mutation", "check_id": case.check_id,
            "title": case.title,
            "passed": usable > 0 and not silent_on,
            "detail": (f"поймано на {len(detected_on)}/{usable}"
                       + (f", ПРОПУЩЕНО у {', '.join(silent_on)}" if silent_on else "")
                       + (f"; вне игры: {', '.join(f'{t} ({w})' for t, w in unusable.items())}"
                          if unusable else "")),
            "usable": usable,
        })

    for case in load_live_cases():
        check = _check_by_id(case.check_id)
        path = COMPANIES / case.ticker / "financials.json"
        if check is None or not path.exists():
            results.append({"case": case.case_id, "kind": "live", "passed": False,
                            "detail": "нет проверки или карточки"})
            continue
        card = json.loads(path.read_text())
        outcomes = check.run(case.ticker, _payload_for(case.ticker, card, today_year))
        got = "fail" if any(o.status is Status.FAIL for o in outcomes) else (
            "skip" if all(o.status is Status.SKIP for o in outcomes) else "ok")
        results.append({"case": case.case_id, "kind": "live", "check_id": case.check_id,
                        "ticker": case.ticker, "passed": got == case.expect,
                        "detail": f"ожидали {case.expect}, получили {got} ({case.why})"})

    passed = sum(1 for r in results if r["passed"])
    return {"total": len(results), "passed": passed,
            "failed": [r for r in results if not r["passed"]], "results": results}
