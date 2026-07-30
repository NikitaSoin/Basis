"""Ежедневный дайджест отдельных статей (Обозреватель): Рыбарь / re:russia /
The Economist и др. источники из config/geo_sources.json.

В отличие от geopolitics.py (слитый синтез по региону), здесь каждая статья
становится отдельной карточкой: подробный пересказ (СВОИМИ СЛОВАМИ — не
дословный, но по существу, а не куцая строка) + тезисы + «зачем это
инвестору». Один LLM-вызов на батч решает сразу три вещи: публиковать ли,
куда (region svo|middle_east|atr — геополитическое событие с экономической
проекцией, или institutions — институциональная среда СТРОГО с экономическим
выводом, без пересказа аппаратной/подковёрной борьбы) и как пересказать
(на русском языке, нейтрально, эвфемизмы вместо острых формулировок).

source_url хранится в БД только для дедупа. source_key — метка источника,
временно ПОКАЗЫВАЕТСЯ на фронте (обкатка пайплайна, владелец явно попросил
прозрачность), в отличие от geopolitics.py."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.models.geo_digest import GeoDigestArticle, GEO_DIGEST_TARGETS
from app.services.geopolitics import load_config

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
         "Accept-Language": "ru-RU,ru;q=0.9"}
_MAX_PER_RUN = 60   # потолок новых статей за прогон (контроль стоимости LLM)
_MAX_AGE_DAYS = 14  # архивные RSS (напр. Economist отдаёт ~300 старых записей на
                    # раздел) — не тащим глубокий архив, только недавнее
_BATCH = 3          # было 6 (до этого 12) — снова уменьшено: настоящий потолок был
                    # не max_tokens, а LLM_TIMEOUT (дефолт 60с, llm.py._timeout) —
                    # генерация подробного пересказа (4-7 предложений + тезисы) на
                    # 6 статей стабильно не укладывалась в 60с → LLMError после
                    # ретраев → ВЕСЬ батч терялся молча (see except LLMError ниже).
                    # Подтверждено на бою: 3 подряд прогона trigger-geo-digest дали
                    # discovered=25, saved=0 — идентично, значит один и тот же батч
                    # падал одинаково, не разовая сетевая тряска.
_KEEP_DAYS = 90     # сколько дней держим карточку-статью в дайджесте (владелец,
                    # 2026-07-22: статьи-аналитика ценны дольше новостей → 90 дней;
                    # плюс дольше держим source_url в дедуп-наборе, статьи не всплывают
                    # повторно). Постоянная память — всё равно в chronicle.
_TEXT_CHARS = 3500  # сколько символов исходника отдаём модели на статью (было 500 —
                    # с куцым excerpt пересказ и получался куцым)

SOURCE_LABELS = {
    "rybar": "Рыбарь", "rybar_middle_east": "Рыбарь", "rybar_atr": "Рыбарь",
    "globalaffairs": "Global Affairs", "carnegie": "Carnegie",
    "rerussia": "re: Russia",
    "economist_europe": "The Economist", "economist_mea": "The Economist",
    "economist_china": "The Economist", "economist_finance": "The Economist",
    "isw": "ISW",
    "tg_carnegie": "Carnegie Politika", "tg_baunov": "Баунов (Carnegie)", "tg_agabuev": "Габуев (Carnegie)",
    "tg_markettwits": "MarketTwits",
}


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def _parse_date(raw: str | None) -> date | None:
    """Дата ИЗ МЕТАДАННЫХ статьи (RSS pubDate / wp_json date) — не из URL-эвристик.
    При невозможности определить — None (статья не публикуется, не выдумываем дату)."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# Egress-релей через Cloudflare Worker для источников, которые Timeweb режет на уровне
# TLS/SNI (TCP проходит, TLS-хендшейк виснет по таймауту — та же болезнь, что была у
# DeepSeek/FRED, см. память deepseek-fred-egress-blocked). re-russia.net подтверждён
# 2026-07-24 через /api/debug/trace: TCP ok, TLS FAIL с самого инстанса, при этом сайт
# живой (прямой запрос с внешнего узла отдаёт свежий RSS). RERUSSIA_BASE_URL — тот же
# паттерн host-swap реверс-прокси, что MINFIN_BASE_URL/DEEPSEEK_BASE_URL/FRED_BASE_URL;
# пусто/не задано — источник фетчится напрямую (безопасный no-op).
_RELAY_ENV_BY_SOURCE = {
    "rerussia": "RERUSSIA_BASE_URL",
}


def _relay_url(src: dict, url: str) -> str:
    env_name = _RELAY_ENV_BY_SOURCE.get(src.get("key"))
    relay = env_name and os.environ.get(env_name)
    if not relay:
        return url
    relay_parts = urlsplit(relay.rstrip("/"))
    parts = urlsplit(url)
    return urlunsplit((relay_parts.scheme, relay_parts.netloc, parts.path, parts.query, parts.fragment))


# ----------------------------- ПАРСЕР ИСТОЧНИКОВ (с URL для дедупа) -----------------------------
def _fetch_wp_json(src: dict) -> list[dict]:
    r = httpx.get(src["url"], params=src.get("params"), timeout=30, headers=_HTTP, follow_redirects=True)
    r.raise_for_status()
    out = []
    for p in r.json():
        link = p.get("link") or ""
        if not link:
            continue
        # content.rendered — полный текст поста (у Рыбаря ~2-3 тыс. символов),
        # excerpt.rendered — куцая выжимка WordPress (~150 симв.), от неё пересказ
        # получался куцым. Полный текст нужен модели для ПОДРОБНОГО (но переписанного
        # своими словами) пересказа, не для копирования.
        body = p.get("content", {}).get("rendered", "") or p.get("excerpt", {}).get("rendered", "")
        out.append({"title": _strip(p.get("title", {}).get("rendered", "")),
                    "text": _strip(body)[:_TEXT_CHARS],
                    "url": link, "date_raw": p.get("date") or "", "src": src["key"]})
    return out


