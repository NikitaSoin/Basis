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


def _rewrite_drift_note(item: dict) -> str:
    """Персональный дрейф для ПИСАТЕЛЯ — без служебного процента.

    🔴 Почему не переиспользуем `_drift_note` патчера. Тот пишет «по коэффициентам
    чувствительности это ≈136% годовой прибыли» — служебная метрика приоритета
    очереди. Писатель на бою дважды принял её за ПРОГНОЗ и выдал «прирост прибыли
    на 134%»; критик оба раза отклонил. Запрет в промпте такое не лечит — модель
    берёт первое похожее число из контекста (в памяти проекта: «контракт данных
    сильнее правил в промпте»). Поэтому число сюда просто НЕ ПОПАДАЕТ, а сила
    расхождения передаётся словом.
    """
    lines = [f"ЧТО ИЗМЕНИЛОСЬ С МОМЕНТА РАЗБОРА (разбор от {item.get('as_of')}, "
             f"{item.get('days_old')} дн. назад):"]
    for spec in (item.get("drift") or {}).values():
        lines.append(f"- {spec['title']}: было {spec['was']} {spec['unit']}, "
                     f"стало {spec['now']} {spec['unit']}")
    impact = abs(float(item.get("impact_pct") or 0))
    strength = ("очень крупное" if impact >= 100 else
                "крупное" if impact >= 50 else "заметное")
    lines.append(f"Для бизнеса этой компании расхождение {strength} — разбор писался "
                 f"в заметно другой обстановке, и вывод в нём мог устареть. "
                 f"НЕ ПЕРЕНОСИ эту оценку силы в текст как число: это внутренняя "
                 f"метрика приоритета, а НЕ прогноз прибыли и не темп её роста.")
    return "\n".join(lines)


def _commodity_facts(db: Session) -> str:
    """Сырьевые цены С ЯВНЫМ НАЗВАНИЕМ СОРТА и готовым дисконтом.

    🔴 Зачем отдельным блоком. В общем макро-контексте цена приходит под родовым
    словом «нефть» (это Brent), а карточка нефтяника рассуждает про URALS и про
    ДИСКОНТ к Brent. Писатель на бою трижды подряд — SIBN, BANE, TATN — перепутал
    сорта и выдумал величину дисконта; критик каждый раз отклонял. Числа при этом
    у нас ЕСТЬ (Urals 75,26, Brent 82,27, скидка 5,46) — просто не передавались.
    Даём их явно и готовыми, чтобы не осталось повода считать самому.
    """
    from sqlalchemy import text as _t
    rows = db.execute(_t("""
        SELECT i.code, i.title, m.value, m.as_of
        FROM macro_indicators i
        JOIN LATERAL (SELECT value, as_of FROM macro_data_points p
                      WHERE p.indicator_code = i.code AND p.metric = 'level'
                      ORDER BY as_of DESC LIMIT 1) m ON true
        WHERE i.code IN ('oil_brent', 'urals', 'urals_brent_spread', 'wb_gold', 'wb_silver')
    """)).fetchall()
    if not rows:
        return ""
    out = ["СЫРЬЕВЫЕ ЦЕНЫ (названия сортов точные, не путай их между собой):"]
    for code, title, value, as_of in rows:
        out.append(f"  {title}: {float(value):g} (на {as_of})")
    out.append("  Дисконт Urals к Brent БЕРИ ГОТОВЫМ из строки «Скидка на российскую "
               "нефть» — НЕ вычисляй его сам и не округляй.")
    return "\n".join(out)


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
        # 🔴 Сравнивать надо в ОДНОЙ нотации. Числа нормализуются к точке («82.27»),
        # а русская проза пишет запятую («82,27») — прямой поиск подстроки не
        # находил НИКОГДА, и проверка резала любую правку (три прогона подряд
        # trigger_not_closed при верном тексте). Нормализуем и текст тоже.
        hay = challenger.replace(",", ".")
        # плюс целая часть: проза законно округляет «82,27» до «около 82»
        want = set(tv_nums) | {n.split(".")[0] for n in tv_nums}
        if tv_nums and not any(n in hay for n in want):
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
        facts = "\n\n".join(x for x in (_macro_env_grounding(db), _commodity_facts(db),
                                        _rewrite_drift_note(item)) if x)
        row = rewrite_one(db, tk, "macro", facts=facts,
                          reason=reason or "ручной прогон", force=bool(only_ticker))
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
            stats["tickers"].append(f"{tk}:{row.status}")
    logger.info("card_rewriter.run_macro_rewrites: %s", stats)
    return stats


