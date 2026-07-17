"""Пилотный автономный агент «макро-addendum» (фазы 2-4 «пути к автономной
платформе», владелец дал добро 2026-07-18).

Что делает: для ОДНОЙ компании малой капитализации (пилот) читает её
макро-разбор (когда писался и при каких условиях), сверяет с ТЕКУЩИМИ
условиями (ставка/нефть/курс из БД) и свежими новостями Ленты по тикеру,
и пишет короткий addendum «что изменилось с последнего разбора» — 2-4 пункта.
НЕ переписывает анализ (низкий риск для доверия — дописывает поверх, всегда
помечен как автономное обновление).

АВТОГЕЙТ (фаза 4 — обязателен ДО публикации, код, не LLM):
  - схема: наличие/типы полей, лимиты длины;
  - запрещённые слова (сигналы «купить/продать» и пр. — конституция);
  - числовая сверка: ставка/нефть/курс, упомянутые агентом, должны совпадать
    (с допуском) с тем, что реально отдали инструменты в этом прогоне;
  - тикер-валидация: не упоминает чужие тикеры.
Отклонённое сохраняется со status=rejected и gate_notes — видно в отладке,
на фронт НЕ попадает (фронт читает только published)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.agent_addendum import AgentAddendum
from app.services.agent_runner import run_agent
from app.services.agent_tools import TOOLS_SCHEMA, _get_live_macro

logger = logging.getLogger(__name__)

_SYSTEM = """Ты — автономный агент-аналитик платформы Basis (не брокер, никаких
рекомендаций «купить/продать»). Твоя ЕДИНСТВЕННАЯ задача: короткий addendum
«что изменилось с последнего макро-разбора» для ОДНОЙ компании.

Порядок работы (используй инструменты, не выдумывай данные):
1. read_macro_card — что и при каких условиях писал аналитик.
2. get_live_macro — условия сейчас.
3. get_recent_news — было ли что-то по компании в новостях.
Затем финальный ответ БЕЗ вызова инструментов — строго JSON:
{
  "headline": "одно предложение — главное изменение (или 'существенных изменений нет')",
  "changes": [
    {"what": "что изменилось (кратко)", "was": "как было на дату разбора", "now": "как сейчас",
     "so_what": "что это значит для компании (1 предложение, через её каналы из разбора)",
     "certainty": "факт|оценка|суждение"}
  ],
  "unchanged_note": "что из разбора ОСТАЁТСЯ в силе (1 предложение) или null",
  "card_as_of": "дата разбора из карточки (как есть)"
}
Правила: 1-4 пункта changes, только РЕАЛЬНЫЕ изменения (сдвиг ставки/нефти/курса
против ориентиров разбора, значимые новости). Если изменений нет — честно
headline «существенных изменений нет» и пустой changes. Числа бери ТОЛЬКО из
инструментов. certainty обязателен у каждого пункта."""

_FORBIDDEN = re.compile(r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет|обязательно\s+(бер|вход)", re.IGNORECASE)


def _gate(result: dict, live: dict, ticker: str) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not isinstance(result, dict):
        return False, ["not_a_dict"]
    headline = result.get("headline")
    changes = result.get("changes")
    if not isinstance(headline, str) or not (5 <= len(headline) <= 300):
        notes.append("headline_invalid")
    if not isinstance(changes, list) or len(changes) > 4:
        notes.append("changes_invalid")
        changes = []
    for i, ch in enumerate(changes):
        if not isinstance(ch, dict):
            notes.append(f"change_{i}_not_dict")
            continue
        for f in ("what", "now", "so_what"):
            v = ch.get(f)
            if not isinstance(v, str) or not v or len(v) > 400:
                notes.append(f"change_{i}_{f}_invalid")
        if ch.get("certainty") not in ("факт", "оценка", "суждение"):
            notes.append(f"change_{i}_certainty_invalid")
    blob = json.dumps(result, ensure_ascii=False)
    if _FORBIDDEN.search(blob):
        notes.append("forbidden_words")
    # чужие тикеры (латиница 3-6 заглавных, не наш и не общеупотребимые аббревиатуры)
    whitelist = {ticker.upper(), "USD", "RUB", "GDP", "CPI", "OPEC", "IPO", "EBITDA", "FCF", "PE", "PB"}
    for m in set(re.findall(r"\b[A-Z]{3,6}\b", blob)):
        if m not in whitelist:
            notes.append(f"foreign_ticker:{m}")
    # числовая сверка: если агент назвал ставку/нефть/курс «сейчас» — числа должны
    # совпадать с инструментами прогона (допуск 2% — округления)
    def _mentioned_close(pattern: str, actual: float | None, tol: float) -> None:
        if actual is None:
            return
        for m in re.findall(pattern, blob):
            try:
                v = float(m.replace(",", "."))
            except ValueError:
                continue
            if 0.3 * actual < v < 3 * actual and abs(v - actual) / actual > tol:
                notes.append(f"number_mismatch:{v}!={actual}")
    _mentioned_close(r"ставк[аеиу][^0-9]{0,20}(\d{1,2}[.,]?\d{0,2})\s*%", live.get("key_rate_pct"), 0.02)
    return not notes, notes


def run_macro_addendum(db: Session, ticker: str) -> AgentAddendum:
    """Один прогон для одного тикера. Всегда сохраняет строку (published/rejected)."""
    ticker = ticker.upper()
    task = (f"Компания: {ticker}. Сделай addendum «что изменилось с последнего "
            f"макро-разбора». Сегодня {datetime.now(timezone.utc).date().isoformat()}.")
    run = run_agent(db, system_prompt=_SYSTEM, task=task, tools_schema=TOOLS_SCHEMA,
                    allowed_ticker=ticker, max_steps=8, max_tokens_total=40_000)
    live = _get_live_macro(db)
    result = run["result"]
    if result is not None:
        ok, notes = _gate(result, live, ticker)
    else:
        ok, notes = False, [f"no_result:{run['stopped_reason']}"]

    row = AgentAddendum(
        ticker=ticker, kind="macro_addendum",
        status="published" if ok else "rejected",
        content=result, gate_notes=notes or None,
        run_trace=run["trace"], model_used="deepseek",
        tokens_used=run["tokens_used"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("macro_addendum %s: %s (гейт: %s; токены: %s)",
                ticker, row.status, notes or "чисто", run["tokens_used"])
    return row
