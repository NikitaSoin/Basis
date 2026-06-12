import json, statistics as st

YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]

# ---- Market params (config) ----
RF = 14.6          # ОФЗ 10y
ERP = 9.0
G = 3.5            # terminal growth (config default)
TAX = 25.0

# ---- Bank P&L (МСФО, млн руб.) — из загруженной отчётности (src_1), сверено ----
nii   = [23281, 25523, 28911, 40268, 50832, 70557, 77758]   # чистый процентный доход
nfi   = [6819, 7539, 9009, 14893, 12487, 11599, 17893]      # чистый комиссионный доход
opinc = [23804, 28715, 42434, 87346, 84829, 88651, 82133]   # операционный доход
prov  = [7655, 8851, 5214, 6847, 4324, 5284, 15530]          # резервы под кредитные убытки
opex  = [14086, 15205, 8508, 28211, 23614, 25935, 30401]     # операционные расходы
np_   = [7906, 10827, 18083, 47648, 47315, 50779, 37847]     # чистая прибыль

# ---- Balance ----
assets = [673651, 730227, 796557, 839329, 1057302, 1137432, 1305759]
equity = [79370, 88693, 103866, 144780, 173892, 201445, 217430]
liab   = [594281, 641534, 692691, 694549, 883410, 935987, 1088329]
retained = [48456, 57785, 74089, 117122, 146514, 174756, 192051]
loans = [396092, 441925, 500902, 562643, 693570, 791262, 936053]
deposits = [568910, 612013, 667542, 661239, 855006, 901372, 1057371]

# Shares
SH_ORD = 445.83    # млн обыкн.
SH_PREF = 20.10    # млн прив.
PRICE = 289.0      # обыкн., MOEX ~12.06.2026 (упала с 335 на 01.06)
PRICE_PREF = 51.2
PRICE_DATE = "2026-06-12"

# ---- BVPS: совокупный капитал / (обыкн.+прив.) ----
bvps = [round(equity[i] / (SH_ORD + SH_PREF), 2) for i in range(len(YEARS))]

# ---- EPS (на обыкн., упрощённо ЧП/обыкн.) ----
eps_ord = [round(np_[i] / SH_ORD, 2) for i in range(len(YEARS))]

# ---- Returns: ROE/ROA по среднему капиталу/активам ----
# для среднего нужен предыдущий год; 2019 берём по концу года (нет 2018 в ряду) -> приближённо по концу
prev_eq = [79370, 79370, 88693, 103866, 144780, 173892, 201445]  # 2019 prev~ self
prev_as = [673651, 673651, 730227, 796557, 839329, 1057302, 1137432]
roe = [round(np_[i] / ((equity[i] + prev_eq[i]) / 2) * 100, 2) for i in range(len(YEARS))]
roa = [round(np_[i] / ((assets[i] + prev_as[i]) / 2) * 100, 2) for i in range(len(YEARS))]
ros = [round(np_[i] / opinc[i] * 100, 2) for i in range(len(YEARS))]  # ЧП/опер.доход

# ---- bank_metrics уже посчитанные (из отчётности/инфографики) ----
nim  = [3.46, 3.64, 3.79, 4.92, 5.36, 6.43, 6.37]
cor  = [2.0, 2.11, 1.11, 1.29, 0.69, 0.71, 1.66]   # 2025 уточнён 1.66 по инфографике
cir  = [round(opex[i] / opinc[i] * 100, 2) for i in range(len(YEARS))]
n10  = [None, None, None, None, None, 21.8, 20.9]
n12  = [None, None, None, None, None, None, 19.7]   # Н1.2 раскрыт за 2025 (business_model)
ltd  = [round(loans[i] / deposits[i] * 100, 2) for i in range(len(YEARS))]

print("ROE:", roe)
print("ROA:", roa)
print("ROS:", ros)
print("CIR:", cir)
print("LTD:", ltd)
print("BVPS:", bvps)
print("EPS:", eps_ord)

# ===================== НОРМАЛИЗАЦИЯ =====================
# Систематический проход по годам. У банка регулярные резервы под кред.убытки —
# это ОПЕРАЦИОННАЯ статья, НЕ нормализуем (методика: recurring provisions не исключать).
# Курсовых/обесценений гудвилла/разовых продаж в отчёте БСПБ за период не выявлено.
# ETR проверим:
# Прибыль до налога недоступна постатейно из инфографики -> ETR не пересчитываем,
# норматив 25% применяем в прогнозе. Разовых налоговых эффектов не выявлено.
# Вывод: adjusted = reported по всем годам (банк, разовых нет).
np_adj = np_[:]              # = reported
adj_bridge = []              # пустой мост
print("ADJUSTED = REPORTED (банк, разовых факторов не выявлено)")

