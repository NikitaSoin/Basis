"""Номинальный ВВП по кварталам — таблица Росстата.

🔴 2026-08-19. Уровень ВВП в триллионах добывался веб-поиском и жил одной точкой: за
квартал добывалось последнее опубликованное число, истории не было, кв/кв посчитать не
из чего. У Росстата на странице «Национальные счета» лежит `VVP_kvartal_*.xlsx` —
квартальный ряд в текущих ценах с 1995 года. Тот же вывод, что и с денежными агрегатами:
сначала ищем файл источника, веб-поиск — последнее средство.

Устройство таблицы (лист 2 «в текущих ценах, млрд руб.»): в шапке год стоит один раз на
четыре колонки, ниже — названия кварталов, ещё ниже — одна длинная строка значений.
Поэтому год «протягивается» по колонкам вправо до следующего года, а квартал берётся из
своей строки-подписи. Значения — млрд ₽, у нас ряд в трлн ₽.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from datetime import date

from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point
from app.services.macro_rosstat_wages_sync import _get

logger = logging.getLogger(__name__)

_PAGE = "https://rosstat.gov.ru/statistics/accounts"
_HOST = "https://rosstat.gov.ru"
# 🔴 Лист выбирается ПО ДАННЫМ, а не по номеру. В файле полтора десятка листов: один и
# тот же ВВП в текущих ценах и в ценах 2008/2011/2021 годов, и каждый лист покрывает
# свой отрезок лет (лист с 1995 обрывается на 2011). Номер листа зашивать нельзя — он
# уже подводил: разбор прочитал 4 точки 2011 года и остановился. Правило выбора:
# берём лист с самой поздней точкой, а при равенстве — с наибольшим значением: после
# базового года номинальный ВВП всегда выше пересчитанного в постоянные цены.
_SHEETS = range(1, 16)
_SINCE_YEAR = 2011
_RANGE_TRN = (1.0, 200.0)      # трлн ₽ за квартал: отсекает годовые итоги и чужие единицы
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def _col_index(col: str) -> int:
    """A→0, B→1, …, AA→26."""
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _find_table_url() -> str | None:
    try:
        html = _get(_PAGE).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("Росстат ВВП: страница недоступна: %s", type(e).__name__)
        return None
    m = re.search(r'href="([^"]*VVP_kvartal[^"]*\.xlsx)"', html)
    if not m:
        return None
    return _HOST + m.group(1) if m.group(1).startswith("/") else m.group(1)


def _parse_sheet(z: zipfile.ZipFile, shared: list[str], n: int) -> list[tuple[date, float]]:
    name = f"xl/worksheets/sheet{n}.xml"
    if name not in z.namelist():
        return []
    sheet = z.read(name).decode("utf-8", "replace")

    # 🔴 Таблица идёт БЛОКАМИ по четыре года: шапка с годами → строка кварталов →
    # строка значений, и так до конца листа. Первый вариант разбора искал одну «самую
    # длинную» шапку и из-за этого прочитал ровно один блок (4 точки вместо всей
    # истории). Поэтому идём по листу подряд и держим текущую раскладку блока.
    cur_years: dict[int, int] = {}
    cur_quarters: dict[int, int] = {}
    out: list[tuple[date, float]] = []
    for body in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.DOTALL):
        row_years, row_q, row_v = {}, {}, {}
        for col, attrs, val in re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', body):
            if val is None or val == "":
                continue
            idx = _col_index(col)
            if 't="s"' in attrs:
                text = shared[int(val)].strip()
                if re.fullmatch(r"(19|20)\d{2}", text):
                    row_years[idx] = int(text)
                m = re.match(r"(I{1,3}|IV)\s+квартал", text)
                if m:
                    row_q[idx] = {"I": 1, "II": 2, "III": 3, "IV": 4}[m.group(1)]
            else:
                try:
                    row_v[idx] = float(val)
                except ValueError:
                    pass
        # Год в шапке может быть числом, а не текстом. Отличаем шапку от строки значений
        # тем, что в шапке ВСЕ числа — целые в диапазоне лет: квартальный ВВП в млрд ₽
        # иногда попадает в 1990–2100, но не бывает целым по всей строке сразу.
        if not row_years and 2 <= len(row_v) <= 6 and all(
                float(v).is_integer() and 1990 <= v <= 2100 for v in row_v.values()):
            row_years, row_v = {i: int(v) for i, v in row_v.items()}, {}
        if row_years:
            cur_years, cur_quarters = row_years, {}
            continue
        if row_q:
            cur_quarters = row_q
            continue
        if not (row_v and cur_years and cur_quarters):
            continue
        ordered = sorted(cur_years.items())
        for idx, raw in sorted(row_v.items()):
            year = next((y for i, y in reversed(ordered) if i <= idx), None)
            q = cur_quarters.get(idx)
            if not year or not q or year < _SINCE_YEAR:
                continue
            trn = round(raw / 1000, 4)
            if not (_RANGE_TRN[0] <= trn <= _RANGE_TRN[1]):
                continue
            m, d = _QUARTER_END[q]
            out.append((date(year, m, d), trn))
    return sorted(set(out))


def sync_gdp_quarterly(db: Session) -> dict:
    """Квартальный номинальный ВВП в трлн ₽ + темпы (г/г, кв/кв) расчётом кода."""
    url = _find_table_url()
    if not url:
        return {"error": "table_link_not_found"}
    try:
        blob = _get(url)
        z = zipfile.ZipFile(io.BytesIO(blob))
        shared = re.findall(r"<t[^>]*>(.*?)</t>",
                            z.read("xl/sharedStrings.xml").decode("utf-8", "replace"),
                            re.DOTALL) if "xl/sharedStrings.xml" in z.namelist() else []
        variants = [(n, _parse_sheet(z, shared, n)) for n in _SHEETS]
        variants = [(n, p) for n, p in variants if p]
        if not variants:
            return {"error": "no_rows", "url": url}
        sheet_no, pts = max(variants, key=lambda v: (v[1][-1][0], v[1][-1][1]))
    except Exception as e:  # noqa: BLE001
        logger.exception("Росстат ВВП: таблица не разобрана")
        return {"error": f"parse_failed:{type(e).__name__}"}
    if not pts:
        return {"error": "no_rows", "url": url}

    saved = 0
    for d, val in pts:
        res = upsert_point(db, "gdp_level", d, "level", val, unit="трлн ₽",
                           source="Росстат (ВВП в текущих ценах)", source_url=_PAGE,
                           ingested_via="rosstat", commit=False)
        if res in ("insert", "revise"):
            saved += 1
    # темпы считает код: у модели их не спрашиваем, из пересказов не берём
    by_date = dict(pts)
    last_d, last_v = pts[-1]
    rates = {}
    year_ago = by_date.get(date(last_d.year - 1, last_d.month, last_d.day))
    if year_ago:
        rates["yoy"] = round((last_v / year_ago - 1) * 100, 1)
    if len(pts) > 1 and pts[-2][1]:
        rates["qoq"] = round((last_v / pts[-2][1] - 1) * 100, 1)
    for metric, val in rates.items():
        upsert_point(db, "gdp_level", last_d, metric, val, unit="%",
                     source="расчёт Basis по данным Росстата", source_url=_PAGE,
                     ingested_via="rosstat", commit=False)
    db.commit()
    out = {"url": url, "sheet": sheet_no, "points": len(pts), "saved": saved,
           "last": str(last_d), "value": last_v, **rates}
    logger.info("Росстат ВВП: %s точек, последняя %s = %s трлн", len(pts), last_d, last_v)
    return out
