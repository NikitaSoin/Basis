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
FUTURES_ASSETS_DIR = Path(__file__).parent.parent.parent / "futures_assets"

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
    # Разборы базовых активов фьючерсов лежат не в companies/, а в futures_assets/
    # <код>/analysis.md, и «тикер» здесь — код актива (BR, GOLD, Si). Один разбор
    # обслуживает ВСЕ контракты на этот актив, поэтому патчить надо его, а не
    # контракт: контракты истекают ежеквартально, и правка контракта умерла бы
    # вместе с ним (у нас так и вышло — четыре разбора на июньские контракты,
    # которых уже нет в списке торгуемых).
    if tab == "futures_asset":
        return FUTURES_ASSETS_DIR / _safe_code(ticker) / "analysis.md"
    fn = _TAB_FILE.get(tab)
    return (COMPANIES_DIR / ticker.upper() / fn) if fn else None


def _safe_code(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", code or "")[:20]


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
    """Кодовый детектор устаревших макро-упоминаний — ПО ОКНАМ вокруг ключевых слов,
    а не «по всей прозе»: первая версия («текущего значения нет нигде в тексте»)
    слепла, когда правильное значение стояло в одном месте, а кривое — в другом
    (бой 2026-08-01, SBER: в теле 14,7 появилось, в шапке остались ожидания 12,1 —
    детектор молчал). Правило: показатель устарел, если СУЩЕСТВУЕТ окно вокруг его
    ключевого слова, где есть числа правдоподобного диапазона, но нет текущего.
    Грубо и дёшево — точность обеспечивает гейт (strict grounding)."""
    checks = [("rate", r"ключев\w+ ставк|ставк\w+ (?:снижен|повышен|сохранен)", (4.0, 30.0)),
              ("inflation", r"инфляци(?!онн\w+ ожидани)", (2.0, 30.0)),
              ("expectations", r"инфляционн\w+ ожидани", (4.0, 30.0))]
    stale = []
    for key, kw, (lo, hi) in checks:
        if key not in anchor:
            continue
        val = anchor[key][0]
        for m in re.finditer(kw, prose, re.IGNORECASE):
            window = prose[max(0, m.start() - 15): m.end() + 100]
            in_range = [float(n) for n in _numbers(window.replace(",", "."))
                        if lo <= float(n) <= hi]
            if in_range and not any(abs(n - val) < 0.01 for n in in_range):
                stale.append(key)
                break
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
    # кулдаун асимметричный: published держит 4 дня (значения не меняются чаще),
    # а rejected — только 1 день: отказ бывает багом ГЕЙТА (лимит 4 правок,
    # 2026-07-31 — 79 карточек в корзину), и после фикса гейта хвост должен
    # добираться следующей же волной, а не ждать 4 суток
    now = datetime.now(timezone.utc)
    if only_ticker:
        recent = set()
    else:
        pub_cut = now - timedelta(days=_MACRO_RETRY_DAYS)
        rej_cut = now - timedelta(days=1)
        rows_cd = (db.query(CardProseOverlay.ticker, CardProseOverlay.status,
                            CardProseOverlay.created_at)
                   .filter(CardProseOverlay.tab == "macro",
                           CardProseOverlay.kind == "fact",
                           CardProseOverlay.created_at >= rej_cut - timedelta(days=_MACRO_RETRY_DAYS)).all())
        recent = {t for t, st, ts in rows_cd
                  if (st == "published" and ts >= pub_cut) or (st == "rejected" and ts >= rej_cut)}
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


# ----------------------------- МАКРО-ИНТЕРПРЕТАЦИЯ (смысл, не только числа) -----------------------------
# Владелец 2026-08-01: «нужно чтобы содержание прям менялось — не перегенерация,
# а изменение устаревших вещей на актуальные». Факт-патч меняет ЧИСЛА; смысловые
# обороты («на июльском заседании может взять паузу» — заседание прошло, ЦБ снизил;
# «в мае рост цен почти остановился») остаются. Этот проход — вторая половина
# моста: те же точечные find/replace, но kind=interpretation (right to судить),
# grounding = полный контекст решения ЦБ (дата/размер/сигнал/следующее заседание).
_MACRO_INTERP_SYS = """Ты — аналитик-редактор платформы Basis (не брокер, без «купить/
продать» и целевых цен). Даны АКТУАЛЬНЫЙ макро-контекст (последнее решение ЦБ:
дата, ставка, сигнал регулятора, дата следующего заседания; инфляция; ожидания)
и ТЕКСТ макро-вкладки карточки компании. Найди УСТАРЕВШИЕ ПО СМЫСЛУ утверждения —
прошедшие заседания, упомянутые как будущие; «регулятор может взять паузу», если
решение уже принято; ссылки на старые месяцы как на «сейчас»; сигнал ЦБ, который
изменился — и верни точечные правки find/replace, приводящие ИМЕННО ЭТИ места в
соответствие актуальному контексту. Правь минимально: НЕ трогай компанию-специфику
(бизнес, маржа, прогнозы по компании), НЕ переписывай структуру, НЕ добавляй
собственных прогнозов сверх сигнала ЦБ. Если смысловых устареваний нет —
confirmed=false.
"""
_MACRO_INTERP_COOLDOWN_DAYS = 7


def _macro_interp_grounding(db: Session) -> str | None:
    """Контекст для смысловых правок: решение ЦБ целиком + инфляция/ожидания."""
    anchor = _macro_anchor(db)
    if not anchor:
        return None
    parts = [_macro_grounding(anchor)]
    from app.models.macro import RateMeeting
    rm = db.query(RateMeeting).order_by(RateMeeting.decision_date.desc()).first()
    if rm:
        parts.append(f"Последнее заседание ЦБ: {rm.decision_date.isoformat()}, "
                     f"ставка {rm.rate_value}%.")
        if rm.signal:
            parts.append(f"Сигнал регулятора: {rm.signal[:300]}")
        if rm.next_meeting_date:
            parts.append(f"Следующее заседание: {rm.next_meeting_date.isoformat()}")
    today = datetime.now(timezone.utc).date()
    parts.append(f"Сегодня: {today.isoformat()}")
    return "\n".join(parts)


def run_macro_interp(db: Session, batch: int = 8, only_ticker: str | None = None) -> dict:
    """Смысловая доводка макро-вкладок ПОСЛЕ фактов: очередь — тикеры со свежим
    published факт-патчем macro (вкладка была устаревшей и уже тронута числами),
    у которых нет свежей macro-интерпретации. Не слепой прогон всех карточек."""
    grounding = _macro_interp_grounding(db)
    if not grounding:
        return {"error": "нет макро-контекста"}
    cut_facts = datetime.now(timezone.utc) - timedelta(days=7)
    cut_interp = datetime.now(timezone.utc) - timedelta(days=_MACRO_INTERP_COOLDOWN_DAYS)
    if only_ticker:
        queue = [only_ticker.upper()]
    else:
        fact_ok = {r[0] for r in db.query(CardProseOverlay.ticker)
                   .filter(CardProseOverlay.tab == "macro", CardProseOverlay.kind == "fact",
                           CardProseOverlay.status == "published",
                           CardProseOverlay.created_at >= cut_facts).all()}
        interp_done = {r[0] for r in db.query(CardProseOverlay.ticker)
                       .filter(CardProseOverlay.tab == "macro",
                               CardProseOverlay.kind == "interpretation",
                               CardProseOverlay.created_at >= cut_interp).all()}
        queue = sorted(fact_ok - interp_done)[:batch]
    stats = {"queued": len(queue), "published": 0, "rejected": 0}
    for tk in queue:

        def _tb(p: str) -> str:
            return (f"Компания: {tk}. Вкладка: macro.\n\n"
                    f"АКТУАЛЬНЫЙ МАКРО-КОНТЕКСТ:\n{grounding}\n\n"
                    f"ТЕКСТ ВКЛАДКИ (правь точечно ТОЛЬКО смысловые устаревания):\n"
                    f"<<<\n{p[:8000]}\n>>>")

        row = _run_patch(db, tk, "macro", sys=_MACRO_INTERP_SYS + _JSON_ONLY,
                         task_builder=_tb, grounding_text=grounding,
                         kind="interpretation",
                         evidence_extra={"macro_interp": True})
        if row is not None:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_macro_interp: %s", stats)
    return stats


# =============================================================================
# ГЕОПОЛИТИКА И ИНСТИТУТЫ: доводка вкладок карточек по состоянию Обозревателя
#
# Владелец (2026-08-04): «нужно выстроить систему, где вкладка карточки
# обновляется с учётом оценки ситуации в Обозревателе и статей источников; нужен
# отдельный агент, который перестраивает вкладки с учётом новых вводных» — задача
# была поставлена по макро, и он же попросил сделать аналогично для гео и
# институтов.
#
# 🔴 ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ УЖЕ РАБОТАЮЩЕГО run_weekly_interp.
# Тот триггерится ВХОДНЫМ ПОТОКОМ: пришёл сигнал про конкретный тикер — правим
# его вкладку. Но геополитика и институты меняются не «новостью про компанию», а
# СРЕДОЙ: сместился балл очага, изменился сценарий, поехали замеры направлений.
# Такое изменение не порождает сигнала ни по одному тикеру, и вкладки молча
# устаревают — именно это владелец и увидел. Здесь очередь строится ОТ СРЕДЫ:
# кого затрагивает текущая картина Обозревателя.
#
# Кто в очереди:
#   • гео — тикеры из affected/sector_flags очагов барометра (кого очаг задевает
#     по мнению самого барометра) + компании затронутых секторов;
#   • институты — компании секторов из «зон передела» и из winners/losers
#     портрета.
# Cooldown не даёт гонять одно и то же по кругу; batch держит стоимость.
# =============================================================================
_ENV_INTERP_COOLDOWN_DAYS = 10
_ENV_BATCH = 8


# 🔴 Модель называет сектора ПРОЗОЙ: «нефтепереработка/downstream (удары по
# НПЗ)», «ставка-чувствительные: девелоперы, дюрация, IT», «морские перевозки».
# В БД же 13 фиксированных значений companies.sector. Прямой LIKE по такой
# строке не находит ничего — первый прогон дал ноль кандидатов при богатом
# контексте, и это выглядело как «никого не задевает».
# Поэтому: ищем в тексте сектора ключевые слова и переводим их в значения БД.
_SECTOR_KEYWORDS = {
    "Нефть и газ": ("нефт", "газ", "нпз", "downstream", "upstream", "спг", "топлив", "азс"),
    "Электроэнергетика": ("энергет", "электро", "генерац", "сет", "тэц", "тариф"),
    "Металлургия": ("металл", "сталь", "уголь", "золот", "руд", "алюмин", "никел"),
    "Финансы": ("банк", "финанс", "страхов", "биржа", "брокер", "расчёт", "расчет"),
    "Потребительский сектор": ("ритейл", "потребит", "продукт", "食", "торгов", "маркетплейс"),
    "IT-сектор": ("it", "айти", "софт", "технолог", "цифров", "интернет", "чип", "полупровод"),
    "Телеком": ("телеком", "связ", "оператор"),
    "Транспорт и логистика": ("логист", "транспорт", "перевоз", "порт", "судох", "танкер", "жд"),
    "Химия": ("хими", "удобрен", "агрохим"),
    "Машиностроение": ("машиностроен", "оборонк", "оборон", "впк", "судострое", "автопром"),
    "Девелопмент": ("девелоп", "застройщ", "недвижим", "строительств", "ипотек"),
    "Здравоохранение": ("здравоохран", "фарм", "медиц"),
}


def _map_to_db_sectors(raw: list[str]) -> list[str]:
    """Проза модели → значения companies.sector."""
    hit: set[str] = set()
    for s in raw:
        low = (s or "").lower()
        if not low:
            continue
        for db_sector, keys in _SECTOR_KEYWORDS.items():
            if any(k in low for k in keys):
                hit.add(db_sector)
    return sorted(hit)


def _tickers_of_sectors(db: Session, sectors: list[str]) -> list[str]:
    """Тикеры компаний названных секторов. Сектор берём ИЗ БД (companies.sector),
    а не из meta карточек: в файлах 97 разных значений против 13 чистых в базе,
    и они противоречат друг другу у трети компаний (память db-sector-is-truth)."""
    mapped = _map_to_db_sectors(sectors)
    if not mapped:
        return []
    rows = db.execute(text(
        "SELECT ticker FROM companies WHERE sector = ANY(:s) LIMIT 400"),
        {"s": mapped}).fetchall()
    return [r[0] for r in rows if r and r[0]]


def _recent_source_articles(db: Session, targets: tuple[str, ...], limit: int = 8,
                            days: int = 21) -> list[str]:
    """Свежие материалы первоисточников (ЦБ, ЦМАКП, re:Russia, Carnegie, ISW и
    прочие из ленты Обозревателя) по нужным доменам.

    🔴 Зачем отдельно от барометра. Барометр и портрет — это уже СВЁРНУТАЯ
    оценка: балл, сценарий, вывод. По ней видно, что среда сместилась, но не
    видно, ЧТО ИМЕННО произошло. Правку вкладки без конкретики модель делает
    общими словами («риски выросли»), а с конкретикой — привязывает к событию.
    Владелец в постановке прямо перечислил источники рядом с оценкой
    Обозревателя, а не вместо неё.
    """
    from app.models.geo_digest import GeoDigestArticle
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(targets),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(limit).all())
    out = []
    for r in rows:
        src = f" [{r.source_label}]" if getattr(r, "source_label", None) else ""
        date_s = r.published_at.isoformat() if r.published_at else ""
        out.append(f"  {date_s}{src} {r.title}: {(r.summary or '')[:280]}")
    return out


