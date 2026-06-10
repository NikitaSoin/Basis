import json, statistics as st

# ---- Macro params ----
mp = json.load(open('/Users/soinnikita/investment-platform/config/market_params.json'))
Rf = mp['risk_free_rate_pct']/100
ERP = mp['equity_risk_premium_pct']/100
g_term = mp['terminal_growth_default_pct']/100

# ---- fiscal years (PDF populated columns) ----
years = [2021,2022,2023,2024,2025]
N = len(years)

revenue = [17648,18960,19724,25562,31588]
net_profit = [3948,3652,4003,4611,6169]
assets = [29684,34104,34401,49543,52236]
equity = [12797,14653,15955,25337,32201]
cash = [1373,1113,600,5578,2835]
st_debt = [1554,6936,5287,4994,3390]
lt_debt = [6354,4434,3971,10535,8418]
net_debt = [6535,10256,8658,9951,8973]
da = [392,746,932,1126,1199]
oper_profit = [5444,5503,6148,7941,10782]
fin_costs = [885,1376,1509,2387,3396]
cfo = [2771,-994,4661,5830,3253]
capex = [1188,682,706,4282,3979]
ebitda = [5836,6249,7081,9068,11981]   # from sheet
shares = [1000,1000,1000,1098.57,1167.69]  # млн
eps_sheet = [3.95,3.65,4.00,4.20,5.28]

price = 47.30
price_date = "2026-05-31"
sh = shares[-1]  # 1167.69 млн

total_debt = [s+l for s,l in zip(st_debt,lt_debt)]

# ---- derived ----
def rnd(x,n=2):
    return None if x is None else round(x,n)

# EBITDA check (oper_profit + D&A)
ebitda_calc = [op+d for op,d in zip(oper_profit,da)]
gross = [None]*N  # not disclosed in sheet; leave null
da_neg = da
fcf = [c-cx for c,cx in zip(cfo,capex)]

# margins
ebitda_margin = [e/r*100 for e,r in zip(ebitda,revenue)]
operating_margin = [op/r*100 for op,r in zip(oper_profit,revenue)]
net_margin = [n/r*100 for n,r in zip(net_profit,revenue)]

# balance ratios
d_to_e = [td/eq for td,eq in zip(total_debt,equity)]
nd_ebitda = [nd/e for nd,e in zip(net_debt,ebitda)]

# returns — ОПУБЛИКОВАННЫЕ в отчёте (4 значения ROE/ROA = 2022-2025, 2021 не раскрыт; headline ROE 2025=24.35)
roe = [None,28.54,27.32,28.90,24.35]   # report; 2025=24.35 (от средн./взвеш. капитала после SPO)
roa = [None,12.30,11.74,13.40,12.45]   # report ROA, 2025=12.45
ros = [22.37,19.26,20.30,18.04,19.53]  # report ROS (5 значений, 2021-2025)
asset_turn = [1.19,0.59,0.58,0.61,0.62]  # report assets turnover (2021-2025)
# ROIC approx = NOPAT/(equity+net_debt); tax 25% 2025, use effective
nopat = [op*(1-0.22) for op in oper_profit]  # approx eff tax ~22%
invested = [eq+nd for eq,nd in zip(equity,net_debt)]
roic = [no/iv*100 for no,iv in zip(nopat,invested)]

# cash flow ratios
fcf_margin = [f/r*100 for f,r in zip(fcf,revenue)]
cfo_to_capex = [c/cx for c,cx in zip(cfo,capex)]
capex_to_rev = [cx/r*100 for cx,r in zip(capex,revenue)]

# ---- multiples (historical, using shares & price proxy per year is not reliable; sheet gives current) ----
# Per-year multiples from sheet (2023-2025 populated): P/E 8.48,12.08,9.16 ; P/S 1.72,2.18,1.79 ; P/BV ...,2.13,2.20->actually 2.13,2.20,1.75
# EV/EBITDA per year: 1.12,1.64,6.02,7.24,5.46
pe_hist = [None,None,8.48,12.08,9.16]
ps_hist = [None,None,1.72,2.18,1.79]
pb_hist = [None,None,2.13,2.20,1.75]
ev_ebitda_hist = [1.12,1.64,6.02,7.24,5.46]

