"""
LNZL financials.json calculation script
Shell/liquidation company — NAV-based valuation only
"""
import json, math, statistics

# ── РЫНОЧНЫЙ КОНТЕКСТ (из rates.csv) ──────────────────────────────────────────
price = 1387.73       # ₽ (для промежуточных проверок, в JSON не сохраняем)
shares_total = 1_140_300   # обыкновенных
shares_pref  =   348_000   # привилегированных (из governance.json)
shares_all   = shares_total + shares_pref  # 1 488 300 — полный уставной капитал
cap_ord      = price * shares_total / 1e6  # капитализация по обыкн., млн ₽

# ── КЛЮЧЕВЫЕ ДАННЫЕ (extracted_financials.json + governance.json) ────────────
fiscal_years = [2020, 2021, 2022, 2023, 2024]

# P&L
revenue      = [68, 90, 320, 150, 294]   # = финансовые доходы, не выручка
net_profit   = [7568, 12, 660, 108, 48]

# Баланс (известные данные)
total_assets  = [23400, 5040, 1690, 1770, 527]
total_equity  = [23275, None, None, None, 318]
total_liab    = [107, None, None, None, 209]
cash          = [23018, None, None, None, 514]

# Долг = 0 (нет долга у оболочки)
long_term_debt  = [0,0,0,0,0]
short_term_debt = [0,0,0,0,0]
net_debt        = [0 - c if c is not None else None for c in cash]
# Отрицательный net_debt = кэш > долга

# ОДДС
cfo  = [None, None, None, None, 77]
capex= [0,0,0,0,0]
fcf  = [None if c is None else c - k for c,k in zip(cfo, capex)]

# ── НОРМАЛИЗАЦИЯ ПРИБЫЛИ (мост reported → adjusted) ──────────────────────────
# 2020: ЧП 7568 млн — разовое от продажи актива ЗДК «Лензолото» Полюсу.
#        Нельзя использовать как операционную базу. Корректировка: исключить.
# 2021: ЧП 12 млн — типичный год оболочки (процентный доход), нет аномалий.
# 2022: ЧП 660 млн >> Revenue 320 млн → вероятно переоценка/продажа инвестиций.
#        Разовый доход. Корректируем к операционной базе (Revenue ≈ ЧП без разовых).
#        Нет подробных данных → сохраняем reported, флаг "unverified_one_off_2022".
# 2023: ЧП 108 млн, Revenue 150 млн → разумная операционная база, аномалий нет.
# 2024: ЧП 48 млн, Revenue 294 млн → аномально мало ЧП при росте финдоходов;
#        вероятно расходы на ликвидацию (advisors, обязательства 209 млн).
#        Нет детальных данных → reported = adjusted, пометка.

# Adjusted = reported (нет данных для точных корректировок по 2022, 2024)
net_profit_adj = list(net_profit)
ebitda_adj     = [None]*5   # нет операционного EBITDA (оболочка)
fcf_normalized = list(fcf)  # нет смысла нормализовать у оболочки без capex

bridge = [
    {
        "year": 2020,
        "item": "Разовый доход от продажи ЗДК «Лензолото» Полюсу (формирует 99% ЧП)",
        "amount": -7500,
        "added_back": False,
        "certainty": "fact",
        "source_ref": "src_5"
    },
    {
        "year": 2022,
        "item": "Переоценка/реализация финансовых активов (ЧП 660 > Revenue 320 — аномалия); корректировка не применена — данных для точного нетто нет, флаг выставлен",
        "amount": 0,
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    },
    {
        "year": 2021,
        "item": "Проверено: аномальных разовых не обнаружено (ЧП = операционный остаток оболочки)",
        "amount": 0,
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    },
    {
        "year": 2023,
        "item": "Проверено: аномальных разовых не обнаружено",
        "amount": 0,
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_1"
    },
    {
        "year": 2024,
        "item": "Расходы на ликвидацию (обязательства 209 млн, рост с 107) снизили ЧП; не нормализуем — часть реального перехода в ликвидацию",
        "amount": 0,
        "added_back": False,
        "certainty": "judgement",
        "source_ref": "src_3"
    }
]

# ── МАРЖИ ────────────────────────────────────────────────────────────────────
# ROS = ЧП / Revenue (Revenue здесь = финдоходы, не выручка)
ros_reported = [round(np/r*100,1) if r else None for np,r in zip(net_profit, revenue)]
# 2020 аномально (7568/68=11129%), нормальный диапазон 2021-2024 после

