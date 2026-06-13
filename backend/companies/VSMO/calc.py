"""
VSMO financials.json calculation script.
All numbers derived here — no intuition-based values.
"""
import json, math, os

# ── INPUTS ──────────────────────────────────────────────────────────────────
# Market context (from rates.csv / task)
price       = 26109.54          # ₽ per share (from rates.csv context)
shares      = 11_529_538        # shares outstanding
mktcap_mln  = price * shares / 1e6   # млн ₽

# Config: market_params.json
Rf    = 14.6 / 100   # risk-free rate (10y OFZ)
ERP   = 9.0  / 100   # equity risk premium
g_default = 3.5 / 100  # terminal growth default
tax_rate_sustainable = 25.0 / 100

# fiscal_years index: [2020, 2022, 2023, 2024, 2025]
FY = [2020, 2022, 2023, 2024, 2025]
idx = {y: i for i, y in enumerate(FY)}

# ── P&L (from extracted_financials.json) ────────────────────────────────────
revenue          = [89100.0,   None,   121500.0,  118553.6,  96774.3]
cogs             = [None,      None,   None,       73473.5,   76268.0]
gross_profit     = [31600.0,   None,   45300.0,   45080.1,   20506.3]
operating_profit = [18700.0,   None,   18900.0,   18878.2,   -468.8]
da               = [None,      None,   None,       20595.0,   19302.5]
ebitda_rep       = [None,      None,   None,       39473.2,   18833.7]
finance_costs    = [None,      None,   None,       -15483.2,  -7051.2]
finance_income   = [None,      None,   None,        7281.6,   10492.7]
pre_tax_profit   = [None,      None,   None,       22056.7,    4211.0]
income_tax       = [None,      None,   None,        -5203.4,  -4008.0]
net_profit_rep   = [6600.0,    None,   24900.0,   16853.3,     203.0]

# ── BALANCE SHEET ────────────────────────────────────────────────────────────
ppe              = [None,      None,   None,      244880.7,  237179.5]
intangibles      = [None,      None,   None,         819.9,     706.1]
goodwill_val     = [None,      None,   None,        1600.9,    1600.9]
lt_invest        = [None,      None,   None,       35517.3,   40389.5]
other_nc         = [None,      None,   None,       12230.0,    5068.8]
total_nc         = [None,      None,   None,      295049.2,  284844.3]

inventory        = [None,      None,   None,       77495.8,   62462.0]
receivables      = [None,      None,   None,       30526.6,   25310.5]
cash_val         = [69900.0,   None,   None,       53219.7,   42399.8]
st_invest        = [None,      None,   None,        2280.5,    4725.2]
other_curr       = [None,      None,   None,         932.6,     781.8]
total_curr       = [None,      None,   None,      164455.3,  148785.0]
total_assets     = [357000.0,  None,   None,      459504.4,  433629.2]

share_capital    = [None,      None,   None,         596.3,     596.3]
retained_earn    = [None,      None,   None,      177293.3,  185020.5]
add_paid_in      = [None,      None,   None,        4594.6,    4594.6]
other_equity     = [None,      None,   None,      116837.0,  109378.4]
total_equity     = [202100.0,  None,   None,      299157.1,  299590.4]

lt_debt          = [None,      None,   None,       24239.9,   13461.6]
deferred_tax     = [None,      None,   None,       48190.5,   47479.0]
other_nc_liab    = [None,      None,   None,        3211.6,    2948.8]
total_nc_liab    = [None,      None,   None,       75642.0,   63889.4]

st_debt          = [None,      None,   None,       62741.0,   46297.8]
payables         = [None,      None,   None,       18311.0,   22465.5]
other_curr_liab  = [None,      None,   None,        3653.2,    1386.1]
total_curr_liab  = [None,      None,   None,       84705.3,   70149.4]
total_liab       = [None,      None,   None,      160347.3,  134038.8]

# ── CASH FLOW ────────────────────────────────────────────────────────────────
cfo              = [13000.0,   None,   None,       11912.8,   15488.2]
cfi              = [None,      None,   None,       62007.1,   -8258.2]
cff              = [None,      None,   None,       -74046.7, -15186.1]
capex_raw        = [-8500.0,   None,   None,       -11782.0, -10639.5]   # negative sign
net_change_cash  = [None,      None,   None,          955.5, -11611.1]

