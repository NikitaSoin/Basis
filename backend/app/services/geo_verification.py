"""«ОТК данных» геополитики — проверки БЕЗ LLM.

У Макроэкономики такой слой есть (macro_verification, 11 проверок: календарь ЦБ,
кросс-сверка с первоисточниками, скачки значений) и он ловит реальные дыры. У
Геополитики его не было вообще: между моделью и витриной стояли только гейт
обоснованности сдвига балла и комплаенс-блоклист. Из-за этого «тихая» поломка —
крон упал, лента перестала приходить, барометр застыл на позапрошлой неделе —
выглядела на экране точно так же, как нормальная работа.

🔴 ЧЕМ ЭТОТ ОТК ОТЛИЧАЕТСЯ ОТ МАКРО-ОТК.
У макро есть внешняя истина: ставку можно сверить с cbr.ru, курс — с Мосбиржей,
и расхождение однозначно означает ошибку. В геополитике сверять не с чем — баллы
G1-G13 и вероятности сценариев ЕСТЬ суждение модели, внешнего эталона у них нет.
Поэтому здесь проверяется не «совпадает ли значение с источником», а то, что
проверяемо объективно:
  • ЖИВОСТЬ конвейера — приходит ли лента, обновляются ли слои, не застыл ли
    барометр (это ловит упавший крон, а такое уже случалось);
  • ВНУТРЕННЯЯ СОГЛАСОВАННОСТЬ — суммы вероятностей, полнота секций, наличие
    обоснования у сдвинутых баллов, непротиворечивость балла очага и общего;
  • ПОЛНОТА ВИТРИНЫ — есть ли у каждого очага то, что фронт собирается рисовать.
Проверка только СИГНАЛИТ и никогда не правит данные сама — тот же принцип, что
в macro_verification.

Результат пишется в macro_verifications с префиксом ключа `geo_`: заводить вторую
таблицу под тот же самый набор полей (run_at / check_key / status / message /
details) значило бы дублировать схему и второй API ради косметики.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion, GeoFrontlineSync
from app.models.geo_digest import GeoDigestArticle
from app.models.macro import MacroVerification
from app.services import barometer_store

logger = logging.getLogger(__name__)

_SCOPES = ("svo", "middle_east", "atr")
_SCOPE_RU = {"svo": "СВО", "middle_east": "Ближний Восток", "atr": "АТР"}

# Сколько дней без новой статьи по очагу считаем поломкой конвейера, а не
# затишьем. По СВО поток плотный (ISW пишет ежедневно) — двое суток тишины уже
# аномалия. По АТР поток разрежённый по своей природе, там порог выше.
_FEED_STALE_DAYS = {"svo": 2, "middle_east": 4, "atr": 7}
_BARO_STALE_DAYS = 3          # барометр пересобирается ежедневным кроном
_PROFILE_STALE_DAYS = 14      # портрет — недельный, две недели = пропущен прогон
_FRONTLINE_STALE_HOURS = 30   # синк линии фронта идёт дважды в сутки


def _res(key: str, title: str, status: str, message: str, **details) -> dict:
    return {"check_key": f"geo_{key}", "check_type": "geo", "title": title,
            "status": status, "message": message, "details": details or None}


# ----------------------------- живость конвейера -----------------------------
def _check_feed_fresh(db: Session) -> dict:
    """Приходит ли лента по каждому очагу. Ловит упавший geo_digest."""
    today = date.today()
    stale, ages = [], {}
    for s in _SCOPES:
        last = (db.query(GeoDigestArticle.published_at)
                .filter(GeoDigestArticle.target == s)
                .order_by(GeoDigestArticle.published_at.desc()).first())
        if not last or not last[0]:
            stale.append(f"{_SCOPE_RU[s]}: материалов нет вообще")
            ages[s] = None
            continue
        age = (today - last[0]).days
        ages[s] = age
        if age > _FEED_STALE_DAYS[s]:
            stale.append(f"{_SCOPE_RU[s]}: последний материал {age} дн. назад "
                         f"(порог {_FEED_STALE_DAYS[s]})")
    title = "Лента по очагам приходит"
    if stale:
        return _res("feed_fresh", title, "warn",
                    "Поток материалов отстаёт: " + "; ".join(stale), ages=ages)
    return _res("feed_fresh", title, "ok",
                "По всем трём очагам есть свежие материалы", ages=ages)


def _check_barometer_fresh(db: Session) -> dict:
    """Не застыл ли барометр. Ловит упавший barometer_daily — самый неочевидный
    отказ: витрина продолжает показывать вчерашние числа как сегодняшние."""
    row = barometer_store.current_row(db, "geo")
    title = "Барометр пересобирается"
    if not row or not row.created_at:
        return _res("baro_fresh", title, "fail", "Опубликованной версии барометра нет")
    age_days = (datetime.now(timezone.utc) - row.created_at).days
    if age_days > _BARO_STALE_DAYS:
        return _res("baro_fresh", title, "fail",
                    f"Барометр не обновлялся {age_days} дн. — вероятно, упал ежедневный крон",
                    age_days=age_days, version_id=row.id)
    return _res("baro_fresh", title, "ok",
                f"Последняя версия — {age_days} дн. назад", age_days=age_days)


def _check_rejected_streak(db: Session) -> dict:
    """Серия отклонённых версий подряд = модель систематически не проходит гейт.
    Витрина при этом выглядит здоровой (показывает последнюю published), поэтому
    без этой проверки деградация невидима."""
    rows = (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == "geo", BarometerVersion.source == "auto")
            .order_by(BarometerVersion.created_at.desc()).limit(5).all())
    title = "Пересборки барометра проходят гейт"
    streak, notes = 0, []
    for r in rows:
        if r.status == "published":
            break
        streak += 1
        notes.extend(list(r.gate_notes or [])[:2])
    if streak >= 3:
        return _res("baro_rejects", title, "fail",
                    f"{streak} последних пересборок отклонены — на витрине держится старая версия",
                    streak=streak, notes=notes[:6])
    if streak == 2:
        return _res("baro_rejects", title, "warn",
                    "Две пересборки подряд отклонены", streak=streak, notes=notes[:4])
    return _res("baro_rejects", title, "ok", "Последняя пересборка опубликована")


def _check_frontline_sync(db: Session) -> dict:
    """Слой линии фронта (без LLM, чистая геометрия) — жив ли ArcGIS-фид."""
    rows = db.query(GeoFrontlineSync).all()
    title = "Слой линии фронта синхронизируется"
    if not rows:
        return _res("frontline", title, "unavailable", "Записей о синхронизации нет")
    bad = []
    for r in rows:
        if r.status and r.status != "ok":
            bad.append(f"{r.theater or 'СВО'}: {r.status}"
                       + (f" ({r.error_note[:80]})" if r.error_note else ""))
            continue
        ts = getattr(r, "synced_at", None) or getattr(r, "updated_at", None)
        if ts:
            hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            if hours > _FRONTLINE_STALE_HOURS:
                bad.append(f"{r.theater or 'СВО'}: не обновлялся {hours:.0f} ч")
    if bad:
        return _res("frontline", title, "warn", "; ".join(bad))
    return _res("frontline", title, "ok", "Слой обновляется по расписанию")


# ------------------------ внутренняя согласованность ------------------------
def _check_probabilities(db: Session) -> dict:
    """Суммы вероятностей = 1.0 — и в общей лестнице, и внутри КАЖДОГО очага.
    Гейт barometer_daily нормализует их при записи, поэтому расхождение здесь
    означает, что на витрину попал payload мимо гейта (импорт якоря, ручная
    правка) — то есть ровно тот случай, который иначе никто не заметит."""
    row = barometer_store.current_row(db, "geo")
    title = "Вероятности сценариев сходятся к 100%"
    if not row or not row.payload:
        return _res("probs", title, "unavailable", "Барометра нет")
    p = row.payload
    bad = []

    def _sum_ok(d, label):
        if not isinstance(d, dict):
            return
        vals = [v for v in d.values() if isinstance(v, (int, float))]
        if not vals:
            return
        total = sum(vals)
        if abs(total - 1.0) > 0.02:
            bad.append(f"{label}: сумма {total:.2f}")

    sc = p.get("scenario") or {}
    _sum_ok(sc.get("probabilities_6m"), "общая лестница, 6 мес")
    _sum_ok(sc.get("probabilities_18m"), "общая лестница, 18 мес")

    for key, reg in (p.get("regions") or {}).items():
        items = ((reg or {}).get("scenarios") or {}).get("items") or []
        for horizon in ("p6m", "p18m"):
            vals = [i.get(horizon) for i in items if isinstance(i.get(horizon), (int, float))]
            if vals and abs(sum(vals) - 1.0) > 0.02:
                bad.append(f"{_SCOPE_RU.get(key, key)}, {horizon}: сумма {sum(vals):.2f}")

    if bad:
        return _res("probs", title, "fail", "Вероятности не сходятся: " + "; ".join(bad), bad=bad)
    return _res("probs", title, "ok", "Все наборы вероятностей дают 100%")


def _check_delta_rationale(db: Session) -> dict:
    """Сдвинутые баллы обязаны нести обоснование со ссылкой на событие. Гейт
    откатывает необоснованные, но если откатов много — модель систематически
    двигает числа в тишине, и это стоит увидеть."""
    rows = (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == "geo", BarometerVersion.source == "auto")
            .order_by(BarometerVersion.created_at.desc()).limit(3).all())
    title = "Изменения баллов обоснованы событиями"
    reverts = []
    for r in rows:
        for n in (r.gate_notes or []):
            if isinstance(n, str) and "откат" in n.lower():
                reverts.append(n[:100])
    if len(reverts) >= 6:
        return _res("delta_rationale", title, "warn",
                    f"За последние прогоны {len(reverts)} баллов откатано как необоснованные",
                    examples=reverts[:5])
    return _res("delta_rationale", title, "ok",
                f"Необоснованных сдвигов немного ({len(reverts)})")


def _check_region_scores(db: Session) -> dict:
    """У каждого очага должен быть СВОЙ балл остроты. Если балл очага исчез,
    витрина молча подставляет общий балл рынка — и пользователь видит одно и то
    же число на всех трёх вкладках, думая, что это оценка конкретного очага."""
    row = barometer_store.current_row(db, "geo")
    title = "У каждого очага свой балл остроты"
    if not row or not row.payload:
        return _res("region_scores", title, "unavailable", "Барометра нет")
    regions = (row.payload or {}).get("regions") or {}
    missing, scores = [], {}
    for s in _SCOPES:
        val = ((regions.get(s) or {}).get("barometer") or {}).get("overall")
        scores[s] = val
        if not isinstance(val, (int, float)):
            missing.append(_SCOPE_RU[s])
    if missing:
        return _res("region_scores", title, "warn",
                    "Нет собственного балла: " + ", ".join(missing) +
                    " — на витрине подставится общий балл рынка", scores=scores)
    if len({round(float(v), 1) for v in scores.values()}) == 1:
        return _res("region_scores", title, "warn",
                    "Все три очага получили одинаковый балл — вероятно, оценка не разделена",
                    scores=scores)
    return _res("region_scores", title, "ok", "Баллы очагов различаются", scores=scores)


# ---------------------------- полнота витрины ----------------------------
def _check_region_sections(db: Session) -> dict:
    """Есть ли у каждого очага всё, что рисует витрина: сценарии, секторные
    флаги, сводка. Пустая секция на экране выглядит как «ничего не происходит»,
    хотя на деле модель просто не вернула поле."""
    row = barometer_store.current_row(db, "geo")
    title = "Секции очагов заполнены"
    if not row or not row.payload:
        return _res("region_sections", title, "unavailable", "Барометра нет")
    regions = (row.payload or {}).get("regions") or {}
    gaps = []
    for s in _SCOPES:
        reg = regions.get(s) or {}
        for field, human in (("summary", "сводка"), ("scenarios", "сценарии"),
                             ("sector_flags", "секторные последствия")):
            if not reg.get(field):
                gaps.append(f"{_SCOPE_RU[s]}: нет «{human}»")
    if gaps:
        return _res("region_sections", title, "warn",
                    "Незаполненное: " + "; ".join(gaps), gaps=gaps)
    return _res("region_sections", title, "ok", "У всех очагов секции на месте")


def _check_profile_fresh(db: Session) -> dict:
    """Портрет очага (стороны/цели/баланс/связки) — недельный слой."""
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == "geoprof", BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    title = "Портрет очагов обновляется"
    if not row:
        return _res("profile_fresh", title, "unavailable",
                    "Портретов ещё нет — слой не запускался")
    age = (datetime.now(timezone.utc) - row.created_at).days
    missing = [_SCOPE_RU[s] for s in _SCOPES if not (row.payload or {}).get(s)]
    if missing:
        return _res("profile_fresh", title, "warn",
                    "Нет портрета: " + ", ".join(missing), age_days=age)
    if age > _PROFILE_STALE_DAYS:
        return _res("profile_fresh", title, "warn",
                    f"Портрет не обновлялся {age} дн. (недельный слой)", age_days=age)
    return _res("profile_fresh", title, "ok", f"Обновлён {age} дн. назад", age_days=age)


def _check_profile_reverse_links(db: Session) -> dict:
    """Обратные связки (макро → гео, институты → гео) — то, ради чего блок и
    переделан. Их легко потерять молча: модель вернёт односторонний разбор, и
    внешне всё будет выглядеть заполненным."""
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == "geoprof", BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    title = "Обратные связки (экономика → конфликт) раскрыты"
    if not row or not row.payload:
        return _res("profile_reverse", title, "unavailable", "Портретов нет")
    gaps = []
    for s in _SCOPES:
        prof = (row.payload or {}).get(s) or {}
        if not (prof.get("macro_link") or {}).get("from_macro"):
            gaps.append(f"{_SCOPE_RU[s]}: нет «макро → гео»")
        if not (prof.get("institutional_link") or {}).get("from_inst"):
            gaps.append(f"{_SCOPE_RU[s]}: нет «институты → гео»")
    if gaps:
        return _res("profile_reverse", title, "warn", "; ".join(gaps), gaps=gaps)
    return _res("profile_reverse", title, "ok", "Двусторонние связки на месте у всех очагов")


# ----------------------------- прогон и выдача -----------------------------
def run_verification(db: Session) -> dict:
    """Полный прогон. Ошибка одной проверки не роняет остальные — тот же
    контракт, что у macro_verification."""
    checks = [
        lambda: _check_feed_fresh(db),
        lambda: _check_barometer_fresh(db),
        lambda: _check_rejected_streak(db),
        lambda: _check_frontline_sync(db),
        lambda: _check_probabilities(db),
        lambda: _check_delta_rationale(db),
        lambda: _check_region_scores(db),
        lambda: _check_region_sections(db),
        lambda: _check_profile_fresh(db),
        lambda: _check_profile_reverse_links(db),
    ]
    run_at = datetime.now(timezone.utc)
    results = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:                                   # noqa: BLE001
            logger.warning("geo_verification: проверка упала (%s)", e)
            results.append(_res("internal", "Проверка не выполнилась", "unavailable",
                                f"Ошибка проверки: {e}"))
    for r in results:
        db.add(MacroVerification(run_at=run_at, **r))
    db.commit()

    counts = {k: sum(1 for r in results if r["status"] == k)
              for k in ("ok", "warn", "fail", "unavailable")}
    overall = "fail" if counts["fail"] else ("warn" if counts["warn"] else "ok")
    logger.info("geo_verification: %s (ok=%d warn=%d fail=%d n/a=%d)", overall,
                counts["ok"], counts["warn"], counts["fail"], counts["unavailable"])
    return {"run_at": run_at.isoformat(), "overall": overall,
            "counts": counts, "results": results}


def latest_results(db: Session) -> dict:
    """READ-PATH витрины: последний прогон гео-проверок."""
    last = (db.query(MacroVerification.run_at)
            .filter(MacroVerification.check_type == "geo")
            .order_by(MacroVerification.run_at.desc()).first())
    if not last:
        return {"available": False, "overall": None, "results": []}
    rows = (db.query(MacroVerification)
            .filter(MacroVerification.check_type == "geo",
                    MacroVerification.run_at == last[0]).all())
    results = [{"check_key": r.check_key, "title": r.title, "status": r.status,
                "message": r.message, "details": r.details} for r in rows]
    overall = ("fail" if any(r["status"] == "fail" for r in results)
               else "warn" if any(r["status"] == "warn" for r in results) else "ok")
    return {"available": True, "run_at": last[0].isoformat(),
            "overall": overall, "results": results}
