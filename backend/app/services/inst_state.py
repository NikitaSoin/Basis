"""Состояние институциональной среды на дату — InstState_t (методика И: Части 7–10, 12).

🔴 ЗАЧЕМ (владелец, 2026-09-13): «у институциональной среды нужно, чтобы так же
обновлялось» — ежедневно, как сводка геополитики и состояние экономики. До
сих пор институциональная сводка (kind="inst") обновлялась одним вызовом модели
раз в месяц с лишним, без методички, без разведки и без цикла инструментов.

Методика сама описывает объект (§9.1): «институциональный снимок — состояние на
дату: кто занимает должности, какие коалиции существуют, какие конфликты идут,
каково фактическое распределение ресурсов», и главный приём: «вопрос "как
события повлияли на институты" решается сравнением снимков, а не реконструкцией
государства с нуля». Здесь снимок ведётся как версии в той же таблице, что
остальные состояния (barometer_versions, kind="inst_state"); вчерашний — вход
для сегодняшнего.

ЧТО ВНУТРИ — по методике:
  sections[12]      — двенадцать разделов снимка §9.2 (А…L) + «государство и
                      бизнес» §4.11; у каждого ОТДЕЛЬНО уровень и тренд (§7.1 —
                      смешать их в один балл есть типовая ошибка), импульс,
                      сопротивление, закрепление (§7.3–7.5), статус утверждений
                      Ф/Д/В/Г (§0.7), доказательства, дельта к прошлой версии.
  drift_file        — §9.8: недавние изменения, каждое классифицировано по типу
                      (Часть 6) и механизму (Часть 5), с выигравшими/проигравшими.
  leading_signals   — §8.2: наблюдённые сигналы по десяти типам индикаторов;
                      единица наблюдения — серия, не событие.
  forecast_card     — §10.9: шестнадцать полей, 6 мес / 2 года / 5 лет,
                      вероятность и уверенность раздельно (§10.3), развилки,
                      критерии опровержения (§10.7).
  verdict           — §12.2: де-юре → де-факто по сегментам → неформальный слой →
                      трансакционные издержки → стимулы. «Среда плохая» и
                      «верховенство права = 40» — запрещённые форматы.

Прежняя институциональная сводка (kind="inst", 13 субиндексов) остаётся для
витрины как есть — витрина переключится на состояние отдельным шагом.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, handoffs, llm

logger = logging.getLogger(__name__)

KIND = "inst_state"
TRIGGER = "ежедневная пересборка состояния"
_WINDOW_DAYS = 14

SECTIONS: list[tuple[str, str]] = [
    ("constitutional", "А. Конституционная архитектура"),
    ("presidential", "Б. Президентский контур"),
    ("security", "В. Силовой контур"),
    ("legislative", "Г. Законодательный контур"),
    ("judicial", "Д. Судебный контур"),
    ("executive", "Е. Исполнительный контур"),
    ("regional", "Ж. Региональный контур"),
    ("state_business", "З. Государственный бизнес"),
    ("private_business", "I. Частный бизнес"),
    ("financial_system", "J. Финансовая система"),
    ("civil_society", "K. Гражданское общество"),
    ("media", "L. СМИ"),
    ("state_vs_business", "Отношения государства и бизнеса (§4.11)"),
]
STATUSES = {"Ф", "Д", "В", "Г"}
FORECAST_FIELDS = ["state", "regime_vector", "power_structure", "gaps", "drift", "mechanisms",
                   "state_business_equilibrium", "leading_indicators", "resistance",
                   "entrenchment", "forecast_6m", "forecast_2y", "scenarios_5y",
                   "critical_junctures", "confidence", "refutation_criteria"]
# Темы летописи с институциональным содержанием — из фиксированной таксономии
# config/chronicle_themes.json; регулярка ниже — дополнительный сетчатый фильтр
# по заголовку для записей с другими темами.
_INST_THEMES = {"nationalization", "regulation", "taxes", "budget_fiscal", "sanctions"}
_INST_THEME = re.compile(r"институт|закон|суд|назнач|отставк|регулир|собствен|госуправ|прокурат|"
                         r"деприват|национализац|коалиц|силов|губернатор|дума|правительств|цб\b|"
                         r"центробанк", re.IGNORECASE)


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

def _conflict_brief(db: Session, days: int = 28) -> str:
    """Собранные данные по очагам — короткое окно: институционалисту нужен темп, не список."""
    try:
        from app.services.feed_tools import conflict_brief_text
        return conflict_brief_text(db, days=days)
    except Exception as e:  # noqa: BLE001
        return f"СОБРАННЫЕ ДАННЫЕ ПО ОЧАГАМ: недоступны ({type(e).__name__})"


def _articles(db: Session) -> list[dict]:
    from app.models.geo_digest import GeoDigestArticle
    cutoff = date.today() - timedelta(days=_WINDOW_DAYS)      # published_at — Date, не datetime
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target == "institutions", GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(60).all())
    try:
        from app.services.feed_tools import source_label
    except ImportError:  # pragma: no cover
        source_label = lambda k: k or "источник не указан"   # noqa: E731
    return [{"id": str(a.id), "date": a.published_at.isoformat() if a.published_at else None,
             "title": a.title, "summary": (a.summary or "")[:500],
             "source": source_label(a.source_key),        # для взвешивания, не для витрины
             "takeaways": a.key_takeaways} for a in rows]


def _chronicle(db: Session) -> list[dict]:
    from app.models.chronicle import ChronicleEntry
    cutoff = datetime.now(timezone.utc) - timedelta(days=_WINDOW_DAYS)
    rows = (db.query(ChronicleEntry).filter(ChronicleEntry.published_at >= cutoff)
            .order_by(ChronicleEntry.importance.desc(), ChronicleEntry.published_at.desc()).limit(300).all())
    out = []
    for r in rows:
        themes = set(r.themes or []) if isinstance(r.themes, list) else set()
        if (themes & _INST_THEMES) or _INST_THEME.search(str(r.title or "")):
            out.append({"id": r.id, "date": r.published_at.date().isoformat() if r.published_at else None,
                        "title": r.title, "summary": (r.summary or "")[:400],
                        "interpretation": (r.interpretation or "")[:400], "importance": r.importance})
        if len(out) >= 40:
            break
    return out


def _edge(db: Session, kind: str, keys: tuple[str, ...]) -> dict:
    row = barometer_store.current_row(db, kind)
    if not row or not row.payload:
        return {"error": f"no_{kind}"}
    p = row.payload
    return {"as_of": p.get("as_of"), "version_id": row.id, **{k: p.get(k) for k in keys if k in p}}


def gather_inputs(db: Session) -> dict:
    return {
        "articles": _articles(db),
        "chronicle": _chronicle(db),
        # прежняя институциональная сводка — как якорь калибровки, не как истина
        "inst_summary_anchor": _edge(db, "inst", ("scenario", "alerts", "power_map_top_conflicts",
                                                  "institutional_crp_floor_pp")),
        # передачи из соседних контуров: геополитика → институты (ГИ), макро → институты (МИ)
        "geo_edge": _edge(db, "geo", ("scenario", "sector_flags", "watchlist_30d")),
        "macro_edge": _edge(db, "macro", ("diagnosis", "revision_triggers")),
        "peers": {k: (r.payload if (r := barometer_store.peer_view(db, k)) and r.payload else None)
                  for k in ("geo", "macro")},
        "peer_questions": _peer_questions(db, "inst_state"),
    }


def _peer_questions(db: Session, me: str) -> list[dict]:
    try:
        from app.services.cross_review import questions_for
        return questions_for(db, me)
    except Exception:  # noqa: BLE001
        return []


# ─────────────────────────── гейт ───────────────────────────

def _index_by_key(items: list, schema: list[tuple[str, str]], notes: list[str]) -> dict:
    """{ключ схемы: раздел}. Ключ модели сверяется точно, затем по названию.

    🔴 Первый прогон снимка: модель вернула тринадцать разделов под СВОИМИ
    ключами («А», «Конституционная архитектура»…), точного совпадения не было,
    и гейт молча заменил одиннадцать из них пустыми заготовками — работа модели
    выброшена, а в базу ушла пустота с пометкой «нет данных». Теперь чужой ключ
    сначала пытаемся узнать по названию, и только потом — заготовка."""
    out: dict = {}
    titles = {k: t.lower() for k, t in schema}
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get("key") or "").strip()
        if key in titles:
            out[key] = it; continue
        probe = (key + " " + str(it.get("title") or "")).lower()
        # отличительное слово — первое после буквы раздела: «Силовой», «Судебный»,
        # «Частный»; общие слова («контур», «бизнес») в сопоставлении не участвуют
        def _distinct(t: str) -> str:
            body = t.split(".", 1)[-1].strip() if "." in t[:3] else t
            return body.split()[0].lower().rstrip(",")
        match = next((k for k, t in titles.items()
                      if t.split(".")[0].strip() == key.upper()          # «А» → «А. …»
                      or _distinct(t) in probe), None)
        if match and match not in out:
            it["key"] = match; out[match] = it
            notes.append(f"{match}: ключ модели «{key}» узнан по названию")
        else:
            notes.append(f"раздел «{key or it.get('title')}» не сопоставлен со схемой — оставлен в extra_sections")
            out.setdefault("_extra", []).append(it)
    return out

def _gate(fresh: dict, prev: dict | None) -> tuple[dict, list[str]]:
    notes: list[str] = []
    prev_secs = {s.get("key"): s for s in ((prev or {}).get("sections") or []) if isinstance(s, dict)}
    have = _index_by_key(fresh.get("sections") or [], SECTIONS, notes)
    rebuilt = []
    for key, title in SECTIONS:
        s = have.get(key)
        if s is None and key in prev_secs:
            s = dict(prev_secs[key]); s["carried_over"] = True
            notes.append(f"{key}: раздел не вернулся — перенесён с прошлой версии")
        if s is None:
            s = {"key": key, "title": title, "level": None, "trend": None, "status": "Г",
                 "data_flag": "нет данных в этом прогоне"}
            notes.append(f"{key}: раздела нет ни сейчас, ни раньше — пустая заготовка")
        s.setdefault("key", key); s.setdefault("title", title)
        # §7.1: уровень и тренд — разные переменные, оба обязаны быть
        if s.get("level") and not s.get("trend"):
            notes.append(f"{key}: есть уровень, нет тренда — §7.1 требует оба раздельно")
        # §0.7: статус утверждения
        if s.get("status") not in STATUSES:
            s["status"] = "Г"; notes.append(f"{key}: статус утверждения не Ф/Д/В/Г → «Г» (гипотеза)")
        # изменение уровня без обоснования — откат
        p = prev_secs.get(key)
        if p and s.get("level") != p.get("level") and len(str(s.get("delta_rationale") or "")) < 20:
            s["level"] = p.get("level"); s["delta_rationale"] = None
            notes.append(f"{key}: уровень изменён без обоснования → откат")
        rebuilt.append(s)
    fresh["sections"] = rebuilt
    if have.get("_extra"):
        fresh["extra_sections"] = have["_extra"]

    card = fresh.get("forecast_card") or {}
    missing = [f for f in FORECAST_FIELDS if not str(card.get(f) or "").strip()]
    if missing:
        notes.append(f"forecast_card: пустые поля {missing} (§10.9 — шестнадцать полей)")
    if not card.get("refutation_criteria"):
        notes.append("forecast_card.refutation_criteria: пусто — прогноз непроверяем (§10.7)")
    # §10.3: вероятность и уверенность раздельно
    if isinstance(card.get("scenarios_5y"), list):
        for sc in card["scenarios_5y"]:
            if isinstance(sc, dict) and "probability" in sc and "confidence" not in sc:
                notes.append("scenarios_5y: у сценария есть вероятность, но нет уверенности (§10.3)")
                break
    # §12.2: запрещённые форматы вердикта
    verdict = str(fresh.get("verdict") or "")
    if re.search(r"среда (плохая|хорошая)|верховенств\w+ права\s*=\s*\d", verdict, re.IGNORECASE):
        notes.append("verdict: запрещённый формат §12.2 («среда плохая», «право = N»)")
    if len(verdict) < 300:
        notes.append("verdict: короче 300 знаков — эталон §12.2 требует цепочку де-юре → де-факто → стимулы")
    # серия, не событие (§8.2): сигнал из одного наблюдения помечаем
    for sig in fresh.get("leading_signals") or []:
        if isinstance(sig, dict) and isinstance(sig.get("observations"), list) and len(sig["observations"]) < 2:
            notes.append(f"leading_signals[{sig.get('type')}]: одно наблюдение — не серия (§8.2)")
    # контракты передач соседям (пункт 3)
    notes += handoffs.gate_notes(fresh, "inst_state")
    # язык и цифры (владелец 2026-09-13)
    digits = re.compile(r"\d")
    if len(digits.findall(str(fresh.get("summary") or ""))) < 3:
        notes.append("summary: меньше трёх чисел/дат — вывод без конкретики")
    banned = re.compile(r"окно возможност|навес|турбулентн|тектоническ", re.IGNORECASE)
    hit = banned.search(json.dumps(fresh, ensure_ascii=False))
    if hit:
        notes.append(f"язык: оборот «{hit.group(0)}» — переформулировать понятными словами")
    return fresh, notes


def _reject(db: Session, parent_id: int | None, why: list[str]) -> BarometerVersion:
    row = BarometerVersion(kind=KIND, source="auto", status="rejected", payload=None,
                           gate_notes=why, parent_id=parent_id, trigger_reason=TRIGGER)
    db.add(row); db.commit(); db.refresh(row)
    logger.warning("inst_state: версия отклонена: %s", " | ".join(why)[:400])
    return row


# ─────────────────────────── сборка ───────────────────────────

def _protocol_core() -> str:
    """Операционный протокол владельца (поведение + регулярный снимок). Мягко."""
    try:
        from app.services.protocol_core import STATE_PARTS, core_text
        return core_text(STATE_PARTS) + "\n"
    except Exception:  # noqa: BLE001
        return ""


def _screen_spec() -> str:
    """Форма экрана «Оценка ситуации» условий для бизнеса (спецификация владельца, 2026-09-18):
    карточки изменений, серии, шесть измерений, ветви — поле screen снимка. Мягко: модуль новый,
    Timeweb выкатывает файлы неравномерно."""
    try:
        from app.services.inst_screen import INST_SCREEN_SPEC
        return INST_SCREEN_SPEC
    except Exception:  # noqa: BLE001
        return ""


def _screen_gate(fresh: dict, prev: dict | None) -> list[str]:
    try:
        from app.services.inst_screen import inst_screen_gate
        return inst_screen_gate(fresh, prev)
    except Exception:  # noqa: BLE001
        logger.warning("inst_state: гейт экрана не отработал", exc_info=True)
        return []


def _screen_task_blocks(db: Session, prev: dict | None, peers: dict | None) -> str:
    """Прошлый экран кратко (id карточек, серии, стрелки, ветви) + ветви геополитика, к которым
    привязываются ветви условий для бизнеса (спецификация, Часть 4.2)."""
    try:
        from app.services.inst_screen import geo_branches_block, prev_screen_block
        return prev_screen_block(prev) + "\n\n" + geo_branches_block(db, peers)
    except Exception:  # noqa: BLE001
        logger.warning("inst_state: блоки экрана в задание не собраны", exc_info=True)
        return ""


_SYSTEM = (
    _protocol_core() +
    "Ты — институциональный аналитик Basis (независимая аналитика для частного "
    "инвестора в РФ). Твоя работа — не текст, а ИНСТИТУЦИОНАЛЬНЫЙ СНИМОК страны на "
    "дату, который ты поддерживаешь и обновляешь: сравнением снимков, а не "
    "реконструкцией государства с нуля (методика inst_env §9.1). Объект — Россия.\n\n"
    "Порядок работы — протокол inst_env §12.1 (двадцать шагов: дата → снимок → "
    "режим → карта силы → государство–бизнес → разрывы формальное/фактическое → "
    "недавние изменения → тип и механизм каждого → выигравшие/проигравшие → "
    "индикаторы → прогноз). Правила доказательности — Общий кодекс (code): открой "
    "его первым. Ключевые требования методики, которые проверит гейт:\n"
    "• §7.1 — уровень и тренд ОТДЕЛЬНО: «низкий, но улучшается» и «высокий, но "
    "деградирует» — разные объекты;\n"
    "• §0.7 — у каждого утверждения статус Ф (формальное) / Д (фактическое) / В "
    "(выводимое) / Г (гипотеза); закрытые структуры — «неизвестно», не догадка;\n"
    "• §8.2 — единица наблюдения СЕРИЯ, не событие: одно назначение ничего не "
    "значит, серия однотипных — сигнал;\n"
    "• §10.3 — вероятность и уверенность раздельно; §10.7 — критерии опровержения;\n"
    "• §12.2 — вердикт строится: де-юре → де-факто по сегментам → неформальный "
    "слой → трансакционные издержки → стимулы. «Среда плохая» и «право = 40» — "
    "запрещённые форматы.\n\n"
    "🔴 ЯЗЫК: обычные слова и конкретика — даты, названия органов, номера законов, "
    "имена должностей, числа. Без эпитетов и метафор. Каждое изменение: было → "
    "стало → когда → источник.\n\n"
    "У тебя есть ПРОШЛЫЙ снимок. Обнови его: по каждому разделу — что изменилось "
    "и почему (delta_rationale), что не изменилось — оставь. Изменение уровня без "
    "обоснования откатится.\n\n"
    "ФОРМАТ (строго JSON): {\n"
    "  \"as_of\": \"YYYY-MM-DD\",\n"
    "  \"regime\": {\"type\", \"subtype\", \"vector\", \"ruling_coalition\", \"status\"},\n"
    "  \"sections\": [ {\"key\": <РОВНО один из: " + ", ".join(k for k, _ in SECTIONS) + ">, "
    "\"title\": <соответственно: " + "; ".join(f"{k} = {t}" for k, t in SECTIONS) + ">, "
    "\"level\": <словами, с "
    "фактами>, \"trend\": <улучшается|стабильно|деградирует + чем измерено>, "
    "\"impulse\", \"resistance\", \"entrenchment\", \"formal_vs_actual_gap\", "
    "\"status\": <Ф|Д|В|Г>, \"evidence\": [{\"what\", \"date\", \"source\"}], "
    "\"delta_vs_prev\", \"delta_rationale\": <≥20 знаков>} ],\n"
    "  \"drift_file\": [ {\"change\", \"date\", \"type\": <дрейф|наслоение|перепрофилирование|"
    "вытеснение|эрозия|восстановление|развилка>, \"mechanism\", \"winners\", \"losers\", "
    "\"status\", \"source\"} ],\n"
    "  \"leading_signals\": [ {\"type\": <один из десяти §8.2>, \"observations\": [..≥2..], "
    "\"reading\", \"status\"} ],\n"
    "  \"forecast_card\": { " + ", ".join(f"\"{f}\"" for f in FORECAST_FIELDS) + " },\n"
    "  \"verdict\": <абзац по эталону §12.2>,\n"
    "  \"summary\": <главное одним абзацем, с датами и фактами>,\n"
    "  \"handoffs\": {\"to_macro\": {..}, \"to_geo\": {..}} — см. блок ПЕРЕДАЧИ СОСЕДЯМ ниже,\n"
    "  \"answers_to_peers\": [ {\"from\", \"question\", \"answer\", \"evidence\"} ] — ответы на "
    "вопросы соседей из задания (обязательно, с фактом и источником),\n"
    "  \"questions_to_peers\": [ {\"to\": <geo|macro>, \"question\", \"why_it_matters\"} ],\n"
    "  \"shocks_from_geo\", \"inputs_from_macro\", \"methodology_used\": [..], "
    "\"sources\": [..], \"data_flags\": [..]\n}"
    + "  " + handoffs.FINAL_FIELDS + "\n"
    + handoffs.prompt_block("inst_state")
    + handoffs.CHAINS_RULE
    # 🔴 Мандат старшего аналитика (владелец 2026-09-13). Мягко: файл handoffs может
    # доехать позже.
    + getattr(handoffs, "mandate_block", lambda c: "")("inst_state")
    # 🔴 Экран «Оценка ситуации» условий для бизнеса (владелец, 2026-09-18): карточки
    # изменений с осязаемыми следствиями, серии, шесть измерений, ветви — поле screen.
    + _screen_spec()
)



def _contradictions_block(db: Session) -> str:
    """Противоречия, найденные сверкой, в которых участвует эта сводка (пункт 3):
    обязана либо снять, либо объяснить, почему права она."""
    try:
        from app.services.consistency_check import contradictions_for
        cs = contradictions_for(db, "inst_state")
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
        vs = critique_for(db, "inst_state")
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
        parts.append(_hist(db, "inst_state", limit=10))
    except Exception:  # noqa: BLE001
        pass
    try:
        from app.services.lessons import for_prompt as _less
        parts.append(_less(db, "inst_state"))
    except Exception:  # noqa: BLE001
        pass
    return "\n\n".join(parts)

def rebuild(db: Session, mode: str = "final") -> BarometerVersion | None:
    """mode="draft" — черновик вечерней сборки (status=draft, витрина не видит);
    "final" — доработка своего черновика с учётом вопросов, сверки, проверки → публикация."""
    prev_row = barometer_store.current_row(db, KIND)
    prev = prev_row.payload if prev_row and prev_row.payload else None
    parent_id = prev_row.id if prev_row else None

    inputs = gather_inputs(db)
    if not inputs["articles"] and not inputs["chronicle"]:
        logger.warning("inst_state: за %d дней ни статей, ни записей летописи — пропуск", _WINDOW_DAYS)
        return None

    dossier = None
    try:
        from app.services import scout
        dossier = scout.run(
            db, kind="inst_dossier",   # ≤16 символов — ложится в barometer_versions.kind
            system=("Ты — разведчик институционального аналитика Basis. Собери досье: "
                    "новые законы и поправки, назначения и отставки (сериями, не поодиночке), "
                    "судебные решения с прецедентным значением, изъятия и передачи собственности, "
                    "перераспределение полномочий между органами, новые организации. По каждому "
                    "пункту — дата, орган, источник. Чего не нашёл — в пробелы, честно."),
            task=("СЕГОДНЯ: " + date.today().isoformat()
                  + "\n\nПРОШЛЫЙ СНИМОК (ищи изменения, не пересказ): " + str((prev or {}).get("summary") or "—")[:1500]
                  + "\n\nСТАТЬИ ЛЕНТЫ:\n" + json.dumps(inputs["articles"][:30], ensure_ascii=False)[:12000]
                  + "\n\nЛЕТОПИСЬ:\n" + json.dumps(inputs["chronicle"][:25], ensure_ascii=False)[:8000]),
            shelf_docs=handoffs.ALL_SHELF,   # все методички, включая чужие (владелец 2026-09-13)
            max_steps=12, web_call_cap=8, trigger_reason="разведка перед институциональным снимком")
    except Exception as e:  # noqa: BLE001
        logger.warning("inst_state: разведка недоступна (%s) — по ленте", e)

    draft_row = barometer_store.today_draft(db, KIND) if mode == "final" else None
    draft = draft_row.payload if draft_row and draft_row.payload else None
    peers_full = ("\n\nПОЛНЫЕ ЧЕРНОВИКИ СОСЕДЕЙ (для цепочек через два ребра и обратных петель):\n"
                  + "\n".join(f"--- {k} ---\n" + json.dumps(v, ensure_ascii=False, default=str)[:30_000]
                              for k, v in inputs["peers"].items() if v)) if mode == "final" else ""
    # 🔴 Раньше здесь был тернарный оператор `X if draft else "" + всё_остальное`:
    # при наличии черновика задание финала состояло из ОДНОГО черновика — без
    # соседей, вопросов, противоречий, замечаний и уроков (приоритет `if/else`
    # ниже, чем у `+`). Нашлось на первом локальном прогоне вечерней сборки.
    draft_txt = (("ТВОЙ ЧЕРНОВИК СЕГОДНЯШНЕГО ВЕЧЕРА (доработай: ответь соседям, сними противоречия, исправь "
                  "замечания, разбери цепочки — и опубликуй):\n" + json.dumps(draft, ensure_ascii=False)[:56_000] + "\n\n")
                 if draft else "")
    if draft_row is not None and draft_row.gate_notes:
        draft_txt += ("ЗАМЕЧАНИЯ АВТОМАТИЧЕСКОЙ ПРОВЕРКИ К ЧЕРНОВИКУ (исправить в финале, иначе публикация "
                      "не пройдёт):\n" + json.dumps(draft_row.gate_notes, ensure_ascii=False) + "\n\n")
    task = (draft_txt
            + peers_full + "\n\n"
            + "ПРОШЛЫЙ СНИМОК (обнови, не переписывай; его экран screen дан ниже кратко):\n"            # 🔴 Лимиты входа ужаты после прогона #51: задание разрослось до 159 тыс.
            # знаков (прошлый снимок + досье + передачи + вопросы + противоречия),
            # 23 шага, 934 тыс. токенов — и итоговый JSON обрезался на середине.
            # Экран (screen) из прошлого снимка вырезан из дампа — он идёт кратким блоком ниже,
            # иначе карточки съедали бы весь лимит и обрезали снимок.
            + (json.dumps({k: v for k, v in prev.items() if k != "screen"}, ensure_ascii=False)[:40_000]
               if prev else "— нет, это первая сборка: собери снимок с нуля по §12.1 —")
            + "\n\n" + _screen_task_blocks(db, prev, inputs["peers"])
            + "\n\nДОСЬЕ РАЗВЕДКИ:\n" + (json.dumps(dossier, ensure_ascii=False)[:24_000] if dossier else "— нет —")
            + "\n\n" + handoffs.incoming_block("inst_state", inputs["peers"])
            + "\n\nВОПРОСЫ СОСЕДЕЙ К ТЕБЕ (ответить в answers_to_peers, с фактом и источником):\n"
            + (json.dumps(inputs["peer_questions"], ensure_ascii=False) if inputs["peer_questions"] else "— нет —")
            + "\n\n" + _contradictions_block(db)
            + "\n\n" + _critique_block(db)
            + "\n\n" + _history_and_lessons(db)
            + "\n\nСВОДКИ СОСЕДЕЙ КРАТКО и прежняя институциональная сводка как якорь:\n"
            + json.dumps({k: inputs[k] for k in ("geo_edge", "macro_edge", "inst_summary_anchor")}, ensure_ascii=False, default=str)
            + "\n\nСТАТЬИ ЛЕНТЫ ЗА 14 ДНЕЙ (остальное — search_feed):\n" + json.dumps(inputs["articles"][:30], ensure_ascii=False)[:20_000]
            + "\n\nЛЕТОПИСЬ (важное за 14 дней):\n" + json.dumps(inputs["chronicle"][:30], ensure_ascii=False)[:14_000]
            + "\n\n" + _conflict_brief(db)
            + f"\n\nСегодня: {date.today().isoformat()}.")

    from app.services import analyst
    diag: list[str] = []
    try:
        fresh = analyst.run(
            db, extra_tools=_feed_schema(), extra_executor=_feed_exec,  system=_SYSTEM, task=task,
            shelf_docs=handoffs.ALL_SHELF,   # все методички, включая чужие (владелец 2026-09-13)
            # Методика институтов — 164 раздела и протокол из двадцати шагов:
            # агенту нужно больше ходов, чем макро (первый прогон: 29 вызовов
            # инструментов за 14 шагов). Бюджет 900 тыс. на 20 шагов хватает.
            # Финал снимка с передачами и ответами соседям длиннее 28 тыс. токенов —
            # #51 обрезался на середине JSON. Бюджет — с запасом на 20 шагов.
            max_steps=20, budget=3_000_000, final_max_tokens=64_000,
            final_instruction="Верни JSON снимка строго по формату из роли, включая поле screen "
                              "(экран оценки ситуации условий для бизнеса), плюс methodology_used.",
            label="inst_state", notes=diag)
        if fresh is None:
            raise llm.LLMError("аналитик не вернул валидный снимок. " + " | ".join(diag)[:600])
    except llm.LLMError as e:
        return _reject(db, parent_id, [f"LLM недоступен: {e}"])

    if not isinstance(fresh, dict) or not fresh.get("sections") or not fresh.get("forecast_card"):
        return _reject(db, parent_id, ["ответ без sections или forecast_card"])

    fresh, notes = _gate(fresh, prev)
    notes += _screen_gate(fresh, prev)
    notes += getattr(handoffs, "situation_gate_notes", lambda *_: [])(fresh, KIND)
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
        if mode != "draft":
            return _reject(db, parent_id, notes + [why])
        # черновик витрина не видит; отклонить его — значит оставить вечернюю сборку
        # без этой сводки целиком (так и случилось на первом прогоне: «продать» в
        # тексте про вынужденную продажу активов). Сохраняем с замечанием — финал обязан
        # убрать формулировку, там проверка строгая.
        notes = notes + [f"КОМПЛАЕНС (черновик): {why} — переформулировать в финале"]

    fresh.setdefault("as_of", date.today().isoformat())
    fresh["inputs_meta"] = {k: {kk: inputs[k].get(kk) for kk in ("as_of", "version_id", "error") if kk in inputs[k]}
                            for k in ("geo_edge", "macro_edge", "inst_summary_anchor")}
    fresh["inputs_meta"]["articles"] = len(inputs["articles"]); fresh["inputs_meta"]["chronicle"] = len(inputs["chronicle"])
    fresh["inputs_meta"]["dossier"] = bool(dossier)
    fresh["stage"] = mode
    row = BarometerVersion(kind=KIND, source="auto", status="draft" if mode == "draft" else "published",
                           payload=fresh, gate_notes=notes or None, parent_id=parent_id,
                           trigger_reason=("черновик вечерней сборки" if mode == "draft" else TRIGGER),
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("inst_state: снимок пересобран (версия #%d, заметок гейта: %d)", row.id, len(notes))
    if mode != "draft":
        try:
            from app.services.forecast_journal import record
            record(db, "inst_state", fresh, row.id)
        except Exception as e:  # noqa: BLE001
            logger.warning("forecast_journal(%s): %s", KIND, e)
    return row


def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)