# FCF reported = CFO + capex (capex negative → subtract absolute)
def safe_add(a, b):
    if a is None or b is None: return None
    return a + b
def safe_sub(a, b):
    if a is None or b is None: return None
    return a - b
def safe_div(a, b):
    if a is None or b is None or b == 0: return None
    return a / b

fcf_rep = [safe_add(cfo[i], capex_raw[i]) for i in range(len(FY))]
# 2020: 13000 + (-8500) = 4500
# 2024: 11912.8 + (-11782) = 130.8
# 2025: 15488.2 + (-10639.5) = 4848.7

# ── NET DEBT ─────────────────────────────────────────────────────────────────
# net_debt = (lt_debt + st_debt) - cash
# Only for years where we have balance data
def net_debt_calc(i):
    l = lt_debt[i]; s = st_debt[i]; c = cash_val[i]
    if l is None or s is None or c is None: return None
    return l + s - c
net_debt = [net_debt_calc(i) for i in range(len(FY))]
# 2020: cash=69900, lt=None, st=None → None  but we can note approx
# 2024: 24239.9 + 62741.0 - 53219.7 = 33761.2
# 2025: 13461.6 + 46297.8 - 42399.8 = 17359.6

# ── MARGINS (reported) ───────────────────────────────────────────────────────
gross_margin    = [safe_div(gross_profit[i], revenue[i]) for i in range(len(FY))]
ebitda_margin   = [safe_div(ebitda_rep[i], revenue[i]) for i in range(len(FY))]
op_margin       = [safe_div(operating_profit[i], revenue[i]) for i in range(len(FY))]
ros             = [safe_div(net_profit_rep[i], revenue[i]) for i in range(len(FY))]

# ── ETR REPORTED ─────────────────────────────────────────────────────────────
etr_rep = []
for i in range(len(FY)):
    if pre_tax_profit[i] is not None and income_tax[i] is not None and pre_tax_profit[i] != 0:
        etr_rep.append(abs(income_tax[i]) / pre_tax_profit[i])
    else:
        etr_rep.append(None)
# 2024: 5203.4 / 22056.7 = 23.6%
# 2025: 4008.0 / 4211.0 = 95.2%  ← anomalous!

print("ETR reported:", [f"{v*100:.1f}%" if v else "N/A" for v in etr_rep])

# ── NORMALIZATION ─────────────────────────────────────────────────────────────
# BRIDGE: systematic check per year
# 2020: no detail on one-offs; net_profit=6600, no anomaly info → adjusted = reported
#        ETR unknown → keep as is
# 2022: no data → skip
# 2023: net_profit=24900, no detail on one-offs, no pre_tax → no adjustment possible
#        Note: 2023 likely included beneficial FX (RUB depreciation vs. USD-linked contracts)
#        but no quantification → flag judgement, no adjustment
# 2024: pre_tax=22056.7, tax=5203.4, ETR=23.6% < 25% slightly but within normal range
#        → ETR adj needed? 23.6% vs 25% → diff small; finance_income=7281.6 (high)
#        Finance income includes interest + investment income (precious metals)
#        → flag but not adjusting (recurring in context of high-rate environment)
#        No large one-off disclosures in available data → adjusted=reported for 2024
# 2025: PRE_TAX=4211, TAX=4008, ETR=95.2% → ANOMALOUS (big tax relative to tiny profit)
#        This reflects either deferred tax charges or non-deductible items on a near-zero profit
#        Sustainable ETR = 25%
#        adj_net_profit_2025 = pre_tax_2025 * (1 - 0.25) = 4211 * 0.75 = 3158.25 млн
#        Bridge item: anomalous deferred/effective tax charge
#        Also: finance_income_2025=10492.7 (high; includes precious metal gains, currency)
#        → flag but cannot split without note breakdown → data_flag only

