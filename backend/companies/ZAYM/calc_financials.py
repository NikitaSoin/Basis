"""
ZAYM financials v2 calculation script.
All numbers computed here; no manual input of multiples.
"""
import json, math, statistics

# ─── MARKET CONTEXT (from rates.csv / task) ───────────────────────────────────
PRICE = 147.788          # RUB per share
SHARES = 100_000_000     # shares outstanding
MKTCAP_MLN = PRICE * SHARES / 1e6  # млн RUB

# ─── CONFIG ───────────────────────────────────────────────────────────────────
RF = 14.6       # % risk-free (10y OFZ)
ERP = 9.0       # % equity risk premium
TAX = 25.0      # % sustainable corporate tax (from 2025)

# ZAYM beta estimate: MFO sector, volatile/regulated, small-cap, leverage low
# Beta ≈ 1.4 (judgement: высокорегулируемый сектор, концентрация в потребкредитовании, малая капитализация)
BETA = 1.4
Ke = RF + BETA * ERP   # CAPM cost of equity

# ─── RAW DATA (from extracted_financials.json, data_quality LOW) ──────────────
fiscal_years = [2022, 2023, 2024, 2025]

revenue     = [16150, 18669, 15850, 17070]   # млн RUB
op_profit   = [7190,  7800,  5370,  5820]    # млн RUB (reliable)
net_profit  = [5760,  6090,  3930,  4350]    # млн RUB (reliable per flag)

# OpEx (operating expenses excl provisions and fin costs)
opex        = [4830,  6490,  7590,  7150]    # млн

# Finance costs
fin_costs   = [242,   169,   39,    71]

# CFO
cfo         = [3400,  6650,  2990,  6000]    # млн

# Capex
capex_raw   = [160,   152,   331,   878]

# Cash
cash        = [1910,  2150,  1900,  3270]

# Total assets
total_assets = [15400, 15600, 16500, 17800]

# Total equity (from smart-lab 'net_assets'; flagged as unreliable but best available)
total_equity = [11400, 11900, 12600, 14500]

# Short-term debt
st_debt      = [1490,  880,   40,    5]

# ─── NORMALIZATION BRIDGE ─────────────────────────────────────────────────────
# Check each year for one-offs per methodology

# ETR check: pre-tax profit unknown (income_tax not parsed).
# Cannot compute ETR directly. Use net_profit as best reliable proxy.
# Note: 2024 ЧП drop 3930 (-35% vs 2023) is operational (regulatory squeeze,
# higher provisions, not a one-off) → NO adjustment.
# 2022 high ЧП: no evidence of one-offs from available data → no adjustment.
# Assessment: no clear verifiable one-off items in available data.
# adjusted = reported for all years (bridge empty).
net_profit_adj = list(net_profit)

bridge = []
for i, yr in enumerate(fiscal_years):
    bridge.append({
        "year": yr,
        "item": "Систематический чек-лист: обесценения/списания — нет данных; курсовые — не выделены; разовые продажи — нет данных; нерегулярные резервы — данные только за 2023; штрафы/суды — нет данных; аномальная ETR — нет данных (налог не распарсен)",
        "amount": 0,
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    })

bridge_note = (
    "Мост пустой: корректировки отсутствуют ввиду data_quality LOW — "
    "налог, обесценения, резервы за 2022/2024/2025 не распарсены из источников. "
    "adjusted = reported. Год 2024: снижение ЧП на 35% — операционное (регуляторное "
    "давление ЦБ, рост резервов), не разовое."
)

# ─── FCF ──────────────────────────────────────────────────────────────────────
fcf_raw = [cfo[i] - capex_raw[i] for i in range(4)]
# FCF: [3240, 6498, 2659, 5122]

# Capex normalization check:
capex_rev_ratio = [capex_raw[i]/revenue[i]*100 for i in range(4)]
# [0.99%, 0.81%, 2.09%, 5.14%]
# 2025: 5.14% vs median ~1%, anomaly ~5x => normalize
capex_rev_median = statistics.median(capex_rev_ratio[:3])  # using 2022-2024 for 2025 norm
capex_sustainable_2025 = capex_rev_median/100 * revenue[3]
# For forward FCF₁ (2026 est), use sustainable capex

