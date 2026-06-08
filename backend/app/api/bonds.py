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
COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"


def _last(seq):
    """Последнее не-None значение временного ряда (актуальный год)."""
    if not isinstance(seq, list):
        return None
    for v in reversed(seq):
        if v is not None:
            return v
    return None


def _issuer_debt_block(ticker: str) -> dict | None:
    """Долговая нагрузка эмитента из его financials.json: «сможет ли расплатиться».
    Только для публичных эмитентов, что есть в нашей базе. None — если нет файла."""
    fpath = COMPANIES_DIR / ticker / "financials.json"
    if not fpath.exists():
        return None
    try:
        fin = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception:
        return None
    bs = fin.get("balance_sheet", {}) or {}
    ratios = bs.get("ratios", {}) or {}
    inc = fin.get("income_statement", {}) or {}
    years = (fin.get("meta", {}) or {}).get("fiscal_years") or []
    as_of_year = years[-1] if years else None
    nd_ebitda = _last(ratios.get("net_debt_ebitda"))
    d_to_e = _last(ratios.get("debt_to_equity"))
    cur = _last(ratios.get("current_ratio"))
    ebitda = _last(inc.get("ebitda"))
    fin_costs = _last(inc.get("finance_costs"))
    coverage = None
    if ebitda is not None and fin_costs:
        try:
            coverage = round(abs(ebitda) / abs(fin_costs), 1)
        except (ZeroDivisionError, TypeError):
            coverage = None

    # вердикт «сможет ли расплатиться» — по долгу/EBITDA и покрытию процентов.
    # Это ОЦЕНКА от данных эмитента, не рейтинг. Банки (нет nd/ebitda) — отдельно.
    flag, verdict = "amber", None
    if nd_ebitda is not None:
        if nd_ebitda <= 2:
            flag = "green"; verdict = f"Долг/EBITDA {nd_ebitda} — низкая нагрузка, обслуживать долг комфортно."
        elif nd_ebitda <= 4:
            flag = "amber"; verdict = f"Долг/EBITDA {nd_ebitda} — умеренная нагрузка, в пределах нормы."
        elif nd_ebitda <= 6:
            flag = "amber"; verdict = f"Долг/EBITDA {nd_ebitda} — повышенная нагрузка, чувствительна к ставке и выручке."
        else:
            flag = "red"; verdict = f"Долг/EBITDA {nd_ebitda} — высокая нагрузка, риск с обслуживанием долга."
        if coverage is not None and coverage < 2:
            flag = "red"; verdict += f" Покрытие процентов EBITDA лишь {coverage}× — мало."
    elif coverage is not None:
        verdict = f"Покрытие процентов EBITDA {coverage}×."
        flag = "green" if coverage >= 4 else "amber" if coverage >= 2 else "red"

    return {
        "ticker": ticker,
        "net_debt_ebitda": nd_ebitda,
        "interest_coverage": coverage,
        "debt_to_equity": d_to_e,
        "current_ratio": cur,
        "as_of_year": as_of_year,
        "flag": flag,
        "verdict": verdict,
        "certainty": "оценка",
    }

RISK_LABEL = {
    "gov": "Госдолг",
    "high": "Надёжный",
    "medium": "Средний риск",
    "speculative": "Высокий риск (ВДО)",
}

COUPON_LABEL = {
    "fixed": "Фикс. купон",
    "floater": "Флоатер (плавающий)",
    "linker": "Линкер (инфляция)",
    "structured": "Структурная (выплата по формуле)",
    "other": "—",
}

# буква рейтинга → грубый тир для сверки с рыночной оценкой по спреду
def _rating_tier(rating: str | None) -> str | None:
    if not rating:
        return None
    base = rating.rstrip("+-").upper()
    if base in ("AAA", "AA"):
        return "high"
    if base in ("A", "BBB"):
        return "medium"
    return "speculative"  # BB и ниже — спекулятивный (ВДО)


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
    d["coupon_label"] = COUPON_LABEL.get(d.get("coupon_type"))
    if d.get("duration_days"):
        d["duration_years"] = round(d["duration_days"] / 365, 1)
    # экстремальная доходность — флаг дистресса/неликвида (не «выгодно»!)
    d["yield_anomaly"] = bool(d.get("ytm") and d["ytm"] > 40)

    # ── двойной рейтинг: рынок (спред) vs агентство — и их расхождение ──
    market_tier = d.get("risk_tier")
    agency_tier = _rating_tier(d.get("agency_rating"))
    d["agency_tier"] = agency_tier
    divergence = None
    # расхождение считаем только когда есть РЕАЛЬНАЯ рыночная оценка (спред)
    if d.get("spread_bp") is not None and market_tier in ("high", "medium", "speculative") and agency_tier:
        order = {"high": 3, "medium": 2, "speculative": 1}
        diff = order[market_tier] - order[agency_tier]
        if diff <= -1:
            # рынок оценивает НИЖЕ агентства (требует больший спред) — настороже
            divergence = "market_stricter"
        elif diff >= 1:
            divergence = "market_milder"
        else:
            divergence = "aligned"
    d["rating_divergence"] = divergence
    d["risk_verdict"] = _risk_verdict(d)
    return d


def _risk_verdict(d: dict) -> str | None:
    """Системный вердикт «оплачен ли риск» по каждой бумаге (3 уровня, без
    «купить/продать»). Применим ко всем, включая ВДО без публичного эмитента."""
    if d.get("bond_type") == "ofz":
        return "Госдолг РФ — кредитный риск минимальный; основной риск тут процентный (дюрация)."
    if d.get("is_defaulted"):
        return "Дефолт / режим Д — возврат тела под вопросом; доходность нерелевантна."
    tier, spread, ytm = d.get("risk_tier"), d.get("spread_bp"), d.get("ytm")
    if d.get("yield_anomaly"):
        return "Экстремальная доходность — почти всегда дистресс/неликвид, а не «выгода»; вероятны потери тела."
    if tier == "speculative":
        s = f" (спред +{spread} б.п.)" if spread is not None else ""
        return f"ВДО{s}: высокая доходность — это плата за реальный риск дефолта, а не «подарок». Сначала вопрос «вернут ли тело»."
    if tier == "high":
        return "Надёжный корпорат: небольшой спред за чуть большую доходность, чем у ОФЗ."
    if tier == "medium":
        return "Средний риск: доходность выше ОФЗ как премия за умеренный кредитный риск эмитента."
    if spread is None and d.get("bond_type") != "ofz":
        return "Нет рыночной оценки (неликвид / нет YTM) — оценить «риск за доходность» по рынку нельзя."
    return None


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

    # Блок «Эмитент»: долговая нагрузка компании-эмитента (сможет ли расплатиться)
    # + переход в её карточку. Только для публичных эмитентов из нашей базы.
    issuer = None
    if bond.get("issuer_ticker"):
        comp = db.execute(text("SELECT ticker, name, sector FROM companies WHERE ticker = :t"),
                          {"t": bond["issuer_ticker"]}).first()
        if comp:
            debt = _issuer_debt_block(bond["issuer_ticker"])
            issuer = {"ticker": comp[0], "name": comp[1], "sector": comp[2], "debt": debt}

    return {"bond": bond, "sensitivity": sensitivity, "cashflow": cashflow, "issuer": issuer}


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
