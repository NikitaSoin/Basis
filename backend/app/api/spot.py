"""Эндпоинты класса активов «Валюта и металлы» (спот MOEX).

Список (вкладка в модуле «Рынок») и карточка под главный вопрос: «что дальше с
курсом/ценой и какова роль в портфеле» (валюта → макро/ДКП; металл → защитный
актив), НЕ «справедливая цена». Текстовая аналитика — из файлов backend/spot/.
"""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter()
SPOT_DIR = Path(__file__).parent.parent.parent / "spot"

KIND_LABEL = {"currency": "Валюта", "metal": "Драгметалл"}


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_")


def _row_to_dict(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if hasattr(v, "real") and not isinstance(v, (int, float, bool)):
            d[k] = float(v)
    d["kind_label"] = KIND_LABEL.get(d.get("kind"))
    return d


@router.get("/spot")
def list_spot(db: Session = Depends(get_db)):
    """Список спот-инструментов (валюты + металлы)."""
    q = "SELECT * FROM spot_assets ORDER BY kind, secid"
    return [_row_to_dict(r) for r in db.execute(text(q))]


@router.get("/spot/{secid}")
def get_spot(secid: str, db: Session = Depends(get_db)):
    """Карточка спот-инструмента: цена/динамика + что дальше + роль в портфеле."""
    row = db.execute(text("SELECT * FROM spot_assets WHERE secid = :s"), {"s": _safe(secid)}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Spot asset not found")
    return {"asset": _row_to_dict(row)}


@router.get("/spot/{secid}/summary", response_class=PlainTextResponse)
def get_spot_summary(secid: str):
    path = SPOT_DIR / _safe(secid) / "analysis_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.get("/spot/{secid}/analysis")
def get_spot_analysis(secid: str):
    path = SPOT_DIR / _safe(secid) / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")
    return json.loads(path.read_text(encoding="utf-8"))