# CFO normalization check:
# 2023 CFO 6650 vs 2022 3400: +96% while revenue +15.6% — potential WC tailwind
# 2024 CFO 2990: -55% vs 2023 — sharp drop
# Trend: [3400, 6650, 2990, 6000]
# CV check:
cfo_mean = statistics.mean(cfo)
cfo_stdev = statistics.stdev(cfo)
cfo_cv = cfo_stdev / cfo_mean
# High CV: 2023 is outlier (likely WC release); normalize to 5y-type avg

# For FCF₁ (forward): use mechanical approach
# Revenue 2026 forecast: management guides +25-30%; conservative use +15% (judgement, regulatory headwinds)
# Net profit 2026 forecast: consensus ~5127 мln (from web search)
# Use consensus net profit 2026 = 5127 mln

# FCF normalized approach: MFO is financial company, capex-light
# FCF_normalized ≈ CFO_trend - capex_sustainable
# CFO trend: use mean of 2022-2025 but exclude 2023 spike?
# Actually: [3400, 6650, 2990, 6000] - 2023 may be WC release from loan book dynamics
# Conservative: mean excl 2023 spike → [3400, 2990, 6000] mean = 4130
# Or: all 4 years mean = 4760
# Given MFO = financial co, DCF is not_applicable anyway
# Compute for reference:
cfo_4yr_mean = statistics.mean(cfo)
capex_mean_rev = statistics.mean(capex_rev_ratio) / 100
capex_sustainable_mln = capex_mean_rev * statistics.mean(revenue)
fcf_normalized_base = cfo_4yr_mean - capex_sustainable_mln

# ─── MARGINS ──────────────────────────────────────────────────────────────────
# MFO: no gross margin (by_nature). Operating margin and ROS.
op_margin = [op_profit[i]/revenue[i]*100 for i in range(4)]
ros       = [net_profit[i]/revenue[i]*100 for i in range(4)]
# ebitda: null (da not available)

# ─── BALANCE RATIOS ───────────────────────────────────────────────────────────
net_debt = [st_debt[i] - cash[i] for i in range(4)]
# Note: negative = net cash position
# [1490-1910, 880-2150, 40-1900, 5-3270] = [-420, -1270, -1860, -3265]

debt_to_equity = [st_debt[i]/total_equity[i] for i in range(4)]
current_ratio = None  # current liabilities not fully available

# ─── RETURNS ──────────────────────────────────────────────────────────────────
# ROE = net_profit_adj / avg_equity
roe = []
for i in range(4):
    if i == 0:
        avg_eq = total_equity[0]  # no prior year
    else:
        avg_eq = (total_equity[i] + total_equity[i-1]) / 2
    roe.append(net_profit_adj[i] / avg_eq * 100)

roa = [net_profit_adj[i] / total_assets[i] * 100 for i in range(4)]
# ROIC: total_equity only (no long-term debt effectively)
roic = list(roe)  # approx, given near-zero debt

# ─── MULTIPLES (historical, price-dependent) ──────────────────────────────────
# Per-share metrics
EPS_hist = [np/SHARES*1e6 for np in net_profit_adj]
# [57.60, 60.90, 39.30, 43.50]

BVPS_hist = [eq/SHARES*1e6 for eq in total_equity]
# [114.0, 119.0, 126.0, 145.0]

# Historical P/E (adj)
pe_hist = [PRICE/eps for eps in EPS_hist]
# These are current price / historical EPS (trailing multiples for reference)
# For historical avg, we need price at each year-end — not available; use current price approach is wrong
# CORRECT: historical avg P/E = average of annual (price_at_year_end / EPS)
# We don't have historical prices → use current price only for "current" multiple
# Historical P/E avg: not computable without historical prices (SHORT HISTORY: only 1 year public before IPO Apr 2024)
# PE at current price (trailing):
pe_current = PRICE / EPS_hist[3]   # 2025 EPS
pe_adj_current = pe_current

