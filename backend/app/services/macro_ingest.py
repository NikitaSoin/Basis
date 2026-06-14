"""MacroIngestService — наполнение числовых рядов Макрообзора.

Каналы точек: file (бэкфилл CSV), cbr (курсы/ставка), fred (мир), news (из Ленты),
minfin (бюджет). Все идут через единый upsert_point() с логикой ревизии.
Справочник показателей сидится из config/macro_indicators.json (идемпотентно;
авторский influence-текст в БД НЕ перетирается при повторном сиде).
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.models.macro import MacroIndicator, MacroDataPoint

logger = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG = os.path.join(_BASE, "config", "macro_indicators.json")
_CSV = os.path.join(_BASE, "config", "cb_model_big.csv")


def load_macro_config() -> dict:
    with open(_CONFIG, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------- справочник -----------------------------
def seed_indicators(db: Session) -> int:
    """Идемпотентный сид справочника. Метаданные обновляем; influence_* НЕ
    перетираем, если в БД уже есть непустой авторский текст."""
    cfg = load_macro_config()
    n = 0
    for ind in cfg["indicators"]:
        row = db.get(MacroIndicator, ind["code"])
        if row is None:
            db.add(MacroIndicator(
                code=ind["code"], title=ind["title"], unit=ind.get("unit"),
                country=ind.get("country", "ru"), frequency=ind.get("frequency"),
                metric_types=ind.get("metric_types"),
                influence_short=ind.get("influence_short"),
                influence_full=ind.get("influence_full"),
                source_type=ind.get("source_type"),
                display_group=ind.get("display_group", "ru"),
                sort_order=ind.get("sort_order", 100),
                sectors=ind.get("sectors"),
            ))
            n += 1
        else:
            row.title = ind["title"]; row.unit = ind.get("unit")
            row.country = ind.get("country", "ru"); row.frequency = ind.get("frequency")
            row.metric_types = ind.get("metric_types")
            row.source_type = ind.get("source_type")
            row.display_group = ind.get("display_group", "ru")
            row.sort_order = ind.get("sort_order", 100)
            # influence_* — только если ещё пусто (не затираем правки владельца)
            if not row.influence_short and ind.get("influence_short"):
                row.influence_short = ind["influence_short"]
            if not row.influence_full and ind.get("influence_full"):
                row.influence_full = ind["influence_full"]
    db.commit()
    logger.info("Справочник макропоказателей: добавлено %d новых", n)
    return n


# Приоритет каналов: официальный первоисточник важнее Ленты. Лента (news) — ранний
# сигнал/резерв и НЕ перезаписывает официальную точку; официальный канал перезаписывает
# ленточную, когда выходит. file — исторический бэкфилл.
_VIA_PRIORITY = {"news": 0, "file": 1, "fred": 2, "wb": 2,
                 "cbr": 3, "rosstat": 3, "minfin": 3}


# ----------------------------- общий upsert точки -----------------------------
def upsert_point(db: Session, code: str, as_of: date, metric: str, value, *,
                 unit: str | None = None, is_preliminary: bool = False,
                 source: str | None = None, source_url: str | None = None,
                 ingested_via: str | None = None, commit: bool = True) -> str:
    """Вставить/обновить точку ряда. Уникальность (code, as_of, metric).
    Лента НЕ перезаписывает официальную точку (приоритет источника).
    Возвращает 'insert' | 'revise' | 'same' | 'skip' | 'kept'."""
    try:
        val = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "skip"
    existing = (db.query(MacroDataPoint)
                .filter_by(indicator_code=code, as_of=as_of, metric=metric).first())
    if existing is not None and ingested_via:
        if _VIA_PRIORITY.get(ingested_via, 1) < _VIA_PRIORITY.get(existing.ingested_via, 1):
            return "kept"  # ленту поверх официального не кладём
    if existing is None:
        db.add(MacroDataPoint(
            indicator_code=code, as_of=as_of, metric=metric, value=val, unit=unit,
            is_preliminary=is_preliminary, source=source, source_url=source_url,
            ingested_via=ingested_via))
        if commit:
            db.commit()
        return "insert"
    # ревизия: обновляем, если значение изменилось (или уточнение preliminary→final)
    changed = existing.value != val or (existing.is_preliminary and not is_preliminary)
    if changed:
        existing.value = val
        existing.is_preliminary = is_preliminary
        existing.revised_at = datetime.now(timezone.utc)
        if source:
            existing.source = source
        if source_url:
            existing.source_url = source_url
        if ingested_via:
            existing.ingested_via = ingested_via
        if commit:
            db.commit()
        return "revise"
    if commit:
        db.commit()
    return "same"


# ----------------------------- бэкфилл из CSV -----------------------------
def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def backfill_from_csv(db: Session) -> dict:
    """Разовый/идемпотентный импорт сырых рядов из cb_model_big.csv по маппингу.
    ML-фичи (нет в csv_mapping) игнорируются. Точки помечаются ingested_via='file'."""
    if not os.path.exists(_CSV):
        logger.warning("Бэкфилл: файл %s не найден", _CSV)
        return {"error": "csv not found"}
    cfg = load_macro_config()
    mapping = cfg["csv_mapping"]
    units = {i["code"]: i.get("unit") for i in cfg["indicators"]}
    inserted = revised = 0
    rows = 0
    with open(_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            d = _parse_date(r.get("Date"))
            if not d:
                continue
            rows += 1
            for col, m in mapping.items():
                raw = (r.get(col) or "").strip()
                if raw == "" or raw.lower() in ("nan", "na", "none"):
                    continue
                res = upsert_point(db, m["code"], d, m["metric"], raw,
                                   unit=units.get(m["code"]), source="cb_model file",
                                   ingested_via="file", commit=False)
                if res == "insert":
                    inserted += 1
                elif res == "revise":
                    revised += 1
    db.commit()
    summary = {"rows": rows, "inserted": inserted, "revised": revised}
    logger.info("Бэкфилл CSV: %s", summary)
    return summary


# ----------------------------- ЦБ РФ: дневные курсы -----------------------------
_CBR_DAILY = "https://www.cbr.ru/scripts/XML_daily.asp"
_HTTP = {"User-Agent": "BasisMacroBot/1.0 (+https://inbasis.ru)"}


def ingest_cbr_currencies(db: Session) -> dict:
    """Официальные дневные курсы USD/CNY/EUR с ЦБ (XML_daily). Идемпотентно по дате."""
    try:
        r = httpx.Client(timeout=20, headers=_HTTP).get(_CBR_DAILY)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:  # noqa: BLE001
        logger.warning("ЦБ курсы недоступны: %s", type(e).__name__)
        return {"error": "cbr unavailable"}
    d = root.get("Date")  # dd.mm.yyyy
    try:
        as_of = datetime.strptime(d, "%d.%m.%Y").date()
    except (TypeError, ValueError):
        as_of = date.today()
    mapping = {"USD": "usdrub", "CNY": "cnyrub", "EUR": "eurrub"}
    n = 0
    for v in root.findall("Valute"):
        cc = v.findtext("CharCode")
        if cc in mapping:
            nominal = float((v.findtext("Nominal") or "1").replace(",", "."))
            val = float((v.findtext("Value") or "0").replace(",", "."))
            if nominal:
                res = upsert_point(db, mapping[cc], as_of, "level", round(val / nominal, 4),
                                   unit="руб", source="ЦБ РФ", source_url=_CBR_DAILY,
                                   ingested_via="cbr", commit=False)
                if res in ("insert", "revise"):
                    n += 1
    db.commit()
    return {"date": str(as_of), "updated": n}


# ----------------------------- FRED: мир -----------------------------
_FRED_OBS = "https://api.stlouisfed.org/fred/series/observations"


def ingest_fred(db: Session, recent: int = 48) -> dict:
    """Мировые показатели из FRED (units=pc1 даёт YoY%). Тянет последние `recent`
    наблюдений по каждому ряду. Ключ FRED_API_KEY — из env."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        logger.warning("FRED_API_KEY не задан — мировой блок пропущен")
        return {"error": "no FRED_API_KEY"}
    cfg = load_macro_config()
    units = {i["code"]: i.get("unit") for i in cfg["indicators"]}
    total = {"insert": 0, "revise": 0, "series": 0, "failed": []}
    client = httpx.Client(timeout=30, headers=_HTTP)
    for code, spec in cfg.get("fred_series", {}).items():
        try:
            r = client.get(_FRED_OBS, params={
                "series_id": spec["series"], "api_key": key, "file_type": "json",
                "units": spec.get("units", "lin"), "sort_order": "desc", "limit": recent})
            r.raise_for_status()
            obs = r.json().get("observations", [])
        except Exception as e:  # noqa: BLE001
            logger.warning("FRED %s (%s) недоступен: %s", code, spec["series"], type(e).__name__)
            total["failed"].append(code)
            continue
        total["series"] += 1
        for o in obs:
            if o.get("value") in (".", "", None):
                continue
            try:
                as_of = datetime.strptime(o["date"], "%Y-%m-%d").date()
            except ValueError:
                continue
            res = upsert_point(db, code, as_of, spec.get("metric", "level"), o["value"],
                               unit=units.get(code), source="FRED",
                               source_url=f"https://fred.stlouisfed.org/series/{spec['series']}",
                               ingested_via="fred", commit=False)
            if res in total:
                total[res] += 1
    db.commit()
    return total