def _fetch_rss(src: dict) -> list[dict]:
    r = httpx.get(_relay_url(src, src["url"]), timeout=30, headers=_HTTP, follow_redirects=True, verify=False)
    r.raise_for_status()
    out = []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return out
    for it in root.iter("item"):
        def t(tag):
            el = it.find(tag)
            return _strip(el.text) if el is not None and el.text else ""
        title, link = t("title"), t("link")
        if not title or not link:
            continue
        # У некоторых RSS (re:russia) <description> содержит ПОЛНЫЙ текст статьи, не
        # тизер — берём столько же, сколько у wp_json, чтобы пересказ был по существу.
        out.append({"title": title, "text": _strip(t("description"))[:_TEXT_CHARS],
                    "url": link, "date_raw": t("pubDate"), "src": src["key"]})
    return out


def _fetch_telegram(src: dict) -> list[dict]:
    """Публичный Телеграм-канал через веб-превью t.me/s/ (владелец, 2026-07-21).
    Только публичные каналы; закрытые/инвайт-only — нужен Client API (не здесь).
    src['channel'] — @username / username."""
    from app.services.agent_telegram import fetch_telegram_posts
    res = fetch_telegram_posts(src.get("channel") or src["key"], limit=src.get("limit", 15))
    if res.get("error"):
        raise RuntimeError(f"telegram {src.get('channel')}: {res['error']}")
    out = []
    for p in res.get("posts", []):
        text = (p.get("text") or "").strip()
        if len(text) < 30 or not p.get("url"):  # служебные/пустые посты пропускаем
            continue
        # заголовок — первая строка/предложение поста (для карточки дайджеста)
        first = re.split(r"[\n.!?]", text, 1)[0].strip()
        title = (first[:90] + "…") if len(first) > 90 else (first or res.get("title") or src["key"])
        out.append({"title": title, "text": text[:_TEXT_CHARS],
                    "url": p["url"], "date_raw": p.get("date") or "", "src": src["key"]})
    return out


def fetch_all(cfg: dict) -> tuple[list[dict], list[str]]:
    arts, blind = [], []
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        try:
            method = src["method"]
            got = (_fetch_wp_json(src) if method == "wp_json"
                   else _fetch_telegram(src) if method == "telegram"
                   else _fetch_rss(src))
            if src.get("no_pubdate"):
                # источник не публикует дату нигде (проверено вручную) — раз статья в
                # текущей ротации фида, она свежая; день неизвестен, ставим дату
                # обнаружения. НЕ путать с фиксом бага macro_analytics: там подставлялась
                # случайная дата для документа неизвестного возраста, здесь — честная
                # метка "видели сегодня" для заведомо свежей статьи.
                for a in got:
                    a["_no_pubdate"] = True
            if not got:
                blind.append(src["key"])
                logger.warning("GEO-дайджест-АЛЕРТ: источник %s вернул 0 статей", src["key"])
            arts.extend(got)
        except Exception as e:  # noqa: BLE001
            blind.append(src["key"])
            logger.warning("GEO-дайджест-АЛЕРТ: источник %s недоступен: %s", src["key"], type(e).__name__)
    return arts, blind