def _geo_env_grounding(db: Session) -> tuple[str | None, list[str]]:
    """Контекст «что сейчас в геополитике» + кого это задевает.

    Собирается из ТРЁХ слоёв Обозревателя, а не из одного: балл и сценарий очага
    (barometer), человеческий разбор очага (портрет) и свежая лента. Один слой
    даёт либо голое число, либо прозу без привязки к движению.
    """
    from app.services import barometer_store
    from app.services.geo_conflict_profile import get_latest as geo_profiles

    row = barometer_store.current_row(db, "geo")
    payload = (row.payload or {}) if row else {}
    if not payload:
        return None, []

    parts: list[str] = []
    sectors: set[str] = set()
    tickers: set[str] = set()

    baro = payload.get("barometer") or {}
    if baro.get("overall") is not None:
        parts.append(f"Острота геополитической среды: {baro['overall']} из 5 "
                     f"(5 — максимальный риск). {baro.get('label') or ''}".strip())
    sc = payload.get("scenario") or {}
    if sc.get("current_lean"):
        parts.append(f"Базовый сценарий сейчас: {sc['current_lean']}.")

    for key, reg in (payload.get("regions") or {}).items():
        if not isinstance(reg, dict):
            continue
        head = f"Очаг «{reg.get('label') or key}»: {reg.get('direction') or ''}"
        if (reg.get("barometer") or {}).get("overall") is not None:
            head += f", острота {reg['barometer']['overall']}/5"
        parts.append(head.strip(" ,") + ".")
        if reg.get("summary"):
            parts.append(f"  {reg['summary'][:400]}")
        for f in (reg.get("sector_flags") or [])[:6]:
            if isinstance(f, dict) and f.get("sector"):
                sectors.add(f["sector"])
                parts.append(f"  Сектор «{f['sector']}» — {f.get('direction') or ''}: "
                             f"{(f.get('reasoning') or '')[:180]}")
        for a in (reg.get("affected") or [])[:8]:
            if isinstance(a, str):
                sectors.add(a)

    profiles = geo_profiles(db) or {}
    for key, prof in profiles.items():
        if key.startswith("_") or not isinstance(prof, dict):
            continue
        if prof.get("why_matters"):
            parts.append(f"Почему очаг «{key}» важен рынку: {prof['why_matters'][:300]}")
        for w in (prof.get("watchpoints") or [])[:2]:
            if isinstance(w, dict) and w.get("signal"):
                parts.append(f"  За чем следить: {w['signal'][:160]}")

    for t in (payload.get("affected_tickers") or [])[:40]:
        if isinstance(t, str):
            tickers.add(t.upper())

    tickers.update(_tickers_of_sectors(db, sorted(sectors)))

    arts = _recent_source_articles(db, ("svo", "middle_east", "atr"))
    if arts:
        parts.append("СВЕЖИЕ МАТЕРИАЛЫ ИСТОЧНИКОВ (что конкретно произошло):")
        parts.extend(arts)

    parts.append(f"Сегодня: {datetime.now(timezone.utc).date().isoformat()}")
    return "\n".join(parts), sorted(tickers)


