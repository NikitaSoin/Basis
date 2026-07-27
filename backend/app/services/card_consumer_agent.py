"""Consumer-агент: сигнал company_signals → датированный addendum на вкладке
карточки под КОД-ГЕЙТОМ (fail-closed). Последнее звено «входной поток → карточки
обновляются сами» (владелец 2026-07-28). Дизайн отревьюен advisor.

РАМКА (почему консервативно):
- v1 пускает в карточку ТОЛЬКО ТОЧНЫЕ по конструкции сигналы:
  trust=official AND signal_type ∈ {rating_action, earnings} AND internal=False.
  Fuzzy-привязка Ленты (dividend/legal/mgmt по ключевым словам) НЕ идёт в
  карточку до ужесточения маппинга (observer-source-map §8: живые ложные
  срабатывания «дивиденды Русагро → SBER»). Неверная инфа на карточке бьёт по
  доверию — ядру продукта, поэтому безопасность — КОДОВАЯ, не «агент подумает».
- агент НЕ переписывает разбор аналитика — дописывает короткую датированную
  плашку «что произошло» поверх, всегда помеченную как автообновление;
- card_tab НЕ выбирает агент — форсим = signal.card_tab кодом;
- числа в интерпретации (so_what) обязаны присутствовать в сигнале/источнике
  (аналог _mentioned_close макро-гейта) — против «дорисовывания»;
- cooldown + supersede на (тикер, вкладка): фронт показывает ОДИН последний
  addendum на вкладку, новый вытесняет старый; второй сигнал в окне → reject;
- claim сигнала (consumed_at) в момент ВЫБОРКИ (анти-гонка перекрытых прогонов);
- shadow: по умолчанию status=draft (на карточку НЕ идёт), публикация — по флагу
  CARD_CONSUMER_PUBLISH=1 (диспетчер сперва глазами смотрит выборку, потом
  включает). Уважает «без вечных черновиков на бою»: draft — разовый пред-полёт.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_addendum import AgentAddendum
from app.models.geo import CompanySignal
from app.services.agent_runner import run_agent
from app.services.agent_tools import CONSUMER_TOOLS_SCHEMA
from app.services.situation_overlay import _BLOCKLIST

logger = logging.getLogger(__name__)

# --- белый список v1 (по ТОЧНОСТИ источника, не по importance) ---
_V1_TYPES = {"rating_action", "earnings"}
_ALLOWED_TABS = {"bonds", "finance", "dividends", "governance", "markets", "macro"}
_KIND = "signal_addendum"

# --- границы прогона ---
_BATCH_CAP = 5           # сигналов за один прогон
_FRESH_DAYS = 10         # не трогаем протухшие сигналы (иначе v2 хлынет бэклогом)
_COOLDOWN_DAYS = 10      # анти-осцилляция на (тикер, вкладка)
_SO_WHAT_MAX = 240       # кэп интерпретации (1–2 предложения)

# публикация: по умолчанию draft (пред-полёт), CARD_CONSUMER_PUBLISH=1 → published
_PUBLISH = os.environ.get("CARD_CONSUMER_PUBLISH", "").lower() in ("1", "true", "yes")

# прогнозные/оценочные конструкции сверх «купить/продать» — интерпретация не
# должна СОЧИНЯТЬ будущее, только называть смысл случившегося факта
_FORBIDDEN = re.compile(
    r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет|целев\w+\s+цен|"
    r"приведёт\s+к|ожида(ем|ется)|вырастет\s+до|упадёт\s+до|прогнозиру|"
    r"потенциал\s+рост|апсайд|обязательно\s+(бер|вход)", re.IGNORECASE)

_SYSTEM = """Ты — автономный агент-аналитик платформы Basis (не брокер, никаких
«купить/продать» и прогнозов цен). Тебе дан ПРОВЕРЕННЫЙ сигнал-событие по ОДНОЙ
компании (официальный источник: рейтинговое агентство или разбор отчётности).
Задача: короткая датированная плашка «что произошло» для указанной вкладки —
БЕЗ переписывания разбора аналитика.

