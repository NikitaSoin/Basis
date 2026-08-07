"""Отраслевая лента: обзоры, прогнозы и аналитика рынков — по отраслям.

Зачем отдельно от geo_digest. Тот собирает ленту про войну/санкции/макро и раскладывает
её по географическим адресатам. Здесь адресат другой — ОТРАСЛЬ: МЭА и ОПЕК про нефтяной
баланс, отраслевые ассоциации про производство, аналитические порталы про спрос. Такие
материалы питают отраслевой барометр (вкладка «Бизнес») и вкладку «Рынки» карточек.

Ключевое отличие от старой схемы подбора: раньше sector_barometer искал материалы по
совпадению СЛОВ из названия отрасли — грубо и с промахами. Здесь привязка явная: каждый
источник объявляет, какие отрасли он покрывает, а модель выбирает конкретную из этого
списка. Статья ложится в ту же таблицу geo_digest_articles с target="sec:<ключ отрасли>",
поэтому дедуп по URL общий с гео-лентой и новая миграция не нужна (в БД несколько
alembic-head — лишняя миграция там сейчас дороже, чем префикс в существующем поле).

Международные источники англоязычные — пересказ модель делает СРАЗУ по-русски.
"""
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.geo_digest import GeoDigestArticle
from app.services.geo_digest import _parse_date, fetch_all
from app.services.sector_barometer import SECTORS

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "sector_sources.json"
TARGET_PREFIX = "sec:"
_MAX_PER_RUN = 30   # потолок новых статей за прогон (контроль стоимости LLM)
_MAX_AGE_DAYS = 30  # отраслевой обзор живёт дольше новости, но архив не тащим
_BATCH = 3

_KEYS = {s["key"] for s in SECTORS}
_FULLTEXT_CHARS = 6000
_MIN_TEXT = 400  # ниже этого RSS-описание — тизер, из него обзор не пересказать


def _fulltext(url: str) -> str:
    """Дозагрузка текста статьи по ссылке из ленты.

    Зачем. У отраслевых лент <description> — это 250-600 знаков анонса (проверено на
    EIA), а материал ценен разбором: баланс спроса, пересмотр прогноза, причины. По
    анонсу модель напишет общие слова. Статей здесь десятки в неделю, не тысячи, —
    один HTTP-запрос на статью того стоит. Сбой не критичен: остаётся описание из RSS.
    """
    import re
    import httpx
    from app.services.geo_digest import _HTTP, _strip
    try:
        r = httpx.get(url, timeout=20, headers=_HTTP, follow_redirects=True, verify=False)
        r.raise_for_status()
        html = r.text
    except Exception:  # noqa: BLE001
        return ""
    html = re.sub(r"(?is)<(script|style|nav|header|footer|aside|form)[^>]*>.*?</\1>", " ", html)
    body = re.search(r"(?is)<(article|main)[^>]*>(.*?)</\1>", html)
    txt = _strip(body.group(2) if body else html)
    return txt[:_FULLTEXT_CHARS]


def target_for(sector_key: str) -> str:
    return f"{TARGET_PREFIX}{sector_key}"


