"""Эндпоинты класса активов «Облигации».

Список (модуль «Рынок», вкладка Облигации), карточка облигации с расчётными
блоками под главный вопрос инвестора: надёжность → доходность/спред → дюрация →
денежный поток. Текстовая аналитика (bond-analyst) — из файлов backend/bonds/.
"""
import json
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import bond_risk
from app.services.moex_bonds import issuer_slug

router = APIRouter()
BONDS_DIR = Path(__file__).parent.parent.parent / "bonds"
COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"
ISSUERS_DIR = Path(__file__).parent.parent.parent / "bond_issuers"


def _read_issuer_file(slug: str | None, fname: str) -> str | None:
    """Профиль непубличного эмитента (бизнес/финансы), общий для всех его серий."""
    if not slug:
        return None
    p = ISSUERS_DIR / slug / fname
    return p.read_text(encoding="utf-8") if p.exists() else None


def _category_slug(name: str | None, bond_type: str | None) -> str | None:
    """Категорийный пояснитель для типовых эмитентов без индивидуального профиля:
    суверенный долг РФ (ОФЗ/замещающие ОВОЗ-ГОВОЗ), иностранные суверены,
    секьюритизация (СФО/ИА — ипотечные агенты), структурные ноты. Возвращает слаг
    директории-категории в bond_issuers/ или None."""
    up = (name or "").upper()
    if bond_type == "ofz" or "ОВОЗ РФ" in up or "ГОВОЗ РФ" in up:
        return "_cat-sovereign-rf"
    # иностранные суверены — ДО муниципалитетов (иначе «Республика Казахстан» уйдёт в муни)
    if re.search(r"(КАЗАХСТАН|KAZAKHSTAN|РЕСБЕЛ|БЕЛАРУС|BELARUS|РЕСПУБЛИКА БЕЛАРУСЬ)", up):
        return "_cat-sovereign-foreign"
    if bond_type == "muni" or re.search(
            r"(ОБЛАСТЬ|ОБЛ\.|РЕСПУБЛИКА|МИНФИН|КРАЙ\b|АВТОНОМН|Г\.МОСКВ|МОСКВА \d|САНКТ-ПЕТЕРБУРГ)", up):
        return "_cat-muni"
    if re.search(r"(^|\b)(СФО|ИА |ИА-|ИПОТЕЧНЫЙ АГЕНТ)", up) or up.startswith("ИА") or "СЕКЬЮР" in up:
        return "_cat-securitization"
    if re.search(r"(СТРУКТУРН|ИНВЕСТИЦИОНН[ЫО].{0,4} ОБЛИГАЦ|ЦИФРОВ.{0,4} ОБЛИГАЦ|\bCIB\b|БСПБ.*НОТ|^ИОС[_ ]|_PRTACM|_LKOH|_BSKT)", up):
        return "_cat-structured-note"
    return None

# кэш медианных спредов по рейтинговым группам (требуемый спред-базис из нашей базы)
_group_medians = {"data": None}


def _get_group_medians(db: Session) -> dict:
    if _group_medians["data"] is None:
        rows = [dict(r._mapping) for r in db.execute(text(
            "SELECT bond_type, risk_tier, agency_rating, spread_bp, is_defaulted, "
            "coupon_type, offer_date, maturity_date, ytm, last_price FROM bonds"))]
        _group_medians["data"] = bond_risk.group_median_spreads(rows)
    return _group_medians["data"]


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


# расшифровка кредитного рейтинга = «сможет ли расплатиться» (нац. шкала РФ)
def _rating_meaning(rating: str | None) -> str | None:
    if not rating:
        return None
    base = rating.rstrip("+-").upper()
    return {
        "AAA": "Максимальная кредитоспособность — риск невыплаты минимальный.",
        "AA": "Очень высокая кредитоспособность — расплатится почти наверняка.",
        "A": "Высокая кредитоспособность — устойчив, но чувствительнее к плохим условиям.",
        "BBB": "Достаточная кредитоспособность (нижняя граница «инвестиционного» уровня) — платит, но запас прочности умеренный.",
        "BB": "Спекулятивный уровень (ВДО): платит сейчас, но при ухудшении условий риск невыплаты заметный.",
        "B": "Высокий риск (ВДО): расплата сильно зависит от внешних условий и рефинансирования.",
        "CCC": "Очень высокий риск дефолта — расплата под вопросом.",
        "CC": "Преддефолтное состояние — дефолт весьма вероятен.",
        "C": "Крайне близко к дефолту / выборочный дефолт.",
        "D": "Дефолт — обязательства не исполняются.",
        "RD": "Выборочный дефолт по части обязательств.",
    }.get(base)


