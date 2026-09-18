"""Экран «Оценка ситуации» раздела «Геополитика» — форма выхода по спецификации владельца.

🔴 ЗАЧЕМ (владелец, 2026-09-16 → 2026-09-18). Спецификация
`docs/Оценка_ситуации_Геополитика.md` (v1.1) задаёт, ЧТО видит пользователь по каждому
очагу: блоки в фиксированном порядке — состояние и динамика; движущие силы и устойчивость;
сценарии развития; последствия для экономики России. По решению владельца после
прототипа (2026-09-18): блоки «Лента» и «Основания» на экран не выводятся, обратимость
снята, карта входит в первый блок, плиток с числами нет; субиндексы G1–G13 и общий балл
не считаются вообще — старая методика.

Разделение труда (владелец, 2026-09-18: «блок про экономику должен писать экономист, а не
геополитик — я для этого и писал все методички, чтобы агенты могли сами всё сделать»):
  • ГЕОПОЛИТИК (barometer_daily) заполняет блоки 1–3 по каждому очагу → поле `screen` его
    сводки; карта — из собранных данных контроля территории и ударов;
  • ЭКОНОМИСТ (macro_state) получает ветви геополитика и заполняет блок 4 по каждому очагу →
    поле `hotspot_effects` его сводки: цифры из данных платформы с датами, каналы с
    механикой, лестница финансирования (МГ 7.2) для очага-участника, институциональный слой
    из передачи институционалиста, отраслевой слой с компаниями, сравнение по ветвям;
  • КОД держит каркас: наличие блоков, пороговое событие у каждой ветви, вероятности числом
    внутри и словами снаружи (единая шкала мандата), словарь замен терминов (Часть 8 +
    замечания владельца к прототипу), перенос пропавшего блока с прошлой версии с пометкой,
    сборка экрана из двух сводок (assemble) — у каждого блока своя дата.

Спецификация читается с диска по времени изменения (как операционный протокол): правка
владельцем доезжает до агентов без деплоя. Методички остаются на полке — агент открывает
разделы сам; здесь только контракт с витриной.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SPEC_PATH = os.path.join(_REPO, "docs", "Оценка_ситуации_Геополитика.md")

HOTSPOTS: tuple[str, ...] = ("svo", "middle_east", "atr")
HOTSPOT_LABELS = {"svo": "СВО", "middle_east": "Ближний Восток", "atr": "АТР"}
# Конфигурация участия России (спецификация, Часть 6): задаёт акценты блоков.
HOTSPOT_CONFIG = {"svo": "участник", "middle_east": "наблюдатель", "atr": "контрагент"}
CONFIG_LABELS = {
    "участник": "Россия — непосредственный участник",
    "наблюдатель": "Россия — внешний наблюдатель и контрагент",
    "контрагент": "Россия — экономический контрагент с риском концентрации",
}

GOAL_DIRECTIONS = ("к цели", "стоит", "от цели")
GOAL_SPEEDS = ("быстрее", "так же", "медленнее")
DURATION_LABELS = ("месяцы", "около года", "год и дольше", "годы")
SECTOR_DIRECTIONS = ("помогает", "мешает", "по-разному", "не влияет")

# ─────────────── вероятности: число внутри, слово снаружи (мандат старшего аналитика) ───────────────
P_WORDS: tuple[tuple[float, str], ...] = (
    (0.05, "крайне маловероятно"), (0.20, "маловероятно"), (0.45, "возможно"),
    (0.70, "скорее да"), (0.90, "вероятно"), (1.01, "почти наверняка"),
)


def p_words(p) -> str | None:
    try:
        x = float(p)
    except (TypeError, ValueError):
        return None
    if x < 0:
        return None
    for top, word in P_WORDS:
        if x <= top:
            return word
    return "почти наверняка"


# ─────────────── словарь замен (спецификация, Часть 8 + прототип 2026-09-18) ───────────────
# Термин → чем заменить. Гейт только ПОМЕЧАЕТ (агент обязан переписать в финале, проверяющий
# видит заметку); код не переписывает текст сам — замена без контекста ломает фразу.
TERM_DICT: tuple[tuple[str, str], ...] = (
    (r"пространств\w* сделк\w*", "«условия, на которые согласились бы обе стороны»"),
    (r"\bистощени\w*", "«сколько ещё стороны могут вести противостояние на нынешних ресурсах»"),
    (r"\bобратимост\w*", "«что вернётся, если ситуация развернётся»"),
    (r"санкционн\w*\s+клин\w*", "«разница между мировой ценой и тем, что реально получает экономика»"),
    (r"\bклин\w*\s+цен\w*", "«разница между мировой ценой и тем, что реально получает экономика»"),
    (r"трансмисси\w*\s+ставк\w*", "«как решения по ставке доходят до экономики»"),
    (r"запас\w*\s+выносливост\w*", "«откуда сторона берёт деньги на продолжение и что это ей стоит»"),
    (r"\bвыносливост\w*", "«сколько ещё сторона может вести противостояние и какой ценой»"),
    (r"хвостов\w*\s+риск\w*", "«маловероятный, но тяжёлый сценарий»"),
    (r"пустот\w*\s+услови\w*", "«нет условий, которые устроили бы обе стороны»"),
    (r"\bактор\w*", "«сторона» или «игрок»"),
    (r"\bселекторат\w*", "«решающая коалиция» словами"),
    (r"двухуровнев\w*\s+игр\w*", "«сделка должна устроить и лидеров, и тех, на кого они опираются»"),
    (r"\bконтрфакт\w*", "«что было бы без этого события»"),
    (r"\bнарратив\w*", "«объяснение» или «версия»"),
    (r"\bсубиндекс\w*", "убрать: субиндексы не считаем"),
    (r"\bбарометр\w*", "«оценка обстановки» или «сводка»"),
    (r"\bэскалац\w*", "допустимо только с пояснением «расширение или ужесточение противостояния»"),
)
_TERM_RX = [(re.compile(p, re.IGNORECASE), hint) for p, hint in TERM_DICT]
# «Эскалация» допустима, если рядом есть расшифровка (первый живой прогон 2026-09-18 дал
# «Эскалация (расширение или ужесточение противостояния)» — это правильно, не замечание).
_ESCALATION_OK = re.compile(r"расширени\w*\s+или\s+ужесточени\w*", re.IGNORECASE)
# Внутренние коды в тексте для пользователя (правило языка витрины).
_CODE_RX = re.compile(r"\b(?:S[1-4][ab]?|G(?:1[0-3]|[1-9])|ME[1-4]|ATR[1-4]|SVO[1-4]|M(?:1[0-3]|[1-9]))\b")
# Статусы утверждений Ф/Д/В/Г — служебная разметка; в тексте для читателя их быть не должно
# (первый прогон: «(NSP, В)», «статус Г», «класс, В/Г» прямо в прозе).
_STATUS_RX = re.compile(r"\((?:[^()]{0,40},\s*)?[ФДВГ](?:/[ФДВГ])?\)|\bстатус\w*\s+[ФДВГ]\b")
_DIGIT_RX = re.compile(r"\d")
_TICKER_RX = re.compile(r"^[A-Z0-9]{2,7}$")
_PROB_IN_LABEL_RX = re.compile(r"\s*\((?:[^()]*\d[^()]*)\)")


def term_notes(obj, label: str) -> list[str]:
    """Заметки по словарю замен, внутренним кодам и статусам во всех текстах объекта."""
    text = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    notes: list[str] = []
    seen: set[str] = set()
    for rx, hint in _TERM_RX:
        m = rx.search(text)
        if not m or hint in seen:
            continue
        if m.group(0).lower().startswith("эскалац") and _ESCALATION_OK.search(text):
            continue
        seen.add(hint)
        notes.append(f"{label}: язык — «{m.group(0)}» → {hint}")
    values = _strip_keys(obj)
    codes = sorted(set(_CODE_RX.findall(values)))
    if codes:
        notes.append(f"{label}: внутренние коды в тексте для пользователя: {', '.join(codes[:6])}")
    st = _STATUS_RX.search(values)
    if st:
        notes.append(f"{label}: статусы Ф/Д/В/Г в тексте для читателя («{st.group(0)}») — словами «факт / оценка / гипотеза» или в поле status")
    return notes


def tickers_by_sector(db, cap: int = 14) -> str:
    """Тикеры платформы по секторам — экономисту для sectors[].tickers (первый прогон
    2026-09-18 вернул пустые списки: агент не знал, какие имена у платформы есть). Мягко."""
    try:
        from app.models.company import Company
        rows = db.query(Company.sector, Company.ticker).all()
    except Exception:  # noqa: BLE001
        return ""
    by: dict[str, list[str]] = {}
    for sector, ticker in rows:
        if ticker:
            by.setdefault(sector or "Прочее", []).append(str(ticker))
    if not by:
        return ""
    lines = ["ТИКЕРЫ ПЛАТФОРМЫ ПО СЕКТОРАМ (для hotspot_effects.<очаг>.sectors[].tickers — только отсюда, 1–4 на строку):"]
    for sector in sorted(by):
        tk = sorted(set(by[sector]))
        more = f" … ещё {len(tk) - cap}" if len(tk) > cap else ""
        lines.append(f"  {sector}: {', '.join(tk[:cap])}{more}")
    return "\n".join(lines)


def _strip_keys(obj) -> str:
    """Текст значений без ключей вроде \"key\": \"SVO3\" — код в ключе ветви законен,
    в подписи для пользователя — нет."""
    if isinstance(obj, dict):
        return " ".join(_strip_keys(v) for k, v in obj.items() if k not in ("key", "columns", "cols", "branch_key"))
    if isinstance(obj, list):
        return " ".join(_strip_keys(v) for v in obj)
    if isinstance(obj, str):
        return obj
    return ""


# ─────────────── спецификация владельца с диска (по времени изменения) ───────────────
_cache: dict[str, tuple[float, str]] = {}


def spec_text() -> str:
    try:
        mtime = os.path.getmtime(SPEC_PATH)
    except OSError:
        return ""
    hit = _cache.get("spec")
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        with open(SPEC_PATH, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    _cache["spec"] = (mtime, text)
    return text


def spec_parts(*keys: str) -> str:
    """Части спецификации по заголовкам «## Часть N…» (ключ — «Часть 1», «Часть 8»…)."""
    text = spec_text()
    if not text:
        return ""
    heads = [(m.start(), m.group(0)) for m in re.finditer(r"^## .+$", text, re.M)]
    out = []
    for i, (pos, head) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        title = head.lstrip("# ").strip()
        m = re.match(r"^(Часть\s+\d+|Приложение)", title)
        key = m.group(1) if m else title
        if key in keys:
            out.append(text[pos:end].strip())
    return "\n\n".join(out)


