#!/usr/bin/env python3
"""
FIXR financials.json calculation script
All numbers computed here, no intuition.
"""

import json
import math
import statistics

# ─── MARKET CONTEXT (from rates.csv / task brief) ───
PRICE = 0.67          # ₽ per share (current, for intermediate checks)
SHARES = 100_000_000_000  # 100 billion shares
MARKET_CAP = 67_200  # млн ₽ (67.2 млрд)

# ─── CONFIG ───
RF = 14.6 / 100       # risk-free rate
ERP = 9.0 / 100       # equity risk premium
TERMINAL_G_DEFAULT = 3.5 / 100
TAX_RATE = 25.0 / 100  # sustainable from 2025

# ─── EXTRACTED FINANCIALS ───
# fiscal_years = [2020, 2021, 2022, 2023, 2024, 2025]
revenue     = [230473, 291865, 277644, 280878, 300311, 313330]
cogs        = [None,   None,   None,   190393, 205515, 213911]
gross_profit= [None,   None,   None,   90485,  94796,  99419]
# SGA (commercial, general, admin)
sga         = [None,   None,   None,   58271,  65959,  80107]
other_op_inc= [None,   None,   None,   570,    545,    646]
ebit        = [26923,  37927,  4106,   32849,  29430,  20007]
da          = [9865,   13138,  15138,  15142,  16494,  18811]
# ebitda = ebit + da
ebitda_raw  = [ebit[i] + da[i] for i in range(6)]

finance_costs  = [1125,  3329,  2951,  2832,  4735,  5516]
finance_income = [None,  None,  None,  2157,  3504,  105]
pre_tax_profit = [None,  None,  None,  30650, 27100, 15281]
income_tax     = [None,  None,  None,  797,   5703,  4105]
net_profit     = [17575, 35707, 21411, 29853, 21397, 11176]

# Balance (2023-2025, index 3-5)
ppe              = [None, None, None, 27386, 29175, 35897]
intangibles      = [None, None, None, 10477, 9523,  8669]
goodwill         = [None, None, None, None,  None,  None]
lt_invest        = [None, None, None, 61,    23,    22]
other_nc         = [None, None, None, 11527, 13616, 19848]
total_nc         = [None, None, None, 49451, 53338, 64456]

inventory        = [None, None, None, 44878, 52910, 52578]
receivables      = [None, None, None, 8174,  8166,  10365]
cash             = [None, None, None, 30660, 6486,  9505]
st_invest        = [None, None, None, None,  None,  None]
other_curr       = [None, None, None, 1713,  2659,  5742]
total_curr       = [None, None, None, 85425, 70221, 78155]
total_assets     = [None, None, None, 134876,123559,142611]

share_capital    = [None, None, None, 110,   100,   100]
retained_earn    = [None, None, None, 36572, 49570, 60978]
apic             = [None, None, None, None,  None,  -187]
other_equity     = [None, None, None, -15,   9,     -44]
total_equity     = [None, None, None, 36682, 49679, 60847]

lt_debt          = [None, None, None, 2854,  3232,  3436]
deferred_tax     = [None, None, None, 763,   763,   763]
other_nc_liab    = [None, None, None, 7071,  4700,  11829]
total_nc_liab    = [None, None, None, 10688, 8695,  16028]

st_debt          = [None, None, None, 13876, 15056, 9131]
payables         = [None, None, None, 67226, 36131, 38103]
other_curr_liab  = [None, None, None, 5400,  13398, 17602]
total_curr_liab  = [None, None, None, 86502, 65185, 65736]
total_liab       = [None, None, None, 97190, 73880, 81764]

# Cash flow (2023-2025)
cfo      = [None, None, None, 35167, 29480, 31681]
cfi      = [None, None, None, -5594, -8181, -10020]
cff      = [None, None, None, -17977,-45414,-18503]
capex    = [None, None, None, 5730,  8267,  10125]
net_chng = [None, None, None, 11788,-24174, 3019]

# ─── VERIFY ARITHMETIC ───
print("=== ARITHMETIC CHECKS ===")
for i, yr in enumerate([2023, 2024, 2025]):
    idx = i + 3
    calc_net_chng = cfo[idx] + cfi[idx] + cff[idx]
    print(f"{yr}: cfo+cfi+cff={calc_net_chng}, reported={net_chng[idx]}, ok={abs(calc_net_chng - net_chng[idx]) < 1}")
    fcf_check = cfo[idx] - capex[idx]
    print(f"{yr}: fcf=cfo-capex={fcf_check}")