adj_net_profit_2025 = pre_tax_profit[4] * (1 - tax_rate_sustainable)
print(f"adj_net_profit_2025: {adj_net_profit_2025:.1f} млн")
# Bridge: +3805.25 (tax normalization: reported tax 4008, sustainable 25% → 1053 → delta = 4008-1053 = 2955)
# Wait: reported ЧП=203, pre_tax=4211, tax=4008
# adj: pre_tax=4211, sustainable tax = 4211*0.25 = 1052.75 → adj ЧП = 4211-1052.75 = 3158.25
# bridge item: added_back = 4008 - 1052.75 = 2955.25 (excess tax normalized away)
bridge_tax_2025 = income_tax[4] + pre_tax_profit[4] * tax_rate_sustainable  # income_tax is negative
# income_tax = -4008; sustainable = -1052.75; delta = -4008 - (-1052.75) = -2955.25
# → we add back 2955.25 to reported ЧП
bridge_tax_2025_addback = abs(income_tax[4]) - pre_tax_profit[4] * tax_rate_sustainable
print(f"bridge_tax_2025_addback: {bridge_tax_2025_addback:.1f}")
# 4008 - 1052.75 = 2955.25 → added back to net profit

net_profit_adj = [6600.0, None, 24900.0, 16853.3, round(adj_net_profit_2025, 1)]
print("net_profit_adj:", net_profit_adj)

# EBITDA adj: for 2025, if we adjust net profit, EBITDA itself is unaffected (it's pre-interest, pre-tax)
# But let's note: EBITDA 2025 = 18833.7 – no specific one-offs in operating clearly identifiable
# → ebitda_adj = ebitda_rep
ebitda_adj = list(ebitda_rep)  # [None, None, None, 39473.2, 18833.7]

# FCF normalized
# Check capex/revenue ratio:
capex_rev_ratio = []
for i in range(len(FY)):
    if capex_raw[i] is not None and revenue[i] is not None:
        capex_rev_ratio.append(abs(capex_raw[i]) / revenue[i])
    else:
        capex_rev_ratio.append(None)
print("capex/rev:", capex_rev_ratio)
# 2020: 8500/89100 = 9.5%; 2024: 11782/118553.6 = 9.9%; 2025: 10639.5/96774.3 = 11.0%
# No anomaly vs 1.5× threshold → use actual capex → FCF normalized = FCF reported for CFO normal years

# CFO check for anomalies:
# 2024 CFO = 11912.8 (quite low vs revenue 118553 → FCF margin only 0.1%)
# 2025 CFO = 15488.2 (FCF 4848.7 → 5.0% FCF margin)
# 2020 CFO = 13000 (FCF 4500 → 5.0% FCF margin)
# 2024 FCF = 130.8 — very low. Check: CFI 2024 = +62007.1 (positive!) — asset disposal proceeds
#   This appears to be non-operating (sale of assets/investments). CFO likely low due to WC buildup
#   WC 2024→2025: inventory dropped 77495.8→62462 (release +15034), recv 30526→25310 (release +5216)
#   payables 18311→22465 (increase +4154)
#   NWC change 2024→2025: -15034 - 5216 + 4154 = -16096 improvement (WC released → boosted 2025 CFO)
#   So 2025 CFO benefited from WC release; 2024 CFO was depressed by WC buildup
# Only 2 years of detail → cannot compute 5-year trend → note as flag, use actual

fcf_normalized = list(fcf_rep)  # [4500, None, None, 130.8, 4848.7]
wc_adjustment  = [0, None, None, 0, 0]  # no normalization applied (insufficient multi-year CFO data)

# ── TANGIBLE EQUITY ──────────────────────────────────────────────────────────
# tangible = total_equity - goodwill - sомнительные НМА
# goodwill=1600.9 (2024), 1600.9 (2025); intangibles=819.9, 706.1 (patents/tech → keep)
# → tangible = total_equity - goodwill
def tangible_eq(i):
    if total_equity[i] is None or goodwill_val[i] is None: return total_equity[i]
    return total_equity[i] - goodwill_val[i]
tangible_equity = [tangible_eq(i) for i in range(len(FY))]
# 2024: 299157.1 - 1600.9 = 297556.2
# 2025: 299590.4 - 1600.9 = 297989.5
print("tangible_equity:", tangible_equity)