# ─────────────── контракт формы: геополитик, блоки 1–3 + карта ───────────────
GEO_SCREEN_SPEC = (
    "\n===== ЭКРАН «ОЦЕНКА СИТУАЦИИ» — поле screen, обязательно (спецификация владельца, "
    "docs/Оценка_ситуации_Геополитика.md; её Части 0–3, 6, 8 открой с полки geo_screen) =====\n"
    "Помимо прежних полей верни \"screen\": { <очаг: svo|middle_east|atr>: {\n"
    "  \"config\": <участник|наблюдатель|контрагент — конфигурация участия России (Часть 6)>,\n"
    "  \"state\": {   // блок 1 «Состояние и динамика»\n"
    "    \"phase\": <фаза по жизненному циклу события обыденными словами: острая фаза, затяжное "
    "противостояние, переговорная пауза, заморозка, послеконфликтное состояние>,\n"
    "    \"summary\": [ <ровно 5 предложений, каждое полное и самодостаточное: 1) фаза и что "
    "происходит физически; 2) стороны и ЧЕГО КАЖДАЯ ДОБИВАЕТСЯ НА ДЕЛЕ — по распределению усилий "
    "(Г 8.5), а не по заявлениям; 3) что удерживает ситуацию; 4) на чьей стороне время; 5) что "
    "изменилось с прошлого среза> ],\n"
    "    // 🔴 ЦЕЛИ СТОРОН ПО СВО (владелец, 2026-09-18, ошибка первого прогона): Россия НЕ "
    "добивается «гарантий безопасности» — это цель УКРАИНЫ (гарантии, что нападение не повторится). "
    "Цели России: закрепление контроля над территориями, нейтральный статус Украины без НАТО, зона "
    "безопасности от дальнобойного оружия; на сделку без этих условий не идёт. Формулировка «Россия "
    "хочет урегулирования с гарантиями безопасности» — брак, гейт её помечает.\n"
    "    \"goals\": [ {\"side\", \"goal\": <фактическая цель словами>, \"direction\": <к цели|стоит|от цели>, "
    "\"speed\": <быстрее|так же|медленнее — относительно прошлого периода>, \"achievable\": <вывод "
    "словами ОБЯЗАТЕЛЬНО с оборотом «при сохранении нынешних условий»; для территориальных целей — "
    "из темпов изменения контроля за период и их динамики, только вывод, без расчёта>, "
    "\"status\": <Ф|Д|В|Г>} ],\n"
    "    \"time\": [ {\"axis\": <военный баланс | откуда стороны берут деньги на продолжение и что "
    "это им стоит | устойчивость внешней поддержки>, \"side\": <в чью пользу время, или «ничья»>, "
    "\"shift\": <как меняется, одной фразой>, \"why\": <2–3 предложения с датами и числами>, "
    "\"status\"} ],\n"
    "    \"time_verdict\": <одна фраза: совокупно на чьей стороне время>\n"
    "  },\n"
    "  \"forces\": {   // блок 2 «Движущие силы и устойчивость ситуации»\n"
    "    \"items\": [ {\"who\": <кто и чего хочет — заголовком>, \"text\": <2–3 фразы: почему не может "
    "иначе; по группам внутри сторон, не по странам как монолитам>} ] — 3–4 силы,\n"
    "    \"holds\": [ <что удерживает ситуацию: заинтересованные в продолжении и их вес, понесённые "
    "издержки, отсутствие приемлемых условий, отсутствие гарантий — по одной полной фразе> ],\n"
    "    \"change\": [ <что способно её изменить: истощение ресурсов и его темп, зависимость от "
    "внешней поддержки, смена целей или решающих коалиций, внешние календари — по фразе> ],\n"
    "    \"duration\": {\"label\": <месяцы|около года|год и дольше|годы>, \"why\": <1–2 фразы, "
    "выведенные из соотношения двух колонок, не из интуиции>, \"shortens\": <что должно измениться, "
    "чтобы горизонт сократился>},\n"
    "    \"twist\": <неочевидное звено одним предложением; допустимо null>\n"
    "  },\n"
    "  \"scenarios\": {   // блок 3 «Сценарии развития»\n"
    "    \"branches\": [ {\"key\": <тот же ключ, что в regions.<очаг>.scenarios.items>, \"label\": "
    "<название ветви для ЭТОГО очага>, \"p6m\": <доля>, \"p18m\": <доля>, \"base\": <true у ровно "
    "одной>, \"most_dangerous\": <true у ровно одной, НЕ базовой>, \"danger_why\": <почему опасна для "
    "экономики; только у опасной>, \"how_we_get_there\": <НАБЛЮДАЕМЫЕ пороговые события перехода в "
    "эту ветвь: подписание, ввод сил, изменение поддержки, физическое событие — не оценки>, "
    "\"what\": <что там происходит, 2–3 предложения>, \"why\": <почему так>, \"how_long\": <как долго>, "
    "\"for_us\": <что это значит для российской экономики — направление и механизм; цифры по "
    "ветвям даст экономист>} ] — 3–4 ветви; для очага с боевыми действиями заморозка — отдельная "
    "ветвь; сумма p6m = 1.0 и сумма p18m = 1.0; вероятности числом — слова подставит код,\n"
    "    \"nearest\": {\"event\": <ближайшее наблюдаемое событие пересмотра>, \"what_it_triggers\": "
    "<какой переход оно запускает и что будет, если не случится>},\n"
    "    \"other_thresholds\": [ <остальные пороговые события по ветвям> ]\n"
    "  },\n"
    "  \"map\": {\"kind\": <для очага с боевыми действиями — контроль территории и удары; для "
    "внешних — узкие места, маршруты и объекты, значимые для каналов в экономику>, "
    "\"dynamics\": [ {\"k\", \"v\"} ] — 3–4 строки с числами за период из данных по очагу "
    "(площадь контроля, изменение за период, заявленные переходы, удары по классам объектов), "
    "\"points\": [ {\"k\", \"v\"} ] — 3–4 точки, значимые для каналов в экономику}\n"
    "} }\n"
    "🔴 ПРАВИЛА ЭКРАНА (Часть 8 спецификации + замечания владельца к прототипу 2026-09-18):\n"
    "  • обычные слова, ПОЛНЫЕ фразы: не «проигнорировано обеими», а «проигнорировали и Москва, "
    "и Киев»; термины заменяй: не «пространство сделки», а «условия, на которые согласились бы "
    "обе стороны»; не «истощение», а «сколько ещё стороны могут вести противостояние»; не "
    "«хвостовой риск», а «маловероятный, но тяжёлый сценарий»; не «актор», а «сторона»;\n"
    "  • НЕ «выдержит ли бюджет N месяцев»: оценивай, на какой ступени лестницы финансирования "
    "стоит государство (резервы → внутренний долг → налоги и изъятия → принудительные займы, "
    "контроль капитала, эмиссия — МГ 7.2, 6.4) и что стоит следующая ступень;\n"
    "  • направление — только по наблюдаемым данным (контроль территории, удары, дорогостоящие "
    "сигналы, поведение покровителей), не по заявлениям; достижимость — не предсказание исхода; "
    "«кто победит» запрещено; политических и моральных оценок нет; хроники в блоках нет;\n"
    "  • ни одного внутреннего кода (S3, G7, ME2) и ни одного числового балла в текстах; "
    "субиндексы и общий балл НЕ возвращай — их больше нет;\n"
    "  • у каждой ветви есть пороговое событие; наиболее вероятная и наиболее опасная ветви "
    "различаются явно; изменение вероятности между срезами — только с обоснованием событием;\n"
    "  • блоки читают люди без подготовки: каждое утверждение самодостаточно, инциденты называй "
    "с расшифровкой («над Балтийским морем: сбитый над Литвой беспилотник…»), не одним словом.\n"
)

