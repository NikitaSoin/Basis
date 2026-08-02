"""«ОТК данных» Макрообзора — автоматическая проверка, что данные на платформе
верные и свежие (владелец, 2026-07-25: «надо чтобы не я вручную замечал баги —
автоматическая подгрузка из правильных мест и отдельная проверка, правильно ли
данные загрузились»).

Три типа проверок (по одобренному плану):
- calendar — обновились ли данные после ОЖИДАЕМОГО СОБЫТИЯ: заседание ЦБ по
  календарю cbr.ru/dkp/cal_mp/ (ставка в тот же день, прогноз на «опорных»),
  недельная инфляция по средам, ожидания/ИБК по месячному графику публикаций;
- cross — значение в БД сверено с НЕЗАВИСИМЫМ путём (другая страница и/или
  другой парсер, чем при загрузке): урок багов 2026-07-25 — один источник +
  один парсер дают КОРРЕЛИРОВАННЫЕ ошибки, ловит только независимый путь.
  Где ЦБ отдаёт машинную таблицу (hd_base) — сверка детерминированная, без LLM;
- delta — значение не прыгнуло неправдоподобно за один шаг (ставка ±3пп за
  заседание и т.п.); ловит класс «цена сахара записана как инфляция».

Каждый прогон пишет полный набор строк в macro_verifications (история хранится —
видно, когда проверка начала краснеть). Витрина (плашка в Обозревателе →
Экономическая статистика, вариант «б» владельца) берёт последний прогон через
latest_results(). Прогон ежедневный (крон, вечер) — после всех дневных синков.

ПРИНЦИП: проверка только СИГНАЛИТ, никогда не правит данные сама (v1) — иначе
проверяльщик может сам внести ошибку, которую уже никто не поймает.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.models.macro import (MacroDataPoint, MacroForecast, MacroVerification,
                              RateMeeting)

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "BasisMacroBot/1.0 (+https://inbasis.ru)"}
_CAL_URL = "https://www.cbr.ru/dkp/cal_mp/"
_KEYRATE_TABLE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
_INFL_TABLE_URL = "https://www.cbr.ru/hd_base/infl/"
_MOEX_USD_URL = ("https://iss.moex.com/iss/engines/currency/markets/selt/"
                 "securities/USD000UTSTOM.json?iss.only=marketdata&marketdata.columns=LAST")
_RATE_PRESS_URL = "https://www.cbr.ru/press/keypr/"

_MONTHS_GEN = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
               "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
               "декабря": 12}


def _get(url: str, timeout: int = 25) -> str | None:
    try:
        r = httpx.Client(timeout=timeout, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("ОТК данных: %s недоступен: %s", url, type(e).__name__)
        return None


def _res(key: str, type_: str, title: str, status: str, message: str | None = None,
         **details) -> dict:
    return {"check_key": key, "check_type": type_, "title": title, "status": status,
            "message": message, "details": details or None}


def _latest_point(db: Session, code: str, metric: str) -> MacroDataPoint | None:
    return (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).first())


def _last_two_points(db: Session, code: str, metric: str) -> list[MacroDataPoint]:
    return (db.query(MacroDataPoint).filter_by(indicator_code=code, metric=metric)
            .order_by(MacroDataPoint.as_of.desc()).limit(2).all())


# ----------------------------- календарь заседаний ЦБ -----------------------------
def fetch_cb_meeting_calendar() -> list[dict] | None:
    """[{"date": date, "has_forecast": bool}, ...] по возрастанию — все заседания
    Совета директоров по ставке из официального календаря ЦБ на текущий год.
    has_forecast=True — «опорное» заседание (в календаре у него явная строка
    «Среднесрочный прогноз» — ЦБ публикует обновлённый прогноз в день решения).
    None — страница недоступна (не путать с «заседаний нет»)."""
    html = _get(_CAL_URL)
    if not html:
        return None
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ")
    text = re.sub(r"\s+", " ", text)
    month_re = "|".join(_MONTHS_GEN)
    # Все даты «24 июля 2026 года» с позициями; заседание — та, за которой сразу
    # идёт «Заседание Совета директоров». Слайс до СЛЕДУЮЩЕЙ любой даты содержит
    # список публикаций этого события — ищем в нём «Среднесрочный прогноз».
    tokens = [(m.start(), m.end(), int(m.group(1)), _MONTHS_GEN[m.group(2)], int(m.group(3)))
              for m in re.finditer(rf"(\d{{1,2}})\s+({month_re})\s+(\d{{4}})\s+года", text)]
    meetings: list[dict] = []
    for i, (start, end, dd, mm, yyyy) in enumerate(tokens):
        tail_end = tokens[i + 1][0] if i + 1 < len(tokens) else len(text)
        chunk = text[end:tail_end]
        if not chunk.lstrip().startswith("Заседание Совета директоров"):
            continue
        try:
            d = date(yyyy, mm, dd)
        except ValueError:
            continue
        meetings.append({"date": d, "has_forecast": "Среднесрочный прогноз" in chunk})
    meetings.sort(key=lambda m: m["date"])
    return meetings or None


# ----------------------------- calendar-проверки -----------------------------
def _check_rate_after_meeting(db: Session, meetings: list[dict] | None) -> dict:
    key, t, title = "calendar_rate_meeting", "calendar", "Ставка обновлена после заседания ЦБ"
    if meetings is None:
        return _res(key, t, title, "unavailable", "Календарь заседаний ЦБ недоступен")
    past = [m for m in meetings if m["date"] <= date.today()]
    if not past:
        return _res(key, t, title, "ok", "Заседаний в этом году ещё не было")
    last = past[-1]["date"]
    p = _latest_point(db, "key_rate", "level")
    mtg = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
    point_ok = p is not None and p.as_of >= last
    meeting_ok = mtg is not None and mtg.decision_date >= last
    if point_ok and meeting_ok:
        return _res(key, t, title, "ok",
                    f"Заседание {last.strftime('%d.%m.%Y')} отражено (ставка {p.value}%)",
                    meeting_date=str(last), db_value=float(p.value), db_as_of=str(p.as_of))
    return _res(key, t, title, "fail",
                f"Заседание ЦБ было {last.strftime('%d.%m.%Y')}, но данные не обновились "
                f"(точка ставки: {p.as_of if p else 'нет'}; запись заседания: "
                f"{mtg.decision_date if mtg else 'нет'})",
                meeting_date=str(last),
                db_point_as_of=str(p.as_of) if p else None,
                db_meeting_date=str(mtg.decision_date) if mtg else None)


def _check_forecast_after_meeting(db: Session, meetings: list[dict] | None) -> dict:
    key, t, title = "calendar_forecast_meeting", "calendar", "Прогноз обновлён после опорного заседания"
    if meetings is None:
        return _res(key, t, title, "unavailable", "Календарь заседаний ЦБ недоступен")
    past = [m for m in meetings if m["date"] <= date.today() and m["has_forecast"]]
    if not past:
        return _res(key, t, title, "ok", "Опорных заседаний в этом году ещё не было")
    last = past[-1]["date"]
    row = db.query(MacroForecast).order_by(MacroForecast.as_of.desc()).first()
    if row is not None and row.as_of >= last:
        return _res(key, t, title, "ok",
                    f"Прогноз от {row.as_of.strftime('%d.%m.%Y')} (опорное заседание "
                    f"{last.strftime('%d.%m.%Y')})",
                    meeting_date=str(last), forecast_as_of=str(row.as_of))
    return _res(key, t, title, "fail",
                f"Опорное заседание было {last.strftime('%d.%m.%Y')} (ЦБ публикует "
                f"обновлённый среднесрочный прогноз в день решения), а последний прогноз "
                f"в БД — от {row.as_of.strftime('%d.%m.%Y') if row else 'никогда'}",
                meeting_date=str(last), forecast_as_of=str(row.as_of) if row else None)


def _check_monthly_due(db: Session, code: str, metric: str, due_day: int,
                       key: str, title: str, what: str) -> dict:
    """Месячная публикация: после числа due_day текущего месяца точка за ТЕКУЩИЙ месяц
    должна быть в БД (у месячных рядов as_of = конец месяца-периода)."""
    today = date.today()
    p = _latest_point(db, code, metric)
    if p is None:
        return _res(key, "calendar", title, "fail", f"{what}: в БД нет ни одной точки")
    age = (today - p.as_of).days
    if today.day > due_day:
        fresh = p.as_of.year == today.year and p.as_of.month == today.month
        if not fresh and age > 45:
            return _res(key, "calendar", title, "fail",
                        f"{what}: ожидалась публикация до {due_day} числа, последняя точка — "
                        f"{p.as_of.strftime('%d.%m.%Y')} ({age} дн. назад)",
                        db_as_of=str(p.as_of), age_days=age)
        if not fresh:
            return _res(key, "calendar", title, "warn",
                        f"{what}: за текущий месяц ещё нет (обычно публикуется до "
                        f"{due_day} числа); последняя — {p.as_of.strftime('%d.%m.%Y')}",
                        db_as_of=str(p.as_of), age_days=age)
    return _res(key, "calendar", title, "ok",
                f"{what}: {p.value} на {p.as_of.strftime('%d.%m.%Y')}",
                db_as_of=str(p.as_of), db_value=float(p.value))


def _check_weekly_inflation_fresh(db: Session) -> dict:
    """Свежесть — от КАЛЕНДАРЯ ПУБЛИКАЦИИ, а не от возраста последней точки.

    Прежний критерий «age ≤ 9 дней → ok» пропустил бы невышедшую среду ещё неделю:
    в четверг после пропущенной публикации точке прошлой недели всего 10 дней.
    Владелец заметил пропуск НА СЛЕДУЮЩИЙ ДЕНЬ (2026-07-30) — проверка обязана
    замечать не позже него. Ожидаемый понедельник считает macro_weekly_watch
    (публикация в среду ~16:00 МСК за неделю по понедельник этой же недели):
    точки за него нет → warn сразу, со следующего дня → fail."""
    from app.services.macro_weekly_watch import _expected_week_end
    key, t, title = "calendar_weekly_inflation", "calendar", "Недельная инфляция выходит по графику"
    p = _latest_point(db, "inflation_weekly", "wow")
    if p is None:
        return _res(key, t, title, "fail", "Недельная инфляция: в БД нет ни одной точки")
    expected = _expected_week_end()
    lag = (expected - p.as_of).days
    if lag <= 0:
        status, msg = "ok", f"Последняя неделя: {p.value}% на {p.as_of.strftime('%d.%m.%Y')}"
    elif (date.today() - expected).days <= 3:
        status, msg = "warn", (f"Ожидалась публикация за неделю по {expected.strftime('%d.%m.%Y')} "
                               f"(среда, вторая половина дня) — в БД последняя точка "
                               f"{p.as_of.strftime('%d.%m.%Y')}")
    else:
        status, msg = "fail", (f"Недельная инфляция за неделю по {expected.strftime('%d.%m.%Y')} "
                               f"так и не получена (последняя — {p.as_of.strftime('%d.%m.%Y')})")
    return _res(key, t, title, status, msg, db_as_of=str(p.as_of),
                expected_week_end=str(expected), lag_days=lag)


# ----------------------------- cross-проверки -----------------------------
def _check_cross_key_rate(db: Session) -> dict:
    key, t, title = "cross_key_rate", "cross", "Ключевая ставка сверена с таблицей ЦБ"
    html = _get(_KEYRATE_TABLE_URL)
    if not html:
        return _res(key, t, title, "unavailable", "Таблица hd_base/KeyRate недоступна")
    rows = re.findall(r"<tr[^>]*>\s*<td[^>]*>\s*(\d{2}\.\d{2}\.\d{4})\s*</td>\s*"
                      r"<td[^>]*>\s*([\d,.]+)\s*</td>", html)
    if not rows:
        return _res(key, t, title, "unavailable",
                    "Таблица hd_base/KeyRate не распарсилась (смена вёрстки?)")
    ref_date_s, ref_val_s = rows[0]
    ref_val = float(ref_val_s.replace(",", "."))
    pts = _last_two_points(db, "key_rate", "level")
    if not pts:
        return _res(key, t, title, "fail", "В БД нет точек ключевой ставки")
    db_latest = float(pts[0].value)
    # hd_base — ставка, ДЕЙСТВУЮЩАЯ в конкретный день; наша точка — по дате РЕШЕНИЯ.
    # Решение вступает в силу через несколько дней (обычно следующий рабочий
    # понедельник), поэтому сразу после заседания hd_base ещё показывает старую
    # ставку — это НЕ расхождение. Грейс: если решение было < 7 дней назад,
    # совпадение hd_base с ПРЕДЫДУЩЕЙ нашей точкой тоже ок.
    tol = 0.011
    if abs(db_latest - ref_val) < tol:
        return _res(key, t, title, "ok", f"Совпадает: {db_latest}%",
                    db_value=db_latest, ref_value=ref_val, ref_date=ref_date_s,
                    ref_url=_KEYRATE_TABLE_URL)
    recent_decision = (date.today() - pts[0].as_of).days < 7
    if recent_decision and len(pts) > 1 and abs(float(pts[1].value) - ref_val) < tol:
        return _res(key, t, title, "ok",
                    f"Новое решение ({db_latest}%) ещё не вступило в силу — hd_base "
                    f"показывает прежнюю ставку {ref_val}% (норма первые дни после заседания)",
                    db_value=db_latest, ref_value=ref_val, ref_date=ref_date_s)
    return _res(key, t, title, "fail",
                f"РАСХОЖДЕНИЕ: в БД {db_latest}%, в официальной таблице ЦБ {ref_val}% "
                f"(на {ref_date_s})",
                db_value=db_latest, ref_value=ref_val, ref_date=ref_date_s,
                ref_url=_KEYRATE_TABLE_URL)


def _check_cross_inflation(db: Session) -> dict:
    key, t, title = "cross_inflation", "cross", "Инфляция г/г сверена с таблицей ЦБ"
    html = _get(_INFL_TABLE_URL)
    if not html:
        return _res(key, t, title, "unavailable", "Таблица hd_base/infl недоступна")
    row_m = None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(cells) >= 3 and re.match(r"^\d{2}\.\d{4}$", cells[0]):
            row_m = cells
            break
    if not row_m:
        return _res(key, t, title, "unavailable",
                    "Таблица hd_base/infl не распарсилась (смена вёрстки?)")
    mm, yyyy = int(row_m[0][:2]), int(row_m[0][3:])
    ref_val = float(row_m[2].replace(",", "."))
    nxt = date(yyyy + (mm == 12), (mm % 12) + 1, 1)
    month_end = nxt - timedelta(days=1)
    db_p = (db.query(MacroDataPoint)
            .filter_by(indicator_code="inflation", metric="yoy", as_of=month_end).first())
    if db_p is None:
        return _res(key, t, title, "warn",
                    f"У ЦБ есть официальное значение за {mm:02d}.{yyyy} ({ref_val}%), "
                    f"а в БД точки за этот месяц нет",
                    ref_value=ref_val, ref_month=f"{yyyy}-{mm:02d}", ref_url=_INFL_TABLE_URL)
    db_val = float(db_p.value)
    if abs(db_val - ref_val) <= 0.06:
        return _res(key, t, title, "ok", f"Совпадает за {mm:02d}.{yyyy}: {db_val}%",
                    db_value=db_val, ref_value=ref_val, ref_month=f"{yyyy}-{mm:02d}")
    return _res(key, t, title, "fail",
                f"РАСХОЖДЕНИЕ за {mm:02d}.{yyyy}: в БД {db_val}%, в официальной "
                f"таблице ЦБ {ref_val}%",
                db_value=db_val, ref_value=ref_val, ref_month=f"{yyyy}-{mm:02d}",
                ref_url=_INFL_TABLE_URL)


def _check_cross_usdrub(db: Session) -> dict:
    key, t, title = "cross_usdrub", "cross", "Курс USD/RUB сверен с Мосбиржей"
    p = _latest_point(db, "usdrub", "level")
    if p is None:
        return _res(key, t, title, "fail", "В БД нет точек курса USD/RUB")
    raw = _get(_MOEX_USD_URL, timeout=15)
    if not raw:
        return _res(key, t, title, "unavailable", "MOEX ISS недоступен")
    try:
        import json as _json
        data = _json.loads(raw)
        lasts = [r[0] for r in data.get("marketdata", {}).get("data", []) if r and r[0]]
        ref_val = float(lasts[0]) if lasts else None
    except Exception:  # noqa: BLE001
        ref_val = None
    if ref_val is None:
        return _res(key, t, title, "unavailable",
                    "MOEX ISS не вернул цену (выходной/не торгуется) — сверка пропущена")
    db_val = float(p.value)
    diff_pct = abs(db_val - ref_val) / ref_val * 100
    # Официальный курс ЦБ и биржевой различаются по времени фиксации — допуск щедрый.
    if diff_pct <= 2.5:
        return _res(key, t, title, "ok",
                    f"БД {db_val:.2f} (офиц. ЦБ) vs биржа {ref_val:.2f} — в допуске",
                    db_value=db_val, ref_value=ref_val, diff_pct=round(diff_pct, 2))
    return _res(key, t, title, "fail",
                f"РАСХОЖДЕНИЕ: курс в БД {db_val:.2f} отличается от биржевого "
                f"{ref_val:.2f} на {diff_pct:.1f}% — вероятно, курс в БД устарел/неверен",
                db_value=db_val, ref_value=ref_val, diff_pct=round(diff_pct, 2))


def _norm_range(s: str) -> str:
    return re.sub(r"[–—−]", "-", (s or "")).replace(" ", "").replace("%", "")


def _check_cross_forecast(db: Session) -> dict:
    """Диапазоны средней ключевой ставки из ТЕКСТА пресс-релиза (регулярка, без LLM)
    против таблицы MacroForecast. Ловит и «прогноз не подтянулся», и «LLM извлёк
    не те числа»."""
    key, t, title = "cross_forecast", "cross", "Прогноз ставки сверен с пресс-релизом ЦБ"
    from app.services.macro_cb_sync import _fetch_text
    text = _fetch_text(_RATE_PRESS_URL)
    if not text:
        return _res(key, t, title, "unavailable", "Пресс-релиз ЦБ недоступен")
    pairs = re.findall(r"диапазоне\s+([\d,]+\s*[-–—]\s*[\d,]+)\s*%\s+годовых\s+в\s+(\d{4})\s+году",
                       text)
    if not pairs:
        return _res(key, t, title, "ok",
                    "В текущем пресс-релизе нет диапазонов прогноза (не опорное заседание) — "
                    "сверка не требуется")
    mismatches, checked = [], []
    for rng, yr in pairs:
        year = int(yr)
        row = (db.query(MacroForecast)
               .filter(MacroForecast.scenario == "базовый",
                       MacroForecast.indicator.ilike("%ключевая ставка%"),
                       MacroForecast.year == year)
               .order_by(MacroForecast.as_of.desc()).first())
        ref_n = _norm_range(rng)
        db_n = _norm_range(row.value) if row and row.value else None
        checked.append({"year": year, "press": ref_n, "db": db_n})
        if db_n != ref_n:
            mismatches.append(f"{year}: пресс-релиз «{ref_n}», БД «{db_n or 'нет'}»")
    if mismatches:
        return _res(key, t, title, "fail",
                    "РАСХОЖДЕНИЕ прогноза ставки с пресс-релизом ЦБ: " + "; ".join(mismatches),
                    checked=checked, ref_url=_RATE_PRESS_URL)
    return _res(key, t, title, "ok",
                f"Диапазоны ставки совпадают с пресс-релизом ({len(checked)} г.)",
                checked=checked)


def _check_cross_expectations(db: Session) -> dict:
    """Инфляционные ожидания против ДЕТЕРМИНИРОВАННОГО парсинга графика PDF-бюллетеня
    инФОМ (_parse_infom_chart — написан после бага 13,0-vs-14,7, когда LLM перепутал
    ряды). Постоянная защита от повторения ровно того бага."""
    key, t, title = "cross_expectations", "cross", "Инфл. ожидания сверены с бюллетенем инФОМ"
    from app.models.macro import MacroAnalyticsDoc
    from app.services.macro_analytics import _pdf_text
    from app.services.macro_cb_sync import _parse_infom_chart, latest_expectations_reference

    # Сначала XLSX-таблица бюллетеня: это точный ряд по метке строки. PDF-график ниже
    # остаётся фолбэком — он месяцами возвращал «вёрстка изменилась», и проверка всё
    # это время висела в unavailable, то есть НЕ проверяла ничего.
    ref = latest_expectations_reference()
    if ref is not None:
        ref_val, ref_url = ref
        p = _latest_point(db, "inflation_expectations", "level")
        if p is None:
            return _res(key, t, title, "fail", "В БД нет точек инфляционных ожиданий")
        db_val = float(p.value)
        if abs(db_val - ref_val) <= 0.05:
            return _res(key, t, title, "ok", f"Совпадает с таблицей инФОМ: {db_val}%",
                        db_value=db_val, ref_value=ref_val, ref_url=ref_url)
        return _res(key, t, title, "fail",
                    f"РАСХОЖДЕНИЕ: в БД {db_val}%, в таблице инФОМ {ref_val}%",
                    db_value=db_val, ref_value=ref_val, ref_url=ref_url)

    doc = (db.query(MacroAnalyticsDoc)
           .filter(MacroAnalyticsDoc.source == "cbr",
                   MacroAnalyticsDoc.doc_type.ilike("%инфляционные ожидания%"))
           .order_by(MacroAnalyticsDoc.published_at.desc()).first())
    if not doc or not doc.source_url:
        return _res(key, t, title, "unavailable", "PDF-бюллетень инФОМ не найден в БД")
    text = _pdf_text(doc.source_url)
    ref_val = _parse_infom_chart(text) if text else None
    if ref_val is None:
        return _res(key, t, title, "unavailable",
                    "График бюллетеня не распарсился (вёрстка изменилась?) — сверка пропущена")
    p = _latest_point(db, "inflation_expectations", "level")
    if p is None:
        return _res(key, t, title, "fail", "В БД нет точек инфляционных ожиданий")
    db_val = float(p.value)
    if abs(db_val - ref_val) <= 0.05:
        return _res(key, t, title, "ok", f"Совпадает: {db_val}%",
                    db_value=db_val, ref_value=ref_val, ref_url=doc.source_url)
    return _res(key, t, title, "fail",
                f"РАСХОЖДЕНИЕ: в БД {db_val}%, в бюллетене инФОМ {ref_val}%",
                db_value=db_val, ref_value=ref_val, ref_url=doc.source_url)


# ----------------------------- delta-проверки -----------------------------
_DELTA_LIMITS = [
    # (code, metric, max_step, человекочитаемое имя)
    ("key_rate", "level", 3.0, "Ключевая ставка"),
    ("inflation", "yoy", 2.0, "Инфляция г/г"),
    ("inflation_weekly", "wow", 0.6, "Недельная инфляция"),
    ("inflation_expectations", "level", 4.0, "Инфляционные ожидания"),
    ("usdrub", "level", 8.0, "Курс USD/RUB"),
]


def _check_deltas(db: Session) -> dict:
    """Скачки «за один шаг» сверх правдоподобного лимита — класс бага «цена сахара
    (2,6%) записана как недельная инфляция (реальная 0,17%)». warn, не fail: редкие
    легитимные скачки бывают (шоковое заседание) — решает человек."""
    key, t, title = "delta_jumps", "delta", "Нет неправдоподобных скачков значений"
    jumps = []
    for code, metric, max_step, name in _DELTA_LIMITS:
        pts = _last_two_points(db, code, metric)
        if len(pts) < 2:
            continue
        step = abs(float(pts[0].value) - float(pts[1].value))
        if step > max_step:
            jumps.append(f"{name}: {float(pts[1].value)} → {float(pts[0].value)} "
                         f"(скачок {step:.2f} при лимите {max_step})")
    if jumps:
        return _res(key, t, title, "warn",
                    "Подозрительные скачки (проверить руками): " + "; ".join(jumps),
                    jumps=jumps)
    return _res(key, t, title, "ok", "Скачков сверх лимитов нет")


# ----------------------------- прогон и выдача -----------------------------
def run_verification(db: Session) -> dict:
    """Полный прогон всех проверок → строки в macro_verifications (один run_at на
    прогон). Ошибка одной проверки не роняет остальные."""
    meetings = fetch_cb_meeting_calendar()
    checks = [
        lambda: _check_rate_after_meeting(db, meetings),
        lambda: _check_forecast_after_meeting(db, meetings),
        lambda: _check_weekly_inflation_fresh(db),
        lambda: _check_monthly_due(db, "inflation_expectations", "level", 26,
                                   "calendar_expectations", "Инфл. ожидания выходят по графику",
                                   "Инфляционные ожидания"),
        lambda: _check_monthly_due(db, "business_climate_indicator", "level", 16,
                                   "calendar_ibc", "ИБК выходит по графику",
                                   "Индикатор бизнес-климата"),
        lambda: _check_cross_key_rate(db),
        lambda: _check_cross_inflation(db),
        lambda: _check_cross_usdrub(db),
        lambda: _check_cross_forecast(db),
        lambda: _check_cross_expectations(db),
        lambda: _check_deltas(db),
    ]
    run_at = datetime.now(timezone.utc)
    results = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:  # noqa: BLE001
            logger.exception("ОТК данных: проверка упала: %s", e)
            db.rollback()
    for r in results:
        db.add(MacroVerification(run_at=run_at, **r))
    db.commit()
    counts = {"ok": 0, "warn": 0, "fail": 0, "unavailable": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    problems = [r["check_key"] for r in results if r["status"] in ("warn", "fail")]
    summary = {"run_at": run_at.isoformat(), "checks": len(results), **counts,
               "problems": problems}
    if counts["fail"]:
        logger.warning("ОТК-ДАННЫХ-АЛЕРТ: %d проверок FAIL: %s", counts["fail"],
                       [r["check_key"] for r in results if r["status"] == "fail"])
    logger.info("ОТК данных: %s", summary)
    return summary


def latest_results(db: Session) -> dict:
    """Последний прогон для витрины: {run_at, overall, checks:[...]}. overall:
    fail > warn > ok; unavailable не портит overall (сеть моргнула — не повод
    пугать пользователя), но виден в списке."""
    # 🔴 Фильтр по check_type ОБЯЗАТЕЛЕН. Таблицу macro_verifications с 2026-08-02
    # делит «ОТК данных» геополитики (geo_verification, check_type="geo") — заводить
    # вторую таблицу под тот же набор полей было бы дублированием схемы. Но его крон
    # идёт в 22:30, ПОЗЖЕ макро-ОТК (18:30), поэтому «последний прогон» без фильтра
    # каждый вечер оказывался бы геополитическим, и на витрине Экономической
    # статистики появлялись бы строки вида «Лента по очагам приходит».
    # Исключаем "geo", а не перечисляем макро-типы: так новый макро-тип проверки
    # попадёт на витрину сам, без правки этого запроса.
    macro_only = MacroVerification.check_type != "geo"
    last = (db.query(MacroVerification.run_at).filter(macro_only)
            .order_by(MacroVerification.run_at.desc()).first())
    if not last:
        return {"run_at": None, "overall": None, "checks": []}
    rows = (db.query(MacroVerification).filter(macro_only, MacroVerification.run_at == last[0])
            .order_by(MacroVerification.id).all())
    statuses = {r.status for r in rows}
    overall = "fail" if "fail" in statuses else "warn" if "warn" in statuses else "ok"
    return {
        "run_at": last[0].isoformat(),
        "overall": overall,
        "checks": [{"key": r.check_key, "type": r.check_type, "title": r.title,
                    "status": r.status, "message": r.message, "details": r.details}
                   for r in rows],
    }
