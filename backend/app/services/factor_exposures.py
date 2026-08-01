"""Единый факторный каркас — код-маппер экспозиций Ф1-Ф8 (методика §3.1-3.2,
docs/Basis_методика_индекса_качества_портфеля_v2.1.md).

Восемь факторов, экспозиция Exp(i,k) ∈ {-2,-1,0,+1,+2}, маппится из
effect_sign существующих карточек (macro.json/geo.json) — LLM НЕ вызывается,
только чтение уже посчитанных субагентами полей. Ф8 (рефинансирование)
считается кодом из financials.json.

Потребители: FactorD (D-модуль), MGI (сценарная устойчивость), forward-ERR —
все три через один и тот же движок (app/services/factor_engine.py), чтобы не
плодить расходящиеся суждения об одних и тех же экспозициях (принцип №2
методики).

🔴 Найдено 2026-07-17 (docs/status.md): effect_sign в commodity-факторе
macro.json кодирует «эффект ПРИ ТЕКУЩЕЙ цене относительно нейтрали, которую
аналитик выбрал на момент написания карточки» (Лукойл: Urals $60 ниже
нейтрали $70 → effect_sign=strong_negative), а не структурную чувствительность
«выигрывает ли компания от РОСТА цены товара» — это фиксированное свойство
бизнес-модели (производитель vs потребитель сырья), не зависящее от текущего
уровня цены. Итог без фикса: сценарий «нефть дорожает» показывал нефтяников
проигравшими. stress_scenarios.py уже точечно обходил это для нефтегазового
сектора (exp["commodity"]=2.0 напрямую, не из тега) — здесь тот же приём
обобщён на ВСЕХ commodity-производителей и перенесён в ИСТОЧНИК
(get_company_exposures), чтобы почистить не только стресс-тест, но и MGI/
FactorD/forward-ERR, которые читают эту функцию напрямую.
Осознанно НЕ трогаем потребителей сырья (авиаперевозки/транспорт — топливо
как расход, обратный знак) — это другой, менее изученный случай; честная
деградация (оставить как есть) безопаснее угадывания. Полная точность по
producer/consumer — задача методики market-analyst (см. work-journal.md,
блок «Товар компании»), это временный код-фикс на грубой секторной эвристике
для явных производителей до полной раскатки.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Девять факторов. 🔴 «costs» отделён от «demand» 2026-07-30: раньше _MACRO_TYPE_MAP
# сваливал demand+inflation+labor в один фактор, хотя они РАЗНОНАПРАВЛЕНЫ — спрос это
# уровень выручки (структурно почти все его любят), а инфляция издержек и зарплаты это
# расход (структурно все страдают от роста). Сценарий задаёт demand: -1.0 = «спрос
# падает», и издержки внутри того же фактора читались как «издержки падают» = хорошо.
# Плюс labor (98% факторов негативны — и это ВЕРНО) утягивал медианную demand-экспозицию
# в -0.67, из-за чего в стрессе большинство компаний «росло». Слить с инверсией знака
# было нельзя: в стагфляционном стрессе спрос падает, а издержки РАСТУТ одновременно.
FACTOR_KEYS = ["rate", "demand", "costs", "fx", "commodity", "sanctions", "conflict",
               "fiscal", "refinancing"]
FACTOR_LABELS = {
    "rate": "Ключевая ставка", "demand": "Внутренний спрос",
    "costs": "Издержки: зарплаты и инфляция", "fx": "Курс рубля",
    "commodity": "Цены экспортного сырья",
    "sanctions": "Санкции и внешние ограничения", "conflict": "Военная эскалация",
    "fiscal": "Регуляторно-налоговое давление", "refinancing": "Рефинансирование и кредитный цикл",
}
# type в macro.json/geo.json → наш факторный ключ
_MACRO_TYPE_MAP = {"rate": "rate", "demand": "demand", "inflation": "costs", "labor": "costs",
                    "fx": "fx", "commodity": "commodity", "fiscal": "fiscal"}

# ────────────────── знак-оракул: структурная бета из quant_inputs ──────────────────
# 🔴 Найдено 2026-07-30. `effect_sign` кодирует «как ТЕКУЩЕЕ состояние фактора влияет на
# компанию», а сценарный движок читает его как «структурную бету к УРОВНЮ фактора». Это
# те же грабли, что с commodity 2026-07-17, но шире. Доказательство из данных: ЛУКОЙЛ
# fx=negative («Крепнущий рубль»), РОСНЕФТЬ fx=strong_negative («Крепкий рубль»), а ГМК
# fx=positive («курс — главный операционный рычаг экспортёра») — три экспортёра, одна
# экономика, противоположные знаки, потому что первые двое описывают СОСТОЯНИЕ курса, а
# третий СТРУКТУРУ. По demand положительных было лишь 7%, хотя конвенция сценариев прямо
# предполагает обратное; М.Видео (strong_negative = «слабый спрос бьёт по нам») движок
# читал как «выигрывает от обвала спроса» и рисовал +15% в стрессе.
#
# Взамен: `quant_inputs.coefficients[канал].net_profit` — Δприбыли на единицу драйвера,
# то есть настоящая структурная бета. Знаки по вселенной экономически верны:
# demand 184+/4-, labor 0+/110-, cost_inflation 4+/199-, cost_of_risk 0+/16-,
# commodity 35+/3-, fx 63+/38-, rate 96+/153- (банки при этом в плюсе — источник
# различает даже их между собой).
# 🔴 Берём из коэффициента ТОЛЬКО ЗНАК: сырой знак корректен всегда, а вот нормировка на
# прибыль ломается при убытке (у Сегежи rate=-0.7 при ЧП=-88.3 млрд деление дало бы
# +0.8% — переворот). Амплитуда остаётся из effect_sign (|значение| он передаёт разумно).
_COEF_CHANNEL_TO_FACTOR = {
    "rate": "rate", "nim": "rate",
    # 🔴 cost_of_risk ведём в demand, а НЕ в rate: кредитные потери банка — функция
    # экономического ЦИКЛА, а не цены денег. Именно это даёт корректный портрет банка,
    # которого требовал владелец: ставка в плюс (NIM), спрос в минус (стоимость риска),
    # и в стрессе (ставка вверх + спрос вниз) каналы честно неттингуются вместо
    # «банк зарабатывает +9.6% на эскалации».
    "cost_of_risk": "demand", "demand": "demand", "equity_market": "demand",
    "collection": "demand",
    "cost_inflation": "costs", "labor": "costs", "food_inflation": "costs",
    "fx": "fx",
    "commodity": "commodity", "steel_price": "commodity",
    # tax (2 компании) сознательно НЕ маппим: налоговый шок вводится отдельным
    # сценарием, а не фактором из карточек (покрытия для фактора нет).
    "tariff": "fiscal",
}

# Каналы, чей драйвер движется ОБРАТНО драйверу своего фактора. Стоимость риска растёт,
# когда цикл (ВВП) слабеет, поэтому её вклад в бету «к росту спроса» берётся с инверсией.
_COEF_CHANNEL_INVERTED = {"cost_of_risk"}

# Единичный шок по каналу — в тех же единицах, в которых задан коэффициент (`per`).
# Калибровка по историческим эпизодам РФ (2014/2020/2022), НЕ по расстоянию от нейтрали:
# расстояние — мера текущего дисбаланса, она разная у разных компаний и дат, нормировать
# бету по ней нельзя. Единицы в данных почти унифицированы (проверено): 100bp == 1pp,
# cost_of_risk везде 1bp, fx везде 1_rub, cost_inflation 1pp.
_CHANNEL_SHOCK = {
    "rate": 3.0, "nim": 3.0,            # ставка +300 б.п.
    "cost_of_risk": 150.0,              # CoR +150 б.п. (в единицах 1bp)
    "demand": 2.0,                      # ВВП ±2 п.п.
    "equity_market": 2.0, "collection": 2.0,
    "labor": 3.0,                       # зарплаты +3 п.п.
    "cost_inflation": 5.0, "food_inflation": 5.0,
    "fx": 15.0,                         # USDRUB +15 ₽ (ослабление рубля ~20%)
    "commodity": 20.0, "steel_price": 20.0,
    "tariff": 5.0,
}
# Доля капитализации, «съедаемая» единичным шоком, которая считается предельной
# экспозицией |2|. Произвол, задокументированный: 12% стоимости на один шок — уже
# экстремальная чувствительность.
_EXPOSURE_FULL_SCALE = 0.12

# Приведение единицы коэффициентов карточки к МЛРД ₽ (в них считается капитализация).
# млн_usd оставлен незакрытым сознательно: курс тут не подставить без риска соврать,
# таких карточек 2 — они честно выпадают в None, а не считаются наугад.
_COEF_UNIT_TO_BLN = {"млрд_руб": 1.0, "млн_руб": 0.001}
# 🔴 УСТАРЕЛ (2026-07-30): geo.json ключа `factors` больше не имеет — схема сменилась
# при миграции geo-system v0.9 (коммит 2335f41ee1, 2026-07-12). Оставлен как фолбэк
# на случай старых файлов; новый путь — gre_profile, см. _sanctions_exposure/
# _conflict_exposure ниже.
_GEO_TYPE_MAP = {"sanctions": "sanctions", "conflict": "conflict"}

# ────────────────────── gre_profile → sanctions/conflict ──────────────────────
# 🔴 Найдено 2026-07-30 (владелец: «сценарная устойчивость 100 у всех»): маппер
# читал geo.json["factors"][].type, но миграция geo v0.9 переименовала всю схему —
# ключа `factors` нет НИ У ОДНОЙ из 264 компаний. Код не падал: экспозиция молча
# становилась None, «честная деградация» съедала фактор. Итог — sanctions и conflict
# имели 0% покрытия, то есть стрессовый сценарий, подписанный в UI как «эскалация +
# санкции», не содержал ни эскалации, ни санкций; работали только rate/demand/
# commodity/fx. Портфель банков «зарабатывал» +9.6% в стрессе → MGI=100.
#
# Взамен `factors` в новой схеме есть gre_profile — 15 компонентов E1-E15 со score
# (покрытие 264/264). Маппинг НЕ механический, знаковая безопасность разная:
#
# SANCTIONS — маппится прямо: все взятые компоненты монотонны в одну сторону (нет
#   компании, которая при E1=5 выигрывает от ужесточения режима). E1 берётся с
#   удвоенным весом (санкционный статус самого эмитента — доминирующий канал), E13
#   («персональный слой») сознательно НЕ берётся: он уже частично сидит в E1/E9,
#   иначе задвоение.
# CONFLICT — знак из score НЕ извлекается, это те же грабли, что с commodity
#   2026-07-17 (см. докстринг файла). Проверено на данных: IRKT E12=4.0 —
#   «БЕНЕФИЦИАР военного цикла», SBER E12=4.0 — «фискальный ДОНОР»; одинаковый балл,
#   противоположный знак. Поэтому амплитуда берётся из E14 (war/peace-бета), а знак —
#   минус по умолчанию (согласовано с _sign_convention в quality_scenarios.json:
#   большинство страдает от эскалации) + курируемый белый список бенефициаров.
_SANCTION_COMPONENT_WEIGHTS = {
    "E1": 2.0,   # санкционный статус эмитента — доминирующий канал
    "E3": 1.0,   # экспортная логистика
    "E4": 1.0,   # платёжные каналы
    "E5": 1.0,   # импортозависимость (капекс/опекс)
    "E6": 1.0,   # технологическая зависимость
    "E10": 1.0,  # зарубежные активы
}

# Война-бенефициары НА УРОВНЕ ЦЕНЫ АКЦИИ (не выручки!). MGI меряет переоценку бумаги,
# поэтому критерий — инвертированная equity-бета из E14, а НЕ «оборонная выручка» из
# E12. Разница принципиальная и проверена по rationale карточек (2026-07-30): из семи
# кандидатов с оборонной выручкой (E12≥3.5) на уровне СТОИМОСТИ война-бенефициарами
# оказались только двое. Остальные развёрнуты самими карточками (их red-team уже это
# отработал): ZVEZ — «ΔS1 ≈ +20…+35%, ΔS4 ≈ −20…−35%» (пис-бета по цене), CHKZ — «на
# уровне стоимости это УМЕРЕННАЯ ПИС-БЕТА», UNAC — «EQUITY эмпирически ведёт себя как
# ОБЫЧНАЯ risk-on бумага, НЕ инверсно», KMAZ — доминирует пис-компонента через
# процентные расходы, RKKE — «лёгкий негативный скос к эскалации». Список ручной и
# короткий сознательно: механический отбор по E12 ошибся бы в 5 случаях из 7.
_WAR_BENEFICIARY_TICKERS = {
    "IRKT",  # «РЕДКИЙ инвертированный профиль (якорь 4 = высокая ВОР-бета)»
    "NAUK",  # «Якорь 4 = высокая ВОР-бета: бенефициар продолжения»
}

_SIGN_MAP = {"strong_negative": -2, "negative": -1, "mixed": 0, "neutral": 0,
             "positive": 1, "strong_positive": 2}

# Секторы, где компания С ВЫСОКОЙ УВЕРЕННОСТЬЮ — чистый ПРОИЗВОДИТЕЛЬ своего
# ключевого сырья (выигрывает от роста его цены) — извлечение/переработка,
# не переработка чужого сырья в конечный продукт с тонкой маржой. Подстроки,
# регистронезависимо, матчатся против company.sector (зоопарк рус/eng слагов,
# см. generate-seo-pages.js normalizeSector() — тот же приём). Осознанно НЕ
# включены: transport/авиаперевозки (топливо — расход, обратный знак),
# consumer/finance_retail/building_materials (неоднозначно без разбора
# конкретной компании — честная деградация лучше угадывания).
_COMMODITY_PRODUCER_SECTOR_TOKENS = (
    "нефт", "газ", "oil_gas", "metals", "металл", "chemicals", "химия",
    "удобрен", "нефтехим", "coal_mining", "уголь", "metals_mining", "добыча",
    "драгоценн", "лесопромышленн", "уран",
)


def _is_commodity_producer_sector(sector: str | None) -> bool:
    s = (sector or "").lower()
    return any(tok in s for tok in _COMMODITY_PRODUCER_SECTOR_TOKENS)


def _load_json(ticker: str, filename: str) -> dict | None:
    path = COMPANIES_DIR / ticker.upper() / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _refinancing_exposure(fin: dict) -> int | None:
    """Ф8 кодом (методика §3.2, произвол): ND/EBITDA>3 и короткий долг>30%→-2;
    ND/EBITDA>2 или короткий долг>30%→-1; иначе 0; чистый кэш→+1."""
    bal = fin.get("balance_sheet") or {}
    ratios = bal.get("ratios") or {}
    nd_ebitda_series = ratios.get("net_debt_ebitda") or []
    nd_ebitda = next((v for v in reversed(nd_ebitda_series) if v is not None), None)
    st = bal.get("short_term_debt") or []
    lt = bal.get("long_term_debt") or []
    st_last = next((v for v in reversed(st) if v is not None), None)
    lt_last = next((v for v in reversed(lt) if v is not None), None)
    short_ratio = None
    if st_last is not None and lt_last is not None and (st_last + lt_last) > 0:
        short_ratio = st_last / (st_last + lt_last)
    if nd_ebitda is None and short_ratio is None:
        return None
    nd_ebitda = nd_ebitda if nd_ebitda is not None else 0
    short_ratio = short_ratio if short_ratio is not None else 0
    if nd_ebitda < 0:  # чистый кэш
        return 1
    if nd_ebitda > 3 and short_ratio > 0.30:
        return -2
    if nd_ebitda > 2 or short_ratio > 0.30:
        return -1
    return 0


_market_caps: dict[str, float] | None = None


def _load_market_caps() -> dict[str, float]:
    """{ticker: капитализация в МЛРД ₽} — живая, close × число акций (как везде на
    платформе цена берётся из quotes). Один раз на процесс."""
    global _market_caps
    if _market_caps is not None:
        return _market_caps
    try:
        from sqlalchemy import text

        from app.db.session import SessionLocal
        db = SessionLocal()
        try:
            rows = db.execute(text(
                "WITH l AS (SELECT DISTINCT ON (company_id) company_id, close FROM quotes "
                "ORDER BY company_id, date DESC) "
                "SELECT c.ticker, COALESCE(l.close * c.shares_outstanding, c.market_cap), "
                "       c.historical_tickers "
                "FROM companies c LEFT JOIN l ON l.company_id = c.id"
            )).all()
        finally:
            db.close()
        caps: dict[str, float] = {}
        for ticker, cap, hist in rows:
            if not ticker or not cap or float(cap) <= 0:
                continue
            value = float(cap) / 1e9
            caps[ticker] = value
            # Карточки живут под ПРЕЖНИМ тикером после редомициляции/переименования
            # (HHRU→HEAD, AGRO→RAGR) — без этого у них не находилась капитализация и
            # они молча оставались на старом (перевёрнутом) effect_sign.
            for h in hist or []:
                alias = h.get("ticker") if isinstance(h, dict) else h
                if alias:
                    caps.setdefault(alias, value)
        _market_caps = caps
    except Exception:  # noqa: BLE001
        logger.warning("factor_exposures: капитализация недоступна, экспозиции из коэффициентов отключены",
                       exc_info=True)
        _market_caps = {}
    return _market_caps


def _exposures_from_coefficients(ticker: str, macro: dict | None) -> dict[str, float]:
    """{factor: экспозиция} из quant_inputs.coefficients — структурная бета к РОСТУ
    драйвера, нормированная на капитализацию.

    Экспозиция = Δчистой прибыли на единичный шок ÷ капитализация, приведённая к шкале
    -2..+2. Нормируем на капитализацию, а НЕ на прибыль: прибыль бывает отрицательной и
    околонулевой, и деление на неё переворачивает знак (у Сегежи rate=-0.7 при ЧП=-88.3
    млрд дало бы +0.8% — компания с долгом «выигрывала» бы от роста ставки). Капитализация
    строго положительна, есть у всех, и Δприбыли/cap — это прямо та величина, которая
    нужна движку: доля стоимости под ударом. Побочный эффект экономически верен —
    убыточные и закредитованные при малой капитализации получают большую экспозицию
    (distressed equity действительно гиперчувствителен), хвосты режет кламп.
    """
    qi = (macro or {}).get("quant_inputs") or {}
    coefs = qi.get("coefficients") or {}
    if not coefs:
        return {}
    cap = _load_market_caps().get((ticker or "").upper())
    if not cap:
        return {}
    # 🔴 Единица коэффициентов НЕ одна на всю вселенную (найдено 2026-08-01): в карточках
    # `quant_inputs.unit` = млрд_руб у 215 компаний, но млн_руб у 47 и млн_usd у 2.
    # Первая версия делила на капитализацию в МЛРД, не глядя на unit, — у 49 компаний
    # экспозиция завышалась в 1000 раз. Кламп [-2;+2] это скрывал: микрокапы просто
    # упирались в максимум по всем факторам и выглядели «гиперчувствительными», что
    # правдоподобно для distressed equity и потому не резало глаз.
    scale = _COEF_UNIT_TO_BLN.get(str(qi.get("unit") or "").strip().lower())
    if scale is None:
        return {}  # незнакомая единица — честно молчим, а не считаем наугад

    acc: dict[str, float] = {}
    for channel, spec in coefs.items():
        factor = _COEF_CHANNEL_TO_FACTOR.get(channel)
        if not factor or not isinstance(spec, dict):
            continue
        delta = spec.get("net_profit")
        if not isinstance(delta, (int, float)):
            continue
        shock = _CHANNEL_SHOCK.get(channel)
        if shock is None:
            continue
        if channel in _COEF_CHANNEL_INVERTED:
            shock = -shock
        acc[factor] = acc.get(factor, 0.0) + (delta * scale * shock) / cap

    return {
        f: round(max(-2.0, min(2.0, v / _EXPOSURE_FULL_SCALE * 2)), 2)
        for f, v in acc.items()
    }


def _gre_scores(geo: dict | None) -> dict[str, float]:
    """{E-ключ: score} из gre_profile. score бывает None (напр. SBER E11 — «ФЛАГ, в
    балл не конвертируется») — такие компоненты пропускаем, а не считаем нулём."""
    out: dict[str, float] = {}
    for c in (geo or {}).get("gre_profile") or []:
        key, score = c.get("key"), c.get("score")
        if key and isinstance(score, (int, float)):
            out[key] = float(score)
    return out


def _score_to_exposure(score_1_5: float) -> float:
    """Шкала GRE (1 = нет уязвимости … 5 = максимальная) → экспозиция 0..-2."""
    return -(score_1_5 - 1) / 4 * 2


def _sanctions_exposure(gre: dict[str, float]) -> float | None:
    """Санкционная экспозиция [-2; 0]: 70% доминирующий канал + 30% взвешенное среднее.

    Чистое среднее здесь неверно, и это видно на данных: у Сбера E3 («экспортная
    логистика») = 1.0 просто потому, что у внутреннего банка такого канала НЕТ — при
    усреднении это «смягчало» его санкционный балл и размывало E1=4.0 (SDN) до -0.79.
    Но отсутствие канала ≠ его безопасность: отключение от SWIFT нельзя усреднить
    наличием здоровых направлений. Поэтому базу задаёт самый больной канал, а среднее
    добавляет вклад накопления уязвимостей (Лукойл болен сразу по всем — ему хуже, чем
    компании с одним больным каналом).
    """
    num = den = 0.0
    worst = None
    for key, w in _SANCTION_COMPONENT_WEIGHTS.items():
        s = gre.get(key)
        if s is None:
            continue
        num += w * s
        den += w
        worst = s if worst is None else max(worst, s)
    if den == 0:
        return None
    combined = 0.7 * worst + 0.3 * (num / den)
    return round(max(-2.0, min(0.0, _score_to_exposure(combined))), 2)


def _conflict_exposure(gre: dict[str, float], ticker: str) -> float | None:
    """Амплитуда — из E14 (war/peace-бета), знак — минус, кроме бенефициаров."""
    e14 = gre.get("E14")
    if e14 is None:
        return None
    magnitude = abs(_score_to_exposure(e14))
    sign = 1.0 if ticker.upper() in _WAR_BENEFICIARY_TICKERS else -1.0
    return round(sign * magnitude, 2)


def get_company_exposures(ticker: str) -> dict:
    """{factor_key: exposure(-2..2) или None (дыра — компания непокрыта по фактору)}."""
    exposures: dict[str, list[int]] = {k: [] for k in FACTOR_KEYS}

    macro = _load_json(ticker, "macro.json")
    if macro:
        for f in macro.get("factors") or []:
            key = _MACRO_TYPE_MAP.get(f.get("type"))
            sign = _SIGN_MAP.get(f.get("effect_sign"))
            if key and sign is not None:
                exposures[key].append(sign)

    geo = _load_json(ticker, "geo.json")
    if geo:
        for f in geo.get("factors") or []:
            key = _GEO_TYPE_MAP.get(f.get("type"))
            sign = _SIGN_MAP.get(f.get("effect_sign"))
            if key and sign is not None:
                exposures[key].append(sign)

    fin = _load_json(ticker, "financials.json")
    refinancing = _refinancing_exposure(fin) if fin else None

    out: dict[str, float | None] = {}
    for k in FACTOR_KEYS:
        if k == "refinancing":
            out[k] = refinancing
            continue
        vals = exposures[k]
        out[k] = round(sum(vals) / len(vals), 2) if vals else None

    # 🔴 ГЛАВНЫЙ ИСТОЧНИК — коэффициенты (структурная бета). effect_sign выше остаётся
    # только фолбэком там, где канала в quant_inputs нет: он кодирует СОСТОЯНИЕ, а не
    # структуру, и на нём знак систематически врал (см. блок про знак-оракул).
    coef_exp = _exposures_from_coefficients(ticker, macro)
    if coef_exp:
        # 🔴 Значения из effect_sign по этим факторам ЗАТИРАЮТСЯ ПОЛНОСТЬЮ, а не
        # дополняются. Иначе старая (перевёрнутая) семантика протекает в результат: у
        # ЗИЛа так получалась costs=+1.0 — «компания выигрывает от роста издержек».
        # Канал, не перечисленный аналитиком при заполненных quant_inputs, — это
        # суждение «канал нематериален», то есть 0, а не дыра. Страховка от того,
        # чтобы этим нулём не проглотить настоящую поломку, — секторные полы в
        # контракт-тестах (tests/test_factor_exposures.py).
        for k in ("rate", "demand", "costs", "fx", "commodity"):
            out[k] = coef_exp.get(k, 0.0)

    # sanctions/conflict — из gre_profile (новая схема geo v0.9). Старый путь через
    # geo.json["factors"] выше остаётся фолбэком: если он что-то нашёл (архивный
    # файл), не перетираем.
    gre = _gre_scores(geo)
    if gre:
        if out.get("sanctions") is None:
            out["sanctions"] = _sanctions_exposure(gre)
        if out.get("conflict") is None:
            out["conflict"] = _conflict_exposure(gre, ticker)
    return out


_FISCAL_DONOR_RE = re.compile(r"фискальн\w*\s+донор|донор\w*\s+перв|донор первой очереди", re.I)
_fiscal_donors: set[str] | None = None


def is_fiscal_donor(ticker: str) -> bool:
    """Компания — фискальный донор «первой очереди» (кого реально бьют windfall/НДПИ).

    Классификация текстовым гейтом по rationale компонента E12 в geo.json, а НЕ по его
    баллу: балл E12 двузначен — у Газпрома 5.0 означает «донор», у Яковлева 4.0
    «бенефициар военного цикла». Тот же приём, что уже применён для conflict
    (_WAR_BENEFICIARY_TICKERS): амплитуда из числа, направление из прозы.
    """
    global _fiscal_donors
    if _fiscal_donors is None:
        donors: set[str] = set()
        if COMPANIES_DIR.exists():
            for d in COMPANIES_DIR.iterdir():
                if not d.is_dir() or d.name.startswith("."):
                    continue
                geo = _load_json(d.name, "geo.json")
                for c in (geo or {}).get("gre_profile") or []:
                    if c.get("key") != "E12":
                        continue
                    score, rationale = c.get("score"), c.get("rationale") or ""
                    if isinstance(score, (int, float)) and score >= 3.0 and _FISCAL_DONOR_RE.search(rationale):
                        donors.add(d.name.upper())
        _fiscal_donors = donors
    return (ticker or "").upper() in _fiscal_donors


def get_portfolio_exposures(tickers_weights: dict[str, float]) -> dict:
    """Exp(p,k) = Σ wᵢ·Exp(i,k). Дыры (компания не покрыта по фактору) не
    участвуют в сумме для ЭТОГО фактора — вес перенормируется на покрытую
    часть (честная деградация, а не молчаливый ноль)."""
    tot_w = sum(tickers_weights.values())
    if tot_w <= 0:
        return {k: None for k in FACTOR_KEYS}
    per_company = {t: get_company_exposures(t) for t in tickers_weights}
    out: dict[str, float | None] = {}
    coverage: dict[str, float] = {}
    for k in FACTOR_KEYS:
        num, den = 0.0, 0.0
        for t, w in tickers_weights.items():
            exp = per_company.get(t, {}).get(k)
            if exp is None:
                continue
            num += w * exp
            den += w
        out[k] = round(num / den, 3) if den > 0 else None
        coverage[k] = round(den / tot_w * 100, 1) if tot_w else 0.0
    return {"exposures": out, "coverage_pct": coverage, "per_company": per_company}