def markets_escalation(db: Session, ticker: str) -> tuple[str | None, str]:
    """Нужна ли перезапись вывода «Рынков» и какие данные ей дать.

    🔴 Якорь у «Рынков» СВОЙ, и он уже лежит в карточке: в `market.json` поле
    `commodity_exposure.revenue_commodities[].current_price.value` хранит цену,
    которую видел аналитик («около $47–57/барр (июль 2026)»), а `benchmark_key`
    связывает её с живым рядом. Коэффициенты чувствительности здесь не нужны —
    сравниваем записанное с текущим.

    Порог другой, чем у макро: там эффект считался в процентах прибыли через
    коэффициенты, здесь их нет — берём относительное отклонение цены. 30% по сырью
    это уже другая фаза цикла, а не колебание.

    🔴 ЧЕСТНОЕ ОГРАНИЧЕНИЕ. Цена «что видел аналитик» лежит в карточке ПРОЗОЙ, и
    регуляркой она берётся плохо: у ЧМК записано «~37 тыс. руб./т» (разряды словом),
    у ММК — «$1 156 за короткую тонну», хотя наш ряд в руб/т, то есть ДРУГИЕ ЕДИНИЦЫ.
    Поэтому здесь стоит предохранитель: расхождение больше чем в 5 раз считается
    ошибкой разбора строки, а не движением рынка, и молча пропускается с логом.
    Настоящее решение — типизированный реестр утверждений (задача #41): извлечь из
    прозы {значение, единица, к чему привязано} один раз, и дальше сверять кодом.
    До тех пор эскалация по «Рынкам» срабатывает редко и только там, где строка
    разобралась однозначно.
    """
    import json as _json
    from pathlib import Path as _Path
    from sqlalchemy import text as _t

    p = _Path(__file__).parent.parent.parent / "companies" / ticker.upper() / "market.json"
    if not p.exists():
        return None, ""
    try:
        card = _json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, ""
    reasons, facts = [], []
    for item in ((card.get("commodity_exposure") or {}).get("revenue_commodities") or []):
        key = (item.get("benchmark_key") or "")
        if not key.startswith("macro:"):
            continue
        code = key[6:]
        row = db.execute(_t("""
            SELECT value, as_of FROM macro_data_points
            WHERE indicator_code = :k AND metric = 'level'
            ORDER BY as_of DESC LIMIT 1
        """), {"k": code}).fetchone()
        if not row:
            continue
        now = float(row[0])
        title = db.execute(_t("SELECT title FROM macro_indicators WHERE code = :k"),
                           {"k": code}).scalar() or code
        facts.append(f"  {title}: {now:g} (на {row[1]})")
        # «что видел аналитик» — из прозы карточки: там диапазон словами, поэтому
        # берём все числа и сравниваем со средним. Точность здесь не нужна: решение
        # бинарное — та же фаза цикла или уже другая.
        was_raw = str((item.get("current_price") or {}).get("value") or "")
        # 🔴 Берём ТОЛЬКО числа при знаке валюты. Наивное «все числа подряд» ломается
        # об даты и дни: у BANE строка «около $47–57/барр (июль 2026)… $40–47, после
        # 14 июля выше $50 (к 20 июля ~$57)» давала среднее 229, у ROSN — 536, и
        # детектор объявлял «падение на 77%» там, где цена выросла.
        # разряды пишут пробелом («$4 073»), и без этого «4 073» распадалось на «4»:
        # у PLZL золото «в разборе ~4» против 4073 сейчас — мнимый рост в 1000 раз
        _NUM = r"\d{1,3}(?:[\s\u00a0]\d{3})+(?:[.,]\d+)?|\d{1,6}(?:[.,]\d+)?"
        raw_hits = re.findall(rf"[$₽]\s*({_NUM})", was_raw)          # «$4 073»
        raw_hits += re.findall(rf"({_NUM})\s*(?:руб|₽|долл|\$)", was_raw)  # «61 772 руб/т»
        nums = [float(x.replace("\u00a0", "").replace(" ", "").replace(",", "."))
                for x in raw_hits]
        nums = [x for x in nums if 0 < x < 100000]
        if not nums:
            continue
        was = sum(nums) / len(nums)
        # 🔴 Предохранитель на разбор. Отклонение в разы почти всегда означает, что
        # мы неверно вытащили «что видел аналитик» (единицы, разряды, чужое число),
        # а не что рынок изменился в разы. Такое молча эскалировать нельзя — цена
        # ошибки тут переписанный вывод на витрине.
        if was and now and (max(now, was) / min(now, was)) > 5:
            logger.warning("markets_escalation %s: подозрительное расхождение "
                           "%s (в разборе %.4g, сейчас %.4g) — пропускаю, похоже на "
                           "ошибку разбора строки «%s»", ticker, title, was, now,
                           was_raw[:80])
            continue
        if was and abs(now - was) / was >= 0.30:
            reasons.append(f"{title}: в разборе ~{was:.0f}, сейчас {now:g} "
                           f"({(now - was) / was * 100:+.0f}%)")
    # Второй, более надёжный сигнал — УСТАРЕВШИЕ УТВЕРЖДЕНИЯ. Цена в прозе разбирается
    # плохо (единицы, разряды словом), а год записан однозначно: если разбор говорит
    # «в 2024 году добыто столько-то», данные за 2025 уже вышли, и утверждение устарело
    # независимо от того, верным ли оно было. Это не оценка содержания, а измерение
    # отставания от календаря — то, что код умеет честно.
    from app.services.card_claims import card_claims
    cl = card_claims(ticker)
    stale = [c for c in cl.get("claims") or [] if c.get("stale")]
    if stale:
        reasons.append(f"утверждений с устаревшей датой: {len(stale)} "
                       f"(максимальное отставание {cl.get('max_lag_years')} лет)")
        facts.append("УСТАРЕВШИЕ УТВЕРЖДЕНИЯ РАЗБОРА (ссылаются на прошедшие периоды; "
                     "свежих чисел взамен у тебя НЕТ — не выдумывай их, а честно "
                     "пометь, что данные требуют обновления):")
        for c in stale[:4]:
            facts.append(f"  [{c['type']}, {c.get('year')}] {c['claim'][:150]}")

    if not reasons:
        return None, ""
    facts.insert(0, "ТЕКУЩИЕ ЦЕНЫ РЫНКОВ КОМПАНИИ (названия точные, не путай сорта):")
    facts.append("Расхождение с тем, что заложено в разборе: " + "; ".join(reasons))
    facts.append("Это ОЦЕНКА СИЛЫ расхождения, а не прогноз выручки или прибыли — "
                 "не переноси проценты отклонения в текст как темп роста.")
    return "; ".join(reasons), "\n".join(facts)


