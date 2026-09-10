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
from datetime import date
from pathlib import Path
from typing import Any, Callable

from app.services.quality.checks_financials import COMPANIES
from app.services.quality.contract import Check, Status
from app.services.quality.pipelines import get as get_pipeline

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


# ── мутации пайплайна «снапшоты» ──

def m_snap_stale(doc: dict) -> dict:
    """Снапшот протух: отметка времени уехала на полгода назад."""
    from datetime import datetime, timedelta, timezone
    stamp = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat().replace("+00:00", "Z")
    if "fetched_at" in doc:
        doc["fetched_at"] = stamp
    else:
        doc.setdefault("meta", {})["fetched_at"] = stamp
    return doc


def m_snap_no_stamp(doc: dict) -> dict:
    """Отметка времени пропала — возраст измерить нечем."""
    doc.pop("fetched_at", None)
    doc.pop("generated_at", None)
    meta = doc.get("meta")
    if isinstance(meta, dict):
        meta.pop("fetched_at", None)
        meta.pop("generated_at", None)
    return doc


def m_snap_empty(doc: dict) -> dict:
    """Источник ответил кодом 200 и пустотой."""
    for key in ("rows", "series", "indices", "items"):
        if key in doc:
            doc[key] = [] if isinstance(doc[key], list) else {}
    return doc


def m_snap_count_drift(doc: dict) -> dict:
    """Объявлено больше записей, чем лежит в файле."""
    actual = None
    for key in ("rows", "series", "indices", "items"):
        if isinstance(doc.get(key), (list, dict)):
            actual = len(doc[key])
            break
    if actual is not None:
        if "count" in doc:
            doc["count"] = actual + 25
        else:
            doc.setdefault("meta", {})["count"] = actual + 25
    return doc


SNAPSHOT_MUTATIONS: list[MutationCase] = [
    MutationCase("m.snap_stale", "snap.freshness", "отметка времени на полгода назад", m_snap_stale),
    MutationCase("m.snap_nostamp", "snap.has_timestamp", "отметка времени пропала", m_snap_no_stamp),
    MutationCase("m.snap_empty", "snap.not_empty", "источник вернул ноль записей", m_snap_empty),
    MutationCase("m.snap_count", "snap.declared_count", "объявлено на 25 записей больше", m_snap_count_drift),
    # та же поломка, но спрашиваем с другой проверки: заметит ли она отставание
    # от СОСЕДЕЙ по папке, а не превышение собственного порога
    MutationCase("m.snap_lag", "snap.age_spread", "отстал от соседей по папке на полгода", m_snap_stale),
]

def m_tax_gap(card: dict) -> dict:
    """Чистая прибыль разошлась с «до налога + налог» втрое, знак сохранён."""
    ist = card.get("income_statement") or {}
    pt, tx, np_ = ist.get("pre_tax_profit"), ist.get("income_tax"), ist.get("net_profit")
    if not all(isinstance(x, list) for x in (pt, tx, np_)):
        return card
    for i in range(min(len(pt), len(tx), len(np_)) - 1, -1, -1):
        if all(isinstance(x[i], (int, float)) for x in (pt, tx, np_)) and abs(np_[i]) > 1:
            np_[i] = np_[i] * 3
            return card
    return card


def m_flip_net_profit(card: dict) -> dict:
    """Знак чистой прибыли перевёрнут — ровно подпись дефекта Иркута-2022:
    величина сходится с расчётом «до налога + налог», а знак нет."""
    ist = card.get("income_statement") or {}
    pt, tx, np_ = ist.get("pre_tax_profit"), ist.get("income_tax"), ist.get("net_profit")
    if not all(isinstance(x, list) for x in (pt, tx, np_)):
        return card
    for i in range(min(len(pt), len(tx), len(np_)) - 1, -1, -1):
        if all(isinstance(x[i], (int, float)) for x in (pt, tx, np_)) and abs(np_[i]) > 1:
            # ставим ровно расчётную величину с обратным знаком
            best = min((pt[i] + s * tx[i] for s in (1, -1)), key=lambda c: abs(c - np_[i]))
            np_[i] = -best
            return card
    return card


def m_bridge_break(card: dict) -> dict:
    """Отчётная прибыль подтянута из другого источника и больше не сходится
    с мостом нормализации — ровно случай БЛНГ."""
    node = (card.get("income_statement") or {}).get("net_profit")
    years = (card.get("meta") or {}).get("fiscal_years") or []
    bridge = (card.get("adjusted") or {}).get("bridge") or []
    touched = {b.get("year") for b in bridge if isinstance(b, dict) and b.get("added_back")}
    if isinstance(node, list):
        for i, y in enumerate(years):
            if y in touched and isinstance(node[i], (int, float)):
                node[i] = node[i] + max(abs(node[i]) * 3, 5000)
    return card


