"""Перезапись ВЫВОДА вкладки, когда факт вышел за границу, названную самой прозой.

🔴 ЗАЧЕМ ОТДЕЛЬНО ОТ ПАТЧЕРА (владелец, 2026-08-08: «если цифры значительно
изменились, агент должен менять анализы/выводы, а не только числа»).
Точечный патчер (`card_prose_patcher`) чинит ЧИСЛО. Но бывает, что число ушло за
рамку, которую текст сам себе поставил, — и тогда неверно РАССУЖДЕНИЕ, а не цифра.
Живой пример с бою: у Башнефти цену Urals обновили на $75, а рядом остался сценарный
блок «медведь: $40–47, бык: $62–65» — оптимистичный сценарий оказался НИЖЕ факта.
Патчер такое не лечит по построению: он не имеет права придумывать новые уровни.

🔴 ЛЕСТНИЦА, А НЕ ЗАМЕНА. Перезапись — ТРЕТЬЯ ступень, редкая и дорогая:
  1) патч числа            — обычный случай, работает ежедневно;
  2) перезапись ВЫВОДА     — здесь: абзац-вывод переписывается целиком, факты рядом
                             не трогаются;
  3) полная перегенерация  — НЕ ДЕЛАЕМ. Проверено и записано в память проекта:
                             перегенерация по замечаниям критика дала БОЛЬШЕ грубых
                             ошибок, чем исходный текст.

🔴 CHAMPION / CHALLENGER, FAIL-CLOSED. Новая версия (challenger) публикуется, только
если прошла ВСЕ три проверки; иначе на витрине остаётся старая (champion):
  (1) все числа заземлены во входных данных — тот же принцип, что у патчера;
  (2) триггер закрыт — новая версия действительно содержит значение, из-за которого
      её запускали (иначе агент «переписал» мимо причины);
  (3) критик не нашёл РЕГРЕССИИ. Вопрос критику асимметричный — не «какая версия
      лучше» (на такой вопрос модель хвалит новую), а «какие утверждения НОВОЙ
      версии обоснованы ХУЖЕ, чем в старой».
Замечания критика НЕ идут на второй круг перегенерации: один challenger — один
вердикт. Провал → блок остаётся в очереди с пометкой, чинится в следующий прогон.

🔴 БЕЗ ВЕБА НА ЭТОМ ШАГЕ. В `card_review_agent` веб отключён сознательно: при живом
тесте поиск дестабилизировал агента (перебор запросов, не сходился к выводу).
Правильное разделение — отдельная фаза-добытчик собирает досье с капом на поиск, а
писатель работает уже по досье. Здесь первая фаза: писатель без веба, на внутренних
данных. Досье добавляется отдельно и не ломает этот контур.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.geo import CardProseOverlay
from app.services.card_prose_patcher import (
    _numbers, current_overlay, read_prose,
)

logger = logging.getLogger(__name__)

_KNOWLEDGE = Path(__file__).parent.parent.parent / "knowledge" / "agents"

# вкладка → методичка роли (те же файлы, по которым писали Claude-аналитики)
_ROLE_BY_TAB = {
    "macro": "macro-analyst",
    "markets": "market-analyst",
    "finance": "financial-analyst",
    "governance": "governance-analyst",
    "geo": "geo-company-analyst",
    "institutions": "institutional-company-analyst",
    "business": "business-model-analyst",
}

# Порог эскалации. У очереди ПАТЧЕЙ порог низкий (5%) — там дешёвая правка числа.
# Перезапись вывода дороже и рискованнее, поэтому нужен отдельный, выше: ниже этого
# уровня расхождение меняет цифру, но не переворачивает рассуждение.
_MIN_IMPACT_FOR_REWRITE = 25.0   # % от прибыли по коэффициентам самой карточки
_COOLDOWN_DAYS = 7               # не трогаем блок, если его недавно уже правили
_MAX_PROSE = 9000


def _methodology(tab: str, limit: int = 6000) -> str:
    role = _ROLE_BY_TAB.get(tab)
    if not role:
        return ""
    p = _KNOWLEDGE / f"{role}.md"
    try:
        return p.read_text(encoding="utf-8")[:limit] if p.exists() else ""
    except Exception:  # noqa: BLE001
        return ""


def escalation_reason(db: Session, ticker: str, tab: str, drift: dict | None) -> str | None:
    """Надо ли поднимать блок со ступени «патч» на ступень «перезапись вывода».

    Возвращает человекочитаемую причину или None. Критерий проверяемый, а не
    «когда сильно изменилось»: величина эффекта по коэффициентам САМОЙ карточки
    плюс операционный сигнал, который у нас уже копится бесплатно, — повторные
    отказы гейта патчера. Отказ гейта здесь не шум: если патчер второй раз подряд
    не может ни найти якорь, ни заземлить число, значит проза структурно разошлась
    с реальностью, и точечная правка ей уже не поможет.
    """
    reasons: list[str] = []
    if drift:
        impact = abs(float(drift.get("impact_pct") or 0))
        if impact >= _MIN_IMPACT_FOR_REWRITE:
            reasons.append(f"расхождение ≈{impact:.0f}% от {drift.get('impact_base') or 'прибыли'}")

    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    rows = (db.query(CardProseOverlay)
            .filter(CardProseOverlay.ticker == ticker.upper(),
                    CardProseOverlay.tab == tab,
                    CardProseOverlay.created_at >= cutoff)
            .order_by(CardProseOverlay.created_at.desc()).limit(4).all())
    fails = 0
    for r in rows:
        if r.status != "rejected":
            break  # успешная правка обрывает серию: блок ещё лечится патчем
        notes = " ".join(str(x) for x in (r.gate_notes or []))
        if "noop_no_change" in notes or "not_confirmed" in notes:
            break  # «изменений нет» — это НЕ провал, а честный ответ
        fails += 1
    if fails >= 2:
        reasons.append(f"патчер не смог поправить блок {fails} раза подряд")
    return "; ".join(reasons) or None


def _recent_touch(db: Session, ticker: str, tab: str) -> bool:
    """Блок недавно уже правили — не пускаем второй механизм поверх первого."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_COOLDOWN_DAYS)
    return db.query(CardProseOverlay).filter(
        CardProseOverlay.ticker == ticker.upper(),
        CardProseOverlay.tab == tab,
        CardProseOverlay.status == "published",
        CardProseOverlay.created_at >= cutoff).first() is not None


