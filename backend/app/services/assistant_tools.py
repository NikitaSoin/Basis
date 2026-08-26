"""Инструменты ассистента — доступ ко ВСЕМ данным платформы, а не к пяти слотам.

До этого контекст ассистента собирался жёстким кодом: акции (5 обрезанных
текстов), лёгкий скринер, три макропоказателя и лента новостей. Всё остальное
для него не существовало — владелец спросил про облигации и получил «в моём
контексте нет данных по облигациям», хотя на платформе 3294 выпуска, 639
эмитентов с досье, фонды, фьючерсы, валюта, дивиденды, календарь и портфель
самого пользователя.

Здесь — инструменты (function calling), которыми модель ДОБИРАЕТ нужное сама:
таблицы читаются запросами, проза — поиском по корпусу (doc_index).

Правила, по которым это писалось:
  1. РЕЗУЛЬТАТ КОМПАКТЕН. Ответ инструмента остаётся в диалоге и переотправляется
     на каждом следующем шаге — «вернуть всё» здесь стоит дороже, чем кажется
     (см. комментарий про рост расхода в agent_runner). Отсюда лимиты строк и
     обрезка прозы.
  2. ЧЕСТНАЯ ДЕГРАДАЦИЯ. Нет данных — возвращаем {"found": false, ...} с
     объяснением, а не пустую структуру, которую модель примет за «ноль».
  3. ПРИВАТНОЕ — ТОЛЬКО СВОЁ. Портфель доступен лишь тому, чей user_id/токен
     пришёл в запрос; чужой портфель через инструмент не достать.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import doc_index

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).parent.parent.parent


def _f(v):
    """Числа из БД (Decimal) → float для JSON, None остаётся None."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _read_file(path: Path, max_chars: int) -> str | None:
    if not path.is_file():
        return None
    try:
        t = path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    return t[:max_chars] if t else None


# ============================== ПРОЗА (retrieval) ==============================

def _search_docs(query: str, entity: str | None = None, entity_kind: str | None = None,
                 limit: int = 6) -> dict:
    rows = doc_index.search(query, entity=entity, entity_kind=entity_kind,
                            limit=min(int(limit or 6), 10))
    return {"found": bool(rows), "count": len(rows), "results": rows,
            "note": "Полный текст найденного — инструментом read_platform_doc по doc_id."}


def _read_platform_doc(doc_id: str, max_chars: int = 6000) -> dict:
    return doc_index.read_doc(doc_id, max_chars=min(int(max_chars or 6000), 12000))


# ============================== ОБЛИГАЦИИ ==============================

_BOND_TYPE_RU = {"ofz": "ОФЗ (госдолг)", "corporate": "корпоративная",
                 "muni": "муниципальная", "other": "прочая"}


def _bond_row(r) -> dict:
    dur_y = round(r.duration_days / 365, 2) if r.duration_days else None
    return {"secid": r.secid, "isin": r.isin, "name": r.short_name,
            "issuer": r.issuer_name, "issuer_ticker": r.issuer_ticker,
            "type": _BOND_TYPE_RU.get(r.bond_type, r.bond_type),
            "currency": r.currency, "coupon_pct": _f(r.coupon_percent),
            "coupon_type": r.coupon_type, "price_pct_of_par": _f(r.last_price),
            "ytm_pct": _f(r.ytm), "ytm_kind": r.ytm_kind, "duration_years": dur_y,
            "maturity": _f(r.maturity_date), "offer": _f(r.offer_date),
            "amortization": bool(r.has_amortization), "defaulted": bool(r.is_defaulted)}


def _search_bonds(db: Session, query: str | None = None, bond_type: str | None = None,
                  issuer: str | None = None, min_ytm: float | None = None,
                  max_ytm: float | None = None, max_duration_years: float | None = None,
                  currency: str | None = None, limit: int = 12) -> dict:
    where, params = ["1=1"], {}
    if query:
        where.append("(LOWER(short_name) LIKE :q OR LOWER(COALESCE(issuer_name,'')) LIKE :q "
                     "OR LOWER(secid) LIKE :q OR LOWER(COALESCE(isin,'')) LIKE :q)")
        params["q"] = f"%{query.lower()}%"
    if bond_type:
        where.append("bond_type = :bt")
        params["bt"] = bond_type
    if issuer:
        where.append("LOWER(COALESCE(issuer_name,'')) LIKE :iss")
        params["iss"] = f"%{issuer.lower()}%"
    if min_ytm is not None:
        where.append("ytm >= :miny")
        params["miny"] = float(min_ytm)
    if max_ytm is not None:
        where.append("ytm <= :maxy")
        params["maxy"] = float(max_ytm)
    if max_duration_years is not None:
        where.append("duration_days <= :maxd")
        params["maxd"] = float(max_duration_years) * 365
    if currency:
        where.append("UPPER(COALESCE(currency,'SUR')) = :cur")
        params["cur"] = currency.upper()
    params["lim"] = min(int(limit or 12), 25)
    rows = db.execute(text(
        "SELECT secid, isin, short_name, issuer_name, issuer_ticker, bond_type, currency, "
        "coupon_percent, coupon_type, last_price, ytm, ytm_kind, duration_days, maturity_date, "
        "offer_date, has_amortization, is_defaulted FROM bonds "
        f"WHERE {' AND '.join(where)} AND ytm IS NOT NULL "
        "ORDER BY ytm DESC LIMIT :lim"), params).all()
    return {"found": bool(rows), "count": len(rows), "bonds": [_bond_row(r) for r in rows],
            "note": ("Отсортировано по доходности вниз. Высокая YTM — это ПЛАТА ЗА РИСК, "
                     "а не «выгоднее»: сверься с надёжностью эмитента (get_bond) прежде "
                     "чем что-то говорить о привлекательности.")}


def _get_bond(db: Session, secid: str) -> dict:
    key = (secid or "").strip().upper()
    r = db.execute(text(
        "SELECT secid, isin, short_name, issuer_name, issuer_ticker, bond_type, currency, "
        "coupon_percent, coupon_type, coupon_period, coupon_value, face_value, last_price, ytm, "
        "ytm_kind, duration_days, maturity_date, offer_date, has_amortization, is_defaulted, "
        "listing_level, accrued_int FROM bonds WHERE UPPER(secid) = :k OR UPPER(COALESCE(isin,'')) = :k "
        "LIMIT 1"), {"k": key}).first()
    if not r:
        return {"found": False, "reason": f"выпуск {secid} не найден в таблице bonds"}
    out = _bond_row(r)
    out["face_value"] = _f(r.face_value)
    out["coupon_value"] = _f(r.coupon_value)
    out["coupon_period_days"] = r.coupon_period
    out["accrued_interest"] = _f(r.accrued_int)
    out["listing_level"] = r.listing_level
    # разбор выпуска, если аналитик его писал
    out["analysis"] = _read_file(BACKEND_DIR / "bonds" / r.secid / "analysis_summary.md", 3000)
    # досье эмитента: либо карточка компании, либо папка эмитента облигаций
    if r.issuer_ticker:
        out["issuer_debt_load"] = _read_file(
            BACKEND_DIR / "companies" / r.issuer_ticker.upper() / "bond_risk.md", 2000)
        out["issuer_card_ticker"] = r.issuer_ticker
    if not out.get("issuer_debt_load") and r.issuer_name:
        found = doc_index.search(r.issuer_name, entity_kind="bond_issuer", limit=2)
        if found:
            out["issuer_docs"] = [{"doc_id": f["doc_id"], "section": f["section"]} for f in found]
    out["found"] = True
    return out


# ============================== ФОНДЫ / ФЬЮЧЕРСЫ / ВАЛЮТА ==============================

