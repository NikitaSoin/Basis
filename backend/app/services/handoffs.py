"""Передачи между тремя аналитиками — как КОНТРАКТ полей, а не как беседа.

🔴 ЗАЧЕМ (владелец, 2026-09-13, пункт 3 плана). Шесть методичек-связок
описывают, что один аналитик обязан передать другому. До сих пор передача была
одна и неформальная: сводка соседа целиком вкладывалась в задание, и агент сам
решал, что оттуда взять. «Недоученное» было невидимо. Здесь каждая из шести
передач — набор именованных полей: производитель ОБЯЗАН их заполнить (гейт
пишет заметку на каждое пустое), потребитель ОБЯЗАН их прочитать (они лежат в
задании отдельным блоком с пометкой «контракт»). Пустое поле — видно механически.

Поля взяты из самих методичек:
  ГМ  геополитика → макро    — ГМ 9.1–9.2: шоки по каналам с направлением, силой,
                               лагом, обратимостью; сценарии; пороговые события.
  МГ  макро → геополитика    — ИГ 8.8 и МГ Части 2, 6: оценка экономической
                               выносливости курса — фискальная способность,
                               долговая устойчивость, точки исчерпания, цена курса.
  ИМ  институты → макро      — ИМ 8.2–8.3: чувствительная доля кредита, доли
                               льготного/административного/теневого контуров,
                               заякоренность ожиданий, признаки фискального
                               доминирования, доля инфляции, недоступная ставке.
  МИ  макро → институты      — МИ Части 1–4, 11: происхождение доходов (рента/
                               налоги), близость кризисной развилки, инфляция как
                               разрушитель, качество роста, опережающие
                               экономические индикаторы институциональных сдвигов.
  ГИ  геополитика → институты — ГИ 3.1, 7.1: событие, вектор интенсивности,
                               материальные изменения (доходы государства, доступ к
                               капиталу, экспорт, импорт, технологии, логистика,
                               труд, валюта, стоимость финансирования).
  ИГ  институты → геополитика — ИГ 9.7 шаги 1–5, 8.8: кто решает, у кого ресурс,
                               правящая коалиция и её интересы, ограничения
                               руководства, кто выигрывает от эскалации/деэскалации,
                               сценарии расходов и ограничений.

Каждое поле — словами и цифрами (правило языка), с датой и источником где
уместно; статус утверждения Ф/Д/В/Г там, где это оценка.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Handoff:
    code: str                 # ГМ, МГ, ИМ, МИ, ГИ, ИГ
    src: str                  # kind производителя: geo | macro | inst_state
    dst: str                  # kind потребителя
    key: str                  # имя блока в payload производителя: handoffs.<key>
    title: str
    fields: dict[str, str]    # имя поля → что в нём должно быть (для роли и для гейта)
    required: tuple[str, ...] = field(default_factory=tuple)


HANDOFFS: dict[str, Handoff] = {
    "ГМ": Handoff("ГМ", "geo", "macro", "to_macro", "Геополитика → макроэкономика", {
        "shocks": "список шоков: событие, канал из четырнадцати (ГМ Часть 2), направление для "
                  "макропеременной, класс масштаба (малый/умеренный/значимый/режимный), лаг, "
                  "обратимость, горизонт",
        "scenario_probabilities": "вероятности сценариев на 6 и 18 месяцев (из сводки)",
        "threshold_events": "наблюдаемые пороговые события смены сценария (ГМ 9.2)",
        "sector_flags": "секторные флаги с направлением",
        "expected_policy_reaction": "что, по геополитической логике, сделают бюджет и ЦБ",
    }, required=("shocks", "scenario_probabilities", "threshold_events")),

    "МГ": Handoff("МГ", "macro", "geo", "to_geo", "Макроэкономика → геополитика", {
        "fiscal_capacity": "сколько государство может тратить без дестабилизации: баланс, "
                           "источники финансирования, резервы — с числами и датами",
        "debt_sustainability": "устойчивость долга в текущем режиме: уровень, стоимость "
                               "обслуживания, доступ к рынку",
        "exhaustion_points": "точки исчерпания: какой показатель, какой порог, когда при "
                             "текущей траектории (МГ Часть 6)",
        "endurance_horizon_months": "оценка выносливости курса в месяцах со статусом В/Г",
        "price_of_course": "цена текущего внешнеполитического курса для экономики и кто её "
                           "платит (адресат)",
        "leading_indicators_for_geo": "экономические индикаторы, опережающие геополитические "
                                      "решения (МГ Часть 10)",
    }, required=("fiscal_capacity", "exhaustion_points", "endurance_horizon_months")),

    "ИМ": Handoff("ИМ", "inst_state", "macro", "to_macro", "Институты → макроэкономика", {
        "sensitive_credit_share": "чувствительная к ставке доля кредита и её обоснование (ИМ 4.3)",
        "preferential_contour_share": "доли льготного, административного, теневого и бюджетного "
                                      "контуров — оценки с пометкой",
        "expectations_anchoring": "заякоренность ожиданий: уровень против цели, скорость "
                                  "затухания после шока (ИМ 8.2, λ)",
        "fiscal_dominance_signs": "признаки фискального доминирования — есть/нет и какие (ИМ 3.6)",
        "inflation_inaccessible_to_rate": "доля инфляции, недоступная ставке: административная, "
                                          "санкционно-издержковая, защищённые контуры (ИМ 8.2 п.4)",
        "growth_institutional_component": "институциональный вклад в потенциальный темп (ИМ 8.1 п.5)",
    }, required=("sensitive_credit_share", "expectations_anchoring", "inflation_inaccessible_to_rate")),

    "МИ": Handoff("МИ", "macro", "inst_state", "to_inst", "Макроэкономика → институты", {
        "fiscal_origin": "происхождение доходов государства: доля ренты против налогов, "
                         "динамика — что это говорит о типе государства (МИ Часть 1)",
        "crisis_proximity": "близость кризисной развилки: какие индикаторы, насколько (МИ Часть 3)",
        "inflation_as_destroyer": "инфляция как перераспределитель: кто теряет, кто выигрывает, "
                                  "скорость разрушения доверия (МИ Часть 4)",
        "growth_quality": "качество роста: рыночный или бюджетный контур, кому достаётся (МИ Часть 2)",
        "leading_indicators_for_institutions": "экономические индикаторы, опережающие "
                                               "институциональные сдвиги (МИ Часть 11)",
    }, required=("fiscal_origin", "crisis_proximity", "inflation_as_destroyer")),

    "ГИ": Handoff("ГИ", "geo", "inst_state", "to_inst", "Геополитика → институты", {
        "events": "события периода по таксономии с вектором интенсивности (ГИ 7.1)",
        "material_changes": "что изменилось материально: доходы государства, доступ к капиталу, "
                            "экспорт, импорт, технологии, логистика, труд, валюта, стоимость "
                            "финансирования (ГИ 3.1) — с числами",
        "market_or_administrative": "по каждому материальному изменению: государство отвечает "
                                    "рынком или административным доступом (ГИ 3.1)",
        "threat_structure": "как изменилась структура угроз и внешних альтернатив",
    }, required=("events", "material_changes")),

    "ИГ": Handoff("ИГ", "inst_state", "geo", "to_geo", "Институты → геополитика", {
        "decision_makers": "кто принимает внешнеполитические решения (ИГ 9.7 ш.1)",
        "resource_holders": "кто реально обладает ресурсом (ш.2)",
        "ruling_coalition": "правящая коалиция и интересы участников (ш.3–4)",
        "leadership_constraints": "фактические ограничения руководства (ш.5)",
        "escalation_beneficiaries": "кто внутри выигрывает от эскалации и от деэскалации",
        "spending_and_constraint_scenarios": "сценарии расходов и ограничений для оценки "
                                             "выносливости (ИГ 8.8)",
        "execution_capacity": "способность государства исполнить принятое решение",
    }, required=("ruling_coalition", "leadership_constraints", "escalation_beneficiaries")),
}


def outgoing(src_kind: str) -> list[Handoff]:
    return [h for h in HANDOFFS.values() if h.src == src_kind]


def incoming(dst_kind: str) -> list[Handoff]:
    return [h for h in HANDOFFS.values() if h.dst == dst_kind]


def prompt_block(src_kind: str) -> str:
    """Что производитель ОБЯЗАН заполнить — для роли агента."""
    out = ["\n===== ПЕРЕДАЧИ СОСЕДЯМ (контракт, обязательно) =====",
           "В поле \"handoffs\" заполни блоки для соседних аналитиков. Каждое поле — "
           "словами и цифрами, с датой и источником; где оценка — статус Ф/Д/В/Г. "
           "Пустое обязательное поле — заметка проверки и вопрос от соседа завтра."]
    for h in outgoing(src_kind):
        out.append(f"\n• handoffs.{h.key} — {h.title} ({h.code}):")
        for name, desc in h.fields.items():
            mark = " [обязательно]" if name in h.required else ""
            out.append(f"    \"{name}\"{mark}: {desc}")
    return "\n".join(out) + "\n"


def gate_notes(payload: dict, src_kind: str) -> list[str]:
    """Заметки гейта: какие обязательные поля передач пусты."""
    notes: list[str] = []
    hs = payload.get("handoffs") or {}
    for h in outgoing(src_kind):
        block = hs.get(h.key) if isinstance(hs, dict) else None
        if not isinstance(block, dict):
            notes.append(f"handoffs.{h.key} ({h.code}): блок передачи отсутствует целиком")
            continue
        for name in h.required:
            v = block.get(name)
            if v in (None, "", [], {}):
                notes.append(f"handoffs.{h.key}.{name} ({h.code}): обязательное поле пусто")
    return notes


def incoming_block(dst_kind: str, sources: dict[str, dict | None]) -> str:
    """Что потребитель ОБЯЗАН прочитать — для задания агента.

    sources: {src_kind: payload производителя (или None)}. Берём только блок
    контракта, а не сводку целиком: агент получает ровно то, что ему адресовано."""
    out = ["===== ПЕРЕДАЧИ ОТ СОСЕДЕЙ (контракт — прочитать обязательно) ====="]
    import json
    for h in incoming(dst_kind):
        src = sources.get(h.src)
        block = ((src or {}).get("handoffs") or {}).get(h.key) if isinstance(src, dict) else None
        as_of = (src or {}).get("as_of") if isinstance(src, dict) else None
        if not isinstance(block, dict):
            out.append(f"\n• {h.title} ({h.code}): передача НЕ ЗАПОЛНЕНА соседом"
                       + (f" (его сводка от {as_of})" if as_of else " (сводки нет)")
                       + " — учти это как пробел и, если критично, задай ему вопрос в questions_to_peers")
            continue
        empty = [n for n in h.required if block.get(n) in (None, "", [], {})]
        out.append(f"\n• {h.title} ({h.code}), сводка соседа от {as_of}"
                   + (f"; пустые обязательные поля: {empty}" if empty else "") + ":")
        out.append(json.dumps(block, ensure_ascii=False, default=str)[:12_000])
    return "\n".join(out) + "\n"


# ─────────────── вечерняя сборка: цепочки через соседей и отчёт финала ───────────────
# 🔴 Владелец (2026-09-13): аналитик обязан считывать эффекты длиннее одного ребра
# (институты → геополитика → экономика) и обратные петли (геополитика → экономика →
# обратно в геополитику). Для этого в финале ему даны ПОЛНЫЕ черновики соседей и
# все методички, включая чужие.
CHAINS_RULE = """
===== ЦЕПОЧКИ ЧЕРЕЗ СОСЕДЕЙ (обязательно) =====
Считывай эффекты длиннее одного ребра и обратные петли — для этого тебе даны ПОЛНЫЕ
черновики обоих соседей и все методички, включая чужие. Примеры: событие в институтах →
изменило геополитику → дошло до экономики; геополитика → экономика → обратно в
геополитику (выносливость курса). Открой методички-связки ОБОИХ рёбер цепочки (не
только своего) и разбери по звеньям. Верни поле "cross_chains": [ {"chain": <контур →
контур → контур>, "trigger": <событие с датой>, "links": [ {"edge": <ГМ|МГ|ГИ|ИГ|ИМ|МИ>,
"mechanism", "methodology": <doc:раздел>} ], "effect_on_me": <какой блок/поле и как>,
"status": <Ф|Д|В|Г>} ]. Нет цепочек — так и напиши, почему.
"""

FINAL_FIELDS = (
    '"answers_to_peers": [...] — ответы на ВСЕ вопросы соседей к черновику, с числом и источником; '
    '"contradictions_resolved": [ {"topic", "action": <снято|объяснено>, "detail"} ] — по каждому '
    'противоречию сверки; "critique_resolved": [ {"rule", "where", "action": <исправлено|отклонено>, '
    '"detail"} ] — по каждому замечанию проверяющего; "lessons_applied": [...]; '
    '"cross_chains": [...] — см. блок ЦЕПОЧКИ'
)

ALL_SHELF = ["code", "macro_base", "inst_env", "geo_base", "geo_events", "geo", "geo_macro",
             "macro_geo", "geo_inst", "inst_geo", "inst_macro", "macro_inst", "macro_sector", "macro"]


def final_gate_notes(fresh: dict, questions: list, contradictions: list, critique: list) -> list[str]:
    """Финал вечерней сборки обязан отчитаться по каждому входу: вопросы соседей,
    противоречия сверки, замечания проверяющего, цепочки. Пустой отчёт при непустом
    входе — заметка: видно механически, что не доработано."""
    notes = []
    if questions and len(fresh.get("answers_to_peers") or []) < len(questions):
        notes.append(f"answers_to_peers: ответов {len(fresh.get('answers_to_peers') or [])} на {len(questions)} вопросов соседей")
    if contradictions and len(fresh.get("contradictions_resolved") or []) < len(contradictions):
        notes.append(f"contradictions_resolved: разобрано {len(fresh.get('contradictions_resolved') or [])} из {len(contradictions)}")
    if critique and len(fresh.get("critique_resolved") or []) < len(critique):
        notes.append(f"critique_resolved: отчёт по {len(fresh.get('critique_resolved') or [])} из {len(critique)} замечаний")
    if not fresh.get("cross_chains"):
        notes.append("cross_chains: цепочки через соседей не разобраны (или не объяснено, почему их нет)")
    return notes