def load_config() -> dict:
    try:
        return json.loads(_CONFIG.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("Отраслевая лента: конфиг источников недоступен: %s", type(e).__name__)
        return {"sources": []}


_SYS = """Ты — аналитик отраслевых рынков российской инвестиционной платформы. На вход —
статьи отраслевых источников (международные агентства, ассоциации, аналитические
порталы). Твоя задача по каждой: решить, полезна ли она частному инвестору в РОССИЙСКИЕ
акции, и если да — сделать пересказ НА РУССКОМ ЯЗЫКЕ.

ЧТО БЕРЁМ (relevant=true):
• баланс спроса и предложения на рынке, прогнозы цен, пересмотры прогнозов;
• состояние отрасли: загрузка мощностей, объёмы производства и потребления, запасы;
• решения, меняющие правила игры на рынке (квоты, пошлины, тарифы, регулирование);
• структурные сдвиги: новые маршруты поставок, замещение поставщиков, спрос новых стран.

ЧТО НЕ БЕРЁМ (relevant=false):
• корпоративные новости одной иностранной компании без влияния на рынок в целом;
• локальные события страны-источника, не меняющие мировой баланс (например,
  внутренний регуляторный спор в отдельном штате США);
• пресс-релизы о конференциях, назначениях, наградах;
• материал без содержания — анонс, тизер, оглавление выпуска.

СВЯЗЬ С РОССИЙСКИМ РЫНКОМ обязательна в поле investor_relevance: через что именно это
доходит до российской компании — цена экспорта, спрос на её продукцию, конкуренция,
стоимость сырья, логистика. Если связь надуманная — значит relevant=false.

ПРАВИЛА ТЕКСТА:
• пересказ СВОИМИ СЛОВАМИ, не перевод дословно; 3-6 предложений, по существу;
• числа переноси только те, что есть в исходнике; не додумывай и не округляй «на глаз»;
• единицы приводи как в источнике, но поясняй по-русски (млн барр./сут, млн т, ГВт);
• никаких «покупать/продавать», никаких инвестиционных рекомендаций;
• не называй конкретных должностных лиц по фамилии — пиши нейтрально по должности
  («профильное министерство», «руководство организации»).

ОТРАСЛЬ выбирай СТРОГО из списка candidates, приложенного к статье. Если ни одна из них
не подходит по смыслу — relevant=false.

ФОРМАТ ОТВЕТА — строго JSON, без текста вне JSON:
{"items": [{"i": <индекс статьи>, "relevant": true|false,
  "sector": "<ключ отрасли из candidates>",
  "title": "<заголовок на русском, до 200 знаков>",
  "summary": "<пересказ на русском, 3-6 предложений>",
  "key_takeaways": ["<тезис>", "<тезис>"],
  "investor_relevance": "<1-2 предложения: чем это важно инвестору в российские акции>"}]}
Для relevant=false остальные поля можно не заполнять."""


def _digest_batch(articles: list[dict]) -> list[dict]:
    from app.services.llm import complete, LLMError
    payload = {"articles": [{"i": i, "source": a.get("_label") or a["src"],
                             "candidates": a["_sectors"],
                             "title": a["title"], "text": a["text"]}
                            for i, a in enumerate(articles)]}
    try:
        res = complete(_SYS, json.dumps(payload, ensure_ascii=False),
                       json_mode=True, max_tokens=12000, temperature=0.3)
        return res.get("items", []) if isinstance(res, dict) else []
    except LLMError as e:
        logger.warning("Отраслевая лента: LLM недоступен (%s) — батч пропущен", e)
        return []


def refresh(db: Session, max_new: int = _MAX_PER_RUN) -> dict:
    """Прогон: фетч → дедуп по URL → LLM (релевантность + отрасль + пересказ) → запись."""
    cfg = load_config()
    by_key = {s["key"]: s for s in cfg.get("sources", [])}
    raw, blind = fetch_all(cfg)
    if blind:
        logger.warning("Отраслевая лента-АЛЕРТ: ослепшие источники: %s", blind)

    known = {u for (u,) in db.query(GeoDigestArticle.source_url).all()}
    cutoff = date.today() - timedelta(days=_MAX_AGE_DAYS)
    fresh = []
    for a in raw:
        if a["url"] in known:
            continue
        src = by_key.get(a["src"], {})
        sectors = [k for k in src.get("sectors", []) if k in _KEYS]
        if not sectors:
            continue  # источник без валидных отраслей — молча не тащим (видно в конфиге)
        pub = date.today() if a.get("_no_pubdate") else _parse_date(a.get("date_raw"))
        if pub is None or pub < cutoff:
            continue
        a["_pub"] = pub
        a["_sectors"] = sectors
        a["_label"] = src.get("label") or a["src"]
        fresh.append(a)

    if not fresh:
        return {"discovered": 0, "saved": 0, "skipped": 0, "blind": blind}
    fresh.sort(key=lambda a: a["_pub"], reverse=True)
    fresh = fresh[:max_new]

    # Дотягиваем текст только там, где ленты дали тизер, — и только у отобранных
    # свежих статей, чтобы не ходить по сети за тем, что всё равно отбросим.
    for a in fresh:
        if len(a.get("text") or "") < _MIN_TEXT:
            full = _fulltext(a["url"])
            if len(full) > len(a.get("text") or ""):
                a["text"] = full

    saved, skipped = 0, 0
    by_sector: dict[str, int] = {}
    for i in range(0, len(fresh), _BATCH):
        chunk = fresh[i:i + _BATCH]
        for it in _digest_batch(chunk):
            idx = it.get("i")
            if not isinstance(idx, int) or not (0 <= idx < len(chunk)):
                continue
            art = chunk[idx]
            if not it.get("relevant"):
                skipped += 1
                continue
            sector = it.get("sector")
            if sector not in art["_sectors"]:
                # модель назвала отрасль вне списка кандидатов источника: если у
                # источника она одна — берём её, иначе отбраковываем (гадать нельзя)
                if len(art["_sectors"]) == 1:
                    sector = art["_sectors"][0]
                else:
                    skipped += 1
                    continue
            summary = (it.get("summary") or "").strip()
            if not summary:
                skipped += 1
                continue
            takeaways = it.get("key_takeaways")
            row = GeoDigestArticle(
                target=target_for(sector),
                title=(it.get("title") or art["title"])[:300],
                summary=summary,
                key_takeaways=takeaways if isinstance(takeaways, list) else None,
                investor_relevance=(it.get("investor_relevance") or "").strip() or None,
                published_at=art["_pub"], source_url=art["url"], source_key=art["src"],
                model_used="deepseek",
            )
            db.add(row)
            try:
                db.commit()
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.warning("Отраслевая лента: пропуск дубля %s: %s", art["url"], type(e).__name__)
                continue
            saved += 1
            by_sector[sector] = by_sector.get(sector, 0) + 1

    logger.info("Отраслевая лента: найдено %d, сохранено %d, отсеяно %d, по отраслям %s",
                len(fresh), saved, skipped, by_sector)
    return {"discovered": len(fresh), "saved": saved, "skipped": skipped,
            "by_sector": by_sector, "blind": blind}


def articles_for(db: Session, sector_key: str, days: int = 45, limit: int = 8) -> list[GeoDigestArticle]:
    """Материалы отрасли — точная выборка по target, без угадывания по словам."""
    cutoff = date.today() - timedelta(days=days)
    return (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target == target_for(sector_key),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(limit).all())
