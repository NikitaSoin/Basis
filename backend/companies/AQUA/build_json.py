# -*- coding: utf-8 -*-
import json, statistics as st, subprocess, sys

d=json.loads(subprocess.check_output([sys.executable,'calc_aqua.py'],cwd='.').decode())
years=[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]; N=len(years)

# raw series (mirror calc)
revenue=[2476,5022,3212,8798,8336,15904,23501,28480,31516,24640]
cogs=[None,None,None,None,None,8844,9781,13480,15316,15840]
gross=[None,None,None,None,None,7060,13720,15000,16200,8800]
op=[838,454,443,3303,2640,7987,12143,12687,13673,4491]
ebitda=[922,691,608,3738,3139,8767,13072,13937,15052,5722]
da=[83,237,165,435,499,780,929,1251,1379,1232]
fin_costs=[452,115,248,286,259,589,959,1276,1330,2814]
np_rep=[3886,376,2291,3258,3172,8493,12200,15471,7762,-2238]
np_adj=d['net_profit_adj']
total_assets=[5945,5578,10953,14036,19875,28887,42673,56786,58762,60251]
total_equity=[2367,3514,6003,9065,11786,18707,27274,39702,42766,39622]
total_liab=[3578,2064,4950,4971,8089,10180,15398,17084,15996,20629]
retained=[-6241,-5865,-3535,527,3258,10094,27274,30293,33707,30603]
cash=[34,1094,105,85,628,299,339,885,1445,3338]
st_debt=[2853,704,684,2190,5174,3529,4945,10638,2387,1342]
lt_debt=[347,1133,3618,1934,1548,4777,8778,3845,11734,15793]
net_debt=d['net_debt']
cfo=[163,2441,-1721,2469,504,3365,2891,8647,12233,2688]
capex=[154,786,1390,2537,1840,3204,3521,4630,6276,2728]
fcf=d['fcf']
shares=87880000; last_price=412.0

def r2(x): return round(x,2) if x is not None else None
revg=[None]+[r2(100*(revenue[i]/revenue[i-1]-1)) for i in range(1,N)]
npg=[None]+[r2(100*(np_adj[i]/np_adj[i-1]-1)) if (np_adj[i-1] and np_adj[i-1]>0) else None for i in range(1,N)]
nd_ebitda=[r2(net_debt[i]/ebitda[i]) for i in range(N)]
d2e=[r2((st_debt[i]+lt_debt[i])/total_equity[i]) for i in range(N)]
fcf_margin=[r2(100*fcf[i]/revenue[i]) for i in range(N)]
cfo_capex=[r2(cfo[i]/capex[i]) for i in range(N)]
capex_rev=[r2(100*capex[i]/revenue[i]) for i in range(N)]
roic=[r2(100*op[i]/(total_equity[i]+st_debt[i]+lt_debt[i]-cash[i])) for i in range(N)]  # NOPAT~op (0% tax)
at=[r2(revenue[i]/((total_assets[i]+total_assets[i-1])/2)) if i>0 else r2(revenue[i]/total_assets[i]) for i in range(N)]

# price-dependent current multiples
mktcap=d['mktcap']
src_cfg='[src_cfg]'
def S(v,note): return f"{v} — {note}"

