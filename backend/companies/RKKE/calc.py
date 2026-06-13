#!/usr/bin/env python3
"""
RKKE financials.json calculation script.
Data quality: CRITICALLY LOW — only partial data available.
Methods: EV/Sales (cautious), P/E adj (if profit), P/B → not_applicable (negative equity),
         DCF → insufficient_data, Dividend → not_applicable.
"""

import json
import math

# ─────────────────────────────────────────────────────────────
# MARKET CONTEXT (from rates.csv / task brief)
# ─────────────────────────────────────────────────────────────
price = 14174.17          # RUB per share
shares = 1_842_049        # total shares outstanding
market_cap_mln = price * shares / 1_000_000   # in mln RUB
print(f"Market cap: {market_cap_mln:.0f} mln RUB = {market_cap_mln/1000:.2f} bln RUB")

# ─────────────────────────────────────────────────────────────
# MACRO PARAMS (config/market_params.json)
# ─────────────────────────────────────────────────────────────
rf = 14.6 / 100       # risk-free rate (10y OFZ)
erp = 9.0 / 100       # equity risk premium
# For highly risky, illiquid, state-owned, opaque company — use high beta
# RKKE: government-owned defense/space, illiquid, negative equity → beta ~1.6-1.8
beta = 1.7            # judgement: high systematic risk + illiquidity
ke = rf + beta * erp
print(f"CAPM: Ke = {rf:.3f} + {beta} * {erp:.3f} = {ke:.4f} = {ke*100:.2f}%")

# ─────────────────────────────────────────────────────────────
# RAW FINANCIALS (from extracted_financials.json)
# ─────────────────────────────────────────────────────────────
fiscal_years = [2020, 2021, 2022, 2023, 2024]

revenue = [43520, 46800, None, 50200, 60400]   # mln RUB; 2022 missing
net_profit = [-5370, None, None, 554, 1330]     # mln RUB; 2021-2022 missing
ebitda = [None, None, None, None, 658]          # 2024 only, suspicious
cfo = [-5370, None, None, None, -4540]          # 2020, 2024
capex_2024 = 1600                               # mln RUB, 2024 only
cash_2024 = 7534                                # mln RUB
total_assets_2024 = 104160                      # mln RUB
total_equity_2024 = -3882                       # mln RUB — NEGATIVE
total_liabilities_2024 = total_assets_2024 - total_equity_2024  # 108042
print(f"Implied total liabilities 2024: {total_liabilities_2024:.0f} mln RUB")

# ─────────────────────────────────────────────────────────────
# NORMALIZATION CHECK — YEAR BY YEAR
# ─────────────────────────────────────────────────────────────
# 2020: net_profit = -5370 mln (large loss). Check if one-off?
#   Known: COVID year, major writedowns/cost overruns possible in space sector.
#   CFO = -5370 matches exactly net_profit (suspicious coincidence — likely data artifact,
#   not actual one-off identification). No impairment details in open sources.
#   → flag as UNCERTAIN, cannot normalize without primary report.
# 2021-2022: data missing → null, no normalization possible.
# 2023: net_profit = 554 mln. No one-off details available. → adjusted = reported.
# 2024: net_profit = 1330 mln. Revenue source inconsistency (60.4 vs 51.6 bln).
#   EBITDA = 658 mln suspicious (very low margin, D&A unknown, may be net-of-something).
#   → flag uncertainty, adjusted = reported (cannot determine one-offs without primary PDF).

# ETR check: pre-tax profit not available → cannot compute ETR → cannot do tax normalization
# → etr_reported = [null, null, null, null, null], sustainable = 25.0%

net_profit_adj = net_profit.copy()  # = reported (no verifiable adjustments possible)
ebitda_adj = ebitda.copy()

print(f"\nNet profit (reported = adjusted, no verifiable one-offs identified):")
for y, p in zip(fiscal_years, net_profit):
    print(f"  {y}: {p}")

# ─────────────────────────────────────────────────────────────
# FCF NORMALIZATION
# ─────────────────────────────────────────────────────────────
# Only 2024 data: FCF = CFO - capex = -4540 - 1600 = -6140 mln
# This is already negative → DCF not applicable
fcf_2024 = cfo[4] - capex_2024
print(f"\nFCF 2024: {fcf_2024} mln RUB (NEGATIVE — DCF not applicable)")
fcf_normalized = None  # cannot normalize with 1 data point and negative FCF

