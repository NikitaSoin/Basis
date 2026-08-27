"""Оплата подписки — интернет-эквайринг Т-Бизнеса (сценарий non-PCI).

Три ручки наружу: создать платёж, принять нотификацию банка, отдать статус
заказа фронту. Плюс справочная — что вообще продаётся и включён ли приём оплаты.

🔴 ЧТО ЗДЕСЬ НАМЕРЕННО НЕ ДЕЛАЕТСЯ: этот код НЕ включает платные границы.
Владелец (см. память проекта) держит платформу открытой; оплата даёт запись о
подписке, а что подписка закрывает — отдельное решение и отдельные флаги.
Подключение эквайринга и включение лимитов — разные вещи, и вторая тут не живёт.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.session import get_db
from app.models.payment import Payment
from app.models.user import SubscriptionType, User
from app.services import tbank_acquiring as tb

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

FRONT_BASE = os.environ.get("FRONTEND_BASE_URL", "https://inbasis.ru").rstrip("/")
# Адрес, на который банк шлёт нотификации. Задаётся отдельно от фронта: это
# ДРУГОЕ приложение (API), и на бою у него свой домен.
API_BASE = os.environ.get("API_BASE_URL", "").rstrip("/")

# Цены в КОПЕЙКАХ — настройкой, а не константой в коде: цену меняет владелец, и
# ради неё не должно требоваться выкатывать релиз. Значения по умолчанию равны
# тем, что показывает витрина тарифов (frontend account/tierCatalog.js: 390 ₽/мес,
# 1990 ₽/год) — расхождение цены на экране и в списании недопустимо.
PLANS = {
    "month": {"kopecks": int(os.getenv("SUBSCRIPTION_PRICE_MONTH_KOPECKS", "39000")),
              "months": 1, "title": "Basis Max — подписка на месяц"},
    "year": {"kopecks": int(os.getenv("SUBSCRIPTION_PRICE_YEAR_KOPECKS", "199000")),
             "months": 12, "title": "Basis Max — подписка на год"},
}
DEFAULT_PLAN = "month"

# Статусы банка, при которых деньги получены. AUTHORIZED — двухстадийная схема
# (деньги захолдированы, нужен Confirm); в одностадийной приходит сразу
# CONFIRMED. Начисляем на обоих: для клиента разницы нет, а Confirm при
# двухстадийке делает банк по настройке терминала.
PAID_STATUSES = {"CONFIRMED", "AUTHORIZED"}
FAILED_STATUSES = {"REJECTED", "CANCELED", "DEADLINE_EXPIRED", "REVERSED", "REFUNDED"}
# Возврат денег. REVERSED — отмена до списания (по захолдированному платежу),
# REFUNDED — возврат уже списанных, PARTIAL_REFUNDED — частичный.
# 🔴 Без обработки этих статусов возврат превращался в подарок: деньги ушли
# обратно, а подписка осталась бы висеть до конца оплаченного срока.
REFUND_STATUSES = {"REFUNDED", "REVERSED", "PARTIAL_REFUNDED"}


def _granted_days(months: int) -> int:
    """Сколько дней даёт оплата. Год — 365, а не 12×30: за «двенадцать месяцев
    по тридцать» человек недополучил бы пять оплаченных дней."""
    return 365 if months >= 12 else 30 * max(1, months)


def _new_order_id(user_id: int) -> str:
    """Уникален и читаем в выписке: видно пользователя и когда платил."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"basis-{user_id}-{stamp}-{secrets.token_hex(3)}"


def _grant_subscription(db: Session, payment: Payment) -> bool:
    """Начислить подписку. Возвращает True, если начислили именно сейчас.

    🔴 Идемпотентность: банк повторяет нотификацию, пока не получит "OK", и
    без отметки granted_at каждая повторная доставка добавляла бы месяц."""
    if payment.granted_at is not None:
        return False
    user = db.get(User, payment.user_id)
    if user is None:
        logger.error("Платёж %s: пользователь %s исчез", payment.order_id, payment.user_id)
        return False
    now = datetime.now(timezone.utc)
    # Продлеваем от текущей даты окончания, если она ещё не прошла: человек,
    # оплативший вторым месяцем заранее, не должен терять остаток первого.
    base = user.subscription_expires_at
    if base is None or base <= now:
        base = now
    elif base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    user.subscription_type = SubscriptionType.premium
    user.subscription_expires_at = base + timedelta(days=_granted_days(payment.months))
    payment.granted_at = now
    db.commit()
    logger.info("Платёж %s: подписка до %s (пользователь %s)",
                payment.order_id, user.subscription_expires_at, user.id)
    _notify_user(user, payment, kind="paid")
    return True


