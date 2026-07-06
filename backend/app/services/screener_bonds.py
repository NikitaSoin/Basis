"""Скринер облигаций — все бумаги с вердиктом «доходность vs риск» (методика
docs/bond_analys.md, тот же движок bond_risk.py, что и в карточке).

Главное отличие от мок-прототипа: НЕТ выдуманного «базис-балла». Заголовок каждой
бумаги — это вердикт-светофор из «доходность vs риск» (оплачен ли риск) + Risk Score
1–5 (кредитный риск). Числа берём из БД (live MOEX), вердикт считаем кодом.

Отдаёт строки + распределения метрик для гистограмм конструктора фильтра. Один
запрос — фронт фильтрует/сортирует/строит карту на клиенте (как у скринера акций).
"""
import threading
import time
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import bond_risk

# Кеш результата — stale-while-revalidate: отдаём старые данные сразу, пересчёт в фоне.
# TTL 1800с (30 мин) — данные меняются только с котировками/деплоем.
_CACHE: dict = {"ts": 0.0, "data": None}
_TTL = 1800
_refresh_lock = threading.Lock()
_refreshing = False

# нац. шкала: буква рейтинга → ранг 20..1 (для гистограммы/фильтра по рейтингу)
RATING_RANK = {
    "AAA": 20, "AA+": 19, "AA": 18, "AA-": 17, "A+": 16, "A": 15, "A-": 14,
    "BBB+": 13, "BBB": 12, "BBB-": 11, "BB+": 10, "BB": 9, "BB-": 8,
    "B+": 7, "B": 6, "B-": 5, "CCC": 4, "CC": 3, "C": 2, "D": 1,
}

# квазивалютные = номинал в иностранной валюте (замещающие / юаневые и т.п.).
# В базе RUB хранится как SUR.
_RUB = {"SUR", "RUB", None}


