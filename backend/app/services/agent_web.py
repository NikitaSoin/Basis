"""Веб-инструменты для агентов (владелец, 2026-07-21): веб-поиск + открытие/
разбор документов (в т.ч. PDF-отчётности МСФО).

🔴 ЧЕСТНЫЙ ПРОД-НЮАНС: egress с инстанса Timeweb режет прямой TLS к внешним
хостам (поэтому DeepSeek/FRED ходят через Cloudflare-релеи — см. .env
DEEPSEEK_BASE_URL/FRED_BASE_URL). Эти инструменты работают напрямую ЛОКАЛЬНО
(проверка возможностей) и на проде — ТОЛЬКО если egress до конкретного хоста
разрешён ИЛИ настроен релей. При блокировке — честная деградация: инструмент
возвращает {"error": ...}, агент продолжает на внутренних данных (не падает).

Веб-поиск:
  - Tavily (если задан TAVILY_API_KEY) — структурированный поиск для LLM,
    свободный тариф ~1000/мес; при желании — через WEB_SEARCH_BASE_URL-релей
    (тот же паттерн, что DeepSeek), чтобы обойти egress.
  - Иначе keyless-фолбэк DuckDuckGo lite (парсинг HTML регэкспом — bs4 нет).

Документы (fetch_document):
  - PDF → текст через pypdf (уже в requirements). HTML → грубая очистка тегов
    регэкспом. Потолок символов, чтобы не раздуть контекст агента.
"""
from __future__ import annotations

import io
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "Mozilla/5.0 (compatible; BasisAgent/1.0; +https://inbasis.ru)"}
_FETCH_TIMEOUT = httpx.Timeout(25.0, connect=8.0)


def _client() -> httpx.Client:
    # переиспользуем клампинг MSS из общего util (обход MTU black hole)
    from app.services.http_util import make_client
    return make_client(timeout=_FETCH_TIMEOUT)


def via_proxy(target: str) -> str:
    """Если задан WEB_FETCH_PROXY_URL (Cloudflare Worker-форвардер, как
    DEEPSEEK_BASE_URL/FRED_BASE_URL) — заворачиваем внешний GET через него.
    Нужно для хостов, которые egress инстанса Timeweb режет (t.me — Telegram,
    и т.п.); хосты, что и так открыты (DuckDuckGo/Tavily/investmint), тоже
    пройдут через воркер без вреда. Без переменной — прямой запрос."""
    from urllib.parse import quote
    proxy = os.environ.get("WEB_FETCH_PROXY_URL")
    if proxy and target.startswith(("http://", "https://")):
        return f"{proxy.rstrip('/')}/?url={quote(target, safe='')}"
    return target


# ─────────────────────────── веб-поиск ───────────────────────────

def _search_tavily(query: str, max_results: int) -> dict | None:
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return None
    base = (os.environ.get("WEB_SEARCH_BASE_URL") or "https://api.tavily.com").rstrip("/")
    try:
        with _client() as c:
            r = c.post(f"{base}/search", json={
                "api_key": key, "query": query, "max_results": max_results,
                "search_depth": "basic", "include_answer": False,
            }, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
        return {"provider": "tavily", "results": [
            {"title": x.get("title"), "url": x.get("url"), "snippet": (x.get("content") or "")[:500]}
            for x in (data.get("results") or [])[:max_results]
        ]}
    except Exception as e:  # noqa: BLE001
        logger.warning("web_search tavily fail: %s", type(e).__name__)
        return {"error": "tavily_failed", "detail": type(e).__name__}


def _ddg_unwrap(href: str) -> str:
    """DuckDuckGo оборачивает результат в /l/?uddg=<urlencoded> — разворачиваем."""
    from urllib.parse import unquote, urlparse, parse_qs
    if "uddg=" in href:
        try:
            q = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
            if q.get("uddg"):
                return unquote(q["uddg"][0])
        except Exception:  # noqa: BLE001
            pass
    return href if href.startswith("http") else "https:" + href


def _search_ddg(query: str, max_results: int) -> dict:
    """Keyless DuckDuckGo (html-эндпоинт, result__a). Парсинг регэкспом (bs4 нет).
    Фрагильно — для демо/фолбэка; при egress-блокировке отдаёт error."""
    try:
        with _client() as c:
            r = c.get("https://html.duckduckgo.com/html/", params={"q": query},
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            r.raise_for_status()
            html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("web_search ddg fail: %s", type(e).__name__)
        return {"error": "search_unavailable", "detail": type(e).__name__,
                "note": "Веб-поиск с сервера недоступен (вероятно egress) — работаю на внутренних данных."}
    results = []
    # результат: <a class="result__a" href="...">Title</a> + рядом result__snippet
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url = _ddg_unwrap(m.group(1))
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if url and title:
            results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= max_results:
            break
    # сниппеты (по позиции — тот же порядок)
    snippets = [re.sub(r"<[^>]+>", "", s).strip()
                for s in re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)]
    for i, sn in enumerate(snippets[:len(results)]):
        results[i]["snippet"] = sn[:400]
    return {"provider": "duckduckgo", "results": results[:max_results]}


def web_search(query: str, max_results: int = 5) -> dict:
    max_results = max(1, min(int(max_results or 5), 8))
    r = _search_tavily(query, max_results)
    if r and "results" in r:
        return r
    return _search_ddg(query, max_results)


# ─────────────────────────── документы ───────────────────────────

def _extract_pdf(content: bytes, max_chars: int) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    parts = []
    total = 0
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            t = ""
        parts.append(t)
        total += len(t)
        if total > max_chars:
            break
    return re.sub(r"[ \t]+", " ", "\n".join(parts)).strip()[:max_chars]


def _extract_html(text: str, max_chars: int) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def fetch_document(url: str, max_chars: int = 12000) -> dict:
    """Открыть URL и вернуть его ТЕКСТ (PDF → pypdf, HTML → очистка тегов).
    Демонстрирует «пришёл PDF отчётности — агент его разобрал». Ограничение по
    символам, чтобы не раздуть контекст."""
    if not re.match(r"^https?://", url or ""):
        return {"error": "bad_url"}
    try:
        with _client() as c:
            r = c.get(via_proxy(url), headers=_UA, follow_redirects=True)
            r.raise_for_status()
            ctype = (r.headers.get("content-type") or "").lower()
            content = r.content
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_document fail %s: %s", url, type(e).__name__)
        return {"error": "fetch_failed", "detail": type(e).__name__,
                "note": "Документ с сервера не открылся (вероятно egress-ограничение хостинга)."}
    is_pdf = "application/pdf" in ctype or url.lower().endswith(".pdf") or content[:5] == b"%PDF-"
    try:
        text = _extract_pdf(content, max_chars) if is_pdf else _extract_html(r.text, max_chars)
    except Exception as e:  # noqa: BLE001
        return {"error": "extract_failed", "detail": type(e).__name__}
    if not text:
        return {"error": "empty_text", "note": "Документ открылся, но текст не извлёкся (возможно скан/картинки в PDF)."}
    return {"url": url, "kind": "pdf" if is_pdf else "html",
            "chars": len(text), "text": text}