def _revoke_subscription(db: Session, payment: Payment) -> bool:
    """Снять подписку при возврате денег. Возвращает True, если сняли сейчас.

    Отматываем ровно то, что выдавали этим платежом: если человек успел
    доплатить второй период, у него останется остаток от него, а не ноль."""
    if payment.granted_at is None:
        return False   # начисления не было — отзывать нечего
    user = db.get(User, payment.user_id)
    if user is None:
        return False
    now = datetime.now(timezone.utc)
    expires = user.subscription_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    new_expires = (expires - timedelta(days=_granted_days(payment.months))) if expires else None
    if new_expires is None or new_expires <= now:
        user.subscription_type = SubscriptionType.free
        user.subscription_expires_at = None
    else:
        user.subscription_expires_at = new_expires
    payment.granted_at = None          # снова «не начислено» — повторный возврат не отмотает дважды
    db.commit()
    logger.info("Платёж %s: возврат, подписка → %s (пользователь %s)",
                payment.order_id, user.subscription_expires_at, user.id)
    _notify_user(user, payment, kind="refunded")
    return True


def _notify_user(user: User, payment: Payment, kind: str) -> None:
    """Письмо от ПЛАТФОРМЫ о судьбе платежа.

    Банк присылает своё письмо о списании, но это письмо банка: в нём нет ни
    слова про то, что подписка включена и до какого числа. Человек не должен
    догадываться, сработало ли у нас, — поэтому пишем сами.

    Отправка не должна ронять обработку платежа: деньги важнее письма, и если
    почта недоступна, платёж всё равно засчитан."""
    try:
        from app.services.email_codes import send_mail
        amount = f"{payment.amount / 100:,.0f}".replace(",", " ")
        if kind == "paid":
            until = (user.subscription_expires_at.strftime("%d.%m.%Y")
                     if user.subscription_expires_at else "—")
            subject = "Basis — оплата получена, тариф Max активен"
            body = (
                f"Оплата прошла успешно.\n\n"
                f"Тариф: Max\n"
                f"Сумма: {amount} ₽\n"
                f"Действует до: {until}\n"
                f"Номер заказа: {payment.order_id}\n\n"
                f"Тариф уже активен — заходить заново не нужно. Посмотреть срок можно в "
                f"профиле: {FRONT_BASE}/?view=profile\n\n"
                f"Если оплата была ошибочной, напишите нам в ответ на это письмо — вернём.\n\n"
                f"Basis — {FRONT_BASE}")
        else:
            subject = "Basis — возврат платежа оформлен"
            body = (
                f"Возврат по заказу {payment.order_id} на сумму {amount} ₽ оформлен.\n\n"
                f"Деньги вернутся на карту в срок, установленный банком (обычно до 3 рабочих "
                f"дней, иногда дольше — зависит от банка-эмитента).\n"
                f"Тариф Max, оплаченный этим платежом, отключён.\n\n"
                f"Basis — {FRONT_BASE}")
        send_mail(user.email, subject, body)
    except Exception:  # noqa: BLE001 — письмо не должно влиять на исход платежа
        logger.exception("Платёж %s: письмо (%s) не отправилось", payment.order_id, kind)


@router.get("/config")
def payments_config():
    """Что показывать на экране оплаты. Фронт по этому ответу решает, рисовать
    ли кнопку: если приём оплаты не настроен, кнопки быть не должно."""
    return {
        "enabled": tb.configured(),
        "demo": tb.is_demo(),
        "currency": "RUB",
        "plans": {k: {"price_rub": round(v["kopecks"] / 100, 2),
                      "price_kopecks": v["kopecks"], "months": v["months"],
                      "title": v["title"]} for k, v in PLANS.items()},
    }