# ----------------------------- World Bank: мировой ВВП -----------------------------
def ingest_worldbank(db: Session) -> dict:
    cfg = load_macro_config()
    units = {i["code"]: i.get("unit") for i in cfg["indicators"]}
    n = 0
    for code, spec in cfg.get("worldbank_series", {}).items():
        url = (f"https://api.worldbank.org/v2/country/WLD/indicator/{spec['indicator']}"
               f"?format=json&per_page=20&mrv=20")
        try:
            r = httpx.Client(timeout=20, headers=_HTTP).get(url)
            j = r.json()
            rows = j[1] if isinstance(j, list) and len(j) > 1 else []
        except Exception as e:  # noqa: BLE001
            logger.warning("World Bank %s недоступен: %s", code, type(e).__name__)
            continue
        for d in rows:
            if d.get("value") is None:
                continue
            try:
                as_of = date(int(d["date"]), 12, 31)
            except (ValueError, TypeError):
                continue
            res = upsert_point(db, code, as_of, spec.get("metric", "yoy"), d["value"],
                               unit=units.get(code), source="World Bank",
                               source_url=url, ingested_via="wb", commit=False)
            if res in ("insert", "revise"):
                n += 1
    db.commit()
    return {"updated": n}


def ingest_all_world(db: Session) -> dict:
    """ЦБ-курсы + FRED + World Bank — дневной мировой/курсовой ингест."""
    return {"cbr": ingest_cbr_currencies(db), "fred": ingest_fred(db), "wb": ingest_worldbank(db)}


