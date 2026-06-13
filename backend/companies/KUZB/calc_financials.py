"""
KUZB financials calculation script
Считает все мультипликаторы, оценки, мосты нормализации.
"""
import json, math, statistics

# ============================================================
# ВХОДНЫЕ ДАННЫЕ
# ============================================================
price = 0.030927        # ₽, из rates.csv
shares = 22_503_490_875 # шт
cap_mln = price * shares / 1_000_000  # млн ₽

# Конфиг
Rf = 14.6 / 100
ERP = 9.0 / 100
key_rate = 14.5 / 100

fiscal_years = [2020, 2021, 2022, 2023, 2024, 2025]
N = len(fiscal_years)

# P&L (млн)
net_profit         = [None, 87.5, 163.5, 224.0, 195.0, 104.5]
pre_tax_profit     = [None, 121.4, 182.5, 224.0, 260.0, 138.7]
income_tax         = [None, 33.9, 19.0, 0.0, 65.0, 34.2]
net_interest_income= [None, 390.0, 450.0, 590.0, 590.0, 589.9]
net_fee_income     = [None, None, None, None, None, 163.5]
operating_income   = [None, None, None, 786.0, None, 753.4]
operating_expenses = [None, 269.0, 291.0, 440.0, None, 619.0]

# Баланс (млн)
total_assets   = [6980.0, 6600.0, 6700.0, 10300.0, 9600.0, 10200.0]
total_equity   = [676.4, 645.0, 681.2, 1053.0, 874.1, 995.3]
total_liab     = [None, None, None, 9247.0, 8726.0, 9204.7]
loans_net      = [None, None, None, 6580.0, 6260.0, 6500.0]
deposits       = [None, None, None, 8690.0, 8100.0, 8400.0]
share_capital  = [None, None, None, 450.0, 450.0, 450.0]
retained_earn  = [None, 195.0, 381.0, 581.0, 581.0, 686.5]

# ============================================================
# ETR CHECK — нормализация
# ============================================================
etr_reported = []
for i in range(N):
    if pre_tax_profit[i] and income_tax[i] is not None:
        etr_reported.append(round(income_tax[i] / pre_tax_profit[i] * 100, 1))
    else:
        etr_reported.append(None)

print("ETR по годам:", etr_reported)
# 2022: income_tax=19 / pre_tax=182.5 = 10.4% — аномально низко
# 2023: income_tax=0 / pre_tax=224 = 0% — очень аномально (нулевой налог)
# 2024: income_tax=65 / pre_tax=260 = 25% — норма
# 2025: income_tax=34.2 / pre_tax=138.7 = 24.7% — норма

# Устойчивая ETR = 25% (с 2025 базовая ставка в РФ для банков)
etr_sustainable = 25.0

# Нормализация:
# 2022: ETR=10.4% (аномально низко) → корректировка
np_adj_2022 = pre_tax_profit[2] * (1 - etr_sustainable/100)
delta_2022 = np_adj_2022 - net_profit[2]
print(f"2022: reported NP={net_profit[2]}, adj NP={np_adj_2022:.1f}, delta={delta_2022:.1f}")

# 2023: ETR=0% → корректировка
np_adj_2023 = pre_tax_profit[3] * (1 - etr_sustainable/100)
delta_2023 = np_adj_2023 - net_profit[3]
print(f"2023: reported NP={net_profit[3]}, adj NP={np_adj_2023:.1f}, delta={delta_2023:.1f}")

# 2024, 2025: ETR ~25% — не корректируем
np_adj_2024 = net_profit[4]  # 195.0
np_adj_2025 = net_profit[5]  # 104.5

# 2021: ETR = 33.9/121.4 = 27.9% — чуть выше нормы, minor, не корректируем (близко к 25%)
np_adj_2021 = net_profit[1]  # 87.5

net_profit_adj = [None, np_adj_2021, np_adj_2022, np_adj_2023, np_adj_2024, np_adj_2025]
print("net_profit_adj:", [round(x,1) if x else None for x in net_profit_adj])

# Bridge items
bridge = [
    {
        "year": 2022,
        "item": "Налоговая нормализация: ETR 10.4% → устойчивая 25% (разовый налоговый эффект/льгота)",
        "amount": round(delta_2022, 1),
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    },
    {
        "year": 2023,
        "item": "Налоговая нормализация: ETR 0% → устойчивая 25% (нулевой налог — разовый эффект отложенных налогов или льгота)",
        "amount": round(delta_2023, 1),
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    }
]
# Остальные годы: 2020 нет данных, 2021 ETR=27.9%~норма, 2024/2025~25%
bridge_note = (
    "2020: данных нет — пропуск. "
    "2021: ETR 27.9% — близко к норме (25%), разового не выявлено, adjusted=reported. "
    "2022: ETR 10.4% аномально низко (возможна временная льгота или эффект ОНО) → досчёт до 25%. "
    "2023: ETR 0% — нулевой налог при прибыли до налога 224 млн — сильная аномалия; РСБУ допускает зачёты отложенных налогов; корректируем до 25%. "
    "2024: ETR 25.0% — норма, adjusted=reported. "
    "2025: ETR 24.7% — норма, adjusted=reported."
)