# ----------------------------- LLM: классификация + пересказ -----------------------------
_DIGEST_SYS = (
    "Ты готовишь ежедневный дайджест для инвестиционной платформы Basis из статей о "
    "геополитике и институциональной среде России. На входе — список статей (заголовок + "
    "полный текст) из разных СМИ, часть текстов на английском. Для КАЖДОЙ статьи реши: "
    "(1) стоит ли её публиковать, (2) в какой раздел, (3) как подробно и политкорректно "
    "пересказать НА РУССКОМ ЯЗЫКЕ — независимо от языка оригинала.\n\n"
    "РАЗДЕЛЫ (target):\n"
    "- \"svo\" / \"middle_east\" / \"atr\" — геополитическое СОБЫТИЕ ИЛИ военная/переговорная "
    "ДИНАМИКА конфликта в соответствующем регионе. ВАЖНО про svo конкретно: цель раздела — "
    "не оценка влияния на отдельный рынок/сектор, а отслеживание ТРАЕКТОРИИ конфликта: "
    "движется ли ситуация к условиям, приемлемым России, к условиям, приемлемым Украине, к "
    "патовой длительной войне, или условия обеих сторон меняются. САМА эта траектория — "
    "макроэкономически значимый сигнал (продолжение/завершение войны определяет бюджет, "
    "ДКП, санкционный режим, курс, весь рыночный фон), поэтому явная привязка к конкретному "
    "сектору/товару НЕ обязательна. Публикуй как svo/middle_east/atr: сводки о ходе боевых "
    "действий и territorial control (кто продвигается, где фронт стабилен/подвижен), удары "
    "по инфраструктуре (энергетика, НПЗ, логистика — даже без явного расчёта $-эффекта), "
    "переговорные треки и позиции сторон (что каждая сторона требует/готова уступить, кто "
    "укрепляет/ослабляет переговорную позицию), мобилизация и военные ресурсы сторон (что "
    "говорит о способности продолжать войну), санкционная и военная поддержка извне. НЕ "
    "публикуй: точечные тактические эпизоды без значения для общей траектории (один бой, "
    "локальная атака дрона без контекста), чистую пропаганду без проверяемого факта, "
    "дублирующие уже опубликованные сегодня события.\n"
    "- \"institutions\" — статья про ИНСТИТУЦИОНАЛЬНУЮ СРЕДУ (защита собственности, "
    "перераспределение активов, регуляторная/судебная практика, госполитика в экономике, "
    "элитная конкуренция) — НО ТОЛЬКО если есть чёткая экономическая проекция (что это "
    "значит для бизнеса/инвестора/рынка). ОТСЕИВАЙ статьи, которые сводятся к пересказу "
    "аппаратной/подковёрной борьбы БЕЗ экономического вывода — это не для инвестора.\n"
    "- \"macro\" — СТРОГО МАКРОЭКОНОМИКА: экономические ПОКАЗАТЕЛИ и оценка их движения. "
    "Это узкий раздел, не «всё про экономику вообще». Сюда и только сюда: инфляция, "
    "ключевая ставка и политика ЦБ/ФРС, ВВП и его компоненты, бюджет и дефицит, госдолг, "
    "курс валюты, платёжный/торговый баланс, занятость и зарплаты, денежная масса и "
    "кредитование, индексы промпроизводства/PMI/потребительской активности, а также "
    "прогнозы и разборы ИМЕННО ЭТИХ показателей. Признак macro — в центре статьи стоит "
    "ПОКАЗАТЕЛЬ (цифра по экономике страны/мира) и его динамика.\n"
    "- \"business\" — реальная экономика: компании, отрасли, рынки товаров, торговля, "
    "логистика. Сюда: корпоративные события (сделки M&A, IPO/SPO, смена собственника или "
    "менеджмента, контракты, инвестпроекты, дивиденды, реструктуризация, дефолт), "
    "операционные и финансовые результаты компаний, конкуренция на конкретном рынке, "
    "ОТРАСЛЕВЫЕ и ТОВАРНЫЕ сюжеты (сырьё и цены на него, экспортные/импортные ограничения "
    "и пошлины по конкретным товарам, логистика и грузопотоки, энергетика, транспорт), "
    "отраслевое регулирование.\n"
    "РАЗГРАНИЧЕНИЕ macro/business — по тому, ПОКАЗАТЕЛЬ ли в центре статьи:\n"
    "  • «Годовая инфляция выросла до 5,84%», «ЦБ сохранил ставку 14,25%», «ВВП вырос на "
    "0,9% г/г», «Курс рубля ослаб выше 80», «ФРС оставила ставку без изменений» → macro.\n"
    "  • «Ограничения на экспорт редкоземельных металлов», «Грузооборот портов падает "
    "третий год», «Цены на нефть волатильны», «Россия продлевает запрет экспорта бензина», "
    "«Прибыль Газпромнефти выросла на 12%», «Porsche сокращает штат» → business. Обрати "
    "внимание: сырьё, пошлины, порты, экспортные запреты — это BUSINESS, а не macro, даже "
    "когда речь про целую страну: субъект здесь товар/отрасль, а не макропоказатель.\n"
    "Если статья описывает конкретный товар, отрасль, компанию или торговое ограничение — "
    "business, даже если в тексте попутно упомянуты инфляция или ВВП. macro — только когда "
    "сам показатель и есть тема статьи.\n"
    "- null — не публиковать (нет связи с экономикой/рынком, чисто военная тактика без "
    "экономических последствий, вторично, слишком локально/малозначимо).\n"
    "ПЛАНКА ЗНАЧИМОСТИ ПО ИСТОЧНИКУ: у каждой статьи есть поле source. Для source=\"MarketTwits\" "
    "(агрегатор — десятки коротких заметок в день, в отличие от штучных содержательных материалов "
    "Carnegie/re:russia/Economist/ISW) планка значимости СУЩЕСТВЕННО ВЫШЕ — публикуй ТОЛЬКО крупные, "
    "самостоятельно значимые события (решение/сигнал ЦБ, крупный санкционный пакет, существенное "
    "движение на глобальных рынках, значимое корпоративное событие с ясным эффектом на сектор), а "
    "рутинные точечные апдейты (обычные ценовые тики нефти/валюты без контекста, мелкие "
    "процедурные новости, ежедневные повторяющиеся сводки по сырью) — null, даже если формально "
    "относятся к macro/svo/institutions. Для остальных источников (Carnegie/re:russia/Economist/"
    "ISW/Global Affairs/Рыбарь) действует обычная планка выше — они и так штучные и уже отобраны "
    "самим источником как значимые.\n\n"
    "ПРАВИЛА ПЕРЕСКАЗА (summary):\n"
    "1. Пиши СВОИМИ СЛОВАМИ, не переводом-калькой и не цитированием — перескажи суть так, "
    "будто объясняешь её инвестору, который не читал оригинал. НЕ копируй фразы/предложения "
    "из исходного текста дословно, даже частично — только пересказ своими словами по смыслу.\n"
    "2. ПОДРОБНО: 4-7 предложений, покрывающих все значимые тезисы статьи (не 1-2 строки) — "
    "как аналитическая выжимка, а не заголовок с подписью. Если в статье несколько отдельных "
    "содержательных линий — отрази каждую.\n"
    "3. key_takeaways — 2-4 отдельных тезиса списком (аналогично выжимкам ЦБ/ЦМАКП), каждый "
    "— самостоятельная мысль, а не дробление одного предложения.\n"
    "4. МАКСИМАЛЬНАЯ политкорректность: нейтральный фактологический язык, без оценок в "
    "чью-либо пользу. Острые формулировки заменяй эвфемизмами (нейтральное описание события "
    "вместо резких характеристик; «сообщается о...» вместо личных обвинений).\n"
    "5. Для target=\"institutions\": фокус СТРОГО на экономических последствиях — НЕ "
    "пересказывай подробности конфликта между конкретными людьми/группами; если в статье это "
    "главное содержание, выведи только экономический итог, без деталей интриги.\n"
    "6. investor_relevance — отдельно, 1-2 фразы: зачем инвестору это знать (на что обратить "
    "внимание, какой актив/сектор может быть затронут). Без рекомендаций «покупать/продавать».\n\n"
    "ДОПОЛНИТЕЛЬНО (только для target=\"svo\"/\"middle_east\"/\"atr\") — извлеки СТРУКТУРИРОВАННЫЕ "
    "события, если они ЯВНО и КОНКРЕТНО описаны в статье (не выдумывай, не притягивай — если "
    "неясно/абстрактно, просто не включай):\n"
    "- strike_events — КОНКРЕТНЫЙ удар/атака по КОНКРЕТНОЙ цели/локации (не общие фразы вида "
    "«обстрелы продолжаются» без места). Каждый: {\"location\": \"<название места/города, как в "
    "тексте>\", \"target_type\": \"<что поражено — НПЗ/склад/аэродром/энергообъект/др., если "
    "указано, иначе null>\", \"significance\": \"major\"|\"minor\" (major — стратегический объект: "
    "НПЗ, крупный склад/арсенал, военная база, энергоинфраструктура, порт; minor — точечный/"
    "локальный, без явного стратегического значения), \"label\": \"<короткая подпись на русском "
    "3-8 слов>\"}. Удары ВГЛУБЬ ТЫЛА любой из сторон (НПЗ, склады, аэродромы, энергетика, "
    "порты, ВПК — хоть по России, хоть по Украине) — ВСЕГДА включай, даже из MarketTwits: "
    "к состоявшимся ударам планка значимости источника не применяется.\n"
    "- territorial_claims (ТОЛЬКО target=\"svo\") — КОНКРЕТНЫЙ насел. пункт, про который статья "
    "явно говорит, что он взят/освобождён/оспаривается ПРЯМО СЕЙЧАС (не общие фразы про "
    "«продвижение», не абстрактные направления). Каждый: {\"settlement\": \"<название>\", "
    "\"oblast\": \"<область, если понятно из контекста, иначе null>\", \"status\": "
    "\"ru_control\"|\"contested\" (ru_control — статья утверждает решительное взятие РФ; "
    "contested — бои идут / заявлено, но источник сам не подтверждает решительно), \"note\": "
    "\"<1 короткое предложение сути на русском>\"}.\n"
    "Если в статье нет ни одного такого события — не включай ключи strike_events/"
    "territorial_claims вовсе (не пустые списки, просто опусти ключ).\n\n"
    'Верни JSON {"items": [{"i": <индекс>, "target": "svo"|"middle_east"|"atr"|"institutions"'
    '|"macro"|"business"|null, "title": "<заголовок на русском>", "summary": "<подробный пересказ 4-7 '
    'предложений на русском>", "key_takeaways": ["<тезис 1>", "<тезис 2>", ...], '
    '"investor_relevance": "<1-2 фразы>", "strike_events": [...], "territorial_claims": [...]}]}. '
    "Для target=null остальные поля можно опустить. "
    "Верни ровно один элемент items на каждую входную статью."
)


