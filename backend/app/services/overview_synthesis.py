"""Вкладка «Обзор»: свод всех разборов карточки в один вывод.

🔴 ЗАЧЕМ (владелец, 2026-08-04): «финальная вкладка Обзор — качественное саммари всех
остальных вкладок, от бизнес-модели до институтов. Это завершающая часть
фундаментального анализа: мы посмотрели на бизнес со всех сторон, теперь надо сделать
общий вывод о нём и качественно объяснить справедливую цену — почему мы считаем её
выше или ниже».

Что здесь происходит: разборы семи вкладок читаются как ВХОД, а не пересказываются.
Пересказ — это то, что уже есть по клику на вкладку; ценность свода в другом — свести
стороны вместе и назвать, что перевешивает.

🔴 СВОЕЙ СПРАВЕДЛИВОЙ ЦЕНЫ ЗДЕСЬ НЕТ И БЫТЬ НЕ МОЖЕТ. Единственный источник числа —
BFV; синтез его ОБЪЯСНЯЕТ словами. Второе число другой методикой на той же карточке
уже ломало доверие (GAZP: в теле −11%, в правом рейле +89%). Поэтому агенту в задании
даётся готовое число со всеми компонентами, а гейт проверяет, что он не пересчитал его
по-своему.

🔴 ЧТО ПРОВЕРЯЕТ КОД, А НЕ МОДЕЛЬ (гейт fail-closed):
  - структура и длины (свод не должен превращаться в простыню — её и так семь вкладок);
  - никаких «купить/продать» и целевых цен (конституция платформы);
  - все числа в объяснении цены заземлены в переданных данных;
  - справедливая цена в тексте совпадает с BFV, а не пересчитана;
  - упоминается только своя компания.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.geo import CardOverviewSynthesis

logger = logging.getLogger(__name__)

COMPANIES_DIR = Path(__file__).parent.parent.parent / "companies"

# Вкладки-источники в порядке фундаментального разбора: от «что за бизнес» к «в какой
# среде он живёт». Тот же порядок идёт в вывод — читателю знаком по вкладкам карточки.
_TABS = [
    ("business", "business_model.md", "Бизнес-модель"),
    ("finance", "financials_summary.md", "Финансы и оценка"),
    ("governance", "governance_summary.md", "Управление"),
    ("markets", "market_summary.md", "Рынки"),
    ("macro", "macro_summary.md", "Макроэкономика"),
    ("geo", "geo_summary.md", "Геополитика"),
    ("institutions", "institutions_summary.md", "Институты"),
]

# Сколько символов каждой вкладки отдаём модели. Семь полных разборов не влезут в
# контекст, а хвосты у них — детализация; вывод делается по существу, которое авторы
# ставят в начало.
_TAB_CHARS = 2600
_MIN_TABS = 3          # меньше трёх разборов — свода не выйдет, честнее не делать

_BANNED = re.compile(r"куп(ить|ать)|прода(ть|вать)|шорт|целев\w+ цен|"
                     r"рекоменд\w*|инвестидея|наша цель", re.I)


def _read(ticker: str, name: str) -> str | None:
    path = COMPANIES_DIR / ticker / name
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return None
    return text or None


def _tab_inputs(db: Session, ticker: str) -> list[dict]:
    """Разборы вкладок — с учётом авто-патчей прозы (оверлей → файл)."""
    out = []
    for tab, filename, title in _TABS:
        text = None
        try:
            from app.services.card_prose_patcher import read_prose
            text, _src = read_prose(db, ticker, tab)
        except Exception:  # noqa: BLE001
            text = None
        text = text or _read(ticker, filename)
        if text:
            out.append({"tab": tab, "title": title, "text": text[:_TAB_CHARS]})
    return out


def _fair_value(db: Session, ticker: str) -> dict | None:
    """Готовое число справедливой цены со всеми компонентами — ВХОД, не задача."""
    try:
        from app.services.bfv.service import get_bfv
    except Exception:  # noqa: BLE001
        logger.warning("overview_synthesis: движок справедливой цены недоступен")
        return None
    try:
        data = get_bfv(db, ticker.upper())
    except Exception:  # noqa: BLE001
        logger.warning("overview_synthesis: BFV для %s не посчитан", ticker, exc_info=True)
        return None
    if not isinstance(data, dict) or data.get("status") != "ok":
        return None
    keep = ("engine", "fair_price", "current_price", "upside_pct", "verdict",
            "expected_return_pct", "hurdle_pct", "spread_to_hurdle_pp",
            "div_yield_y1_pct", "reliability", "terminal_share_pct", "warnings")
    out = {k: data[k] for k in keep if k in data}
    base = data.get("base_meta") or {}
    out["drivers"] = {k: base[k] for k in
                      ("roe0", "roe_terminal", "payout0", "governance_score", "is_bank",
                       "h_expropriation", "h_distress", "sector")
                      if k in base}
    return out


_SYSTEM = """Ты — аналитик платформы Basis (независимая аналитика для частного
инвестора; НЕ брокер, НЕ даёт сигналов «купить/продать» и целевых цен).

