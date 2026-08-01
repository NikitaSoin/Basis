"""Замыкание контура: код нашёл дыру → агент добыл → факт-чекер подтвердил → запись.

🔴 Владелец 2026-08-02: «не нужна схема где я за агентом перепроверяю, можно просто ещё
одного агента факт-чекера сделать». Ручная приёмка не масштабируется и становится
бутылочным горлышком — вместо неё два НЕЗАВИСИМЫХ агента плюс проверки кодом.

Четыре барьера перед записью, и ни один не полагается на «модель обещала»:
  1. добытчик обязан вернуть цитату, а гейт — найти его число в реально открытом тексте;
  2. факт-чекер ищет то же значение ЗАНОВО и в ДРУГОМ источнике (совпадение домена
     подтверждением не считается);
  3. правдоподобие: значение сверяется с историей самого ряда (уровень и шаг);
  4. FIRST-WRITE-WINS: существующая точка НИКОГДА не перезаписывается — только
     заполнение дыр. Прецедент прямой: автоматика уже затирала верное значение
     инфляционных ожиданий, владелец ловил это дважды.

Неподтверждённое не теряется: пишется в лог прогона со статусом, видно в отладке.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Максимально допустимое отклонение новой точки от медианы истории, в стандартных
# отклонениях ряда. Грубый фильтр «ошибка ввода», а не суждение об экономике.
_MAX_Z = 6.0


def _plausible(db: Session, code: str, metric: str, value: float) -> tuple[bool, str]:
    rows = db.execute(text(
        "SELECT value FROM macro_data_points WHERE indicator_code=:c AND metric=:m "
        "ORDER BY as_of DESC LIMIT 24"), {"c": code, "m": metric}).all()
    vals = [float(r[0]) for r in rows if r[0] is not None]
    if len(vals) < 6:
        return True, "истории мало — проверка правдоподобия пропущена"
    med = statistics.median(vals)
    try:
        spread = statistics.pstdev(vals)
    except statistics.StatisticsError:
        return True, "разброс не посчитан"
    if spread <= 0:
        return abs(value - med) < max(0.5, abs(med) * 0.5), "ряд без разброса"
    z = abs(value - med) / spread
    return z <= _MAX_Z, f"отклонение {z:.1f}σ от медианы {med:g}"


def _point_exists(db: Session, code: str, metric: str, as_of: str) -> bool:
    return db.execute(text(
        "SELECT 1 FROM macro_data_points WHERE indicator_code=:c AND metric=:m AND as_of=:d"
    ), {"c": code, "m": metric, "d": as_of}).first() is not None


def process_finding(db: Session, code: str, metric: str, item: dict,
                    origin_url: str | None, *, dry_run: bool = False) -> dict:
    """Один найденный период: проверить и, если всё сошлось, записать."""
    from app.services.macro_fact_checker import check_finding, normalize_period

    period = normalize_period(item.get("period"))
    value = item.get("value")
    unit = item.get("unit") or ""
    if not period or not isinstance(value, (int, float)):
        return {"code": code, "status": "skipped", "reason": "bad_period_or_value", "item": item}
    value = float(value)

    if _point_exists(db, code, metric, period):
        # Не перезаписываем: агент дозаполняет дыры, а не правит опубликованное.
        return {"code": code, "period": period, "status": "skipped", "reason": "point_exists"}

    ok, why = _plausible(db, code, metric, value)
    if not ok:
        return {"code": code, "period": period, "value": value,
                "status": "rejected", "reason": f"implausible ({why})"}

    check = check_finding(db, code, period, value, unit, origin_url)
    if check["verdict"] != "confirmed":
        return {"code": code, "period": period, "value": value, "status": "unconfirmed",
                "reason": check["verdict"], "checker": check}

    if dry_run:
        return {"code": code, "period": period, "value": value, "status": "would_write",
                "checker": check}

    from app.services.macro_ingest import upsert_point
    upsert_point(db, code, date.fromisoformat(period), metric, value,
                 source="агент+факт-чекер", source_url=check.get("source_url"),
                 ingested_via="agent")
    db.commit()
    logger.info("gap_pipeline: записана точка %s %s = %s (подтверждено %s)",
                code, period, value, check.get("source_url"))
    return {"code": code, "period": period, "value": value, "status": "written",
            "confirmed_by": check.get("source_url"), "quote": check.get("quote")}


def run_round(db: Session, limit: int = 2, *, dry_run: bool = False) -> dict:
    """Раунд: закрыть несколько самых важных дыр целиком (добыть → проверить → записать).

    limit маленький намеренно: это регулярная чистка по чуть-чуть, а не «починить всё
    разом». Каждая дыра — два агентских прогона (добытчик + чекер), ~8 центов.
    """
    from app.services.macro_gap_agent import run_gap_round

    started = datetime.now(timezone.utc)
    findings = run_gap_round(db, limit=limit)
    processed = []
    for f in findings:
        res = f.get("result") or {}
        if not f.get("accepted"):
            processed.append({"code": f.get("code"), "status": "no_finding",
                              "reason": f.get("gate_notes") or f.get("stopped_reason")})
            continue
        for item in res.get("values") or []:
            try:
                processed.append(process_finding(
                    db, f["code"], "level", item, res.get("source_url"), dry_run=dry_run))
            except Exception as e:  # noqa: BLE001
                db.rollback()
                logger.exception("gap_pipeline: обработка находки упала")
                processed.append({"code": f.get("code"), "status": "error", "reason": str(e)[:200]})
    return {"started_at": started.isoformat(), "questions": len(findings),
            "results": processed,
            "written": sum(1 for p in processed if p.get("status") == "written")}