# ============================================================
# ROE / ROA (adjusted) по годам
# Для банка ROE = NP / средний капитал
# ============================================================
roe_adj = []
roa_adj = []
for i in range(N):
    if net_profit_adj[i] is not None and total_equity[i] is not None:
        # средний капитал
        eq_prev = total_equity[i-1] if i > 0 else None
        if eq_prev:
            avg_eq = (total_equity[i] + eq_prev) / 2
        else:
            avg_eq = total_equity[i]
        roe = net_profit_adj[i] / avg_eq * 100
        roe_adj.append(round(roe, 1))
        # ROA
        as_prev = total_assets[i-1] if i > 0 else None
        if as_prev:
            avg_as = (total_assets[i] + as_prev) / 2
        else:
            avg_as = total_assets[i]
        roa = net_profit_adj[i] / avg_as * 100
        roa_adj.append(round(roa, 1))
    else:
        roe_adj.append(None)
        roa_adj.append(None)

print("ROE adj:", roe_adj)
print("ROA adj:", roa_adj)

# ============================================================
# МУЛЬТИПЛИКАТОРЫ (P/B, P/E) по годам — от текущей цены
# ============================================================
bvps = [total_equity[i] * 1_000_000 / shares for i in range(N)]
eps_adj = [net_profit_adj[i] * 1_000_000 / shares if net_profit_adj[i] else None for i in range(N)]

pb_hist = [round(price / bvps[i], 2) if bvps[i] else None for i in range(N)]
pe_adj_hist = [round(price / eps_adj[i], 1) if eps_adj[i] else None for i in range(N)]

print("BVPS (₽):", [round(x,4) for x in bvps])
print("EPS adj (₽):", [round(x,6) if x else None for x in eps_adj])
print("P/B hist:", pb_hist)
print("P/E adj hist:", pe_adj_hist)

# Текущий P/B (по последнему equity)
current_pb = round(cap_mln / total_equity[5], 3)
print(f"Текущий P/B: {current_pb:.3f}")

# Текущий P/E adj (по последней adj NP)
current_pe_adj = round(cap_mln / net_profit_adj[5], 1)
print(f"Текущий P/E adj: {current_pe_adj:.1f}")

# ============================================================
# ИСТОРИЧЕСКИЙ СРЕДНИЙ P/B  (правило CV)
# ============================================================
pb_valid = [x for x in pb_hist if x is not None]
pb_mean = statistics.mean(pb_valid)
pb_stdev = statistics.stdev(pb_valid)
cv_pb = pb_stdev / pb_mean
print(f"P/B: mean={pb_mean:.3f}, stdev={pb_stdev:.3f}, CV={cv_pb:.3f}")
# CV < 0.5 → среднее; CV > 0.5 → медиана
if cv_pb > 0.5:
    pb_used = statistics.median(pb_valid)
    pb_basis = f"5y_median (CV={cv_pb:.2f})"
else:
    pb_used = pb_mean
    pb_basis = f"5y_mean (CV={cv_pb:.2f})"
print(f"P/B used: {pb_used:.3f}, basis: {pb_basis}")

# ============================================================
# ИСТОРИЧЕСКИЙ СРЕДНИЙ P/E adj (правило CV)
# ============================================================
pe_valid = [x for x in pe_adj_hist if x is not None]
pe_mean = statistics.mean(pe_valid)
pe_stdev = statistics.stdev(pe_valid)
cv_pe = pe_stdev / pe_mean
print(f"P/E adj: mean={pe_mean:.1f}, stdev={pe_stdev:.1f}, CV={cv_pe:.3f}")
if cv_pe > 0.5:
    pe_used = statistics.median(pe_valid)
    pe_basis = f"5y_median (CV={cv_pe:.2f})"
else:
    pe_used = pe_mean
    pe_basis = f"5y_mean (CV={cv_pe:.2f})"
print(f"P/E used: {pe_used:.1f}, basis: {pe_basis}")

