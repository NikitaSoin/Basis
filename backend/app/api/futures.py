"""Эндпоинты класса активов «Фьючерсы» (срочный рынок FORTS).

Список (модуль «Рынок», вкладка Фьючерсы) и карточка контракта под главный
вопрос: на что ставка → плечо/риск → стоимость удержания (срочная структура) →
связь с базовым активом. БЕЗ сигналов/таргетов (см. docs/futures-methodology.md).
Текстовая аналитика (futures-analyst) — из файлов backend/futures/.
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
FUTURES_DIR = Path(__file__).parent.parent.parent / "futures"

KIND_LABEL = {
    "currency": "Валюта",
    "index": "Индекс",
    "commodity": "Сырьё",
    "stock": "На акцию",
    "rate": "Ставка",
    "other": "Другие",
}


def _safe(s: str) -> str:
    # FORTS-тикеры регистрозависимы (Si, Eu, CNY…) — НЕ приводим к upper,
    # только отсекаем небезопасные символы
    return "".join(c for c in s if c.isalnum() or c in "-_")


def _row_to_dict(r) -> dict:
    d = dict(r._mapping)
    for k, v in d.items():
        if isinstance(v, date):
            d[k] = v.isoformat()
        elif hasattr(v, "real") and not isinstance(v, (int, float, bool)):
            d[k] = float(v)
    d["kind_label"] = KIND_LABEL.get(d.get("asset_kind"))
    if d.get("expiration_date"):
        d["days_to_expiry"] = (date.fromisoformat(d["expiration_date"]) - date.today()).days
    return d


@router.get("/futures")
def list_futures(
    asset_kind: str | None = Query(None, description="currency|index|commodity|stock|rate|other"),
    db: Session = Depends(get_db),
):
    """Список контрактов для раздела «Рынок» (сгруппирован по типу базового актива)."""
    q = "SELECT * FROM futures"
    params = {}
    if asset_kind:
        q += " WHERE asset_kind = :k"
        params["k"] = asset_kind
    # по ликвидности (открытые позиции) внутри — чтобы ближние/живые были вверху
    q += " ORDER BY asset_kind, open_position DESC NULLS LAST"
    return [_row_to_dict(r) for r in db.execute(text(q), params)]


@router.get("/futures/{secid}")
def get_future(secid: str, db: Session = Depends(get_db)):
    """Карточка контракта: параметры + плечо/риск + срочная структура
    (контанго/бэквордация по сериям) + чувствительность к плечу + связь с БА."""
    row = db.execute(text("SELECT * FROM futures WHERE secid = :s"), {"s": _safe(secid)}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Future not found")
    fut = _row_to_dict(row)

    # Срочная структура: все серии того же базового актива по экспирации.
    # дальняя дороже ближней → контанго; дешевле → бэквордация. Чистый факт MOEX
    # (без внешнего спота). Это КОНТЕКСТ ожиданий, не сигнал.
    series_rows = db.execute(text(
        "SELECT secid, short_name, expiration_date, settle_price, open_position "
        "FROM futures WHERE asset_code = :a AND settle_price IS NOT NULL "
        "ORDER BY expiration_date NULLS LAST"
    ), {"a": fut["asset_code"]}).all()
    series = [_row_to_dict(r) for r in series_rows]
    term_structure = None
    if len(series) >= 2:
        # форму carry смотрим по БЛИЖНИЙ vs СЛЕДУЮЩИЙ контракт (актуальная
        # стоимость переноса), аннуализируем по дням между экспирациями
        near, nxt = series[0], series[1]
        if near.get("settle_price") and nxt.get("settle_price"):
            diff_pct = (nxt["settle_price"] / near["settle_price"] - 1) * 100
            shape = "contango" if diff_pct > 0.3 else "backwardation" if diff_pct < -0.3 else "flat"
            ann = None
            dn, df = near.get("days_to_expiry"), nxt.get("days_to_expiry")
            if dn is not None and df is not None and df > dn:
                ann = round(diff_pct * 365 / (df - dn), 1)
            term_structure = {
                "shape": shape,
                "near": {"short_name": near["short_name"], "expiration_date": near.get("expiration_date"), "settle": near["settle_price"]},
                "next": {"short_name": nxt["short_name"], "expiration_date": nxt.get("expiration_date"), "settle": nxt["settle_price"]},
                "diff_pct": round(diff_pct, 2),
                "annualized_pct": ann,   # «годовая стоимость удержания», оценка
                "series": [{"short_name": s["short_name"], "expiration_date": s.get("expiration_date"),
                            "settle": s.get("settle_price"), "days_to_expiry": s.get("days_to_expiry")} for s in series],
                "certainty": "факт (форма) / оценка (годовая)",
            }

    # Чувствительность к плечу (в НЕГАТИВНОЙ рамке как риск): движение БА против
    # позиции на X% → −плечо×X% от ГО. Это информирование о риске, не прогноз.
    sensitivity = None
    lev = fut.get("leverage")
    if lev:
        sensitivity = {
            "leverage": lev,
            "certainty": "оценка",
            "scenarios": [
                {"asset_move_pct": m, "margin_change_pct": round(-lev * m, 1)}
                for m in (1, 3, 5)
            ],
        }

    # Связь с базовым активом: для фьючерса на акцию — переход в карточку компании.
    linked = None
    if fut.get("linked_ticker"):
        comp = db.execute(text("SELECT ticker, name FROM companies WHERE ticker = :t"),
                          {"t": fut["linked_ticker"]}).first()
        if comp:
            linked = {"ticker": comp[0], "name": comp[1]}

    return {"future": fut, "term_structure": term_structure, "sensitivity": sensitivity, "linked_company": linked}


@router.get("/futures/{secid}/summary", response_class=PlainTextResponse)
def get_future_summary(secid: str):
    """Текстовая аналитика контракта (futures-analyst, markdown)."""
    path = FUTURES_DIR / _safe(secid) / "analysis_summary.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Summary not found")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")


@router.get("/futures/{secid}/analysis")
def get_future_analysis(secid: str):
    """Структурированная аналитика контракта (futures-analyst, JSON)."""
    path = FUTURES_DIR / _safe(secid) / "analysis.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Analysis not found")
    return json.loads(path.read_text(encoding="utf-8"))
