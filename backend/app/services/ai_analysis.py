import json
import os
from anthropic import Anthropic
from app.models.company import Company

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in environment")
        _client = Anthropic(api_key=api_key)
    return _client


_SYSTEM_PROMPT = """\
Ты — старший инвестиционный аналитик с опытом работы на российском и мировом фондовых рынках. \
Твоя задача — формировать структурированный аналитический разбор публичных компаний для частных инвесторов.

Ты отвечаешь ТОЛЬКО валидным JSON без каких-либо пояснений, markdown-блоков или текста вне JSON. \
Структура ответа строго фиксирована:
{
  "business_model": {"text": "<строка>"},
  "financials": {"text": "<строка>"},
  "competitors": {"text": "<строка>"},
  "macro_economy": {"text": "<строка>"},
  "global_economy": {"text": "<строка>"},
  "geopolitics": {"text": "<строка>"},
  "technical_analysis": {"text": "<строка>"},
  "bull_case": ["<строка>", "<строка>", "<строка>"],
  "bear_case": ["<строка>", "<строка>", "<строка>"],
  "risks": ["<строка>", "<строка>", "<строка>"],
  "fair_price": "<число с двумя знаками после запятой>",
  "analyst_note": "<строка>"
}

Правила:
- Каждое текстовое поле — 2–4 предложения, конкретно и по делу.
- bull_case, bear_case, risks — ровно по 3 пункта, каждый 1 предложение.
- fair_price — справедливая цена акции в рублях, только число (например "312.50").
- analyst_note — краткий вывод аналитика, 1–2 предложения.
- Не выдумывай данные — если точных цифр нет, давай обоснованные диапазонные оценки.
"""


def generate_company_analysis(company: Company) -> dict:
    """Call Claude API and return parsed analysis dict for saving to DB."""
    client = _get_client()

    last_price_str = (
        f"Последняя известная цена: {company.last_price} руб."
        if getattr(company, "last_price", None)
        else "Котировки не загружены."
    )

    user_message = (
        f"Сделай инвестиционный разбор компании:\n"
        f"Тикер: {company.ticker}\n"
        f"Название: {company.name}\n"
        f"Сектор: {company.sector or 'не указан'}\n"
        f"Описание: {company.description or 'не указано'}\n"
        f"{last_price_str}\n\n"
        f"Верни ответ строго в формате JSON, описанном в системном промпте."
    )

    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        response = stream.get_final_message()

    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text = block.text
            break

    return json.loads(raw_text)
