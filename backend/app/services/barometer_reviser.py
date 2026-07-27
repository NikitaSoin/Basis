"""Автономный агент-РЕВИЗОР барометров (гео/институты) — SHADOW-режим.

Владелец (2026-07-27): «убрать ручные перезапуски — агенты на DeepSeek сами
переделывают барометр с учётом новостей». Владелец выбрал путь «shadow
сначала». План — docs/autonomous-barometer-plan.md (ревью advisor).

РАМКА: автономное ОБСЛУЖИВАНИЕ калибровки, НЕ автономное суждение.
- агент НЕ переписывает барометр свободно и НЕ ежедневно;
- по СОБЫТИЙНОМУ триггеру от situation_overlay (сенсор) наследует экспертный
  ЯКОРЬ (баллы+rationale+anchor_note) и предлагает РЕВИЗИЮ на поводке:
  каждое движение балла обосновано ссылками на статьи ленты, суммарный дрейф
  от экспертной версии ограничен кодом;
- SHADOW: результат пишется status=draft, на бой НЕ публикуется (первые ~2
  недели наблюдения). Автопубликацию включает владелец отдельным решением.

Гейт качества (fail-closed, образец macro_addendum_agent._gate):
  схема · кэпы движения · поводок дрейфа · verifiable delta_rationale ·
  дословный перенос нетронутого rationale · комплаенс-блоклист.
Провал → status=rejected, published-версия не меняется.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import BarometerVersion, SituationOverlay
from app.models.geo_digest import GeoDigestArticle
from app.services import llm
from app.services.situation_overlay import _BLOCKLIST, _GREY_SOURCES

logger = logging.getLogger(__name__)

_BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FILES = {"geo": os.path.join(_BACKEND, "config", "geo_barometer.json"),
          "inst": os.path.join(_BACKEND, "config", "institutional_barometer.json")}
_KIND_SCOPES = {"geo": ("svo", "middle_east", "atr"), "inst": ("institutions",)}

# --- поводок и кэпы (гейт) ---
_MAX_STEP = 0.5          # |Δ| одного субиндекса за одну ревизию
_MAX_MOVED = 5           # сколько субиндексов можно сдвинуть за ревизию
_MAX_DRIFT = 1.0         # кумулятивный |дрейф| от экспертного якоря
_MAX_PROB_STEP = 0.10    # сдвиг вероятности сценария за ревизию
_WINDOW_DAYS = 14

# --- триггеры ревизии ---
_COOLDOWN_DAYS = 5       # анти-осцилляция: не чаще раза в 5 дней на барометр
_STALE_DAYS = 30         # плановая ревизия «для свежести» даже в тишине
_SHIFT_QUORUM = 4        # «сдвигает» в ≥4 из 7 последних оверлеев → ревизия


# ----------------------------- ЕДИНЫЙ READ-PATH -----------------------------
def get_current_barometer(db: Session, kind: str) -> tuple[dict | None, BarometerVersion | None]:
    """Текущий барометр: последняя published-версия из БД; если в БД ещё нет —
    импортирует экспертный файл как source=expert/published (паттерн
    asset_data — файл остаётся источником правды экспертного якоря, БД его
    зеркалит и версионирует). Возвращает (payload, row-якоря или None).

    NB: боевой фронт/эндпоинты и situation_overlay пока читают ФАЙЛ напрямую —
    их перевод на этот read-path идёт вместе с включением автопубликации (тогда
    же, чтобы не плодить расхождение). Сейчас (shadow) этим read-path пользуется
    только ревизор."""
    row = (db.query(BarometerVersion)
           .filter(BarometerVersion.kind == kind, BarometerVersion.status == "published")
           .order_by(BarometerVersion.created_at.desc()).first())
    if row is not None:
        return row.payload, row
    path = _FILES.get(kind)
    if not path or not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("barometer_reviser: файл якоря %s не прочитан: %s", kind, e)
        return None, None
    row = BarometerVersion(kind=kind, source="expert", status="published",
                           payload=payload, trigger_reason="import_from_file")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("barometer_reviser: экспертный якорь %s импортирован в БД как v#%d", kind, row.id)
    return payload, row


def _last_expert(db: Session, kind: str) -> BarometerVersion | None:
    return (db.query(BarometerVersion)
            .filter(BarometerVersion.kind == kind, BarometerVersion.source == "expert")
            .order_by(BarometerVersion.created_at.desc()).first())


# ----------------------------- ТРИГГЕР -----------------------------
def should_revise(db: Session, kind: str) -> tuple[bool, str | None]:
    """Пора ли ревизовать барометр kind. Все сигналы — из уже работающего
    situation_overlay (оверлей = сенсор). Возвращает (надо, причина)."""
    # cooldown: недавняя авторевизия (любой статус) → пропускаем
    recent = (db.query(BarometerVersion)
              .filter(BarometerVersion.kind == kind, BarometerVersion.source == "auto")
              .order_by(BarometerVersion.created_at.desc()).first())
    now = datetime.now(timezone.utc)
    if recent and (now - recent.created_at) < timedelta(days=_COOLDOWN_DAYS):
        return False, None

    scopes = _KIND_SCOPES[kind]
    overlays = (db.query(SituationOverlay)
                .filter(SituationOverlay.published.is_(True))
                .order_by(SituationOverlay.generated_at.desc()).limit(7).all())
    # 1) противоречие в самом свежем оверлее по любому scope барометра
    if overlays:
        latest = overlays[0].blocks or {}
        for sc in scopes:
            if (latest.get(sc) or {}).get("alignment") == "противоречит":
                return True, f"противоречие ленты по {sc}"
    # 2) накопленный сдвиг: «сдвигает»/«противоречит» в ≥quorum из 7 по одному scope
    for sc in scopes:
        n = sum(1 for o in overlays
                if (o.blocks or {}).get(sc, {}).get("alignment") in ("сдвигает", "противоречит"))
        if n >= _SHIFT_QUORUM:
            return True, f"накопленный сдвиг по {sc} ({n}/7)"
    # 3) свежесть: экспертный якорь давно, авторевизий тоже давно
    anchor = _last_expert(db, kind)
    last_any = recent or anchor
    if last_any and (now - last_any.created_at) >= timedelta(days=_STALE_DAYS):
        return True, f"плановая (>{_STALE_DAYS} дней без ревизии)"
    return False, None


# ----------------------------- ГЕЙТ -----------------------------
def _subindices(payload: dict) -> dict:
    return {s.get("key"): s for s in (payload.get("subindices") or []) if s.get("key")}


def _gate(revision: dict, anchor: dict, expert_anchor: dict,
          article_ids: set[str]) -> tuple[bool, list[str]]:
    """revision — предложение агента; anchor — версия-родитель (от неё дельта);
    expert_anchor — последний ЭКСПЕРТНЫЙ барометр (от него считаем поводок)."""
    notes: list[str] = []
    if not isinstance(revision, dict):
        return False, ["not_a_dict"]
    rev_si = _subindices(revision)
    anc_si = _subindices(anchor)
    exp_si = _subindices(expert_anchor)

    # схема: те же ключи, что у якоря
    if set(rev_si) != set(anc_si):
        notes.append(f"schema_keys_mismatch: {set(anc_si) ^ set(rev_si)}")

    moved = 0
    for key, rs in rev_si.items():
        a = anc_si.get(key)
        if not a:
            continue
        try:
            rscore = float(rs.get("score"))
        except (TypeError, ValueError):
            notes.append(f"{key}:score_not_number"); continue
        # балл в диапазоне и шаг 0.5
        if not (1.0 <= rscore <= 5.0):
            notes.append(f"{key}:score_out_of_range")
        if round(rscore * 2) != rscore * 2:
            notes.append(f"{key}:score_step")
        ascore = float(a.get("score")) if a.get("score") is not None else rscore
        step = abs(rscore - ascore)
        if step > _MAX_STEP + 1e-9:
            notes.append(f"{key}:step>{_MAX_STEP} ({ascore}→{rscore})")
        if step > 1e-9:
            moved += 1
            # каждое движение — с delta_rationale со ссылкой на реальные статьи
            dr = rs.get("delta_rationale") or ""
            cited = [t for t in (rs.get("evidence_ids") or []) if str(t) in article_ids]
            if not cited:
                notes.append(f"{key}:no_verifiable_evidence")
            if not dr.strip():
                notes.append(f"{key}:no_delta_rationale")
            # поводок: кумулятивный дрейф от ЭКСПЕРТНОГО якоря
            e = exp_si.get(key)
            if e and e.get("score") is not None:
                if abs(rscore - float(e.get("score"))) > _MAX_DRIFT + 1e-9:
                    notes.append(f"{key}:drift>{_MAX_DRIFT} от эксперта")
        else:
            # нетронутый субиндекс: rationale/anchor_note переносятся ДОСЛОВНО
            if (rs.get("rationale") or "") != (a.get("rationale") or ""):
                notes.append(f"{key}:rationale_edited_without_move")
    if moved > _MAX_MOVED:
        notes.append(f"too_many_moved: {moved}>{_MAX_MOVED}")

    # вероятности сценариев: Σ≈1 и сдвиг ≤ кэпа
    for hk in ("probabilities_6m", "probabilities_18m"):
        rp = (revision.get("scenario") or {}).get(hk)
        ap = (anchor.get("scenario") or {}).get(hk)
        if isinstance(rp, dict) and rp:
            s = sum(v for v in rp.values() if isinstance(v, (int, float)))
            if not (0.9 <= s <= 1.1):
                notes.append(f"{hk}:sum!=1 ({s:.2f})")
            if isinstance(ap, dict):
                for sk, v in rp.items():
                    if isinstance(v, (int, float)) and isinstance(ap.get(sk), (int, float)):
                        if abs(v - ap[sk]) > _MAX_PROB_STEP + 1e-9:
                            notes.append(f"{hk}:{sk}_step>{_MAX_PROB_STEP}")

    # комплаенс — тот же фильтр, что у оверлея
    blob = json.dumps(revision, ensure_ascii=False)
    m = _BLOCKLIST.search(blob)
    if m:
        notes.append(f"blocklist:{m.group(0)}")
    if _GREY_SOURCES.search(blob):
        notes.append("grey_source_named")
    return not notes, notes


# ----------------------------- ПРОГОН -----------------------------
_SYS = (
    "Ты — аналитик Basis, ОБСЛУЖИВАЕШЬ калибровку геополитического/"
    "институционального барометра. Тебе дан текущий барометр (ЯКОРЬ: баллы 1-5 "
    "по субиндексам с rationale и anchor_note) и свежие статьи ленты. Задача — "
    "предложить МИНИМАЛЬНУЮ ревизию баллов там, где события ленты этого требуют. "
    "ЖЁСТКИЕ ПРАВИЛА (нарушение → ревизия отклоняется):\n"
    f"- двигай балл максимум на ±{_MAX_STEP} за раз и не более {_MAX_MOVED} "
    "субиндексов; реальное событие не двигает все оси разом;\n"
    "- КАЖДОЕ изменение балла снабди delta_rationale (что именно в ленте "
    "сдвинуло) и evidence_ids — список id переданных статей-оснований;\n"
    "- субиндексы, которые НЕ меняешь, верни С ТЕМ ЖЕ score и ДОСЛОВНО тем же "
    "rationale/anchor_note (не переписывай прозу);\n"
    "- вероятности сценариев меняй максимум на ±0.10, сумма = 1;\n"
    "- РФ-топонимика, нейтральный тон, без «оккупир/аннексир/купить/продать», "
    "без имён СМИ-источников;\n"
    "Верни JSON РОВНО той же структуры, что якорь (subindices[], scenario{}), "
    "плюс у сдвинутых субиндексов поля delta_rationale и evidence_ids. "
    "Никакого текста вне JSON."
)


def revise(db: Session, kind: str, force: bool = False) -> BarometerVersion | None:
    """Один прогон ревизора. SHADOW: пишет draft/rejected, НЕ published.
    Возвращает строку BarometerVersion или None (если триггер не сработал и не
    force)."""
    trig_ok, reason = (True, "ручной") if force else should_revise(db, kind)
    if not trig_ok:
        return None

    anchor_payload, anchor_row = get_current_barometer(db, kind)
    if not anchor_payload:
        logger.warning("barometer_reviser: нет якоря для %s", kind)
        return None
    expert_row = _last_expert(db, kind)
    expert_payload = expert_row.payload if expert_row else anchor_payload

    # свежие статьи-основания по scope барометра
    cutoff = date.today() - timedelta(days=_WINDOW_DAYS)
    scopes = _KIND_SCOPES[kind]
    arts = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(scopes),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).limit(40).all())
    if not arts:
        logger.info("barometer_reviser: %s — нет свежих статей, ревизия не нужна", kind)
        return None
    article_ids = {str(a.id) for a in arts}
    articles_for_prompt = [{"id": str(a.id), "date": a.published_at.isoformat() if a.published_at else None,
                            "title": a.title, "summary": (a.summary or "")[:400]} for a in arts]

    user = ("ЯКОРЬ (текущий барометр — правь минимально):\n"
            + json.dumps(anchor_payload, ensure_ascii=False)[:24000]
            + "\n\nСВЕЖИЕ СТАТЬИ ЛЕНТЫ (id — для evidence_ids):\n"
            + json.dumps(articles_for_prompt, ensure_ascii=False))
    model = llm.pro_model()
    try:
        revision = llm.complete(_SYS, user, json_mode=True, model=model,
                                max_tokens=16000, temperature=0.2)
    except llm.LLMError as e:
        row = BarometerVersion(kind=kind, source="auto", status="rejected",
                               parent_id=anchor_row.id if anchor_row else None,
                               trigger_reason=reason, gate_notes=[f"llm_error:{e}"],
                               model_used=None)
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("barometer_reviser: %s LLM недоступен — rejected #%d", kind, row.id)
        return row

    ok, notes = _gate(revision, anchor_payload, expert_payload, article_ids)
    row = BarometerVersion(
        kind=kind, source="auto",
        status="draft" if ok else "rejected",   # SHADOW: даже прошедший гейт — draft, не published
        payload=revision if ok else None,
        parent_id=anchor_row.id if anchor_row else None,
        trigger_reason=reason, gate_notes=None if ok else notes,
        model_used=f"{llm.provider_info().get('provider')}:{model}")
    db.add(row); db.commit(); db.refresh(row)
    logger.info("barometer_reviser: %s → %s #%d (%s)%s", kind, row.status, row.id, reason,
                "" if ok else f" gate: {notes}")
    return row


def run_all(db: Session, force: bool = False) -> dict:
    """Обе барометра за прогон (крон). SHADOW."""
    out = {}
    for kind in ("geo", "inst"):
        try:
            row = revise(db, kind, force=force)
            out[kind] = {"id": row.id, "status": row.status, "trigger": row.trigger_reason,
                         "gate_notes": row.gate_notes} if row else "триггер не сработал"
        except Exception as e:  # noqa: BLE001
            logger.exception("barometer_reviser: %s упал: %s", kind, e)
            out[kind] = f"error: {type(e).__name__}"
    return out
