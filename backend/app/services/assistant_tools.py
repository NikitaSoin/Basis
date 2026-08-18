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
        if name == "get_macro":
            return _get_macro(db, args.get("codes"))
        if name == "get_calendar":
            return _get_calendar(db, args.get("days", 30), args.get("ticker"),
                                 args.get("event_type"), args.get("limit", 15))
        if name == "get_portfolio":
            return _get_portfolio(db, user_id, guest_token)
        if name == "get_news":
            return _get_news(db, args.get("ticker"), args.get("query"), args.get("limit", 8))
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
