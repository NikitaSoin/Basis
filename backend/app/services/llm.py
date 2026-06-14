"""Провайдер-агностичная обёртка вызова LLM.

Весь код направлений Обозревателя (новости, макро, отчёты, геополитика) зовёт
ТОЛЬКО этот сервис, а не DeepSeek/Claude/OpenAI напрямую. Переключение провайдера —
смена переменной окружения LLM_PROVIDER, без правок кода направлений.

ENV:
  LLM_PROVIDER  = deepseek | claude | openai   (по умолчанию deepseek)
  LLM_MODEL     = имя модели (по умолчанию — дефолт провайдера)
  DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY
  LLM_TIMEOUT   = таймаут запроса, сек (по умолчанию 60)
  LLM_RETRIES   = число повторов при сбое (по умолчанию 2)

Заметки по стоимости:
  - DeepSeek кэширует повторяющийся ПРЕФИКС промпта (system_prompt), попадание в
    кэш ~в 50 раз дешевле. Поэтому system_prompt держим СТАБИЛЬНЫМ между вызовами
    (одинаковый текст, без меняющихся дат/счётчиков), а изменчивое кладём в
    user_content.
  - DeepSeek подключается по OpenAI-совместимому формату: base_url
    https://api.deepseek.com, модель deepseek-v4-flash (legacy deepseek-chat/
    reasoner отключаются 24.07.2026 — не используем).
"""
from __future__ import annotations

import json
import logging
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()  # ключи/настройки из .env (идемпотентно; в проде — переменные Timeweb)

logger = logging.getLogger(__name__)

# Дефолты провайдеров: (base_url, model, env-имя ключа)
_PROVIDERS = {
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com", "gpt-4o-mini", "OPENAI_API_KEY"),
    # claude обрабатывается отдельной веткой через anthropic SDK
    "claude": (None, "claude-haiku-4-5-20251001", "ANTHROPIC_API_KEY"),
}


class LLMError(RuntimeError):
    """Ошибка вызова LLM (после исчерпания повторов)."""


def _provider() -> str:
    return (os.environ.get("LLM_PROVIDER") or "deepseek").strip().lower()


def _model(provider: str) -> str:
    env_model = os.environ.get("LLM_MODEL")
    if env_model:
        return env_model.strip()
    return _PROVIDERS[provider][1]


def _api_key(provider: str) -> str:
    env_name = _PROVIDERS[provider][2]
    key = os.environ.get(env_name)
    if not key:
        raise LLMError(f"{env_name} не задан в окружении (провайдер {provider})")
    return key


def _timeout() -> float:
    try:
        return float(os.environ.get("LLM_TIMEOUT", "60"))
    except ValueError:
        return 60.0


def _retries() -> int:
    try:
        return int(os.environ.get("LLM_RETRIES", "2"))
    except ValueError:
        return 2


def _strip_json_fence(text: str) -> str:
    """Убирает ```json ... ``` обёртку, если модель её добавила вопреки запросу."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: -3]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    return t.strip()


def _call_openai_compatible(provider: str, system_prompt: str, user_content: str,
                            json_mode: bool, max_tokens: int, temperature: float) -> str:
    base_url, _, _ = _PROVIDERS[provider]
    model = _model(provider)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {_api_key(provider)}",
               "Content-Type": "application/json"}
    with httpx.Client(timeout=_timeout()) as client:
        resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_claude(system_prompt: str, user_content: str, json_mode: bool,
                 max_tokens: int, temperature: float) -> str:
    from anthropic import Anthropic
    proxy = os.environ.get("ANTHROPIC_PROXY_URL") or None
    client = Anthropic(api_key=_api_key("claude"),
                       base_url=proxy if proxy else None)
    # Просьба строгого JSON для Claude идёт текстом в system (нет response_format).
    sys = system_prompt
    if json_mode and "JSON" not in sys.upper():
        sys = sys + "\n\nОтвечай строго валидным JSON без текста вне JSON."
    msg = client.messages.create(
        model=_model("claude"),
        system=sys,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(getattr(b, "text", "") for b in msg.content)


def complete(system_prompt: str, user_content: str, *, json_mode: bool = True,
             max_tokens: int = 4096, temperature: float = 0.2):
    """Единая точка вызова LLM.

    system_prompt — СТАБИЛЬНЫЙ префикс (для кэша провайдера); user_content —
    изменчивая часть. json_mode=True → вернёт распарсенный dict/list; иначе str.
    При сбое повторяет _retries() раз с экспоненциальной паузой, затем LLMError.
    """
    provider = _provider()
    if provider not in _PROVIDERS:
        raise LLMError(f"Неизвестный LLM_PROVIDER={provider}")

    last_err: Exception | None = None
    for attempt in range(_retries() + 1):
        try:
            if provider == "claude":
                raw = _call_claude(system_prompt, user_content, json_mode, max_tokens, temperature)
            else:
                raw = _call_openai_compatible(provider, system_prompt, user_content,
                                              json_mode, max_tokens, temperature)
            if not json_mode:
                return raw
            return json.loads(_strip_json_fence(raw))
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, Exception) as e:  # noqa: BLE001
            last_err = e
            # Логируем БЕЗ утечки ключа (httpx не печатает заголовки в str(e)).
            logger.warning("LLM(%s) попытка %d/%d не удалась: %s",
                           provider, attempt + 1, _retries() + 1, type(e).__name__)
            if attempt < _retries():
                time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"LLM({provider}) недоступен после повторов: {type(last_err).__name__}")


def provider_info() -> dict:
    """Диагностика для health-эндпоинта (без секретов)."""
    p = _provider()
    base, default_model, key_env = _PROVIDERS.get(p, (None, None, None))
    return {
        "provider": p,
        "model": _model(p) if p in _PROVIDERS else None,
        "key_present": bool(os.environ.get(key_env)) if key_env else False,
        "base_url": base,
    }