def _search_funds(db: Session, query: str | None = None, fund_type: str | None = None,
                  max_ter: float | None = None, limit: int = 12) -> dict:
    where, params = ["1=1"], {}
    if query:
        where.append("(LOWER(short_name) LIKE :q OR LOWER(COALESCE(sec_name,'')) LIKE :q "
                     "OR LOWER(secid) LIKE :q)")
        params["q"] = f"%{query.lower()}%"
    if fund_type:
        where.append("fund_type = :ft")
        params["ft"] = fund_type
    if max_ter is not None:
        where.append("ter <= :ter")
        params["ter"] = float(max_ter)
    params["lim"] = min(int(limit or 12), 25)
    rows = db.execute(text(
        "SELECT secid, short_name, sec_name, fund_type, benchmark, ter, last_price, val_today "
        f"FROM funds WHERE {' AND '.join(where)} ORDER BY COALESCE(val_today,0) DESC LIMIT :lim"),
        params).all()
    return {"found": bool(rows), "count": len(rows),
            "funds": [{"secid": r.secid, "name": r.sec_name or r.short_name,
                       "type": r.fund_type, "benchmark": r.benchmark, "ter_pct": _f(r.ter),
                       "price": _f(r.last_price), "turnover_rub_today": r.val_today}
                      for r in rows],
            "note": "TER — комиссия фонда в % годовых, главный тихий вычет из результата."}


def _get_fund(db: Session, secid: str) -> dict:
    key = (secid or "").strip().upper()
    r = db.execute(text(
        "SELECT secid, short_name, sec_name, fund_type, benchmark, currency, ter, last_price, "
        "val_today, num_trades, listing_level FROM funds WHERE UPPER(secid) = :k LIMIT 1"),
        {"k": key}).first()
    if not r:
        return {"found": False, "reason": f"фонд {secid} не найден"}
    return {"found": True, "secid": r.secid, "name": r.sec_name or r.short_name,
            "type": r.fund_type, "benchmark": r.benchmark, "currency": r.currency,
            "ter_pct": _f(r.ter), "price": _f(r.last_price),
            "turnover_rub_today": r.val_today, "num_trades": r.num_trades,
            "listing_level": r.listing_level,
            "analysis": _read_file(BACKEND_DIR / "funds" / r.secid / "analysis_summary.md", 3000)}


def _search_futures(db: Session, query: str | None = None, asset_kind: str | None = None,
                    limit: int = 12) -> dict:
    where, params = ["1=1"], {}
    if query:
        where.append("(LOWER(short_name) LIKE :q OR LOWER(COALESCE(sec_name,'')) LIKE :q "
                     "OR LOWER(COALESCE(asset_name,'')) LIKE :q OR LOWER(secid) LIKE :q "
                     "OR LOWER(asset_code) LIKE :q)")
        params["q"] = f"%{query.lower()}%"
    if asset_kind:
        where.append("asset_kind = :ak")
        params["ak"] = asset_kind
    params["lim"] = min(int(limit or 12), 25)
    rows = db.execute(text(
        "SELECT secid, short_name, sec_name, asset_code, asset_name, asset_kind, linked_ticker, "
        "expiration_date, last_price, initial_margin, contract_value, open_position "
        f"FROM futures WHERE {' AND '.join(where)} ORDER BY COALESCE(open_position,0) DESC LIMIT :lim"),
        params).all()
    out = []
    for r in rows:
        lev = None
        if r.contract_value and r.initial_margin and float(r.initial_margin) > 0:
            lev = round(float(r.contract_value) / float(r.initial_margin), 1)
        out.append({"secid": r.secid, "name": r.sec_name or r.short_name,
                    "underlying": r.asset_name or r.asset_code, "kind": r.asset_kind,
                    "linked_ticker": r.linked_ticker, "expiration": _f(r.expiration_date),
                    "price": _f(r.last_price), "margin_rub": _f(r.initial_margin),
                    "contract_value_rub": _f(r.contract_value), "leverage_x": lev,
                    "open_positions": r.open_position})
    return {"found": bool(out), "count": len(out), "futures": out,
            "note": "leverage_x — эффективное плечо (номинал/ГО): усиливает и прибыль, и убыток."}


def _get_spot(db: Session, kind: str | None = None) -> dict:
    where = "WHERE kind = :k" if kind else ""
    rows = db.execute(text(
        f"SELECT secid, short_name, name, kind, base_code, last_price, change_pct, updated_at "
        f"FROM spot_assets {where} ORDER BY kind, secid"),
        ({"k": kind} if kind else {})).all()
    return {"found": bool(rows), "count": len(rows),
            "assets": [{"secid": r.secid, "name": r.name or r.short_name, "kind": r.kind,
                        "price_rub": _f(r.last_price), "change_pct": _f(r.change_pct),
                        "as_of": _f(r.updated_at)} for r in rows]}


# ============================== АКЦИИ ==============================

def _screen_stocks(db: Session, sector: str | None = None, max_pe: float | None = None,
                   min_div_yield: float | None = None, min_upside_pct: float | None = None,
                   sort_by: str = "upside", limit: int = 15) -> dict:
    where, params = ["m.pe_current IS NOT NULL"], {}
    if sector:
        where.append("LOWER(c.sector) LIKE :sec")
        params["sec"] = f"%{sector.lower()}%"
    if max_pe is not None:
        where.append("m.pe_current <= :mpe")
        params["mpe"] = float(max_pe)
    if min_div_yield is not None:
        where.append("m.div_yield >= :mdy")
        params["mdy"] = float(min_div_yield)
    params["lim"] = min(int(limit or 15), 30)
    rows = db.execute(text(
        "SELECT c.ticker, c.name, c.sector, m.pe_current, m.div_yield, m.fair_value, m.beta, "
        "m.return_total_3y, l.close AS price FROM companies c "
        "JOIN company_metrics m ON m.ticker = c.ticker "
        "LEFT JOIN LATERAL (SELECT close FROM quotes q WHERE q.company_id = c.id "
        "ORDER BY q.date DESC LIMIT 1) l ON true "
        f"WHERE {' AND '.join(where)}"), params).all()
    out = []
    for r in rows:
        upside = None
        if r.fair_value and r.price:
            try:
                upside = round((float(r.fair_value) / float(r.price) - 1) * 100, 1)
            except (TypeError, ZeroDivisionError):
                pass
        if min_upside_pct is not None and (upside is None or upside < float(min_upside_pct)):
            continue
        out.append({"ticker": r.ticker, "name": r.name, "sector": r.sector,
                    "pe": _f(r.pe_current), "div_yield_pct": _f(r.div_yield),
                    "price": _f(r.price), "fair_value_basis": _f(r.fair_value),
                    "upside_pct": upside, "beta": _f(r.beta),
                    "return_3y_pct": _f(r.return_total_3y)})
    key = {"upside": "upside_pct", "pe": "pe", "div": "div_yield_pct",
           "return": "return_3y_pct"}.get(sort_by, "upside_pct")
    rev = key != "pe"
    out.sort(key=lambda d: (d.get(key) is None, -(d.get(key) or 0) if rev else (d.get(key) or 0)))
    out = out[:params["lim"]]
    return {"found": bool(out), "count": len(out), "stocks": out,
            "note": ("fair_value_basis и upside_pct — МОДЕЛЬНАЯ оценка Basis, не факт и не "
                     "сигнал к сделке.")}


_CARD_FILES = {
    "business": "business_model.md", "finance": "financials_summary.md",
    "governance": "governance_summary.md", "markets": "market_summary.md",
    "macro": "macro_summary.md", "geo": "geo_summary.md",
    "institutions": "institutions_summary.md", "debt": "bond_risk.md",
}


