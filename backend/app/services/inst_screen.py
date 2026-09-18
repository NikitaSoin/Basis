"""Экран «Оценка ситуации» раздела «Институциональная среда» — форма выхода по спецификации
владельца `docs/Экран_Институциональная_среда_спецификация_v1.md`.

🔴 ЗАЧЕМ (владелец, 2026-09-18, после прототипа): «можешь сделать теперь, чтобы у нас в
обозревателе было так — по дизайну как показал, без всяких плиток». Экран состоит из трёх
блоков в фиксированном порядке (Часть 0.1): изменения условий для бизнеса за период (карточки,
дайджест, вектор, серии); накопленный эффект по шести измерениям и что это значит для
экономики и отраслей; направление на год и ветви на 12–24 месяца, привязанные к сценариям
геополитического экрана. Решения владельца по прототипу: лента «Обзор» остаётся как была;
список всех карточек периода в оценке ситуации свёрнут по умолчанию; явление «белых списков»
(доступ к инфраструктуре и льготам по перечням, утверждаемым государством) обязательно
оценивается как условие для бизнеса.

Разделение труда (спецификация, Часть 7.1): карточки пишет ИНСТИТУЦИОНАЛИСТ (inst_state) —
поле `screen` его снимка; ЭКОНОМИСТ проверяет адресата, метрику и масштаб в перекрёстном
опросе; ПРОВЕРЯЮЩИЙ — язык, блоклист и чек-лист (Части 6 и 8 на полке inst_screen). КОД держит
каркас: обязательные поля карточки, словарь осязаемых следствий (Часть 5), накопление карточек
между сборками (Часть 7.2 — снимок ежедневный, а период — месяц и квартал), дайджест по
масштабу, ровно шесть измерений, ветви с пороговым событием и отметками «наиболее вероятная» и
«наиболее неблагоприятная», вероятности числом внутри и словами снаружи, словарь замен терминов
(Часть 6.1), сборка витрины (assemble).

Спецификация читается с диска по времени изменения: правка владельцем доезжает до агентов без
деплоя. Только контракт с витриной — методики остаются на полке.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SPEC_FILENAME = "Экран_Институциональная_среда_спецификация_v1.md"
SPEC_PATH = os.path.join(_REPO, "docs", SPEC_FILENAME)

MONTH_DAYS = 30
QUARTER_DAYS = 92

CARD_TYPES = ("налоги", "регулирование", "деньги", "собственность", "дивиденды", "полномочия", "внешние условия")
CARD_STATUSES = ("обсуждается", "принято", "вступает с даты", "действует", "отменено", "прецедент")
SCALES = ("малый", "умеренный", "значимый", "режимный")
_SCALE_RANK = {s: i for i, s in enumerate(SCALES)}
HORIZONS = ("месяцы", "около года", "годы")
REVERSIBILITY = ("временно", "надолго", "необратимо")
METRICS = ("выручка", "маржа", "инвестиции", "дивиденды", "стоимость капитала", "спрос", "издержки")
# Словарь осязаемых следствий (Часть 5.2) — закрытый перечень групп.
CONSEQUENCE_KINDS = {
    "taxes": "налоги", "rate": "ставка и деньги", "fx": "курс и открытость", "prices": "цены и издержки",
    "sectors": "отрасли", "property": "собственность и горизонт", "equity": "оценка акций", "budget": "бюджет",
}
DIMENSIONS: tuple[tuple[str, str, str], ...] = (
    ("predictability", "Предсказуемость условий",
     "насколько заранее известны налоги, регулирование и правила распоряжения собственностью"),
    ("property", "Защита собственности и исполнение договоров",
     "работают ли суд и принуждение к исполнению одинаково для всех"),
    ("taxes", "Налоговая нагрузка и её стабильность",
     "уровень и частота изменений налогов, пошлин, разовых изъятий"),
    ("state_share", "Участие государства в экономике",
     "доля государственного заказа, государственных компаний, регулируемых цен, льготного кредита"),
    ("competition", "Равенство условий и конкуренция",
     "насколько результат зависит от близости к государству"),
    ("openness", "Открытость экономики",
     "ограничения капитала, санкционная закрытость, внешние обязательства"),
)
DIMENSION_KEYS = tuple(k for k, _, _ in DIMENSIONS)
ARROWS = ("вверх", "вниз", "смешанно", "без изменений")
SECTOR_DIRECTIONS = ("помогает", "мешает", "по-разному")
BRANCH_KEYS = ("continuation", "fiscal", "state_expansion", "normalization")
SERIES_STATUSES = ("активна", "закрыта")


# ─────────────── вероятности словами — единая шкала мандата ───────────────
def p_words(p) -> str | None:
    try:
        from app.services.geo_screen import p_words as _pw
        return _pw(p)
    except Exception:  # noqa: BLE001 — модуль мог не доехать (Timeweb выкатывает файлы неравномерно)
        try:
            x = float(p)
        except (TypeError, ValueError):
            return None
        for top, word in ((0.05, "крайне маловероятно"), (0.20, "маловероятно"), (0.45, "возможно"),
                          (0.70, "скорее да"), (0.90, "вероятно")):
            if x <= top:
                return word
        return "почти наверняка"


# ─────────────── словарь замен (спецификация, Часть 6.1) ───────────────
# Гейт только ПОМЕЧАЕТ: агент переписывает в финале, проверяющий видит заметку. Код текст
# не правит — замена без контекста ломает фразу.
TERM_DICT: tuple[tuple[str, str], ...] = (
    (r"\bинститут\w*", "«условия для бизнеса»"),
    (r"правил\w*\s+игры", "«условия для бизнеса»"),
    (r"механизм\w*\s+изменен\w*", "«что меняется»"),
    (r"\bдискреци\w*", "«право менять условия решением, а не законом»"),
    (r"\bперсонализац\w*", "«зависимость результата от близости к государству»"),
    (r"трансакционн\w*", "«издержки на защиту, посредников и соблюдение требований»"),
    (r"фискальн\w*\s+доминирован\w*", "«бюджет требует более низкой ставки, чем нужна для инфляции»"),
    (r"порядк\w*\s+доступа", "не используется — опиши условие словами"),
    (r"\bрежим(?!н)\w*", "не используется (кроме класса масштаба «режимный») — опиши условие словами"),
    (r"\bкоалиц\w*", "не используется — причина через бюджет, внешние условия и приоритеты политики"),
    (r"\bрент(?!абельн)\w*", "не используется — назови источник дохода словами"),
    (r"\bактор\w*", "«сторона» или «игрок»"),
    (r"\bбарометр\w*", "«оценка обстановки» или «сводка»"),
    # жаргон из первого живого прогона 2026-09-18
    (r"\bэкстракц\w*", "«изъятия» или «перераспределение доходов» словами"),
    (r"фискальн\w*\s+голод\w*", "«потребность бюджета в доходах»"),
    (r"\b(?:гос)?контур\w*", "«государственный сектор» / «получатели государственного заказа и льгот» / «рыночный сегмент»"),
    (r"двухконтурн\w*", "«экономика из двух частей: государственной и рыночной»"),
)
_TERM_RX = [(re.compile(p, re.IGNORECASE), hint) for p, hint in TERM_DICT]
_CODE_RX = re.compile(r"\b(?:M(?:1[0-3]|[1-9])|S[1-4][ab]?|G(?:1[0-3]|[1-9])|И\s?\d+(?:\.\d+)?|§\s?\d)\b")
_INTENT_RX = re.compile(r"\b(?:хочет|хотят|намерен\w*|стремится|стремятся|желает|желают|решил\w*\s+наказать)\b",
                        re.IGNORECASE)
_BARE_RISK_RX = re.compile(r"риск\w*\s+(?:выше|растут|растёт|высок\w*)", re.IGNORECASE)
# вероятности числом в тексте для пользователя («p≈0,42», «вероятность 0.3») — слова подставляет код
_PROB_NUM_RX = re.compile(r"\bp\s*[≈=~]\s*0[.,]\d+|вероятност\w*\s*[≈=~:]?\s*0[.,]\d+", re.IGNORECASE)
_LEVEL_MAX = 60
_DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}")
_WHITELIST_RX = re.compile(r"бел\w*\s+спис\w*|перечн\w*|реестр\w*\s+допущенн\w*", re.IGNORECASE)


def _values_text(obj, skip_keys=("key", "id", "kind", "geo_branch", "cards", "series")) -> str:
    """Текст значений без служебных ключей: коды и ссылки (id карточек, ключи серий и ветвей) законны,
    в подписи для пользователя — нет. Пропускаются только строковые значения и списки строк под
    этими ключами; список карточек-словарей под «cards» читается целиком."""
    if isinstance(obj, dict):
        parts = []
        for k, v in obj.items():
            if k in skip_keys and (isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v))):
                continue
            parts.append(_values_text(v, skip_keys))
        return " ".join(parts)
    if isinstance(obj, list):
        return " ".join(_values_text(v, skip_keys) for v in obj)
    if isinstance(obj, str):
        return obj
    return ""


def term_notes(obj, label: str) -> list[str]:
    text = _values_text(obj)
    notes: list[str] = []
    seen: set[str] = set()
    for rx, hint in _TERM_RX:
        m = rx.search(text)
        if m and hint not in seen:
            seen.add(hint)
            notes.append(f"{label}: язык — «{m.group(0)}» → {hint}")
    codes = sorted(set(_CODE_RX.findall(text)))
    if codes:
        notes.append(f"{label}: внутренние коды в тексте для пользователя: {', '.join(codes[:6])}")
    return notes


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
    """Части спецификации по заголовкам «## Часть N…» (ключ — «Часть 5», «Приложение»…)."""
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


