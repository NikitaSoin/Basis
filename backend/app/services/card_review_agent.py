"""Агент-ревизор актуальности блоков карточки (владелец, 2026-07-21): не
переписывать анализ, а РЕВИЗОВАТЬ — всё ли ещё соответствует текущему моменту,
что изменилось за сутки/неделю? Те же методички, что у наших Claude-аналитиков
(backend/knowledge/agents/*.md — копии .claude/agents), как ЛИНЗА ревизии, но
задача другая: проверка свежести, не производство.

Работает для ЛЮБОЙ вкладки карточки (business/finance/governance/markets/macro/
geo/institutions) и для облигаций (bond). Источник свежести — Обозреватель и
БД платформы (лента/отчёты/календарь/барометры/живое макро). Веб-поиск/открытие
PDF в рутинную ревизию НЕ включены СОЗНАТЕЛЬНО: при живом тесте они дестабилизировали
агента (перебор запросов, не сходился к выводу), а внутренних данных для проверки
актуальности хватает. Веб+PDF как способность живут отдельно: эндпоинт разбора
документа /agents/analyze-document (document_analyst.py) и /agents/web-search —
там они работают надёжно. Прод-нюанс egress — см. agent_web.py.

Масштаб: ПО ТРЕБОВАНИЮ + кэш (не крон по всем 264×7 — тысячи вызовов/день).
Ревизия запускается при открытии вкладки, если свежей нет; результат кэшируется
в agent_addenda (kind='review:<tab>'). Автокрон — узкий пилот отдельно.

ДЕМО: суждение DeepSeek над нашими материалами, не расчёт; проходит автогейт."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_addendum import AgentAddendum
from app.services.agent_runner import run_agent
from app.services.agent_tools import REVIEW_TOOLS_SCHEMA

logger = logging.getLogger(__name__)

_KNOWLEDGE = Path(__file__).parent.parent.parent / "knowledge" / "agents"
_COMPANIES = Path(__file__).parent.parent.parent / "companies"
_BONDS = Path(__file__).parent.parent.parent / "bonds"

# вкладка → методичка-роль + файл-сводка блока + человекочитаемая метка.
TAB_CONFIG: dict[str, dict] = {
    "business":     {"role": "business-model-analyst",       "summary": "business_model.md",        "label": "Бизнес-модель"},
    "finance":      {"role": "financial-analyst",            "summary": "financials_summary.md",    "label": "Финансы и оценка"},
    "governance":   {"role": "governance-analyst",           "summary": "governance_summary.md",    "label": "Корпоративное управление"},
    "markets":      {"role": "market-analyst",               "summary": "market_summary.md",        "label": "Рынки"},
    "macro":        {"role": "macro-analyst",                "summary": "macro_summary.md",         "label": "Макроэкономика"},
    "geo":          {"role": "geo-company-analyst",          "summary": "geo_summary.md",           "label": "Геополитика"},
    "institutions": {"role": "institutional-company-analyst","summary": "institutions_summary.md",  "label": "Институты"},
}

_SYSTEM_TMPL = """Ты — аналитик-ревизор платформы Basis (не брокер, никаких «купить/продать»).
Тебе дана МЕТОДИКА твоей роли (как этот блок анализируется) и ТЕКУЩИЙ ТЕКСТ блока
карточки компании. Твоя задача — НЕ переписывать анализ, а проверить его
АКТУАЛЬНОСТЬ на сегодня: всё ли ещё соответствует моменту, что изменилось за
последние сутки/неделю относительно того, что заложено в разборе?

