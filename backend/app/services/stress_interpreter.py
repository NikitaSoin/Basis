"""Качественный разбор готового сценария стресс-теста («что это вообще значит»).

🔴 ЗАЧЕМ (владелец, 2026-08-08): «когда выбираешь конкретный сценарий — там нет
никакого ответа от ЛЛМ… качественная интерпретация могла бы идти от агентов по
политике/экономике/институтам, на основе карточек и данных прикинуть кому хреново, а
кому нет». Числовой компас отвечает «кто вверх, кто вниз», но не «почему» — и список
из тридцати тикеров без объяснения читается как случайный, даже когда он верный.

Что здесь происходит: разбор НЕ считает сценарий заново и НЕ спорит с расчётом. Он
берёт уже посчитанную реакцию (stress_scenarios.compute_impact) как ДАННОСТЬ и
объясняет её словами, опираясь на то, что платформа уже знает:
  - своды «Обзора» по компаниям из верха и низа списка (чем компания держится и что
    её тянет вниз — итог всех семи вкладок карточки);
  - геополитический барометр (сценарная рамка S1-S4, секторные флаги, очаги);
  - институциональный барометр (сценарий среды, алерты, институциональный пол CRP);
  - текущие макроуровни (ставка/курс/нефть) — точка, ОТ которой считается шок.

🔴 ЧТО ПРОВЕРЯЕТ КОД, А НЕ МОДЕЛЬ (гейт fail-closed, rejected на витрину не идёт):
  - названы только те компании, которые реально есть в расчёте, и в ПРАВИЛЬНОЙ
    половине списка (нельзя объявить пострадавшим того, кто у нас в выигравших);
  - все числа в прозе заземлены во входных данных (модель не дорисовывает «ВВП
    упадёт на 3%»);
  - нет «купить/продать», целевых цен и рекомендаций (конституция платформы);
  - есть блок «чего расчёт не видит» — без него разбор выглядит всезнающим, а он
    построен на неполном покрытии факторов.

🔴 Своей реакции компаний здесь НЕТ и быть не может: единственный источник чисел —
факторный движок. Разбор их ОБЪЯСНЯЕТ. Второе число другой методикой на том же
экране уже ломало доверие (карточка GAZP: тело −11%, рейл +89%).

Хранится версионно в БД (StressInterpretation), собирается кроном раз в неделю и по
ручному триггеру — не на каждый запрос пользователя: набор пресетов фиксирован,
экспозиции компаний меняются медленно, а прогон платный.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.stress import StressInterpretation

logger = logging.getLogger(__name__)

# Сколько компаний из верха и низа списка отдаём модели со сводом карточки. Больше —
# дороже прогон и длиннее вход, а разбор всё равно называет 3-6 имён: остальные нужны
# ему как фон, а не как материал для каждого абзаца.
_CARDS_PER_SIDE = 6
_VERDICT_CHARS = 520
_PILLAR_CHARS = 160

# Тот же запрет, что в своде «Обзора»: платформа не советует. «Рекомендация совета
# директоров» — корпоративная процедура, а не наш совет, поэтому маска узкая.
_BANNED = re.compile(r"куп(ить|ать)|прода(ть|вать)|шорт|целев\w+ цен|"
                     r"мы\s+рекоменду|рекомендуем|наша\s+рекомендаци|"
                     r"инвестидея|наша цель", re.I)


def _compact_geo(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    sc = payload.get("scenario") or {}
    flags = []
    for f in (payload.get("sector_flags") or [])[:8]:
        if isinstance(f, dict):
            flags.append({"sector": f.get("sector"), "direction": f.get("direction"),
                          "why": str(f.get("reasoning") or "")[:220]})
    regions = []
    for r in (payload.get("regions") or []):
        if isinstance(r, dict):
            regions.append({"key": r.get("key"), "label": r.get("label") or r.get("title"),
                            "direction": r.get("direction") or r.get("trend")})
    return {
        "as_of": payload.get("as_of"),
        "overall": (payload.get("barometer") or {}).get("overall"),
        "label": (payload.get("barometer") or {}).get("label"),
        "current_lean": sc.get("current_lean"),
        "probabilities_6m": sc.get("probabilities_6m"),
        "sector_flags": flags,
        "regions": regions,
    }


def _compact_inst(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    sc = payload.get("scenario") or {}
    alerts = [str((a or {}).get("title") or "")[:180]
              for a in (payload.get("alerts") or [])[:4] if isinstance(a, dict)]
    return {
        "as_of": payload.get("as_of"),
        "overall": (payload.get("barometer") or {}).get("overall"),
        "label": (payload.get("barometer") or {}).get("label"),
        "scenario": sc.get("current"),
        "probabilities": sc.get("probabilities"),
        "crp_floor_pp": payload.get("institutional_crp_floor_pp"),
        "alerts": alerts,
    }


def _barometers(db: Session) -> dict:
    """Барометры читаем через единый read-path (published-версия из БД, файл —
    фолбэк). Мягко: без барометра разбор беднее, но возможен."""
    out: dict = {}
    try:
        from app.services.barometer_store import get_payload_with_meta
    except Exception:  # noqa: BLE001 — модуль недоехал на полу-выкаченном деплое
        logger.warning("stress_interpreter: barometer_store недоступен")
        return out
    for kind, compact, key in (("geo", _compact_geo, "geo_barometer"),
                               ("inst", _compact_inst, "institutional_barometer")):
        try:
            payload = get_payload_with_meta(db, kind)
        except Exception:  # noqa: BLE001
            logger.warning("stress_interpreter: барометр %s не прочитан", kind, exc_info=True)
            continue
        compacted = compact(payload)
        if compacted:
            out[key] = compacted
    return out


def _card(db: Session, row: dict) -> dict | None:
    """Свод «Обзора» по компании — то, что платформа уже знает о ней целиком."""
    ticker = row["ticker"]
    data = None
    try:
        from app.services.overview_synthesis import current, file_synthesis
        db_row = current(db, ticker)
        if db_row is not None and db_row.verdict:
            data = {"verdict": db_row.verdict, "pillars": db_row.pillars}
        else:
            data = file_synthesis(ticker)
    except Exception:  # noqa: BLE001
        logger.warning("stress_interpreter: свод по %s не прочитан", ticker, exc_info=True)
    if not isinstance(data, dict) or not data.get("verdict"):
        return None
    pillars = []
    for p in (data.get("pillars") or []):
        if not isinstance(p, dict) or p.get("stance") == "нейтрально":
            continue
        pillars.append({"stance": p.get("stance"), "point": str(p.get("point") or "")[:_PILLAR_CHARS]})
    return {
        "ticker": ticker, "name": row.get("name"), "sector": row.get("sector"),
        "reaction_pct": row.get("reaction_pct"),
        "verdict": str(data["verdict"])[:_VERDICT_CHARS],
        "pillars": pillars[:4],
    }


def _cards(db: Session, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows[:_CARDS_PER_SIDE]:
        card = _card(db, r)
        if card:
            out.append(card)
    return out


def _levels(db: Session) -> dict | None:
    """Точка отсчёта: от каких ставки/курса/нефти считается шок."""
    try:
        from app.services.stress_numeric import get_current_levels
        levels = get_current_levels(db)
    except Exception:  # noqa: BLE001
        return None
    return levels if isinstance(levels, dict) else None


def build_snapshot(db: Session, scenario_key: str) -> dict | None:
    """Полный вход разбора. None — сценарий неизвестен или расчёт не удался."""
    from app.services.stress_scenarios import build_scenario_result

    result = build_scenario_result(db, scenario_key, None, None)
    if not isinstance(result, dict) or result.get("error"):
        return None
    winners = result.get("winners") or []
    losers = result.get("losers") or []
    # Нужны ОБЕ стороны: гейт проверяет, что пострадавшие названы из низа списка, а
    # устойчивые — из верха. Без одной из сторон проверять нечем, а разбор «все
    # одинаково» ничего не объясняет — честнее не делать его вовсе.
    if not winners or not losers:
        return None
    return {
        "scenario": result.get("scenario"),
        "reaction": {
            "winners": [{k: w.get(k) for k in ("ticker", "name", "sector", "reaction_pct")}
                        for w in winners],
            "losers": [{k: l.get(k) for k in ("ticker", "name", "sector", "reaction_pct")}
                       for l in losers],
            "sectors": (result.get("sectors") or [])[:14],
            "ranked_from": result.get("ranked_from"),
            "total_companies": result.get("total_companies"),
            "companies_with_signal": result.get("companies_with_signal"),
            # доля вселенной, у которой фактор вообще тегирован — материал для
            # честного блока «чего расчёт не видит»
            "coverage_by_factor_pct": result.get("coverage_by_factor"),
        },
        "cards_hit": _cards(db, losers),
        "cards_resilient": _cards(db, winners),
        "current_levels": _levels(db),
        **_barometers(db),
    }


_SYSTEM = """Ты — аналитик платформы Basis (независимая аналитика для частного
инвестора; НЕ брокер, НЕ даёт сигналов «купить/продать» и целевых цен).

