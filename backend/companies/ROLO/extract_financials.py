#!/usr/bin/env python3
"""
РУСОЛОВО (ROLO) financial data extraction from МСФО consolidated reports.
Extracts data from PDF/text and validates arithmetic consistency.
"""

import json
from datetime import datetime

# Extracted from Rusolovo_2024 МСФО отчёт (млн руб)
# Data is in thousands of RUB; will convert to millions

financials = {
    "meta": {
        "ticker": "ROLO",
        "name": "ПАО Русолово",
        "profile": "standard",
        "reporting_standard": "МСФО",
        "currency": "RUB",
        "unit": "млн",
        "converted_years": [],
        "conversion_note": "All data sourced from official МСФО consolidated statements in thousands RUB, converted to millions",
        "fiscal_years": [2021, 2022, 2023, 2024],
        "source": {
            "type": "company_ir",
            "url": "https://rus-olovo.ru/for-investors/disclouser/international/",
            "doc_title": "Консолидированная финансовая отчётность по МСФО",
            "retrieved": "2026-06-13"
        },
        "data_quality": "high",
        "parse_method": "pdftotext + manual extraction",
        "arithmetic_check": "pending"
    },
    "income_statement": {
        "cost_format": "by_function",  # Has себестоимость/валовая прибыль
        "revenue": [None, 5997, 6276, 7455],  # 2021, 2022, 2023, 2024 (млн руб)
        "cogs": [None, None, 5259, 6490],  # 2024 = 6489.842 млн; 2023 = 5259.013 млн
        "gross_profit": [None, 1644, 1017, 965],  # валовая прибыль
        "expense_lines": [
            {
                "name": "Коммерческие и административные расходы",
                "values": [None, None, 1160, 1700]  # 2024 = 1699.817 млн
            },
            {
                "name": "Прочие операционные расходы, нетто",
                "values": [None, None, 919, 2108]  # 2024 = 2108.340 млн
            }
        ],
        "operating_profit": [None, None, -1062, -2843],  # EBIT
        "da": [None, 813, 1459, 1398],  # амортизация
        "ebitda": [None, 1382, 1340, 692],  # EBITDA
        "finance_costs": [None, None, 530, 900],  # finance costs / процентные расходы
        "finance_income": [None, None, -29, -69],  # процентный доход (отрицательно в выражении)
        "pre_tax_profit": [None, -667, -1942, -3703],  # убыток до налога
        "income_tax": [None, None, 315, 297],  # налог на прибыль (положительный отложенный)
        "net_profit": [None, -667, -1626, -3406]  # чистая прибыль/убыток
    },
    "balance_sheet": {
        "non_current_assets": {
            "ppe": [None, 14869, 17010, 24450],  # основные средства
            "intangibles": [None, 43, 43, 6],  # нематериальные активы
            "goodwill": [None, None, None, None],
            "long_term_investments": [None, None, None, None],
            "other_non_current": [None, 1960, 1319, 1373],  # разведка + отлож.налог + прочие
            "total_non_current": [None, 15922, 18372, 26308]
        },
        "current_assets": {
            "inventory": [None, 2857, 3564, 4617],  # запасы
            "receivables": [None, 1402, 1237, 2365],  # дебиторская задолженность + авансы
            "cash": [None, 191, 978, 435],  # денежные средства
            "short_term_investments": [None, 4, 68, 52],  # финактивы по справ.стоимости
            "other_current": [None, 219, 522, 792],  # НДС к возмещению + авансы + займы
            "total_current": [None, 4674, 6369, 8261]
        },
        "total_assets": [None, 20596, 24741, 34569],
        "equity": {
            "share_capital": [None, 3000, 3000, 3000],  # уставный капитал
            "retained_earnings": [None, -133, -1164, -3519],  # нераспределённая прибыль/убыток
            "additional_paid_in": [None, 1735, 1735, 4683],  # добавочный капитал
            "other_equity": [None, 1813, 1218, 2127],  # неконтролирующая доля
            "total_equity": [None, 6416, 4790, 6291]
        },
        "non_current_liabilities": {
            "long_term_debt": [None, 4586, 5108, 7546],  # кредиты и займы (долгосроч.)
            "deferred_tax": [None, 1366, 1049, 862],  # отложенные налоговые обязательства
            "other_non_current_liab": [None, 1978, 2253, 2188],  # векселя + аренда + резерв
            "total_non_current_liab": [None, 7930, 8410, 10596]
        },
        "current_liabilities": {
            "short_term_debt": [None, 758, 981, 5403],  # кредиты, займы, векселя (краткосроч.)
            "payables": [None, 5466, 10430, 12047],  # кредиторская задолженность
            "other_current_liab": [None, 26, 130, 232],  # обязательства по аренде
            "total_current_liab": [None, 6250, 11541, 17682]
        },
        "total_liabilities": [None, 14180, 19951, 28278]
    },
    "cash_flow": {
        "cfo": [None, None, 4638, -2931],  # денежный поток от операционной деятельности
        "cfi": [None, None, -3733, -4184],  # денежный поток от инвестиционной деятельности
        "cff": [None, None, -118, 6572],  # денежный поток от финансовой деятельности
        "capex": [None, None, 3670, 4002],  # инвестиции в ОС и НМА
        "net_change_in_cash": [None, None, None, None]  # net change = cfo + cfi + cff
    },
    "data_flags": []
}

