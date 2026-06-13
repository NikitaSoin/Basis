#!/usr/bin/env python3
"""
MRKZ financials.json calculator
Все числа считаются здесь, никаких ручных значений в JSON.
"""
import json, math, statistics

# ── ВХОДНЫЕ ДАННЫЕ ─────────────────────────────────────────────────────────────
# Из rates.csv / задания
price = 0.168176          # ₽
shares = 95_785_923_138   # штук
market_cap_mln = price * shares / 1e6   # млн ₽

dps_2024 = 0.0012724      # из rates.csv

# Macro (config/market_params.json)
Rf   = 14.6 / 100
ERP  = 9.0  / 100
g_terminal = 3.5 / 100
tax_norm = 25.0 / 100

# ── ОТЧЁТНОСТЬ (extracted_financials.json) ─────────────────────────────────────
# Годы: [2020, 2021, 2022, 2023, 2024]  — 2020-2022 null для P&L/баланс/ОДД
#  P&L (2023, 2024)
revenue      = {2023: 53709.835,  2024: 62720.138}
op_profit    = {2023: 408.021,    2024: 3121.741}
da           = {2023: 4910.265,   2024: 4995.162}
ebitda_rep   = {2023: 5318.286,   2024: 8116.903}
fin_costs    = {2023: 1941.225,   2024: 3115.728}
fin_income   = {2023: 393.495,    2024: 1062.629}
pre_tax      = {2023: -1139.709,  2024: 1068.642}
income_tax   = {2023: -115.808,   2024: 601.343}
net_profit   = {2023: -550.973,   2024: 1787.435}   # reported

# Balance sheet (2023, 2024)
ppe          = {2023: 39281.724,  2024: 46199.932}
total_equity = {2023: 16966.826,  2024: 18807.169}
lt_debt      = {2023: 2837.537,   2024: 3018.549}
st_debt      = {2023: 12187.570,  2024: 12425.304}
cash         = {2023: 3692.214,   2024: 10183.059}
total_assets = {2023: 55737.325,  2024: 71227.244}
intangibles  = {2023: 1073.325,   2024: 1111.881}
goodwill     = {2023: 0.0,        2024: 0.0}

# Cash flows
cfo          = {2023: 10988.084,  2024: 14871.064}
cfi          = {2023: -7277.296,  2024: -6780.975}
cff          = {2023: -3801.128,  2024: -1556.199}
capex        = {2023: 7602.880,   2024: 7494.012}

# ── ПРОВЕРКИ АРИФМЕТИКИ ────────────────────────────────────────────────────────
checks = {}
for y in [2023, 2024]:
    net_debt_chk   = (lt_debt[y] + st_debt[y]) - cash[y]
    fcf_chk        = cfo[y] - capex[y]
    net_chg_chk    = cfo[y] + cfi[y] + cff[y]
    checks[y] = {
        "net_debt":   round(net_debt_chk,3),
        "fcf":        round(fcf_chk,3),
        "net_change": round(net_chg_chk,3),
    }
print("CHECKS:", json.dumps(checks, indent=2))

# ── НОРМАЛИЗАЦИЯ ───────────────────────────────────────────────────────────────
# Чек-лист по каждому году:
# 2023: убыток. Pre_tax = -1139.7, tax credit 115.8 → EBT отрицателен.
#   Разовые? В раскрытии нет крупных списаний/курсовых в выжимке.
#   ETR = tax/pre_tax: 2023 pre_tax отрицателен → ETR неприменима как мультипликатор.
#   Убыток операционный: op_profit 408 млн, но финансовые расходы 1941 при доходе 393 →
#   убыток от финансов. Это рецидивирующая структура (долг). Не разовое.
#   → нет крупных разовых корректировок, adjusted = reported 2023.
# 2024: прибыль. ETR = 601.343/1068.642 = 56.3% — АНОМАЛЬНО ВЫСОКО (норма 25%).
#   Значит: либо отложенный налог из прошлых убытков (признан в 2024 как расход), либо
#   иные временные факторы. При норме 25%: adjusted_net = pre_tax * (1-0.25).
#   Однако: компания только что вышла из убытков — ОНА (отложенные налоговые активы) могут
#   тянуть ETR вверх при признании обязательств. Это временный эффект → нормализуем.
#   adjusted_net_2024 = pre_tax_2024 * (1 - tax_norm)

