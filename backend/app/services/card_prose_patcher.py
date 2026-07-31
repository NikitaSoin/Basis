"""Авто-свежесть ПРОЗЫ вкладок карточки — патчер (план docs/prose-freshness-plan.md).

Владелец (2026-07-29): текст разборов должен сам обновляться — ФАКТЫ дневным
кроном, ИНТЕРПРЕТАЦИЯ недельным; БЕЗ черновика (сразу published, гейт — барьер);
задача НЕ перегенерить, а поправить ТОЛЬКО там, где входной поток показал
изменение. Дизайн ревью advisor.

🔴 ФОРМАТ ОТВЕТА (общий для обоих режимов, добавляется к промпту): модель обязана
вернуть ТОЛЬКО валидный JSON и ничего больше — без рассуждений/анализа/markdown, по-
русски, первый символ `{`. Реальный боевой сбой (SBER/markets): DeepSeek ушёл в
reasoning-прозу на английском вместо JSON → unparseable_final (гейт отклонил, fail-
closed, проза цела). Лечится жёсткой директивой формата + примером (_JSON_ONLY).

МЕХАНИКА (безопасность — кодовая):
- Патч выражается как точечные find/replace правки прозы. Нетронутый текст
  ДОСЛОВЕН ПО ПОСТРОЕНИЮ (меняются только совпавшие подстроки) — это надёжнее
  перегенерации/полного переписа.
- Гейт: каждый `find` встречается в прозе РОВНО раз; число в `replace`, которого
  нет в `find`, обязано присутствовать в тексте сигнала (аналог _mentioned_close —
  против выдумывания чисел); блоклист прогнозных/«купить-продать»; комплаенс РФ;
  no-op (проза не изменилась) → reject. Провал → published-версия НЕ меняется.
- Хранение — ОВЕРЛЕЙ в БД (CardProseOverlay): файлы на Timeweb эфемерны. Витрина
  (summary-эндпоинты) читает «оверлей → фолбэк файл». Supersede: последний
  published на (ticker, tab).
- Триггер — ВХОДНОЙ ПОТОК (company_signals), не слепой прогон всех: очередь
  (тикер, вкладка) из свежих значимых сигналов, ещё не отражённых оверлеем.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.geo import CardProseOverlay, CompanySignal
from app.services.agent_runner import run_agent
from app.services.agent_tools import WEB_TOOLS_SCHEMA
from app.services.situation_overlay import _BLOCKLIST

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# вкладка → файл прозы (summary.md — основной аналитический текст вкладки)
_TAB_FILE = {
    "business": "business_model.md",
    "finance": "financials_summary.md",
    "governance": "governance_summary.md",
    "markets": "market_summary.md",
    "macro": "macro_summary.md",
    "geo": "geo_summary.md",
    "institutions": "institutions_summary.md",
}
# вкладки сигнала → вкладка прозы (bonds/dividends не имеют summary у КОМПАНИИ)
_SIGNAL_TAB_TO_PROSE = {
    "finance": "finance", "governance": "governance", "markets": "markets",
    "macro": "macro", "geo": "geo", "institutions": "institutions",
}

_MAX_EDITS = 10         # было 4 («вывод не упирается в токены») — насыщенной макро-
# вкладке (ставка+дата решения+инфляция+ожидания+заседание, по нескольку упоминаний)
# законно нужно больше: на бою 2026-07-31 SBER/macro отклонился edits_invalid при
# корректной полной правке. Токен-бюджет поднят синхронно (см. max_tokens в _run_patch)
_MAX_FIND_LEN = 450     # якорь find: раньше 200 «≤ предложение», но интерпретация
# правит АБЗАЦЫ, и модель законно отдаёт 200-300-символьные якоря — на бою
# 2026-07-31 find_too_long(247/256) резал содержательные правки (SBER finance,
# TATN markets). 450 покрывает абзац; от обрезки/экранирования JSON защищает не
# лимит, а требование точного вхождения (обрезанный find просто не найдётся)
_FRESH_DAYS = 10
_BATCH_CAP = 5

# прогнозные/оценочные конструкции — факт-патч НЕ добавляет суждение о будущем
_FORBIDDEN = re.compile(
    r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет|целев\w+\s+цен|приведёт\s+к|"
    r"ожида(ем|ется)|вырастет\s+до|упадёт\s+до|прогнозиру|потенциал\s+рост|апсайд",
    re.IGNORECASE)
# Для ИНТЕРПРЕТАЦИИ полный список не годится: её работа — суждение, и «ожидается»/
# «прогнозируется» там легитимны (на бою 2026-07-31 forbidden резал валидные
# интерпретационные правки). Жёсткое ядро остаётся: сделки и целевые цены
# запрещены ЛЮБОМУ виду патча (не брокер, без «купить/продать»).
_FORBIDDEN_INTERP = re.compile(
    r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет|целев\w+\s+цен",
    re.IGNORECASE)

_FACT_SYS = """Ты — редактор-факт-чекер платформы Basis (не брокер, без «купить/
продать» и прогнозов). Тебе дан ТЕКСТ разбора вкладки и ПРОВЕРЕННЫЙ сигнал-событие
(официальный источник). Задача: если в тексте есть УСТАРЕВШИЙ ФАКТ (число, дата,
уровень, показатель), который сигнал делает неверным — верни ТОЧЕЧНЫЕ правки
find/replace, меняющие ТОЛЬКО устаревший факт. НЕ переписывай текст, НЕ добавляй
интерпретацию, НЕ меняй смысл предложения кроме самого числа/факта. Если текст уже
верен или сигнал не про факт из этого текста — confirmed=false.