_WRITER_SYS = """Ты — аналитик платформы Basis (не брокер, без «купить/продать» и без
целевых цен). Тебе даны МЕТОДИКА твоей роли, ТЕКУЩИЙ ТЕКСТ вкладки карточки и
АКТУАЛЬНЫЕ ДАННЫЕ, которые разошлись с этим текстом настолько, что вывод в нём стал
неверным.

Задача: переписать ТОЛЬКО вывод — рассуждение и его следствия, — оставив фактическую
часть текста нетронутой.

🔴 ЧТО МОЖНО МЕНЯТЬ: формулировки вывода, направление и силу оценки, сценарные
уровни и их вероятности, трактовку фазы цикла, ранжирование рисков.
🔴 ЧТО НЕЛЬЗЯ ТРОГАТЬ: исторические факты и отчётные числа компании, структуру
собственности, состав менеджмента, справедливую цену и апсайд (их считает финансовый
слой платформы — цитируй существующие, не выводи свои), заголовки и структуру разделов.
🔴 ЧИСЛА — ТОЛЬКО ИЗ БЛОКА АКТУАЛЬНЫХ ДАННЫХ ИЛИ ИЗ САМОГО ТЕКСТА. Ни одного числа,
которого нет ни там, ни там. Если для нового уровня данных не хватает — не выдумывай
его, а напиши честно, что уровень требует пересчёта.
🔴 НЕ ОКРУГЛЯЙ ДО «КРАСИВОГО». Дано 82,27 — пиши «82,27» или «около 82», но НЕ «85»
и не «80-90»: округлённый вверх уровень выглядит правдоподобно и потому опаснее явной
ошибки. Первый же боевой прогон отклонён именно за это.
🔴 УСЛОВНЫЕ ПОРОГИ ФОРМУЛИРУЙ СЛОВАМИ, БЕЗ ЧИСЛА. Нельзя «эффект ослабнет, если рубль
уйдёт к 85» — числа 85 нет ни в данных, ни в тексте, это выдуманный порог, и правка
будет отклонена целиком (проверено шесть прогонов подряд на одной карточке). Пиши
«эффект ослабнет, если рубль заметно укрепится относительно текущего уровня» — смысл
тот же, выдумки нет. Это касается любых конструкций «если X дойдёт до N».
🔴 Сохраняй эпистемические пометки: (факт) / (оценка) / (суждение). Новое суждение
помечай суждением, а не фактом.
🔴 Никаких фамилий должностных лиц; про государство — только наблюдаемые изменения
правил и их экономические последствия.

Ответ — СТРОГО ОДИН JSON, без текста вокруг:
{"rewritten_md": "<полный текст вкладки с переписанным выводом>",
 "what_changed": "<1-2 предложения: что именно пересмотрено и почему>",
 "trigger_value": "<значение из актуальных данных, из-за которого правка>"}"""

