"""Сверка противоречий между тремя сводками.

🔴 ЗАЧЕМ (владелец, 2026-09-13, пункт 3). Не начальник и не тимлид — проверка:
один небольшой прогон сравнивает состояние экономики, институциональный снимок
и сводку геополитики и ищет, где они СПОРЯТ: экономист ждёт ставку 14% до конца
года, геополитик закладывает эскалацию и рост расходов, институционалист пишет
о давлении на ЦБ. Найденное уходит всем трём в задание на следующую сборку
блоком «ПРОТИВОРЕЧИЯ», и каждый обязан либо снять его, либо объяснить, почему
прав он. Хранится версией kind="consistency".
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.services import barometer_store, llm

logger = logging.getLogger(__name__)

KIND = "consistency"
_KINDS = ("macro", "inst_state", "geo")
_TITLE = {"macro": "состояние экономики", "inst_state": "институциональный снимок",
          "geo": "сводка геополитики"}


def _digest(kind: str, p: dict) -> dict:
    """Компактная выжимка для сравнения — не вся сводка, а её утверждения."""
    if kind == "macro":
        return {"as_of": p.get("as_of"), "diagnosis": p.get("diagnosis"),
                "forecast": p.get("forecast"), "revision_triggers": p.get("revision_triggers"),
                "handoffs": p.get("handoffs"), "summary": p.get("summary")}
    if kind == "inst_state":
        return {"as_of": p.get("as_of"), "regime": p.get("regime"),
                "forecast_card": p.get("forecast_card"), "drift_file": (p.get("drift_file") or [])[:12],
                "handoffs": p.get("handoffs"), "summary": p.get("summary"), "verdict": p.get("verdict")}
    return {"as_of": p.get("as_of"), "scenario": p.get("scenario"), "regions": p.get("regions"),
            "sector_flags": p.get("sector_flags"), "watchlist_30d": p.get("watchlist_30d"),
            "handoffs": p.get("handoffs"), "summary": p.get("summary")}


def run(db: Session) -> BarometerVersion | None:
    payloads = {k: (r.payload if (r := barometer_store.current_row(db, k)) and r.payload else None)
                for k in _KINDS}
    present = {k: v for k, v in payloads.items() if v}
    if len(present) < 2:
        logger.warning("consistency: сводок меньше двух — сравнивать нечего")
        return None
    system = (
        "Ты — сверщик Basis. Перед тобой две-три сводки трёх аналитиков (экономика, институты, "
        "геополитика) на одну дату. Твоя единственная задача — найти, где они ПРОТИВОРЕЧАТ друг "
        "другу: разные числа одного показателя, несовместимые сценарии (один ждёт ставку 14% до "
        "конца года, другой закладывает рост расходов и эмиссию), взаимоисключающие оценки одного "
        "события, несогласованные горизонты, а также где один опирается на передачу от другого, "
        "которой тот не дал. Не суди, кто прав, и не пиши свою аналитику.\n"
        "🔴 НЕ противоречие (не включать): одна сводка цитирует число другой — это согласие; "
        "сводки датированы разными днями — это свежесть, а не спор (укажи в agreements или "
        "notes); одно и то же число в разной записи (6,29% и 6,3%). Противоречие — только когда "
        "оба утверждают РАЗНОЕ об одном и том же на одну дату или строят несовместимые ожидания.\n\n"
        "ФОРМАТ (строго JSON): {\"contradictions\": [ {\"topic\", \"claim_a\": {\"source\": "
        "<macro|inst_state|geo>, \"text\", \"where\"}, \"claim_b\": {\"source\", \"text\", \"where\"}, "
        "\"severity\": <критично|существенно|мелочь>, \"what_to_check\": <что и где проверить, чтобы "
        "снять>} ], \"agreements\": [ <в чём сводки согласны — коротко, 3-5 пунктов> ], "
        "\"missing_handoffs\": [ <какие передачи по контракту пусты и кому это мешает> ]}\n"
        "Язык — обычные слова и цифры, без эпитетов."
    )
    task = "\n\n".join(f"=== {_TITLE[k].upper()} (от {v.get('as_of')}) ===\n"
                       + json.dumps(_digest(k, v), ensure_ascii=False, default=str)[:40_000]
                       for k, v in present.items()) + f"\n\nСегодня: {date.today().isoformat()}."
    model = llm.pro_model()
    try:
        out = llm.complete(system, task, json_mode=True, model=model, max_tokens=8_000, temperature=0.1)
    except llm.LLMError as e:
        row = BarometerVersion(kind=KIND, source="auto", status="rejected", payload=None,
                               gate_notes=[f"LLM недоступен: {e}"], trigger_reason="сверка противоречий")
        db.add(row); db.commit(); db.refresh(row)
        return row
    contradictions, pseudo = _drop_pseudo((out or {}).get("contradictions") or [])
    payload = {"as_of": date.today().isoformat(), "contradictions": contradictions,
               "agreements": ((out or {}).get("agreements") or []) + pseudo,
               "missing_handoffs": (out or {}).get("missing_handoffs") or [],
               "sources": {k: v.get("as_of") for k, v in present.items()}}
    row = BarometerVersion(kind=KIND, source="auto", status="published", payload=payload,
                           trigger_reason="сверка противоречий", model_used=f"{llm.provider_info().get('provider')}:{model}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("consistency: противоречий %d, версия #%d", len(contradictions), row.id)
    return row


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _drop_pseudo(items: list[dict]) -> tuple[list[dict], list[str]]:
    """Убирает «противоречия», где обе стороны называют ОДНО И ТО ЖЕ число.

    🔴 Модель и после запрета в роли записывала в «мелочь» пары вида
    «дефицит 5 795 млрд ₽ (2,5% ВВП)» против «дефицит 5 795 млрд ₽ (2,5% ВВП) за
    январь–август» — это согласие. Промпт — пожелание, фильтр — гарантия."""
    keep, pseudo = [], []
    for c in items:
        a = str((c.get("claim_a") or {}).get("text") or ""); b = str((c.get("claim_b") or {}).get("text") or "")
        na = {n.replace(",", ".") for n in _NUM.findall(a)}; nb = {n.replace(",", ".") for n in _NUM.findall(b)}
        shared = {n for n in na & nb if len(n) >= 2}
        if shared and str(c.get("severity")) == "мелочь":
            pseudo.append(f"согласие, не спор: {c.get('topic')} ({', '.join(sorted(shared))})")
        else:
            keep.append(c)
    return keep, pseudo


def contradictions_for(db: Session, kind: str) -> list[dict]:
    """Противоречия, в которых участвует данная сводка, — для её следующей сборки."""
    row = barometer_store.current_row(db, KIND)
    if not row or not row.payload:
        return []
    return [c for c in (row.payload.get("contradictions") or [])
            if kind in ((c.get("claim_a") or {}).get("source"), (c.get("claim_b") or {}).get("source"))]


def current(db: Session) -> dict | None:
    return barometer_store.get_payload_with_meta(db, KIND)