# ─────────────── контракт формы: институционалист, поле screen ───────────────
INST_SCREEN_SPEC = (
    "\n===== ЭКРАН «ОЦЕНКА СИТУАЦИИ» ИНСТИТУЦИОНАЛЬНОЙ СРЕДЫ — поле screen, обязательно "
    "(спецификация владельца docs/" + SPEC_FILENAME + "; её Части 0–6 и Приложение открой с полки "
    "inst_screen) =====\n"
    "Помимо прежних полей снимка верни \"screen\": {\n"
    "  \"period\": {\"from\": <YYYY-MM-DD, месяц назад>, \"to\": <сегодня>},\n"
    "  \"vector\": <ВЕКТОР ПЕРИОДА — одна фраза по адресатам и следствиям: в какую сторону и для кого "
    "сдвинулись условия за месяц (Часть 2.3); фраза без адресата и следствия не допускается>,\n"
    "  \"cards\": [ {   // КАРТОЧКА ИЗМЕНЕНИЯ (Часть 1.2) — по каждому событию периода, прошедшему тест "
    "на экономический адресат (Часть 0.2: что меняется / для кого / какая метрика)\n"
    "    \"id\": <устойчивый ключ «YYYY-MM-DD-короткий-слаг-латиницей»; у карточек из прошлого снимка "
    "СОХРАНЯЙ прежний id — по нему код накапливает карточки между сборками>,\n"
    "    \"date\": <YYYY-MM-DD события>, \"type\": <" + "|".join(CARD_TYPES) + ">,\n"
    "    \"status\": <" + "|".join(CARD_STATUSES) + ">,\n"
    "    \"title\": <что произошло — заголовком в одну строку>,\n"
    "    \"fact\": <ЧТО ПРОИЗОШЛО: документ, решение, прецедент, дата, орган — без интерпретации; 2–4 "
    "предложения>,\n"
    "    \"change\": <ЧТО МЕНЯЕТСЯ В УСЛОВИЯХ: одна фраза о механизме словами — «даёт право менять "
    "пошлины без закона», «создаёт прецедент изъятия актива по такому-то основанию», «выводит сегмент "
    "кредита из-под рыночной ставки»>,\n"
    "    \"who\": <КОГО КАСАЕТСЯ: секторы и типы компаний ПО ПРИЗНАКАМ (экспортёры, государственные "
    "компании, компании с иностранными владельцами, высокорентабельные, льготные заёмщики, активы с "
    "определённой историей приобретения) — признак важнее списка>,\n"
    "    \"who_tags\": [ <2–4 признака-тега для фильтра> ],\n"
    "    \"means\": {\"text\": <ЧТО ЭТО ЗНАЧИТ для этих компаний — метрика и направление одной фразой>, "
    "\"metrics\": [ <из: " + ", ".join(METRICS) + "> ], \"scale\": <" + "|".join(SCALES) + ">, "
    "\"horizon\": <" + "|".join(HORIZONS) + ">, \"reversibility\": <" + "|".join(REVERSIBILITY) + ">},\n"
    "    \"consequences\": [ {\"kind\": <ключ группы словаря Части 5: "
    + ", ".join(f"{k} = {v}" for k, v in CONSEQUENCE_KINDS.items()) + ">, \"text\": <ОСЯЗАЕМОЕ СЛЕДСТВИЕ как "
    "ожидание с направлением, ВСЕГДА с адресатом и метрикой: «налоговая нагрузка на экспортёров, вероятно, "
    "вырастет», «ставка останется высокой дольше для рыночных заёмщиков из-за расширения льготного "
    "кредита», «премия за риск для активов с приватизационной историей должна быть выше»; «риски выше» "
    "без адресата запрещено>} ] — 1–3 сильнейших,\n"
    "    \"driver\": <ЧТО ЗА ЭТИМ СТОИТ: одна фраза о движущей силе как ЭКОНОМИЧЕСКОЙ ПРИЧИНЕ — "
    "потребность бюджета в доходах, санкционная адаптация, приоритет бесперебойности, ответ на кризис; "
    "НЕ намерение и НЕ оценка лиц и групп (Часть 0.5, 6.2)>,\n"
    "    \"series\": {\"key\": <ключ серии из screen.series или null>, \"step\": <порядковый номер или null>},\n"
    "    \"digest\": <true у 3–5 карточек периода с наибольшим масштабом и самым широким адресатом — НЕ по "
    "громкости в новостях>,\n"
    "    \"confidence\": {\"level\": <высокая|средняя|низкая>, \"why\": <одна фраза, что её снижает>},\n"
    "    \"source\": <документ или официальное сообщение с датой; лента — сигнал, не источник факта>\n"
    "  } ] — все карточки за месяц (обычно 8–16) плюс обновлённые старые; карточки старше месяца, которые "
    "ты не вернул, код сохранит сам из прошлого снимка (до квартала),\n"
    "  \"series\": [ {\"key\": <слаг латиницей>, \"title\": <закономерность заголовком>, \"pattern\": <описание "
    "закономерности, 2–3 предложения>, \"events\": [ <строки «дата — событие», ≥2> ], \"accumulated\": "
    "<НАКОПЛЕННОЕ СЛЕДСТВИЕ — как правило, для предсказуемости условий и премии за риск; сильнее следствия "
    "любого события>, \"p_continue\": <доля 0–1, слово подставит код>, \"stop\": <что может серию остановить>, "
    "\"status\": <активна|закрыта>} ] — серия заводится при трёх и более событиях одного типа с одним "
    "адресатом за год или при двух прямо продолжающих друг друга (Часть 1.3),\n"
    "  \"dimensions\": [ {\"key\": <РОВНО шесть: " + ", ".join(f"{k} = {t}" for k, t, _ in DIMENSIONS) + ">, "
    "\"level\": <словесная оценка состояния>, \"arrow\": <" + "|".join(ARROWS) + " — за квартал>, "
    "\"arrow_note\": <«снизилась за квартал», «выросло», «смешанно»>, \"text\": <оценка как СУММА КАРТОЧЕК, "
    "2–4 предложения с датами и числами>, \"consequence\": <одно предложение об осязаемом следствии "
    "текущего состояния из словаря Части 5>, \"cards\": [ <id карточек, которые произвели стрелку — "
    "стрелка без карточек не допускается> ]} ],\n"
    "  \"economy\": [ <3–5 полных предложений: что накопленные изменения означают для экономики — стоимость "
    "денег и доступ к кредиту, инвестиции, цены, бюджет и вероятность новых изъятий; каждое выведено из "
    "измерения и карточек, с числами на дату> ],\n"
    "  \"sectors\": [ {\"who\": <сектор или тип компаний>, \"tags\": [ <тикеры Мосбиржи с платформы или "
    "признаки> ], \"direction\": <" + "|".join(SECTOR_DIRECTIONS) + ">, \"metric\": <через какую метрику>, "
    "\"measured\": <чем измерено — цифры и даты>, \"stability\": <устойчивость выигрыша или давления>} ] — 3–8 "
    "строк: кто под давлением и через что, кто выигрывает за счёт льгот, государственного заказа, защиты "
    "от конкуренции,\n"
    "  \"tax_target\": [ {\"feature\": <признак компании, повышающий вероятность изъятия в текущих условиях>, "
    "\"why\": <чем подтверждено — карточка, цифра>} ] — 3–6 признаков,\n"
    "  \"direction\": [ {\"key\": <ключ измерения>, \"arrow\": <вверх|вниз|смешанно>, \"why\": <обоснование "
    "одной фразой>} ] — ровно шесть, на год вперёд,\n"
    "  \"branches\": [ {\"key\": <" + "|".join(BRANCH_KEYS) + ">, \"label\": <название ветви словами>, "
    "\"geo_branch\": <ключ ветви геополитика из задания (S1…S4 или ключ, который дал геополитик)>, "
    "\"geo_note\": <при каком сценарии геополитического экрана, словами>, \"p\": <доля 0–1 на 12–24 месяца; "
    "сумма = 1.0>, \"base\": <true у ровно одной — наиболее вероятной>, \"worst\": <true у ровно одной, НЕ "
    "базовой — наиболее неблагоприятной для бизнеса>, \"how_we_get_there\": <ПОРОГОВЫЕ СОБЫТИЯ перехода — "
    "наблюдаемые факты: принятие документа, объявление бюджета, внешнее событие>, \"what\": <что меняется "
    "в условиях>, \"who\": <для кого>, \"means\": <что это значит — метрики и направление>, "
    "\"consequences\": [ <1–3 осязаемых следствия из словаря> ]} ] — 3–4 ветви,\n"
    "  \"thresholds\": [ <остальные пороговые события ближайших месяцев с датами> ]\n"
    "}\n"
    "🔴 ПРАВИЛА ЭКРАНА (Части 0, 5, 6, 8 спецификации + решения владельца 2026-09-18):\n"
    "  • язык: не «институты» и не «правила игры», а «условия для бизнеса»; не «механизм изменения», а «что "
    "меняется»; не «дискреция», а «право менять условия решением, а не законом»; не «персонализация», а "
    "«зависимость результата от близости к государству»; не «трансакционные издержки», а «издержки на "
    "защиту, посредников и соблюдение требований»; не «фискальное доминирование», а «бюджет требует более "
    "низкой ставки, чем нужна для инфляции»; «порядок доступа», «режим», «коалиция», «рента» не используются;\n"
    "  • причины изменений — через потребности бюджета, внешние условия и приоритеты экономической "
    "политики, НЕ через намерения; прецеденты описываются как условие, которое они создают, а не как "
    "эпизод с участниками; оценок лиц и групп, типологии режима, карт силы и внутренних баллов на экране нет;\n"
    "  • каждая карточка, каждое измерение и каждая ветвь заканчиваются следствием из словаря Части 5 с "
    "адресатом и метрикой; событие без экономического адресата на экран не выходит (кадровые — только с "
    "известным изменением политики);\n"
    "  • пять разовых изъятий — не пять событий, а один режим: серию веди как отдельный объект с "
    "накопленным следствием; отметь шаг серии в карточке;\n"
    "  • 🔴 ЯВЛЕНИЕ «БЕЛЫХ СПИСКОВ» (владелец, 2026-09-18) обязательно оценивается как условие для бизнеса: "
    "доступ к инфраструктуре, рынку и льготам определяется включением в перечень, утверждаемый органом "
    "власти, — белые списки сайтов и сервисов при отключениях мобильного интернета, перечни "
    "системообразующих и допущенных к льготному кредиту и госзаказу, перечни для параллельного импорта, "
    "реестры для отсрочек и субсидий. Если за период есть события — карточка и, при повторяемости, серия; "
    "если событий нет — явление отражается в измерении «равенство условий и конкуренция» и в отраслевом "
    "разрезе (кто выигрывает по включению в перечень, а не по эффективности);\n"
    "  • ветви привязаны к сценариям геополитического экрана из задания: наиболее вероятная и наиболее "
    "неблагоприятная для бизнеса помечены раздельно; у каждой ветви — пороговое событие; изменение "
    "вероятности без события не допускается;\n"
    "  • статус события — факт; следствие — оценка Basis; граница видна в тексте («принято» — факт, "
    "«вероятно, приведёт» — оценка); ни одного внутреннего кода (M1, S3, И 5.2) и ни одного балла в текстах;\n"
    "  • рекомендаций «купить/продать» нет; компании называются как затронутые условием;\n"
    "  • ФАМИЛИИ не называть — ни должностных лиц, ни владельцев (решение владельца): «генеральный "
    "прокурор заявил», «основатель компании», «бенефициар»; уровень измерения (level) — 1–4 слова "
    "(«низкая», «высокое и растущее»), развёрнутое обоснование — в text; в geo_note и в подписях ветвей "
    "вероятности только словами, без «p≈0,4» — числа живут в поле p; в тексте для пользователя нет "
    "слов «контур», «госконтур», «экстракция», «фискальный голод».\n"
)