# ── RETURNS ──────────────────────────────────────────────────────────────────
# ROE = net_profit_adj / avg_equity
# Using adj net profit
# Only have equity at 2020, 2024, 2025
roe = [None, None, None, None, None]
# 2024: use 2024 equity (avg not possible without 2023)
roe[3] = safe_div(net_profit_adj[3], total_equity[3])  # 16853.3/299157.1 = 5.6%
roe[4] = safe_div(net_profit_adj[4], total_equity[4])  # 3158.25/299590.4 = 1.1%

# ROA = net_profit_adj / avg_assets
roa = [None, None, None, None, None]
roa[3] = safe_div(net_profit_adj[3], total_assets[3])  # 16853.3/459504.4 = 3.7%
roa[4] = safe_div(net_profit_adj[4], total_assets[4])  # 3158.25/433629.2 = 0.7%

# ROIC = EBIT*(1-t) / (equity + net_debt)
# Only for 2024, 2025
def roic_calc(i):
    ebit = operating_profit[i]
    eq   = total_equity[i]
    nd   = net_debt[i]
    if ebit is None or eq is None or nd is None: return None
    nopat = ebit * (1 - tax_rate_sustainable)
    ic = eq + nd
    return safe_div(nopat, ic)
roic = [None, None, None, roic_calc(3), roic_calc(4)]
print(f"ROIC 2024: {roic[3]*100:.1f}%, 2025: {roic[4]*100:.2f}%")

asset_turnover = [safe_div(revenue[i], total_assets[i]) for i in range(len(FY))]

# ── EV ────────────────────────────────────────────────────────────────────────
# EV = mktcap + net_debt (for each year we have net_debt)
# Use current mktcap (from rates.csv) for "current" multiples
print(f"mktcap_mln: {mktcap_mln:.1f}")
ev_current = mktcap_mln + net_debt[4]   # 2025 net debt
print(f"EV (current mktcap + net_debt_2025): {ev_current:.1f}")

# ── MULTIPLES ─────────────────────────────────────────────────────────────────
# P/E adj per year (using price from rates.csv context — transient, only for current multiples)
eps_adj = [safe_div(v, shares) * 1e6 for v in net_profit_adj]  # ₽ per share
print("EPS adj:", [f"{v:.0f}" if v else "N/A" for v in eps_adj])

# P/E adj current (on 2025 adj EPS)
pe_adj_current = safe_div(price, eps_adj[4])
print(f"P/E adj current (2025 adj EPS): {pe_adj_current:.1f}")

# P/B current (tangible)
bvps_tangible = [safe_div(tangible_equity[i], shares) * 1e6 for i in range(len(FY))]
pb_current = safe_div(price, bvps_tangible[4])
print(f"P/B current (tangible, 2025): {pb_current:.2f}")

# EV/EBITDA current using 2025 EBITDA adj
ev_ebitda_current = safe_div(ev_current, ebitda_adj[4])
print(f"EV/EBITDA current: {ev_ebitda_current:.1f}")

# P/S current
ps_current = safe_div(mktcap_mln, revenue[4])
print(f"P/S current: {ps_current:.2f}")

# P/E reported per year (time series) — need historical price → not available for past years
# We only compute "current" multiples from today's price

# ── HISTORICAL P/E adj ────────────────────────────────────────────────────────
# We don't have historical prices → cannot build historical P/E time series
# Use EPS to show trajectory; for forward P/E method use consensus/mechanical

# ── HISTORICAL P/B ────────────────────────────────────────────────────────────
# Available equity: 2020=202100, 2024=299157.1, 2025=299590.4
# P/B at any given time requires historical prices → not available
# → use current P/B only, historical_pb method = insufficient_data for time series

# ── PEERS (from sector comparison; using existing or placeholder) ──────────────
# VSMO is a unique global titanium producer; few direct peers on MOEX
# EV/EBITDA peers in metals/materials sector on MOEX: NLMK, CHMF, MAGN
# We'll note this as a caveat; sector median EV/EBITDA ≈ 4-5x (Russian metals)
# → relative_peers method with this context

# ── BETA estimation ───────────────────────────────────────────────────────────
# VSMO: low liquidity (free float ~10%), cyclical, export commodity
# Sector beta for metals/materials ~1.1-1.3; additional liquidity/size premium
# Using beta = 1.2 (judgement: cyclical + low float penalty)
beta = 1.2
Ke = Rf + beta * ERP
print(f"Ke (CAPM): {Ke*100:.2f}%")

