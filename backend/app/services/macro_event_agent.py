"""Агент-исследователь события (методичка v3, Часть 16 «событие → макро»).

Что закрывает: до сих пор блок узнавал о событии только из пересказов ленты и барометра.
Между «в ленте мелькнул топливный кризис» и «вот что он делает с инфляцией и ставкой»
лежит работа, которую никто не выполнял: собрать факты о масштабе, проверить их у
источника, разложить по каналам входа в экономику.

🔴 Разделение ролей (Часть 0 методички): агент собирает ФАКТЫ и раскладывает их по
маршруту 16.1, но НЕ выносит суждение о траектории ставки — это работа синтеза, который
видит всю картину. Агент, рассуждающий о ДКП в одиночку по одному событию, будет
переоценивать его значимость: он больше ничего не видит.

Результат идёт в снапшот отдельной секцией: синтез получает не «в ленте что-то про
топливо», а разобранное событие с числами, каналами, лагом и ссылками.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import macro_gap_tools
from app.services.agent_runner import run_agent

logger = logging.getLogger(__name__)

# Каналы входа события в экономику — закрытый список из Части 16.2. Закрытый намеренно:
# свободная формулировка канала превращает разбор в пересказ.
_CHANNELS = ("издержки/предложение", "логистика", "совокупный спрос", "предложение труда",
             "бюджет и налоговое изъятие", "курс", "ожидания и неопределённость")

_SYSTEM = f"""Ты — аналитик-исследователь платформы Basis. Тебе называют СОБЫТИЕ, которое
сейчас на повестке. Твоя задача — собрать по нему ФАКТЫ и разложить их по маршруту
разбора. Ты НЕ прогнозируешь ставку и НЕ оцениваешь рынок — это делает другой модуль,
который видит всю макрокартину целиком.

Порядок работы:
1. search_our_feed — что об этом писали у нас (Коммерсант, Интерфакс, РБК, ЦБ, аналитика).
2. read_feed_item — открой самые содержательные материалы, вытащи ЧИСЛА (масштаб, объёмы,
   доли, сроки).
3. web_search / fetch_document — только если своего материала не хватает.
Максимум 3-4 поиска. Нашёл подходящее — открывай, а не ищи дальше.

Что важно:
- 🔴 ВАЖНОСТЬ И СТАДИЮ оценивай САМ, опираясь на величины. Одно и то же событие в
  разные недели значит разное: топливный кризис на пике и он же на спаде — это разные
  выводы. «Удары по складам» могут быть локальным эпизодом (importance 1-2), а могут
  означать перенос войны на гражданскую логистику (4-5) — решает МАСШТАБ: какая доля
  оборота/мощностей/перевозок затронута.
- Событие УЖЕ ОТЫГРАННОЕ рынком и затухающее помечай stage="затухает" или
  "исчерпано" — это ценнее, чем пересказывать его как новость.
- Числа бери ТОЛЬКО из текста источника, дословно. Не оценивай «на глаз».
- Различай факт и чью-то оценку: «переработка упала на 25%» и «эксперты ожидают падения»
  это разные вещи, помечай.
- Каналы входа выбирай ТОЛЬКО из списка: {', '.join(_CHANNELS)}.
- Масштаб указывай порядком величины, а не выдуманной точностью.
- Чего не нашёл — оставь пустым и скажи в gaps. Пустое поле честнее выдуманного.

