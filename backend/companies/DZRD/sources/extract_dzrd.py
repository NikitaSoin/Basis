#!/usr/bin/env python3
"""
DZRD Financial Data Extractor
============================
Assembles IFRS (МСФО) data fragments from web sources.
Full РСБУ not available in open internet; marks as incomplete.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

def validate_arithmetic(block: Dict[str, Any], block_name: str) -> bool:
    """
    Validate basic arithmetic in a financial block.
    Returns True if checks pass (or insufficient data).
    """
    errors = []

    # Income statement checks
    if block_name == "income_statement" and "revenue" in block:
        revenue = block["revenue"]
        cogs = block.get("cogs")
        gross = block["gross_profit"]

        if revenue and cogs and gross and len(revenue) > 0:
            for i, (rev, cost, gp) in enumerate(zip(revenue, cogs, gross)):
                if rev is not None and cost is not None and gp is not None:
                    expected_gp = rev - cost
                    if abs(gp - expected_gp) > rev * 0.01:  # 1% tolerance
                        errors.append(f"Year {i}: gross_profit={gp}, expected {expected_gp}")

    # Balance sheet checks
    if block_name == "balance_sheet":
        assets = block.get("total_assets")
        liabilities = block.get("total_liabilities")
        equity = block.get("equity", {}).get("total_equity")

        if assets and liabilities and equity and len(assets) > 0:
            for i, (a, l, e) in enumerate(zip(assets, liabilities, equity)):
                if a is not None and l is not None and e is not None:
                    expected_eq = a - l
                    if abs(e - expected_eq) > a * 0.01:  # 1% tolerance
                        errors.append(f"Year {i}: equity={e}, assets-liab={expected_eq}")

    if errors:
        print(f"[ARITHMETIC WARNING] {block_name}: {'; '.join(errors)}")
        return False
    return True


def build_financials() -> Dict[str, Any]:
    """Build extracted financials JSON from collected IFRS data."""

    # Years for which we have at least fragmentary data
    years = [2020, 2021, 2022, 2023, 2024, 2025]

    # Data sources:
    # 2023: smart-lab blog (IFRS)
    # 2024: smart-lab summary (IFRS)
    # 2025: cbonds (IFRS, contradictory profit data)

    doc = {
        "meta": {
            "ticker": "DZRD",
            "name": "Донской завод радиодеталей / Donskoy Radio Components Plant",
            "profile": "standard",
            "reporting_standard": "МСФО",  # РСБУ не найдена в интернете
            "currency": "RUB",
            "unit": "млн",
            "converted_years": [],
            "conversion_note": "",
            "fiscal_years": [2020, 2021, 2022, 2023, 2024, 2025],
            "source": {
                "type": "multi-source",
                "url": "smart-lab.ru (IFRS), cbonds.ru, e-disclosure.ru",
                "doc_title": "IFRS Annual Reports 2023–2025 (РСБУ 2023–2024 not found)",
                "retrieved": datetime.now().strftime("%Y-%m-%d")
            },
            "data_quality": "low",
            "parse_method": "web-aggregate",
            "arithmetic_check": "partial"
        },

        "income_statement": {
            "cost_format": "by_function",
            "revenue": [None, None, None, 3260, 3270, 1750],  # 2020-2025, млн
            "cogs": [None, None, None, 2054, None, None],  # 2023 calc: 3260*(1-0.37)
            "gross_profit": [None, None, None, 1206, None, None],  # 2023: 37% margin
            "expense_lines": [
                {
                    "name": "Administrative and other expenses (admin & operating)",
                    "values": [None, None, None, None, None, None]
                },
                {
                    "name": "Provision for doubtful receivables (резерв по сомнительным)",
                    "values": [None, None, None, -909, None, None]  # 2023 only
                }
            ],
            "operating_profit": [None, None, None, -600, -824, None],
            "da": [None, None, None, None, None, None],
            "ebitda": [None, None, None, None, -462, None],  # 2024 EBITDA
            "finance_costs": [None, None, None, None, None, None],
            "finance_income": [None, None, None, None, None, None],
            "pre_tax_profit": [None, None, None, None, None, None],
            "income_tax": [None, None, None, None, None, None],
            "net_profit": [None, None, None, None, -1210, None]  # 2024 loss; 2025 data contradictory
        },

        "balance_sheet": {
            "non_current_assets": {
                "ppe": [None, None, None, None, None, None],
                "intangibles": [None, None, None, None, None, None],
                "goodwill": [None, None, None, None, None, None],
                "long_term_investments": [None, None, None, None, None, None],
                "other_non_current": [None, None, None, None, None, None],
                "total_non_current": [None, None, None, None, None, None]
            },
            "current_assets": {
                "inventory": [None, None, None, None, None, None],
                "receivables": [None, None, None, 126, None, None],  # 2023: fell to 0.126B
                "cash": [None, None, None, None, None, None],
                "short_term_investments": [None, None, None, None, None, None],
                "other_current": [None, None, None, None, None, None],
                "total_current": [None, None, None, None, None, None]
            },
            "total_assets": [None, None, None, None, 5080, None],  # 2024: 5.08B
            "equity": {
                "share_capital": [None, None, None, None, None, None],
                "retained_earnings": [None, None, None, None, None, None],
                "additional_paid_in": [None, None, None, None, None, None],
                "other_equity": [None, None, None, None, None, None],
                "total_equity": [None, None, None, 3379, 3580, None]  # 2023: 3.379B; 2024: 3.58B
            },
            "non_current_liabilities": {
                "long_term_debt": [None, None, None, None, None, None],
                "deferred_tax": [None, None, None, None, None, None],
                "other_non_current_liab": [None, None, None, None, None, None],
                "total_non_current_liab": [None, None, None, None, None, None]
            },
            "current_liabilities": {
                "short_term_debt": [None, None, None, None, None, None],
                "payables": [None, None, None, None, None, None],
                "other_current_liab": [None, None, None, None, None, None],
                "total_current_liab": [None, None, None, None, None, None]
            },
            "total_liabilities": [None, None, None, None, 1500, None]  # 2024 inferred: 5080-3580
        },

        "cash_flow": {
            "cfo": [None, None, None, None, 248, None],  # 2024: 0.248B
            "cfi": [None, None, None, None, None, None],
            "cff": [None, None, None, None, None, None],
            "capex": [None, None, None, None, 669, None],  # 2023: CapEx (ОС) 669M in report
            "net_change_in_cash": [None, None, None, None, 53, None]  # 2024: FCF 0.053B
        },

        "data_flags": [
            "РСБУ not found in open internet; using МСФО (IFRS) only",
            "2020-2022: no data found",
            "2023: partial (P&L fragments from smart-lab blog analysis)",
            "2024: revenue & losses from smart-lab, EBITDA from aggregate; COGS/gross estimated",
            "2025: contradictory profit data (70.56M vs -1.31B); using loss figure",
            "Q1 2026: exists but not included (incomplete quarter)",
            "Balance sheet incomplete: only totals; detail (ppe/inventory/debt) not available",
            "Cash flow: only CFO, CapEx, FCF for 2024; CFI/CFF unknown",
            "Receivables drop 2023 (2.07→0.126B) and PP&E jump (1.4→2.66B) flagged in audit as 'suspicious'",
            "Large 909M provision for doubtful receivables (2023) suggests asset quality issues",
            "Arithmetic: gross_profit estimated from margin %; total_liabilities inferred from A-E",
            "data_quality=low; incomplete; manual РСБУ upload recommended"
        ]
    }

    # Validate arithmetic
    validate_arithmetic(doc["income_statement"], "income_statement")
    validate_arithmetic(doc["balance_sheet"], "balance_sheet")

    return doc


def main():
    """Generate and save extracted financials."""
    financials = build_financials()

    output_path = "/Users/soinnikita/investment-platform/backend/companies/DZRD/sources/extracted_financials.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(financials, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved: {output_path}")
    print(f"Years covered (fragmented): 2023–2024 (МСФО)")
    print(f"Data quality: LOW (РСБУ not found; МСФО incomplete)")
    print(f"Arithmetic: Partial (estimated fields marked; see data_flags)")
    print(f"Recommendation: Manual РСБУ upload needed for full 5-year extraction")

    # Summary
    with open(output_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    print("\n--- Summary ---")
    print(f"Ticker: {doc['meta']['ticker']}")
    print(f"Standard: {doc['meta']['reporting_standard']}")
    print(f"Years available (with any data): {[y for y, v in enumerate(doc['income_statement']['revenue'], 2020) if v is not None]}")
    print(f"Income statement: revenue yes (3yr), COGS partial (1yr est), loss data (2yr)")
    print(f"Balance sheet: totals only (2yr), no detail")
    print(f"Cash flow: partial (1yr CFO/CapEx/FCF)")
    print(f"Data flags: {len(doc['data_flags'])} warnings (РСБУ missing, arithmetic estimated)")


if __name__ == "__main__":
    main()
