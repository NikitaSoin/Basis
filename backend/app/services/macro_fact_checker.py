"""Агент-факт-чекер: независимое подтверждение находки добытчика.

🔴 Владелец 2026-08-02: «не нужна схема где я за агентом перепроверяю, можно просто ещё
одного агента факт-чекера сделать, который в случае сомнений пойдёт и перепроверит».

Схема двух независимых свидетелей:
  1. добытчик (`macro_gap_agent`) находит значение и цитату;
  2. код-гейт проверяет, что число реально есть в открытом тексте;
  3. ФАКТ-ЧЕКЕР ищет то же значение ЗАНОВО и, главное, В ДРУГОМ ИСТОЧНИКЕ;
  4. совпало — точка пишется в ряд автоматически; разошлись — не пишем.

🔴 Ключевое условие независимости: чекеру НЕ передаётся ссылка добытчика, и источник,
совпадающий с ней, подтверждением НЕ считается. Иначе «подтверждение» вырождается в
чтение той же статьи дважды — два агента ошибутся одинаково.

Чекер знает ожидаемое значение (иначе не с чем сверять), но инструкция требует
искать факт, а не подгонять: расхождение — законный и полезный исход.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.services import macro_gap_tools
from app.services.agent_runner import run_agent

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — факт-чекер аналитической платформы Basis. Тебе дают УТВЕРЖДЕНИЕ о
значении макропоказателя, найденное другим агентом. Твоя задача — проверить его
НЕЗАВИСИМО и сказать, подтверждается оно или нет.

Как работать:
1. Ищи публикации по этому показателю и периоду: сначала search_our_feed (наша лента —
   Коммерсант, Интерфакс, РБК, ЦБ), затем при необходимости web_search/fetch_document.
2. Найди число САМ. Тебе назвали ожидаемое значение только для сверки — это НЕ
   ориентир, под который надо подогнать ответ.
3. Источник должен быть ДРУГИМ, не тем, на который ссылался первый агент (его домен
   указан в задании). Подтверждение из той же публикации ничего не стоит.

Что считается результатом:
- "confirmed" — нашёл то же значение за тот же период в независимом источнике;
- "contradicted" — нашёл ДРУГОЕ значение за тот же период (укажи, какое именно);
- "unverified" — подтверждения не нашлось. Это НОРМАЛЬНЫЙ исход, не пиши «подтверждаю»
  из вежливости: цена ошибки в данных платформы выше, чем цена ненайденного факта.

Различай период и дату публикации; проверяй единицу измерения.

Финальный ответ БЕЗ вызова инструментов, строго JSON:
{
  "verdict": "confirmed|contradicted|unverified",
  "found_value": <число или null>,
  "period": "YYYY-MM-DD или null",
  "source_url": "<где нашёл, или null>",
  "quote": "<дословный фрагмент с числом, до 300 знаков>",
  "note": "<если contradicted/unverified — что именно мешает>"
}"""


def _domain(url: str | None) -> str:
    try:
        return (urlparse(url or "").netloc or "").lower().replace("www.", "")
    except Exception:  # noqa: BLE001
        return ""


_COUNTRY_RU = {"ru": "Россия", "cn": "Китай", "us": "США", "eu": "Еврозона", "world": "мир"}


def _describe(db: Session, code: str) -> tuple[str, str, str]:
    """Человеческое имя показателя, страна и единица — из справочника."""
    try:
        from app.models.macro import MacroIndicator
        ind = db.get(MacroIndicator, code)
    except Exception:  # noqa: BLE001
        ind = None
    if ind is None:
        return code, "", ""
    return (ind.title or code, _COUNTRY_RU.get(ind.country or "", ind.country or ""),
            ind.unit or "")


def check_finding(db: Session, code: str, period: str, value: float, unit: str,
                  origin_url: str | None, *, max_steps: int = 6) -> dict:
    """Независимая проверка одного значения. Возвращает вердикт + метаданные."""
    origin = _domain(origin_url)
    # 🔴 Чекеру нужно ЧЕЛОВЕЧЕСКОЕ имя показателя, а не код. Раньше в задании стояло
    # «показатель "real_wage"» — агент шёл искать в веб буквально это и, разумеется,
    # ничего не находил. Добытчик при этом получал нормальный вопрос с названием и
    # страной, находил число за один поиск, а чекер отбраковывал его как
    # неподтверждённое: контур работал вхолостую.
    title, country, unit_ru = _describe(db, code)
    task = (
        f"Проверь утверждение: «{title}»"
        + (f" (страна: {country})" if country else "")
        + f" за период {period} имеет значение {value} {unit or unit_ru}.\n"
        f"🔴 Ищи по НАЗВАНИЮ показателя (у него может быть другое официальное имя в "
        f"статистике), а не по служебному коду «{code}».\n"
        f"Единица: {unit or unit_ru or 'не указана'} — уровень и темп роста это РАЗНЫЕ "
        f"величины, не спутай их.\n"
        f"Первый агент ссылался на источник с домена «{origin or 'неизвестен'}» — "
        f"НАЙДИ ДРУГОЙ источник, этот подтверждением не считается.\n"
        f"Сегодня {datetime.now(timezone.utc).date().isoformat()}."
    )
    seen: list[str] = []

    def _executor(db_, name, args):
        out = macro_gap_tools.execute(db_, name, args)
        try:
            seen.append(json.dumps(out, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
        return out

    run = run_agent(db, system_prompt=_SYSTEM, task=task,
                    tools_schema=macro_gap_tools.TOOLS_SCHEMA,
                    max_steps=max_steps, max_tokens_total=90_000,
                    web_call_cap=3, executor=_executor)
    res = run.get("result") or {}
    verdict = str(res.get("verdict") or "unverified")
    blob = "\n".join(seen)
    notes: list[str] = []

    # Код-проверки поверх вердикта модели — доверяем, но сверяем.
    found = res.get("found_value")
    if verdict == "confirmed":
        if not isinstance(found, (int, float)):
            verdict, notes = "unverified", notes + ["no_found_value"]
        else:
            if abs(float(found) - float(value)) > max(0.05, abs(value) * 0.01):
                verdict = "contradicted"
                notes.append(f"value_differs:{found}!={value}")
            as_dot = f"{found:g}"
            if as_dot not in blob and as_dot.replace(".", ",") not in blob:
                verdict, _ = "unverified", notes.append("value_not_in_seen_text")
        src = _domain(res.get("source_url"))
        if verdict == "confirmed" and origin and src and src == origin:
            # тот же домен — независимости нет, подтверждение не засчитываем
            verdict = "unverified"
            notes.append(f"same_source:{src}")
    return {"verdict": verdict, "found_value": found,
            "source_url": res.get("source_url"), "quote": res.get("quote"),
            "note": res.get("note"), "checker_notes": notes,
            "tokens_used": run.get("tokens_used"), "stopped_reason": run.get("stopped_reason")}


_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")


def normalize_period(period: str) -> str | None:
    """«2026-06» / «2026-06-30» → дата конца месяца (как хранятся месячные ряды)."""
    m = _PERIOD_RE.match(str(period or "").strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if m.group(3):
        return f"{year:04d}-{month:02d}-{int(m.group(3)):02d}"
    import calendar
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