# ─────────────── блоки в задание институционалисту ───────────────
def prev_screen_block(prev: dict | None) -> str:
    """Прошлый экран кратко: id и заголовки карточек, серии, стрелки, ветви — чтобы агент сохранял
    ключи и обновлял, а не собирал заново (полный прошлый снимок в задание режется по длине)."""
    sc = (prev or {}).get("screen") if isinstance(prev, dict) else None
    if not isinstance(sc, dict) or not sc:
        return "ПРОШЛЫЙ ЭКРАН ОЦЕНКИ СИТУАЦИИ: нет — это первая сборка экрана, собери screen по спецификации целиком."
    out = [f"ПРОШЛЫЙ ЭКРАН ОЦЕНКИ СИТУАЦИИ (период {((sc.get('period') or {}).get('from'))}…"
           f"{((sc.get('period') or {}).get('to'))}; сохраняй id карточек и ключи серий, обновляй по событиям):"]
    for c in sc.get("cards") or []:
        if isinstance(c, dict):
            ser = (c.get("series") or {}).get("key") if isinstance(c.get("series"), dict) else None
            out.append(f"  • карточка {c.get('id')} — {c.get('date')} — {c.get('type')} — {str(c.get('title') or '')[:120]}"
                       + (f" [серия {ser}]" if ser else "") + (" [дайджест]" if c.get("digest") else ""))
    for s in sc.get("series") or []:
        if isinstance(s, dict):
            out.append(f"  • серия {s.get('key')} ({s.get('status')}) — {str(s.get('title') or '')[:120]}")
    dims = [f"{d.get('key')}: {d.get('arrow')}" for d in (sc.get("dimensions") or []) if isinstance(d, dict)]
    if dims:
        out.append("  • стрелки измерений за квартал: " + "; ".join(dims))
    brs = [f"{b.get('key')} {b.get('p')}" + (" [базовая]" if b.get("base") else "") + (" [неблагоприятная]" if b.get("worst") else "")
           for b in (sc.get("branches") or []) if isinstance(b, dict)]
    if brs:
        out.append("  • ветви: " + "; ".join(brs))
    if sc.get("vector"):
        out.append("  • прошлый вектор периода: " + str(sc["vector"])[:300])
    return "\n".join(out)


