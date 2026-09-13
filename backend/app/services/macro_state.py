"""Состояние экономики на дату — MacroState_t (макро-база §0.1–0.2, §16.2, §16.4, §15.4).

🔴 ЗАЧЕМ (владелец, 2026-09-13, пункт 2 плана «три карты пациента»).
Методика прямо говорит: «агент не является генератором экономических текстов;
его задача — поддерживать постоянно обновляемую модель состояния экономики, в
которой каждый новый выпуск статистики — входящий сигнал, обновляющий состояние,
диагноз и прогноз» (§0.1). До сих пор макро-контур имел только ВЫПУСКИ
(macro_interpretations — текст на сегодня) и ни одной записи «состояние на
дату, что изменилось с прошлого раза». У геополитики такая запись есть —
барометр с версиями (barometer_versions, kind="geo"). Здесь то же самое для
макро: kind="macro", тот же стол, тот же read-path (barometer_store), тот же
принцип «вчерашняя версия — вход для сегодняшней».

ЧТО ВНУТРИ ПОЛЕЗНОЙ НАГРУЗКИ — по методике, не по вкусу:
  blocks[]      — тринадцать блоков §16.2 (выпуск, спрос, предложение, инфляция,
                  труд, кредит, финусловия, бюджет, внешний сектор, курс,
                  ожидания, регионы, потенциал); у каждого уровень / тренд /
                  ускорение / отклонение от нормы / механизм / маркировка §16.5
                  / доказательства (коды индикаторов) / дельта к прошлой версии.
  diagnosis     — §16.4: состояние → механизм → режим → главное ограничение →
                  вероятная политика. ДО прогноза, не после (кодекс К 0.1).
  forecast      — §15.4: по переменным, три сценария с вероятностями, наиболее
                  вероятный ОТДЕЛЬНО от наиболее опасного, механизм у каждого.
  revision_triggers — §15.4: объявленные заранее пусковые условия пересмотра;
                  без них прогноз не проверяем.
  inputs        — что подали на вход: срез данных, гео-барометр (ребро ГМ),
                  институциональные параметры (ребро ИМ — пока заглушка).

ЧЕГО ЗДЕСЬ НЕТ. Витрины и прозы для пользователя — это работа интерпретатора
(macro_interpreter), который теперь может опираться на состояние. Сам расчёт
чисел — числа приходят из статистики (кодекс К 0.7), агент их не выводит.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, handoffs, llm

logger = logging.getLogger(__name__)

KIND = "macro"
TRIGGER = "ежедневная пересборка состояния"

# Тринадцать блоков §16.2 — фиксированный список, чтобы состояние не «худело»
# от прогона к прогону (память проекта: правило стабильности консервирует схему,
# поэтому схему задаём кодом, а не просим модель её помнить).
BLOCKS: list[tuple[str, str]] = [
    ("output", "Выпуск: рост, источники, ограничения"),
    ("demand", "Спрос: потребление, инвестиции, госспрос, чистый экспорт"),
    ("supply", "Предложение: мощности, труд, производительность, потенциал"),
    ("inflation", "Инфляция: уровень, состав, устойчивые компоненты, ожидания"),
    ("labor", "Рынок труда: безработица, вакансии, зарплаты, дефицит"),
    ("credit", "Кредит: корпоративный, розничный, импульс, льготный"),
    ("financial_conditions", "Финансовые условия: реальная ставка, спреды, доступность"),
    ("budget", "Бюджет: баланс, импульс, структура расходов, финансирование"),
    ("external", "Внешний сектор: текущий счёт, условия торговли, экспорт"),
    ("fx", "Курс: уровень, каналы, режим"),
    ("expectations", "Ожидания: инфляционные, деловые, потребительские"),
    ("regions", "Региональная и отраслевая неоднородность"),
    ("potential", "Структурный потенциал и главное ограничение"),
]
FORECAST_VARS = ["gdp", "inflation", "key_rate", "fx", "unemployment", "credit", "budget"]
MARKS = {"факт", "расчёт", "внешняя оценка", "суждение", "сценарий"}


# ─────────────────────────── вход ───────────────────────────


def _feed_schema():
    """Поиск по всему потоку платформы — для аналитика (владелец 2026-09-13). Мягко."""
    try:
        from app.services.feed_tools import FEED_TOOLS_SCHEMA
        return list(FEED_TOOLS_SCHEMA)
    except ImportError:  # pragma: no cover
        return []


def _feed_exec(db, name, args):
    try:
        from app.services.feed_tools import execute
        return execute(db, name, args)
    except ImportError:  # pragma: no cover
        return None

def _prev_state(db: Session) -> BarometerVersion | None:
    return barometer_store.current_row(db, KIND)


def _geo_edge(db: Session) -> dict:
    """Ребро ГМ «геополитика → макроэкономика»: шоки и сценарии из ТЕКУЩЕЙ
    опубликованной версии гео-барометра (не из файла — файл июльский)."""
    row = barometer_store.current_row(db, "geo")
    if not row or not row.payload:
        return {"error": "no_geo_barometer"}
    p = row.payload
    return {"as_of": p.get("as_of"), "version_id": row.id,
            "scenario": p.get("scenario"), "regions_summary": {
                k: (v.get("summary") if isinstance(v, dict) else None)
                for k, v in (p.get("regions") or {}).items()},
            "sector_flags": p.get("sector_flags"), "watchlist_30d": p.get("watchlist_30d")}


def _inst_edge(db: Session) -> dict:
    """Ребро ИМ «институты → макроэкономика»: пока только барометр институтов
    целиком (сценарий, алерты, пол премии). Разложение на параметры трансмиссии
    (ИМ Часть 3) — следующий шаг пункта 3 плана."""
    row = barometer_store.current_row(db, "inst")
    if not row or not row.payload:
        return {"error": "no_inst_barometer"}
    p = row.payload
    return {"as_of": p.get("as_of"), "version_id": row.id, "scenario": p.get("scenario"),
            "alerts": p.get("alerts"), "crp_floor_pp": p.get("institutional_crp_floor_pp")}


def edges_for_scout(inputs: dict) -> dict:
    return {"geo_edge": inputs.get("geo_edge"), "inst_edge": inputs.get("inst_edge")}


def _peer_payloads(db: Session) -> dict[str, dict | None]:
    out = {}
    for kind in ("geo", "inst_state"):
        row = barometer_store.peer_view(db, kind)   # сегодняшний черновик соседа, иначе опубликованное
        out[kind] = row.payload if row and row.payload else None
    return out


def _peer_questions(db: Session, me: str) -> list[dict]:
    """Вопросы соседей ко мне из последней перекрёстной проверки."""
    try:
        from app.services.cross_review import questions_for
        return questions_for(db, me)
    except Exception:  # noqa: BLE001
        return []


def gather_inputs(db: Session) -> dict:
    """Тот же типизированный срез, что у интерпретатора, плюс два ребра.

    🔴 Агенту уходит СЖАТЫЙ текст среза (_snapshot_text, ~90 тыс. знаков), а не
    сырой JSON: сырой с полными текстами записок весит 610 тыс. знаков, а бюджет
    цикла считается НАКОПИТЕЛЬНО — задача уходит модели на каждом шаге, и такой
    вход сжёг бы бюджет за два хода (в analyst.py записан прогон, где один шаг
    съел 590 тыс. токенов). Полные тексты записок агент при нужде читает
    инструментом. Один вход — два потребителя (выпуск и состояние): расхождений
    между ними по данным быть не может."""
    from app.services.macro_interpreter import gather_snapshot, _snapshot_text
    snap = gather_snapshot(db)
    return {
        "snapshot_text": _snapshot_text(snap),
        "indicators": snap.get("indicators"),          # для проверки «есть ли данные»
        "data_gaps": snap.get("data_gaps"),
        "geo_edge": _geo_edge(db),
        "inst_edge": _inst_edge(db),
        "peers": _peer_payloads(db),
        "peer_questions": _peer_questions(db, "macro"),
    }


# ─────────────────────────── гейт ───────────────────────────

def _gate(fresh: dict, prev: dict | None) -> tuple[dict, list[str]]:
    """Не отклоняет прогон из-за одной строки — откатывает её к прошлой версии
    и пишет заметку. Отклонение целиком — только за отсутствие каркаса."""
    notes: list[str] = []
    prev_blocks = {b.get("key"): b for b in ((prev or {}).get("blocks") or []) if isinstance(b, dict)}

    # 1. Все тринадцать блоков на месте; пропавший — переносится с прошлой версии
    have = {b.get("key"): b for b in (fresh.get("blocks") or []) if isinstance(b, dict)}
    rebuilt = []
    for key, title in BLOCKS:
        b = have.get(key)
        if b is None and key in prev_blocks:
            b = dict(prev_blocks[key]); b["carried_over"] = True
            notes.append(f"{key}: блок не вернулся — перенесён с прошлой версии")
        if b is None:
            b = {"key": key, "title": title, "level": None, "mark": "суждение",
                 "data_flag": "нет данных в этом прогоне"}
            notes.append(f"{key}: блока нет ни сейчас, ни раньше — пустая заготовка")
        b.setdefault("key", key); b.setdefault("title", title)
        # 2. Маркировка §16.5 обязательна
        if b.get("mark") not in MARKS:
            b["mark"] = "суждение"; notes.append(f"{key}: маркировка не из списка → «суждение»")
        # 3. Изменение без обоснования — откат к прошлому уровню
        pb = prev_blocks.get(key)
        if pb and b.get("level") != pb.get("level") and len(str(b.get("delta_rationale") or "")) < 20:
            b["level"] = pb.get("level"); b["delta_rationale"] = None
            notes.append(f"{key}: уровень изменён без обоснования → откат")
        rebuilt.append(b)
    fresh["blocks"] = rebuilt

    # 4. Диагноз до прогноза (К 0.1): без диагноза прогноз не публикуем
    diag = fresh.get("diagnosis") or {}
    for f in ("current_state", "mechanism", "regime", "main_constraint"):
        if not str(diag.get(f) or "").strip():
            notes.append(f"diagnosis.{f}: пусто")
    # 5. Прогноз: вероятности к единице, «вероятный» ≠ «опасный» помечаем
    fc = fresh.get("forecast") or {}
    for var, v in (fc.get("variables") or {}).items() if isinstance(fc.get("variables"), dict) else []:
        probs = (v or {}).get("probabilities")
        if isinstance(probs, dict) and probs:
            try:
                total = sum(float(x) for x in probs.values())
                if total > 0 and abs(total - 1.0) > 0.005:
                    v["probabilities"] = {k: round(float(x) / total, 3) for k, x in probs.items()}
                    notes.append(f"forecast.{var}: вероятности {total:.3f} → нормализованы")
            except (TypeError, ValueError):
                notes.append(f"forecast.{var}: нечисловые вероятности")
        if v and v.get("most_likely") and v.get("most_likely") == v.get("most_dangerous"):
            notes.append(f"forecast.{var}: вероятный и опасный сценарии совпали — проверить (§15.4)")
    # 6. Пусковые условия пересмотра — без них прогноз непроверяем
    if not fresh.get("revision_triggers"):
        notes.append("revision_triggers: пусто — прогноз непроверяем (§15.4)")
    # 6б. Контракты передач соседям: пустое обязательное поле — заметка (пункт 3)
    notes += handoffs.gate_notes(fresh, "macro")
    # 7. Цифры и язык (владелец 2026-09-13: «везде конкретные цифры», без эпитетов).
    #    Код не умеет судить о стиле, но умеет считать числа и ловить запрещённые
    #    обороты — этого достаточно, чтобы пустословие не прошло молча.
    import re as _re
    digits = _re.compile(r"\d")
    if len(digits.findall(str(fresh.get("summary") or ""))) < 4:
        notes.append("summary: меньше четырёх чисел — вывод без конкретики")
    for b in fresh["blocks"]:
        text = " ".join(str(b.get(k) or "") for k in ("level", "trend", "momentum", "delta_vs_prev"))
        if b.get("level") and not digits.search(text) and "нет данных" not in text.lower():
            notes.append(f"{b['key']}: ни одного числа в описании состояния")
    banned = _re.compile(r"плоск\w+ рост|липк\w+ инфляц|перегрев|мягк\w+ посадк|навес|окно возможност",
                         _re.IGNORECASE)
    hit = banned.search(json.dumps(fresh, ensure_ascii=False))
    if hit:
        notes.append(f"язык: запрещённый оборот «{hit.group(0)}» — переформулировать понятными словами")
    return fresh, notes


def _reject(db: Session, parent_id: int | None, why: list[str]) -> BarometerVersion:
    row = BarometerVersion(kind=KIND, source="auto", status="rejected", payload=None,
                           gate_notes=why, parent_id=parent_id, trigger_reason=TRIGGER)
    db.add(row); db.commit(); db.refresh(row)
    logger.warning("macro_state: версия отклонена: %s", " | ".join(why)[:400])
    return row


# ─────────────────────────── сборка ───────────────────────────

_SYSTEM = (
    "Ты — макроэкономический агент Basis (независимая аналитика для частного "
    "инвестора в РФ). Твоя работа — не текст, а МОДЕЛЬ СОСТОЯНИЯ ЭКОНОМИКИ на "
    "дату, которую ты поддерживаешь и обновляешь: каждый новый выпуск статистики — "
    "входящий сигнал, обновляющий состояние, диагноз и прогноз, а не повод для "
    "комментария. Объект — экономика России.\n\n"
    "Порядок работы задаёт методичка macro_base (§0.1: данные → состояние → "
    "диагноз → механизм → режим → прогноз; §16.2: тринадцать блоков состояния; "
    "§16.4: формат — сначала диагноз режима, потом всё остальное; §15.4: прогноз "
    "причинный, сценарный, вероятностный, с пусковыми условиями пересмотра). "
    "Правила доказательности — Общий кодекс (code): открой его первым.\n\n"
    "У тебя есть ПРОШЛАЯ версия состояния. Не переписывай её заново — обнови: "
    "по каждому блоку скажи, что изменилось и почему (delta_rationale), а что не "
    "изменилось — оставь. Изменение уровня без обоснования откатится гейтом.\n\n"
    "🔴 ЯЗЫК: обычные слова и цифры. Первая сборка написала «плоский рост при "
    "липкой инфляции, выпуск около полупроцента» — это запрещено. Надо: «ВВП растёт "
    "на 0,5% в год; инфляция 8,4% в годовом выражении, за август ускорилась с 7,9%, "
    "не снижается с мая». Слово «выпуск» не употреблять — говори «ВВП» или "
    "«промышленное производство» и называй число. Каждое изменение — было → стало → "
    "за какой период → источник.\n\n"
    "Числа берёшь ТОЛЬКО из переданного среза данных и внешних прогнозов, с кодом "
    "индикатора в evidence. Ненаблюдаемые величины (потенциал, нейтральная ставка) "
    "— без ложной точности, классом масштаба.\n\n"
    "ФОРМАТ (строго JSON): {\n"
    "  \"as_of\": \"YYYY-MM-DD\",\n"
    "  \"blocks\": [ {\"key\": <РОВНО один из: " + ", ".join(k for k, _ in BLOCKS) + ">, "
    "\"title\": <соответственно: " + "; ".join(f"{k} = {ti}" for k, ti in BLOCKS) + ">, "
    "\"level\": <словами: "
    "уровень>, \"trend\": <растёт|стоит|падает>, \"momentum\": <ускоряется|замедляется|"
    "стабильно>, \"deviation_from_norm\": <выше|около|ниже нормы + чем>, \"mechanism\": "
    "<что двигает, через какой канал>, \"leading_indicators\": [..], \"policy_stance\", "
    "\"constraints\", \"heterogeneity\", \"mark\": <факт|расчёт|внешняя оценка|суждение|"
    "сценарий>, \"evidence\": [{\"indicator_code\", \"value\", \"as_of\"}], "
    "\"delta_vs_prev\": <что изменилось>, \"delta_rationale\": <почему, ≥20 знаков>} ],\n"
    "  \"diagnosis\": {\"current_state\", \"mechanism\", \"regime\", \"main_constraint\", "
    "\"likely_policy\", \"main_risk\"},\n"
    "  \"forecast\": {\"horizons\": {..}, \"variables\": { <gdp|inflation|key_rate|fx|"
    "unemployment|credit|budget>: {\"base\", \"favorable\", \"adverse\", \"probabilities\": "
    "{\"base\":p,\"favorable\":p,\"adverse\":p}, \"most_likely\", \"most_dangerous\", "
    "\"mechanism\"} } },\n"
    "  \"revision_triggers\": [ {\"condition\", \"indicator_code\", \"threshold\", "
    "\"revises\"} ],\n"
    "  \"indicators_to_watch\": [..], \"shocks_from_geo\": <как учтён гео-барометр>, "
    "\"institutional_params\": <как учтены институты>,\n"
    "  \"summary\": <диагноз одним абзацем, §16.4 — НЕ начинать с числа>,\n"
    "  \"handoffs\": {\"to_geo\": {..}, \"to_inst\": {..}}  — см. блок ПЕРЕДАЧИ СОСЕДЯМ ниже,\n"
    "  \"answers_to_peers\": [ {\"from\", \"question\", \"answer\", \"evidence\"} ] — ответы на "
    "вопросы соседей из задания (если вопросы были — отвечать ОБЯЗАТЕЛЬНО, с числом и источником),\n"
    "  \"questions_to_peers\": [ {\"to\": <geo|inst_state>, \"question\", \"why_it_matters\"} ] — что "
    "тебе не хватило от соседей для твоего вывода,\n"
    "  \"methodology_used\": [..], \"sources\": [..], \"data_flags\": [..]\n"
    "}"
    + "  " + handoffs.FINAL_FIELDS + "\n"
    + handoffs.prompt_block("macro")
    + handoffs.CHAINS_RULE
)



def _contradictions_block(db: Session) -> str:
    """Противоречия, найденные сверкой, в которых участвует эта сводка (пункт 3):
    обязана либо снять, либо объяснить, почему права она."""
    try:
        from app.services.consistency_check import contradictions_for
        cs = contradictions_for(db, "macro")
    except Exception:  # noqa: BLE001
        cs = []
    return ("ПРОТИВОРЕЧИЯ, ЗАФИКСИРОВАННЫЕ СВЕРКОЙ С СОСЕДЯМИ (в поле contradictions_resolved "
            "по каждому: снято / объяснено, с числом и источником):\n"
            + (json.dumps(cs, ensure_ascii=False) if cs else "— нет —"))


def _critique_block(db: Session) -> str:
    """Замечания проверяющего к прошлой версии (пункт 5): исправить в этой сборке
    и отчитаться по каждому в поле critique_resolved (что сделано / почему нет)."""
    try:
        from app.services.critic import critique_for
        vs = critique_for(db, "macro")
    except Exception:  # noqa: BLE001
        vs = []
    return ("ЗАМЕЧАНИЯ ПРОВЕРЯЮЩЕГО К ПРОШЛОЙ ВЕРСИИ (исправить; по каждому — строка в "
            "critique_resolved: что сделано или почему замечание неверно):\n"
            + (json.dumps(vs, ensure_ascii=False) if vs else "— нет —"))


def _history_and_lessons(db: Session) -> str:
    """Хронология прошлых версий (траектория, не только вчера) + уроки прошлых
    проверок (владелец 2026-09-13). Мягкие импорты."""
    parts = []
    try:
        from app.services.state_history import for_prompt as _hist
        parts.append(_hist(db, "macro", limit=10))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.lessons import for_prompt as _less
        parts.append(_less(db, "macro"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)

def rebuild(db: Session, mode: str = "final") -> BarometerVersion | None:
    """mode="draft" — черновик вечерней сборки (status=draft, витрина не видит);
    "final" — доработка своего черновика с учётом вопросов, сверки, проверки → публикация."""
    prev_row = _prev_state(db)
    prev = prev_row.payload if prev_row and prev_row.payload else None
    parent_id = prev_row.id if prev_row else None

    inputs = gather_inputs(db)
    if not inputs.get("indicators"):
        logger.warning("macro_state: нет индикаторов — пересборка пропущена")
        return None

    # Разведка (веб, документы) — как у гео: не обязательна для публикации
    dossier = None
    try:
        from app.services import macro_scout
        dossier = macro_scout.run(db, {"snapshot": inputs["snapshot_text"][:14_000], **edges_for_scout(inputs)},
                                  prev_summary=str((prev or {}).get("summary") or ""))
    except Exception as e:  # noqa: BLE001
        logger.warning("macro_state: разведка недоступна (%s) — по данным платформы", e)

    edges = {"geo_edge": inputs["geo_edge"], "inst_edge": inputs["inst_edge"],
             "data_gaps": inputs.get("data_gaps")}
    # 🔴 Лимиты входа ужаты после боевого прогона #222: задание 176 тыс. знаков
    # (прошлая версия + досье + передачи + вопросы + противоречия + замечания),
    # 21 шаг, 916 тыс. токенов, итоговый JSON обрезался. То же лечение, что у
    # институтов (#51): вход компактнее, финал длиннее, бюджет с запасом.
    draft_row = barometer_store.today_draft(db, KIND) if mode == "final" else None
    draft = draft_row.payload if draft_row and draft_row.payload else None
    peers_full = ("\n\nПОЛНЫЕ ЧЕРНОВИКИ СОСЕДЕЙ (для цепочек через два ребра и обратных петель):\n"
                  + "\n".join(f"--- {k} ---\n" + json.dumps(v, ensure_ascii=False, default=str)[:30_000]
                              for k, v in inputs["peers"].items() if v)) if mode == "final" else ""
    task = (("ТВОЙ ЧЕРНОВИК СЕГОДНЯШНЕГО ВЕЧЕРА (доработай: ответь соседям, сними противоречия, исправь "
             "замечания, разбери цепочки — и опубликуй):\n" + json.dumps(draft, ensure_ascii=False)[:40_000] + "\n\n")
            if draft else ""
            + peers_full + "\n\n"
            + "ПРОШЛАЯ ВЕРСИЯ СОСТОЯНИЯ (обнови, не переписывай):\n"            + (json.dumps(prev, ensure_ascii=False)[:40_000] if prev else "— нет, это первая сборка: собери состояние с нуля —")
            + "\n\nДОСЬЕ РАЗВЕДКИ:\n" + (json.dumps(dossier, ensure_ascii=False)[:24_000] if dossier else "— нет —")
            + "\n\n" + handoffs.incoming_block("macro", inputs["peers"])
            + "\n\nВОПРОСЫ СОСЕДЕЙ К ТЕБЕ (ответить в answers_to_peers, с числом и источником):\n"
            + (json.dumps(inputs["peer_questions"], ensure_ascii=False) if inputs["peer_questions"] else "— нет —")
            + "\n\n" + _contradictions_block(db)
            + "\n\n" + _critique_block(db)
            + "\n\n" + _history_and_lessons(db)
            + "\n\nСВОДКИ СОСЕДЕЙ КРАТКО (для контекста; контракт выше важнее):\n"
            + json.dumps(edges, ensure_ascii=False, default=str)
            + "\n\nДАННЫЕ ПЛАТФОРМЫ (единственный источник чисел; остальное — search_feed):\n"
            + inputs["snapshot_text"][:80_000]
            + f"\n\nСегодня: {date.today().isoformat()}.")

    from app.services import analyst
    diag: list[str] = []
    try:
        fresh = analyst.run(
            db, extra_tools=_feed_schema(), extra_executor=_feed_exec,  system=_SYSTEM, task=task,
            shelf_docs=handoffs.ALL_SHELF,   # все методички, включая чужие (владелец 2026-09-13)
            # Бюджет — защита от зацикливания, не экономия (владелец 2026-09-13:
            # «пусть агент больше прочитает»). Вход ~30 тыс. токенов × до 14
            # шагов — без запаса цикл упрётся в потолок на середине.
            max_steps=16, budget=3_000_000, final_max_tokens=64_000,
            final_instruction="Верни JSON состояния строго по формату из роли, плюс methodology_used.",
            label="macro_state", notes=diag)
        if fresh is None:
            raise llm.LLMError("аналитик не вернул валидное состояние. " + " | ".join(diag)[:600])
    except llm.LLMError as e:
        return _reject(db, parent_id, [f"LLM недоступен: {e}"])

    if not isinstance(fresh, dict) or not fresh.get("blocks") or not fresh.get("diagnosis"):
        return _reject(db, parent_id, ["ответ без blocks или diagnosis"])

    fresh, notes = _gate(fresh, prev)
    if mode == "final":
        try:
            from app.services.consistency_check import contradictions_for
            from app.services.critic import critique_for
            notes += handoffs.final_gate_notes(fresh, inputs.get("peer_questions") or [],
                                               contradictions_for(db, KIND), critique_for(db, KIND))
        except Exception:  # noqa: BLE001
            pass
    from app.services.barometer_daily import compliance_ok
    ok, why = compliance_ok(fresh)
    if not ok:
        return _reject(db, parent_id, notes + [why])

    fresh.setdefault("as_of", date.today().isoformat())
    fresh["inputs_meta"] = {"geo_edge": {k: inputs["geo_edge"].get(k) for k in ("as_of", "version_id", "error") if k in inputs["geo_edge"]},
                            "inst_edge": {k: inputs["inst_edge"].get(k) for k in ("as_of", "version_id", "error") if k in inputs["inst_edge"]},
                            "indicators": len(inputs.get("indicators") or []),
                            "dossier": bool(dossier)}
    fresh["stage"] = mode
    row = BarometerVersion(kind=KIND, source="auto", status="draft" if mode == "draft" else "published",
                           payload=fresh, gate_notes=notes or None, parent_id=parent_id,
                           trigger_reason=("черновик вечерней сборки" if mode == "draft" else TRIGGER),
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("macro_state: состояние пересобрано (версия #%d, заметок гейта: %d)", row.id, len(notes))
    return row


def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)
