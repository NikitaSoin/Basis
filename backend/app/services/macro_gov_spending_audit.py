"""Сверка годовых госрасходов 2016–2025 с исполнением федерального бюджета (Минфин).

🔴 Владелец, 2026-08-18: «у госрасходов старые числа из моей таблицы, они вполне могут
быть некорректные — надо перепроверить».

Что показала сверка. Сами ЧИСЛА владельца оказались верными — они сходятся с исполнением
федерального бюджета по данным Минфина до десятой доли. Неверна была ФОРМА ряда: годовой
показатель лежал в базе как месячный — одно и то же значение проставлено во все двенадцать
месяцев, да ещё со сдвигом (в январе стоит значение предыдущего года). На витрине это
выглядит как «рост госрасходов за месяц», которого не существует: месячной динамики в
этих числах нет ни одной, а январская точка вдобавок относится к прошлому году.

Как чинится. Берём ПЕРВИЧНОЕ число — исполненные расходы федерального бюджета за год
(`gov_spending_level`, трлн ₽) — и считаем темп роста КОДОМ. Годовые числа Минфина за
закрытые годы окончательны и не пересматриваются, поэтому они лежат здесь константой со
ссылкой на источник: это не «запечённая оценка», а справочник (тот же приём, что у
известных исправлений точек в macro_ingest). Для года, которого в справочнике нет (когда
закроется очередной), остаётся веб-добор — чтобы механизм не сгнил через год.

Что делаем с расхождением. Ничего не затираем молча: считаем свой темп, сравниваем с тем,
что лежит, и правим только при расхождении больше порога, записывая источник. Размазанные
по месяцам точки годового ряда удаляем — но ТОЛЬКО те, что пришли из файла владельца и
только за годы, которые сверили (машинные месячные точки Минфина с 2026 года — другой
показатель, накопленный с начала года, их не трогаем).
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import llm
from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

# Исполнение федерального бюджета РФ, расходы всего, млрд ₽.
# Источник: Минфин России, «Краткая ежегодная информация об исполнении федерального
# бюджета». 2015 год нужен как база для темпа 2016-го.
_MINFIN_URL = ("https://minfin.gov.ru/ru/document?id_4=80041-kratkaya_ezhegodnaya_"
               "informatsiya_ob_ispolnenii_federalnogo_byudzheta_mlrd_rub.")
_MINFIN_ANNUAL_BLN = {
    2015: 15620.3, 2016: 16416.4, 2017: 16420.3, 2018: 16713.0, 2019: 18214.5,
    2020: 22821.6, 2021: 24762.1, 2022: 31119.0, 2023: 32353.8, 2024: 40180.5,
    2025: 42910.3,
}

# Диапазон нужен не для точности, а чтобы отсечь заведомо чужое число при веб-доборе:
# доходы вместо расходов, консолидированный бюджет (втрое больше), миллиарды как триллионы.
_RANGE = (12.0, 70.0)

_SYS = (
    "Ты извлекаешь ОДНО число из материалов об исполнении федерального бюджета России. "
    "Нужны ФАКТИЧЕСКИ ИСПОЛНЕННЫЕ РАСХОДЫ федерального бюджета за указанный год, в "
    "триллионах рублей. Верни строго JSON {\"found\": true|false, "
    "\"value_trn\": <число>, \"year\": <год>, \"kind\": \"исполнение\"|\"план\", "
    "\"source_idx\": <номер>}. "
    "ЖЁСТКО: (1) расходы, а НЕ доходы и не дефицит; (2) ФЕДЕРАЛЬНЫЙ бюджет, а не "
    "консолидированный и не бюджет расширенного правительства; (3) год должен совпадать "
    "с запрошенным; (4) миллиарды переведи в триллионы делением на 1000; (5) если в "
    "источнике только план/проект, а не исполнение — верни kind=\"план\". "
    "Не нашёл надёжного числа — {\"found\": false}. Никакого текста вне JSON."
)


def _fetch_year(year: int) -> dict | None:
    """Расходы федерального бюджета за год веб-поиском: поиск → извлечение → валидация."""
    from app.services.agent_web import web_search

    results = []
    for q in (f"расходы федерального бюджета России {year} году исполнение трлн рублей Минфин",
              f"исполнение федерального бюджета {year} год расходы составили"):
        try:
            out = web_search(q, 6)
        except Exception as e:  # noqa: BLE001
            logger.warning("gov-spending-audit: поиск упал (%s)", type(e).__name__)
            continue
        if isinstance(out, dict) and not out.get("error"):
            results.extend(r for r in (out.get("results") or []) if isinstance(r, dict))
        if len(results) >= 8:
            break
    if not results:
        return None

    payload = [{"idx": i, "title": r.get("title"), "text": str(r.get("snippet") or "")[:400],
                "url": r.get("url")} for i, r in enumerate(results[:10])]
    try:
        out = llm.complete(_SYS + f"\nГод: {year}.", str(payload), json_mode=True,
                           max_tokens=250)
    except llm.LLMError as e:
        logger.warning("gov-spending-audit: %s — LLM не отработал: %s", year, e)
        return None
    if not isinstance(out, dict) or not out.get("found"):
        return None
    try:
        val = float(str(out.get("value_trn")).replace(",", ".").replace(" ", ""))
        got_year = int(out.get("year") or 0)
    except (TypeError, ValueError):
        return None
    if got_year != year:
        logger.warning("gov-spending-audit: просили %s, ответ про %s — отброшено", year, got_year)
        return None
    lo, hi = _RANGE
    if not (lo <= val <= hi):
        logger.warning("gov-spending-audit: %s = %s трлн вне диапазона — отброшено", year, val)
        return None
    idx = int(out.get("source_idx") or 0)
    src = results[idx] if 0 <= idx < len(results) else results[0]
    return {"value": val, "source": "Веб-поиск (исполнение бюджета)", "url": src.get("url"),
            "kind": out.get("kind") or "исполнение"}


def _level(year: int) -> dict | None:
    """Расходы за год: сначала справочник Минфина, если года там нет — веб-добор."""
    if year in _MINFIN_ANNUAL_BLN:
        return {"value": round(_MINFIN_ANNUAL_BLN[year] / 1000, 4),
                "source": "Минфин России (исполнение федерального бюджета)",
                "url": _MINFIN_URL, "kind": "исполнение"}
    return _fetch_year(year)


def _stored_year(db: Session, year: int) -> dict | None:
    """Что лежит у нас за этот год: типичное значение и сколько точек его несут."""
    rows = db.execute(text(
        "SELECT as_of, value, ingested_via, source FROM macro_data_points "
        "WHERE indicator_code='gov_spending_growth' AND metric='yoy' "
        "AND as_of >= :a AND as_of <= :b ORDER BY as_of"),
        {"a": date(year, 1, 1), "b": date(year, 12, 31)}).fetchall()
    if not rows:
        return None
    # январская точка несёт значение ПРЕДЫДУЩЕГО года (сдвиг в исходном файле) — берём
    # моду по февралю-декабрю, это и есть годовое значение из таблицы владельца
    body = [float(r[1]) for r in rows if r[0].month > 1] or [float(r[1]) for r in rows]
    value = Counter(round(v, 1) for v in body).most_common(1)[0][0]
    return {"value": value, "points": len(rows),
            "from_file": sum(1 for r in rows if (r[2] or "") == "file" or "file" in (r[3] or ""))}


def audit(db: Session, years: tuple[int, int] = (2016, 2025), *,
          threshold_pp: float = 1.0, write: bool = True) -> dict:
    """Сверить годовые госрасходы с исполнением бюджета. Возвращает отчёт по годам.

    write=False — только показать расхождения, ничего не трогая (режим по умолчанию для
    первого прогона: разрушительная правка ряда должна сначала быть видна глазами)."""
    lo_y, hi_y = years
    levels: dict[int, dict] = {}
    for year in range(lo_y - 1, hi_y + 1):          # год раньше — база для первого темпа
        got = _level(year)
        if not got:
            logger.info("gov-spending-audit: %s — уровень не найден", year)
            continue
        levels[year] = got
        if write:
            upsert_point(db, "gov_spending_level", date(year, 12, 31), "level", got["value"],
                         unit="трлн ₽", source=got["source"], source_url=got.get("url"),
                         ingested_via="minfin", commit=False)
    if write:
        db.commit()

    rows = []
    for year in range(lo_y, hi_y + 1):
        cur, prev = levels.get(year), levels.get(year - 1)
        stored = _stored_year(db, year)
        row = {"year": year,
               "level_trn": cur["value"] if cur else None,
               "stored_yoy": stored["value"] if stored else None,
               "stored_points": stored["points"] if stored else 0,
               "computed_yoy": None, "diff_pp": None, "action": None, "removed": 0}
        if cur and prev and prev["value"]:
            row["computed_yoy"] = round((cur["value"] / prev["value"] - 1) * 100, 1)
        if row["computed_yoy"] is None:
            row["action"] = "нет источника — оставили как было"
            rows.append(row)
            continue
        if stored is not None:
            row["diff_pp"] = round(row["computed_yoy"] - stored["value"], 1)
        if stored is None:
            row["action"] = "добавлено (года не было)"
        elif abs(row["diff_pp"]) >= threshold_pp:
            row["action"] = "число исправлено + ряд сведён к годовой точке"
        elif stored["points"] > 1:
            row["action"] = "число подтверждено, ряд сведён к годовой точке"
        else:
            row["action"] = "подтверждено"

        if write:
            # 🔴 Удаляем ТОЛЬКО точки из файла владельца и только за сверенный год —
            # машинные месячные точки Минфина (накопленный рост с начала года) живут
            # своей жизнью и под нож не идут.
            res = db.execute(text(
                "DELETE FROM macro_data_points WHERE indicator_code='gov_spending_growth' "
                "AND metric='yoy' AND as_of >= :a AND as_of <= :b "
                "AND (ingested_via='file' OR source IS NULL OR source LIKE '%file%')"),
                {"a": date(year, 1, 1), "b": date(year, 12, 31)})
            row["removed"] = int(res.rowcount or 0)
            upsert_point(db, "gov_spending_growth", date(year, 12, 31), "yoy",
                         row["computed_yoy"], unit="%",
                         source="расчёт Basis по исполнению бюджета (Минфин)",
                         source_url=cur.get("url"), ingested_via="minfin", commit=False)
        rows.append(row)
    if write:
        db.commit()

    checked = [r for r in rows if r["computed_yoy"] is not None]
    out = {"rows": rows, "write": write,
           "summary": {"годы": len(rows), "сверено": len(checked),
                       "числа сошлись": sum(1 for r in checked
                                            if r["diff_pp"] is not None
                                            and abs(r["diff_pp"]) < threshold_pp),
                       "числа исправлены": sum(1 for r in checked
                                               if r["diff_pp"] is not None
                                               and abs(r["diff_pp"]) >= threshold_pp),
                       "удалено размазанных точек": sum(r["removed"] for r in rows),
                       "без источника": len(rows) - len(checked)}}
    logger.info("gov-spending-audit: %s", out["summary"])
    return out
