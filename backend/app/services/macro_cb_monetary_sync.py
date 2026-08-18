"""Денежные агрегаты М0/М1/М2/M2X — машинный источник, файл Банка России.

🔴 Найдено 2026-08-19. До этого уровни денежных агрегатов добывались веб-поиском: на
странице ЦБ дашборд без JSON, и казалось, что машинного канала нет. Он есть — рядом со
страницей лежит `monetary_agg.xlsx` с полной историей помесячно с 1993 года и всеми
четырьмя агрегатами, включая M2X, который поиск не находил вовсе.

Почему это важнее удобства: веб-поиск даёт ОДНО последнее число и не даёт истории, а
главное — не гарантирует, что определение показателя то же самое. Так в M0 прилетело
21,28 трлн при 19,79 месяцем раньше: рост на 7,5% за месяц у наличных денег невозможен,
просто в выдаче попалось «наличные деньги в обращении» (другой показатель). Файл ЦБ
снимает оба вопроса: определение фиксировано, история приходит целиком.

Значения в файле — млрд ₽, у нас ряды в трлн ₽ (делим на 1000).
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date, timedelta

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_URL = "https://www.cbr.ru/vfs/statistics/credit_statistics/monetary_agg.xlsx"
_PAGE = "https://www.cbr.ru/statistics/macro_itm/dkfs/monetary_agg/"
_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; BasisBot/1.0)"}

# метка строки в файле → (код ряда, допустимый диапазон в трлн ₽)
_ROWS = {
    "денежный агрегат м0": ("m0_level", (0.05, 60.0)),
    "денежный агрегат м1": ("m1_level", (0.05, 150.0)),
    "денежный агрегат м2": ("m2_level", (0.05, 300.0)),
    "денежный агрегат m2x": ("m2x_level", (0.05, 400.0)),
}

# История с 2000 года: раньше — другая экономика и деноминационный масштаб, на витрине
# такой хвост только мешает.
_SINCE = date(2000, 1, 1)


def _excel_date(serial: float) -> date | None:
    """Дата из экселевского порядкового номера (1900-я система с известным сдвигом)."""
    try:
        return date(1899, 12, 30) + timedelta(days=int(serial))
    except (ValueError, OverflowError):
        return None


def _norm(s: str) -> str:
    """Метку строки сравниваем без регистра, переносов и латиницы-кириллицы в «М»."""
    s = re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip().lower()
    return s.replace("m0", "м0").replace("m1", "м1").replace("m2 ", "м2 ")


def _parse(blob: bytes) -> dict[str, list[tuple[date, float]]]:
    """Разобрать xlsx без внешних зависимостей: sharedStrings + первый лист."""
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = re.findall(r"<t[^>]*>(.*?)</t>",
                        z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.DOTALL)
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "replace")
    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.DOTALL)

    dates: dict[str, date] = {}
    out: dict[str, list[tuple[date, float]]] = {}
    for body in rows:
        cells = re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', body)
        if not cells:
            continue
        label = ""
        values: list[tuple[str, str]] = []
        for col, attrs, val in cells:
            if val is None or val == "":
                continue
            if col == "A":
                label = shared[int(val)] if 't="s"' in attrs else val
            elif 't="s"' not in attrs:
                values.append((col, val))
        if not dates:                       # первая строка с числами — шапка с датами
            for col, val in values:
                d = _excel_date(float(val))
                if d:
                    dates[col] = d
            if dates:
                continue
        norm = _norm(label)
        match = next((v for k, v in _ROWS.items() if norm.startswith(k)), None)
        if not match:
            continue
        code, (lo, hi) = match
        pts = []
        for col, val in values:
            d = dates.get(col)
            if not d or d < _SINCE:
                continue
            try:
                trn = round(float(val) / 1000, 4)
            except ValueError:
                continue
            if lo <= trn <= hi:
                pts.append((d, trn))
        if pts:
            out.setdefault(code, []).extend(pts)
    return out


def sync_monetary_aggregates(db: Session, full_history: bool = False) -> dict:
    """Загрузить агрегаты из файла ЦБ. По умолчанию — последние 24 месяца."""
    try:
        r = httpx.get(_URL, timeout=40, headers=_HTTP, follow_redirects=True)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.warning("ЦБ денежные агрегаты: файл недоступен: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}
    try:
        parsed = _parse(r.content)
    except Exception as e:  # noqa: BLE001
        logger.exception("ЦБ денежные агрегаты: файл не разобран")
        return {"error": f"parse_failed:{type(e).__name__}: {e}"}
    if not parsed:
        return {"error": "no_rows"}

    cutoff = date.today() - timedelta(days=760)
    report: dict = {}
    for code, pts in parsed.items():
        pts = sorted(set(pts))
        if not full_history:
            pts = [p for p in pts if p[0] >= cutoff]
        saved = 0
        for d, val in pts:
            res = upsert_point(db, code, d, "level", val, unit="трлн ₽",
                               source="Банк России (денежные агрегаты)", source_url=_PAGE,
                               ingested_via="cbr", commit=False)
            if res in ("insert", "revise"):
                saved += 1
        db.commit()
        report[code] = {"points": len(pts), "saved": saved,
                        "last": str(pts[-1][0]) if pts else None,
                        "value": pts[-1][1] if pts else None}
        logger.info("ЦБ денежные агрегаты: %s — %s точек, последняя %s = %s трлн",
                    code, len(pts), report[code]["last"], report[code]["value"])
    return report
