"""
BFV-D — эталонная реализация дивидендного движка (методика BFV v1.0, §18 «минимальное ядро»).

Назначение: проверяемый образец расчёта для портирования в продакшен.
Это НЕ продакшен-код: нет хранилища, API и логирования. Один файл, чистые функции.

Структура повторяет разделы методики:
  Params/Scenario   — входы
  project_flows     — §5-§8: капитал, права, события, акции
  bank_capacity     — §9: банковский мост достаточности
  expected_flows    — §3: агрегация по состояниям (по потокам, НЕ по ставкам)
  solve_rate        — §12: ожидаемая доходность
  hurdle/value_at   — §11, §13: порог и справедливая цена
  checks_*          — §14: обязательные проверки
  tests             — §17, §19: золотой, свойственные и негативные тесты
"""

from dataclasses import dataclass, replace
from typing import List, Tuple, Optional
import math


# ============================================================
# ВХОДЫ
# ============================================================

@dataclass(frozen=True)
class Params:
    """Параметры компании. В продакшене каждое поле — запись с распределением (§20)."""
    # --- фундаментальный блок (§5) ---
    bv0: float = 100.0          # балансовая стоимость на акцию
    roe0: float = 0.30          # стартовый ROE
    roe_terminal: float = 0.22  # терминальный ROE (суждение аналитика)
    phi: float = 0.87           # коэф. затухания спреда, φ = 0.5**(1/полураспад)
    payout0: float = 0.30       # стартовый payout
    payout_ramp: int = 12       # лет до терминального payout
    g_terminal: float = 0.035   # терминальный рост (по географии выручки)
    T_forecast: int = 15        # прогнозное окно
    T_explicit: int = 50        # горизонт явного счёта

    # --- классы удержанного (§5.4) ---
    productive_share: float = 0.60  # доля benign-удержанного в продуктивные инвестиции
    r_cash: float = 0.12            # доходность кэш-корзины

    # --- права на распределение (§6) ---
    p_ability: float = 1.0
    p_permission: float = 1.0
    p_willingness: float = 0.94     # ЕДИНСТВЕННЫЙ канал скоринга управления
    payment_fraction: float = 0.95
    s_benign: float = 0.50          # доля willingness-недовыплаты, остающаяся в компании

    # --- события (§7) ---
    h_distress: float = 0.002       # интенсивности, НЕ вероятности
    h_expropriation: float = 0.003
    theta: float = 0.50             # доля выплаты в год события
    alpha_recovery: float = 0.50    # возврат при экспроприации = α × BVPS
    recovery_distress: float = 0.0  # для банков акционеру обычно 0

    # --- акции (§8) ---
    dilution_events: Tuple = ()     # ((год, ΔN/N, κ), ...)

    # --- банковский режим (§9) ---
    is_bank: bool = False
    cet1_ratio0: float = 0.13       # текущая достаточность
    cet1_target: float = 0.11       # целевая с надбавками
    rwa_growth: float = 0.10        # рост активов под риском


@dataclass(frozen=True)
class Scenario:
    name: str
    prob: float
    overrides: dict          # что меняется по состоянию (§10.2) — ТОЛЬКО входы потоков
    catastrophic: bool = False
    cat_recovery: float = 0.0


# ============================================================
# §9 — БАНКОВСКИЙ МОСТ ДОСТАТОЧНОСТИ
# ============================================================

def bank_capacity(cet1_pre: float, rwa: float, target_ratio: float) -> float:
    """Распределимо только превышение над требуемым капиталом.
    Прибыль входит в мост ОДИН раз — она уже внутри cet1_pre."""
    return max(0.0, cet1_pre - target_ratio * rwa)


# ============================================================
# §5-§8 — ОСНОВНОЙ ПРОГОН ПО ОДНОМУ СОСТОЯНИЮ
# ============================================================

