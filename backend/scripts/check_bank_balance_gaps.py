#!/usr/bin/env python3
"""Проверка полноты банковских балансов: сколько ячеек «строка × год» пусто.

Мерит ровно то, что видит пользователь — блок `balance_sheet`, который читает
вкладка «Финансы» (FinanceTab.jsx). Это принципиально: данные в карточках лежат
и в `bank_balance`, но фронт его не показывает, и первая версия этой проверки
именно из-за подмены поля дала неверную картину.

Чем «пропуск» отличается от «неприменимо»:
  • у микрофинансовых компаний (Кармани, Займер) нет вкладов клиентов и портфеля
    ценных бумаг как класса — пустая строка тут свойство бизнеса;
  • у банков, публикующих «обобщённую» отчётность без примечаний (Кузнецкий,
    МКБ за 2020-2022), не раскрывается разбивка на валовые кредиты и резерв —
    льгота ЦБ, действует с 2022 года.
Такие случаи помечены в карточке (`data_flags.not_applicable_rows`,
`meta.disclosure_note`) и считаются отдельно, чтобы «ноль пропусков» означал
«всё, что раскрыто, — на месте», а не «мы дорисовали недостающее».

Запуск: python3 backend/scripts/check_bank_balance_gaps.py [--verbose]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

ROWS = ["gross_loans", "loan_provisions", "net_loans", "securities", "customer_deposits",
        "due_to_banks", "cash_and_equivalents", "total_assets", "total_liabilities", "total_equity"]

# строки, которых у эмитента нет по природе бизнеса или из-за режима раскрытия
NOT_APPLICABLE = {
    "CARM": {"securities": "все", "customer_deposits": "все"},      # МФО: нет вкладов и портфеля ЦБ
    "ZAYM": {"securities": [2022, 2023], "customer_deposits": [2022, 2023]},
    "KUZB": {"gross_loans": "все", "loan_provisions": "все"},       # публикуемая форма без примечаний
    "CBOM": {"gross_loans": [2020, 2021, 2022], "loan_provisions": [2020, 2021, 2022]},
    "MBNK": {"gross_loans": [2020, 2021, 2022, 2023], "loan_provisions": [2020, 2021, 2022, 2023]},
}


def main():
    verbose = "--verbose" in sys.argv
    total_gap = total_na = 0
    rows = []
    for path in sorted(COMPANIES.glob("*/financials.json")):
        card = json.loads(path.read_text())
        if not (card.get("bank_pnl") or card.get("bank_balance")):
            continue
        ticker = path.parent.name
        bs = card.get("balance_sheet") or {}
        years = (card.get("meta") or {}).get("fiscal_years") or []
        na_map = NOT_APPLICABLE.get(ticker, {})
        gaps, na, details = 0, 0, []
        for row in ROWS:
            vals = bs.get(row) if isinstance(bs.get(row), list) else []
            vals = list(vals) + [None] * (len(years) - len(vals))
            rule = na_map.get(row)
            for i, year in enumerate(years):
                if vals[i] is not None:
                    continue
                if rule == "все" or (isinstance(rule, list) and year in rule):
                    na += 1
                else:
                    gaps += 1
                    details.append(f"{row}[{year}]")
        total_gap += gaps
        total_na += na
        rows.append((gaps, na, ticker, len(ROWS) * len(years), details))

    rows.sort(reverse=True)
    print(f"{'тикер':8}{'пропуски':>10}{'неприменимо':>13}{'ячеек':>8}")
    for gaps, na, ticker, cells, details in rows:
        mark = "" if gaps else "  ✓"
        print(f"{ticker:8}{gaps:>10}{na:>13}{cells:>8}{mark}")
        if verbose and details:
            print("          " + ", ".join(details[:12]) + (" …" if len(details) > 12 else ""))
    print(f"\nИТОГО: пропусков {total_gap}, неприменимо (объяснено на карточке) {total_na}")
    return 0 if total_gap == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