def _years_to(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
        return max(0.0, round((d - date.today()).days / 365.25, 2))
    except Exception:
        return None


def _verdict_kind(yvr: dict, coupon_type: str | None) -> str:
    """Тип вердикта — фронт по нему подбирает короткую подпись и тон пилюли."""
    if yvr.get("is_ofz"):
        return "ofz"
    if yvr.get("is_defaulted_verdict"):
        return "defaulted"
    if yvr.get("near_offer"):
        return "near_offer"
    if yvr.get("floater_verdict"):
        return "floater"
    if yvr.get("no_data"):
        return "structured" if coupon_type in ("structured", "other", "linker") else "nodata"
    return "premium"


def _do_calculate(db: Session) -> dict:
    """Внутренний расчёт без кеш-логики. Вызывается и синхронно, и из фонового треда."""
    rows_db = db.execute(text(
        "SELECT b.secid, b.isin, b.short_name, b.issuer_name, b.issuer_ticker, "
        "       b.bond_type, b.board, b.currency, b.coupon_percent, b.coupon_type, "
        "       b.coupon_period, b.maturity_date, b.offer_date, b.has_amortization, "
        "       b.last_price, b.ytm, b.duration_days, b.spread_bp, b.floater_spread_bp, "
        "       b.agency_rating, b.risk_tier, b.is_defaulted, "
        "       c.sector AS company_sector "
        "FROM bonds b LEFT JOIN companies c ON c.ticker = b.issuer_ticker"
    )).mappings().all()

    # требуемый спред-базис (медианы групп) — один раз из всей базы
    group_medians = bond_risk.group_median_spreads([dict(r) for r in rows_db])

    out = []
    dist = {k: [] for k in ("ytm", "spr", "cpn", "mat", "dur", "rat", "risk", "px")}

    for r in rows_db:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, date):
                d[k] = v.isoformat()
            elif hasattr(v, "real") and not isinstance(v, (int, float, bool)) and v is not None:
                d[k] = float(v)

        ytm = d.get("ytm")
        # структурные ноты / котировочный мусор: YTM ≤ 0 — не доходность, обнуляем
        if ytm is not None and ytm <= 0:
            ytm = None
        anomaly = bool(ytm and ytm > 40)
        mat_years = _years_to(d.get("maturity_date"))
        dur_years = round(d["duration_days"] / 365, 2) if d.get("duration_days") else None
        cur = d.get("currency")
        quasi = cur not in _RUB
        rating = d.get("agency_rating")
        rat_rank = RATING_RANK.get((rating or "").upper())

        # вердикт «доходность vs риск» — тот же движок, что в карточке
        bond_for_risk = {
            "bond_type": d.get("bond_type"), "is_defaulted": d.get("is_defaulted"),
            "offer_date": d.get("offer_date"), "maturity_date": d.get("maturity_date"),
            "ytm": ytm, "last_price": d.get("last_price"), "coupon_type": d.get("coupon_type"),
            "coupon_percent": d.get("coupon_percent"), "floater_spread_bp": d.get("floater_spread_bp"),
            "agency_rating": rating, "risk_tier": d.get("risk_tier"),
            "spread_bp": d.get("spread_bp"), "issuer_ticker": d.get("issuer_ticker"),
            "yield_anomaly": anomaly,
        }
        yvr = bond_risk.yield_vs_risk(bond_for_risk, group_medians) or {}
        risk_score = yvr.get("risk_score")
        if risk_score is None:
            risk_score = bond_risk.compute_risk_score(bond_for_risk, 0.0)

        sec = _bond_sector(d)
        out.append({
            "id": d["secid"], "n": d.get("short_name"), "issuer": d.get("issuer_name"),
            "tk": d.get("issuer_ticker"), "sec": sec,
            "bt": d.get("bond_type"), "cur": cur, "quasi": quasi,
            "ct": d.get("coupon_type"), "cpn": d.get("coupon_percent"),
            "flspr": d.get("floater_spread_bp"),
            "ytm": ytm, "px": d.get("last_price"),
            "spr": d.get("spread_bp"), "mat": mat_years, "dur": dur_years,
            "offer": d.get("offer_date"), "has_offer": bool(d.get("offer_date")),
            "amort": bool(d.get("has_amortization")),
            "rating": rating, "rat": rat_rank, "agency_group": yvr.get("agency_group"),
            "risk": risk_score, "bgroup": yvr.get("implied_group") or yvr.get("rating_group"),
            "light": yvr.get("light"), "vkind": _verdict_kind(yvr, d.get("coupon_type")),
            "premium": yvr.get("premium_bp"), "required": yvr.get("required_bp"),
            "defaulted": bool(d.get("is_defaulted")), "anomaly": anomaly,
            "near_offer": bool(yvr.get("near_offer")),
            "artifact": d.get("coupon_type") in ("floater", "linker", "structured", "other"),
        })

        # распределения (для гистограмм конструктора) — только осмысленные значения
        if ytm is not None and ytm < 60:
            dist["ytm"].append(ytm)
        if d.get("spread_bp") is not None:
            dist["spr"].append(d["spread_bp"])
        if d.get("coupon_percent"):
            dist["cpn"].append(float(d["coupon_percent"]))
        if mat_years is not None and mat_years <= 30:
            dist["mat"].append(mat_years)
        if dur_years is not None and dur_years <= 30:
            dist["dur"].append(dur_years)
        if rat_rank is not None:
            dist["rat"].append(rat_rank)
        if risk_score is not None:
            dist["risk"].append(risk_score)
        if d.get("last_price"):
            dist["px"].append(float(d["last_price"]))

    result = {"rows": out, "distributions": dist, "count": len(out)}
    _CACHE["ts"] = time.time()
    _CACHE["data"] = result
    return result


def score_bonds(db: Session) -> dict:
    """Возвращает данные мгновенно: свежий кеш → сразу; протухший → старые данные + фоновый пересчёт;
    холодный старт → синхронный расчёт."""
    global _refreshing
    now = time.time()
    age = now - _CACHE["ts"]

    if _CACHE["data"] is not None:
        if age < _TTL:
            return _CACHE["data"]
        # Кеш протух — отдаём старое, пересчитываем в фоне (stale-while-revalidate)
        with _refresh_lock:
            if not _refreshing:
                _refreshing = True
                threading.Thread(target=_background_refresh, daemon=True).start()
        return _CACHE["data"]

    # Первый запрос (кеш пустой) — считаем синхронно
    return _do_calculate(db)


def _background_refresh() -> None:
    global _refreshing
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        _do_calculate(db)
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()
        _refreshing = False


def warm_bonds_cache():
    """Фоновый прогрев кеша скринера облигаций при старте — чтобы первый пользовательский
    запрос не упирался в тяжёлый расчёт по всей базе."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        score_bonds(db)
    except Exception:  # noqa: BLE001
        pass
    finally:
        db.close()


def _bond_sector(d: dict) -> str:
    """Категория бумаги для фильтра-сектора и цвета на карте. Публичный эмитент →
    сектор его компании (чистая таксономия Basis); непубличный — грубый тип по имени."""
    bt = d.get("bond_type")
    if bt == "ofz":
        return "Госдолг (ОФЗ)"
    if bt == "muni":
        return "Муниципальные"
    if d.get("company_sector"):
        return d["company_sector"]
    from app.api.bonds import _issuer_type_guess
    guess = _issuer_type_guess(d.get("issuer_name") or d.get("short_name"))
    return "Корпораты — прочие" if guess.startswith("Компания") else guess
