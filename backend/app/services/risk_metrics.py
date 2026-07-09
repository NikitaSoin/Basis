"""Риск-метрики из истории котировок (Этап 2 аналитики портфеля).

Методика (согласована с владельцем):
  - Окно: 3 года дневных данных (меньше — считаем на доступном, history_years
    фиксирует фактическую глубину; <1 года → UI ставит «*»).
  - Доходности: ЛОГАРИФМИЧЕСКИЕ r_t = ln(close_t / close_{t-1}) — аддитивны
    во времени, стандарт для оценки волатильности; от простых отличаются
    на доли процента на дневном шаге.
  - Волатильность: СКО дневных лог-доходностей × √252 → годовая, в %.
  - Бета: cov(бумага, IMOEX) / var(IMOEX) на пересечении торговых дат
    (дни, когда торговались оба ряда). Против IMOEX — рублёвого индекса
    Мосбиржи; RTSI долларовый, MCFTR дивидендный — не подходят.
  - Доходность за 3 года: CAGR = (P_конец / P_начало)^(1/лет) − 1 — честно
    отражает «сколько реально заработал держатель» (средняя дневных
    переоценивает при волатильности). Это ФАКТ прошлого, не прогноз.
  - Сплиты/консолидации (разрыв цены, как VTBR 1:5000): дневная доходность
    |r| > 50% за день считается корпоративным действием и исключается из
    рядов; CAGR через сплит не считается — берём отрезок после разрыва.

Минимум 30 совпадающих торговых дней для беты/корреляции — иначе NULL.
"""
import logging
import math
from datetime import date, timedelta

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Quote
from app.models.market import IndexHistory

logger = logging.getLogger(__name__)

WINDOW_YEARS = 3
TRADING_DAYS = 252
MIN_OVERLAP = 30          # минимум совпадающих дней для беты/корреляции
SPLIT_THRESHOLD = 0.50    # |дневная доходность| выше — разрыв (сплит), не рынок


def window_start(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=int(WINDOW_YEARS * 365.25))


def load_price_series(db: Session, company_id: int, since: date) -> dict[date, float]:
    """Цены закрытия по датам (только положительные)."""
    rows = (
        db.query(Quote.date, Quote.close)
        .filter(Quote.company_id == company_id, Quote.date >= since, Quote.close.isnot(None))
        .order_by(Quote.date)
        .all()
    )
    return {r.date: float(r.close) for r in rows if r.close and float(r.close) > 0}


def load_index_series(db: Session, ticker: str, since: date) -> dict[date, float]:
    rows = (
        db.query(IndexHistory.date, IndexHistory.close)
        .filter(IndexHistory.ticker == ticker, IndexHistory.date >= since)
        .order_by(IndexHistory.date)
        .all()
    )
    return {r.date: float(r.close) for r in rows if r.close and float(r.close) > 0}


def log_returns(series: dict[date, float]) -> dict[date, float]:
    """Дневные лог-доходности по датам; разрывы-сплиты выброшены."""
    dates = sorted(series)
    out: dict[date, float] = {}
    for prev, cur in zip(dates, dates[1:]):
        r = math.log(series[cur] / series[prev])
        if abs(r) <= math.log(1 + SPLIT_THRESHOLD):
            out[cur] = r
    return out


def normalize_splits(series: dict[date, float]) -> dict[date, float]:
    """Склеивает ряд через сплиты/консолидации в непрерывный.

    Движение в разы за день (|r| > SPLIT_THRESHOLD) — корпоративное действие
    (кейс T −89,8% при сплите), а не рынок: рыночные обвалы 24.02.2022 (−36%)
    и ковид (−22%) ниже порога и не трогаются. Цены ДО разрыва домножаются на
    коэффициент сплита (отношение цен после/до), история сохраняется целиком —
    CAGR считается по полному окну, как у бумаг без сплитов.
    """
    dates = sorted(series)
    if len(dates) < 2:
        return dict(series)
    out = dict(series)
    for prev, cur in zip(dates, dates[1:]):
        ratio = series[cur] / series[prev]
        if abs(math.log(ratio)) > math.log(1 + SPLIT_THRESHOLD):
            # всё, что до разрыва, приводим к послесплитовому масштабу
            for d in dates:
                if d <= prev:
                    out[d] = out[d] * ratio
    return out