_CRITIC_SYS = """Ты — критик-скептик аналитической платформы. Тебе даны СТАРАЯ и НОВАЯ
версии одного аналитического блока и АКТУАЛЬНЫЕ ДАННЫЕ.

🔴 Твой вопрос НЕ «какая версия лучше». Твой вопрос: КАКИЕ УТВЕРЖДЕНИЯ НОВОЙ ВЕРСИИ
ОБОСНОВАНЫ ХУЖЕ, ЧЕМ В СТАРОЙ. Ищи именно регрессии:
• появилось число, которого нет ни в актуальных данных, ни в старом тексте;
• исчез факт или оговорка, которые были в старой версии и не потеряли силу;
• суждение подано как факт (пропала эпистемическая пометка);
• вывод не следует из приведённых данных или противоречит другому месту текста;
• появилась рекомендация «купить/продать» или целевая цена.

Severity: high — публиковать нельзя (выдуманное число, потерянный существенный факт,
рекомендация); medium — заметный дефект, но текст не вводит в заблуждение; low — стиль.

Ответ — СТРОГО ОДИН JSON:
{"regressions": [{"what": "<в чём именно хуже>", "severity": "high|medium|low",
                  "quote": "<цитата из НОВОЙ версии>"}],
 "verdict": "<одно предложение>"}"""


def _grounding_ok(new_md: str, old_md: str, facts: str) -> list[str]:
    """Числа новой версии обязаны быть либо в актуальных данных, либо в старом тексте.

    Тот же принцип, что в гейте патчера, но по ПОЛНОМУ тексту: перезапись вывода —
    это как раз тот случай, когда модель охотнее всего добавит правдоподобную цифру.
    """
    allowed = set(_numbers(facts.replace(",", "."))) | set(_numbers(old_md.replace(",", ".")))
    # округления заземлённых значений — законны (проза пишет «~57%» от 57.07)
    for n in list(allowed):
        try:
            v = float(n)
        except ValueError:
            continue
        allowed |= {f"{round(v):g}", f"{round(v, 1):g}", f"{round(v, 2):g}"}
    bad = [n for n in set(_numbers(new_md.replace(",", "."))) if n not in allowed]
    # годы и проценты вероятностей — частый ложный флаг; их отсеиваем отдельно
    bad = [n for n in bad if not re.fullmatch(r"(19|20)\d\d", n)]
    return sorted(bad)[:8]


def _around_numbers(text: str, notes: list[str], width: int = 90) -> list[str]:
    """Фрагменты вокруг чисел, из-за которых отказ, — чтобы разбирать причину."""
    nums: list[str] = []
    for n in notes:
        nums += re.findall(r"'([\d.,]+)'", n)
    out = []
    for num in nums[:4]:
        i = text.find(num)
        if i >= 0:
            out.append(text[max(0, i - width):i + width].replace("\n", " "))
    return out or [text[:200]]


def _ask(system: str, task: str, max_tokens: int = 9000) -> dict | None:
    from app.services.llm import complete, LLMError
    try:
        res = complete(system, task, json_mode=True, max_tokens=max_tokens, temperature=0.2)
        return res if isinstance(res, dict) else None
    except LLMError as e:
        logger.warning("card_rewriter: LLM недоступен (%s)", e)
        return None