def project_flows(p: Params) -> Tuple[List[float], List[float], List[float]]:
    """Возвращает (поток на акцию, BVPS по годам, прибыль на акцию по годам).

    Порядок внутри года: прибыль → ёмкость → цель → фильтры прав →
    разделение недовыплаты → классы удержанного → события.
    """
    payout_terminal = 1.0 - p.g_terminal / p.roe_terminal   # тождество §5, проверка на выходе

    bv_core, bv_cash = p.bv0, 0.0
    roe = p.roe0
    survival = 1.0
    shares = 1.0
    # §9: CET1 приблизительно равен капиталу; RWA выводится из заявленной достаточности.
    # Ошибка «CET1 = ratio × капитал» занижает капитал в 1/ratio раз (~7.7×) и обнуляет
    # ёмкость распределения — банк выглядит неспособным платить. Проверяется test_bank_golden.
    cet1 = p.bv0 if p.is_bank else 0.0
    rwa = cet1 / p.cet1_ratio0 if p.is_bank else 0.0

    flows, bvps_path, eps_path = [], [], []

    for t in range(1, p.T_explicit + 1):
        # --- траектории (§5.2, §5.3) ---
        # Затухание спреда продолжается ВСЕГДА: замораживание ROE на границе прогнозного
        # окна оставляло его выше терминального и ломало тождество роста.
        roe = p.roe_terminal + (roe - p.roe_terminal) * p.phi
        if t <= p.T_forecast:
            payout = p.payout0 + (payout_terminal - p.payout0) * min(t, p.payout_ramp) / p.payout_ramp
        else:
            # В терминальной фазе payout держит тождество ежегодно: b = g/ROE_t → рост = g точно.
            payout = 1.0 - p.g_terminal / roe

        earnings_core = roe * bv_core
        cash_yield = p.r_cash * bv_cash
        earnings_total = earnings_core + cash_yield

        # --- ёмкость распределения (§6.1 / §9) ---
        if p.is_bank:
            cet1 += earnings_core
            rwa *= (1.0 + p.rwa_growth)
            capacity = bank_capacity(cet1, rwa, p.cet1_target)
        else:
            capacity = earnings_core

        target = min(capacity, payout * earnings_core)

        # --- фильтры прав (§6.1) ---
        transmit = p.p_ability * p.p_permission * p.p_willingness * p.payment_fraction
        paid_core = target * transmit
        paid_cash = cash_yield * p.p_willingness * p.payment_fraction
        dist = paid_core + paid_cash

        if p.is_bank:
            cet1 -= paid_core

        # --- разделение недовыплаты (§6.3) ---
        short_will = target * (1.0 - p.p_willingness)
        short_frac = target * p.p_willingness * (1.0 - p.payment_fraction)
        leakage = short_will * (1.0 - p.s_benign) + short_frac * 0.5
        benign = short_will * p.s_benign + short_frac * 0.5
        to_cash = benign * (1.0 - p.productive_share)   # productive остаётся в ядре и работает под ROE

        # --- капитал (§8) ---
        bv_core += earnings_core - paid_core - leakage - to_cash
        bv_cash += to_cash + (cash_yield - paid_cash)

        # --- эмиссии/выкупы (§8) ---
        for (yr, dn, kappa) in p.dilution_events:
            if yr == t:
                proceeds_ps = kappa * (bv_core + bv_cash) * dn
                bv_core += proceeds_ps * shares
                shares *= (1.0 + dn)

        book_ps = (bv_core + bv_cash) / shares

        # --- события (§7.1-§7.3) ---
        h_total = p.h_distress + p.h_expropriation
        q_total = 1.0 - math.exp(-h_total)
        if h_total > 0:
            q_d = p.h_distress / h_total * q_total
            q_e = p.h_expropriation / h_total * q_total
        else:
            q_d = q_e = 0.0
        recovery = q_d * p.recovery_distress + q_e * (p.alpha_recovery * book_ps)

        dist_ps = dist / shares
        cf = survival * ((1.0 - q_total) * dist_ps + q_total * p.theta * dist_ps + recovery)

        flows.append(cf)
        bvps_path.append(book_ps)
        eps_path.append(earnings_total / shares)
        survival *= (1.0 - q_total)

    return flows, bvps_path, eps_path


# ============================================================
# §3 — АГРЕГАЦИЯ ПО СОСТОЯНИЯМ
# ============================================================

