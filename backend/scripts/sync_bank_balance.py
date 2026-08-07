#!/usr/bin/env python3
"""Синхронизация банковского баланса: bank_balance → balance_sheet.

🔴 ЗАЧЕМ. В карточках банков живут ДВА блока баланса — `bank_balance` и
`balance_sheet`. Вкладка «Финансы» (frontend/Basis/src/company/FinanceTab.jsx:383)
читает ТОЛЬКО `balance_sheet`; `bank_balance` не читает никто. Данные при этом
добывались в оба, и у девяти банков видимый блок оказался БЕДНЕЕ скрытого — до
24 значений на карточку просто не доезжали до экрана. Именно это владелец увидел
в карточке Т-Технологий как «по балансу мало что заполнено».

Правила:
  1. Совмещение ПО ГОДАМ (fiscal_years карточки), а не по индексу.
  2. По умолчанию заполняются только дыры; существующее не перетирается,
     расхождения печатаются как конфликт.
  3. --force TICKER — для карточек, где ряды в bank_balance выверены по
     первоисточнику и должны заменить старые (у Т так исправлены кредитный
     портфель и резервы).
  4. Имена строк приводятся к тем, что читает фронт (gross_loans/net_loans/…).

Запуск: python3 backend/scripts/sync_bank_balance.py [TICKER ...] [--apply] [--force]
Без тикеров — все банки. Без --apply — сухой прогон.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPANIES = ROOT / "backend" / "companies"

# слева — имя, которое читает FinanceTab; справа — синонимы в bank_balance
FRONT = {
    "gross_loans": ["gross_loans", "loans_gross", "loans_to_customers_gross"],
    "net_loans": ["net_loans", "loans_net"],
    "loan_provisions": ["loan_provisions", "loans_impairment_reserve"],
    "securities": ["securities", "investment_securities"],
    "customer_deposits": ["customer_deposits", "deposits"],
    "deposits_retail": ["deposits_retail"],
    "deposits_corporate": ["deposits_corporate"],
    "loans_corporate": ["loans_corporate"],
    "loans_retail": ["loans_retail"],
    "due_to_banks": ["due_to_banks", "due_to_cbanks_and_credit_orgs"],
    "due_from_banks": ["due_from_banks", "interbank_funds"],
    "cash_and_equivalents": ["cash_and_equivalents", "cash_and_cb", "cash"],
    "ppe_intangibles": ["ppe_intangibles"],
    "other_assets": ["other_assets"],
    "debt_securities_issued": ["debt_securities_issued", "issued_bills"],
    "subordinated_debt": ["subordinated_debt", "subordinated_debt_as_equity"],
    "other_liabilities": ["other_liabilities"],
    "total_assets": ["total_assets"],
    "total_liabilities": ["total_liabilities"],
    "total_equity": ["total_equity"],
    "share_capital_and_premium": ["share_capital_and_premium", "share_capital"],
    "retained_earnings": ["retained_earnings"],
}


def pick(section, names):
    for nm in names:
        v = section.get(nm)
        if isinstance(v, list) and any(x is not None for x in v):
            return nm, v
    return None, None


def sync(ticker, apply, force):
    path = COMPANIES / ticker / "financials.json"
    card = json.loads(path.read_text())
    if not (card.get("bank_pnl") or card.get("bank_balance")):
        return 0, 0
    src = card.get("bank_balance") or {}
    if not src:
        return 0, 0
    dst = card.setdefault("balance_sheet", {})
    years = (card.get("meta") or {}).get("fiscal_years") or src.get("years") or []
    n = len(years)
    written = conflicts = 0

    for front_name, names in FRONT.items():
        s_name, s_vals = pick(src, names)
        if s_vals is None:
            continue
        d_vals = dst.get(front_name)
        cur = list(d_vals) if isinstance(d_vals, list) else [None] * n
        if len(cur) < n:
            cur += [None] * (n - len(cur))
        for i in range(min(n, len(s_vals))):
            new, old = s_vals[i], cur[i]
            if new is None:
                continue
            if old is None:
                cur[i] = new
                written += 1
            elif abs(float(old) - float(new)) > max(abs(float(old)) * 0.005, 1):
                if force:
                    cur[i] = new
                    written += 1
                    print(f"  {ticker} {front_name}[{years[i]}]: {old} → {new} (force)")
                else:
                    conflicts += 1
                    print(f"  ⚠ {ticker} {front_name}[{years[i]}]: видно {old}, выверено {new} — оставил")
        dst[front_name] = cur
        note = src.get(f"{s_name}_note") or src.get(f"{front_name}_note")
        if note:
            dst[f"{front_name}_note"] = note

    if apply and (written or conflicts == 0):
        path.write_text(json.dumps(card, ensure_ascii=False, indent=2))
    return written, conflicts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    force = "--force" in sys.argv
    tickers = args or sorted(
        p.parent.name for p in COMPANIES.glob("*/financials.json")
        if (lambda d: d.get("bank_pnl") or d.get("bank_balance"))(json.loads(p.read_text()))
    )
    tw = tc = 0
    for t in tickers:
        w, c = sync(t, apply, force)
        if w or c:
            print(f"{t}: перенесено {w}, конфликтов {c}")
        tw += w
        tc += c
    print(f"\nитого: перенесено {tw}, конфликтов {tc}" + ("" if apply else "  (сухой прогон)"))


if __name__ == "__main__":
    main()