def _get_company_card(db: Session, ticker: str, tabs: list | None = None,
                      max_chars_per_tab: int = 2500) -> dict:
    tk = (ticker or "").strip().upper()
    row = db.execute(text("SELECT ticker, name, sector FROM companies WHERE ticker = :t"),
                     {"t": tk}).first()
    if not row:
        return {"found": False, "reason": f"тикера {tk} нет в базе компаний платформы"}
    price_row = db.execute(text(
        "SELECT q.close, q.date FROM quotes q JOIN companies c ON c.id = q.company_id "
        "WHERE c.ticker = :t ORDER BY q.date DESC LIMIT 1"), {"t": tk}).first()
    price = _f(price_row.close) if price_row else None
    out = {"found": True, "ticker": row.ticker, "name": row.name, "sector": row.sector,
           "price": price, "price_date": _f(price_row.date) if price_row else None}
    m = db.execute(text(
        "SELECT pe_current, div_yield, fair_value, eps_implied, dps_implied, beta "
        "FROM company_metrics WHERE ticker = :t"), {"t": tk}).first()
    if m:
        eps, dps = _f(m.eps_implied), _f(m.dps_implied)
        pe_live = round(price / eps, 2) if price and eps and eps > 0 else _f(m.pe_current)
        dy_live = round(dps / price * 100, 2) if price and dps else _f(m.div_yield)
        fv = _f(m.fair_value)
        out["live_multiples"] = {
            "pe": pe_live, "div_yield_pct": dy_live, "beta": _f(m.beta),
            "fair_value_basis": fv,
            "upside_pct": round((fv / price - 1) * 100, 1) if fv and price else None,
            "note": "P/E и дивдоходность посчитаны от ТЕКУЩЕЙ цены — приоритетнее чисел в текстах",
        }
    # Числовые ряды отчётности по годам (та же выжимка из financials.json, что
    # идёт в предзагруженный контекст) — без них карточка отвечала прозой на
    # вопрос «покажи выручку по годам».
    try:
        from app.services.assistant import _key_financials
        kf = _key_financials(tk)
        if kf:
            out["key_financials"] = kf
    except Exception:  # noqa: BLE001 — числа необязательны, карточка полезна и без них
        logger.exception("get_company_card: не удалось собрать key_financials по %s", tk)
    wanted = [t for t in (tabs or ["business", "finance"]) if t in _CARD_FILES]
    prose = {}
    for t in wanted[:4]:
        txt = _read_file(BACKEND_DIR / "companies" / tk / _CARD_FILES[t],
                         min(int(max_chars_per_tab or 2500), 4000))
        if txt:
            prose[t] = txt
    out["prose"] = prose
    out["available_tabs"] = list(_CARD_FILES)
    return out


def _get_dividends(db: Session, ticker: str, limit: int = 10) -> dict:
    tk = (ticker or "").strip().upper()
    rows = db.execute(text(
        "SELECT record_date, amount, currency FROM dividends WHERE ticker = :t "
        "ORDER BY record_date DESC LIMIT :lim"),
        {"t": tk, "lim": min(int(limit or 10), 20)}).all()
    if not rows:
        return {"found": False, "reason": f"выплат по {tk} в таблице дивидендов нет"}
    return {"found": True, "ticker": tk,
            "payments": [{"record_date": _f(r.record_date), "amount_per_share": _f(r.amount),
                          "currency": r.currency or "RUB"} for r in rows],
            "note": "record_date — дата фиксации реестра (отсечка)."}


# ============================== МАКРО / СОБЫТИЯ / ПОРТФЕЛЬ ==============================

def _get_earnings(db: Session, ticker: str) -> dict:
    """Разобранные отчётности эмитента за последние 120 дней. Берём готовую
    выборку из agent_tools — она уже используется агентами обновления карточек,
    второй такой же запрос заводить незачем."""
    from app.services.agent_tools import _get_recent_earnings
    out = _get_recent_earnings(db, (ticker or "").strip().upper())
    rows = out.get("earnings") or []
    return {"found": bool(rows), "count": len(rows), "earnings": rows,
            "note": "gist — краткий разбор Basis по вышедшему отчёту (суждение)."} if rows else {
            "found": False, "reason": f"разобранных отчётов по {ticker} за 120 дней нет"}


def _get_macro(db: Session, codes: list | None = None) -> dict:
    codes = codes or ["key_rate", "inflation", "usdrub", "gdp", "unemployment"]
    out = {}
    for code in [str(c) for c in codes][:8]:
        rows = db.execute(text(
            "SELECT value, metric, as_of, unit FROM macro_data_points WHERE indicator_code = :c "
            "ORDER BY as_of DESC LIMIT 3"), {"c": code}).all()
        if rows:
            out[code] = [{"value": _f(r.value), "metric": r.metric, "as_of": _f(r.as_of),
                          "unit": r.unit} for r in rows]
    meetings = db.execute(text(
        "SELECT decision_date, rate_value, signal, next_meeting_date FROM rate_meetings "
        "WHERE rate_value IS NOT NULL ORDER BY decision_date DESC LIMIT 4")).all()
    return {"found": bool(out), "indicators": out,
            "key_rate_path": [{"date": _f(r.decision_date), "rate": _f(r.rate_value),
                               "signal": (r.signal or "")[:160] or None,
                               "next_meeting": _f(r.next_meeting_date)} for r in meetings],
            "note": "Траектория ставки — из журнала решений ЦБ (rate_meetings)."}


def _get_calendar(db: Session, days: int = 30, ticker: str | None = None,
                  event_type: str | None = None, limit: int = 15) -> dict:
    today = date.today()
    params = {"d0": today, "d1": today + timedelta(days=min(int(days or 30), 180)),
              "lim": min(int(limit or 15), 25)}
    where = ["event_date BETWEEN :d0 AND :d1"]
    if ticker:
        where.append("UPPER(COALESCE(ticker,'')) = :t")
        params["t"] = ticker.strip().upper()
    if event_type:
        where.append("event_type = :et")
        params["et"] = event_type
    rows = db.execute(text(
        "SELECT event_date, event_time, event_type, ticker, title, status, payload "
        f"FROM calendar_events WHERE {' AND '.join(where)} ORDER BY event_date LIMIT :lim"),
        params).all()
    return {"found": bool(rows), "count": len(rows),
            "events": [{"date": _f(r.event_date), "time_msk": r.event_time, "type": r.event_type,
                        "ticker": r.ticker, "title": r.title, "status": r.status,
                        "details": json.dumps(r.payload, ensure_ascii=False)[:200] if r.payload else None}
                       for r in rows]}


def _get_portfolio(db: Session, user_id: int | None, guest_token: str | None) -> dict:
    """Портфель СПРАШИВАЮЩЕГО. Чужой достать нельзя: выборка идёт строго по
    user_id сессии (или по гостевому токену этого же браузера)."""
    if user_id is None and not guest_token:
        return {"found": False, "reason": "портфель доступен только в своём аккаунте — "
                                          "пользователь не авторизован"}
    if user_id is not None:
        p = db.execute(text("SELECT id, name FROM portfolios WHERE user_id = :u "
                            "ORDER BY id LIMIT 1"), {"u": user_id}).first()
    else:
        p = db.execute(text("SELECT id, name FROM portfolios WHERE guest_token = :g "
                            "ORDER BY id LIMIT 1"), {"g": guest_token}).first()
    if not p:
        return {"found": False, "reason": "у пользователя ещё нет портфеля на платформе"}
    rows = db.execute(text(
        "SELECT pp.instrument_type, pp.secid, pp.quantity, pp.avg_buy_price, pp.currency, "
        "c.ticker, c.name, l.close AS price FROM portfolio_positions pp "
        "LEFT JOIN companies c ON c.id = pp.company_id "
        "LEFT JOIN LATERAL (SELECT close FROM quotes q WHERE q.company_id = pp.company_id "
        "ORDER BY q.date DESC LIMIT 1) l ON true WHERE pp.portfolio_id = :p"), {"p": p.id}).all()
    positions, total = [], 0.0
    for r in rows:
        qty = _f(r.quantity) or 0
        price = _f(r.price)
        value = round(qty * price, 2) if price else None
        if value:
            total += value
        positions.append({"type": r.instrument_type, "ticker": r.ticker or r.secid,
                          "name": r.name, "quantity": qty, "avg_buy_price": _f(r.avg_buy_price),
                          "price": price, "value_rub": value, "currency": r.currency})
    for pos in positions:
        if pos["value_rub"] and total:
            pos["weight_pct"] = round(pos["value_rub"] / total * 100, 1)
    return {"found": bool(positions), "portfolio": p.name, "positions": positions,
            "total_value_rub": round(total, 2) if total else None,
            "note": "Стоимость — по последней цене в базе котировок; облигации/фонды "
                    "могут идти без цены, если их нет в quotes."}