Порядок (используй инструменты, не выдумывай):
1. read_card_tab — что уже на этой вкладке; если событие УЖЕ отражено → confirmed=false.
2. При необходимости get_recent_earnings / get_recent_news / get_calendar — контекст.
3. Можно fetch_document(source_url) — сверить первоисточник (не обязательно; если
   не открылся — опирайся на сам сигнал, он от официального источника).
Затем финальный ответ БЕЗ вызова инструментов — строго JSON:
{
  "confirmed": true|false,   // событие реально про ЭТОГО эмитента и НЕ отражено ранее
  "headline": "одно предложение — суть события (что и когда сделал источник)",
  "event": "факт как есть: действие + уровень/показатель + источник + дата",
  "so_what": "что это значит для держателя бумаги — 1-2 предложения, БЕЗ прогнозов и чисел, которых нет в сигнале",
  "certainty": "факт|оценка|суждение",
  "reject_reason": "если confirmed=false — почему (уже отражено / не про эмитента / несущественно), иначе null"
}
Правила: so_what — СМЫСЛ случившегося факта (напр. понижение рейтинга = рост
кредитного риска / удорожание заимствований), НЕ предсказание. Любое ЧИСЛО в
so_what обязано быть в тексте сигнала. Если событие уже на вкладке или не про
эмитента — confirmed=false, честно. Числа/уровни бери из сигнала."""


# ----------------------------- ГЕЙТ -----------------------------
def _numbers_grounded(so_what: str, signal_text: str) -> bool:
    """Каждое число из so_what должно встречаться в тексте сигнала (против
    «дорисовывания» — прямой аналог _mentioned_close макро-гейта)."""
    src = signal_text.replace(",", ".")
    for tok in re.findall(r"\d+[.,]?\d*", so_what):
        if tok.replace(",", ".") not in src:
            return False
    return True


def _gate(result: dict, signal: CompanySignal) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not isinstance(result, dict):
        return False, ["not_a_dict"]
    if result.get("confirmed") is not True:
        return False, [f"not_confirmed:{result.get('reject_reason') or 'agent'}"]

    headline = result.get("headline")
    event = result.get("event")
    so_what = result.get("so_what")
    if not isinstance(headline, str) or not (5 <= len(headline) <= 200):
        notes.append("headline_invalid")
    if not isinstance(event, str) or not (5 <= len(event) <= 400):
        notes.append("event_invalid")
    if not isinstance(so_what, str) or not so_what or len(so_what) > _SO_WHAT_MAX:
        notes.append("so_what_invalid")
    if result.get("certainty") not in ("факт", "оценка", "суждение"):
        notes.append("certainty_invalid")

    blob = json.dumps(result, ensure_ascii=False)
    if _FORBIDDEN.search(blob):
        notes.append("forbidden_words")
    # чужие тикеры (латиница 3-6 заглавных, не наш и не общеупотребимые)
    whitelist = {signal.ticker.upper(), "USD", "RUB", "GDP", "CPI", "OPEC", "IPO",
                 "EBITDA", "FCF", "YTM", "MSFO", "RSBU", "AAA", "AA", "BBB", "BB", "RU", "NKR"}
    for m in set(re.findall(r"\b[A-Z]{3,6}\b", blob)):
        if m not in whitelist:
            notes.append(f"foreign_ticker:{m}")
    # числа в so_what — только из сигнала
    signal_text = f"{signal.title or ''} {signal.summary or ''}"
    if isinstance(so_what, str) and not _numbers_grounded(so_what, signal_text):
        notes.append("so_what_number_not_in_signal")
    # комплаенс РФ (переиспользуем блоклист-regex оверлея)
    m = _BLOCKLIST.search(blob)
    if m:
        notes.append(f"compliance:{m.group(0)[:24]}")
    return not notes, notes


# ----------------------------- ТРИГГЕР/CLAIM -----------------------------
def _cooldown_active(db: Session, ticker: str, tab: str) -> bool:
    since = datetime.now(timezone.utc) - timedelta(days=_COOLDOWN_DAYS)
    row = (db.query(AgentAddendum.id)
           .filter(AgentAddendum.ticker == ticker.upper(),
                   AgentAddendum.kind == _KIND,
                   AgentAddendum.status.in_(("published", "draft")),
                   AgentAddendum.created_at >= since,
                   AgentAddendum.content["card_tab"].astext == tab)
           .first())
    return row is not None


def _claim_batch(db: Session) -> list[CompanySignal]:
    """Выбрать и СРАЗУ заклеймить (consumed_at=now) свежие v1-сигналы — claim в той
    же выборке против гонки перекрытых прогонов. Возвращает заклеймленные строки."""
    fresh = datetime.now(timezone.utc).date() - timedelta(days=_FRESH_DAYS)
    rows = (db.query(CompanySignal)
            .filter(CompanySignal.importance == "high",
                    CompanySignal.trust == "official",
                    CompanySignal.internal.is_(False),
                    CompanySignal.consumed_at.is_(None),
                    CompanySignal.signal_type.in_(_V1_TYPES),
                    CompanySignal.card_tab.in_(_ALLOWED_TABS),
                    CompanySignal.published_at >= fresh)
            .order_by(CompanySignal.published_at.desc().nullslast(),
                      CompanySignal.created_at.desc())
            .limit(_BATCH_CAP).all())
    now = datetime.now(timezone.utc)
    for s in rows:
        s.consumed_at = now  # claim
    db.commit()
    return rows


# ----------------------------- ПРОГОН -----------------------------
def run_for_signal(db: Session, signal: CompanySignal) -> AgentAddendum | None:
    """Один сигнал → addendum (published|draft|rejected) или None если cooldown."""
    ticker = signal.ticker.upper()
    tab = signal.card_tab
    if _cooldown_active(db, ticker, tab):
        logger.info("card_consumer %s/%s: cooldown — пропуск", ticker, tab)
        return None

    task = (
        f"Компания: {ticker}. Вкладка: {tab}. Сегодня "
        f"{datetime.now(timezone.utc).date().isoformat()}.\n"
        f"ПРОВЕРЕННЫЙ сигнал (тип {signal.signal_type}, источник {signal.source_key}, "
        f"trust={signal.trust}, дата {signal.published_at}):\n"
        f"Заголовок: {signal.title}\n"
        f"Содержание: {(signal.summary or '')[:600]}\n"
        f"Источник (можно открыть fetch_document): {signal.source_url or '—'}\n"
        f"Сделай плашку «что произошло» для вкладки {tab}."
    )
    run = run_agent(db, system_prompt=_SYSTEM, task=task,
                    tools_schema=CONSUMER_TOOLS_SCHEMA, allowed_ticker=ticker,
                    max_steps=6, max_tokens_total=30_000, web_call_cap=1)
    result = run["result"]
    if result is not None:
        ok, notes = _gate(result, signal)
    else:
        ok, notes = False, [f"no_result:{run['stopped_reason']}"]

    # card_tab форсим кодом (агент вкладку НЕ выбирает); прикрепляем источник
    content = None
    if isinstance(result, dict):
        content = {
            "card_tab": tab,
            "signal_id": signal.id,
            "signal_type": signal.signal_type,
            "headline": result.get("headline"),
            "event": result.get("event"),
            "so_what": result.get("so_what"),
            "certainty": result.get("certainty"),
            "source_key": signal.source_key,
            "source_url": signal.source_url,
            "event_date": signal.published_at.isoformat() if signal.published_at else None,
        }
    status = ("published" if _PUBLISH else "draft") if ok else "rejected"
    row = AgentAddendum(
        ticker=ticker, kind=_KIND, status=status,
        content=content, gate_notes=notes or None,
        run_trace=run["trace"], model_used="deepseek", tokens_used=run["tokens_used"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("card_consumer %s/%s [%s]: %s (гейт: %s; токены %s)",
                ticker, tab, signal.signal_type, row.status, notes or "чисто",
                run["tokens_used"])
    return row


def run_consumer(db: Session) -> dict:
    """Полный прогон (крон): заклеймить батч → обработать каждый."""
    batch = _claim_batch(db)
    stats = {"claimed": len(batch), "published": 0, "draft": 0, "rejected": 0,
             "cooldown": 0, "publish_mode": _PUBLISH}
    for s in batch:
        row = run_for_signal(db, s)
        if row is None:
            stats["cooldown"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("card_consumer.run: %s", stats)
    return stats