def geo_branches_block(db, peers: dict | None = None) -> str:
    """Ветви геополитика — в задание институционалисту (Часть 4.2: ветви условий производны от внешних).
    Черновик соседа сегодняшнего вечера, если есть, иначе опубликованная сводка."""
    payload = None
    if isinstance(peers, dict) and isinstance(peers.get("geo"), dict):
        payload = peers["geo"]
    if payload is None:
        try:
            from app.services import barometer_store
            row = barometer_store.current_row(db, "geo")
            payload = row.payload if row and row.payload else None
        except Exception:  # noqa: BLE001
            payload = None
    try:
        from app.services.geo_screen import branches_block
        txt = branches_block(payload)
    except Exception:  # noqa: BLE001
        txt = "ВЕТВИ ГЕОПОЛИТИКА: недоступны — ветви условий привяжи к типовым сценариям словами и пометь в data_flags."
    return txt + "\n(Привяжи каждую ветвь условий для бизнеса к одной из этих ветвей: поле geo_branch = её ключ.)"


# ─────────────── гейт ───────────────
def _d(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _norm_title(t) -> str:
    return re.sub(r"[^а-яa-z0-9]+", " ", str(t or "").lower()).strip()


def _merge_cards(fresh_cards: list, prev_cards: list, as_of: date, notes: list[str]) -> list[dict]:
    """Накопление (Часть 7.2): свежие карточки по id перекрывают прошлые; прошлые, которые агент не
    вернул, остаются до квартала. Одинаковые по дате и заголовку — одна карточка."""
    out: dict[str, dict] = {}
    seen_titles: dict[tuple, str] = {}
    for c in fresh_cards:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "").strip()
        if not cid:
            cid = f"{c.get('date')}-{_norm_title(c.get('title'))[:40].replace(' ', '-')}"
            c["id"] = cid
            notes.append(f"screen.cards: карточка без id — присвоен «{cid}»")
        out[cid] = c
        seen_titles[(str(c.get("date"))[:10], _norm_title(c.get("title")))] = cid
    kept = 0
    cutoff = as_of - timedelta(days=QUARTER_DAYS)
    for c in prev_cards:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id") or "")
        if not cid or cid in out:
            continue
        if (str(c.get("date"))[:10], _norm_title(c.get("title"))) in seen_titles:
            continue
        d = _d(c.get("date"))
        if d is None or d < cutoff:
            continue
        out[cid] = c
        kept += 1
    if kept:
        notes.append(f"screen.cards: {kept} карточек прошлого снимка сохранены (накопление до квартала)")
    cards = list(out.values())
    cards.sort(key=lambda c: str(c.get("date") or ""), reverse=True)
    return cards


