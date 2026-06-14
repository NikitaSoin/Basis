"""Ингест Росстатовских рядов (безработица, ИЦП, реальная зарплата/доходы, ВВП).

ОСНОВНОЙ канал — ingest_rosstat_file: ручная выгрузка из fedstat (long-CSV).
ПОЧЕМУ не машинно: fedstat.ru закрыт антибот-WAF — 403 на ВСЁ (главная, страница
показателя, data.do, SDMX), при любом User-Agent (Chrome/Googlebot/без UA), ДАЖЕ
с боевого сервера в РФ. Подтверждено диагностикой с боя (не предположение). Поэтому
история закрывается файлом config/rosstat_manual.csv (см. config/ROSSTAT_MANUAL.md).

Safeguards (оба канала): валидация диапазона min/max; ingested_via='rosstat'
(официальный приоритет — Лента не перезаписывает); при ошибке — НИЧЕГО не пишем.

ingest_fedstat (HTTP/SDMX) оставлен как нерабочий артефакт на случай, если WAF
когда-нибудь снимут; в проде НЕ вызывается.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import load_macro_config, upsert_point

logger = logging.getLogger(__name__)

_BASE = "https://www.fedstat.ru"
_DATA = _BASE + "/indicator/data.do"
_HTTP = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": _BASE + "/",
}
_MONTHS_GENITIVE = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7,
    "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _period_to_date(period: str) -> date | None:
    """SDMX TIME_PERIOD → дата конца периода. Поддержка: YYYY-MM, YYYY, YYYY-Qn."""
    p = (period or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})$", p)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        first_next = date(y + (mo == 12), (mo % 12) + 1, 1)
        return date.fromordinal(first_next.toordinal() - 1)  # последний день месяца
    m = re.match(r"^(\d{4})-?[QК](\d)$", p, re.I)
    if m:
        y, q = int(m.group(1)), int(m.group(2))
        return date(y, q * 3, 28)
    m = re.match(r"^(\d{4})$", p)
    if m:
        return date(int(m.group(1)), 12, 31)
    return None


def _parse_sdmx(content: bytes) -> tuple[list[tuple[date, float]], str | None]:
    """Разбор SDMX-ML: возвращает [(дата, значение)] и название набора (если есть)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return [], None
    pts: list[tuple[date, float]] = []
    name = None
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "Name" and name is None and (el.text or "").strip():
            name = el.text.strip()
        if tag == "Obs":
            tdim = el.attrib.get("TIME_PERIOD")
            val = el.attrib.get("OBS_VALUE") or el.attrib.get("value")
            if tdim is None or val is None:
                # generic-формат: дочерние ObsDimension/ObsValue
                for ch in el:
                    ctag = ch.tag.rsplit("}", 1)[-1]
                    if ctag == "ObsDimension":
                        tdim = ch.attrib.get("value")
                    elif ctag == "ObsValue":
                        val = ch.attrib.get("value")
            d = _period_to_date(tdim or "")
            try:
                v = float(str(val).replace(",", ".")) if val is not None else None
            except (TypeError, ValueError):
                v = None
            if d and v is not None:
                pts.append((d, v))
    return pts, name


def _all_filter_values(html: str) -> dict[str, list[str]]:
    """Из HTML страницы показателя вытащить фильтры и ВСЕ их значения (выбираем всё,
    чтобы получить полный ряд). fedstat кладёт их в JS-структуру; парсим устойчиво."""
    fields: dict[str, list[str]] = {}
    # пары filterId -> [valueId...] из встроенного JSON ("filterId":NN,...,"id":"MM")
    for fm in re.finditer(r'"filterId"\s*:\s*"?(\d+)"?', html):
        fid = fm.group(1)
        fields.setdefault(fid, [])
    # значения опций: data-filter-value / "id" внутри блоков фильтров — берём все числовые id
    for fid in list(fields):
        # ищем значения, помеченные этим фильтром (грубо: все option value id рядом)
        vals = re.findall(r'filter_%s_(\d+)' % fid, html) or re.findall(r'name="%s"[^>]*value="(\d+)"' % fid, html)
        fields[fid] = sorted(set(vals))
    return {k: v for k, v in fields.items() if v}