J={
 "meta":{"ticker":"AQUA","name":"ПАО «Инарктика»","sector":"Сельское хозяйство / аквакультура",
   "profile":"standard","currency":"RUB","unit":"млн","reporting_standard":"МСФО",
   "converted_years":[],"conversion_note":"",
   "fiscal_years":years,"last_price":last_price,"price_date":"2026-05-15","shares_outstanding":shares,
   "data_quality":"medium","data_source_priority":["official_report","uploaded_file","broker","aggregator"],
   "anomaly_flag":True,
   "anomaly_note":"Прибыль и P/E искажены неденежной переоценкой биологических активов (живая рыба в воде по справедливой стоимости, IAS 41). В 2025 отчётный убыток −2 238 млн ₽ при положительной скорр. ЧП ~+2 100 млн и EBITDA +5 722 млн: убыток — это разворот переоценки (−4 338 млн чистый эффект), а не операционный провал. Из-за этого отчётный P/E 2025 отрицателен. Зеркально, 2023 отчётная ЧП 15 471 завышена переоценочным доходом (+6 271 млн); скорр. ЧП 2023 ~9 200 млн. Оценку строить на НОРМАЛИЗОВАННОЙ (mid-cycle / скорр.) прибыли. Длинный (~2 года) биоцикл делает прибыль/EBITDA крайне волатильными.",
   "adjustments_aggressive":False},

 "income_statement":{
   "cost_format":"by_function",
   "revenue":revenue,"cogs":cogs,"gross_profit":gross,
   "expense_lines":[
     {"name":"Себестоимость реализации (после переоценки биоактивов)","values":cogs},
     {"name":"Коммерческие, общехоз. и административные расходы","values":[None]*N},
     {"name":"Финансовые расходы (проценты)","values":fin_costs}],
   "operating_profit":op,"da":da,"ebitda":ebitda,
   "finance_costs":fin_costs,"finance_income":[None]*N,
   "pre_tax_profit":np_rep,"income_tax":[None]*N,"net_profit":np_rep,
   "margins":{"gross_margin":d['gross_margin'],"ebitda_margin":d['ebitda_margin'],
     "operating_margin":d['op_margin'],"ros":d['ros_adj'],"ros_reported":d['ros_rep']}},

 "adjusted":{
   "net_profit_adj":np_adj,
   "net_profit_reported":np_rep,
   "ebitda_adj":ebitda,
   "fcf_normalized":[None,None,None,None,None,None,None,None,None,d['fcf_norm']],
   "wc_adjustment":[0]*N,
   "capex_sustainable_mln":d['sust_capex'],
   "capex_note":"Фактический capex 2025 = 2 728 млн (низкий, после пика 6 276 в 2024). Устойчивый capex = медиана(capex/выручка 2021–2025)=16,3% × mid-cycle выручка 28 078 = 4 565 млн — взят в DCF как нормальный уровень обновления садков/смолтовых заводов.",
   "etr_reported":[0.0]*N,"etr_sustainable":0.0,
   "bridge":[
     {"year":2025,"item":"Убыток от переоценки биологических активов по справедливой стоимости (IAS 41): валовая переоценка ~−4 400 млн (падение цены лосося −38,5% и снижение доли товарной рыбы), нетто-эффект в ЧП −4 338 млн (налог 0%, агрольгота) → исключаем","amount":4338,"added_back":True,"certainty":"fact","source_ref":"src_2"},
     {"year":2024,"item":"Переоценка биологических активов (IAS 41): отчётная ЧП 7 762 ниже скорр. 10 300 → переоценочный убыток −2 538 млн исключаем (возвращаем к 10 300)","amount":2538,"added_back":True,"certainty":"fact","source_ref":"src_2"},
     {"year":2023,"item":"Переоценка биологических активов (IAS 41): отчётная ЧП 15 471 ЗАВЫШЕНА переоценочным доходом +6 271 млн → исключаем, скорр. ЧП 9 200 млн (анти-приукрашивание)","amount":-6271,"added_back":True,"certainty":"fact","source_ref":"src_2"},
     {"year":2022,"item":"Переоценка биологических активов (IAS 41): небольшой переоценочный доход +300 млн исключаем, скорр. ЧП 11 900 (отчётная 12 200)","amount":-300,"added_back":True,"certainty":"logic","source_ref":"src_2"},
     {"year":2021,"item":"Переоценка биологических активов (IAS 41): небольшой эффект +107 млн исключаем, скорр. ЧП 8 600 (отчётная 8 493)","amount":107,"added_back":True,"certainty":"logic","source_ref":"src_2"}],
   "bridge_note":"Главная разовая/неденежная компонента — переоценка живой рыбы по справедливой стоимости (IAS 41): в годы падения цен/доли товарной рыбы (2024, 2025) она вычитает из отчётной прибыли, в годы роста (2023) — добавляет. Скорр. ЧП отражает операционную суть. 2016–2020: отдельная переоценка в наших источниках не раскрыта — adj=reported, помечено."
 },

 "balance_sheet":{
   "non_current_assets":{"ppe":[None]*N,"intangibles":[None]*N,"goodwill":[None]*N,
     "long_term_investments":[None]*N,"other_non_current":[None]*N,"total_non_current":[None]*N},
   "current_assets":{"inventory":[None]*N,"receivables":[None]*N,"cash":cash,
     "short_term_investments":[None]*N,"other_current":[None]*N,"total_current":[None]*N},
   "total_assets":total_assets,
   "equity":{"share_capital":[None]*N,"retained_earnings":retained,"additional_paid_in":[None]*N,
     "other_equity":[None]*N,"total_equity":total_equity},
   "total_equity":total_equity,
   "non_current_liabilities":{"long_term_debt":lt_debt,"deferred_tax":[None]*N,
     "other_non_current_liab":[None]*N,"total_non_current_liab":[None]*N},
   "current_liabilities":{"short_term_debt":st_debt,"payables":[None]*N,
     "other_current_liab":[None]*N,"total_current_liab":[None]*N},
   "total_liabilities":total_liab,"net_debt":net_debt,
   "tangible_equity":total_equity,
   "tangible_note":"Гудвил и сомнительные НМА в раскрытии не выделены; биологические активы — реальные (живая рыба), не «нарисованный» капитал. Ощутимый капитал ≈ балансовому.",
   "ratios":{"debt_to_equity":d2e,"net_debt_ebitda":nd_ebitda,"current_ratio":[None]*N}},

 "cash_flow":{
   "cfo":cfo,"cfi":[None]*N,"cff":[None]*N,"net_change_in_cash":[None]*N,
   "capex":capex,"fcf":fcf,
   "cfo_lines":[],"cfi_lines":[{"name":"Капитальные вложения (CapEx)","values":[-x for x in capex]}],"cff_lines":[],
   "ratios":{"fcf_margin":fcf_margin,"cfo_to_capex":cfo_capex,"capex_to_revenue":capex_rev}},

 "returns":{"roe":d['roe_adj'],"roe_reported":d['roe_rep'],"roa":d['roa_adj'],"roa_reported":d['roa_rep'],
   "roic":roic,"ros":d['ros_adj'],"asset_turnover":at},

 "metrics_timeseries":{
   "pe":d['pe_adj_hist'],"pe_reported":d['pe_rep_hist'],"pb":d['pb_hist'],"ps":d['ps_hist'],"ev_ebitda":d['ev_ebitda_hist'],
   "roe":d['roe_adj'],"roa":d['roa_adj'],"roic":roic,
   "gross_margin":d['gross_margin'],"ebitda_margin":d['ebitda_margin'],"operating_margin":d['op_margin'],"ros":d['ros_adj'],
   "net_debt_ebitda":nd_ebitda,"revenue_growth":revg,"net_profit_growth":npg},

 "multiples":{
   "pe":d['pe_adj_hist'],"pe_reported":d['pe_rep_hist'],"ps":d['ps_hist'],"pb":d['pb_hist'],"ev_ebitda":d['ev_ebitda_hist'],
   "pe_adj":d['pe_adj_hist'],
   "current":{"pe":d['pe_adj_cur'],"pe_adj":d['pe_adj_cur'],"pe_reported":d['pe_rep_cur'],
     "ps":d['ps_cur'],"pb":d['pb_cur'],"ev_ebitda":d['ev_ebitda_cur'],"as_of":"2026-05-15"},
   "historical_avg":{"pe_5y_avg":r2(st.mean([x for x in d['pe_adj_5y']])),
     "pe_5y_median":r2(st.median(d['pe_adj_5y'])),
     "pe_adj_5y_used":d['pe_used'],"pe_adj_basis":f"{d['pe_basis']} (CV={d['pe_cv']})",
     "pb_5y_avg":d['pb_used'],"pb_5y_median":r2(st.median(d['pb_5y'])),"pb_basis":f"{d['pb_basis']} (CV={d['pb_cv']})",
     "ev_ebitda_5y_median":r2(st.median(d['ev_ebitda_hist'][5:])),
     "period":"2021–2025; P/E_adj по скорр. прибыли"}},

 "forecast":{"source_type":"mechanical","providers":["консенсус MOEX-агрегаторов (12м таргет ~605 ₽, диапазон 550–660)"],
   "revenue_growth_pct":[20,12,8,6,5],"net_profit_growth_pct":[None]*5,
   "note":"Брокерского постатейного консенсуса по прибыли в источниках нет; есть консенсус-таргет цены ~605 ₽ на 12 мес (recovery-идея). Прогноз механический: биомасса в воде на конец 2025 +33% до 30,1 тыс. т — запас для восстановления объёмов 2026 (отскок от провального 2025) с затуханием к долгосрочному тренду. Forward ЧП для P/E взята консервативно 6 500 млн (между трогом 2 100 и mid-cycle 8 420)."},

 "valuation":{"methods":[],"methods_divergence_note":"","fair_value_range":{},"sensitivity":{}},

 "sources":[
   {"id":"src_1","type":"uploaded_file","title":"ИНАРКТИКА (МСФО 2025) на 13.05.2026 — инфографика СРКИ/ИнтерФакс, 20 стр. (хедлайны, контрольная сверка)","period":"2016-2025","reliability":"medium","url":"sources/ИНАРКТИКА (МСФО 2025) на 13.05.2026г.pdf"},
   {"id":"src_2","type":"official_report","title":"ПАО «Инарктика» — пресс-релизы и отчётность МСФО (2021–2025): reported vs adjusted ЧП, переоценка биоактивов, EBITDA","period":"2021-2025","reliability":"high","url":"https://inarctica.com/investors/reports-and-results/"},
   {"id":"src_3","type":"aggregator","title":"smart-lab AQUA — постатейные ряды МСФО (себестоимость, валовая прибыль, скорр. ЧП)","period":"2016-2025","reliability":"medium","url":"https://smart-lab.ru/q/AQUA/f/y/"},
   {"id":"src_4","type":"aggregator","title":"MOEX/консенсус-агрегаторы — котировка AQUA и 12м таргет ~605 ₽","period":"2026-05","reliability":"medium","url":"https://beststocks.ru/rustock/aqua/analysts"},
   {"id":"src_cfg","type":"config","title":"config/market_params.json — ОФЗ 14,6%, ERP 9,0%, g 3,5%","period":"2026-05-31","reliability":"high"}],

 "data_flags":[]
}

