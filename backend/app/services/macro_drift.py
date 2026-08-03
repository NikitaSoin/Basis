"""Детектор макро-дрейфа карточек: у кого разбор устарел и насколько это дорого.

🔴 ЗАЧЕМ (владелец, 2026-08-04): «нужно, чтобы вкладка макроэкономика у карточек
обновлялась с учётом оценки макроситуации в Обозревателе, статей ЦБ/ЦМАКП/Re:Russia
и новых вводных».

Разбор на вкладке «Макроэкономика» писался в конкретный день при конкретных условиях
(у большинства карточек — начало июля 2026). С тех пор Brent ушёл с ~$69 к ~$90, а
ключевая с 15% к 14%. Числа на витрине подменяются живыми (`macro_snapshot_live`), но
СУЖДЕНИЕ — «дорогой макрофон», «рублёвая выручка с барреля сжимается» — осталось от
того дня и теперь может противоречить самому себе.

Этот модуль — первое звено: он находит, ЧЬЙ разбор разошёлся с реальностью и на
сколько это дорого для компании. Без него агент-переработчик пришлось бы гонять по
всем 264 карточкам вслепую.

🔴 ТОЧКА ОТСЧЁТА — СНИМОК В КАРТОЧКЕ, А НЕ РЯД ИЗ БД. В карточке лежит `snapshot`:
значения, которые аналитик ВИДЕЛ, когда писал разбор. Ряды в БД мы задним числом
чиним (в этой же сессии переписали цену Urals), и тогда «дрейф» покажет нашу
собственную правку данных вместо изменения мира. Снимок карточки такого не умеет.
Ряд на дату разбора — фолбэк, когда снимка нет.

🔴 ВАЖНОСТЬ МЕРИМ ДЕНЬГАМИ, А НЕ ДАВНОСТЬЮ. «Разбору 40 дней» ничего не значит: у
защитной компании ставка может ходить на 2 п.п. без последствий, а у застройщика тот
же сдвиг переворачивает картину. Поэтому дрейф прогоняется через КОЭФФИЦИЕНТЫ
ЧУВСТВИТЕЛЬНОСТИ самой карточки (`scenario_transmission`) — и очередь строится по
эффекту на прибыль, а не по календарю.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Канал чувствительности → как достать его текущее значение и как опознать в снимке.
# Единица дрейфа совпадает с `per` коэффициентов карточек: ставка и инфляция в
# процентных пунктах, курс в рублях за доллар, нефть в долларах за баррель.
_CHANNELS = {
    "rate": {
        "code": ("key_rate", "level"),
        "match": re.compile(r"ключев\w*\s+ставк", re.I),
        "unit": "п.п.",
        "title": "ключевая ставка",
        # Ниже порога это шум решений ЦБ, а не смена картины.
        "threshold": 1.0,
    },
    "cost_inflation": {
        "code": ("inflation", "yoy"),
        "match": re.compile(r"инфляци", re.I),
        "unit": "п.п.",
        "title": "инфляция",
        "threshold": 1.0,
    },
    "fx": {
        "code": ("usdrub", "level"),
        "match": re.compile(r"usd\s*/\s*rub|курс\s+доллар|рубл\w*\s+к\s+доллар", re.I),
        "unit": "₽/$",
        "title": "курс рубля",
        "threshold": 5.0,
    },
    "commodity": {
        "code": ("oil_brent", "level"),
        "match": re.compile(r"brent|urals|нефт", re.I),
        "unit": "$/барр",
        "title": "нефть",
        "threshold": 8.0,
    },
}

# Эффект ниже этого порога не стоит прогона агента: разбор от него не изменится.
_MIN_IMPACT_PCT = 5.0
# Потолок для СОРТИРОВКИ (не для отбора). У компании с околонулевой прибылью дрейф даёт
# десятки тысяч процентов — это свойство базы, а не сила события, и наверх очереди такие
# строки пускать нельзя. Из очереди при этом не выбрасываем: разбор у них тоже устарел.
_RANK_CAP_PCT = 300.0
# 🔴 Канал commodity в карточках ОБОБЩЁННЫЙ: нефть у нефтяников, титан у ВСМПО, уголь у
# угольщиков, золото у добытчиков. Подставлять всем цену Brent нельзя — на этом уже
# стоял стресс-тест (2026-07-17: «обвал нефти» давал Полюсу −17,8%). Поэтому нефтяной
# дрейф считаем, только если сама карточка называет нефть в снимке.
_OIL_NAMED = re.compile(r"brent|urals|нефт", re.I)
# Инфляционные ожидания и прочее в снимке идут в процентах — отсекаем заведомо чужие
# величины, чтобы «Чистый долг / EBITDA 2,1» не попал в ставку.
_SANE_RANGE = {"rate": (2.0, 30.0), "cost_inflation": (0.0, 30.0),
               "fx": (30.0, 200.0), "commodity": (10.0, 200.0)}


def _load(ticker: str, name: str) -> dict | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _parse_number(raw: str) -> float | None:
    """«14,25%» → 14.25; «≈ 78 ₽» → 78.0; «$55» → 55.0; «~$60-65» → 62.5."""
    if not raw:
        return None
    cleaned = str(raw).replace(" ", " ").replace(",", ".")
    # 🔴 Дефис между цифрами — это ДИАПАЗОН, а не знак минус. Без нормализации
    # «~$60-65» разбиралось как 60 и −65, а среднее давало −2,5: правдоподобное на
    # вид число, которое молча ломало бы весь дрейф.
    is_range = bool(re.search(r"\d\s*[–—-]\s*\d", cleaned))
    if is_range:
        cleaned = re.sub(r"(\d)\s*[–—-]\s*(\d)", r"\1 \2", cleaned)
    nums = re.findall(r"-?\d+(?:\.\d+)?", cleaned)
    if not nums:
        return None
    values = [float(n) for n in nums[:2]]
    # Диапазон — берём середину: аналитик имел в виду интервал, а не две величины.
    if is_range and len(values) == 2:
        return sum(values) / 2
    return values[0]


def baseline_from_card(macro: dict) -> dict[str, float]:
    """Что видел аналитик, когда писал разбор (из `snapshot` карточки)."""
    out: dict[str, float] = {}
    for item in macro.get("snapshot") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("indicator") or "")
        for channel, spec in _CHANNELS.items():
            if channel in out or not spec["match"].search(name):
                continue
            value = _parse_number(str(item.get("value") or ""))
            if value is None:
                continue
            low, high = _SANE_RANGE[channel]
            if low <= value <= high:
                out[channel] = value
    return out


def _series_value(db: Session, code: str, metric: str, on: date | None = None) -> float | None:
    sql = ("SELECT value FROM macro_data_points WHERE indicator_code=:c AND metric=:m "
           + ("AND as_of<=:d " if on else "")
           + "ORDER BY as_of DESC LIMIT 1")
    params = {"c": code, "m": metric}
    if on:
        params["d"] = on
    row = db.execute(text(sql), params).first()
    return float(row[0]) if row and row[0] is not None else None


def current_macro(db: Session) -> dict[str, float]:
    out = {}
    for channel, spec in _CHANNELS.items():
        value = _series_value(db, *spec["code"])
        if value is not None:
            out[channel] = value
    return out


def company_drift(db: Session, ticker: str, now: dict[str, float] | None = None) -> dict | None:
    """Насколько условия ушли от тех, при которых писался разбор, и чего это стоит."""
    macro = _load(ticker, "macro.json")
    if not macro:
        return None
    meta = macro.get("meta") or {}
    as_of_raw = str(meta.get("as_of") or "")
    try:
        as_of = date.fromisoformat(as_of_raw)
    except ValueError:
        as_of = None
    now = now if now is not None else current_macro(db)
    # 🔴 Считаем дрейф ТОЛЬКО по каналам, заведённым в самой карточке. Иначе телеком
    # получает «дрейф нефти +$21» из общего фолбэка — формально правда, содержательно
    # шум: у МТС нефтяного канала нет и разбор от неё не зависит.
    own = set((macro.get("quant_inputs") or {}).get("coefficients") or {})
    baseline = {k: v for k, v in baseline_from_card(macro).items() if k in own}
    # Нефть засчитываем ТОЛЬКО когда карточка сама её называет: иначе титан ВСМПО и
    # уголь Белона получат дрейф цены нефти и возглавят очередь по чужому поводу.
    oil_named = any(_OIL_NAMED.search(str(i.get("indicator") or ""))
                    for i in (macro.get("snapshot") or []) if isinstance(i, dict))
    if not oil_named:
        baseline.pop("commodity", None)
    # Фолбэк: снимок не распознан — берём ряд на дату разбора. Хуже, но лучше молчания.
    for channel, spec in _CHANNELS.items():
        if channel not in own or (channel == "commodity" and not oil_named):
            continue
        if channel not in baseline and as_of:
            value = _series_value(db, *spec["code"], on=as_of)
            if value is not None:
                baseline[channel] = value

    drift = {}
    for channel, was in baseline.items():
        if channel not in now:
            continue
        delta = round(now[channel] - was, 2)
        if abs(delta) >= _CHANNELS[channel]["threshold"]:
            drift[channel] = {"was": was, "now": now[channel], "delta": delta,
                              "unit": _CHANNELS[channel]["unit"],
                              "title": _CHANNELS[channel]["title"]}
    if not drift:
        return None

    # Дрейф → деньги: те же коэффициенты, что считают сценарии. Компания без
    # коэффициента по каналу на него просто не реагирует — это честная деградация,
    # а не «нулевой эффект».
    impact = None
    try:
        from app.services.scenario_transmission import company_impact
        impact = company_impact(ticker, {c: d["delta"] for c, d in drift.items()},
                                drop_implausible=False)
    except Exception:  # noqa: BLE001
        logger.warning("macro_drift: эффект для %s не посчитан", ticker, exc_info=True)
    return {
        "ticker": ticker,
        "as_of": as_of_raw or None,
        "days_old": (date.today() - as_of).days if as_of else None,
        "drift": drift,
        "impact_pct": (impact or {}).get("profit_pct"),
        "impact_base": (impact or {}).get("base"),
        **({"beyond_plausible": True} if (impact or {}).get("beyond_plausible") else {}),
        "by_channel": (impact or {}).get("by_channel"),
    }


def drift_queue(db: Session, limit: int = 20,
                min_impact_pct: float = _MIN_IMPACT_PCT) -> list[dict]:
    """Очередь на переработку: у кого разбор разошёлся с реальностью дороже всего.

    Сортировка по величине эффекта, а не по давности: старый разбор защитной компании
    может быть по-прежнему верен, а свежий разбор застройщика — уже нет.
    """
    if not COMPANIES_DIR.exists():
        return []
    now = current_macro(db)
    if not now:
        logger.warning("macro_drift: текущее макро недоступно — очередь пуста")
        return []
    rows = []
    for d in sorted(COMPANIES_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        item = company_drift(db, d.name, now=now)
        if not item:
            continue
        impact = item.get("impact_pct")
        # Без посчитанного эффекта строку не выбрасываем: канал мог быть не заведён в
        # карточке, но дрейф реален. Такие идут в конец очереди.
        if impact is not None and abs(impact) < min_impact_pct:
            continue
        rows.append(item)
    # Сначала достоверные эффекты по убыванию, в конце — те, где база несопоставима
    # (околонулевая прибыль даёт тысячи процентов). Их разбор тоже устарел, но число
    # недостоверно, и занимать верх очереди они не должны.
    rows.sort(key=lambda r: (bool(r.get("beyond_plausible")),
                             -min(abs(r.get("impact_pct") or 0), _RANK_CAP_PCT)))
    return rows[:limit]


def drift_digest(db: Session) -> dict:
    """Сводка для диспетчера и для промпта: что изменилось и кого это задело."""
    now = current_macro(db)
    queue = drift_queue(db, limit=200)
    return {
        "as_of": datetime.now().date().isoformat(),
        "current": now,
        "affected": len(queue),
        "top": queue[:15],
        "_note": "Дрейф — расхождение между условиями, при которых писался разбор, и "
                 "сегодняшними. Эффект посчитан по коэффициентам самой карточки.",
    }