def _inst_env_grounding(db: Session) -> tuple[str | None, list[str]]:
    """Контекст «что сейчас с правилами игры» + кого это задевает."""
    from app.services import barometer_store
    from app.services.institutions_profile import get_latest as inst_profile
    from app.services.institutions_domains import get_latest as inst_domains

    row = barometer_store.current_row(db, "inst")
    payload = (row.payload or {}) if row else {}
    prof = inst_profile(db) or {}
    doms = inst_domains(db) or {}
    if not payload and not prof:
        return None, []

    parts: list[str] = []
    sectors: set[str] = set()

    baro = payload.get("barometer") or {}
    if baro.get("overall") is not None:
        parts.append(f"Оценка институциональной среды: {baro['overall']} из 5 "
                     f"(выше — надёжнее правила).")
    if (payload.get("scenario") or {}).get("current"):
        parts.append(f"Текущий сценарий: {payload['scenario']['current']}.")

    if prof.get("plain", {}).get("what_happens"):
        parts.append(f"Что происходит: {prof['plain']['what_happens'][:400]}")
    if prof.get("plain", {}).get("what_it_means"):
        parts.append(f"Что это значит для рынка: {prof['plain']['what_it_means'][:400]}")
    for f in (prof.get("pushing_worse") or [])[:4]:
        if isinstance(f, dict):
            parts.append(f"  Толкает к ухудшению: {f.get('factor', '')[:160]}")
    for f in (prof.get("pushing_better") or [])[:3]:
        if isinstance(f, dict):
            parts.append(f"  Работает в обратную сторону: {f.get('factor', '')[:160]}")

    # Замеры направлений: в контекст идут только те, что ДВИНУЛИСЬ или стоят
    # низко — иначе десять строк «без изменений» вытесняют полезное.
    for d in (doms.get("domains") or []):
        if not isinstance(d, dict):
            continue
        moved = "ухудш" in str(d.get("direction") or "") or "улучш" in str(d.get("direction") or "")
        low = isinstance(d.get("score"), (int, float)) and float(d["score"]) <= 2.0
        if moved or low:
            parts.append(f"  {d.get('label')}: {d.get('score')}/5, {d.get('direction')} — "
                         f"{(d.get('verdict') or '')[:150]}")

    for z in (prof.get("redistribution_zones") or []):
        if isinstance(z, dict):
            for sx in (z.get("sectors") or []):
                if isinstance(sx, str):
                    sectors.add(sx)
            parts.append(f"  Зона передела «{z.get('zone')}»: {(z.get('what') or '')[:180]}")
    wl = prof.get("winners_losers") or {}
    for side in ("winners", "losers"):
        for x in (wl.get(side) or []):
            if isinstance(x, dict) and x.get("who"):
                sectors.add(x["who"])

    arts = _recent_source_articles(db, ("institutions", "macro"))
    if arts:
        parts.append("СВЕЖИЕ МАТЕРИАЛЫ ИСТОЧНИКОВ (что конкретно произошло):")
        parts.extend(arts)

    parts.append(f"Сегодня: {datetime.now(timezone.utc).date().isoformat()}")
    return "\n".join(parts), _tickers_of_sectors(db, sorted(sectors))


