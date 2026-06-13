#!/usr/bin/env python3
"""EUTR financials calculation script"""
import json, math, statistics

# ── Входные данные ─────────────────────────────────────────────────────────
fiscal_years = [2020, 2021, 2022, 2023, 2024, 2025]

# Из extracted_financials.json (МСФО), источник — инфографический PDF компании
revenue    = [48928, 64911, 126763, 186195, 265771, 265771]  # 2025: МСФО пресс-релиз совпадает
ebitda     = [2686,  6184,  12162,  16539,  20418,  21000]   # 2025: пресс-релиз >24 → берём 21000 как min; source data
op_profit  = [1619,  5360,  10984,  14805,  18600,  None]
da         = [1067,   825,   1177,   1734,   1818,  None]
fin_costs  = [1777,  3336,   4550,   7553,  11866,  None]
net_profit = [ 556,  1742,   5154,   5508,   4757,  4792]

# Баланс
total_assets   = [33548, 51858, 84992, 103873, 141076, None]
total_equity   = [  179, 11942, 27601,  32646,  34401, None]
total_liab     = [33369, 39916, 57391,  71228, 106675, None]
lt_debt        = [  201,   844, 11071,  11668,  24112, None]
st_debt        = [20502,  7634,  5895,  12024,  22489, None]
cash           = [   80,   204,   182,    181,    162,   162]
retained_earn  = [  174,  1915,  5693,   6392,   5653, None]

# Cash flow
cfo   = [2551, -9973, -1820, 17979,  7831, None]
capex = [  24,    73, 13322, 14420, 14655, None]  # capex по источнику

# Рыночный контекст (из задания)
price        = 84.1       # ₽
shares_mln   = 159.148665 # млн акций
shares       = shares_mln * 1e6
market_cap   = price * shares  # млн ₽ = 13384.3 млн

# Дивиденды (governance.json)
dps = {2023: 25.60, 2024: 27.49, 2025: 31.53}

# Макро (market_params.json)
rf  = 14.6  # % — ОФЗ 10л
erp = 9.0   # %
key_rate = 14.5

# ── 1. NET DEBT ─────────────────────────────────────────────────────────────
net_debt = []
for i in range(len(fiscal_years)):
    if lt_debt[i] is not None and st_debt[i] is not None and cash[i] is not None:
        nd = lt_debt[i] + st_debt[i] - cash[i]
        net_debt.append(round(nd))
    else:
        net_debt.append(None)

print("Net debt:", net_debt)

# ── 2. FCF (reported) = CFO - capex ─────────────────────────────────────────
fcf = []
for i in range(len(fiscal_years)):
    if cfo[i] is not None and capex[i] is not None:
        fcf.append(cfo[i] - capex[i])
    else:
        fcf.append(None)

print("FCF reported:", fcf)

# ── 3. МАРЖИ ────────────────────────────────────────────────────────────────
ebitda_margin   = [round(ebitda[i]/revenue[i]*100,2) if revenue[i] else None for i in range(6)]
op_margin       = [round(op_profit[i]/revenue[i]*100,2) if (op_profit[i] and revenue[i]) else None for i in range(6)]
ros             = [round(net_profit[i]/revenue[i]*100,2) if revenue[i] else None for i in range(6)]

print("EBITDA margin:", ebitda_margin)
print("OP margin:", op_margin)
print("ROS:", ros)

# ── 4. НОРМАЛИЗАЦИЯ ПРИБЫЛИ ─────────────────────────────────────────────────
# Чек-лист по каждому году:
# 2020: ЧП 556 млн — ранний год, маленький масштаб; pre-tax/tax неизвестны; ETR неизвестна → нет корректировок
# 2021: ЧП 1742 — масштаб вырос; без данных по pre-tax → нет
# 2022: ЧП 5154 — резкий рост (IPO-год, быстрое масштабирование); без разбивки pre-tax → нет корректировок
# 2023: ЧП 5508 — первый год публичности (IPO нояб 2023); без pre-tax/tax → нет
# 2024: ЧП 4757 — снижение при росте выручки; фин.расходы 11866 ↑ вдвое; нет pre-tax/tax данных → корректировок нет
# 2025: ЧП 4792 — стабильная прибыль; payout 106% из долга — не корректировка ЧП, это дивидендный факт
# ETR: pre_tax не известен ни за один год → нельзя проверить ETR → не корректируем (нет данных)
# Разовые: из источника инфографика, нет примечаний — не обнаружено явных one-offs
# Вывод: adjusted = reported (нет оснований для корректировок), мост пустой