def _digest_batch(articles: list[dict]) -> list[dict]:
    from app.services.llm import complete, LLMError
    payload = {"articles": [{"i": i, "source": SOURCE_LABELS.get(a["src"], a["src"]),
                             "title": a["title"], "text": a["text"]}
                            for i, a in enumerate(articles)]}
    try:
        res = complete(_DIGEST_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=16000, temperature=0.3)
        return res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("GEO-дайджест: LLM недоступен (%s) — батч пропущен", e)
        return []


# ----------------------------- Гео-события (удары / territorial claims) -----------------------------
# Retention удара на карте — владелец, 2026-07-24: «малозначимые удары через
# какое-то время удалять, у значимых retention в разы больше».
_STRIKE_RETENTION_DAYS = {"major": 60, "minor": 14}
_geocode_cache: dict[str, tuple[float, float] | None] = {}


def _geocode_place(name: str) -> tuple[float, float] | None:
    """Лёгкий геокодинг через Wikipedia API (тот же паттерн, что
    scripts/geo_svo_wikipedia_dates.py использовал офлайн) — best-effort, не
    блокирует пайплайн при неудаче. Кэш на время процесса — карта Обозревателя
    упоминает одни и те же города многократно за прогон."""
    if not name:
        return None
    if name in _geocode_cache:
        return _geocode_cache[name]
    result = None
    try:
        r = httpx.get("https://ru.wikipedia.org/w/api.php", params={
            "action": "query", "titles": name, "prop": "coordinates",
            "format": "json", "redirects": 1,
        }, timeout=10, headers={"User-Agent": "BasisPlatform/1.0 (https://inbasis.ru) geo_digest"})
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            co = page.get("coordinates")
            if co:
                result = (co[0]["lat"], co[0]["lon"])
                break
    except Exception as e:  # noqa: BLE001
        logger.debug("geo_digest: геокодинг '%s' не удался: %s", name, type(e).__name__)
    _geocode_cache[name] = result
    return result


