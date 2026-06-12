# -*- coding: utf-8 -*-
import json, statistics as st

years = [2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]
N = len(years)

# ---------- HEADLINE SERIES (anchored on official/PDF, 2022 corrected) ----------
revenue = [2476,5022,3212,8798,8336,15904,23501,28480,31516,24640]
# COGS / gross profit by_function: from smart-lab MSFO table (2021-2025 reliable);
# earlier years reconstructed where disclosed, else null.
cogs = [None,None,None,None,None,8844,9781,13480,15316,15840]
gross = [None,None,None,None,None,7060,13720,15000,16200,8800]
operating_profit = [838,454,443,3303,2640,7987,12143,12687,13673,4491]
ebitda = [922,691,608,3738,3139,8767,13072,13937,15052,5722]
da = [83,237,165,435,499,780,929,1251,1379,1232]
finance_costs = [452,115,248,286,259,589,959,1276,1330,2814]

# REPORTED net profit (with biological revaluation). 2022 corrected 1127->12200
# (official: +44% to 12.2 bln; PDF aggregator value 1127 is an error).
net_profit = [3886,376,2291,3258,3172,8493,12200,15471,7762,-2238]

# Pre-tax profit: agri salmon activity ~0% income tax; reported tax tiny.
# Reconstruct pre_tax ~ net_profit + small tax where known; treat tax ~0 (agri льгота)
# We set income_tax mostly None/small; pre_tax ~ net for transparency.
income_tax = [None,None,None,None,None,None,None,None,None,None]
pre_tax = net_profit[:]  # agri 0% on core activity; tax negligible

# ---------- BALANCE ----------
total_assets = [5945,5578,10953,14036,19875,28887,42673,56786,58762,60251]
total_equity = [2367,3514,6003,9065,11786,18707,27274,39702,42766,39622]
total_liab = [3578,2064,4950,4971,8089,10180,15398,17084,15996,20629]
retained = [-6241,-5865,-3535,527,3258,10094,27274,30293,33707,30603]
cash = [34,1094,105,85,628,299,339,885,1445,3338]
st_debt = [2853,704,684,2190,5174,3529,4945,10638,2387,1342]
lt_debt = [347,1133,3618,1934,1548,4777,8778,3845,11734,15793]
net_debt = [(st_debt[i]+lt_debt[i]-cash[i]) for i in range(N)]

# ---------- CASH FLOW ----------
cfo = [163,2441,-1721,2469,504,3365,2891,8647,12233,2688]
capex = [154,786,1390,2537,1840,3204,3521,4630,6276,2728]
fcf = [cfo[i]-capex[i] for i in range(N)]

# ---------- DIVIDENDS per share (rub) ----------
dps = [None,None,None,None,None,8,30,55,40,10]
shares = 87.88e6

# ============================================================
# NORMALIZATION: biological asset revaluation (IAS 41) per year
# ============================================================
# Adjusted net profit (WITHOUT revaluation) — official anchors:
#  2024 adj = 10300 (reported 7762 -> reval effect -2538)
#  2025 adj = 2100  (reported -2238 -> reval effect -4338, ~ -4400 pre-tax fair-value loss)
#  2023: reported 15471 was BOOSTED by reval gain; company adj ~9200 (smart-lab adj series)
#  2022: reported 12200; adj ~11900 (small)
#  2021: reported 8493; adj ~8600 (~ small positive op)
# Earlier years (2016-2020) revaluation not separately disclosed in our sources -> treat adj=reported, flagged.
net_profit_adj = [3886,376,2291,3258,3172,8600,11900,9200,10300,2100]

# reval effect per year = reported - adjusted (the non-cash IAS41 swing in net profit)
reval_effect = [ (net_profit[i]-net_profit_adj[i]) if net_profit_adj[i] is not None else 0 for i in range(N) ]

# EBITDA adj: company reports "adjusted EBITDA" which already strips reval (reval sits below EBITDA
# only partly; company's adj EBITDA 2024=12500, 2025=5722). EBITDA here already pre-reval for
# most years; we set ebitda_adj = ebitda except where company adj differs materially.
ebitda_adj = ebitda[:]  # reval is a non-operating fair-value line below EBITDA in company's adj definition

# ---------- MARGINS ----------
def pct(a,b): return round(100*a/b,2) if (a is not None and b) else None
ebitda_margin=[pct(ebitda[i],revenue[i]) for i in range(N)]
op_margin=[pct(operating_profit[i],revenue[i]) for i in range(N)]
gross_margin=[pct(gross[i],revenue[i]) if gross[i] is not None else None for i in range(N)]
ros_rep=[pct(net_profit[i],revenue[i]) for i in range(N)]
ros_adj=[pct(net_profit_adj[i],revenue[i]) for i in range(N)]

