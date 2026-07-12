"""Синхронизация hh.индекса (рынок труда) с открытых отчётов hh.ru.

hh_index раньше имел только разовый CSV-бэкфилл БЕЗ крона (застрял на 2026-03-28).
Дедicated API статистики (stats.hh.ru/api/v1, /_api/data) закрыт без авторизации
(403/500 на прямые запросы) — не стали реверс-инжинирить SPA дальше. Вместо этого —
стабильная страница-хаб hh.ru/article/26641 «Обзоры рынка труда от hh.ru», которая
ЕЖЕМЕСЯЧНО обновляется и содержит прямую ссылку на PDF-отчёт последнего месяца на
hhcdn.ru (статический CDN, без анти-бота) — «Обзор за <месяц> <год>» → hhcdn.ru/file/*.pdf.
Проверено вручную 2026-07-12: отчёт за июнь 2026 дал hh.индекс=8,3 — совпало с
независимой сверкой (поиск/цитаты в прессе) 1-в-1.
"""
from __future__ import annotations

import html as html_module
import logging
import re
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
_HUB = "https://hh.ru/article/26641"
# Свежий отчёт лежит в обычном (не экранированном) HTML; АРХИВ прошлых месяцев —
# ВНУТРИ HTML-эскейпленного JSON-блока для гидратации React (доп. слой экранирования
# кавычек через \") — оба формата встречаются на одной странице, оба надо парсить.
_REPORT_RE = re.compile(
    r'Обзор за\s+([а-яё]+)\s+(\d{4})</b></td><td[^>]*><a[^>]+href="(https://hhcdn\.ru/[^"]+\.pdf)"',
    re.IGNORECASE,
)
_ARCHIVE_RE = re.compile(
    r'Обзор за\s+([а-яё]+)\s+(\d{4})</td><td[^>]*><noindex><a[^>]+href="(https://hhcdn\.ru/[^"]+\.pdf)"',
    re.IGNORECASE,
)
_RU_MONTHS = {"январь": 1, "февраль": 2, "март": 3, "апрель": 4, "май": 5, "июнь": 6,
              "июль": 7, "август": 8, "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12}

_SYS = (
    "Это фрагмент отчёта hh.ru «Краткий обзор рынка труда» за конкретный месяц. Извлеки "
    "значение hh.индекса (фраза вида «В <месяц> hh.индекс составил X пункта» или отдельное "
    "число рядом с подписью «hh.индекс»). Верни строго JSON: {\"hh_index\":<число>}. "
    "Число через точку, не через запятую. Только из текста. Без текста вне JSON."
)


def _month_end(year: int, month: int) -> date:
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    return nxt - timedelta(days=1)


def _all_reports() -> list[tuple[str, date]]:
    """[(url, as_of), ...] по возрастанию даты: свежий отчёт (обычный HTML) + архив
    прошлых месяцев (экранированный JSON-блок гидратации — см. докстринг файла)."""
    try:
        r = httpx.get(_HUB, timeout=25, headers=_HTTP, follow_redirects=True)
        r.raise_for_status()
        raw = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("hh-sync: страница-хаб недоступна: %s", type(e).__name__)
        return []
    normalized = html_module.unescape(raw).replace('\\"', '"')
    out: dict[date, str] = {}
    for pattern in (_REPORT_RE, _ARCHIVE_RE):
        for month_name, year, url in pattern.findall(normalized):
            month_num = _RU_MONTHS.get(month_name.lower())
            if not month_num:
                continue
            out[_month_end(int(year), month_num)] = url
    return sorted(out.items())


def sync_hh_index(db: Session, months_back: int = 1) -> dict:
    reports = _all_reports()
    if not reports:
        return {"error": "index"}
    todo = reports[-months_back:]
    out = {}
    for d, url in todo:
        out[str(d)] = _process_report(db, url, d)
    return out if months_back > 1 else next(iter(out.values()), {"error": "empty"})


def _process_report(db: Session, url: str, d: date) -> dict:
    try:
        r = httpx.get(url, timeout=30, headers=_HTTP, follow_redirects=True)
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:  # noqa: BLE001
        logger.warning("hh-sync: PDF недоступен: %s", type(e).__name__)
        return {"error": "pdf"}
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = (reader.pages[1].extract_text() or "") if len(reader.pages) > 1 else ""
    except Exception as e:  # noqa: BLE001
        logger.warning("hh-sync: парсинг PDF упал: %s", type(e).__name__)
        return {"error": "parse_pdf"}
    if not text:
        return {"error": "empty_page"}
    from app.services import llm
    try:
        out = llm.complete(_SYS, text[:2000], json_mode=True, max_tokens=200)
    except llm.LLMError:
        return {"error": "llm"}
    try:
        val = float(str(out.get("hh_index")).replace(",", "."))
    except (TypeError, ValueError):
        return {"error": "parse"}
    if not (0.1 <= val <= 20):
        return {"error": "range"}
    upsert_point(db, "hh_index", d, "level", val, unit="ед", source="hh.ru",
                 source_url=url, ingested_via="hh")
    return {"date": str(d), "hh_index": val}
