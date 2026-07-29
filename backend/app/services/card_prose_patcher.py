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

_MAX_EDITS = 4          # мало правок за раз → вывод агента не упирается в 1600 токенов
_MAX_FIND_LEN = 200     # якорь find — КОРОТКИЙ (≤ предложение): против обрезки/экранирования JSON
_FRESH_DAYS = 10
_BATCH_CAP = 5

# прогнозные/оценочные конструкции — факт-патч НЕ добавляет суждение о будущем
_FORBIDDEN = re.compile(
    r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет|целев\w+\s+цен|приведёт\s+к|"
    r"ожида(ем|ется)|вырастет\s+до|упадёт\s+до|прогнозиру|потенциал\s+рост|апсайд",
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
    return re.findall(r"\d+[.,]?\d*", s or "")


# нормализация для ПОИСКА find в прозе — 1:1 (длина сохраняется, чтобы индексы
# совпадали): виды тире → «-», неразрывные/узкие пробелы → обычный. Иначе валидная
# правка не находит место из-за «–» vs «-» и т.п.
_MATCH_NORM = str.maketrans({
    "–": "-", "—": "-", "−": "-", "‑": "-", " ": " ", " ": " ", " ": " ",
})


def _norm_match(s: str) -> str:
    return s.translate(_MATCH_NORM)


def _apply_and_gate(prose: str, result: dict, signal_text: str) -> tuple[str | None, list[str]]:
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
    allowed_nums = (set(_numbers(signal_text.replace(",", ".")))
                    | set(_numbers(prose.replace(",", "."))))
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
        if cnt == 0:
            notes.append(f"edit{i}:find_not_in_prose")
            continue
        if cnt > 1:
            notes.append(f"edit{i}:find_ambiguous({cnt})")
            continue
        if len(repl) > len(find) + 200:
            notes.append(f"edit{i}:replace_too_long")
            continue
        if _FORBIDDEN.search(repl):
            notes.append(f"edit{i}:forbidden")
            continue
        # число в replace, которого НЕТ в find, обязано быть обосновано (сигнал/проза)
        new_nums = set(_numbers(repl.replace(",", "."))) - set(_numbers(find.replace(",", ".")))
        ungrounded = [n for n in new_nums if n not in allowed_nums]
        if ungrounded:
            notes.append(f"edit{i}:ungrounded_numbers:{ungrounded[:3]}")
            continue
        idx = n_patched.find(n_find)  # применяем правку по оригинальному span
        patched = patched[:idx] + repl + patched[idx + len(find):]

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
               evidence_extra: dict | None = None) -> CardProseOverlay | None:
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
                          max_tokens=2000, temperature=0.1)
    except LLMError as e:
        result, stopped = None, f"llm_error:{str(e)[:60]}"
    if isinstance(result, dict):
        patched, notes = _apply_and_gate(prose, result, grounding_text)
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
        f"- {r.published_at} [{r.source_key}] {r.title}: {(r.summary or '')[:160]}"
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
