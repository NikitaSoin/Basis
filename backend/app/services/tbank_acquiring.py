"""Интернет-эквайринг Т-Бизнеса — сценарий non-PCI (платёжная форма банка).

Как это работает у нас: бэкенд зовёт Init → банк отдаёт PaymentURL → человек
платит на форме банка (карту мы не видим и не храним, поэтому PCI DSS нас не
касается) → банк дёргает наш NotificationURL и/или возвращает человека на
SuccessURL. Начисление подписки делает ТОЛЬКО бэкенд, увидев подтверждённый
статус, — возврат на SuccessURL сам по себе ничего не подтверждает (его легко
открыть руками).

Контракт сверен практикой на демо-терминале 2026-08-26, а не по памяти:
  POST https://securepay.tbank.ru/v2/Init      → {"Success":true,"Status":"NEW",
                                                  "PaymentId":…,"PaymentURL":…}
  POST https://securepay.tbank.ru/v2/GetState  → {"Success":true,"Status":…}
🔴 Домен именно `securepay.tbank.ru`. Исторический `securepay.tinkoff.ru` в
проверке молчал (TLS-таймаут) — если увидишь его в чужих примерах, не переноси.

Подпись (Token): берутся ТОЛЬКО корневые пары ключ-значение (вложенные объекты и
массивы — Receipt, DATA — не участвуют), добавляется Password, ключи сортируются
по алфавиту, значения склеиваются подряд, от строки берётся SHA-256 в hex.
"""
from __future__ import annotations

import hashlib
import logging
import os

import httpx

logger = logging.getLogger(__name__)

API_URL = os.getenv("TBANK_API_URL", "https://securepay.tbank.ru/v2").rstrip("/")
TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY", "")
PASSWORD = os.getenv("TBANK_PASSWORD", "")
TIMEOUT = float(os.getenv("TBANK_TIMEOUT", "20"))


class AcquiringError(RuntimeError):
    """Банк ответил отказом или не ответил вовсе."""

    def __init__(self, message: str, code: str | None = None, details: str | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


def configured() -> bool:
    """Есть ли ключи. Без них платёжные ручки обязаны честно говорить «не
    настроено», а не падать пятисоткой на первом же обращении."""
    return bool(TERMINAL_KEY and PASSWORD)


def is_demo() -> bool:
    """Демо-терминал банка (суффикс DEMO) — деньги не списываются."""
    return TERMINAL_KEY.upper().endswith("DEMO")


def _stringify(value) -> str:
    """🔴 Булевы значения в подписи — строчными `true`/`false`, как в JSON.
    Python отдаёт `True`/`False` с большой буквы, и подпись нотификации
    (там приходит Success: true) не сошлась бы ни разу."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def make_token(params: dict, password: str | None = None) -> str:
    """Подпись запроса/нотификации. Вложенные структуры и сам Token исключаются."""
    flat = {k: v for k, v in params.items()
            if k != "Token" and not isinstance(v, (dict, list)) and v is not None}
    flat["Password"] = password or PASSWORD
    raw = "".join(_stringify(flat[k]) for k in sorted(flat))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _call(method: str, payload: dict) -> dict:
    if not configured():
        raise AcquiringError("эквайринг не настроен: нет TBANK_TERMINAL_KEY/TBANK_PASSWORD")
    body = dict(payload)
    body["TerminalKey"] = TERMINAL_KEY
    body["Token"] = make_token(body)
    url = f"{API_URL}/{method}"
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(url, json=body, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError as e:
        # Сетевой отказ отличается от отказа банка: у платёжного шлюза это чаще
        # всего заблокированный egress (та же история, что была с LLM-провайдером),
        # и разбираться надо с сетью инстанса, а не с параметрами платежа.
        logger.exception("Эквайринг: %s не ответил", url)
        raise AcquiringError(f"платёжный шлюз недоступен: {type(e).__name__}") from e
    if not data.get("Success"):
        raise AcquiringError(data.get("Message") or "банк отклонил запрос",
                             code=str(data.get("ErrorCode") or ""),
                             details=data.get("Details"))
    return data


def init_payment(*, order_id: str, amount_kopecks: int, description: str,
                 success_url: str | None = None, fail_url: str | None = None,
                 notification_url: str | None = None, customer_email: str | None = None,
                 receipt: dict | None = None) -> dict:
    """Создать платёж. Возвращает {PaymentId, PaymentURL, Status}.

    🔴 Сумму и товар задаёт СЕРВЕР. Принимать их из браузера нельзя — иначе
    подписка покупается за рубль правкой запроса в консоли."""
    payload: dict = {
        "Amount": int(amount_kopecks),
        "OrderId": order_id,
        "Description": description[:250],
    }
    if success_url:
        payload["SuccessURL"] = success_url
    if fail_url:
        payload["FailURL"] = fail_url
    if notification_url:
        payload["NotificationURL"] = notification_url
    if customer_email:
        # DATA не участвует в подписи (вложенный объект), но банк присылает по
        # нему чек и показывает почту в личном кабинете.
        payload["DATA"] = {"Email": customer_email}
    if receipt:
        payload["Receipt"] = receipt
    return _call("Init", payload)


def get_state(payment_id: str) -> dict:
    """Статус платежа глазами банка — источник истины перед начислением."""
    return _call("GetState", {"PaymentId": str(payment_id)})


def cancel_payment(payment_id: str, amount_kopecks: int | None = None) -> dict:
    """Возврат денег (метод Cancel).

    Один метод на три случая — банк сам выбирает по текущему статусу платежа:
    отмена до списания (AUTHORIZED → REVERSED) и возврат уже списанных
    (CONFIRMED → REFUNDED). Без суммы возвращается всё, с суммой — частично
    (PARTIAL_REFUNDED).

    Возврат — необратимая операция с чужими деньгами, поэтому наружу она
    выведена только под отладочным токеном, а не в открытую ручку."""
    payload: dict = {"PaymentId": str(payment_id)}
    if amount_kopecks:
        payload["Amount"] = int(amount_kopecks)
    return _call("Cancel", payload)


def verify_notification(payload: dict) -> bool:
    """Подпись нотификации. Без этой проверки любой, кто знает адрес вебхука,
    выпишет себе подписку обычным POST-запросом."""
    got = str(payload.get("Token") or "")
    if not got or not configured():
        return False
    expected = make_token(payload)
    # hmac.compare_digest не нужен: сравниваем два hex-дайджеста, но сравнение
    # всё равно делаем постоянного времени — привычка дешевле инцидента.
    import hmac
    return hmac.compare_digest(expected, got)


def build_receipt(email: str | None, phone: str | None, description: str,
                  amount_kopecks: int) -> dict | None:
    """Чек по 54-ФЗ. Нужен, когда к терминалу подключена онлайн-касса; на демо
    без кассы Init проходит и без него, поэтому собираем только если включено
    настройкой и есть контакт покупателя (без него чек отправить некуда)."""
    if os.getenv("TBANK_RECEIPT", "0") not in ("1", "true", "True"):
        return None
    if not (email or phone):
        return None
    receipt: dict = {
        "Taxation": os.getenv("TBANK_TAXATION", "usn_income"),
        "Items": [{
            "Name": description[:128],
            "Price": int(amount_kopecks),
            "Quantity": 1,
            "Amount": int(amount_kopecks),
            "Tax": os.getenv("TBANK_VAT", "none"),
            "PaymentMethod": "full_payment",
            "PaymentObject": "service",
        }],
    }
    if email:
        receipt["Email"] = email
    if phone:
        receipt["Phone"] = phone
    return receipt