Тебе даны разборы компании по вкладкам (бизнес-модель, финансы, управление, рынки,
макро, геополитика, институты) и ГОТОВАЯ справедливая цена по методике платформы со
всеми её компонентами.

Твоя задача — ЗАВЕРШАЮЩИЙ ВЫВОД фундаментального анализа. Не пересказ вкладок: их
читатель откроет сам. Нужно свести стороны вместе и сказать, что перевешивает.

🔴 СПРАВЕДЛИВУЮ ЦЕНУ НЕ СЧИТАЙ И НЕ ПОДПРАВЛЯЙ. Она уже посчитана. Твоя работа —
объяснить её словами: за счёт чего она оказалась выше или ниже рынка, какие стороны
бизнеса её держат, какие тянут вниз, и насколько прочно она стоит. Числа бери только
из переданных данных.

Верни JSON:
{
  "verdict": "2-4 предложения: что это за бизнес по итогам всего разбора и чем он
              держится. Без воды и без пересказа отдельных вкладок.",
  "pillars": [
    {"tab": "business|finance|governance|markets|macro|geo|institutions",
     "stance": "сила|нейтрально|слабость",
     "point": "одна фраза: что эта сторона даёт инвестору или чем угрожает"}
  ],
  "fair_value_story": {
    "direction": "выше рынка|ниже рынка|близко к рынку",
    "why": "3-5 предложений: КАЧЕСТВЕННОЕ объяснение, почему цена такая. Именно
            рассуждение, а не перечисление коэффициентов.",
    "supports": ["что поднимает справедливую цену — 2-4 пункта"],
    "drags": ["что её опускает или делает менее надёжной — 2-4 пункта"],
    "confidence": "одна фраза: насколько прочно стоит оценка и от чего это зависит"
  },
  "what_would_change": ["2-4 конкретных события, после которых вывод придётся менять"]
}