# ─────────────── контракт формы: экономист, блок 4 по очагам ───────────────
MACRO_SCREEN_SPEC = (
    "\n===== БЛОК «ПОСЛЕДСТВИЯ ДЛЯ ЭКОНОМИКИ РОССИИ» ПО ОЧАГАМ — поле hotspot_effects, обязательно "
    "(спецификация владельца docs/Оценка_ситуации_Геополитика.md, Часть 4 и 6 — на полке geo_screen) =====\n"
    "Это ТВОЙ блок на экране геополитики: геополитик даёт ветви и состояние очага (в задании), а "
    "цифры и механика влияния на экономику — твои. По КАЖДОМУ очагу из задания верни "
    "\"hotspot_effects\": { <svo|middle_east|atr>: {\n"
    "  \"intro\": <2–3 фразы: какие каналы задействованы и с чего начинается разбор — для участника "
    "с бюджета/труда/санкций/инфраструктуры; для внешнего очага — с МИРОВЫХ переменных (цена "
    "сырья, маршруты, мировой спрос и ставки), две волны с разными знаками; для контрагента — с "
    "КОНЦЕНТРАЦИИ: канал сбыта, расчёты, компоненты>,\n"
    "  \"now\": [ {\"indicator\", \"value\", \"note\": <дата, источник, сравнение>} ] — 6–10 показателей "
    "на дату из данных платформы (ставка, инфляция, ВВП, дефицит, инвестиции, безработица, курс, "
    "цена сырья, для внешнего — трафик/фрахт/ставки ФРС, для контрагента — товарооборот и доля "
    "расчётов),\n"
    "  \"channels\": [ {\"name\": <канал обыденно: «Топливо и заводы», «Бюджет и госзаказ», «Ставка и "
    "кредит», «Санкции», «Курс рубля», «Плата за риск»…>, \"scale\": <класс масштаба словами и "
    "куда движется>, \"now\": <ЧТО ПРОИСХОДИТ — с числами и датами, 2–4 предложения>, "
    "\"how\": <КАК ДОХОДИТ — механика шаг за шагом до макропоказателя, с числами; что усиливает и "
    "что мешает каналу работать>, \"where\": <КУДА ДВИЖЕТСЯ — путь по базовому и по другим "
    "ветвям, с числами: ставка, инфляция, дефицит, курс>, \"who\": <кого касается: отрасли и "
    "компании>} ] — 4–6 каналов; для очага-участника ОБЯЗАТЕЛЕН канал бюджета с ЛЕСТНИЦЕЙ "
    "ФИНАНСИРОВАНИЯ (МГ 7.2): на какой ступени государство — резервы → долг → налоги и изъятия → "
    "принудительные займы/контроль капитала/эмиссия, — что уже происходит на каждой ступени "
    "(с числами) и что стоит следующая; НЕ «хватит ли денег на N месяцев»;\n"
    "  \"systemic\": <абзац: как каналы усиливают друг друга через ставку и бюджет — не по одному>,\n"
    "  \"institutional\": [ {\"what\": <конкретное проявление с датами и числами — из передачи "
    "институционалиста и его сводки>, \"effect\": <во что выливается для экономики и бизнеса>} ] — "
    "4–6 строк,\n"
    "  \"sectors\": [ {\"sector\", \"tickers\": [<1–4 тикера ИЗ СПИСКА «ТИКЕРЫ ПЛАТФОРМЫ ПО СЕКТОРАМ» "
    "в задании — обязательно; пустой список только если в секторе нет подходящих имён, тогда скажи "
    "почему в why>], \"direction\": <помогает|мешает|по-разному|не влияет>, \"metric\": <через что: "
    "выручка, маржа, издержки, логистика, спрос, ставка>, \"numbers\": <цифры>, \"why\": <почему "
    "именно этот очаг>} ] — 5–10 строк, кому помогает и кому мешает,\n"
    "  \"by_branch\": {\"columns\": [ {\"key\": <ключ ветви геополитика>, \"label\"} ], "
    "\"rows\": [ {\"indicator\": <ВВП|инфляция|ставка|дефицит|курс|экспорт и топливо…>, "
    "\"cells\": [<по колонке, с числами или диапазонами>]} ]} — сравнение по ветвям ИМЕННО ЭТОГО "
    "очага, колонки = ветви геополитика из задания (те же ключи и порядок); в label колонки — "
    "название ветви БЕЗ вероятности числом (вероятности на экране только словами)\n"
    "} }\n"
    "🔴 ПРАВИЛА: числа только из данных платформы и внешних прогнозов, с датами; обычные слова, "
    "полные фразы, без терминов (не «клин цены», а «разница между мировой ценой и тем, что реально "
    "получает экономика»; не «трансмиссия ставки», а «как решения по ставке доходят до "
    "экономики»); каналы не бьют по одному — покажи связки; компании называй как затронутые "
    "каналом, без «купить/продать»; внутренних кодов и баллов нет.\n"
)


