"""Сигнальная шина «поток Обозревателя → карточка компании».

Владелец (2026-07-27): «входящий поток должен системно дообновлять карточки
компаний (вкладки), а не гонять агентов в веб-серч за всей информацией».
Штурм и карта источников — docs/observer-source-map.md.

Два источника сигналов:
  1. ЛЕНТА (market_updates) — уже классифицирована и промапплена по тикерам
     (news_pipeline.map_tickers). Конвертируем без LLM: category+ключевые
     слова → signal_type + card_tab. trust=media (или official, если источник
     раскрытия/рейтинговое агентство).
  2. ДАЙДЖЕСТ (geo_digest_articles, включая инсайд-TG) — LLM-проход «какие
     тикеры/вкладки затронуты» (большинство макро/гео-статей ни одного тикера
     не дадут — это нормально). trust по источнику; internal=True для инсайд-
     каналов (moi_misli_vslukh/insider_*): такие сигналы НЕ отдаются публично,
     питают только агентов/барометры с пометкой «непроверенный инсайд».

Consumer (агент, обновляющий вкладку по сигналу importance≥high) — следующий
этап, по образцу macro_addendum + barometer_reviser (гейт качества).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import CompanySignal
from app.models.company import Company
from app.models.market import MarketUpdate
from app.models.geo_digest import GeoDigestArticle

logger = logging.getLogger(__name__)

# Инсайд-каналы: internal-only + low trust (владелец: «любят приукрасить/
# приврать, но для рисков и подсветки внутрянки полезны»). НЕ публикуются
# клиентам, НЕ единственное основание изменить карточку.
INTERNAL_SOURCE_KEYS = {"moi_misli_vslukh", "insider_best_tg", "insider_elites"}
_OFFICIAL_SOURCES = {"e_disclosure", "acra", "raexpert", "nkr", "nra", "cbr", "moex"}

_KEEP_DAYS = 45

# category/keyword → (signal_type, card_tab, importance)
_KW_RULES = [
    (r"дивиден", ("dividend", "dividends", "high")),
    (r"отчёт|отчет|МСФО|РСБУ|выручк|чист(ая|ой) прибыл|EBITDA|финрезультат", ("earnings", "finance", "high")),
    (r"рейтинг|АКРА|Эксперт РА|downgrade|upgrade|дефолт|оферт", ("rating_action", "bonds", "high")),
    (r"допэмисс|buyback|обратн\w+ выкуп|byback|SPO|размещени", ("capital", "governance", "high")),
    (r"смен\w+ (гендир|CEO|руковод)|совет директоров|назначен\w+ (гендир|глав)", ("management", "governance", "medium")),
    (r"иск|суд|арест|санкц|национализ|деприватиз", ("legal", "governance", "high")),
    (r"buyback|выкуп акци", ("buyback", "governance", "medium")),
    (r"поглощ|слияни|M&A|приобрел|покупк\w+ доли", ("ma", "governance", "medium")),
]


def _classify_by_text(text: str) -> tuple[str, str, str]:
    t = (text or "").lower()
    for pat, res in _KW_RULES:
        if re.search(pat, t, re.IGNORECASE):
            return res
    return ("news", "markets", "low")


def _trust_for(source_key: str | None) -> tuple[str, bool]:
    """(trust, internal) по ключу источника."""
    sk = (source_key or "").lower()
    if sk in INTERNAL_SOURCE_KEYS:
        return "insider", True
    if sk in _OFFICIAL_SOURCES:
        return "official", False
    if sk in ("rybar", "isw", "economist", "carnegie", "rerussia", "globalaffairs", "tg_carnegie"):
        return "analytical", False
    return "media", False


def _upsert(db: Session, **kw) -> bool:
    """Идемпотентная вставка по (ticker, signal_type, dedup_key). True если новый."""
    exists = (db.query(CompanySignal.id)
              .filter_by(ticker=kw["ticker"], signal_type=kw["signal_type"],
                         dedup_key=kw["dedup_key"]).first())
    if exists:
        return False
    db.add(CompanySignal(**kw))
    try:
        db.commit()
        return True
    except Exception:  # noqa: BLE001 — гонка уникальности не роняет пачку
        db.rollback()
        return False


def extract_from_lenta(db: Session, hours: int = 26) -> int:
    """Ленты-новости с affected_tickers → сигналы (без LLM: маппинг уже сделан
    news_pipeline). dedup по source_url (одна новость = один сигнал на тикер)."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.status == "published", MarketUpdate.published_at >= since,
                    MarketUpdate.affected_tickers.isnot(None)).all())
    saved = 0
    for r in rows:
        tickers = r.affected_tickers if isinstance(r.affected_tickers, list) else []
        if not tickers:
            continue
        stype, tab, imp = _classify_by_text(f"{r.title} {r.summary or ''}")
        # важность источника поверх keyword-важности
        if r.importance == "high":
            imp = "high"
        trust, internal = _trust_for(r.source)
        dedup = (r.source_url or f"mu{r.id}")[:64]
        for tk in tickers:
            if _upsert(db, ticker=tk, signal_type=stype, card_tab=tab, importance=imp,
                       trust=trust, internal=internal, title=(r.title or "")[:400],
                       summary=(r.summary or r.content or "")[:1000],
                       source_key=r.source, source_url=r.source_url,
                       published_at=r.published_at.date() if r.published_at else date.today(),
                       dedup_key=dedup):
                saved += 1
    logger.info("company_signals: из Ленты сохранено %d сигналов", saved)
    return saved