def m_prose_drift(card: dict) -> dict:
    """Числа карточки уехали от прозы вкладок на 40% — ровно тот стык, на
    котором платформа ломается чаще всего."""
    # Двигаем ВСЕ числовые ряды отчётных блоков, а не три избранных: у банка нет
    # «выручки», у кого-то проза опирается на другие строки — узкая мутация
    # молчала на SBER и GMKN, и виноват был стенд, а не проверка.
    for group in ("income_statement", "balance_sheet", "cash_flow", "bank_pnl",
                  "bank_balance", "bank_metrics"):
        node = card.get(group)
        if not isinstance(node, dict):
            continue
        for key, series in node.items():
            if key.endswith("_note") or not isinstance(series, list):
                continue
            node[key] = [v * 1.4 if isinstance(v, (int, float)) and not isinstance(v, bool)
                         else v for v in series]
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
    MutationCase("m.prose", "fin.cross_tab", "числа уехали от прозы вкладок на 40%", m_prose_drift),
    MutationCase("m.tax_sign", "fin.tax_sign",
                 "чистая прибыль перевёрнута по знаку", m_flip_net_profit),
    MutationCase("m.tax_gap", "fin.tax_identity",
                 "чистая прибыль втрое разошлась с налоговой арифметикой", m_tax_gap),
    MutationCase("m.bridge", "fin.adjusted_bridge",
                 "отчётная прибыль перестала сходиться с мостом", m_bridge_break),
]


MUTATIONS_BY_PIPELINE: dict[str, list[MutationCase]] = {
    "financials": MUTATIONS,
    "snapshots": SNAPSHOT_MUTATIONS,
}


def load_live_cases(pipeline: str) -> list[LiveCase]:
    p = GOLDEN_DIR / f"{pipeline}_live.json"
    if not p.exists():
        return []
    raw = json.loads(p.read_text())
    return [LiveCase(**c) for c in raw.get("cases", [])]


def load_base_subjects(pipeline: str) -> list[str]:
    """Носители мутаций: заведомо чистые субъекты. Одного мало — берём несколько,
    чтобы результат не зависел от особенностей одного файла или компании."""
    p = GOLDEN_DIR / f"{pipeline}_base.json"
    if p.exists():
        raw = json.loads(p.read_text())
        return raw.get("tickers") or raw.get("subjects") or []
    return []


def _check_by_id(pipeline: str, check_id: str) -> Check | None:
    return next((c for c in get_pipeline(pipeline).checks if c.check_id == check_id), None)


def _payload_for(pipeline: str, subject: str, mutated: Any, today: date) -> dict:
    """Готовый payload, где ПОДМЕНЁН основной документ субъекта: карточка для
    финансов, файл снапшота для снапшотов. Остальное берётся у пайплайна."""
    base = get_pipeline(pipeline).payload(subject, today) or {}
    key = "card" if pipeline == "financials" else "doc"
    return {**base, key: mutated}


def _load_subject_doc(pipeline: str, subject: str) -> Any:
    if pipeline == "financials":
        path = COMPANIES / subject / "financials.json"
        return json.loads(path.read_text()) if path.exists() else None
    from app.services.quality.checks_snapshots import load_snapshot
    return load_snapshot(subject)


def run_golden(pipeline: str = "financials", today_year: int | None = None) -> dict[str, Any]:
    """Прогон эталонного набора пайплайна. Возвращает сводку и список провалов."""
    from datetime import date as _date
    today = _date(today_year, _date.today().month, _date.today().day) if today_year else _date.today()
    results: list[dict[str, Any]] = []
    bases = load_base_subjects(pipeline)

    for case in MUTATIONS_BY_PIPELINE.get(pipeline, []):
        check = _check_by_id(pipeline, case.check_id)
        if check is None:
            results.append({"case": case.case_id, "kind": "mutation", "passed": False,
                            "detail": f"проверки {case.check_id} нет в наборе"})
            continue
        detected_on, silent_on, unusable = [], [], {}
        for ticker in bases:
            clean = _load_subject_doc(pipeline, ticker)
            if clean is None:
                unusable[ticker] = "субъект не читается"
                continue
            # 1. на чистой карточке проверка обязана молчать — иначе носитель негоден.
            #    SKIP тоже негоден: проверке нечего смотреть у этой компании
            #    (напр. «выручка против прибыли» у банка), и мутация ничего не докажет.
            before = check.run(ticker, _payload_for(pipeline, ticker, copy.deepcopy(clean), today))
            if any(o.status is Status.FAIL for o in before):
                unusable[ticker] = "уже красная до мутации"
                continue
            if before and all(o.status is Status.SKIP for o in before):
                unusable[ticker] = "проверке нечего смотреть"
                continue
            # 2. на испорченной — обязана сработать
            broken = case.mutate(copy.deepcopy(clean))
            after = check.run(ticker, _payload_for(pipeline, ticker, broken, today))
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

    for case in load_live_cases(pipeline):
        check = _check_by_id(pipeline, case.check_id)
        doc = _load_subject_doc(pipeline, case.ticker)
        if check is None or doc is None:
            results.append({"case": case.case_id, "kind": "live", "passed": False,
                            "detail": "нет проверки или субъекта"})
            continue
        outcomes = check.run(case.ticker, _payload_for(pipeline, case.ticker, doc, today))
        got = "fail" if any(o.status is Status.FAIL for o in outcomes) else (
            "skip" if all(o.status is Status.SKIP for o in outcomes) else "ok")
        results.append({"case": case.case_id, "kind": "live", "check_id": case.check_id,
                        "ticker": case.ticker, "passed": got == case.expect,
                        "detail": f"ожидали {case.expect}, получили {got} ({case.why})"})

    passed = sum(1 for r in results if r["passed"])
    return {"total": len(results), "passed": passed,
            "failed": [r for r in results if not r["passed"]], "results": results}