Тебе дан ГОТОВЫЙ сценарий стресс-теста и УЖЕ ПОСЧИТАННАЯ реакция компаний на него
(факторный движок платформы), плюс то, что платформа знает о среде: геополитический и
институциональный барометры, текущие макроуровни и своды карточек по компаниям из
верха и низа списка.

Твоя задача — объяснить сценарий словами. Пользователь видит список тикеров со
стрелками и не понимает, почему они там оказались и что вообще произойдёт с экономикой.

🔴 РЕАКЦИЮ НЕ ПЕРЕСЧИТЫВАЙ И НЕ ОСПАРИВАЙ. Проценты уже посчитаны движком — ты
объясняешь ИХ, а не выводишь свои. Своих чисел не выдумывай: любое число в твоём
тексте обязано присутствовать во входных данных.

🔴 Компании называй ТОЛЬКО из переданных списков и ТОЛЬКО на своей стороне: в
«кому тяжелее» (hit_hard) — из списка losers, в «кто держится» (resilient) — из
списка winners. Списки относительные: winners — верх ранжирования, losers — низ.
Смотри на сами проценты и говори то, что в них есть: если в сценарии почти все в
минусе, winners — это «теряют меньше остальных», а не «зарабатывают»; если почти все
в плюсе, losers — «выигрывают меньше», а не «страдают». Знак не переворачивай.

