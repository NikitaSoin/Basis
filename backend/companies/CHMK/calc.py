import json, math, statistics

years = [2021, 2022, 2023, 2024, 2025]
revenue_mln   = [176300, 168000, 161500, 172100, 143100]
op_profit_mln = [10700,   8820,  16100,   2760,  -7170]
ebitda_mln    = [14300,  12100,  19600,   6810,  -2720]
net_profit_mln= [ 6490,  12900,   4180,  -7120, -17400]
cfo_mln       = [   45,  -2340,  29100,  27000,  21400]
capex_mln     = [ 1240,   1800,   6890,   4140,   2410]

price = 4026.94
shares = 3_161_965
mcap_mln = price * shares / 1e6

rf = 14.6; erp = 9.0

debt_2024_mln = 153_000
cash_2024_mln = 148
net_debt_mln = debt_2024_mln - cash_2024_mln
ev_mln = mcap_mln + net_debt_mln

equity_map = {2021: 67_600, 2024: 54_900, 2025: 62_900}

capex_sustainable = statistics.mean([1240, 1800, 4140, 2410])
cfo_trend = statistics.mean([29100, 27000, 21400])
fcf_normalized = cfo_trend - capex_sustainable

def cv(data):
    if len(data) < 2: return 0
    m = statistics.mean(data)
    s = statistics.stdev(data)
    return s/m if m != 0 else 0

def avg_or_median(data):
    if not data: return None, "N/A"
    c = cv(data)
    if c > 0.5:
        return statistics.median(data), "5y_median (CV={:.2f})".format(c)
    return statistics.mean(data), "5y_mean (CV={:.2f})".format(c)

pe_valid = []
ev_eb_valid = []
pb_valid = []
for i, y in enumerate(years):
    np_ = net_profit_mln[i]
    eb_ = ebitda_mln[i]
    eq_ = equity_map.get(y)
    if np_ > 500:
        pe_valid.append(mcap_mln / np_)
    if eb_ > 500:
        ev_eb_valid.append(ev_mln / eb_)
    if eq_:
        pb_valid.append(mcap_mln / eq_)

pe_avg, pe_basis = avg_or_median(pe_valid)
ev_eb_avg, ev_eb_basis = avg_or_median(ev_eb_valid)
pb_avg, pb_basis = avg_or_median(pb_valid)

print("P/E valid:", [round(x,1) for x in pe_valid], "avg=", round(pe_avg,2) if pe_avg else None)
print("EV/EBITDA valid:", [round(x,1) for x in ev_eb_valid], "avg=", round(ev_eb_avg,2) if ev_eb_avg else None)
print("P/B valid:", [round(x,3) for x in pb_valid], "avg=", round(pb_avg,3) if pb_avg else None)
print("pe_basis:", pe_basis, "ev_eb_basis:", ev_eb_basis, "pb_basis:", pb_basis)

ebitda_cycle = statistics.mean([14300, 12100, 19600])
print(f"\nEBITDA_cycle={ebitda_cycle:.0f}")

ev_mult_results = {}
for mult in [4.0, 5.0, 6.0]:
    ev_imp = mult * ebitda_cycle
    eq_imp = ev_imp - net_debt_mln
    p = max(0.0, eq_imp / shares * 1e6)
    ev_mult_results[mult] = round(p)
    print(f"EV/EBITDA {mult}x: EV={ev_imp:.0f} equity={eq_imp:.0f} price={p:.0f}")

eps_cycle = statistics.mean([6490, 12900, 4180]) / shares * 1e6
price_pe = round(pe_avg * eps_cycle) if pe_avg else None
print(f"\nP/E: pe_avg={round(pe_avg,2) if pe_avg else None} eps_cycle={eps_cycle:.1f} price_pe={price_pe}")

loans_grp = 34_000
tangible = equity_map[2025] - loans_grp
bvps_tangible = tangible / shares * 1e6
bvps_balance = equity_map[2025] / shares * 1e6
price_pb_tangible = round(pb_avg * bvps_tangible) if pb_avg else None
print(f"P/B tangible: pb_avg={round(pb_avg,3) if pb_avg else None} BVPS_t={bvps_tangible:.1f} price={price_pb_tangible}")

beta = 1.5
ke = rf + beta * erp
r = ke / 100
g = 0.035
fcf1 = fcf_normalized
ev_dcf = fcf1 / (r - g)
eq_dcf = ev_dcf - net_debt_mln
price_dcf = max(0.0, eq_dcf / shares * 1e6)
implied_mult = ev_dcf / ebitda_cycle
print(f"\nDCF: ke={ke}% fcf1={fcf1:.0f} ev={ev_dcf:.0f} equity={eq_dcf:.0f} price={price_dcf:.0f} implied_ev_eb={implied_mult:.1f}x")

r_grid = [0.25, round(ke/100,3), 0.33]
g_grid = [0.02, 0.035, 0.04]
matrix = []
for r_ in r_grid:
    row = []
    for g_ in g_grid:
        ev_ = fcf1 / (r_ - g_) if r_ > g_ else 0
        eq_ = ev_ - net_debt_mln
        p_ = max(0.0, eq_ / shares * 1e6)
        row.append(round(p_))
    matrix.append(row)
