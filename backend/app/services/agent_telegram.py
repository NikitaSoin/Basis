"""Чтение публичных Телеграм-каналов через ВЕБ-ПРЕВЬЮ t.me/s/<channel>
(владелец, 2026-07-21). Без Bot API и без Client API: у публичного канала есть
HTML-страница t.me/s/<username> с последними постами — парсим её (bs4 нет, регэксп).

🔴 ГРАНИЦЫ СПОСОБА (честно):
  - Работает ТОЛЬКО для ПУБЛИЧНЫХ каналов (есть @username / t.me/<name>).
  - Каналы, куда нужно, чтобы тебя ДОБАВИЛИ (инвайт-only, нет публичного
    username), через t.me/s/ НЕ читаются — там нужен Telegram Client API
    (Telethon) с аккаунтом-участником. Это отдельная инфраструктура (номер,
    сессия, серая зона ToS) — не в этом контуре.
  - Только последние ~20 постов (без глубокой истории).
  - Egress-нюанс инстанса Timeweb — как у остального внешнего (см. agent_web.py).
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)


def _clean(html_fragment: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html_fragment)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), t)
    t = re.sub(r"&amp;", "&", t).replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]+", " ", t).strip()


def fetch_telegram_posts(channel: str, limit: int = 15) -> dict:
    """Последние посты публичного канала. channel — @name / name / t.me-ссылка."""
    name = re.sub(r"^https?://t\.me/(s/)?", "", channel.strip()).lstrip("@").strip("/")
    name = re.split(r"[/?]", name)[0]
    if not re.match(r"^[A-Za-z0-9_]{3,64}$", name):
        return {"error": "bad_channel", "note": "Ожидается @username или t.me/username публичного канала."}
    from app.services.http_util import make_client
    try:
        with make_client(timeout=httpx.Timeout(20.0, connect=8.0)) as c:
            r = c.get(f"https://t.me/s/{name}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            r.raise_for_status()
            html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("telegram fetch %s fail: %s", name, type(e).__name__)
        return {"error": "fetch_failed", "detail": type(e).__name__,
                "note": "Канал не открылся (закрытый/инвайт-only — нужен Client API; либо egress-ограничение сервера)."}
    # блоки сообщений; в каждом — текст, дата, ссылка, просмотры
    blocks = re.split(r'class="tgme_widget_message ', html)[1:]
    posts = []
    for b in blocks:
        mt = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>\s*(?:<div class="tgme_widget_message_footer|<div class="tgme_widget_message_bubble|$)', b, re.S)
        text = _clean(mt.group(1)) if mt else ""
        link_m = re.search(r'tgme_widget_message_date[^>]+href="(https://t\.me/[^"]+)"', b)
        date_m = re.search(r'<time[^>]+datetime="([^"]+)"', b)
        views_m = re.search(r'tgme_widget_message_views"[^>]*>([^<]+)<', b)
        if text or link_m:
            posts.append({
                "text": text[:1200],
                "url": link_m.group(1) if link_m else None,
                "date": date_m.group(1) if date_m else None,
                "views": views_m.group(1).strip() if views_m else None,
            })
    posts = posts[-limit:][::-1]  # свежие сверху
    title_m = re.search(r'tgme_channel_info_header_title[^>]*>.*?>([^<]+)<', html, re.S) \
        or re.search(r'<meta property="og:title" content="([^"]+)"', html)
    return {"channel": name, "title": title_m.group(1).strip() if title_m else name,
            "posts": posts, "count": len(posts)}
