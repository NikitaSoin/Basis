"""Полные тексты первоисточников для макро-интерпретатора.

🔴 ЗАЧЕМ (владелец, 2026-08-01): «отправляй в дипсик целиком статьи (ЦБ, ЦМАКП,
Карнеги, Re:Russia и все важные) — токены дешёвые, не паримся». До этого в промпт шёл
только НАШ пересказ, про который владелец сам и сказал: «краткая выжимка местами без
сути». Хуже того — пересказ делает другая LLM и он не проходит никакой проверки: на нём
я в тот же день ошибся с инфляционными ожиданиями, приняв «наблюдаемую инфляцию» из
пересказа за наш показатель.

Контекстное окно DeepSeek V4 Pro — 1 048 576 токенов, использовали 75 тыс. (7%).
Места под первоисточники с избытком, ограничение не в окне.

Механика: текст качается ОДИН раз и кладётся в БД (full_text). Дальше берётся из кэша.
Неудачная попытка тоже отмечается временем — чтобы не долбить мёртвый URL каждый прогон.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/122 Safari/537.36",
            "Accept": "text/html,application/pdf,*/*"}
_TIMEOUT = 25
# Потолок на документ. 60k знаков ≈ 27k токенов — при окне 1M это не давит; целиком
# помещаются даже длинные бюллетени ЦБ. Транспортный лимит (таймаут прокси Timeweb,
# из-за которого объём временно резали до 14k) снят фоновой генерацией — HTTP больше
# не ждёт модель, см. macro_interpreter.start_background_generation.
_MAX_CHARS = 60_000
# Повторная попытка для документа, который не дался, — не раньше чем через неделю.
_RETRY_AFTER = timedelta(days=7)


def _clean_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'), ("&#39;", "'"),
                 ("&laquo;", "«"), ("&raquo;", "»"), ("&mdash;", "—"), ("&ndash;", "–")):
        text = text.replace(a, b)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def fetch_article_text(url: str) -> str | None:
    """HTML или PDF по ссылке → плоский текст. None, если не получилось."""
    if not url or not url.startswith("http"):
        return None
    try:
        import httpx
        with httpx.Client(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            if "pdf" in ctype or url.lower().endswith(".pdf"):
                try:
                    import io

                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(r.content))
                    text = "\n".join((p.extract_text() or "") for p in reader.pages)
                except Exception:  # noqa: BLE001
                    logger.warning("article_texts: PDF не распарсен: %s", url)
                    return None
            else:
                text = _clean_html(r.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("article_texts: не скачал %s (%s)", url, type(e).__name__)
        return None
    text = (text or "").strip()
    if len(text) < 200:  # заглушка/капча/пустая страница — не считаем текстом
        return None
    return text[:_MAX_CHARS]


def ensure_full_texts(db: Session, rows: list, limit: int = 25) -> int:
    """Дозагрузить full_text у переданных записей (ORM-объектов с source_url).

    Вызывается при сборке снапшота. Тихо пропускает то, что уже есть или недавно не
    далось: интерпретатор не должен падать из-за недоступного сайта.
    """
    now = datetime.now(timezone.utc)
    filled = 0
    for row in rows:
        if filled >= limit:
            break
        if getattr(row, "full_text", None):
            continue
        last_try = getattr(row, "full_text_fetched_at", None)
        if last_try and (now - last_try) < _RETRY_AFTER:
            continue
        url = getattr(row, "source_url", None)
        text = fetch_article_text(url) if url else None
        row.full_text_fetched_at = now
        if text:
            row.full_text = text
            filled += 1
    if filled:
        try:
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("article_texts: не сохранил тексты", exc_info=True)
            return 0
    return filled