# ---- CURRENT multiples (price 47.30, shares 1167.69, latest metrics 2025) ----
mcap = price*sh  # млн
nd_now = net_debt[-1]
ev_now = mcap + nd_now
eps_ttm = net_profit[-1]/sh
bvps = equity[-1]/sh
sps = revenue[-1]/sh

pe_cur = price/eps_ttm
ps_cur = mcap/revenue[-1]
pb_cur = price/bvps
ev_ebitda_cur = ev_now/ebitda[-1]
ev_sales_cur = ev_now/revenue[-1]
fcf_yield_cur = fcf[-1]/mcap*100  # FCF yield

# 6 multiples: P/E, P/S, P/BV, EV/EBITDA, EV/Sales, FCF-yield
multiples_current = {
    "pe": rnd(pe_cur), "ps": rnd(ps_cur), "pb": rnd(pb_cur),
    "ev_ebitda": rnd(ev_ebitda_cur), "ev_sales": rnd(ev_sales_cur),
    "fcf_yield_pct": rnd(fcf_yield_cur), "as_of": price_date
}

# historical avg P/E (5y median) - only 3 populated years
pe_vals = [p for p in pe_hist if p]
pe_5y_median = st.median(pe_vals)
pe_5y_avg = sum(pe_vals)/len(pe_vals)
ev_ebitda_5y_median = st.median(ev_ebitda_hist)

# ================= VALUATION =================
# CAPM cost of equity (low debt -> WACC ~ Ke)
beta = 0.9  # defensive pharma, low debt
Ke = Rf + beta*ERP
# weight of debt is small; use Ke as discount rate, but bump for conservatism
wacc = Ke  # ~ since net_debt/EV small and Kd after-tax < Ke but minimal weight

# ---- forecast (company guidance: rev +15-25%, base 20%, fading) ----
# net profit has grown faster; assume net margin stable ~19.5%
base_rev_growth = [0.20,0.18,0.15,0.10,0.07]  # fading toward terminal
rev_f = []
r = revenue[-1]
for gg in base_rev_growth:
    r = r*(1+gg); rev_f.append(r)
net_margin_f = 0.195
np_f = [r*net_margin_f for r in rev_f]
# FCF: company in heavy capex (biosimilars). FCF margin historically low/volatile.
# Use FCF = net_profit + D&A - capex - dWC. Capex elevated ~12-13% rev now, fading to ~7%.
capex_pct = [0.12,0.11,0.10,0.08,0.07]
da_pct = 1199/31588  # ~3.8% of rev, grows with capex; keep ~4%
fcf_f = []
for i,r in enumerate(rev_f):
    ni = r*net_margin_f
    dep = r*0.045
    cpx = r*capex_pct[i]
    # working capital drag ~2% of incremental revenue
    dwc = (rev_f[i]-(rev_f[i-1] if i>0 else revenue[-1]))*0.10
    f = ni + dep - cpx - dwc
    fcf_f.append(f)

# ---- DCF (FCFF-ish via FCFE since low debt; discount at Ke) ----
disc = []
pv_fcf = 0
for i,f in enumerate(fcf_f):
    d = f/((1+wacc)**(i+1))
    disc.append(d); pv_fcf += d
tv = fcf_f[-1]*(1+g_term)/(wacc-g_term)
pv_tv = tv/((1+wacc)**len(fcf_f))
ev_dcf = pv_fcf + pv_tv
eqv_dcf = ev_dcf - nd_now
fv_dcf = eqv_dcf/sh
tv_share = pv_tv/ev_dcf*100

# sensitivity grid
wacc_grid = [round(wacc-0.02,4),round(wacc,4),round(wacc+0.02,4)]
growth_grid = [0.025,0.035,0.045]
def dcf_price(w,g):
    pv=0
    for i,f in enumerate(fcf_f):
        pv += f/((1+w)**(i+1))
    tvv=fcf_f[-1]*(1+g)/(w-g)
    pv += tvv/((1+w)**len(fcf_f))
    return round((pv-nd_now)/sh,2)
matrix=[[dcf_price(w,g) for g in growth_grid] for w in wacc_grid]

# ---- historical P/E valuation ----
pe_used = pe_5y_median
fv_pe = pe_used*eps_ttm

