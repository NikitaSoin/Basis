"""Пишущий аналитик как НАСТОЯЩИЙ агент: методичка — база знаний, а не промпт.

🔴 ПОСТАНОВКА ВЛАДЕЛЬЦА (2026-08-20), исправляющая мой компромисс:
«Методичка — это база знаний агента, куда ему стоит обращаться за методикой
анализа. Методичка НЕ должна быть системным промптом — агент обращается в неё,
если это надо, и возможно не ко всей, а только к нужной части. Так же работает
полноценный ИИ-агент. И так должно быть у всех методичек».

Что было не так до этого. Разведчик получил инструменты и открывал разделы сам, а
пишущие слои остались одиночными вызовами `llm.complete`, и им я вклеивал в
системный промпт «ядра» — выбранные мной разделы. Отсюда росли три беды сразу:
  • ВЫБИРАЛ Я, А НЕ АГЕНТ. Список разделов — это моё предположение о том, что
    понадобится, зафиксированное навсегда. Задачи разные, а набор один;
  • ПРОМПТ РАСПУХАЛ. У макро-выпуска системная часть дошла до 121 тысячи знаков —
    около 40 тысяч токенов ДО того, как туда лягут данные. Из-за этого приходилось
    урезать методику по размеру, то есть терять её содержание;
  • НУМЕРАЦИЯ РАЗДЕЛОВ ЖИВАЯ. Владелец правит методички, номера смещаются, и
    зафиксированный список молча начинает указывать на другой текст. Ловил это
    трижды.
Все три исчезают, если агент ходит в методичку сам: он берёт то, что нужно ЕМУ и
СЕЙЧАС, промпт остаётся коротким, а смещение номеров перестаёт что-либо значить —
он выбирает раздел по оглавлению, которое видит.

Что остаётся в системном промпте: РОЛЬ, ФОРМА ВЫВОДА и запреты — то есть контракт
с витриной, который к доменному знанию отношения не имеет. Это и есть разделение,
которого требует постановка.

🔴 ЧЕГО ЭТОТ МОДУЛЬ НЕ ДЕЛАЕТ. Не заставляет читать методичку. Заставить нельзя, но
можно сделать видимым: агент обязан вернуть `methodology_used`, и слой пишет это в
лог. Пустой список при сложной задаче — сигнал, что промпт роли плох, а не повод
вернуть методичку обратно в промпт.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_RULES = (
    "\n\n===== КАК ТЫ РАБОТАЕШЬ =====\n"
    "🔴 У тебя есть ПОЛКА МЕТОДИЧЕК — база знаний платформы. Ниже её оглавление.\n"
    "Когда для вывода нужна МЕТОДИКА (через какой канал эффект доходит до денег, "
    "какого он порядка, обратим ли, каким механизмом давление превращается в сдвиг, "
    "как разложить показатель, что считается признаком, а что нет) — ОТКРОЙ нужный "
    "раздел инструментом read_methodology_section и рассуждай по нему. Не по общей "
    "эрудиции и не по памяти о похожих текстах.\n"
    "Не уверен, в каком разделе аппарат — посмотри оглавление "
    "(list_methodology_sections) и открой один-два подходящих.\n"
    "🔴 Открывай то, что нужно ДЛЯ ЭТОЙ задачи, а не всё подряд: прочитанное "
    "остаётся в диалоге и дорожает с каждым шагом. Ориентир — три-пять разделов.\n"
    "🔴 В поле methodology_used перечисли, что открыл (формат «doc:раздел»). Это не "
    "формальность: по нему мы видим, на чём построен вывод.\n"
    "🔴 Если методичка недоступна или в ней нет нужного — скажи об этом в выводе "
    "честно и рассуждай осторожнее, а не делай вид, что аппарат был.\n"
)


def run(db: Session, *, system: str, task: str, shelf_docs: list[str],
        extra_tools: list[dict] | None = None, extra_executor=None,
        max_steps: int = 10, budget: int = 160_000,
        step_max_tokens: int = 3000, final_max_tokens: int = 20_000,
        final_instruction: str = "", label: str = "analyst") -> dict | None:
    """Прогнать пишущего аналитика. Возвращает разобранный JSON или None.

    system — РОЛЬ и ФОРМА ВЫВОДА (без методичек!). shelf_docs — какие методички
    показать в оглавлении. extra_tools/extra_executor — доменные инструменты слоя,
    если они есть (данные платформы, веб).
    """
    from app.services.agent_runner import run_agent
    from app.services.methodology import METHODOLOGY_TOOLS_SCHEMA, shelf_card

    tools = list(METHODOLOGY_TOOLS_SCHEMA) + list(extra_tools or [])
    full_system = system + _RULES + shelf_card(shelf_docs)

    def _exec(_db, name, args):
        from app.services.methodology import execute as _m
        got = _m(name, args)
        if got is not None:
            return got
        if extra_executor is not None:
            return extra_executor(_db, name, args)
        return {"error": "unknown_tool", "note": name}

    try:
        out = run_agent(
            db, system_prompt=full_system, task=task, tools_schema=tools,
            allowed_ticker="", max_steps=max_steps, max_tokens_total=budget,
            web_call_cap=0 if not extra_tools else 4,
            executor=_exec, step_max_tokens=step_max_tokens,
            final_max_tokens=final_max_tokens,
            final_instruction=final_instruction,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("analyst[%s]: прогон не удался (%s)", label, e)
        return None

    result = out.get("result")
    trace = out.get("trace") or []
    used = (result or {}).get("methodology_used") if isinstance(result, dict) else None
    logger.info("analyst[%s]: шагов %d, токенов %s, остановка %s, методички: %s",
                label, len(trace), out.get("tokens_used"), out.get("stopped_reason"),
                json.dumps(used, ensure_ascii=False) if used else "НЕ ОТКРЫВАЛ")
    if not isinstance(result, dict):
        logger.warning("analyst[%s]: валидного JSON нет (%s); хвост финала: %s",
                       label, out.get("stopped_reason"),
                       str(out.get("final_raw") or "")[-300:])
        return None
    if not used:
        # Не отклоняем: бывают задачи, где методика не нужна. Но это должно быть
        # ЗАМЕТНО — молчаливое «агент не открыл ничего» и есть та деградация,
        # которую раньше нельзя было увидеть вовсе.
        logger.warning("analyst[%s]: агент не открыл ни одного раздела методички",
                       label)
    return result
