"""Журнал прогнозов: запись в момент выдачи, сверка с фактом по сроку, уроки и калибровка.

🔴 ЗАЧЕМ (операционный протокол владельца, 2.5 и 10.3; решение «встрой» 2026-09-14).
Сводки пересобираются каждый день, и вчерашний прогноз исчезает под сегодняшним.
Обучение на ошибках шло только по замечаниям проверяющего — не по реальности. Здесь:
  1. ЗАПИСЬ. После публикации сводки (гео / экономика / институты), ответа совета или
     экзамена из её текста ИЗВЛЕКАЮТСЯ прогнозы: исход, вероятность (число + слово),
     горизонт, механизм, пороговые события, дата пересмотра, версия знания. Повторная
     публикация того же дня ту же строку не дублирует.
  2. СВЕРКА. Раз в неделю (крон forecast_review) записи с наступившим сроком сверяются с
     фактами: судья получает прогноз и то, что по этой теме есть в потоке платформы
     с даты прогноза, и выносит статус: подтвердился / опровергнут / частично / неясно,
     какой механизм сработал, урок. Урок уходит в базу уроков контура.
  3. КАЛИБРОВКА. По закрытым записям считается, насколько названные вероятности
     соответствуют исходам (по источникам и горизонтам) — это и есть «система узнаёт свои
     систематические ошибки по классам».
Всё через try/except: запись в журнал не имеет права уронить публикацию сводки.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.forecast_journal import ForecastEntry

logger = logging.getLogger(__name__)

_HORIZON_DAYS = {"6m": 182, "18m": 548, "2y": 730, "5y": 1826, "3m": 91, "12m": 365, "1y": 365}
_WORDS = [(0.05, "крайне маловероятно"), (0.20, "маловероятно"), (0.45, "возможно"),
          (0.70, "скорее да"), (0.90, "вероятно"), (1.01, "почти наверняка")]


def p_words(p: float | None) -> str | None:
    if p is None:
        return None
    for top, w in _WORDS:
        if p <= top:
            return w
    return "почти наверняка"


def _horizon_key(text: str | None) -> str:
    t = str(text or "").lower()
    if "18" in t:
        return "18m"
    if "2 г" in t or "2y" in t or "два г" in t or "24" in t:
        return "2y"
    if "5" in t and ("лет" in t or "y" in t):
        return "5y"
    if "3 мес" in t or "3m" in t or "квартал" in t:
        return "3m"
    if "12" in t or "год" in t or "1y" in t:
        return "12m"
    return "6m"


def _review_date(as_of: date, horizon: str) -> date:
    return as_of + timedelta(days=_HORIZON_DAYS.get(horizon, 182))


def methodology_version() -> str:
    """Отпечаток знания на момент прогноза: время изменения методичек и протокола."""
    try:
        from app.services import methodology, protocol_core
        parts = []
        for d in methodology.REGISTRY.values():
            try:
                parts.append(f"{d.doc_id}:{int(os.path.getmtime(d.path))}")
            except OSError:
                pass
        try:
            parts.append(f"protocol:{int(os.path.getmtime(protocol_core.PATH))}")
        except OSError:
            pass
        return hashlib.sha1("|".join(sorted(parts)).encode()).hexdigest()[:12]
    except Exception:  # noqa: BLE001
        return "unknown"


# ─────────────────────────── извлечение прогнозов из выпусков ───────────────────────────

def _num(x) -> float | None:
    try:
        v = float(x)
        return v if 0.0 <= v <= 1.0 else None
    except (TypeError, ValueError):
        return None


def extract(source: str, payload: dict) -> list[dict]:
    """Прогнозы из выпуска → список {scope, outcome, p, horizon, mechanism, triggers}."""
    out: list[dict] = []
    if not isinstance(payload, dict):
        return out
    if source == "geo":
        for rkey, reg in (payload.get("regions") or {}).items():
            sc = (reg or {}).get("scenarios") if isinstance(reg, dict) else None
            if not isinstance(sc, dict):
                continue
            trig = sc.get("triggers") or []
            for it in sc.get("items") or []:
                if not isinstance(it, dict) or not it.get("label"):
                    continue
                for hz, key in (("6m", "p6m"), ("18m", "p18m")):
                    p = _num(it.get(key))
                    if p is not None:
                        out.append({"scope": rkey, "outcome": str(it["label"])[:400], "p": p, "horizon": hz,
                                    "mechanism": str(it.get("note") or "")[:600], "triggers": trig[:8]})
    elif source == "macro":
        fc = payload.get("forecast") or {}
        for var, v in (fc.get("variables") or {}).items() if isinstance(fc.get("variables"), dict) else []:
            if not isinstance(v, dict):
                continue
            probs = v.get("probabilities") or {}
            for name in ("base", "favorable", "adverse"):
                txt = v.get(name)
                if not txt:
                    continue
                out.append({"scope": var, "outcome": f"{name}: {str(txt)[:380]}", "p": _num(probs.get(name)),
                            "horizon": "6m", "mechanism": str(v.get("mechanism") or "")[:600],
                            "triggers": [t.get("condition") if isinstance(t, dict) else t for t in (payload.get("revision_triggers") or [])][:8]})
    elif source == "inst_state":
        card = payload.get("forecast_card") or {}
        for key, hz in (("forecast_6m", "6m"), ("forecast_2y", "2y")):
            txt = card.get(key)
            if txt:
                out.append({"scope": key, "outcome": str(txt)[:600], "p": None, "horizon": hz,
                            "mechanism": str(card.get("mechanisms") or "")[:600],
                            "triggers": card.get("refutation_criteria") if isinstance(card.get("refutation_criteria"), list) else None})
        for sc in card.get("scenarios_5y") or []:
            if isinstance(sc, dict) and (sc.get("name") or sc.get("label") or sc.get("scenario")):
                out.append({"scope": "scenarios_5y", "outcome": str(sc.get("name") or sc.get("label") or sc.get("scenario"))[:400],
                            "p": _num(sc.get("probability") or sc.get("p")), "horizon": "5y",
                            "mechanism": str(sc.get("mechanism") or sc.get("description") or "")[:600], "triggers": None})
    elif source in ("council", "probe"):
        s = payload.get("synthesis") if source == "council" else payload
        fc = (s or {}).get("forecast") or {}
        probs = fc.get("probabilities") if isinstance(fc, dict) else None
        if probs is None and isinstance(payload.get("probabilities"), list):
            probs = payload.get("probabilities")
        for it in probs or []:
            if isinstance(it, dict) and it.get("outcome"):
                out.append({"scope": str(payload.get("label") or payload.get("id") or "")[:80] or None,
                            "outcome": str(it["outcome"])[:400], "p": _num(it.get("p")),
                            "horizon": _horizon_key(it.get("horizon")), "mechanism": str(it.get("basis") or "")[:600],
                            "triggers": (fc.get("triggers") if isinstance(fc, dict) else None)})
        if isinstance(fc, dict) and fc.get("most_dangerous"):
            out.append({"scope": str(payload.get("label") or "")[:80] or None, "outcome": "наиболее опасный: " + str(fc["most_dangerous"])[:380],
                        "p": None, "horizon": "6m", "mechanism": None, "triggers": None})
    return out


def record(db: Session, source: str, payload: dict, version_id: int | None = None) -> int:
    """Записать прогнозы выпуска; повтор того же дня (source, scope, outcome, horizon) не дублируется."""
    try:
        items = extract(source, payload)
        if not items:
            return 0
        as_of_s = payload.get("as_of")
        try:
            as_of = date.fromisoformat(str(as_of_s)) if as_of_s else date.today()
        except ValueError:
            as_of = date.today()
        mv = methodology_version()
        existing = {(e.scope, e.outcome, e.horizon) for e in
                    db.query(ForecastEntry).filter(ForecastEntry.source == source, ForecastEntry.as_of == as_of).all()}
        n = 0
        for it in items:
            key = (it.get("scope"), it["outcome"], it.get("horizon"))
            if key in existing:
                continue
            existing.add(key)
            db.add(ForecastEntry(source=source, version_id=version_id, scope=it.get("scope"), outcome=it["outcome"],
                                 p=it.get("p"), p_words=p_words(it.get("p")), horizon=it.get("horizon"),
                                 made_at=datetime.now(timezone.utc), as_of=as_of,
                                 review_at=_review_date(as_of, it.get("horizon") or "6m"),
                                 mechanism=it.get("mechanism"), triggers=it.get("triggers"),
                                 methodology_version=mv, status="open"))
            n += 1
        db.commit()
        if n:
            logger.info("forecast_journal: %s — записано %d прогнозов (версия #%s)", source, n, version_id)
        return n
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("forecast_journal: запись %s не удалась (%s)", source, e)
        return 0


# ─────────────────────────── сверка с фактом ───────────────────────────

_JUDGE_SYSTEM = (
    "Ты — судья журнала прогнозов Basis. Тебе дан прогноз, сделанный в прошлом (исход, вероятность, "
    "горизонт, механизм, пороговые события), и подборка того, что по этой теме есть в потоке платформы с "
    "даты прогноза до сегодня. Определи честно: исход подтвердился, опровергнут, реализовался частично, "
    "или по имеющимся данным сказать нельзя (unclear). Не додумывай факты: если в подборке нет — так и "
    "скажи. Ответь, какой механизм сработал, а какой нет, и сформулируй один урок для аналитика этого "
    "контура (как надо было рассуждать), без общих слов.\n"
    "ФОРМАТ (строго JSON): {\"status\": \"confirmed|refuted|partial|unclear\", \"realized\": \"<что произошло, "
    "с датами и источниками из подборки>\", \"mechanism_note\": \"<какой механизм сработал / нет>\", "
    "\"lesson\": \"<урок в одну-две фразы>\"}"
)

_CONTOUR_OF_SOURCE = {"geo": "geo", "macro": "macro", "inst_state": "inst_state", "council": None, "probe": None}


def _evidence(db: Session, entry: ForecastEntry) -> str:
    try:
        from app.services.feed_tools import search_feed
        days = max(7, (date.today() - (entry.as_of or date.today())).days + 1)
        q = " ".join(str(entry.outcome).split()[:8])
        found = search_feed(db, q, days=min(days, 730), limit=15)
        items = found.get("items") or []
        return json.dumps(items, ensure_ascii=False)[:12_000] if items else "— по запросу ничего не нашлось —"
    except Exception as e:  # noqa: BLE001
        return f"— поток недоступен ({type(e).__name__}) —"


def judge_entry(db: Session, entry: ForecastEntry) -> dict | None:
    from app.services import llm
    task = ("ПРОГНОЗ:\n" + json.dumps({"источник": entry.source, "область": entry.scope, "исход": entry.outcome,
                                       "вероятность": float(entry.p) if entry.p is not None else None,
                                       "словами": entry.p_words, "горизонт": entry.horizon,
                                       "сделан": entry.as_of.isoformat() if entry.as_of else None,
                                       "срок пересмотра": entry.review_at.isoformat(),
                                       "механизм": entry.mechanism, "пороговые события": entry.triggers},
                                      ensure_ascii=False)
            + "\n\nЧТО ЕСТЬ В ПОТОКЕ С ДАТЫ ПРОГНОЗА:\n" + _evidence(db, entry)
            + f"\n\nСегодня: {date.today().isoformat()}.")
    try:
        out = llm.complete(_JUDGE_SYSTEM, task, json_mode=True, max_tokens=2_000, temperature=0.1,
                           thinking=True, model=llm.pro_model())
        return out if isinstance(out, dict) and out.get("status") in ("confirmed", "refuted", "partial", "unclear") else None
    except Exception as e:  # noqa: BLE001
        logger.warning("forecast_journal judge #%s: %s", entry.id, e)
        return None


def review_due(db: Session, today: date | None = None, limit: int = 40) -> dict:
    """Сверить записи с наступившим сроком; уроки — в базу уроков контура."""
    today = today or date.today()
    due = (db.query(ForecastEntry).filter(ForecastEntry.status == "open", ForecastEntry.review_at <= today)
           .order_by(ForecastEntry.review_at.asc()).limit(limit).all())
    stats = {"due": len(due), "confirmed": 0, "refuted": 0, "partial": 0, "unclear": 0, "failed": 0}
    lessons_by_contour: dict[str, list[dict]] = {}
    for e in due:
        verdict = judge_entry(db, e)
        if not verdict:
            stats["failed"] += 1
            continue
        e.status = verdict["status"]; e.resolved_at = datetime.now(timezone.utc)
        e.realized = str(verdict.get("realized") or "")[:2000]
        e.resolution_note = str(verdict.get("mechanism_note") or "")[:2000]
        e.lesson = str(verdict.get("lesson") or "")[:1000]
        stats[verdict["status"]] += 1
        contour = _CONTOUR_OF_SOURCE.get(e.source)
        if contour and e.lesson and verdict["status"] in ("refuted", "partial"):
            lessons_by_contour.setdefault(contour, []).append(
                {"rule": f"прогноз: {str(e.outcome)[:80]}", "where": f"{e.source}/{e.scope or '-'}/{e.horizon}",
                 "severity": "существенно" if verdict["status"] == "refuted" else "мелочь", "fix": e.lesson,
                 "quote": str(e.realized)[:200]})
        db.commit()
    for contour, viol in lessons_by_contour.items():
        try:
            from app.services.lessons import harvest
            harvest(db, contour, viol)
        except Exception as ex:  # noqa: BLE001
            logger.warning("forecast_journal: уроки для %s не записаны (%s)", contour, ex)
    stats["calibration"] = calibration(db)
    logger.warning("forecast_journal: сверка — %s", stats)
    return stats


# ─────────────────────────── чтение и калибровка ───────────────────────────

def calibration(db: Session) -> dict:
    """По закрытым записям с числовой вероятностью: средняя p против доли подтвердившихся."""
    rows = (db.query(ForecastEntry).filter(ForecastEntry.status.in_(("confirmed", "refuted", "partial")),
                                           ForecastEntry.p.isnot(None)).all())
    by: dict[str, dict] = {}
    for r in rows:
        b = by.setdefault(r.source, {"n": 0, "p_sum": 0.0, "hits": 0.0})
        b["n"] += 1; b["p_sum"] += float(r.p); b["hits"] += {"confirmed": 1.0, "partial": 0.5, "refuted": 0.0}[r.status]
    return {src: {"n": b["n"], "avg_p": round(b["p_sum"] / b["n"], 3), "hit_rate": round(b["hits"] / b["n"], 3),
                  "bias": round(b["p_sum"] / b["n"] - b["hits"] / b["n"], 3)} for src, b in by.items() if b["n"]}


def listing(db: Session, status: str | None = None, source: str | None = None, limit: int = 100) -> dict:
    q = db.query(ForecastEntry)
    if status:
        q = q.filter(ForecastEntry.status == status)
    if source:
        q = q.filter(ForecastEntry.source == source)
    rows = q.order_by(ForecastEntry.review_at.asc(), ForecastEntry.id.desc()).limit(max(1, min(int(limit), 500))).all()
    counts = {}
    for r in db.query(ForecastEntry.source, ForecastEntry.status).all():
        counts.setdefault(r[0], {}).setdefault(r[1], 0); counts[r[0]][r[1]] += 1
    return {"count": len(rows), "counts": counts, "calibration": calibration(db),
            "items": [{"id": r.id, "source": r.source, "scope": r.scope, "outcome": r.outcome,
                       "p": float(r.p) if r.p is not None else None, "p_words": r.p_words, "horizon": r.horizon,
                       "as_of": r.as_of.isoformat() if r.as_of else None, "review_at": r.review_at.isoformat(),
                       "status": r.status, "realized": r.realized, "lesson": r.lesson,
                       "methodology_version": r.methodology_version, "version_id": r.version_id} for r in rows]}