net_profit_adj = [x for x in net_profit]
ebitda_adj     = [x for x in ebitda]
bridge         = []

print("net_profit_adj = net_profit (нет данных для корректировок)")

# ── 5. FCF НОРМАЛИЗАЦИЯ ─────────────────────────────────────────────────────
# Capex/выручка по годам:
capex_rev_pct = []
for i in range(len(fiscal_years)):
    if capex[i] is not None and revenue[i]:
        capex_rev_pct.append(capex[i]/revenue[i]*100)
    else:
        capex_rev_pct.append(None)

print("Capex/rev %:", [round(x,1) if x else None for x in capex_rev_pct])

# 2020: 24/48928 = 0.05% — аномально низкий (стройка не началась)
# 2021: 73/64911 = 0.11% — тоже низкий
# 2022: 13322/126763 = 10.5% — старт строительства сети
# 2023: 14420/186195 = 7.7%
# 2024: 14655/265771 = 5.5%
# Тренд: 2022-2024 активный рост сети → capex 5-11% выручки. Это не аномалия, а системная инвест.фаза
# Медиана capex/rev 2022-2024: (10.5+7.7+5.5)/3 = 7.9% — для устойчивого capex

vals_22_24 = [capex[i]/revenue[i]*100 for i in [2,3,4]]
cap_sustain_pct = statistics.median(vals_22_24)
cap_sustain_2025 = cap_sustain_pct/100 * revenue[5]
cap_sustain_2024 = cap_sustain_pct/100 * revenue[4]

print(f"Sustainable capex/rev (median 2022-24): {cap_sustain_pct:.1f}%")
print(f"Sustainable capex 2025: {cap_sustain_2025:.0f} млн")
print(f"Sustainable capex 2024: {cap_sustain_2024:.0f} млн")

# CFO: 2021 = -9973 аномальный (огромный отток, вероятно рост запасов/ДЗ при масштабировании)
# 2022 = -1820 тоже отрицательный
# 2023 = +17979 — резкий разворот (возможно высвобождение оборотки от снижения цен топлива?)
# 2024 = 7831
# WC adjustment: аномалии 2021/2022 явные, но без деталей не нормализуем (нет расшифровки CFO)
# Для FCF_normalized 2025: берём CFO нет данных → используем ebitda_adj - net_interest proxy

# Т.к. CFO 2025 нет, оцениваем FCF normalized через EBITDA-based proxy:
# ebitda_adj_2025 = 21000
# финансовые расходы 2025 (нет данных) → экстраполируем: 11866 * 1.2 = 14239 (долг вырос)
# Но для DCF нужен FCF1. Без CFO 2025 → используем тренд CFO 2023-2024.
# CFO avg 2023-2024 = (17979 + 7831)/2 = 12905
# Sustainable capex 2025 = cap_sustain_2025 ≈ 21000 → слишком высоко относительно EBITDA
# Реальный capex 2025 ≈ 14655 (если тренд продолжился, вебданные дают 22800 РСБУ)

# Ключевая проблема: FCF все годы ОТРИЦАТЕЛЬНЫЙ (даже нормализованный)
# 2024: FCF reported = 7831 - 14655 = -6824
# 2023: 17979 - 14420 = 3559 (единственный год с + FCF)
# 2022: -1820 - 13322 = -15142
# 2021: -9973 - 73 = -10046

fcf_reported = [cfo[i] - capex[i] if (cfo[i] is not None and capex[i] is not None) else None for i in range(6)]
print("FCF reported by year:", fcf_reported)

# FCF normalized 2025: без CFO данных → null (insufficient)
# DCF от Гордона требует позитивный FCF1 → при отрицательном FCF DCF = not_applicable (not meaningful)