def _get_news(db: Session, ticker: str | None = None, query: str | None = None,
              limit: int = 8) -> dict:
    where, params = ["status = 'published'"], {"lim": min(int(limit or 8), 15)}
    if ticker:
        # affected_tickers — JSONB-массив (["SBER", ...]), поэтому containment,
        # а не ANY(): ANY работает только с массивами PostgreSQL и здесь падает
        # CAST(...), а не :t::jsonb — text() принимает «::» за начало
        # bind-параметра и падает синтаксической ошибкой у самого двоеточия
        where.append("affected_tickers @> CAST(:t AS jsonb)")
        params["t"] = json.dumps([ticker.strip().upper()])
    if query:
        where.append("(LOWER(title) LIKE :q OR LOWER(COALESCE(impact_comment,'')) LIKE :q)")
        params["q"] = f"%{query.lower()}%"
    rows = db.execute(text(
        "SELECT title, impact_comment, affected_tickers, published_at, source_url "
        f"FROM market_updates WHERE {' AND '.join(where)} "
        "ORDER BY published_at DESC LIMIT :lim"), params).all()
    return {"found": bool(rows), "count": len(rows),
            "news": [{"title": r.title, "impact": (r.impact_comment or "")[:220],
                      "tickers": list(r.affected_tickers or []),
                      "published_at": _f(r.published_at), "url": r.source_url} for r in rows]}


# ============================== ОТЧЁТНОСТЬ ЦЕЛИКОМ ==============================

_STATEMENTS = {"income": "income_statement", "balance": "balance_sheet",
               "cash_flow": "cash_flow", "bank": "bank_pnl"}

# Строки, которые отдаём при statement="all" — иначе три полных отчёта не влезают
# в лимит ответа инструмента и обрезаются на середине числа.
_STATEMENT_CORE = {
    "income": ["revenue", "ebitda", "operating_profit", "net_profit"],
    "balance": ["total_assets", "total_equity", "net_debt", "cash"],
    "cash_flow": ["cfo", "capex", "fcf"],
}


def _series_by_year(series, years: list) -> dict | None:
    """Ряд из financials.json — позиционный список, выровненный по meta.fiscal_years.
    🔴 Отдаём модели ПАРАМИ год→значение, а не голым списком: позиционное
    выравнивание — источник года-сдвига (в файлах такие сдвиги уже находились),
    и модель, считая «последний элемент = последний год», ошибётся молча."""
    if not isinstance(series, list) or not years:
        return None
    out = {str(y): _f(v) for y, v in zip(years, series) if v is not None}
    return out or None


def _itemized(series: list, years: list, expand: bool) -> dict:
    """Постатейная расшифровка (`cfo_lines`, `expense_lines` …) — это СПИСОК
    СЛОВАРЕЙ [{name, values, note}], а не числовой ряд.
    🔴 Обрабатывать её как ряд нельзя: zip с годами даёт «2016 → {name: …}» —
    правдоподобную с виду чушь, которую модель пересказала бы как факт.
    По умолчанию отдаём только перечень статей (расшифровка тяжелее самого
    отчёта — до 5 КБ), полностью — по адресному запросу через lines."""
    names = [str(it.get("name")) for it in series if isinstance(it, dict) and it.get("name")]
    if not expand:
        return {"available": names[:20], "count": len(names),
                "note": "расшифровка свёрнута — запроси её через lines"}
    out = {}
    for it in series:
        if not isinstance(it, dict) or not it.get("name"):
            continue
        row = _series_by_year(it.get("values"), years)
        if row:
            out[str(it["name"])[:80]] = row
    return out


def _statement_block(node: dict, years: list, lines: list | None) -> dict:
    out = {}
    for name, series in (node or {}).items():
        if lines and name not in lines:
            continue
        if isinstance(series, str):         # cost_format и подобные метки
            out[name] = series[:120]
            continue
        if isinstance(series, dict):        # margins / ratios — вложенная группа
            sub = {k: _series_by_year(v, years) for k, v in series.items()}
            sub = {k: v for k, v in sub.items() if v}
            if sub:
                out[name] = sub
            continue
        if isinstance(series, list) and any(isinstance(x, dict) for x in series):
            block = _itemized(series, years, expand=bool(lines and name in lines))
            if block:
                out[name] = block
            continue
        row = _series_by_year(series, years)
        if row:
            out[name] = row
    return out


def _get_financial_statements(db: Session, ticker: str, statement: str = "all",
                              period: str = "annual", lines: list | None = None) -> dict:
    """Полная отчётность из financials.json — единого источника чисел карточки.
    До этого ассистент видел только выжимку (_key_financials): выручка, прибыль и
    ещё несколько строк. Вопрос «какой у компании операционный денежный поток» или
    «сколько было капзатрат в 2023-м» упирался в её отсутствие."""
    tk = (ticker or "").strip().upper()
    path = BACKEND_DIR / "companies" / tk / "financials.json"
    if not path.is_file():
        return {"found": False, "reason": f"по {tk} нет файла отчётности на платформе"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"found": False, "reason": f"файл отчётности {tk} не читается"}

    meta = data.get("meta") or {}
    years = meta.get("fiscal_years") or []
    out = {"found": True, "ticker": tk, "name": meta.get("name"),
           "currency": meta.get("currency", "RUB"), "unit": meta.get("unit"),
           "standard": meta.get("reporting_standard"), "fiscal_years": years,
           "profile": meta.get("profile")}

    if period == "interim":
        interim = data.get("interim") or {}
        periods = interim.get("periods") or []
        if not periods:
            return {"found": False, "ticker": tk,
                    "reason": "промежуточной отчётности (квартал/полугодие) по этой "
                              "компании на платформе нет — она раскатана только на "
                              "~45 голубых фишек"}
        labels = [p.get("label") for p in periods]
        # Перебираем ВСЕ блоки, а не фиксированную тройку: у банков промежуточные
        # ряды лежат в bank_pnl/bank_metrics, и жёсткий список молча отдавал по
        # Сберу пустую отчётность при found=true — худший вид ошибки.
        block = {}
        for key, node in interim.items():
            if key in ("periods", "data_flags") or not isinstance(node, dict):
                continue
            packed = _statement_block(node, labels, lines)
            if packed:
                block[key] = packed
        out["interim"] = {"periods": periods, "statements": block}
        out["note"] = ("Промежуточные периоды кумулятивные (6М = полугодие нарастающим "
                       "итогом), сравнивать их можно только с таким же периодом прошлого года.")
        return out

    wanted = ([statement] if statement in _STATEMENTS
              else ["income", "balance", "cash_flow"])
    for short in wanted:
        node = data.get(_STATEMENTS[short])
        if not isinstance(node, dict):
            continue
        pick = lines if lines else (None if statement in _STATEMENTS
                                    else _STATEMENT_CORE.get(short))
        block = _statement_block(node, years, pick)
        if block:
            out[short] = block
    if data.get("bank_pnl") and statement in ("all", "bank", "income"):
        out["bank"] = _statement_block(data["bank_pnl"], years, lines)

    # 🔴 data_flags у части компаний — 9 КБ прозы (оговорки аналитика к каждой
    # строке). Сами отчёты весят ~2 КБ, а лимит ответа инструмента 5 КБ: без
    # обрезки флаги съедали бы ответ целиком и JSON приходил бы рубленым.
    flags = data.get("data_flags")
    if flags:
        flags = flags if isinstance(flags, list) else [str(flags)]
        out["data_flags"] = [str(f)[:260] for f in flags[:5]]
        if len(flags) > 5:
            out["data_flags_more"] = len(flags) - 5
    out["note"] = (f"Числа в {meta.get('unit') or '?'} {meta.get('currency', 'RUB')}. "
                   "🔴 Знак capex в файлах непоследователен (у части компаний минус, "
                   "у части плюс) — свободный поток считай как CFO − |capex|, а не "
                   "вычитанием вслепую. Если statement не задан, отданы только "
                   "ключевые строки; полный отчёт — вызвать с statement=income/balance/cash_flow.")
    return out


# ============================== ФИНАНСОВАЯ МОДЕЛЬ ==============================

def _fm_lines(series: dict | None, keep: int = 4) -> dict | None:
    if not isinstance(series, dict):
        return None
    return {k: _f(v) for k, v in list(series.items())[:keep]}