# ----------------------------- ЦБ: история курсов (бэкфилл) -----------------------------
_CBR_DYNAMIC = "https://www.cbr.ru/scripts/XML_dynamic.asp"
_CBR_VAL = {"usdrub": "R01235", "eurrub": "R01239", "cnyrub": "R01375"}


def backfill_cbr_currency_history(db: Session, years: int = 4) -> dict:
    """Дневная история курсов USD/CNY/EUR с ЦБ за `years` лет (идемпотентно)."""
    end = date.today()
    start = date(end.year - years, end.month, end.day)
    total = 0
    for code, vcode in _CBR_VAL.items():
        try:
            r = httpx.Client(timeout=40, headers=_HTTP).get(_CBR_DYNAMIC, params={
                "date_req1": start.strftime("%d/%m/%Y"), "date_req2": end.strftime("%d/%m/%Y"),
                "VAL_NM_RQ": vcode})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            logger.warning("ЦБ история %s недоступна: %s", code, type(e).__name__)
            continue
        for rec in root.findall("Record"):
            try:
                d = datetime.strptime(rec.get("Date"), "%d.%m.%Y").date()
            except (TypeError, ValueError):
                continue
            nominal = float((rec.findtext("Nominal") or "1").replace(",", "."))
            val = float((rec.findtext("Value") or "0").replace(",", "."))
            if nominal:
                res = upsert_point(db, code, d, "level", round(val / nominal, 4), unit="руб",
                                   source="ЦБ РФ", source_url=_CBR_DYNAMIC, ingested_via="cbr",
                                   commit=False)
                if res in ("insert", "revise"):
                    total += 1
    db.commit()
    logger.info("ЦБ: бэкфилл истории курсов — %d точек", total)
    return {"points": total}


# ----------------------------- надёжность: проверка устаревания -----------------------------
# Допустимый «возраст» последней точки по частоте (дней) — сверх него ряд считается
# залипшим (источник перестал обновляться) → алерт в лог.
_STALE_DAYS = {"daily": 7, "weekly": 21, "monthly": 75, "quarterly": 140, "yearly": 500}


def check_staleness(db: Session) -> list[dict]:
    """Найти ряды, которые перестали обновляться (последняя точка старше нормы частоты).
    Логирует предупреждение по каждому — чтобы владелец узнал, что источник замолчал."""
    today = date.today()
    stale = []
    for ind in db.query(MacroIndicator).all():
        thr = _STALE_DAYS.get(ind.frequency or "monthly", 75)
        for m in (ind.metric_types or ["level"]):
            p = (db.query(MacroDataPoint).filter_by(indicator_code=ind.code, metric=m)
                 .order_by(MacroDataPoint.as_of.desc()).first())
            if p is None:
                continue
            age = (today - p.as_of).days
            if age > thr:
                stale.append({"code": ind.code, "metric": m, "last": str(p.as_of),
                              "age_days": age, "via": p.ingested_via})
    if stale:
        logger.warning("МАКРО-АЛЕРТ: %d рядов не обновляются дольше нормы: %s",
                       len(stale), ", ".join(f"{s['code']}/{s['metric']}({s['age_days']}д)" for s in stale[:15]))
    return stale