Верни JSON:
{
  "headline": "одно предложение: суть сценария для рынка, без воды",
  "economy": "3-5 предложений: что происходит в экономике страны при таком сценарии —
              спрос, бюджет, инфляция, ставка, экспорт. Это фон, на котором дальше
              разбираются компании.",
  "channels": [
    {"channel": "короткое имя канала (спрос, ставка, курс, сырьё, санкции, налоги,
                 логистика, бюджет)",
     "how": "1-2 предложения: как именно этот канал доносит сценарий до бизнеса",
     "who": "кого он задевает сильнее всего — КОРОТКАЯ ИМЕННАЯ ГРУППА из отраслей,
             без глагола и без вводных слов: «банки и девелоперы», «экспортёры сырья».
             Не пиши «сильнее всего задевает…» — эта подводка уже есть на экране"}
  ],
  "hit_hard": [
    {"ticker": "ТИКЕР из списка losers",
     "why": "1-2 предложения: почему ИМЕННО эта компания страдает — опираясь на свод
             её карточки (чем держится бизнес и что его тянет вниз), а не на общие слова"}
  ],
  "resilient": [
    {"ticker": "ТИКЕР из списка winners",
     "why": "1-2 предложения: за счёт чего держится или выигрывает"}
  ],
  "sector_note": "1-3 предложения: секторная картина целиком — где перевес и почему",
  "blind_spots": ["2-4 пункта: чего этот расчёт НЕ видит — конкретно, без общих
                  оговорок. Опирайся на coverage_by_factor_pct (доля компаний, у
                  которых фактор вообще размечен: где она низкая, «нет реакции»
                  означает «нет данных», а не «не заденет»), а также на то, что движок
                  не моделирует события одной компании, вторичные эффекты, ликвидность
                  и долговую нагрузку"],
  "watch": ["2-4 наблюдаемых признака: по чему станет понятно, что сценарий разворачивается"]
}

hit_hard — 3-6 компаний, resilient — 2-5, channels — 3-5.

Пиши по-русски, спокойно и предметно, как аналитик для взрослого читателя. Не
используй слова «купить», «продать», «рекомендуем», «целевая цена». Не называй
фамилий должностных лиц. Не обещай будущего как факта: сценарий — это допущение.

Служебные ключи факторов в русский текст не переноси — называй их по-русски:
rate — ставка, demand — спрос, fx — курс, commodity — сырьё, sanctions — санкции,
conflict — конфликт, fiscal — налоги и бюджет, refi — рефинансирование долга."""


def _is_number(s: str) -> bool:
    try:
        float(s.replace(",", "."))
        return True
    except ValueError:
        return False


def _grounding_numbers(snapshot: dict) -> set[str]:
    blob = json.dumps(snapshot, ensure_ascii=False)
    # Разряды в прозе карточек пишутся с пробелом («3 050 млн»), а автор разбора
    # склеивает их — иначе гейт объявит законное число выдумкой (на этом в своде
    # «Обзора» разом отвалились 17 годных выводов).
    blob = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", blob)
    nums = set(re.findall(r"\d+(?:[.,]\d+)?", blob))
    nums |= {n.replace(",", ".") for n in nums}
    nums |= {n.replace(".", ",") for n in nums}
    # Вероятности барометра лежат долями (0.64), а в прозе живут процентами (64%).
    for raw in list(nums):
        if not _is_number(raw):
            continue
        value = float(raw.replace(",", "."))
        if 0 < value <= 1:
            nums.add(f"{value * 100:.2f}".rstrip("0").rstrip("."))
            nums.add(str(int(round(value * 100))))
    return nums


def _ungrounded(text: str, grounding: set[str]) -> list[str]:
    out = []
    for num in re.findall(r"\d+(?:[.,]\d+)?", text):
        if num in grounding:
            continue
        value = float(num.replace(",", ".")) if _is_number(num) else None
        if value is None:
            continue
        # Годы — законная историческая ссылка («как в 2022»), не выдуманная величина.
        if value.is_integer() and 1990 <= value <= 2035:
            continue
        # Округления живой прозы: «около 21%» при 21,4 — законно.
        if any(abs(value - float(g.replace(",", "."))) < max(0.5, abs(value) * 0.02)
               for g in grounding if _is_number(g)):
            continue
        out.append(num)
    return out


def _gate(result: dict, snapshot: dict) -> list[str]:
    """Код-проверка перед публикацией. Пусто = чисто."""
    notes: list[str] = []
    if not isinstance(result, dict):
        return ["not_a_dict"]

    headline = str(result.get("headline") or "").strip()
    if len(headline) < 20:
        notes.append("headline_too_short")
    if len(headline) > 400:
        notes.append("headline_too_long")

    economy = str(result.get("economy") or "").strip()
    if len(economy) < 120:
        notes.append("economy_too_short")
    if len(economy) > 2000:
        notes.append("economy_too_long")

    channels = result.get("channels")
    if not isinstance(channels, list) or len(channels) < 2:
        notes.append("channels_missing")
    elif any(not isinstance(c, dict) or not str(c.get("how") or "").strip() for c in channels):
        notes.append("channel_malformed")

    blind = result.get("blind_spots")
    # Разбор без «чего не видно» выглядит всезнающим, а он стоит на неполном
    # покрытии факторов — это не украшение, а условие честности блока.
    if not isinstance(blind, list) or len(blind) < 2:
        notes.append("blind_spots_missing")

    reaction = snapshot.get("reaction") or {}
    winners = {w["ticker"] for w in (reaction.get("winners") or []) if w.get("ticker")}
    losers = {l["ticker"] for l in (reaction.get("losers") or []) if l.get("ticker")}

    for field, allowed, lo, hi in (("hit_hard", losers, 2, 8), ("resilient", winners, 2, 8)):
        items = result.get(field)
        if not isinstance(items, list) or not (lo <= len(items) <= hi):
            notes.append(f"{field}_count")
            continue
        for it in items:
            if not isinstance(it, dict) or not str(it.get("why") or "").strip():
                notes.append(f"{field}_malformed")
                break
            ticker = str(it.get("ticker") or "").upper()
            # 🔴 Главная проверка блока: нельзя объявить пострадавшим того, кто у нас
            # в выигравших. Читатель сверит объяснение со списком под ним за секунду.
            if ticker not in allowed:
                notes.append(f"{field}_wrong_side:{ticker or '—'}")
                break

    blob = json.dumps(result, ensure_ascii=False)
    if _BANNED.search(blob):
        notes.append("banned_wording")

    prose = " ".join([headline, economy, str(result.get("sector_note") or "")]
                     + [str((c or {}).get("how", "")) + " " + str((c or {}).get("who", ""))
                        for c in (channels if isinstance(channels, list) else [])]
                     + [str((i or {}).get("why", ""))
                        for f in ("hit_hard", "resilient")
                        for i in (result.get(f) if isinstance(result.get(f), list) else [])]
                     + [str(x) for x in (blind if isinstance(blind, list) else [])]
                     + [str(x) for x in (result.get("watch") or [])])
    ungrounded = _ungrounded(prose, _grounding_numbers(snapshot))
    if ungrounded:
        notes.append(f"ungrounded_numbers:{ungrounded[:5]}")
    return notes


def build_for_scenario(db: Session, scenario_key: str) -> StressInterpretation | None:
    """Собрать разбор одного сценария и сохранить (published | rejected)."""
    snapshot = build_snapshot(db, scenario_key)
    if snapshot is None:
        logger.info("stress_interpreter: %s — расчёт не дал списка, разбор не делаем",
                    scenario_key)
        return None

    task = ["СЦЕНАРИЙ:", json.dumps(snapshot["scenario"], ensure_ascii=False, indent=1),
            "\nПОСЧИТАННАЯ РЕАКЦИЯ (движок платформы, менять нельзя):",
            json.dumps(snapshot["reaction"], ensure_ascii=False, indent=1)]
    if snapshot.get("current_levels"):
        task.append("\nТЕКУЩИЕ МАКРОУРОВНИ (точка отсчёта шока):\n"
                    + json.dumps(snapshot["current_levels"], ensure_ascii=False))
    if snapshot.get("geo_barometer"):
        task.append("\nГЕОПОЛИТИЧЕСКИЙ БАРОМЕТР:\n"
                    + json.dumps(snapshot["geo_barometer"], ensure_ascii=False, indent=1))
    if snapshot.get("institutional_barometer"):
        task.append("\nИНСТИТУЦИОНАЛЬНЫЙ БАРОМЕТР:\n"
                    + json.dumps(snapshot["institutional_barometer"], ensure_ascii=False, indent=1))
    if snapshot.get("cards_hit"):
        task.append("\nСВОДЫ КАРТОЧЕК — НИЗ СПИСКА (losers):\n"
                    + json.dumps(snapshot["cards_hit"], ensure_ascii=False, indent=1))
    if snapshot.get("cards_resilient"):
        task.append("\nСВОДЫ КАРТОЧЕК — ВЕРХ СПИСКА (winners):\n"
                    + json.dumps(snapshot["cards_resilient"], ensure_ascii=False, indent=1))

    from app.services.llm import LLMError, complete
    try:
        result = complete(_SYSTEM, "\n".join(task), json_mode=True,
                          max_tokens=3000, temperature=0.3)
    except LLMError as e:
        logger.warning("stress_interpreter: %s — модель не ответила: %s", scenario_key, e)
        return None

    notes = _gate(result if isinstance(result, dict) else {}, snapshot)
    # 🔴 Один ремонтный проход. Гейт бракует ВЕСЬ разбор за одну оплошность — чаще
    # всего за число, которого нет во входных данных, или за компанию, названную не с
    # той стороны списка. Выбрасывать из-за этого связный анализ расточительно: модель
    # почти всегда чинит ровно указанное место. Проход РОВНО один — дальше честный
    # rejected, а не бесконечная торговля с моделью.
    repaired = bool(notes)
    if notes:
        logger.info("stress_interpreter: %s — ремонтный проход, замечания: %s",
                    scenario_key, notes)
        repair = ("\n\nТвой предыдущий ответ не прошёл проверку. Замечания кода:\n"
                  + "\n".join(f"- {n}" for n in notes)
                  + "\n\nВерни ПОЛНЫЙ JSON того же формата, исправив ровно эти места и "
                    "сохранив остальное. ungrounded_numbers — числа, которых нет во "
                    "входных данных: убери их или замени на те, что переданы. "
                    "wrong_side — компания названа не с той стороны: возьми тикер из "
                    "нужного списка. Предыдущий ответ:\n"
                  + json.dumps(result, ensure_ascii=False)[:4000])
        try:
            result = complete(_SYSTEM, "\n".join(task) + repair, json_mode=True,
                              max_tokens=3000, temperature=0.2)
            notes = _gate(result if isinstance(result, dict) else {}, snapshot)
        except LLMError as e:
            logger.warning("stress_interpreter: %s — ремонт не удался: %s", scenario_key, e)
    ok = not notes
    data = result if isinstance(result, dict) else {}
    row = StressInterpretation(
        scenario_key=scenario_key,
        status="published" if ok else "rejected",
        headline=data.get("headline") if ok else None,
        sections={k: data.get(k) for k in
                  ("economy", "channels", "hit_hard", "resilient",
                   "sector_note", "blind_spots", "watch")} if ok else None,
        inputs_used={
            "cards_hit": [c["ticker"] for c in snapshot.get("cards_hit") or []],
            "cards_resilient": [c["ticker"] for c in snapshot.get("cards_resilient") or []],
            "geo_barometer_as_of": (snapshot.get("geo_barometer") or {}).get("as_of"),
            "institutional_barometer_as_of": (snapshot.get("institutional_barometer") or {}).get("as_of"),
            "companies_with_signal": (snapshot.get("reaction") or {}).get("companies_with_signal"),
            "repaired": repaired,
            "ranked_from": (snapshot.get("reaction") or {}).get("ranked_from"),
            "raw_tail": None if ok else str(result)[:800],
        },
        gate_notes=notes or None,
        model_used="deepseek",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("stress_interpreter %s: %s (гейт: %s)", scenario_key, row.status,
                notes or "чисто")
    return row


def current(db: Session, scenario_key: str) -> StressInterpretation | None:
    """Последний опубликованный разбор сценария."""
    return (db.query(StressInterpretation)
            .filter(StressInterpretation.scenario_key == scenario_key,
                    StressInterpretation.status == "published")
            .order_by(StressInterpretation.created_at.desc()).first())


# Служебные ключи факторов в русской прозе. Промпт просит называть их по-русски,
# и после этого утечек стало меньше — но «покрытие фактора fiscal всего 26.1%»
# всё равно проскакивает: модель цитирует имя поля из входных данных. Просьбой это
# не лечится надёжно, поэтому подменяем на витрине — заодно чинятся уже сохранённые
# выпуски, не гоняя платный прогон заново.
_FACTOR_RU = {
    "rate": "ставка", "demand": "спрос", "fx": "курс", "commodity": "сырьё",
    "sanctions": "санкции", "conflict": "конфликт", "fiscal": "налоги",
    "refi": "рефинансирование", "tax": "налоги",
}
_FACTOR_RE = re.compile(r"\b(" + "|".join(_FACTOR_RU) + r")\b", re.I)


def _ru_factors(value):
    """Рекурсивно по строкам структуры: служебный ключ → русское имя."""
    if isinstance(value, str):
        return _FACTOR_RE.sub(lambda m: _FACTOR_RU[m.group(1).lower()], value)
    if isinstance(value, list):
        return [_ru_factors(v) for v in value]
    if isinstance(value, dict):
        return {k: _ru_factors(v) for k, v in value.items()}
    return value


def payload(db: Session, scenario_key: str) -> dict | None:
    """Разбор для витрины. None — разбора нет (фронт честно молчит, а не выдумывает).
    Никогда не роняет ответ сценария: расчёт важнее интерпретации."""
    try:
        row = current(db, scenario_key)
    except Exception:  # noqa: BLE001 — таблицы может ещё не быть на полу-мигрированной БД
        logger.warning("stress_interpreter: чтение разбора %s упало", scenario_key,
                       exc_info=True)
        return None
    if row is None:
        return None
    out = {"headline": _ru_factors(row.headline),
           "generated_at": row.created_at.isoformat() if row.created_at else None,
           "model_used": row.model_used,
           "inputs_used": row.inputs_used}
    out.update(_ru_factors(row.sections or {}))
    return out


def _stale_keys(db: Session, stale_days: int) -> list[str]:
    from app.services.stress_scenarios import list_scenarios
    keys = [s["key"] for s in list_scenarios()]
    cutoff = datetime.now(timezone.utc).timestamp() - stale_days * 86400
    out = []
    for key in keys:
        row = current(db, key)
        if row is None or not row.created_at or row.created_at.timestamp() < cutoff:
            out.append(key)
    return out


def run_batch(db: Session, only_key: str | None = None, batch: int = 3,
              stale_days: int = 14) -> dict:
    """Пересборка разборов. Партиями: каждый сценарий — отдельный прогон LLM."""
    queue = [only_key] if only_key else _stale_keys(db, stale_days)[:batch]
    stats = {"queued": len(queue), "published": 0, "rejected": 0, "skipped": 0,
             "keys": queue}
    for key in queue:
        try:
            row = build_for_scenario(db, key)
        except Exception:  # noqa: BLE001
            logger.exception("stress_interpreter: %s не собран", key)
            continue
        if row is None:
            stats["skipped"] += 1
        else:
            stats[row.status] = stats.get(row.status, 0) + 1
    logger.info("stress_interpreter.run_batch: %s", stats)
    return stats
