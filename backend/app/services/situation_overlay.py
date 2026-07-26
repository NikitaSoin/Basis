"""Оперативный слой-ОВЕРЛЕЙ «текущая ситуация по ленте» для геополитики и
институтов (Обозреватель, «Оценка ситуации»).

Владелец (2026-07-27): «у макро текущая ситуация постоянно обновляется, а в
геополитике и институтах — нет; надо чтобы с учётом поступающих новостей
текущая ситуация менялась; в геополитике — отдельно 3 категории СВО/БВ/АТР».

Образец — macro_interpreter.generate (тот же паттерн: снапшот → LLM → строка в
БД, версионируется). НО архитектурно это ДЕЛЬТА-СЛОЙ, не вторая оценка
(ревью advisor 2026-07-27):
  - экспертный барометр (geo_barometer.json / institutional_barometer.json)
    остаётся МЕТОДИЧЕСКИМ ЯКОРЁМ (баллы G1-G13/M1-M13, сценарии, калибровка) —
    оверлей его НЕ трогает и НЕ переписывает, только аннотирует;
  - вход: per-scope выжимка якоря + статьи geo_digest за окно дней по target;
  - выход по каждому scope: alignment ∈ {подтверждает|сдвигает|противоречит}
    относительно якоря + 3-5 атомарных тезисов (claim/detail/tag), БЕЗ баллов;
  - alignment=противоречит → фронт показывает плашку «лента расходится с
    экспертной оценкой» + это триггер на ручной перезапуск экспертного
    субагента (стык становится честной фичей, а не скрытым багом).

Четыре гардрейла fail-closed (все обязательны):
  1. детерминированный пост-фильтр (regex-блоклист) ПОСЛЕ LLM — промпт это
     пожелание, фильтр это гарантия; срабатывание → выпуск НЕ публикуется;
  2. fail-closed на ошибках LLM / пустой ленте — не публиковать частичный
     выпуск, фронт продолжает отдавать последний published;
  3. синтез ТОЛЬКО из переданных статей (они уже прошли слой классификации
     digest с редакционными конвенциями) — никаких утверждений вне ленты;
  4. источники серой зоны в публикуемый текст не пропускаем (обезличенно
     «по данным ленты»); имена источников в тезисы не тащим.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.geo import SituationOverlay
from app.models.geo_digest import GeoDigestArticle
from app.services import llm

logger = logging.getLogger(__name__)

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_GEO_BARO = os.path.join(_REPO, "config", "geo_barometer.json")
_INST_BARO = os.path.join(_REPO, "config", "institutional_barometer.json")

_WINDOW_DAYS = 10          # окно свежести статей ленты
_MIN_ARTICLES = 2         # меньше — честная деградация «существенных событий нет»
_SCOPES = ("svo", "middle_east", "atr", "institutions")
_SCOPE_TITLE = {"svo": "СВО / российская повестка", "middle_east": "Ближний Восток",
                "atr": "АТР", "institutions": "Институциональная среда РФ"}

# ---- ГАРДРЕЙЛ 1: детерминированный комплаенс-блоклист (РФ-юрисдикция) ----
# Срабатывание в ЛЮБОМ поле выпуска → весь выпуск fail-closed. Ловит: про-
# украинские формулировки территорий, инвестрекомендации, укр. написания
# ключевых топонимов. Не полагаемся на промпт (см. память feedback_ru_market_
# legal_framing + гардрейл-требование advisor).
_BLOCKLIST = re.compile(
    r"оккупир|аннексир|незаконн\w* присоедин|"
    r"рекоменд(уем|ация|ую)|购?куп(ить|ля)\s+(акци|облига|бумаг)|"
    r"\bпродать\b|стоит (купить|покупать|продавать)|"
    r"Бахмут|Артёмівськ|Бахмут|Покровськ|Часів Яр|Авдіївк|Куп'янськ|Херсо́н",
    re.IGNORECASE)
# Серая зона источников — не тиражируем имена в публикуемый текст (обезличиваем).
_GREY_SOURCES = re.compile(r"Meduza|Медуза|RFE|Радио Свобода|Настоящее время|The Insider", re.IGNORECASE)

_OUTPUT_SPEC = (
    "\n\n============ ФОРМАТ ОТВЕТА (СТРОГО JSON, на русском) ============\n"
    "Ты аннотируешь ЭКСПЕРТНЫЙ ЯКОРЬ свежей лентой — НЕ пишешь оценку заново. "
    "Никаких баллов, никакого пересмотра направления якоря, только дельта.\n"
    "Верни {\"blocks\": {\"<scope>\": {\n"
    "  \"alignment\": \"подтверждает\"|\"сдвигает\"|\"противоречит\", // как лента "
    "соотносится с якорем: подтверждает — новости в русле якоря; сдвигает — "
    "тон/интенсивность меняются, но не разворот; противоречит — лента прямо "
    "против направления якоря (напр. якорь 'эскалация', лента — деэскалация)\n"
    "  \"headline\": \"<что нового за период, 1 предложение до 20 слов>\",\n"
    "  \"theses\": [ // 3-5 штук, СТРОГО из переданных статей, без домыслов\n"
    "     {\"tag\": \"факт из ленты\"|\"оценка\", \"claim\": \"<тезис до 16 слов>\", "
    "\"detail\": \"<конкретика/числа из статей до 18 слов>\"}\n"
    "  ]\n"
    "}, ...}}. Ключи blocks — ТОЛЬКО те scope, по которым переданы статьи. "
    "Тон нейтральный, фактологический. РФ-топонимика (Артёмовск, не Бахмут; "
    "«перешёл под контроль», не «оккупирован»). БЕЗ «купить/продать/рекомендуем». "
    "НЕ упоминай названия СМИ-источников — обезличенно «по данным ленты». "
    "Никакого текста вне JSON."
)


def _load_anchor(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


def _anchor_digest_for_prompt() -> dict:
    """Компактная выжимка якорей — контекст, относительно которого меряем дельту."""
    geo = _load_anchor(_GEO_BARO)
    inst = _load_anchor(_INST_BARO)
    out = {}
    regions = geo.get("regions") or {}
    for scope in ("svo", "middle_east", "atr"):
        r = regions.get(scope) or {}
        out[scope] = {"anchor_label": r.get("label"), "anchor_direction": r.get("direction"),
                      "anchor_summary": (r.get("summary") or "")[:600], "anchor_as_of": r.get("as_of") or geo.get("as_of")}
    out["institutions"] = {"anchor_label": (inst.get("barometer") or {}).get("label"),
                            "anchor_scenario": (inst.get("scenario") or {}).get("current_lean")
                                               or (inst.get("scenario") or {}).get("current"),
                            "anchor_as_of": inst.get("as_of")}
    return out


def gather_articles(db: Session, window_days: int = _WINDOW_DAYS) -> dict:
    """Свежие статьи ленты по каждому scope (target). Только заголовок+пересказ —
    они уже прошли слой классификации digest (гардрейл 3)."""
    cutoff = date.today() - timedelta(days=window_days)
    by_scope: dict[str, list] = {s: [] for s in _SCOPES}
    rows = (db.query(GeoDigestArticle)
            .filter(GeoDigestArticle.target.in_(_SCOPES),
                    GeoDigestArticle.published_at >= cutoff)
            .order_by(GeoDigestArticle.published_at.desc()).all())
    for r in rows:
        by_scope.setdefault(r.target, []).append({
            "date": r.published_at.isoformat() if r.published_at else None,
            "title": r.title, "summary": (r.summary or "")[:500],
            "takeaways": r.key_takeaways if isinstance(r.key_takeaways, list) else None,
        })
    # кап на scope — не раздувать промпт (свежее уже сверху)
    return {s: v[:12] for s, v in by_scope.items()}


def _compliance_ok(blocks: dict) -> tuple[bool, str | None]:
    """Гардрейл 1: детерминированный пост-фильтр по всему тексту выпуска."""
    blob = json.dumps(blocks, ensure_ascii=False)
    m = _BLOCKLIST.search(blob)
    if m:
        return False, f"блоклист: '{m.group(0)}'"
    return True, None


def _sanitize_sources(blocks: dict) -> dict:
    """Гардрейл 4: обезличиваем имена источников серой зоны, если просочились."""
    def scrub(x):
        if isinstance(x, str):
            return _GREY_SOURCES.sub("по данным ленты", x)
        if isinstance(x, dict):
            return {k: scrub(v) for k, v in x.items()}
        if isinstance(x, list):
            return [scrub(v) for v in x]
        return x
    return scrub(blocks)


def generate(db: Session, window_days: int = _WINDOW_DAYS) -> SituationOverlay:
    """Суточный прогон оверлея. Fail-closed: при ошибке/пустой ленте/блоклисте
    пишем ряд с published=False (фронт отдаёт последний published, не этот)."""
    anchors = _anchor_digest_for_prompt()
    articles = gather_articles(db, window_days)
    counts = {s: len(articles.get(s) or []) for s in _SCOPES}

    # Гардрейл 2 (частично): scope с недостатком статей — честная деградация,
    # не высасываем синтез из воздуха.
    active = {s: articles[s] for s in _SCOPES if counts[s] >= _MIN_ARTICLES}
    snapshot = {"window_days": window_days, "counts": counts,
                "anchor_as_of": {s: anchors[s].get("anchor_as_of") for s in _SCOPES}}

    if not active:
        row = SituationOverlay(blocks={}, model_used=None, source_snapshot=snapshot,
                               published=False, blocked_reason="лента пуста по всем scope")
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("Оверлей ситуации: лента пуста — выпуск не опубликован (#%d)", row.id)
        return row

    system = (
        "Ты — старший аналитик Basis (независимая аналитика для инвестора в РФ). "
        "Задача: по СВЕЖИМ статьям ленты аннотировать экспертный якорь оценки "
        "геополитики/институтов — что изменилось за период. Только из переданных "
        "статей, без собственных суждений о территориях/санкциях сверх текста."
        + _OUTPUT_SPEC)
    user = ("ЯКОРЬ (экспертная оценка, НЕ переписывай — меряй дельту от неё):\n"
            + json.dumps({s: anchors[s] for s in active}, ensure_ascii=False, indent=1)
            + "\n\nСВЕЖИЕ СТАТЬИ ЛЕНТЫ по scope (за %d дней):\n" % window_days
            + json.dumps(active, ensure_ascii=False, indent=1))

    model = llm.pro_model()
    try:
        out = llm.complete(system, user, json_mode=True, model=model,
                           max_tokens=8000, temperature=0.3)
    except llm.LLMError as e:  # гардрейл 2: fail-closed на ошибке LLM
        row = SituationOverlay(blocks={}, model_used=None, source_snapshot=snapshot,
                               published=False, blocked_reason=f"LLM недоступен: {e}")
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("Оверлей ситуации: LLM недоступен — выпуск не опубликован (#%d)", row.id)
        return row

    blocks = out.get("blocks") if isinstance(out, dict) else None
    if not blocks or not isinstance(blocks, dict):
        row = SituationOverlay(blocks={}, model_used=f"{llm.provider_info().get('provider')}:{model}",
                               source_snapshot=snapshot, published=False,
                               blocked_reason="модель не вернула blocks")
        db.add(row); db.commit(); db.refresh(row)
        logger.warning("Оверлей ситуации: пустой ответ модели — не опубликован (#%d)", row.id)
        return row

    blocks = _sanitize_sources(blocks)               # гардрейл 4
    ok, reason = _compliance_ok(blocks)              # гардрейл 1
    published = ok
    row = SituationOverlay(
        blocks=blocks, generated_at=datetime.now(timezone.utc),
        model_used=f"{llm.provider_info().get('provider')}:{model}",
        source_snapshot=snapshot, published=published,
        blocked_reason=None if ok else f"комплаенс-фильтр — {reason}")
    db.add(row); db.commit(); db.refresh(row)
    if not ok:
        logger.warning("Оверлей ситуации: комплаенс-фильтр заблокировал выпуск #%d (%s)", row.id, reason)
    else:
        logger.info("Оверлей ситуации: опубликован #%d, scope=%s", row.id, list(blocks))
    return row


def get_latest_published(db: Session) -> SituationOverlay | None:
    return (db.query(SituationOverlay)
            .filter(SituationOverlay.published.is_(True))
            .order_by(SituationOverlay.generated_at.desc()).first())