@router.post("/create")
def create_payment(request: Request, period: str = DEFAULT_PLAN,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Создать платёж за подписку и отдать ссылку на форму банка.

    🔴 Из браузера принимается только ВЫБОР ТАРИФА (месяц/год) — сумма берётся
    по нему из серверной таблицы. Принимать саму сумму нельзя: подписка
    покупалась бы за рубль правкой запроса в консоли."""
    if not tb.configured():
        raise HTTPException(status_code=503, detail="Приём оплаты пока не настроен")
    plan = PLANS.get(period)
    if plan is None:
        raise HTTPException(status_code=400,
                            detail=f"Неизвестный период оплаты: {period}")

    order_id = _new_order_id(current_user.id)
    payment = Payment(order_id=order_id, user_id=current_user.id, amount=plan["kopecks"],
                      tier=SubscriptionType.premium.value, months=plan["months"],
                      status="NEW")
    db.add(payment)
    db.commit()

    api_base = API_BASE or str(request.base_url).rstrip("/")
    try:
        result = tb.init_payment(
            order_id=order_id,
            amount_kopecks=plan["kopecks"],
            description=plan["title"],
            # 🔴 Возвращаем на ЭКРАН ТАРИФОВ, а не на главную: подтверждение
            # «оплата прошла, Max до такого-то» живёт там. С возвратом на «/»
            # человек видел обычную главную и не понимал, сработало ли вообще
            # (владелец так и прогнал первый платёж — письмо от банка пришло,
            # а от платформы никакого ответа).
            success_url=f"{FRONT_BASE}/?view=pricing&payment=success&order={order_id}",
            fail_url=f"{FRONT_BASE}/?view=pricing&payment=fail&order={order_id}",
            notification_url=f"{api_base}/api/payments/notification",
            customer_email=current_user.email,
            receipt=tb.build_receipt(current_user.email, None, plan["title"], plan["kopecks"]),
        )
    except tb.AcquiringError as e:
        payment.status = "INIT_FAILED"
        payment.error_code = e.code
        payment.error_message = str(e)[:500]
        db.commit()
        logger.warning("Платёж %s: Init не прошёл (%s)", order_id, e)
        raise HTTPException(status_code=502, detail=f"Банк не принял платёж: {e}") from e

    payment.payment_id = str(result.get("PaymentId") or "") or None
    payment.payment_url = result.get("PaymentURL")
    payment.status = result.get("Status") or "NEW"
    payment.raw = result
    db.commit()
    return {"order_id": order_id, "payment_url": payment.payment_url,
            "payment_id": payment.payment_id, "status": payment.status,
            "amount_rub": round(plan["kopecks"] / 100, 2), "months": plan["months"],
            "demo": tb.is_demo()}


@router.post("/notification")
async def payment_notification(request: Request, db: Session = Depends(get_db)):
    """Вебхук банка. Отвечать нужно ровно строкой OK — иначе банк будет
    повторять доставку.

    🔴 Подпись проверяется ДО любых действий: без неё адрес вебхука сам по себе
    становится способом выписать себе подписку обычным POST-запросом."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — банк прислал не JSON
        logger.warning("Нотификация: тело не разобралось")
        raise HTTPException(status_code=400, detail="bad payload")

    if not tb.verify_notification(payload):
        logger.warning("Нотификация: подпись не сошлась, order=%s", payload.get("OrderId"))
        raise HTTPException(status_code=403, detail="bad token")

    order_id = str(payload.get("OrderId") or "")
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if payment is None:
        # Чужой или устаревший заказ. Отвечаем OK: повторять доставку незачем,
        # у нас такого платежа всё равно нет.
        logger.warning("Нотификация: заказ %s неизвестен", order_id)
        return Response(content="OK", media_type="text/plain")

    status_ = str(payload.get("Status") or "")
    payment.status = status_ or payment.status
    payment.payment_id = str(payload.get("PaymentId") or payment.payment_id or "") or None
    payment.raw = payload
    if payload.get("ErrorCode") and str(payload["ErrorCode"]) != "0":
        payment.error_code = str(payload["ErrorCode"])[:16]
    db.commit()

    if status_ in PAID_STATUSES:
        # Перепроверяем у банка: нотификация — уведомление, а деньги подтверждает
        # состояние платежа. Если запрос не прошёл, доверяем подписанной
        # нотификации (подпись мы уже проверили) — иначе оплативший останется
        # без подписки из-за нашей сетевой проблемы.
        confirmed = True
        if payment.payment_id:
            try:
                state = tb.get_state(payment.payment_id)
                confirmed = str(state.get("Status") or "") in PAID_STATUSES
                if not confirmed:
                    logger.warning("Платёж %s: нотификация %s, а GetState — %s",
                                   order_id, status_, state.get("Status"))
            except tb.AcquiringError as e:
                logger.warning("Платёж %s: GetState недоступен (%s), верим нотификации",
                               order_id, e)
        if confirmed:
            _grant_subscription(db, payment)
    elif status_ in REFUND_STATUSES:
        # Возврат оформляется в личном кабинете банка (или нашей ручкой ниже) —
        # к нам он приходит вот этой нотификацией, и подписку надо снять.
        _revoke_subscription(db, payment)
    return Response(content="OK", media_type="text/plain")


@router.get("/status/{order_id}")
def payment_status(order_id: str, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    """Статус заказа для экрана «спасибо»: человек вернулся с формы банка, а
    нотификация могла ещё не дойти — тогда спрашиваем банк напрямую.

    Возврат на SuccessURL сам по себе НЕ считается оплатой."""
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    if payment is None or payment.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Платёж не найден")

    if payment.granted_at is None and payment.payment_id and payment.status not in FAILED_STATUSES:
        try:
            state = tb.get_state(payment.payment_id)
            payment.status = str(state.get("Status") or payment.status)
            payment.raw = state
            db.commit()
            if payment.status in PAID_STATUSES:
                _grant_subscription(db, payment)
        except tb.AcquiringError as e:
            logger.info("Статус %s: банк не ответил (%s)", order_id, e)

    return {
        "order_id": payment.order_id,
        "status": payment.status,
        "paid": payment.granted_at is not None,
        "amount_rub": round(payment.amount / 100, 2),
        "subscription_expires_at": (current_user.subscription_expires_at.isoformat()
                                    if current_user.subscription_expires_at else None),
        "error": payment.error_message,
    }