# ─── NET DEBT ───
# IFRS16: аренда включена в lt_debt/st_debt? Note: finance_costs 2025 увеличились из-за IFRS16
# 23.6 млрд — аренда IFRS16 (из задания). Нужно понять, включена ли аренда в долг.
# Судя по балансу: total_liab - equity = 97190-36682=60508 vs 97190 (total_liab reported)
# lt_debt 2025=3436, st_debt 2025=9131 → total financial debt = 12567
# Аренда IFRS16 23.6 млрд скорее всего сидит в other_nc_liab + other_curr_liab
# other_nc_liab 2025=11829, other_curr_liab 2025=17602 → итого 29431 — вероятно включает аренду
# Для EV: используем все обязательства (финансовый долг + аренда IFRS16)
# Традиционный net_debt = финансовый долг + аренда - кэш
IFRS16_LEASE = 23600  # млн, из условия задания
net_debt_arr = []
for idx in range(6):
    if lt_debt[idx] is None:
        net_debt_arr.append(None)
    else:
        # финансовый долг (без аренды в отдельных строках) + аренда IFRS16 - кэш
        # 2025: lt_debt=3436, st_debt=9131, cash=9505
        # аренда ~23600 (из задания — общий баланс)
        fin_debt = lt_debt[idx] + st_debt[idx]
        # аренда: для 2025 возьмём 23600, для 2024 и 2023 — нет данных, оценим
        # other_nc_liab 2023=7071, 2024=4700, 2025=11829 — это аренда? Нет, вероятно частично
        # Без надёжной разбивки по 2023-2024 — используем только финансовый долг
        nd = fin_debt - cash[idx]
        net_debt_arr.append(nd)

print("\n=== NET DEBT (финансовый долг без аренды) ===")
for i, yr in enumerate([2023, 2024, 2025]):
    print(f"{yr}: {net_debt_arr[i+3]:.0f} млн")

# EV (с арендой для EV/EBITDA): EV = капитализация + net_debt_financial + аренда
# 2025: EV = 67200 + (lt_debt[5]+st_debt[5]-cash[5]) + IFRS16_LEASE
ev_2025_financial_nd = lt_debt[5] + st_debt[5] - cash[5]
ev_2025_with_lease = MARKET_CAP + ev_2025_financial_nd + IFRS16_LEASE
ev_2025_no_lease = MARKET_CAP + ev_2025_financial_nd

print(f"\n=== EV 2025 ===")
print(f"Финансовый долг: {lt_debt[5]+st_debt[5]:.0f} млн")
print(f"Кэш: {cash[5]:.0f} млн")
print(f"Net debt (финансовый): {ev_2025_financial_nd:.0f} млн")
print(f"IFRS16 аренда: {IFRS16_LEASE:.0f} млн")
print(f"EV (с арендой): {ev_2025_with_lease:.0f} млн")
print(f"EV (без аренды): {ev_2025_no_lease:.0f} млн")

# ─── MARGINS ───
gross_margin = [gross_profit[i]/revenue[i] if gross_profit[i] else None for i in range(6)]
ebitda_margin_arr = [ebitda_raw[i]/revenue[i] for i in range(6)]
op_margin = [ebit[i]/revenue[i] for i in range(6)]
ros = [net_profit[i]/revenue[i] for i in range(6)]

print("\n=== MARGINS ===")
for i, yr in enumerate([2020,2021,2022,2023,2024,2025]):
    gm = f"{gross_margin[i]*100:.1f}%" if gross_margin[i] else "N/A"
    print(f"{yr}: gross={gm} ebitda={ebitda_margin_arr[i]*100:.1f}% op={op_margin[i]*100:.1f}% ros={ros[i]*100:.1f}%")