# ---------- VALUATION METHODS ----------
mc=d  # alias
J["valuation"]["methods"]=[
 {"method":"DCF","fair_value_per_share":mc['price_dcf'],"horizon":"intrinsic_now",
  "key_assumptions":{"fcf1_mln":mc['fcf1'],"r":mc['wacc'],"g":3.5,"tax_rate_used":0.0,
    "fcf_base":"normalized_midcycle","implied_exit_multiple":mc['implied_ev_ebitda']},
  "status":"ok",
  "explain":{
   "inputs":{
     "mid-cycle EBITDA":S("11 310 млн","среднее EBITDA 2021–2025 (сглаживает биоцикл: трог 2025=5 722, пик 2024=15 052) [src_3]"),
     "устойчивый capex":S("4 565 млн","медиана capex/выручка 16,3% × mid-cycle выручка 28 078 [src_3]"),
     "нормализованные проценты":S("1 807 млн","среднее финрасходов 2023–2025 [src_1]"),
     "ставка налога":S("0%","сельхоздеятельность по лососю/форели облагается 0% [src_2]"),
     "FCF нормализованный":S(f"{mc['fcf_norm']} млн","= EBITDA(mid) 11 310 − capex 4 565 − проценты 1 807 − налог 0"),
     "Rf":S("14,6%","доходность 10-летних ОФЗ, config [src_cfg]"),
     "ERP":S("9,0%","премия за риск рынка акций РФ, config [src_cfg]"),
     "beta":S("0,9","оценка беты для аквакультуры (волатильный агро) [judgement]"),
     "Ke":S("22,7%","= 14,6% + 0,9×9,0%"),
     "доля долга / капитала":S("D=17 135 / E=36 207","для WACC, рыночная капитализация при 412 ₽ [src_1]"),
     "стоимость долга kd":S("18%","ориентир по ключевой ставке 14,5% + спред; налог 0% → after-tax=18% [src_cfg]"),
     "WACC":S(f"{mc['wacc']}%","= (E/(E+D))×22,7% + (D/(E+D))×18%"),
     "g":S("3,5%","терминальный рост = потолок из config, ниже ставки [src_cfg]"),
     "чистый долг":S("13 797 млн","на конец 2025 [src_1]"),
     "акций":S("87,88 млн","обыкновенные [src_1]")},
   "steps":[
     "1) База FCF₁: бизнес с 2-летним биоциклом — берём mid-cycle, а не трог-2025. Mid-cycle EBITDA = среднее 2021–2025 = 11 310 млн.",
     "2) Устойчивый capex = медиана(capex/выручка)=16,3% × mid-cycle выручка 28 078 = 4 565 млн (фактический 2025=2 728 занижен после пика).",
     "3) Нормализованные проценты = среднее 2023–2025 = 1 807 млн; налог 0% (агрольгота).",
     f"4) FCF нормализованный = 11 310 − 4 565 − 1 807 − 0 = {mc['fcf_norm']} млн. FCF₁ = {mc['fcf_norm']} × (1+0,035) = {mc['fcf1']} млн.",
     f"5) Ставка: Ke = 14,6% + 0,9×9,0% = 22,7%. WACC = доля капитала×22,7% + доля долга×18% = {mc['wacc']}%.",
     f"6) Стоимость бизнеса (Гордон): EV = FCF₁/(WACC−g) = {mc['fcf1']}/({mc['wacc']/100:.4f}−0,035) = {mc['EV_dcf']} млн.",
     f"7) Cross-check: неявный EV/EBITDA = {mc['EV_dcf']}/11 310 = {mc['implied_ev_ebitda']}× — ниже сектора (3–5×), что отражает высокую ставку 21% и волатильность; консервативно.",
     f"8) Переход к цене: EV {mc['EV_dcf']} − чистый долг 13 797 = equity {mc['equity_dcf']} млн (долг положительный, поэтому equity ниже EV). Цена = {mc['equity_dcf']}×1e6/87,88 млн = {mc['price_dcf']} ₽."],
   "caveats":[
     "Одностадийный Гордон — вся стоимость терминальная (100%); очень чувствителен к WACC 21% и g.",
     "Mid-cycle EBITDA — оценка по среднему 5 лет; при новой вспышке биорисков база окажется ниже.",
     "Высокая ставка дисконтирования (ключевая 14,5%) сильно давит оценку; при снижении ставок DCF вырастет."]}},

 {"method":"historical_pe","fair_value_per_share":mc['price_pe_fwd'],"horizon":"intrinsic_now",
  "key_assumptions":{"pe_used":mc['pe_used'],"basis":f"5y_median_adj (CV={mc['pe_cv']})",
    "eps_forward":mc['eps_fwd'],"eps_forward_source":"mechanical","eps_backward_ref":mc['eps_backward']},
  "status":"ok",
  "explain":{
   "inputs":{
     "P/E_adj по годам 2021–2025":S(str(mc['pe_adj_5y']),"скорр. P/E (цена÷скорр.EPS); 2025=16,79 — высокий из-за трог-EPS [src_3]"),
     "CV выборки":S(f"{mc['pe_cv']}",">0,55 → берём медиану, а не среднее [правило методики]"),
     "P/E используемый":S(f"{mc['pe_used']}","медиана 5 лет [src_3]"),
     "forward скорр. ЧП":S("6 500 млн","механический recovery-2026 между трогом 2 100 и mid-cycle 8 420 [judgement]"),
     "forward EPS":S(f"{mc['eps_fwd']} ₽","= 6 500 млн / 87,88 млн акций"),
     "backward скорр. EPS 2025":S(f"{mc['eps_backward']} ₽","= 2 100 млн / 87,88 млн (трог) [src_2]")},
   "steps":[
     f"1) P/E_adj за 2021–2025 = {mc['pe_adj_5y']}. CV={mc['pe_cv']}>0,55 → используем МЕДИАНУ = {mc['pe_used']} (2025-трог раздул разброс).",
     "2) Forward скорр. ЧП 2026 (механический): биомасса +33% даёт частичное восстановление объёмов при мягких ценах → 6 500 млн. EPS_fwd = 6 500/87,88 = "+f"{mc['eps_fwd']} ₽.",
     f"3) Цена (forward) = P/E {mc['pe_used']} × EPS_fwd {mc['eps_fwd']} = {mc['price_pe_fwd']} ₽.",
     f"4) Справочно backward = P/E {mc['pe_used']} × скорр. EPS-2025 {mc['eps_backward']} ₽ = {mc['price_pe_back']} ₽ (от трога — нижняя граница)."],
   "caveats":[
     "Forward ЧП 6 500 млн — суждение (нет постатейного брокерского консенсуса).",
     "P/E крайне чувствителен к выбору базы прибыли из-за волатильности биоцикла.",
     "Медиана P/E включает годы высокой оценки 2021–2022 (de-rating с тех пор)."]}},

 {"method":"historical_pb","fair_value_per_share":mc['price_pb'],"horizon":"intrinsic_now",
  "key_assumptions":{"pb_used":mc['pb_used'],"basis":f"5y_mean (CV={mc['pb_cv']})",
    "book_value_per_share_used":mc['bvps'],"equity_basis":"balance","cv":mc['pb_cv']},
  "status":"ok",
  "explain":{
   "inputs":{
     "P/B по годам 2021–2025":S(str(mc['pb_5y']),"P/B на конец года [src_1]"),
     "CV выборки":S(f"{mc['pb_cv']}","≤0,55 → среднее [правило методики]"),
     "P/B используемый":S(f"{mc['pb_used']}","среднее 5 лет [src_1]"),
     "BVPS текущий":S(f"{mc['bvps']} ₽","= капитал 39 622 млн / 87,88 млн акций [src_1]"),
     "ощутимый капитал":S("≈ балансовому","биоактивы реальны, гудвил не выделен [src_2]")},
   "steps":[
     f"1) P/B за 2021–2025 = {mc['pb_5y']}. CV={mc['pb_cv']}≤0,55 → СРЕДНЕЕ = {mc['pb_used']}.",
     f"2) BVPS = капитал 39 622 млн / 87,88 млн акций = {mc['bvps']} ₽ (ощутимый ≈ балансовому).",
     f"3) Цена = P/B {mc['pb_used']} × BVPS {mc['bvps']} = {mc['price_pb']} ₽."],
   "caveats":[
     "5y-среднее P/B 1,51 включает годы growth-премии (2021 P/B 2,12); текущий P/B всего 0,89 — сток де-рейтился.",
     "Метод даёт верхнюю границу диапазона; для де-рейтнутой recovery-истории завышает.",
     "Капитал просел в 2025 из-за переоценочного убытка — BVPS чувствителен к биологии."]}},

 {"method":"relative_peers","fair_value_per_share":mc['price_rel'],"horizon":"intrinsic_now",
  "key_assumptions":{"peer_multiple":"ev_ebitda","peer_median":mc['peer_med'],
    "metric_used":"mid-cycle EBITDA 11 310 млн"},
  "status":"ok",
  "explain":{
   "inputs":{
     "конкуренты EV/EBITDA 2025":S("GCHE 4,2; BELU 3,05; RAGR 5,12; ABRD 5,41","агросектор [src_1]"),
     "медиана сектора":S(f"{mc['peer_med']}","медиана 4 компаний [src_1]"),
     "mid-cycle EBITDA AQUA":S("11 310 млн","среднее 2021–2025 (не трог-2025) [src_3]"),
     "чистый долг":S("13 797 млн","конец 2025 [src_1]")},
   "steps":[
     f"1) Выбран EV/EBITDA (циклический агро — P/E на трог-годе ломается). Медиана сектора = {mc['peer_med']}.",
     f"2) EV = {mc['peer_med']} × mid-cycle EBITDA 11 310 = {mc['EV_rel']} млн.",
     f"3) Цена = (EV {mc['EV_rel']} − чистый долг 13 797)/87,88 млн = {mc['price_rel']} ₽."],
   "caveats":[
     "На отчётной EBITDA-2025 (5 722) метод дал бы ~232 ₽ — сильно зависит от базы EBITDA.",
     "Сектор-медиана по 4 компаниям; AQUA исторически торговалась с премией к агро (премиальный продукт)."]}},

 {"method":"CAPM","fair_value_per_share":mc['capm_target'],"horizon":"12m",
  "key_assumptions":{"ke":mc['Ke'],"beta":0.9,"expected_div_yield_pct":2.5},
  "status":"ok",
  "explain":{
   "inputs":{
     "Ke":S(f"{mc['Ke']}%","= 14,6% + 0,9×9,0% [src_cfg]"),
     "ожидаемая дивдоходность":S("2,5%","mid-cycle DPS ~30 ₽ к цене ~ за вычетом [judgement]"),
     "текущая цена":S("412 ₽","MOEX, 2026-05-15 [src_4]")},
   "steps":[
     f"1) Ke = 14,6% + 0,9×9,0% = {mc['Ke']}%.",
     f"2) 12м-таргет = 412 × (1 + (Ke − дивдоходность)) = 412 × (1 + ({mc['Ke']}%−2,5%)) = {mc['capm_target']} ₽.",
     "3) Это ориентир требуемой доходности на 12 мес, не внутренняя стоимость."],
   "caveats":["CAPM-таргет показывает требуемую доходность, не справедливую цену; горизонт 12м, не intrinsic.",
     "Консенсус-агрегаторы дают ~605 ₽ на 12м (recovery), выше нашего CAPM-ориентира 495 ₽."]}},

 {"method":"dividend","fair_value_per_share":mc['price_div'],"horizon":"intrinsic_now",
  "key_assumptions":{"expected_dps_normalized":30.0,"required_dividend_yield_pct":12.0},
  "status":"ok",
  "explain":{
   "inputs":{
     "mid-cycle DPS":S("30 ₽","между трогом 10 ₽ (2025) и пиком 55 ₽ (2023) [src_3]"),
     "требуемая дивдоходность":S("12%","для волатильного агро при ставке 14,5% [judgement]")},
   "steps":[
     "1) Нормализованный DPS ~30 ₽ (история: 2021→8, 2022→30, 2023→55, 2024→40, 2025→10).",
     f"2) Цена = DPS 30 / требуемая дивдоходность 12% = {mc['price_div']} ₽."],
   "caveats":["Дивиденды нерегулярны и привязаны к ND/EBITDA≤3,5 и отсутствию биорисков; 2025-дивиденд под вопросом.",
     "Метод даёт нижнюю границу — дивиденд срезается в плохие годы."]}},
]