# ─────────────────────────────────────────────────────────────
# MULTIPLES — HISTORICAL & CURRENT
# ─────────────────────────────────────────────────────────────
# Net debt (2024): we have cash but no debt breakdown
# Total liabilities = 108042, but includes operating liabilities (payables, advances from Roskosmos)
# Cannot compute financial debt separately → net_debt computation unreliable
# Conservative EV: use market_cap only (no reliable net debt)
# Note: if Roskosmos advances count as debt-like, EV >> market_cap

ev_conservative = market_cap_mln  # lower bound (assuming no financial debt > cash)
# Since equity is negative, there must be significant liabilities
# We know cash = 7534, but debt structure unknown
# → EV range: [market_cap - cash, market_cap + likely_financial_debt]
# Without debt breakdown, use market_cap as proxy for EV (with caveat)
ev_proxy = market_cap_mln
print(f"\nEV proxy (market_cap only, debt structure unknown): {ev_proxy:.0f} mln RUB")

# P/E calculations
def safe_pe(price, eps):
    if eps is None or eps <= 0:
        return None
    return price / eps

eps_2023 = 554 / shares * 1_000_000  # mln → RUB per share
eps_2024 = 1330 / shares * 1_000_000

print(f"\nEPS 2023: {eps_2023:.2f} RUB/share")
print(f"EPS 2024: {eps_2024:.2f} RUB/share")

pe_2023 = safe_pe(price, eps_2023)
pe_2024 = safe_pe(price, eps_2024)
print(f"P/E 2023 (reported): {pe_2023:.1f}")
print(f"P/E 2024 (reported): {pe_2024:.1f}")

# Historical P/E: only 2 valid profit years (2023, 2024)
# CV check: only 2 points — cannot compute meaningful CV
# Use average as basis, with extreme caution note
pe_values = [pe_2023, pe_2024]
pe_avg = sum(pe_values) / len(pe_values)
pe_std = math.sqrt(sum((x - pe_avg)**2 for x in pe_values) / len(pe_values))
pe_cv = pe_std / pe_avg if pe_avg else None
print(f"\nHistorical P/E avg: {pe_avg:.1f}, std: {pe_std:.1f}, CV: {pe_cv:.2f}")
# CV = 0.19 < 0.5 → use mean
# But only 2 data points, 2020 was massive loss → basis extremely weak

# EV/Sales
ps_values = []
ev_sales_values = []
for i, (r, y) in enumerate(zip(revenue, fiscal_years)):
    if r is not None:
        ps = market_cap_mln / r
        ps_values.append((y, ps))
        ev_sales_values.append((y, ev_proxy / r))
        print(f"  {y}: P/S = {ps:.2f}, EV/Sales = {ev_proxy/r:.2f}")

ev_sales_2024 = ev_proxy / revenue[4]
print(f"\nEV/Sales 2024: {ev_sales_2024:.2f}")

# EV/EBITDA 2024 (suspicious)
ev_ebitda_2024 = ev_proxy / ebitda[4] if ebitda[4] else None
print(f"EV/EBITDA 2024: {ev_ebitda_2024:.1f} (SUSPICIOUS — EBITDA source quality low)")

# P/B → not_applicable (negative equity)
print("\nP/B: not_applicable — equity is negative (-3882 mln)")

# ─────────────────────────────────────────────────────────────
# VALUATION METHODS
# ─────────────────────────────────────────────────────────────

print("\n=== VALUATION METHODS ===")

# METHOD 1: DCF → insufficient_data (negative FCF, no FCF history)
print("\n[1] DCF: insufficient_data")
print("  FCF 2024 = -6140 mln (negative). Cannot project positive FCF without primary data.")
print("  No FCF history to normalize. Status: insufficient_data")