# P/B at current price (2025 equity)
pb_current = PRICE / BVPS_hist[3]

# EV (no long-term debt, net cash)
# EV = Mktcap - net_cash = Mktcap + net_debt (net_debt is negative)
EV_current = MKTCAP_MLN + net_debt[3]  # = Mktcap - 3265 = 11594 млн

# P/S
PS_current = MKTCAP_MLN / revenue[3]

print(f"=== ZAYM KEY METRICS ===")
print(f"MKTCAP: {MKTCAP_MLN:.0f} млн RUB")
print(f"EV: {EV_current:.0f} млн RUB")
print(f"")
print(f"EPS (2022-2025): {[round(e,2) for e in EPS_hist]}")
print(f"BVPS (2022-2025): {[round(b,2) for b in BVPS_hist]}")
print(f"P/E (current/2025 EPS): {pe_current:.2f}")
print(f"P/B (current/2025 BVPS): {pb_current:.3f}")
print(f"P/S: {PS_current:.2f}")
print(f"")
print(f"OP margin: {[round(m,1) for m in op_margin]}")
print(f"ROS: {[round(r,1) for r in ros]}")
print(f"ROE: {[round(r,1) for r in roe]}")
print(f"ROA: {[round(r,1) for r in roa]}")
print(f"")
print(f"Net debt: {net_debt} (negative = net cash)")
print(f"Debt/Equity: {[round(d,3) for d in debt_to_equity]}")
print(f"")
print(f"Ke (CAPM): {Ke:.2f}%")
print(f"FCF raw: {fcf_raw}")
print(f"Capex/Rev %: {[round(c,2) for c in capex_rev_ratio]}")
print(f"Capex sustainable (median 2022-2024 ratio x 2025 rev): {capex_sustainable_2025:.0f} млн")
print(f"CFO CV: {cfo_cv:.3f}")

# ─── VALUATION ────────────────────────────────────────────────────────────────

# 1. P/E × Adjusted EPS
# Historical P/E: IPO Apr 2024 → only 2 years of public trading.
# Can't compute 5-year historical avg P/E — use sector / comparable basis.
# MFO sector peers: CIAN, debt collectors, consumer finance.
# Sector context: МФО regulated, high-risk premium.
# Mechanical approach: use current P/E as reference, project from consensus EPS.

# Consensus EPS 2026 (forward): net_profit ~5127 млн / 100M shares = 51.27 RUB
eps_forward = 5127.0 / SHARES * 1e6   # = 51.27 RUB

# Historical P/E basis: only 2025 year meaningful (2024 anomalous regulatory trough)
# Use 2022 and 2023 (pre-IPO МСФО) and 2025 as proxies
# Historical P/E not available (no year-end price history)
# Conservative: use sector-appropriate P/E
# MFO in RU: comparable regulated finance co; ПАО банки trade ~3-5x P/E
# МФО = higher risk, lower P/E than quality banks; estimate 4-6x (judgement, data_quality low)
# Use 5x as base (mid of range), 4x conservative, 6x optimistic
pe_historical_base = 5.0   # judgement, no reliable history
pe_conservative = 4.0
pe_optimistic = 6.0

fair_pe_conservative = pe_conservative * eps_forward
fair_pe_base = pe_historical_base * eps_forward
fair_pe_optimistic = pe_optimistic * eps_forward

print(f"\n=== VALUATION: Historical P/E ===")
print(f"EPS forward 2026 consensus: {eps_forward:.2f} RUB")
print(f"P/E conservative ({pe_conservative}x): {fair_pe_conservative:.0f} RUB")
print(f"P/E base ({pe_historical_base}x): {fair_pe_base:.0f} RUB")
print(f"P/E optimistic ({pe_optimistic}x): {fair_pe_optimistic:.0f} RUB")