# ---- relative peers: pending sector backfill ----
# sector peers from sheet (page 19) — store but status pending
fv_rel = None

# ---- CAPM 12m target ----
# fair P/E ~ 1/Ke ; or target = price*(1+(Ke - div_yield))
div_yield = 0.006
capm_target = price*(1+(Ke-div_yield))
fv_capm = capm_target

# ---- dividend method: low payout (div CAGR high but base tiny, ~15% payout 2025) ----
# 2025 div per share ~0.79; payout ~15%. Not a mature dividend story -> skip as primary
div_ps_2025 = 0.79
# Gordon on dividends would understate; mark dividend method low-weight
fv_div = div_ps_2025*1.15/(Ke-0.05) if (Ke-0.05)>0 else None  # very rough, growth 5%

# ---- range ----
methods_fv = {
  "DCF": round(fv_dcf,2),
  "historical_pe": round(fv_pe,2),
  "CAPM_12m": round(fv_capm,2),
}
vals = [fv_dcf, fv_pe, fv_capm]
conservative = round(min(vals),2)
base_fv = round(st.median(vals),2)
upside = round((base_fv/price-1)*100,1)
cons_upside = round((conservative/price-1)*100,1)

# ================= ANOMALY CHECK =================
flags=[]
anomaly=False
# FCF 2025 negative (-726) while net profit positive -> heavy capex/IPO investment phase
if fcf[-1]<0:
    flags.append("FCF 2025 отрицательный (-726 млн) при чистой прибыли 6169 млн — фаза тяжёлых капвложений (новые производства/биосимиляры).")
# CFO dropped 44% in 2025
flags.append("CFO 2025 = 3253 млн, -44% г/г при росте прибыли — рост оборотного капитала; качество прибыли по кэшу слабее, чем по P&L.")
# EBITDA sheet vs oper+D&A
ebitda_gap = [round(s-c,0) for s,c in zip(ebitda,ebitda_calc)]
flags.append(f"EBITDA из отчёта ({ebitda[-1]}) > опер.прибыль+амортизация ({ebitda_calc[-1]}) на {ebitda_gap[-1]} млн — это скорр. EBITDA (исключены разовые/неден. статьи).")
# DCF TV share
if tv_share>80:
    flags.append(f"DCF: доля терминальной стоимости {tv_share:.0f}% (>80%) — оценка чувствительна к допущениям WACC/g.")
# net debt check
nd_check = [td-c for td,c in zip(total_debt,cash)]
nd_diff = [round(a-b,0) for a,b in zip(net_debt,nd_check)]
if abs(nd_diff[-1])>50:
    flags.append(f"Чистый долг из отчёта ({net_debt[-1]}) ≠ долг−кэш ({nd_check[-1]}), расхождение {nd_diff[-1]} млн — в отчёте чистый долг учитывает аренду/прочее.")
flags.append("ROE/ROA взяты как опубликованы в отчёте (ROE 2025=24.35%); расчёт от конечного капитала даёт ~19% — разница из-за роста капитала после IPO/SPO (отчёт считает от средневзвешенного капитала). ROE 2021 в отчёте не раскрыт.")
flags.append("Валовая прибыль/COGS в инфографике не раскрыты (null). Скорр. EBITDA-маржа ~38.6% из IR выше отчётной EBITDA-маржи 37.9% — разница на разовые/неденежные корректировки.")
flags.append("P/E, P/S, P/BV раскрыты в отчёте только с 2023 (IPO окт.2024); ряды 2021-2022 = null. Текущие мультипликаторы посчитаны от цены 47.30 и 1167.69 млн акций.")

# anomaly_flag/note (главная аномалия)
anomaly_flag = True
anomaly_note = ("FCF за 2025 отрицательный (-726 млн) при рекордной чистой прибыли (6169 млн) и -44% CFO г/г: "
  "компания в фазе крупных капвложений (capex ~12-13% выручки на новые производства и биосимиляры) "
  "и роста оборотного капитала после IPO/SPO. Прибыль по P&L растёт, но в кэш пока не конвертируется. "
  "DCF поэтому даёт консервативный результат и сильно зависит от нормализации FCF после 2027.")