Можно fetch_document(source_url) — сверить первоисточник (необязательно).
Финальный ответ БЕЗ инструментов — строго JSON:
{
  "confirmed": true|false,
  "edits": [
    {"find": "<ТОЧНАЯ подстрока из текста, включающая устаревший факт>",
     "replace": "<та же подстрока с исправленным фактом>",
     "why": "что изменилось и почему (1 фраза)", "certainty": "факт"}
  ],
  "note": "если confirmed=false — почему; иначе краткое резюме правок"
}
Правила: `find` — КОРОТКАЯ дословная подстрока из текста (скопируй ТОЧНО), максимум
ОДНО предложение, ≤200 символов, встречается в тексте РОВНО раз (выбери минимальный
уникальный фрагмент вокруг устаревшего факта — НЕ целый абзац); в `replace` меняй
МИНИМУМ (только сам факт), новые числа бери из сигнала; 1-4 правки. Не копируй
длинные куски — только точечный фрагмент с фактом."""

_INTERP_SYS = """Ты — редактор-аналитик платформы Basis (не брокер, без «купить/
продать» и таргетов). Тебе дан ТЕКСТ разбора вкладки и СВОДКА входного потока за
неделю (что произошло). Задача: НЕ перегенерировать разбор, а точечно скорректировать
ТОЛЬКО те места, где поток реально изменил картину (сдвиг тренда/риска/позиции). Не
изменилось — confirmed=false, ничего не трогаем. Правь ТОЧЕЧНО через find/replace,
сохраняя стиль и эпистемические теги; без прогнозов цен и сигналов сделок.
🔴 `find` — КОРОТКИЙ дословный фрагмент (одна фраза/предложение, ≤200 символов),
встречается РОВНО раз; НЕ копируй целые абзацы (иначе ответ обрежется). Несколько
мелких правок лучше одной большой; максимум 1-4 правки.
Финальный ответ — строго JSON того же формата, что у факт-редактора (confirmed/edits/
note), certainty у правок: оценка|суждение."""


# жёсткая директива формата — против reasoning-прозы вместо JSON (боевой сбой DeepSeek)
_JSON_ONLY = (
    "\n\n🔴 КРИТИЧНО — ФОРМАТ ОТВЕТА. Верни РОВНО ОДИН валидный JSON-объект и БОЛЬШЕ "
    "НИЧЕГО: без рассуждений, без анализа, без пояснений, без markdown и без какого-либо "
    "текста до или после. ПЕРВЫЙ символ ответа — `{`, ПОСЛЕДНИЙ — `}`. Всё по-русски. "
    "Не пиши «Let me analyze» и подобное — сразу JSON. Если менять нечего — верни "
    '{"confirmed": false, "edits": [], "note": "изменений нет"}. Пример валидного ответа: '
    '{"confirmed": true, "edits": [{"find": "выручка 100 млрд руб.", "replace": '
    '"выручка 120 млрд руб.", "why": "новый отчёт за 2025", "certainty": "факт"}], '
    '"note": "обновил выручку по свежему отчёту"}')


# ----------------------------- ЧТЕНИЕ ПРОЗЫ (оверлей-first) -----------------------------
def _tab_path(ticker: str, tab: str) -> Path | None:
    fn = _TAB_FILE.get(tab)
    return (COMPANIES_DIR / ticker.upper() / fn) if fn else None


def current_overlay(db: Session, ticker: str, tab: str) -> CardProseOverlay | None:
    return (db.query(CardProseOverlay)
            .filter(CardProseOverlay.ticker == ticker.upper(),
                    CardProseOverlay.tab == tab,
                    CardProseOverlay.status == "published")
            .order_by(CardProseOverlay.created_at.desc()).first())


def read_prose(db: Session, ticker: str, tab: str) -> tuple[str | None, str]:
    """(текст, источник 'overlay'|'file'|'none'). Оверлей-first — то, что отдаём."""
    ov = current_overlay(db, ticker, tab)
    if ov and ov.patched_md:
        return ov.patched_md, "overlay"
    p = _tab_path(ticker, tab)
    if p and p.exists():
        try:
            return p.read_text(encoding="utf-8"), "file"
        except Exception:  # noqa: BLE001
            return None, "none"
    return None, "none"


# ----------------------------- ГЕЙТ -----------------------------
def _numbers(s: str) -> list[str]:
    # «1 019 млрд» (пробел/неразрывный как разделитель тысяч) без склейки распадается
    # на токены «1» и «019» — и валидная правка падала на ungrounded_numbers:['019']
    # (бой 2026-07-31). Склеиваем разряды ДО разбора — одинаково для сигнала, прозы,
    # find и replace, так что строгость проверки не меняется.
    s = re.sub(r"(?<=\d)[\u00a0\u202f\u2009 ](?=\d{3}(?!\d))", "", s or "")
    # точка/запятая КОНЦА ПРЕДЛОЖЕНИЯ прилипает к числу («в 2025.» → токен «2025.»,
    # который не равен «2025» из сигнала — бой 2026-07-31, ungrounded:['2025.']);
    # нормализация одинакова для обеих сторон сравнения
    return [t.rstrip(".,") for t in re.findall(r"\d+[.,]?\d*", s)]


# нормализация для ПОИСКА find в прозе — 1:1 (длина сохраняется, чтобы индексы
# совпадали): тире → «-», спецпробелы И ПЕРЕНОСЫ → пробел, «ёлочки»/„лапки" → ",
# типографский апостроф → ', ё → е. На бою 2026-07-31 недостающая нормализация
# (кавычки/переносы) дала 0 публикаций интерпретации за 14 дней: содержательные
# правки (SBER: прибыль 1П2026, статус дивиденда) резались find_not_in_prose.
_MATCH_NORM = str.maketrans({
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2011": "-",
    "\u00a0": " ", "\u202f": " ", "\u2009": " ",
    "\n": " ", "\t": " ",
    "\u00ab": '"', "\u00bb": '"', "\u201e": '"', "\u201c": '"', "\u201d": '"',
    "\u2019": "'", "\u2018": "'", "\u0451": "\u0435", "\u0401": "\u0415",
})


def _norm_match(s: str) -> str:
    return s.translate(_MATCH_NORM)


import re as _re_flex  # noqa: E402 (локальный алиас, чтобы не путать с модульным re)


def _flexible_spans(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Вторая линия поиска, когда 1:1-нормализация не нашла: та же толерантность
    плюс СХЛОПЫВАНИЕ пробелов — модель отдаёт find с одиночными пробелами, а в
    прозе двойные/переносы, и 1:1-замена (длина сохраняется) этого не покрывает.
    Ищем регекспом ПО ОРИГИНАЛУ; длина совпадения может отличаться от find —
    возвращаем реальные спаны."""
    tokens = _norm_match(needle).split()
    if not tokens:
        return []
    def _tok(t: str) -> str:
        out = []
        for ch in t:
            if ch == "-":
                out.append("[-\u2013\u2014\u2212\u2011]")
            elif ch == '"':
                out.append("[\"\u00ab\u00bb\u201e\u201c\u201d]")
            elif ch == "'":
                out.append("['\u2019\u2018]")
            elif ch in ("е", "Е"):
                out.append("[еЕёЁ]" if ch == "Е" else "[её]")
            else:
                out.append(re.escape(ch))
        return "".join(out)
    pattern = r"\s+".join(_tok(t) for t in tokens)
    try:
        return [(m.start(), m.end()) for m in re.finditer(pattern, haystack)]
    except re.error:
        return []