_ENV_INTERP_SYS = """Ты — аналитик-редактор платформы Basis (не брокер, без
«купить/продать» и целевых цен). Даны АКТУАЛЬНОЕ СОСТОЯНИЕ СРЕДЫ (оценка
Обозревателя) и ТЕКСТ вкладки карточки компании.

Найди в тексте утверждения, которые УСТАРЕЛИ ПО СМЫСЛУ относительно этого
состояния: описанный сценарий сменился; названо «текущим» то, что уже прошло;
направление среды в тексте противоречит нынешнему; риск описан как возможный,
хотя он уже реализовался (или наоборот — как реализованный, хотя откатился).
Верни точечные правки find/replace ТОЛЬКО для этих мест.

ПРАВЬ МИНИМАЛЬНО. Не трогай специфику компании (бизнес, активы, конкретные
цифры её отчётности), не переписывай структуру, не добавляй прогнозов сверх
переданного состояния среды. Если смысловых устареваний нет — confirmed=false.

🔴 Никаких фамилий и имён должностных лиц; про государственные органы — только
наблюдаемые изменения правил и их экономические последствия, без оценок мотивов.
"""


def _run_env_interp(db: Session, *, tab: str, grounding: str, queue: list[str],
                    kind: str, sys_prompt: str | None = None) -> dict:
    stats = {"queued": len(queue), "published": 0, "rejected": 0}
    for tk in queue:
        def _tb(p: str, _tk=tk) -> str:
            return (f"Компания: {_tk}. Вкладка: {tab}.\n\n"
                    f"АКТУАЛЬНОЕ СОСТОЯНИЕ СРЕДЫ:\n{grounding}\n\n"
                    f"ТЕКСТ ВКЛАДКИ (правь точечно ТОЛЬКО смысловые устаревания):\n"
                    f"<<<\n{p[:8000]}\n>>>")

        row = _run_patch(db, tk, tab, sys=(sys_prompt or _ENV_INTERP_SYS) + _JSON_ONLY,
                         task_builder=_tb, grounding_text=grounding,
                         kind=kind, evidence_extra={"env_interp": tab})
        if row is not None:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.env_interp[%s]: %s", tab, stats)
    return stats


def _env_queue(db: Session, tab: str, candidates: list[str], batch: int) -> list[str]:
    """Кого правим в этот прогон: из кандидатов убираем тех, кому вкладку уже
    трогали недавно. Так очередь сама двигается по компаниям, а не долбит
    первые восемь по алфавиту."""
    cut = datetime.now(timezone.utc) - timedelta(days=_ENV_INTERP_COOLDOWN_DAYS)
    done = {r[0] for r in db.query(CardProseOverlay.ticker)
            .filter(CardProseOverlay.tab == tab,
                    CardProseOverlay.created_at >= cut).all()}
    return [t for t in candidates if t not in done][:batch]


def run_geo_env_interp(db: Session, batch: int = _ENV_BATCH,
                       only_ticker: str | None = None) -> dict:
    """Доводка вкладок «Геополитика» карточек под текущее состояние очагов."""
    grounding, candidates = _geo_env_grounding(db)
    if not grounding:
        return {"error": "нет гео-контекста"}
    queue = [only_ticker.upper()] if only_ticker else _env_queue(db, "geo", candidates, batch)
    return _run_env_interp(db, tab="geo", grounding=grounding, queue=queue,
                           kind="interpretation")


def run_inst_env_interp(db: Session, batch: int = _ENV_BATCH,
                        only_ticker: str | None = None) -> dict:
    """Доводка вкладок «Институты» карточек под текущее состояние правил игры."""
    grounding, candidates = _inst_env_grounding(db)
    if not grounding:
        return {"error": "нет институционального контекста"}
    queue = [only_ticker.upper()] if only_ticker else _env_queue(db, "institutions",
                                                                candidates, batch)
    return _run_env_interp(db, tab="institutions", grounding=grounding, queue=queue,
                           kind="interpretation")


