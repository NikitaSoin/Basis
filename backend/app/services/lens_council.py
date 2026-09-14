"""Совет агентов-методичек: каждая методичка — отдельный агент, оркестратор и сведение.

🔴 ЗАЧЕМ (владелец, 2026-09-14). Один аналитик с полкой из 14 методичек открывает за
прогон 6–8 разделов из ~1 400 — «читает пять процентов базы». Модель не применяет
теорию, которую «и так знает», пока рамка не лежит у неё перед глазами в момент
ответа. Решение владельца — декомпозиция: «оркестратор и множество агентов, каждая
методичка — отдельный агент; задание отдаётся каждому, чтобы он посмотрел со своей
перспективы; набор ответов дополняет друг друга, потому что базово они мыслили
по-разному». На самых мощных моделях, реже по расписанию.

Как устроено:
  1. АГЕНТ-МЕТОДИЧКА (lens). Системное задание = роль + ПОЛНЫЙ текст его методички +
     общий кодекс + форма ответа. Всё это статично и одинаково от вызова к вызову —
     DeepSeek держит 1M контекста и кэширует одинаковый префикс (повторное чтение в
     ~30 раз дешевле первого), поэтому методичка целиком в контексте — это дёшево.
     Динамика (задача, пачка данных) — только в пользовательском сообщении.
     Инструменты: поиск по потоку платформы, данные по очагам, прошлые сводки, веб
     с потолком. Ответ короткий и фиксированной формы: иначе проблема «не проглотить»
     переезжает к тому, кто сводит.
  2. ОРКЕСТРАТОР. Одна и та же задача и одна и та же пачка фактов — всем агентам;
     параллельно небольшими волнами; затем ОДИН круг вопросов между агентами (агент
     ГМ спросил у ИМ про льготный кредит — ИМ ответил).
  3. СВЕДЕНИЕ. Самая сильная модель с рассуждением, по схеме, а не пересказом: где
     согласны, где спорят и кто прав по доказательствам, какие цепочки складываются
     через несколько взглядов, что неизвестно. Разногласия сохраняются, не усредняются.
  4. Результат — версия kind="council" (история хранится), чтение —
     /api/market/council?format=md. Экзамен (probe_questions) умеет режим "council"
     для сравнения с одним аналитиком тем же экзаменатором.

Методички при этом не трогаются: агент = документ + роль; поменяли документ —
поменялся агент. Старый прикладной документ `geo` (третий словарь каналов) в совете
не участвует.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, llm, methodology

logger = logging.getLogger(__name__)

KIND = "council"

# Агенты совета — id методичек с полки. Кодекс входит в каждого; старый `geo` исключён.
LENSES: list[str] = ["geo_base", "geo_events", "geo_macro", "macro_geo", "geo_inst", "inst_geo",
                     "inst_env", "inst_macro", "macro_inst", "macro_base", "macro", "macro_sector"]
CONTOUR_OF: dict[str, str] = {
    "geo_base": "геополитика", "geo_events": "геополитика", "inst_env": "институты",
    "macro_base": "экономика", "macro": "экономика", "macro_sector": "экономика",
    "geo_macro": "связка геополитика → экономика", "macro_geo": "связка экономика → геополитика",
    "geo_inst": "связка геополитика → институты", "inst_geo": "связка институты → геополитика",
    "inst_macro": "связка институты → экономика", "macro_inst": "связка экономика → институты",
}

_DOC_MAX_CHARS = 220_000     # inst_env — 184k знаков; предохранитель от случайного гиганта
_PARALLEL = 3                # волна параллельных вызовов LLM (один релей, одно ядро на бою)
_ANSWER_MAX_TOKENS = 16_000
_SYNTH_MAX_TOKENS = 32_000


# ─────────────────────────── тексты методичек ───────────────────────────

def _doc_text(doc_id: str) -> str:
    doc = methodology.REGISTRY.get(doc_id)
    if not doc:
        return ""
    text = methodology._read_file(doc) or ""
    if len(text) > _DOC_MAX_CHARS:
        text = text[:_DOC_MAX_CHARS] + "\n\n[… методичка обрезана предохранителем длины …]"
    return text


_LENS_FORM = """
===== ФОРМА ОТВЕТА (строго JSON, по-русски; коротко — до ~1 200 слов суммарно) =====
{
  "lens": "<id методички>",
  "sees": "<что происходит, если смотреть ТОЛЬКО через эту методичку: 5–10 предложений с датами и числами из данных>",
  "mechanisms": [ {"name": "<механизм/канал по методичке>", "section": "<doc:раздел>",
                   "chain": "<событие → звено → звено → результат>", "status": "Ф|Д|В|Г",
                   "evidence": "<факт с датой/источником или «данных нет»>"} ],
  "watch": ["<что наблюдать по методичке, конкретный признак>", ...],
  "forecast": {"most_likely": "<...>", "most_dangerous": "<...>",
               "probabilities": [ {"outcome": "<...>", "p": <0..1>, "horizon": "<6 мес|18 мес|...>", "basis": "<...>"} ],
               "triggers": ["<что изменит картину>", ...]},
  "blind_spots": "<чего эта методичка НЕ видит в этой задаче — честно>",
  "questions_to": [ {"lens": "<id другой методички>", "question": "<...>"} ],
  "sections_used": ["<doc:раздел>", ...],
  "data_gaps": ["<искал там-то, не нашёл>", ...]
}
"""

_LENS_RULES = """
===== КАК ТЫ РАБОТАЕШЬ =====
🔴 Операционный протокол выше описывает работу СОВЕТА целиком (три контура всегда, маршрут, второй и
третий порядок): твоя доля в нём — ОДНА методичка; переводы в соседние контуры делают другие агенты, а
картину собирает сведение. Оптика лица, принимающего решения (восемь вопросов) и девять правил —
обязательны и для тебя.
🔴 Ты смотришь на задачу ТОЛЬКО через свою методичку — она лежит выше целиком. Не пересказывай её:
применяй к сегодняшним фактам из пачки данных и инструментов. Каждый механизм — с номером раздела.
🔴 Чего методичка не видит — скажи прямо в blind_spots. Это не слабость, это разделение труда:
другие агенты смотрят через другие методички, сведение соберёт картину.
🔴 Данные: сначала пачка в задании, затем инструменты (search_feed, conflict_data, read_state_version),
веб — только если не нашёл в нашем потоке, не больше нескольких запросов. Числа — только с источником;
нет данных — «данных нет», без правдоподобных реконструкций.
🔴 Статус каждого утверждения Ф/Д/В/Г (кодекс 0.5). Вероятность: в JSON число, по таблице
«крайне маловероятно» ≤0,05; «маловероятно» 0,05–0,20; «возможно» 0,20–0,45; «скорее да» 0,45–0,70;
«вероятно» 0,70–0,90; «почти наверняка» >0,90.
🔴 Язык — обычный, без жаргона и эпитетов; юридические рамки платформы: нейтральный тон,
РФ-топонимика («перешёл под контроль», не «оккупирован»), без «купить/продать/рекомендуем».
Ответ — короткий и по форме: его читает не человек, а сведение вместе с ответами 11 коллег.
"""


def lens_system(doc_id: str) -> str:
    """Статичное системное задание агента-методички: роль + методичка целиком + кодекс + форма.
    Ничего динамического здесь быть не должно — иначе префикс не кэшируется."""
    doc = methodology.REGISTRY.get(doc_id)
    title = doc.title if doc else doc_id
    contour = CONTOUR_OF.get(doc_id, "")
    head = (f"Ты — агент-методичка Basis «{title}» (контур: {contour}; id={doc_id}). Basis — независимая "
            "аналитика для частного инвестора в РФ. Ты один из двенадцати агентов совета: у каждого своя "
            "методичка, и на любую задачу совет смотрит двенадцатью разными способами, а потом сводит. "
            "Твоя работа — увидеть в задаче ровно то, что позволяет увидеть ТВОЯ методичка, и сказать это "
            "конкретно, с механизмами и разделами.\n\n")
    code = _doc_text("code")
    return (head + _protocol() + f"\n===== ТВОЯ МЕТОДИЧКА (целиком): {title} =====\n" + _doc_text(doc_id)
            + "\n\n===== ОБЩИЙ КОДЕКС АНАЛИЗА (правила доказательности, обязателен для всех) =====\n"
            + code + _LENS_RULES + _LENS_FORM)


def _protocol(parts=None) -> str:
    """Операционный протокол владельца — общее ядро (мягко: файл может отсутствовать)."""
    try:
        from app.services.protocol_core import core_text
        return core_text(parts)
    except Exception:  # noqa: BLE001
        return ""


# ─────────────────────────── пачка данных ───────────────────────────

def build_packet(db: Session) -> str:
    """Одна и та же пачка фактов для всех агентов: опубликованные сводки трёх сред,
    собранные данные по очагам, летопись за две недели. Без неё агенты-связки теоретизируют."""
    parts: list[str] = []
    try:
        from app.services.probe_questions import states_context
        parts.append(states_context(db))
    except Exception as e:  # noqa: BLE001
        parts.append(f"СВОДКИ СРЕД: недоступны ({type(e).__name__})")
    try:
        from app.services.feed_tools import conflict_brief_text
        parts.append(conflict_brief_text(db, days=56))
    except Exception as e:  # noqa: BLE001
        parts.append(f"СОБРАННЫЕ ДАННЫЕ ПО ОЧАГАМ: недоступны ({type(e).__name__})")
    try:
        from datetime import timedelta
        from app.models.chronicle import ChronicleEntry
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        rows = (db.query(ChronicleEntry).filter(ChronicleEntry.published_at >= cutoff)
                .order_by(ChronicleEntry.importance.desc(), ChronicleEntry.published_at.desc()).limit(40).all())
        items = [{"date": r.published_at.date().isoformat() if r.published_at else None, "title": r.title,
                  "summary": (r.summary or "")[:220], "themes": r.themes} for r in rows]
        parts.append("ЛЕТОПИСЬ (важное за 14 дней; полный текст — read_feed_item('chronicle', id); остальное — search_feed):\n"
                     + json.dumps(items, ensure_ascii=False)[:14_000])
    except Exception as e:  # noqa: BLE001
        parts.append(f"ЛЕТОПИСЬ: недоступна ({type(e).__name__})")
    parts.append(f"СЕГОДНЯ: {date.today().isoformat()}")
    return "\n\n".join(parts)


# ─────────────────────────── инструменты ───────────────────────────

def _tools() -> tuple[list[dict], callable]:
    tools: list[dict] = []
    try:
        from app.services.feed_tools import FEED_TOOLS_SCHEMA
        tools += list(FEED_TOOLS_SCHEMA)
    except ImportError:  # pragma: no cover
        pass
    try:
        from app.services.agent_tools import WEB_TOOLS_SCHEMA
        tools += list(WEB_TOOLS_SCHEMA)
    except ImportError:  # pragma: no cover
        pass

    def _exec(_db, name, args):
        try:
            from app.services.feed_tools import execute as feed_exec
            got = feed_exec(_db, name, args)
            if got is not None:
                return got
        except ImportError:  # pragma: no cover
            pass
        if name in ("web_search", "fetch_document"):
            from app.services.agent_tools import execute_tool
            return execute_tool(_db, name, args, "")
        return {"error": "unknown_tool", "note": name}
    return tools, _exec


# ─────────────────────────── агент-методичка ───────────────────────────

def run_lens(db: Session, doc_id: str, task: str, packet: str, *, questions: list[dict] | None = None,
             notes: list[str] | None = None) -> dict | None:
    """Один агент-методичка на одну задачу. questions — вопросы коллег (второй круг):
    тогда ответ короче и только по вопросам."""
    from app.services.agent_runner import run_agent
    tools, executor = _tools()
    if questions:
        user = ("ЗАДАЧА СОВЕТА (для контекста):\n" + task
                + "\n\nВОПРОСЫ КОЛЛЕГ К ТЕБЕ (ответь ТОЛЬКО на них, по своей методичке, с разделами и фактами):\n"
                + json.dumps(questions, ensure_ascii=False)
                + "\n\nПАЧКА ДАННЫХ (та же):\n" + packet[:40_000]
                + "\n\nФОРМА: {\"lens\": \"<id>\", \"answers\": [ {\"to\": \"<id коллеги>\", \"question\": \"...\", "
                  "\"answer\": \"<с разделом и фактом>\", \"status\": \"Ф|Д|В|Г\"} ]}")
        max_steps, final_tokens, cap = 4, 6_000, 1
    else:
        user = ("ЗАДАЧА СОВЕТА:\n" + task + "\n\nПАЧКА ДАННЫХ (одна на всех агентов):\n" + packet
                + "\n\nОтветь по форме из роли. Помни: только через свою методичку; blind_spots обязательны.")
        max_steps, final_tokens, cap = 8, _ANSWER_MAX_TOKENS, 3
    t0 = time.monotonic()
    try:
        out = run_agent(db, system_prompt=lens_system(doc_id), task=user, tools_schema=tools,
                        allowed_ticker="", max_steps=max_steps, max_tokens_total=1_500_000,
                        web_call_cap=cap, executor=executor, step_max_tokens=12_000,
                        final_max_tokens=final_tokens,
                        final_instruction="Верни JSON строго по форме из роли.",
                        model=llm.pro_model(), thinking=True, effort=getattr(llm, "ANALYST_EFFORT", "max"))
    except Exception as e:  # noqa: BLE001
        logger.warning("council[%s]: прогон упал (%s)", doc_id, e)
        if notes is not None:
            notes.append(f"{doc_id}: упал — {type(e).__name__}: {str(e)[:160]}")
        return None
    res = out.get("result")
    took = round(time.monotonic() - t0, 1)
    if notes is not None:
        notes.append(f"{doc_id}: шагов {len(out.get('trace') or [])}, токенов {out.get('tokens_used')}, "
                     f"{took} с, остановка {out.get('stopped_reason')}")
    if not isinstance(res, dict):
        logger.warning("council[%s]: JSON не получен (%s)", doc_id, out.get("stopped_reason"))
        return None
    res.setdefault("lens", doc_id)
    res["_meta"] = {"seconds": took, "tokens": out.get("tokens_used"), "steps": len(out.get("trace") or [])}
    return res


def _run_lens_own_session(doc_id: str, task: str, packet: str, questions=None) -> tuple[str, dict | None, list[str]]:
    """Для параллельной волны: каждому потоку — своя сессия БД."""
    from app.db.session import SessionLocal
    notes: list[str] = []
    db = SessionLocal()
    try:
        return doc_id, run_lens(db, doc_id, task, packet, questions=questions, notes=notes), notes
    finally:
        db.close()


# ─────────────────────────── круг вопросов ───────────────────────────

def route_questions(results: dict[str, dict], max_per_lens: int = 3) -> dict[str, list[dict]]:
    """Вопросы агентов друг к другу → по адресатам (не больше max_per_lens на адресата)."""
    inbox: dict[str, list[dict]] = {}
    for src, res in results.items():
        for q in (res or {}).get("questions_to") or []:
            if not isinstance(q, dict):
                continue
            to = str(q.get("lens") or "").strip()
            if to in LENSES and to != src and q.get("question") and len(inbox.get(to, [])) < max_per_lens:
                inbox.setdefault(to, []).append({"from": src, "question": str(q["question"])[:400]})
    return inbox


# ─────────────────────────── сведение ───────────────────────────

_SYNTH_SYSTEM = (
    "Ты — сведение совета Basis (независимая аналитика для частного инвестора в РФ). Двенадцать "
    "агентов посмотрели на одну задачу каждый через свою методичку (три базовые: геополитика, "
    "экономика, институты; шесть связок между ними; классы событий; интерпретатор показателей; "
    "отрасли) и ответили короткой формой; затем ответили на вопросы друг друга. Твоя работа — не "
    "пересказать двенадцать ответов, а собрать из них ОДНУ системную картину.\n\n"
    "🔴 ПРАВИЛА СВЕДЕНИЯ:\n"
    "1. Сначала диагноз (что происходит и почему), потом прогноз (кодекс 0.1).\n"
    "2. Цепочки через несколько взглядов — главная ценность: событие → механизм у одного агента → "
    "следствие у другого → результат для экономики и рынка. Назови, чей взгляд дал каждое звено.\n"
    "3. Где агенты спорят — не усредняй: изложи позиции, реши по доказательствам (факт сильнее "
    "гипотезы, кодекс 0.5), а если решить нельзя — оставь расхождение открытым и скажи, что его снимет.\n"
    "4. Вероятности не усредняй механически: возьми оценку того агента, чья методичка отвечает за "
    "этот исход, и объясни, почему; таблица слов и чисел — как у агентов.\n"
    "5. Что не видит НИ ОДНА методичка — отдельно, честно.\n"
    "6. Числа и даты — только из ответов агентов и пачки данных, с источником.\n"
    "7. Язык — обычный, без жаргона; нейтральный тон, РФ-топонимика, без «купить/продать/рекомендуем».\n\n"
    "ФОРМА (строго JSON): {\n"
    "  \"answer\": \"<ответ владельцу обычным языком, 600–1200 слов, абзацами: главный вывод → диагноз "
    "→ цепочки → куда движется и что наблюдать → чего не знаем>\",\n"
    "  \"causal_map\": [ {\"chain\": \"<событие → … → результат>\", \"lenses\": [\"<id>\", ...], "
    "\"status\": \"Ф|Д|В|Г\", \"confidence\": \"низкая|средняя|высокая\"} ],\n"
    "  \"agreements\": [\"<в чём сошлись>\", ...],\n"
    "  \"disagreements\": [ {\"topic\": \"...\", \"positions\": [ {\"lens\": \"<id>\", \"claim\": \"...\"} ], "
    "\"resolution\": \"<кто прав и почему | открыто>\", \"evidence\": \"...\"} ],\n"
    "  \"forecast\": {\"most_likely\": \"...\", \"most_dangerous\": \"...\", "
    "\"probabilities\": [ {\"outcome\": \"...\", \"p\": <0..1>, \"horizon\": \"...\", \"owner_lens\": \"<id>\", \"basis\": \"...\"} ], "
    "\"triggers\": [\"...\"]},\n"
    "  \"watch\": [\"<признак — и чей взгляд его требует>\", ...],\n"
    "  \"unknowns\": [\"<чего не видит ни одна методичка / данных нет>\", ...],\n"
    "  \"lens_coverage\": { \"<id>\": \"использован|тонко|пусто\" }\n"
    "}"
)


def synth_system() -> str:
    """Системное задание сведения: операционный протокол владельца + правила сведения."""
    return _protocol() + "\n" + _SYNTH_SYSTEM


def synthesize(db: Session, task: str, results: dict[str, dict], replies: dict[str, dict],
               packet: str, notes: list[str] | None = None) -> dict | None:
    from app.services.agent_runner import run_agent
    compact = {k: {kk: vv for kk, vv in (v or {}).items() if kk != "_meta"} for k, v in results.items() if v}
    user = ("ЗАДАЧА СОВЕТА:\n" + task
            + "\n\nОТВЕТЫ АГЕНТОВ (id → ответ по форме):\n" + json.dumps(compact, ensure_ascii=False)[:180_000]
            + "\n\nОТВЕТЫ НА ВОПРОСЫ КОЛЛЕГ:\n" + (json.dumps(replies, ensure_ascii=False)[:40_000] if replies else "— круг вопросов не проводился —")
            + "\n\nПАЧКА ДАННЫХ (та же, что у агентов; для сверки чисел):\n" + packet[:30_000]
            + f"\n\nСегодня: {date.today().isoformat()}.")
    t0 = time.monotonic()
    try:
        out = run_agent(db, system_prompt=synth_system(), task=user, tools_schema=[], allowed_ticker="",
                        max_steps=2, max_tokens_total=1_000_000, web_call_cap=0, executor=lambda *_: None,
                        step_max_tokens=_SYNTH_MAX_TOKENS, final_max_tokens=_SYNTH_MAX_TOKENS,
                        final_instruction="Верни JSON строго по форме из роли.",
                        model=llm.pro_model(), thinking=True, effort=getattr(llm, "ANALYST_EFFORT", "max"))
    except Exception as e:  # noqa: BLE001
        logger.warning("council synthesis: упало (%s)", e)
        if notes is not None:
            notes.append(f"сведение: упало — {type(e).__name__}: {str(e)[:160]}")
        return None
    res = out.get("result")
    if notes is not None:
        notes.append(f"сведение: токенов {out.get('tokens_used')}, {round(time.monotonic() - t0, 1)} с, "
                     f"остановка {out.get('stopped_reason')}")
    return res if isinstance(res, dict) else None


# ─────────────────────────── оркестратор ───────────────────────────

def run_council(db: Session, task: str, *, lenses: list[str] | None = None, parallel: int = _PARALLEL,
                question_round: bool = True, persist: bool = True, label: str = "совет") -> dict:
    """Вся цепочка: пачка → агенты волнами → круг вопросов → сведение → версия kind=council."""
    ids = [x for x in (lenses or LENSES) if x in LENSES] or list(LENSES)
    notes: list[str] = []
    t0 = time.monotonic()
    packet = build_packet(db)
    results: dict[str, dict | None] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(int(parallel or 1), 6))) as pool:
        for doc_id, res, n in pool.map(lambda d: _run_lens_own_session(d, task, packet), ids):
            results[doc_id] = res
            notes.extend(n)
    answered = {k: v for k, v in results.items() if v}
    logger.warning("council[%s]: ответили %d из %d агентов", label, len(answered), len(ids))

    replies: dict[str, dict] = {}
    if question_round and answered:
        inbox = route_questions(answered)
        if inbox:
            with ThreadPoolExecutor(max_workers=max(1, min(int(parallel or 1), 6))) as pool:
                for doc_id, res, n in pool.map(lambda kv: _run_lens_own_session(kv[0], task, packet, kv[1]), inbox.items()):
                    notes.extend(n)
                    if res:
                        replies[doc_id] = res

    synthesis = synthesize(db, task, answered, replies, packet, notes=notes) if answered else None
    ok, why = True, None
    try:
        from app.services.barometer_daily import compliance_ok
        if synthesis:
            ok, why = compliance_ok(synthesis)
    except Exception:  # noqa: BLE001
        pass
    payload = {
        "as_of": date.today().isoformat(), "task": task, "label": label, "lenses": ids,
        "answered": sorted(answered), "failed": sorted(k for k, v in results.items() if not v),
        "lens_answers": answered, "replies": replies, "synthesis": synthesis,
        "compliance_blocked": (None if ok else why),
        "notes": notes, "seconds": round(time.monotonic() - t0, 1),
        "model": f"{llm.provider_info().get('provider')}:{llm.pro_model()}",
    }
    if persist:
        row = BarometerVersion(kind=KIND, source="auto", status="published" if synthesis else "rejected",
                               payload=payload, trigger_reason=label[:120], model_used=payload["model"])
        db.add(row); db.commit(); db.refresh(row)
        payload["version_id"] = row.id
    logger.warning("council[%s]: готово за %.0f с, сведение %s", label, payload["seconds"], "есть" if synthesis else "НЕТ")
    return payload


# ─────────────────────────── чтение ───────────────────────────

def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)


def history(db: Session, limit: int = 20) -> list[dict]:
    rows = (db.query(BarometerVersion).filter(BarometerVersion.kind == KIND)
            .order_by(BarometerVersion.created_at.desc()).limit(limit).all())
    return [{"version_id": r.id, "status": r.status, "as_of": (r.payload or {}).get("as_of"),
             "label": (r.payload or {}).get("label"), "task": str((r.payload or {}).get("task") or "")[:160],
             "answered": len((r.payload or {}).get("answered") or []), "seconds": (r.payload or {}).get("seconds")}
            for r in rows]


def render_md(payload: dict) -> str:
    s = payload.get("synthesis") or {}
    out = [f"# Совет агентов-методичек — {payload.get('as_of')}",
           f"**Задача.** {payload.get('task')}", "",
           f"Ответили {len(payload.get('answered') or [])} из {len(payload.get('lenses') or [])} агентов"
           + (f", не ответили: {', '.join(payload['failed'])}" if payload.get("failed") else "")
           + f"; {payload.get('seconds')} с.", ""]
    if payload.get("compliance_blocked"):
        out.append(f"_Сведение скрыто автопроверкой: {payload['compliance_blocked']}_")
    elif s:
        out.append("## Сведение"); out.append(str(s.get("answer") or "")); out.append("")
        if s.get("causal_map"):
            out.append("**Цепочки.** " + " | ".join(f"{c.get('chain')} [{', '.join(c.get('lenses') or [])}; {c.get('status')}]"
                                                    for c in s["causal_map"] if isinstance(c, dict)))
        if s.get("disagreements"):
            out.append("**Расхождения.** " + " | ".join(f"{d.get('topic')}: {d.get('resolution')}" for d in s["disagreements"] if isinstance(d, dict)))
        f = s.get("forecast") or {}
        if f:
            out.append(f"**Прогноз.** Вероятнее всего: {f.get('most_likely')} Опаснее всего: {f.get('most_dangerous')}")
            if f.get("probabilities"):
                out.append("Вероятности: " + "; ".join(f"{p.get('outcome')} — {p.get('p')} ({p.get('horizon')}, {p.get('owner_lens')})"
                                                    for p in f["probabilities"] if isinstance(p, dict)))
        if s.get("unknowns"):
            out.append("**Не видит ни одна методичка.** " + "; ".join(str(u) for u in s["unknowns"]))
        out.append("")
    out.append("## Взгляды агентов")
    for lens_id, a in (payload.get("lens_answers") or {}).items():
        if not isinstance(a, dict):
            continue
        out.append(f"### {lens_id} · {CONTOUR_OF.get(lens_id, '')}")
        out.append(str(a.get("sees") or ""))
        if a.get("blind_spots"):
            out.append(f"_Не видит:_ {a['blind_spots']}")
        out.append("")
    return "\n".join(out)
