"""Пересчёт риск-метрик в company_metrics из истории котировок (Этап 2).

Наполняет beta / volatility / return_3y / history_years для всех компаний:
  - волатильность: СКО дневных лог-доходностей за 3 года × √252, годовая %
  - бета: против IMOEX (index_history), на пересечении торговых дат
  - return_3y: CAGR по цене за период (факт прошлого, не прогноз)
  - history_years: фактическая глубина истории (для пометки «*» при <1 года)

Идемпотентно (UPDATE по тикеру). Запуск вручную в консоли (как остальные):
  cd backend && python -m scripts.recalc_risk_metrics
Метрики устаревают по мере набегания истории — пересчитывать периодически
(можно завести в cron позже; пока ручной запуск).
"""
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.company import Company
from app.services.risk_metrics import (
    compute_for_company, load_index_series, log_returns, window_start,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_UPDATE_SQL = text("""
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
""")


def main() -> None:
    # 1) Официальные беты MOEX (приоритетный источник; при недоступности
    #    URL и локального файла — работаем на своём расчёте)
    try:
        from app.services.moex_coefficients import sync_official_betas
        res = sync_official_betas()
        logger.info("Официальные беты MOEX: %s, файл %s, обновлено %d",
                    res["source"] or "недоступны", res["date"], res["updated"])
    except Exception as e:
        logger.warning("Официальные беты MOEX: пропуск (%s)", e)

    db = SessionLocal()
    try:
        since = window_start()
        index_series = load_index_series(db, "IMOEX", since)
        if len(index_series) < 100:
            logger.error("IMOEX: в index_history мало данных (%d строк) — сначала "
                         "запусти scripts.load_quote_history --indices", len(index_series))
            sys.exit(1)
        index_returns = log_returns(index_series)
        logger.info("IMOEX: %d торговых дней с %s", len(index_returns), since)

        companies = db.query(Company).order_by(Company.ticker).all()
        now = datetime.now(timezone.utc)
        filled = {"volatility": 0, "beta_calc": 0, "return_3y": 0, "downside_vol": 0, "var_95": 0}
        short_history, empty = [], []

        from app.services.moex_dividends import load_dividends_map
        for c in companies:
            divs = load_dividends_map(db, c.ticker)
            m = compute_for_company(db, c.id, index_returns, since, dividends=divs)
            db.execute(_UPDATE_SQL, {"ticker": c.ticker, "updated_at": now, **m})
            for k in filled:
                if m[k] is not None:
                    filled[k] += 1
            if m["history_years"] is None:
                empty.append(c.ticker)
            elif m["history_years"] < 1:
                short_history.append(c.ticker)
        db.commit()

        total = len(companies)
        logger.info("─" * 60)
        logger.info("Готово: %d компаний", total)
        for k, v in filled.items():
            logger.info("  %-12s заполнено %3d / %d", k, v, total)
        logger.info("  история <1 года (в UI «*»): %d — %s", len(short_history), ", ".join(short_history) or "—")
        logger.info("  без истории (NULL): %d — %s", len(empty), ", ".join(empty) or "—")

        # 3) Этап 3: безрисковая ставка, доходность рынка → альфа/Сортино/CAPM.
        #    Все члены годовые, %. Бета — показываемая (moex || calc).
        from app.services.moex_dividends import update_risk_free_rate
        from app.services.risk_metrics import market_return_3y
        rf = update_risk_free_rate(db)
        rm = market_return_3y(db, "MCFTR")
        if rf is not None and rm is not None:
            db.execute(text("""
                INSERT INTO market_params (key, value, as_of, note, updated_at)
                VALUES ('market_return_3y', :rm, CURRENT_DATE,
                        'CAGR MCFTR (полная доходность) за окно 3 года', :now)
                ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value,
                    as_of=EXCLUDED.as_of, updated_at=EXCLUDED.updated_at
            """), {"rm": rm, "now": now})
            db.execute(text("""
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
            logger.info("Коэффициенты Этапа 3: Rf=%.2f%% (ОФЗ-1г), Rm=%.2f%% (MCFTR 3г), премия=%.2f%%",
                        rf, rm, rm - rf)
        else:
            logger.warning("Альфа/Сортино/CAPM пропущены: Rf=%s, Rm=%s", rf, rm)

        # 4) Контроль качества фолбэка: расхождение beta_calc vs beta_moex
        rows = db.execute(text("""
            SELECT ticker, beta_calc, beta_moex,
                   ABS(beta_calc - beta_moex) AS gap
            FROM company_metrics
            WHERE beta_calc IS NOT NULL AND beta_moex IS NOT NULL
            ORDER BY gap DESC
        """)).all()
        if rows:
            gaps = [float(r.gap) for r in rows]
            logger.info("  сверка с MOEX: %d бумаг, средний |разрыв| %.3f, медианный %.3f",
                        len(rows), sum(gaps) / len(gaps), sorted(gaps)[len(gaps) // 2])
            logger.info("  топ-10 расхождений (сигнал качества нашего расчёта):")
            for r in rows[:10]:
                logger.info("    %-6s calc=%.3f moex=%.3f Δ=%.3f",
                            r.ticker, float(r.beta_calc), float(r.beta_moex), float(r.gap))
        src = db.execute(text(
            "SELECT beta_source, count(*) FROM company_metrics WHERE beta IS NOT NULL GROUP BY beta_source"
        )).all()
        logger.info("  источник показываемой беты: %s",
                    ", ".join(f"{s or '—'}: {n}" for s, n in src))
    finally:
        db.close()


if __name__ == "__main__":
    main()
