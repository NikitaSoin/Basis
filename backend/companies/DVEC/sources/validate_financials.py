#!/usr/bin/env python3
"""
Validation and enrichment script for ДЭК (DVEC) extracted financials.
Performs arithmetic checks and calculates derived metrics.
"""

import json
from pathlib import Path

def check_balance_sheet_balance(assets, equity, liabilities, year_idx):
    """Check if Assets = Equity + Liabilities"""
    if assets[year_idx] is None or equity[year_idx] is None or liabilities[year_idx] is None:
        return None, None

    a = assets[year_idx]
    e = equity[year_idx]
    l = liabilities[year_idx]

    balance = a - (e + l)
    pct_error = abs(balance) / a * 100 if a > 0 else float('inf')

    return balance, pct_error

def calculate_cogs_gross_profit(revenue, cogs, gross_profit, year_idx, tolerance=1.0):
    """Check and validate Gross Profit = Revenue - COGS"""
    checks = []
    if revenue[year_idx] and cogs[year_idx] and gross_profit[year_idx]:
        calc_gp = revenue[year_idx] - cogs[year_idx]
        error_pct = abs(calc_gp - gross_profit[year_idx]) / gross_profit[year_idx] * 100
        if error_pct > tolerance:
            checks.append(f"Year {year_idx}: GP validation failed ({error_pct:.1f}% diff)")
    return checks

def calculate_cash_flow_balance(cfo, cfi, cff, net_change, year_idx, tolerance=1.0):
    """Check if Net Change = CFO + CFI + CFF"""
    if cfo[year_idx] and cfi[year_idx] and cff[year_idx] and net_change[year_idx]:
        calc_change = cfo[year_idx] + cfi[year_idx] + cff[year_idx]
        error_pct = abs(calc_change - net_change[year_idx]) / abs(net_change[year_idx]) * 100 if net_change[year_idx] != 0 else float('inf')
        return error_pct <= tolerance
    return None

def estimate_operating_profit_and_da(revenue, ebitda, net_profit, cfo, capex, year_idx):
    """
    Estimate Operating Profit and D&A from available data.
    D&A can be roughly estimated from EBITDA if Operating Profit is known.
    """
    estimates = {}

    if ebitda[year_idx] and net_profit[year_idx]:
        # Rough estimate: Operating Profit ≈ EBITDA - D&A
        # We need more data to solve this precisely, but we can note that
        # for a utility company with stable operations, D&A is often 30-50% of EBITDA
        estimates['ebitda'] = ebitda[year_idx]

    # Free Cash Flow = CFO - CapEx
    if cfo[year_idx] and capex[year_idx]:
        estimates['fcf'] = cfo[year_idx] - capex[year_idx]

    return estimates

