"""Связка трёх слоёв: документ → статьи → карточка.

    report_documents.py   добыть файл отчётности (центр раскрытия / IR-сайт)
    statement_extract.py  извлечь статьи и проверить тождества
    ЭТОТ МОДУЛЬ           привести к единицам карточки и положить в оверлей

Почему записываем в оверлей, а не в `financials.json`. Файл — выверенный аналитиком
слой, и автомат туда не допущен намеренно (аудит показал, что платформа ломается на
стыках: два разных числа на одной карточке хуже, чем одно с оговоркой). Оверлей же
дозаполняет ТОЛЬКО периоды, которых в файле нет, и помечает их как предварительные —
см. interim_overlay.merge_into.

🔴 Единицы. Извлекатель возвращает масштаб отдельным полем («тыс»/«млн»/«млрд»), как
он написан в шапке таблицы. Оверлей хранит млн ₽. Пересчёт делает КОД, а не модель:
просить модель пересчитать — тот самый шаг, на котором в проекте появлялись ошибки в
1000 раз. Не распознали единицу — период не пишем вовсе.

🔴 Валюта. Отчётность в долларах (у части эмитентов) в рублёвую витрину не годится:
курс на дату отчёта здесь неизвестен, а пересчёт по текущему исказил бы прошлый
период. Не RUB — отказ, честный и явный.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# во сколько раз домножить, чтобы получить млн ₽ — единицу оверлея
_TO_MLN = {"тыс": 0.001, "млн": 1.0, "млрд": 1000.0}

# Что из извлечённых статей едет на карточку. Ключи СПРАВА — те, которые читает
# FinanceTab (bs.total_assets, cf.cfo и т.д.); под своим именем число доехало бы до
# карточки и не отрисовалось ни в одной строке — эти грабли уже были с
# operating_cash_flow, см. interim_overlay._PLAIN_MAP.
_CARD_FIELDS = {
    "income_statement": {
        "revenue": "revenue", "gross_profit": "gross_profit",
        "operating_profit": "operating_profit", "ebitda": "ebitda",
        "net_profit": "net_profit",
    },
    "balance_sheet": {
        "total_assets": "total_assets", "equity": "total_equity",
        "total_liabilities": "total_liabilities", "cash": "cash",
        "long_term_debt": "long_term_debt", "short_term_debt": "short_term_debt",
        "current_assets": "current_assets", "non_current_assets": "non_current_assets",
    },
    "cash_flow": {
        "cfo": "cfo", "cfi": "cfi", "cff": "cff", "capex": "capex",
        "net_change_in_cash": "net_change_in_cash",
    },
}


def _flatten(data: dict, factor: float) -> dict:
    """Статьи → плоский словарь для оверлея, в млн ₽."""
    out: dict[str, float] = {}
    for section, mapping in _CARD_FIELDS.items():
        block = data.get(section) or {}
        for src, dest in mapping.items():
            v = block.get(src)
            if isinstance(v, (int, float)):
                out[dest] = round(float(v) * factor, 3)
    # Чистый долг отчётность отдельной строкой обычно не даёт — считаем сами, но
    # ТОЛЬКО когда известны все три слагаемых. Полуизвестный чистый долг хуже, чем
    # его отсутствие: на карточке он встанет рядом с выверенными периодами.
    ltd, std, cash = out.get("long_term_debt"), out.get("short_term_debt"), out.get("cash")
    if None not in (ltd, std, cash):
        out["net_debt"] = round(ltd + std - cash, 3)
    return out


def ingest(db: Session, ticker: str, text: str, *, company_name: str | None = None,
           period_hint: str | None = None, source: str = "statement_doc",
           source_url: str | None = None, apply: bool = False) -> dict:
    """Текст документа → проверенные статьи → (по флагу) запись в оверлей карточки.

    apply=False (по умолчанию) — сухой прогон: извлекаем, проверяем, показываем, что
    получилось бы, но ничего не пишем. Так и надо смотреть первый раз на новом
    эмитенте: цена ошибки в витрине выше, чем стоимость лишнего прогона.
    """
    from app.services.statement_extract import extract
    from app.services import interim_periods

    res = extract(text, company_name=company_name, expected_period=period_hint)
    data, issues = res.get("data"), res.get("issues") or []
    out: dict = {"ticker": ticker.upper(), "usable": bool(res.get("usable")),
                 "issues": issues, "written": False}
    if not data:
        out["reason"] = "статьи не извлеклись"
        return out

    out["period_label"] = data.get("period_label")
    out["period_end"] = data.get("period_end")
    out["standard"] = data.get("standard")
    out["unit"] = data.get("unit")
    out["found_statements"] = data.get("found_statements") or []

    if (data.get("currency") or "RUB").upper() != "RUB":
        out["reason"] = f"валюта отчётности {data.get('currency')} — рублёвая витрина такое не принимает"
        out["usable"] = False
        return out
    factor = _TO_MLN.get(data.get("unit") or "")
    if factor is None:
        out["reason"] = "не распознан масштаб (тыс/млн/млрд) — числа без единицы не пишем"
        out["usable"] = False
        return out

    figures = _flatten(data, factor)
    out["figures_mln"] = figures
    if not figures:
        out["reason"] = "ни одной статьи, пригодной для карточки"
        out["usable"] = False
        return out
    if issues:
        out["reason"] = "тождества отчётности не сошлись — на витрину не публикуем"
        return out

    # период → канон оверлея (год/окно месяцев). Годовой период сюда не пишем:
    # оверлей — про промежуточные периоды, годовые числа живут в financials.json.
    pe = data.get("period_end")
    period_obj = None
    if pe:
        try:
            period_obj = interim_periods.report_period_to_interim(
                data.get("period_label") or "", date.fromisoformat(str(pe)[:10]))
        except (ValueError, TypeError):
            period_obj = None
    if not period_obj:
        out["reason"] = "период не привёлся к промежуточному (годовой или нераспознанный)"
        return out
    out["period_canon"] = period_obj

    if not apply:
        out["reason"] = "сухой прогон — записи нет (apply=true, чтобы записать)"
        return out

    written = _write_overlay(db, ticker.upper(), period_obj, figures,
                             standard=data.get("standard"), source=source,
                             source_url=source_url)
    out["written"] = written != "skipped"
    out["write_result"] = written
    return out


def _write_overlay(db: Session, ticker: str, period_obj: dict, figures: dict,
                   *, standard: str | None, source: str, source_url: str | None) -> str:
    """Апсерт строки оверлея. Богатый источник не должен проигрывать бедному."""
    from sqlalchemy import select

    from app.models.earnings import InterimFinancialsOverlay
    existing = db.execute(
        select(InterimFinancialsOverlay).where(
            InterimFinancialsOverlay.ticker == ticker,
            InterimFinancialsOverlay.fiscal_year == period_obj["fiscal_year"],
            InterimFinancialsOverlay.start_m == period_obj["start_m"],
            InterimFinancialsOverlay.end_m == period_obj["end_m"],
        )).scalar_one_or_none()
    present = sum(1 for v in figures.values() if isinstance(v, (int, float)))
    if existing is not None:
        # Документ отчётности — заведомо богаче пресс-релиза, но проверяем по факту:
        # если там почему-то больше заполненных статей, не обедняем карточку.
        if present <= (existing.fields_present or 0):
            return "skipped"
        existing.figures = {**(existing.figures or {}), **figures}
        existing.fields_present = present
        existing.standard = standard or existing.standard
        existing.source = source
        existing.source_report_id = existing.source_report_id
        db.commit()
        return "updated"
    db.add(InterimFinancialsOverlay(
        ticker=ticker, fiscal_year=period_obj["fiscal_year"],
        start_m=period_obj["start_m"], end_m=period_obj["end_m"],
        period_label=period_obj["period_label"], period_type=period_obj["period_type"],
        cumulative=period_obj["cumulative"], standard=standard,
        end_date=period_obj["end_date"], figures=figures, fields_present=present,
        source=source))
    db.commit()
    return "created"


def ingest_from_url(db: Session, ticker: str, url: str, *, company_name: str | None = None,
                    period_hint: str | None = None, apply: bool = False) -> dict:
    """Скачать документ по ссылке и провести через всю цепочку."""
    from app.services.report_documents import fetch_document_text
    got = fetch_document_text(url)
    if not got["ok"]:
        return {"ticker": ticker.upper(), "usable": False, "written": False,
                "reason": f"документ не скачался или пуст ({url})"}
    res = ingest(db, ticker, got["text"], company_name=company_name,
                 period_hint=period_hint, source="statement_doc", source_url=url, apply=apply)
    res["source_url"] = url
    res["doc_chars"] = got["chars"]
    return res
