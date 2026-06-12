#!/usr/bin/env python3
"""
Детектор устаревших/неполных финансовых данных карточек → очередь обновления.

ВАЖНО ПРО АРХИТЕКТУРУ (почему это НЕ авто-запуск добытчика):
report-fetcher и financial-analyst — это AI-субагенты (LLM), а не скрипты. Серверный
cron / start.sh не может «запустить добытчика» — для этого нужна сессия Claude с
доступом к субагентам. Поэтому автоматизируемая часть триггера — ДЕТЕКЦИЯ: этот скрипт
идемпотентно сканирует companies/*/financials.json и пишет companies/_refresh_queue.json
с приоритизированным списком «что обновить». Сам шаг добычи/дозаполнения выполняет
оператор в сессии, читая очередь (report-fetcher → financial-analyst по тикерам).

Критерии устаревания (компания попадает в очередь, если выполнен ЛЮБОЙ):
  - data_quality == "low";
  - последний фискальный год < (текущий год − 1)  → отчётность старше ~12 мес;
  - неполные постатейные данные: у НЕ-банка пусты cogs И cfi (нет добытых статей),
    у банка пусты процентные доходы брутто (bank_pnl) → кандидат на report-fetcher;
  - нет блока valuation.methods с explain (старый формат, не пересчитан по v2).

Запуск: python -m scripts.refresh_financials   (из backend/)
Идемпотентно: повторный запуск просто перезаписывает очередь.
"""
import json
import os
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANIES = os.path.join(BASE, "companies")
OUT = os.path.join(COMPANIES, "_refresh_queue.json")
CUR_YEAR = datetime.now(timezone.utc).year


def _nonempty(a):
    return isinstance(a, list) and any(x is not None for x in a)


def _has_extracted(ticker):
    return os.path.exists(os.path.join(COMPANIES, ticker, "sources", "extracted_financials.json"))


def assess(ticker, fin):
    meta = fin.get("meta", {}) or {}
    reasons = []

    dq = (meta.get("data_quality") or "").lower()
    if dq == "low":
        reasons.append("data_quality=low")

    fy = meta.get("fiscal_years") or []
    last_fy = max([y for y in fy if isinstance(y, int)], default=None)
    if last_fy is not None and last_fy < CUR_YEAR - 1:
        reasons.append(f"отчётность устарела (последний год {last_fy} < {CUR_YEAR - 1})")

    is_bank = (meta.get("profile") == "bank")
    if is_bank:
        bp = fin.get("bank_pnl", {}) or {}
        # признак неполноты — нет брутто процентных доходов
        if not any(_nonempty(bp.get(k)) for k in ("interest_income", "total_interest_income", "interest_income_eir")):
            reasons.append("банк: нет постатейного bank_pnl (кандидат на report-fetcher)")
    else:
        is_ = fin.get("income_statement", {}) or {}
        cf = fin.get("cash_flow", {}) or {}
        if not _nonempty(is_.get("cogs")) and not _nonempty(cf.get("cfi")):
            reasons.append("неполные статьи (cogs/cfi пусты) — кандидат на report-fetcher")

    methods = (fin.get("valuation", {}) or {}).get("methods", []) or []
    if not methods or not any(m.get("explain") for m in methods):
        reasons.append("нет valuation.explain (старый формат, не пересчитан по v2)")

    return reasons


def main():
    items = []
    total = 0
    for ticker in sorted(os.listdir(COMPANIES)):
        cdir = os.path.join(COMPANIES, ticker)
        fpath = os.path.join(cdir, "financials.json")
        if not os.path.isdir(cdir) or not os.path.isfile(fpath):
            continue
        total += 1
        try:
            with open(fpath, encoding="utf-8") as f:
                fin = json.load(f)
        except Exception as e:
            items.append({"ticker": ticker, "reasons": [f"financials.json не читается: {e}"],
                          "has_extracted": _has_extracted(ticker)})
            continue
        reasons = assess(ticker, fin)
        if reasons:
            items.append({"ticker": ticker, "reasons": reasons,
                          "has_extracted": _has_extracted(ticker)})

    # приоритет: сначала те, у кого нет extracted (нужен добытчик), потом по числу причин
    items.sort(key=lambda it: (it.get("has_extracted", False), -len(it["reasons"]), it["ticker"]))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_year": CUR_YEAR,
        "criteria": "data_quality=low | отчётность>12мес | неполные статьи | нет v2-explain",
        "note": "Очередь обновления. Добыча выполняется в сессии Claude: "
                "report-fetcher <TICKER> → financial-analyst <TICKER>. Cron не запускает "
                "субагентов (LLM). Сначала тикеры без has_extracted.",
        "total_companies": total,
        "stale_count": len(items),
        "items": items,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[refresh_financials] просканировано {total}, в очереди {len(items)} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