etr_2023 = None   # pre_tax отрицателен, ETR неопределён
etr_2024 = income_tax[2024] / pre_tax[2024]

adj_net_2023 = net_profit[2023]   # нет корректировок, reported = adjusted
# 2023: pre_tax отрицательный → adjusted тоже убыток. ETR не нормализуем (убыток).

adj_net_2024 = pre_tax[2024] * (1 - tax_norm)
bridge_2024_tax = adj_net_2024 - net_profit[2024]   # разница (корректировка)

print(f"\nETR 2024: {etr_2024:.1%}  (норма 25%)")
print(f"adj_net_2024 (нормализованный налог): {adj_net_2024:.3f} млн")
print(f"bridge налоговый 2024: {bridge_2024_tax:.3f} млн")

# EBITDA adjusted: нет операционных разовых → ebitda_adj = ebitda_rep
ebitda_adj = {2023: ebitda_rep[2023], 2024: ebitda_rep[2024]}

# ── FCF ────────────────────────────────────────────────────────────────────────
fcf_reported = {y: cfo[y] - capex[y] for y in [2023, 2024]}

# Capex/revenue: 2023=7602.88/53709.835=14.2%, 2024=7494.012/62720.138=11.9%
# Только 2 года — нет 5-летней истории. Используем среднее этих двух.
capex_to_rev = {y: capex[y]/revenue[y] for y in [2023, 2024]}
capex_rev_avg = statistics.mean(capex_to_rev.values())
print(f"\nCapex/Rev: {capex_to_rev}  среднее: {capex_rev_avg:.1%}")

# Оборотный капитал: только 2 года, ΔWC не оцениваем по тренду (нет базы).
# CFO 2023=10988 (~20.5% выручки), CFO 2024=14871 (~23.7%) — стабильный.
# Нет аномалии 1.5× → WC не нормализуем.
wc_adj = {2023: 0, 2024: 0}

# FCF_normalized = cfo - capex (нет аномалий)
fcf_norm = {y: fcf_reported[y] for y in [2023, 2024]}
print(f"\nFCF reported: {fcf_reported}")
print(f"FCF normalized: {fcf_norm}")

# ── NET DEBT ───────────────────────────────────────────────────────────────────
net_debt = {y: (lt_debt[y] + st_debt[y]) - cash[y] for y in [2023, 2024]}
print(f"\nNet debt: {net_debt}")

# ── МУЛЬТИПЛИКАТОРЫ ────────────────────────────────────────────────────────────
# EV = market_cap + net_debt
ev = {y: market_cap_mln + net_debt[y] for y in [2023, 2024]}

pe_rep  = {2023: None,  2024: market_cap_mln / net_profit[2024]}
pe_adj  = {2023: None,  2024: market_cap_mln / adj_net_2024}
pb      = {y: market_cap_mln / total_equity[y] for y in [2023, 2024]}
ps      = {y: market_cap_mln / revenue[y] for y in [2023, 2024]}
ev_ebitda = {y: ev[y] / ebitda_adj[y] for y in [2023, 2024]}

print(f"\nMarket cap млн: {market_cap_mln:.1f}")
print(f"EV: {ev}")
print(f"P/E rep 2024: {pe_rep[2024]:.2f}")
print(f"P/E adj 2024: {pe_adj[2024]:.2f}")
print(f"P/B: {pb}")
print(f"P/S: {ps}")
print(f"EV/EBITDA: {ev_ebitda}")

# ── RETURNS ────────────────────────────────────────────────────────────────────
roe_rep  = {y: net_profit[y] / total_equity[y] for y in [2023, 2024]}
roe_adj  = {2023: adj_net_2023 / total_equity[2023], 2024: adj_net_2024 / total_equity[2024]}
roa_rep  = {y: net_profit[y] / total_assets[y] for y in [2023, 2024]}
roic_2024 = (op_profit[2024] * (1-tax_norm)) / (total_equity[2024] + lt_debt[2024] + st_debt[2024])
ros_rep   = {y: net_profit[y] / revenue[y] for y in [2023, 2024]}
ros_adj   = {2023: adj_net_2023 / revenue[2023], 2024: adj_net_2024 / revenue[2024]}
ebitda_margin = {y: ebitda_adj[y] / revenue[y] for y in [2023, 2024]}
op_margin     = {y: op_profit[y] / revenue[y] for y in [2023, 2024]}
net_debt_ebitda = {y: net_debt[y] / ebitda_adj[y] for y in [2023, 2024]}