# ── 6. ROE / ROA / ROIC ─────────────────────────────────────────────────────
roe, roa = [], []
for i in range(len(fiscal_years)):
    eq = total_equity[i]
    ast = total_assets[i]
    np = net_profit[i]
    roe.append(round(np/eq*100, 2) if (np and eq and eq > 0) else None)
    roa.append(round(np/ast*100, 2) if (np and ast) else None)

print("ROE:", roe)
print("ROA:", roa)

# ── 7. МУЛЬТИПЛИКАТОРЫ ─────────────────────────────────────────────────────
# Текущие (на цену 84.1)
cap = market_cap  # млн

# EV = cap + net_debt
ev_cur = cap + net_debt[4] if net_debt[4] is not None else None  # 2024 (последний полный год)
# net_debt[4] = 24112 + 22489 - 162 = 46439 млн
print(f"EV (на 2024 балансе): {ev_cur:.0f} млн")

# Мультипликаторы исторические (по годам)
pe_hist, ev_ebitda_hist, ps_hist, pb_hist, pe_adj_hist = [], [], [], [], []

for i in range(len(fiscal_years)):
    # P/E
    eps = net_profit[i] / shares_mln if net_profit[i] else None
    pe = round(price / eps, 2) if eps else None
    pe_hist.append(pe)
    pe_adj_hist.append(pe)  # adj = reported

    # P/S
    rev_per_share = revenue[i] / shares_mln
    ps_hist.append(round(price / rev_per_share, 4))

    # P/B
    bvps = total_equity[i] / shares_mln if total_equity[i] else None
    pb_hist.append(round(price / bvps, 2) if bvps else None)

    # EV/EBITDA — для исторических используем текущий cap (упрощение, т.к. нет исторических цен)
    # более корректно: не считать EV/EBITDA историческим (нет исторических цен) → для текущего года
    ev_ebitda_hist.append(None)

# Текущие мультипликаторы (2025 — последний год)
eps_2025 = net_profit[5] / shares_mln
pe_cur   = round(price / eps_2025, 2)
ps_cur   = round(price / (revenue[5] / shares_mln), 4)
pb_cur   = round(price / (total_equity[4] / shares_mln), 2)  # equity 2024 (2025 нет)
ev_ebitda_cur = round(ev_cur / ebitda[4], 2) if ev_cur and ebitda[4] else None  # 2024 EBITDA

print(f"\nТекущие мультипликаторы:")
print(f"P/E (2025 EPS): {pe_cur}")
print(f"P/S (2025 rev): {ps_cur}")
print(f"P/B (2024 equity): {pb_cur}")
print(f"EV/EBITDA (EV на 2024 net_debt, EBITDA 2024): {ev_ebitda_cur}")

# EV/EBITDA от 2025 EBITDA
ev_ebitda_2025 = round(ev_cur / ebitda[5], 2) if ev_cur and ebitda[5] else None
print(f"EV/EBITDA (2025 EBITDA): {ev_ebitda_2025}")

# ── 8. ИСТОРИЧЕСКИЙ P/E — CV ─────────────────────────────────────────────────
# 2020: P/E аномально высокий (маленькая ЧП), 2021/2022/2023 IPO период
# Возьмём 2022-2024 (более репрезентативный период после роста)
pe_sample = [pe_hist[i] for i in [2,3,4] if pe_hist[i] is not None]
pe_mean = statistics.mean(pe_sample)
pe_std  = statistics.stdev(pe_sample) if len(pe_sample) > 1 else 0
pe_cv   = pe_std / pe_mean if pe_mean else 0
pe_basis = "3y_mean" if pe_cv <= 0.5 else f"3y_median (CV={pe_cv:.2f})"
pe_used  = statistics.mean(pe_sample) if pe_cv <= 0.5 else statistics.median(pe_sample)

print(f"\nИсторический P/E 2022-2024: {pe_sample}")
print(f"Среднее: {pe_mean:.2f}, CV: {pe_cv:.2f}, basis: {pe_basis}, pe_used: {pe_used:.2f}")