def expected_flows(base: Params, scenarios: List[Scenario]) -> Tuple[List[float], List[float]]:
    """Вероятностно-взвешенный поток. Сначала потоки, ПОТОМ одна ставка (§3)."""
    total_p = sum(s.prob for s in scenarios)
    if abs(total_p - 1.0) > 1e-9:
        raise ValueError(f"Вероятности состояний не суммируются в 1: {total_p:.6f}")

    T = base.T_explicit
    exp_cf = [0.0] * T
    exp_bv = [0.0] * T

    for s in scenarios:
        if s.catastrophic:
            exp_cf[0] += s.prob * s.cat_recovery
            continue
        cf, bv, _ = project_flows(replace(base, **s.overrides))
        for t in range(T):
            exp_cf[t] += s.prob * cf[t]
            exp_bv[t] += s.prob * bv[t]
    return exp_cf, exp_bv


def average_rates_forbidden(*args, **kwargs):
    """§3: усреднение сценарных ставок запрещено. Метод ломается на катастрофическом
    хвосте (ставка там не существует) и даёт ложное приближение там, где не нужен."""
    raise NotImplementedError(
        "Запрещено усреднять ставки по состояниям. Агрегируйте потоки (expected_flows), "
        "затем решайте уравнение один раз (solve_rate). См. §3 методики."
    )


# ============================================================
# §11-§13 — СТАВКА, ПОРОГ, ВЫХОДЫ
# ============================================================

def pv(flows: List[float], rate: float) -> float:
    return sum(cf / (1.0 + rate) ** (i + 1) for i, cf in enumerate(flows))


def solve_rate(flows: List[float], price: float, lo=0.005, hi=0.60) -> float:
    """Ожидаемая доходность. Единственность корня гарантирована структурой (§12):
    все потоки акционеру неотрицательны, отток один — покупка."""
    if any(cf < -1e-12 for cf in flows):
        raise ValueError("Отрицательный поток акционеру — единственность корня не гарантирована")
    if pv(flows, hi) > price:
        raise ValueError("Доходность выше верхней границы поиска — расширьте диапазон")
    if pv(flows, lo) < price:
        raise ValueError("Поток не окупает цену даже при минимальной ставке")
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if pv(flows, mid) > price:
            lo = mid
        else:
            hi = mid
    return lo


def hurdle(z_dur: float, beta: float, required_spread: float) -> float:
    """§11. Единственное суждение платформы — required_spread."""
    return z_dur + beta * required_spread


def duration(flows: List[float], rate: float) -> float:
    p0 = pv(flows, rate)
    return sum((i + 1) * cf / (1.0 + rate) ** (i + 1) for i, cf in enumerate(flows)) / p0


def holding_return(flows: List[float], bvps: List[float], price: float,
                   horizon: int, entry_multiple: float) -> float:
    """§12: доходность удержания — выход по мультипликатору входа,
    согласия рынка не требует."""
    cf = flows[:horizon][:]
    cf[horizon - 1] += entry_multiple * bvps[horizon - 1]
    return solve_rate(cf, price)


def moat_value(base: Params, scenarios: List[Scenario], h: float) -> float:
    """§13: V(прогнозный терминальный ROE) − V(терминальный ROE = порог)."""
    cf_fc, _ = expected_flows(base, scenarios)
    neutral = [replace(s, overrides={**s.overrides, "roe_terminal": h}) for s in scenarios]
    cf_nt, _ = expected_flows(replace(base, roe_terminal=h), neutral)
    return pv(cf_fc, h) - pv(cf_nt, h)


# ============================================================
# §14-§15 — ОБЯЗАТЕЛЬНЫЕ ПРОВЕРКИ
# ============================================================

def check_terminal_identity(p: Params) -> None:
    """payout_L = 1 − g_L/ROE_L должно выполняться на выходе."""
    pl = 1.0 - p.g_terminal / p.roe_terminal
    if not (0.0 <= pl <= 1.0):
        raise ValueError(f"Терминальный payout вне [0;1]: {pl:.3f} — g и ROE несогласованы")


def check_recovery_not_circular(alpha: float) -> None:
    """§7.3: возврат задаётся долей балансовой стоимости или цены, но не справедливой стоимости."""
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("Якорь возврата вне допустимого диапазона")