print(f"\nROE rep: {roe_rep}")
print(f"ROE adj: {roe_adj}")
print(f"ROIC 2024: {roic_2024:.3%}")
print(f"Net debt / EBITDA: {net_debt_ebitda}")

# ── TANGIBLE EQUITY ────────────────────────────────────────────────────────────
# Goodwill=0; intangibles небольшие (1073/1111), но НМА сетевой компании — в основном
# лицензии/ПО, не переоценки → исключаем формально, но отмечаем незначительность.
tang_eq = {y: total_equity[y] - intangibles[y] - goodwill[y] for y in [2023, 2024]}
print(f"\nTangible equity: {tang_eq}")
bvps = {y: total_equity[y] / shares * 1e6 for y in [2023, 2024]}
tang_bvps = {y: tang_eq[y] / shares * 1e6 for y in [2023, 2024]}
print(f"BVPS: {bvps}")
print(f"Tangible BVPS: {tang_bvps}")

# ── ОЦЕНКА: СТАВКА ДИСКОНТИРОВАНИЯ ────────────────────────────────────────────
# Бета для сетевых монополий РФ: ~0.5-0.7 (низкая волатильность, гос-компания).
# Используем β=0.65 (суждение: ниже рынка, но не минимум — регуляторный риск)
beta = 0.65
Ke = Rf + beta * ERP
print(f"\nKe = {Rf:.3f} + {beta} × {ERP:.3f} = {Ke:.3%}")

# WACC: долг значительный → считаем WACC
# Стоимость долга: финансовые расходы / долг
kd_2024 = fin_costs[2024] / ((lt_debt[2024] + st_debt[2024]))
kd_after_tax = kd_2024 * (1 - tax_norm)
equity_val = market_cap_mln
debt_val   = lt_debt[2024] + st_debt[2024]
V = equity_val + debt_val
we = equity_val / V
wd = debt_val / V
WACC = we * Ke + wd * kd_after_tax
print(f"Kd 2024: {kd_2024:.3%}, after-tax: {kd_after_tax:.3%}")
print(f"E/V={we:.2%}, D/V={wd:.2%}")
print(f"WACC = {WACC:.3%}")

# ── DCF (Гордон от FCF₁) ──────────────────────────────────────────────────────
# FCF₁ = FCF_normalized 2024, скорректированный на умеренный рост (тарифная индексация)
# Прогноз: механический. Рост выручки 2023→2024 = (62720-53709)/53709 = 16.8%.
# Тарифная компания: тариф индексируется на инфляцию (~8-10% в 2024, снижение к 2025).
# Консервативно: FCF₁ ~ FCF_norm_2024 × 1.05 (только реальный рост тарифа)
rev_growth_2023_2024 = (revenue[2024] - revenue[2023]) / revenue[2023]
print(f"\nРост выручки 2023→2024: {rev_growth_2023_2024:.1%}")

FCF_norm_2024 = fcf_norm[2024]
g_fcf1 = 0.05   # умеренный рост FCF₁ от базы 2024 (механический)
FCF1 = FCF_norm_2024 * (1 + g_fcf1)
g_terminal_used = 0.03   # ≤ 3.5% default; ≤ номинал. роста экономики

r_dcf = WACC

EV_dcf = FCF1 / (r_dcf - g_terminal_used)
equity_dcf = EV_dcf - net_debt[2024]
price_dcf = equity_dcf / shares * 1e6

implied_exit = EV_dcf / ebitda_adj[2024]

print(f"\nDCF: FCF1={FCF1:.1f} млн, r={r_dcf:.3%}, g={g_terminal_used:.1%}")
print(f"EV_dcf={EV_dcf:.1f} млн, net_debt={net_debt[2024]:.1f}, equity_dcf={equity_dcf:.1f} млн")
print(f"Цена DCF: {price_dcf:.4f} ₽")
print(f"Implied EV/EBITDA exit: {implied_exit:.1f}x  (рынок: {ev_ebitda[2024]:.1f}x)")

