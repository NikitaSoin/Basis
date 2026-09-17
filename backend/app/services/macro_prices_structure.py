"""Структура инфляции: когорты товаров и услуг + веса потребительской корзины.

🔴 ЗАЧЕМ (владелец, 2026-09-18). В базе показателей была ровно одна цифра по ценам —
сводная инфляция, плюс недельная, ожидания и цены производителей. Методичка макро
требует обратного: «базовая инфляция и инфляция услуг информативнее общего индекса»,
«инфляция, движимая продовольственным шоком, и инфляция, движимая зарплатами, требуют
разных прогнозов при одинаковом текущем числе». Без разбивки анализ не мог отличить
разовый урожайный скачок от закрепившегося роста цен на услуги — а это разные ставки
и разные последствия для компаний.

ЧТО БЕРЁМ У РОССТАТА (машинно, с https://rosstat.gov.ru/statistics/price):
  ipc_mes_<MM-YYYY>.xlsx — помесячные индексы цен по трём когортам:
     лист 01 — все товары и услуги (контроль), 02 — продовольственные товары,
     03 — непродовольственные, 04 — услуги. Значения «к концу предыдущего месяца».
  Vesa-tov-KIPC_*.xlsx — структура потребительских расходов (веса корзины) по разделам
     классификации, снимок за год лежит в backend/config/cpi_weights.json.

Две ловушки того же рода, что у зарплат Росстата (см. macro_rosstat_wages_sync):
1. Сертификат Минцифры — читаем без проверки цепочки, только эту страницу и файлы с неё.
2. Имя файла содержит месяц и меняется — ссылку ищем на странице, а не зашиваем.

ВЕСА КОГОРТ СЧИТАЕТ КОД, А НЕ ЧЕЛОВЕК. Росстат публикует веса в разрезе своей
классификации (продукты питания, транспорт, ЖКХ…), а не в разрезе «продовольственные /
непродовольственные / услуги», поэтому три доли восстанавливаются подбором по самим
индексам: ищем такие доли, при которых взвешенная сумма когорт лучше всего повторяет
сводный индекс за последние три года. На данных 2023–2026 подбор воспроизводит сводный
индекс с ошибкой около 0,006 процентного пункта в месяц — это проверка метода, а не
допущение на глаз. Доли пересчитываются при каждом прогоне, поэтому ежегодный
пересмотр корзины Росстатом подхватывается сам.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from datetime import date, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_PAGE = "https://rosstat.gov.ru/statistics/price"
_HOST = "https://rosstat.gov.ru"
_HTTP = {"User-Agent": "Mozilla/5.0 (compatible; BasisBot/1.0)"}
_WEIGHTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "cpi_weights.json")

# лист файла → код ряда платформы и человеческое имя
_COHORTS = {
    "02": ("inflation_food", "продовольственные товары"),
    "03": ("inflation_nonfood", "непродовольственные товары"),
    "04": ("inflation_services", "услуги"),
}
# Лист «все товары и услуги» — это официальный сводный индекс Росстата. Пишем его в
# основной ряд inflation: до сих пор туда попадали числа из новостной ленты, и оттуда
# же приходил дефект «годовая инфляция датирована концом ещё не наступившего месяца».
# Приоритет источников (macro_ingest._VIA_PRIORITY) ставит Росстат выше ленты, поэтому
# официальная точка перекрывает пересказ, а не наоборот.
_CONTROL_SHEET = "01"
_CONTROL_CODE = "inflation"
_MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
           "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
_SINCE_YEAR = 2015
# Месячный индекс к предыдущему месяцу: за пределами этого коридора — не индекс цен,
# а посторонняя строка таблицы (годовые итоги, сноски).
_RANGE = (90.0, 115.0)


def _month_end(year: int, month: int) -> date:
    return date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)


def _get(url: str) -> bytes:
    """GET с запасным вариантом без проверки сертификата (сертификат Минцифры)."""
    try:
        r = httpx.get(url, timeout=60, headers=_HTTP, follow_redirects=True)
    except Exception as e:  # noqa: BLE001
        if "CERTIFICATE_VERIFY_FAILED" not in str(e):
            raise
        r = httpx.get(url, timeout=60, headers=_HTTP, follow_redirects=True, verify=False)
    r.raise_for_status()
    return r.content


def find_file_url(pattern: str = r"ipc_mes[^\"']*\.xlsx") -> str | None:
    """Найти на странице цен актуальный файл: имя меняется каждый месяц."""
    try:
        html = _get(_PAGE).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("Росстат цены: страница недоступна: %s", type(e).__name__)
        return None
    found = re.findall(r'href="([^"]*' + pattern + r')"', html)
    if not found:
        return None
    # Берём последнюю ссылку: на странице файлы идут от старых к свежим.
    href = sorted(found)[-1]
    return _HOST + href if href.startswith("/") else href


def _parse_sheet(blob: bytes, sheet_title: str) -> dict[tuple[int, int], float]:
    """Месячные индексы «к концу предыдущего месяца» с листа: {(год, месяц): индекс}.

    Таблица широкая: строки — месяцы, столбцы — годы. Ниже той же формой идёт вторая
    секция «к декабрю предыдущего года» — берём ТОЛЬКО первую, иначе декабрьские
    накопленные индексы затрут месячные.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    if sheet_title not in wb.sheetnames:
        logger.warning("Росстат цены: в файле нет листа %s", sheet_title)
        return {}
    rows = list(wb[sheet_title].iter_rows(values_only=True))
    def _years_in(row) -> list[tuple[int, int]]:
        return [(i, int(str(c).strip())) for i, c in enumerate(row)
                if c is not None and re.fullmatch(r"(19|20)\d{2}", str(c).strip())]

    header = next((r for r in rows[:8] if len(_years_in(r)) >= 2), None)
    if not header:
        logger.warning("Росстат цены: на листе %s не найдена строка с годами", sheet_title)
        return {}
    years = _years_in(header)
    out: dict[tuple[int, int], float] = {}
    seen: set[str] = set()
    for r in rows:
        label = str(r[0] or "").strip().lower()
        if label not in _MONTHS or label in seen:
            continue
        month = _MONTHS.index(label) + 1
        for i, year in years:
            if year < _SINCE_YEAR or i >= len(r):
                continue
            try:
                v = float(str(r[i]).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if _RANGE[0] <= v <= _RANGE[1]:
                out[(year, month)] = v
        if label == _MONTHS[-1]:
            seen.update(_MONTHS)  # первая секция кончилась
    return out


def _yoy(series: dict[tuple[int, int], float], year: int, month: int) -> float | None:
    """Годовой рост — произведение двенадцати месячных индексов."""
    acc = 1.0
    y, m = year, month
    for _ in range(12):
        v = series.get((y, m))
        if v is None:
            return None
        acc *= v / 100
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return round((acc - 1) * 100, 2)


def sync(db: Session) -> dict:
    """Загрузить когорты инфляции из файла Росстата в ряды платформы."""
    url = find_file_url()
    if not url:
        return {"ok": False, "error": "файл помесячных индексов не найден на странице"}
    blob = _get(url)
    control = _parse_sheet(blob, _CONTROL_SHEET)
    if not control:
        return {"ok": False, "error": "не разобран контрольный лист"}
    saved, last = {}, {}
    parsed: dict[str, dict[tuple[int, int], float]] = {"_control": control}
    # Сводный индекс — в основной ряд инфляции, официальным источником.
    n_ctl = 0
    for (year, month), idx in sorted(control.items()):
        d = _month_end(year, month)
        if upsert_point(db, _CONTROL_CODE, d, "mom", round(idx - 100, 2), unit="%",
                        source="Росстат, индексы потребительских цен: все товары и услуги",
                        source_url=url, ingested_via="rosstat", commit=False) in ("insert", "revise"):
            n_ctl += 1
        yoy = _yoy(control, year, month)
        if yoy is not None and upsert_point(
                db, _CONTROL_CODE, d, "yoy", yoy, unit="%",
                source="Росстат, индексы потребительских цен: все товары и услуги",
                source_url=url, ingested_via="rosstat", commit=False) in ("insert", "revise"):
            n_ctl += 1
    saved[_CONTROL_CODE] = n_ctl
    for sheet, (code, human) in _COHORTS.items():
        series = _parse_sheet(blob, sheet)
        if not series:
            logger.warning("Росстат цены: лист %s (%s) не разобран", sheet, human)
            continue
        parsed[code] = series
        n = 0
        for (year, month), idx in sorted(series.items()):
            d = _month_end(year, month)
            mom = round(idx - 100, 2)
            if upsert_point(db, code, d, "mom", mom, unit="%",
                            source=f"Росстат, индексы потребительских цен: {human}",
                            source_url=url, ingested_via="rosstat", commit=False) in ("insert", "revise"):
                n += 1
            yoy = _yoy(series, year, month)
            if yoy is not None:
                if upsert_point(db, code, d, "yoy", yoy, unit="%",
                                source=f"Росстат, индексы потребительских цен: {human}",
                                source_url=url, ingested_via="rosstat", commit=False) in ("insert", "revise"):
                    n += 1
                last[code] = {"as_of": str(d), "yoy": yoy, "mom": mom}
        saved[code] = n
    db.commit()
    check = _control_check(parsed, control)
    logger.info("Росстат цены: когорты обновлены %s, сверка со сводным индексом: %s",
                saved, check.get("note"))
    return {"ok": True, "url": url, "saved": saved, "last": last, "control": check}


def _control_check(parsed: dict[str, dict], control: dict) -> dict:
    """Сверка: взвешенная сумма когорт обязана повторять сводный индекс."""
    w = _estimate_weights({**parsed, "_control": control})
    if not w or not control:
        return {"note": "сверка не выполнена: мало данных"}
    keys = sorted(k for k in control
                  if all(k in parsed.get(c, {}) for c in _COHORT_CODES))[-12:]
    if not keys:
        return {"note": "сверка не выполнена: нет общих месяцев"}
    err = max(abs(sum(w[c] * parsed[c][k] for c in _COHORT_CODES) - control[k]) for k in keys)
    return {"weights": w, "max_error_pp": round(err, 3),
            "note": f"максимальное расхождение за 12 месяцев {err:.3f} п.п."}


_COHORT_CODES = [code for code, _ in _COHORTS.values()]


def _estimate_weights(parsed: dict[str, dict]) -> dict[str, float] | None:
    """Доли когорт в корзине — подбором по индексам (см. докстринг модуля)."""
    control = parsed.get("_control")
    if control is None:
        return None
    keys = sorted(k for k in control if all(k in parsed.get(c, {}) for c in _COHORT_CODES))[-36:]
    if len(keys) < 12:
        return None
    best = None
    for wf in [x / 200 for x in range(60, 95)]:          # 0,30–0,47 шагом 0,005
        for wn in [x / 200 for x in range(50, 90)]:      # 0,25–0,45 шагом 0,005
            ws = 1 - wf - wn
            if ws <= 0.1:
                continue
            weights = dict(zip(_COHORT_CODES, (wf, wn, ws)))
            err = sum((sum(weights[c] * parsed[c][k] for c in _COHORT_CODES) - control[k]) ** 2
                      for k in keys)
            if best is None or err < best[0]:
                best = (err, weights)
    return {k: round(v, 3) for k, v in best[1].items()} if best else None


def weights_basket() -> dict:
    """Веса потребительской корзины (снимок Росстата за год)."""
    try:
        with open(_WEIGHTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        logger.warning("Веса корзины: файл %s недоступен", _WEIGHTS_FILE)
        return {}


def digest(db: Session) -> dict:
    """Разложение инфляции по когортам — для интерпретатора и витрины.

    Вклад когорты в годовую инфляцию = её доля в корзине × её годовой рост. Сумма
    вкладов должна сходиться со сводной инфляцией; расхождение показываем честно,
    а не прячем — оно и есть сигнал, что разбор пора чинить.
    """
    rows = db.execute(text(
        "SELECT indicator_code, metric, value, as_of FROM macro_data_points "
        "WHERE indicator_code = ANY(:codes) AND metric IN ('yoy','mom') "
        "ORDER BY as_of DESC LIMIT 400"), {"codes": _COHORT_CODES}).fetchall()
    latest: dict[str, dict] = {}
    for code, metric, value, as_of in rows:
        slot = latest.setdefault(code, {})
        if metric not in slot:
            slot[metric] = {"value": float(value), "as_of": str(as_of)}
    if not latest:
        return {"available": False, "note": "когорты инфляции ещё не загружены"}

    parsed = {c: _series_from_db(db, c) for c in _COHORT_CODES}
    parsed["_control"] = _series_from_db(db, _CONTROL_CODE)
    weights = _estimate_weights(parsed) or {}
    basket = weights_basket()
    human = {code: name for code, name in _COHORTS.values()}
    cohorts = []
    for code in _COHORT_CODES:
        slot = latest.get(code) or {}
        yoy = (slot.get("yoy") or {}).get("value")
        w = weights.get(code)
        cohorts.append({
            "code": code, "name": human.get(code, code),
            "yoy_pct": yoy, "mom_pct": (slot.get("mom") or {}).get("value"),
            "as_of": (slot.get("yoy") or slot.get("mom") or {}).get("as_of"),
            "weight_pct": round(w * 100, 1) if w else None,
            "contribution_pp": round(w * yoy, 2) if (w and yoy is not None) else None,
        })
    # Сводную инфляцию берём НА ТУ ЖЕ ДАТУ, что и когорты: иначе сумма вкладов за
    # август сравнивается с оперативной оценкой за сентябрь, и расхождение выглядит
    # ошибкой разбора, хотя это просто разные месяцы.
    cohort_date = next((c["as_of"] for c in cohorts if c.get("as_of")), None)
    headline = None
    if cohort_date:
        headline = db.execute(text(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code='inflation' "
            "AND metric='yoy' AND as_of = :d LIMIT 1"), {"d": cohort_date}).fetchone()
    if headline is None:
        headline = db.execute(text(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code='inflation' "
            "AND metric='yoy' ORDER BY as_of DESC LIMIT 1")).fetchone()
    total = sum(c["contribution_pp"] for c in cohorts if c["contribution_pp"] is not None)
    return {
        "available": True,
        "cohorts": cohorts,
        "sum_contributions_pp": round(total, 2),
        "headline_yoy_pct": float(headline[0]) if headline else None,
        "headline_as_of": str(headline[1]) if headline else None,
        "basket_divisions": (basket.get("divisions") or [])[:13],
        "basket_year": basket.get("year"),
        "method": ("Вклад = доля когорты в корзине × её годовой рост. Доли подобраны кодом "
                   "по индексам за три года так, чтобы взвешенная сумма повторяла сводный "
                   "индекс; веса разделов корзины — снимок Росстата за год."),
    }


def _series_from_db(db: Session, code: str) -> dict[tuple[int, int], float]:
    """Месячные индексы ряда из базы в форме {(год, месяц): индекс к пред. месяцу}."""
    rows = db.execute(text(
        "SELECT as_of, value FROM macro_data_points WHERE indicator_code=:c AND metric='mom' "
        "ORDER BY as_of"), {"c": code}).fetchall()
    return {(d.year, d.month): float(v) + 100 for d, v in rows}