J["valuation"]["methods_divergence_note"]="Методы расходятся очень сильно (110–681 ₽): прямое следствие искажения прибыли переоленкой биоактивов и волатильности EBITDA в 2-летнем биоцикле. Кластер intrinsic_now: DCF 172 (mid-cycle FCF при WACC 21%) и дивидендный 250 — внизу; P/E forward 341 и относительная 443 — середина; P/B 681 (5y-среднее на де-рейтнутом стоке) — выброс вверх. Надёжность оценки НИЗКАЯ, коридор умышленно широкий."
J["valuation"]["fair_value_range"]={"conservative":180,"base":320,"current_price":last_price,
  "upside_downside_pct":round((320-last_price)/last_price*100,1)}
J["valuation"]["sensitivity"]={"wacc_grid":mc['r_grid'],"growth_grid":mc['g_grid'],"matrix":mc['sens_matrix']}

J["data_flags"]=[
 "АНОМАЛИЯ (IAS 41): отчётная ЧП/P/E/ROE/ROA искажены неденежной переоценкой биологических активов. 2025: отчётный убыток −2 238 при скорр. ЧП +2 100 (эффект переоценки −4 338). 2023: отчётная ЧП 15 471 ЗАВЫШЕНА переоценочным доходом +6 271 (скорр. 9 200). Для оценки — нормализованная прибыль.",
 "ИСПРАВЛЕНО РАСХОЖДЕНИЕ >5%: отчётная ЧП 2022 в загруженной инфографике (src_1) = 1 127 млн — ОШИБКА агрегатора; официальный релиз компании (src_2): +44% г/г до 12 200 млн. В рядах взято 12 200; старый JSON-1127 заменён.",
 "by_function: себестоимость и валовая прибыль раскрыты в МСФО-таблице с 2021 (src_3); 2016–2020 — null (в источниках не выделены). Себестоимость МСФО уже включает переоценку биоактивов, поэтому валовая маржа 2025 (35,7%) занижена эффектом переоценки.",
 "CFI, CFF, net_change_in_cash, постатейный баланс (запасы/биоактивы/дебиторка/ОС) в загруженной инфографике и доступных агрегаторах не приведены → null; нужна первичная МСФО-форма в sources/ для полной детализации.",
 "Налог: сельхоздеятельность (лосось/форель) облагается налогом на прибыль 0% — устойчивая ставка в DCF = 0% (не 25%); это ПОСТОЯННАЯ льгота, риск пересмотра помечен.",
 "FCF нормализованный построен от mid-cycle EBITDA (а не от волатильного CFO, который проседает в годы наращивания биомассы); фактический FCF 2025 = CFO 2 688 − capex 2 728 = −40 млн.",
 "Forward ЧП для P/E (6 500 млн) и mid-cycle EBITDA (11 310 млн) — оценки/суждения; брокерского постатейного консенсуса по прибыли в источниках нет (есть только ценовой таргет ~605 ₽).",
 "Расхождение методов оценки очень велико (110–681 ₽) → methods_divergence_note; коридор 180–320 ₽ широкий, надёжность НИЗКАЯ. Обе границы ниже текущей цены 412 ₽ (даунсайд −56%…−22%).",
 "relative_peers: медиана агросектора по 4 компаниям из src_1 (GCHE/BELU/RAGR/ABRD); peers.json по сектору будет обновлён при прогоне всего агросектора."]