def branches_block(geo_payload: dict | None) -> str:
    """Ветви и состояние очагов из сводки геополитика — в задание экономисту."""
    if not isinstance(geo_payload, dict):
        return "ВЕТВИ ГЕОПОЛИТИКА ПО ОЧАГАМ: сводки геополитика нет — блок hotspot_effects строй по regions прошлой версии, если есть, и пометь в data_flags."
    screen = geo_payload.get("screen") if isinstance(geo_payload.get("screen"), dict) else {}
    regions = geo_payload.get("regions") if isinstance(geo_payload.get("regions"), dict) else {}
    out = [f"ВЕТВИ ГЕОПОЛИТИКА ПО ОЧАГАМ (сводка от {geo_payload.get('as_of')}; заполни hotspot_effects по каждому):"]
    for h in HOTSPOTS:
        sc = screen.get(h) if isinstance(screen.get(h), dict) else {}
        st = sc.get("state") or {}
        branches = ((sc.get("scenarios") or {}).get("branches")) or []
        if not branches:
            items = ((regions.get(h) or {}).get("scenarios") or {}).get("items") or []
            branches = [{"key": it.get("key"), "label": it.get("label"), "p6m": it.get("p6m"), "p18m": it.get("p18m"),
                         "how_we_get_there": it.get("note")} for it in items if isinstance(it, dict)]
        out.append(f"\n— {HOTSPOT_LABELS[h]} ({h}; конфигурация: {sc.get('config') or HOTSPOT_CONFIG[h]}):")
        if st.get("phase"):
            out.append(f"  фаза: {st['phase']}")
        if st.get("summary"):
            out.append("  состояние: " + " ".join(str(x) for x in st["summary"])[:1500])
        elif (regions.get(h) or {}).get("summary"):
            out.append("  состояние: " + str(regions[h]["summary"])[:1500])
        for b in branches:
            if not isinstance(b, dict):
                continue
            mark = " [базовая]" if b.get("base") else (" [наиболее опасная]" if b.get("most_dangerous") else "")
            out.append(f"  • {b.get('key')} — {b.get('label')}{mark}: 6 мес {b.get('p6m')}, 18 мес {b.get('p18m')}; "
                       f"как сюда попадём: {str(b.get('how_we_get_there') or '')[:300]}")
    return "\n".join(out)


