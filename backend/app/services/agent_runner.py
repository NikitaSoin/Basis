"""Агентский цикл (tool-loop) для автономных DeepSeek-агентов — пилот.

То, чего у DeepSeek API нет из коробки (в отличие от субагентов Claude Code):
цикл «подумал → вызвал инструмент → получил результат → подумал дальше», с
ЗАКОДИРОВАННЫМИ ограничителями (фаза 5 плана автономности — лимиты не на
дисциплине, а в коде):
  - max_steps: максимум итераций цикла (по умолчанию 8);
  - max_tokens_total: суммарный бюджет токенов прогона;
  - каждый шаг журналируется в trace (что звал, с чем, сколько байт получил) —
    прогон воспроизводим и проверяем постфактум.

Runner НЕ знает про конкретного агента — роль задаёт system_prompt, инструменты
приходят параметром. Финал: агент отвечает ОБЫЧНЫМ сообщением (без tool_calls),
содержащим JSON — runner его парсит и отдаёт вместе с trace."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.services.llm import complete_messages, LLMError, _strip_json_fence
from app.services.agent_tools import execute_tool

logger = logging.getLogger(__name__)


class AgentRunError(RuntimeError):
    pass


# инструменты с внешним доступом — их вызовы дороги/медленны, ограничиваем счётчиком
_WEB_TOOLS = {"web_search", "fetch_document"}
# Лимит тратится ПОИСКАМИ (они множат варианты), а чтение найденного — то, ради чего
# всё и затевалось. Поэтому кап считаем по поисковым инструментам, а fetch_document
# остаётся доступным до конца прогона.
_SEARCH_TOOLS = {"web_search", "search_our_feed"}


def run_agent(db: Session, *, system_prompt: str, task: str, tools_schema: list[dict],
              allowed_ticker: str = "", max_steps: int = 8, max_tokens_total: int = 40_000,
              web_call_cap: int = 2, executor=None, step_max_tokens: int = 1600) -> dict:
    """Возвращает {"result": dict|None, "trace": list, "tokens_used": int,
    "stopped_reason": str}. result=None — агент не дал валидного JSON-финала.
    web_call_cap — сколько раз всего разрешён веб-поиск/открытие документа: после
    исчерпания веб-инструменты убираются из схемы (не даём агенту зациклиться на
    поиске — реальная проблема без кэпа: 7 web_search → max_steps без ответа).
    executor — свой диспетчер инструментов execute(db, name, args). По умолчанию
    тикер-контур пилота; макро-вопросы тикера не имеют и приносят свой (2026-08-02).
    step_max_tokens — потолок ответа модели на шаг. 1600 рассчитан на короткие
    структурные ответы пилота; агент с объёмным финалом (разбор события с фактами и
    цитатами) на нём ОБРЕЗАЕТСЯ на середине JSON, и финал не парсится."""
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    trace: list[dict] = []
    tokens_used = 0
    web_calls = 0

    for step in range(1, max_steps + 1):
        # когда веб-бюджет исчерпан — не предлагаем веб-инструменты дальше
        step_tools = tools_schema
        if web_calls >= web_call_cap:
            # 🔴 Исчерпан бюджет ПОИСКА — убираем только поисковые инструменты, но
            # оставляем чтение документов. Раньше срезалось всё разом, и агент,
            # потративший лимит на поиски, физически не мог открыть найденное:
            # 10 шагов подряд искал и возвращал «не нашёл», хотя ссылки были на руках
            # (2026-08-02, pmi_composite).
            step_tools = [t for t in tools_schema
                          if (t.get("function") or {}).get("name") not in _SEARCH_TOOLS]
        try:
            resp = complete_messages(messages, tools=step_tools, max_tokens=step_max_tokens, temperature=0.2)
        except LLMError as e:
            trace.append({"step": step, "event": "llm_error", "detail": str(e)})
            return {"result": None, "trace": trace, "tokens_used": tokens_used,
                    "stopped_reason": "llm_error"}
        msg = resp["message"]
        tokens_used += resp.get("total_tokens") or 0
        if tokens_used > max_tokens_total:
            trace.append({"step": step, "event": "budget_exceeded", "tokens": tokens_used})
            return {"result": None, "trace": trace, "tokens_used": tokens_used,
                    "stopped_reason": "token_budget"}

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # финальный ответ — парсим JSON
            content = _strip_json_fence(msg.get("content") or "")
            try:
                lo, hi = content.find("{"), content.rfind("}")
                result = json.loads(content[lo:hi + 1]) if lo != -1 and hi > lo else None
            except json.JSONDecodeError:
                result = None
            trace.append({"step": step, "event": "final", "parsed": result is not None})
            # final_raw — сырой финал агента (для диагностики unparseable-падений;
            # аддитивно, не ломает существующих потребителей run_agent)
            return {"result": result, "trace": trace, "tokens_used": tokens_used,
                    "final_raw": content[:1500],
                    "stopped_reason": "final" if result is not None else "unparseable_final"}

        # исполняем вызовы инструментов и кладём результаты в диалог.
        # 🔴 Обрезаем СПИСОК ДО добавления в assistant-сообщение: API (DeepSeek/
        # OpenAI) требует ответ на КАЖДЫЙ tool_call_id в assistant.tool_calls —
        # если ответить не на все (было tool_calls[:4] при полном списке в
        # сообщении), следующий запрос падает 400. Кап оставляем от runaway.
        tool_calls = tool_calls[:4]
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": tool_calls})
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if name in _SEARCH_TOOLS:
                web_calls += 1
            # 🔴 Кап проверяем НА ИСПОЛНЕНИИ, а не только убирая инструмент из схемы:
            # модель продолжает вызывать его по памяти из прошлых сообщений. Наблюдалось
            # 2026-08-02: агент с лимитом 4 сделал ~12 поисков и ушёл искать композитный
            # PMI по Китаю, Японии и Австралии, хотя вопрос был про Россию. Отказ в
            # исполнении разворачивает его к ответу.
            if name in _SEARCH_TOOLS and web_calls > web_call_cap:
                out = {"error": "search_budget_exhausted",
                       "note": ("Лимит поисков исчерпан. Работай с тем, что уже нашёл: "
                                "открой подходящий источник или верни found=false.")}
            else:
                out = (executor(db, name, args) if executor
                       else execute_tool(db, name, args, allowed_ticker))
            payload = json.dumps(out, ensure_ascii=False)
            trace.append({"step": step, "event": "tool", "name": name,
                          "args": args, "result_bytes": len(payload)})
            messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                             "content": payload[:12_000]})

    trace.append({"event": "max_steps"})
    return {"result": None, "trace": trace, "tokens_used": tokens_used,
            "stopped_reason": "max_steps"}