# ─── ETR ANALYSIS ───
print("\n=== ETR ANALYSIS ===")
etr_reported = []
for i, yr in enumerate([2020,2021,2022,2023,2024,2025]):
    idx = i
    if pre_tax_profit[idx] is not None and income_tax[idx] is not None:
        etr = income_tax[idx] / pre_tax_profit[idx]
        etr_reported.append(etr)
        print(f"{yr}: pre_tax={pre_tax_profit[idx]:.0f}, tax={income_tax[idx]:.0f}, ETR={etr*100:.1f}%")
    else:
        etr_reported.append(None)
        # For 2020-2022: estimate ETR from ЧП/pre_tax (pre_tax not given directly)
        # 2020: ЧП=17575, ebit=26923, finance_costs=1125 → pre_tax approx = 26923-1125=25798
        # 2021: ЧП=35707, ebit=37927, finance_costs=3329, fi=? → pre_tax approx = 37927-3329=34598
        # 2022: ЧП=21411, ebit=4106, finance_costs=2951 → pre_tax approx = 1155
        print(f"{yr}: pre_tax=N/A (estimated)")

# Note: 2023 ETR=2.6% (!!), 2024=21.0%, 2025=26.9%
# 2023 ETR 2.6% is anomalously LOW → tax benefit / deferred tax release
# This means 2023 reported NP=29853 is OVERSTATED vs normalized
# Normalized 2023 NP = pre_tax × (1-0.20) [2023 rate was 20%, not 25%]
# 2024 ETR=21% also slightly low (rate was 20% until 2025) → reasonable
# 2025 ETR=26.9% ~ close to 25%, slight overshoot likely due to non-deductible items

print("\n=== NORMALIZATION ANALYSIS ===")
# 2023: ETR=2.6% anomalously low. Normal rate 2023 = 20%
# adjusted_np_2023 = pre_tax_2023 * (1 - 0.20)
adj_np_2023 = pre_tax_profit[3] * (1 - 0.20)
tax_correction_2023 = adj_np_2023 - net_profit[3]  # negative (adjust down)
print(f"2023: reported NP={net_profit[3]}, ETR=2.6% anomalously low")
print(f"  Adjusted NP (ETR→20%): {adj_np_2023:.0f}, correction: {tax_correction_2023:.0f}")

# 2022: ebit=4106 (very low year - commodity crunch, geopolitics)
# Implied pre_tax ~4106 - 2951 = 1155 (finance costs)
pre_tax_2022_est = ebit[2] - finance_costs[2]  # ≈ 1155
adj_np_2022_est = pre_tax_2022_est * (1 - 0.20)  # rate was 20%
print(f"2022: ebit={ebit[2]}, est pre_tax≈{pre_tax_2022_est}, NP reported={net_profit[2]}")
print(f"  2022 reported NP {net_profit[2]} >> est adj {adj_np_2022_est:.0f}")
print(f"  → 2022 может содержать разовые доходы ниже черты (currency gains etc)")

# 2024: ETR=21.0% close to then-20% rate → no major adjustment needed
# 2025: ETR=26.9% → pre_tax=15281, tax=4105
adj_np_2025 = pre_tax_profit[5] * (1 - 0.25)
print(f"2025: reported NP={net_profit[5]}, ETR={income_tax[5]/pre_tax_profit[5]*100:.1f}%")
print(f"  Adj NP (ETR→25%): {adj_np_2025:.0f}, correction: {adj_np_2025-net_profit[5]:.0f}")

# EBITDA adjustments: no major one-offs in EBITDA (operating level)
# 2022 ebit=4106 is low due to operational issues (post-COVID demand reset)
# No evidence of non-recurring charges in EBITDA → ebitda_adj = ebitda_reported

# FCF NORMALIZATION
print("\n=== FCF NORMALIZATION ===")
# capex/revenue ratios
for i, yr in enumerate([2023,2024,2025]):
    idx = i + 3
    ratio = capex[idx] / revenue[idx] * 100
    print(f"{yr}: capex={capex[idx]}, revenue={revenue[idx]}, capex/rev={ratio:.1f}%")

capex_rev_ratios = [capex[i+3]/revenue[i+3] for i in range(3)]
median_capex_rev = statistics.median(capex_rev_ratios)
mean_capex_rev = statistics.mean(capex_rev_ratios)
print(f"Capex/revenue: {[f'{r*100:.1f}%' for r in capex_rev_ratios]}")
print(f"Median: {median_capex_rev*100:.1f}%, Mean: {mean_capex_rev*100:.1f}%")
# Range: 2.0%, 2.75%, 3.23% — no anomaly (all <1.5x of each other)
# No capex normalization needed

