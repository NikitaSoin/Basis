"""Замеры качества институтов ПО НАПРАВЛЕНИЯМ — «датчики» институциональной среды.

Владелец (2026-08-02): «нужны прям местами детальные отдельные проходы, которые
бы мониторили качество институтов, и по ним видели, есть ли институциональные
изменения: собственность, суды и парламент, СМИ, государственная доля в
экономике, монополизация, регулирование, рыночные институты по типу ЦБ и других
(если ЦБ пляшет под дудку — это плохой ЦБ, и это нужно делать), конфликты на
уровне бизнеса и государства, возможности ассоциаций и агентств продавливать
частные интересы, что с конкуренцией в целом».

🔴 ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ 13 СУБИНДЕКСОВ БАРОМЕТРА.
Барометр даёт ОДИН балл на всю среду и обновляется событийно (ревизор с
cooldown 5 дней), причём его субиндексы — про разное сразу: «Конфигурация
власти и кланы», «Ресурсная рента», «Санкционный режим». Вопрос «стало ли хуже
именно с судами» по нему не отвечается: движение одного субиндекса тонет в
общем балле, а история изменений по направлению не хранится.
Здесь — датчики: у каждого направления свой балл, своё направление движения и
свои свидетельства из потока. Смысл не в «ещё одной оценке», а в ВОЗМОЖНОСТИ
УВИДЕТЬ ИЗМЕНЕНИЕ: балл направления сравнивается с прошлым замером, и если он
сдвинулся — видно, ЧТО именно сдвинулось и на основании чего.

🔴 ПОЧЕМУ БАТЧИ, А НЕ 10 ОТДЕЛЬНЫХ ВЫЗОВОВ.
Владелец просил «отдельные детальные проходы». Десять reasoning-вызовов в неделю
— это дорого и долго, а главное, соседние направления невозможно оценить
изолированно: монополизация без конкуренции и госдоли — это гадание. Поэтому
направления сгруппированы в четыре смысловых батча, внутри которых они реально
связаны, а между батчами — независимы. Детальность прохода сохраняется (в каждом
2-3 направления, а не десять), стоимость падает вдвое с лишним.

🔴 ЭТОТ ВЫХОД НУЖЕН НЕ ТОЛЬКО ВИТРИНЕ. Владелец отдельно просил, чтобы домены
давали материал другим агентам — макро, гео и разбору карточек компаний.
Поэтому payload содержит `for_agents`: компактную сводку без прозы, которую
можно положить в промпт соседнего домена, не таща туда весь текст.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion
from app.models.geo_digest import GeoDigestArticle
from app.services import llm
from app.services.institutions_profile import (
    _COMPLIANCE_HEAD, _blocklist_hit, _PERSON, _UNSAFE, _sanitize_sources,
)

logger = logging.getLogger(__name__)

_KIND = "instdom"          # varchar(8), см. пояснение в geo_conflict_profile
_WINDOW_DAYS = 45          # шире, чем у портрета: изменение института за месяц
                           # видно редко, нужна дистанция
_MAX_ARTICLES = 26
_SUMMARY_CHARS = 900
_MIN_ARTICLES = 5

# Направления. key — стабильный идентификатор (используется для сравнения с
# прошлым замером), label — то, что видит пользователь; question — что именно
# меряем, чтобы модель не расползалась в общие слова.
DOMAINS = [
    {"key": "property", "label": "Права собственности",
     "question": "Насколько надёжно бизнес владеет своими активами: пересматриваются ли "
                 "права на крупные активы, растёт ли число споров о собственности, "
                 "меняются ли условия владения задним числом."},
    {"key": "courts", "label": "Суды и правоприменение",
     "question": "Насколько предсказуем исход спора для частной стороны, особенно против "
                 "государства или крупной госструктуры; меняется ли практика."},
    {"key": "lawmaking", "label": "Законотворчество и стабильность правил",
     "question": "Как быстро и предсказуемо меняются правила: успевает ли бизнес "
                 "адаптироваться, вводятся ли нормы задним числом, что с обсуждением."},
    {"key": "state_share", "label": "Доля государства в экономике",
     "question": "Растёт ли доля государства и госкомпаний: переход активов, новые "
                 "госструктуры на рынках, вытеснение частных игроков."},
    {"key": "monopoly", "label": "Монополизация рынков",
     "question": "Концентрируются ли рынки, вытесняются ли независимые игроки, "
                 "появляются ли барьеры входа."},
    {"key": "competition", "label": "Конкуренция и равные условия",
     "question": "Одинаковы ли правила для всех участников рынка или доступ к ресурсам, "
                 "тарифам и госзаказу зависит от статуса компании."},
    {"key": "regulation", "label": "Регуляторная нагрузка",
     "question": "Растут ли требования, проверки, отчётность и издержки соответствия; "
                 "предсказуемы ли они."},
    {"key": "market_institutions", "label": "Рыночные институты (ЦБ, биржа, инфраструктура)",
     "question": "Насколько самостоятельны и предсказуемы институты, отвечающие за "
                 "денежную политику, биржевую инфраструктуру и защиту инвесторов: "
                 "принимаются ли их решения по объявленным правилам или под задачи "
                 "бюджета и приоритетного кредитования."},
    {"key": "business_state", "label": "Конфликты бизнеса и государства",
     "question": "Частота и характер споров компаний с государством: изъятия, "
                 "доначисления, принудительные сделки, пересмотр приватизации."},
    {"key": "lobbying", "label": "Лоббизм и отраслевые ассоциации",
     "question": "Могут ли объединения бизнеса реально влиять на решения, или влияние "
                 "распределено в пользу отдельных крупных игроков."},
]

# Смысловые батчи: внутри — связанные направления, оценивать их порознь значило
# бы терять контекст (монополизация без конкуренции и госдоли — гадание).
_BATCHES = [
    ("собственность и правоприменение", ["property", "courts", "business_state"]),
    ("рынки и конкуренция", ["state_share", "monopoly", "competition"]),
    ("правила и нагрузка", ["lawmaking", "regulation", "lobbying"]),
    ("рыночные институты", ["market_institutions"]),
]

_SPEC = """