def _get_financial_model(db: Session, ticker: str) -> dict:
    """Прогнозная модель компании (три сценария) — та же, что на вкладке «Финансы».
    Берём через движок, а не файлом: он подставляет живые Brent/курс/ставку и
    пересчитывает базовый сценарий, поэтому числа совпадают с экраном."""
    tk = (ticker or "").strip().upper()
    try:
        from app.services.financial_model import get_financial_model
        model = get_financial_model(db, tk)
    except Exception as e:  # noqa: BLE001 — модель необязательна
        logger.exception("assistant: финмодель %s не собралась", tk)
        return {"found": False, "reason": f"модель не собралась: {type(e).__name__}"}
    if not model:
        return {"found": False, "ticker": tk,
                "reason": "прогнозной модели по этой компании нет (построены не для всех "
                          "эмитентов) — прогноз и справедливая цена есть в блоке valuation "
                          "карточки, инструмент get_company_card"}

    meta = model.get("meta") or {}
    forecast = model.get("forecast") or {}
    out = {"found": True, "ticker": tk, "horizon": meta.get("horizon_years"),
           "currency": meta.get("currency", "RUB"), "unit": meta.get("unit"),
           "as_of": meta.get("as_of"),
           "drivers": [{"name": d.get("name"), "kind": d.get("kind"),
                        "base_value": _f(d.get("base_value")),
                        "live_value": _f(d.get("live_value")),
                        "live_status": d.get("live_status"),
                        "rationale": (d.get("rationale") or "")[:220]}
                       for d in (model.get("drivers") or [])[:6]],
           "scenarios": {},
           "scenario_weights": model.get("scenario_weights"),
           "sensitivity": model.get("sensitivity")}
    # valuation и data_flags у части моделей — по 4 КБ прозы каждый, и вместе с
    # тремя сценариями ответ переваливал за лимит инструмента (12 КБ): модель
    # получала бы обрезанный JSON. Оставляем суть, оговорки — первыми пунктами.
    val = model.get("valuation") or {}
    if isinstance(val, dict):
        out["valuation"] = {k: (str(v)[:400] if isinstance(v, str) else v)
                            for k, v in val.items()
                            if k in ("method", "fair_value", "fair_value_per_share",
                                     "upside_pct", "target_multiple", "wacc",
                                     "terminal_growth", "cross_check", "comment",
                                     "rationale", "as_of")}
    flags = model.get("data_flags")
    if flags:
        flags = flags if isinstance(flags, list) else [str(flags)]
        out["data_flags"] = [str(f)[:260] for f in flags[:4]]
        if len(flags) > 4:
            out["data_flags_more"] = len(flags) - 4
    for name in ("base", "bull", "bear"):
        sc = forecast.get(name)
        if not isinstance(sc, dict):
            continue
        out["scenarios"][name] = {
            k: _fm_lines(v) for k, v in sc.items()
            if k in ("revenue", "ebitda", "net_profit", "fcf", "eps", "dps") and v}
        if sc.get("assumptions"):
            out["scenarios"][name]["assumptions"] = str(sc["assumptions"])[:300]
    out["note"] = ("Модель — ОЦЕНКА (суждение аналитика Basis по методике), не факт. "
                   "Базовый сценарий пересчитан на живые значения драйверов, "
                   "бык/медведь — авторские. Справедливая цена карточки считается "
                   "отдельным движком (BFV) и может отличаться от valuation модели.")
    return out


# ============================== БАРОМЕТРЫ СРЕДЫ ==============================

_BAROMETER_KINDS = {"geo": "геополитический", "inst": "институциональный"}