def _safe(s: str) -> str:
    return "".join(c for c in s if c.isalnum() or c in "-_").upper()


def _issuer_type_guess(name: str | None) -> str:
    """Грубый тип эмитента по имени выпуска (для непубличных — чтобы вкладка
    «Бизнес эмитента» не была пустой; это ОЦЕНКА по названию, не факт)."""
    s = (name or "").lower()
    pairs = [
        (("микрофин", "мфк", "мфо", "займер", "быстроденьги", "вэббанкир"), "Микрофинансовая организация (МФО)"),
        (("лизинг",), "Лизинговая компания"),
        (("банк", "кредит союз"), "Банк / кредитная организация"),
        (("девелоп", "строит", "жилье", "жилищ", "недвиж", "девелопмент", "сз ", "гк "), "Девелопер / строительство"),
        (("агро", "урожай", "зерн", "мясо", "сельхоз", "птиц", "свин", "молоч"), "АПК / сельское хозяйство"),
        (("транс", "логист", "перевоз", "автоколонна", "экспедици"), "Транспорт / логистика"),
        (("нефт", "газ", "топлив", "энерг", "ресурс"), "Энергетика / топливо / сырьё"),
        (("лес", "дерев", "пиломат", "целлюлоз"), "Лесопромышленность"),
        (("торг", "ритейл", "магазин", "маркет", "сеть"), "Торговля / ритейл"),
        (("девел", "концесс", "дорог", "инфраструктур"), "Инфраструктура / концессия"),
        (("финанс", "капитал", "инвест", "холдинг"), "Финансовый холдинг / SPV"),
    ]
    for keys, label in pairs:
        if any(k in s for k in keys):
            return label
    return "Компания (профиль уточняется)"


def _read_company_file(ticker: str, fname: str) -> str | None:
    """Текст файла аналитики компании-эмитента (для вкладок бизнес/финансы)."""
    p = COMPANIES_DIR / ticker / fname
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


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

    # near-maturity / near-offer: до ближайшего события (оферта или погашение) ≤120 дн.
    # На коротком хвосте YTM/спред технически раздуты — это НЕ премия за риск.
    tails = []
    for fld in ("offer_date", "maturity_date"):
        v = d.get(fld)
        if v:
            try:
                tails.append((date.fromisoformat(v[:10]) - date.today()).days)
            except Exception:
                pass
    d_near = min([t for t in tails if t is not None], default=None)
    d["near_offer"] = bool(d_near is not None and 0 <= d_near <= 120)
    # спред/YTM как «премия за риск» осмыслены только у фикс-купона вне near-зоны
    d["spread_artifact"] = bool(
        d.get("coupon_type") in ("floater", "linker", "structured") or d["near_offer"])

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
    d["agency_rating_meaning"] = _rating_meaning(d.get("agency_rating"))
    d["risk_verdict"] = _risk_verdict(d)
    d["arbitrage_note"] = _arbitrage_note(d, divergence)
    # 3-й взгляд надёжности — оценка Basis (Risk Score → группа), лёгкая (без чтения
    # файлов): якорь по рейтингу/тиру + стоп-флаги; полная (с долгом) — в карточке
    if d.get("bond_type") != "ofz":
        d["basis_score"] = bond_risk.compute_risk_score(d, 0.0)
        d["basis_group"] = bond_risk.score_to_group(d["basis_score"])
    return d


