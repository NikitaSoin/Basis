"""Шаг 4 агентного контура: мини-агенты закрывают вопросы к данным.

Один вопрос — один прогон — один ответ. Агент НЕ решает, куда идти: список вопросов
уже составлен кодом (`macro_data_questions`), он лишь закрывает тикеты. Это защита от
главного риска свободного агента — блуждания и сжигания бюджета.

🔴 ПОРЯДОК ПОИСКА (владелец): сначала СВОЯ лента, потом первоисточник по её ссылке, и
только затем веб. Проверено: нужное число часто уже пришло к нам (Коммерсант «Росстат
фиксирует стабильную занятость» лежал в ленте свежее нашего ряда безработицы).

🔴 ГЕЙТ РЕЗУЛЬТАТА, кодом а не LLM: число обязано ПРИСУТСТВОВАТЬ в тексте, который агент
реально открыл в этом прогоне. Это тот же принцип числовой сверки, что в пилоте, и он
здесь критичен: находка идёт в данные платформы, а «правдоподобное» число, придуманное
моделью, отравит ряд надолго.

Пока контур READ-ONLY: находки идут в снапшот выпуска и в лог, но НЕ пишутся в ряды.
Запись — отдельный шаг с карантином и ручной приёмкой (первая точка неверных данных
стоит дороже, чем недостающая).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services.agent_runner import run_agent
from app.services import macro_gap_tools

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — агент-добытчик данных аналитической платформы Basis. Твоя ЕДИНСТВЕННАЯ
задача: найти конкретное опубликованное значение макропоказателя. Ты НЕ рассуждаешь о
рынке, НЕ прогнозируешь и НЕ интерпретируешь.

ПОРЯДОК РАБОТЫ (соблюдай, это экономит время и деньги):
1. get_series_state — посмотри, что у нас уже есть в ряду (какая единица, какая частота,
   какие последние точки). Это задаёт, что именно искать.
2. search_our_feed — ищи в НАШЕЙ ленте. Крупные СМИ (Коммерсант, Интерфакс, РБК) и
   аналитика к нам уже приходят: очень часто нужное число здесь. Пробуй разные
   формулировки запроса, прежде чем идти наружу.
3. read_feed_item — если запись похожа на нужную, открой её полностью (инструмент сам
   дочитает первоисточник по ссылке, если в пересказе числа нет).
4. web_search / fetch_document — ТОЛЬКО если своя лента не дала ответа.

🔴 НЕ ЗАЦИКЛИВАЙСЯ НА ПОИСКЕ. Максимум 3-4 поисковых запроса ВСЕГО. Если выдача
содержит подходящий заголовок или сниппет с числом — СРАЗУ открывай источник
(read_feed_item / fetch_document) и работай с текстом. Перебирать формулировки запроса
бесконечно — самая частая ошибка: шаги кончаются, а ответа нет.
Если после 3-4 поисков нужного нет — верни found=false, это нормальный результат.

🔴 СЛЕДИ ЗА ТЕМ, ТОТ ЛИ ЭТО ПОКАЗАТЕЛЬ. Похожие названия — разные величины:
композитный PMI ≠ PMI обрабатывающих отраслей ≠ PMI услуг; номинальная зарплата ≠
реальная; наблюдаемая инфляция ≠ ожидаемая. Нашёл похожий, но не тот — это found=false,
а не «сойдёт».

ЖЁСТКИЕ ПРАВИЛА:
- Возвращай ТОЛЬКО то число, которое ты РЕАЛЬНО УВИДЕЛ в тексте источника. Не считай,
  не переводи единицы, не восстанавливай «по смыслу», не бери из своей памяти.
- Различай ДАТУ ПЕРИОДА (за какой месяц значение) и дату публикации. Нужна первая.
- Проверь единицу: если у нас ряд в %, а в источнике млрд рублей — это ДРУГАЯ величина,
  не подгоняй. Лучше честно вернуть found=false.
- Не нашёл — так и скажи. Пустой ответ полезнее выдуманного: неверное число в данных
  платформы живёт долго и портит все выводы поверх него.

Финальный ответ БЕЗ вызова инструментов, строго JSON:
{
  "found": true|false,
  "values": [{"period": "YYYY-MM-DD", "value": <число>, "unit": "<единица как в источнике>"}],
  "source_url": "<ссылка, где это опубликовано>",
  "quote": "<дословный фрагмент источника с этим числом, до 300 знаков>",
  "confidence": "высокая|средняя|низкая",
  "note": "<если не нашёл или есть сомнение — что именно мешает>"
}"""


