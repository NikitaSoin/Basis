"""Агент-ревизор выпуска: проверяет спорные утверждения ПОСЛЕ генерации.

Разделение с код-гейтом (`macro_release_gate`):
  - гейт ловит то, что проверяется формально: структура, наличие центра и диапазона,
    числа против key_facts, несуществующие тикеры, эпистемические теги;
  - ревизор ловит то, что формально не проверяется: утверждение о факте, которого нет
    в переданных данных, ссылка на событие без подтверждения, «уверенная» цифра из
    ниоткуда. Для этого нужно пойти и посмотреть, а не сверить по таблице.

🔴 Ревизор НЕ переписывает выпуск. Правка чужого суждения моделью — это подмена автора,
а не проверка: непонятно, кто в итоге отвечает за текст. Он возвращает ЗАМЕЧАНИЯ, они
пишутся в срез и видны в отладке; грубое ловится гейтом до публикации.

🔴 Проверяет ВЫБОРОЧНО — 2-3 самых рискованных утверждения, а не весь выпуск. Полная
ревизия каждого тезиса стоила бы дороже самого выпуска и всё равно упиралась бы в те же
источники. Берём то, где цена ошибки максимальна: числа, поданные как ФАКТ.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.services import macro_gap_tools
from app.services.agent_runner import run_agent

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — ревизор аналитической платформы Basis. Тебе дают УТВЕРЖДЕНИЕ из готового
макро-выпуска. Задача: проверить, подтверждается ли оно источниками.

Как работать:
1. search_our_feed — что об этом есть у нас (Коммерсант, Интерфакс, РБК, ЦБ, ЦМАКП).
2. read_feed_item — открой подходящее и найди конкретное число или формулировку.
3. web_search / fetch_document — если своего материала не хватило.
Максимум 3 поиска. Нашёл — открывай, а не ищи дальше.

Возможные вердикты:
- "supported" — нашёл подтверждение (укажи источник и цитату);
- "contradicted" — источники говорят иное (укажи, что именно);
- "unsupported" — подтверждения не нашлось. Это НОРМАЛЬНЫЙ исход: значит утверждение
  подано увереннее, чем позволяют данные.

Не придирайся к формулировкам и оценкам («экономика охлаждается» — это суждение, а не
факт, его проверять не надо). Проверяй ЧИСЛА и утверждения о свершившихся событиях.

Финальный ответ БЕЗ вызова инструментов, строго JSON:
{
  "verdict": "supported|contradicted|unsupported",
  "source_url": "<ссылка или null>",
  "quote": "<дословный фрагмент, до 250 знаков, или null>",
  "note": "<если contradicted/unsupported — в чём расхождение>"
}"""

# Утверждение достойно проверки, если в нём есть число И оно подано как факт.
_NUM_RE = re.compile(r"\d+[.,]?\d*\s*(?:%|млрд|млн|трлн|п\.п\.|пункт)")

_ANY_NUM_RE = re.compile(r"-?\d+[.,]?\d*")
# Величина = число С ЕДИНИЦЕЙ. Без этого требования в «чужие» попадали «2» из «2кв2026»
# и «4» из диапазона «4-5% SAAR» — порядковые номера, а не данные.
# (?<![\d.,-]) — минус берём как знак, только если перед ним не цифра: в «4-5% SAAR»
# это дефис диапазона, и «-5» уходило ревизору как отдельная величина.
_VALUE_RE = re.compile(r"(?<![\d.,-])(-?\d+[.,]?\d*)\s*(?:%|млрд|млн|трлн|п\.п\.|пункт)")


def _our_numbers(snapshot: dict | None) -> set[float]:
    """Все числа, которые платформа знает сама (ряды + готовые формулировки key_facts)."""
    out: set[float] = set()
    if not snapshot:
        return out
    for ind in snapshot.get("indicators") or []:
        if not isinstance(ind, dict):
            continue
        for k in ("current_value", "previous_value", "year_ago_value", "change_vs_previous"):
            v = ind.get(k)
            if isinstance(v, (int, float)):
                out.add(round(abs(float(v)), 2))
    for v in (snapshot.get("key_facts") or {}).values():
        for m in _ANY_NUM_RE.findall(str(v)):
            try:
                out.add(round(abs(float(m.replace(",", "."))), 2))
            except ValueError:
                continue
    return out


