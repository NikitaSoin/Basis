"""Экспертный контур «Стресс-тестирования» (владелец, 2026-07-17, третья
итерация): вопрос «какие компании и сектора выигрывают от войны на Ближнем
Востоке?» — это ВАЛИДНЫЙ сценарный вопрос, но 8-факторная числовая рамка его
не ловит (v2 честно отвечала «не удалось извлечь» — неприемлемо). Здесь LLM
(DeepSeek, прод-контур) отвечает КАЧЕСТВЕННО — объясняет, что произойдёт, на
кого и насколько повлияет, называет сектора и компании — опираясь на БАЗУ
ЗНАНИЙ ПЛАТФОРМЫ, приложенную прямо в промпт:
  1) геополитический барометр (config/geo_barometer.json — очаги СВО/Ближний
     Восток/АТР с каналами влияния на РФ, секторные флаги, сценарная рамка);
  2) карта вселенной: сектора + крупнейшие компании каждого (из БД);
  3) агрегированные факторные экспозиции секторов (санкции/конфликт/сырьё/
     ставка/курс — из тех же карточек, что питают MGI).

Архитектурная заметка про «агентский режим» (вопрос владельца): DeepSeek API —
это chat-completion + function calling, НЕ готовый агент как субагенты Claude
Code; полноценный агентский цикл (LLM сам ходит по базе инструментами) нужно
писать руками — отдельный проект. Для демо выбран RAG-подход: мы САМИ кладём
релевантные материалы в промпт одним вызовом — дешевле, быстрее (~1 вызов
вместо цикла), предсказуемее по токенам. Если демо приживётся — следующий шаг
как раз tool-loop по полной базе (все 264 карточки, облигации).

ДЕМО: ответ LLM = суждение модели над нашими материалами, не расчёт; тикеры
валидируются против вселенной (галлюцинированные отбрасываются)."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.llm import complete, LLMError

logger = logging.getLogger(__name__)

_GEO_BAROMETER = Path(__file__).parent.parent.parent / "config" / "geo_barometer.json"

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 3600
_cache_lock = threading.Lock()

_SYSTEM = """Ты — аналитик-эксперт платформы Basis (независимая аналитика российского
фондового рынка; НЕ брокер, НИКАКИХ «купить/продать»). Тебе дан сценарный вопрос
пользователя и МАТЕРИАЛЫ ПЛАТФОРМЫ (геополитический барометр, карта секторов с
крупнейшими компаниями, факторные экспозиции секторов).

Ответь на вопрос КАЧЕСТВЕННО, опираясь В ПЕРВУЮ ОЧЕРЕДЬ на материалы (они свежие и
проверенные), дополняя общей логикой экономической трансмиссии. Правила:
- Тикеры используй ТОЛЬКО из приложенной карты секторов.
- Не выдумывай точные числа (проценты/рубли) — сила эффекта только шкалой 1-3.
- Явно различай: что известно из материалов vs твоя интерпретация.
- Пиши по-русски, сжато, для частного инвестора.