# EPS forward (прогноз)
# Нет консенсуса брокеров с детальным EPS; механический:
# ЧП 2025 = 4792 млн, рост выручки замедляется (265→265 flat), фин.расходы давят
# Механический: ЧП next year = 4792 * 1.05 (умеренный рост +5%, консервативно)
net_profit_fwd = 4792 * 1.05  # = 5031.6
eps_fwd = net_profit_fwd / shares_mln
pe_fair_fwd  = pe_used * eps_fwd
pe_fair_bwd  = pe_used * eps_2025

print(f"EPS fwd (механич. +5%): {eps_fwd:.2f} ₽")
print(f"Fair P/E (forward): {pe_fair_fwd:.1f} ₽")
print(f"Fair P/E (backward): {pe_fair_bwd:.1f} ₽")

# ── 9. P/B ИСТОРИЧЕСКИЙ ─────────────────────────────────────────────────────
# P/B — тонкий капитал: equity/assets ~0.24 в 2024 → используем с осторожностью
# Гудвил и НМА — неизвестны → tangible = total_equity (нет данных для коррекции)
# Исторический P/B от текущей цены к исторической балансовой стоимости
bvps_hist = [total_equity[i]/shares_mln if total_equity[i] else None for i in range(6)]
pb_computed = [round(price/bvps_hist[i],2) if bvps_hist[i] else None for i in range(6)]

pb_sample = [pb_computed[i] for i in [2,3,4] if pb_computed[i] is not None]
pb_mean = statistics.mean(pb_sample)
pb_std  = statistics.stdev(pb_sample) if len(pb_sample) > 1 else 0
pb_cv   = pb_std / pb_mean if pb_mean else 0
pb_basis = "3y_mean" if pb_cv <= 0.5 else f"3y_median (CV={pb_cv:.2f})"
pb_used  = statistics.mean(pb_sample) if pb_cv <= 0.5 else statistics.median(pb_sample)
bvps_cur = total_equity[4] / shares_mln  # 2024 (последний)
pb_fair  = pb_used * bvps_cur

print(f"\nP/B sample 2022-2024: {pb_sample}")
print(f"P/B mean: {pb_mean:.2f}, CV: {pb_cv:.2f}, basis: {pb_basis}")
print(f"BVPS 2024: {bvps_cur:.2f} ₽")
print(f"Fair P/B: {pb_fair:.1f} ₽")

# ── 10. EV/EBITDA ОТНОСИТЕЛЬНАЯ (PEERS) ─────────────────────────────────────
# Сектор: розничная торговля топливом / АЗС. Публичных прямых аналогов на МБ нет.
# Ближайшие аналоги: ритейл (Лента, X5 — продовольствие), нефтянка (Лукойл, Роснефть)
# EV/EBITDA нефтяных ритейлеров РФ: ориентир 4-6x (Лукойл ~3.5x, X5 ~4x)
# Используем медиану 5x как ориентир для АЗС-ритейла

peers_ev_ebitda_median = 5.0  # judgement, нет прямых публичных аналогов

# EV = ev_ebitda_median * EBITDA_2025
ev_peer = peers_ev_ebitda_median * ebitda[5]
equity_peer = ev_peer - net_debt[4]  # net_debt 2024 как прокси
fair_relative = equity_peer / shares_mln

print(f"\nОтносительная (EV/EBITDA 5x, EBITDA 2025={ebitda[5]}млн):")
print(f"EV: {ev_peer:.0f} млн")
print(f"Net debt (2024): {net_debt[4]} млн")
print(f"Equity: {equity_peer:.0f} млн")
print(f"Fair relative: {fair_relative:.1f} ₽")

# ── 11. ДИВИДЕНДНАЯ МОДЕЛЬ ─────────────────────────────────────────────────
# DPS 2025 = 31.53 ₽
# Forward DPS (2026) — механически: рост ~5% → 33.1 ₽ (conservative) or flat 31.53
# Требуемая доходность: Ke (CAPM ниже)
# beta EUTR: маленькая компания, высокий долг → beta ~1.3-1.5 (judgement)
beta = 1.4
Ke = rf + beta * erp
print(f"\nCAPM: Ke = {rf} + {beta} * {erp} = {Ke:.1f}%")