def run_markets_rewrites(db: Session, batch: int = 3, only_ticker: str | None = None,
                         use_web: bool = True) -> dict:
    """Перезапись выводов «Рынков»: цена ушла из фазы цикла ИЛИ утверждения устарели.

    use_web=True включает фазу-добытчика для устаревших утверждений — только там, где
    внутренних данных заведомо нет (объём рынка за прошлый год из внешней статистики).
    """
    from sqlalchemy import text as _t

    if only_ticker:
        candidates = [only_ticker.upper()]
    else:
        candidates = [r[0] for r in db.execute(_t(
            "SELECT ticker FROM companies ORDER BY market_cap DESC NULLS LAST")).fetchall()]
    stats = {"checked": 0, "published": 0, "rejected": 0, "skipped": 0, "tickers": []}
    for tk in candidates:
        if stats["published"] + stats["rejected"] >= batch and not only_ticker:
            break
        stats["checked"] += 1
        reason, facts = markets_escalation(db, tk)
        if not reason:
            continue
        # Если устарели УТВЕРЖДЕНИЯ (а не цена), писателю нечем их заменить из
        # внутренних данных — здесь и нужна фаза-добытчик. Веба у писателя нет и не
        # будет: он получает готовое досье. Пустое досье не блокирует прогон —
        # писатель тогда обязан честно пометить, что данные требуют обновления.
        if use_web and "устаревшей датой" in reason:
            need = "\n".join(l for l in facts.split("\n") if l.startswith("  ["))
            if need:
                d = scout_dossier(db, tk, need)
                block = dossier_block(d)
                if block:
                    facts += "\n\n" + block
                logger.info("card_rewriter %s: досье — фактов %d, не найдено %d",
                            tk, len(d.get("facts") or []), len(d.get("not_found") or []))
        row = rewrite_one(db, tk, "markets", facts=facts,
                          reason=f"цена рынка ушла за рамки разбора: {reason}",
                          force=bool(only_ticker))
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
            stats["tickers"].append(f"{tk}:{row.status}")
    logger.info("card_rewriter.run_markets_rewrites: %s", stats)
    return stats