# Sensitivity r × g
r_grid = [WACC - 0.02, WACC, WACC + 0.02]
g_grid = [0.02, 0.03, 0.035]
matrix = []
for r_s in r_grid:
    row = []
    for g_s in g_grid:
        if r_s > g_s:
            ev_s = FCF1 / (r_s - g_s)
            eq_s = ev_s - net_debt[2024]
            p_s  = eq_s / shares * 1e6
            row.append(round(p_s, 4))
        else:
            row.append(None)
    matrix.append(row)
print("\nSensitivity DCF (цена ₽):")
for i, r_s in enumerate(r_grid):
    print(f"  r={r_s:.2%}: {matrix[i]}")

# ── ИСТОРИЧЕСКИЙ P/E ──────────────────────────────────────────────────────────
# Только 1 год adj прибыли (2024, 2023 убыток). P/E исторический не считаем — нет выборки.
# Forward P/E: нет консенсуса → механический прогноз EPS
# Прогноз adj прибыли 2025: рост выручки ~10-12% (тариф), маржа стабильна
# Механически: adj_net_2025 = adj_net_2024 * 1.1
adj_net_2025_mech = adj_net_2024 * 1.10
eps_forward = adj_net_2025_mech / shares * 1e6
# P/E текущий adj = market_cap / adj_net_2024
pe_adj_current = market_cap_mln / adj_net_2024

# Для исторического P/E: P/E adj 2024 = единственная точка
# CV неприменим (1 точка) → метод не даёт надёжного исторического среднего
# → historical_pe: only 1 прибыльный год → status="insufficient_data"
print(f"\nP/E adj 2024: {pe_adj_current:.2f}x")
print(f"EPS adj forward 2025 (механически): {eps_forward:.6f} ₽")
# Forward цена через P/E: нет исторического среднего → используем P/E=pe_adj_current
# Но это не даёт нового числа (self-referential). Метод = insufficient_data.

# ── ИСТОРИЧЕСКИЙ P/B ──────────────────────────────────────────────────────────
# 2 точки: 2023 и 2024
pb_vals = [pb[2023], pb[2024]]
pb_mean = statistics.mean(pb_vals)
cv_pb   = statistics.stdev(pb_vals) / pb_mean if len(pb_vals) > 1 else 0
# CV < 0.5 → среднее
pb_used = pb_mean
bvps_2024 = bvps[2024]
price_hist_pb = pb_used * bvps_2024
print(f"\nP/B 2023={pb[2023]:.3f}, 2024={pb[2024]:.3f}")
print(f"P/B mean={pb_mean:.3f}, CV={cv_pb:.3f}")
print(f"Цена по историч. P/B: {price_hist_pb:.4f} ₽")

# ── ОТНОСИТЕЛЬНАЯ (peers) ──────────────────────────────────────────────────────
# Сектор: сетевые компании РФ. Peers: MRKV, MRKU, MRKY и другие МРСК.
# Нет файла peers.json → используем ориентиры из открытых источников (суждение).
# Типичный EV/EBITDA сетевых МРСК: 2-4x (регуляторные риски, гос-контроль).
# Медиана сектора EV/EBITDA ~ 2.5x (суждение, нет данных peers.json).
sector_ev_ebitda_median = 2.5   # judgement
ebitda_adj_2024 = ebitda_adj[2024]
ev_peers = sector_ev_ebitda_median * ebitda_adj_2024
equity_peers = ev_peers - net_debt[2024]
price_peers  = equity_peers / shares * 1e6
print(f"\nОтносительная: EV/EBITDA median={sector_ev_ebitda_median}x × EBITDA {ebitda_adj_2024:.1f}")
print(f"EV_peers={ev_peers:.1f}, equity={equity_peers:.1f}, цена={price_peers:.4f} ₽")

# ── ДИВИДЕНДНАЯ ───────────────────────────────────────────────────────────────
# DPS 2024 (из rates.csv) = 0.0012724 ₽
# Дивдоходность требуемая = Ke (или выше для нерегулярного плательщика)
# Payout: DPS/EPS_adj = 0.0012724 / eps_adj
eps_adj_2024 = adj_net_2024 / shares * 1e6
payout_adj = dps_2024 / eps_adj_2024
print(f"\nDPS 2024: {dps_2024} ₽")
print(f"EPS adj 2024: {eps_adj_2024:.6f} ₽")
print(f"Payout (adj): {payout_adj:.1%}")

