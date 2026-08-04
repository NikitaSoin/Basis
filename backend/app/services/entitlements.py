"""Границы тарифов — ЕДИНЫЙ источник правды (бэкенд).

Владелец (2026-08-01): «пропиши эти ограничения, просто оставь их не включёнными».
Здесь описано, что именно закрыто на бесплатном тарифе, и стоит ОДИН рубильник.
Пока рубильник выключен, каждая проверка отвечает «можно» — поведение платформы
ровно такое же, как до появления этого файла.

🔴 ВКЛЮЧЕНИЕ: переменная окружения TIER_LIMITS_ENFORCED=1 (Timeweb → env приложения).
Перезапуск подхватит. Отдельно надо снять флаг на фронте — frontend/Basis/src/account/
tierCatalog.js::FREE_LIMITS_ENFORCED (он же убирает плашку «пока всё открыто» со
страницы тарифов). ДВА флага намеренно: бэкенд закрывает данные, фронт перестаёт
обещать открытость; включать их надо вместе.

Почему через env, а не константой в коде: включение/выключение продуктовой границы —
операционное решение (обкатка, откат при жалобах), для него не должен требоваться
деплой. Тот же приём, что у CARD_CONSUMER_PUBLISH (см. память проекта).

Соответствие таблице на странице тарифов (tierCatalog.js::COMPARE_GROUPS) — построчно:
  cardAnalytics       → FEATURE_CARD_FULL_ANALYTICS
  fairPrice           → FEATURE_FAIR_PRICE
  observerDeep        → FEATURE_OBSERVER_DEEP
  portfolioAnalytics  → FEATURE_PORTFOLIO_FULL
  stressTest          → FEATURE_STRESS_CUSTOM
  aiAssistant         → ASSISTANT_DAILY_LIMIT_FREE
Если добавляете строку в таблицу — заводите фичу здесь, иначе страница пообещает
границу, которой нет.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.user import SubscriptionType, User

# ── рубильник ────────────────────────────────────────────────────────────────
def limits_enforced() -> bool:
    """Читаем env КАЖДЫЙ раз, а не в момент импорта: иначе переключение флага
    потребовало бы не только перезапуска, но и уверенности, что модуль не был
    импортирован раньше в другом порядке. Стоимость — чтение словаря."""
    return os.environ.get("TIER_LIMITS_ENFORCED", "").strip() == "1"


# ── что закрыто на бесплатном ────────────────────────────────────────────────
FEATURE_CARD_FULL_ANALYTICS = "card_full_analytics"   # полный разбор вкладок карточки
FEATURE_FAIR_PRICE = "fair_price"                     # справедливая цена и потенциал
FEATURE_OBSERVER_DEEP = "observer_deep"               # разборы отчётов и аналитические разборы
FEATURE_PORTFOLIO_FULL = "portfolio_full"             # полная аналитика портфеля
FEATURE_STRESS_CUSTOM = "stress_custom"               # свои сценарии стресс-теста

PAID_ONLY_FEATURES = frozenset({
    FEATURE_CARD_FULL_ANALYTICS,
    FEATURE_FAIR_PRICE,
    FEATURE_OBSERVER_DEEP,
    FEATURE_PORTFOLIO_FULL,
    FEATURE_STRESS_CUSTOM,
})

ASSISTANT_DAILY_LIMIT_FREE = 3   # запросов в сутки зарегистрированному (владелец 2026-08-04)
FREE_POSITION_LIMIT = 50         # позиций в портфеле (единственный лимит, работавший и раньше)


def is_paid(user: User | None) -> bool:
    return bool(user) and user.subscription_type != SubscriptionType.free


def has_feature(user: User | None, feature: str) -> bool:
    """Доступна ли фича. Пока рубильник выключен — всегда True (см. докстринг модуля)."""
    if not limits_enforced():
        return True
    if feature not in PAID_ONLY_FEATURES:
        return True
    return is_paid(user)


def require_feature(user: User | None, feature: str, what: str) -> None:
    """Бросает 402 (Payment Required), если фича закрыта. 402, а не 403: это не
    «нет прав», а «нужен платный тариф» — фронту нужно различать, чтобы показать
    предложение перейти на Max, а не ошибку доступа."""
    if has_feature(user, feature):
        return
    from fastapi import HTTPException
    raise HTTPException(status_code=402, detail=f"{what} доступно на тарифе Max.")


def assistant_daily_limit(user: User | None) -> int | None:
    """Сколько запросов к ассистенту в сутки. None — без ограничения."""
    if not limits_enforced() or is_paid(user):
        return None
    return ASSISTANT_DAILY_LIMIT_FREE


def assistant_usage_today(db: Session, user_id: int) -> int:
    """Сколько вопросов пользователь задал за последние 24 часа.

    Считаем по messages(role="user") — отдельного счётчика заводить не стали:
    история и так пишется, а лишняя таблица требовала бы синхронизации с ней.
    Окно скользящее (24 часа), а не календарные сутки — не зависит от таймзоны
    пользователя и не даёт «обнулиться в полночь по серверу»."""
    from app.models.assistant import Conversation, Message
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return (db.query(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .filter(Conversation.user_id == user_id,
                    Message.role == "user",
                    Message.created_at >= since)
            .count())


def check_assistant_quota(db: Session, user: User) -> None:
    """Бросает 402, если суточный лимит ассистента исчерпан."""
    limit = assistant_daily_limit(user)
    if limit is None:
        return
    used = assistant_usage_today(db, user.id)
    if used >= limit:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=402,
            detail=(f"На бесплатном тарифе — до {limit} запросов к ассистенту в сутки "
                    f"(использовано {used}). Без ограничений — на тарифе Max."),
        )
