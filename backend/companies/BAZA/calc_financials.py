"""
BAZA financials calculation script
All numbers computed here, not by intuition.
"""
import json, math, statistics

# ── MARKET CONTEXT (from rates.csv / task) ─────────────────────────────────
PRICE = 121.308        # ₽ per share (from rates.csv)
SHARES = 165_000_000   # shares outstanding
MKTCAP_MLN = PRICE * SHARES / 1_000_000   # ₽ млн

# ── MACRO (config/market_params.json) ──────────────────────────────────────
RF = 14.6       # % OFZ 10Y
ERP = 9.0       # %
G_DEFAULT = 3.5 # %
TAX_NORM = 25.0 # % with 2025

# ── SOURCE DATA (extracted_financials.json) ─────────────────────────────────
YEARS = [2024, 2025]
REVENUE = [4603, 6303]      # млн ₽
EBITDA  = [2832, 3840]      # млн ₽
NET_PROFIT_REP = [2044, 2219]  # reported
NET_PROFIT_ADJ = [1779, 2369]  # company-disclosed adjusted (NIC)
FCF     = [850, 2067]       # млн ₽ (disclosed)
NET_CASH = [288, 1478]      # чистая денежная позиция (положительная = кэша > долга)

# ── GOVERNANCE — dividends ──────────────────────────────────────────────────
DPS_Q1_2026 = 7.2   # ₽/акц (рекомендовано СД за 1кв 2026, источник governance.json)

# ── MARGINS ────────────────────────────────────────────────────────────────
ebitda_margin = [EBITDA[i]/REVENUE[i]*100 for i in range(2)]
ros_rep = [NET_PROFIT_REP[i]/REVENUE[i]*100 for i in range(2)]
ros_adj = [NET_PROFIT_ADJ[i]/REVENUE[i]*100 for i in range(2)]

print("=== MARGINS ===")
for i, y in enumerate(YEARS):
    print(f"{y}: EBITDA margin={ebitda_margin[i]:.1f}%, ROS_rep={ros_rep[i]:.1f}%, ROS_adj={ros_adj[i]:.1f}%")

# ── NORMALIZATION BRIDGE ────────────────────────────────────────────────────
# Company discloses 'adjusted NIC' but not what's excluded.
# Net profit REP vs ADJ:
# 2024: rep=2044, adj=1779 → adj is LOWER by 265 → suggests adj removes some ONE-OFF INCOME
# 2025: rep=2219, adj=2369 → adj is HIGHER by 150 → suggests adj adds back some one-off COSTS
# Plausibly: 2024 had ~265 non-recurring income (IPO prep gains? revaluation?), 2025 had ~150 of non-recurring expenses (IPO costs, LTI accrual)
# Without primary source we use company-disclosed adj as our base (certainty=judgement for 2024 direction, logic for 2025 LTI)
# ETR: pre-tax not disclosed → cannot compute ETR directly. We note IT льгота (5% possible) vs norm 25%
# Net profit adj 2025 = 2369 млн — use as adjusted base

bridge_2024 = 2044 - 1779   # +265 removed from adj (one-off income)
bridge_2025 = 2369 - 2219   # +150 added back (one-off costs)
print(f"\n=== BRIDGE ===")
print(f"2024: reported={2044}, adj={1779}, delta={bridge_2024} (one-off income excluded)")
print(f"2025: reported={2219}, adj={2369}, delta={bridge_2025} (one-off costs added back, likely IPO/LTI)")

# ── EPS ─────────────────────────────────────────────────────────────────────
eps_rep = [NET_PROFIT_REP[i]*1e6 / SHARES for i in range(2)]
eps_adj = [NET_PROFIT_ADJ[i]*1e6 / SHARES for i in range(2)]
print(f"\n=== EPS ===")
for i, y in enumerate(YEARS):
    print(f"{y}: EPS_rep={eps_rep[i]:.2f}₽, EPS_adj={eps_adj[i]:.2f}₽")