Верни СТРОГО JSON:
{
  "summary": "3-5 предложений: суть — что произойдёт и через какие каналы это бьёт по рынку РФ",
  "channels": ["канал влияния 1 (одним предложением)", "..."],
  "sector_winners": [{"sector": "...", "strength": 1|2|3, "why": "одно предложение"}],
  "sector_losers": [{"sector": "...", "strength": 1|2|3, "why": "..."}],
  "company_winners": [{"ticker": "...", "why": "одно предложение"}],
  "company_losers": [{"ticker": "...", "why": "..."}],
  "caveats": ["важная оговорка/неопределённость", "..."]
}
strength: 1 — слабо/косвенно, 2 — заметно, 3 — сильно. Секторов — до 4 на сторону,
компаний — до 6 на сторону (можно меньше; если сторона пустая — пустой массив)."""


def _compact_barometer() -> str:
    try:
        d = json.loads(_GEO_BAROMETER.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "(геобарометр недоступен)"
    keep = {
        "as_of": d.get("as_of"),
        "scenario": d.get("scenario"),
        "regions": d.get("regions"),
        "sector_flags": d.get("sector_flags"),
    }
    return json.dumps(keep, ensure_ascii=False)


def _sector_map(db: Session) -> str:
    rows = db.execute(text("""
        SELECT c.sector, c.ticker, c.name, c.market_cap
        FROM companies c JOIN company_metrics m ON m.ticker = c.ticker
        WHERE c.sector IS NOT NULL
        ORDER BY c.sector, c.market_cap DESC NULLS LAST
    """)).fetchall()
    by_sector: dict[str, list] = {}
    for r in rows:
        by_sector.setdefault(r[0], []).append((r[1], r[2]))
    lines = []
    for s, comps in sorted(by_sector.items(), key=lambda kv: -len(kv[1])):
        tops = ", ".join(f"{t} ({n})" for t, n in comps[:5])
        lines.append(f"{s} [{len(comps)} комп.]: {tops}")
    return "\n".join(lines)


def _sector_exposures(db: Session) -> str:
    """Средние факторные экспозиции по секторам (краткая карта чувствительности)."""
    from app.services.factor_exposures import get_company_exposures
    rows = db.execute(text("""
        SELECT c.sector, c.ticker FROM companies c
        JOIN company_metrics m ON m.ticker = c.ticker WHERE c.sector IS NOT NULL
    """)).fetchall()
    agg: dict[str, dict[str, list]] = {}
    for sector, ticker in rows:
        exp = get_company_exposures(ticker)
        for k in ("sanctions", "conflict", "commodity", "rate", "fx", "fiscal"):
            v = exp.get(k)
            if v is not None:
                agg.setdefault(sector, {}).setdefault(k, []).append(v)
    lines = []
    for s, factors in agg.items():
        parts = []
        for k, vals in factors.items():
            avg = sum(vals) / len(vals)
            if abs(avg) >= 0.4:
                parts.append(f"{k}:{avg:+.1f}")
        if parts:
            lines.append(f"{s}: {' '.join(parts)}")
    return "\n".join(lines) + "\n(шкала -2..+2: знак = выигрывает(+)/страдает(-) от роста фактора; только выраженные)"


def _valid_tickers(db: Session) -> set[str]:
    rows = db.execute(text("SELECT ticker FROM companies")).fetchall()
    return {r[0] for r in rows}


def expert_answer(db: Session, question: str, understood: str | None = None) -> dict | None:
    """Качественный экспертный ответ. None — LLM недоступен (вызывающий деградирует)."""
    key = hashlib.sha256(("expert:" + " ".join(question.lower().split())[:500]).encode()).hexdigest()
    now = time.time()
    with _cache_lock:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    user_content = (
        f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: {question}\n"
        + (f"(интерпретация: {understood})\n" if understood else "")
        + "\n=== ГЕОПОЛИТИЧЕСКИЙ БАРОМЕТР BASIS ===\n" + _compact_barometer()
        + "\n\n=== СЕКТОРА И КРУПНЕЙШИЕ КОМПАНИИ ===\n" + _sector_map(db)
        + "\n\n=== ФАКТОРНЫЕ ЭКСПОЗИЦИИ СЕКТОРОВ ===\n" + _sector_exposures(db)
    )
    try:
        # Короткий таймаут/ретраи — путь интерактивный (см. пояснение в stress_ask.py:
        # parse_scenario), это ВТОРОЙ LLM-вызов в цепочке одного запроса /ask.
        raw = complete(_SYSTEM, user_content, json_mode=True, max_tokens=2200, temperature=0.3,
                       timeout=25, retries=1)
    except LLMError as e:
        logger.warning("stress_expert: LLM недоступен: %s", e)
        return None
    if not isinstance(raw, dict):
        return None

    valid = _valid_tickers(db)
    for side in ("company_winners", "company_losers"):
        items = raw.get(side) or []
        raw[side] = [x for x in items if isinstance(x, dict) and x.get("ticker") in valid]

    out = {
        "summary": raw.get("summary"),
        "channels": raw.get("channels") or [],
        "sector_winners": raw.get("sector_winners") or [],
        "sector_losers": raw.get("sector_losers") or [],
        "company_winners": raw.get("company_winners") or [],
        "company_losers": raw.get("company_losers") or [],
        "caveats": raw.get("caveats") or [],
        "kb_note": "Ответ построен ИИ на материалах платформы (геобарометр, факторные карты, вселенная компаний) — суждение, не расчёт.",
    }
    with _cache_lock:
        _CACHE[key] = (now, out)
    return out