# ============================================================================
# ФАЗА-ДОБЫТЧИК: досье из веба ОТДЕЛЬНО от писателя
#
# 🔴 Почему двумя фазами, а не «дать писателю веб». В card_review_agent веб отключён
# сознательно: при живом тесте один агент, который И ИЩЕТ, И СВОДИТ, уходил в перебор
# запросов и не сходился к выводу. Разделение снимает причину — добытчик отвечает
# только за факты со ссылками и не обязан ничего решать, писатель получает готовое
# досье и не имеет доступа к поиску вообще.
#
# 🔴 Пустое досье — это НОРМАЛЬНЫЙ исход, а не сбой. Если фактов не нашлось, перезапись
# откладывается: лучше устаревший текст, чем свежий и выдуманный. Тот же принцип, что
# у гейта заземления.
# ============================================================================
_SCOUT_SYS = """Ты — добытчик фактов для аналитической платформы. Тебе дан ЗАПРОС: какие
именно данные нужны, чтобы обновить устаревшее утверждение в разборе компании.

Твоя задача — НАЙТИ ФАКТЫ И ВЕРНУТЬ ИХ СО ССЫЛКАМИ. Ты НИЧЕГО не решаешь и не
формулируешь выводов: их сделает другой аналитик по твоему досье.

🔴 Правила:
• ищи экономно: несколько запросов, не долби один источник;
• каждый факт — с числом, единицей, периодом и ССЫЛКОЙ на источник;
• чего не нашёл — так и скажи, НЕ ДОДУМЫВАЙ. Пустое досье лучше выдуманного;
• единицы переноси как в источнике, не пересчитывай;
• никаких прогнозов и оценок от себя.

Финальный ответ — строго JSON, без вызова инструментов:
{"facts": [{"what": "<что за показатель>", "value": "<число с единицей>",
            "period": "<год/квартал/дата>", "source": "<название>", "url": "<ссылка>"}],
 "not_found": ["<чего найти не удалось>"],
 "note": "<одно предложение о полноте досье>"}"""


def scout_dossier(db: Session, ticker: str, need: str, *, web_calls: int = 3) -> dict:
    """Собрать досье под конкретную нехватку данных. Возвращает {facts, not_found}."""
    from app.services.agent_runner import run_agent
    from app.services.agent_tools import WEB_TOOLS_SCHEMA
    task = (f"Компания: {ticker}. Нужны свежие данные, чтобы обновить разбор.\n"
            f"ЧЕГО НЕ ХВАТАЕТ:\n{need}\n\n"
            f"Сегодня: {datetime.now(timezone.utc).date().isoformat()}. "
            f"Нужны САМЫЕ СВЕЖИЕ доступные значения с указанием периода.")
    try:
        res = run_agent(db, system_prompt=_SCOUT_SYS, task=task,
                        tools_schema=WEB_TOOLS_SCHEMA, allowed_ticker=ticker,
                        max_steps=6, web_call_cap=web_calls, step_max_tokens=2200)
    except Exception as e:  # noqa: BLE001
        logger.warning("scout_dossier %s: %s", ticker, type(e).__name__)
        return {"facts": [], "not_found": ["добытчик не отработал"], "error": str(e)[:120]}
    out = res.get("result") or {}
    facts = [f for f in (out.get("facts") or [])
             if isinstance(f, dict) and f.get("value") and f.get("url")]
    return {"facts": facts, "not_found": out.get("not_found") or [],
            "note": out.get("note"), "tokens": res.get("tokens_used"),
            "stopped": res.get("stopped_reason")}


def dossier_block(dossier: dict) -> str:
    """Досье в виде блока фактов для писателя. Пустое — пустая строка (значит,
    перезапись пойдёт без внешних данных или не пойдёт вовсе)."""
    facts = dossier.get("facts") or []
    if not facts:
        return ""
    lines = ["ДОСЬЕ ИЗ ВНЕШНИХ ИСТОЧНИКОВ (проверено добытчиком, бери числа отсюда):"]
    for f in facts[:8]:
        lines.append(f"  {f.get('what')}: {f.get('value')} ({f.get('period')}) "
                     f"— {f.get('source')}")
    if dossier.get("not_found"):
        lines.append("НЕ НАЙДЕНО (так и напиши, что данных нет, ничего не выдумывай): "
                     + "; ".join(str(x)[:80] for x in dossier["not_found"][:3]))
    return "\n".join(lines)
