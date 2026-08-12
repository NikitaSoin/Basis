"""Общая фаза РАЗВЕДКИ: собрать материал и записать досье — до написания текста.

🔴 ЗАЧЕМ ОБЩИЙ МОДУЛЬ. Разведка появилась у геополитики (`geo_scout`) и оказалась
нужна везде: макро-выпуску, карточкам, отраслям. Копировать её по доменам —
верный способ развести три расходящиеся версии одного механизма: где-то починили
обрыв финала, где-то нет. Домен задаёт ТОЛЬКО промпт и набор методичек; цикл,
границы, сохранение и разбор результата — здесь, в одном месте.

🔴 ЧТО ТАКОЕ ДОСЬЕ И ПОЧЕМУ ОНО ХРАНИТСЯ ОТДЕЛЬНО.
Досье — сырьё: факты с подтверждением, разбор по методичке, честный список
пробелов. Оно сохраняется своей версией и живёт независимо от опубликованного
текста. Это даёт три вещи, каждая проверена болью на этом проекте:
  • проверяемость — можно спросить, есть ли число из текста в собранном материале;
  • диагностику — когда блок выглядит бедно, видно, что случилось: не нашли
    материал или нашли и не использовали. По готовому тексту это неразличимо;
  • честную деградацию — пустая разведка видна как пустая, а не превращается в
    уверенный текст ни о чём.

🔴 РАЗВЕДКА НИКОГДА НЕ ОБЯЗАТЕЛЬНА ДЛЯ ПУБЛИКАЦИИ. Сбой поиска, недоступный сайт,
исчерпанный бюджет не должны гасить выпуск: слой пишется как раньше, по имеющимся
данным. Разведка добавляет материал, а не становится точкой отказа.
"""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion

logger = logging.getLogger(__name__)

# Общая часть промпта для любой разведки. Доменное — сверху, это — снизу.
FORMAT_SPEC = (
    "ФОРМАТ ОТВЕТА — строго JSON без пояснений вокруг:\n"
    "{\n"
    '  "facts": [ {"scope":"<к чему относится>", "claim":"<что произошло, '
    'конкретно>", "evidence":"<чем подтверждается: цифра, документ, решение>", '
    '"source_url":"<ссылка или пусто, если из переданных данных>", '
    '"tag":"факт"} ],\n'
    '  "analysis": [ {"scope":"...", "channel":"<канал/механизм из методички>", '
    '"reasoning":"<как это доходит до денег>", "section":"<какой раздел методички '
    'применён>", "tag":"оценка|суждение"} ],\n'
    '  "gaps": [ "<чего добыть не удалось и почему — честно>" ],\n'
    '  "methodology_used": [ "<doc:раздел>", ... ]\n'
    "}\n"
)

COMMON_RULES = (
    "\n🔴 ЭКОНОМЬ ПРОГОН. Открывай не больше трёх-четырёх КОНКРЕТНЫХ разделов "
    "методичек (по номеру, а не части целиком): прочитанное остаётся в диалоге и "
    "дорожает с каждым шагом. Поиск — точечно, по тому, чего реально не хватает. "
    "Собирай досье по ходу, не откладывая до конца.\n"
    "🔴 ГЛАВНОЕ ПРАВИЛО. Досье — сырьё, а не витрина. Лучше пять проверенных "
    "фактов со ссылками и честный список пробелов, чем двадцать гладких фраз без "
    "опоры. Не выдумывай числа: нет цифры — так и напиши, это ценнее ложной.\n\n"
    + FORMAT_SPEC
)