def rewrite_one(db: Session, ticker: str, tab: str, *, facts: str, reason: str,
                force: bool = False) -> CardProseOverlay | None:
    """Одна перезапись вывода: challenger → три проверки → публикация или отказ."""
    ticker = ticker.upper()
    if not force and _recent_touch(db, ticker, tab):
        logger.info("card_rewriter: %s/%s пропущен — блок правили меньше %d дней назад",
                    ticker, tab, _COOLDOWN_DAYS)
        return None
    champion, src = read_prose(db, ticker, tab)
    if not champion:
        return None

    method = _methodology(tab)
    task = (f"Компания: {ticker}. Вкладка: {tab}.\n"
            f"ПРИЧИНА ПЕРЕСМОТРА: {reason}\n\n"
            f"МЕТОДИКА РОЛИ:\n{method}\n\n"
            f"АКТУАЛЬНЫЕ ДАННЫЕ:\n{facts}\n\n"
            f"ТЕКУЩИЙ ТЕКСТ ВКЛАДКИ:\n<<<\n{champion[:_MAX_PROSE]}\n>>>")
    out = _ask(_WRITER_SYS, task)
    challenger = ((out or {}).get("rewritten_md") or "").strip()
    notes: list[str] = []
    if not challenger:
        notes.append("no_result")
    elif len(challenger) < len(champion) * 0.55:
        # усох больше чем на 45% — это уже не «переписан вывод», а потеря содержания
        notes.append(f"too_short({len(challenger)}/{len(champion)})")

    if not notes:
        ungrounded = _grounding_ok(challenger, champion, facts)
        if ungrounded:
            notes.append(f"ungrounded_numbers:{ungrounded[:4]}")

    # (2) триггер закрыт: новая версия должна содержать значение, из-за которого её звали
    if not notes:
        tv = str((out or {}).get("trigger_value") or "")
        tv_nums = _numbers(tv.replace(",", "."))
        if tv_nums and not any(n in challenger for n in tv_nums):
            notes.append("trigger_not_closed")

    # (3) критик — асимметрично: ищем РЕГРЕССИИ новой версии, не «что лучше»
    critique = None
    if not notes:
        critique = _ask(_CRITIC_SYS,
                        f"АКТУАЛЬНЫЕ ДАННЫЕ:\n{facts}\n\n"
                        f"СТАРАЯ ВЕРСИЯ:\n<<<\n{champion[:_MAX_PROSE]}\n>>>\n\n"
                        f"НОВАЯ ВЕРСИЯ:\n<<<\n{challenger[:_MAX_PROSE]}\n>>>",
                        max_tokens=3000)
        if critique is None:
            # критик не ответил — публиковать нельзя: непроверенное не выходит на витрину
            notes.append("critic_unavailable")
        else:
            high = [r for r in (critique.get("regressions") or [])
                    if str(r.get("severity")).lower() == "high"]
            if high:
                notes.append("critic_high:" + "; ".join(
                    str(r.get("what"))[:70] for r in high[:2]))

    ok = not notes
    parent = current_overlay(db, ticker, tab)
    row = CardProseOverlay(
        ticker=ticker, tab=tab, kind="rewrite",
        status="published" if ok else "rejected",
        patched_md=challenger if ok else None,
        original_md=champion if ok else None,
        change_note=(out or {}).get("what_changed"),
        evidence={"prose_source": src, "reason": reason,
                  "trigger_value": (out or {}).get("trigger_value"),
                  "critic": (critique or {}).get("verdict"),
                  "regressions": (critique or {}).get("regressions") or [],
                  # у ОТКЛОНЁННОЙ версии сам текст не публикуется, но без образца
                  # отказ невозможно разобрать: на первом же боевом прогоне гейт
                  # поймал «85», а посмотреть, в какой фразе оно стояло, было нечем
                  **({} if ok else {"rejected_sample": _around_numbers(challenger, notes)})},
        gate_notes=notes or None,
        parent_id=parent.id if (ok and parent) else None,
        model_used="deepseek",
    )
    db.add(row)
    db.commit()
    logger.info("card_rewriter %s/%s: %s %s", ticker, tab, row.status, notes or "")
    return row


def run_macro_rewrites(db: Session, batch: int = 3, only_ticker: str | None = None) -> dict:
    """Голова очереди макро-дрейфа: где вывод стал неверным — переписываем вывод.

    Батч намеренно крошечный: это дорогая ступень, и её адресаты — единицы. Замер на
    бою 2026-08-08: из 40 карточек с дрейфом эффект >100% прибыли у семи, 30-100% ещё
    у шести, у остальных мелочь. Гонять перезапись по всем 264 не нужно и вредно.
    """
    from app.services.macro_drift import company_drift, current_macro, drift_queue
    from app.services.card_prose_patcher import _drift_note, _macro_env_grounding

    stats = {"queued": 0, "published": 0, "rejected": 0, "skipped": 0, "tickers": []}
    now = current_macro(db)
    if only_ticker:
        item = company_drift(db, only_ticker.upper(), now)
        queue = [item] if item else []
    else:
        queue = drift_queue(db, limit=25)
        queue = [x for x in queue
                 if abs(float(x.get("impact_pct") or 0)) >= _MIN_IMPACT_FOR_REWRITE][:batch]
    stats["queued"] = len(queue)
    for item in queue:
        tk = item.get("ticker")
        reason = escalation_reason(db, tk, "macro", item)
        if not reason and not only_ticker:
            stats["skipped"] += 1
            continue
        # Контекст = общая макросреда (та же, что у патчера) + персональный дрейф
        # ЭТОЙ карточки. Персональная часть обязательна: без неё писатель не знает,
        # какое именно расхождение он должен закрыть, и правит «вообще».
        facts = "\n\n".join(x for x in (_macro_env_grounding(db), _drift_note(item)) if x)
        row = rewrite_one(db, tk, "macro", facts=facts,
                          reason=reason or "ручной прогон", force=bool(only_ticker))
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
            stats["tickers"].append(f"{tk}:{row.status}")
    logger.info("card_rewriter.run_macro_rewrites: %s", stats)
    return stats