# ── NET DEBT / NET CASH ──────────────────────────────────────────────────────
# net_cash positive means cash > debt (company has net cash position)
# net_debt = -net_cash
net_debt = [-nc for nc in NET_CASH]
ev = [MKTCAP_MLN + net_debt[i] for i in range(2)]
print(f"\n=== EV ===")
print(f"Market cap = {MKTCAP_MLN:.0f} млн")
for i, y in enumerate(YEARS):
    print(f"{y}: Net cash={NET_CASH[i]}, Net debt={net_debt[i]}, EV={ev[i]:.0f} млн")

# ── MULTIPLES (historical — only 2 years, caution) ───────────────────────────
pe_rep = [MKTCAP_MLN / NET_PROFIT_REP[i] for i in range(2)]
pe_adj = [MKTCAP_MLN / NET_PROFIT_ADJ[i] for i in range(2)]
ps     = [MKTCAP_MLN / REVENUE[i] for i in range(2)]
ev_ebitda = [ev[i] / EBITDA[i] for i in range(2)]

print(f"\n=== MULTIPLES (at current price {PRICE}) ===")
for i, y in enumerate(YEARS):
    print(f"{y}: P/E_rep={pe_rep[i]:.1f}x, P/E_adj={pe_adj[i]:.1f}x, EV/EBITDA={ev_ebitda[i]:.1f}x, P/S={ps[i]:.1f}x")

# CV check (2 data points — can only note, no reliable mean/median)
# With 2 years, both mean and median = average of 2 values — use mean but flag low reliability
pe_adj_mean = statistics.mean(pe_adj)
ps_mean = statistics.mean(ps)
ev_ebitda_mean = statistics.mean(ev_ebitda)
print(f"\nHistorical averages (2yr only — LOW reliability):")
print(f"  P/E_adj avg = {pe_adj_mean:.1f}x")
print(f"  EV/EBITDA avg = {ev_ebitda_mean:.1f}x")
print(f"  P/S avg = {ps_mean:.1f}x")

# ── FORECASTS ─────────────────────────────────────────────────────────────────
# Management guidance: revenue +30-40% in 2026
# Consensus target: 2 analysts, avg 211 ₽, range 175-247
# Use midpoint of management guidance for mechanistic forecast
rev_growth_lo = 0.30
rev_growth_hi = 0.40
rev_growth_mid = (rev_growth_lo + rev_growth_hi) / 2  # 35%

rev_2026_mech = REVENUE[1] * (1 + rev_growth_mid)
# Assume EBITDA margin stable ~61% (average of 2 years)
ebitda_margin_avg = statistics.mean(ebitda_margin) / 100
ebitda_2026_mech = rev_2026_mech * ebitda_margin_avg

# Adjusted NIC margin 2025 = 2369/6303 = 37.6% — use as forward NIC margin (conservative)
nic_margin_2025 = NET_PROFIT_ADJ[1] / REVENUE[1]
nic_2026_mech = rev_2026_mech * nic_margin_2025
eps_2026_mech = nic_2026_mech * 1e6 / SHARES

print(f"\n=== 2026 FORECASTS (mechanical, mgmt guidance +35%) ===")
print(f"Revenue 2026 = {rev_2026_mech:.0f} млн")
print(f"EBITDA 2026  = {ebitda_2026_mech:.0f} млн (margin {ebitda_margin_avg*100:.1f}%)")
print(f"NIC adj 2026 = {nic_2026_mech:.0f} млн (margin {nic_margin_2025*100:.1f}%)")
print(f"EPS adj 2026 = {eps_2026_mech:.2f}₽")

# ── BETA (proxy) ────────────────────────────────────────────────────────────
# BAZA IPO Dec 2025, <6 months trading, no reliable beta.
# Use sector proxy: Russian IT (POSI, ASTR, DATA) beta ~1.3 (judgement based on sector volatility)
BETA = 1.3
Ke = RF + BETA * ERP
print(f"\n=== CAPM ===")
print(f"Rf={RF}%, Beta={BETA} (proxy sector IT), ERP={ERP}%")
print(f"Ke = {RF} + {BETA}*{ERP} = {Ke:.2f}%")

# ── VALUATION ────────────────────────────────────────────────────────────────

