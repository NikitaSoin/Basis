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
import re
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
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
_KEEP_DAYS = 30     # сколько дней держим карточку в дайджесте
_TEXT_CHARS = 3500  # сколько символов исходника отдаём модели на статью (было 500 —
                    # с куцым excerpt пересказ и получался куцым)

SOURCE_LABELS = {
    "rybar": "Рыбарь", "rybar_middle_east": "Рыбарь", "rybar_atr": "Рыбарь",
    "globalaffairs": "Global Affairs", "carnegie": "Carnegie",
    "rerussia": "re: Russia",
    "economist_europe": "The Economist", "economist_mea": "The Economist",
    "economist_china": "The Economist", "economist_finance": "The Economist",
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
    r = httpx.get(src["url"], timeout=30, headers=_HTTP, follow_redirects=True, verify=False)
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


def fetch_all(cfg: dict) -> tuple[list[dict], list[str]]:
    arts, blind = [], []
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        try:
            got = _fetch_wp_json(src) if src["method"] == "wp_json" else _fetch_rss(src)
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
    "- \"macro\" — статья ПРЕИМУЩЕСТВЕННО про МАКРОЭКОНОМИКУ (инфляция, ставка ЦБ, ВВП, "
    "бюджет/дефицит, курс рубля, торговый баланс, санкционное давление на макропоказатели) "
    "БЕЗ доминирующего военно-политического или институционального сюжета — если статья "
    "прежде всего разбирает цифры и механику экономики (в т.ч. зарубежный взгляд на "
    "российскую/мировую экономику — Economist Finance, ISW про экономические последствия), "
    "используй \"macro\", а не \"svo\"/\"institutions\", даже если триггер — военное событие "
    "(например «удар по НПЗ → дефицит топлива → инфляция» — это macro, а не svo, если фокус "
    "статьи на экономическом следствии, а не на военной динамике).\n"
    "- null — не публиковать (нет связи с экономикой/рынком, чисто военная тактика без "
    "экономических последствий, вторично, слишком локально/малозначимо).\n\n"
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
    'Верни JSON {"items": [{"i": <индекс>, "target": "svo"|"middle_east"|"atr"|"institutions"'
    '|"macro"|null, "title": "<заголовок на русском>", "summary": "<подробный пересказ 4-7 '
    'предложений на русском>", "key_takeaways": ["<тезис 1>", "<тезис 2>", ...], '
    '"investor_relevance": "<1-2 фразы>"}]}. Для target=null остальные поля можно опустить. '
    "Верни ровно один элемент items на каждую входную статью."
)


def _digest_batch(articles: list[dict]) -> list[dict]:
    from app.services.llm import complete, LLMError
    payload = {"articles": [{"i": i, "title": a["title"], "text": a["text"]}
                            for i, a in enumerate(articles)]}
    try:
        res = complete(_DIGEST_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=16000, temperature=0.3)
        return res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("GEO-дайджест: LLM недоступен (%s) — батч пропущен", e)
        return []


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
            db.add(GeoDigestArticle(
                target=target, title=(it.get("title") or art["title"])[:300],
                summary=summary, key_takeaways=takeaways,
                investor_relevance=(it.get("investor_relevance") or "").strip() or None,
                published_at=pub, source_url=art["url"], source_key=art["src"],
                model_used="deepseek",
            ))
            try:
                db.commit()
                saved += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning("GEO-дайджест: пропуск дубля/конфликта при сохранении %s: %s",
                               art["url"], type(e).__name__)
    res = {"discovered": len(fresh), "saved": saved, "blind": blind}
    logger.info("GEO-дайджест: %s", res)
    return res
