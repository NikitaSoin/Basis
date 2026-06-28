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


def _timeout() -> "httpx.Timeout":
    try:
        total = float(os.environ.get("LLM_TIMEOUT", "60"))
    except ValueError:
        total = 60.0
    # connect_timeout короткий — если сервер недоступен, падаем быстро (не держим тред 3 мин)
    return httpx.Timeout(total, connect=8.0)


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
                            json_mode: bool, max_tokens: int, temperature: float,
                            thinking: bool, model_override: str | None = None) -> str:
    base_url, _, _ = _PROVIDERS[provider]
    # Релей через Cloudflare Worker (как ANTHROPIC_PROXY_URL): на этом инстансе egress
    # к api.deepseek.com режется на TLS (TCP проходит, TLS молча в таймаут — подтверждено
    # raw-socket + openssl с внешнего узла проходит). DEEPSEEK_BASE_URL направляет вызов
    # на воркер, который форвардит к DeepSeek со своей сети. Без релея DeepSeek недостижим.
    if provider == "deepseek" and os.environ.get("DEEPSEEK_BASE_URL"):
        base_url = os.environ["DEEPSEEK_BASE_URL"].rstrip("/")
    model = model_override or _model(provider)
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
    # DeepSeek v4-flash — гибрид thinking/non-thinking. Для механических задач
    # (фильтр/выжимка/категоризация/извлечение чисел) рассуждение НЕ нужно: оно
    # жжёт токены и роняет content. Явно выключаем (×8 меньше токенов, сразу JSON).
    # Параметр специфичен для DeepSeek — другим провайдерам не шлём.
    if provider == "deepseek":
        payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
    headers = {"Authorization": f"Bearer {_api_key(provider)}",
               "Content-Type": "application/json"}
    from app.services.http_util import make_client
    # make_client — клампинг TCP MSS (обход MTU black hole к api.deepseek.com).
    with make_client(timeout=_timeout()) as client:
        resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    msg = data["choices"][0]["message"]
    # Reasoning-модели (напр. deepseek-v4-flash) кладут размышления в
    # reasoning_content и при нехватке max_tokens отдают ПУСТОЙ content. Если так —
    # подстраховываемся текстом reasoning_content (из него извлечём JSON ниже).
    return msg.get("content") or msg.get("reasoning_content") or ""


def _call_claude(system_prompt: str, user_content: str, json_mode: bool,
                 max_tokens: int, temperature: float) -> str:
    from anthropic import Anthropic
    proxy = os.environ.get("ANTHROPIC_PROXY_URL") or None
    client = Anthropic(api_key=_api_key("claude"),
                       base_url=proxy if proxy else None,
                       timeout=_timeout(), max_retries=0)
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
             max_tokens: int = 4096, temperature: float = 0.2, thinking: bool = False,
             model: str | None = None):
    """Единая точка вызова LLM.

    system_prompt — СТАБИЛЬНЫЙ префикс (для кэша провайдера); user_content —
    изменчивая часть. json_mode=True → вернёт распарсенный dict/list; иначе str.
    thinking — режим рассуждения (только DeepSeek): по умолчанию ВЫКЛ, т.к. наши
    пайплайны решают механические задачи по чёткому промпту; включай (thinking=True)
    только там, где реально нужно рассуждение. При сбое повторяет _retries() раз.
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
                                              json_mode, max_tokens, temperature, thinking, model)
            if not json_mode:
                return raw
            cleaned = _strip_json_fence(raw)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # Подстраховка для reasoning-моделей: вытащить крайний JSON-объект
                # {...} из «грязного» текста (reasoning_content и т.п.).
                lo, hi = cleaned.find("{"), cleaned.rfind("}")
                if lo != -1 and hi > lo:
                    return json.loads(cleaned[lo:hi + 1])
                raise
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, Exception) as e:  # noqa: BLE001
            last_err = e
            # Логируем БЕЗ утечки ключа (httpx не печатает заголовки в str(e)).
            logger.warning("LLM(%s) попытка %d/%d не удалась: %s",
                           provider, attempt + 1, _retries() + 1, type(e).__name__)
            if attempt < _retries():
                time.sleep(1.5 * (attempt + 1))
    raise LLMError(f"LLM({provider}) недоступен после повторов: {type(last_err).__name__}")


def pro_model() -> str:
    """Имя «думающей» модели DeepSeek (reasoning) для Интерпретатора/интерпретаций.
    Из env LLM_MODEL_PRO или дефолт deepseek-v4-pro."""
    return (os.environ.get("LLM_MODEL_PRO") or "deepseek-v4-pro").strip()


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