def _persist_strike_events(db: Session, theater: str, events: list, event_date, source_key: str | None,
                            source_url: str | None) -> int:
    """Сохранение ударов с ДЕДУПЛИКАЦИЕЙ: одна и та же атака приходит из
    нескольких источников (Рыбарь + РБК + Интерфакс + MarketTwits) и из
    повторных прогонов — совпадение по координатам (±0.05° ≈ 5 км) и дате
    (±2 дня) считается тем же событием и не плодит дубль-маркеры."""
    from app.models.geo import GeoStrikeEvent
    now = datetime.now(timezone.utc)
    existing = [(e.lat, e.lon, e.event_date, (e.location_name or "").lower())
                for e in db.query(GeoStrikeEvent)
                .filter(GeoStrikeEvent.theater == theater, GeoStrikeEvent.expires_at >= now).all()]

    def _is_dup(lat, lon, name, ev_date):
        for elat, elon, edate, ename in existing:
            same_date = (edate is None or ev_date is None
                         or abs((edate - ev_date).days) <= 2)
            if not same_date:
                continue
            if lat is not None and elat is not None:
                if abs(elat - lat) < 0.05 and abs(elon - lon) < 0.05:
                    return True
            elif name and ename and name == ename:
                return True
        return False

    saved = 0
    for ev in events:
        if not isinstance(ev, dict) or not ev.get("location"):
            continue
        significance = ev.get("significance") if ev.get("significance") in ("major", "minor") else "minor"
        coords = _geocode_place(ev["location"])
        _lat, _lon = (coords if coords else (None, None))
        if _is_dup(_lat, _lon, ev["location"].lower(), event_date):
            continue
        existing.append((_lat, _lon, event_date, ev["location"].lower()))
        row = GeoStrikeEvent(
            theater=theater, location_name=ev["location"][:200],
            lat=coords[0] if coords else None, lon=coords[1] if coords else None,
            target_type=(ev.get("target_type") or None), significance=significance,
            label=(ev.get("label") or ev["location"])[:300], note=None,
            event_date=event_date, source_key=source_key, source_url=source_url,
            expires_at=datetime.now(timezone.utc) + timedelta(days=_STRIKE_RETENTION_DAYS[significance]),
        )
        db.add(row)
        try:
            db.commit()
            saved += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning("geo_digest: удар не сохранён (%s): %s", ev.get("location"), type(e).__name__)
    return saved


def _persist_territorial_claims(db: Session, claims: list, claimed_date, source_key: str | None,
                                 source_url: str | None) -> int:
    from app.models.geo import GeoTerritorialClaim
    saved = 0
    for cl in claims:
        if not isinstance(cl, dict) or not cl.get("settlement") or cl.get("status") not in ("ru_control", "contested"):
            continue
        settlement = cl["settlement"][:200]
        oblast = (cl.get("oblast") or None)
        row = (db.query(GeoTerritorialClaim)
               .filter_by(settlement=settlement, oblast=oblast).first())
        coords = _geocode_place(settlement)
        if row is None:
            row = GeoTerritorialClaim(settlement=settlement, oblast=oblast)
            db.add(row)
        row.status = cl["status"]
        row.note = (cl.get("note") or None)
        row.claimed_date = claimed_date
        row.source_key = source_key
        row.source_url = source_url
        if coords:
            row.lat, row.lon = coords
        try:
            db.commit()
            saved += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning("geo_digest: territorial_claim не сохранён (%s): %s", settlement, type(e).__name__)
    return saved


def cleanup_expired_strikes(db: Session) -> int:
    """Ретеншен — вызывать периодически (тот же крон, что refresh()).
    Малозначимые удары исчезают с карты через _STRIKE_RETENTION_DAYS['minor']
    дней, значимые — через ['major'] (владелец: «в разы дольше»)."""
    from app.models.geo import GeoStrikeEvent
    now = datetime.now(timezone.utc)
    removed = (db.query(GeoStrikeEvent).filter(GeoStrikeEvent.expires_at < now)
               .delete(synchronize_session=False))
    db.commit()
    if removed:
        logger.info("geo_digest: удалено %d просроченных ударов с карты", removed)
    return removed


_BACKFILL_SYS = (
    "Тебе дан список уже готовых пересказов статей геополитического дайджеста "
    "(заголовок+summary, СВОИМИ СЛОВАМИ, уже опубликованы). Извлеки из каждого "
    "СТРУКТУРИРОВАННЫЕ события, ТОЛЬКО если они ЯВНО и КОНКРЕТНО описаны в "
    "тексте (не выдумывай, не притягивай — если неясно/абстрактно, просто не "
    "включай ключ вовсе):\n"
    "- strike_events — КОНКРЕТНЫЙ удар/атака по КОНКРЕТНОЙ цели/локации (не "
    "общие фразы вида «обстрелы продолжаются» без места). Каждый: "
    "{\"location\": \"<название места/города, как в тексте>\", \"target_type\": "
    "\"<что поражено — НПЗ/склад/аэродром/энергообъект/логистический центр/др., "
    "если указано, иначе null>\", \"significance\": \"major\"|\"minor\" (major — "
    "стратегический объект или крупный ущерб/жертвы, minor — точечный/локальный), "
    "\"label\": \"<короткая подпись на русском 3-8 слов>\"}.\n"
    "- territorial_claims (ТОЛЬКО у статей с target=\"svo\") — КОНКРЕТНЫЙ насел. "
    "пункт, взятый/освобождённый/оспариваемый ПРЯМО СЕЙЧАС (не общие фразы про "
    "«продвижение»). Каждый: {\"settlement\": \"<название>\", \"oblast\": "
    "\"<область, если понятно, иначе null>\", \"status\": \"ru_control\"|"
    "\"contested\", \"note\": \"<1 короткое предложение на русском>\"}.\n"
    'Верни JSON {"items": [{"i": <индекс>, "strike_events": [...], '
    '"territorial_claims": [...]}]}, включай только индексы, где реально есть '
    "хотя бы одно событие — для остальных просто не создавай элемент items."
)