def _shrink(node, str_max: int = 500, list_max: int = 12, depth: int = 0):
    """Ужать ветку payload до размера, который влезает в ответ инструмента.
    🔴 Резать сериализованный JSON строкой нельзя — обратно он не разберётся;
    сжимаем САМУ структуру: длинные строки укорачиваем, длинные списки
    подрезаем с честной пометкой, вглубь не уходим дальше четвёртого уровня."""
    if isinstance(node, str):
        return node if len(node) <= str_max else node[:str_max] + "…"
    if isinstance(node, dict):
        if depth >= 4:
            return {"…": f"вложенность свёрнута, ключи: {sorted(node)[:8]}"}
        return {k: _shrink(v, str_max, list_max, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        out = [_shrink(v, str_max, list_max, depth + 1) for v in node[:list_max]]
        if len(node) > list_max:
            out.append(f"…ещё {len(node) - list_max} пунктов")
        return out
    return node


def _get_barometer(db: Session, kind: str = "geo", section: str | None = None) -> dict:
    """Барометр среды из Обозревателя («Оценка ситуации»): геополитический (13
    субиндексов G1-G13, сценарии S1-S4) или институциональный (M1-M13).
    🔴 Институциональный отдаём ЧЕРЕЗ ту же анонимизацию, что и витрина: иначе
    через ассистента утекло бы то, что на экране намеренно обезличено."""
    k = "inst" if str(kind).startswith("inst") else "geo"
    try:
        from app.services.barometer_store import get_payload_with_meta
        payload = get_payload_with_meta(db, k)
    except Exception as e:  # noqa: BLE001
        logger.exception("assistant: барометр %s не читается", k)
        return {"found": False, "reason": f"барометр не читается: {type(e).__name__}"}
    if not payload:
        return {"found": False, "reason": f"{_BAROMETER_KINDS[k]} барометр ещё не сформирован"}
    if k == "inst":
        try:
            from app.api.market import _inst_anonymize
            payload = _inst_anonymize(payload)
        except Exception:  # noqa: BLE001 — без анонимизации отдавать нельзя
            logger.exception("assistant: анонимизация институционального барометра упала")
            return {"found": False, "reason": "институциональный барометр временно недоступен"}

    out = {"found": True, "kind": k, "as_of": payload.get("as_of"),
           "barometer": payload.get("barometer"),
           "summary": (payload.get("summary") or "")[:900] or None,
           "meta": payload.get("_meta")}
    scen = payload.get("scenario") or {}
    if scen:
        out["scenario"] = {kk: vv for kk, vv in scen.items()
                           if kk in ("current", "scenarios", "probabilities", "horizon",
                                     "current_key", "rationale")}
    subs = payload.get("subindices") or []
    out["subindices"] = [{"key": s.get("key"), "name": s.get("name"),
                          "score": _f(s.get("score")), "direction": s.get("direction"),
                          "comment": (s.get("comment") or "")[:180]} for s in subs[:13]]
    if k == "geo":
        out["sector_flags"] = [{"sector": s.get("sector"), "direction": s.get("direction"),
                                "comment": (s.get("comment") or "")[:200]}
                               if isinstance(s, dict) else s
                               for s in (payload.get("sector_flags") or [])[:8]]
        # 🔴 Очаги целиком — 19 КБ (по каждому: траектория, ход боёв, переговоры,
        # сценарии). Больше лимита ответа инструмента, то есть модель получила бы
        # обрывок. Отдаём шапку по каждому очагу, полностью — section="regions".
        out["regions"] = {}
        for name, node in (payload.get("regions") or {}).items():
            if isinstance(node, dict):
                out["regions"][name] = {
                    "status": node.get("status") or node.get("label"),
                    "direction": node.get("direction") or node.get("trend"),
                    "summary": str(node.get("summary") or node.get("comment") or "")[:400],
                    "detail_available": sorted(kk for kk in node if kk not in
                                               ("status", "label", "direction", "trend",
                                                "summary", "comment"))[:12]}
            else:
                out["regions"][name] = str(node)[:400]
        out["regions_note"] = ("по очагу целиком — вызвать с section='regions' "
                               "(вернётся подробный разбор, он большой)")
    else:
        out["alerts"] = [{"title": a.get("title") or a.get("name"),
                          "severity": a.get("severity") or a.get("level"),
                          "comment": (a.get("comment") or a.get("text") or "")[:220]}
                         if isinstance(a, dict) else str(a)[:220]
                         for a in (payload.get("alerts") or [])[:6]]
        out["institutional_crp_floor_pp"] = payload.get("institutional_crp_floor_pp")

    if section and isinstance(payload.get(section), (list, dict)):
        # Страховка по РАЗМЕРУ, а не по одному проходу: разделы барометра растут
        # (очаги на бою — 19 КБ против 4 КБ в файле-якоре), и одного сжатия не
        # хватало — ответ всё равно вылезал за лимит и приходил рубленым.
        node = None
        for str_max, list_max, depth_cap in ((500, 12, 4), (260, 6, 3), (140, 4, 2)):
            node = _shrink(payload[section], str_max=str_max, list_max=list_max,
                           depth=4 - depth_cap)
            if len(json.dumps(node, ensure_ascii=False, default=str)) <= 8000:
                break
            out["section_truncated"] = True
        out["section_full"] = node
    out["note"] = ("Барометр — контекст РЫНКА, не рекомендация по бумаге. Оценка "
                   "конкретной компании в этой рамке — вкладки «Геополитика»/«Институты» "
                   "её карточки (get_company_card с tabs=[geo] / [institutions]).")
    return out


# ============================== КАРТА РЫНКА И ИНДЕКСЫ ==============================

def _top_movers(sectors: list, limit: int = 8) -> dict:
    tiles = [t for s in (sectors or []) for t in (s.get("tiles") or [])]
    tiles = [t for t in tiles if t.get("change_pct") is not None]
    tiles.sort(key=lambda t: t["change_pct"], reverse=True)
    short = lambda t: {"ticker": t.get("ticker"), "name": t.get("name"),  # noqa: E731
                       "sector": t.get("sector"), "change_pct": t.get("change_pct")}
    return {"leaders": [short(t) for t in tiles[:limit]],
            "laggards": [short(t) for t in tiles[-limit:][::-1]],
            "instruments_total": len(tiles)}


def _get_market_map(db: Session, kind: str = "stocks", period: str = "day",
                    limit: int = 8) -> dict:
    """Карта рынка Обозревателя. Целиком (261 бумага) отдавать нельзя — ответ
    инструмента переотправляется на каждом шаге; отдаём лидеров, аутсайдеров и
    сводку по секторам, а деталь по конкретной бумаге модель добирает точечно."""
    kind = (kind or "stocks").lower()
    lim = max(3, min(int(limit or 8), 15))
    from app.services import market_maps
    try:
        if kind == "indices":
            rows = db.execute(text(
                "SELECT DISTINCT ON (ticker) ticker, date, close FROM index_history "
                "ORDER BY ticker, date DESC")).all()
            if not rows:
                return {"found": False, "reason": "истории индексов в базе нет"}
            out = []
            for r in rows:
                prev = db.execute(text(
                    "SELECT close FROM index_history WHERE ticker = :t AND date < :d "
                    "ORDER BY date DESC LIMIT 1"), {"t": r.ticker, "d": r.date}).first()
                chg = None
                if prev and _f(prev.close):
                    chg = round((float(r.close) / float(prev.close) - 1) * 100, 2)
                out.append({"ticker": r.ticker, "close": _f(r.close),
                            "date": _f(r.date), "change_pct": chg})
            return {"found": True, "kind": "indices", "indices": out,
                    "note": "IMOEX — ценовой индекс, MCFTR — полной доходности (с дивидендами)."}
        if kind == "valuation":
            data = market_maps.valuation(db)
            tiles = [t for s in (data.get("sectors") or []) for t in (s.get("tiles") or [])
                     if t.get("upside_pct") is not None]
            tiles.sort(key=lambda t: t["upside_pct"], reverse=True)
            keep = lambda t: {"ticker": t.get("ticker"), "name": t.get("name"),  # noqa: E731
                              "upside_pct": t.get("upside_pct"), "sector": t.get("sector")}
            return {"found": True, "kind": "valuation",
                    "most_undervalued": [keep(t) for t in tiles[:lim]],
                    "most_overvalued": [keep(t) for t in tiles[-lim:][::-1]],
                    "covered": len(tiles),
                    "note": "Потенциал — к справедливой цене Basis (модель), не прогноз рынка."}
        if kind == "spot":
            return {"found": True, "kind": "spot", **market_maps.spot_grid(db)}
        if kind in ("bonds", "funds", "futures"):
            fn = {"bonds": market_maps.heatmap_bonds, "funds": market_maps.heatmap_funds,
                  "futures": market_maps.heatmap_futures}[kind]
            data = fn(db)
            items = data.get("items") or [t for s in (data.get("sectors") or [])
                                          for t in (s.get("tiles") or [])]
            return {"found": True, "kind": kind, "count": len(items), "items": items[:lim * 2]}
        data = market_maps.heatmap(db, period if period in ("day", "week", "month") else "day")
        sectors = data.get("sectors") or []
        return {"found": True, "kind": "stocks", "period": data.get("period"),
                "sectors": [{"sector": s.get("sector"), "change_pct": s.get("change_pct"),
                             "count": len(s.get("tiles") or [])} for s in sectors],
                **_top_movers(sectors, lim)}
    except Exception as e:  # noqa: BLE001
        logger.exception("assistant: карта рынка %s упала", kind)
        return {"found": False, "reason": f"карта не собралась: {type(e).__name__}"}


# ============================== СТРЕСС-ТЕСТ И ДИАГНОЗ ==============================

def _portfolio_id(db: Session, user_id: int | None, guest_token: str | None) -> int | None:
    if user_id is not None:
        row = db.execute(text("SELECT id FROM portfolios WHERE user_id = :u ORDER BY id LIMIT 1"),
                         {"u": user_id}).first()
    elif guest_token:
        row = db.execute(text("SELECT id FROM portfolios WHERE guest_token = :g ORDER BY id LIMIT 1"),
                         {"g": guest_token}).first()
    else:
        return None
    return row.id if row else None


def _stress_test(db: Session, scenario: str | None = None, key_rate_pct: float | None = None,
                 fx_usdrub: float | None = None, oil_brent_usd: float | None = None,
                 apply_to_portfolio: bool = False, *, user_id: int | None = None,
                 guest_token: str | None = None) -> dict:
    """Стресс-тест: пресет («ставка 25%», «нефть 40$») или свои уровни. Уровни —
    АБСОЛЮТНЫЕ целевые значения, не сдвиги: так же, как в экране платформы."""
    from app.services import stress_numeric, stress_scenarios
    out = {"found": True}
    try:
        out["current_levels"] = stress_numeric.get_current_levels(db)
    except Exception:  # noqa: BLE001 — уровни справочные
        logger.exception("assistant: текущие уровни стресса не читаются")

    if scenario:
        try:
            res = stress_scenarios.build_scenario_result(db, scenario, None, None) or {}
            if res.get("error"):
                raise ValueError(res["error"])
            meta = res.get("scenario") or {}
            # Поле реакции в движке называется reaction_pct (не impact/change) —
            # промах в имени давал null у каждой компании при внешне рабочем ответе.
            short = lambda r: {"ticker": r.get("ticker"), "name": r.get("name"),  # noqa: E731
                               "reaction_pct": r.get("reaction_pct"),
                               "sector": r.get("sector"),
                               "coverage": r.get("coverage")}
            # 🔴 Среднего «по рынку» здесь намеренно нет: один выброс перекашивает
            # его в плюс, когда почти все задетые в минусе (боевой случай Ozon
            # +377 % в «Индексе рынка»). Отдаём разброс: секторы и края.
            out["scenario"] = {
                "key": meta.get("key", scenario), "label": meta.get("label"),
                "description": (meta.get("description") or "")[:400],
                "intensities": meta.get("intensities"),
                "sectors": (res.get("sectors") or [])[:12],
                "winners": [short(r) for r in (res.get("winners") or [])[:8]],
                "losers": [short(r) for r in (res.get("losers") or [])[:8]],
                "companies_with_signal": res.get("companies_with_signal"),
                "total_companies": res.get("total_companies")}
        except Exception as e:  # noqa: BLE001
            logger.exception("assistant: пресет стресса %s упал", scenario)
            out["scenario_error"] = f"{type(e).__name__}"
            out["available_scenarios"] = [s.get("key") for s in stress_scenarios.list_scenarios()]
    elif any(v is not None for v in (key_rate_pct, fx_usdrub, oil_brent_usd)):
        try:
            out["numeric"] = stress_numeric.numeric_impact(db, key_rate_pct, fx_usdrub,
                                                           oil_brent_usd)
        except Exception as e:  # noqa: BLE001
            logger.exception("assistant: числовой стресс упал")
            out["numeric_error"] = f"{type(e).__name__}"
    else:
        out["available_scenarios"] = stress_scenarios.list_scenarios()

    if apply_to_portfolio:
        pid = _portfolio_id(db, user_id, guest_token)
        if pid is None:
            out["portfolio"] = {"found": False,
                                "reason": "портфель доступен только в своём аккаунте — "
                                          "пользователь не авторизован или портфеля нет"}
        else:
            try:
                from app.services.portfolio import compute_portfolio_stress_v2
                res = compute_portfolio_stress_v2(db, pid, key_rate_pct, fx_usdrub, oil_brent_usd)
                if res is None:
                    out["portfolio"] = {"found": False,
                                        "reason": "по позициям портфеля нет коэффициентов "
                                                  "чувствительности — расчёт не покрывает их"}
                else:
                    out["portfolio"] = {
                        "found": True, "drop_pct": res.get("drop_pct"),
                        "value_loss_rub": res.get("value_loss"),
                        "coverage_pct": res.get("coverage_pct"),
                        "positions": (res.get("positions") or [])[:12],
                        "uncovered_tickers": res.get("uncovered_tickers"),
                        "assumption": res.get("assumption")}
            except Exception as e:  # noqa: BLE001
                logger.exception("assistant: стресс портфеля упал")
                out["portfolio"] = {"found": False, "reason": f"{type(e).__name__}"}
    out["note"] = ("🔴 Это МОДЕЛЬ, а не прогноз: считается чувствительность прибыли к "
                   "факторам при неизменном P/E. Средняя по рынку легко искажается одним "
                   "выбросом — смотри на разброс по секторам, а не только на итог.")
    return out


def _get_portfolio_diagnosis(db: Session, user_id: int | None, guest_token: str | None) -> dict:
    """Уже сгенерированный ИИ-диагноз портфеля + индекс качества.
    🔴 ЧИТАЕМ, а не генерируем: генерация — отдельный дорогой LLM-прогон по кнопке
    «Обновить диагноз», запускать его из ответа ассистента нельзя."""
    pid = _portfolio_id(db, user_id, guest_token)
    if pid is None:
        return {"found": False, "reason": "портфель доступен только в своём аккаунте — "
                                          "пользователь не авторизован или портфеля нет"}
    out = {"found": False, "portfolio_id": pid}
    try:
        from app.models.portfolio_diagnosis import PortfolioDiagnosis
        diag = db.query(PortfolioDiagnosis).filter_by(portfolio_id=pid).first()
        if diag:
            out.update({"found": True,
                        "shield": (diag.shield or [])[:6],
                        "vulnerabilities": (diag.vulnerabilities or [])[:6],
                        "summary": diag.summary,
                        "summary_type": diag.summary_type,
                        "generated_at": _f(diag.generated_at),
                        "portfolio_snapshot": diag.portfolio_snapshot or []})
    except Exception:  # noqa: BLE001
        logger.exception("assistant: диагноз портфеля не читается")
    try:
        from app.services.portfolio import compute_portfolio_metrics
        m = compute_portfolio_metrics(db, pid) or {}
        q = m.get("quality") or {}
        if isinstance(q, dict) and q:
            out["quality_index"] = {k: v for k, v in q.items()
                                    if k in ("score", "grade", "label", "verdict",
                                             "coverage_pct", "subindices", "dimensions")}
        # Риск-метрики лежат в строке «портфель целиком», причём каждая — не число,
        # а {value, ...}: разворачиваем в плоские числа, иначе модель пересказала бы
        # служебную обёртку вместо значения.
        prow = m.get("portfolio") or {}
        risk = {}
        for k in ("volatility", "var_95", "max_drawdown", "sharpe", "beta",
                  "return_total_3y", "alpha"):
            v = prow.get(k)
            if isinstance(v, dict):
                v = v.get("value")
            if v is not None:
                risk[k] = _f(v)
        if risk:
            out["risk"] = risk
        out["risk_scope"] = m.get("risk_metrics_scope")
    except Exception:  # noqa: BLE001 — метрики необязательны
        logger.exception("assistant: метрики портфеля не собрались")
    if not out["found"]:
        out["reason"] = ("диагноз по этому портфелю ещё не сгенерирован — его запускает "
                         "сам пользователь кнопкой на вкладке «ИИ-Диагноз»")
    return out


# ============================== СХЕМА ДЛЯ МОДЕЛИ ==============================

def _fn(name, desc, props, required=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required or []}}}