# ── 1. DCF (Gordon от FCF₁) — осторожно, insufficient_data ──────────────────
# FCF 2025 = 2067 млн. Very limited history (2 years), FCF nearly doubled.
# FCF₁ = FCF 2025 adjusted for sustainability. We note FCF 2024 was low (850), 2025 high (2067).
# Average = 1459 млн. Use average as FCF₁ base (conservative — neither peak nor trough).
# Actually management says 35% growth 2026, so FCF₁ ~ FCF_2025 * (1+partial) ~ 2067 * 1.15 (margin compression expected)
# Given data scarcity: use FCF_avg * 1.0 = 1459 mlm as conservative FCF₁
FCF_avg = statistics.mean(FCF)
FCF1_dcf = FCF_avg  # conservative base
g_dcf = 3.5         # = default terminal growth (conservative)
r_dcf = Ke / 100

EV_dcf = FCF1_dcf / (r_dcf - g_dcf/100)
# Net cash 2025 = +1478 млн (cash > debt) → EV + net_cash = equity value
equity_dcf = EV_dcf + NET_CASH[1]  # кэша больше долга, прибавляем
price_dcf = equity_dcf * 1e6 / SHARES

print(f"\n=== DCF (Gordon, осторожно — insufficient_data) ===")
print(f"FCF₁ = {FCF1_dcf:.0f} млн (среднее FCF 2024-2025, консервативная база)")
print(f"r = {r_dcf*100:.2f}%, g = {g_dcf}%")
print(f"EV = {FCF1_dcf} / ({r_dcf*100:.2f}% - {g_dcf}%) = {EV_dcf:.0f} млн")
print(f"EV + чистая денежная позиция {NET_CASH[1]} = {equity_dcf:.0f} млн equity")
print(f"Цена DCF = {price_dcf:.1f} ₽")

# implied EV/EBITDA check
implied_exit = EV_dcf / EBITDA[1]
print(f"Implied EV/EBITDA (cross-check) = {implied_exit:.1f}x (sector comps: POSI ~12-15x, Arenadata ~8x)")

# Sensitivity r x g
print(f"\nSensitivity (DCF price ₽):")
r_grid = [Ke*0.95/100, r_dcf, Ke*1.05/100]
g_grid = [2.5/100, 3.0/100, 3.5/100]
matrix = []
for g in g_grid:
    row = []
    for r in r_grid:
        if r > g:
            ev_s = FCF1_dcf / (r - g)
            eq_s = ev_s + NET_CASH[1]
            p_s = eq_s * 1e6 / SHARES
        else:
            p_s = None
        row.append(round(p_s, 1) if p_s else None)
    matrix.append(row)
    print(f"  g={g*100:.1f}%: {row}")
r_grid_pct = [round(r*100, 2) for r in r_grid]
g_grid_pct = [round(g*100, 1) for g in g_grid]

# ── 2. Historical P/E (adj) — forward ─────────────────────────────────────
# Only 2 data points — use mean, flag low reliability; CV irrelevant at n=2
pe_adj_2024 = pe_adj[0]
pe_adj_2025 = pe_adj[1]
pe_hist_mean = statistics.mean([pe_adj_2024, pe_adj_2025])
# Forward: EPS 2026 = 14.36 ₽ (mechanical)
eps_forward = eps_2026_mech
price_pe_forward = pe_hist_mean * eps_forward
# Backward: current adj EPS = EPS 2025 adj
eps_backward = eps_adj[1]
price_pe_backward = pe_hist_mean * eps_backward
print(f"\n=== Historical P/E (adj) ===")
print(f"P/E_adj 2024={pe_adj_2024:.1f}x, 2025={pe_adj_2025:.1f}x, mean={pe_hist_mean:.1f}x (n=2, low reliability)")
print(f"EPS forward 2026 mech={eps_forward:.2f}₽")
print(f"Fair value (forward) = {pe_hist_mean:.1f} × {eps_forward:.2f} = {price_pe_forward:.1f}₽")
print(f"Fair value (backward ref) = {pe_hist_mean:.1f} × {eps_backward:.2f} = {price_pe_backward:.1f}₽")

