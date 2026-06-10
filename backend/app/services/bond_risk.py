"""Методика «Доходность vs риск» (docs/bond_analys.md) — расчёт КОДОМ.

3 шага: (1) фактический G-spread → (2) требуемый спред = медиана группы из нашей
базы + надбавки + Risk Score → (3) вердикт-светофор + проверка ожидаемыми потерями
+ стоп-правила. Risk Score (1–5) — синтез доступных сигналов: агентский рейтинг
(якорь), долговая нагрузка эмитента из financials.json (блок A, для публичных),
рыночный сигнал (спред vs группа), стоп-флаги (дефолт, аномалия). Где данных нет —
честная деградация (помечается). Без «купить/продать».
"""
import json
from datetime import date
from pathlib import Path

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"


def _days_to(d) -> int | None:
    """Дней до даты (offer_date). Принимает date/ISO-строку. None — если нет/прошло давно."""
    if not d:
        return None
    try:
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        elif hasattr(d, "date"):
            d = d.date()
        return (d - date.today()).days
    except Exception:
        return None


def is_near_offer_artifact(bond: dict) -> bool:
    """YTM-артефакт близкой пут-оферты: до оферты считаные дни/месяцы, цена у номинала,
    а YTM к ПОГАШЕНИЮ технически раздут коротким горизонтом. Это НЕ премия за риск и
    НЕ дистресс (дистресс = цена сильно ниже номинала). Дискриминатор — цена ≥ ~93%."""
    d_off = _days_to(bond.get("offer_date"))
    ytm, price = bond.get("ytm"), bond.get("last_price")
    return (d_off is not None and 0 <= d_off <= 120 and ytm is not None and ytm > 35
            and (price is None or price >= 93))

# рейтинговая группа по букве (нац. шкала)
def rating_group(rating: str | None) -> str | None:
    if not rating:
        return None
    b = rating.rstrip("+-").upper()
    if b in ("AAA", "AA"):
        return "AAA-AA"
    if b == "A":
        return "A"
    if b == "BBB":
        return "BBB"
    if b == "BB":
        return "BB"
    if b == "B":
        return "B"
    return "CCC-"  # CCC/CC/C/RD/D

# годовая вероятность дефолта по группе (ориентиры из методики, верификация — на ОК)
PD_BY_GROUP = {"AAA-AA": 0.001, "A": 0.005, "BBB": 0.01, "BB": 0.03, "B": 0.07, "CCC-": 0.22}
LGD = 0.70  # консервативно для необеспеченных ВДО
# базовый Risk Score (1–5) по агентскому рейтингу
SCORE_BY_GROUP = {"AAA-AA": 1.4, "A": 2.2, "BBB": 3.0, "BB": 3.8, "B": 4.3, "CCC-": 4.8}
# Risk Score → подразумеваемая группа (для «оценки Basis»)
SCORE_TO_GROUP = [(1.8, "AAA-AA"), (2.6, "A"), (3.4, "BBB"), (3.8, "BB"), (4.2, "B"), (5.1, "CCC-")]
# порядок групп по росту риска (для выбора худшей и требуемого спреда)
GROUP_RANK = {"AAA-AA": 0, "A": 1, "BBB": 2, "BB": 3, "BB-B": 3, "B": 4, "CCC-": 5}


def worse_group(g1: str | None, g2: str | None) -> str | None:
    cands = [g for g in (g1, g2) if g]
    if not cands:
        return None
    return max(cands, key=lambda g: GROUP_RANK.get(g, 3))


def score_to_group(score: float) -> str:
    for hi, g in SCORE_TO_GROUP:
        if score < hi:
            return g
    return "CCC-"


def _last(seq):
    if not isinstance(seq, list):
        return None
    for v in reversed(seq):
        if v is not None:
            return v
    return None


