"""Движок «Геополитика → Рынок» (Обозреватель, Направление 7).

Пайплайн (по образцу Конвейера 2): парсер следит за источниками → жёсткий фильтр темы
(LLM) → синтез DeepSeek Pro (reasoning) СТРОГО по docs/geo_methodology.md
(нейтрализация, каналы→секторы→бумаги→сценарии, синтез БЕЗ цитат и без ссылок на
источники в выдаче). Источники — в config/geo_sources.json (не в коде, не в выдаче).
Парсер устойчив к смене вёрстки: пустой результат → алерт (лог), не падаем молча.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.models.geo import GeoBlock, GEO_REGIONS
from app.models.company import Company

logger = logging.getLogger(__name__)
_CFG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "geo_sources.json")
_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
         "Accept-Language": "ru-RU,ru;q=0.9"}
_METH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "docs", "geo_methodology.md")
_REGION_TITLE = {"svo": "СВО / российская повестка", "middle_east": "Ближний Восток", "atr": "АТР"}


def load_config() -> dict:
    with open(_CFG, encoding="utf-8") as f:
        return json.load(f)


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


# ----------------------------- ПАРСЕР ИСТОЧНИКОВ -----------------------------
def _fetch_wp_json(src: dict) -> list[dict]:
    r = httpx.get(src["url"], params=src.get("params"), timeout=30, headers=_HTTP, follow_redirects=True)
    r.raise_for_status()
    out = []
    for p in r.json():
        out.append({"title": _strip(p.get("title", {}).get("rendered", "")),
                    "text": _strip(p.get("excerpt", {}).get("rendered", ""))[:600],
                    "date": (p.get("date") or "")[:10], "role": src["role"], "src": src["key"]})
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
        title = t("title")
        if not title:
            continue
        out.append({"title": title, "text": _strip(t("description"))[:600],
                    "date": t("pubDate")[:16], "role": src["role"], "src": src["key"]})
    return out


def fetch_articles(cfg: dict) -> tuple[list[dict], list[str]]:
    """Все источники → статьи. Возвращает (статьи, ослепшие_источники для алерта)."""
    arts, blind = [], []
    for src in cfg.get("sources", []):
        if not src.get("enabled", True):
            continue
        try:
            if src["method"] == "wp_json":
                got = _fetch_wp_json(src)
            else:
                got = _fetch_rss(src)
            if not got:
                blind.append(src["key"])
                logger.warning("GEO-АЛЕРТ: источник %s вернул 0 статей (смена вёрстки?)", src["key"])
            arts.extend(got)
        except Exception as e:  # noqa: BLE001
            blind.append(src["key"])
            logger.warning("GEO-АЛЕРТ: источник %s недоступен: %s", src["key"], type(e).__name__)
    return arts, blind


def _assign_region(text: str, kw: dict) -> str | None:
    t = text.lower()
    best, score = None, 0
    for region, words in kw.items():
        s = sum(1 for w in words if w in t)
        if s > score:
            best, score = region, s
    return best if score > 0 else None


# ----------------------------- ЖЁСТКИЙ ФИЛЬТР ТЕМЫ (LLM) -----------------------------
_FILTER_SYS = (
    "Ты — фильтр темы для аналитики «геополитика→рынок» (раздел 2 методики). Из списка "
    "заголовков оставь ТОЛЬКО про экономику/динамику конфликта и их последствия для "
    "рынков (сырьё, санкции, логистика, расчёты, бюджет, спрос, оценка активов). "
    "ОТСЕКАЙ: персоналии/расследования, миграция, внутренняя политика, оценки власти, "
    "идеология, моральные оценки сторон, военная тактика без экономики. "
    'Верни JSON {"keep":[индексы релевантных, целые числа]}.'
)


def _topic_filter(articles: list[dict]) -> list[dict]:
    from app.services.llm import complete, LLMError
    if not articles:
        return []
    payload = {"articles": [{"i": i, "title": a["title"], "text": a["text"][:200]}
                            for i, a in enumerate(articles)]}
    try:
        res = complete(_FILTER_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=1500, temperature=0.0)
        keep = set(res.get("keep", [])) if isinstance(res, dict) else None
        if keep is not None:
            return [a for i, a in enumerate(articles) if i in keep]
    except LLMError as e:
        logger.warning("GEO фильтр темы: LLM недоступен (%s) — мягкий fallback по ключам", e)
    return articles  # fallback: дальше синтез сам нейтрализует


# ----------------------------- СИНТЕЗ (DeepSeek Pro) -----------------------------
def _methodology() -> str:
    try:
        return open(_METH, encoding="utf-8").read()
    except OSError:
        return ""


_CHANNELS = ("Сырьё и цены", "Санкции и доступ", "Логистика и маршруты",
             "Валюта и потоки капитала", "Бюджет и госрасходы", "Риск-премия и оценка",
             "Конечный спрос")
_CH_HINT = " channel — СТРОГО одно из: " + " | ".join(_CHANNELS) + "."

_SYNTH_SPEC_DEEP = (
    'Верни JSON: {"status_text":"нейтральная фактура динамики (2-4 фразы, без оценок сторон)",'
    '"channels":[{"channel":"канал","effect":"короткий эффект"}],' + _CH_HINT +
    '"affected_sectors":["секторы МосБиржи"],"affected_tickers":["ТИКЕРЫ только из переданного списка"],'
    '"scenarios":{"base":{"text":"...","triggers":["..."],"sectors":["..."]},'
    '"bull":{"text":"...","triggers":["..."],"sectors":["..."]},'
    '"bear":{"text":"...","triggers":["..."],"sectors":["..."]}},'
    '"market_impact":"что это значит для рынков (итог, экономический язык)"}'
)
_SYNTH_SPEC_OVERVIEW = (
    'Верни JSON: {"status_text":"событийная динамика региона нейтрально (3-5 фраз)",'
    '"channels":[{"channel":"канал","effect":"кратко"}],' + _CH_HINT +
    '"affected_sectors":["секторы"],"affected_tickers":["ТИКЕРЫ только из списка"],'
    '"market_impact":"краткое: что это значит для рынков"}'
)


def _synthesize(region: str, tab: str, articles: list[dict], tickers_ref: list[dict]) -> dict | None:
    from app.services.llm import complete, pro_model, LLMError
    if not articles:
        return None
    spec = _SYNTH_SPEC_DEEP if tab == "deep" else _SYNTH_SPEC_OVERVIEW
    layer = ("ГЛУБОКАЯ АНАЛИТИКА: структурный разбор каналы→секторы→бумаги→сценарии "
             "base/bull/bear с триггерами." if tab == "deep" else
             "ОБЗОР: событийная оперативная картина + краткое влияние на рынки. "
             "Для СВО — ОБЩИЙ вектор, не пообъектно по фронтам.")
    system = (_methodology() + "\n\n=== ЗАДАЧА ===\n" + layer +
              "\nСинтезируй СВОИМИ СЛОВАМИ (раздел 7: без цитат, без ссылок на источники, "
              "без дословных заимствований). Нейтрализуй язык (раздел 6). Все прогнозы — "
              "сценарные, словесные вероятности, помечай мысленно как «оценка Basis». "
              "Каждый вывод доведи до канала и бумаги. Тикеры — ТОЛЬКО из переданного "
              "справочника.\n" + spec)
    payload = {"region": _REGION_TITLE.get(region, region),
               "articles": [{"title": a["title"], "text": a["text"]} for a in articles[:18]],
               "tickers_ref": tickers_ref}
    try:
        res = complete(system, json.dumps(payload, ensure_ascii=False), json_mode=True,
                       thinking=True, model=pro_model(), max_tokens=8192, temperature=0.4)
        return res if isinstance(res, dict) else None
    except LLMError as e:
        logger.warning("GEO синтез %s/%s: Pro недоступен: %s", region, tab, e)
        return None


def _valid_tickers(db: Session) -> dict[str, str]:
    return {c.ticker: c.sector for c in db.query(Company).all()}


def _save(db: Session, region: str, tab: str, data: dict, n: int, valid: dict):
    tickers = [t for t in (data.get("affected_tickers") or []) if t in valid]
    block = (db.query(GeoBlock).filter_by(region=region, tab=tab).first()
             or GeoBlock(region=region, tab=tab))
    block.title = _REGION_TITLE.get(region, region)
    block.status_text = data.get("status_text")
    block.channels = data.get("channels")
    block.scenarios = data.get("scenarios")
    block.market_impact = data.get("market_impact")
    block.affected_sectors = data.get("affected_sectors")
    block.affected_tickers = tickers
    block.source_count = n
    block.model_used = "deepseek-pro"
    block.updated_at = datetime.now(timezone.utc)
    db.add(block); db.commit()


def refresh(db: Session) -> dict:
    """Полный пересбор: фетч → фильтр темы → синтез обеих вкладок по регионам."""
    cfg = load_config()
    kw = cfg.get("region_keywords", {})
    valid = _valid_tickers(db)
    ref = [{"ticker": t, "sector": s} for t, s in list(valid.items())]
    raw, blind = fetch_articles(cfg)
    if blind:
        logger.warning("GEO-АЛЕРТ: ослепшие источники: %s", blind)
    if not raw:
        logger.warning("GEO-АЛЕРТ: ни одной статьи — пропуск синтеза")
        return {"error": "no_articles", "blind": blind}
    kept = _topic_filter(raw)
    # группировка по региону
    by_region: dict[str, list] = {r: [] for r in GEO_REGIONS}
    for a in kept:
        reg = _assign_region(a["title"] + " " + a["text"], kw)
        if reg in by_region:
            by_region[reg].append(a)
    res = {"blind": blind, "regions": {}}
    for region, arts in by_region.items():
        if not arts:
            continue
        # overview — все регионы; deep — события + аналитика (берём все статьи региона)
        for tab in ("overview", "deep"):
            data = _synthesize(region, tab, arts, ref)
            if data:
                _save(db, region, tab, data, len(arts), valid)
                res["regions"].setdefault(region, []).append(tab)
    logger.info("GEO пересбор: %s", res)
    return res