================================================================
ФОРМАТ ОТВЕТА — СТРОГО JSON, на русском, без текста вне JSON:

{"domains": [
  {"key": "<ключ направления, дословно как дан>",
   "score": <1..5, шаг 0.5 — где 1 «правила не защищают, всё зависит от доступа»,
             5 «правила работают одинаково для всех и предсказуемы»>,
   "direction": "<ухудшение|без изменений|улучшение>",
   "verdict": "<ОДНА фраза: что происходит на этом направлении сейчас>",
   "evidence": [ {"what": "<конкретное наблюдаемое событие или практика>",
                  "tag": "<факт|оценка>"} ],
   "for_investor": "<1-2 фразы: что это меняет для того, кто держит российские
                     акции — через издержки, риск изъятия, дивиденды, оценку>",
   "confidence": "<низкая|средняя|высокая>"}
]}

ПРАВИЛА:
• score — это СОСТОЯНИЕ направления, direction — КУДА оно движется. Не путай:
  можно иметь низкий балл и при этом «без изменений».
• Двигай балл относительно прошлого замера ТОЛЬКО если в ленте есть событие,
  которое это оправдывает, и назови его в evidence. Нет события — сохрани
  прошлый балл. Институты меняются медленно; шевеление балла в тишине
  обесценивает весь замер.
• evidence — 1-3 пункта, конкретных. «Ситуация ухудшается» — не свидетельство.
• confidence «низкая», если по направлению в ленте почти ничего не было: это
  честнее, чем уверенный балл из воздуха.
• Никаких фамилий, никаких оценок государственных органов и политики — только
  наблюдаемые изменения правил и их экономические последствия.