print(f"Sensitivity r_grid={r_grid} g_grid={g_grid}")
for i, r_ in enumerate(r_grid):
    print(f"  r={r_}: {matrix[i]}")

valid_prices = []
for mult, p in ev_mult_results.items():
    if p > 0: valid_prices.append(p)
if price_pe and price_pe > 0: valid_prices.append(price_pe)
if price_pb_tangible and price_pb_tangible > 0: valid_prices.append(price_pb_tangible)
if price_dcf > 0: valid_prices.append(price_dcf)

conservative = 0
base = round(statistics.mean(valid_prices)) if valid_prices else 0
optimistic = round(max(valid_prices)) if valid_prices else 0
print(f"\nCOIRDOR: conservative=0 base={base} optimistic={optimistic}")
print(f"current_price={price}")

# Timeseries
fcf_raw = [cfo_mln[i] - capex_mln[i] for i in range(5)]
pe_ts = [round(mcap_mln/net_profit_mln[i],1) if net_profit_mln[i]>500 else None for i in range(5)]
ev_eb_ts = [round(ev_mln/ebitda_mln[i],1) if ebitda_mln[i]>500 else None for i in range(5)]
pb_ts = [round(mcap_mln/equity_map[y],3) if equity_map.get(y) else None for y in years]
ps_ts = [round(mcap_mln/revenue_mln[i],3) for i in range(5)]
rev_growth = [None]+[round((revenue_mln[i]-revenue_mln[i-1])/revenue_mln[i-1]*100,1) for i in range(1,5)]
ebitda_margin = [round(ebitda_mln[i]/revenue_mln[i]*100,1) for i in range(5)]
op_margin = [round(op_profit_mln[i]/revenue_mln[i]*100,1) for i in range(5)]
ros = [round(net_profit_mln[i]/revenue_mln[i]*100,1) for i in range(5)]
nd_eb = [round(net_debt_mln/ebitda_mln[i],1) if ebitda_mln[i]>0 else None for i in range(5)]
fcf_margin = [round(fcf_raw[i]/revenue_mln[i]*100,1) for i in range(5)]
cfo_to_cap = [round(cfo_mln[i]/capex_mln[i],2) if cfo_mln[i]>0 else None for i in range(5)]
cap_to_rev = [round(capex_mln[i]/revenue_mln[i]*100,2) for i in range(5)]

roe_ts = [None]*5
roic_ts = [None]*5
roa_ts = [None]*5
for i, y in enumerate(years):
    eq = equity_map.get(y)
    if eq:
        roe_ts[i] = round(net_profit_mln[i]/eq*100,1)
        nopat = op_profit_mln[i]*(1-0.25)
        invested = eq + net_debt_mln
        roic_ts[i] = round(nopat/invested*100,1)
roa_ts[3] = round(net_profit_mln[3]/268000*100,1)  # 2024 only

np_growth = [None]*5
for i in range(1,5):
    if net_profit_mln[i-1] > 0:
        np_growth[i] = round((net_profit_mln[i]-net_profit_mln[i-1])/net_profit_mln[i-1]*100,1)

print("\n--- all timeseries ---")
print("pe_ts:", pe_ts)
print("ev_eb_ts:", ev_eb_ts)
print("pb_ts:", pb_ts)
print("ps_ts:", ps_ts)
print("roe_ts:", roe_ts)
print("roic_ts:", roic_ts)
print("nd_eb:", nd_eb)
print("ebitda_margin:", ebitda_margin)
print("op_margin:", op_margin)
print("ros:", ros)
print("rev_growth:", rev_growth)
print("np_growth:", np_growth)
print("fcf_raw:", fcf_raw)
print("fcf_margin:", fcf_margin)
print("cfo_to_cap:", cfo_to_cap)
print("cap_to_rev:", cap_to_rev)
print("roa_ts:", roa_ts)
print("mcap_mln:", round(mcap_mln,1))
print("ev_mln:", round(ev_mln,1))
print("net_debt:", net_debt_mln)
print("ke:", ke)
print("pe_avg:", round(pe_avg,2) if pe_avg else None, pe_basis)
print("ev_eb_avg:", round(ev_eb_avg,2) if ev_eb_avg else None, ev_eb_basis)
print("pb_avg:", round(pb_avg,3) if pb_avg else None, pb_basis)
print("eps_cycle:", round(eps_cycle,1))
print("bvps_balance:", round(bvps_balance,1))
print("bvps_tangible:", round(bvps_tangible,1))
print("capex_sustainable:", round(capex_sustainable,0))
print("fcf_normalized:", round(fcf_normalized,0))
print("price_ev_eb:", ev_mult_results)
print("price_pe:", price_pe)
print("price_pb_tangible:", price_pb_tangible)
print("price_dcf:", round(price_dcf,0))
