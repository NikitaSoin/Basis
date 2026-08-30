"""Ежедневная добыча документов отчётности у тех, кто отчитался.

Замысел владельца (2026-08-29) дословно: «смотрим в календарь, видим отчёт
Северстали завтра, в этот день ИИ отправляется на сайт Северстали, заходит в
раздел инвесторам, находит там отчётность и анализирует». Здесь это и живёт.

Почему отдельной задачей, а не внутри report_watch. У них разная цена и разный
темп: report_watch ходит раз в два часа по всем и читает НОВОСТИ (дёшево), а
здесь скачивается и разбирается документ на десятки тысяч знаков (дорого).
Поэтому — раз в сутки, вечером, только по тем, у кого отчёт вышел сегодня или
вчера, и с жёстким потолком компаний за прогон.

Что считается «отчитался»: событие календаря типа earnings на нужную дату ИЛИ
свежая запись в earnings_reports. Второе важно, потому что у большинства отчётов
календарного события нет вовсе — их детектит лента (замер августа: 20 записей из
ленты против 5 из календаря).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Потолок на прогон: документ + разбор — это минуты и деньги на модель. Лучше
# растянуть на несколько дней, чем сжечь бюджет за один вечер.
MAX_PER_RUN = 6


def _candidates(db: Session, days_back: int) -> list[str]:
    since = date.today() - timedelta(days=days_back)
    rows = db.execute(text("""
        SELECT DISTINCT t.ticker FROM (
            SELECT ticker FROM calendar_events
             WHERE event_type = 'earnings' AND event_date BETWEEN :since AND :today
            UNION
            SELECT ticker FROM earnings_reports
             WHERE published_at >= :since_ts
        ) t
        JOIN companies c ON c.ticker = t.ticker
        WHERE t.ticker IS NOT NULL
        ORDER BY t.ticker
    """), {"since": since, "today": date.today(), "since_ts": since}).all()
    return [r.ticker for r in rows]


def _already_harvested(db: Session, ticker: str, days_back: int) -> bool:
    """Не ходить второй раз за тем же: если по свежему периоду уже лежит разбор
    ИЗ ДОКУМЕНТА, повторная добыча ничего не добавит, а денег стоит."""
    row = db.execute(text("""
        SELECT 1 FROM earnings_reports
         WHERE ticker = :t AND source = 'ir_document'
           AND published_at >= :since LIMIT 1
    """), {"t": ticker, "since": date.today() - timedelta(days=days_back)}).first()
    return row is not None


def run(db: Session, days_back: int = 2, limit: int = MAX_PER_RUN) -> dict:
    """Пройти по отчитавшимся и добыть у них документ отчётности."""
    from app.services import ir_registry

    todo = _candidates(db, days_back)
    out = {"candidates": len(todo), "processed": [], "skipped": []}
    for ticker in todo:
        if len(out["processed"]) >= limit:
            out["stopped_at_limit"] = True
            break
        try:
            if _already_harvested(db, ticker, days_back):
                out["skipped"].append({"ticker": ticker, "why": "документ уже разобран"})
                continue
            res = ir_registry.harvest(db, ticker, since=date.today(), extract=True)
        except Exception as e:  # noqa: BLE001 — один эмитент не должен ронять прогон
            logger.exception("harvest_job: %s упал", ticker)
            out["processed"].append({"ticker": ticker, "ok": False,
                                     "reason": type(e).__name__})
            continue
        item = {"ticker": ticker, "ok": res.get("ok"), "stage": res.get("stage"),
                "via_search": res.get("via_search"), "rebound": res.get("rebound_from")}
        extracted = res.get("extracted") or {}
        if extracted:
            forms = {f: len([v for v in (extracted.get(f) or {}).values() if v is not None])
                     for f in ("income_statement", "balance_sheet", "cash_flow")}
            item["period"] = extracted.get("period_label")
            item["lines"] = forms
            item["one_offs"] = len(extracted.get("one_offs") or [])
        else:
            item["reason"] = res.get("reason")
        out["processed"].append(item)
    logger.info("harvest_job: кандидатов %s, разобрано %s",
                out["candidates"], sum(1 for p in out["processed"] if p.get("ok")))
    return out