def annualized_volatility(returns: dict[date, float]) -> float | None:
    """Годовая волатильность, % (СКО дневных лог-доходностей × √252)."""
    if len(returns) < MIN_OVERLAP:
        return None
    sd = float(np.std(list(returns.values()), ddof=1))
    return round(sd * math.sqrt(TRADING_DAYS) * 100, 2)


def beta_vs_index(stock_returns: dict[date, float], index_returns: dict[date, float]) -> float | None:
    """Простая бета: cov/var на пересечении торговых дат."""
    common = sorted(set(stock_returns) & set(index_returns))
    if len(common) < MIN_OVERLAP:
        return None
    s = np.array([stock_returns[d] for d in common])
    i = np.array([index_returns[d] for d in common])
    var = float(np.var(i, ddof=1))
    if var <= 0:
        return None
    cov = float(np.cov(s, i, ddof=1)[0][1])
    return round(cov / var, 4)


def dimson_beta(stock_returns: dict[date, float], index_returns: dict[date, float]) -> float | None:
    """Бета с поправкой Диммсона против занижения от асинхронной торговли.

    Неликвид реагирует на движение индекса с задержкой → дневная ковариация
    «размазывается» по соседним дням и простая бета занижается. Диммсон:
    бета = Σ коэффициентов регрессии доходности бумаги на доходность индекса
    с лагами −1, 0, +1 (β = β₋₁ + β₀ + β₊₁). Стандартный метод (Dimson, 1979).
    """
    common = sorted(set(stock_returns) & set(index_returns))
    if len(common) < MIN_OVERLAP + 2:
        return None
    s = np.array([stock_returns[d] for d in common])
    i = np.array([index_returns[d] for d in common])
    # выравниваем по позициям в общем ряду: lag −1 (индекс вчера),
    # 0 (сегодня), +1 (индекс завтра — ловит опережение бумаги)
    y = s[1:-1]
    x = np.column_stack([i[:-2], i[1:-1], i[2:]])
    x = np.column_stack([np.ones(len(y)), x])
    try:
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    b = float(coef[1] + coef[2] + coef[3])
    if math.isnan(b) or math.isinf(b):
        return None
    return round(b, 4)


def r_squared_vs_index(stock_returns: dict[date, float], index_returns: dict[date, float]) -> float | None:
    """R² = corr² с индексом — доля движения бумаги, объяснённая рынком."""
    common = sorted(set(stock_returns) & set(index_returns))
    if len(common) < MIN_OVERLAP:
        return None
    s = np.array([stock_returns[d] for d in common])
    i = np.array([index_returns[d] for d in common])
    if float(np.std(s)) == 0.0 or float(np.std(i)) == 0.0:
        return None  # «замёрзшая» цена неликвида — корреляция не определена
    corr = float(np.corrcoef(s, i)[0][1])
    if math.isnan(corr):
        return None
    return round(corr * corr, 4)


def downside_volatility(returns: dict[date, float]) -> float | None:
    """Нисходящая волатильность (порог 0): σ только по дням с доходностью <0,
    ×√252, годовая в %. Самостоятельная метрика; полный Сортино — Этап 3
    (числителю нужна безрисковая ставка ОФЗ)."""
    vals = [r for r in returns.values() if r < 0]
    if len(vals) < MIN_OVERLAP:
        return None
    sd = float(np.std(vals, ddof=1))
    return round(sd * math.sqrt(TRADING_DAYS) * 100, 2)


