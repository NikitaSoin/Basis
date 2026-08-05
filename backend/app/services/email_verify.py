"""Подтверждение почты ССЫЛКОЙ из письма (владелец 2026-08-06).

Отличие от email_codes (код при регистрации): регистрация НЕ блокируется —
аккаунт создаётся сразу, письмо со ссылкой уходит следом, подтвердить можно
в любое удобное время (ссылка бессрочная — решение владельца). Статус виден
в профиле: подтверждена/не подтверждена + повторная отправка.

Токен — подписанный JWT (тот же секрет, что авторизация) с purpose-клеймом,
БЕЗ exp. В токен вшит email: если адрес аккаунта когда-нибудь сменится,
старая ссылка перестанет подходить (email не совпадёт) — «вечность» ссылки
не превращается в вечный доступ к чужому решению.

Ссылка ведёт на ФРОНТ (inbasis.ru), не на API: адрес API периодически
меняется при пересоздании приложения Timeweb, домен фронта стабилен.

Rate-limit повторной отправки — та же таблица verification_codes
(purpose='verify_link', хранится только факт отправки для кулдауна).
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import ALGORITHM, SECRET_KEY
from app.models.user import User
from app.services.email_codes import is_verification_enabled, send_mail

logger = logging.getLogger(__name__)

RESEND_COOLDOWN_SEC = 60
MAX_SENDS_PER_HOUR = 5
_PURPOSE = "verify_link"
FRONT_BASE = os.environ.get("FRONTEND_BASE_URL", "https://inbasis.ru")


def make_verify_token(user: User) -> str:
    return jwt.encode({"sub": str(user.id), "purpose": _PURPOSE, "email": user.email},
                      SECRET_KEY, algorithm=ALGORITHM)


def _rate_limit(db: Session, email: str) -> None:
    """ValueError с человекочитаемой причиной, если слать пока нельзя."""
    now = datetime.now(timezone.utc)
    row = db.execute(text(
        "SELECT MAX(created_at) AS last, COUNT(*) FILTER (WHERE created_at > :hour_ago) AS cnt "
        "FROM verification_codes WHERE destination = :d AND purpose = :p"),
        {"d": email, "p": _PURPOSE, "hour_ago": now - timedelta(hours=1)}).one()
    if row.last is not None:
        last = row.last if row.last.tzinfo else row.last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < RESEND_COOLDOWN_SEC:
            raise ValueError("Письмо уже отправлено. Повторно — через минуту.")
    if (row.cnt or 0) >= MAX_SENDS_PER_HOUR:
        raise ValueError("Слишком много писем. Попробуйте через час.")


def send_verification_link(db: Session, user: User, enforce_limit: bool = True) -> dict:
    """Шлёт письмо со ссылкой. ValueError — лимит/сбой отправки."""
    if not is_verification_enabled():
        return {"status": "disabled"}
    if user.email_verified:
        return {"status": "already"}
    email = user.email.strip().lower()
    if enforce_limit:
        _rate_limit(db, email)
    link = f"{FRONT_BASE}/?view=verify-email&token={make_verify_token(user)}"
    body = (
        "Здравствуйте!\n\n"
        "Вы зарегистрировались на Basis (inbasis.ru). Чтобы подтвердить адрес почты, "
        "откройте ссылку — это можно сделать в любое удобное время:\n\n"
        f"{link}\n\n"
        "Если вы не регистрировались на inbasis.ru — просто игнорируйте это письмо, "
        "адрес не будет подтверждён.\n\n"
        "— Basis, независимая аналитика российского рынка"
    )
    try:
        send_mail(email, "Basis — подтвердите адрес почты", body)
    except Exception as e:  # noqa: BLE001
        logger.error("email_verify: отправка на %s не удалась: %s", email, e)
        raise ValueError("Не удалось отправить письмо. Попробуйте позже.")
    # факт отправки — для кулдауна (code_hash не используется ссылкой)
    db.execute(text(
        "INSERT INTO verification_codes (channel, destination, purpose, code_hash, attempts, expires_at, created_at) "
        "VALUES ('email', :d, :p, '', 0, :exp, :now)"),
        {"d": email, "p": _PURPOSE,
         "exp": datetime.now(timezone.utc) + timedelta(days=1),
         "now": datetime.now(timezone.utc)})
    db.commit()
    return {"status": "sent"}


def apply_verify_token(db: Session, token: str) -> dict:
    """Проверяет токен и отмечает почту подтверждённой. Идемпотентно.
    Возвращает {"status": "ok"|"already"}; ValueError — токен не годится."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise ValueError("Ссылка повреждена или недействительна.")
    if payload.get("purpose") != _PURPOSE:
        raise ValueError("Ссылка недействительна.")
    user = db.get(User, int(payload.get("sub", 0) or 0))
    if user is None or user.email.strip().lower() != str(payload.get("email", "")).strip().lower():
        raise ValueError("Ссылка не подходит к этому аккаунту.")
    if user.email_verified:
        return {"status": "already", "email": user.email}
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "ok", "email": user.email}
