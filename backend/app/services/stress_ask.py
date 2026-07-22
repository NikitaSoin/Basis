"""«Спроси любой сценарий» — LLM-контур Стресс-тестирования v2 (владелец,
2026-07-17: «я пользователь спрашиваю (и называю ЛЮБОЙ сценарий) что произойдёт
— и мы должны ответить»).

Архитектура (философия та же, что macro_quant: LLM НЕ считает числа):
  1. ПАРСЕР (LLM, DeepSeek через llm.complete — прод-контур, как весь
     Обозреватель): свободный текст сценария → структурированный вектор:
     числовые целевые уровни (ставка/курс/нефть, если сценарий их подразумевает)
     + качественные факторы (санкции/конфликт/налоги/спрос, -1..1) + горизонт +
     короткая интерпретация «как мы поняли ваш сценарий». Только трансляция
     смысла, никакой арифметики.
  2. ЧИСЛА (код): числовая часть вектора → stress_numeric.numeric_impact()
     (детерминированные Δ выручки/EBITDA/прибыли по коэффициентам аналитика).
  3. НАПРАВЛЕНИЯ (код): качественные факторы → факторный движок
     (stress_scenarios.compute_impact) — только НАПРАВЛЕНИЕ по компаниям,
     без псевдоточных процентов (фронт показывает бакеты ▲▲/▲/─/▼/▼▼).

Кэш: нормализованный текст вопроса → ответ (in-memory, TTL 1ч) — повторные и
похожие вопросы не жгут токены. system_prompt СТАБИЛЬНЫЙ (DeepSeek кэширует
префикс — попадание ~в 50 раз дешевле, см. llm.py).

ДЕМО: наследует все оговорки контуров + сам парсер может понять сценарий не так
— интерпретация возвращается пользователю явно («как мы поняли»), чтобы он видел,
на ЧТО именно получил ответ.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time

from sqlalchemy.orm import Session

from app.services.llm import complete, LLMError

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 3600
_cache_lock = threading.Lock()

# Стабильный префикс (не менять между вызовами без причины — кэш DeepSeek).
_PARSER_SYSTEM = """Ты — парсер сценариев для стресс-теста российского фондового рынка.
Переведи пользовательский сценарий в структурированный JSON. НИКАКОЙ арифметики и
никаких выводов о компаниях — только трансляция смысла сценария в поля.

Верни СТРОГО JSON:
{
  "understood": "1-2 предложения: как ты понял сценарий (по-русски, для показа пользователю)",
  "horizon": "краткое указание горизонта, если назван (напр. '4 года'), иначе null",
  "numeric": {
    "key_rate_pct": <число или null — целевая ключевая ставка ЦБ в %, если сценарий её подразумевает>,
    "fx_usdrub": <число или null — целевой курс USD/RUB>,
    "oil_brent_usd": <число или null — целевая цена Brent $/барр.>
  },
  "qualitative": {
    "sanctions": <-1..1 или 0 — усиление(+)/ослабление(-) санкционного давления>,
    "conflict": <-1..1 или 0 — эскалация(+)/деэскалация(-) военного конфликта>,
    "fiscal": <-1..1 или 0 — рост(+)/снижение(-) налогово-регуляторного изъятия у бизнеса>,
    "demand": <-1..1 или 0 — ухудшение(-)/улучшение(+) внутреннего спроса и деловой активности>,
    "rate_direction": <-1..1 или 0 — направление ставки, ЕСЛИ числовое значение не названо: жёстче(+)/мягче(-)>
  },
  "out_of_scope": <true ТОЛЬКО если сценарий про внутрикорпоративное событие одной
    конкретной компании (адресный налог именно на неё, смена её собственника, авария
    на её заводе). Любые гео/макро/отраслевые сценарии — война где угодно, санкции,
    цены сырья, ставки, налоги на отрасль/экономику — это НАША тема, out_of_scope=false>,
  "out_of_scope_note": "<если out_of_scope — одно предложение почему, иначе null>"
}

Правила:
- Численные уровни заполняй ТОЛЬКО если сценарий их прямо называет или однозначно
  подразумевает конкретное значение. «Нефть обвалится» без цифры → oil_brent_usd: null,
  но это НЕ качественный фактор нефти — просто отметь в understood, что уровень не задан.
- Текущие ориентиры (для контекста, НЕ выводи их в ответ): ставка ЦБ ~14%, курс ~78 ₽/$,
  Brent ~$75-85. Если пользователь говорит «ставка вырастет до 20» → key_rate_pct: 20.
