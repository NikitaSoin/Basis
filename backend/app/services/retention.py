"""Удаление данных по истечении сроков хранения (152-ФЗ, ч. 7 ст. 5).

Зачем: закон требует хранить персональные данные не дольше, чем этого требует
цель обработки. Юр-аудит 2026-09-06 нашёл три места, где данные копились вечно:
записи об отправке писем (verification_codes с purpose='verify_link' не
удалялись НИКОГДА), журнал событий интерфейса и гостевые портфели брошенных
устройств. Сроки здесь обязаны совпадать с разделом 6 опубликованной Политики
(docs/legal/02-политика-обработки-пдн.md) — если меняешь тут, меняй и там.

🔴 ПРЕДОХРАНИТЕЛЬ. Правило удаления, ошибшееся в условии, сносит живую таблицу
молча и необратимо (в этом проекте так уже дважды теряли ряды данных). Поэтому:
  * сначала СЧИТАЕМ, сколько попадает под удаление, и только потом удаляем;
  * если под правило попадает больше MAX_SHARE от таблицы и больше MIN_ROWS
    строк — правило НЕ выполняется, а пишет предупреждение в лог: это почти
    всегда ошибка в условии (сдвинутая дата, NULL вместо времени), а не
    честное накопление;
  * есть режим dry_run — вернуть план без единого удаления (ручка
    /api/debug/retention-preview);
  * удаляем партиями, чтобы не держать долгую блокировку.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Сроки в днях. Значения по умолчанию = разделу 6 Политики.
DAYS_VERIFICATION_CODES = int(os.getenv("RETENTION_VERIFICATION_CODES_DAYS", "30"))
DAYS_USER_EVENTS = int(os.getenv("RETENTION_USER_EVENTS_DAYS", "365"))
DAYS_GUEST_PORTFOLIOS = int(os.getenv("RETENTION_GUEST_PORTFOLIO_DAYS", "365"))
DAYS_ASSISTANT = int(os.getenv("RETENTION_ASSISTANT_DAYS", "365"))
DAYS_OBSERVER_REPORTS = int(os.getenv("RETENTION_OBSERVER_REPORTS_DAYS", "365"))
DAYS_DIAGNOSES = int(os.getenv("RETENTION_DIAGNOSES_DAYS", "365"))

# Предохранитель: доля таблицы, выше которой правило считается подозрительным.
MAX_SHARE = float(os.getenv("RETENTION_MAX_SHARE", "0.6"))
MIN_ROWS_FOR_GUARD = int(os.getenv("RETENTION_MIN_ROWS", "1000"))
BATCH = 5000


def _table_exists(db: Session, table: str) -> bool:
    return bool(db.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}).scalar())


def _sweep(db: Session, *, name: str, table: str, where: str, params: dict,
           dry_run: bool, force: bool) -> dict:
    """Одно правило удаления. Возвращает отчёт, ничего не бросает наружу."""
    out = {"rule": name, "table": table, "matched": 0, "total": 0, "deleted": 0, "status": "ok"}
    if not _table_exists(db, table):
        out["status"] = "нет таблицы"
        return out
    try:
        out["total"] = int(db.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)
        out["matched"] = int(db.execute(
            text(f"SELECT count(*) FROM {table} WHERE {where}"), params).scalar() or 0)
    except Exception as e:  # noqa: BLE001
        out["status"] = f"ошибка подсчёта: {type(e).__name__}"
        logger.exception("retention[%s]: не удалось посчитать", name)
        return out

    if out["matched"] == 0:
        out["status"] = "нечего удалять"
        return out

    share = out["matched"] / out["total"] if out["total"] else 1.0
    if not force and out["matched"] >= MIN_ROWS_FOR_GUARD and share > MAX_SHARE:
        out["status"] = (f"ОСТАНОВЛЕНО предохранителем: под правило попало "
                         f"{out['matched']} из {out['total']} строк ({share:.0%})")
        logger.error("retention[%s]: %s — правило не выполнено, проверьте условие",
                     name, out["status"])
        return out

    if dry_run:
        out["status"] = "план (dry-run), ничего не удалено"
        return out

    deleted = 0
    while True:
        res = db.execute(text(
            f"DELETE FROM {table} WHERE id IN "
            f"(SELECT id FROM {table} WHERE {where} LIMIT {BATCH})"), params)
        db.commit()
        n = res.rowcount or 0
        deleted += n
        if n < BATCH:
            break
    out["deleted"] = deleted
    logger.info("retention[%s]: удалено %s из %s", name, deleted, out["total"])
    return out


def run_retention(db: Session, dry_run: bool = False, force: bool = False) -> dict:
    """Прогон всех правил. dry_run — только посчитать; force — снять предохранитель."""
    now = datetime.now(timezone.utc)
    ago = lambda d: now - timedelta(days=d)  # noqa: E731
    rules = [
        # Записи об отправке писем: нужны только для кулдауна повторной отправки.
        dict(name="письма: журнал отправки", table="verification_codes",
             where="created_at < :t", params={"t": ago(DAYS_VERIFICATION_CODES)}),
        # Журнал событий интерфейса (собственная аналитика).
        dict(name="события интерфейса", table="user_events",
             where="created_at < :t", params={"t": ago(DAYS_USER_EVENTS)}),
        # Гостевые портфели брошенных устройств. Позиции и сделки уходят каскадом
        # (ondelete=CASCADE в моделях). Портфели зарегистрированных не трогаем.
        dict(name="гостевые портфели", table="portfolios",
             where=("guest_token IS NOT NULL AND user_id IS NULL AND "
                    "COALESCE(guest_seen_at, created_at) < :t"),
             params={"t": ago(DAYS_GUEST_PORTFOLIOS)}),
        # Диалоги с ассистентом (сообщения — каскадом).
        dict(name="диалоги ассистента", table="assistant_conversations",
             where="COALESCE(updated_at, created_at) < :t", params={"t": ago(DAYS_ASSISTANT)}),
        dict(name="ИИ-отчёты Обозревателя", table="observer_reports",
             where="generated_at < :t", params={"t": ago(DAYS_OBSERVER_REPORTS)}),
        dict(name="ИИ-диагнозы портфелей", table="portfolio_diagnoses",
             where="generated_at < :t", params={"t": ago(DAYS_DIAGNOSES)}),
    ]
    report = {"at": now.isoformat(), "dry_run": dry_run, "force": force, "rules": []}
    for r in rules:
        try:
            report["rules"].append(_sweep(db, dry_run=dry_run, force=force, **r))
        except Exception as e:  # noqa: BLE001 — одно правило не должно ронять остальные
            logger.exception("retention[%s]: правило упало", r["name"])
            report["rules"].append({"rule": r["name"], "status": f"ошибка: {type(e).__name__}: {e}"})
    report["deleted_total"] = sum(x.get("deleted", 0) for x in report["rules"])
    return report
