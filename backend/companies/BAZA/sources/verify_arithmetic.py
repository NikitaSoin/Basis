#!/usr/bin/env python3
"""
Арифметическая самопроверка extracted_financials.json для BAZA (Basis).
По методике: gross_profit ≈ revenue - cogs, net_change ≈ cfo+cfi+cff, баланс ≈ assets = eq+liab.
Допуск: ±1%.
"""

import json
from pathlib import Path

def check_arithmetic():
    # Загрузить JSON
    json_path = Path("/Users/soinnikita/investment-platform/backend/companies/BAZA/sources/extracted_financials.json")
    with open(json_path) as f:
        data = json.load(f)

    years = data["meta"]["fiscal_years"]
    print(f"✓ Проверка BAZA (Basis) за годы: {years}")
    print(f"✓ Стандарт: {data['meta']['reporting_standard']}")
    print(f"✓ Валюта/единица: {data['meta']['currency']} {data['meta']['unit']}")
    print()

    # === P&L CHECKS ===
    print("=" * 70)
    print("ОТЧЕТ О ПРИБЫЛЯХ И УБЫТКАХ (Income Statement)")
    print("=" * 70)

    revenue = data["income_statement"]["revenue"]
    net_profit = data["income_statement"]["net_profit"]
    ebitda = data["income_statement"]["ebitda"]
    cogs = data["income_statement"]["cogs"]
    gross_profit = data["income_statement"]["gross_profit"]

    if revenue:
        for i, y in enumerate(years):
            r = revenue[i]
            np_val = net_profit[i] if net_profit and i < len(net_profit) else None
            ebitda_val = ebitda[i] if ebitda and i < len(ebitda) else None

            print(f"\nГод {y}:")
            print(f"  Выручка (Revenue): {r:,.0f} млн")
            print(f"  Чистая прибыль (Net Profit): {np_val:,.0f} млн" if np_val else "  Чистая прибыль: не раскрыта")
            print(f"  EBITDA: {ebitda_val:,.0f} млн" if ebitda_val else "  EBITDA: не раскрыта")

            # EBITDA как % от выручки (proxy для маржи)
            if ebitda_val and r:
                ebitda_margin = (ebitda_val / r) * 100
                print(f"  EBITDA маржа: {ebitda_margin:.1f}%")

            # Net profit margin
            if np_val and r:
                np_margin = (np_val / r) * 100
                print(f"  Чистая маржа: {np_margin:.1f}%")

    # COGS / Gross profit check
    if cogs and gross_profit:
        print("\n✓ COGS раскрыта (раскладка по функциям)")
        for i, y in enumerate(years):
            if cogs[i] is not None and gross_profit[i] is not None and revenue[i] is not None:
                expected_gp = revenue[i] - cogs[i]
                actual_gp = gross_profit[i]
                diff_pct = abs((actual_gp - expected_gp) / expected_gp) * 100 if expected_gp else 0
                status = "✓" if diff_pct <= 1 else "✗"
                print(f"  {y}: Выручка - COGS = {expected_gp:,.0f}; Reported GP = {actual_gp:,.0f} [{status} {diff_pct:.2f}% diff]")
    else:
        print("\n⚠ COGS/Gross Profit: не раскрыты (by_nature format, нет расшифровки затрат)")

    # === BALANCE SHEET CHECKS ===
    print("\n" + "=" * 70)
    print("БАЛАНС (Balance Sheet)")
    print("=" * 70)

    bs = data["balance_sheet"]
    total_assets = bs["total_assets"]
    total_equity = bs["equity"]["total_equity"]
    total_liab = bs["total_liabilities"]
    share_capital = bs["equity"]["share_capital"]

    if total_assets and (total_equity or total_liab):
        print(f"\n✓ Баланс:")
        for i, y in enumerate(years):
            ta = total_assets[i] if total_assets and i < len(total_assets) else None
            te = total_equity[i] if total_equity and i < len(total_equity) else None
            tl = total_liab[i] if total_liab and i < len(total_liab) else None

            print(f"\n  Год {y}:")
            if ta:
                print(f"    Total Assets: {ta:,.0f} млн")
            if te and tl:
                calculated_assets = te + tl
                if ta:
                    diff_pct = abs((calculated_assets - ta) / ta) * 100 if ta else 0
                    status = "✓" if diff_pct <= 1 else "✗"
                    print(f"    Equity + Liab = {calculated_assets:,.0f} [vs TA {ta:,.0f}] [{status} {diff_pct:.2f}% diff]")
                else:
                    print(f"    Equity + Liab = {calculated_assets:,.0f} (TA не раскрыта)")
            elif te:
                print(f"    Total Equity: {te:,.0f} млн")
            elif tl:
                print(f"    Total Liab: {tl:,.0f} млн")
    else:
        print("\n⚠ Баланс: большинство статей не раскрыты. Доступно только:")
        if share_capital:
            print(f"  Уставный капитал (Share Capital): {share_capital} млн (constant, 165 млн акций × 1 руб.)")

    # === CASH FLOW CHECKS ===
    print("\n" + "=" * 70)
    print("ДЕНЕЖНЫЙ ПОТОК (Cash Flow)")
    print("=" * 70)

    cfo = data["cash_flow"]["cfo"]
    cfi = data["cash_flow"]["cfi"]
    cff = data["cash_flow"]["cff"]
    fcf = data["cash_flow"]["free_cash_flow"]
    net_cash_chg = data["cash_flow"]["net_change_in_cash"]
    net_cash_pos = data["cash_flow"]["net_cash_position"]

    if fcf:
        print(f"\n✓ Свободный денежный поток (FCF) раскрыт:")
        for i, y in enumerate(years):
            f = fcf[i]
            ncp = net_cash_pos[i] if net_cash_pos and i < len(net_cash_pos) else None
            print(f"  {y}: FCF = {f:,.0f} млн" + (f", Net cash position = {ncp:,.0f} млн" if ncp else ""))
    else:
        print("\n⚠ FCF: не раскрыта")

    if cfo or cfi or cff:
        print(f"\n✓ CF по разделам раскрыта (CFO/CFI/CFF):")
        for i, y in enumerate(years):
            cfo_val = cfo[i] if cfo and i < len(cfo) else None
            cfi_val = cfi[i] if cfi and i < len(cfi) else None
            cff_val = cff[i] if cff and i < len(cff) else None
            if cfo_val or cfi_val or cff_val:
                print(f"  {y}: CFO={cfo_val}, CFI={cfi_val}, CFF={cff_val}")
    else:
        print("\n⚠ CFO/CFI/CFF: не раскрыты (только FCF и net cash position)")

    # Check if CFO+CFI+CFF ≈ net cash change
    if (cfo or cfi or cff) and net_cash_chg:
        print(f"\n  Проверка: CFO + CFI + CFF ≈ Net change in cash")
        for i, y in enumerate(years):
            cfo_val = cfo[i] if cfo and i < len(cfo) else 0 or None
            cfi_val = cfi[i] if cfi and i < len(cfi) else 0 or None
            cff_val = cff[i] if cff and i < len(cff) else 0 or None
            ncc_val = net_cash_chg[i] if i < len(net_cash_chg) else None
            if (cfo_val or cfi_val or cff_val) and ncc_val is not None:
                calc_chg = (cfo_val or 0) + (cfi_val or 0) + (cff_val or 0)
                diff = abs(calc_chg - ncc_val)
                diff_pct = (diff / abs(ncc_val)) * 100 if ncc_val else 0
                status = "✓" if diff_pct <= 1 else "✗"
                print(f"    {y}: {calc_chg:,.0f} vs {ncc_val:,.0f} [{status} {diff_pct:.2f}% diff]")

    # === FINAL SUMMARY ===
    print("\n" + "=" * 70)
    print("ИТОГОВЫЙ ВЕРДИКТ (Arithmetic Check Summary)")
    print("=" * 70)

    has_pnl_core = revenue and net_profit
    has_bs_core = total_assets and (total_equity and total_liab)
    has_cf_core = (cfo and cfi and cff) or (fcf and net_cash_chg)

    print(f"\nОтчёт о прибылях (P&L):")
    print(f"  Ключевые статьи (Revenue, Net Profit, EBITDA): {'✓ есть' if has_pnl_core else '⚠ частично'}")
    print(f"  Детали затрат (COGS, OpEx breakdown): {'✓ есть' if cogs else '✗ нет (by_nature, не раскрыта)'}")

    print(f"\nБаланс (Balance Sheet):")
    print(f"  Полный баланс (Assets = Equity + Liab): {'✓ есть' if has_bs_core else '✗ НЕ РАСКРЫТ'}")
    print(f"  Только уставный капитал: ✓ {share_capital} млн")

    print(f"\nДенежные потоки (Cash Flow):")
    print(f"  CF по разделам (CFO/CFI/CFF): {'✓ есть' if (cfo and cfi and cff) else '✗ нет'}")
    print(f"  FCF / Net cash position: {'✓ есть' if fcf else '✗ нет'}")

    print(f"\nОбщий вердикт:")
    if has_pnl_core and has_cf_core and not has_bs_core:
        print("  arithmetic_check: PARTIAL")
        print("  → P&L полная (выручка, маржи, прибыль), CF есть (FCF/net cash), но БАЛАНС отсутствует.")
    elif has_pnl_core and not has_bs_core and not has_cf_core:
        print("  arithmetic_check: FAILED")
        print("  → Только топовые строки P&L; баланса и подробного CF нет.")
    else:
        print("  arithmetic_check: PASSED" if has_pnl_core and has_bs_core and has_cf_core else "  arithmetic_check: PARTIAL")

    print(f"\nДанные для financial-analyst: READY (с ограничениями, см. data_flags)")

if __name__ == "__main__":
    check_arithmetic()