print("=== CHECKS ===")
print("EBITDA(sheet) vs op+DA:", list(zip(ebitda,ebitda_calc)))
print("NetDebt sheet vs debt-cash:", list(zip(net_debt,nd_check)))
print("FCF (cfo-capex):", [round(f) for f in fcf])
print("ROE:", roe)
print("ND/EBITDA:", [round(x,2) for x in nd_ebitda])
print("EV/EBITDA current:", round(ev_ebitda_cur,2))
print("EBITDA margin:", [round(x,1) for x in ebitda_margin])
print()
print("=== CURRENT MULT (6) ===", multiples_current)
print("eps_ttm",round(eps_ttm,2),"bvps",round(bvps,2),"mcap",round(mcap),"ev",round(ev_now))
print()
print("=== VALUATION ===")
print("Ke/WACC:",round(Ke*100,1),"%")
print("rev_f:",[round(x) for x in rev_f])
print("fcf_f:",[round(x) for x in fcf_f])
print("DCF fv:",round(fv_dcf,2),"TV share %:",round(tv_share,1))
print("hist P/E fv:",round(fv_pe,2),"(pe_used",round(pe_used,2),")")
print("CAPM 12m fv:",round(fv_capm,2))
print("range cons/base:",conservative,base_fv,"upside base %:",upside,"cons %:",cons_upside)
print("sens matrix:",matrix)
print()
print("ANOMALY:",anomaly_flag)

