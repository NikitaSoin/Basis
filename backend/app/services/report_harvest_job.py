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


def store_harvested(db: Session, ticker: str, data: dict, doc: dict,
                    force: bool = False) -> str:
    """Записать разобранный документ так же, как записываются отчёты из новостей.

    Переиспользуем ядро report_watch._store_report через `fig_override` — это
    предусмотренный там путь для готовых цифр без LLM-угадывания (им же ходит
    ГИР БО). Свой параллельный путь записи означал бы вторую логику слияния с
    карточкой и второй набор ошибок.

    Возвращает статус ядра (created/updated/…) либо причину отказа."""
    from app.models.company import Company
    from app.models.earnings import EarningsReport
    from app.services import report_deep_extract as deep
    from app.services.report_watch import _store_report

    period = (data.get("period_label") or "").strip()
    if not period:
        return "skip_no_period"
    figures = deep.to_overlay_figures(data)
    if not figures:
        # Пусто бывает по делу: масштаб не сошёлся с карточкой (см.
        # normalize_scale) — тогда лучше не писать ничего. Но «масштаб не сошёлся»
        # и «документ ничего не дал» лечатся по-разному, а один общий статус
        # заставляет каждый раз лезть в логи — разводим их сразу.
        if data.get("scale_suspect"):
            return "skip_scale_suspect"
        return "skip_no_figures"

    company = db.query(Company).filter(Company.ticker == ticker).first()
    if company is None:
        return "skip_no_company"

    standard = data.get("standard") or "МСФО"
    exists = db.query(EarningsReport).filter(
        EarningsReport.ticker == ticker, EarningsReport.period == period,
        EarningsReport.standard == standard).first()
    if exists is not None and exists.source == "ir_document" and not force:
        # Уже разобран этим же путём — повторять незачем. При force перезаписываем:
        # разбор мог стать лучше, и старая запись иначе осталась бы навсегда.
        return "already_stored"

    figures = dict(figures)
    figures["has_figures"] = True
    figures["is_company_report"] = True
    # 🔴 Ядро записи обращается к fig["ticker"]/["period"]/["name"] по КЛЮЧУ, а не
    # через .get — без них падает KeyError и весь разбор пропадает (на бою так
    # потерялась Инарктика: документ разобран, 9 строк P&L, а запись «error»).
    figures["ticker"] = ticker
    figures["period"] = period
    figures["name"] = company.name
    # 🔴 Ядро кладёт fig_override целиком в EarningsFigures.extracted_fields.
    # Если отдать только восемь плоских чисел, вся глубина документа (построчные
    # формы, разовые факторы, ставка налога, оборотный капитал) исчезнет сразу
    # после лога — ради неё документ и качали. Поэтому прикладываем полный разбор:
    # лишние ключи ядро игнорирует, а в базе они сохранятся.
    figures["deep"] = {k: data.get(k) for k in (
        "income_statement", "balance_sheet", "cash_flow", "one_offs", "tax_note",
        "working_capital_note", "derived", "currency", "unit_in_source",
        "scale_factor_applied", "scale_fixed_by") if data.get(k) is not None}
    figures["deep"]["document_url"] = (doc.get("url") or "")[:500]
    # Годовой период («2025») от квартального отличается наличием квартальной
    # метки: витрина показывает квартальные периоды отдельной шкалой.
    is_annual = period.isdigit() and len(period) == 4
    report = exists or EarningsReport(
        ticker=ticker, period=period, standard=standard,
        report_type="annual" if is_annual else "quarter",
        published_at=date.today(), source="ir_document",
        source_url=(doc.get("url") or "")[:1000])
    if exists is not None:
        # Документ первоисточника точнее пересказа — обновляем источник.
        report.source = "ir_document"
        report.source_url = (doc.get("url") or "")[:1000]
        # 🔴 Ядро записи рассчитано на СОЗДАНИЕ: оно всегда добавляет новые
        # EarningsFigures и EarningsDigest, а связь с отчётом один-к-одному.
        # Для уже существующего отчёта это UniqueViolation, и разбор пропадал
        # целиком (на бою так потерялись Инарктика и Эталон при живом разборе:
        # 9-10 строк P&L, статус «error»). Поэтому старые снимаем — их место
        # займут те, что построены по документу.
        from app.models.earnings import EarningsDigest, EarningsFigures
        db.query(EarningsFigures).filter(EarningsFigures.report_id == exists.id).delete()
        db.query(EarningsDigest).filter(EarningsDigest.report_id == exists.id).delete()
        db.flush()
    try:
        return _store_report(db, report, company, text_blob=None, is_operational=False,
                             price_now=None, mcap=None, fig_override=figures)
    except Exception:  # noqa: BLE001 — запись не должна ронять прогон
        db.rollback()
        logger.exception("harvest_job: запись отчёта %s/%s не удалась", ticker, period)
        return "error"


def run(db: Session, days_back: int = 2, limit: int = MAX_PER_RUN,
        force: bool = False) -> dict:
    """Пройти по отчитавшимся и добыть у них документ отчётности.

    force=True переразбирает даже тех, у кого документ уже разобран. Нужен, когда
    улучшился САМ разбор: старые записи сделаны прежней версией и обновятся только
    повторным проходом (иначе карточка навсегда останется с тем, что удалось
    извлечь в первый раз)."""
    from app.services import ir_registry

    todo = _candidates(db, days_back)
    out = {"candidates": len(todo), "processed": [], "skipped": []}
    for ticker in todo:
        if len(out["processed"]) >= limit:
            out["stopped_at_limit"] = True
            break
        try:
            if not force and _already_harvested(db, ticker, days_back):
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
            # Разобрали — значит доводим до карточки, иначе добыча остаётся
            # красивым логом, которого пользователь не видит.
            item["stored"] = store_harvested(db, ticker, extracted,
                                             res.get("document") or {}, force=force)
        else:
            item["reason"] = res.get("reason")
        out["processed"].append(item)
    logger.info("harvest_job: кандидатов %s, разобрано %s",
                out["candidates"], sum(1 for p in out["processed"] if p.get("ok")))
    return out