_DIGEST_MAP_SYS = (
    "Тебе даны статьи ленты и справочник тикеров MOEX. Для КАЖДОЙ статьи найди, "
    "к каким КОНКРЕТНЫМ публичным компаниям из справочника она относится ПРЯМО "
    "(упомянута компания/её бизнес/конкретное событие по ней). НЕ притягивай по "
    "сектору/макро — только прямая привязка. Большинство статей (макро/гео) не "
    "относятся ни к одному тикеру — верни для них пустой список, это норма.\n"
    "Для каждой релевантной пары определи card_tab (finance|dividends|governance|"
    "markets|macro|geo|institutions|bonds) и signal_type (earnings|dividend|"
    "rating_action|capital|management|legal|ma|news).\n"
    'Верни JSON {"items":[{"i":<индекс>,"hits":[{"ticker":"<из справочника>",'
    '"card_tab":"...","signal_type":"...","importance":"high|medium|low"}]}]} — '
    "только статьи, где hits непусты."
)


def extract_from_digest(db: Session, days: int = 3) -> int:
    """geo_digest-статьи (вкл. инсайд-TG) → сигналы по тикерам через LLM.
    internal-флаг наследуется от источника (инсайд-каналы не публичны)."""
    from app.services.llm import complete, LLMError
    cutoff = date.today() - timedelta(days=days)
    arts = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(60).all())
    if not arts:
        return 0
    directory = [{"ticker": c.ticker, "name": c.name} for c in
                 db.query(Company).order_by(Company.ticker).all()]
    valid = {c["ticker"] for c in directory}
    payload = {"directory": directory,
               "articles": [{"i": i, "title": a.title, "summary": (a.summary or "")[:400]}
                            for i, a in enumerate(arts)]}
    try:
        res = complete(_DIGEST_MAP_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=6000, temperature=0.1)
        items = res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("company_signals: LLM для дайджеста недоступен (%s)", e)
        return 0
    saved = 0
    for it in items:
        idx = it.get("i")
        if not isinstance(idx, int) or not (0 <= idx < len(arts)):
            continue
        a = arts[idx]
        trust, internal = _trust_for(a.source_key)
        pub = a.published_at or date.today()
        for h in (it.get("hits") or []):
            tk = h.get("ticker")
            if tk not in valid:
                continue
            if _upsert(db, ticker=tk, signal_type=h.get("signal_type") or "news",
                       card_tab=h.get("card_tab") or "markets",
                       importance=h.get("importance") or "low",
                       trust=trust, internal=internal, title=(a.title or "")[:400],
                       summary=(a.summary or "")[:1000], source_key=a.source_key,
                       source_url=a.source_url, published_at=pub,
                       dedup_key=(a.source_url or f"gd{a.id}")[:64]):
                saved += 1
    logger.info("company_signals: из дайджеста сохранено %d сигналов", saved)
    return saved


def cleanup_old(db: Session, days: int = _KEEP_DAYS) -> int:
    cutoff = date.today() - timedelta(days=days)
    removed = (db.query(CompanySignal)
               .filter(CompanySignal.published_at < cutoff)
               .delete(synchronize_session=False))
    db.commit()
    return removed


def refresh(db: Session) -> dict:
    """Полный прогон шины (крон)."""
    cleanup_old(db)
    lenta = extract_from_lenta(db)
    digest = extract_from_digest(db)
    return {"from_lenta": lenta, "from_digest": digest}


def public_signals_for(db: Session, ticker: str, limit: int = 20) -> list[dict]:
    """Публичные (не internal) сигналы по тикеру — для карточки/API."""
    rows = (db.query(CompanySignal)
            .filter(CompanySignal.ticker == ticker.upper(),
                    CompanySignal.internal.is_(False))
            .order_by(CompanySignal.published_at.desc().nullslast(),
                      CompanySignal.created_at.desc()).limit(limit).all())
    return [{"signal_type": r.signal_type, "card_tab": r.card_tab, "importance": r.importance,
             "trust": r.trust, "title": r.title, "summary": r.summary,
             "source_key": r.source_key, "source_url": r.source_url,
             "published_at": r.published_at.isoformat() if r.published_at else None}
            for r in rows]