def backfill_strike_events(db: Session, days: int = 7, limit: int = 80) -> dict:
    """Догоняющий прогон по УЖЕ сохранённым статьям (owner, 2026-07-25: реальный
    пример — удары по складам Wildberries 18-24.07.2026 — статьи Рыбаря/
    MarketTwits об этом УЖЕ есть в geo_digest_articles, но strike_events для них
    остались пустыми, т.к. основной пайплайн извлекает структуру ТОЛЬКО у
    заново обнаруженных статей (дедуп по source_url — уже известный URL второй
    раз не проходит через LLM). Разовый/периодический догон по хвосту последних
    `days` дней закрывает этот пробел, не трогая основной пайплайн refresh()."""
    from app.services.llm import complete, LLMError

    cutoff = date.today() - timedelta(days=days)
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(("svo", "middle_east", "atr")))
            .filter(GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc())
            .limit(limit).all())
    if not rows:
        return {"scanned": 0, "strikes_saved": 0, "claims_saved": 0}

    payload = {"articles": [{"i": i, "target": r.target, "title": r.title, "summary": r.summary}
                            for i, r in enumerate(rows)]}
    try:
        res = complete(_BACKFILL_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=8000, temperature=0.2)
        items = res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("geo_digest backfill: LLM недоступен (%s)", e)
        return {"scanned": len(rows), "strikes_saved": 0, "claims_saved": 0, "error": str(e)}

    strikes_saved = 0
    claims_saved = 0
    for it in items:
        idx = it.get("i")
        if not isinstance(idx, int) or not (0 <= idx < len(rows)):
            continue
        row = rows[idx]
        strikes = it.get("strike_events")
        if isinstance(strikes, list) and strikes:
            strikes_saved += _persist_strike_events(db, row.target, strikes, row.published_at,
                                                      row.source_key, row.source_url)
        if row.target == "svo":
            claims = it.get("territorial_claims")
            if isinstance(claims, list) and claims:
                claims_saved += _persist_territorial_claims(db, claims, row.published_at,
                                                              row.source_key, row.source_url)
    logger.info("geo_digest backfill: просмотрено %d статей, %d ударов, %d territorial_claims",
                len(rows), strikes_saved, claims_saved)
    return {"scanned": len(rows), "strikes_saved": strikes_saved, "claims_saved": claims_saved}


# ------------- Разделение macro → business на УЖЕ накопленных статьях -------------
_MACRO_SPLIT_SYS = (
    "Ты сортируешь уже опубликованные статьи инвестиционной платформы Basis по двум "
    "разделам. Раньше раздел был один («Макроэкономика»), и в него попадало всё подряд; "
    "теперь появился отдельный раздел «Бизнес», и накопленное надо разложить.\n\n"
    "ПРАВИЛО — по тому, что стоит В ЦЕНТРЕ статьи:\n"
    "- \"macro\" — СТРОГО экономические ПОКАЗАТЕЛИ и оценка их движения: инфляция, "
    "ключевая ставка и политика ЦБ/ФРС, ВВП, бюджет и дефицит, госдолг, курс валюты, "
    "платёжный/торговый баланс, занятость и зарплаты, денежная масса и кредитование, "
    "индексы промпроизводства/PMI/потребительской активности, прогнозы ИМЕННО ЭТИХ "
    "показателей. Макроэкономика — это узкий раздел про ЦИФРЫ по экономике, а НЕ «всё "
    "про экономику вообще».\n"
    "- \"business\" — реальная экономика: компании, отрасли, товарные рынки, торговля, "
    "логистика. Результаты и отчётность компаний, сделки, контракты, дивиденды, а также "
    "ОТРАСЛЕВЫЕ и ТОВАРНЫЕ сюжеты: сырьё и цены на него, экспортные/импортные "
    "ограничения и пошлины, порты и грузопотоки, энергетика, транспорт.\n\n"
    "Примеры macro: «Годовая инфляция выросла до 5,84%», «ЦБ сохранил ставку 14,25%», "
    "«ВВП вырос на 0,9% г/г», «Курс рубля ослаб выше 80», «ФРС оставила ставку», "
    "«Опережающие индикаторы указывают на спад экономики».\n"
    "Примеры business: «Прибыль Газпромнефти выросла на 12%», «Porsche сокращает штат», "
    "«Ограничения на экспорт редкоземельных металлов», «Грузооборот портов Эстонии "
    "падает третий год», «Цены на нефть остаются волатильными», «Россия продлевает "
    "запрет экспорта бензина», «Сбер сохранит дивиденды 50%».\n\n"
    "ВАЖНО: сырьё, пошлины, экспортные запреты, порты, логистика, отраслевые истории — "
    "это BUSINESS, даже когда речь про целую страну: субъект здесь товар или отрасль, а "
    "не макропоказатель. macro — только когда сам показатель и есть тема статьи. Если "
    "сомневаешься — business.\n\n"
    'Верни JSON {"items": [{"i": <индекс>, "target": "macro"|"business"}]} — ровно один '
    "элемент на каждую входную статью."
)