# =============================================================================
# МАКРО: доводка вкладки под ТЕКУЩУЮ макросреду, с приоритетом по деньгам
#
# Владелец (2026-08-04): «нужно, чтобы вкладка макроэкономика у карточек
# обновлялась с учётом оценки макроситуации в Обозревателе, статей ЦБ/ЦМАКП/
# Re:Russia и новых вводных».
#
# Что уже было и почему этого мало. `run_macro_interp` (выше) правит вкладку под
# ПОСЛЕДНЕЕ РЕШЕНИЕ ЦБ — ставка, инфляция, ожидания. Но макросреда — это не только
# ЦБ: с начала июля, когда писалось большинство разборов, Brent ушёл с ~$69 к ~$90,
# а рубль с 72 к 79. Такие сдвиги решением ЦБ не описываются и мимо той очереди
# проходили целиком.
#
# Два отличия от соседних env-доводок (гео/институты):
#   1. ОЧЕРЕДЬ ПО ДЕНЬГАМ, а не по алфавиту. `macro_drift` считает, насколько
#      условия ушли от тех, при которых писался разбор, и прогоняет этот сдвиг
#      через КОЭФФИЦИЕНТЫ ЧУВСТВИТЕЛЬНОСТИ самой карточки. Наверх очереди попадает
#      не самый старый разбор, а тот, чьё расхождение с реальностью дороже стоит:
#      у защитной компании ставка может ходить на 2 п.п. без последствий, у
#      нефтяника $35 по нефти переворачивают картину.
#   2. ПЕРСОНАЛЬНЫЙ КОНТЕКСТ. Каждой компании в задание идёт её собственный дрейф
#      («нефть 55 → 90 с момента разбора»), а не только общая сводка среды.
# =============================================================================
_MACRO_ENV_COOLDOWN_DAYS = 10
# Отказ гейта — не приговор: через двое суток пробуем снова (причина могла быть
# устранена правкой кода), но не в тот же прогон, чтобы не жечь бюджет на цикле.
_MACRO_REJECT_RETRY_DAYS = 2


def _num_forms(v: float) -> str:
    """Число во всех формах, которые может написать аналитик.

    🔴 Найдено на боевом прогоне (SIBN, 2026-08-04): правка была верной по сути, но
    гейт отклонил её с `ungrounded_numbers: ['84', '79.5']` — в заземлении лежали
    точные «83,68» и «79,46», а редактор естественно написал «около $84» и «79,5».
    Требовать от прозы двух знаков после запятой бессмысленно, а пускать любые числа
    нельзя. Компромисс: заземляем САМО значение вместе с его законными округлениями —
    выдуманное «90» по-прежнему не пройдёт.
    """
    forms = {f"{v:.2f}".rstrip("0").rstrip("."), f"{v:.1f}".rstrip("0").rstrip("."),
             str(int(round(v)))}
    return " ".join(sorted(forms | {f.replace(".", ",") for f in forms}))


def _macro_env_grounding(db: Session) -> str | None:
    """Состояние макросреды: числа + выпуск Обозревателя + свежая аналитика.

    Это же текст ЗАЗЕМЛЕНИЯ: гейт требует, чтобы каждое новое число в правке
    встречалось здесь. Поэтому кладём значения, а не только словесные выводы.
    """
    parts = []
    anchor = _macro_anchor(db)
    if anchor:
        parts.append(_macro_grounding(anchor))
        # Те же значения в округлённых формах — иначе «ставка ~14%» не заземляется.
        parts.append("Допустимые написания: "
                     + "; ".join(_num_forms(v) for v, _ in anchor.values()))
    from sqlalchemy import text as _sql
    for code, metric, label, unit in (("oil_brent", "level", "Нефть Brent", "$/барр"),
                                      ("urals", "level", "Нефть Urals", "$/барр"),
                                      ("usdrub", "level", "Курс USD/RUB", "₽")):
        row = db.execute(_sql(
            "SELECT value, as_of FROM macro_data_points WHERE indicator_code=:c "
            "AND metric=:m ORDER BY as_of DESC LIMIT 1"), {"c": code, "m": metric}).first()
        if row:
            parts.append(f"{label}: {_num_forms(float(row[0]))} {unit} "
                         f"(на {row[1].isoformat()})")
    if not parts:
        return None

    # Оценка макроситуации Обозревателя — то самое «второе мнение платформы»,
    # которое владелец просил донести до карточек.
    try:
        from app.models.macro import MacroInterpretation
        issue = (db.query(MacroInterpretation)
                 .order_by(MacroInterpretation.generated_at.desc()).first())
        sections = (issue.sections or {}) if issue else {}
        if sections.get("headline"):
            parts.append(f"\nОЦЕНКА ОБОЗРЕВАТЕЛЯ ({issue.generated_at.date().isoformat()}): "
                         f"{str(sections['headline'])[:400]}")
        for thesis in (sections.get("theses") or [])[:4]:
            if isinstance(thesis, dict) and thesis.get("claim"):
                parts.append(f"- {str(thesis['claim'])[:220]}")
    except Exception:  # noqa: BLE001
        logger.warning("macro_env: выпуск Обозревателя недоступен", exc_info=True)

    # Аналитика ЦБ / ЦМАКП / Re:Russia: то, чего нет в рядах — трактовка и повестка.
    try:
        rows = db.execute(_sql(
            "SELECT source, title, summary, published_at::date FROM macro_analytics_docs "
            "WHERE published_at >= now() - interval '45 days' "
            "ORDER BY published_at DESC LIMIT 5")).fetchall()
        if rows:
            parts.append("\nСВЕЖАЯ АНАЛИТИКА:")
            for source, title, summary, published in rows:
                parts.append(f"- [{source} {published}] {str(title)[:110]}: "
                             f"{str(summary or '')[:260]}")
    except Exception:  # noqa: BLE001
        logger.warning("macro_env: аналитика недоступна", exc_info=True)
    parts.append(f"\nСегодня: {datetime.now(timezone.utc).date().isoformat()}")
    return "\n".join(parts)