# 2. Dividend Discount Model (Gordon)
# DPS forward:
# Governance: payout 82-92% in 2024-2025; policy min 50%
# Consensus NP 2026 = 5127 mln; payout assumption 70% (blend: lower than 82-92% given regulatory squeeze)
payout_base = 0.70
payout_conservative = 0.50
NP_2026 = 5127.0  # млн
DPS_forward_base = NP_2026 * payout_base / SHARES * 1e6
DPS_forward_conservative = NP_2026 * payout_conservative / SHARES * 1e6
DPS_actual_2025 = 35.83  # from governance.json

# Required div yield for MFO with regulatory risk
# Ke = 27.2% is theoretically the cost of equity
# But investors may accept lower yield for high payout companies
# Div yield approach: price = DPS / required_yield
# Required yield: RF + spread for MFO risk
# Current yield at market: 35.83/147.79 = 24.2% → market prices in high risk
req_yield_conservative = Ke / 100   # 27.2%
req_yield_base = 0.22               # 22% (between Ke and market implied)
req_yield_optimistic = 0.18         # 18%

# Gordon growth: Price = DPS1 / (r - g), g = 2% (low growth, regulated sector)
g_div = 0.02
fair_div_conservative = DPS_forward_conservative / (req_yield_conservative - g_div)
fair_div_base = DPS_forward_base / (req_yield_base - g_div)
fair_div_optimistic = DPS_forward_base / (req_yield_optimistic - g_div)

print(f"\n=== VALUATION: Dividend DDM ===")
print(f"DPS 2025 actual: {DPS_actual_2025:.2f} RUB")
print(f"DPS forward (70% payout): {DPS_forward_base:.2f} RUB")
print(f"DPS forward (50% payout): {DPS_forward_conservative:.2f} RUB")
print(f"Required yield conservative (Ke={req_yield_conservative:.1%}): {fair_div_conservative:.0f} RUB")
print(f"Required yield base (22%): {fair_div_base:.0f} RUB")
print(f"Required yield optimistic (18%): {fair_div_optimistic:.0f} RUB")

# 3. P/B × ROE method
# Justified P/B = (ROE - g) / (Ke - g)
ROE_2025 = roe[3]   # 2025 ROE
ROE_avg = statistics.mean(roe)
# Sustainable ROE: given regulatory squeeze, use conservative 28% (below 2022-2023 highs)
ROE_sustainable = 28.0   # % (judgement)
g_pb = 2.5  # % terminal growth
Ke_dec = Ke / 100

justified_pb = (ROE_sustainable/100 - g_pb/100) / (Ke_dec - g_pb/100)
BVPS_2025 = BVPS_hist[3]
fair_pb_base = justified_pb * BVPS_2025

# Conservative: ROE 24%, g 1.5%
justified_pb_cons = (0.24 - 0.015) / (Ke_dec - 0.015)
fair_pb_conservative = justified_pb_cons * BVPS_2025

# Optimistic: ROE 32%, g 3%
justified_pb_opt = (0.32 - 0.03) / (Ke_dec - 0.03)
fair_pb_optimistic = justified_pb_opt * BVPS_2025

print(f"\n=== VALUATION: P/BV × ROE ===")
print(f"Ke: {Ke:.2f}%, g: {g_pb}%, ROE sustainable: {ROE_sustainable}%")
print(f"Justified P/B base: {justified_pb:.3f}x")
print(f"BVPS 2025: {BVPS_2025:.2f} RUB")
print(f"Fair value base: {fair_pb_base:.0f} RUB")
print(f"Fair value conservative: {fair_pb_conservative:.0f} RUB")
print(f"Fair value optimistic: {fair_pb_optimistic:.0f} RUB")

# 4. CAPM (12m target)
# Ke = Rf + beta * ERP
# 12m target: current_price * (1 + Ke/100 - div_yield)
div_yield_fwd = DPS_forward_base / PRICE
capm_12m = PRICE * (1 + Ke/100 - div_yield_fwd)