def issuer_debt_adjustment(ticker: str | None) -> tuple[float, str | None]:
    """Поправка к Risk Score из financials.json эмитента (блок A). (Δscore, факт)."""
    if not ticker:
        return 0.0, None
    p = COMPANIES_DIR / ticker / "financials.json"
    if not p.exists():
        return 0.0, None
    try:
        fin = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0.0, None
    ratios = (fin.get("balance_sheet", {}) or {}).get("ratios", {}) or {}
    inc = fin.get("income_statement", {}) or {}
    nd = _last(ratios.get("net_debt_ebitda"))
    ebitda, fin_costs = _last(inc.get("ebitda")), _last(inc.get("finance_costs"))
    icr = (abs(ebitda) / abs(fin_costs)) if (ebitda and fin_costs) else None
    adj, facts = 0.0, []
    if nd is not None:
        if nd > 6: adj += 0.8; facts.append(f"Долг/EBITDA {nd:.1f}× — критическая нагрузка")
        elif nd > 4: adj += 0.5; facts.append(f"Долг/EBITDA {nd:.1f}× — высокая нагрузка")
        elif nd > 3: adj += 0.2; facts.append(f"Долг/EBITDA {nd:.1f}× — повышенная")
        elif nd < 1.5: adj -= 0.3; facts.append(f"Долг/EBITDA {nd:.1f}× — низкая нагрузка")
    if icr is not None:
        if icr < 1: adj += 0.6; facts.append(f"Покрытие процентов {icr:.1f}× — проедает себя")
        elif icr < 1.5: adj += 0.3; facts.append(f"Покрытие процентов {icr:.1f}× — напряжённо")
        elif icr > 4: adj -= 0.2; facts.append(f"Покрытие процентов {icr:.1f}× — комфортно")
    return adj, ("; ".join(facts) if facts else None)


def compute_risk_score(bond: dict, debt_adj: float = 0.0) -> float:
    """Risk Score (1–5): якорь по рейтингу/спред-тиру + блок A + стоп-флаги."""
    if bond.get("is_defaulted"):
        return 5.0
    g = rating_group(bond.get("agency_rating"))
    if g:
        base = SCORE_BY_GROUP[g]
    else:  # нет рейтинга → по рыночному тиру
        base = {"gov": 1.2, "high": 2.2, "medium": 3.2, "speculative": 4.2}.get(bond.get("risk_tier"), 3.5)
    score = base + debt_adj
    if bond.get("yield_anomaly"):
        score = max(score, 4.6)
    return round(min(max(score, 1.0), 5.0), 2)


def group_median_spreads(rows: list[dict]) -> dict:
    """Медианный G-spread по рейтинговой группе из нашей базы (требуемый спред-базис)."""
    from statistics import median
    buckets: dict[str, list] = {}
    for b in rows:
        if b.get("bond_type") == "ofz" or b.get("spread_bp") is None or b.get("is_defaulted"):
            continue
        # чистим базис требуемого спреда: флоатеры/линкеры (G-spread к фикс-ОФЗ
        # бессмыслен), near-offer артефакты и аномалии не должны раздувать медиану
        if b.get("coupon_type") in ("floater", "linker"):
            continue
        if is_near_offer_artifact(b):
            continue
        g = rating_group(b.get("agency_rating")) or _tier_group(b.get("risk_tier"))
        if g:
            buckets.setdefault(g, []).append(b["spread_bp"])
    return {g: round(median(v)) for g, v in buckets.items() if v}


def _tier_group(tier: str | None) -> str | None:
    return {"high": "A", "medium": "BBB", "speculative": "B"}.get(tier)