def check_hazard_mode(h_list: List[float], approx: bool) -> None:
    """§7.1: приближённое сложение допустимо только при малой сумме."""
    q_approx = sum(h_list)
    if approx and q_approx >= 0.05:
        raise ValueError(f"Сумма интенсивностей {q_approx:.3f} ≥ 5% — приближение запрещено, "
                         "используйте строгую формулу через exp")


def check_tv_share(flows: List[float], rate: float, t_forecast: int) -> Tuple[float, str]:
    """§15: доля терминальной фазы."""
    total = pv(flows, rate)
    tail = sum(cf / (1.0 + rate) ** (i + 1) for i, cf in enumerate(flows) if i >= t_forecast)
    share = tail / total
    if share > 0.90:
        status = "публикация только с отдельным пояснением"
    elif share > 0.85:
        status = "оценка крайне чувствительна"
    elif share > 0.75:
        status = "предупреждение"
    else:
        status = "норма"
    return share, status


def check_ri_equivalence(p: Params, rate: float) -> float:
    """§15: на бессобытийной траектории дивидендный и остаточно-доходный расчёты
    обязаны совпадать. Возвращает расхождение."""
    clean = replace(p, h_distress=0.0, h_expropriation=0.0,
                    p_willingness=1.0, payment_fraction=1.0, dilution_events=())
    flows, bvps, eps = project_flows(clean)
    v_ddm = pv(flows, rate)
    ri = clean.bv0
    bv_prev = clean.bv0
    for t in range(len(flows)):
        ri += (eps[t] - rate * bv_prev) / (1.0 + rate) ** (t + 1)
        bv_prev = bvps[t]
    # Телескопирование даёт МИНУС остаточную книгу на конце горизонта:
    #   V = BV0 + Σ RI_t/(1+k)^t − BV_T/(1+k)^T
    ri -= bvps[-1] / (1.0 + rate) ** len(flows)
    return abs(v_ddm - ri)


# ============================================================
# §17 — ЗОЛОТОЙ ТЕСТ
# ============================================================

def golden_case():
    base = Params()
    scenarios = [
        Scenario("деэскалация", 0.19, dict(roe_terminal=0.22, p_willingness=0.97,
                                           h_distress=0.001, h_expropriation=0.001)),
        Scenario("статус-кво", 0.52, dict(roe_terminal=0.22, p_willingness=0.94,
                                          h_distress=0.002, h_expropriation=0.003)),
        Scenario("эскалация", 0.24, dict(roe_terminal=0.18, p_willingness=0.88,
                                         payment_fraction=0.90, h_distress=0.004,
                                         h_expropriation=0.011, s_benign=0.40)),
        Scenario("катастрофический хвост", 0.05, {}, catastrophic=True, cat_recovery=5.0),
    ]
    price, z_dur, beta, req = 95.0, 0.144, 1.1, 0.08
    return base, scenarios, price, z_dur, beta, req


def run_golden():
    base, scen, price, z_dur, beta, req = golden_case()
    check_terminal_identity(base)
    check_recovery_not_circular(base.alpha_recovery)

    cf, bv = expected_flows(base, scen)
    r = solve_rate(cf, price)
    h = hurdle(z_dur, beta, req)
    dur = duration(cf, r)
    v_fair = pv(cf, h)
    r_hold = holding_return(cf, bv, price, 10, price / base.bv0)
    tv_share, tv_status = check_tv_share(cf, h, base.T_forecast)
    moat = moat_value(base, scen, h)

    return {
        "ожидаемая доходность, %": r * 100,
        "эффективная дюрация, лет": dur,
        "порог, %": h * 100,
        "спред к ОФЗ, п.п.": (r - z_dur) * 100,
        "вердикт": "проходит" if r >= h else "не проходит",
        "справедливая цена при пороге": v_fair,
        "див. доходность 1-го года, %": cf[0] / price * 100,
        "доходность удержания 10 лет, %": r_hold * 100,
        "компонента переоценки, п.п.": (r - r_hold) * 100,
        "доля терминальной фазы, %": tv_share * 100,
        "статус доли терминала": tv_status,
        "стоимость рва": moat,
    }


# ============================================================
# МАРШРУТИЗАТОР ДВИЖКОВ (§0.2 — восстановлен)
# ============================================================