_S = {"type": "string"}
_N = {"type": "number"}
_I = {"type": "integer"}

TOOLS_SCHEMA = [
    _fn("search_platform_docs",
        "Поиск по ВСЕЙ аналитической прозе платформы: разборы вкладок карточек компаний "
        "(бизнес-модель, финансы, управление, рынки, макро, гео, институты), досье эмитентов "
        "облигаций, разборы выпусков/фондов/фьючерсов, методички Basis. Используй, когда "
        "вопрос про смысл/причины/формулировки, а не про число из таблицы.",
        {"query": {**_S, "description": "поисковый запрос на русском"},
         "entity": {**_S, "description": "тикер/SECID, если нужно искать внутри одной бумаги"},
         "entity_kind": {**_S, "enum": ["company", "bond_issuer", "bond", "fund", "future", "doc"]},
         "limit": _I}, ["query"]),
    _fn("read_platform_doc",
        "Прочитать найденный документ целиком по doc_id из выдачи search_platform_docs.",
        {"doc_id": _S, "max_chars": _I}, ["doc_id"]),
    _fn("search_bonds",
        "Поиск облигаций в базе платформы (3000+ выпусков): по названию/эмитенту/ISIN и по "
        "фильтрам доходности, дюрации, типа и валюты.",
        {"query": _S, "bond_type": {**_S, "enum": ["ofz", "corporate", "muni", "other"]},
         "issuer": _S, "min_ytm": _N, "max_ytm": _N, "max_duration_years": _N,
         "currency": {**_S, "description": "SUR (рубль), USD, CNY…"}, "limit": _I}, []),
    _fn("get_bond",
        "Полные параметры одного выпуска по SECID или ISIN + разбор аналитика и долговая "
        "нагрузка эмитента, если они есть.", {"secid": _S}, ["secid"]),
    _fn("search_funds", "Биржевые фонды (БПИФ/ETF): поиск и фильтр по типу и комиссии TER.",
        {"query": _S, "fund_type": {**_S, "enum": ["equity", "bonds", "gold", "money_market",
                                                   "currency", "mixed"]},
         "max_ter": _N, "limit": _I}, []),
    _fn("get_fund", "Один фонд по SECID: тип, бенчмарк, TER, ликвидность, разбор аналитика.",
        {"secid": _S}, ["secid"]),
    _fn("search_futures",
        "Фьючерсы MOEX: поиск по контракту/базовому активу, с ГО, номиналом и эффективным плечом.",
        {"query": _S, "asset_kind": {**_S, "enum": ["currency", "index", "commodity", "stock", "rate"]},
         "limit": _I}, []),
    _fn("get_spot_prices", "Валюта и драгметаллы на бирже: цена в рублях и изменение за день.",
        {"kind": {**_S, "enum": ["currency", "metal"]}}, []),
    _fn("screen_stocks",
        "Скрининг акций по метрикам платформы: сектор, P/E, дивдоходность, потенциал к "
        "справедливой цене Basis, бета, доходность за 3 года.",
        {"sector": _S, "max_pe": _N, "min_div_yield": _N, "min_upside_pct": _N,
         "sort_by": {**_S, "enum": ["upside", "pe", "div", "return"]}, "limit": _I}, []),
    _fn("get_company_card",
        "Карточка компании: живая цена, P/E и дивдоходность от текущей цены, справедливая "
        "цена Basis + проза выбранных вкладок.",
        {"ticker": _S,
         "tabs": {"type": "array", "items": {**_S, "enum": ["business", "finance", "governance",
                                                            "markets", "macro", "geo",
                                                            "institutions", "debt"]}},
         "max_chars_per_tab": _I}, ["ticker"]),
    _fn("get_dividends", "История дивидендных выплат компании (дата отсечки, сумма на акцию).",
        {"ticker": _S, "limit": _I}, ["ticker"]),
    _fn("get_earnings",
        "Вышедшие отчётности компании за 120 дней с кратким разбором Basis.",
        {"ticker": _S}, ["ticker"]),
    _fn("get_macro", "Макропоказатели РФ и траектория ключевой ставки из журнала решений ЦБ.",
        {"codes": {"type": "array", "items": _S}}, []),
    _fn("get_calendar", "Календарь событий: дивиденды, оферты, погашения, отчётности, макро.",
        {"days": _I, "ticker": _S,
         "event_type": {**_S, "enum": ["dividend", "bond_offer", "bond_maturity", "macro",
                                       "corporate", "earnings", "ipo", "expiration"]},
         "limit": _I}, []),
    _fn("get_portfolio",
        "Портфель ТЕКУЩЕГО пользователя: позиции, веса, стоимость. Если пользователь не "
        "авторизован — вернёт found:false, это нормально.", {}, []),
    _fn("get_news", "Лента новостей платформы с оценкой влияния; фильтр по тикеру или теме.",
        {"ticker": _S, "query": _S, "limit": _I}, []),
    _fn("get_financial_statements",
        "ПОЛНАЯ отчётность компании по годам: отчёт о прибылях (выручка, себестоимость, EBITDA, "
        "проценты, налог, чистая прибыль, маржи), баланс (активы, капитал, долг, чистый долг, "
        "оборотные/внеоборотные) и ОДДС (операционный/инвестиционный/финансовый поток, capex, "
        "свободный поток). Есть промежуточные периоды (квартал/полугодие) у крупнейших компаний. "
        "Используй, когда спрашивают конкретную строку отчётности или динамику за годы.",
        {"ticker": _S,
         "statement": {**_S, "enum": ["all", "income", "balance", "cash_flow", "bank"],
                       "description": "bank — процентные доходы/расходы банков"},
         "period": {**_S, "enum": ["annual", "interim"]},
         "lines": {"type": "array", "items": _S,
                   "description": "конкретные строки, напр. ['revenue','net_profit']"}},
        ["ticker"]),
    _fn("get_financial_model",
        "Прогнозная финансовая модель компании: драйверы с эластичностями, три сценария "
        "(база/бык/медведь) на 3 года — выручка, EBITDA, прибыль, FCF, EPS, дивиденд на акцию, "
        "веса сценариев, таблица чувствительности. Базовый сценарий пересчитан на живые нефть/"
        "курс/ставку. Построена не по всем компаниям.", {"ticker": _S}, ["ticker"]),
    _fn("get_barometer",
        "Барометр среды из Обозревателя: геополитический (13 субиндексов, сценарии по войне/"
        "санкциям/логистике, секторные флаги, очаги СВО/Ближний Восток/АТР) или "
        "институциональный (защита собственности, верховенство закона, госсектор, алерты). "
        "Это контекст РЫНКА, а не оценка отдельной бумаги.",
        {"kind": {**_S, "enum": ["geo", "inst"]},
         "section": {**_S, "description": "вернуть раздел целиком: subindices, scenario, "
                                          "regions, sector_flags, alerts, watchlist_30d"}}, []),
    _fn("get_market_map",
        "Карта рынка и индексы: движение акций по секторам (лидеры/аутсайдеры за день/неделю/"
        "месяц), карта недооценённости к справедливой цене Basis, срезы облигаций, фондов, "
        "фьючерсов, валюты и металлов, значения индексов (IMOEX, RTSI, MCFTR).",
        {"kind": {**_S, "enum": ["stocks", "valuation", "indices", "bonds", "funds",
                                 "futures", "spot"]},
         "period": {**_S, "enum": ["day", "week", "month"]}, "limit": _I}, []),
    _fn("stress_test",
        "Стресс-тест: как сценарий (ставка, нефть, курс, санкции) бьёт по компаниям и секторам. "
        "Без параметров вернёт список готовых пресетов. Можно задать свои АБСОЛЮТНЫЕ уровни "
        "(не сдвиги): ставка в %, курс ₽/$, нефть $/барр. С apply_to_portfolio=true считает "
        "просадку портфеля СПРАШИВАЮЩЕГО по его реальным позициям.",
        {"scenario": {**_S, "description": "ключ пресета из списка"},
         "key_rate_pct": _N, "fx_usdrub": _N, "oil_brent_usd": _N,
         "apply_to_portfolio": {"type": "boolean"}}, []),
    _fn("get_portfolio_diagnosis",
        "ИИ-диагноз портфеля текущего пользователя (что защищает, где уязвимости, резюме) + "
        "индекс качества и риск-метрики. Только читает уже сделанный диагноз — если его ещё "
        "не запускали, честно вернёт found:false.", {}, []),
]