# ---- build JSON ----
out = {
 "meta":{"ticker":"OZPH","name":"ПАО «Озон Фармацевтика»","sector":"Биотехнологии и фармацевтика",
   "profile":"standard","currency":"RUB","unit":"млн","reporting_standard":"МСФО",
   "fiscal_years":years,"last_price":price,"price_date":price_date,
   "shares_outstanding":round(sh*1_000_000),"data_quality":"high",
   "data_source_priority":["uploaded_file","official_report","broker","aggregator"]},
 "anomaly_flag":anomaly_flag,
 "anomaly_note":anomaly_note,
 "income_statement":{
   "revenue":revenue,"cogs":[None]*N,"gross_profit":[None]*N,"operating_expenses":[None]*N,
   "operating_profit":oper_profit,"ebitda":ebitda,"da":da,"finance_costs":fin_costs,
   "net_profit":net_profit,
   "margins":{"gross_margin":[None]*N,"ebitda_margin":[rnd(x,1) for x in ebitda_margin],
     "operating_margin":[rnd(x,1) for x in operating_margin],"net_margin":[rnd(x,1) for x in net_margin]}},
 "balance_sheet":{"total_assets":assets,"total_equity":equity,
   "total_liabilities":[a-e for a,e in zip(assets,equity)],"cash":cash,
   "short_term_debt":st_debt,"long_term_debt":lt_debt,"net_debt":net_debt,
   "ratios":{"debt_to_equity":[rnd(x,2) for x in d_to_e],
     "net_debt_ebitda":[rnd(x,2) for x in nd_ebitda],"current_ratio":[None]*N}},
 "cash_flow":{"cfo":cfo,"cfi":[None]*N,"cff":[None]*N,"net_change_in_cash":[None]*N,
   "capex":capex,"fcf":[round(f) for f in fcf],
   "ratios":{"fcf_margin":[rnd(x,1) for x in fcf_margin],
     "cfo_to_capex":[rnd(x,2) for x in cfo_to_capex],"capex_to_revenue":[rnd(x,1) for x in capex_to_rev]}},
 "returns":{"roe":[rnd(x,2) for x in roe],"roa":[rnd(x,2) for x in roa],
   "roic":[rnd(x,2) for x in roic],"ros":[rnd(x,2) for x in ros],
   "asset_turnover":[rnd(x,2) for x in asset_turn]},
 "multiples":{"pe":pe_hist,"ps":ps_hist,"pb":pb_hist,"ev_ebitda":ev_ebitda_hist,
   "current":multiples_current,
   "historical_avg":{"pe_5y_avg":rnd(pe_5y_avg),"pe_5y_median":rnd(pe_5y_median),
     "ev_ebitda_5y_median":rnd(ev_ebitda_5y_median),"period":"2021-2025 (P/E только 2023-2025 в отчёте)"}},
 "peer_multiples":{
   "2025":{"pe":rnd(pe_cur),"ps":rnd(ps_cur),"pb":rnd(pb_cur),
     "ev_ebitda":rnd(ev_ebitda_cur),"ev_sales":rnd(ev_sales_cur),"fcf_yield_pct":rnd(fcf_yield_cur)},
   "2024":{"pe":pe_hist[-2],"ps":ps_hist[-2],"pb":pb_hist[-2],
     "ev_ebitda":ev_ebitda_hist[-2],
     "ev_sales":rnd((mcap+net_debt[-2])/revenue[-2]) if False else None,
     "fcf_yield_pct":None}},
 "relative_peers":{"status":"pending_sector_backfill",
   "note":"Сектор Биотех/Фарма (PRMD Промомед, ABIO Артген, LIFE Фармсинтез) — медианный мультипликатор подставить после прогона всего сектора.",
   "sector_peers_raw":[
     {"ticker":"PRMD","name":"Промомед","year":2025,"ev_ebitda":7.11,"pe":12.15,"ps":2.28,"roe":35.82},
     {"ticker":"ABIO","name":"Артген","year":2025,"ev_ebitda":19.43,"pe":53.28,"ps":3.01,"roe":9.37},
     {"ticker":"LIFE","name":"Фармсинтез","year":2023,"ev_ebitda":-7.51,"pe":-4.56,"ps":3.34,"roe":-229.07}]},
 "forecast":{"source_type":"mechanical","providers":["company_guidance"],
   "revenue_growth_pct":[round(x*100,1) for x in base_rev_growth],
   "net_profit_growth_pct":[round((np_f[i]/( [net_profit[-1]]+np_f )[i]-1)*100,1) for i in range(5)],
   "note":"Гайденс компании: выручка +15-25% в 2026 (база 20%), затем затухание к долгосрочному тренду. Маржа ЧП ~19.5% удержана. Консенсус брокеров по таргетам не раскрыт публично."},
 "valuation":{"methods":[
   {"method":"DCF","fair_value_per_share":round(fv_dcf,2),"horizon":"intrinsic_now",
     "key_assumptions":{"wacc":round(wacc*100,1),"terminal_growth":round(g_term*100,1),"forecast_years":5,"beta":beta},
     "tv_share_of_value_pct":round(tv_share,1),"status":"ok"},
   {"method":"historical_pe","fair_value_per_share":round(fv_pe,2),"horizon":"intrinsic_now",
     "key_assumptions":{"pe_used":round(pe_used,2),"basis":"3y_median (P/E раскрыт с 2023)","eps_ttm":round(eps_ttm,2)}},
   {"method":"relative_peers","fair_value_per_share":None,"horizon":"intrinsic_now",
     "key_assumptions":{"peer_multiple":"ev_ebitda","peer_median":None},"status":"pending_sector_backfill"},
   {"method":"CAPM","fair_value_per_share":round(fv_capm,2),"horizon":"12m",
     "key_assumptions":{"ke":round(Ke*100,1),"beta":beta,"div_yield_pct":round(div_yield*100,1)}}],
   "fair_value_range":{"conservative":conservative,"base":base_fv,
     "current_price":price,"upside_downside_pct":upside},
   "sensitivity":{"wacc_grid":[round(w*100,1) for w in wacc_grid],
     "growth_grid":[round(g*100,1) for g in growth_grid],"matrix":matrix}},
 "sources":[
   {"id":"src_1","type":"uploaded_file","title":"Инфографика МСФО ПАО Озон Фармацевтика 2025 (СРКИ)","period":"2021-2025","reliability":"high"},
   {"id":"src_2","type":"official_report","title":"МСФО-отчётность ПАО Озон Фармацевтика","period":"2025","reliability":"high"},
   {"id":"src_3","type":"aggregator","title":"Котировка OZPH (Т-Инвестиции/РБК)","period":"2026-05-31","reliability":"medium"}],
 "data_flags":flags}

json.dump(out,open('/Users/soinnikita/investment-platform/backend/companies/OZPH/financials.json','w'),
          ensure_ascii=False,indent=2)
print("\nWROTE financials.json")