def _foreign_numbers(claim: str, ours: set[float]) -> list[str]:
    """Величины утверждения, которых НЕТ в данных платформы.

    🔴 Смысл фильтра. Первый живой прогон дал два «unsupported» на числах из НАШЕЙ же
    базы: внешний источник просто не повторял их дословно. Это не дефект выпуска —
    это шум, который обесценивает замечания ревизора и стоит платного прогона за штуку.
    Проверять во внешнем мире имеет смысл ровно то, чего у нас нет: число из прозы
    записки, из статьи или из воздуха. Своё сверяет код (гейт), а не агент.

    Сравнение по модулю: «-14,3%» в тексте и −14.3 в ряду — одна и та же величина, а
    знак в прозе часто несёт направление («падение на 14,3%»), не арифметику.
    """
    out: list[str] = []
    for m in _VALUE_RE.findall(claim):
        try:
            v = round(abs(float(m.replace(",", "."))), 2)
        except ValueError:
            continue
        if any(abs(v - o) <= max(0.05, o * 0.01) for o in ours):
            continue
        out.append(m)
    return out


def _text_of(block: dict) -> str:
    """Весь смысловой текст блока — БЕЗ белого списка имён полей.

    🔴 Осознанно не перечисляем ключи. Схема тезиса уже менялась («detail» →
    «chain»/«evidence»), и белый список дал ровно тот отказ, который невозможно
    заметить: ревизор отработал успешно, проверив НОЛЬ утверждений. Молчаливое
    обнуление проверки хуже её падения.
    """
    return " ".join(str(v) for k, v in block.items()
                    if k != "tag" and isinstance(v, str) and v.strip()).strip()


def _claims_to_check(sections: dict, limit: int = 3) -> list[str]:
    """Отобрать самые рискованные утверждения: числа под тегом «факт»."""
    out: list[str] = []
    for t in sections.get("theses") or []:
        if not isinstance(t, dict):
            continue
        text = _text_of(t)
        if t.get("tag") == "факт" and _NUM_RE.search(text):
            out.append(text)
    ev = sections.get("event_context")
    if isinstance(ev, dict) and ev.get("event"):
        blob = _text_of(ev)
        if _NUM_RE.search(blob):
            out.append(blob)
    # длинные утверждения режем: ревизору нужен тезис, а не абзац
    return [c[:400] for c in out[:limit]]


def review_release(db: Session, sections: dict, *, limit: int = 3,
                   snapshot: dict | None = None) -> dict:
    """Выборочная ревизия выпуска. Возвращает замечания, ничего не переписывая."""
    claims = _claims_to_check(sections, limit=limit * 2)
    ours = _our_numbers(snapshot)
    targeted: list[tuple[str, list[str]]] = []
    skipped_own = 0
    for c in claims:
        foreign = _foreign_numbers(c, ours) if ours else []
        if ours and not foreign:
            skipped_own += 1        # всё число утверждения — наши данные, проверять нечего
            continue
        targeted.append((c, foreign))
    targeted = targeted[:limit]
    if not targeted:
        return {"checked": 0, "issues": [], "skipped_own_data": skipped_own,
                "note": "все числовые утверждения опираются на данные платформы"}

    issues, checked, tokens = [], 0, 0
    for claim, foreign in targeted:
        seen: list[str] = []

        def _executor(db_, name, args, _seen=seen):
            out = macro_gap_tools.execute(db_, name, args)
            try:
                _seen.append(json.dumps(out, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass
            return out

        focus = (f"\n\nПроверяй В ПЕРВУЮ ОЧЕРЕДЬ эти числа — их нет в наших данных: "
                 f"{', '.join(foreign)}." if foreign else "")
        task = (f"Проверь утверждение из макро-выпуска:\n«{claim}»{focus}\n\n"
                f"Сегодня {datetime.now(timezone.utc).date().isoformat()}.")
        try:
            run = run_agent(db, system_prompt=_SYSTEM, task=task,
                            tools_schema=macro_gap_tools.TOOLS_SCHEMA,
                            max_steps=6, max_tokens_total=80_000,
                            web_call_cap=3, executor=_executor)
        except Exception:  # noqa: BLE001
            logger.exception("reviewer: проверка утверждения упала")
            continue
        checked += 1
        tokens += run.get("tokens_used") or 0
        res = run.get("result") or {}
        verdict = str(res.get("verdict") or "unsupported")
        if verdict == "supported":
            # Подтверждение засчитываем, только если цитата реально была в открытых
            # текстах — иначе «подтвердил» по памяти.
            quote = str(res.get("quote") or "")[:60].strip()
            if quote and quote not in "\n".join(seen):
                verdict = "unsupported"
        if verdict != "supported":
            issues.append({"claim": claim[:200], "verdict": verdict,
                           "note": res.get("note"), "source_url": res.get("source_url")})
    logger.info("reviewer: проверено %s утверждений, замечаний %s, своих пропущено %s, токенов %s",
                checked, len(issues), skipped_own, tokens)
    return {"checked": checked, "issues": issues, "skipped_own_data": skipped_own,
            "tokens_used": tokens}