def _drift_note(item: dict) -> str:
    """Персональная часть задания: что сдвинулось именно у этой компании."""
    lines = [f"ЧТО ИЗМЕНИЛОСЬ С МОМЕНТА РАЗБОРА (разбор от {item.get('as_of')}, "
             f"{item.get('days_old')} дн. назад):"]
    for spec in (item.get("drift") or {}).values():
        lines.append(f"- {spec['title']}: было {spec['was']} {spec['unit']}, "
                     f"стало {spec['now']} {spec['unit']}")
    impact = item.get("impact_pct")
    if impact is not None:
        lines.append(f"По коэффициентам чувствительности САМОЙ карточки это ≈{impact}% "
                     f"годовой {item.get('impact_base') or 'прибыли'} — то есть разбор "
                     f"писался в заметно другой обстановке.")
    return "\n".join(lines)


def run_macro_env_interp(db: Session, batch: int = _ENV_BATCH,
                         only_ticker: str | None = None) -> dict:
    """Доводка вкладок «Макроэкономика» под текущую макросреду.

    Очередь — из детектора дрейфа (дороже расхождение → раньше в очереди), минус
    те, кому вкладку уже трогали в окне кулдауна.
    """
    grounding = _macro_env_grounding(db)
    if not grounding:
        return {"error": "нет макро-контекста"}
    from app.services.macro_drift import company_drift, drift_queue

    if only_ticker:
        item = company_drift(db, only_ticker.upper())
        queue = [item] if item else []
    else:
        # 🔴 Кулдаун разный для успеха и отказа. Опубликованную правку повторять рано:
        # вкладку только что тронули. А ОТКЛОНЁННУЮ гейтом — наоборот, надо
        # перепробовать, когда причина отказа устранена: на боевом прогоне SIBN
        # отвалился из-за незаземлённого округления, фикс выехал через час, а компания
        # была бы заперта на десять дней и молча осталась с устаревшим разбором.
        now = datetime.now(timezone.utc)
        fresh_ok = {r[0] for r in db.query(CardProseOverlay.ticker)
                    .filter(CardProseOverlay.tab == "macro",
                            CardProseOverlay.status == "published",
                            CardProseOverlay.created_at >= now - timedelta(
                                days=_MACRO_ENV_COOLDOWN_DAYS)).all()}
        retry_wait = {r[0] for r in db.query(CardProseOverlay.ticker)
                      .filter(CardProseOverlay.tab == "macro",
                              CardProseOverlay.status == "rejected",
                              CardProseOverlay.created_at >= now - timedelta(
                                  days=_MACRO_REJECT_RETRY_DAYS)).all()}
        done = fresh_ok | retry_wait
        queue = [i for i in drift_queue(db, limit=200) if i["ticker"] not in done][:batch]

    stats = {"queued": len(queue), "published": 0, "rejected": 0}
    for item in queue:
        ticker = item["ticker"]
        personal = _drift_note(item)
        full_grounding = f"{grounding}\n\n{personal}"

        def _tb(prose: str, _tk=ticker, _p=personal) -> str:
            return (f"Компания: {_tk}. Вкладка: macro.\n\n"
                    f"АКТУАЛЬНОЕ СОСТОЯНИЕ МАКРОСРЕДЫ:\n{grounding}\n\n{_p}\n\n"
                    f"ТЕКСТ ВКЛАДКИ (правь точечно ТОЛЬКО смысловые устаревания):\n"
                    f"<<<\n{prose[:8000]}\n>>>")

        row = _run_patch(db, ticker, "macro", sys=_ENV_INTERP_SYS + _JSON_ONLY,
                         task_builder=_tb, grounding_text=full_grounding,
                         kind="interpretation",
                         evidence_extra={"macro_env": True,
                                         "drift": item.get("drift"),
                                         "impact_pct": item.get("impact_pct")})
        if row is not None:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_macro_env_interp: %s", stats)
    return stats


# =============================================================================
# ВКЛАДКА «РЫНКИ»: доводка под состояние ОТРАСЛИ
#
# Владелец (2026-08-07): «нужно чтобы карточки самообновлялись» — по рынкам и
# governance, после того как то же сделано для гео, институтов и макро.
#
# 🔴 ПОЧЕМУ ОЧЕРЕДЬ СТРОИТСЯ ИНАЧЕ, ЧЕМ У ГЕО И ИНСТИТУТОВ.
# Там среда ОДНА на всех: сместился балл очага — задело всех, кого этот очаг
# касается. Здесь среда РАЗНАЯ у каждой отрасли: сталевары и золотодобытчики
# живут в противоположных фазах цикла (в первом же прогоне барометра чёрная
# металлургия 1.5/5, цветная 4.5/5). Поэтому очередь — не «кого задевает», а
# «чья отрасль сдвинулась»: берём отрасли с движением балла или с низким
# баллом и правим карточки их компаний.
#
# 🔴 ЧЕГО ЗДЕСЬ НЕЛЬЗЯ ДЕЛАТЬ — ВЫДУМЫВАТЬ ДОЛИ РЫНКА.
# Проза «Рынков» полна утверждений вида «Северсталь 33%, ММК 30%, НЛМК 23%».
# Источника долей у нас нет ни одного (в реестрах источников это отмечено как
# дыра почти во всех секторах). Модель, которой велено «обновить рынки», такие
# числа охотно перепишет — и получится выдуманная конкретика вместо устаревшей.
# Отсюда отдельное правило в промпте и проверка в гейте патчера: число в замене
# обязано присутствовать во входном тексте.
# =============================================================================
_MARKETS_INTERP_SYS = """Ты — аналитик-редактор платформы Basis (не брокер, без
«купить/продать» и целевых цен). Даны СОСТОЯНИЕ ОТРАСЛИ (оценка Обозревателя),
цены на её продукцию и ТЕКСТ вкладки «Рынки» карточки компании.

Найди в тексте утверждения, устаревшие относительно этого состояния: описана
фаза цикла, которая сменилась; спрос назван растущим, хотя отрасль сжимается
(или наоборот); цена товара в тексте разошлась с переданной; риск описан как
возможный, хотя реализовался. Верни точечные правки find/replace ТОЛЬКО для них.

🔴 ЗАПРЕЩЕНО МЕНЯТЬ ЧИСЛА, КОТОРЫХ НЕТ ВО ВХОДНЫХ ДАННЫХ. Особенно доли рынка
компаний и конкурентов, объёмы производства и потребления, ёмкость рынка: если
переданные данные их не содержат — НЕ ТРОГАЙ такие предложения вообще. Лучше
оставить старое число с прежней датой, чем поставить выдуманное свежее.

ПРАВЬ МИНИМАЛЬНО. Не трогай специфику компании (её активы, проекты, стратегию),
не переписывай структуру, не добавляй прогнозов сверх переданного состояния.
Если смысловых устареваний нет — confirmed=false.
"""