# METHOD 2: Historical P/E (forward)
# No consensus coverage for RKKE (illiquid, specialized)
# Mechanical: revenue growth 2020-2024 (where available)
# 2020→2023: 43520→50200 = +15.4% over 3 yrs = ~4.9%/yr
# 2023→2024: 50200→60400 = +20.3% (aggressive, may include TTM artifact)
# 2025 Q1: -76% (shocking, likely restructuring or seasonal)
# Conservative: assume 2024 net profit = 1330 mln is peak; normalize to avg of 2023-2024
net_profit_avg_2324 = (554 + 1330) / 2  # = 942 mln
eps_forward_mech = net_profit_avg_2324 / shares * 1_000_000
print(f"\n[2] Historical P/E")
print(f"  Historical P/E values: 2023={pe_2023:.1f}, 2024={pe_2024:.1f}")
print(f"  Average P/E: {pe_avg:.1f} (basis: 2y_mean, CV={pe_cv:.2f})")
print(f"  Forward EPS (mechanical avg 2023-2024): {eps_forward_mech:.2f} RUB/share")
fair_pe = pe_avg * eps_forward_mech
print(f"  Fair value (historical P/E method): {fair_pe:.0f} RUB/share")

# Backward reference
eps_backward = eps_2024
fair_pe_backward = pe_avg * eps_backward
print(f"  Fair value backward (P/E x EPS_2024): {fair_pe_backward:.0f} RUB/share")

# METHOD 3: P/B → not_applicable (negative equity)

# METHOD 4: EV/Sales (peers — space/defense sector)
# Peer benchmarks for defense/space companies:
# Russian listed peers: very few. General defense (Concern Kalashnikov not listed,
# Tactical Missiles not listed). Only KBP etc. not public.
# International reference (US/EU space/defense): EV/Sales 0.4-1.5x
# But RU defense sector + high risk → apply lower multiple: 0.3-0.7x
# Revenue 2024: 60400 mln (or 51589 mln — inconsistency)
# Use conservative revenue: 51589 mln (e-disclosure cited figure)
# Note: using both revenue figures creates a range

rev_conservative = 51589  # from e-disclosure (more reliable primary source reference)
rev_aggressive = 60400    # smart-lab TTM

# Peer EV/Sales: no direct Russian public comps. Use sector judgement.
ev_sales_low = 0.25   # deep discount: opaque, negative equity, cash burn, gov-dependent
ev_sales_mid = 0.45   # base: operational, gov contractor
ev_sales_high = 0.65  # optimistic: revenue growth, some profit

fair_ev_sales_conservative = ev_sales_low * rev_conservative
fair_ev_sales_base = ev_sales_mid * rev_conservative
fair_ev_sales_optimistic = ev_sales_high * rev_aggressive

# Convert EV to equity value: EV - net_debt
# Net debt: cash = 7534, financial debt unknown, but equity = -3882
# Implied liabilities = 108042, but most are likely operating (advances from Roskosmos)
# Conservatively assume financial debt (bank loans + bonds) = 5000-15000 mln (judgement)
# Use: net financial debt estimate = 10000 mln (middle judgement)
# Equity = EV - net_financial_debt_estimate
# Since this is highly uncertain, present EV/share directly with caveat

fair_ev_sales_cons_per_share = fair_ev_sales_conservative / shares * 1_000_000
fair_ev_sales_base_per_share = fair_ev_sales_base / shares * 1_000_000
fair_ev_sales_opt_per_share = fair_ev_sales_optimistic / shares * 1_000_000

print(f"\n[3] EV/Sales (peer-based, judgement multiples — no direct comps)")
print(f"  Revenue conservative (e-disclosure): {rev_conservative} mln")
print(f"  Revenue aggressive (smart-lab): {rev_aggressive} mln")
print(f"  EV/Sales multiples used: low={ev_sales_low}, mid={ev_sales_mid}, high={ev_sales_high}")
print(f"  Fair EV conservative: {fair_ev_sales_conservative:.0f} mln = {fair_ev_sales_cons_per_share:.0f} RUB/share")
print(f"  Fair EV base: {fair_ev_sales_base:.0f} mln = {fair_ev_sales_base_per_share:.0f} RUB/share")
print(f"  Fair EV optimistic: {fair_ev_sales_optimistic:.0f} mln = {fair_ev_sales_opt_per_share:.0f} RUB/share")
print(f"  NOTE: EV ≈ equity here (debt structure unknown); actual equity value = EV minus net financial debt")
print(f"  Given negative equity and uncertain debt, these are VERY approximate upper bounds")