- «Оптимистичный сценарий ЦБ» → снижение ставки (rate_direction: -1) + улучшение спроса.
- «Война ещё N лет» → conflict: +0.5..0.7, sanctions: +0.4..0.6, fiscal: +0.3..0.5.
- Не выдумывай качественные факторы, которых в сценарии нет — ставь 0."""


def _norm_question(q: str) -> str:
    return " ".join(q.lower().split())[:500]


def parse_scenario(question: str) -> dict:
    key = hashlib.sha256(_norm_question(question).encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]
    parsed = complete(_PARSER_SYSTEM, question, json_mode=True, max_tokens=800, temperature=0.1)
    if not isinstance(parsed, dict):
        raise LLMError("Парсер вернул не-объект")
    with _cache_lock:
        _CACHE[key] = (now, parsed)
    return parsed


def _qualitative_intensities(q: dict) -> dict:
    """Качественные поля парсера → интенсивности факторного движка (знаковая
    конвенция quality_scenarios.json: для rate/sanctions/conflict знак интенсивности
    ОБРАТЕН выгоде компаний — растущее давление = положительная интенсивность)."""
    out = {}
    for k in ("sanctions", "conflict", "fiscal"):
        v = q.get(k)
        if isinstance(v, (int, float)) and v != 0:
            out[k] = max(-1.0, min(1.0, float(v)))
    v = q.get("demand")
    if isinstance(v, (int, float)) and v != 0:
        out["demand"] = max(-1.0, min(1.0, float(v)))
    v = q.get("rate_direction")
    if isinstance(v, (int, float)) and v != 0:
        out["rate"] = max(-1.0, min(1.0, float(v)))
    return out


def ask_scenario(db: Session, question: str) -> dict:
    """Полный конвейер: вопрос → парсер → числа + направления."""
    from app.services.stress_numeric import numeric_impact
    from app.services.stress_scenarios import compute_impact

    question = (question or "").strip()
    if not question or len(question) < 5:
        return {"error": "empty_question"}
    if len(question) > 1000:
        return {"error": "question_too_long"}

    try:
        parsed = parse_scenario(question)
    except LLMError as e:
        logger.warning("stress_ask: LLM недоступен: %s", e)
        return {"error": "llm_unavailable",
                "note": "Интерпретатор сценариев временно недоступен — попробуйте числовые поля (ставка/курс/нефть) или готовые сценарии."}

    result: dict = {
        "question": question,
        "understood": parsed.get("understood"),
        "horizon": parsed.get("horizon"),
        "is_demo": True,
    }

    if parsed.get("out_of_scope"):
        result["out_of_scope"] = True
        result["out_of_scope_note"] = parsed.get("out_of_scope_note") or (
            "Сценарий про точечное событие одной компании — факторная модель считает только "
            "общерыночные/секторные сдвиги. Такое разбирается вручную в карточке компании.")
        return result

    num = parsed.get("numeric") or {}
    key_rate = num.get("key_rate_pct") if isinstance(num.get("key_rate_pct"), (int, float)) else None
    fx = num.get("fx_usdrub") if isinstance(num.get("fx_usdrub"), (int, float)) else None
    oil = num.get("oil_brent_usd") if isinstance(num.get("oil_brent_usd"), (int, float)) else None

    if any(v is not None for v in (key_rate, fx, oil)):
        result["numeric"] = numeric_impact(db, key_rate, fx, oil)
        # Целевые уровни, которые парсер извлёк из текста — фронт двигает по ним
        # слайдеры визуально (не выдумывает уровни сам), только для полей, которые
        # сценарий реально называл (null остаётся null, не 0).
        result["numeric_targets"] = {"key_rate_pct": key_rate, "fx_usdrub": fx, "oil_brent_usd": oil}

    intensities = _qualitative_intensities(parsed.get("qualitative") or {})
    if intensities:
        from app.services.stress_scenarios import _OIL_SECTOR_TOKENS
        qual = compute_impact(db, intensities, {"commodity": _OIL_SECTOR_TOKENS})
        qual["intensities"] = intensities
        result["qualitative"] = qual

    # Экспертный качественный ответ (владелец, 2026-07-17 v3): ВСЕГДА при валидном
    # сценарии — LLM-эксперт на базе знаний платформы (геобарометр/сектора/экспозиции)
    # объясняет, что произойдёт и кто бенефициары/пострадавшие. Вопросы вроде «кто
    # выиграет от войны на Ближнем Востоке» 8-факторная рамка не ловила и v2 честно
    # отказывала — теперь на них отвечает именно этот контур.
    from app.services.stress_expert import expert_answer
    expert = expert_answer(db, question, parsed.get("understood"))
    if expert:
        result["expert"] = expert

    if "numeric" not in result and "qualitative" not in result and "expert" not in result:
        result["no_signal"] = True
        result["note"] = ("Не удалось интерпретировать сценарий — уточните формулировку "
                         "(например: «ставка 20%», «нефть $50», «война затягивается», "
                         "«налоги на бизнес растут»).")
    return result