def var_95_daily(returns: dict[date, float]) -> float | None:
    """Исторический VaR 95%, дневной горизонт: 5-й перцентиль дневных
    доходностей, знак перевёрнут (положительное число = величина потери, %).
    На горизонт T дней масштабируется ×√T."""
    vals = list(returns.values())
    if len(vals) < MIN_OVERLAP:
        return None
    p5 = float(np.percentile(vals, 5))
    return round(-p5 * 100, 2)


def cagr_pct(series: dict[date, float]) -> float | None:
    """Доходность за период серии, %.

    Ряд предварительно склеивается через сплиты (normalize_splits) — история
    НЕ отбрасывается, CAGR по полному окну. Защита от взрыва аннуализации:
    при истории < 1 года НЕ возводим в годовую степень — возвращаем простой %
    за период (раньше хвост T в 0,13 года давал дикие ±50% годовых).
    """
    series = normalize_splits(series)
    dates = sorted(series)
    if len(dates) < 2:
        return None
    p0, p1 = series[dates[0]], series[dates[-1]]
    years = (dates[-1] - dates[0]).days / 365.25
    if p0 <= 0 or years <= 0:
        return None
    if years < 1.0:
        # простой % за фактический период, без аннуализации
        return round((p1 / p0 - 1) * 100, 2)
    return round(((p1 / p0) ** (1 / years) - 1) * 100, 2)