def select_engine(bvps: Optional[float], roe: Optional[float], pb: Optional[float],
                  payout: Optional[float], is_bank: bool = False,
                  g_terminal: float = 0.035) -> str:
    """Выбор движка ДО расчёта. Применение BFV-D вне его области — источник
    систематической недооценки, а не свойство рынка.

    BFV-D пригоден, когда книга — якорь стоимости и платится ощутимый дивиденд:
    банки, страховщики, сети и утилиты, зрелые сырьевики и индустрия.
    """
    if is_bank:
        return "BFV-D"                      # книга и капитал — сама суть бизнеса
    if bvps is None or bvps <= 0:
        return "BFV-F"                      # §1: отрицательный капитал — якоря нет
    if roe is None:
        return "BFV-F"
    if roe <= g_terminal:
        return "BFV-F"                      # §2: устойчивый рост от книги невозможен
    if pb is not None and pb >= 3.0:
        return "BFV-F"                      # §3: книга не отражает экономику (asset-light)
    if roe >= 0.45:
        return "BFV-F"                      # доходность на книгу так велика, что книга не связывает
    return "BFV-D"


# ============================================================
# ДВИЖОК BFV-F — от денежного потока (для asset-light и растущих)
# ============================================================

@dataclass(frozen=True)
class ParamsF:
    """Движок от выручки и реинвестиций. Части I, III, IV методики общие с BFV-D:
    те же права, события, состояния, агрегация, порог, режим доходности.
    Отличается ТОЛЬКО построение потока (Часть II, §5)."""
    revenue0: float                 # выручка на акцию
    g_revenue0: float = 0.30        # стартовый рост выручки
    g_terminal: float = 0.035
    fade_years: int = 10            # лет до терминального роста
    margin0: float = 0.30           # маржа чистой прибыли
    margin_terminal: float = 0.25
    sales_to_capital: float = 6.0   # ₽ прироста выручки на ₽ нового капитала
                                    # (asset-light: 5-10; тяжёлая промышленность: 0.5-1.5)
    net_borrow_share: float = 0.0   # доля реинвестиций, финансируемая долгом
    T_explicit: int = 50

    # права и события — те же, что в BFV-D
    p_ability: float = 1.0
    p_permission: float = 1.0
    p_willingness: float = 0.94
    payment_fraction: float = 0.95
    h_distress: float = 0.002
    h_expropriation: float = 0.003
    theta: float = 0.50
    recovery_share_of_price: float = 0.0   # якорь возврата — доля цены до события,
                                           # т.к. книга у asset-light не якорь


def project_flows_fcfe(p: ParamsF, price_pre_event: float = 0.0) -> List[float]:
    """FCFE = чистая прибыль − реинвестиции + чистые заимствования.
    Рост здесь берётся из выручки, а не из компаундирования книги — поэтому
    компания со 100% payout может расти, что в BFV-D невозможно по построению."""
    rev = p.revenue0
    survival = 1.0
    flows = []
    for t in range(1, p.T_explicit + 1):
        # затухание роста выручки к терминальному
        k = min(t, p.fade_years) / p.fade_years
        g = p.g_revenue0 + (p.g_terminal - p.g_revenue0) * k
        margin = p.margin0 + (p.margin_terminal - p.margin0) * k

        rev_new = rev * (1.0 + g)
        earnings = rev_new * margin
        reinvest = (rev_new - rev) / p.sales_to_capital      # подход через капиталоотдачу
        net_borrow = reinvest * p.net_borrow_share
        fcfe = earnings - reinvest + net_borrow
        rev = rev_new

        # те же фильтры прав, что в BFV-D (§6)
        dist = max(0.0, fcfe) * p.p_ability * p.p_permission * p.p_willingness * p.payment_fraction

        # те же события (§7), но якорь возврата — доля цены, а не книги
        h_total = p.h_distress + p.h_expropriation
        q_total = 1.0 - math.exp(-h_total)
        recovery = q_total * p.recovery_share_of_price * price_pre_event

        flows.append(survival * ((1.0 - q_total) * dist + q_total * p.theta * dist + recovery))
        survival *= (1.0 - q_total)
    return flows


