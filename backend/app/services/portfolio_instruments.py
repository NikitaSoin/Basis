"""Оценка non-equity позиций портфеля (облигации/фьючерсы/фонды/денежные средства).

Раздельно от app/services/portfolio.py (там — equity-путь через Quote/
company_metrics, риск-метрики, корреляции). Здесь — только ТЕКУЩАЯ СТОИМОСТЬ
позиции по классу актива, для распределения по классам активов/весов/
концентрации. Риск-метрики (бета/волатильность/корреляции) для non-equity
НЕ считаются в этой раскатке — честно возвращаются null, а не выдуманное
число (не путать «не посчитано» с «риска нет»).

Источники цены по классу:
- bond: instrument_history (asset_class='bond') — close это % НОМИНАЛА,
  грязная цена = close/100 × face_value + accrued_int (bonds.face_value).
- future: instrument_history (asset_class='future') settle — расчётная цена
  клиринга в пунктах. «Стоимость» позиции для весов портфеля — НЕ нотионал
  (это дало бы обманчиво огромный вес при малом реальном риске), а
  ГО × количество контрактов (futures.initial_margin) — то, что реально
  иммобилизовано. P&L считается отдельно через шаг цены (futures.step_price).
- fund: funds.last_price (свежее, чем instrument_history — обновляется
  отдельным джобом) с fallback на instrument_history.close.
- cash: номинал, price всегда 1, никакой рыночной переоценки.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.bond import Bond
from app.models.fund import Fund
from app.models.future import Future
from app.models.instrument import InstrumentHistory
from app.models.portfolio import PortfolioPosition

ASSET_CLASS_LABEL = {
    "bond": "Облигации",
    "future": "Фьючерсы",
    "fund": "Фонды",
    "cash": "Денежные средства",
}


def _latest_instrument_history(db: Session, asset_class: str, secids: list[str]) -> dict[str, InstrumentHistory]:
    if not secids:
        return {}
    rows = (
        db.query(InstrumentHistory)
        .filter(InstrumentHistory.asset_class == asset_class, InstrumentHistory.secid.in_(secids))
        .order_by(InstrumentHistory.secid, InstrumentHistory.date.desc())
        .all()
    )
    out: dict[str, InstrumentHistory] = {}
    for r in rows:
        if r.secid not in out:  # первая по secid = самая свежая (сортировка выше)
            out[r.secid] = r
    return out


def value_non_equity_positions(db: Session, positions: list[PortfolioPosition]) -> list[dict]:
    """Возвращает по одной записи на позицию: ticker/name/sector(=класс)/
    value/quantity/instrument_type/price/data_flag (если цену найти не
    удалось — value=None, честно, не «0»)."""
    by_type: dict[str, list[PortfolioPosition]] = {}
    for p in positions:
        by_type.setdefault(p.instrument_type, []).append(p)

    out: list[dict] = []

    # ── Денежные средства: номинал, никакой рыночной переоценки ──
    for p in by_type.get("cash", []):
        qty = float(p.quantity)
        out.append({
            "id": p.id, "ticker": p.currency or "RUB", "name": f"Денежные средства ({p.currency or 'RUB'})",
            "company_id": None, "secid": None, "sector": ASSET_CLASS_LABEL["cash"], "instrument_type": "cash",
            "value": round(qty, 2), "quantity": qty, "avg_buy_price": 1.0, "price": 1.0, "data_flag": None,
        })

    # ── Фонды: last_price свежее, fallback на instrument_history ──
    fund_positions = by_type.get("fund", [])
    if fund_positions:
        secids = [p.secid for p in fund_positions]
        funds = {f.secid: f for f in db.query(Fund).filter(Fund.secid.in_(secids)).all()}
        hist = _latest_instrument_history(db, "fund", secids)
        for p in fund_positions:
            f = funds.get(p.secid)
            price_as_of = None
            if f and f.last_price is not None:
                price = float(f.last_price)
                price_as_of = f.updated_at.date().isoformat() if f.updated_at else None
            elif p.secid in hist and hist[p.secid].close is not None:
                price = float(hist[p.secid].close)
                price_as_of = hist[p.secid].date.isoformat()
            else:
                price = None
            qty = float(p.quantity)
            out.append({
                "id": p.id, "ticker": p.secid, "name": f.short_name if f else p.secid,
                "company_id": None, "secid": p.secid, "sector": ASSET_CLASS_LABEL["fund"], "instrument_type": "fund",
                "value": round(qty * price, 2) if price is not None else None,
                "quantity": qty, "avg_buy_price": float(p.avg_buy_price), "price": price,
                "price_as_of": price_as_of,
                "data_flag": None if price is not None else "нет актуальной цены фонда",
            })

    # ── Облигации: грязная цена = %номинала × face_value + НКД ──
    bond_positions = by_type.get("bond", [])
    if bond_positions:
        secids = [p.secid for p in bond_positions]
        bonds = {b.secid: b for b in db.query(Bond).filter(Bond.secid.in_(secids)).all()}
        hist = _latest_instrument_history(db, "bond", secids)
        for p in bond_positions:
            b = bonds.get(p.secid)
            h = hist.get(p.secid)
            price = clean = accrued = None
            price_as_of = None
            accrued = round(float(h.accrued_int), 2) if h and h.accrued_int is not None else 0.0
            # Предпочитаем ЖИВУЮ чистую цену (bonds.last_price, тянется через
            # Tinkoff каждые 5 мин в торговые часы для покрытых бумаг — см.
            # asset_data.refresh_bond_live_prices), если она СВЕЖЕЕ дневного
            # среза MOEX ISS (instrument_history, T+1). НКД по-прежнему из
            # instrument_history — у Tinkoff нет отдельного накопленного
            # купонного дохода в этом ответе, а он меняется предсказуемо
            # день в день, дневной точности достаточно.
            if b and b.face_value and b.last_price is not None and b.updated_at is not None \
                    and (not h or b.updated_at.date() >= h.date):
                clean = round(float(b.last_price) / 100 * float(b.face_value), 2)
                price_as_of = b.updated_at.date().isoformat()
            elif b and b.face_value and h and h.close is not None:
                clean = round(float(h.close) / 100 * float(b.face_value), 2)
                price_as_of = h.date.isoformat()
            if clean is not None:
                price = clean + accrued
            qty = float(p.quantity)
            out.append({
                "id": p.id, "ticker": p.secid, "name": b.short_name if b else p.secid,
                "company_id": None, "secid": p.secid, "sector": ASSET_CLASS_LABEL["bond"], "instrument_type": "bond",
                "isin": b.isin if b else None, "issuer_ticker": b.issuer_ticker if b else None,
                "value": round(qty * price, 2) if price is not None else None,
                "quantity": qty, "avg_buy_price": float(p.avg_buy_price), "price": price,
                # "price" остаётся ГРЯЗНОЙ ценой (для value/P&L — реальная сумма расчётов
                # при покупке/продаже сегодня). Но брокеры/MOEX ПОВСЕМЕСТНО показывают
                # ЧИСТУЮ цену как "цену облигации", а НКД — отдельной строкой; наш "price"
                # молча совмещал оба числа, из-за чего цена на сайте казалась владельцу
                # "не той" при сверке с реальной котировкой (нашли 2026-07-24: ОФЗ 26247
                # чистая ~818₽, у нас показывалась грязная ~836₽ без разбивки — не баг
                # свежести данных, а конвенция отображения). price_clean/accrued_interest —
                # для честного разбора на фронте, price_clean не заменяет price.
                "price_clean": clean,
                "accrued_interest": accrued,
                "price_as_of": price_as_of,
                "data_flag": None if price is not None else "нет актуальной цены облигации",
            })

    # ── Фьючерсы: вес портфеля = ГО (реально иммобилизованное), не нотионал ──
    future_positions = by_type.get("future", [])
    if future_positions:
        secids = [p.secid for p in future_positions]
        futures = {f.secid: f for f in db.query(Future).filter(Future.secid.in_(secids)).all()}
        for p in future_positions:
            f = futures.get(p.secid)
            margin = float(f.initial_margin) if f and f.initial_margin is not None else None
            qty = float(p.quantity)
            out.append({
                "id": p.id, "ticker": p.secid, "name": f.short_name if f else p.secid,
                "company_id": None, "secid": p.secid, "sector": ASSET_CLASS_LABEL["future"], "instrument_type": "future",
                "value": round(qty * margin, 2) if margin is not None else None,
                "quantity": qty, "avg_buy_price": float(p.avg_buy_price), "price": float(f.settle_price) if f and f.settle_price is not None else None,
                "data_flag": None if margin is not None else "нет данных по ГО контракта",
            })

    return out


def compute_non_equity_pnl(db: Session, position: PortfolioPosition) -> dict | None:
    """Нереализованный P&L non-equity позиции. Формула по классу — см. docstring
    модуля (грязная цена для облигаций, шаг цены для фьючерсов, 0 для кэша)."""
    if position.instrument_type == "cash":
        return {"unrealized_pnl": 0.0, "unrealized_pnl_pct": 0.0}

    if position.instrument_type == "bond":
        b = db.query(Bond).filter(Bond.secid == position.secid).first()
        h = (db.query(InstrumentHistory)
             .filter(InstrumentHistory.asset_class == "bond", InstrumentHistory.secid == position.secid)
             .order_by(InstrumentHistory.date.desc()).first())
        if not (b and b.face_value and h and h.close is not None):
            return None
        current = float(h.close) / 100 * float(b.face_value) + float(h.accrued_int or 0)
        buy = float(position.avg_buy_price)
        pnl = (current - buy) * float(position.quantity)
        return {"unrealized_pnl": round(pnl, 2), "unrealized_pnl_pct": round((current / buy - 1) * 100, 2) if buy else None}

    if position.instrument_type == "future":
        f = db.query(Future).filter(Future.secid == position.secid).first()
        if not (f and f.settle_price is not None and f.min_step and f.step_price):
            return None
        # P&L = число шагов цены × стоимость шага × количество контрактов
        price_steps = (float(f.settle_price) - float(position.avg_buy_price)) / float(f.min_step)
        pnl = price_steps * float(f.step_price) * float(position.quantity)
        return {"unrealized_pnl": round(pnl, 2), "unrealized_pnl_pct": None}  # % бессмысленен без нотионала

    if position.instrument_type == "fund":
        fnd = db.query(Fund).filter(Fund.secid == position.secid).first()
        if not (fnd and fnd.last_price is not None):
            return None
        current = float(fnd.last_price)
        buy = float(position.avg_buy_price)
        pnl = (current - buy) * float(position.quantity)
        return {"unrealized_pnl": round(pnl, 2), "unrealized_pnl_pct": round((current / buy - 1) * 100, 2) if buy else None}

    return None
