"""Коды подтверждения при регистрации: генерация, отправка на email, проверка.

Включение фичи — НАЛИЧИЕМ SMTP-конфига в env (секреты только в .env, как всегда):
  SMTP_HOST, SMTP_PORT (465 = SSL, иначе STARTTLS), SMTP_USER, SMTP_PASSWORD,
  SMTP_FROM (по умолчанию = SMTP_USER).
Без конфига is_verification_enabled() == False и регистрация работает по-старому
(email+пароль без кода) — фича деградирует честно, ничего не ломает. Как только
владелец кладёт SMTP-креды в env — подтверждение включается само, без деплоя.

SMS-канал: таблица verification_codes уже умеет channel='sms', но отправка
НЕ реализована — нужен платный SMS-провайдер (SMS.ru / SMSC / Twilio: аккаунт,
API-ключ, имя отправителя) — это решение владельца. До этого телефонов в UI нет.

Безопасность: код 6 цифр (secrets), хранится только sha256; TTL 15 минут;
максимум 5 попыток ввода на код; повторная отправка не чаще раза в 60 сек и
не больше 5 кодов на адрес за час.
"""
import hashlib
import logging
import os
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CODE_TTL_MIN = 15
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SEC = 60
MAX_CODES_PER_HOUR = 5


def is_verification_enabled() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER")
                and os.environ.get("SMTP_PASSWORD"))


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _send_email(to_addr: str, code: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    from_addr = os.environ.get("SMTP_FROM", user)

    body = (
        f"Ваш код подтверждения: {code}\n\n"
        f"Код действует {CODE_TTL_MIN} минут. Введите его в форме регистрации Basis.\n"
        "Если вы не регистрировались на inbasis.ru — просто игнорируйте это письмо.\n"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Basis — код подтверждения {code}"
    msg["From"] = formataddr(("Basis", from_addr))
    msg["To"] = to_addr

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as s:
            s.login(user, password)
            s.sendmail(from_addr, [to_addr], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
            s.sendmail(from_addr, [to_addr], msg.as_string())


def request_code(db: Session, email: str) -> dict:
    """Генерит и шлёт код. Возвращает {"status": "sent"} либо кидает ValueError
    с человекочитаемой причиной (кулдаун/лимит/сбой отправки)."""
    email = email.strip().lower()
    now = datetime.now(timezone.utc)

    row = db.execute(text(
        "SELECT MAX(created_at) AS last, COUNT(*) FILTER (WHERE created_at > :hour_ago) AS cnt "
        "FROM verification_codes WHERE destination = :d AND purpose = 'register'"),
        {"d": email, "hour_ago": now - timedelta(hours=1)}).one()
    if row.last is not None:
        last = row.last if row.last.tzinfo else row.last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < RESEND_COOLDOWN_SEC:
            raise ValueError("Код уже отправлен. Повторная отправка — через минуту.")
    if (row.cnt or 0) >= MAX_CODES_PER_HOUR:
        raise ValueError("Слишком много запросов кода. Попробуйте через час.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        _send_email(email, code)
    except Exception as e:
        logger.error("email_codes: отправка на %s не удалась: %s", email, e)
        raise ValueError("Не удалось отправить письмо. Проверьте адрес и попробуйте ещё раз.")

    # новый код инвалидирует прежние
    db.execute(text(
        "DELETE FROM verification_codes WHERE destination = :d AND purpose = 'register'"),
        {"d": email})
    db.execute(text(
        "INSERT INTO verification_codes (channel, destination, purpose, code_hash, attempts, expires_at, created_at) "
        "VALUES ('email', :d, 'register', :h, 0, :exp, :now)"),
        {"d": email, "h": _hash(code), "exp": now + timedelta(minutes=CODE_TTL_MIN), "now": now})
    db.commit()
    return {"status": "sent"}


def verify_code(db: Session, email: str, code: str) -> bool:
    """Проверяет код; расходует попытку. True — код верный (и сразу гасится)."""
    email = email.strip().lower()
    now = datetime.now(timezone.utc)
    row = db.execute(text(
        "SELECT id, code_hash, attempts, expires_at FROM verification_codes "
        "WHERE destination = :d AND purpose = 'register' ORDER BY created_at DESC LIMIT 1"),
        {"d": email}).one_or_none()
    if row is None:
        return False
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires < now or row.attempts >= MAX_ATTEMPTS:
        return False
    if row.code_hash != _hash((code or "").strip()):
        db.execute(text("UPDATE verification_codes SET attempts = attempts + 1 WHERE id = :i"),
                   {"i": row.id})
        db.commit()
        return False
    db.execute(text("DELETE FROM verification_codes WHERE id = :i"), {"i": row.id})
    db.commit()
    return True