def demo_asset_light():
    """Демонстрация §3: одна и та же компания в двух движках.
    Профиль близок к asset-light рекрутинговой платформе."""
    price, bvps, roe, payout = 2790.0, 279.0, 1.11, 1.00
    engine = select_engine(bvps=bvps, roe=roe, pb=price / bvps, payout=payout)

    # BFV-D (как раскатывали): книга якорь, payout 100% -> роста нет
    d = Params(bv0=bvps, roe0=min(roe, 0.45), roe_terminal=0.20, payout0=payout,
               payout_ramp=1, p_willingness=0.97, payment_fraction=0.98,
               h_distress=0.001, h_expropriation=0.002)
    cf_d, _, _ = project_flows(d)
    v_d = pv(cf_d, 0.232)

    # BFV-F: рост от выручки, реинвестиции малы (высокая капиталоотдача)
    f = ParamsF(revenue0=560.0, g_revenue0=0.28, margin0=0.33, margin_terminal=0.22,
                sales_to_capital=7.0, p_willingness=0.97, payment_fraction=0.98,
                h_distress=0.001, h_expropriation=0.002)
    cf_f = project_flows_fcfe(f, price_pre_event=price)
    v_f = pv(cf_f, 0.232)
    r_f = solve_rate(cf_f, price)

    return {
        "маршрутизатор выбрал": engine,
        "BFV-D (вне области): цена": v_d,
        "BFV-D: отклонение от рынка, %": (v_d / price - 1) * 100,
        "BFV-F: цена": v_f,
        "BFV-F: отклонение от рынка, %": (v_f / price - 1) * 100,
        "BFV-F: ожидаемая доходность, %": r_f * 100,
    }


# ============================================================
# ТЕСТЫ (§19)
# ============================================================

def test_golden():
    got = run_golden()
    expect = {
        "ожидаемая доходность, %": 23.50,
        "эффективная дюрация, лет": 8.56,
        "порог, %": 23.20,
        "справедливая цена при пороге": 97.03,
        "див. доходность 1-го года, %": 9.18,
        "доходность удержания 10 лет, %": 24.70,
        "компонента переоценки, п.п.": -1.19,
        "доля терминальной фазы, %": 13.07,
        "стоимость рва": -7.86,
    }
    for k, v in expect.items():
        tol = 0.05 if "%" in k or "п.п." in k else 0.1
        assert abs(got[k] - v) <= tol, f"{k}: получено {got[k]:.3f}, ожидалось {v} (допуск {tol})"
    assert got["вердикт"] == "проходит"
    return "OK"


def test_property_terminal_identity():
    """payout_L = 1 − g/ROE выполняется, и рост на выходе сходится к g_terminal."""
    p = Params()
    flows, bvps, eps = project_flows(replace(p, h_distress=0, h_expropriation=0,
                                             p_willingness=1.0, payment_fraction=1.0))
    g_late = flows[-1] / flows[-2] - 1.0
    assert abs(g_late - p.g_terminal) < 1e-4, f"терминальный рост {g_late:.5f} ≠ {p.g_terminal}"
    return "OK"


def test_property_ri_equivalence():
    """Дивидендный и остаточно-доходный расчёты совпадают на бессобытийной траектории."""
    diff = check_ri_equivalence(Params(), 0.232)
    assert diff < 1e-6, f"расхождение DDM/RI = {diff:.9f}"
    return "OK"


def test_property_unique_root():
    """Найденная ставка действительно обнуляет невязку и единственна на интервале."""
    base, scen, price, *_ = golden_case()
    cf, _ = expected_flows(base, scen)
    r = solve_rate(cf, price)
    assert abs(pv(cf, r) - price) < 1e-6
    assert pv(cf, r - 0.01) > price and pv(cf, r + 0.01) < price, "PV не монотонна"
    return "OK"


def test_negative_rate_averaging():
    try:
        average_rates_forbidden()
    except NotImplementedError:
        return "OK"
    raise AssertionError("усреднение ставок должно падать")


def test_negative_hazard_sum():
    try:
        check_hazard_mode([0.10, 0.15, 0.05], approx=True)
    except ValueError:
        return "OK"
    raise AssertionError("приближённое сложение больших интенсивностей должно падать")


def test_negative_bad_probabilities():
    base, scen, *_ = golden_case()
    bad = [replace(scen[0], prob=0.5)] + scen[1:]
    try:
        expected_flows(base, bad)
    except ValueError:
        return "OK"
    raise AssertionError("несуммирующиеся вероятности должны падать")


