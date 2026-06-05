"""Синхронизация company_metrics из файлов аналитики (Этап 1 аналитики портфеля).

Один источник правды: файлы companies/<TICKER>/financials.json (+ история
дивидендов из governance.json как фолбэк) → числа в таблицу company_metrics.
Ничего НЕ считает заново и НЕ выдумывает: чего нет в файлах — NULL
(0 исказил бы средневзвешенные по портфелю).

Откуда берутся поля:
  pe_current    — multiples.current.pe
  pe_historical — multiples.historical_avg.pe_5y_median (или pe_5y_avg)
  div_yield     — multiples.current.{dividend_yield_pct|div_yield|dividend_yield};
                  фолбэк: governance.json → dividends.history[последний год].yield_pct
  fair_value    — valuation.fair_value_range.base
  sector        — таблица companies (тот же сектор, что на сайте)
  beta/volatility — НЕ заполняются (Этап 2, история котировок)

Идемпотентно: ON CONFLICT (ticker) DO UPDATE. Запуск вручную (как import_data):
  cd backend && python -m scripts.sync_company_metrics
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from app.db.session import SessionLocal
from app.models.company import Company

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent / "companies"

_UPSERT_SQL = text("""
    INSERT INTO company_metrics (ticker, sector, pe_current, pe_historical,
                                 div_yield, fair_value, updated_at)
    VALUES (:ticker, :sector, :pe_current, :pe_historical,
            :div_yield, :fair_value, :updated_at)
    ON CONFLICT (ticker) DO UPDATE SET
        sector        = EXCLUDED.sector,
        pe_current    = EXCLUDED.pe_current,
        pe_historical = EXCLUDED.pe_historical,
        div_yield     = EXCLUDED.div_yield,
        fair_value    = EXCLUDED.fair_value,
        updated_at    = EXCLUDED.updated_at
""")
# beta/volatility намеренно не трогаем: их заполнит Этап 2, синк их не затирает.


def _num(v) -> float | None:
    """Число или NULL — никаких нулей-заглушек."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("%s: не парсится (%s)", path, e)
        return None


def extract_metrics(ticker: str) -> dict:
    """Достаёт числа из файлов компании. Чего нет — None."""
    fin = _load_json(COMPANIES_DIR / ticker / "financials.json") or {}
    multiples = fin.get("multiples") or {}
    current = multiples.get("current") or {}
    hist = multiples.get("historical_avg") or {}

    pe_current = _num(current.get("pe"))
    pe_historical = _num(hist.get("pe_5y_median"))
    if pe_historical is None:
        pe_historical = _num(hist.get("pe_5y_avg"))

    # Дивдоходность: сначала скаляры financials, затем история из governance
    div_yield = None
    for key in ("dividend_yield_pct", "div_yield", "dividend_yield"):
        div_yield = _num(current.get(key))
        if div_yield is not None:
            break
    if div_yield is None:
        gov = _load_json(COMPANIES_DIR / ticker / "governance.json") or {}
        history = (gov.get("dividends") or {}).get("history") or []
        dated = [
            (r.get("year"), _num(r.get("yield_pct")))
            for r in history
            if isinstance(r, dict) and _num(r.get("yield_pct")) is not None
        ]
        if dated:
            div_yield = max(dated, key=lambda x: x[0] or 0)[1]

    fair_value = _num(((fin.get("valuation") or {}).get("fair_value_range") or {}).get("base"))

    return {
        "pe_current": pe_current,
        "pe_historical": pe_historical,
        "div_yield": div_yield,
        "fair_value": fair_value,
    }


def main() -> None:
    db = SessionLocal()
    try:
        companies = db.query(Company).order_by(Company.ticker).all()
        logger.info("Синхронизация метрик: %d компаний", len(companies))

        missing = {"pe_current": [], "pe_historical": [], "div_yield": [], "fair_value": []}
        now = datetime.now(timezone.utc)

        for c in companies:
            m = extract_metrics(c.ticker)
            for field, tickers in missing.items():
                if m[field] is None:
                    tickers.append(c.ticker)
            db.execute(_UPSERT_SQL, {
                "ticker": c.ticker,
                "sector": c.sector,
                "updated_at": now,
                **m,
            })
        db.commit()

        total = len(companies)
        logger.info("─" * 60)
        logger.info("Готово: %d строк в company_metrics", total)
        for field, tickers in missing.items():
            logger.info("  %-14s заполнено %3d / %d  (пропусков %d%s)",
                        field, total - len(tickers), total, len(tickers),
                        ": " + ", ".join(tickers[:10]) + ("…" if len(tickers) > 10 else "")
                        if tickers else "")
    finally:
        db.close()


if __name__ == "__main__":
    main()