# 🔴 ОЧИСТКА ДОСЬЕ ПЕРЕД ПЕРЕДАЧЕЙ ПИСАТЕЛЮ — защита от собственного материала.
# Разведка ходит в открытый веб и приносит тексты как есть: украинские написания
# топонимов, формулировки «оккупирован», имена изданий, которые платформа в РФ
# называть не должна. Писатель, опираясь на такой материал, повторяет его — и
# фильтр соответствия, работающий по принципу «всё или ничего», отклоняет ВЕСЬ
# суточный выпуск. То есть чем лучше сработала разведка, тем выше шанс потерять
# выпуск целиком. Поэтому материал приводится к допустимому виду ДО того, как
# попадёт в промпт: подмена, а не запрет в инструкции — запреты в длинном промпте
# размываются, замена в данных работает всегда.
# Это не отменяет фильтр на выходе: он остаётся последней линией.
_TOPONYMS = {
    r"Бахмут\w*": "Артёмовск",
    r"Артемівськ\w*|Артёмівськ\w*": "Артёмовск",
    r"Покровськ\w*": "Красноармейск",
    r"Часів\s+Яр\w*": "Часов Яр",
    r"Авдіївк\w*": "Авдеевка",
    r"Куп'янськ\w*|Куп’янськ\w*": "Купянск",
    r"Соледар\w*\s*\(укр\.?\)": "Соледар",
}
_WORDINGS = {
    # Замена должна ЧИТАТЬСЯ, а не только проходить фильтр: «город перешедш» —
    # мусор, который писатель повторит буквально. «Под контролем» встаёт в текст
    # и в именной, и в глагольной позиции без правки согласования.
    r"оккупир\w*": "под контролем",
    r"аннексир\w*": "вошедшие в состав",
    r"незаконн\w*\s+присоедин\w*": "вхождение в состав",
}
# Издания, чьи имена не тиражируем в материале (в РФ у части статус, при котором
# упоминание несёт юридический риск). Факт из них не выбрасываем — обезличиваем.
_GREY_MEDIA = re.compile(
    r"(?:The\s+)?(?:Meduza|Медуза|RFE/RL|RFE|Радио\s*Свобода|Настоящее\s*время|"
    r"Insider|Moscow\s*Times|Медиазона)",
    re.IGNORECASE)
_GREY_DOMAINS = re.compile(
    r"themoscowtimes\.com|meduza\.io|svoboda\.org|currenttime\.tv|theins\.ru|"
    r"zona\.media", re.IGNORECASE)


def _compliance_scrub(obj):
    """Привести материал к допустимому виду. Возвращает (очищенное, сколько замен).

    Ссылки обрабатываются ОТДЕЛЬНО от текста: подставлять «по данным ленты»
    внутрь URL бессмысленно — получается битый адрес вида
    «https://ru.по данным ленты/x». Адрес из серой зоны убирается целиком, а на
    его месте остаётся пометка, что источник обезличен: факт сохраняется, ссылка
    не тиражируется.
    """
    hits = 0

    def fix_text(s: str) -> str:
        nonlocal hits
        for pat, repl in _TOPONYMS.items():
            s, n = re.subn(pat, repl, s, flags=re.IGNORECASE)
            hits += n
        for pat, repl in _WORDINGS.items():
            s, n = re.subn(pat, repl, s, flags=re.IGNORECASE)
            hits += n
        s, n = _GREY_MEDIA.subn("по данным ленты", s)
        hits += n
        return s

    def fix_url(s: str) -> str:
        nonlocal hits
        if _GREY_DOMAINS.search(s) or _GREY_MEDIA.search(s):
            hits += 1
            return "источник обезличен"
        return s

    def walk(x, key: str = ""):
        if isinstance(x, str):
            return fix_url(x) if key in ("source_url", "url") else fix_text(x)
        if isinstance(x, dict):
            return {k: walk(v, k) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v, key) for v in x]
        return x

    return walk(obj), hits