# ── 3. EV/EBITDA relative ──────────────────────────────────────────────────
# Peers: POSI, ASTR, DATA — sector IT
# POSI EV/EBITDA ~12-14x (2025), ASTR ~15x, DATA ~8-9x → sector median ~12x
# Source: public data / web search findings
SECTOR_EVEBITDA_MEDIAN = 12.0  # judgement, 3 peers
ebitda_2026 = ebitda_2026_mech
ev_relative = SECTOR_EVEBITDA_MEDIAN * ebitda_2026
equity_relative = ev_relative + NET_CASH[1]  # + net cash
price_evebitda = equity_relative * 1e6 / SHARES
print(f"\n=== EV/EBITDA relative (sector peers) ===")
print(f"Sector median EV/EBITDA = {SECTOR_EVEBITDA_MEDIAN}x (POSI/ASTR/DATA, judgement)")
print(f"EBITDA 2026 mech = {ebitda_2026:.0f} млн")
print(f"EV = {SECTOR_EVEBITDA_MEDIAN} × {ebitda_2026:.0f} = {ev_relative:.0f} млн")
print(f"Equity = {ev_relative:.0f} + {NET_CASH[1]} = {equity_relative:.0f} млн")
print(f"Fair value EV/EBITDA = {price_evebitda:.1f}₽")

# ── 4. EV/Sales relative ───────────────────────────────────────────────────
# Sector IT EV/Sales: POSI ~6x, ASTR ~8x, DATA ~4x → median ~6x
SECTOR_EVSALES_MEDIAN = 6.0
ev_sales_rel = SECTOR_EVSALES_MEDIAN * rev_2026_mech
equity_sales_rel = ev_sales_rel + NET_CASH[1]
price_evsales = equity_sales_rel * 1e6 / SHARES
print(f"\n=== EV/Sales relative ===")
print(f"Sector median EV/Sales = {SECTOR_EVSALES_MEDIAN}x (judgement)")
print(f"Revenue 2026 mech = {rev_2026_mech:.0f} млн")
print(f"EV = {ev_sales_rel:.0f} млн, Equity = {equity_sales_rel:.0f} млн")
print(f"Fair value EV/Sales = {price_evsales:.1f}₽")

# ── 5. CAPM 12m ────────────────────────────────────────────────────────────
# Current div yield on Q1 annualised: 4*7.2/121.308 = 23.7% — clearly not sustainable
# Use policy: 50% of adj NIC; annualised NIC 2025 adj = 2369 млн → 50% = 1184.5 млн
# DPS expected for 2025 full year ~ 1184.5/165 = 7.18 ₽ → policy first year
# For CAPM: target = current * (1 + Ke - expected div yield)
# expected div yield (policy 50%, NIC 2026): DPS = 0.5*nic_2026/shares
dps_2026_policy = 0.5 * nic_2026_mech * 1e6 / SHARES
div_yield_forward = dps_2026_policy / PRICE * 100
price_capm = PRICE * (1 + (Ke - div_yield_forward) / 100)
print(f"\n=== CAPM 12m ===")
print(f"Ke = {Ke:.2f}%, expected div yield (policy 50% NIC 2026) = {div_yield_forward:.1f}%")
print(f"CAPM target = {PRICE} × (1 + ({Ke:.2f}% - {div_yield_forward:.1f}%)/100) = {price_capm:.1f}₽")

# ── 6. Dividend yield method ───────────────────────────────────────────────
# DPS 2026 = 7.2 ₽ (Q1 interim, annualised ≈ 28.8₽) but that is forward interim only
# Policy: 50% of adj NIC. For 2025 year: adj NIC 2025=2369 → DPS=2369*0.5/165 = 7.18₽ per year
# Required div yield for IT growth stock in Russia: ~5-7% (vs Ke 26%)
# Div method yields a very wide range — note
dps_policy_2025 = NET_PROFIT_ADJ[1] * 1e6 * 0.5 / SHARES
req_yield_lo = 5.0 / 100
req_yield_hi = 7.0 / 100
price_div_lo = dps_policy_2025 / req_yield_lo
price_div_hi = dps_policy_2025 / req_yield_hi
print(f"\n=== Dividend method (reference) ===")
print(f"DPS policy 2025 = {dps_policy_2025:.2f}₽")
print(f"Required yield range {req_yield_lo*100:.0f}%–{req_yield_hi*100:.0f}%")
print(f"Fair value range = {price_div_hi:.0f}–{price_div_lo:.0f}₽")