def _gate(result: dict, seen_texts: str) -> tuple[bool, list[str]]:
    """Проверка находки КОДОМ. Число должно быть в реально открытом тексте."""
    notes: list[str] = []
    if not isinstance(result, dict):
        return False, ["not_a_dict"]
    if not result.get("found"):
        return False, ["not_found"]
    values = result.get("values")
    if not isinstance(values, list) or not values:
        return False, ["no_values"]
    if not result.get("source_url"):
        notes.append("no_source_url")
    for i, v in enumerate(values):
        if not isinstance(v, dict):
            notes.append(f"value_{i}_not_dict")
            continue
        num = v.get("value")
        if not isinstance(num, (int, float)):
            notes.append(f"value_{i}_not_number")
            continue
        period = str(v.get("period") or "")
        if not re.match(r"^\d{4}-\d{2}(-\d{2})?$", period):
            notes.append(f"value_{i}_bad_period:{period}")
        # 🔴 Главная проверка: число обязано встречаться в тексте, который агент открыл.
        # Ищем и «2.2», и «2,2» — источники пишут по-разному.
        as_dot = f"{num:g}".replace(",", ".")
        as_comma = as_dot.replace(".", ",")
        if as_dot not in seen_texts and as_comma not in seen_texts:
            notes.append(f"value_{i}_not_in_source:{num}")
    return (not notes), notes


def answer_question(db: Session, question: dict, *, max_steps: int = 10) -> dict:
    """Один вопрос — один прогон. Возвращает находку с вердиктом гейта."""
    code = question.get("code")
    task = (f"{question['question']}\n\n"
            f"Код показателя в нашей базе: {code}. "
            f"Сегодня {datetime.now(timezone.utc).date().isoformat()}.")
    seen: list[str] = []

    def _executor(db_, name, args):
        out = macro_gap_tools.execute(db_, name, args)
        # копим ВСЁ, что агент реально видел, — на этом основана проверка числа
        try:
            seen.append(json.dumps(out, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass
        return out

    run = run_agent(db, system_prompt=_SYSTEM, task=task,
                    tools_schema=macro_gap_tools.TOOLS_SCHEMA,
                    # Бюджет считается суммой по шагам, а каждый шаг тащит всю историю
                    # диалога — расход растёт нелинейно. 30k хватало на два обращения к
                    # инструментам, и агент упирался в лимит, не дойдя до ответа.
                    # 90k при цене входа ~$0.44/M — это ~4 цента за вопрос.
                    # Поднято до 140k/10 шагов: по трассе видно, что пропуск за НЕСКОЛЬКО
                    # периодов требует нескольких заходов (в ленте нашёлся июнь, за май
                    # пришлось идти в веб), и на прежних лимитах агент иногда не
                    # добирался до ответа — результат «нашёл/не нашёл» плавал от прогона
                    # к прогону. Дешевле дать шаги, чем терять находку.
                    max_steps=max_steps, max_tokens_total=140_000,
                    web_call_cap=3, executor=_executor, step_max_tokens=2500)
    result = run.get("result")
    ok, notes = _gate(result or {}, "\n".join(seen))
    out = {
        "code": code,
        # 🔴 Метрику несём из вопроса. Пайплайн писал жёстко "level", и находка по
        # «Реальной зарплате» (ряд ведётся в yoy) легла в параллельную ветку level:
        # ряд остался протухшим, а рядом появилась точка, которую никто не читает.
        "metric": question.get("metric") or "level",
        "question": question.get("question"),
        "accepted": ok,
        "gate_notes": notes,
        "result": result,
        "tokens_used": run.get("tokens_used"),
        "stopped_reason": run.get("stopped_reason"),
    }
    logger.info("gap_agent[%s]: accepted=%s tokens=%s notes=%s",
                code, ok, run.get("tokens_used"), notes[:3])
    return out


def run_gap_round(db: Session, limit: int = 3) -> list[dict]:
    """Раунд: берём самые приоритетные вопросы и закрываем каждый отдельным прогоном.

    limit намеренно маленький: это не «починить все данные разом», а регулярная
    чистка по чуть-чуть. Каждый прогон стоит денег, а непроверенная находка дороже.
    """
    from app.services.macro_data_questions import collect_questions
    questions = [q for q in collect_questions(db) if q.get("kind") == "stale_series"]
    out = []
    for q in questions[:limit]:
        try:
            out.append(answer_question(db, q))
        except Exception:  # noqa: BLE001
            logger.exception("gap_agent: вопрос %s не отработал", q.get("code"))
    return out