Пиши по-русски, спокойно и предметно. Не используй слова «купить», «продать»,
«рекомендуем», «целевая цена». Не называй фамилий должностных лиц."""


def _gate(result: dict, tabs: list[dict], fair: dict | None, ticker: str) -> list[str]:
    """Код-проверка перед публикацией. Пусто = чисто."""
    notes = []
    if not isinstance(result, dict):
        return ["not_a_dict"]
    verdict = str(result.get("verdict") or "").strip()
    if len(verdict) < 60:
        notes.append("verdict_too_short")
    if len(verdict) > 1200:
        notes.append("verdict_too_long")

    pillars = result.get("pillars")
    if not isinstance(pillars, list) or len(pillars) < _MIN_TABS:
        notes.append("pillars_missing")
    else:
        known = {t["tab"] for t in tabs}
        for p in pillars:
            if not isinstance(p, dict) or not p.get("point"):
                notes.append("pillar_malformed")
                break
            # 🔴 Свод не имеет права говорить о вкладке, которой у компании нет: так
            # появляется «институциональный риск умеренный» там, где разбора институтов
            # не существует, и читатель принимает выдумку за прочитанный анализ.
            if p.get("tab") not in known:
                notes.append(f"pillar_without_source:{p.get('tab')}")
                break
            if str(p.get("stance")) not in ("сила", "нейтрально", "слабость"):
                notes.append("pillar_stance_invalid")
                break

    story = result.get("fair_value_story")
    if not isinstance(story, dict) or not str(story.get("why") or "").strip():
        notes.append("fair_value_story_missing")
        story = {}

    blob = json.dumps(result, ensure_ascii=False)
    if _BANNED.search(blob):
        notes.append("banned_wording")
    # Чужие тикеры: свод пишется по ОДНОЙ компании.
    for foreign in set(re.findall(r"\b[A-Z]{4,5}\b", blob)):
        if foreign != ticker.upper() and foreign not in ("BFV", "EBITDA", "OFZ"):
            notes.append(f"foreign_ticker:{foreign}")
            break

    # 🔴 Числа объяснения обязаны быть заземлены в переданных данных: разбор вкладок
    # плюс компоненты справедливой цены. Иначе модель «дорисовывает» правдоподобные
    # величины — на этом уже горел макро-выпуск.
    grounding = " ".join(t["text"] for t in tabs) + " " + json.dumps(fair or {}, ensure_ascii=False)
    grounding_nums = set(re.findall(r"\d+(?:[.,]\d+)?", grounding))
    grounding_nums |= {n.replace(",", ".") for n in grounding_nums}
    grounding_nums |= {n.replace(".", ",") for n in grounding_nums}
    # 🔴 Движок справедливой цены отдаёт ДОЛИ (payout 0,498; ROE 0,2402), а живая проза
    # пишет ПРОЦЕНТЫ («payout около 50%», «ROE 24%»). Без пересчёта гейт резал бы
    # каждое второе законное предложение — и синтез замолчал бы именно там, где должен
    # объяснять. Добавляем процентную форму каждой доли из диапазона 0..1.
    for raw in list(grounding_nums):
        if not _is_number(raw):
            continue
        value = float(raw.replace(",", "."))
        if 0 < value <= 1:
            grounding_nums.add(f"{value * 100:.2f}".rstrip("0").rstrip("."))
            grounding_nums.add(str(int(round(value * 100))))
    story_text = " ".join([str(story.get("why") or "")]
                          + [str(x) for x in (story.get("supports") or [])]
                          + [str(x) for x in (story.get("drags") or [])])
    ungrounded = []
    for num in re.findall(r"\d+(?:[.,]\d+)?", story_text):
        if num in grounding_nums:
            continue
        # Округления живой прозы: «около 24%» при 24,17 — законно.
        try:
            value = float(num.replace(",", "."))
        except ValueError:
            continue
        if any(abs(value - float(g.replace(",", "."))) < max(0.5, abs(value) * 0.02)
               for g in grounding_nums if _is_number(g)):
            continue
        ungrounded.append(num)
    if ungrounded:
        notes.append(f"ungrounded_numbers:{ungrounded[:5]}")

    # 🔴 Направление обязано совпадать со знаком апсайда. Иначе карточка противоречит
    # сама себе: число говорит «дешевле рынка», а объяснение под ним — «дороже». На
    # проверенных компаниях модель попадала верно, но «обычно попадает» — не гарантия,
    # а этот разрыв читатель заметит первым.
    if fair and isinstance(fair.get("upside_pct"), (int, float)) and story:
        upside = float(fair["upside_pct"])
        direction = str(story.get("direction") or "")
        expected = ("выше рынка" if upside > 3 else
                    "ниже рынка" if upside < -3 else "близко к рынку")
        if direction and direction != expected:
            notes.append(f"direction_vs_upside:{direction}!={expected}({upside}%)")

    # Справедливая цена в тексте не должна расходиться с посчитанной.
    if fair and fair.get("fair_price"):
        stated = re.findall(r"справедлив\w*\s+цен\w*[^\d]{0,24}(\d+(?:[.,]\d+)?)",
                            story_text, re.I)
        for raw in stated:
            try:
                value = float(raw.replace(",", "."))
            except ValueError:
                continue
            if abs(value - float(fair["fair_price"])) > float(fair["fair_price"]) * 0.03:
                notes.append(f"fair_price_mismatch:{raw}")
                break
    return notes


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def build_for_ticker(db: Session, ticker: str) -> CardOverviewSynthesis | None:
    """Собрать свод по одной компании и сохранить (published | rejected)."""
    ticker = ticker.upper()
    tabs = _tab_inputs(db, ticker)
    if len(tabs) < _MIN_TABS:
        logger.info("overview_synthesis: %s — разборов всего %d, свод не делаем",
                    ticker, len(tabs))
        return None
    fair = _fair_value(db, ticker)

    task = [f"Компания: {ticker}."]
    if fair:
        task.append("СПРАВЕДЛИВАЯ ЦЕНА ПЛАТФОРМЫ (уже посчитана, менять нельзя):\n"
                    + json.dumps(fair, ensure_ascii=False, indent=1))
    else:
        task.append("СПРАВЕДЛИВАЯ ЦЕНА: не рассчитана — объясняй качественно, БЕЗ чисел, "
                    "и честно скажи, что оценка недоступна.")
    task.append("\nРАЗБОРЫ ПО ВКЛАДКАМ:")
    for t in tabs:
        task.append(f"\n### {t['title']} ({t['tab']})\n{t['text']}")

    from app.services.llm import LLMError, complete
    try:
        result = complete(_SYSTEM, "\n".join(task), json_mode=True,
                          max_tokens=2500, temperature=0.3)
    except LLMError as e:
        logger.warning("overview_synthesis: %s — модель не ответила: %s", ticker, e)
        return None
    notes = _gate(result if isinstance(result, dict) else {}, tabs, fair, ticker)
    ok = not notes
    row = CardOverviewSynthesis(
        ticker=ticker,
        status="published" if ok else "rejected",
        verdict=(result or {}).get("verdict") if ok else None,
        pillars=(result or {}).get("pillars") if ok else None,
        fair_value_story=(result or {}).get("fair_value_story") if ok else None,
        what_would_change=(result or {}).get("what_would_change") if ok else None,
        inputs_used={"tabs": [t["tab"] for t in tabs],
                     "fair_value": bool(fair),
                     "raw_tail": None if ok else str(result)[:600]},
        gate_notes=notes or None,
        model_used="deepseek",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("overview_synthesis %s: %s (гейт: %s)", ticker, row.status,
                notes or "чисто")
    return row


SYNTHESIS_FILE = "overview_synthesis.json"


def file_synthesis(ticker: str) -> dict | None:
    """Свод, заготовленный в карточке (файл в репозитории).

    🔴 Зачем нужен второй источник. Ночной крон собирает по восемь компаний за раз —
    полный круг по 264 занимает больше недели, и всё это время у большинства карточек
    завершающего вывода нет. Заготовку можно собрать разом и положить в репозиторий:
    она едет на бой вместе с образом и работает сразу. БД остаётся главнее — там
    свежее, крон обновляет по мере устаревания.
    """
    raw = _read(ticker.upper(), SYNTHESIS_FILE)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        logger.warning("overview_synthesis: %s/%s не читается", ticker, SYNTHESIS_FILE)
        return None
    return data if isinstance(data, dict) and data.get("verdict") else None


def current(db: Session, ticker: str) -> CardOverviewSynthesis | None:
    """Последний опубликованный свод по компании (из БД)."""
    return (db.query(CardOverviewSynthesis)
            .filter(CardOverviewSynthesis.ticker == ticker.upper(),
                    CardOverviewSynthesis.status == "published")
            .order_by(CardOverviewSynthesis.created_at.desc()).first())


def _candidates(db: Session, batch: int, stale_days: int) -> list[str]:
    """Кого собирать в этот прогон: сперва те, у кого свода нет вовсе."""
    if not COMPANIES_DIR.exists():
        return []
    all_tickers = sorted(d.name for d in COMPANIES_DIR.iterdir()
                         if d.is_dir() and not d.name.startswith("."))
    from sqlalchemy import text as _sql
    seen = {r[0]: r[1] for r in db.execute(_sql(
        "SELECT ticker, max(created_at) FROM card_overview_synthesis "
        "WHERE status='published' GROUP BY ticker"
    )).all()}
    # Компания с заготовкой в карточке уже не «пустая» — крон идёт к тем, у кого
    # вывода нет вовсе, а не пересобирает готовое платной моделью.
    with_file = {t for t in all_tickers if (COMPANIES_DIR / t / SYNTHESIS_FILE).exists()}
    cutoff = datetime.now(timezone.utc).timestamp() - stale_days * 86400
    fresh = {t for t, ts in seen.items() if ts and ts.timestamp() >= cutoff}
    never = [t for t in all_tickers if t not in seen and t not in with_file]
    stale = [t for t in all_tickers if t in seen and t not in fresh]
    return (never + stale)[:batch]


def run_batch(db: Session, batch: int = 5, stale_days: int = 30,
              only_ticker: str | None = None) -> dict:
    """Пакетная сборка сводов. Маленькими партиями: это LLM-прогон на компанию."""
    queue = [only_ticker.upper()] if only_ticker else _candidates(db, batch, stale_days)
    stats = {"queued": len(queue), "published": 0, "rejected": 0, "skipped": 0}
    for ticker in queue:
        try:
            row = build_for_ticker(db, ticker)
        except Exception:  # noqa: BLE001
            logger.exception("overview_synthesis: %s не собран", ticker)
            continue
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("overview_synthesis.run_batch: %s", stats)
    return stats
