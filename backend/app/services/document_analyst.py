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
честно скажи это в summary и оставь массивы пустыми.
ВАЖНО про пропуски: если в задании указано, что часть страниц PDF не имеет
текстового слоя (таблицы-изображения) — показатели, которых нет в переданном
тексте, скорее всего именно ТАМ. НИКОГДА не пиши «компания не раскрыла X» — пиши
«X не извлечён из PDF (страница без текстового слоя)» в data_gaps. Это реальное
различие: у отчётностей крупных эмитентов страница P&L/баланса часто свёрстана
изображением, и выручка/себестоимость при этом РАСКРЫТЫ компанией."""


def analyze_document(url: str, question: str | None = None, max_chars: int = 28000) -> dict:
    doc = fetch_document(url, max_chars=max_chars)
    if doc.get("error"):
        # detail (тип исключения — ReadTimeout/ConnectError/...) раньше терялся
        # здесь — диагностика egress-сбоя требовала внешнего curl к прод-API,
        # чтобы увидеть точную причину. Пробрасываем дальше.
        return {"error": doc["error"], "detail": doc.get("detail"), "note": doc.get("note"),
                "hint": "Если это server-egress — документ можно проверить локально; на проде может требоваться релей."}
    text = doc.get("text") or ""
    ext = doc.get("extraction") or {}
    ext_note = ""
    if ext.get("pages_no_text_layer"):
        ext_note = (f"⚠️ ТЕХНИЧЕСКОЕ ОГРАНИЧЕНИЕ ИЗВЛЕЧЕНИЯ: страницы "
                    f"{ext['pages_no_text_layer']} из {ext.get('pages_total')} НЕ имеют "
                    f"текстового слоя (таблицы-изображения) — их содержимое ОТСУТСТВУЕТ в "
                    f"тексте ниже. Показатели, которых не видишь, вероятно там — говори "
                    f"«не извлечён из PDF», НЕ «компания не раскрыла».\n")
    if ext.get("truncated"):
        ext_note += "⚠️ Текст обрезан по лимиту — хвост документа не передан.\n"
    user = (f"URL: {url}\nТип: {doc.get('kind')}\nДлина текста: {doc.get('chars')} символов.\n"
            + ext_note
            + (f"Вопрос пользователя: {question}\n" if question else "")
            + f"\n=== ТЕКСТ ДОКУМЕНТА ===\n{text}")
    try:
        res = complete(_SYSTEM, user, json_mode=True, max_tokens=2000, temperature=0.2)
    except LLMError as e:
        logger.warning("analyze_document LLM fail: %s", e)
        return {"error": "llm_unavailable", "note": "Интерпретатор временно недоступен."}
    if not isinstance(res, dict):
        return {"error": "bad_llm_output"}
    res["source"] = {"url": url, "kind": doc.get("kind"), "chars": doc.get("chars"),
                     "pages_no_text_layer": ext.get("pages_no_text_layer") or []}
    res["is_demo"] = True
    return res


def analysis_to_markdown(res: dict, url: str) -> str:
    """Разбор → markdown для сохранения в историю диалогов ассистента (раньше
    разбор жил только в локальном состоянии панели и терялся при уходе со
    вкладки — жалоба владельца 2026-07-26)."""
    lines = [f"**Разбор документа:** {res.get('doc_type') or 'документ'}",
             f"_{url}_", ""]
    if res.get("summary"):
        lines += [res["summary"], ""]
    if res.get("key_figures"):
        lines.append("**Ключевые показатели:**")
        for kf in res["key_figures"]:
            note = f" — {kf['note']}" if kf.get("note") else ""
            lines.append(f"- {kf.get('metric')}: {kf.get('value')}{note}")
        lines.append("")
    if res.get("highlights"):
        lines.append("**Главное:**")
        lines += [f"- {h}" for h in res["highlights"]]
        lines.append("")
    if res.get("risks_or_caveats"):
        lines.append("**На что обратить внимание:**")
        lines += [f"- {r}" for r in res["risks_or_caveats"]]
        lines.append("")
    if res.get("data_gaps"):
        lines.append(f"**Пробелы данных:** {res['data_gaps']}")
    lines.append("")
    lines.append("_Разбор ИИ (демо), не аудит. Не является ИИР._")
    return "\n".join(lines)
