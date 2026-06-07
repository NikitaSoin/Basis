"""Эндпоинты класса активов «Облигации».

Список (модуль «Рынок», вкладка Облигации), карточка облигации с расчётными
блоками под главный вопрос инвестора: надёжность → доходность/спред → дюрация →
денежный поток. Текстовая аналитика (bond-analyst) — из файлов backend/bonds/.
"""
import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()
BONDS_DIR = Path(__file__).parent.parent.parent / "bonds"

RISK_LABEL = {
    "gov": "Госдолг",
    "high": "Надёжный",
    "medium": "Средний риск",
    "speculative": "Высокий риск (ВДО)",
}


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_").upper()


def _row_to_dict(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if isinstance(v, date):
            d[k] = v.isoformat()
        elif hasattr(v, "real") and not isinstance(v, (int, float, bool)):
            d[k] = float(v)
    d["risk_label"] = RISK_LABEL.get(d.get("risk_tier"))
    if d.get("duration_days"):
        d["duration_years"] = round(d["duration_days"] / 365, 1)
    # экстремальная доходность — флаг дистресса/неликвида (не «выгодно»!)
    d["yield_anomaly"] = bool(d.get("ytm") and d["ytm"] > 40)
    return d


@router.get("/bonds")
def list_bonds(
    bond_type: str | None = Query(None, description="ofz | corporate"),
    db: Session = Depends(get_db),
):
    """Список облигаций для раздела «Рынок» (по образцу списка акций)."""
    q = "SELECT * FROM bonds"
    params = {}
    if bond_type:
        q += " WHERE bond_type = :t"
        params["t"] = bond_type
    q += " ORDER BY bond_type, risk_tier, ytm DESC NULLS LAST"
    return [_row_to_dict(r) for r in db.execute(text(q), params)]


@router.get("/bonds/{secid}")
def get_bond(secid: str, db: Session = Depends(get_db)):
    """Карточка облигации: параметры + расчётные блоки (сценарии переоценки от
    дюрации, спред к ОФЗ) + денежный поток с MOEX."""
    row = db.execute(text("SELECT * FROM bonds WHERE secid = :s"), {"s": _safe(secid)}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Bond not found")
    bond = _row_to_dict(row)

    # Блок «Чувствительность к ставке»: сценарии переоценки тела от модиф.
    # дюрации. ΔЦена ≈ −modDur × Δставки. modDur ≈ дюрация/(1+YTM). Это ОЦЕНКА
    # (линейное приближение, без выпуклости) — помечаем уровень достоверности.
    sensitivity = None
    dy, ytm = bond.get("duration_years"), bond.get("ytm")
    if dy and ytm is not None:
        mod_dur = dy / (1 + ytm / 100)
        sensitivity = {
            "modified_duration": round(mod_dur, 2),
            "certainty": "оценка",
            "scenarios": [
                {"rate_change_pp": d, "price_change_pct": round(-mod_dur * d, 2)}
                for d in (-2, -1, 1, 2)
            ],
        }

    # Блок «Денежный поток»: купоны/амортизация/оферты с MOEX (факт эмиссии)
    cashflow = None
    try:
        from app.services.moex_bonds import fetch_cashflow
        cf = fetch_cashflow(bond["secid"])
        today = date.today().isoformat()
        coupons = [{"date": c.get("coupondate"), "value": c.get("value")}
                   for c in cf.get("coupons", []) if c.get("coupondate")]
        bond["has_amortization"] = len(cf.get("amortizations", [])) > 1
        cashflow = {
            "coupons_upcoming": [c for c in coupons if c["date"] and c["date"] >= today][:8],
            "coupons_total": len(coupons),
            "amortizations": [{"date": a.get("amortdate"), "value": a.get("value")}
                              for a in cf.get("amortizations", [])],
            "offers": [{"date": o.get("offerdate")} for o in cf.get("offers", []) if o.get("offerdate")],
            "certainty": "факт",
        }
    except Exception:
        pass

    return {"bond": bond, "sensitivity": sensitivity, "cashflow": cashflow}


@router.get("/bonds/{secid}/summary", response_class=PlainTextResponse)
def get_bond_summary(secid: str):
    """Текстовая аналитика облигации (bond-analyst, markdown)."""
    path = BONDS_DIR / _safe(secid) / "analysis_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.get("/bonds/{secid}/analysis")
def get_bond_analysis(secid: str):
    """Структурированная аналитика облигации (bond-analyst, JSON)."""
    path = BONDS_DIR / _safe(secid) / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")
    return json.loads(path.read_text(encoding="utf-8"))