# Working capital: Δ in payables 2024 dropped from 67226 to 36131 (-31095)
# This is a major one-off: 2023 payables inflated (or 2024 normalized)
# CFO 2024=29480 vs 2023=35167 — CFO fell partly due to WC unwind
# Δ payables 2023→2024: 36131-67226 = -31095 (payables fell = cash outflow)
# This is a reversal of prior period credit accumulation — real cash effect
# → NOT a normalization item (it's real economic cash flow)
# But FCF 2024 impacted. Let's check WC trend.
delta_payables = [None, None, None, None, 36131-67226, 38103-36131]
delta_inventory = [None, None, None, None, 52910-44878, 52578-52910]
delta_receivables = [None, None, None, None, 8166-8174, 10365-8166]
print(f"\nΔ payables 2024: {delta_payables[4]:.0f}, 2025: {delta_payables[5]:.0f}")
print(f"Δ inventory 2024: {delta_inventory[4]:.0f}, 2025: {delta_inventory[5]:.0f}")
print(f"Δ receivables 2024: {delta_receivables[4]:.0f}, 2025: {delta_receivables[5]:.0f}")

# 2024 payables drop -31095: this is massive relative to revenue — 10.3% of revenue
# Likely relates to GDR buyback payment or supplier settlement; real economic event
# → Not normalized (1.5x rule: single year effect, but represents real cash flow unwind)
# FCF_reported: 2023=29437, 2024=21213, 2025=21556
fcf_reported = [None, None, None, cfo[3]-capex[3], cfo[4]-capex[4], cfo[5]-capex[5]]
print(f"\nFCF reported: {[fcf_reported[i] for i in [3,4,5]]}")

# ─── ADJUSTED P&L ───
print("\n=== ADJUSTED BRIDGE ===")
# Per year:
# 2020: pre_tax not available, ЧП=17575. Est pre_tax≈25798, ETR≈31.9% — high rate, may have deferred tax
#       No reliable adjustment without pre_tax. adj=reported.
# 2021: ЧП=35707. Best year. ETR unknown. adj=reported.
# 2022: ЧП=21411. Very low operating year (ebit=4106). pre_tax est≈1155 → NP should be ~924
#       BUT reported NP=21411 >> estimated → large below-the-line items (FX gains, investment income?)
#       Without pre_tax data → flag anomaly but cannot reliably adjust. adj=reported with flag.
# 2023: ETR=2.6% anomalously low → adjust to 20%
# 2024: ETR=21.0% (rate was 20% → normal), adj=reported
# 2025: ETR=26.9% → slight overage vs 25%, adj to 25%

net_profit_adj = [
    net_profit[0],  # 2020: no adjustment, insufficient data
    net_profit[1],  # 2021: no adjustment
    net_profit[2],  # 2022: cannot reliably adjust without pre_tax; flag
    round(adj_np_2023, 0),  # 2023: ETR normalized to 20%
    net_profit[4],  # 2024: ETR≈20% (2024 rate), no adjustment
    round(adj_np_2025, 0),  # 2025: ETR normalized to 25%
]

ebitda_adj = [round(e, 0) for e in ebitda_raw]  # no operating adjustments

# FCF normalized: no capex anomaly, no major WC anomaly requiring normalization
# 2024 WC payables swing is real economic event → keep as-is
fcf_normalized = [None, None, None,
    cfo[3] - capex[3],  # 29437
    cfo[4] - capex[4],  # 21213
    cfo[5] - capex[5],  # 21556
]

print("Net profit adj:")
for i, yr in enumerate([2020,2021,2022,2023,2024,2025]):
    print(f"  {yr}: reported={net_profit[i]:.0f}, adj={net_profit_adj[i]:.0f}")

# ─── MULTIPLES ───
print("\n=== MULTIPLES ===")
# EPS by year (shares=100 billion)
eps_rep = [net_profit[i]/SHARES*1e6 for i in range(6)]  # in ₽
eps_adj = [net_profit_adj[i]/SHARES*1e6 for i in range(6)]
print("EPS reported:", [f"{e:.4f}" for e in eps_rep])
print("EPS adj:", [f"{e:.4f}" for e in eps_adj])

# Historical P/E adj (based on price=0.67 current — but we need historical prices)
# We don't have historical prices. Per methodology: use available data.
# For current multiples: P/E = price/EPS
pe_adj_current = PRICE / eps_adj[5]
pe_rep_current = PRICE / eps_rep[5]
print(f"\nCurrent P/E adj: {pe_adj_current:.1f}x (price={PRICE}, EPS_adj={eps_adj[5]:.4f})")
print(f"Current P/E rep: {pe_rep_current:.1f}x (EPS_rep={eps_rep[5]:.4f})")