def _fetch_indicator(ind_id: int) -> tuple[str | None, list[tuple[date, float]]]:
    """Запросить ряд показателя с fedstat: SDMX по ID. Возвращает (название, точки)."""
    s = httpx.Client(timeout=40, headers=_HTTP, follow_redirects=True)
    try:
        page = s.get(_DATA, params={"id": ind_id})
        page.raise_for_status()
        html = page.text
    except Exception as e:  # noqa: BLE001
        logger.warning("fedstat: страница показателя %s недоступна: %s", ind_id, type(e).__name__)
        return None, []
    tm = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else None
    # POST за SDMX: id + все значения всех фильтров (полный ряд)
    filters = _all_filter_values(html)
    form: list[tuple[str, str]] = [("id", str(ind_id))]
    for fid, vals in filters.items():
        for v in vals:
            form.append((fid, v))
    try:
        resp = s.post(_DATA, params={"format": "sdmx"}, data=form)
        resp.raise_for_status()
        pts, name = _parse_sdmx(resp.content)
    except Exception as e:  # noqa: BLE001
        logger.warning("fedstat: SDMX-выгрузка %s не получена: %s", ind_id, type(e).__name__)
        return title, []
    return (name or title), pts


import csv
import os

_MANUAL_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "config", "rosstat_manual.csv")


def ingest_rosstat_file(db: Session) -> dict:
    """ОСНОВНОЙ канал Росстата: ручная выгрузка из fedstat (браузером), формат long-CSV.

    Причина: fedstat.ru закрыт антибот-WAF (403 на всё, включая главную) даже с боевого
    сервера в РФ — подтверждено диагностикой. Машинный ингест невозможен. Поэтому история
    закрывается файлом-выгрузкой, который владелец экспортирует из fedstat вручную.

    Формат config/rosstat_manual.csv (utf-8): колонки indicator,period,value[,metric].
      indicator — код из fedstat_series (unemployment/ppi/real_wage/gdp/real_income/...)
      period    — YYYY-MM | YYYY | YYYY-Qn
      value     — число (точка или запятая)
      metric    — необязательно; по умолчанию из конфига (level/yoy)
    Safeguards те же: валидация диапазона min/max, ingested_via='rosstat' (Лента не перетрёт).
    Идемпотентно: повторный запуск не дублирует и не портит данные.
    """
    if not os.path.exists(_MANUAL_CSV):
        logger.info("Росстат-файл %s отсутствует — пропуск (ждём ручную выгрузку)", _MANUAL_CSV)
        return {"status": "no_file"}
    cfg = load_macro_config()
    series = cfg.get("fedstat_series", {})
    out = {"loaded": {}, "skipped": {}}
    with open(_MANUAL_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("indicator") or "").strip()
            spec = series.get(code)
            if not spec:
                out["skipped"][code or "?"] = "неизвестный код"
                continue
            d = _period_to_date((r.get("period") or "").strip())
            raw = (r.get("value") or "").strip().replace(",", ".")
            if not d or raw == "" or raw.lower() in ("nan", "na", "none"):
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            if not (spec["min"] <= v <= spec["max"]):
                out["skipped"][code] = out["skipped"].get(code, "") + f" вне диапазона {v};"
                continue
            metric = (r.get("metric") or "").strip() or spec.get("metric", "level")
            res = upsert_point(db, code, d, metric, v, unit=spec.get("unit"),
                               source="Росстат (fedstat, ручная выгрузка)",
                               source_url=f"{_BASE}/indicator/{spec['id']}",
                               ingested_via="rosstat", commit=False)
            if res in ("insert", "revise"):
                out["loaded"][code] = out["loaded"].get(code, 0) + 1
    db.commit()
    logger.info("Росстат файл-ингест: %s", out)
    return out


def ingest_fedstat(db: Session, recent_months: int = 60) -> dict:
    """Ингест Росстат-рядов с fedstat. Самопроверка названия + валидация диапазона."""
    cfg = load_macro_config()
    series = cfg.get("fedstat_series", {})
    cutoff = date.today().replace(year=date.today().year - (recent_months // 12 + 1))
    out = {"loaded": {}, "skipped": {}}
    for code, spec in series.items():
        if not isinstance(spec, dict) or "id" not in spec:
            continue
        title, pts = _fetch_indicator(spec["id"])
        # САМОПРОВЕРКА: название ряда должно содержать ожидаемое слово, иначе ID не тот
        if not title or spec["expect"].lower() not in title.lower():
            out["skipped"][code] = f"название не совпало ('{(title or '')[:40]}')"
            logger.warning("fedstat: %s id=%s — название не подтверждает показатель ('%s'), "
                           "НЕ загружаем (защита от неверного ID)", code, spec["id"], (title or "")[:50])
            continue
        saved = 0
        for d, v in pts:
            if d < cutoff:
                continue
            if not (spec["min"] <= v <= spec["max"]):  # мусор не пишем
                continue
            res = upsert_point(db, code, d, spec.get("metric", "level"), v, unit=spec.get("unit"),
                               source="Росстат (fedstat/EMISS)",
                               source_url=f"{_BASE}/indicator/{spec['id']}",
                               ingested_via="rosstat", commit=False)
            if res in ("insert", "revise"):
                saved += 1
        db.commit()
        out["loaded"][code] = saved
    logger.info("fedstat ингест: %s", out)
    return out
