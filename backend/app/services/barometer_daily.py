"""ЕЖЕДНЕВНАЯ полная пересборка гео-барометра силами DeepSeek.

Владелец (2026-08-01): «слой 1 перестроить так же, как в макроэкономике —
ежедневный крон, где DeepSeek всё обновляет».

ЧЕМ ОТЛИЧАЕТСЯ ОТ ПРЕЖНЕЙ СХЕМЫ (barometer_reviser.py):
  было — экспертный якорь правился РЕДКО (событийный триггер + cooldown 5 дней)
         и на коротком поводке (±0.5 на субиндекс, ≤5 субиндексов, дрейф ≤1.0
         от экспертной версии). Рамка: «обслуживание калибровки, НЕ суждение»;
  стало — КАЖДЫЙ ДЕНЬ модель пересобирает барометр целиком: все 13 субиндексов
         (балл + rationale), сценарии S1-S4 с вероятностями, регионы, секторные
         флаги, watchlist. Поводок дрейфа и cooldown сняты — они противоречили
         бы задаче «всё обновляет».
Ревизор оставлен ТОЛЬКО для институтов (kind="inst"), иначе два механизма
переписывали бы один и тот же барометр (см. barometer_reviser._KIND_SCOPES).

ЭТАЛОН — macro_interpreter.generate: методичка целиком в системный промпт +
DeepSeek Pro на РАССУЖДЕНИИ (thinking=True), версионирование в БД, ежедневный
крон. Здесь то же самое, но домен геополитический.

🔴 ПРОБЛЕМА, КОТОРУЮ ПРИШЛОСЬ РЕШАТЬ ОТДЕЛЬНО — ДРОЖАНИЕ ЧИСЕЛ.
У макро числа (инфляция, ставка, ВВП) приходят из внешних источников, а LLM
пишет только интерпретацию. Здесь же баллы G1-G13 — это и ЕСТЬ суждение модели,
внешнего источника у них нет. Полная перегенерация каждый день без защиты дала
бы «шевеление» баллов и вероятностей просто от недетерминированности модели:
пользователь видел бы движение там, где в мире ничего не произошло, и перестал
бы верить блоку.
Решение — не поводок на ВЕЛИЧИНУ (он противоречит задаче), а требование
ОБОСНОВАНИЯ: вчерашний барометр передаётся как отправная точка, и любой
изменённый балл обязан нести delta_rationale со ссылкой на конкретную статью
ленты. Балл, сдвинутый без обоснования, гейт откатывает к вчерашнему значению
(остальной выпуск при этом публикуется). Так модель свободна менять что угодно
при реальных событиях и не создаёт шум в тишине.

Комплаенс-гардрейлы сохранены полностью (закон РФ, см. situation_overlay):
блоклист-постфильтр ПОСЛЕ модели (fail-closed, режет весь выпуск) и
обезличивание источников серой зоны.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.models.geo_digest import GeoDigestArticle
from app.services import barometer_store, llm
from app.services.situation_overlay import _BLOCKLIST, _sanitize_sources

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_METHODOLOGY = os.path.join(_REPO, "docs", "geopolitics_methodology.md")

_SCOPES = ("svo", "middle_east", "atr")
_WINDOW_DAYS = 14        # окно ленты для суточной пересборки
_MAX_PER_SCOPE = 14      # кап статей на очаг — не раздувать промпт
_MIN_ARTICLES_TOTAL = 3  # меньше — не пересобираем (честная деградация)


def _load_methodology() -> str:
    try:
        with open(_METHODOLOGY, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        logger.warning("barometer_daily: методичка недоступна (%s)", e)
        return ""


def gather_articles(db: Session, window_days: int = _WINDOW_DAYS) -> dict:
    """Свежая лента по очагам. Только заголовок+пересказ: статьи уже прошли
    слой классификации geo_digest с редакционными конвенциями."""
    cutoff = date.today() - timedelta(days=window_days)
    by_scope: dict[str, list] = {s: [] for s in _SCOPES}
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(_SCOPES),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).all())
    for r in rows:
        by_scope.setdefault(r.target, []).append({
            "date": r.published_at.isoformat() if r.published_at else None,
            "title": r.title,
            "summary": (r.summary or "")[:500],
        })
    return {s: v[:_MAX_PER_SCOPE] for s, v in by_scope.items()}


_OUTPUT_SPEC = (
    "\n\n================================================================\n"
    "ФОРМАТ ОТВЕТА — СТРОГО JSON, на русском, без текста вне JSON.\n"
    "Ты пересобираешь барометр ЦЕЛИКОМ на сегодня. Верни объект той же формы, "
    "что ВЧЕРАШНИЙ БАРОМЕТР во входных данных, с ключами:\n"
    "  \"as_of\": \"<сегодняшняя дата YYYY-MM-DD>\",\n"
    "  \"subindices\": [ {\"key\":\"G1\"...\"G13\", \"label\":\"<как вчера>\", "
    "\"score\": <1..5, шаг 0.5>, \"type\":\"оценка\", "
    "\"rationale\":\"<почему такой балл, с конкретикой>\", "
    "\"delta_rationale\":\"<ОБЯЗАТЕЛЬНО, если балл отличается от вчерашнего: "
    "что именно в ленте это оправдывает, со ссылкой на событие; если балл не "
    "менялся — null>\"} ],\n"
    "  \"scenario\": {\"probabilities_6m\": {\"S1\":..,\"S2\":..,\"S3\":..,\"S4\":..}, "
    "\"probabilities_18m\": {...}, \"current_lean\":\"<S1|S2|S3|S4>\", "
    "\"delta_explanation\":\"<что изменилось против вчера и почему>\", "
    "\"triggers\": [...], \"wild_cards\": [...], \"confidence\":\"<низкая|средняя|высокая>\"}, "
    "// ЭТО СЦЕНАРНАЯ ЛЕСТНИЦА СВО (война/перемирие/мир) — она НЕ описывает "
    "Ближний Восток и АТР, для них сценарии свои, см. regions ниже\n"
    "  \"regions\": {\"svo\": {...}, \"middle_east\": {...}, \"atr\": {...}}, "
    "\"sector_flags\": [...], \"watchlist_30d\": [...], "
    "\"summary\": \"<3-5 предложений: где мы сейчас и куда движемся>\"\n"
    "Вероятности в каждом горизонте — доли, сумма ровно 1.0.\n\n"
    "🔴 КАЖДЫЙ ОЧАГ — СО СВОИМ СЦЕНАРНЫМ НАБОРОМ. Внутри regions.<очаг> верни:\n"
    "  \"label\", \"summary\", \"direction\" (эскалация|деэскалация|статус-кво), "
    "\"confidence\", \"duration_estimate\", \"affected\" — как раньше, ПЛЮС:\n"
    "  \"barometer\": {\"overall\": <1..5, шаг 0.5 — насколько остро В ЭТОМ ОЧАГЕ "
    "сейчас, 5 = максимальный риск>, \"label\":\"<вердикт одной фразой ПРО ЭТОТ ОЧАГ>\"}, "
    "// балл очага СВОЙ, не копия общего: у СВО и АТР острота разная\n"
    "  \"scenarios\": {\"items\": [ {\"key\":\"<короткий id, напр. ME1>\", "
    "\"label\":\"<название сценария ИМЕННО ЭТОГО очага>\", "
    "\"p6m\": <доля>, \"p18m\": <доля>, \"note\":\"<1 фраза, что это значит>\"} ], "
    "\"current_lean\":\"<key базового>\", \"confidence\":\"<низкая|средняя|высокая>\", "
    "\"triggers\": [\"<что переведёт очаг в другой сценарий>\", ...]},\n"
    "  \"sector_flags\": [ {\"sector\":\"<сектор рынка РФ>\", "
    "\"direction\":\"негатив|позитив|нейтрально\", "
    "\"reasoning\":\"<почему ИМЕННО этот очаг это делает>\"} ]\n"
    "Сценарии очага должны быть ОСМЫСЛЕННЫ ДЛЯ НЕГО: для СВО это война/перемирие/мир; "
    "для Ближнего Востока — например удары по нефтяной инфраструктуре, перекрытие "
    "Ормузского пролива, локализация конфликта, деэскалация; для АТР — тайваньский "
    "кризис, торгово-технологическая война, статус-кво, разрядка. НЕ переноси лестницу "
    "СВО на другие очаги и не пиши общих сценариев «для всего сразу». 3-4 сценария на "
    "очаг, сумма p6m = 1.0 и сумма p18m = 1.0 ВНУТРИ КАЖДОГО очага отдельно.\n"
    "sector_flags внутри очага — только те последствия, которые идут ИМЕННО от него "
    "(удары по НПЗ — СВО; Ормузский пролив и нефтяная премия — Ближний Восток; "
    "доступ к чипам и цепочки — АТР). Верхнеуровневый sector_flags оставь как сводный.\n\n"
    "🔴 ГЛАВНОЕ ПРАВИЛО СТАБИЛЬНОСТИ: барометр меряет СРЕДУ, а не новостной шум. "
    "Если за период не произошло события, меняющего картину, — СОХРАНИ вчерашний "
    "балл и вчерашнюю вероятность дословно. Двигай число ТОЛЬКО когда в переданной "
    "ленте есть конкретное событие, которое это оправдывает, и назови его в "
    "delta_rationale. Балл, сдвинутый без такой ссылки, будет отклонён автоматически.\n"
    "Тон нейтральный, фактологический. РФ-топонимика (Артёмовск, не Бахмут; "
    "«перешёл под контроль», не «оккупирован»). Без «купить/продать/рекомендуем». "
    "Не называй СМИ-источники — обезличенно «по данным ленты»."
)


def _index_subindices(payload: dict) -> dict:
    return {s.get("key"): s for s in (payload.get("subindices") or []) if s.get("key")}


def _gate(fresh: dict, prev: dict) -> tuple[dict, list[str]]:
    """Возвращает (выпуск, заметки). НЕ отклоняет весь прогон из-за одного балла:
    сдвиг без обоснования просто откатывается к вчерашнему значению — так суточная
    пересборка не срывается целиком из-за одной небрежной строки.
    Комплаенс — отдельно и жёстко (см. compliance_ok), там fail-closed."""
    notes: list[str] = []
    prev_idx = _index_subindices(prev)
    for s in fresh.get("subindices") or []:
        key = s.get("key")
        p = prev_idx.get(key)
        if not p:
            continue
        try:
            new_score, old_score = float(s.get("score")), float(p.get("score"))
        except (TypeError, ValueError):
            s["score"] = p.get("score")
            notes.append(f"{key}: нечисловой балл → откат")
            continue
        if abs(new_score - old_score) < 1e-9:
            continue
        just = (s.get("delta_rationale") or "").strip()
        if len(just) < 20:                       # пусто/отписка «уточнено»
            s["score"] = old_score
            s["delta_rationale"] = None
            notes.append(f"{key}: {old_score}→{new_score} без обоснования → откат")

    # вероятности сценариев: нормализуем к 1.0, чтобы витрина не показывала 97%/103%
    sc = fresh.get("scenario") or {}
    for hk in ("probabilities_6m", "probabilities_18m"):
        probs = sc.get(hk)
        if isinstance(probs, dict) and probs:
            try:
                total = sum(float(v) for v in probs.values())
                if total > 0 and abs(total - 1.0) > 0.005:
                    sc[hk] = {k: round(float(v) / total, 3) for k, v in probs.items()}
                    notes.append(f"{hk}: сумма {total:.3f} → нормализована")
            except (TypeError, ValueError):
                notes.append(f"{hk}: нечисловые вероятности — оставлены как есть")

    # то же для сценариев КАЖДОГО очага (владелец 2026-08-01: сценарии должны быть
    # по очагам, а не общие) — суммы считаются внутри очага независимо.
    for rkey, r in (fresh.get("regions") or {}).items():
        items = ((r or {}).get("scenarios") or {}).get("items")
        if not isinstance(items, list) or not items:
            continue
        for field in ("p6m", "p18m"):
            try:
                vals = [float(it.get(field)) for it in items if it.get(field) is not None]
                total = sum(vals)
            except (TypeError, ValueError):
                notes.append(f"{rkey}.{field}: нечисловые вероятности — как есть")
                continue
            if total > 0 and abs(total - 1.0) > 0.005:
                for it in items:
                    if it.get(field) is not None:
                        it[field] = round(float(it[field]) / total, 3)
                notes.append(f"{rkey}.{field}: сумма {total:.3f} → нормализована")
    return fresh, notes


def compliance_ok(payload: dict) -> tuple[bool, str | None]:
    """Гардрейл закона РФ: детерминированный постфильтр по всему тексту выпуска.
    Промпт — пожелание, этот фильтр — гарантия. Срабатывание → не публикуем."""
    m = _BLOCKLIST.search(json.dumps(payload, ensure_ascii=False))
    return (False, f"блоклист: '{m.group(0)}'") if m else (True, None)


def rebuild(db: Session, window_days: int = _WINDOW_DAYS) -> BarometerVersion | None:
    """Суточная полная пересборка гео-барометра. Возвращает строку версии
    (published либо rejected) или None, если пересобирать не из чего."""
    prev_row = barometer_store.current_row(db, "geo")
    if not prev_row or not prev_row.payload:
        logger.warning("barometer_daily: нет текущей версии барометра — пропуск")
        return None
    prev = prev_row.payload

    articles = gather_articles(db, window_days)
    total = sum(len(v) for v in articles.values())
    if total < _MIN_ARTICLES_TOTAL:
        logger.info("barometer_daily: лента пуста (%d статей) — барометр не трогаем", total)
        return None

    system = (
        "Ты — старший гео-политэкономический аналитик Basis (независимая аналитика "
        "для частного инвестора в РФ). Твоя задача — ежедневно пересобирать "
        "геополитический барометр рынка строго по методичке ниже.\n\n"
        + _load_methodology() + _OUTPUT_SPEC
    )
    user = (
        "ВЧЕРАШНИЙ БАРОМЕТР (отправная точка; сохраняй значения, если лента не даёт "
        "основания их менять):\n"
        + json.dumps(prev, ensure_ascii=False, indent=1)[:60000]
        + f"\n\nСВЕЖАЯ ЛЕНТА ПО ОЧАГАМ (за {window_days} дней, {total} статей):\n"
        + json.dumps(articles, ensure_ascii=False, indent=1)
        + f"\n\nСЕГОДНЯ: {date.today().isoformat()}"
    )

    try:
        fresh = llm.complete(system, user, json_mode=True, thinking=True,
                             model=llm.pro_model(), max_tokens=16000, temperature=0.3)
    except llm.LLMError as e:
        row = BarometerVersion(kind="geo", source="auto", status="rejected",
                               payload=None, gate_notes=[f"LLM недоступен: {e}"],
                               parent_id=prev_row.id, trigger_reason="ежедневная пересборка")
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("barometer_daily: LLM недоступен (%s) — версия не опубликована", e)
        return row

    if not isinstance(fresh, dict) or not fresh.get("subindices"):
        row = BarometerVersion(kind="geo", source="auto", status="rejected",
                               payload=None, gate_notes=["ответ без subindices"],
                               parent_id=prev_row.id, trigger_reason="ежедневная пересборка")
        db.add(row); db.commit(); db.refresh(row)
        return row

    # поля, которые модель могла не вернуть, — переносим со вчера, чтобы витрина
    # не потеряла блок целиком из-за одного пропущенного ключа
    for k in ("kb_version", "barometer", "implied_market", "premortem", "handoff",
              "sources", "data_flags"):
        if k not in fresh and k in prev:
            fresh[k] = prev[k]

    fresh, notes = _gate(fresh, prev)
    fresh = _sanitize_sources(fresh)

    ok, why = compliance_ok(fresh)
    if not ok:
        row = BarometerVersion(kind="geo", source="auto", status="rejected",
                               payload=None, gate_notes=(notes + [why]),
                               parent_id=prev_row.id, trigger_reason="ежедневная пересборка")
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("barometer_daily: комплаенс-блок (%s) — published не меняем", why)
        return row

    fresh.setdefault("as_of", date.today().isoformat())
    # дата ЭКСПЕРТНОГО якоря сохраняется отдельно — витрина показывает её рядом,
    # чтобы не создавать иллюзию, что вся калибровка сделана сегодня
    expert = barometer_store.last_expert(db, "geo")
    meta_anchor = (expert.payload or {}).get("as_of") if expert else prev.get("as_of")

    # Витрина (barometer_store.current_row) берёт ПОСЛЕДНЮЮ published по created_at,
    # поэтому прежнюю версию помечать не нужно — она просто перестаёт быть последней
    # и остаётся в истории (barometer_history строит по ней таймлайн ревизий).
    fresh.setdefault("expert_anchor_as_of", meta_anchor)
    row = BarometerVersion(kind="geo", source="auto", status="published",
                           payload=fresh, gate_notes=notes or None,
                           parent_id=prev_row.id,
                           trigger_reason="ежедневная пересборка",
                           model_used=f"{llm.provider_info().get('provider')}:{llm.pro_model()}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("barometer_daily: барометр пересобран (версия #%d, заметок гейта: %d)",
                row.id, len(notes))
    return row