# ── SUMMARY ───────────────────────────────────────────────────────────────
print(f"\n=== FAIR VALUE SUMMARY ===")
methods = {
    "DCF (осторожно, insufficient)": price_dcf,
    "Исторический P/E adj (forward)": price_pe_forward,
    "EV/EBITDA relative (peers)": price_evebitda,
    "EV/Sales relative (peers)": price_evsales,
    "CAPM 12m": price_capm,
}
for m, p in methods.items():
    upside = (p - PRICE) / PRICE * 100
    print(f"  {m}: {p:.1f}₽  ({upside:+.1f}%)")

# Fair value range
all_prices = list(methods.values())
conservative = min(all_prices)
base = statistics.mean(all_prices)
optimistic = max(all_prices)
print(f"\nКоридор: conservative={conservative:.0f}₽, base={base:.0f}₽, optimistic={optimistic:.0f}₽")
print(f"Consensus avg (2 analysts) = 211₽, range 175-247₽")

# ── RETURNS ────────────────────────────────────────────────────────────────
# ROE, ROA not computable — no balance sheet
# ROE proxy: NIC adj / est equity — equity unknown
print(f"\n=== RETURNS — не вычислимы (баланс отсутствует) ===")

# ── CAPEX / FCF check ─────────────────────────────────────────────────────
# FCF disclosed, CFO/capex not separated
# FCF 2024=850, 2025=2067; net_profit_adj 2024=1779, 2025=2369
# FCF/NIC ratio: proxy for cash conversion
fcf_to_nic = [FCF[i]/NET_PROFIT_ADJ[i] for i in range(2)]
print(f"\nFCF/NIC_adj: 2024={fcf_to_nic[0]:.2f}, 2025={fcf_to_nic[1]:.2f} (2024 low — may reflect WC build or capex)")

# ── OUTPUT dict for JSON ──────────────────────────────────────────────────
result = {
    "mktcap_mln": round(MKTCAP_MLN, 1),
    "ev_2025": round(ev[1], 0),
    "pe_adj": [round(x,1) for x in pe_adj],
    "pe_rep": [round(x,1) for x in pe_rep],
    "ps": [round(x,1) for x in ps],
    "ev_ebitda": [round(x,1) for x in ev_ebitda],
    "ebitda_margin": [round(x,1) for x in ebitda_margin],
    "ros_rep": [round(x,1) for x in ros_rep],
    "ros_adj": [round(x,1) for x in ros_adj],
    "eps_rep": [round(x,2) for x in eps_rep],
    "eps_adj": [round(x,2) for x in eps_adj],
    "Ke_pct": round(Ke, 2),
    "rev_2026_mech": round(rev_2026_mech, 0),
    "ebitda_2026_mech": round(ebitda_2026_mech, 0),
    "nic_2026_mech": round(nic_2026_mech, 0),
    "eps_2026_mech": round(eps_2026_mech, 2),
    "price_dcf": round(price_dcf, 1),
    "price_pe_forward": round(price_pe_forward, 1),
    "price_evebitda": round(price_evebitda, 1),
    "price_evsales": round(price_evsales, 1),
    "price_capm": round(price_capm, 1),
    "fair_conservative": round(conservative, 0),
    "fair_base": round(base, 0),
    "fair_optimistic": round(optimistic, 0),
    "sensitivity_r_grid": r_grid_pct,
    "sensitivity_g_grid": g_grid_pct,
    "sensitivity_matrix": matrix,
    "FCF_avg": round(FCF_avg, 0),
    "FCF1_dcf": round(FCF1_dcf, 0),
    "EV_dcf": round(EV_dcf, 0),
    "implied_exit_dcf": round(implied_exit, 1),
    "pe_hist_mean": round(pe_hist_mean, 1),
    "dps_policy_2025": round(dps_policy_2025, 2),
}

print("\n=== JSON RESULT DICT ===")
print(json.dumps(result, ensure_ascii=False, indent=2))