def _card_notes(c: dict, notes: list[str]) -> None:
    label = f"screen.cards[{c.get('id')}]"
    if _d(c.get("date")) is None:
        notes.append(f"{label}: дата не в формате YYYY-MM-DD")
    if c.get("type") not in CARD_TYPES:
        notes.append(f"{label}: тип «{c.get('type')}» не из списка ({', '.join(CARD_TYPES)})")
    if c.get("status") not in CARD_STATUSES:
        notes.append(f"{label}: статус «{c.get('status')}» не из списка ({', '.join(CARD_STATUSES)})")
    for f in ("title", "fact", "change", "who", "driver", "source"):
        if len(str(c.get(f) or "").strip()) < 8:
            notes.append(f"{label}: нет поля «{f}» (Часть 1.2)")
    m = c.get("means") if isinstance(c.get("means"), dict) else None
    if not m or not m.get("text"):
        notes.append(f"{label}: нет «что это значит» с метрикой и направлением")
    else:
        if m.get("scale") not in SCALES:
            notes.append(f"{label}.means.scale: «{m.get('scale')}» не из списка ({', '.join(SCALES)})")
        if m.get("horizon") not in HORIZONS:
            notes.append(f"{label}.means.horizon: не из списка ({', '.join(HORIZONS)})")
        if m.get("reversibility") not in REVERSIBILITY:
            notes.append(f"{label}.means.reversibility: не из списка ({', '.join(REVERSIBILITY)})")
    cons = c.get("consequences") if isinstance(c.get("consequences"), list) else []
    cons = [x for x in cons if isinstance(x, dict) and x.get("text")]
    c["consequences"] = cons[:3]
    if not cons:
        notes.append(f"{label}: нет осязаемого следствия — карточка без следствия на экран не выходит (Часть 0.3)")
    for x in cons:
        if x.get("kind") not in CONSEQUENCE_KINDS:
            notes.append(f"{label}: следствие вне словаря Части 5 (kind «{x.get('kind')}»)")
        t = str(x.get("text") or "")
        if _BARE_RISK_RX.search(t) and " для " not in f" {t.lower()} ":
            notes.append(f"{label}: следствие «{t[:60]}» — «риски выше» без адресата и метрики (Часть 5.3)")
    if _INTENT_RX.search(str(c.get("driver") or "")):
        notes.append(f"{label}.driver: причина через намерения — переформулировать как экономическую причину (Часть 0.5)")
    conf = c.get("confidence") if isinstance(c.get("confidence"), dict) else None
    if not conf or conf.get("level") not in ("высокая", "средняя", "низкая"):
        notes.append(f"{label}: уверенность не по шкале высокая/средняя/низкая")
    if not isinstance(c.get("series"), dict):
        c["series"] = {"key": None, "step": None}