def _apply_and_gate(prose: str, result: dict, signal_text: str,
                    kind: str = "fact",
                    strict_numbers: bool = False) -> tuple[str | None, list[str]]:
    """→ (patched_md|None, notes). Применяет find/replace и проверяет каждую правку."""
    notes: list[str] = []
    if not isinstance(result, dict):
        return None, ["not_a_dict"]
    if result.get("confirmed") is not True:
        return None, [f"not_confirmed:{(result.get('note') or 'agent')[:40]}"]
    edits = result.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > _MAX_EDITS:
        return None, ["edits_invalid"]

    # число «обосновано», если есть в тексте сигнала ИЛИ уже в самой прозе
    # (аналитик его туда внёс) — иначе это выдуманное агентом число.
    # strict_numbers (макро-факты): новые числа — ТОЛЬКО из официального якоря.
    # Обычный режим разрешает и числа из прозы (перестройка предложения), но для
    # обновления макро-показателей это дыра: на бою 2026-08-01 модель поставила
    # ожидания «12,1%» (число из ДРУГОГО места прозы) вместо 14,7 из якоря — гейт
    # пропустил, т.к. «12,1» встречался в тексте.
    allowed_nums = set(_numbers(signal_text.replace(",", ".")))
    if not strict_numbers:
        allowed_nums |= set(_numbers(prose.replace(",", ".")))
    # даты «30.07»/«30.07.2026» — производные ISO-дат источника (published_at
    # сигнала пишется как 2026-07-30): токен «30.07» не совпадает с «2026», «07»,
    # «30» по отдельности, и валидные правки резались ungrounded_numbers (бой
    # 2026-07-31, GAZP governance). Разрешаем ровно производные, не любые даты.
    for iso in re.findall(r"(\d{4})-(\d{2})-(\d{2})", signal_text + " " + prose):
        y, mo, d = iso
        allowed_nums |= {f"{d}.{mo}", f"{int(d)}.{mo}", f"{d}.{mo}.{y}", f"{int(d)}.{mo}.{y}"}
    patched = prose
    for i, e in enumerate(edits):
        if not isinstance(e, dict):
            notes.append(f"edit{i}:not_dict"); continue
        find = e.get("find") or ""
        repl = e.get("replace") or ""
        if not find or not repl:
            notes.append(f"edit{i}:empty"); continue
        if len(find) > _MAX_FIND_LEN:
            notes.append(f"edit{i}:find_too_long({len(find)})"); continue
        # поиск find толерантно к тире/пробелам (1:1 нормализация сохраняет длину →
        # индекс в нормализованной = индекс в оригинале)
        n_patched, n_find = _norm_match(patched), _norm_match(find)
        cnt = n_patched.count(n_find)
        span = None
        if cnt == 1:
            idx0 = n_patched.find(n_find)
            span = (idx0, idx0 + len(find))
        elif cnt == 0:
            spans = _flexible_spans(patched, find)
            if len(spans) == 1:
                span = spans[0]
            elif len(spans) > 1:
                notes.append(f"edit{i}:find_ambiguous({len(spans)})")
                continue
            else:
                notes.append(f"edit{i}:find_not_in_prose")
                continue
        else:
            notes.append(f"edit{i}:find_ambiguous({cnt})")
            continue
        # интерпретация легитимно дописывает абзац (новый риск/тезис) — +200 ей
        # мало (бой 2026-07-31: replace_too_long на валидных правках); переписывание
        # с нуля по-прежнему отсечено лимитом
        max_grow = 500 if kind == "interpretation" else 200
        if len(repl) > len(find) + max_grow:
            notes.append(f"edit{i}:replace_too_long")
            continue
        forb = _FORBIDDEN_INTERP if kind == "interpretation" else _FORBIDDEN
        if forb.search(repl):
            notes.append(f"edit{i}:forbidden")
            continue
        # число в replace, которого НЕТ в find, обязано быть обосновано (сигнал/проза)
        new_nums = set(_numbers(repl.replace(",", "."))) - set(_numbers(find.replace(",", ".")))
        ungrounded = [n for n in new_nums if n not in allowed_nums]
        if ungrounded:
            notes.append(f"edit{i}:ungrounded_numbers:{ungrounded[:3]}")
            continue
        patched = patched[:span[0]] + repl + patched[span[1]:]

    if notes:
        return None, notes
    if patched == prose:
        return None, ["noop_no_change"]
    # комплаенс РФ на итоговом тексте изменений
    m = _BLOCKLIST.search(patched)
    if m and not _BLOCKLIST.search(prose):  # блоклист внесён патчем
        return None, [f"compliance:{m.group(0)[:24]}"]
    return patched, []


