"""Разбор документа по ссылке (владелец, 2026-07-21: «чтобы агент умел открывать
файлы и анализировать их — например PDF-отчётность МСФО»). Отдельный чистый
демо-контур: URL → fetch_document (PDF/HTML → текст) → DeepSeek структурирует
разбор. Не агентский цикл — один заход (документ уже открыт кодом, модель только
анализирует текст), это дешевле и предсказуемее.

ДЕМО: извлечение текста надёжно (pypdf); качество разбора — DeepSeek (суждение,
не аудит). Скан-PDF без текстового слоя не читаются (честно возвращаем ошибку).
Egress-нюанс fetch см. agent_web.py."""
from __future__ import annotations

import logging

from app.services.agent_web import fetch_document
from app.services.llm import complete, LLMError

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — финансовый аналитик Basis (не брокер, без «купить/продать»). Тебе
дан ТЕКСТ документа (часто это отчётность МСФО/РСБУ или пресс-релиз). Разбери его
структурно и по делу, по-русски. Верни СТРОГО JSON:
{
  "doc_type": "что это за документ (одна фраза)",
  "summary": "3-5 предложений — главное содержание/итоги",
  "key_figures": [{"metric": "показатель", "value": "значение как в документе", "note": "контекст/динамика если есть"}],
  "highlights": ["важный факт/тезис", "..."],
  "risks_or_caveats": ["на что обратить внимание / оговорки", "..."],
  "data_gaps": "чего в документе НЕ хватает для полной картины (или null)"
}
Правила: числа бери ТОЛЬКО из текста, не выдумывай. key_figures до 8, highlights и
risks до 5. Если текст не похож на осмысленный документ (обрывки/навигация) —
честно скажи это в summary и оставь массивы пустыми."""


def analyze_document(url: str, question: str | None = None, max_chars: int = 14000) -> dict:
    doc = fetch_document(url, max_chars=max_chars)
    if doc.get("error"):
        return {"error": doc["error"], "note": doc.get("note"),
                "hint": "Если это server-egress — документ можно проверить локально; на проде может требоваться релей."}
    text = doc.get("text") or ""
    user = (f"URL: {url}\nТип: {doc.get('kind')}\nДлина текста: {doc.get('chars')} символов.\n"
            + (f"Вопрос пользователя: {question}\n" if question else "")
            + f"\n=== ТЕКСТ ДОКУМЕНТА ===\n{text}")
    try:
        res = complete(_SYSTEM, user, json_mode=True, max_tokens=2000, temperature=0.2)
    except LLMError as e:
        logger.warning("analyze_document LLM fail: %s", e)
        return {"error": "llm_unavailable", "note": "Интерпретатор временно недоступен."}
    if not isinstance(res, dict):
        return {"error": "bad_llm_output"}
    res["source"] = {"url": url, "kind": doc.get("kind"), "chars": doc.get("chars")}
    res["is_demo"] = True
    return res