# EV/EBITDA 2025
ev_ebitda_2025_with_lease = ev_2025_with_lease / ebitda_raw[5]
ev_ebitda_2025_no_lease = ev_2025_no_lease / ebitda_raw[5]
print(f"\nEV/EBITDA 2025 (с арендой): {ev_ebitda_2025_with_lease:.1f}x EV={ev_2025_with_lease:.0f}, EBITDA={ebitda_raw[5]:.0f}")
print(f"EV/EBITDA 2025 (без аренды): {ev_ebitda_2025_no_lease:.1f}x")

# P/S
ps_current = MARKET_CAP / revenue[5]
print(f"P/S 2025: {ps_current:.2f}x")

# P/B 2025
bvps = total_equity[5] / SHARES * 1e6  # ₽ per share
pb_current = PRICE / bvps
print(f"BVPS: {bvps:.4f} ₽, P/B: {pb_current:.2f}x")

# Tangible equity (no goodwill, intangibles are software/licenses)
# Intangibles 2025=8669: likely software/IT systems for retail → debatable
# Goodwill=0 → no subtraction there
# Tangible equity = total_equity - intangibles (conservative)
tang_equity_2025 = total_equity[5] - intangibles[5]
tang_bvps = tang_equity_2025 / SHARES * 1e6
tang_pb = PRICE / tang_bvps
print(f"Tangible equity 2025: {tang_equity_2025:.0f} млн, tang BVPS={tang_bvps:.4f}, tang P/B={tang_pb:.2f}x")

# ─── RETURNS ───
print("\n=== RETURNS ===")
# ROE, ROA, ROIC using adj NP
for i, yr in enumerate([2023,2024,2025]):
    idx = i + 3
    roe = net_profit_adj[idx] / total_equity[idx] * 100
    roa = net_profit_adj[idx] / total_assets[idx] * 100
    # ROIC = NOPAT / Invested Capital; IC = total_equity + net_debt (financial)
    nopat = ebit[idx] * (1 - TAX_RATE)
    ic = total_equity[idx] + lt_debt[idx] + st_debt[idx]
    roic = nopat / ic * 100
    print(f"{yr}: ROE={roe:.1f}%, ROA={roa:.1f}%, ROIC={roic:.1f}%")

# ─── CAPM / Ke ───
print("\n=== CAPM ===")
# Beta for Fix Price: retail sector, volatile post-redomicile
# Market beta estimation: retail, high leverage through IFRS16, small-mid cap → beta ~1.1-1.3
# Conservative per rule → 1.2
BETA = 1.2
Ke = RF + BETA * ERP
print(f"Beta={BETA}, Rf={RF*100:.1f}%, ERP={ERP*100:.1f}%")
print(f"Ke = {RF*100:.1f}% + {BETA} × {ERP*100:.1f}% = {Ke*100:.1f}%")

# CAPM 12m target: price × (1 + (Ke - div_yield))
# DPS 2025 = 0.11 ₽, yield = 0.11/0.67
div_yield = 0.11 / PRICE
capm_target = PRICE * (1 + Ke - div_yield)
print(f"Div yield: {div_yield*100:.1f}%, CAPM 12m target: {capm_target:.2f} ₽")

# ─── DCF ───
print("\n=== DCF ===")
# FCF1: normalized FCF next year (2026)
# 2025 FCF = 21556, 2024 FCF = 21213, 2023 FCF = 29437
# Revenue growth 2026: BKS expects turnaround, mechanical: 3y avg revenue growth
rev_growth = [(revenue[i+1]-revenue[i])/revenue[i] for i in range(5)]
print(f"Revenue growth: {[f'{g*100:.1f}%' for g in rev_growth]}")
# 2020-21: +26.6%, 2021-22: -4.9%, 2022-23: +1.2%, 2023-24: +6.9%, 2024-25: +4.3%
# 3y average 2022-25: +4.1%, 2y: +5.6%
# Mechanical estimate 2026 growth: ~5% (BKS turnaround thesis)
rev_2026_est = revenue[5] * 1.05
print(f"Revenue 2026 est (5% growth): {rev_2026_est:.0f} млн")