def _sector_key_for(db: Session, ticker: str, sector_map: dict) -> str | None:
    """Ключ отрасли барометра для тикера. Барометр делит металлургию на чёрную и
    цветную, а в БД это один сектор — поэтому сначала ищем по явным спискам
    тикеров, и только потом по значению companies.sector."""
    from app.services.sector_barometer import SECTORS
    for s in SECTORS:
        only = s.get("only_tickers")
        if only and ticker in only:
            return s["key"]
    db_sector = sector_map.get(ticker)
    if not db_sector:
        return None
    for s in SECTORS:
        if not s.get("only_tickers") and db_sector in s["db_sectors"]:
            return s["key"]
    return None


def _markets_env_grounding(db: Session, sec: dict, tickers: list[str]) -> str:
    """Контекст для отрасли: оценка барометра + цены её товаров + свежая лента."""
    from app.services.sector_barometer import _sector_prices

    parts = [f"ОТРАСЛЬ: {sec.get('label')}",
             f"Оценка состояния: {sec.get('score')} из 5 "
             f"(1 — кризис, 3 — обычное состояние, 5 — подъём), "
             f"направление: {sec.get('direction')}."]
    if sec.get("headline"):
        parts.append(f"Что происходит: {sec['headline']}")
    if sec.get("what_happens"):
        parts.append(f"  {sec['what_happens'][:500]}")
    if sec.get("winners"):
        parts.append(f"В лучшем положении: {sec['winners'][:220]}")
    if sec.get("losers"):
        parts.append(f"В худшем: {sec['losers'][:220]}")

    prices = _sector_prices(db, tickers)
    if prices:
        parts.append("ЦЕНЫ НА ПРОДУКЦИЮ ОТРАСЛИ (текущие, из наших рядов):")
        parts.extend(prices)

    # Сначала обзоры отраслевых источников по ЭТОЙ отрасли (МЭА, ОПЕК, ассоциации —
    # привязка точная), затем добор из общей бизнес/макро-ленты. Иначе правка вкладки
    # «Рынки» шла бы от общих новостей, а рынок компании — предмет отраслевой аналитики.
    arts = _recent_source_articles(db, (f"sec:{sec.get('key')}",), limit=6, days=45)
    if len(arts) < 5:
        arts += _recent_source_articles(db, ("business", "macro"), limit=5 - len(arts))
    if arts:
        parts.append("СВЕЖИЕ МАТЕРИАЛЫ (что конкретно произошло):")
        parts.extend(arts)

    parts.append(f"Сегодня: {datetime.now(timezone.utc).date().isoformat()}")
    return "\n".join(parts)


def run_markets_env_interp(db: Session, batch: int = _ENV_BATCH,
                           only_ticker: str | None = None) -> dict:
    """Доводка вкладок «Рынки» под текущее состояние отраслей.

    Очередь: отрасли, которые сдвинулись с прошлого замера ИЛИ стоят низко
    (≤2.5 — там устаревший оптимистичный текст вреднее всего), затем их
    компании с учётом cooldown.
    """
    from app.services.sector_barometer import get_latest as sector_latest

    baro = sector_latest(db)
    sectors = baro.get("sectors") or []
    if not sectors:
        return {"error": "отраслевой барометр пуст"}

    moved = {c.get("key") for c in (baro.get("changes") or [])}
    # Приоритет: сначала сдвинувшиеся, потом кризисные, потом остальные —
    # так батч тратится на отрасли, где проза точно разошлась с реальностью.
    ranked = sorted(sectors, key=lambda s: (
        0 if s.get("key") in moved else 1,
        float(s.get("score") or 3),
    ))

    sector_map = {r[0]: r[1] for r in db.execute(text(
        "SELECT ticker, sector FROM companies WHERE sector IS NOT NULL")).fetchall()}

    stats = {"queued": 0, "published": 0, "rejected": 0, "sectors": []}
    left = batch
    for sec in ranked:
        if left <= 0 and not only_ticker:
            break
        from app.services.sector_barometer import _sector_tickers, SECTORS
        meta = next((s for s in SECTORS if s["key"] == sec.get("key")), None)
        if not meta:
            continue
        tickers = _sector_tickers(db, meta)
        if only_ticker:
            if only_ticker.upper() not in tickers:
                continue
            queue = [only_ticker.upper()]
        else:
            queue = _env_queue(db, "markets", tickers, min(left, 3))
        if not queue:
            continue

        grounding = _markets_env_grounding(db, sec, tickers)
        res = _run_env_interp(db, tab="markets", grounding=grounding, queue=queue,
                              kind="interpretation", sys_prompt=_MARKETS_INTERP_SYS)
        stats["queued"] += res.get("queued", 0)
        stats["published"] += res.get("published", 0)
        stats["rejected"] += res.get("rejected", 0)
        stats["sectors"].append(sec.get("key"))
        left -= len(queue)
        if only_ticker:
            break

    logger.info("card_prose_patcher.run_markets_env_interp: %s", stats)
    return stats


