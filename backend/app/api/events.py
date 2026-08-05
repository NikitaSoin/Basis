"""Приём продуктовых событий с фронтенда.

Владелец 2026-08-01: «хотелось бы записывать логи по клиентам и знать, как часто они
заходят, по каким страницам ходят, что кликают».

ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ МЕТРИКИ: Метрика считает ВИЗИТЫ и не знает, кто их совершил. Она
не ответит на вопрос «пользователи с портфелем из пяти и более бумаг чаще открывают
корреляции?» — а именно такие вопросы двигают продукт. Здесь события ложатся в ту же
базу, что users и portfolios, поэтому джойнятся обычным SQL. Метрику это не заменяет:
карта кликов и записи сессий остаются за ней.

🔴 БЕЗ ПЕРСОНАЛЬНЫХ ДАННЫХ. Пишем user_id (у гостей NULL) и анонимный идентификатор
устройства из localStorage. Ни почт, ни имён, ни IP: для продуктовых выводов они не
нужны, а хранить их — брать на себя обязательства по 152-ФЗ без надобности.

🔴 ЭНДПОИНТ НИКОГДА НЕ МЕШАЕТ ПОЛЬЗОВАТЕЛЮ. Любая ошибка записи проглатывается и
возвращается 200: аналитика не тот повод, чтобы у человека сломался экран. По той же
причине стоят жёсткие ограничения на размер — иначе кривой клиент может залить базу.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.auth import get_current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_BATCH = 20          # событий за один запрос
_MAX_STR = 512



# 🔴 Роботов отделяем НА СЕРВЕРЕ по User-Agent: со стороны браузера этого не видно, а без
# разделения метрики бессмысленны. За первые 12 часов лога 382 «посетителя» оказались
# поисковым обходом — они пришли через час после отправки адресов в IndexNow, обошли 426
# разных страниц по 1-2 события каждый и все без источника перехода.
# 🔴 МАРКЕРЫ РОБОТОВ — ТОЛЬКО ОДНОЗНАЧНЫЕ. Первая версия содержала голые «yandex»,
# «google», «mail.ru», «whatsapp», и это записывало в роботы ЖИВЫХ ЛЮДЕЙ: строка браузера
# мобильного приложения Яндекса содержит YandexSearch, браузера Mail.ru — mail.ru,
# встроенного браузера WhatsApp — WhatsApp. В России это заметная доля мобильного трафика,
# и именно она объясняла разрыв с Метрикой (05.08: у нас 13 человек, у Метрики 34, при
# 151 «роботе» за день).
#
# Второе соображение: /api/events зовётся ИЗ JAVASCRIPT. Простые краулеры сюда не доходят
# вовсе — им не нужны маркеры. Ловить надо тех, кто исполняет скрипты: поисковых роботов
# Яндекса и Google и headless-браузеры.
_BOT_MARKERS = (
    # поисковые роботы, исполняющие JS
    "yandexbot", "yandexmobilebot", "yandexrenderresourcesbot", "yandexmetrika",
    "googlebot", "google-inspectiontool", "bingbot", "duckduckbot", "baiduspider",
    "petalbot", "ahrefsbot", "semrushbot", "mj12bot", "dotbot", "slurp",
    # автоматизация и headless
    "headlesschrome", "phantomjs", "puppeteer", "playwright", "selenium",
    "python-requests", "curl/", "wget", "go-http-client", "java/", "okhttp",
    # общие самоназвания — в строках настоящих браузеров не встречаются
    "crawler", "spider", "crawling", "bot/", "-bot", "_bot", "bot;", "bot)",
)


def _bot_reason(ua: str) -> str | None:
    """Какой маркер сработал — или None, если это похоже на человека.

    Возвращаем ПРИЧИНУ, а не булево: без неё классификатор нельзя проверить постфактум.
    Строку браузера не храним (это отпечаток устройства), а название сработавшего маркера —
    достаточно, чтобы найти ошибку и не собирать лишнего о человеке.
    """
    u = (ua or "").lower()
    if not u:
        return "no-ua"       # живые браузеры без User-Agent не ходят
    for m in _BOT_MARKERS:
        if m in u:
            return m
    return None


def _looks_like_bot(ua: str) -> bool:
    return _bot_reason(ua) is not None


class EventIn(BaseModel):
    kind: str = Field(max_length=24)              # pageview | click | action
    name: str | None = Field(default=None, max_length=120)
    path: str | None = Field(default=None, max_length=_MAX_STR)
    referrer: str | None = Field(default=None, max_length=_MAX_STR)
    meta: dict | None = None
    anon_id: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)


class EventsIn(BaseModel):
    events: list[EventIn] = Field(default_factory=list)


@router.post("/events")
def collect_events(payload: EventsIn, request: Request,
                   db: Session = Depends(get_db),
                   user=Depends(get_current_user_optional)):
    """Принять пачку событий. Всегда отвечает 200, даже при сбое записи."""
    try:
        uid = getattr(user, "id", None)
        bot_reason = _bot_reason(request.headers.get("user-agent", ""))
        is_bot = bot_reason is not None
        rows = payload.events[:_MAX_BATCH]
        if not rows:
            return {"принято": 0}

        записано = 0
        for e in rows:
            kind = (e.kind or "").strip()[:24]
            if kind not in ("pageview", "click", "action"):
                continue                      # неизвестный вид не пишем, чтобы не мусорить
            meta = e.meta if isinstance(e.meta, dict) else None
            if meta and len(str(meta)) > 2000:
                meta = {"_обрезано": True}
            # Причина классификации — в meta, чтобы ошибку детектора можно было найти
            # постфактум. Саму строку браузера не храним: это отпечаток устройства.
            if bot_reason:
                meta = {**(meta or {}), "_bot": bot_reason}
            db.execute(text(
                "INSERT INTO user_events (user_id, anon_id, session_id, kind, name, path, referrer, meta, is_bot) "
                "VALUES (:uid, :anon, :sess, :kind, :name, :path, :ref, CAST(:meta AS JSON), :bot)"
            ), {
                "uid": uid,
                "anon": (e.anon_id or None), "sess": (e.session_id or None),
                "kind": kind, "name": (e.name or None),
                "path": (e.path or None)[:_MAX_STR] if e.path else None,
                "ref": (e.referrer or None)[:_MAX_STR] if e.referrer else None,
                "meta": __import__("json").dumps(meta, ensure_ascii=False) if meta else None,
                "bot": is_bot,
            })
            записано += 1
        db.commit()
        return {"принято": записано, "отброшено": len(rows) - записано}
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("события не записаны: %s", e)
        return {"принято": 0}