def run(db: Session, *, kind: str, system: str, task: str,
        shelf_docs: list[str], max_steps: int = 12, web_call_cap: int = 5,
        budget: int = 150_000, trigger_reason: str = "разведка перед выпуском",
        ) -> dict | None:
    """Прогнать разведку и сохранить досье. None — валидного досье нет.

    kind — короткое имя версии (колонка varchar(8)!), например geodoss/macdoss.
    """
    from app.services.agent_runner import run_agent
    from app.services.agent_tools import WEB_TOOLS_SCHEMA
    from app.services.methodology import METHODOLOGY_TOOLS_SCHEMA, shelf_card

    tools = list(METHODOLOGY_TOOLS_SCHEMA) + list(WEB_TOOLS_SCHEMA)
    try:
        out = run_agent(
            db, system_prompt=system + COMMON_RULES + shelf_card(shelf_docs),
            task=task, tools_schema=tools, allowed_ticker="",
            max_steps=max_steps, max_tokens_total=budget,
            web_call_cap=web_call_cap, step_max_tokens=3000,
            final_max_tokens=7000,   # досье объёмное — иначе JSON обрывается
            final_instruction=FORMAT_SPEC,
        )
    except Exception as e:  # noqa: BLE001 — разведка не должна ронять выпуск
        logger.warning("scout[%s]: прогон не удался (%s) — слой пойдёт без досье",
                       kind, e)
        return None

    dossier = out.get("result")
    trace = out.get("trace") or []
    if not isinstance(dossier, dict):
        logger.warning("scout[%s]: досье нет (%s), шагов %d",
                       kind, out.get("stopped_reason"), len(trace))
        _save(db, kind, None, out, trigger_reason)
        return None

    dossier["_stats"] = {
        "фактов": len(dossier.get("facts") or []),
        "разборов": len(dossier.get("analysis") or []),
        "пробелов": len(dossier.get("gaps") or []),
        "разделов_методички": len(dossier.get("methodology_used") or []),
        "шагов": len(trace),
        "токенов": out.get("tokens_used"),
        "остановка": out.get("stopped_reason"),
    }
    logger.info("scout[%s]: досье — %s", kind, dossier["_stats"])
    _save(db, kind, dossier, out, trigger_reason)
    return dossier


def _save(db: Session, kind: str, dossier: dict | None, run_out: dict,
          trigger_reason: str) -> None:
    """Сохранить досье версией. Неудачная разведка тоже сохраняется — как
    rejected: «не сработало» обязано быть видно, иначе завтра будем гадать, был
    ли прогон вообще."""
    try:
        row = BarometerVersion(
            kind=kind, source="auto",
            status="published" if dossier else "rejected",
            payload=dossier,
            # Хвост сырого финала: когда досье не распарсилось, без него не
            # отличить «модель написала прозу вместо JSON» от «JSON оборвался
            # на середине» — а чинится это по-разному.
            gate_notes=[f"шагов: {len(run_out.get('trace') or [])}",
                        f"остановка: {run_out.get('stopped_reason')}",
                        f"токенов: {run_out.get('tokens_used')}",
                        f"хвост финала: {str(run_out.get('final_raw') or '')[-300:]}"],
            trigger_reason=trigger_reason,
        )
        db.add(row)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("scout[%s]: досье не сохранено (%s)", kind, e)
        db.rollback()


def dossier_block(dossier: dict | None, title: str = "СОБРАННОЕ ДОСЬЕ") -> str:
    """Досье в вид, пригодный для промпта аналитика-писателя."""
    if not isinstance(dossier, dict):
        return ""
    dossier, scrubbed = _compliance_scrub(dossier)
    if scrubbed:
        logger.info("scout: материал приведён к допустимому виду — %d замен", scrubbed)
    facts = dossier.get("facts") or []
    analysis = dossier.get("analysis") or []
    gaps = dossier.get("gaps") or []
    if not facts and not analysis:
        return ""
    parts = [f"{title} (разведка перед выпуском). 🔴 Это ТВОЙ материал: опирайся "
             "на него, а не на общие представления. Числа и факты бери отсюда; "
             "чего здесь нет — того не утверждай."]
    # 🔴 Досье компактнее, чем соблазн передать всё: вход писателя и так велик
    # (методички + вчерашний выпуск + лента), а с разросшимся досье ответ начал
    # обрываться на середине JSON. Отдаём выжимку без отступов — тот же материал
    # занимает вдвое меньше.
    if facts:
        parts.append("ФАКТЫ С ПОДТВЕРЖДЕНИЕМ:\n"
                     + json.dumps(facts[:20], ensure_ascii=False)[:4500])
    if analysis:
        parts.append("РАЗБОР ПО МЕТОДИЧКАМ (канал → как доходит):\n"
                     + json.dumps(analysis[:12], ensure_ascii=False)[:4500])
    if gaps:
        parts.append("ЧЕГО РАЗВЕДКЕ НЕ ХВАТИЛО (не заполняй эти пробелы догадками — "
                     "лучше честно сузить утверждение):\n- " + "\n- ".join(
                         str(g) for g in gaps[:8]))
    return "\n\n".join(parts)