# ============================================================================
# СВЕЖЕСТЬ РАЗБОРОВ БАЗОВЫХ АКТИВОВ ФЬЮЧЕРСОВ
# Владелец 2026-08-07: «чтобы в карточках по облигациям/фьючерсам/фондам информация
# тоже обновлялась, а не была статичным json». Проверено на бою 2026-08-08: разборы
# датированы началом июня и содержат цены того дня как ТЕКУЩИЕ — «Brent торгуется
# около $94/баррель», «золото около $4 330 за унцию». Это не устаревший нюанс, а
# прямо неверное число на живой карточке.
#
# Патчим разбор АКТИВА (futures_assets/<код>/analysis.md), а не контракта: один
# разбор обслуживает все контракты на актив, а контракты истекают ежеквартально —
# правка контракта умерла бы вместе с ним.
# ============================================================================
_FUT_ASSET_SYS = """Ты — аналитик-редактор платформы Basis (не брокер, без
«купить/продать» и целевых цен). Дан разбор БАЗОВОГО АКТИВА фьючерса и АКТУАЛЬНЫЕ
РЫНОЧНЫЕ ДАННЫЕ по нему.

Твоя задача — ТОЧЕЧНО поправить в тексте то, что разошлось с реальностью:
• цены и уровни, названные текущими, если фактическая цена другая;
• даты и периоды («на начало июня», «в мае») — если данные уже за другой период;
• утверждения о направлении движения, которые фактические числа опровергают
  («откатился с уровней выше X», если цена с тех пор выросла).

🔴 ЖЁСТКИЕ ПРАВИЛА:
• бери числа ТОЛЬКО из блока актуальных данных, ничего не додумывай и не округляй
  «примерно»; если нужного числа в данных нет — этот фрагмент НЕ ТРОГАЙ;
• не переписывай разбор целиком: механика контракта, гарантийное обеспечение,
  структура рынка, факторы спроса — всё это не устаревает от смены цены;
• сохраняй эпистемические пометки в исходном виде (факт / оценка / суждение);
• указывай дату актуального значения там, где в тексте была дата старого;
• никаких прогнозов и целевых цен от себя."""


def _fut_asset_grounding(db: Session, code: str) -> str:
    """Живые данные по активу: ближний контракт, кривая по срокам, товарный ряд."""
    parts = [f"АКТИВ: {code}", f"Сегодня: {datetime.now(timezone.utc).date().isoformat()}"]
    rows = db.execute(text("""
        SELECT secid, settle_price, expiration_date
        FROM futures
        WHERE asset_code = :a AND settle_price IS NOT NULL
          AND expiration_date >= CURRENT_DATE
        ORDER BY expiration_date LIMIT 4
    """), {"a": code}).fetchall()
    if rows:
        parts.append("ФЬЮЧЕРСЫ НА ЭТОТ АКТИВ (расчётная цена, ближние контракты):")
        for r in rows:
            parts.append(f"  {r[0]} — {float(r[1]):g}, экспирация {r[2]}")
        if len(rows) > 1:
            near, far = float(rows[0][1]), float(rows[-1][1])
            shape = "контанго (дальние дороже)" if far > near else (
                "бэквордация (дальние дешевле)" if far < near else "плоская кривая")
            parts.append(f"  Форма кривой сейчас: {shape}")
    # Товарный ряд Всемирного банка/наших фидов, если для актива он заведён.
    series = _FUT_ASSET_SERIES.get(code)
    if series:
        row = db.execute(text("""
            SELECT value, as_of FROM macro_data_points
            WHERE indicator_code = :k AND metric = 'level'
            ORDER BY as_of DESC LIMIT 1
        """), {"k": series}).fetchone()
        if row:
            title = db.execute(text("SELECT title FROM macro_indicators WHERE code = :k"),
                               {"k": series}).scalar() or series
            parts.append(f"СПОТ-РЯД: {title} — {float(row[0]):g} (на {row[1]})")
        else:
            # Код ряда в таблице есть, а данных нет — почти всегда опечатка в коде.
            # Молча это выглядит как «у актива просто нет спота» (я так и ошибся,
            # написав brent_price вместо oil_brent), поэтому пишем в лог.
            logger.warning("futures_asset %s: ряд %s пуст — проверь код в _FUT_ASSET_SERIES",
                           code, series)
    return "\n".join(parts)


# Актив → код спот-ряда. Явная таблица, а не угадывание по имени: молча не совпавший
# код дал бы разбор без спот-цены и никакой ошибки.
_FUT_ASSET_SERIES = {
    "BR": "oil_brent",       # спот-ряд, обновляется ежедневно (wb_oil_brent — месячный)
    "GOLD": "wb_gold",
    "SILV": "wb_silver",
    "NG": "wb_gas_us",       # Henry Hub — базис фьючерса NG на МосБирже
    "WHEAT": "wb_wheat",
}


def run_futures_asset_facts(db: Session, batch: int = 4,
                            only_code: str | None = None) -> dict:
    """Доводка разборов базовых активов фьючерсов под живые цены."""
    codes = ([only_code.upper()] if only_code else
             sorted(p.name for p in FUTURES_ASSETS_DIR.iterdir()
                    if p.is_dir() and (p / "analysis.md").exists()))
    if not only_code:
        codes = _env_queue(db, "futures_asset", codes, batch)
    stats = {"queued": len(codes), "published": 0, "rejected": 0, "codes": codes}
    for code in codes:
        grounding = _fut_asset_grounding(db, code)
        if "ФЬЮЧЕРСЫ НА ЭТОТ АКТИВ" not in grounding:
            # нет ни одного живого контракта — править нечем, гадать нельзя
            stats["rejected"] += 1
            continue

        def _tb(p: str, _g=grounding) -> str:
            return (f"АКТУАЛЬНЫЕ РЫНОЧНЫЕ ДАННЫЕ:\n{_g}\n\n"
                    f"РАЗБОР АКТИВА (правь точечно только разошедшееся с данными):\n"
                    f"<<<\n{p[:8000]}\n>>>")

        row = _run_patch(db, code, "futures_asset", sys=_FUT_ASSET_SYS + _JSON_ONLY,
                         task_builder=_tb, grounding_text=grounding,
                         kind="fact", strict_numbers=True,
                         evidence_extra={"futures_asset": code})
        if row is not None:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_prose_patcher.run_futures_asset_facts: %s", stats)
    return stats