# ─────────────── гейт геополитика ───────────────
def _normalize(branches: list[dict], field: str, label: str, notes: list[str]) -> None:
    try:
        vals = [(b, float(b.get(field))) for b in branches if b.get(field) is not None]
    except (TypeError, ValueError):
        notes.append(f"{label}: нечисловые вероятности {field} — оставлены как есть")
        return
    total = sum(v for _, v in vals)
    if total > 0 and abs(total - 1.0) > 0.005:
        for b, v in vals:
            b[field] = round(v / total, 3)
        notes.append(f"{label}: сумма {field} {total:.3f} → нормализована")


def geo_screen_gate(fresh: dict, prev: dict | None) -> list[str]:
    """Каркас экрана держит код. Пропавший очаг — с прошлой версии с пометкой; отсутствие
    поля целиком — заметка, не отклонение (сводка без экрана хуже, чем с ним, но лучше, чем
    никакой). Слова вероятностей подставляются здесь же."""
    notes: list[str] = []
    screen = fresh.get("screen")
    prev_screen = (prev or {}).get("screen") if isinstance(prev, dict) else None
    if not isinstance(screen, dict) or not screen:
        if isinstance(prev_screen, dict) and prev_screen:
            fresh["screen"] = json.loads(json.dumps(prev_screen, ensure_ascii=False))
            fresh["screen"]["carried_over"] = True
            notes.append("screen: не вернулся — перенесён с прошлой версии целиком")
        else:
            notes.append("screen: отсутствует — экран «Оценка ситуации» не собран (спецификация владельца)")
        return notes
    for h in HOTSPOTS:
        label = f"screen.{h}"
        sc = screen.get(h)
        if not isinstance(sc, dict) or not sc:
            if isinstance(prev_screen, dict) and isinstance(prev_screen.get(h), dict):
                screen[h] = json.loads(json.dumps(prev_screen[h], ensure_ascii=False))
                screen[h]["carried_over"] = True
                notes.append(f"{label}: очаг не вернулся — перенесён с прошлой версии")
            else:
                notes.append(f"{label}: очага нет ни сейчас, ни раньше")
            continue
        sc.pop("carried_over", None)
        if sc.get("config") not in CONFIG_LABELS:
            sc["config"] = HOTSPOT_CONFIG[h]
            notes.append(f"{label}.config: не из списка → «{HOTSPOT_CONFIG[h]}»")
        # блок 1
        st = sc.get("state") if isinstance(sc.get("state"), dict) else None
        if not st:
            notes.append(f"{label}.state: блок 1 пуст")
        else:
            summ = st.get("summary")
            if not isinstance(summ, list) or len(summ) < 4:
                notes.append(f"{label}.state.summary: меньше четырёх предложений")
            goals = st.get("goals") if isinstance(st.get("goals"), list) else []
            if len(goals) < 2:
                notes.append(f"{label}.state.goals: меньше двух сторон")
            for g in goals:
                if not isinstance(g, dict):
                    continue
                # 🔴 Владелец (2026-09-18): гарантии безопасности просит Украина, не Россия.
                if h == "svo" and re.search(r"росси", str(g.get("side") or ""), re.IGNORECASE) \
                        and re.search(r"гарант", str(g.get("goal") or ""), re.IGNORECASE):
                    notes.append(f"{label}.state.goals[Россия]: цель сформулирована через «гарантии безопасности» — это цель Украины; у России: закрепление контроля, нейтральный статус Украины, зона безопасности — переписать")
                if g.get("direction") not in GOAL_DIRECTIONS:
                    notes.append(f"{label}.state.goals[{g.get('side')}]: направление не из списка")
                if g.get("speed") not in GOAL_SPEEDS:
                    notes.append(f"{label}.state.goals[{g.get('side')}]: скорость не из списка")
                if "при сохранении" not in str(g.get("achievable") or ""):
                    notes.append(f"{label}.state.goals[{g.get('side')}]: достижимость без оговорки «при сохранении нынешних условий»")
            if len(st.get("time") or []) < (3 if sc.get("config") == "участник" else 2):
                notes.append(f"{label}.state.time: шкал фактора времени меньше, чем требует конфигурация")
        # блок 2
        fo = sc.get("forces") if isinstance(sc.get("forces"), dict) else None
        if not fo:
            notes.append(f"{label}.forces: блок 2 пуст")
        else:
            if len(fo.get("items") or []) < 3:
                notes.append(f"{label}.forces.items: меньше трёх движущих сил")
            if not fo.get("holds") or not fo.get("change"):
                notes.append(f"{label}.forces: колонки «удерживает / способно изменить» неполны")
            dur = fo.get("duration") if isinstance(fo.get("duration"), dict) else {}
            if dur.get("label") not in DURATION_LABELS:
                notes.append(f"{label}.forces.duration.label: не из списка ({', '.join(DURATION_LABELS)})")
            if len(str(dur.get("why") or "")) < 40:
                notes.append(f"{label}.forces.duration.why: длительность без обоснования из двух колонок")
        # блок 3
        sn = sc.get("scenarios") if isinstance(sc.get("scenarios"), dict) else None
        branches = (sn or {}).get("branches") if sn else None
        if not isinstance(branches, list) or len(branches) < 3:
            notes.append(f"{label}.scenarios: меньше трёх ветвей")
        else:
            branches = [b for b in branches if isinstance(b, dict)]
            sn["branches"] = branches
            _normalize(branches, "p6m", label, notes)
            _normalize(branches, "p18m", label, notes)
            bases = [b for b in branches if b.get("base")]
            dangers = [b for b in branches if b.get("most_dangerous")]
            if len(bases) != 1:
                # базовая — самая вероятная на 6 мес
                for b in branches:
                    b["base"] = False
                try:
                    top = max(branches, key=lambda b: float(b.get("p6m") or 0))
                    top["base"] = True
                    notes.append(f"{label}.scenarios: базовая ветвь помечена кодом по максимальной вероятности")
                except (TypeError, ValueError):
                    notes.append(f"{label}.scenarios: базовая ветвь не определена")
            if len(dangers) != 1 or (dangers and dangers[0].get("base")):
                notes.append(f"{label}.scenarios: наиболее опасная ветвь не помечена ровно одна и отдельно от базовой")
            for b in branches:
                if len(str(b.get("how_we_get_there") or "")) < 15:
                    notes.append(f"{label}.scenarios[{b.get('key')}]: нет порогового события перехода — ветвь без него в дерево не входит")
                for f in ("what", "why", "how_long", "for_us"):
                    if not b.get(f):
                        notes.append(f"{label}.scenarios[{b.get('key')}]: ветвь не раскрыта — нет «{f}»")
                b["p6m_words"] = p_words(b.get("p6m"))
                b["p18m_words"] = p_words(b.get("p18m"))
            if not ((sn.get("nearest") or {}).get("event")):
                notes.append(f"{label}.scenarios.nearest: ближайшее событие пересмотра не названо")
        # карта
        mp = sc.get("map") if isinstance(sc.get("map"), dict) else None
        if not mp or not mp.get("dynamics"):
            notes.append(f"{label}.map: нет строк динамики за период")
        # язык
        notes += term_notes({k: v for k, v in sc.items() if k != "map"}, label)
    return notes