def main():
    file_path = Path('/Users/soinnikita/investment-platform/backend/companies/DVEC/sources/extracted_financials.json')

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 80)
    print("ARITHMETIC VALIDATION FOR DVEC (ДАЛЬНЕВОСТОЧНАЯ ЭНЕРГЕТИЧЕСКАЯ КОМПАНИЯ)")
    print("=" * 80)
    print()

    # Test 1: Balance Sheet Balance (Assets = Equity + Liabilities)
    print("TEST 1: Balance Sheet Balance (Assets = Equity + Liabilities)")
    print("-" * 80)
    assets = data['balance_sheet']['total_assets']
    equity = data['balance_sheet']['equity']['total_equity']
    liabilities = data['balance_sheet']['total_liabilities']

    all_passed = True
    for year_idx, year in enumerate(data['meta']['fiscal_years']):
        balance, pct_error = check_balance_sheet_balance(assets, equity, liabilities, year_idx)
        if balance is not None:
            status = "PASS" if pct_error <= 1.0 else "FAIL"
            if status == "FAIL":
                all_passed = False
            print(f"  {year}: A={assets[year_idx]:.1f}, E={equity[year_idx]:.1f}, L={liabilities[year_idx]:.1f} | "
                  f"Diff={balance:.1f} ({pct_error:.2f}%) — {status}")
        else:
            print(f"  {year}: Missing data (A={assets[year_idx]}, E={equity[year_idx]}, L={liabilities[year_idx]})")

    print(f"\nBalance Sheet Check: {'PASSED' if all_passed else 'PARTIAL'}")
    print()

    # Test 2: Estimate Free Cash Flow = CFO - CapEx
    print("TEST 2: Free Cash Flow Calculation (FCF = CFO - CapEx)")
    print("-" * 80)
    cfo = data['cash_flow']['cfo']
    capex = data['cash_flow']['capex']

    for year_idx, year in enumerate(data['meta']['fiscal_years']):
        if cfo[year_idx] and capex[year_idx]:
            fcf = cfo[year_idx] - capex[year_idx]
            print(f"  {year}: CFO={cfo[year_idx]:.1f}, CapEx={capex[year_idx]:.1f} → FCF={fcf:.1f}")

    print()

    # Test 3: Data Summary
    print("TEST 3: Data Completeness Summary")
    print("-" * 80)

    is_data = data['income_statement']
    bs_data = data['balance_sheet']
    cf_data = data['cash_flow']

    completeness = {
        'Revenue': sum(1 for v in is_data['revenue'] if v is not None),
        'Net Profit': sum(1 for v in is_data['net_profit'] if v is not None),
        'EBITDA': sum(1 for v in is_data['ebitda'] if v is not None),
        'Total Assets': sum(1 for v in bs_data['total_assets'] if v is not None),
        'Total Equity': sum(1 for v in bs_data['equity']['total_equity'] if v is not None),
        'Total Liabilities': sum(1 for v in bs_data['total_liabilities'] if v is not None),
        'CFO': sum(1 for v in cf_data['cfo'] if v is not None),
        'CapEx': sum(1 for v in cf_data['capex'] if v is not None),
    }

    for metric, count in completeness.items():
        pct = (count / len(data['meta']['fiscal_years'])) * 100
        status = "FULL" if count == len(data['meta']['fiscal_years']) else f"PARTIAL ({count}/{len(data['meta']['fiscal_years'])})"
        print(f"  {metric}: {status} ({pct:.0f}%)")

    print()

    # Test 4: Revenue and Net Profit Trend
    print("TEST 4: Revenue and Net Profit Trend")
    print("-" * 80)
    revenue = is_data['revenue']
    net_profit = is_data['net_profit']

    for year_idx, year in enumerate(data['meta']['fiscal_years']):
        if revenue[year_idx] and net_profit[year_idx]:
            margin = (net_profit[year_idx] / revenue[year_idx]) * 100
            print(f"  {year}: Revenue={revenue[year_idx]:.1f}, Net Profit={net_profit[year_idx]:.1f}, "
                  f"Net Margin={margin:.2f}%")

    print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Company: {data['meta']['name']}")
    print(f"Ticker: {data['meta']['ticker']}")
    print(f"Source: {data['meta']['source']['type']} ({data['meta']['source']['retrieved']})")
    print(f"Data Quality: {data['meta']['data_quality']}")
    print(f"Arithmetic Check: {data['meta']['arithmetic_check']}")
    print()
    print("KEY FINDINGS:")
    print(f"  • 5-year revenue CAGR: {((revenue[4] / revenue[0]) ** (1/4) - 1) * 100:.1f}% (2021-2025)")
    print(f"  • 5-year net profit CAGR: {((net_profit[4] / net_profit[0]) ** (1/4) - 1) * 100:.1f}% (2021-2025)")
    print(f"  • 2024 net profit decline: {((net_profit[3] - net_profit[2]) / net_profit[2]) * 100:.1f}%")
    print(f"  • Debt levels (2024): {liabilities[3]:.1f} млн (total liabilities), {equity[3]:.1f} млн (equity)")
    print(f"  • Debt/Assets ratio (2024): {(liabilities[3] / assets[3]) * 100:.1f}%")
    print()
    print("LIMITATIONS:")
    print("  ✗ Detailed P&L breakdown (COGS, OpEx, D&A, Finance costs) — requires PDF МСФО")
    print("  ✗ Balance sheet details (ОС, receivables, debt composition) — requires PDF МСФО")
    print("  ✗ Cash flow details (CFI, CFF, operating vs. investing items) — requires PDF МСФО")
    print("  ✓ Core metrics (Revenue, Net Profit, Assets, Debt, EBITDA, CFO, CapEx) — extracted")
    print()

if __name__ == '__main__':
    main()