def _mark_digest(cards: list[dict], as_of: date, notes: list[str]) -> None:
    month = [c for c in cards if (_d(c.get("date")) or date.min) >= as_of - timedelta(days=MONTH_DAYS)]
    for c in cards:
        if c not in month:
            c["digest"] = False
    flagged = [c for c in month if c.get("digest")]

    def rank(c):
        m = c.get("means") if isinstance(c.get("means"), dict) else {}
        return (_SCALE_RANK.get(m.get("scale"), -1), str(c.get("date") or ""))

    if len(flagged) < 3 and month:
        for c in sorted(month, key=rank, reverse=True)[:max(3, len(flagged))]:
            c["digest"] = True
        notes.append("screen.digest: меньше трёх карточек отмечено — дополнено кодом по классу масштаба")
    elif len(flagged) > 5:
        keep = set(id(c) for c in sorted(flagged, key=rank, reverse=True)[:5])
        for c in flagged:
            if id(c) not in keep:
                c["digest"] = False
        notes.append("screen.digest: больше пяти карточек отмечено — оставлены пять с наибольшим масштабом")


def _normalize_p(branches: list[dict], notes: list[str]) -> None:
    try:
        vals = [(b, float(b.get("p"))) for b in branches if b.get("p") is not None]
    except (TypeError, ValueError):
        notes.append("screen.branches: нечисловые вероятности — оставлены как есть")
        return
    total = sum(v for _, v in vals)
    if total > 0 and abs(total - 1.0) > 0.005:
        for b, v in vals:
            b["p"] = round(v / total, 3)
        notes.append(f"screen.branches: сумма вероятностей {total:.3f} → нормализована")