Используй инструменты (живое макро, свежие новости, отчёты, календарь, гео-
барометр — что релевантно ТВОЕЙ вкладке), не выдумывай данные. Затем финальный
ответ БЕЗ вызова инструментов — строго JSON:
{
  "verdict": "актуально" | "требует внимания" | "устарело",
  "headline": "одно предложение — главный вывод ревизии",
  "findings": [
    {"what": "что могло измениться/устареть (кратко)",
     "in_card": "что об этом говорит текущий разбор",
     "now": "что показывают свежие данные/события",
     "so_what": "нужно ли обновлять и почему (1 предложение)",
     "certainty": "факт|оценка|суждение"}
  ],
  "still_valid": "что из разбора точно ОСТАЁТСЯ в силе (1 предложение) или null"
}
Правила: 0-4 пункта findings, ТОЛЬКО реальные расхождения свежих данных с
разбором. Нет расхождений → verdict «актуально», headline «блок соответствует
текущему моменту», пустой findings. certainty обязателен. Числа — из инструментов.

=== МЕТОДИКА РОЛИ (__ROLE__) ===
__METHODOLOGY__"""

_FORBIDDEN = re.compile(r"купи(ть|те)|прода(ть|йте)|рекоменду|таргет", re.IGNORECASE)


def _load_methodology(role: str) -> str:
    p = _KNOWLEDGE / f"{role}.md"
    if not p.exists():
        return "(методика недоступна — ревизия по общей логике роли)"
    txt = p.read_text(encoding="utf-8")
    # срезаем YAML-фронтматтер (name/description/tools/model) — не нужен модели
    if txt.startswith("---"):
        parts = txt.split("---", 2)
        if len(parts) == 3:
            txt = parts[2]
    return txt.strip()[:9000]  # потолок токенов на методику (баланс линза/бюджет)


def _load_block(ticker: str, summary_file: str) -> str:
    p = _COMPANIES / ticker.upper() / summary_file
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")[:6000]


def _gate(result: dict) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not isinstance(result, dict):
        return False, ["not_a_dict"]
    if result.get("verdict") not in ("актуально", "требует внимания", "устарело"):
        notes.append("verdict_invalid")
    hl = result.get("headline")
    if not isinstance(hl, str) or not (5 <= len(hl) <= 400):
        notes.append("headline_invalid")
    findings = result.get("findings")
    if not isinstance(findings, list) or len(findings) > 4:
        notes.append("findings_invalid")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            notes.append(f"finding_{i}_not_dict"); continue
        for fld in ("what", "now", "so_what"):
            v = f.get(fld)
            if not isinstance(v, str) or not v or len(v) > 500:
                notes.append(f"finding_{i}_{fld}_invalid")
        if f.get("certainty") not in ("факт", "оценка", "суждение"):
            notes.append(f"finding_{i}_certainty_invalid")
    if _FORBIDDEN.search(json.dumps(result, ensure_ascii=False)):
        notes.append("forbidden_words")
    return not notes, notes


def run_card_review(db: Session, ticker: str, tab: str) -> AgentAddendum:
    ticker = ticker.upper()
    cfg = TAB_CONFIG.get(tab)
    if not cfg:
        raise ValueError(f"unknown_tab:{tab}")
    block = _load_block(ticker, cfg["summary"])
    methodology = _load_methodology(cfg["role"])
    system = _SYSTEM_TMPL.replace("__ROLE__", cfg["role"]).replace("__METHODOLOGY__", methodology)
    task = (f"Компания: {ticker}. Вкладка: «{cfg['label']}». Сегодня "
            f"{datetime.now(timezone.utc).date().isoformat()}.\n\n"
            f"=== ТЕКУЩИЙ ТЕКСТ БЛОКА ===\n{block or '(текст блока недоступен)'}")

    run = run_agent(db, system_prompt=system, task=task, tools_schema=REVIEW_TOOLS_SCHEMA,
                    allowed_ticker=ticker, max_steps=6, max_tokens_total=90_000)
    result = run["result"]
    ok, notes = _gate(result) if result is not None else (False, [f"no_result:{run['stopped_reason']}"])

    row = AgentAddendum(
        ticker=ticker, kind=f"review:{tab}",
        status="published" if ok else "rejected",
        content=result, gate_notes=notes or None,
        run_trace=run["trace"], model_used="deepseek", tokens_used=run["tokens_used"],
    )
    db.add(row); db.commit(); db.refresh(row)
    logger.info("card_review %s/%s: %s (%s токенов, гейт: %s)",
                ticker, tab, row.status, run["tokens_used"], notes or "чисто")
    return row


# ─────────── Облигации ───────────
_BOND_SYSTEM_TMPL = """Ты — ревизор облигационного анализа платформы Basis (не брокер,
без «купить/продать»). Дана МЕТОДИКА оценки «доходность за риск» и ТЕКУЩИЙ разбор
конкретной облигации. Задача — НЕ переписывать, а проверить АКТУАЛЬНОСТЬ: не
изменилось ли что-то за сутки/неделю (ставка ЦБ, свежие новости эмитента,
приближение оферты/погашения, события), что делает вывод разбора устаревшим?