# ====== ARITHMETIC CHECKS ======
def check_arithmetic(data):
    """Validate internal arithmetic consistency."""
    errors = []
    years = data["meta"]["fiscal_years"]

    for i, year in enumerate(years):
        if i == 0:  # Skip 2021 (no data)
            continue

        pnl = data["income_statement"]
        bs = data["balance_sheet"]

        # gross_profit = revenue - cogs (by_function)
        if (pnl["revenue"][i] is not None and pnl["cogs"][i] is not None and
            pnl["gross_profit"][i] is not None):
            expected_gp = pnl["revenue"][i] - pnl["cogs"][i]
            actual_gp = pnl["gross_profit"][i]
            if abs(expected_gp - actual_gp) > abs(expected_gp) * 0.01:
                errors.append(
                    f"{year}: Gross profit mismatch. Expected {expected_gp:.0f}, got {actual_gp:.0f}"
                )

        # total_assets = non_current + current
        nca = bs["non_current_assets"]["total_non_current"][i]
        ca = bs["current_assets"]["total_current"][i]
        ta = bs["total_assets"][i]
        if nca is not None and ca is not None and ta is not None:
            expected_ta = nca + ca
            if abs(expected_ta - ta) > abs(expected_ta) * 0.01:
                errors.append(
                    f"{year}: Total assets (A≠NCA+CA). Expected {expected_ta:.0f}, got {ta:.0f}"
                )

        # total_assets = equity + liabilities
        eq = bs["equity"]["total_equity"][i]
        liab = bs["total_liabilities"][i]
        if eq is not None and liab is not None and ta is not None:
            expected_ta = eq + liab
            if abs(expected_ta - ta) > abs(expected_ta) * 0.01:
                errors.append(
                    f"{year}: Balance mismatch (A≠E+L). Expected {expected_ta:.0f}, got {ta:.0f}"
                )

        # total_liabilities = non_current + current
        ncl = bs["non_current_liabilities"]["total_non_current_liab"][i]
        cl = bs["current_liabilities"]["total_current_liab"][i]
        if ncl is not None and cl is not None and liab is not None:
            expected_liab = ncl + cl
            if abs(expected_liab - liab) > abs(expected_liab) * 0.01:
                errors.append(
                    f"{year}: Total liabilities mismatch. Expected {expected_liab:.0f}, got {liab:.0f}"
                )

        # equity sum
        sc = bs["equity"]["share_capital"][i]
        re = bs["equity"]["retained_earnings"][i]
        api = bs["equity"]["additional_paid_in"][i]
        oe = bs["equity"]["other_equity"][i]
        if all(x is not None for x in [sc, re, api, oe, eq]):
            expected_eq = sc + re + api + oe
            if abs(expected_eq - eq) > abs(expected_eq) * 0.01:
                errors.append(
                    f"{year}: Total equity sum mismatch. Expected {expected_eq:.0f}, got {eq:.0f}"
                )

        # Cash flow check
        cf = data["cash_flow"]
        if (cf["cfo"][i] is not None and cf["cfi"][i] is not None and
            cf["cff"][i] is not None):
            net_change = cf["cfo"][i] + cf["cfi"][i] + cf["cff"][i]
            cf["net_change_in_cash"][i] = round(net_change, 0)

    return errors

# Run checks
errors = check_arithmetic(financials)

if errors:
    financials["meta"]["arithmetic_check"] = "partial"
    for err in errors:
        financials["data_flags"].append(f"ARITHMETIC: {err}")
else:
    financials["meta"]["arithmetic_check"] = "passed"

print("="*70)
print("ФИНАНСОВЫЕ ДАННЫЕ: РУСОЛОВО (ROLO) — 2022, 2023, 2024")
print("="*70)
print(f"Стандарт: {financials['meta']['reporting_standard']}")
print(f"Источник: {financials['meta']['source']['type']} ({financials['meta']['source']['url']})")
print(f"Арифметика: {financials['meta']['arithmetic_check']}")

if errors:
    print(f"\n⚠️  Обнаружены ошибки ({len(errors)}):")
    for err in errors:
        print(f"  - {err}")
else:
    print("\n✓ Арифметика пройдена")

print("\n" + "-"*70)
print("КЛЮЧЕВЫЕ ПОКАЗАТЕЛИ (млн руб)")
print("-"*70)
for year_idx, year in enumerate(financials["meta"]["fiscal_years"]):
    if year_idx == 0:
        continue
    print(f"\n{year}:")
    pnl = financials["income_statement"]
    bs = financials["balance_sheet"]
    cf = financials["cash_flow"]
    
    print(f"  Выручка: {pnl['revenue'][year_idx]}")
    print(f"  Себестоимость: {pnl['cogs'][year_idx]}")
    print(f"  Валовая прибыль: {pnl['gross_profit'][year_idx]} ({100*pnl['gross_profit'][year_idx]/pnl['revenue'][year_idx]:.1f}%)")
    print(f"  EBITDA: {pnl['ebitda'][year_idx]}")
    print(f"  Чистая прибыль: {pnl['net_profit'][year_idx]}")
    
    total_debt = (bs["non_current_liabilities"]["long_term_debt"][year_idx] or 0) + \
                 (bs["current_liabilities"]["short_term_debt"][year_idx] or 0)
    print(f"  Общий долг: {total_debt}")
    print(f"  Активы: {bs['total_assets'][year_idx]}")
    print(f"  Капитал: {bs['equity']['total_equity'][year_idx]}")
    print(f"  CFO: {cf['cfo'][year_idx]}")

# Write to JSON
output_path = "/Users/soinnikita/investment-platform/backend/companies/ROLO/sources/extracted_financials.json"
import os
os.makedirs(os.path.dirname(output_path), exist_ok=True)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(financials, f, ensure_ascii=False, indent=2)

print(f"\n✓ Сохранено: {output_path}")
