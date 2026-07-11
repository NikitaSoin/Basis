"""Ежедневный дайджест отдельных статей (Обозреватель): Рыбарь / re:russia /
Carnegie и др. источники из config/geo_sources.json.

В отличие от geopolitics.py (слитый синтез по региону), здесь каждая статья
становится отдельной карточкой: политкорректный пересказ + «зачем это
инвестору». Один LLM-вызов на батч решает сразу три вещи: публиковать ли,
куда (region svo|middle_east|atr — геополитическое событие с экономической
проекцией, или institutions — институциональная среда СТРОГО с экономическим
выводом, без пересказа аппаратной/подковёрной борьбы) и как пересказать
(нейтрально, эвфемизмы вместо острых формулировок, без цитат и ссылок на
источник — geo_methodology.md, раздел 7).

Источник/URL хранятся в БД только для дедупа, наружу (API/фронт) не отдаются.
"""
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
_BATCH = 12
_KEEP_DAYS = 30     # сколько дней держим карточку в дайджесте


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
        out.append({"title": _strip(p.get("title", {}).get("rendered", "")),
                    "text": _strip(p.get("excerpt", {}).get("rendered", ""))[:800],
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
        out.append({"title": title, "text": _strip(t("description"))[:800],
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
    "фрагмент текста) из разных СМИ. Для КАЖДОЙ статьи реши: (1) стоит ли её публиковать, "
    "(2) в какой раздел, (3) как политкорректно и нейтрально пересказать.\n\n"
    "РАЗДЕЛЫ (target):\n"
    "- \"svo\" / \"middle_east\" / \"atr\" — геополитическое СОБЫТИЕ или динамика конфликта "
    "в соответствующем регионе, У КОТОРОГО ЕСТЬ связь с экономикой/рынками (санкции, сырьё, "
    "логистика, расчёты, бюджет, курс).\n"
    "- \"institutions\" — статья про ИНСТИТУЦИОНАЛЬНУЮ СРЕДУ (защита собственности, "
    "перераспределение активов, регуляторная/судебная практика, госполитика в экономике, "
    "элитная конкуренция) — НО ТОЛЬКО если есть чёткая экономическая проекция (что это "
    "значит для бизнеса/инвестора/рынка). ОТСЕИВАЙ статьи, которые сводятся к пересказу "
    "аппаратной/подковёрной борьбы БЕЗ экономического вывода — это не для инвестора.\n"
    "- null — не публиковать (нет связи с экономикой/рынком, чисто военная тактика без "
    "экономических последствий, вторично, слишком локально/малозначимо).\n\n"
    "ЖЁСТКИЕ ПРАВИЛА ПЕРЕСКАЗА:\n"
    "1. Пиши СВОИМИ СЛОВАМИ — без цитат, без упоминания конкретного СМИ/канала/автора как "
    "источника.\n"
    "2. МАКСИМАЛЬНАЯ политкорректность: нейтральный фактологический язык, без оценок в "
    "чью-либо пользу. Острые формулировки заменяй эвфемизмами (нейтральное описание события "
    "вместо резких характеристик; «сообщается о...» вместо личных обвинений).\n"
    "3. Для target=\"institutions\": фокус СТРОГО на экономических последствиях — НЕ "
    "пересказывай подробности конфликта между конкретными людьми/группами; если в статье это "
    "главное содержание, выведи только экономический итог одной фразой, без деталей интриги.\n"
    "4. investor_relevance — отдельно, 1-2 фразы: зачем инвестору это знать (на что обратить "
    "внимание, какой актив/сектор может быть затронут). Без рекомендаций «покупать/продавать».\n\n"
    'Верни JSON {"items": [{"i": <индекс>, "target": "svo"|"middle_east"|"atr"|"institutions"'
    '|null, "title": "<нейтральный заголовок>", "summary": "<пересказ 2-4 предложения>", '
    '"investor_relevance": "<1-2 фразы>"}]}. Для target=null остальные поля можно опустить. '
    "Верни ровно один элемент items на каждую входную статью."
)


def _digest_batch(articles: list[dict]) -> list[dict]:
    from app.services.llm import complete, LLMError
    payload = {"articles": [{"i": i, "title": a["title"], "text": a["text"][:500]}
                            for i, a in enumerate(articles)]}
    try:
        res = complete(_DIGEST_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=4000, temperature=0.3)
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
            db.add(GeoDigestArticle(
                target=target, title=(it.get("title") or art["title"])[:300],
                summary=summary, investor_relevance=(it.get("investor_relevance") or "").strip() or None,
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