Инструменты: живое макро (ставка), новости эмитента. Затем финал БЕЗ вызова
инструментов — строго JSON ИМЕННО такой структуры (verdict — СТРОКА, не объект;
не используй здесь «светофор» из методики, только эти три значения):
{
  "verdict": "актуально" | "требует внимания" | "устарело",
  "headline": "одно предложение — главный вывод ревизии (строка)",
  "findings": [
    {"what": "что могло измениться", "in_card": "что говорит разбор",
     "now": "что показывают свежие данные", "so_what": "нужно ли обновлять (1 предложение)",
     "certainty": "факт|оценка|суждение"}
  ],
  "still_valid": "что из разбора остаётся в силе (строка) или null"
}
Нет расхождений → verdict «актуально», пустой findings. 0-4 пункта findings.

=== МЕТОДИКА (bond-risk-analyst) ===
__METHODOLOGY__"""


def run_bond_review(db: Session, secid: str) -> AgentAddendum:
    secid = secid.upper()
    # тикер эмитента (для инструментов новостей) — из таблицы bonds
    row = db.execute(text("SELECT issuer_ticker, short_name FROM bonds WHERE secid=:s"), {"s": secid}).first()
    issuer_ticker = (row[0] if row and row[0] else "") or ""
    p = _BONDS / secid / "analysis_summary.md"
    block = p.read_text(encoding="utf-8")[:6000] if p.exists() else ""
    methodology = _load_methodology("bond-risk-analyst")
    system = _BOND_SYSTEM_TMPL.replace("__METHODOLOGY__", methodology)
    task = (f"Облигация: {secid}"
            + (f" (эмитент {issuer_ticker})" if issuer_ticker else "")
            + f". Сегодня {datetime.now(timezone.utc).date().isoformat()}.\n\n"
            f"=== ТЕКУЩИЙ РАЗБОР ===\n{block or '(разбор недоступен)'}")

    # облигации: инструменты работают по тикеру эмитента (если публичный),
    # иначе только живое макро (allowed_ticker пустой → чужие тикеры не пустим,
    # разрешаем сам secid и эмитента)
    allowed = issuer_ticker or secid
    run = run_agent(db, system_prompt=system, task=task, tools_schema=REVIEW_TOOLS_SCHEMA,
                    allowed_ticker=allowed, max_steps=6, max_tokens_total=50_000)
    result = run["result"]
    ok, notes = _gate(result) if result is not None else (False, [f"no_result:{run['stopped_reason']}"])
    rec = AgentAddendum(
        ticker=secid, kind="review:bond",
        status="published" if ok else "rejected",
        content=result, gate_notes=notes or None,
        run_trace=run["trace"], model_used="deepseek", tokens_used=run["tokens_used"],
    )
    db.add(rec); db.commit(); db.refresh(rec)
    logger.info("bond_review %s: %s (%s токенов)", secid, rec.status, run["tokens_used"])
    return rec