# tangible_equity: у банка нет существенного гудвилла/сомнительных НМА -> = equity
tangible_equity = equity[:]

# ===================== МУЛЬТИПЛИКАТОРЫ ПО ГОДАМ =====================
# P/E и P/B используем по ТЕКУЩЕЙ цене для current; исторические — по ценам годов.
# Историческую цену по годам берём из инфографики P/B (P/B источника) обратно:
# источник давал P/B по году. Воспользуемся источниковыми P/B и P/E (надёжнее, это
# рыночные цены на конец каждого года).
pb_src = [0.28, 0.30, 0.25, 0.95, 1.01, 0.71, 0.66]   # P/BV из инфографики (2019-2025)
pe_src = [2.85, 2.50, 1.46, 2.88, 3.72, 2.98, 3.81]   # P/E из инфографики (2019-2025)
# Эти P/E уже по reported=adjusted (разовых нет) => pe_adj = pe
pe_adj = pe_src[:]

# ---- 5-летние истор. средние с проверкой CV (правило: среднее, медиана только CV>0.5-0.6)
def mean(x): return sum(x)/len(x)
def cv(x):
    m = mean(x)
    sd = st.pstdev(x)
    return sd/m if m else None

pb5 = pb_src[-5:]   # 2021-2025
pe5 = pe_adj[-5:]
cv_pb = cv(pb5); cv_pe = cv(pe5)
pb_mean = round(mean(pb5), 3)
pb_med = round(st.median(pb5), 3)
pe_mean = round(mean(pe5), 3)
pe_med = round(st.median(pe5), 3)
print(f"\nP/B 5y {pb5}: mean={pb_mean} median={pb_med} CV={cv_pb:.3f}")
print(f"P/E 5y {pe5}: mean={pe_mean} median={pe_med} CV={cv_pe:.3f}")
# CV для P/B: 2021=0.25 -> 2022=0.95 большой разброс
pb_used = pb_mean if cv_pb <= 0.55 else pb_med
pb_basis = "5y_mean" if cv_pb <= 0.55 else f"5y_median (CV={cv_pb:.2f})"
pe_used = pe_mean if cv_pe <= 0.55 else pe_med
pe_basis = "5y_mean" if cv_pe <= 0.55 else f"5y_median (CV={cv_pe:.2f})"
print(f"P/B used={pb_used} ({pb_basis}); P/E used={pe_used} ({pe_basis})")

# ---- current multiples (по текущей цене) ----
mcap_ord = round(PRICE * SH_ORD, 1)             # капитализация обыкн.
mcap_total = round(PRICE * SH_ORD + PRICE_PREF * SH_PREF, 1)
cur_pe = round(PRICE / eps_ord[-1], 2)          # по reported=adjusted EPS 2025
cur_pb = round(mcap_total / equity[-1], 3)      # совокупная капит. / совокупн. капитал
cur_ps = round(mcap_total / opinc[-1], 3)
print(f"\nMcap total={mcap_total}; current P/E={cur_pe}, P/B={cur_pb}, P/S={cur_ps}")

# ===================== ОЦЕНКА =====================
# Ke (CAPM), beta=1.0 для банка-индекса
BETA = 1.0
KE = RF + BETA * ERP
print(f"\nKe = {RF} + {BETA}*{ERP} = {KE}%")

# --- Метод 1: P/BV x ROE — justified P/BV = (ROE - g)/(Ke - g) ---
# Консервативный: ROE 2025 подавленный 18.07 (скачок резервов)
# Базовый: through-cycle ROE ~22% (нормализация CoR к среднему 1.0-1.2%)
def pbv_roe(roe_pct):
    jpb = (roe_pct - G) / (KE - G)
    return round(jpb, 4), round(jpb * bvps[-1], 1)

roe_cons = roe[-1]    # 18.07
roe_base = 22.0       # сквозной
jpb_c, fv_c = pbv_roe(roe_cons)
jpb_b, fv_b = pbv_roe(roe_base)
print(f"\nP/BV×ROE cons: ROE={roe_cons} jPB={jpb_c} -> FV={fv_c}")
print(f"P/BV×ROE base: ROE={roe_base} jPB={jpb_b} -> FV={fv_b}")

# --- Метод 2: исторический P/B ---
fv_histpb = round(pb_used * bvps[-1], 1)
print(f"Истор. P/B: {pb_used} × BVPS {bvps[-1]} = {fv_histpb}")

# --- Метод 3: дивидендная ---
# Итоговый 2025: 26.33 на обыкн. + промежуточный 16.61 = 42.94 итого за 2025
DPS_2025 = 26.33 + 16.61
REQ_YIELD = 15.0   # требуемая дивдоходность (≈ОФЗ + спред)
fv_div = round(DPS_2025 / (REQ_YIELD/100), 1)
print(f"Дивидендная: DPS {DPS_2025} / {REQ_YIELD}% = {fv_div}")

