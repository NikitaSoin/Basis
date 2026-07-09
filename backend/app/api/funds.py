"""Эндпоинты класса активов «Биржевые фонды» (БПИФ/ETF).

Список (модуль «Рынок», вкладка Фонды) и карточка фонда под главный вопрос:
что внутри → сколько стоит (TER) → честно ли следует → нужен ли поверх портфеля.
БЕЗ «купить/продать». Текстовая аналитика (fund-analyst) — из файлов backend/funds/.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()
FUNDS_DIR = Path(__file__).parent.parent.parent / "funds"

TYPE_LABEL = {
    "equity": "Акции",
    "bonds": "Облигации",
    "gold": "Золото",
    "money_market": "Денежный рынок",
    "currency": "Валютный",
    "mixed": "Смешанный",
}


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_").upper()


def _row_to_dict(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if hasattr(v, "real") and not isinstance(v, (int, float, bool)):
            d[k] = float(v)
    d["type_label"] = TYPE_LABEL.get(d.get("fund_type"))
    return d


def _ter_in_money(ter: float | None) -> dict | None:
    """Проекция TER в накопленные потери доходности на горизонте (на 100 000 ₽,
    без учёта роста — иллюстрация «тихого врага»). ОЦЕНКА."""
    if ter is None:
        return None
    base = 100_000
    out = {}
    for years in (1, 5, 10):
        # накопленная доля расходов ≈ 1 - (1 - ter/100)^years
        frac = 1 - (1 - ter / 100) ** years
        out[str(years)] = round(base * frac)
    return out


@router.get("/funds")
def list_funds(
    fund_type: str | None = Query(None),
    search: str | None = Query(None, description="поиск по SECID/названию (добавление в портфель)"),
    db: Session = Depends(get_db),
):
    """Список фондов для раздела «Рынок» (группировка по типу)."""
    q = "SELECT * FROM funds"
    where = []
    params = {}
    if fund_type:
        where.append("fund_type = :t")
        params["t"] = fund_type
    if search:
        where.append("(secid ILIKE :s OR short_name ILIKE :s)")
        params["s"] = f"%{search}%"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY fund_type, val_today DESC NULLS LAST"
    if search:
        q += " LIMIT 8"
    return [_row_to_dict(r) for r in db.execute(text(q), params)]


@router.get("/funds/{secid}")
def get_fund(secid: str, db: Session = Depends(get_db)):
    """Карточка фонда: паспорт (что внутри) + TER (в % и в деньгах) + ликвидность."""
    row = db.execute(text("SELECT * FROM funds WHERE secid = :s"), {"s": _safe(secid)}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Fund not found")
    fund = _row_to_dict(row)
    return {"fund": fund, "ter_cost": _ter_in_money(fund.get("ter"))}


@router.get("/funds/{secid}/summary", response_class=PlainTextResponse)
def get_fund_summary(secid: str):
    """Текстовая аналитика фонда (fund-analyst, markdown)."""
    path = FUNDS_DIR / _safe(secid) / "analysis_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.get("/funds/{secid}/analysis")
def get_fund_analysis(secid: str):
    """Структурированная аналитика фонда (fund-analyst, JSON)."""
    path = FUNDS_DIR / _safe(secid) / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")
    return json.loads(path.read_text(encoding="utf-8"))
