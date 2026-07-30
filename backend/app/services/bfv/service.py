"""Оркестратор BFV-D для карточки/скрининга: тикер + БД → живой расчёт.

Собирает входы (financials/governance/institutions/geo-барометр из файлов; живую
цену из quotes, кривую ОФЗ и бету из market_params/company_metrics) и зовёт
compute.compute_bfv. Кэша нет (движок — миллисекунды): справедливая цена
пересчитывается на КАЖДЫЙ запрос от живых цены/кривой/беты — «не статичное число».
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.bfv.compute import compute_bfv, DEFAULT_REQUIRED_SPREAD

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent.parent / "companies"
_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _live_price(db: Session, ticker: str) -> float | None:
    try:
        r = db.execute(text(
            "SELECT q.close FROM quotes q JOIN companies c ON c.id = q.company_id "
            "WHERE c.ticker = :t AND q.close IS NOT NULL "
            "ORDER BY q.date DESC LIMIT 1"), {"t": ticker}).first()
        return float(r[0]) if r and r[0] else None
    except Exception:  # noqa: BLE001
        return None


def _live_beta(db: Session, ticker: str) -> float | None:
    try:
        # 🔴 company_metrics идентифицируется по TICKER (unique-колонка), колонки
        # company_id в ней НЕТ вовсе — прежний JOIN по cm.company_id падал, ошибка
        # глоталась except-ом, и бета молча подменялась дефолтом β=1.0 у ВСЕХ бумаг.
        # То есть порог доходности не различал Сбер и микрокап, хотя реальные беты в
        # таблице есть (проверено 2026-07-30: 261 из 261, у SBER 0,55).
        r = db.execute(text(
            "SELECT beta FROM company_metrics "
            "WHERE ticker = :t AND beta IS NOT NULL LIMIT 1"), {"t": ticker}).first()
        return float(r[0]) if r and r[0] is not None else None
    except Exception:  # noqa: BLE001
        return None


def _ofz_curve(db: Session) -> list[tuple[float, float]] | None:
    """Полная G-кривая ОФЗ из market_params (ключ ofz_curve, JSON в note). Фолбэк —
    построить 2-точечную из risk_free_1y/10y (проценты → доли), если полной ещё нет
    (крон persistence добавлен позже; до первого прогона крона — фолбэк)."""
    try:
        r = db.execute(text("SELECT note FROM market_params WHERE key='ofz_curve'")).first()
        if r and r[0]:
            pts = json.loads(r[0])
            return [(float(a), float(b)) for a, b in pts]
    except Exception:  # noqa: BLE001
        pass
    try:
        rows = db.execute(text(
            "SELECT key, value FROM market_params WHERE key IN ('risk_free_1y','risk_free_10y')"
        )).all()
        m = {k: float(v) for k, v in rows}
        curve = []
        if "risk_free_1y" in m:
            curve.append((1.0, m["risk_free_1y"] / 100.0))
        if "risk_free_10y" in m:
            curve.append((10.0, m["risk_free_10y"] / 100.0))
        return curve or None
    except Exception:  # noqa: BLE001
        return None


def get_bfv(db: Session, ticker: str, required_spread: float = DEFAULT_REQUIRED_SPREAD) -> dict | None:
    """Живой BFV для тикера. None — компании нет; словарь со status иначе."""
    ticker = ticker.upper()
    cdir = COMPANIES_DIR / ticker
    if not (cdir / "financials.json").exists():
        return None
    fin = _load_json(cdir / "financials.json")
    # 🔴 Капитализация — по всем классам акций эмитента (share_capital.py). BFV берёт
    # BVPS как «цена / P/B», поэтому заниженная капитализация задирала BVPS и вместе с
    # ним справедливую цену: у TRNFP P/B 0,07 вместо 0,34 — почти впятеро.
    try:
        from app.services.share_capital import apply_issuer_capital
        apply_issuer_capital(db, ticker, fin)
    except Exception:  # noqa: BLE001
        pass
    gov = _load_json(cdir / "governance.json")
    inst = _load_json(cdir / "institutions.json")
    market = _load_json(cdir / "market.json")   # valuation_inputs (архетип/рост/маржа) для BFV-F
    barometer = _load_json(_CONFIG_DIR / "geo_barometer.json")

    # ручной слой суждений аналитика (§20), если заведён — не перетирается компилятором
    overrides = _load_json(cdir / "bfv_overrides.json") or None

    price = _live_price(db, ticker)
    if price is None:
        price = fin.get("meta", {}).get("last_price")  # фолбэк на снапшот
    shares = fin.get("meta", {}).get("shares_outstanding")

    return compute_bfv(
        fin, gov, inst, barometer, market=market,
        shares_outstanding=shares, live_price=price,
        ofz_curve=_ofz_curve(db), beta=_live_beta(db, ticker),
        required_spread=required_spread, overrides=overrides,
    )