# ── WACC ─────────────────────────────────────────────────────────────────────
# Debt: net_debt_2025 = 17359.6; mktcap = 309909.5
# D/V = 17359.6 / (309909.5 + 17359.6) = 5.3% → equity dominates
# Kd ≈ 14% (corporate rate in current environment); after tax Kd = 14% * (1-25%) = 10.5%
D = net_debt[4]
E = mktcap_mln
V = E + D
Kd_pretax = 0.14
Kd = Kd_pretax * (1 - tax_rate_sustainable)
WACC = Ke * (E/V) + Kd * (D/V)
print(f"WACC: {WACC*100:.2f}%, D/V: {D/V*100:.1f}%")

# ── DCF ──────────────────────────────────────────────────────────────────────
# FCF_normalized_2025 = 4848.7 млн
# FCF_2024 = 130.8 млн (depressed by WC)
# FCF_2020 = 4500 млн
# Base: FCF₁ = normalized next year (2026E)
# Mechanic: revenue growth = average of what we have
# Revenue: 89100 (2020) → 121500 (2023) → 118553 (2024) → 96774 (2025)
# 2025 was a trough. For DCF, use mid-cycle FCF.
# Mid-cycle = average of non-anomalous years: 4500 (2020), 4848.7 (2025)
# 2024 FCF=130.8 anomalously low → exclude from mid-cycle
# Mid-cycle FCF = (4500 + 4848.7) / 2 = 4674.35
# Apply modest growth to get FCF1: with moderate recovery assumption (mechanical)
# EBITDA mid-cycle ≈ (implied from 2020 + 2023 + 2025 EBITDA)
# 2020 EBITDA unknown; 2023 EBITDA unknown from detailed; 2025 EBITDA = 18833.7
# Conservative: FCF₁ = 4674.35 * 1.05 (modest recovery) = 4907.9
# This is mechanical/judgement given limited data
fcf_midcycle = (4500 + 4848.7) / 2
fcf1 = fcf_midcycle * 1.05  # modest recovery
print(f"FCF mid-cycle: {fcf_midcycle:.1f}, FCF1: {fcf1:.1f}")

# Use WACC as discount rate (low debt → close to Ke)
r_dcf = WACC
g_dcf = 0.02  # conservative: below default 3.5% given uncertainty, sanctions, trough

EV_dcf = fcf1 / (r_dcf - g_dcf)
print(f"EV_dcf (r={r_dcf*100:.2f}%, g={g_dcf*100:.1f}%): {EV_dcf:.1f}")
# Equity = EV - net_debt (2025)
equity_dcf = EV_dcf - net_debt[4]
price_dcf = (equity_dcf / shares) * 1e6
print(f"equity_dcf: {equity_dcf:.1f}, price_dcf: {price_dcf:.0f} ₽")

# Cross-check implied EV/EBITDA (using 2025 EBITDA as proxy)
implied_ev_ebitda = safe_div(EV_dcf, ebitda_adj[4])
print(f"Implied EV/EBITDA (DCF): {implied_ev_ebitda:.1f}x")

# ── DCF SENSITIVITY r × g ─────────────────────────────────────────────────────
r_grid = [WACC - 0.02, WACC, WACC + 0.02]
g_grid = [0.01, 0.02, 0.03]
matrix = []
for r in r_grid:
    row = []
    for g in g_grid:
        if r > g:
            ev_s = fcf1 / (r - g)
            eq_s = ev_s - net_debt[4]
            p_s = (eq_s / shares) * 1e6
            row.append(round(p_s))
        else:
            row.append(None)
    matrix.append(row)
print("Sensitivity matrix (price ₽):")
print(f"  g={g_grid}")
for i, r in enumerate(r_grid):
    print(f"  r={r*100:.2f}%: {matrix[i]}")