# ---------- RETURNS (adjusted = main) ----------
def avg2(lst,i): return (lst[i]+lst[i-1])/2 if i>0 else lst[i]
roe_adj=[pct(net_profit_adj[i],avg2(total_equity,i)) for i in range(N)]
roe_rep=[pct(net_profit[i],avg2(total_equity,i)) for i in range(N)]
roa_adj=[pct(net_profit_adj[i],avg2(total_assets,i)) for i in range(N)]
roa_rep=[pct(net_profit[i],avg2(total_assets,i)) for i in range(N)]

# ---------- MULTIPLES (price-dependent) ----------
last_price=412.0
mktcap=last_price*shares/1e6  # in mln
EV_current=mktcap+net_debt[-1]
pe_adj_cur=round(mktcap/net_profit_adj[-1],2)
pe_rep_cur=round(mktcap/net_profit[-1],2)
ps_cur=round(mktcap/revenue[-1],2)
pb_cur=round(mktcap/total_equity[-1],2)
ev_ebitda_cur=round(EV_current/ebitda[-1],2)

# Historical P/E and P/B per year (need historical prices). Use PDF multiples series for P/E(rep)
pe_rep_hist=[1.34,33.28,8.30,5.61,8.58,4.66,47.86,4.25,5.02,-15.83]  # from PDF (rep, 2022 distorted)
pb_hist=[2.20,3.56,3.17,2.02,2.31,2.12,1.98,1.66,0.91,0.89]
ps_hist=[2.10,2.49,5.92,2.08,3.27,2.49,2.30,2.31,1.24,1.44]
ev_ebitda_hist=[9.09,19.20,38.20,5.97,10.61,5.43,5.15,5.70,3.43,8.60]

# implied historical price per year (to compute pe_adj_hist): price = pe_rep * eps_rep
eps_rep=[net_profit[i]*1e6/shares for i in range(N)]
eps_adj=[net_profit_adj[i]*1e6/shares for i in range(N)]
bvps_year=[total_equity[i]*1e6/shares for i in range(N)]
price_hist=[pb_hist[i]*bvps_year[i] for i in range(N)]
# pe_adj historical where adj>0 and price known
pe_adj_hist=[round(price_hist[i]/eps_adj[i],2) if (price_hist[i] and eps_adj[i]>0) else None for i in range(N)]

# 5y window 2021-2025 for averaging. P/E_adj: use years where adj>0 and price>0
pe_adj_5y=[pe_adj_hist[i] for i in range(5,N) if pe_adj_hist[i] is not None]
pb_5y=[pb_hist[i] for i in range(5,N)]

def mean_or_median(vals):
    m=st.mean(vals); sd=st.pstdev(vals); cv=sd/m if m else 0
    if cv>0.55: return ('median', round(st.median(vals),2), round(cv,2))
    return ('mean', round(m,2), round(cv,2))

pe_basis,pe_used,pe_cv=mean_or_median(pe_adj_5y)
pb_basis,pb_used,pb_cv=mean_or_median(pb_5y)

# ============================================================
# VALUATION
# ============================================================
rf=0.146; erp=0.09; beta=0.9; g=0.035; tax=0.0  # agri 0% income tax on core activity
Ke=rf+beta*erp
# Debt is meaningful (ND 13.8bn vs equity 39.6bn). WACC:
debt=st_debt[-1]+lt_debt[-1]; E=mktcap; D=debt
kd=0.18  # ~ cost of debt near key rate +; after tax = kd*(1-0)=kd (0% tax)
wacc=(E/(E+D))*Ke + (D/(E+D))*kd*(1-tax)

# ---- FCF normalization for DCF ----
# Mid-cycle FCF: salmon biology cycle ~2yr; 2024 was peak (FCF 5957), 2025 trough (-40).
# Sustainable capex: median capex/revenue * mid-cycle revenue
capex_rev=[capex[i]/revenue[i] for i in range(5,N)]  # 2021-2025
med_capex_rev=st.median(capex_rev)
midcycle_rev=st.mean([revenue[-2],revenue[-1]])  # 2024-2025 avg ~28078; conservative blend
# mid-cycle EBITDA: blend trough(5722) & peak(15052) -> use mean of 2021-2025 ebitda
midcycle_ebitda=st.mean(ebitda[5:N])
# mid-cycle CFO ~ proportional: avg CFO 2021-2025 excluding... use mean
midcycle_cfo=st.mean(cfo[5:N])
sust_capex=med_capex_rev*midcycle_rev
# Mid-cycle FCF from EBITDA (robust to volatile CFO which swings with biomass WC build):
# FCF = EBITDA(mid) - sust_capex - normalized cash interest - tax(0%, agri).
norm_interest=st.mean(finance_costs[7:N])  # 2023-2025 avg interest ~1807
fcf_norm=midcycle_ebitda - sust_capex - norm_interest
fcf1=fcf_norm*(1+g)  # next-year normalized FCF base grown by g once