def max_drawdown_pct(series: dict[date, float]) -> float | None:
    """Максимальная просадка, %: самое глубокое падение от локального максимума
    до последующего минимума за всю историю ряда (не от начала окна — от
    исторического пика). Отрицательное число = величина просадки."""
    series = normalize_splits(series)
    dates = sorted(series)
    if len(dates) < 2:
        return None
    peak = series[dates[0]]
    max_dd = 0.0
    for d in dates:
        p = series[d]
        if p > peak:
            peak = p
        dd = (p - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return round(max_dd * 100, 2)


def total_return_pct(series: dict[date, float], dividends: dict[date, float]) -> float | None:
    """ПОЛНАЯ доходность за период, % годовых: цена + дивиденды.

    Модель реинвестирования: TR = (P_end/P_start) × Π(1 + D_i/P_i), где
    D_i/P_i — дивиденд к цене на дату отсечки. Сплиты согласованы с
    нормировкой Этапа 2.2 автоматически: дивиденд и цена на одну дату — в
    одном масштабе («дореформенные» дивиденды делятся на «дореформенную»
    цену), поэтому отношение D/P инвариантно к сплиту; ценовое плечо берётся
    по склеенному ряду (normalize_splits). История <1 года — простой % за
    период, без аннуализации (как у ценовой доходности).
    """
    dates = sorted(series)
    if len(dates) < 2:
        return None
    norm = normalize_splits(series)
    p0, p1 = norm[dates[0]], norm[dates[-1]]
    years = (dates[-1] - dates[0]).days / 365.25
    if p0 <= 0 or years <= 0:
        return None

    div_factor = 1.0
    for d, amount in dividends.items():
        if d < dates[0] or d > dates[-1]:
            continue
        # цена на дату отсечки (или ближайший торговый день до неё) в ИСХОДНОМ
        # масштабе — том же, в котором объявлен дивиденд
        price_dates = [x for x in dates if x <= d]
        if not price_dates:
            continue
        p = series[price_dates[-1]]
        if p > 0 and 0 < amount / p < 1:   # защита от мусорных выплат >100% цены
            div_factor *= 1 + amount / p

    growth = (p1 / p0) * div_factor
    if years < 1.0:
        return round((growth - 1) * 100, 2)
    return round((growth ** (1 / years) - 1) * 100, 2)


def market_return_3y(db: Session, ticker: str = "MCFTR") -> float | None:
    """R_m: CAGR индекса ПОЛНОЙ доходности MCFTR за то же окно (дивиденды
    внутри индекса — согласовано с total return бумаг)."""
    series = load_index_series(db, ticker, window_start())
    dates = sorted(series)
    if len(dates) < 2:
        return None
    years = (dates[-1] - dates[0]).days / 365.25
    if years < 1.0:
        return None
    return round(((series[dates[-1]] / series[dates[0]]) ** (1 / years) - 1) * 100, 2)


def history_years_of(series: dict[date, float]) -> float | None:
    dates = sorted(series)
    if len(dates) < 2:
        return None
    return round((dates[-1] - dates[0]).days / 365.25, 2)


def compute_for_company(db: Session, company_id: int, index_returns: dict[date, float],
                        since: date, dividends: dict[date, float] | None = None) -> dict:
    """Все риск-метрики одной бумаги (Этап 2 + 2.2 + 3)."""
    series = load_price_series(db, company_id, since)
    if len(series) < 2:
        return {"volatility": None, "beta_calc": None, "return_3y": None,
                "history_years": None, "r_squared_calc": None,
                "downside_vol": None, "var_95": None, "return_total_3y": None}
    rets = log_returns(series)
    return {
        "volatility": annualized_volatility(rets),
        "beta_calc": dimson_beta(rets, index_returns),   # Диммсон −1..+1
        "return_3y": cagr_pct(series),
        "return_total_3y": total_return_pct(series, dividends or {}),
        "history_years": history_years_of(series),
        "r_squared_calc": r_squared_vs_index(rets, index_returns),
        "downside_vol": downside_volatility(rets),
        "var_95": var_95_daily(rets),
    }


def pairwise_correlation(returns_by_ticker: dict[str, dict[date, float]]) -> tuple[list[str], list[list[float | None]], int]:
    """Матрица попарных корреляций на пересечении доступных дат каждой пары.

    Возвращает (tickers, matrix, min_overlap_found). Пары с пересечением
    короче MIN_OVERLAP получают None (UI покажет прочерк)."""
    tickers = list(returns_by_ticker)
    n = len(tickers)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    min_overlap = 10 ** 9
    for a in range(n):
        matrix[a][a] = 1.0
        for b in range(a + 1, n):
            ra, rb = returns_by_ticker[tickers[a]], returns_by_ticker[tickers[b]]
            common = sorted(set(ra) & set(rb))
            min_overlap = min(min_overlap, len(common))
            if len(common) < MIN_OVERLAP:
                continue
            va = np.array([ra[d] for d in common])
            vb = np.array([rb[d] for d in common])
            if float(np.std(va)) == 0.0 or float(np.std(vb)) == 0.0:
                continue  # «замёрзшая» цена — корреляция не определена
            corr = float(np.corrcoef(va, vb)[0][1])
            if not math.isnan(corr):
                matrix[a][b] = matrix[b][a] = round(corr, 2)
    return tickers, matrix, (0 if min_overlap == 10 ** 9 else min_overlap)


def portfolio_volatility(returns_by_ticker: dict[str, dict[date, float]],
                         weights: dict[str, float]) -> float | None:
    """Волатильность портфеля через ковариационную матрицу: σ_p = √(wᵀ Σ w) × √252.

    НЕ взвешенное среднее волатильностей: ковариация учитывает корреляции,
    поэтому портфельная волатильность ниже среднего — эффект диверсификации.
    Ковариации пар — на пересечении доступных дат пары (молодые бумаги
    участвуют тем, что есть); дисперсии — на собственном ряду бумаги.
    """
    tickers = [t for t in returns_by_ticker if weights.get(t)]
    if not tickers:
        return None
    w = np.array([weights[t] for t in tickers])
    w = w / w.sum()
    n = len(tickers)
    cov = np.zeros((n, n))
    for a in range(n):
        ra = returns_by_ticker[tickers[a]]
        if len(ra) < MIN_OVERLAP:
            return None  # без дисперсии одной из бумаг портфельная σ не определена
        cov[a][a] = float(np.var(list(ra.values()), ddof=1))
        for b in range(a + 1, n):
            rb = returns_by_ticker[tickers[b]]
            common = sorted(set(ra) & set(rb))
            if len(common) >= MIN_OVERLAP:
                va = np.array([ra[d] for d in common])
                vb = np.array([rb[d] for d in common])
                cov[a][b] = cov[b][a] = float(np.cov(va, vb, ddof=1)[0][1])
            # иначе 0 — консервативно считаем пару некоррелированной
    var_p = float(w @ cov @ w)
    if var_p < 0:
        return None
    return round(math.sqrt(var_p) * math.sqrt(TRADING_DAYS) * 100, 2)


def risk_contributions(returns_by_ticker: dict[str, dict[date, float]],
                       weights: dict[str, float]) -> dict[str, float] | None:
    """Вклад каждой бумаги в ОБЩИЙ РИСК портфеля, % (сумма = 100%) — Эйлерова
    декомпозиция дисперсии: вклад_i = w_i × (Σw)_i / (wᵀΣw). Отвечает на вопрос
    «кто реально держит риск», который отличается от «доли в стоимости»
    (низкобета-бумага весит много в деньгах, но мало в риске, и наоборот)."""
    tickers = [t for t in returns_by_ticker if weights.get(t)]
    if not tickers:
        return None
    w = np.array([weights[t] for t in tickers])
    w = w / w.sum()
    n = len(tickers)
    cov = np.zeros((n, n))
    for a in range(n):
        ra = returns_by_ticker[tickers[a]]
        if len(ra) < MIN_OVERLAP:
            return None
        cov[a][a] = float(np.var(list(ra.values()), ddof=1))
        for b in range(a + 1, n):
            rb = returns_by_ticker[tickers[b]]
            common = sorted(set(ra) & set(rb))
            if len(common) >= MIN_OVERLAP:
                va = np.array([ra[d] for d in common])
                vb = np.array([rb[d] for d in common])
                cov[a][b] = cov[b][a] = float(np.cov(va, vb, ddof=1)[0][1])
    var_p = float(w @ cov @ w)
    if var_p <= 0:
        return None
    marginal = cov @ w  # (Σw)_i
    contrib = w * marginal / var_p  # доли, сумма = 1
    return {tickers[i]: round(float(contrib[i]) * 100, 1) for i in range(n)}


# ──────────────── пересчёт company_metrics (было: только ручной скрипт) ────────────────

_RECALC_UPDATE_SQL_TEXT = """
    UPDATE company_metrics
    SET beta_calc = :beta_calc,
        volatility = :volatility,
        return_3y = :return_3y,
        return_total_3y = :return_total_3y,
        history_years = :history_years,
        downside_vol = :downside_vol,
        var_95 = :var_95,
        r_squared = COALESCE(r_squared_moex, :r_squared_calc),
        earnings_yield = CASE WHEN pe_current IS NOT NULL AND pe_current > 0
                              THEN ROUND(100.0 / pe_current, 2) END,
        beta = COALESCE(beta_moex, :beta_calc),
        beta_source = CASE WHEN beta_moex IS NOT NULL THEN 'moex'
                           WHEN :beta_calc IS NOT NULL THEN 'calc' END,
        updated_at = :updated_at
    WHERE ticker = :ticker
"""


def recalc_all_company_metrics() -> dict:
    """Пересчитывает company_metrics (бета/волатильность/доходность/Шарп/
    Сортино/CAPM/альфа) для ВСЕХ компаний из СВЕЖЕЙ истории quotes/index_history.

    Раньше это была ТОЛЬКО ручная операция (scripts/recalc_risk_metrics.py,
    "cron позже" по докстрингу) — на практике никто не гонял её регулярно,
    поэтому company_metrics годами показывала снапшот на момент последнего
    ручного запуска: бэкфилл истории (напр. YDEX←YNDX) обновляет quotes, но
    БЕЗ этого пересчёта history_years/beta/return_3y в UI не меняются, даже
    когда рынок ощутимо двигается. Теперь вызывается из ежедневного джоба
    (main.py _history_job) ПОСЛЕ обновления истории котировок — та же логика,
    что раньше жила только в scripts/recalc_risk_metrics.py.
    """
    from datetime import datetime, timezone
    from sqlalchemy import text as _text
    from app.db.session import SessionLocal
    from app.models.company import Company

    db = SessionLocal()
    try:
        try:
            from app.services.moex_coefficients import sync_official_betas
            sync_official_betas()
        except Exception as e:  # noqa: BLE001
            logger.warning("Официальные беты MOEX: пропуск (%s)", e)

        since = window_start()
        index_series = load_index_series(db, "IMOEX", since)
        if len(index_series) < 100:
            logger.warning("Пересчёт risk-метрик: в index_history мало данных IMOEX (%d) — пропуск", len(index_series))
            return {"skipped": True}
        index_returns = log_returns(index_series)

        companies = db.query(Company).order_by(Company.ticker).all()
        now = datetime.now(timezone.utc)
        update_sql = _text(_RECALC_UPDATE_SQL_TEXT)

        # try/except НА КАЖДУЮ компанию — раньше одна ошибка (плохие данные
        # дивидендов/котировок у одного тикера) роняла ВЕСЬ пересчёт ДО
        # db.commit() (он был один в конце цикла), и company_metrics ВСЕХ
        # компаний оставалась на снапшоте предыдущего успешного прогона —
        # поймал на живом проде: RAGR несколько деплоев подряд не обновлялся,
        # хотя T/HEAD/X5 из того же коммита обновились (значит цикл падал
        # НА КАКОЙ-ТО компании раньше финального commit, и RAGR — с ней или
        # позже — просто не успевал дойти до записи).
        from app.services.moex_dividends import load_dividends_map
        failed = []
        for c in companies:
            try:
                divs = load_dividends_map(db, c.ticker)
                m = compute_for_company(db, c.id, index_returns, since, dividends=divs)
                db.execute(update_sql, {"ticker": c.ticker, "updated_at": now, **m})
            except Exception as e:  # noqa: BLE001
                failed.append(c.ticker)
                logger.warning("Пересчёт company_metrics: %s пропущен (%s)", c.ticker, e)
        db.commit()
        if failed:
            logger.warning("Пересчёт company_metrics: %d тикеров пропущено: %s", len(failed), ", ".join(failed))

        # Rf/Rm → альфа/Сортино/CAPM (те же формулы, что и раньше в скрипте)
        from app.services.moex_dividends import update_risk_free_rate
        rf = update_risk_free_rate(db)
        rm = market_return_3y(db, "MCFTR")
        if rf is not None and rm is not None:
            db.execute(_text("""
                INSERT INTO market_params (key, value, as_of, note, updated_at)
                VALUES ('market_return_3y', :rm, CURRENT_DATE,
                        'CAGR MCFTR (полная доходность) за окно 3 года', :now)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,
                    as_of=EXCLUDED.as_of, updated_at=EXCLUDED.updated_at
            """), {"rm": rm, "now": now})
            db.execute(_text("""
                UPDATE company_metrics SET
                    capm_expected = ROUND((:rf + beta * (:rm - :rf))::numeric, 2),
                    alpha_3y = CASE WHEN return_total_3y IS NOT NULL AND beta IS NOT NULL
                        THEN ROUND((return_total_3y - (:rf + beta * (:rm - :rf)))::numeric, 2) END,
                    sortino_3y = CASE WHEN return_total_3y IS NOT NULL
                                       AND downside_vol IS NOT NULL AND downside_vol > 0
                        THEN ROUND(((return_total_3y - :rf) / downside_vol)::numeric, 2) END
                WHERE beta IS NOT NULL
            """), {"rf": rf, "rm": rm})
            db.commit()
        logger.info("Пересчёт company_metrics: %d компаний, Rf=%s Rm=%s", len(companies), rf, rm)
        return {"companies": len(companies), "rf": rf, "rm": rm, "failed": failed}
    finally:
        db.close()