# ============================================================
# МЕТОД 1: P/BV × ROE (Гордон для банков)
# Справедливый P/B = (ROE - g) / (Ke - g)
# ============================================================
# Beta малого регионального банка: высокий специфический риск
# Для малого неликвидного регионального банка применяем повышенную бету
beta = 1.3  # консервативно, малый банк, низкая ликвидность, высокий кредитный риск

Ke = Rf + beta * ERP
print(f"\nKe = {Rf*100:.1f}% + {beta} × {ERP*100:.1f}% = {Ke*100:.1f}%")

# Устойчивый ROE: берём средний adjusted ROE за 2024–2025 (последние два нормальных года)
roe_adj_2024 = roe_adj[4]
roe_adj_2025 = roe_adj[5]
roe_sustainable = (roe_adj_2024 + roe_adj_2025) / 2
print(f"Устойчивый ROE: ({roe_adj_2024}% + {roe_adj_2025}%) / 2 = {roe_sustainable:.1f}%")

g = 3.5 / 100  # terminal growth = default max

# Справедливый P/B по модели Гордона
ROE_s = roe_sustainable / 100
fair_pb_gordon = (ROE_s - g) / (Ke - g)
print(f"Fair P/B (Gordon) = ({ROE_s*100:.1f}% - {g*100:.1f}%) / ({Ke*100:.1f}% - {g*100:.1f}%) = {fair_pb_gordon:.3f}")

# Справедливая цена от последнего BVPS
bvps_2025 = bvps[5]
fair_price_gordon = fair_pb_gordon * bvps_2025
print(f"Fair price (Gordon P/BV×ROE): {fair_pb_gordon:.3f} × {bvps_2025:.5f} = {fair_price_gordon:.5f} ₽")

# ============================================================
# МЕТОД 2: Исторический P/B × BVPS
# ============================================================
fair_price_hist_pb = pb_used * bvps_2025
print(f"\nFair price (hist P/B): {pb_used:.3f} × {bvps_2025:.5f} = {fair_price_hist_pb:.5f} ₽")

# ============================================================
# МЕТОД 3: Дивидендная
# Из rates.csv дивиденд=0.0022₽ — проверим
# governance.json: выплаты не подтверждены, нерегулярны
# Вероятность: нет устойчивой дивполитики → метод ненадёжен
# ============================================================
# Тем не менее считаем как reference
dps = 0.0022  # из rates.csv (но источник неясен, скорее всего исторический)
# Требуемая дивдоходность ≈ Ke (для зрелого банка)
# Дивидендная цена = DPS / Ke (упрощённая perpetuity, без роста)
fair_price_div = dps / Ke
print(f"\nFair price (dividend, DPS={dps}, Ke={Ke*100:.1f}%): {fair_price_div:.5f} ₽")
# Дивидендная — ненадёжна из-за нерегулярности; status = low_confidence

# ============================================================
# МЕТОД 4: Исторический P/E adj
# Прогнозный EPS forward: механический (нет консенсуса)
# Динамика прибыли: 2024→2025 -46% из-за роста ставки → рост КС снижается
# В 2026 ожидаем восстановление: КС снижается с июня 2025, Ke снижается
# Механический прогноз: NP_2026 ≈ среднее adj 2024/2025 * 1.1 (умеренное восстановление)
# ============================================================
np_avg_2425 = (net_profit_adj[4] + net_profit_adj[5]) / 2
np_forward_2026 = np_avg_2425 * 1.10  # +10% восстановление при снижении ставки
eps_forward = np_forward_2026 * 1_000_000 / shares
print(f"\nNP forward 2026 (mech): {np_forward_2026:.1f} млн")
print(f"EPS forward 2026: {eps_forward:.7f} ₽")
fair_price_hist_pe = pe_used * eps_forward
print(f"Fair price (hist P/E × EPS_fwd): {pe_used:.1f} × {eps_forward:.7f} = {fair_price_hist_pe:.5f} ₽")

# ============================================================
# ОТНОСИТЕЛЬНАЯ (сектор) — региональные банки
# Для KUZB нет релевантных региональных аналогов на бирже
# Ближайшие: крупные банки (Сбер P/B~1, ВТБ P/B~0.4, БСП P/B~0.8)
# Малый банк торгуется с дополнительным дисконтом к крупным
# Медиана сектора P/B: используем Сбер/ВТБ/БСП/Тинькофф ~0.7 (сейчас рынок)
# ============================================================
sector_pb_median = 0.7  # оценка по публичным банкам, из peers.json если есть
fair_price_relative = sector_pb_median * bvps_2025
print(f"\nFair price (relative P/B={sector_pb_median}): {fair_price_relative:.5f} ₽")