# ── МУЛЬТИПЛИКАТОРЫ ──────────────────────────────────────────────────────────
# EV = market_cap - cash (net_debt отрицательный = кубышка)
# Используем equity с обыкновенными (market_cap по обыкновенным)
# cap_ord = 1387.73 * 1_140_300 / 1e6

ev_values = []
pe_adj_values = []
pb_values = []

for i, yr in enumerate(fiscal_years):
    te = total_equity[i]
    np_ = net_profit_adj[i]
    c = cash[i]
    # EV = cap_ord - (cash - debt) = cap_ord - cash (нет долга)
    # Но cap_ord = текущая рыночная кап — используем только для мультов "на дату анализа"
    # Для исторических P/E нет исторических цен — null
    ev_values.append(None)   # нет исторических цен для EV
    pe_adj_values.append(None)
    # P/B по 2020 и 2024
    if te is not None:
        bvps = te / shares_total  # балансовая стоимость на 1 обыкн. акцию, ₽
        pb_values.append(round(price / bvps, 2))
    else:
        pb_values.append(None)

# Текущие мультипликаторы (price = 1387.73, shares_ord = 1_140_300)
cap_mln = price * shares_total / 1e6   # ~1582.6 млн
cash_2024 = 514   # млн
equity_2024 = 318 # млн (total_equity 2024)

# EV с кубышкой: EV = cap - (cash - 0) = 1582.6 - 514 = 1068.6 млн
ev_current = cap_mln - cash_2024
bvps_2024 = equity_2024 / shares_total   # ₽ на акцию
pb_current = round(price / bvps_2024, 2)

# P/E на adjusted ЧП 2024 (48 млн, operating)
eps_2024 = net_profit_adj[4] / shares_total * 1e6  # ₽ на акцию
pe_adj_current = round(price / eps_2024, 1) if eps_2024 > 0 else None

print(f"=== РЫНОЧНЫЙ КОНТЕКСТ ===")
print(f"Цена: {price} ₽ | Акций обыкновенных: {shares_total:,} | Кап (обыкн.): {cap_mln:.1f} млн ₽")
print(f"Кэш 2024: {cash_2024} млн | EV (с кубышкой): {ev_current:.1f} млн ₽")
print(f"BVPS (equity 2024 / shares_ord): {bvps_2024:.2f} ₽ | P/B: {pb_current}")
print(f"EPS adj 2024: {eps_2024:.2f} ₽ | P/E adj: {pe_adj_current}")

# ── ЛИКВИДАЦИОННАЯ СТОИМОСТЬ (NAV) — ОСНОВНОЙ МЕТОД ─────────────────────────
# Источник: extracted_financials.json (meta.liquidation_status)
# Данные:
#   - Чистые активы конец 2024: equity = 318 млн, cash = 514 млн
#   - февраль 2026 (после дивидендов 2025): cash = 168.3 млн

# Акции: обыкновенные 1 140 300 + привилегированные 348 000 = 1 488 300 (полный уставный)
# Привилегированные имеют ПРИОРИТЕТ при ликвидации (governance.json)
# Сценарии:
# (A) Консервативный: cash_feb2026 = 168.3 млн
#     - расходы ликвидации (advisor fees, налоги, доп. обязательства) ~20 млн (оценка)
#     - остаток = 148.3 млн
#     - на LNZLP (приоритет): ликвидационная стоимость = ном + накопл.дивиденды (неизвестно)
#       оценка: доля prefs в ликвидации ≈ 348000/(1488300) × остаток = 34.7 млн
#     - на LNZL остаток = 148.3 - 34.7 = 113.6 млн
#     - NAV/акцию (LNZL) = 113.6 млн / 1_140_300 = 99.6 ₽
# (B) Базовый: cash_feb2026 = 168.3 млн, расходы 10 млн
#     - остаток = 158.3 млн
#     - pref_share = 158.3 × (348000/1488300) = 37.0 млн
#     - ord_nav = 121.3 млн / 1_140_300 = 106.4 ₽
# (C) Оптимистичный: допускаем, что расходы минимальны (5 млн) и часть кэша
#     возможно чуть выше (подвижки в дебиторке/активах)
#     - остаток = 163.3 млн, pref_share = 38.1 млн
#     - ord_nav = 125.2 млн / 1_140_300 = 109.8 ₽

cash_feb26 = 168.3  # млн, факт (liquidation_status)
shares_ord = 1_140_300
shares_pref_n = 348_000
shares_all_n = shares_ord + shares_pref_n