# ----------------------------- ПРОГОН (общее ядро) -----------------------------
def _run_patch(db: Session, ticker: str, tab: str, *, sys: str, task_builder,
               grounding_text: str, kind: str, source_signal_id: int | None = None,
               evidence_extra: dict | None = None,
               strict_numbers: bool = False) -> CardProseOverlay | None:
    """Ядро патча: прочитать прозу (оверлей-first) → агент правит find/replace →
    код-гейт → published|rejected-оверлей. grounding_text — источник, в котором
    обязаны присутствовать новые числа (сигнал для фактов / сводка потока для
    интерпретации). Нетронутая проза дословна по построению."""
    prose, src = read_prose(db, ticker, tab)
    if not prose:
        return None
    # json_mode: провайдер ФОРСИТ валидный JSON (DeepSeek иначе уходит в reasoning-
    # прозу вместо JSON — боевой сбой). Прямой complete вместо tool-loop: патчеру
    # инструменты почти не нужны (grounding — в задаче), а json_mode устойчивее.
    from app.services.llm import complete, LLMError
    stopped = "final"
    try:
        result = complete(sys, task_builder(prose), json_mode=True,
                          max_tokens=3500, temperature=0.1)
    except LLMError as e:
        result, stopped = None, f"llm_error:{str(e)[:60]}"
    if isinstance(result, dict):
        patched, notes = _apply_and_gate(prose, result, grounding_text, kind=kind,
                                         strict_numbers=strict_numbers)
    else:
        patched, notes = None, [f"no_result:{stopped}"]
    ok = patched is not None
    parent = current_overlay(db, ticker, tab)
    # диагностика: stopped_reason всегда; сырой результат — при провале
    evidence = {"prose_source": src, "stopped_reason": stopped, **(evidence_extra or {})}
    if not ok:
        evidence["raw_result_tail"] = str(result)[:700]
    row = CardProseOverlay(
        ticker=ticker, tab=tab, kind=kind,
        status="published" if ok else "rejected",
        patched_md=patched if ok else None,
        original_md=prose if ok else None,
        change_note=(result or {}).get("note") if isinstance(result, dict) else None,
        evidence=evidence,
        gate_notes=notes or None, source_signal_id=source_signal_id,
        parent_id=parent.id if (ok and parent) else None,
        model_used="deepseek", tokens_used=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("card_prose_patcher %s/%s [%s]: %s (гейт: %s)",
                ticker, tab, kind, row.status, notes or "чисто")
    return row


# ----------------------------- ФАКТЫ (дневной, по сигналу) -----------------------------
def run_for_signal(db: Session, signal: CompanySignal, kind: str = "fact") -> CardProseOverlay | None:
    """Один сигнал → факт-патч прозы вкладки. None если нет прозы/уже отражено."""
    ticker = signal.ticker.upper()
    tab = _SIGNAL_TAB_TO_PROSE.get(signal.card_tab or "")
    if not tab:
        return None
    if db.query(CardProseOverlay.id).filter(
            CardProseOverlay.source_signal_id == signal.id).first():
        return None  # уже патчили этим сигналом

    def _tb(prose: str) -> str:
        return (
            f"Компания: {ticker}. Вкладка: {tab}. Сегодня "
            f"{datetime.now(timezone.utc).date().isoformat()}.\n\n"
            f"СИГНАЛ (тип {signal.signal_type}, источник {signal.source_key}, "
            f"дата {signal.published_at}):\nЗаголовок: {signal.title}\n"
            f"Содержание: {(signal.summary or '')[:600]}\n"
            f"Первоисточник: {signal.source_url or '—'}\n\n"
            f"ТЕКСТ РАЗБОРА ВКЛАДКИ (правь точечно find/replace):\n<<<\n{prose[:8000]}\n>>>")

    return _run_patch(
        db, ticker, tab, sys=_FACT_SYS + _JSON_ONLY, task_builder=_tb,
        grounding_text=f"{signal.title or ''} {signal.summary or ''}", kind="fact",
        source_signal_id=signal.id,
        evidence_extra={"signal_id": signal.id, "source_key": signal.source_key,
                        "source_url": signal.source_url})


def _fact_queue(db: Session) -> list[CompanySignal]:
    """Свежие ЗНАЧИМЫЕ сигналы, мапящиеся на прозу-вкладку, ещё не отражённые
    оверлеем. Триггер от входного потока — не слепой прогон всех карточек."""
    fresh = datetime.now(timezone.utc).date() - timedelta(days=_FRESH_DAYS)
    rows = (db.query(CompanySignal)
            .filter(CompanySignal.importance == "high",
                    CompanySignal.trust == "official",
                    CompanySignal.internal.is_(False),
                    CompanySignal.card_tab.in_(list(_SIGNAL_TAB_TO_PROSE)),
                    CompanySignal.published_at >= fresh)
            .order_by(CompanySignal.published_at.desc().nullslast())
            .limit(_BATCH_CAP * 3).all())
    # отфильтровать уже отражённые оверлеем (по source_signal_id)
    done = {r[0] for r in db.query(CardProseOverlay.source_signal_id)
            .filter(CardProseOverlay.source_signal_id.isnot(None)).all()}
    return [s for s in rows if s.id not in done][:_BATCH_CAP]


def run_daily_facts(db: Session) -> dict:
    """Дневной проход ФАКТОВ: очередь из входного потока → факт-патч под гейтом."""
    queue = _fact_queue(db)
    stats = {"queued": len(queue), "published": 0, "rejected": 0, "skipped": 0}
    for s in queue:
        row = run_for_signal(db, s, kind="fact")
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_daily_facts: %s", stats)
    return stats


# ----------------------------- ИНТЕРПРЕТАЦИЯ (недельный, по потоку) -----------------------------
_INTERP_COOLDOWN_DAYS = 6   # не переинтерпретировать вкладку чаще раза в ~неделю
_INTERP_FLOW_DAYS = 8       # окно «входного потока за неделю»
_INTERP_BATCH_CAP = 6       # (тикер, вкладка) за прогон


def _week_flow(db: Session, ticker: str, prose_tab: str) -> list[CompanySignal]:
    """Входной поток за неделю для (тикер, прозная вкладка): сигналы company_signals
    по тикеру, мапящиеся на эту вкладку."""
    since = datetime.now(timezone.utc).date() - timedelta(days=_INTERP_FLOW_DAYS)
    sig_tabs = [st for st, pt in _SIGNAL_TAB_TO_PROSE.items() if pt == prose_tab]
    return (db.query(CompanySignal)
            .filter(CompanySignal.ticker == ticker.upper(),
                    CompanySignal.card_tab.in_(sig_tabs),
                    CompanySignal.published_at >= since)
            .order_by(CompanySignal.published_at.desc()).limit(12).all())


def run_interp_for_tab(db: Session, ticker: str, tab: str,
                       flow_rows: list[CompanySignal]) -> CardProseOverlay | None:
    """Дельта-правка ИНТЕРПРЕТАЦИИ вкладки по входному потоку недели: агент меняет
    только те места, где поток изменил картину (не перегенерация). Cooldown на
    (тикер, вкладка)."""
    if not flow_rows:
        return None
    since = datetime.now(timezone.utc) - timedelta(days=_INTERP_COOLDOWN_DAYS)
    if db.query(CardProseOverlay.id).filter(
            CardProseOverlay.ticker == ticker.upper(), CardProseOverlay.tab == tab,
            CardProseOverlay.kind == "interpretation",
            CardProseOverlay.status == "published",  # rejected/no-op не вызывает cooldown
            CardProseOverlay.created_at >= since).first():
        return None  # cooldown: недавно УЖЕ меняли интерпретацию этой вкладки
    flow_txt = "\n".join(
        # 500, не 160: обрезка резала сами ЧИСЛА из сигналов, и законные правки
        # падали на ungrounded_numbers (заземление проверяется по этому тексту)
        f"- {r.published_at} [{r.source_key}] {r.title}: {(r.summary or '')[:500]}"
        for r in flow_rows)

    def _tb(prose: str) -> str:
        return (
            f"Компания: {ticker}. Вкладка: {tab}. Сегодня "
            f"{datetime.now(timezone.utc).date().isoformat()}.\n\n"
            f"ВХОДНОЙ ПОТОК ЗА НЕДЕЛЮ (что пришло):\n{flow_txt}\n\n"
            f"ТЕКСТ РАЗБОРА (правь точечно find/replace ТОЛЬКО там, где поток "
            f"изменил картину; не изменил — confirmed=false):\n<<<\n{prose[:8000]}\n>>>")

    return _run_patch(db, ticker, tab, sys=_INTERP_SYS + _JSON_ONLY, task_builder=_tb,
                      grounding_text=flow_txt, kind="interpretation",
                      evidence_extra={"flow_signal_ids": [r.id for r in flow_rows]})


def run_weekly_interp(db: Session) -> dict:
    """Недельный проход: (тикер, вкладка) с потоком за неделю → дельта-правка
    интерпретации по потоку. НЕ перегенерация, НЕ слепой прогон всех карточек."""
    since = datetime.now(timezone.utc).date() - timedelta(days=_INTERP_FLOW_DAYS)
    # только значимый поток (high/medium) — не жечь бюджет на шумовых новостях
    # широкого маппинга Ленты (§8 observer-source-map)
    rows = (db.query(CompanySignal)
            .filter(CompanySignal.internal.is_(False),
                    CompanySignal.importance.in_(("high", "medium")),
                    CompanySignal.card_tab.in_(list(_SIGNAL_TAB_TO_PROSE)),
                    CompanySignal.published_at >= since)
            .order_by(CompanySignal.published_at.desc()).all())
    # приоритет пар по «активности»: есть high → выше, затем по числу сигналов
    score: dict = {}
    for s in rows:
        pt = _SIGNAL_TAB_TO_PROSE.get(s.card_tab or "")
        if not pt:
            continue
        key = (s.ticker.upper(), pt)
        w = 10 if s.importance == "high" else 1
        score[key] = score.get(key, 0) + w
    pairs = [k for k, _ in sorted(score.items(), key=lambda kv: kv[1], reverse=True)][:_INTERP_BATCH_CAP]
    stats = {"pairs": len(pairs), "published": 0, "rejected": 0, "skipped": 0}
    for tk, pt in pairs:
        row = run_interp_for_tab(db, tk, pt, _week_flow(db, tk, pt))
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_weekly_interp: %s", stats)
    return stats


# ----------------------------- МАКРО-ФАКТЫ (мост рынок → карточки) -----------------------------
# Владелец 2026-07-31 (кейс SBER/macro: «ставка 14,25% от 19 июня, инфляция ~5,6,
# ожидания ~13 — на сайте ничего не меняется»): сигналы card_tab="macro" не
# производит НИКТО — шина company_signals мапит только КОРПОРАТИВНЫЕ события
# (дивиденды/отчёты/рейтинги/суды), а решение ЦБ — событие рынка, не тикера.
# Макро-вкладки всех ~264 карточек стояли вне контура авто-свежести by design.
# Этот проход — недостающий мост: живые макро-ряды (те же, что чинили сегодня:
# ставка/инфляция/ожидания) → детектор устаревших упоминаний в прозе кодом →
# обычный факт-патч под тем же гейтом. Никакой новой аналитики: только замена
# устаревших значений НА официальные текущие.
_MACRO_BATCH_CAP = 12
_MACRO_RETRY_DAYS = 4   # не долбить один тикер, пока значения не изменились/LLM думает no-op

_MACRO_FACT_SYS = """Ты — редактор-факт-чекер платформы Basis (не брокер, без «купить/
продать» и прогнозов). Даны АКТУАЛЬНЫЕ официальные макро-значения (ЦБ РФ, Росстат,
опрос инФОМ) и ТЕКСТ макро-вкладки карточки компании. Найди в тексте УСТАРЕВШИЕ
значения ЭТИХ ЖЕ показателей (ключевая ставка, инфляция г/г, инфляционные ожидания,
дата/размер последнего решения ЦБ) и верни точечные правки find/replace, обновляющие
ТОЛЬКО эти числа/даты и напрямую зависящие от них короткие обороты. ИСТОРИЧЕСКИЕ
сравнения («с пика 21% в начале 2025») НЕ трогай — они про прошлое и верны. Смысл,
выводы и структуру текста НЕ меняй. Если все значения актуальны — confirmed=false.
"""


def _fmt_num_variants(v: float) -> str:
    """Число в вариантах написания, чтобы гейт заземления узнал любой стиль прозы:
    14.0 → «14,0 14», 5.94 → «5,94», 14.25 → «14,25»."""
    out = [f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")]
    if float(v) == int(v):
        out.append(str(int(v)))
    return " ".join(out)


def _macro_anchor(db: Session) -> dict | None:
    """Актуальные ставка/инфляция/ожидания из живых рядов + дата решения ЦБ."""
    from sqlalchemy import text as _sql
    vals = {}
    for code, metric, key in (("key_rate", "level", "rate"),
                              ("inflation", "yoy", "inflation"),
                              ("inflation_expectations", "level", "expectations")):
        row = db.execute(_sql(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
            "AND metric=:m ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()
        if row:
            vals[key] = (float(row[0]), row[1])
    if "rate" not in vals:
        return None
    return vals


def _macro_grounding(anchor: dict) -> str:
    parts = []
    r, rd = anchor["rate"]
    parts.append(f"Ключевая ставка ЦБ: {_fmt_num_variants(r)} % (решение {rd.isoformat()})")
    if "inflation" in anchor:
        v, d = anchor["inflation"]
        parts.append(f"Инфляция г/г: {_fmt_num_variants(v)} % (на {d.isoformat()})")
    if "expectations" in anchor:
        v, d = anchor["expectations"]
        parts.append(f"Инфляционные ожидания населения: {_fmt_num_variants(v)} % ({d.isoformat()})")
    return "\n".join(parts)


def _macro_prose_stale(prose: str, anchor: dict) -> list[str]:
    """Кодовый детектор: в прозе упоминается показатель, но ТЕКУЩЕГО значения нет
    нигде в тексте. Грубо и дёшево — точность обеспечивает гейт, детектор лишь
    строит очередь."""
    nums = set(_numbers(prose.replace(",", ".")))
    stale = []
    checks = [("rate", r"ключев\w+ ставк|ставк\w+ (снижен|повышен|сохранен)"),
              ("inflation", r"инфляци"),
              ("expectations", r"инфляционн\w+ ожидани")]
    for key, kw in checks:
        if key not in anchor:
            continue
        val = anchor[key][0]
        variants = {f"{val:.2f}".rstrip("0").rstrip("."), str(int(val)) if val == int(val) else None}
        variants.discard(None)
        if re.search(kw, prose, re.IGNORECASE) and not (variants & nums):
            stale.append(key)
    return stale


def run_macro_facts(db: Session, batch: int = _MACRO_BATCH_CAP,
                    only_ticker: str | None = None) -> dict:
    """Проход по макро-вкладкам: устаревшие ставка/инфляция/ожидания → факт-патч.
    only_ticker — точечный перезапуск одного тикера БЕЗ ретрай-кулдауна (после
    фикса гейта не ждать 4 дня)."""
    anchor = _macro_anchor(db)
    if not anchor:
        return {"error": "нет макро-якоря (key_rate)"}
    grounding = _macro_grounding(anchor)
    retry_cut = datetime.now(timezone.utc) - timedelta(days=_MACRO_RETRY_DAYS)
    recent = set() if only_ticker else {
        r[0] for r in db.query(CardProseOverlay.ticker)
        .filter(CardProseOverlay.tab == "macro",
                CardProseOverlay.kind == "fact",
                CardProseOverlay.created_at >= retry_cut).all()}
    stats = {"checked": 0, "queued": 0, "published": 0, "rejected": 0}
    tickers = ([only_ticker.upper()] if only_ticker else
               sorted(d.name for d in COMPANIES_DIR.iterdir()
                      if d.is_dir() and (d / "macro_summary.md").exists()))
    for tk in tickers:
        if stats["queued"] >= batch:
            break
        if tk in recent:
            continue
        prose, _src = read_prose(db, tk, "macro")
        if not prose:
            continue
        stats["checked"] += 1
        stale = _macro_prose_stale(prose, anchor)
        if not stale:
            continue
        stats["queued"] += 1

        def _tb(p: str) -> str:
            return (f"Компания: {tk}. Вкладка: macro. Сегодня "
                    f"{datetime.now(timezone.utc).date().isoformat()}.\n\n"
                    f"АКТУАЛЬНЫЕ ОФИЦИАЛЬНЫЕ ЗНАЧЕНИЯ:\n{grounding}\n\n"
                    f"Устаревшие показатели по детектору: {', '.join(stale)}\n\n"
                    f"ТЕКСТ ВКЛАДКИ:\n<<<\n{p[:8000]}\n>>>")

        row = _run_patch(db, tk, "macro", sys=_MACRO_FACT_SYS + _JSON_ONLY,
                         task_builder=_tb, grounding_text=grounding, kind="fact",
                         strict_numbers=True,
                         evidence_extra={"macro_anchor": {k: [v[0], v[1].isoformat()]
                                                          for k, v in anchor.items()},
                                         "stale_keys": stale})
        if row is not None:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_macro_facts: %s", stats)
    return stats
