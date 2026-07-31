"""Авто-довесок квартальных/полугодовых данных к `financials.json.interim`.

Владелец (2026-07-31): цепочка «календарь → отчёт вышел → разбор в Обозревателе»
уже работает (report_watch.py), но карточка компании (вкладка «Финансы») и «Заметки
аналитика» на неё не реагировали. `financials.json` остаётся выверенным ГОДОВЫМ
слоем (ручной report-fetcher + git-коммит) — не трогаем его автоматикой. Довесок —
узкая, ДОПОЛНЯЮЩАЯ прослойка в БД (`InterimFinancialsOverlay`), по образцу уже
проверенного `CardProseOverlay`: рантайм-запись в сам JSON-файл на Timeweb
бессмысленна (перезатирается при следующем деплое), поэтому оверлей живёт в БД и
домешивается в `interim` ТОЛЬКО на чтении (`merge_into`), никогда не подменяя
периоды, которые уже есть в файле.

write()      — вызывается из report_watch.py::_store_report() после сохранения
               EarningsFigures; пишет строку оверлея (если гейты пройдены) +
               сигнал company_signals (trust="official" — иначе card_prose_patcher
               его не увидит, см. _fact_queue).
merge_into() — вызывается из companies.py::get_financials_json() перед
               _normalize_financials(); мутирует fin["interim"] in-place.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.earnings import EarningsReport, InterimFinancialsOverlay
from app.services import interim_periods

logger = logging.getLogger(__name__)

_HEADLINE_FIELDS = ("revenue", "ebitda", "net_profit", "net_debt")

# ранг источника — при равном fields_present более богатый источник побеждает
# при повторном апсерте того же периода (новость из Ленты не должна перетереть
# цифры, уже добытые из полного релиза)
_SOURCE_RANK = {"girbo": 3, "company_rss": 3, "agent_fetcher": 2, "report_watch": 2,
                "market_updates": 1}


def _fields_present(figures: dict) -> int:
    return sum(1 for k in _HEADLINE_FIELDS if figures.get(k) is not None)


def write(db: Session, report: EarningsReport, fig: dict, company_name: str | None = None) -> None:
    """`fig` — тот же dict, что `_store_report` собирает для EarningsFigures/Digest
    (ticker/period/standard/unit/revenue/ebitda/net_profit/net_debt/...). Молчаливо
    не пишет ничего при любой неоднозначности (annual/operating, нераспознанный
    период, < 2 непустых headline-полей) — fail-closed, не роняет вызывающий код."""
    try:
        _write(db, report, fig, company_name)
    except Exception:  # noqa: BLE001 — не должно ронять report_watch.refresh()
        db.rollback()
        logger.exception("interim_overlay.write: сбой для %s/%s", report.ticker, report.period)


def _write(db: Session, report: EarningsReport, fig: dict, company_name: str | None) -> None:
    if report.report_type != "quarter":
        return
    period_obj = interim_periods.report_period_to_interim(report.period, report.published_at)
    if period_obj is None:
        return
    figures = {k: fig.get(k) for k in _HEADLINE_FIELDS}
    fields_present = _fields_present(figures)
    if fields_present < 2:
        return

    existing = db.execute(
        select(InterimFinancialsOverlay).where(
            InterimFinancialsOverlay.ticker == report.ticker,
            InterimFinancialsOverlay.fiscal_year == period_obj["fiscal_year"],
            InterimFinancialsOverlay.start_m == period_obj["start_m"],
            InterimFinancialsOverlay.end_m == period_obj["end_m"],
        )
    ).scalar_one_or_none()

    source = "report_watch"
    if existing is not None:
        new_rank = _SOURCE_RANK.get(source, 0)
        old_rank = _SOURCE_RANK.get(existing.source or "", 0)
        better = fields_present > existing.fields_present or (
            fields_present == existing.fields_present and new_rank > old_rank)
        if not better:
            return
        existing.period_label = period_obj["period_label"]
        existing.period_type = period_obj["period_type"]
        existing.cumulative = period_obj["cumulative"]
        existing.standard = report.standard
        existing.end_date = period_obj["end_date"]
        existing.figures = figures
        existing.fields_present = fields_present
        existing.source = source
        existing.source_report_id = report.id
        existing.updated_at = datetime.now(timezone.utc)
        row = existing
        is_new = False
    else:
        row = InterimFinancialsOverlay(
            ticker=report.ticker, fiscal_year=period_obj["fiscal_year"],
            start_m=period_obj["start_m"], end_m=period_obj["end_m"],
            period_label=period_obj["period_label"], period_type=period_obj["period_type"],
            cumulative=period_obj["cumulative"], standard=report.standard,
            end_date=period_obj["end_date"], figures=figures, fields_present=fields_present,
            source=source, source_report_id=report.id,
        )
        db.add(row)
        is_new = True
    db.commit()

    from app.services.company_signals import _upsert as _signal_upsert
    name = company_name or report.ticker
    parts = []
    if figures.get("revenue") is not None:
        parts.append(f"выручка {figures['revenue']} млн ₽")
    if figures.get("ebitda") is not None:
        parts.append(f"EBITDA {figures['ebitda']} млн ₽")
    if figures.get("net_profit") is not None:
        parts.append(f"чистая прибыль {figures['net_profit']} млн ₽")
    if figures.get("net_debt") is not None:
        parts.append(f"чистый долг {figures['net_debt']} млн ₽")
    _signal_upsert(
        db, ticker=report.ticker, signal_type="earnings", card_tab="finance",
        importance="high", trust="official", internal=False,
        title=f"{name}: отчёт за {period_obj['period_label']} ({report.standard or 'отчётность'})"[:400],
        summary=(", ".join(parts) + ".")[:1000] if parts else None,
        source_key=report.source, source_url=report.source_url,
        published_at=report.published_at or date.today(),
        dedup_key=f"earnings_overlay:{report.id}",
    )
    logger.info("interim_overlay.write: %s %s%s", report.ticker, period_obj["period_label"],
                " (обновлено)" if not is_new else "")


# --- слияние в ответ /financials ------------------------------------------------

_UNIT_FACTORS = {"млн": 1.0, None: 1.0, "": 1.0, "млрд": 0.001,
                 "тыс": 1000.0, "тысячи": 1000.0, "тыс. руб.": 1000.0, "тыс руб": 1000.0}

# обычная компания vs банк — какие поля оверлея куда мапятся
_PLAIN_MAP = {
    "income_statement": {"revenue": "revenue", "ebitda": "ebitda", "net_profit": "net_profit"},
    "balance_sheet": {"net_debt": "net_debt"},
}
_BANK_MAP = {
    "bank_pnl": {"net_profit": "net_profit"},
}


def merge_into(db: Session, ticker: str, fin: dict) -> None:
    """Домешивает НОВЫЕ периоды из оверлея в `fin["interim"]` (мутирует `fin`
    in-place). Периоды, уже присутствующие в файле, НЕ трогает (файл — более
    выверенный слой). Синтезирует `interim`, если в файле его вообще нет.
    Fail-closed: любая неопределённость (неизвестная единица измерения) —
    merge для тикера пропускается целиком, а не показывается «примерно»."""
    try:
        _merge_into(db, ticker, fin)
    except Exception:  # noqa: BLE001 — обогащение не должно ронять отдачу /financials
        logger.exception("interim_overlay.merge_into: сбой для %s", ticker)


def _merge_into(db: Session, ticker: str, fin: dict) -> None:
    rows = db.execute(
        select(InterimFinancialsOverlay)
        .where(InterimFinancialsOverlay.ticker == ticker)
        .order_by(InterimFinancialsOverlay.end_date)
    ).scalars().all()
    if not rows:
        return

    unit = (fin.get("meta") or {}).get("unit")
    unit_key = unit if unit in _UNIT_FACTORS else (unit or "").strip().lower()
    if unit_key not in _UNIT_FACTORS:
        logger.warning("interim_overlay.merge_into: неизвестная unit=%r у %s — merge пропущен",
                       unit, ticker)
        return
    factor = _UNIT_FACTORS[unit_key]

    file_interim = fin.get("interim")
    file_periods = file_interim.get("periods") if isinstance(file_interim, dict) else None
    file_periods = file_periods if isinstance(file_periods, list) else []
    file_canon = interim_periods.canon_periods(file_periods)
    file_keys = {(c["year"], c["start_m"], c["end_m"]) for c in file_canon if c}
    frontier = None
    for p in file_periods:
        ed = p.get("end_date") if isinstance(p, dict) else None
        if ed:
            try:
                d = date.fromisoformat(str(ed)[:10])
            except ValueError:
                continue
            if frontier is None or d > frontier:
                frontier = d

    candidates = []
    for r in rows:
        key = (r.fiscal_year, r.start_m, r.end_m)
        if key in file_keys:
            continue
        if frontier is not None and r.end_date <= frontier:
            continue
        candidates.append(r)
    if not candidates:
        return

    is_bank = (fin.get("meta") or {}).get("profile") == "bank"
    field_map = _BANK_MAP if is_bank else _PLAIN_MAP

    interim = fin.get("interim") if isinstance(fin.get("interim"), dict) else {}
    periods = list(interim.get("periods") or [])
    series = {}
    for section in field_map:
        block = interim.get(section) if isinstance(interim.get(section), dict) else {}
        series[section] = {k: list(v) if isinstance(v, list) else []
                            for k, v in block.items()}
        for dest_key in field_map[section].values():
            series[section].setdefault(dest_key, [])

    base_len = len(periods)
    new_period_objs = []
    for i, r in enumerate(candidates):
        new_period_objs.append({
            "label": r.period_label, "type": r.period_type, "fiscal_year": r.fiscal_year,
            "end_date": r.end_date.isoformat(), "cumulative": r.cumulative,
            "standard": r.standard, "source": "auto_overlay",
        })
        for section, mapping in field_map.items():
            for src_key, dest_key in mapping.items():
                arr = series[section][dest_key]
                while len(arr) < base_len:
                    arr.append(None)
                v = r.figures.get(src_key)
                arr.append(v * factor if isinstance(v, (int, float)) else v)

    for section in field_map:
        for dest_key, arr in series[section].items():
            while len(arr) < base_len + len(candidates):
                arr.append(None)

    all_periods = periods + new_period_objs
    order = sorted(range(len(all_periods)),
                   key=lambda i: (all_periods[i].get("end_date") or ""))
    interim["periods"] = [all_periods[i] for i in order]
    for section in field_map:
        block = interim.get(section) if isinstance(interim.get(section), dict) else {}
        for dest_key, arr in series[section].items():
            block[dest_key] = [arr[i] for i in order]
        interim[section] = block

    n = len(candidates)
    note = (f"{n} период(а) добавлены автоматически из потока отчётов: только "
            f"выручка/EBITDA/прибыль/чистый долг, предварительно, не сверено аналитиком.")
    interim["data_flags"] = list(interim.get("data_flags") or []) + [note]
    fin["interim"] = interim