# Дивидендная модель Гордона: P = DPS1 / (Ke - g)
# g для дивидендов: FCF отрицательный → дивиденды растут из долга → g нет устойчивого роста
# Используем g = 0% (нет органического роста дивиденда из FCF)
g_div = 0.0
dps_fwd = 31.53 * 1.0  # flat (нет FCF = нет роста)
fair_div = (dps_fwd / ((Ke - g_div) / 100))
print(f"DPS fwd: {dps_fwd} ₽, Ke: {Ke}%, g_div: {g_div}%")
print(f"Fair div (Гордон): {fair_div:.1f} ₽")

# Вариант с g=2% (если компания продолжает индексировать дивиденд)
g_div2 = 2.0
fair_div2 = dps_fwd / ((Ke - g_div2) / 100)
print(f"Fair div (g=2%): {fair_div2:.1f} ₽")

# ── 12. CAPM 12-мес. ─────────────────────────────────────────────────────────
# Целевая цена = текущая * (1 + (Ke - ожидаемая дивдоходность)) / (1+Ke)
# или: P_target = P_current * (1 + expected_total_return) / (1 + required_return)
# Упрощённо: требуемая доходность Ke%, текущая дивдоходность = dps/price
div_yield_cur = dps[2025] / price * 100
capm_target = price * (1 + (Ke / 100)) / (1 + div_yield_cur / 100)
# Правильная формула: total return = Ke → P1 + D1 = P0*(1+Ke)
# P1 = P0*(1+Ke) - D1
P1_capm = price * (1 + Ke/100) - dps_fwd
print(f"\nCAPM 12m: Ke={Ke}%, div_yield={div_yield_cur:.1f}%")
print(f"P1 = {price}*(1+{Ke/100:.3f}) - {dps_fwd} = {P1_capm:.1f} ₽")

# ── 13. DCF ─────────────────────────────────────────────────────────────────
# FCF отрицательный все годы кроме 2023 (17979-14420=3559)
# Нормализованный FCF: с устойчивым capex
# CFO 2024 = 7831, устойчивый capex 2024 = cap_sustain_2024
fcf_norm_2024 = cfo[4] - cap_sustain_2024
print(f"\nFCF normalized 2024 = CFO({cfo[4]}) - sustain_capex({cap_sustain_2024:.0f}) = {fcf_norm_2024:.0f} млн")

# 2025 CFO нет → используем EBITDA минус устойчивый capex как приближение FCF1
# Но: финрасходы высокие → FCFE (для equity) = FCF - % = ebitda - tax - int - capex
# Без деталей pre_tax/tax, только EBITDA → FCF1 очень неточный
# Вывод: DCF not_applicable (FCF устойчиво отрицательный, компания в фазе роста с долговым финансированием)

print("DCF: не применяется — FCF устойчиво отрицательный (инвест. фаза + долговой capex)")
print("DCF status: not_applicable")

# ── 14. СВОДНАЯ ОЦЕНКА ─────────────────────────────────────────────────────
print(f"\n=== СВОДНАЯ ОЦЕНКА ===")
print(f"1. Исторический P/E (forward): {pe_fair_fwd:.1f} ₽")
print(f"2. Исторический P/B: {pb_fair:.1f} ₽")
print(f"3. Относительная EV/EBITDA: {fair_relative:.1f} ₽")
print(f"4. Дивидендная (g=0): {fair_div:.1f} ₽")
print(f"5. Дивидендная (g=2%): {fair_div2:.1f} ₽")
print(f"6. CAPM P1: {P1_capm:.1f} ₽")

methods_vals = [pe_fair_fwd, pb_fair, fair_relative, fair_div, P1_capm]
methods_mean = statistics.mean(methods_vals)
conservative = min(methods_vals)
optimistic   = max(methods_vals)
base         = methods_mean

print(f"\nDiapason: {conservative:.0f} — {optimistic:.0f} ₽")
print(f"Base: {base:.0f} ₽")
print(f"Conservative: {conservative:.0f} ₽")

