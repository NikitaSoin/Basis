import os
import logging
from datetime import datetime, timezone
from anthropic import Anthropic
from app.db.session import SessionLocal
from app.models.market import MarketOverview, OverviewType

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        import httpx
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY не задан")

        proxy_url = os.environ.get("ANTHROPIC_PROXY_URL")
        logger.info("Anthropic client init: base_url=%s", proxy_url or "не задан (прямой)")

        http_client = httpx.Client(timeout=httpx.Timeout(120.0))
        kwargs = dict(api_key=key, http_client=http_client)
        if proxy_url:
            # Cloudflare Worker — это URL-прокси, не SOCKS/HTTP. Используем base_url.
            kwargs["base_url"] = proxy_url
        _client = Anthropic(**kwargs)
    return _client


def check_anthropic_connectivity() -> dict:
    """Проверяет доступность Anthropic API — используется в диагностическом endpoint."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    proxy_url = os.environ.get("ANTHROPIC_PROXY_URL")
    result = {
        "api_key_set": bool(key),
        "proxy_set": bool(proxy_url),
        "proxy_host": proxy_url if proxy_url else None,
        "status": "unknown",
        "error": None,
    }
    if not key:
        result["status"] = "error"
        result["error"] = "ANTHROPIC_API_KEY не задан"
        return result
    try:
        client = _get_client()
        # Минимальный запрос для проверки доступности
        client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    return result


_PROMPTS = {
    "express": (
        "Напиши экспресс-обзор российского фондового рынка (MOEX) в формате аналитической заметки. "
        "Включи: 3–5 ключевых факторов, которые влияют на рынок прямо сейчас (ставка ЦБ, нефть, геополитика, корпоративные события), "
        "краткую оценку настроений рынка (риск-он / риск-офф), один-два конкретных тикера в фокусе. "
        "Пиши уверенно, как аналитик который объясняет текущую ситуацию клиенту. "
        "Объём — 200–300 слов. Без markdown-заголовков, сплошным текстом."
    ),
    "detailed": (
        "Напиши детальный аналитический обзор российского фондового рынка (MOEX). "
        "Структура: (1) Общий рыночный фон и ключевые драйверы недели, "
        "(2) Разбор по секторам — нефтегаз, банки, технологии, металлы, ритейл, "
        "(3) Топ-3 идеи с кратким обоснованием, "
        "(4) Риски для рынка на ближайший месяц. "
        "Пиши как старший аналитик для клиентов private banking. "
        "Объём — 400–600 слов. Без markdown, структурируй абзацами."
    ),
    "deep": (
        "Напиши глубокий инвестиционный обзор российского рынка (MOEX). "
        "Охвати: макроэкономический контекст (ставка ЦБ, инфляция, курс рубля, цены на нефть), "
        "геополитические факторы и их влияние на конкретные сектора, "
        "технический анализ индекса MOEX (ключевые уровни, тренд, объёмы), "
        "секторальный анализ с конкретными именами компаний, "
        "инвестиционные идеи с горизонтом 3–12 месяцев и обоснованием. "
        "Объём — 700–1000 слов. Профессиональный аналитический стиль. Без markdown."
    ),
}


def generate_market_overview(overview_type: str) -> MarketOverview:
    client = _get_client()
    prompt = _PROMPTS.get(overview_type, _PROMPTS["express"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=(
            "Ты — старший аналитик инвестиционной платформы InBasis. "
            "Пиши на русском языке. Опирайся на свои знания о российском фондовом рынке. "
            "Не используй markdown-заголовки (#, ##). Структурируй текст абзацами."
        ),
        messages=[{"role": "user", "content": prompt}],
    )

    content = ""
    for block in response.content:
        if hasattr(block, "text") and block.text:
            content = block.text

    db = SessionLocal()
    try:
        overview = MarketOverview(
            overview_type=OverviewType(overview_type),
            content=content,
            period=today,
        )
        db.add(overview)
        db.commit()
        db.refresh(overview)
        return overview
    finally:
        db.close()