def split_macro_business(db: Session, limit: int = 200) -> dict:
    """Разовый догоняющий проход: разложить уже накопленные target="macro" статьи на
    macro/business (владелец, 2026-07-31: «часть статей в Макроэкономике вообще не
    макроэкономические, а бизнесовые»). До появления раздела "business" у
    классификатора не было другого адресата, поэтому корпоративные сюжеты
    (отчётность компаний, сделки, дивиденды) оседали в macro и разбавляли ленту про
    инфляцию/ставку/ВВП. Основной пайплайн refresh() новые статьи уже раскладывает
    правильно — этот проход закрывает ИСТОРИЮ, не трогая её.

    Идемпотентен: гоняет только по target="macro", повторный запуск просто
    подтвердит оставшиеся macro. Возвращает счётчики, ничего не удаляет."""
    from app.services.llm import complete, LLMError

    rows = (db.query(GeoDigestArticle).filter_by(target="macro")
            .order_by(GeoDigestArticle.published_at.desc().nullslast())
            .limit(limit).all())
    if not rows:
        return {"scanned": 0, "moved": 0}

    moved = 0
    # Батчами: весь хвост одним запросом упирается в лимит ответа (у каждой статьи
    # заголовок + выжимка) — тот же приём, что в refresh().
    BATCH = 40
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        payload = {"articles": [{"i": i, "title": r.title, "summary": (r.summary or "")[:400]}
                                for i, r in enumerate(chunk)]}
        try:
            res = complete(_MACRO_SPLIT_SYS, json.dumps(payload, ensure_ascii=False),
                           json_mode=True, max_tokens=4000, temperature=0.1)
            items = res.get("items", []) if isinstance(res, dict) else []
        except LLMError as e:
            logger.warning("split_macro_business: LLM недоступен (%s)", e)
            return {"scanned": len(rows), "moved": moved, "error": str(e)}
        for it in items:
            idx = it.get("i")
            if not isinstance(idx, int) or not (0 <= idx < len(chunk)):
                continue
            if it.get("target") == "business":
                chunk[idx].target = "business"
                moved += 1
        db.commit()

    logger.info("split_macro_business: просмотрено %d, переведено в business %d", len(rows), moved)
    return {"scanned": len(rows), "moved": moved}


# ----------------------- Удары из ОБЩЕЙ новостной ленты -----------------------
# Владелец (2026-07-26): «недавно новость была про Тюмень, что там что-то
# ударили — а на карте я этого не увидел». Разбор показал: удар по Тюменскому
# НПЗ был в ленте новостей (market_updates: РБК, Интерфакс — три заметки), но
# экстракция ударов слушала ТОЛЬКО источники гео-дайджеста (Рыбарь/Economist/
# ISW/MarketTwits) — общая лента в неё не попадала вовсе. Этот проход закрывает
# дыру: дешёвый префильтр по ключевым словам → один LLM-вызов на батч →
# геокодинг → _persist_strike_events (там дедуп, поэтому событие, пришедшее и
# из Рыбаря, и из РБК, не плодит дубль-маркеры).
_NEWS_STRIKE_KEYWORDS = ("бпла", "дрон", "удар", "атак", "ракет", "обстрел",
                          "взрыв", "прилет", "прилёт", "беспилотн", "бэк")
_NEWS_STRIKE_SYS = (
    "Тебе даны заголовки и выжимки новостей рыночной ленты. Найди среди них "
    "КОНКРЕТНЫЕ СОСТОЯВШИЕСЯ военные удары/атаки (БПЛА, ракеты, безэкипажные "
    "катера, диверсии) с КОНКРЕТНЫМ местом. НЕ включай: планы/угрозы/учения, "
    "перехваты без поражения цели, общие фразы без места, повторные новости о "
    "ликвидации последствий БЕЗ самого факта атаки в тексте — ВКЛЮЧАЙ, если "
    "факт атаки в тексте назван («пожар после атаки БПЛА» — это удар).\n"
    "theater: \"svo\" — конфликт России и Украины, удары по территории ЛЮБОЙ из "
    "сторон, включая глубокий тыл (НПЗ, склады, аэродромы, порты, энергетика — "
    "Тюмень, Киров, Киев, Одесса и т.п.); \"middle_east\" — Иран/США/Израиль и "
    "регион; \"atr\" — Азиатско-Тихоокеанский регион.\n"
    "significance: \"major\" — стратегический объект (НПЗ, крупный склад/"
    "логистический хаб, военная база/аэродром, энергетика, порт, ВПК) или "
    "жертвы/крупный ущерб; \"minor\" — точечный/локальный.\n"
    'Верни JSON {"items": [{"i": <индекс>, "theater": "svo"|"middle_east"|"atr", '
    '"strike_events": [{"location": "<место, как в тексте>", "target_type": '
    '"<что поражено или null>", "significance": "major"|"minor", "label": '
    '"<подпись на русском 3-8 слов>"}]}]} — только элементы, где удар реально '
    "есть; остальные индексы не включай вовсе."
)


def extract_strikes_from_news(db: Session, hours: int = 3, limit: int = 40) -> dict:
    """Проход по свежим записям Ленты новостей (market_updates) — извлечение
    ударов для карты. Дешёвый: префильтр по словам, один LLM-вызов, дедуп на
    persist-слое. Вызывается ежечасным кроном гео-дайджеста (main.py) и
    вручную через /debug/trigger-news-strikes (hours побольше — догон)."""
    from app.models.market import MarketUpdate
    from app.services.llm import complete, LLMError

    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.status == "published", MarketUpdate.published_at >= since)
            .order_by(MarketUpdate.published_at.desc()).limit(300).all())
    cand = []
    for r in rows:
        text = f"{r.title or ''} {r.summary or ''}".lower()
        if any(k in text for k in _NEWS_STRIKE_KEYWORDS):
            cand.append(r)
    cand = cand[:limit]
    if not cand:
        return {"scanned": 0, "strikes_saved": 0}

    payload = {"items": [{"i": i, "title": r.title,
                           "summary": (r.summary or r.content or "")[:600]}
                          for i, r in enumerate(cand)]}
    try:
        res = complete(_NEWS_STRIKE_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=4000, temperature=0.2)
        items = res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("news-strikes: LLM недоступен (%s)", e)
        return {"scanned": len(cand), "strikes_saved": 0, "error": str(e)}

    saved = 0
    for it in items:
        idx = it.get("i")
        if not isinstance(idx, int) or not (0 <= idx < len(cand)):
            continue
        theater = it.get("theater")
        strikes = it.get("strike_events")
        if theater not in ("svo", "middle_east", "atr") or not isinstance(strikes, list) or not strikes:
            continue
        r = cand[idx]
        pub = r.published_at.date() if r.published_at else date.today()
        try:
            saved += _persist_strike_events(db, theater, strikes, pub, r.source, r.source_url)
        except Exception:  # noqa: BLE001 — одна битая новость не роняет проход
            logger.warning("news-strikes: не сохранён удар из %s", r.source_url, exc_info=True)
    logger.info("news-strikes: кандидатов %d, сохранено ударов %d", len(cand), saved)
    return {"scanned": len(cand), "strikes_saved": saved}