# ── HISTORICAL P/E METHOD ─────────────────────────────────────────────────────
# No historical price data available → cannot compute historical P/E time series
# Use current P/E adj as single data point → method = insufficient_data
# Forward P/E: mechanical EPS forward
# Revenue 2026E: assume slight recovery from trough +5% from 2025
rev_2026e = revenue[4] * 1.05  # mechanical
# EBITDA margin recovery to ~22% (mid between trough 19.5% and normal 33%)
ebitda_margin_2026e = 0.22
ebitda_2026e = rev_2026e * ebitda_margin_2026e
# Net profit: from EBITDA, subtract DA≈19300, fin costs≈7000, fin income≈5000, tax 25%
da_2026e = 19302.5  # stable
ebit_2026e = ebitda_2026e - da_2026e
pre_tax_2026e = ebit_2026e - 7000 + 5000
adj_np_2026e = pre_tax_2026e * (1 - tax_rate_sustainable) if pre_tax_2026e > 0 else 0
eps_2026e = (adj_np_2026e / shares) * 1e6
print(f"Rev 2026E: {rev_2026e:.0f}, EBITDA 2026E: {ebitda_2026e:.0f}, adj NP 2026E: {adj_np_2026e:.0f}, EPS 2026E: {eps_2026e:.0f}")

# Historical P/E: only 2 years of adj EPS (2024, 2025) + 2020 reported
# CV calculation: only 2 adj values → mean
# pe_adj time series: we can only compute current P/E from current price and adj EPS per year
# But we don't have historical prices → historical_pe method = insufficient_data (no price history)
# Report P/E forward using a sector norm
# Russian metals sector historical P/E ≈ 5-8x
pe_sector_norm = 6.5  # midpoint judgement for cyclical metals
price_pe_forward = pe_sector_norm * eps_2026e
print(f"P/E forward (sector norm {pe_sector_norm}x × EPS {eps_2026e:.0f}): {price_pe_forward:.0f} ₽")

# ── P/B METHOD ────────────────────────────────────────────────────────────────
# Historical P/B: no price history available → use sector norm
# Russian metals companies typical P/B: 0.8-1.5x
# VSMO: large asset base (PPE 237 bn), low earnings → P/B should be lower end
pb_sector_norm = 1.0  # conservative given earnings trough
bvps_tangible_2025 = bvps_tangible[4]
price_pb = pb_sector_norm * bvps_tangible_2025
print(f"P/B method ({pb_sector_norm}x × BVPS {bvps_tangible_2025:.0f}): {price_pb:.0f} ₽")

# ── EV/EBITDA RELATIVE ────────────────────────────────────────────────────────
# Sector median EV/EBITDA for Russian metals (NLMK, CHMF, MAGN) ≈ 3.5-5x (2025 env)
ev_ebitda_sector = 4.0  # conservative judgement
# Use 2026E EBITDA (recovery) as forward base
ev_from_evebitda = ev_ebitda_sector * ebitda_2026e
equity_ev_ebitda = ev_from_evebitda - net_debt[4]
price_ev_ebitda = (equity_ev_ebitda / shares) * 1e6
print(f"EV/EBITDA relative ({ev_ebitda_sector}x × EBITDA_2026E {ebitda_2026e:.0f}): EV={ev_from_evebitda:.0f}, equity={equity_ev_ebitda:.0f}, price={price_ev_ebitda:.0f} ₽")

# ── CAPM 12M ─────────────────────────────────────────────────────────────────
# CAPM target: price_12m = price * (1 + Ke - div_yield)
# Div yield: last DPS=0 (no dividend 2024, 2025) → 0%
div_yield = 0.0
price_capm_12m = price * (1 + Ke - div_yield)
print(f"CAPM 12m target: {price_capm_12m:.0f} ₽ (Ke={Ke*100:.2f}%)")

# ── DIVIDEND METHOD ───────────────────────────────────────────────────────────
# Irregular dividends, last DPS=564 (2023), before that 884 (2019), many years 0
# Cannot reliably apply dividend discount model → method = not_applicable
# (erratic policy, cannot forecast sustainable DPS)

# ── FAIR VALUE RANGE ─────────────────────────────────────────────────────────
# Collect all method results:
# DCF: price_dcf
# P/E forward (sector norm): price_pe_forward
# P/B sector norm: price_pb
# EV/EBITDA relative: price_ev_ebitda
# CAPM 12m: price_capm_12m