def yield_vs_risk(bond: dict, group_medians: dict) -> dict | None:
    """Полный вердикт «доходность vs риск» по методике для одной бумаги."""
    if bond.get("bond_type") == "ofz":
        return {"verdict": "ОФЗ — госдолг, кредитного риска практически нет; доходность = безрисковая ставка.", "light": "green", "is_ofz": True}
    # дефолт проверяем ДО спреда: у дефолтных YTM обнулён, иначе попали бы в «нет данных»
    if bond.get("is_defaulted"):
        return {"light": "red", "label": "Дефолт — доходность нерелевантна", "is_defaulted_verdict": True,
                "verdict_prose": ["**Эмитент в дефолте** (режим Д / отметка MOEX). Доходность к погашению здесь нерелевантна — вопрос не «сколько заработаю», а «какую часть тела удастся вернуть». Цена обычно отражает ожидаемый процент возврата (recovery), а не доход. Risk Score = 5,0 из 5. Подробности — в «Разборе аналитика», если он есть."],
                "risk_score": 5.0, "stops": ["дефолт/режим Д"],
                "certainty": "факт (дефолт по данным MOEX)"}
    # near-offer артефакт: близкая пут-оферта раздувает YTM к погашению — это не
    # премия за риск и не дистресс. Светофор-вердикт по премии не строим.
    if is_near_offer_artifact(bond):
        d_off = _days_to(bond.get("offer_date"))
        return {"light": "gray", "near_offer": True, "simple_verdict": True,
                "label": "Доходность искажена близкой офертой",
                "verdict": (f"До пут-оферты ~{d_off} дн., бумага у номинала — поэтому «доходность к погашению» "
                            f"({bond.get('ytm'):.0f}%) технически раздута коротким сроком и НЕ отражает ни риска, "
                            "ни реальной отдачи. Это не дистресс. Корректно оценивать доходность можно только после "
                            "оферты, когда эмитент назначит новый купон. Кредитное качество — см. рейтинг и разбор ниже."),
                "certainty": "оценка (артефакт near-offer)"}

    # флоатер: купон привязан к ставке (КС/RUONIA), G-spread к фиксированной ОФЗ
    # бессмыслен. Премию-арифметику не строим — даём кредитную оценку по Risk Score.
    if bond.get("coupon_type") == "floater":
        debt_adj_f, debt_facts_f = issuer_debt_adjustment(bond.get("issuer_ticker"))
        score_f = compute_risk_score(bond, debt_adj_f)
        implied_f = score_to_group(score_f)
        agency_f = rating_group(bond.get("agency_rating"))
        if score_f < 2.6: light_f, lab_f = "green", "Кредитный риск умеренный (плавающий купон)"
        elif score_f < 3.4: light_f, lab_f = "amber", "Кредитный риск средний (плавающий купон)"
        elif score_f < 4.2: light_f, lab_f = "orange", "Повышенный кредитный риск (ВДО, плавающий купон)"
        else: light_f, lab_f = "red", "Высокий кредитный риск (плавающий купон)"
        _gm = {"AAA-AA": "высшая надёжность", "A": "крепкий инвестуровень", "BBB": "нижний инвестуровень",
               "BB": "спекулятивный (ВДО)", "B": "высокий риск (ВДО)", "CCC-": "близко к дефолту"}.get(implied_f, "")
        vp_f = [(f"**Плавающий купон (флоатер).** Процентного риска тела почти нет — купон подстраивается под "
                 "ключевую ставку, поэтому YTM/спред к фиксированной ОФЗ для такой бумаги некорректны. Плата за "
                 "риск здесь — это надбавка купона к ставке (КС/RUONIA), а весь оставшийся риск — **кредитный**."),
                (f"**Кредитная оценка Basis: {implied_f}{(' — ' + _gm) if _gm else ''}** (Risk Score "
                 f"{str(score_f).replace('.', ',')} из 5)" + (f"; агентство — {bond.get('agency_rating')}." if agency_f else "; рейтинга агентств нет."))]
        if debt_facts_f:
            vp_f.append(f"**Долг эмитента:** {debt_facts_f}.")
        return {"light": light_f, "label": lab_f, "floater_verdict": True, "simple_verdict": True,
                "risk_score": score_f, "implied_group": implied_f, "agency_group": agency_f,
                "debt_facts": debt_facts_f, "verdict_prose": vp_f,
                "certainty": "оценка (флоатер: кредитный риск без G-спреда)"}

    spread = bond.get("spread_bp")
    if spread is None:
        return {"verdict": "Нет рыночной оценки (неликвид / нет YTM) — соответствие доходности риску оценить нельзя.", "light": "gray", "no_data": True}

    debt_adj, debt_facts = issuer_debt_adjustment(bond.get("issuer_ticker"))
    score = compute_risk_score(bond, debt_adj)
    implied = score_to_group(score)
    agency_g = rating_group(bond.get("agency_rating"))
    rgroup = agency_g or _tier_group(bond.get("risk_tier")) or implied
    # требуемый спред — по ХУДШЕЙ из (агентский рейтинг, оценка Basis): если наш
    # анализ видит риск выше рейтинга, не занижаем требуемую премию (методика 3.1)
    req_group = worse_group(rgroup, implied)
    base_req = group_medians.get(req_group) or group_medians.get(rgroup) or spread
    req = base_req
    adj_notes = []
    if not bond.get("agency_rating"):
        req += 100; adj_notes.append("+100 б.п. за отсутствие рейтинга")
    divergence_note = None
    if agency_g and GROUP_RANK.get(implied, 3) - GROUP_RANK.get(agency_g, 3) >= 2:
        divergence_note = f"Наш анализ видит риск ВЫШЕ рейтинга: оценка Basis ~{implied} против {agency_g} у агентства."
    elif agency_g and GROUP_RANK.get(agency_g, 3) - GROUP_RANK.get(implied, 3) >= 2:
        divergence_note = f"Наш анализ видит риск НИЖЕ рейтинга: оценка Basis ~{implied} против {agency_g} у агентства."
    required = round(req)

    premium = spread - required  # >0 = риск оплачен
    # светофор по методике
    if premium > 200: light, label = "green", "Риск оплачен с запасом"
    elif premium >= 50: light, label = "green", "Риск оплачен"
    elif premium >= -50: light, label = "amber", "Справедливо"
    elif premium >= -200: light, label = "orange", "Риск недоплачен"
    else: light, label = "red", "Риск существенно недоплачен"

    # стоп-правила (перекрывают арифметику премии — методика 3.4)
    stops = []
    _ytm, _price = bond.get("ytm"), bond.get("last_price")
    anomaly = bool(bond.get("yield_anomaly")) or (_ytm is not None and _ytm > 40)
    distress_price = _price is not None and _price < 90  # цена сильно ниже номинала = рынок ждёт потерь
    distress = False
    if bond.get("is_defaulted"):
        light, label = "red", "Дефолт — доходность нерелевантна"; stops.append("дефолт/режим Д"); distress = True
    if distress_price:
        # дистресс: огромная «премия» — это не оплата риска, а дисконт под ожидаемые потери
        if light in ("green", "amber", "orange"):
            light, label = "red", "Дистресс — цена сильно ниже номинала"
        stops.append(f"цена ~{_price:.0f}% номинала — рынок закладывает потери (recovery), а не премию")
        distress = True
    if anomaly:
        if light in ("green", "amber"):
            light, label = "orange", "Риск недоплачен (аномальная доходность)"
        stops.append("аномальная доходность (>40% годовых) — маркер дистресса/неликвида, не премии")
        if premium > 200:  # большой спред + аномалия = почти всегда дистресс
            light = "red" if distress_price else light
            distress = True
    if premium > 400 and (score >= 4.2):
        if light in ("green", "amber"):
            light, label = "orange", "Большая премия — рынок видит риск выше"
        stops.append("очень большая премия при высоком риске — спросите «что знает рынок?»")
        distress = True

    # проверка ожидаемыми потерями — по худшей группе (консервативно)
    pd = PD_BY_GROUP.get(req_group, PD_BY_GROUP.get(implied, 0.05))
    min_spread_el = round(pd * LGD * 10000)
    el_note = (f"При вероятности дефолта ~{pd*100:.0f}%/год и потере ~{int(LGD*100)}% при дефолте "
               f"минимально нужно ~{min_spread_el} б.п. только за ожидаемые потери. "
               f"Бумага платит {spread} б.п.")

    # НОРМАЛЬНЫЙ ВЕРДИКТ-ОПИСАНИЕ по методике — читаемая оценка «доходность за риск»
    # для КАЖДОЙ бумаги (не голые числа). Главный вывод → расхождение → проверка EL →
    # процентный риск. Это и есть «вердикт», который видит держатель.
    _GRP_MEANING = {
        "AAA-AA": "высшая надёжность (квазигос/крупнейшие)",
        "A": "крепкий эмитент инвестиционного уровня",
        "BBB": "нижний инвестиционный уровень, умеренный риск",
        "BB": "спекулятивный уровень, повышенный риск (ВДО)",
        "B": "высокий кредитный риск (ВДО)",
        "CCC-": "очень высокий риск, близко к дефолту",
    }
    grp = req_group or implied
    gm = _GRP_MEANING.get(grp, "")
    gm_s = f" — {gm}" if gm else ""
    vp = []
    if bond.get("is_defaulted"):
        vp.append("**Эмитент в дефолте.** Доходность к погашению здесь нерелевантна — вопрос не «сколько заработаю», а «какую часть тела удастся вернуть». Цена обычно отражает ожидаемый процент возврата, а не доход.")
    elif distress:
        _why = []
        if distress_price: _why.append(f"цена ~{_price:.0f}% номинала")
        if anomaly: _why.append(f"доходность ~{_ytm:.0f}% годовых")
        _w = ", ".join(_why) or "аномальный спред"
        vp.append(f"**Риск НЕ оплачен — это ценник дистресса, а не премия.** Спред **{spread} б.п.** к ОФЗ выглядит огромным, но это не «доходность с запасом»: {_w} означают, что рынок закладывает высокую вероятность потерь (recovery), а не дарит премию. По стоп-правилам методики аномально широкий спред при таких признаках трактуется как сигнал близости к дефолту/дистресса, а не как выгодная сделка.")
        if divergence_note:
            vp.append(divergence_note)
        vp.append(f"**Проверка здравым смыслом:** на одни ожидаемые потери для группы {grp}{gm_s} нужно ~**{min_spread_el} б.п.**; рынок же требует {spread} б.п. — это и есть мера того, насколько он не доверяет этой бумаге. Здесь вопрос смещается с «какая доходность» на «сколько удастся вернуть».")
        if bond.get("coupon_type") == "floater":
            vp.append("Купон плавающий — процентного риска тела почти нет; весь риск здесь кредитный.")
        if not bond.get("agency_rating"):
            vp.append("⚠ У выпуска нет рейтинга агентств — оценка идёт от рынка и методики Basis.")
    else:
        if light == "green":
            vp.append(f"**Риск оплачен.** Бумага даёт спред **{spread} б.п.** к ОФЗ, а за её уровень кредитного риска (группа {grp}{gm_s}) рынок обычно требует около **{required} б.п.** Премия **{premium:+d} б.п.** в пользу держателя: доходность с запасом покрывает риск этого эмитента.")
        elif light == "amber":
            vp.append(f"**Оценено справедливо.** Спред **{spread} б.п.** к ОФЗ против требуемых ~**{required} б.п.** для группы {grp}{gm_s}. Премия {premium:+d} б.п. в пределах нормы: рынок платит примерно столько, сколько стоит риск, без явной недо- или переоценки.")
        elif light == "orange":
            vp.append(f"**Доходность недоплачивает за риск.** Спред **{spread} б.п.** ниже требуемых ~**{required} б.п.** для группы {grp}{gm_s} (дисконт {premium:+d} б.п.). Вы берёте риск, который рынок в среднем оценивает дороже, чем платит эта бумага.")
        else:
            vp.append(f"**Риск существенно недоплачен.** Спред **{spread} б.п.** заметно ниже требуемых ~**{required} б.п.** для группы {grp}{gm_s} (дисконт {premium:+d} б.п.). За такую доходность кредитный риск этого эмитента не компенсируется.")
        if divergence_note:
            vp.append(divergence_note)
        _cover = "покрывает" if spread >= min_spread_el else "НЕ покрывает"
        _tail = "остаётся премия за неопределённость" if spread >= min_spread_el else "запаса на неожиданности почти нет"
        vp.append(f"**Проверка здравым смыслом:** только на ожидаемые потери (вероятность дефолта ~{pd*100:.0f}%/год × потеря ~{int(LGD*100)}% при дефолте) такой бумаге нужно минимум ~**{min_spread_el} б.п.** Её спред {spread} б.п. этот минимум {_cover} — {_tail}.")
        _ct = bond.get("coupon_type")
        if _ct == "floater":
            vp.append("Купон **плавающий**: процентного риска тела почти нет (купон подстраивается под ставку) — весь риск здесь кредитный.")
        elif _ct == "linker":
            vp.append("Номинал **индексируется на инфляцию** (линкер): доходность считается сверх инфляции, есть защита от роста цен.")
        if not bond.get("agency_rating"):
            vp.append("⚠ У выпуска нет рейтинга агентств — оценка идёт от рынка (спред) и методики Basis; к выводу относитесь осторожнее, чем к рейтингованным бумагам.")
    verdict_prose = vp

    # Прозрачная деривация Risk Score — «за прозрачность»: показываем, КАК получили
    # оценку (методика docs/bond_analys.md), а не отдаём число «из чёрного ящика».
    derivation = []
    if bond.get("is_defaulted"):
        derivation.append("Эмитент в дефолте (режим Д / отметка MOEX) → Risk Score = 5,0 из 5 (максимум). Доходность к погашению нерелевантна — вопрос в проценте возврата тела.")
    else:
        if bond.get("agency_rating"):
            derivation.append(f"Якорь — агентский рейтинг {bond.get('agency_rating')} (группа {agency_g}): базовый Risk Score {SCORE_BY_GROUP.get(agency_g, '—')} из 5.")
        else:
            tier_base = {"gov": 1.2, "high": 2.2, "medium": 3.2, "speculative": 4.2}.get(bond.get("risk_tier"), 3.5)
            derivation.append(f"Рейтинга агентств нет → якорь по рыночному тиру «{bond.get('risk_tier') or 'н/д'}» (спред к ОФЗ): базовый Risk Score {tier_base} из 5.")
        if debt_facts:
            derivation.append(f"Блок A — платёжеспособность (из отчётности эмитента): {debt_facts}. Поправка к Score {debt_adj:+.1f}.")
        elif bond.get("issuer_ticker"):
            derivation.append("Блок A — платёжеспособность: в отчётности эмитента нет ключевых метрик долга, поправка не применена.")
        else:
            derivation.append("Блок A — платёжеспособность: эмитент непубличный, выверенной отчётности в базе нет (нужен глубокий разбор для оценки долга из РСБУ).")
        if bond.get("yield_anomaly"):
            derivation.append("Стоп-флаг: аномальная доходность (>40% годовых) → Risk Score поднят минимум до 4,6 (маркер дистресса/неликвида).")
        derivation.append(f"Итог: Risk Score {str(score).replace('.', ',')} из 5 → оценка Basis ~{implied}.")

    score_method = ("Систематическая оценка по методике Basis: рейтинг-якорь + блок A "
                    "(долговая нагрузка из отчётности, для публичных) + стоп-флаги. "
                    "Блоки бизнеса, собственников, макро/PESTEL и параметров выпуска "
                    "учитываются в полном объёме в «Разборе аналитика» (если он есть по бумаге).")

    return {
        "spread_bp": spread, "required_bp": required, "premium_bp": premium,
        "light": light, "label": label,
        "risk_score": score, "implied_group": implied, "agency_group": agency_g,
        "rating_group": req_group, "group_median_bp": base_req,
        "divergence_note": divergence_note,
        "adjustments": adj_notes, "debt_facts": debt_facts,
        "expected_loss_note": el_note, "min_spread_el_bp": min_spread_el,
        "stops": stops, "verdict_prose": verdict_prose,
        "derivation": derivation, "score_method": score_method,
        "certainty": "оценка (методика Basis по нашей базе)",
    }