# ---------------- SELF-CHECKS ----------------
errs=[]
for i in range(N):
    nd=st_debt[i]+lt_debt[i]-cash[i]
    if nd!=net_debt[i]: errs.append(f"net_debt {years[i]}")
# bridge arithmetic: np_adj = np_rep + sum(added-back where amount is the removed reval; sign convention)
# our convention: reval_effect = rep - adj ; adj = rep - reval_effect
reval={2025:-4338,2024:-2538,2023:6271,2022:300,2021:-107}
for y,eff in reval.items():
    i=years.index(y)
    if np_adj[i]!=np_rep[i]-eff: errs.append(f"bridge {y}: adj {np_adj[i]} != rep {np_rep[i]} - reval {eff}")
# fcf=cfo-capex
for i in range(N):
    if fcf[i]!=cfo[i]-capex[i]: errs.append(f"fcf {years[i]}")
# tangible<=total
for i in range(N):
    if J["balance_sheet"]["tangible_equity"][i]>total_equity[i]: errs.append(f"tangible {years[i]}")
# explain type-check
def check_explain(m):
    e=m.get("explain")
    if not e: return [f"{m['method']}: no explain"]
    out=[]
    if not isinstance(e.get("inputs"),dict): out.append(f"{m['method']}: inputs not dict")
    else:
        for k,v in e["inputs"].items():
            if not isinstance(v,str): out.append(f"{m['method']}.inputs.{k} not str ({type(v).__name__})")
    if not isinstance(e.get("steps"),list) or not all(isinstance(x,str) for x in e["steps"]): out.append(f"{m['method']}: steps")
    if not isinstance(e.get("caveats"),list) or not all(isinstance(x,str) for x in e["caveats"]): out.append(f"{m['method']}: caveats")
    return out
for m in J["valuation"]["methods"]:
    errs+=check_explain(m)
# array lengths
for path,arr in [("revenue",revenue),("net_profit_adj",np_adj),("pe_adj_hist",d['pe_adj_hist']),
                 ("roe_adj",d['roe_adj']),("net_debt",net_debt),("ebitda_margin",d['ebitda_margin'])]:
    if len(arr)!=N: errs.append(f"len {path}={len(arr)}")

print("SELF-CHECK ERRORS:",errs if errs else "NONE")
print("total_equity flat field present:", "total_equity" in J["balance_sheet"], "=", J["balance_sheet"]["total_equity"][-1])
print("anomaly_flag top-level (meta):", J["meta"]["anomaly_flag"])

json.dump(J,open('financials.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print("WROTE financials.json")