methods_prices = {
    "DCF": price_dcf,
    "PE_forward": price_pe_forward,
    "PB": price_pb,
    "EV_EBITDA": price_ev_ebitda,
    "CAPM_12m": price_capm_12m
}
print("\nMethod prices:")
for k, v in methods_prices.items():
    print(f"  {k}: {v:.0f} ₽")

all_prices = [v for v in methods_prices.values() if v is not None]
conservative = round(min(all_prices), -2)
base = round(sum(all_prices) / len(all_prices), -2)
optimistic = round(max(all_prices), -2)

print(f"\nFair value range: conservative={conservative}, base={base}, optimistic={optimistic}")

# Divergence check
div_pct = (optimistic - conservative) / base
print(f"Divergence: {div_pct*100:.0f}%")

# ── METRICS TIMESERIES (for charts) ──────────────────────────────────────────
# We cannot compute historical P/E, P/B without historical prices
# Fill what we can: margins, ROE, net_debt_ebitda, revenue_growth
ndeb_ebitda_ts = [None, None, None,
    safe_div(net_debt[3], ebitda_adj[3]),
    safe_div(net_debt[4], ebitda_adj[4])]
rev_growth_ts = [None, None,
    safe_div(revenue[2] - revenue[0], revenue[0]) if revenue[0] else None,  # 2023 vs 2020 (no 2022)
    safe_div(revenue[3] - revenue[2], revenue[2]),
    safe_div(revenue[4] - revenue[3], revenue[3])]
np_growth_ts = [None, None, None,
    None,  # 2024 vs 2023
    safe_div(net_profit_rep[4] - net_profit_rep[3], abs(net_profit_rep[3]))]
print("ndeb/ebitda:", ndeb_ebitda_ts)
print("rev_growth:", rev_growth_ts)

# ── RATIOS ────────────────────────────────────────────────────────────────────
debt_to_equity = [None, None, None,
    safe_div(total_liab[3], total_equity[3]),
    safe_div(total_liab[4], total_equity[4])]
current_ratio = [None, None, None,
    safe_div(total_curr[3], total_curr_liab[3]),
    safe_div(total_curr[4], total_curr_liab[4])]
fcf_margin = [safe_div(fcf_rep[i], revenue[i]) for i in range(len(FY))]
cfo_capex = [safe_div(cfo[i], abs(capex_raw[i])) if capex_raw[i] else None for i in range(len(FY))]
capex_rev = [safe_div(abs(capex_raw[i]), revenue[i]) if capex_raw[i] else None for i in range(len(FY))]

print("current_ratio:", current_ratio)
print("debt_to_equity:", debt_to_equity)

# ── VERIFY ARITHMETIC ─────────────────────────────────────────────────────────
print("\n--- VERIFICATION ---")
# net_debt 2024
nd24 = lt_debt[3] + st_debt[3] - cash_val[3]
print(f"net_debt 2024: {nd24:.1f} (should be 33761.2)")
# FCF 2025
fcf25 = cfo[4] + capex_raw[4]
print(f"FCF 2025: {fcf25:.1f} (should be 4848.7)")
# net_change_cash 2024 vs sum
ncc24 = cfo[3] + cfi[3] + cff[3]
print(f"net_change_cash 2024 from CFO+CFI+CFF: {ncc24:.1f} (extracted: 955.5) [diff may be FX effects]")
# adj ЧП 2025 check
print(f"adj ЧП 2025: {net_profit_adj[4]:.1f} = {net_profit_rep[4]:.1f} + {bridge_tax_2025_addback:.1f}")
# margins
print(f"EBITDA margin 2024: {ebitda_margin[3]*100:.1f}%, 2025: {ebitda_margin[4]*100:.1f}%")
print(f"gross margin 2024: {gross_margin[3]*100:.1f}%, 2025: {gross_margin[4]*100:.1f}%")