# --- Метод 4: CAPM (12m) ---
# целевой ориентир P/E ≈ 1/Ke; целевая цена = fair_pe × EPS(forward)
fair_pe = round(1/(KE/100), 2)
# forward EPS: через-цикл ЧП ~ ROE_base × BVPS_avg... используем сквозную ЧП:
# нормализованная ЧП ~ roe_base% × средний капитал 2025 ≈ 0.22 × ((217430+201445)/2)
np_norm = roe_base/100 * (equity[-1] + equity[-2]) / 2
eps_fwd = round(np_norm / SH_ORD, 2)
fv_capm = round(fair_pe * eps_fwd, 1)
print(f"CAPM: fair_pe={fair_pe}, eps_fwd(сквозн.)={eps_fwd} -> {fv_capm}")

# --- Относительная (сектор) — медиана банков РФ P/BV ~0.88 (предв., будет уточнено peers.json) ---
peer_pb = 0.88
fv_rel = round(peer_pb * bvps[-1], 1)
print(f"Относительная: peer P/BV {peer_pb} × BVPS {bvps[-1]} = {fv_rel}")

# ===================== ДИАПАЗОН =====================
# Основной — P/BV×ROE (cons/base). Сверка с остальными.
methods_fv = {"pbv_roe_cons": fv_c, "pbv_roe_base": fv_b, "hist_pb": fv_histpb,
              "dividend": fv_div, "capm": fv_capm, "relative": fv_rel}
print("\nВсе методы:", methods_fv)
intrinsic = [fv_c, fv_b, fv_histpb, fv_div, fv_rel]  # intrinsic_now (без CAPM 12m)
cons = round(min(fv_c, fv_div, fv_histpb), 1)
base = round(mean([fv_b, fv_histpb, fv_rel, fv_div]), 1)
opt = round(max(fv_b, fv_rel), 1)
ud_c = round((cons/PRICE - 1)*100, 1)
ud_b = round((base/PRICE - 1)*100, 1)
print(f"\nКоридор: cons={cons} ({ud_c}%), base={base} ({ud_b}%), opt={opt}")
spread = (max(intrinsic)-min(intrinsic))/min(intrinsic)*100
print(f"Расхождение intrinsic методов: {spread:.1f}%")

# revenue growth / np growth для metrics_timeseries
rev_growth = [None] + [round((opinc[i]/opinc[i-1]-1)*100,1) for i in range(1,len(YEARS))]
np_growth = [None] + [round((np_[i]/np_[i-1]-1)*100,1) for i in range(1,len(YEARS))]
nd_ebitda = [None]*len(YEARS)  # банк: не применимо

OUT = dict(YEARS=YEARS, nii=nii, nfi=nfi, opinc=opinc, prov=prov, opex=opex, np_=np_,
    np_adj=np_adj, assets=assets, equity=equity, liab=liab, retained=retained,
    loans=loans, deposits=deposits, bvps=bvps, eps_ord=eps_ord, roe=roe, roa=roa,
    ros=ros, nim=nim, cor=cor, cir=cir, n10=n10, n12=n12, ltd=ltd,
    tangible_equity=tangible_equity, pb_src=pb_src, pe_src=pe_src, pe_adj=pe_adj,
    pb_used=pb_used, pb_basis=pb_basis, cv_pb=round(cv_pb,3), pe_used=pe_used,
    pe_basis=pe_basis, cv_pe=round(cv_pe,3), mcap_total=mcap_total, mcap_ord=mcap_ord,
    cur_pe=cur_pe, cur_pb=cur_pb, cur_ps=cur_ps, KE=KE, BETA=BETA,
    jpb_c=jpb_c, fv_c=fv_c, roe_cons=roe_cons, jpb_b=jpb_b, fv_b=fv_b, roe_base=roe_base,
    fv_histpb=fv_histpb, DPS_2025=DPS_2025, REQ_YIELD=REQ_YIELD, fv_div=fv_div,
    fair_pe=fair_pe, eps_fwd=eps_fwd, fv_capm=fv_capm, peer_pb=peer_pb, fv_rel=fv_rel,
    cons=cons, base=base, opt=opt, ud_c=ud_c, ud_b=ud_b, spread=round(spread,1),
    rev_growth=rev_growth, np_growth=np_growth, nd_ebitda=nd_ebitda,
    PRICE=PRICE, PRICE_PREF=PRICE_PREF, PRICE_DATE=PRICE_DATE, np_norm=round(np_norm,0))
with open('/tmp/bspb_calc.json','w') as f:
    json.dump(OUT, f, ensure_ascii=False)
print("\nSaved /tmp/bspb_calc.json")