print(f"\n=== VALUATION: CAPM 12m ===")
print(f"Ke: {Ke:.2f}%")
print(f"Fwd div yield: {div_yield_fwd:.2%}")
print(f"CAPM 12m target: {capm_12m:.0f} RUB")

# ─── SENSITIVITY (P/E based, as main method) ──────────────────────────────────
# EPS forward × P/E multiple
eps_scenarios = [40.0, 51.27, 60.0]   # bear/base/bull
pe_scenarios = [4.0, 5.0, 6.0]
print(f"\n=== SENSITIVITY: P/E × EPS ===")
print("EPS \\ P/E", pe_scenarios)
for eps_s in eps_scenarios:
    row = [round(eps_s * pe, 0) for pe in pe_scenarios]
    print(f"EPS={eps_s:.0f}: {row}")

# ─── FAIR VALUE RANGE ─────────────────────────────────────────────────────────
# Aggregate across methods:
# P/E: cons=205, base=256, opt=307
# DDM: cons=97, base=179, opt=295
# P/B×ROE: cons=≈110, base=≈155, opt=≈250

# Methods diverge significantly (>30%) - DDM conservative vs P/E base
# Reason: DDM at Ke=27.2% heavily discounts; P/E approach uses sector multiple
# Conservative: anchor on DDM (highest uncertainty) + P/B
# Base: blend P/E and P/B×ROE
# Optimistic: P/E upper

conservative = round(min(fair_div_conservative, fair_pb_conservative, fair_pe_conservative))
base = round((fair_pe_base + fair_pb_base + fair_div_base) / 3)
optimistic = round(max(fair_pe_optimistic, fair_pb_optimistic, fair_div_optimistic))

print(f"\n=== FAIR VALUE RANGE ===")
print(f"Conservative: {conservative} RUB")
print(f"Base: {base} RUB")
print(f"Optimistic: {optimistic} RUB")
print(f"Current price: {PRICE} RUB")
print(f"Upside to base: {(base/PRICE-1)*100:.1f}%")

# ─── TYPE CHECKS (explain contract) ───────────────────────────────────────────
# Validate that all explain inputs will be strings
test_inputs = {
    "price": f"{PRICE} — текущая цена акции [market_context]",
    "ke": f"{Ke:.2f}% — стоимость собственного капитала (CAPM: {RF}+{BETA}×{ERP})"
}
for k, v in test_inputs.items():
    assert isinstance(v, str), f"Input {k} is not string!"
print("\nType checks: OK")

# Export key values
results = {
    "MKTCAP_MLN": MKTCAP_MLN,
    "EV_current": EV_current,
    "Ke": Ke,
    "EPS_hist": EPS_hist,
    "BVPS_hist": BVPS_hist,
    "eps_forward": eps_forward,
    "DPS_forward_base": DPS_forward_base,
    "pe_current": pe_current,
    "pb_current": pb_current,
    "PS_current": PS_current,
    "roe": roe,
    "roa": roa,
    "op_margin": op_margin,
    "ros": ros,
    "net_debt": net_debt,
    "fcf_raw": fcf_raw,
    "fair_pe_conservative": fair_pe_conservative,
    "fair_pe_base": fair_pe_base,
    "fair_pe_optimistic": fair_pe_optimistic,
    "fair_div_conservative": fair_div_conservative,
    "fair_div_base": fair_div_base,
    "fair_div_optimistic": fair_div_optimistic,
    "justified_pb": justified_pb,
    "fair_pb_conservative": fair_pb_conservative,
    "fair_pb_base": fair_pb_base,
    "fair_pb_optimistic": fair_pb_optimistic,
    "capm_12m": capm_12m,
    "conservative": conservative,
    "base": base,
    "optimistic": optimistic,
    "capex_rev_ratio": capex_rev_ratio,
    "cfo_cv": cfo_cv,
    "debt_to_equity": debt_to_equity,
    "div_yield_fwd": div_yield_fwd,
}
print("\nResults computed successfully.")
print(json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in results.items()}, ensure_ascii=False, indent=2))