def nav_calc(cash_avail, liquidation_costs, label):
    net = cash_avail - liquidation_costs
    if net <= 0:
        return 0
    pref_share = net * (shares_pref_n / shares_all_n)
    ord_pool = net - pref_share
    nav_per_share = ord_pool / shares_ord * 1e6  # ₽ (млн / шт → ₽ через ×1e6 компенсирует млн)
    # проверка: ord_pool в млн, shares_ord в штуках → nav = ord_pool_mln × 1_000_000 / shares_ord
    nav_rub = (ord_pool * 1_000_000) / shares_ord
    print(f"  [{label}] cash={cash_avail}, costs={liquidation_costs}, net={net:.1f} млн")
    print(f"    pref_pool={pref_share:.1f} млн | ord_pool={ord_pool:.1f} млн")
    print(f"    NAV/LNZL = {nav_rub:.1f} ₽")
    return round(nav_rub, 0)

print("\n=== NAV (ЛИКВИДАЦИОННАЯ СТОИМОСТЬ) ===")
nav_conservative = nav_calc(cash_feb26, 20, "Консервативный")
nav_base         = nav_calc(cash_feb26, 10, "Базовый")
nav_optimistic   = nav_calc(cash_feb26,  5, "Оптимистичный")

print(f"\nКоридор NAV (LNZL): {nav_conservative} — {nav_base} — {nav_optimistic} ₽")
print(f"Рыночная цена: {price} ₽")
print(f"Премия к NAV base: {(price/nav_base - 1)*100:.0f}%  ← КРИТИЧЕСКИЙ РИСК")

# ── SENSITIVITY: расходы на ликвидацию × доля префов ─────────────────────────
print("\n=== SENSITIVITY: расходы ликвидации ×  доля преф-пула ===")
cost_grid  = [5, 10, 15, 20, 30]
pref_share_grid = [0.20, 0.2338, 0.30]  # 0.2338 = пропорциональная
matrix = []
for cost in cost_grid:
    row = []
    for pf in pref_share_grid:
        net = cash_feb26 - cost
        ord_pool = net * (1 - pf)
        nav_rub = (ord_pool * 1_000_000) / shares_ord if net > 0 else 0
        row.append(round(nav_rub, 0))
    matrix.append(row)
    print(f"  costs={cost:2d} млн | prefsplit={[f'{p:.0%}' for p in pref_share_grid]}: {row}")

# ── CAPM (12 мес.) — для справки ─────────────────────────────────────────────
# Ликвидационная компания: Beta ≈ не применима (нет рыночного риска в обычном смысле)
# Оставляем not_applicable

# ── ПРОВЕРКИ ──────────────────────────────────────────────────────────────────
print("\n=== АРИФМЕТИЧЕСКИЕ ПРОВЕРКИ ===")
# 2024
assets_24 = 527
eq_24 = 318
liab_24 = 209
print(f"2024: assets={assets_24} = equity+liab = {eq_24+liab_24} | diff={assets_24-(eq_24+liab_24)}")
# 2020
assets_20 = 23400; eq_20=23275; liab_20=107
print(f"2020: assets={assets_20} = equity+liab = {eq_20+liab_20} | diff={assets_20-(eq_20+liab_20)}")
# net_debt 2024
print(f"net_debt 2024 = debt(0) - cash(514) = {0-514} млн (кубышка)")
# EV 2024
print(f"EV 2024 = cap({cap_mln:.1f}) + net_debt({0-514}) = {cap_mln + (0-514):.1f} млн")

# ── СБОРКА РЕЗУЛЬТАТОВ ──────────────────────────────────────────────────────
result = {
    "price": price,
    "shares_ord": shares_ord,
    "cap_mln": round(cap_mln, 1),
    "cash_feb26": cash_feb26,
    "nav_conservative": nav_conservative,
    "nav_base": nav_base,
    "nav_optimistic": nav_optimistic,
    "ev_current": round(ev_current, 1),
    "bvps_2024": round(bvps_2024, 2),
    "pb_current": pb_current,
    "eps_adj_2024": round(eps_2024, 2),
    "pe_adj_current": pe_adj_current,
    "sensitivity_costs": cost_grid,
    "sensitivity_prefsplit": pref_share_grid,
    "sensitivity_matrix": matrix,
}

with open("/Users/soinnikita/investment-platform/backend/companies/LNZL/calc_output.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("\n=== РАСЧЁТ ЗАВЕРШЁН ===")
print(json.dumps(result, ensure_ascii=False, indent=2))
