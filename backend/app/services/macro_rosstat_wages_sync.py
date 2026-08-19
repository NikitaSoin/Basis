"""Зарплаты Росстата — машинный источник вместо веб-поиска.

🔴 Найдено 2026-08-19, после того как веб-добор трижды вернул «не найдено». Считалось,
что у Росстата машинного канала нет (fedstat/ЕМИСС отдаёт 403). Это верно для ЕМИСС, но
не для самого Росстата: на странице «Рынок труда, занятость и заработная плата» лежат
xlsx-таблицы, и в `tab1-zpl_<MM-YYYY>.xlsx` — помесячный ряд номинальной начисленной
зарплаты с 1991 года.

Две ловушки, из-за которых источник считался недоступным:
1. **Сертификат.** rosstat.gov.ru подписан сертификатом Минцифры, которого нет в
   доверенных у контейнера — httpx падает с CERTIFICATE_VERIFY_FAILED. Для публичной
   статистики читаем без проверки цепочки (осознанно, здесь нет ни авторизации, ни
   персональных данных), но берём ТОЛЬКО эту одну страницу и файлы с неё.
2. **Имя файла меняется каждый месяц** (`tab1-zpl_05-2026.xlsx` → `06-2026`), поэтому
   ссылку ищем на странице, а не зашиваем.

Реальная зарплата считается КОДОМ из номинальной и ИПЦ: отдельной машинной таблицы с
ней у Росстата на этой странице нет, а определение однозначно — номинальный рост,
делённый на инфляцию. Брать её из пересказов в новостях мы больше не хотим.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_PAGE = "https://rosstat.gov.ru/labor_market_employment_salaries"
_HOST = "https://rosstat.gov.ru"
_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; BasisBot/1.0)"}
# Помесячные колонки таблицы: G — январь … R — декабрь
_MONTH_COLS = ["G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R"]
_SINCE_YEAR = 2015
# Зарплата ниже этого — данные до деноминации или другая единица; выше — явная ошибка
_RANGE = (5_000.0, 500_000.0)


def _month_end(year: int, month: int) -> date:
    """Конец месяца — принятая в рядах платформы дата месячной точки."""
    return (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1))


def _get(url: str) -> bytes:
    """GET с запасным вариантом без проверки сертификата (см. докстринг)."""
    try:
        r = httpx.get(url, timeout=40, headers=_HTTP, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        r = httpx.get(url, timeout=40, headers=_HTTP, follow_redirects=True, verify=False)
    r.raise_for_status()
    return r.content


def _find_table_url() -> str | None:
    """Найти на странице ссылку на актуальную таблицу номинальной зарплаты."""
    try:
        html = _get(_PAGE).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("Росстат: страница недоступна: %s", type(e).__name__)
        return None
    m = re.search(r'href="([^"]*tab1[-_]zpl[^"]*\.xlsx)"', html)
    return (_HOST + m.group(1)) if m and m.group(1).startswith("/") else (m.group(1) if m else None)


def _parse_months(blob: bytes, file_year: int) -> list[tuple[date, float]]:
    """Месячные значения по годам. Год берём НЕ из подписи строки, а по порядку.

    🔴 Почему так. С 2022 года в колонке с годом стоят сноски («(2)», «2)», пусто), и
    подпись перестаёт быть годом. Первый прогон из-за этого положил данные 2025 года в
    2023-й — ряд выглядел заполненным и был неверен, самая опасная из ошибок. Строки в
    таблице идут подряд по годам, а год файла известен из его имени, поэтому годы
    расставляются отсчётом назад от последней строки. Подпись используется как ПРОВЕРКА:
    если читаемый год не совпадает с расставленным, разбор прекращается — лучше без
    данных, чем со сдвинутыми.
    """
    z = zipfile.ZipFile(io.BytesIO(blob))
    shared = re.findall(r"<t[^>]*>(.*?)</t>",
                        z.read("xl/sharedStrings.xml").decode("utf-8", "replace"), re.DOTALL) \
        if "xl/sharedStrings.xml" in z.namelist() else []
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "replace")

    rows: list[tuple[str, dict]] = []
    for body in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.DOTALL):
        cells = {}
        for col, attrs, val in re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', body):
            if val is None or val == "":
                continue
            cells[col] = shared[int(val)] if 't="s"' in attrs else val
        months = {}
        for i, col in enumerate(_MONTH_COLS, start=1):
            try:
                v = float(str(cells.get(col, "")).replace(",", "."))
            except ValueError:
                continue
            if _RANGE[0] <= v <= _RANGE[1]:
                months[i] = round(v, 1)
        if months:
            rows.append(((cells.get("A") or "").strip(), months))
    if not rows:
        return []

    out: list[tuple[date, float]] = []
    for back, (label, months) in enumerate(reversed(rows)):
        year = file_year - back
        if year < _SINCE_YEAR:
            break
        if re.fullmatch(r"(19|20)\d{2}", label) and int(label) != year:
            logger.warning("Росстат зарплаты: подпись строки %s не совпала с расчётным "
                           "годом %s — разбор остановлен", label, year)
            break
        for m, val in months.items():
            out.append((_month_end(year, m), val))
    return sorted(set(out))


def _derive_real(db: Session, pts: list[tuple[date, float]]) -> dict:
    """Реальная зарплата = номинальный рост, делённый на инфляцию (расчёт кода)."""
    by_date = dict(pts)
    saved, last = 0, None
    for d, val in pts[-24:]:
        prev = by_date.get(_month_end(d.year - 1, d.month))
        if not prev:
            continue
        cpi = db.execute(text(
            "SELECT value FROM macro_data_points WHERE indicator_code='inflation' AND "
            "metric='yoy' AND as_of >= :a AND as_of <= :b ORDER BY as_of DESC LIMIT 1"),
            {"a": date(d.year, d.month, 1), "b": date(d.year, d.month, 28)}).scalar()
        if cpi is None:
            continue
        nom_yoy = val / prev - 1
        real_yoy = round(((1 + nom_yoy) / (1 + float(cpi) / 100) - 1) * 100, 1)
        if not (-30 <= real_yoy <= 30):
            continue
        res = upsert_point(db, "real_wage", d, "yoy", real_yoy, unit="%",
                           source="расчёт Basis: зарплата Росстата, дефлированная ИПЦ",
                           source_url=_PAGE, ingested_via="rosstat", commit=False)
        if res in ("insert", "revise"):
            saved += 1
        last = (d, real_yoy)
    db.commit()
    return {"saved": saved, "last": str(last[0]) if last else None,
            "value": last[1] if last else None}


def sync_wages(db: Session) -> dict:
    """Один прогон: номинальная зарплата из таблицы Росстата + реальная расчётом."""
    url = _find_table_url()
    if not url:
        return {"error": "table_link_not_found"}
    try:
        blob = _get(url)
    except Exception as e:  # noqa: BLE001
        logger.warning("Росстат: таблица недоступна: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}
    fy = re.search(r"_(\d{1,2})-(\d{4})\.xlsx", url)
    file_year = int(fy.group(2)) if fy else date.today().year
    try:
        pts = _parse_months(blob, file_year)
    except Exception as e:  # noqa: BLE001
        logger.exception("Росстат: таблица зарплат не разобрана")
        return {"error": f"parse_failed:{type(e).__name__}"}
    if not pts:
        return {"error": "no_rows", "url": url}

    # Полная перезапись своего канала: файл несёт всю историю, а прошлый разбор мог
    # положить точки не на те даты (см. докстринг _parse_months). Чистим только СВОИ
    # точки — чужие каналы (файл владельца, лента) не трогаем.
    db.execute(text("DELETE FROM macro_data_points WHERE indicator_code IN "
                    "('nominal_wage','real_wage') AND ingested_via='rosstat'"))
    saved = 0
    for d, val in pts:
        res = upsert_point(db, "nominal_wage", d, "level", val, unit="₽",
                           source="Росстат (среднемесячная начисленная)", source_url=_PAGE,
                           ingested_via="rosstat", commit=False)
        if res in ("insert", "revise"):
            saved += 1
    db.commit()
    out = {"url": url, "points": len(pts), "saved": saved,
           "last": str(pts[-1][0]), "value": pts[-1][1],
           "real_wage": _derive_real(db, pts)}
    logger.info("Росстат зарплаты: %s точек, последняя %s = %s ₽", len(pts),
                out["last"], out["value"])
    return out
