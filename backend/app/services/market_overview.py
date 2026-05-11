import os
from datetime import datetime, timezone
from anthropic import Anthropic
from app.db.session import SessionLocal
from app.models.market import MarketOverview, OverviewType

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY не задан")
        _client = Anthropic(api_key=key)
    return _client


_PROMPTS = {
    "express": (
        "Сделай краткий экспресс-обзор российского фондового рынка (MOEX) за сегодня. "
        "Найди 3–5 главных новостей и событий дня, которые влияют на рынок. "
        "Для каждой: заголовок, 1–2 предложения сути, оценка влияния (позитив/негатив/нейтрал). "
        "В конце — одно итоговое предложение про общий тон рынка. "
        "Пиши по-русски, без markdown-заголовков, сплошным читаемым текстом."
    ),
    "detailed": (
        "Сделай детальный обзор российского фондового рынка (MOEX) за сегодня. "
        "Найди 7–10 значимых новостей и событий. Разбей по секторам: нефтегаз, банки, технологии, металлы, потребительский. "
        "Для каждого события: что произошло, почему это важно для инвестора, какие бумаги под влиянием. "
        "В конце — краткий секторальный итог (2–3 предложения). "
        "Пиши по-русски, структурировано, но без markdown."
    ),
    "deep": (
        "Сделай глубокий аналитический обзор российского фондового рынка (MOEX) за сегодня. "
        "Охвати: ключевые события дня и их причины, макроэкономический контекст (ставка ЦБ, инфляция, нефть), "
        "геополитический фон, динамику по секторам, технические уровни индекса MOEX, "
        "ожидания на ближайшую неделю. "
        "Минимум 500 слов. Профессиональный аналитический стиль. По-русски."
    ),
}


def generate_market_overview(overview_type: str) -> MarketOverview:
    client = _get_client()
    prompt = _PROMPTS.get(overview_type, _PROMPTS["express"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=(
            "Ты — старший аналитик инвестиционной платформы. "
            "Используй web_search для поиска актуальных новостей российского рынка. "
            "Отвечай только на русском языке."
        ),
        messages=[{"role": "user", "content": f"Дата: {today}. {prompt}"}],
        betas=["web-search-2025-03-05"],
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