def inst_screen_gate(fresh: dict, prev: dict | None) -> list[str]:
    """Каркас экрана держит код. Отсутствие поля целиком — перенос с прошлой версии с пометкой
    (снимок без экрана хуже, чем с ним, но лучше, чем никакой)."""
    notes: list[str] = []
    screen = fresh.get("screen")
    prev_screen = (prev or {}).get("screen") if isinstance(prev, dict) else None
    if not isinstance(screen, dict) or not screen:
        if isinstance(prev_screen, dict) and prev_screen:
            fresh["screen"] = json.loads(json.dumps(prev_screen, ensure_ascii=False))
            fresh["screen"]["carried_over"] = True
            notes.append("screen: не вернулся — перенесён с прошлой версии целиком")
        else:
            notes.append("screen: отсутствует — экран «Оценка ситуации» условий для бизнеса не собран (спецификация владельца)")
        return notes
    screen.pop("carried_over", None)
    as_of = _d(fresh.get("as_of")) or date.today()
    prev_screen = prev_screen if isinstance(prev_screen, dict) else {}

    # период
    per = screen.get("period") if isinstance(screen.get("period"), dict) else {}
    if _d(per.get("to")) is None or _d(per.get("from")) is None:
        screen["period"] = {"from": (as_of - timedelta(days=MONTH_DAYS)).isoformat(), "to": as_of.isoformat()}
        notes.append("screen.period: не задан или не по формату — выставлен код (месяц до as_of)")

    # вектор
    if len(str(screen.get("vector") or "").strip()) < 40:
        if prev_screen.get("vector"):
            screen["vector"] = prev_screen["vector"]
            notes.append("screen.vector: пуст — перенесён прошлый вектор периода")
        else:
            notes.append("screen.vector: вектор периода отсутствует (Часть 2.3)")

    # карточки — накопление и обязательные поля
    fresh_cards = screen.get("cards") if isinstance(screen.get("cards"), list) else []
    prev_cards = prev_screen.get("cards") if isinstance(prev_screen.get("cards"), list) else []
    cards = _merge_cards(fresh_cards, prev_cards, as_of, notes)
    if not cards:
        notes.append("screen.cards: ни одной карточки — блок «Изменения условий для бизнеса» пуст")
    for c in fresh_cards:
        if isinstance(c, dict):
            _card_notes(c, notes)
    screen["cards"] = cards
    _mark_digest(cards, as_of, notes)
    card_ids = {str(c.get("id")) for c in cards}

    # серии
    series = [s for s in (screen.get("series") or []) if isinstance(s, dict)]
    prev_series = {s.get("key"): s for s in (prev_screen.get("series") or []) if isinstance(s, dict)}
    have_keys = {s.get("key") for s in series}
    for k, s in prev_series.items():
        if k not in have_keys and s.get("status") == "активна":
            s2 = dict(s); s2["carried_over"] = True
            series.append(s2)
            notes.append(f"screen.series[{k}]: активная серия не вернулась — перенесена с прошлой версии")
    for s in series:
        lbl = f"screen.series[{s.get('key')}]"
        if len(s.get("events") or []) < 2:
            notes.append(f"{lbl}: меньше двух событий — серия из одного события не серия (Часть 1.3)")
        if len(str(s.get("accumulated") or "")) < 20:
            notes.append(f"{lbl}: нет накопленного следствия (Часть 1.3)")
        if s.get("status") not in SERIES_STATUSES:
            s["status"] = "активна"
        s["p_continue_words"] = p_words(s.get("p_continue"))
        if s.get("p_continue") is not None and s["p_continue_words"] is None:
            notes.append(f"{lbl}: вероятность продолжения не число")
    screen["series"] = series
    series_keys = {s.get("key") for s in series}
    for c in cards:
        sk = (c.get("series") or {}).get("key") if isinstance(c.get("series"), dict) else None
        if sk and sk not in series_keys:
            notes.append(f"screen.cards[{c.get('id')}]: ссылается на серию «{sk}», которой нет в screen.series")

    # измерения — ровно шесть
    dims_in = {d.get("key"): d for d in (screen.get("dimensions") or []) if isinstance(d, dict)}
    prev_dims = {d.get("key"): d for d in (prev_screen.get("dimensions") or []) if isinstance(d, dict)}
    dims_out = []
    for key, title, sub in DIMENSIONS:
        d = dims_in.get(key)
        if d is None and key in prev_dims:
            d = dict(prev_dims[key]); d["carried_over"] = True
            notes.append(f"screen.dimensions[{key}]: измерение не вернулось — перенесено с прошлой версии")
        if d is None:
            d = {"key": key, "level": None, "arrow": "без изменений", "text": None, "consequence": None,
                 "cards": [], "data_flag": "нет оценки в этом прогоне"}
            notes.append(f"screen.dimensions[{key}]: измерения нет ни сейчас, ни раньше — пустая заготовка")
        d["key"] = key; d["title"] = title; d["subtitle"] = sub
        if d.get("arrow") not in ARROWS:
            notes.append(f"screen.dimensions[{key}].arrow: «{d.get('arrow')}» не из списка ({', '.join(ARROWS)})")
            d["arrow"] = "смешанно"
        if len(str(d.get("level") or "")) > _LEVEL_MAX:
            notes.append(f"screen.dimensions[{key}].level: уровень длиннее {_LEVEL_MAX} знаков — 1–4 слова, обоснование в text")
        if not d.get("consequence"):
            notes.append(f"screen.dimensions[{key}]: нет предложения об осязаемом следствии (Часть 3.2)")
        ids = [x for x in (d.get("cards") or []) if isinstance(x, str)]
        missing = [x for x in ids if x not in card_ids]
        if missing:
            notes.append(f"screen.dimensions[{key}]: ссылки на несуществующие карточки {missing[:3]}")
        d["cards"] = [x for x in ids if x in card_ids]
        if not d["cards"] and not d.get("carried_over") and not d.get("data_flag"):
            notes.append(f"screen.dimensions[{key}]: стрелка не раскрывается в карточки — оценка как мнение, а не как сумма событий (Часть 8)")
        dims_out.append(d)
    extra = [k for k in dims_in if k not in DIMENSION_KEYS]
    if extra:
        notes.append(f"screen.dimensions: лишние измерения {extra[:3]} отброшены — их ровно шесть")
    screen["dimensions"] = dims_out

    # экономика, отрасли, мишень
    econ = screen.get("economy")
    if isinstance(econ, str):
        econ = [x.strip() for x in re.split(r"(?<=[.!?])\s+", econ) if x.strip()]
        screen["economy"] = econ
    if not isinstance(econ, list) or len(econ) < 3:
        notes.append("screen.economy: меньше трёх предложений о том, что это значит для экономики (Часть 3.3)")
    secs = [s for s in (screen.get("sectors") or []) if isinstance(s, dict)]
    if len(secs) < 3:
        notes.append("screen.sectors: меньше трёх строк отраслевого разреза (Часть 3.4)")
    for s in secs:
        if s.get("direction") not in SECTOR_DIRECTIONS:
            notes.append(f"screen.sectors[{s.get('who')}]: направление не из списка ({', '.join(SECTOR_DIRECTIONS)})")
        if not s.get("metric"):
            notes.append(f"screen.sectors[{s.get('who')}]: отраслевой разрез без метрики (Часть 8)")
    screen["sectors"] = secs
    tt = [t for t in (screen.get("tax_target") or []) if isinstance(t, dict) and t.get("feature")]
    if len(tt) < 3:
        notes.append("screen.tax_target: меньше трёх признаков налоговой мишени (Часть 3.4)")
    screen["tax_target"] = tt

    # направление на год
    dir_in = {d.get("key"): d for d in (screen.get("direction") or []) if isinstance(d, dict)}
    if set(dir_in) != set(DIMENSION_KEYS):
        notes.append("screen.direction: направление на год не по всем шести измерениям (Часть 4.1)")
    screen["direction"] = [dict(dir_in[k], title=t) for k, t, _ in DIMENSIONS if k in dir_in]

    # ветви
    branches = [b for b in (screen.get("branches") or []) if isinstance(b, dict)]
    if len(branches) < 3:
        if isinstance(prev_screen.get("branches"), list) and len(prev_screen["branches"]) >= 3:
            branches = json.loads(json.dumps(prev_screen["branches"], ensure_ascii=False))
            for b in branches:
                b["carried_over"] = True
            notes.append("screen.branches: меньше трёх ветвей — перенесены с прошлой версии")
        else:
            notes.append("screen.branches: меньше трёх ветвей (Часть 4.2)")
    if branches:
        _normalize_p(branches, notes)
        bases = [b for b in branches if b.get("base")]
        if len(bases) != 1:
            for b in branches:
                b["base"] = False
            try:
                max(branches, key=lambda b: float(b.get("p") or 0))["base"] = True
                notes.append("screen.branches: наиболее вероятная ветвь помечена кодом по максимальной вероятности")
            except (TypeError, ValueError):
                notes.append("screen.branches: наиболее вероятная ветвь не определена")
        worsts = [b for b in branches if b.get("worst")]
        if len(worsts) != 1 or worsts[0].get("base"):
            notes.append("screen.branches: наиболее неблагоприятная для бизнеса ветвь не помечена ровно одна и отдельно от наиболее вероятной (Часть 4.3)")
        for b in branches:
            lbl = f"screen.branches[{b.get('key')}]"
            if len(str(b.get("how_we_get_there") or "")) < 15:
                notes.append(f"{lbl}: нет порогового события перехода — ветвь без него не допускается (Часть 4.3)")
            if not b.get("geo_branch") and not b.get("geo_note"):
                notes.append(f"{lbl}: ветвь не привязана к сценарию геополитического экрана (Часть 4.2)")
            if _PROB_NUM_RX.search(str(b.get("geo_note") or "") + " " + str(b.get("label") or "")):
                notes.append(f"{lbl}: вероятность числом в тексте для пользователя — только словами (Часть 4.3)")
            for f in ("what", "who", "means"):
                if not b.get(f):
                    notes.append(f"{lbl}: ветвь не раскрыта — нет «{f}»")
            if not b.get("consequences"):
                notes.append(f"{lbl}: нет осязаемых следствий")
            b["p_words"] = p_words(b.get("p"))
        branches.sort(key=lambda b: float(b.get("p") or 0), reverse=True)
    screen["branches"] = branches
    if len([t for t in (screen.get("thresholds") or []) if t]) < 2:
        notes.append("screen.thresholds: меньше двух пороговых событий")

    # белые списки (владелец, 2026-09-18)
    if not _WHITELIST_RX.search(_values_text(screen)):
        notes.append("screen: явление «белых списков» (доступ по перечням, утверждаемым государством) не отражено "
                     "ни карточкой, ни в измерении «равенство условий», ни в отраслевом разрезе — требование владельца")

    # язык
    notes += term_notes({k: v for k, v in screen.items() if k not in ("period",)}, "screen")
    return notes