EV_dcf=fcf1/(wacc-g)
equity_dcf=EV_dcf-net_debt[-1]
price_dcf=equity_dcf*1e6/shares
implied_ev_ebitda=EV_dcf/midcycle_ebitda

# ---- Historical P/E (forward) ----
# forward EPS: consensus implies recovery; mechanical mid-cycle adj EPS
eps_adj_midcycle=st.mean([net_profit_adj[i] for i in range(5,N)])*1e6/shares  # mid-cycle adj EPS = mean 2021-25
# 2026 recovery EPS (mechanical): biomass +33% supports partial volume recovery, prices soft.
# Conservative recovery adj NP ~6500 mln (between trough 2100 and 5y-mean 8420).
np_fwd=6500.0
eps_fwd= np_fwd*1e6/shares
price_pe_fwd=pe_used*eps_fwd
eps_backward=net_profit_adj[-1]*1e6/shares
price_pe_back=pe_used*eps_backward

# ---- Historical P/B ----
bvps=total_equity[-1]*1e6/shares
price_pb=pb_used*bvps

# ---- Relative (peers) ----
# sector ag peers EV/EBITDA 2025 (from existing peer data): GCHE 4.2, BELU 3.05, RAGR 5.12, ABRD 5.41
peer_evebitda=[4.2,3.05,5.12,5.41]
peer_med=st.median(peer_evebitda)
EV_rel=peer_med*midcycle_ebitda
price_rel=(EV_rel-net_debt[-1])*1e6/shares

# ---- CAPM (12m) ----
exp_div_yield=0.025
capm_target=last_price*(1+(Ke-exp_div_yield))

# ---- Dividend (Gordon-ish / required yield) ----
# mid-cycle DPS ~ between trough 10 and peak 55; ~30 rub
dps_norm=30.0
req_yield=0.12
price_div=dps_norm/req_yield

# ---- Sensitivity r x g ----
r_grid=[0.20,wacc,0.25]
g_grid=[0.025,0.035]
matrix=[]
for r in r_grid:
    row=[]
    for gg in g_grid:
        f1=fcf_norm*(1+gg)
        ev=f1/(r-gg); eq=ev-net_debt[-1]; row.append(round(eq*1e6/shares))
    matrix.append(row)

# ---- TV share for Gordon: entire value is terminal -> 100% (single-stage) ----
results={
 'Ke':round(Ke*100,2),'wacc':round(wacc*100,2),
 'mktcap':round(mktcap),'EV_current':round(EV_current),
 'pe_adj_cur':pe_adj_cur,'pe_rep_cur':pe_rep_cur,'ps_cur':ps_cur,'pb_cur':pb_cur,'ev_ebitda_cur':ev_ebitda_cur,
 'pe_used':pe_used,'pe_basis':pe_basis,'pe_cv':pe_cv,'pe_adj_5y':pe_adj_5y,
 'pb_used':pb_used,'pb_basis':pb_basis,'pb_cv':pb_cv,'pb_5y':pb_5y,
 'med_capex_rev':round(med_capex_rev,4),'midcycle_rev':round(midcycle_rev),'midcycle_ebitda':round(midcycle_ebitda),
 'midcycle_cfo':round(midcycle_cfo),'sust_capex':round(sust_capex),'norm_interest':round(norm_interest),'fcf_norm':round(fcf_norm),'fcf1':round(fcf1),
 'EV_dcf':round(EV_dcf),'equity_dcf':round(equity_dcf),'price_dcf':round(price_dcf),'implied_ev_ebitda':round(implied_ev_ebitda,2),
 'eps_adj_midcycle':round(eps_adj_midcycle,2),'eps_fwd':round(eps_fwd,2),'np_fwd':round(np_fwd),'price_pe_fwd':round(price_pe_fwd),
 'eps_backward':round(eps_backward,2),'price_pe_back':round(price_pe_back),
 'bvps':round(bvps,2),'price_pb':round(price_pb),
 'peer_med':peer_med,'EV_rel':round(EV_rel),'price_rel':round(price_rel),
 'capm_target':round(capm_target),'price_div':round(price_div),
 'sens_matrix':matrix,'r_grid':[round(x*100,2) for x in r_grid],'g_grid':[round(x*100,2) for x in g_grid],
 'reval_effect':reval_effect,'net_profit_adj':net_profit_adj,'net_profit_rep':net_profit,
 'roe_adj':roe_adj,'roe_rep':roe_rep,'roa_adj':roa_adj,'roa_rep':roa_rep,
 'ros_rep':ros_rep,'ros_adj':ros_adj,'ebitda_margin':ebitda_margin,'op_margin':op_margin,'gross_margin':gross_margin,
 'pe_adj_hist':pe_adj_hist,'pb_hist':pb_hist,'ps_hist':ps_hist,'ev_ebitda_hist':ev_ebitda_hist,'pe_rep_hist':pe_rep_hist,
 'net_debt':net_debt,'fcf':fcf,
}
print(json.dumps(results,ensure_ascii=False,indent=1))