# Дивидендная модель: нерегулярный плательщик → модель ненадёжна.
# Горизонт: требуемая дивдоходность ~ Ke + premium 2% (нерегулярность)
req_div_yield = Ke + 0.02
price_div = dps_2024 / req_div_yield
print(f"Требуемая дивдоходность: {req_div_yield:.2%}")
print(f"Цена дивидендная: {price_div:.4f} ₽")

# ── CAPM (12 мес.) ────────────────────────────────────────────────────────────
div_yield_current = dps_2024 / price
expected_return = Ke
# Целевая цена = текущая × (1 + (Ke - div_yield))
price_capm = price * (1 + (Ke - div_yield_current))
print(f"\nCAPM: Ke={Ke:.3%}, div_yield={div_yield_current:.3%}")
print(f"Цена CAPM: {price_capm:.4f} ₽")

# ── ИТОГОВЫЙ КОРИДОР ──────────────────────────────────────────────────────────
all_prices = {
    "DCF": price_dcf,
    "hist_pb": price_hist_pb,
    "peers_ev_ebitda": price_peers,
    "dividend": price_div,
    "CAPM": price_capm,
}
print("\nМетоды → цена:")
for k, v in all_prices.items():
    print(f"  {k}: {v:.4f} ₽")

valid_prices = [v for v in all_prices.values() if v is not None and v > 0]
conservative = round(min(valid_prices), 4)
optimistic   = round(max(valid_prices), 4)
base         = round(statistics.median(valid_prices), 4)

# Проверка расхождения
ratio = optimistic / conservative
print(f"\nКоридор: {conservative} — {base} — {optimistic} ₽")
print(f"Расхождение max/min: {ratio:.2f}x")

# ── ФИНАЛЬНЫЙ ВЫВОД ───────────────────────────────────────────────────────────
result = {
    "market_cap_mln": round(market_cap_mln, 1),
    "net_debt_2024": round(net_debt[2024], 3),
    "ev_2024": round(ev[2024], 1),
    "etr_2024": round(etr_2024, 4),
    "adj_net_2024": round(adj_net_2024, 3),
    "bridge_tax_2024": round(bridge_2024_tax, 3),
    "Ke": round(Ke, 5),
    "WACC": round(WACC, 5),
    "beta": beta,
    "kd_2024": round(kd_2024, 5),
    "pe_adj_2024": round(pe_adj_current, 2),
    "pb_2023": round(pb[2023], 4),
    "pb_2024": round(pb[2024], 4),
    "pb_mean": round(pb_mean, 4),
    "cv_pb": round(cv_pb, 4),
    "bvps_2024": round(bvps[2024], 8),
    "tang_bvps_2024": round(tang_bvps[2024], 8),
    "eps_adj_2024": round(eps_adj_2024, 8),
    "eps_adj_forward_2025": round(eps_forward, 8),
    "payout_adj": round(payout_adj, 4),
    "FCF1": round(FCF1, 3),
    "price_dcf": round(price_dcf, 4),
    "implied_exit_multiple": round(implied_exit, 2),
    "price_hist_pb": round(price_hist_pb, 4),
    "price_peers": round(price_peers, 4),
    "price_div": round(price_div, 4),
    "price_capm": round(price_capm, 4),
    "fair_conservative": conservative,
    "fair_base": base,
    "fair_optimistic": optimistic,
    "r_grid": [round(r, 5) for r in r_grid],
    "g_grid": g_grid,
    "matrix": matrix,
    "capex_rev_avg": round(capex_rev_avg, 4),
    "fcf_norm_2024": round(fcf_norm[2024], 3),
    "roe_adj_2024": round(roe_adj[2024], 5),
    "roic_2024": round(roic_2024, 5),
    "ebitda_margin_2024": round(ebitda_margin[2024], 5),
    "net_debt_ebitda_2024": round(net_debt_ebitda[2024], 3),
    "rev_growth_2023_2024": round(rev_growth_2023_2024, 4),
}
print("\nRESULT JSON:")
print(json.dumps(result, ensure_ascii=False, indent=2))