# ─────────────── гейт экономиста ───────────────
def macro_screen_gate(fresh: dict, prev: dict | None, geo_payload: dict | None) -> list[str]:
    notes: list[str] = None or []
    eff = fresh.get("hotspot_effects")
    prev_eff = (prev or {}).get("hotspot_effects") if isinstance(prev, dict) else None
    if not isinstance(eff, dict) or not eff:
        if isinstance(prev_eff, dict) and prev_eff:
            fresh["hotspot_effects"] = json.loads(json.dumps(prev_eff, ensure_ascii=False))
            fresh["hotspot_effects"]["carried_over"] = True
            notes.append("hotspot_effects: не вернулись — перенесены с прошлой версии целиком")
        else:
            notes.append("hotspot_effects: отсутствуют — блок «Последствия для экономики» по очагам не собран")
        return notes
    geo_screen = (geo_payload or {}).get("screen") if isinstance(geo_payload, dict) else None
    for h in HOTSPOTS:
        label = f"hotspot_effects.{h}"
        e = eff.get(h)
        if not isinstance(e, dict) or not e:
            if isinstance(prev_eff, dict) and isinstance(prev_eff.get(h), dict):
                eff[h] = json.loads(json.dumps(prev_eff[h], ensure_ascii=False))
                eff[h]["carried_over"] = True
                notes.append(f"{label}: очаг не вернулся — перенесён с прошлой версии")
            else:
                notes.append(f"{label}: очага нет ни сейчас, ни раньше")
            continue
        e.pop("carried_over", None)
        now = e.get("now") if isinstance(e.get("now"), list) else []
        if len(now) < 5:
            notes.append(f"{label}.now: меньше пяти показателей на дату")
        chans = e.get("channels") if isinstance(e.get("channels"), list) else []
        if len(chans) < 3:
            notes.append(f"{label}.channels: меньше трёх каналов")
        for c in chans:
            if not isinstance(c, dict):
                continue
            for f in ("now", "how", "where", "who"):
                if not c.get(f):
                    notes.append(f"{label}.channels[{c.get('name')}]: нет «{f}»")
            if c.get("now") and not _DIGIT_RX.search(str(c.get("now"))):
                notes.append(f"{label}.channels[{c.get('name')}]: «что происходит» без единого числа")
        if h == "svo":
            blob = json.dumps(chans, ensure_ascii=False).lower()
            if not any(w in blob for w in ("ступен", "лестниц")):
                notes.append(f"{label}: для очага-участника нет лестницы финансирования (МГ 7.2): резервы → долг → налоги и изъятия → принудительные займы")
        if not e.get("systemic"):
            notes.append(f"{label}.systemic: нет абзаца о связи каналов между собой")
        if len(e.get("institutional") or []) < 2:
            notes.append(f"{label}.institutional: институциональный слой пуст или из одной строки")
        secs = e.get("sectors") if isinstance(e.get("sectors"), list) else []
        if len(secs) < 3:
            notes.append(f"{label}.sectors: меньше трёх отраслей")
        empty_tickers = 0
        for s in secs:
            if not isinstance(s, dict):
                continue
            if s.get("direction") not in SECTOR_DIRECTIONS:
                notes.append(f"{label}.sectors[{s.get('sector')}]: направление не из списка ({', '.join(SECTOR_DIRECTIONS)})")
            bad = [t for t in (s.get("tickers") or []) if not isinstance(t, str) or not _TICKER_RX.match(t)]
            if bad:
                notes.append(f"{label}.sectors[{s.get('sector')}]: не тикеры — {bad[:3]}")
            if not s.get("tickers"):
                empty_tickers += 1
        if secs and empty_tickers * 2 >= len(secs):
            notes.append(f"{label}.sectors: тикеры пусты у {empty_tickers} из {len(secs)} отраслей — назвать компании из списка платформы в задании")
        bb = e.get("by_branch") if isinstance(e.get("by_branch"), dict) else {}
        cols = bb.get("columns") if isinstance(bb.get("columns"), list) else []
        # вероятность числом в подписи колонки — на экране только словами: срезаем скобку
        stripped = []
        for c in cols:
            if isinstance(c, dict) and isinstance(c.get("label"), str) and _PROB_IN_LABEL_RX.search(c["label"]):
                c["label"] = _PROB_IN_LABEL_RX.sub("", c["label"]).strip()
                stripped.append(c.get("key"))
        if stripped:
            notes.append(f"{label}.by_branch: из подписей колонок убраны числа в скобках ({stripped}) — вероятности на экране словами")
        if not cols or not bb.get("rows"):
            notes.append(f"{label}.by_branch: сравнение по ветвям пусто")
        elif isinstance(geo_screen, dict) and isinstance(geo_screen.get(h), dict):
            gk = [b.get("key") for b in (((geo_screen[h].get("scenarios") or {}).get("branches")) or []) if isinstance(b, dict)]
            ck = [c.get("key") if isinstance(c, dict) else None for c in cols]
            if gk and set(ck) != set(gk):
                notes.append(f"{label}.by_branch: колонки {ck} не совпадают с ветвями геополитика {gk}")
        notes += term_notes(e, label)
    return notes