def execute(db: Session, name: str, args: dict, *, user_id: int | None = None,
            guest_token: str | None = None) -> dict:
    """Диспетчер инструментов ассистента. Ошибку инструмента НЕ поднимаем наверх:
    цикл должен продолжаться, а модель — увидеть причину и попробовать иначе."""
    args = args or {}
    try:
        if name == "search_platform_docs":
            return _search_docs(args.get("query", ""), args.get("entity"),
                                args.get("entity_kind"), args.get("limit", 6))
        if name == "read_platform_doc":
            return _read_platform_doc(args.get("doc_id", ""), args.get("max_chars", 6000))
        if name == "search_bonds":
            return _search_bonds(db, args.get("query"), args.get("bond_type"), args.get("issuer"),
                                 args.get("min_ytm"), args.get("max_ytm"),
                                 args.get("max_duration_years"), args.get("currency"),
                                 args.get("limit", 12))
        if name == "get_bond":
            return _get_bond(db, args.get("secid", ""))
        if name == "search_funds":
            return _search_funds(db, args.get("query"), args.get("fund_type"),
                                 args.get("max_ter"), args.get("limit", 12))
        if name == "get_fund":
            return _get_fund(db, args.get("secid", ""))
        if name == "search_futures":
            return _search_futures(db, args.get("query"), args.get("asset_kind"),
                                   args.get("limit", 12))
        if name == "get_spot_prices":
            return _get_spot(db, args.get("kind"))
        if name == "screen_stocks":
            return _screen_stocks(db, args.get("sector"), args.get("max_pe"),
                                  args.get("min_div_yield"), args.get("min_upside_pct"),
                                  args.get("sort_by", "upside"), args.get("limit", 15))
        if name == "get_company_card":
            return _get_company_card(db, args.get("ticker", ""), args.get("tabs"),
                                     args.get("max_chars_per_tab", 2500))
        if name == "get_dividends":
            return _get_dividends(db, args.get("ticker", ""), args.get("limit", 10))
        if name == "get_earnings":
            return _get_earnings(db, args.get("ticker", ""))
        if name == "get_macro":
            return _get_macro(db, args.get("codes"))
        if name == "get_calendar":
            return _get_calendar(db, args.get("days", 30), args.get("ticker"),
                                 args.get("event_type"), args.get("limit", 15))
        if name == "get_portfolio":
            return _get_portfolio(db, user_id, guest_token)
        if name == "get_news":
            return _get_news(db, args.get("ticker"), args.get("query"), args.get("limit", 8))
        if name == "get_financial_statements":
            return _get_financial_statements(db, args.get("ticker", ""),
                                             args.get("statement", "all"),
                                             args.get("period", "annual"), args.get("lines"))
        if name == "get_financial_model":
            return _get_financial_model(db, args.get("ticker", ""))
        if name == "get_barometer":
            return _get_barometer(db, args.get("kind", "geo"), args.get("section"))
        if name == "get_market_map":
            return _get_market_map(db, args.get("kind", "stocks"), args.get("period", "day"),
                                   args.get("limit", 8))
        if name == "stress_test":
            return _stress_test(db, args.get("scenario"), args.get("key_rate_pct"),
                                args.get("fx_usdrub"), args.get("oil_brent_usd"),
                                bool(args.get("apply_to_portfolio")),
                                user_id=user_id, guest_token=guest_token)
        if name == "get_portfolio_diagnosis":
            return _get_portfolio_diagnosis(db, user_id, guest_token)
        return {"error": f"инструмент {name} не поддерживается"}
    except Exception as e:  # noqa: BLE001 — цикл важнее одного инструмента
        logger.exception("Ассистент: инструмент %s упал", name)
        return {"error": f"{type(e).__name__}: {e}"[:300]}


def make_executor(user_id: int | None, guest_token: str | None):
    """Замыкание для agent_runner: приватные данные привязаны к сессии спрашивающего."""
    def _exec(db: Session, name: str, args: dict) -> dict:
        return execute(db, name, args, user_id=user_id, guest_token=guest_token)
    return _exec


def tool_result_json(payload: dict, max_chars: int = 5000) -> str:
    s = json.dumps(payload, ensure_ascii=False, default=str)
    return s if len(s) <= max_chars else s[:max_chars] + "…(обрезано)"