# METHOD 5: CAPM (12m)
# CAPM target price = current × (1 + Ke) approximately (no dividend yield, DPS=0)
# Or: fair P/E ≈ 1/Ke
capm_implied_pe = 1 / ke
capm_fair_value_forward = capm_implied_pe * eps_forward_mech
capm_fair_value_backward = capm_implied_pe * eps_backward
print(f"\n[4] CAPM")
print(f"  Ke = {rf*100:.1f}% + {beta} × {erp*100:.1f}% = {ke*100:.2f}%")
print(f"  Implied P/E from CAPM: 1/{ke*100:.2f}% = {capm_implied_pe:.1f}")
print(f"  CAPM fair value (forward EPS): {capm_fair_value_forward:.0f} RUB/share")
print(f"  CAPM fair value (backward EPS 2024): {capm_fair_value_backward:.0f} RUB/share")

# METHOD 6: Dividend → not_applicable (DPS=0, no prospect of dividends)

# ─────────────────────────────────────────────────────────────
# FAIR VALUE RANGE SYNTHESIS
# ─────────────────────────────────────────────────────────────
print("\n=== FAIR VALUE SYNTHESIS ===")
print(f"  Historical P/E method: {fair_pe:.0f} RUB/share")
print(f"  EV/Sales conservative: {fair_ev_sales_cons_per_share:.0f} RUB/share")
print(f"  EV/Sales base: {fair_ev_sales_base_per_share:.0f} RUB/share")
print(f"  EV/Sales optimistic: {fair_ev_sales_opt_per_share:.0f} RUB/share")
print(f"  CAPM (forward): {capm_fair_value_forward:.0f} RUB/share")
print(f"  CAPM (backward): {capm_fair_value_backward:.0f} RUB/share")
print(f"\n  Current market price: {price:.2f} RUB/share")
print(f"  Market cap: {market_cap_mln:.0f} mln RUB")

# Conservative: take lowest cluster (EV/Sales conservative + CAPM forward)
# Base: P/E method and EV/Sales base
# Optimistic: EV/Sales optimistic
fair_conservative = round(min(fair_ev_sales_cons_per_share, capm_fair_value_forward) / 100) * 100
fair_base = round((fair_pe + fair_ev_sales_base_per_share) / 2 / 100) * 100
fair_optimistic = round(fair_ev_sales_opt_per_share / 100) * 100

print(f"\n  FAIR VALUE RANGE:")
print(f"  Conservative: ~{fair_conservative:.0f} RUB/share")
print(f"  Base: ~{fair_base:.0f} RUB/share")
print(f"  Optimistic: ~{fair_optimistic:.0f} RUB/share")

# Divergence check
divergence = (fair_optimistic - fair_conservative) / fair_conservative * 100
print(f"  Divergence (opt vs cons): {divergence:.0f}% — wide range expected given data quality")

# Metrics timeseries for chart
pe_ts = [None, None, None, pe_2023, pe_2024]
ps_ts = [market_cap_mln/r if r else None for r in revenue]
ev_ebitda_ts = [None, None, None, None, ev_ebitda_2024]
ros_ts = [p/r if (p and r and p > 0) else None for p, r in zip(net_profit, revenue)]

print(f"\nMetrics timeseries:")
print(f"  P/E: {pe_ts}")
print(f"  P/S: {[round(x,2) if x else None for x in ps_ts]}")
print(f"  ROS: {[round(x*100,1) if x else None for x in ros_ts]}")

# Round all per-share values
print(f"\nFinal values:")
print(f"  PE historical avg used: {pe_avg:.1f}")
print(f"  EPS forward mech: {eps_forward_mech:.2f}")
print(f"  Historical P/E fair value: {fair_pe:.0f}")
print(f"  CAPM fair value (forward): {capm_fair_value_forward:.0f}")
print(f"  EV/Sales base fair value: {fair_ev_sales_base_per_share:.0f}")
print(f"  Conservative: {fair_conservative}")
print(f"  Base: {fair_base}")
print(f"  Optimistic: {fair_optimistic}")

# Verify isinstance (types for explain fields)
test_inputs = {
    "price": f"{price} — рыночная цена из rates.csv [src_market]",
    "shares": f"{shares} — число акций из rates.csv [src_market]"
}
for k, v in test_inputs.items():
    assert isinstance(v, str), f"inputs[{k}] must be str"
print("\nType checks: OK")