# ----------------------------- ПАЙПЛАЙН -----------------------------
def _known_urls(db: Session) -> set[str]:
    return {u for (u,) in db.query(GeoDigestArticle.source_url).all()}


def cleanup_old(db: Session, days: int = _KEEP_DAYS) -> int:
    cutoff = date.today() - timedelta(days=days)
    removed = (db.query(GeoDigestArticle)
               .filter(GeoDigestArticle.published_at < cutoff)
               .delete(synchronize_session=False))
    db.commit()
    if removed:
        logger.info("GEO-дайджест: удалено %d старых статей (старше %d дн.)", removed, days)
    return removed


def refresh(db: Session, max_new: int = _MAX_PER_RUN) -> dict:
    """Полный прогон: фетч → дедуп по URL → батч-классификация+пересказ LLM → сохранение."""
    cleanup_old(db)
    cleanup_expired_strikes(db)
    cfg = load_config()
    raw, blind = fetch_all(cfg)
    if blind:
        logger.warning("GEO-дайджест-АЛЕРТ: ослепшие источники: %s", blind)
    known = _known_urls(db)
    cutoff = date.today() - timedelta(days=_MAX_AGE_DAYS)
    fresh = []
    for a in raw:
        if a["url"] in known:
            continue
        if a.get("_no_pubdate"):
            pub = date.today()  # источник без дат вообще — см. fetch_all()
        else:
            pub = _parse_date(a.get("date_raw"))
        if pub is None or pub < cutoff:
            continue  # архив (напр. Economist отдаёт ~300 старых записей на раздел) — не тащим
        a["_pub"] = pub
        fresh.append(a)
    if not fresh:
        return {"discovered": 0, "saved": 0, "blind": blind}
    fresh.sort(key=lambda a: a["_pub"], reverse=True)  # свежее — в приоритете за прогон
    fresh = fresh[:max_new]
    saved = 0
    strikes_saved = 0  # счётчики для цепочки «нашли взятие → сразу пересинк линии» (main.py)
    claims_saved = 0
    saved_rows: list = []  # для промоута в летопись
    for i in range(0, len(fresh), _BATCH):
        chunk = fresh[i:i + _BATCH]
        items = _digest_batch(chunk)
        for it in items:
            idx = it.get("i")
            if not isinstance(idx, int) or not (0 <= idx < len(chunk)):
                continue
            target = it.get("target")
            if target not in GEO_DIGEST_TARGETS:
                continue
            art = chunk[idx]
            pub = art["_pub"]  # уже определена и провалидирована на этапе фильтрации fresh
            summary = (it.get("summary") or "").strip()
            if not summary:
                continue
            # Коммит ПО ОДНОЙ статье: параллельный прогон (cron + ручной debug-триггер
            # почти одновременно) может успеть вставить тот же source_url раньше —
            # конфликт уникальности не должен ронять всю пачку остальных статей.
            takeaways = it.get("key_takeaways")
            if not isinstance(takeaways, list):
                takeaways = None
            row = GeoDigestArticle(
                target=target, title=(it.get("title") or art["title"])[:300],
                summary=summary, key_takeaways=takeaways,
                investor_relevance=(it.get("investor_relevance") or "").strip() or None,
                published_at=pub, source_url=art["url"], source_key=art["src"],
                model_used="deepseek",
            )
            db.add(row)
            try:
                db.commit()
                saved += 1
                saved_rows.append(row)
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning("GEO-дайджест: пропуск дубля/конфликта при сохранении %s: %s",
                               art["url"], type(e).__name__)
                continue

            # Автоизвлечение карточных событий (владелец, 2026-07-24) — только
            # для театров карты (не institutions/macro), не блокирует сохранение
            # самой статьи дайджеста при сбое.
            if target in ("svo", "middle_east", "atr"):
                try:
                    strikes = it.get("strike_events")
                    if isinstance(strikes, list) and strikes:
                        strikes_saved += _persist_strike_events(db, target, strikes, pub, art["src"], art["url"])
                except Exception as e:  # noqa: BLE001
                    logger.warning("geo_digest: strike_events для %s не обработаны: %s", art["url"], type(e).__name__)
                if target == "svo":
                    try:
                        claims = it.get("territorial_claims")
                        if isinstance(claims, list) and claims:
                            claims_saved += _persist_territorial_claims(db, claims, pub, art["src"], art["url"])
                    except Exception as e:  # noqa: BLE001
                        logger.warning("geo_digest: territorial_claims для %s не обработаны: %s",
                                       art["url"], type(e).__name__)

    # Промоут свежих статей в аналитическую летопись (постоянная память агентов) —
    # теги одним батч-вызовом. Отдельно от сохранения дайджеста, не роняет его.
    chronicled = 0
    if saved_rows:
        try:
            from app.services.chronicle import ingest_geo_articles
            chronicled = ingest_geo_articles(db, saved_rows)
        except Exception as e:  # noqa: BLE001
            logger.warning("GEO-дайджест→chronicle: %s", type(e).__name__)
    res = {"discovered": len(fresh), "saved": saved, "chronicled": chronicled,
           "strikes_saved": strikes_saved, "claims_saved": claims_saved, "blind": blind}
    logger.info("GEO-дайджест: %s", res)
    return res