def _arbitrage_note(d: dict, divergence: str | None) -> str | None:
    """Есть ли расхождение цены и риска (потенциальный арбитраж/мис-прайсинг).
    Честно, без «купи/продай»: указываем НАПРАВЛЕНИЕ несоответствия и его смысл."""
    if d.get("bond_type") == "ofz" or divergence is None:
        return None
    rating = d.get("agency_rating")
    if divergence == "market_stricter":
        return (f"Рынок требует доходность ВЫШЕ, чем подразумевает рейтинг {rating}: "
                "либо рынок видит свежие проблемы, не отражённые в рейтинге (повод проверить эмитента), "
                "либо бумага недооценена и премия за риск избыточна. Это место, где «доходность не соответствует рейтингу».")
    if divergence == "market_milder":
        return (f"Рынок просит доходность НИЖЕ, чем подразумевает рейтинг {rating}: "
                "либо рынок видит улучшение раньше агентства, либо доходность НЕ компенсирует риск по рейтингу "
                "(бумага может быть дорогой за свой риск).")
    return "Рыночная оценка и агентский рейтинг согласованы — явного расхождения «цена против риска» нет."


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
    if d.get("coupon_type") in ("floater", "linker", "structured"):
        return ("Плавающий/индексируемый купон: YTM и G-спред к ОФЗ здесь не «премия за риск» "
                "(купон сам идёт за ставкой). Смотреть надо надбавку купона к ключевой ставке, "
                "а не доходность к погашению.")
    if d.get("near_offer"):
        return ("До ближайшего события (оферта/погашение) считаные недели — YTM технически раздут "
                "коротким хвостом, это не плата за кредитный риск. Вопрос здесь — вернут ли тело в срок.")
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

    # Блок «Эмитент» (для вкладок «Бизнес эмитента» / «Финансы эмитента»):
    # долговая нагрузка + бизнес-модель + управление компании-эмитента + переход в
    # её карточку. Только для публичных эмитентов из нашей базы (переиспользуем).
    issuer = None
    comp = None
    risk_md = None  # качественный вердикт «доходность за риск» по методике (пер-эмитент)
    if bond.get("issuer_ticker"):
        comp = db.execute(text("SELECT ticker, name, sector FROM companies WHERE ticker = :t"),
                          {"t": bond["issuer_ticker"]}).first()
    if comp:
        tk = bond["issuer_ticker"]
        risk_md = _read_company_file(tk, "bond_risk.md")
        issuer = {
            "ticker": comp[0], "name": comp[1], "sector": comp[2], "is_public": True,
            "debt": _issuer_debt_block(tk),
            "business_md": _read_company_file(tk, "business_model.md"),
            "governance_md": _read_company_file(tk, "governance_summary.md"),
        }
    else:
        # непубличный/суверенный эмитент — индивидуальный профиль из bond_issuers/<slug>
        # (общий для всех серий эмитента), иначе категорийный пояснитель (ОФЗ/суверены/
        # секьюритизация/структурные ноты), иначе заглушка.
        name = bond.get("issuer_name") or bond.get("short_name")
        slug = issuer_slug(name)
        bus = _read_issuer_file(slug, "business.md")
        fin = _read_issuer_file(slug, "financials.md")
        risk_md = _read_issuer_file(slug, "risk.md")
        is_category = False
        if not bus and not fin:
            cat = _category_slug(name, bond.get("bond_type"))
            if cat:
                bus = _read_issuer_file(cat, "business.md")
                fin = _read_issuer_file(cat, "financials.md")
                risk_md = _read_issuer_file(cat, "risk.md")
                is_category = bool(bus or fin)
        if bus or fin or bond.get("bond_type") != "ofz":
            issuer = {
                "ticker": None, "name": name, "sector": None, "is_public": False,
                "issuer_slug": slug, "is_category_profile": is_category,
                "type_guess": _issuer_type_guess(name),
                "issuer_business_md": bus,
                "issuer_financials_md": fin,
                "has_deep": (BONDS_DIR / _safe(secid) / "analysis_summary.md").exists(),
            }

    # Вкладка «Доходность vs риск» — методика docs/bond_analys.md (расчёт кодом)
    yvr = bond_risk.yield_vs_risk(bond, _get_group_medians(db))
    # обогащаем basis-оценку в bond полным score (с учётом долга эмитента)
    if yvr and yvr.get("risk_score") is not None:
        bond["basis_score"] = yvr["risk_score"]
        bond["basis_group"] = yvr.get("implied_group")
    if yvr:
        per_secid_deep = (BONDS_DIR / _safe(secid) / "analysis_summary.md").exists()
        # «разобрано по методике» = есть качественный вердикт пер-эмитент (risk.md)
        # ИЛИ индивидуальный глубокий разбор по конкретной бумаге.
        yvr["qualitative_md"] = risk_md
        yvr["has_deep_analysis"] = bool(risk_md) or per_secid_deep

    return {"bond": bond, "sensitivity": sensitivity, "cashflow": cashflow,
            "issuer": issuer, "yield_vs_risk": yvr}


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