# ============================================================
# CAPM (12 мес)
# Ke уже посчитан выше
# Ожидаемая дивдоходность = 0 (дивиденды не подтверждены в 2025)
# 12m target = current * (1 + (Ke - div_yield))
# Но для неликвидного банка CAPM менее информативен
# ============================================================
div_yield = 0.0  # нет дивидендов в 2025
capm_12m = price * (1 + (Ke - div_yield))
print(f"\nCAPM 12m: {price} × (1 + {Ke*100:.1f}% - {div_yield*100:.1f}%) = {capm_12m:.5f} ₽")
# Это просто Ke = минимально требуемая доходность

# ============================================================
# ИТОГ МЕТОДОВ
# ============================================================
print("\n=== ИТОГ МЕТОДОВ ===")
print(f"1. P/BV×ROE (Gordon): {fair_price_gordon:.5f} ₽")
print(f"2. Исторический P/B:  {fair_price_hist_pb:.5f} ₽")
print(f"3. Исторический P/E:  {fair_price_hist_pe:.5f} ₽")
print(f"4. Относительная:     {fair_price_relative:.5f} ₽")
print(f"5. Дивидендная:       {fair_price_div:.5f} ₽ (low confidence)")
print(f"6. CAPM 12m:          {capm_12m:.5f} ₽")
print(f"\nТекущая цена: {price:.6f} ₽")

# Коридор: берём ключевые методы (1, 2, 3)
# Conservative = min из (Gordon, hist P/B, hist P/E)
# Base = среднее из (Gordon, hist P/B, hist P/E)
# Optimistic = max из них
methods_main = [fair_price_gordon, fair_price_hist_pb, fair_price_hist_pe]
conservative = min(methods_main)
base = statistics.mean(methods_main)
optimistic = max(methods_main)
print(f"\nКоридор: conservative={conservative:.5f}, base={base:.5f}, optimistic={optimistic:.5f}")

# Расхождение методов
max_div = (optimistic - conservative) / conservative * 100
print(f"Расхождение методов: {max_div:.0f}%")

# ============================================================
# Implied exit multiple (для проверки)
# Для банка: implied P/B at fair price
# ============================================================
print(f"\nImplied P/B at fair_gordon: {fair_price_gordon/bvps_2025:.3f}")
print(f"Implied P/B at fair_hist_pb: {fair_price_hist_pb/bvps_2025:.3f}")

# ============================================================
# SENSITIVITY: Ke × ROE (для Gordon метода)
# ============================================================
print("\n=== SENSITIVITY P/BV×ROE ===")
ke_grid = [Ke - 0.02, Ke, Ke + 0.02]
roe_grid = [roe_sustainable/100 - 0.03, roe_sustainable/100, roe_sustainable/100 + 0.03]
print(f"Ke grid: {[f'{k*100:.1f}%' for k in ke_grid]}")
print(f"ROE grid: {[f'{r*100:.1f}%' for r in roe_grid]}")
matrix = []
for roe_s in roe_grid:
    row = []
    for ke_s in ke_grid:
        pb_s = (roe_s - g) / (ke_s - g)
        price_s = pb_s * bvps_2025
        row.append(round(price_s, 5))
    matrix.append(row)
    print(row)

# ============================================================
# bank_metrics
# ============================================================
nim = []  # нет данных по ЧПД / активам (ЧПД есть, активы есть)
for i in range(N):
    if net_interest_income[i] and total_assets[i]:
        avg_as = (total_assets[i] + (total_assets[i-1] if i>0 else total_assets[i])) / 2
        nim.append(round(net_interest_income[i] / avg_as * 100, 2))
    else:
        nim.append(None)
print("NIM %:", nim)

# CIR (cost-income ratio)
cir = []
for i in range(N):
    if operating_expenses[i] and operating_income[i]:
        cir.append(round(operating_expenses[i] / operating_income[i] * 100, 1))
    else:
        cir.append(None)
print("CIR %:", cir)

# Loan/deposits ratio
ldr = []
for i in range(N):
    if loans_net[i] and deposits[i]:
        ldr.append(round(loans_net[i] / deposits[i] * 100, 1))
    else:
        ldr.append(None)
print("Loans/Deposits %:", ldr)

# Capital adequacy proxy: total_equity / total_assets (proxy H1)
h1_proxy = [round(total_equity[i]/total_assets[i]*100, 1) for i in range(N)]
print("Capital/Assets % (H1 proxy):", h1_proxy)

print("\n--- DONE ---")
print(f"Shares: {shares:,}")
print(f"Cap mlн: {cap_mln:.2f}")
print(f"bvps_2025: {bvps_2025:.6f} ₽")
print(f"eps_adj_2025: {eps_adj[5]:.7f} ₽")