# ─────────────── сборка экрана из двух сводок ───────────────
def _row_date(row) -> str | None:
    if row is None:
        return None
    p = row.payload or {}
    return p.get("as_of") or (row.created_at.date().isoformat() if getattr(row, "created_at", None) else None)


def assemble(db) -> dict:
    """Экран по очагам: блоки 1–3 и карта — из опубликованной сводки геополитика, блок 4 — из
    опубликованной сводки экономиста. У каждого блока своя дата (Часть 9.2: экран не создаёт
    иллюзии, что всё собрано сегодня)."""
    from app.services import barometer_store
    geo_row = barometer_store.current_row(db, "geo")
    geo = (geo_row.payload or {}) if geo_row else {}
    screen = geo.get("screen") if isinstance(geo.get("screen"), dict) else {}
    macro_row = barometer_store.current_row(db, "macro")
    macro = (macro_row.payload or {}) if macro_row else {}
    eff = macro.get("hotspot_effects") if isinstance(macro.get("hotspot_effects"), dict) else {}
    profile_date = None
    try:
        from app.services.geo_conflict_profile import get_latest as _profiles
        prof = _profiles(db) or {}
        profile_date = str(prof.get("_generated_at") or "")[:10] or None
    except Exception:  # noqa: BLE001
        prof = {}
    hotspots = {}
    for h in HOTSPOTS:
        sc = screen.get(h) if isinstance(screen.get(h), dict) else None
        if not sc:
            continue
        sc = json.loads(json.dumps(sc, ensure_ascii=False))
        for b in (((sc.get("scenarios") or {}).get("branches")) or []):
            if isinstance(b, dict):
                b.setdefault("p6m_words", p_words(b.get("p6m")))
                b.setdefault("p18m_words", p_words(b.get("p18m")))
        cfg = sc.get("config") if sc.get("config") in CONFIG_LABELS else HOTSPOT_CONFIG[h]
        econ = eff.get(h) if isinstance(eff.get(h), dict) else None
        hotspots[h] = {
            "key": h, "label": HOTSPOT_LABELS[h], "config": cfg, "config_label": CONFIG_LABELS[cfg],
            "dates": {"geo": _row_date(geo_row), "macro": _row_date(macro_row) if econ else None,
                      "profile": profile_date},
            "state": sc.get("state"), "forces": sc.get("forces"), "scenarios": sc.get("scenarios"),
            "map": sc.get("map"), "economy": econ,
            "why_matters": ((prof.get(h) or {}).get("why_matters") if isinstance(prof, dict) else None),
            "carried_over": bool(sc.get("carried_over")),
        }
    return {"available": bool(hotspots), "order": [h for h in HOTSPOTS if h in hotspots],
            "hotspots": hotspots,
            "note": None if hotspots else "Экран по спецификации ещё не собран: ждём вечернюю сборку с полем screen у геополитика."}


# ─────────────── карточка для полки: спецификация как документ ───────────────
def shelf_when_to_use() -> str:
    return ("Когда собираешь или проверяешь экран «Оценка ситуации» раздела «Геополитика»: что "
            "именно выводится пользователю по каждому очагу (семь блоков, состав, правила "
            "заполнения), различия очагов по конфигурации участия России (Часть 6), словарь "
            "замен терминов и запреты языка (Часть 8), чек-лист ошибок вывода (Часть 10). "
            "Открывать геополитику для блоков 1–3 и карты, экономисту — для блока 4 (Часть 4), "
            "проверяющему — Части 8 и 10.")


def last_modified() -> str | None:
    try:
        return datetime.fromtimestamp(os.path.getmtime(SPEC_PATH)).isoformat(timespec="minutes")
    except OSError:
        return None