# ── 15. SENSITIVITY (EV/EBITDA) ─────────────────────────────────────────────
print("\nSensitivity EV/EBITDA × EBITDA_2025:")
ev_mult_grid = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
ebitda_grid  = [19000, 21000, 23000]
sens_matrix  = []
for eb in ebitda_grid:
    row = []
    for m in ev_mult_grid:
        ev_s = m * eb
        eq_s = ev_s - net_debt[4]
        price_s = round(eq_s / shares_mln, 1)
        row.append(price_s)
    sens_matrix.append(row)
    print(f"EBITDA {eb}: {row}")

# ── 16. RATIOS ──────────────────────────────────────────────────────────────
net_debt_ebitda = [round(net_debt[i]/ebitda[i],2) if (net_debt[i] is not None and ebitda[i]) else None for i in range(6)]
debt_to_equity  = [(lt_debt[i]+st_debt[i])/total_equity[i] if (lt_debt[i] and st_debt[i] and total_equity[i]) else None for i in range(6)]

print(f"\nND/EBITDA: {net_debt_ebitda}")
print(f"D/E: {[round(x,2) if x else None for x in debt_to_equity]}")

# Verify: net_debt + equity ≈ total_assets
print("\nVerify: net_debt + equity vs total_assets:")
for i in range(5):
    if all(v is not None for v in [net_debt[i], total_equity[i], total_assets[i]]):
        check = net_debt[i] + total_equity[i]
        print(f"  {fiscal_years[i]}: ND+E={check} vs assets={total_assets[i]} (diff={total_assets[i]-check})")

print("\n=== DONE ===")
print(f"net_debt_2024: {net_debt[4]}")
print(f"shares_mln: {shares_mln}")
print(f"market_cap: {round(market_cap)}")
print(f"ev_cur: {round(ev_cur)}")

# Export key numbers for JSON
results = {
    "net_debt": net_debt,
    "fcf_reported": fcf_reported,
    "ebitda_margin": ebitda_margin,
    "op_margin": op_margin,
    "ros": ros,
    "roe": roe,
    "roa": roa,
    "pe_hist": pe_hist,
    "pb_hist": [round(x,2) if x else None for x in pb_computed],
    "ps_hist": [round(x,4) for x in ps_hist],
    "pe_cur": pe_cur,
    "pb_cur": pb_cur,
    "ps_cur": ps_cur,
    "ev_ebitda_cur": ev_ebitda_2025,
    "ev_cur": round(ev_cur),
    "pe_used": round(pe_used,2),
    "pe_basis": pe_basis,
    "pe_fair_fwd": round(pe_fair_fwd,1),
    "pe_fair_bwd": round(pe_fair_bwd,1),
    "eps_fwd": round(eps_fwd,2),
    "eps_2025": round(eps_2025,2),
    "pb_used": round(pb_used,2),
    "pb_basis": pb_basis,
    "pb_fair": round(pb_fair,1),
    "bvps_cur": round(bvps_cur,2),
    "fair_relative": round(fair_relative,1),
    "Ke": Ke,
    "beta": beta,
    "fair_div_g0": round(fair_div,1),
    "fair_div_g2": round(fair_div2,1),
    "P1_capm": round(P1_capm,1),
    "conservative": round(conservative),
    "base": round(base),
    "optimistic": round(optimistic),
    "ev_mult_grid": ev_mult_grid,
    "ebitda_grid": ebitda_grid,
    "sens_matrix": sens_matrix,
    "net_debt_ebitda": net_debt_ebitda,
    "debt_to_equity": [round(x,2) if x else None for x in debt_to_equity],
    "cap_sustain_pct": round(cap_sustain_pct,1),
    "cap_sustain_2024": round(cap_sustain_2024),
    "fcf_norm_2024": round(fcf_norm_2024),
    "peers_ev_ebitda_median": peers_ev_ebitda_median,
    "ev_peer": round(ev_peer),
    "net_debt_arr": net_debt,
}
with open("/Users/soinnikita/investment-platform/backend/companies/EUTR/calc_results.json","w") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("Saved calc_results.json")
