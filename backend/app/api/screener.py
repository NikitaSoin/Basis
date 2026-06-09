"""Скрининг акций — сортировка/фильтрация по готовым метрикам (company_metrics).

Опирается на уже посчитанное: P/E, дивдоходность, справедливая цена, бета,
волатильность, доходность 3г, Sortino, VaR, earnings yield + последняя цена из
quotes (для апсайда к справедливой цене). Без «купить/продать» — инструмент
фильтрации, выводы делает пользователь.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()

_Q = text("""
    WITH latest AS (
        SELECT DISTINCT ON (company_id) company_id, close
        FROM quotes ORDER BY company_id, date DESC
    )
    SELECT c.ticker, c.name, c.sector,
           m.pe_current, m.div_yield, m.fair_value, m.beta, m.volatility,
           m.return_total_3y, m.sortino_3y, m.earnings_yield, m.var_95, m.alpha_3y,
           l.close AS price
    FROM companies c
    JOIN company_metrics m ON m.ticker = c.ticker
    LEFT JOIN latest l ON l.company_id = c.id
    ORDER BY c.ticker
""")


@router.get("/screener/stocks")
def screener_stocks(db: Session = Depends(get_db)):
    """Все акции с метриками + текущей ценой + апсайдом к справедливой цене.
    Фильтрация/сортировка — на фронте (данные готовые, отдаём целиком)."""
    out = []
    for r in db.execute(_Q):
        d = dict(r._mapping)
        for k, v in d.items():
            if hasattr(v, "real") and not isinstance(v, (int, float, bool)) and v is not None:
                d[k] = float(v)
        # апсайд к справедливой цене (оценка): fair_value / price − 1
        fv, px = d.get("fair_value"), d.get("price")
        d["upside_pct"] = round((fv / px - 1) * 100, 1) if fv and px else None
        out.append(d)
    return out