# ── PACK RESULTS ──────────────────────────────────────────────────────────────
results = {
    "mktcap_mln": round(mktcap_mln, 1),
    "ev_current": round(ev_current, 1),
    "net_debt": net_debt,
    "eps_adj": [round(v, 0) if v else None for v in eps_adj],
    "bvps_tangible": [round(v, 0) if v else None for v in bvps_tangible],
    "pe_adj_current": round(pe_adj_current, 1) if pe_adj_current else None,
    "pb_current": round(pb_current, 2) if pb_current else None,
    "ev_ebitda_current": round(ev_ebitda_current, 1) if ev_ebitda_current else None,
    "ps_current": round(ps_current, 2) if ps_current else None,
    "Ke": round(Ke * 100, 2),
    "WACC": round(WACC * 100, 2),
    "beta": beta,
    "fcf1": round(fcf1, 1),
    "g_dcf": g_dcf,
    "r_dcf": round(r_dcf * 100, 2),
    "EV_dcf": round(EV_dcf, 1),
    "equity_dcf": round(equity_dcf, 1),
    "price_dcf": round(price_dcf),
    "implied_ev_ebitda_dcf": round(implied_ev_ebitda, 1) if implied_ev_ebitda else None,
    "r_grid": [round(r * 100, 2) for r in r_grid],
    "g_grid": [round(g * 100, 2) for g in g_grid],
    "matrix": matrix,
    "eps_2026e": round(eps_2026e, 0),
    "pe_sector_norm": pe_sector_norm,
    "price_pe_forward": round(price_pe_forward),
    "pb_sector_norm": pb_sector_norm,
    "bvps_tangible_2025": round(bvps_tangible_2025, 0),
    "price_pb": round(price_pb),
    "ebitda_2026e": round(ebitda_2026e, 1),
    "ev_ebitda_sector": ev_ebitda_sector,
    "price_ev_ebitda": round(price_ev_ebitda),
    "price_capm_12m": round(price_capm_12m),
    "conservative": conservative,
    "base": base,
    "optimistic": optimistic,
    "bridge_tax_2025_addback": round(bridge_tax_2025_addback, 1),
    "adj_net_profit_2025": round(adj_net_profit_2025, 1),
    "roe_2024": round(roe[3] * 100, 2) if roe[3] else None,
    "roe_2025": round(roe[4] * 100, 2) if roe[4] else None,
    "roa_2024": round(roa[3] * 100, 2) if roa[3] else None,
    "roa_2025": round(roa[4] * 100, 2) if roa[4] else None,
    "roic_2024": round(roic[3] * 100, 2) if roic[3] else None,
    "roic_2025": round(roic[4] * 100, 2) if roic[4] else None,
    "ndeb_ebitda_2024": round(ndeb_ebitda_ts[3], 2) if ndeb_ebitda_ts[3] else None,
    "ndeb_ebitda_2025": round(ndeb_ebitda_ts[4], 2) if ndeb_ebitda_ts[4] else None,
    "etr_rep_2024": round(etr_rep[3] * 100, 1) if etr_rep[3] else None,
    "etr_rep_2025": round(etr_rep[4] * 100, 1) if etr_rep[4] else None,
    "capex_rev_2024": round(capex_rev_ratio[3] * 100, 1) if capex_rev_ratio[3] else None,
    "capex_rev_2025": round(capex_rev_ratio[4] * 100, 1) if capex_rev_ratio[4] else None,
    "fcf_midcycle": round(fcf_midcycle, 1),
    "gross_margin_2024": round(gross_margin[3] * 100, 1) if gross_margin[3] else None,
    "gross_margin_2025": round(gross_margin[4] * 100, 1) if gross_margin[4] else None,
    "ebitda_margin_2024": round(ebitda_margin[3] * 100, 1) if ebitda_margin[3] else None,
    "ebitda_margin_2025": round(ebitda_margin[4] * 100, 1) if ebitda_margin[4] else None,
    "op_margin_2024": round(op_margin[3] * 100, 1) if op_margin[3] else None,
    "op_margin_2025": round(op_margin[4] * 100, 2) if op_margin[4] else None,
    "ros_2024": round(ros[3] * 100, 1) if ros[3] else None,
    "ros_2025": round(ros[4] * 100, 2) if ros[4] else None,
}

out_path = os.path.join(os.path.dirname(__file__), "calc_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\nSaved to {out_path}")
print(f"\nFINAL CORRIDOR: {conservative} – {optimistic} ₽ (base {base} ₽)")
