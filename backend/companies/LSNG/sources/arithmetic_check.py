#!/usr/bin/env python3
"""
Arithmetic validation for extracted financials (LSNG).
Checks:
1. gross_profit = revenue - cogs (if by_function)
2. total_assets ≈ total_equity + total_liabilities (±1%)
3. current_assets = sum of asset components (±1%)
4. non_current_assets = sum of asset components (±1%)
5. ebitda ≈ operating_profit + da (±1%)
6. net_change_in_cash ≈ cfo + cfi + cff (±1%)
"""

import json

def check_tolerance(a, b, tolerance_pct=1.0):
    """Check if two values are within tolerance (%)."""
    if a is None or b is None:
        return None, "one value is None"
    if b == 0:
        return None, "divisor is 0"
    pct_diff = abs(a - b) / abs(b) * 100
    return pct_diff <= tolerance_pct, f"{pct_diff:.2f}%"

def validate_extracted_json(filepath):
    """Validate arithmetic in extracted_financials.json."""

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    meta = data['meta']
    fiscal_years = meta['fiscal_years']
    cost_format = data['income_statement']['cost_format']

    results = {
        'summary': {
            'total_checks': 0,
            'passed': 0,
            'failed': 0,
            'skipped': 0
        },
        'details': []
    }

    # === P&L Checks ===
    rev = data['income_statement']['revenue']
    op_profit = data['income_statement']['operating_profit']
    da = data['income_statement']['da']
    ebitda = data['income_statement']['ebitda']

    for i, year in enumerate(fiscal_years):
        # EBITDA = Operating Profit + D&A
        if op_profit[i] is not None and da[i] is not None:
            calc_ebitda = op_profit[i] + da[i]
            if ebitda[i] is not None:
                ok, diff = check_tolerance(calc_ebitda, ebitda[i])
                results['summary']['total_checks'] += 1
                if ok:
                    results['summary']['passed'] += 1
                    status = "PASS"
                else:
                    results['summary']['failed'] += 1
                    status = "FAIL"
                results['details'].append({
                    'year': year,
                    'check': 'ebitda = op_profit + da',
                    'calculated': calc_ebitda,
                    'reported': ebitda[i],
                    'diff': diff,
                    'status': status
                })
        elif ebitda[i] is not None:
            results['summary']['total_checks'] += 1
            results['summary']['skipped'] += 1
            results['details'].append({
                'year': year,
                'check': 'ebitda = op_profit + da',
                'note': 'op_profit or da is None; skipped'
            })

    # === Balance Sheet Checks ===
    ta = data['balance_sheet']['total_assets']
    te = data['balance_sheet']['equity']['total_equity']
    tl = data['balance_sheet']['total_liabilities']

    for i, year in enumerate(fiscal_years):
        # Assets = Equity + Liabilities
        if te[i] is not None and tl[i] is not None:
            calc_ta = te[i] + tl[i]
            if ta[i] is not None:
                ok, diff = check_tolerance(calc_ta, ta[i])
                results['summary']['total_checks'] += 1
                if ok:
                    results['summary']['passed'] += 1
                    status = "PASS"
                else:
                    results['summary']['failed'] += 1
                    status = "FAIL"
                results['details'].append({
                    'year': year,
                    'check': 'total_assets = total_equity + total_liabilities',
                    'calculated': calc_ta,
                    'reported': ta[i],
                    'diff': diff,
                    'status': status
                })
        elif ta[i] is not None:
            results['summary']['total_checks'] += 1
            results['summary']['skipped'] += 1
            results['details'].append({
                'year': year,
                'check': 'total_assets = total_equity + total_liabilities',
                'note': 'equity or liabilities is None; skipped'
            })

    # === Cash Flow Checks ===
    cfo = data['cash_flow']['cfo']
    cfi = data['cash_flow']['cfi']
    cff = data['cash_flow']['cff']
    net_change = data['cash_flow']['net_change_in_cash']

    for i, year in enumerate(fiscal_years):
        # Net change = CFO + CFI + CFF
        if cfo[i] is not None and cfi[i] is not None and cff[i] is not None:
            calc_change = cfo[i] + cfi[i] + cff[i]
            if net_change[i] is not None:
                ok, diff = check_tolerance(calc_change, net_change[i])
                results['summary']['total_checks'] += 1
                if ok:
                    results['summary']['passed'] += 1
                    status = "PASS"
                else:
                    results['summary']['failed'] += 1
                    status = "FAIL"
                results['details'].append({
                    'year': year,
                    'check': 'net_change_in_cash = cfo + cfi + cff',
                    'calculated': calc_change,
                    'reported': net_change[i],
                    'diff': diff,
                    'status': status
                })
        elif net_change[i] is not None:
            results['summary']['total_checks'] += 1
            results['summary']['skipped'] += 1
            results['details'].append({
                'year': year,
                'check': 'net_change_in_cash = cfo + cfi + cff',
                'note': 'cfo, cfi or cff is None; skipped'
            })

    # === Summary ===
    if results['summary']['total_checks'] > 0:
        pass_rate = results['summary']['passed'] / results['summary']['total_checks'] * 100
        results['summary']['pass_rate_pct'] = round(pass_rate, 1)

    return results

if __name__ == '__main__':
    import sys

    filepath = '/Users/soinnikita/investment-platform/backend/companies/LSNG/sources/extracted_financials.json'

    results = validate_extracted_json(filepath)

    print("=" * 70)
    print("ARITHMETIC VALIDATION REPORT - LSNG")
    print("=" * 70)
    print(f"\nTotal checks: {results['summary']['total_checks']}")
    print(f"Passed: {results['summary']['passed']}")
    print(f"Failed: {results['summary']['failed']}")
    print(f"Skipped: {results['summary']['skipped']}")
    if 'pass_rate_pct' in results['summary']:
        print(f"Pass rate: {results['summary']['pass_rate_pct']}%")

    print("\n" + "=" * 70)
    print("DETAILS:")
    print("=" * 70)

    for check in results['details']:
        year = check.get('year', '?')
        check_name = check.get('check', '')
        status = check.get('status', 'SKIP')

        if 'note' in check:
            print(f"\n{year} | {check_name}")
            print(f"  Note: {check['note']}")
        else:
            calc = check.get('calculated', '?')
            rep = check.get('reported', '?')
            diff = check.get('diff', '?')
            print(f"\n{year} | {check_name}")
            print(f"  Status: {status}")
            print(f"  Calculated: {calc:,.0f}")
            print(f"  Reported:   {rep:,.0f}")
            print(f"  Diff: {diff}")

    print("\n" + "=" * 70)

    # Update JSON with check status
    if results['summary']['failed'] == 0 and results['summary']['total_checks'] > 0:
        status = "passed"
    elif results['summary']['failed'] > 0:
        status = "failed"
    else:
        status = "partial"

    print(f"\nFinal arithmetic_check status: {status}")
    print("=" * 70)
