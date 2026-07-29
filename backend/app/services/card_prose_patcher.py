"""Авто-свежесть ПРОЗЫ вкладок карточки — патчер (план docs/prose-freshness-plan.md).

Владелец (2026-07-29): текст разборов должен сам обновляться — ФАКТЫ дневным
кроном, ИНТЕРПРЕТАЦИЯ недельным; БЕЗ черновика (сразу published, гейт — барьер);
задача НЕ перегенерить, а поправить ТОЛЬКО там, где входной поток показал
изменение. Дизайн ревью advisor.

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

_MAX_EDITS = 6
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
Правила: `find` — ДОСЛОВНАЯ подстрока из текста (скопируй точно), встречается один
раз; в `replace` меняй МИНИМУМ (только факт), новые числа бери из сигнала; 1-6 правок."""

_INTERP_SYS = """Ты — редактор-аналитик платформы Basis (не брокер, без «купить/
продать» и таргетов). Тебе дан ТЕКСТ разбора вкладки и СВОДКА входного потока за
неделю (что произошло). Задача: НЕ перегенерировать разбор, а точечно скорректировать
ТОЛЬКО те места, где поток реально изменил картину (сдвиг тренда/риска/позиции). Не
изменилось — confirmed=false, ничего не трогаем. Меняй абзацами через find/replace,
сохраняя стиль и эпистемические теги; без прогнозов цен и сигналов сделок.
Финальный ответ — строго JSON того же формата, что у факт-редактора (confirmed/edits/
note), certainty у правок: оценка|суждение."""


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

    src_nums = set(_numbers(signal_text.replace(",", ".")))
    patched = prose
    for i, e in enumerate(edits):
        if not isinstance(e, dict):
            notes.append(f"edit{i}:not_dict"); continue
        find = e.get("find") or ""
        repl = e.get("replace") or ""
        if not find or not repl:
            notes.append(f"edit{i}:empty"); continue
        cnt = patched.count(find)
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
        # число в replace, которого НЕТ в find, обязано быть в тексте сигнала
        new_nums = set(_numbers(repl.replace(",", "."))) - set(_numbers(find.replace(",", ".")))
        ungrounded = [n for n in new_nums if n not in src_nums]
        if ungrounded:
            notes.append(f"edit{i}:ungrounded_numbers:{ungrounded[:3]}")
            continue
        patched = patched.replace(find, repl, 1)

    if notes:
        return None, notes
    if patched == prose:
        return None, ["noop_no_change"]
    # комплаенс РФ на итоговом тексте изменений
    m = _BLOCKLIST.search(patched)
    if m and not _BLOCKLIST.search(prose):  # блоклист внесён патчем
        return None, [f"compliance:{m.group(0)[:24]}"]
    return patched, []


# ----------------------------- ПРОГОН -----------------------------
def run_for_signal(db: Session, signal: CompanySignal, kind: str = "fact") -> CardProseOverlay | None:
    """Один сигнал → патч прозы соответствующей вкладки (published|rejected) или
    None если нет прозы/уже отражено."""
    ticker = signal.ticker.upper()
    tab = _SIGNAL_TAB_TO_PROSE.get(signal.card_tab or "")
    if not tab:
        return None
    # уже патчили этим сигналом?
    if db.query(CardProseOverlay.id).filter(
            CardProseOverlay.source_signal_id == signal.id).first():
        return None
    prose, src = read_prose(db, ticker, tab)
    if not prose:
        return None

    sys = _FACT_SYS if kind == "fact" else _INTERP_SYS
    task = (
        f"Компания: {ticker}. Вкладка: {tab}. Сегодня "
        f"{datetime.now(timezone.utc).date().isoformat()}.\n\n"
        f"СИГНАЛ (тип {signal.signal_type}, источник {signal.source_key}, "
        f"дата {signal.published_at}):\nЗаголовок: {signal.title}\n"
        f"Содержание: {(signal.summary or '')[:600]}\n"
        f"Первоисточник: {signal.source_url or '—'}\n\n"
        f"ТЕКСТ РАЗБОРА ВКЛАДКИ (правь точечно find/replace):\n<<<\n{prose[:8000]}\n>>>"
    )
    run = run_agent(db, system_prompt=sys, task=task, tools_schema=[WEB_TOOLS_SCHEMA[1]],
                    allowed_ticker=ticker, max_steps=5, max_tokens_total=30_000, web_call_cap=1)
    result = run["result"]
    signal_text = f"{signal.title or ''} {signal.summary or ''}"
    if result is not None:
        patched, notes = _apply_and_gate(prose, result, signal_text)
    else:
        patched, notes = None, [f"no_result:{run['stopped_reason']}"]

    ok = patched is not None
    parent = current_overlay(db, ticker, tab)
    row = CardProseOverlay(
        ticker=ticker, tab=tab, kind=kind,
        status="published" if ok else "rejected",
        patched_md=patched if ok else None,
        original_md=prose if ok else None,
        change_note=(result or {}).get("note") if isinstance(result, dict) else None,
        evidence={"signal_id": signal.id, "source_key": signal.source_key,
                  "source_url": signal.source_url, "prose_source": src},
        gate_notes=notes or None, source_signal_id=signal.id,
        parent_id=parent.id if (ok and parent) else None,
        model_used="deepseek", tokens_used=run["tokens_used"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("card_prose_patcher %s/%s [%s]: %s (гейт: %s; токены %s)",
                ticker, tab, kind, row.status, notes or "чисто", run["tokens_used"])
    return row


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