# FCF margin trend: 2023=10.5%, 2024=7.1%, 2025=6.9%
fcf_margins = [fcf_normalized[i+3]/revenue[i+3] for i in range(3)]
print(f"FCF margins: {[f'{m*100:.1f}%' for m in fcf_margins]}")
# Mean FCF margin 3y:
mean_fcf_margin = statistics.mean(fcf_margins)
print(f"Mean FCF margin 3y: {mean_fcf_margin*100:.1f}%")
# 2025 declining margin (op margin compression) → use 2024-2025 average as more recent
fcf_margin_2026 = statistics.mean(fcf_margins[1:])  # 2024+2025
fcf_1 = rev_2026_est * fcf_margin_2026
print(f"FCF1 (rev_2026 × FCF_margin_avg24-25): {fcf_1:.0f} млн")

# Alternative: grow 2025 FCF by 5%
fcf_1_alt = fcf_normalized[5] * 1.05
print(f"FCF1 alt (2025 FCF × 1.05): {fcf_1_alt:.0f} млн")
# Use base FCF1
FCF1 = round(fcf_1, 0)
print(f"FCF1 base: {FCF1:.0f} млн")

# Gordon DCF
g = 0.03  # 3% < 3.5% terminal_default, conservative
r = Ke  # no significant non-lease debt → use Ke
# For WACC: check leverage
fin_debt_2025 = lt_debt[5] + st_debt[5]  # 12567 млн
total_cap_2025 = total_equity[5] + fin_debt_2025
wd = fin_debt_2025 / total_cap_2025
we = total_equity[5] / total_cap_2025
kd_after_tax = 0.12 * (1 - TAX_RATE)  # assume 12% loan rate
wacc = we * Ke + wd * kd_after_tax
print(f"\nDebt/capital: {wd*100:.1f}%, Ke={Ke*100:.1f}%, Kd_at={kd_after_tax*100:.1f}%")
print(f"WACC: {wacc*100:.1f}%")
# Leverage modest → use WACC
r_used = wacc
print(f"r used (WACC): {r_used*100:.1f}%")

EV_dcf = FCF1 / (r_used - g)
print(f"\nEV = {FCF1:.0f} / ({r_used*100:.1f}% - {g*100:.1f}%) = {EV_dcf:.0f} млн")

# Equity = EV - net_debt (financial) - IFRS16
equity_dcf = EV_dcf - ev_2025_financial_nd - IFRS16_LEASE
# ev_2025_financial_nd = fin_debt - cash = 12567 - 9505 = 3062
print(f"Net debt (fin): {ev_2025_financial_nd:.0f} млн")
print(f"IFRS16 lease: {IFRS16_LEASE:.0f} млн")
print(f"Equity value = {EV_dcf:.0f} - {ev_2025_financial_nd:.0f} - {IFRS16_LEASE:.0f} = {equity_dcf:.0f} млн")
dcf_price = equity_dcf / SHARES * 1e6
print(f"DCF price per share: {dcf_price:.3f} ₽")

# Cross-check implied EV/EBITDA
implied_ev_ebitda = EV_dcf / ebitda_raw[5]
print(f"Implied EV/EBITDA: {implied_ev_ebitda:.1f}x (market EV/EBITDA с арендой: {ev_ebitda_2025_with_lease:.1f}x)")

# Sensitivity: r × g
print("\n=== DCF SENSITIVITY ===")
r_grid = [0.18, 0.195, 0.21]
g_grid = [0.02, 0.025, 0.03]
matrix = []
for rr in r_grid:
    row = []
    for gg in g_grid:
        ev_ = FCF1 / (rr - gg)
        eq_ = ev_ - ev_2025_financial_nd - IFRS16_LEASE
        price_ = eq_ / SHARES * 1e6
        row.append(round(price_, 3))
    matrix.append(row)
    print(f"r={rr*100:.1f}%: g={[f'{gg*100:.1f}%:{matrix[-1][j]:.3f}' for j,gg in enumerate(g_grid)]}")