"""


def gather_articles(db: Session, window_days: int = _WINDOW_DAYS) -> list[dict]:
    cutoff = date.today() - timedelta(days=window_days)
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(("institutions", "macro")),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc())
            .limit(_MAX_ARTICLES).all())
    return [{"date": r.published_at.isoformat() if r.published_at else None,
             "title": r.title, "summary": (r.summary or "")[:_SUMMARY_CHARS]} for r in rows]


def previous(db: Session) -> dict:
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == _KIND, BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    return (row.payload or {}) if row else {}


def _check(items: list[dict]) -> tuple[list[str], list[str]]:
    """Проверки без LLM: структура и отсутствие запрещённой лексики."""
    bad, notes = [], []
    for d in items:
        k = d.get("key")
        if not isinstance(d.get("score"), (int, float)):
            bad.append(f"{k}: балл не число")
        elif not (1 <= float(d["score"]) <= 5):
            bad.append(f"{k}: балл вне 1-5 ({d['score']})")
        if not d.get("verdict"):
            bad.append(f"{k}: нет вердикта")
        if not d.get("evidence"):
            notes.append(f"{k}: без свидетельств — балл повисает")
        if not d.get("for_investor"):
            notes.append(f"{k}: не сказано, что это меняет для инвестора")
    blob = json.dumps(items, ensure_ascii=False)
    p = _PERSON.search(blob)
    if p:
        bad.append(f"похоже на имя должностного лица: «{p.group(0)}»")
    u = _UNSAFE.search(blob)
    if u:
        bad.append(f"оценочная формулировка о государстве: «{u.group(0)}»")
    m = _blocklist_hit(blob)
    if m:
        bad.append(f"блоклист: «{m.group(0)}»")
    return bad, notes


def _run_batch(name: str, keys: list[str], articles: list[dict],
               prev_map: dict) -> tuple[list[dict], list[str]]:
    doms = [d for d in DOMAINS if d["key"] in keys]
    system = (
        "Ты — аналитик Basis. Ты ведёшь ПОСТОЯННЫЙ ЗАМЕР качества институтов "
        "российского рынка по конкретным направлениям. Твоя задача — не рассуждать "
        "о политике, а фиксировать: изменилось ли что-то на этом направлении и что это "
        "значит для инвестора.\n\n" + _COMPLIANCE_HEAD + _SPEC
    )
    prev_part = ""
    if prev_map:
        prev_part = ("\n\nПРОШЛЫЙ ЗАМЕР по этим направлениям (отправная точка):\n"
                     + json.dumps({k: prev_map[k] for k in keys if k in prev_map},
                                  ensure_ascii=False, indent=1))
    user = (
        f"НАПРАВЛЕНИЯ БАТЧА «{name}» — оцени каждое:\n"
        + json.dumps([{"key": d["key"], "label": d["label"], "что_мерим": d["question"]}
                      for d in doms], ensure_ascii=False, indent=1)
        + prev_part
        + f"\n\nПОТОК МАТЕРИАЛОВ за {_WINDOW_DAYS} дней ({len(articles)}):\n"
        + json.dumps(articles, ensure_ascii=False, indent=1)
        + f"\n\nСЕГОДНЯ: {date.today().isoformat()}"
    )
    try:
        out = llm.complete(system, user, json_mode=True, thinking=True,
                           model=llm.pro_model(), max_tokens=6000, temperature=0.3)
    except llm.LLMError as e:
        return [], [f"батч «{name}»: LLM недоступен ({e})"]

    items = (out or {}).get("domains") if isinstance(out, dict) else None
    if not isinstance(items, list) or not items:
        return [], [f"батч «{name}»: пустой ответ"]

    items = [d for d in items if isinstance(d, dict) and d.get("key") in keys]
    bad, notes = _check(items)
    if bad:
        # Батч отклоняем целиком: если в нём нашлась запрещённая лексика, чинить
        # её выборочно нельзя — вырезав пункт, получим балл без обоснования.
        return [], [f"батч «{name}» отклонён: {b}" for b in bad] + notes
    return items, [f"батч «{name}»: {n}" for n in notes]


def rebuild(db: Session, window_days: int = _WINDOW_DAYS) -> BarometerVersion | None:
    articles = gather_articles(db, window_days)
    if len(articles) < _MIN_ARTICLES:
        logger.info("institutions_domains: материалов мало (%d) — замер пропущен", len(articles))
        return None

    prev = previous(db)
    prev_map = {d["key"]: d for d in (prev.get("domains") or [])}

    collected: list[dict] = []
    all_notes: list[str] = []
    for name, keys in _BATCHES:
        items, notes = _run_batch(name, keys, articles, prev_map)
        all_notes.extend(notes)
        if items:
            collected.extend(items)
        else:
            # Батч не собрался — переносим прошлые замеры этих направлений,
            # иначе на витрине направления просто исчезнут, и это будет
            # выглядеть как «нет проблемы», а не как «нет данных».
            carried = [prev_map[k] for k in keys if k in prev_map]
            collected.extend(carried)
            if carried:
                all_notes.append(f"батч «{name}»: перенесены прошлые замеры")

    if not collected:
        logger.warning("institutions_domains: ни одно направление не собрано")
        return None

    # Сравнение с прошлым замером — то, ради чего всё и делается: не «какой
    # балл», а «что изменилось».
    changes = []
    for d in collected:
        old = prev_map.get(d.get("key"))
        if old and isinstance(old.get("score"), (int, float)) and isinstance(d.get("score"), (int, float)):
            delta = round(float(d["score"]) - float(old["score"]), 1)
            if abs(delta) >= 0.5:
                changes.append({"key": d["key"], "label": next(
                    (x["label"] for x in DOMAINS if x["key"] == d["key"]), d["key"]),
                    "from": old["score"], "to": d["score"], "delta": delta,
                    "why": d.get("verdict")})

    labels = {d["key"]: d["label"] for d in DOMAINS}
    for d in collected:
        d["label"] = labels.get(d.get("key"), d.get("key"))

    payload = {
        "as_of": date.today().isoformat(),
        "domains": collected,
        "changes": changes,
        # Компактная сводка для СОСЕДНИХ АГЕНТОВ (макро, гео, разбор карточек):
        # только ключ, балл и направление — без прозы, чтобы её можно было
        # положить в чужой промпт, не раздувая его.
        "for_agents": {d["key"]: {"score": d.get("score"), "direction": d.get("direction")}
                       for d in collected},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = _sanitize_sources(payload)

    row = BarometerVersion(kind=_KIND, source="auto", status="published",
                           payload=payload, gate_notes=all_notes[:20],
                           trigger_reason="еженедельный замер направлений",
                           model_used=llm.pro_model())
    db.add(row); db.commit(); db.refresh(row)
    logger.info("institutions_domains: версия %s, направлений %d, изменений %d",
                row.id, len(collected), len(changes))
    return row


def get_latest(db: Session) -> dict:
    return previous(db)


def for_agents(db: Session) -> dict:
    """Сводка для промптов соседних доменов (макро/гео/карточки компаний).
    Отдельная функция, а не чтение payload напрямую: потребителям нужен
    стабильный контракт, а не форма хранения."""
    p = previous(db)
    if not p:
        return {}
    return {"as_of": p.get("as_of"), "domains": p.get("for_agents") or {},
            "changes": [{"label": c.get("label"), "delta": c.get("delta")}
                        for c in (p.get("changes") or [])]}