Финальный ответ БЕЗ вызова инструментов, строго JSON:
{{
  "event": "<что произошло, одно предложение, БЕЗ домыслов о причинах>",
  "facts": [{{"claim": "<факт с числом>", "source_url": "<ссылка>",
              "quote": "<дословный фрагмент, до 200 знаков>", "kind": "факт|оценка"}}],
  "channels": ["<канал из списка>"],
  "scale": "<порядок величины: сколько процентов рынка/объёма/бюджета затронуто>",
  "importance": "<1-5, где 1 — локальный эпизод без макроэффекта, 3 — заметно для
     отдельных отраслей, 5 — меняет траекторию ставки/инфляции/курса для всей экономики>",
  "importance_why": "<чем измеряется этот балл: доля рынка, объёмы, число занятых, сумма
     в бюджете. Без опоры на величину балл не ставь>",
  "stage": "<нарастает|пик|затухает|исчерпано> — на какой стадии событие СЕЙЧАС",
  "stage_why": "<по каким наблюдаемым признакам видно стадию>",
  "scenario_link": "<как событие соотносится с текущим геополитическим сценарием: он
     подтверждается, приближается переход к другому или ничего не меняется>",
  "lag": "<сразу|кварталы|отложенно> — и почему",
  "persistence": "<разовый шок|структурный сдвиг> — и почему",
  "affected_sectors": ["<сектор>"],
  "gaps": ["<чего не удалось найти>"]
}}"""


def pick_current_event(db: Session) -> str | None:
    """Главное событие повестки — из барометра, иначе из горячих тем ленты.

    Сознательно НЕ спрашиваем у LLM «что сейчас главное»: барометр уже собран
    аналитиком-геополитиком, а лента ранжирована. Лишний вызов ради того, что уже
    посчитано, — трата.
    """
    try:
        from app.services.barometer_store import get_payload_with_meta
        payload = get_payload_with_meta(db, "geo") or {}
        summary = payload.get("summary")
        if isinstance(summary, str) and len(summary) > 40:
            return summary[:400]
    except Exception:  # noqa: BLE001
        logger.warning("event_agent: барометр недоступен", exc_info=True)
    try:
        row = db.execute(text(
            "SELECT title FROM chronicle_entries "
            "WHERE importance IS NOT NULL AND published_at > now() - interval '10 days' "
            "ORDER BY importance DESC, published_at DESC LIMIT 1")).first()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


def _geo_context(db: Session) -> str:
    """Короткая рамка из гео-барометра: текущий сценарий и вероятности.

    🔴 Без неё агент оценивает событие в вакууме. «Слухи о мобилизации» значат разное
    при сценарии затяжной войны и при сценарии перемирия — и именно связку со
    сценарием владелец назвал ненастроенной.
    """
    try:
        from app.services.barometer_store import get_payload_with_meta
        sc = ((get_payload_with_meta(db, "geo") or {}).get("scenario") or {})
        if not isinstance(sc, dict):
            return ""
        parts = []
        if sc.get("current_lean"):
            parts.append(f"текущий сценарий {sc['current_lean']}")
        probs = sc.get("probabilities_6m")
        if isinstance(probs, dict):
            top = sorted(probs.items(), key=lambda kv: -float(kv[1] or 0))[:3]
            parts.append("вероятности 6м: " + ", ".join(f"{k} {float(v):.0%}" for k, v in top))
        trig = sc.get("triggers")
        if isinstance(trig, list) and trig:
            parts.append("триггеры перехода: " + "; ".join(str(t)[:110] for t in trig[:3]))
        return ". ".join(parts)[:700]
    except Exception:  # noqa: BLE001
        return ""


def research_event(db: Session, event_hint: str, *, max_steps: int = 8) -> dict:
    """Разобрать событие по маршруту Части 16. Возвращает факты, не суждения."""
    geo = _geo_context(db)
    task = (f"Событие на повестке: {event_hint}\n\n"
            + (f"Текущая геополитическая рамка (барометр платформы): {geo}\n\n" if geo else "")
            + (f"Разбери его по маршруту: что произошло (факты с числами и ссылками), каким "
            f"каналом входит в экономику, масштаб, лаг, разовое или структурное, какие "
            f"секторы затрагивает. Сегодня {datetime.now(timezone.utc).date().isoformat()}."))
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
                    max_steps=max_steps, max_tokens_total=120_000,
                    # финал этого агента объёмный (факты с цитатами) — на 1600 он
                    # обрывался на середине JSON и не парсился
                    web_call_cap=4, executor=_executor, step_max_tokens=4000)
    result = run.get("result") or {}
    blob = "\n".join(seen)
    verified, dropped = [], []
    for f in result.get("facts") or []:
        if not isinstance(f, dict):
            continue
        quote = str(f.get("quote") or "")
        # Факт остаётся, только если его цитата реально встречалась в открытых текстах.
        # Тот же принцип, что в гейте добытчика: без этого «факт» — пересказ по памяти.
        probe = quote[:60].strip()
        if probe and probe in blob:
            verified.append(f)
        else:
            dropped.append(f.get("claim"))
    if dropped:
        logger.info("event_agent: отброшено неподтверждённых фактов: %s", len(dropped))
    channels = [c for c in (result.get("channels") or []) if c in _CHANNELS]
    return {
        "event": result.get("event"),
        "importance": result.get("importance"),
        "importance_why": result.get("importance_why"),
        "stage": result.get("stage"),
        "stage_why": result.get("stage_why"),
        "scenario_link": result.get("scenario_link"),
        "facts": verified[:8],
        "channels": channels,
        "scale": result.get("scale"),
        "lag": result.get("lag"),
        "persistence": result.get("persistence"),
        "affected_sectors": result.get("affected_sectors") or [],
        "gaps": result.get("gaps") or [],
        "unverified_dropped": len(dropped),
        "tokens_used": run.get("tokens_used"),
        "stopped_reason": run.get("stopped_reason"),
    }


def research_current_event(db: Session) -> dict | None:
    hint = pick_current_event(db)
    if not hint:
        return None
    try:
        return research_event(db, hint)
    except Exception:  # noqa: BLE001
        logger.exception("event_agent: разбор события упал")
        return None