# ─────────────── сборка витрины ───────────────
def _row_date(row) -> str | None:
    if row is None:
        return None
    p = row.payload or {}
    return p.get("as_of") or (row.created_at.date().isoformat() if getattr(row, "created_at", None) else None)


def _period_of(card: dict, as_of: date) -> str:
    d = _d(card.get("date"))
    if d is None:
        return "older"
    if d >= as_of - timedelta(days=MONTH_DAYS):
        return "month"
    if d >= as_of - timedelta(days=QUARTER_DAYS):
        return "quarter"
    return "older"


def assemble(db) -> dict:
    """Витрина экрана: из опубликованного снимка институционалиста (поле screen). Даты — у экрана
    своя (снимок), у ветвей — дата сводки геополитика, к которой они привязаны."""
    from app.services import barometer_store
    row = barometer_store.current_row(db, "inst_state")
    payload = (row.payload or {}) if row else {}
    sc = payload.get("screen") if isinstance(payload.get("screen"), dict) else None
    if not sc:
        return {"available": False,
                "note": "Экран по спецификации ещё не собран: ждём вечернюю сборку с полем screen у институционалиста."}
    sc = json.loads(json.dumps(sc, ensure_ascii=False))
    as_of = _d(payload.get("as_of")) or _d(_row_date(row)) or date.today()
    cards = [c for c in (sc.get("cards") or []) if isinstance(c, dict)]
    for c in cards:
        c["period"] = _period_of(c, as_of)
    cards.sort(key=lambda c: str(c.get("date") or ""), reverse=True)
    by_id = {str(c.get("id")): c for c in cards}

    def rank(c):
        m = c.get("means") if isinstance(c.get("means"), dict) else {}
        return (_SCALE_RANK.get(m.get("scale"), -1), str(c.get("date") or ""))

    digest = sorted([c for c in cards if c.get("digest") and c["period"] == "month"], key=rank, reverse=True)[:5]
    series = [s for s in (sc.get("series") or []) if isinstance(s, dict)]
    for s in series:
        s.setdefault("p_continue_words", p_words(s.get("p_continue")))
        s["cards"] = [{"id": c.get("id"), "date": c.get("date"), "title": c.get("title")}
                      for c in cards if isinstance(c.get("series"), dict) and c["series"].get("key") == s.get("key")]
    dims = []
    for d in (sc.get("dimensions") or []):
        if not isinstance(d, dict):
            continue
        d["cards"] = [{"id": i, "date": by_id[i].get("date"), "title": by_id[i].get("title")}
                      for i in (d.get("cards") or []) if isinstance(i, str) and i in by_id]
        dims.append(d)
    branches = [b for b in (sc.get("branches") or []) if isinstance(b, dict)]
    for b in branches:
        b.setdefault("p_words", p_words(b.get("p")))
    branches.sort(key=lambda b: float(b.get("p") or 0), reverse=True)
    geo_row = None
    try:
        geo_row = barometer_store.current_row(db, "geo")
    except Exception:  # noqa: BLE001
        geo_row = None
    types = sorted({str(c.get("type")) for c in cards if c.get("type")}, key=lambda t: CARD_TYPES.index(t) if t in CARD_TYPES else 99)
    return {
        "available": True,
        "as_of": as_of.isoformat(),
        "dates": {"inst": _row_date(row), "geo": _row_date(geo_row)},
        "period": sc.get("period"),
        "vector": sc.get("vector"),
        "digest": digest,
        "cards": cards,
        "card_types": types,
        "counts": {"month": sum(1 for c in cards if c["period"] == "month"),
                   "quarter": sum(1 for c in cards if c["period"] in ("month", "quarter")),
                   "series": sum(1 for s in series if s.get("status") != "закрыта")},
        "series": series,
        "dimensions": dims,
        "economy": sc.get("economy") if isinstance(sc.get("economy"), list) else [],
        "sectors": sc.get("sectors") or [],
        "tax_target": sc.get("tax_target") or [],
        "direction": sc.get("direction") or [],
        "branches": branches,
        "thresholds": sc.get("thresholds") or [],
        "carried_over": bool(sc.get("carried_over")),
        "labels": {"consequence_kinds": CONSEQUENCE_KINDS, "dimensions": {k: t for k, t, _ in DIMENSIONS}},
    }


# ─────────────── карточка для полки: спецификация как документ ───────────────
def shelf_when_to_use() -> str:
    return ("Когда собираешь или проверяешь экран «Оценка ситуации» раздела «Институциональная среда»: "
            "что выводится пользователю об изменениях условий для бизнеса — карточка изменения и "
            "серии (Часть 1), три блока экрана (Части 2–4), словарь осязаемых следствий (Часть 5), "
            "язык и границы (Часть 6), чек-лист ошибок вывода (Часть 8), порядок сборки (Приложение). "
            "Институционалисту — для поля screen целиком; экономисту — для проверки адресата, метрики "
            "и масштаба (Части 0.2, 3.3–3.4); проверяющему — Части 6 и 8.")


def last_modified() -> str | None:
    try:
        return datetime.fromtimestamp(os.path.getmtime(SPEC_PATH)).isoformat(timespec="minutes")
    except OSError:
        return None