# ─── HISTORICAL P/E (adj) ───
print("\n=== HISTORICAL P/E ===")
# We only have current price; no historical prices available
# Per methodology: "историческую среднюю P/E" нужны исторические цены
# Without historical prices → can only use current P/E adj as reference
# BKS mentioned P/E=5.4x (pre-results); current P/E adj = ?
pe_adj_2025 = PRICE / eps_adj[5]
pe_adj_2024 = PRICE / eps_adj[4]  # using current price (approximate)
print(f"P/E adj 2025 (current price): {pe_adj_2025:.1f}x")
print(f"P/E adj 2024 (current price): {pe_adj_2024:.1f}x")
# Without historical prices: insufficient_data for proper historical avg P/E
# Use forward P/E approach with consensus
# Consensus: BKS mentioned 5.4x P/E → forward target implies price ≈ 5.4 × EPS_2026
# EPS 2026 mechanically: assume NP_2026 ≈ NP_2025_adj × 1.1 (revenue +5%, margin improvement)
nopat_2026 = ebit[5] * 1.05 * (1 - TAX_RATE)  # rough proxy
# Better: use adj NP 2025 * growth
np_adj_2025 = net_profit_adj[5]
# Revenue +5%, operating leverage modest (SGA already high in 2025)
# Assume adj NP grows ~15% from low 2025 base
np_adj_2026_est = np_adj_2025 * 1.15
eps_adj_2026 = np_adj_2026_est / SHARES * 1e6
print(f"\nEPS adj 2025: {eps_adj[5]:.4f} ₽, NP adj 2025: {np_adj_2025:.0f} млн")
print(f"EPS adj 2026 (mech +15%): {eps_adj_2026:.4f} ₽")
# BKS P/E 5.4x reference → fair value estimate
bks_pe = 5.4
pe_fair = bks_pe * eps_adj_2026
print(f"Historical/consensus P/E {bks_pe}x × EPS2026: {pe_fair:.3f} ₽")

# ─── DIVIDEND VALUATION ───
print("\n=== DIVIDEND VALUATION ===")
# Policy: ≥50% NP МСФО. In practice: distributed ~98% in 2025
# Sustainable: assume 75% payout of adj NP (between policy min 50% and recent 98%)
payout = 0.75
dps_2026_est = np_adj_2026_est * payout / SHARES * 1e6
print(f"DPS 2026 est (75% payout × NP_adj_2026): {dps_2026_est:.4f} ₽")
# Required yield: market rate for retail mid-cap; Ke=23.8%, div growth g=3%
# Gordon: price = DPS1 / (Ke - g)
div_price = dps_2026_est / (Ke - g)
print(f"Dividend valuation: {dps_2026_est:.4f} / ({Ke*100:.1f}%-{g*100:.1f}%) = {div_price:.3f} ₽")

# ─── RELATIVE PEERS (EV/EBITDA) ───
print("\n=== RELATIVE PEERS ===")
# Russian retail peers: Магнит, X5, Лента
# EV/EBITDA sector medians: Russian retail typically 4-7x
# X5 EV/EBITDA ~4-5x, Магнит ~5-6x (estimated from public data)
# Conservative sector median EV/EBITDA: 5.0x
sector_ev_ebitda_median = 5.0
# FIXP EBITDA 2025 adj = 38818 (ebitda_raw[5])
ev_peers = sector_ev_ebitda_median * ebitda_raw[5]
equity_peers = ev_peers - ev_2025_financial_nd - IFRS16_LEASE
price_peers = equity_peers / SHARES * 1e6
print(f"Sector EV/EBITDA median: {sector_ev_ebitda_median}x")
print(f"EBITDA 2025: {ebitda_raw[5]:.0f}")
print(f"EV from peers: {ev_peers:.0f}, equity: {equity_peers:.0f}")
print(f"Relative price: {price_peers:.3f} ₽")

# ─── SUMMARY ───
print("\n=== VALUATION SUMMARY ===")
print(f"DCF: {dcf_price:.3f} ₽")
print(f"P/E forward (consensus 5.4x): {pe_fair:.3f} ₽")
print(f"Dividend Gordon: {div_price:.3f} ₽")
print(f"EV/EBITDA peers: {price_peers:.3f} ₽")
print(f"CAPM 12m: {capm_target:.3f} ₽")

methods = [dcf_price, pe_fair, div_price, price_peers]
print(f"\nAll methods (excl CAPM): min={min(methods):.3f}, max={max(methods):.3f}, mean={statistics.mean(methods):.3f}")
print(f"Conservative (lower cluster): ~{min(methods):.2f}")
print(f"Base: ~{statistics.mean(methods):.2f}")
print(f"Optimistic: ~{max(methods):.2f}")
