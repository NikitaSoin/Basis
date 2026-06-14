"""MacroAnalyticsService — Конвейер 2: автоматический мониторинг аналитики.

Постоянный пайплайн (раз в сутки), НЕ разовое скачивание:
1) ОБНАРУЖЕНИЕ новых документов ПАРСЕРОМ (код, бесплатно): зайти на страницы
   публикаций (ЦБ /dkp/, ЦМАКП forecast.ru), собрать ссылки на PDF, сравнить с уже
   обработанными (по source_url) → новые.
2) СКАЧИВАНИЕ нового PDF (код) + извлечение текста (pypdf).
3) АНАЛИЗ И ПЕРЕСКАЗ — DeepSeek (LLM-прослойка): выжимка строго по тексту + тезисы
   с акцентом на ВЛИЯНИЕ (компании/секторы/рынок/ставка/макро). Запрет на додумывание.
4) СОХРАНЕНИЕ в MacroAnalyticsDoc.
УСТОЙЧИВОСТЬ: если страница-источник дала 0 ссылок (смена вёрстки) — лог-алерт,
НЕ падаем молча.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date

import httpx
from sqlalchemy.orm import Session

from app.models.macro import MacroAnalyticsDoc
from app.services import llm
from app.services.macro_ingest import load_macro_config

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "BasisMacroBot/1.0 (+https://inbasis.ru)"}
_MAX_PER_RUN = 6        # потолок новых документов за прогон (контроль стоимости)
_MAX_PDF_CHARS = 14000  # сколько текста PDF отдаём модели (хватает на выжимку)

_DOC_SYS = (
    "Ты пересказываешь аналитический документ (Банк России / ЦМАКП) для "
    "инвестиционно-аналитической платформы. Дан текст документа. Верни строго JSON "
    "{\"title\": \"<краткий заголовок документа>\", \"summary\": \"<выжимка 3-5 "
    "предложений строго по тексту>\", \"key_takeaways\": [\"<тезис>\", ...]}. "
    "key_takeaways — 3-6 тезисов с акцентом на ВЛИЯНИЕ: что документ значит для "
    "компаний/секторов/рынка/ключевой ставки/макро (НЕ общий пересказ, а выводы, "
    "влияющие на рынок). ЖЁСТКОЕ ПРАВИЛО: только из текста документа, не выдумывай "
    "факты/цифры; без торговых рекомендаций. Никакого текста вне JSON."
)


_INTERP_SYS = (
    "Ты — макроаналитик Basis. Дана выжимка аналитического документа (ЦБ/ЦМАКП). "
    "Дай КОРОТКУЮ интерпретацию (2-4 предложения): на какие рынки/секторы/компании и на "
    "ключевую ставку это влияет и НА ЧТО ОБРАТИТЬ ВНИМАНИЕ В ПЕРВУЮ ОЧЕРЕДЬ (главное, не всё "
    "подряд), через какой механизм. Опирайся только на содержание выжимки, без выдумок, без "
    "‘купить/продать’. Верни строго JSON {\"interpretation\": \"...\"}. Без текста вне JSON."
)


def _interpret(title: str, summary: str | None, takeaways: list) -> str | None:
    """F: интерпретация влияния через DeepSeek Pro (reasoning)."""
    if not summary and not takeaways:
        return None
    payload = {"title": title, "summary": summary, "key_takeaways": takeaways}
    import json as _json
    try:
        out = llm.complete(_INTERP_SYS, _json.dumps(payload, ensure_ascii=False),
                           json_mode=True, thinking=True, model=llm.pro_model(), max_tokens=3000)
        return (out.get("interpretation") or "").strip() or None
    except llm.LLMError as e:
        logger.warning("Интерпретация обзора не получена: %s", e)
        return None


def _absolutize(href: str, base: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return base.rstrip("/") + "/" + href.lstrip("/")


def discover(db: Session) -> list[dict]:
    """Собрать ссылки на новые документы (которых ещё нет в БД). Парсер, без LLM."""
    cfg = load_macro_config()
    known = {u for (u,) in db.query(MacroAnalyticsDoc.source_url).all()}
    found: list[dict] = []
    for src in cfg.get("analytics_sources", []):
        try:
            r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(src["page_url"])
            r.raise_for_status()
            html = r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("Аналитика: страница %s недоступна: %s", src["page_url"], type(e).__name__)
            continue
        ext = src.get("ext", ".pdf")
        links = re.findall(r'href="([^"]+%s)"' % re.escape(ext), html, flags=re.IGNORECASE)
        if not links:
            # СЛЕПОТА парсера — алерт владельцу (смена вёрстки), не молчим
            logger.warning("Аналитика-мониторинг: источник %s (%s) дал 0 ссылок — "
                           "возможна смена вёрстки сайта!", src["source"], src["page_url"])
            continue
        seen = set()
        per_src = 0
        cap = int(src.get("max", _MAX_PER_RUN))
        for href in links:
            url = _absolutize(href, src["base_url"])
            if url in known or url in seen:
                continue
            seen.add(url)
            title = href.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            found.append({"source": src["source"], "doc_type": src.get("doc_type"),
                          "url": url, "title": title})
            per_src += 1
            if per_src >= cap:  # не более N новых на источник за прогон
                break
    return found


def _pdf_text(url: str) -> str | None:
    try:
        r = httpx.Client(timeout=40, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        parts = []
        for page in reader.pages[:20]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) > _MAX_PDF_CHARS:
                break
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        return text[:_MAX_PDF_CHARS] or None
    except Exception as e:  # noqa: BLE001
        logger.warning("Аналитика: не удалось извлечь PDF %s: %s", url, type(e).__name__)
        return None


def process(db: Session, max_docs: int = _MAX_PER_RUN) -> dict:
    """Полный прогон мониторинга: обнаружить новые → скачать → выжимка LLM → сохранить."""
    candidates = discover(db)
    if not candidates:
        return {"discovered": 0, "saved": 0}
    model_used = f"{llm.provider_info().get('provider')}:{llm.provider_info().get('model')}"
    saved = 0
    for c in candidates[:max_docs]:
        text = _pdf_text(c["url"])
        if not text or len(text) < 400:
            continue  # не извлеклось содержимое — пропускаем (не выдумываем)
        try:
            out = llm.complete(_DOC_SYS, text[:_MAX_PDF_CHARS], json_mode=True, max_tokens=2048)
        except llm.LLMError as e:
            logger.error("Аналитика: LLM не дал выжимку для %s: %s", c["url"], e)
            continue
        title = (out.get("title") or c["title"])[:500]
        summary = (out.get("summary") or "").strip() or None
        takeaways = out.get("key_takeaways") or []
        # F. Интерпретация «на что влияет / на кого смотреть в первую очередь» —
        # это РАССУЖДЕНИЕ → DeepSeek Pro (reasoning), не Flash.
        interp = _interpret(title, summary, takeaways)
        db.add(MacroAnalyticsDoc(
            source=c["source"], doc_type=c["doc_type"], title=title,
            summary=summary, key_takeaways=takeaways, interpretation=interp,
            published_at=date.today(), source_url=c["url"],
            model_used=model_used + ("+pro" if interp else ""),
        ))
        saved += 1
    db.commit()
    res = {"discovered": len(candidates), "saved": saved}
    logger.info("Аналитика-мониторинг: %s", res)
    return res