def test_negative_catastrophic_irr():
    """В катастрофическом состоянии ставка не существует — solve_rate обязан отказать."""
    cf = [5.0] + [0.0] * 49
    try:
        solve_rate(cf, 95.0)
    except ValueError:
        return "OK"
    raise AssertionError("несуществующая ставка должна падать, а не возвращать число")


def test_bank_capacity_no_double_count():
    """Прибыль не должна учитываться в мосте дважды."""
    cet1_pre = 13.0 + 3.0     # капитал прошлого года + прибыль
    cap = bank_capacity(cet1_pre, rwa=110.0, target_ratio=0.11)
    assert abs(cap - (16.0 - 12.1)) < 1e-9
    return "OK"


def test_bank_golden():
    """Банк с достаточностью выше целевой ОБЯЗАН иметь ненулевую ёмкость и осмысленную
    дивидендную доходность. Тест закрывает ошибку инициализации CET1, найденную при
    раскатке на реальных данных (Сбер давал 0.4% дивдоходности)."""
    p = Params(is_bank=True, cet1_ratio0=0.13, cet1_target=0.11, rwa_growth=0.10,
               roe0=0.24, roe_terminal=0.20, payout0=0.50)
    flows, bvps, _ = project_flows(p)
    dy = flows[0] / p.bv0
    assert dy > 0.03, f"дивдоходность банка {dy*100:.2f}% — ёмкость обнулена, проверьте мост CET1"
    assert flows[0] > 0 and flows[5] > 0, "поток банка не должен схлопываться"
    return "OK"


def test_engine_router():
    """Маршрутизатор обязан уводить непригодные для BFV-D профили в другой движок,
    а не считать их дивидендно-балансовой моделью."""
    assert select_engine(bvps=-50, roe=0.20, pb=None, payout=0.9) == "BFV-F"      # отриц. капитал
    assert select_engine(bvps=279, roe=1.11, pb=10.0, payout=1.0) == "BFV-F"      # asset-light
    assert select_engine(bvps=100, roe=0.02, pb=0.5, payout=0.0) == "BFV-F"       # ROE ниже роста
    assert select_engine(bvps=100, roe=0.22, pb=1.0, payout=0.5) == "BFV-D"       # ядро
    assert select_engine(bvps=100, roe=0.24, pb=0.9, payout=0.5, is_bank=True) == "BFV-D"
    return "OK"


ALL_TESTS = [
    ("золотой тест §17", test_golden),
    ("золотой тест: банк", test_bank_golden),
    ("маршрутизатор движков", test_engine_router),
    ("свойство: терминальное тождество", test_property_terminal_identity),
    ("свойство: DDM ≡ RI без событий", test_property_ri_equivalence),
    ("свойство: единственность корня", test_property_unique_root),
    ("негатив: усреднение ставок", test_negative_rate_averaging),
    ("негатив: сложение интенсивностей", test_negative_hazard_sum),
    ("негатив: сумма вероятностей", test_negative_bad_probabilities),
    ("негатив: ставка не существует", test_negative_catastrophic_irr),
    ("банк: прибыль в мосте один раз", test_bank_capacity_no_double_count),
]


if __name__ == "__main__":
    print("=" * 66)
    print("BFV-D — эталонный расчёт (методика v1.0, §17)")
    print("=" * 66)
    for k, v in run_golden().items():
        print(f"  {k:<34} {v if isinstance(v, str) else f'{v:>8.2f}'}")

    print("\n" + "=" * 66)
    print("ТЕСТЫ (§19)")
    print("=" * 66)
    failed = 0
    for name, fn in ALL_TESTS:
        try:
            print(f"  [{fn()}]   {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}\n         {e}")
    print(f"\n  итог: {len(ALL_TESTS) - failed}/{len(ALL_TESTS)} пройдено")


def _demo_footer():
    print("\n" + "=" * 66)
    print("ДЕМОНСТРАЦИЯ §3: asset-light в двух движках")
    print("=" * 66)
    for k, v in demo_asset_light().items():
        print(f"  {k:<36} {v if isinstance(v,str) else f'{v:>9.1f}'}")
