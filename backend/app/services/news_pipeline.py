"""Конвейер Ленты новостей Обозревателя (Направление 1).

Шаги: 1) сбор RSS (только новые) → 2) дедупликация в кластеры событий →
3) фильтр важности (LLM) → 4) выжимка + «на что влияет» (LLM) →
5) маппинг на тикеры/секторы (LLM + справочник Basis) → 6) запись в market_updates.

Вся работа с LLM идёт ТОЛЬКО через app.services.llm (провайдер-агностично).
Системные промпты — стабильные модульные константы (попадание в кэш провайдера).

Этот модуль — ФУНДАМЕНТ: разбор RSS, дедуп и батч-вызовы LLM переиспользуют
направления 2 (макро), 3 (отчёты), 7 (геополитика).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.market import MarketUpdate, NEWS_CATEGORIES
from app.services import llm

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "config", "news_sources.json")

_HTTP_TIMEOUT = 25.0
_UA = {"User-Agent": "BasisNewsBot/1.0 (+https://inbasis.ru)"}


# ----------------------------- конфиг -----------------------------
def load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ----------------------------- Шаг 1: RSS -----------------------------
def _clean_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&[a-z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(raw: str | None):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        # ISO-формат на всякий случай
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None


def fetch_feed(feed: dict, limit: int) -> list[dict]:
    """Загрузка одной RSS-ленты. Падение источника не роняет прогон (вернёт [])."""
    url = feed["url"]
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, headers=_UA, follow_redirects=True) as c:
            resp = c.get(url)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
    except Exception as e:  # noqa: BLE001
        logger.warning("RSS источник недоступен (%s): %s", url, type(e).__name__)
        return []

    items = []
    for item in root.iter("item"):
        def _t(tag):
            el = item.find(tag)
            return el.text if el is not None else None
        title = _clean_html(_t("title") or "")
        link = (_t("link") or "").strip()
        if not title or not link:
            continue
        items.append({
            "source": feed["source"],
            "rubric": feed.get("rubric", "economy"),
            "title": title,
            "announce": _clean_html(_t("description") or "")[:1200],
            "url": link,
            "published_at": _parse_date(_t("pubDate")),
        })
        if len(items) >= limit:
            break
    return items


def fetch_new_items(db: Session, cfg: dict) -> list[dict]:
    """Все ленты, ТОЛЬКО новые (которых ещё нет в БД по source_url)."""
    limit = int(cfg.get("max_items_per_feed", 60))
    raw: list[dict] = []
    for feed in cfg.get("feeds", []):
        if not feed.get("enabled", True):
            continue
        raw.extend(fetch_feed(feed, limit))

    if not raw:
        return []
    urls = [it["url"] for it in raw]
    existing = set(db.execute(
        select(MarketUpdate.source_url).where(MarketUpdate.source_url.in_(urls))
    ).scalars().all())
    # плюс дедуп внутри текущего прогона по url
    seen = set()
    new_items = []
    for it in raw:
        if it["url"] in existing or it["url"] in seen:
            continue
        seen.add(it["url"])
        new_items.append(it)
    logger.info("RSS: получено %d записей, новых %d", len(raw), len(new_items))
    return new_items


# ----------------------------- Шаг 2: дедупликация -----------------------------
_STOP = set("в во и на по за от до из о об с со к у не что как для при это года году".split())


def _norm_title(t: str) -> str:
    t = t.lower()
    t = re.sub(r"[^\wа-яё ]", " ", t)
    toks = [w for w in t.split() if w not in _STOP and len(w) > 2]
    return " ".join(toks)


def cluster_items(items: list[dict], threshold: float) -> list[dict]:
    """Группирует похожие новости (одно событие из разных источников) в кластер.

    Эвристика по схожести нормализованных заголовков (difflib). Каждому элементу
    проставляет cluster_idx; представитель кластера — самый ранний по времени.
    """
    norms = [_norm_title(it["title"]) for it in items]
    cluster_of = [-1] * len(items)
    clusters: list[list[int]] = []
    for i in range(len(items)):
        if cluster_of[i] != -1:
            continue
        cluster_of[i] = len(clusters)
        group = [i]
        for j in range(i + 1, len(items)):
            if cluster_of[j] != -1:
                continue
            if SequenceMatcher(None, norms[i], norms[j]).ratio() >= threshold:
                cluster_of[j] = cluster_of[i]
                group.append(j)
        clusters.append(group)
    for idx, it in enumerate(items):
        it["cluster_idx"] = cluster_of[idx]
    return items


def merge_clusters_llm(items: list[dict], threshold: float, low: float = 0.40,
                       max_pairs: int = 40) -> list[dict]:
    """Дослияние ПОГРАНИЧНЫХ кластеров через LLM («про одно событие?»).

    Эвристика по difflib не ловит парафразы разных источников. Берём пары
    представителей кластеров со схожестью заголовков в [low, threshold) и спрашиваем
    LLM, одно ли это событие; при «да» — сливаем. Только пограничные пары (дёшево).
    """
    # представитель каждого кластера = первый его элемент
    rep_idx: dict[int, int] = {}
    for i, it in enumerate(items):
        rep_idx.setdefault(it["cluster_idx"], i)
    reps = list(rep_idx.items())  # [(cluster_idx, item_index)]
    pairs = []
    for a in range(len(reps)):
        for b in range(a + 1, len(reps)):
            ca, ia = reps[a]; cb, ib = reps[b]
            r = SequenceMatcher(None, _norm_title(items[ia]["title"]),
                                _norm_title(items[ib]["title"])).ratio()
            if low <= r < threshold:
                pairs.append((ca, cb, ia, ib))
    if not pairs:
        return items
    pairs = pairs[:max_pairs]
    payload = {"pairs": [{"id": i, "a": items[ia]["title"], "b": items[ib]["title"]}
                         for i, (ca, cb, ia, ib) in enumerate(pairs)]}
    res = _llm_results(_DEDUP_SYS, payload)
    # union-find по подтверждённым «same»
    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        parent[find(x)] = find(y)
    for i, (ca, cb, ia, ib) in enumerate(pairs):
        if res.get(i, {}).get("same"):
            union(ca, cb)
    if parent:
        for it in items:
            it["cluster_idx"] = find(it["cluster_idx"])
    return items


# ----------------------------- LLM-промпты (СТАБИЛЬНЫЕ) -----------------------------
_FILTER_SYS = (
    "Ты — фильтр новостей для инвестиционно-аналитической платформы. Тебе дают список "
    "новостей (заголовок + анонс). Оставь только те, что СЕРЬЁЗНО влияют на финансовые "
    "рынки, отдельные компании/секторы или экономику РФ.\n"
    "ВАЖНО ПРО БАЛАНС: корпоративные, отраслевые и экономические новости часто "
    "сформулированы СПОКОЙНО и «тихо», но рыночно значимы НЕ МЕНЬШЕ громкой политики — НЕ "
    "недооценивай их и не отдавай ленту преимущественно политике. При наличии значимого "
    "корпоратива/экономики обязательно пропускай их наравне с геополитикой.\n"
    "ОСТАВЛЯЙ (равный приоритет всем пунктам):\n"
    "• КОРПОРАТИВНОЕ: финансовые отчётности и операционные результаты; прогнозы и гайденс; "
    "дивиденды/байбэки; M&A, крупные сделки и контракты; SPO/IPO/допэмиссии/выкупы; смена "
    "ключевого менеджмента и контроля; реструктуризации, дефолты, рейтинговые действия; "
    "крупные капвложения и новые проекты эмитентов;\n"
    "• ОТРАСЛЕВОЕ/РЕГУЛЯТОРНОЕ: изменения тарифов, пошлин, налогов, акцизов, квот; "
    "субсидии и господдержка секторов; новые отраслевые правила и ограничения;\n"
    "• МАКРО: решения ЦБ по ставке, инфляция, ВВП, промпроизводство, бюджет, курс рубля, "
    "цены на нефть/газ/ключевые сырьевые товары; крупные мировые экономические события "
    "(ФРС, мировые рынки, спрос), если влияют на РФ-рынок;\n"
    "• ГЕОПОЛИТИКА — только с ПРЯМЫМ понятным рыночным эффектом (санкции, нефтяная "
    "логистика, перекрытие проливов и т.п.).\n"
    "ОТСЕКАЙ как шум: фронтовые сводки без рыночного эффекта; проходные заявления чиновников "
    "без принятых решений; разовые высказывания политиков без конкретики; происшествия, спорт, "
    "светскую хронику, быт.\n"
    "importance: high — прямой и сильный эффект на рынок/крупного эмитента; medium — заметный, "
    "но косвенный/отраслевой; low (обычно keep=false) — слабый/неясный эффект.\n"
    "Верни строго JSON вида {\"results\": [{\"id\": <id>, \"keep\": true/false, "
    "\"importance\": \"high\"|\"medium\"|\"low\", \"reason\": \"<кратко>\"}]}. "
    "Никакого текста вне JSON."
)

_SUMMARY_SYS = (
    "По каждой новости верни: (1) summary — выжимка 2-3 предложения с КОНКРЕТНОЙ ФАКТУРОЙ из "
    "текста источника: суммы, числа, проценты, сроки/даты, кто именно (компания/ведомство/"
    "страна), и СТАТУС события; (2) impact — «на что влияет».\n"
    "ВАЖНО про глубину impact: у каждой новости передан importance (high/medium/low) — "
    "УЖЕ решено фильтром важности, не переоценивай его. Для importance=\"high\" impact "
    "делай РАЗВЁРНУТЫМ (2-4 предложения): назови КОНКРЕТНЫЙ механизм (через что именно "
    "событие влияет — выручку, маржу, стоимость долга, курс, спрос), КОГО затрагивает "
    "(конкретные бумаги/сектора, не общие слова) и ПОЧЕМУ это существенно именно сейчас "
    "(масштаб/контекст), а не просто констатируй факт влияния. Для medium/low — как раньше, "
    "1-2 сжатых предложения.\n"
    "СТАТУС события различай и называй явно, НЕ смешивай: «подписано/принято/вступает в силу» "
    "≠ «одобрено/рекомендовано» ≠ «обсуждается/на рассмотрении» ≠ «только заявлено/анонсировано» "
    "≠ «по данным СМИ/источников».\n"
    "ЖЁСТКОЕ ПРАВИЛО ДОВЕРИЯ: используй ТОЛЬКО информацию из переданного текста; НЕ добавляй "
    "цифры/суммы/имена/даты/прогнозы, которых в тексте НЕТ. Если RSS-анонс короткий и деталей в "
    "нём нет — НЕ догенерируй и НЕ выдумывай (это предел источника, передай факт обобщённо и "
    "честно). Не давай торговых рекомендаций.\n"
    "(3) category — РЕАЛЬНАЯ категория новости ПО СОДЕРЖАНИЮ (а не по разделу источника), строго "
    "одно из: \"Экономика\" (макро, ЦБ, инфляция, бюджет, налоги), \"Рынки\" (котировки, индексы, "
    "нефть/газ/валюта/сырьё, санкции на торговлю/нефть, нефтяная логистика), \"Бизнес\" (конкретные "
    "компании: отчётности, дивиденды, M&A, менеджмент, проекты), \"Политика\" (внутренняя политика/"
    "власть без прямого рыночного механизма), \"Геополитика\" (международные конфликты/отношения). "
    "Если новость про рынок/нефть/санкции — это \"Рынки\", даже если пришла из политического раздела.\n"
    "Формат строго JSON вида {\"results\": [{\"id\": <id>, \"summary\": \"...\", "
    "\"impact\": \"...\", \"category\": \"...\"}]}. Никакого текста вне JSON."
)

_MAP_SYS = (
    "Ты сопоставляешь новость с затронутыми публичными компаниями (по их тикерам) и секторами. "
    "Тебе дают новость (выжимка) и СПРАВОЧНИК компаний платформы (тикер — название — сектор). "
    "Верни тикеры ТОЛЬКО из справочника, которые новость затрагивает ПРЯМО и однозначно, и "
    "секторы, на которые она влияет. Если уверенной привязки нет — верни пустые списки, НЕ "
    "придумывай ложных связей. Формат строго JSON вида {\"results\": [{\"id\": <id>, "
    "\"tickers\": [\"SBER\"], \"sectors\": [\"banks\"]}]}. Никакого текста вне JSON."
)

_DEDUP_SYS = (
    "Тебе дают пары новостей. Для каждой пары ответь, описывают ли они ОДНО И ТО ЖЕ событие. "
    "Формат строго JSON вида {\"results\": [{\"id\": <id>, \"same\": true/false}]}. Без текста вне JSON."
)

_EXTRACT_SYS = (
    "Ты извлекаешь ЧИСЛОВЫЕ макропоказатели РФ из новостей-статрелизов для графиков. "
    "Тебе дают список новостей и СПРАВОЧНИК показателей (код — описание — допустимые метрики). "
    "Для КАЖДОЙ новости, где явно сообщается значение показателя из справочника, верни дата-точку.\n"
    "КРИТИЧНО ДЛЯ ДОВЕРИЯ:\n"
    "1) Точно различай тип метрики: mom = к предыдущему месяцу (м/м), yoy = к тому же месяцу "
    "год назад (г/г, «в годовом выражении»), wow = неделя к неделе (недельная), level = уровень/"
    "значение (ставка, безработица, PMI, ожидания). Спутать м/м и г/г НЕЛЬЗЯ.\n"
    "2) as_of — дата КОНЦА периода, к которому относится число (инфляция за май 2026 → 2026-05-31; "
    "неделя по 9 июня → 2026-06-09). Формат YYYY-MM-DD.\n"
    "3) is_preliminary=true, если число предварительное/оценка/Росстат уточнит; иначе false.\n"
    "4) Если НЕ однозначно, какой это показатель/период/метрика — НЕ извлекай (лучше пропустить, "
    "чем записать неверно). Бери только то, что прямо в тексте.\n"
    "5) value — число (точка как десятичный разделитель), знак сохраняй (дефицит/спад — отрицательно).\n"
    "Формат строго JSON: {\"results\": [{\"id\": <id новости>, \"indicator\": \"<код>\", "
    "\"metric\": \"mom|yoy|wow|level\", \"value\": <число>, \"as_of\": \"YYYY-MM-DD\", "
    "\"is_preliminary\": true|false}]}. Новости без чёткого показателя в results НЕ включай. "
    "Никакого текста вне JSON."
)


def _llm_results(system: str, payload: dict, max_tokens: int = 8192) -> dict:
    """Зовёт LLM, возвращает {id: record} из ответа {"results":[...]}."""
    try:
        out = llm.complete(system, json.dumps(payload, ensure_ascii=False),
                           json_mode=True, max_tokens=max_tokens)
    except llm.LLMError as e:
        logger.error("LLM-шаг не выполнен: %s", e)
        return {}
    rows = out.get("results") if isinstance(out, dict) else out
    res = {}
    for r in rows or []:
        if isinstance(r, dict) and "id" in r:
            res[r["id"]] = r
    return res


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


# ----------------------------- Шаги 3-5 -----------------------------
def filter_importance(reps: list[dict], batch: int = 25) -> dict:
    """Фильтр важности пачками (большой батч → обрезка JSON; см. _chunks)."""
    res = {}
    for ch in _chunks(reps, batch):
        payload = {"news": [{"id": r["id"], "title": r["title"], "announce": r["announce"]}
                            for r in ch]}
        res.update(_llm_results(_FILTER_SYS, payload, max_tokens=8192))
    return res


def summarize(reps: list[dict], batch: int = 15) -> dict:
    """reps должны нести importance (проставлено шагом фильтра, run_pipeline) —
    от него зависит глубина impact (см. _SUMMARY_SYS)."""
    res = {}
    for ch in _chunks(reps, batch):
        payload = {"news": [{"id": r["id"], "title": r["title"], "text": r["announce"],
                             "importance": r.get("importance", "medium")}
                            for r in ch]}
        res.update(_llm_results(_SUMMARY_SYS, payload, max_tokens=8192))
    return res


def map_tickers(reps: list[dict], db: Session, batch: int = 20) -> dict:
    ref = [{"ticker": c.ticker, "name": c.name, "sector": c.sector or ""}
           for c in db.query(Company).order_by(Company.ticker).all()]
    valid = {c["ticker"] for c in ref}
    res = {}
    for ch in _chunks(reps, batch):
        payload = {"directory": ref,
                   "news": [{"id": r["id"], "summary": r.get("summary") or r["title"]} for r in ch]}
        raw = _llm_results(_MAP_SYS, payload, max_tokens=8192)
        for rid, rec in raw.items():
            rec["tickers"] = [t for t in (rec.get("tickers") or []) if t in valid]
            rec["sectors"] = [s for s in (rec.get("sectors") or []) if isinstance(s, str)]
            res[rid] = rec
    return res


# ----------------------------- Извлечение числовых дата-точек (Макрообзор) -----------------------------
def _parse_asof(s: str):
    from datetime import date as _d, datetime as _dt
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            dt = _dt.strptime(s, fmt).date()
            if fmt == "%Y-%m":  # только месяц → последний день месяца
                nm = dt.replace(day=28)
                while True:
                    try:
                        nm2 = nm.replace(day=nm.day + 1)
                    except ValueError:
                        return nm
                    nm = nm2
            return dt
        except ValueError:
            continue
    return None


def extract_macro_points(reps: list[dict], db: Session, batch: int = 12) -> dict:
    """Извлекает числовые дата-точки макропоказателей из новостей-статрелизов и
    кладёт в ряды Макрообзора (ingested_via='news'). Строгая валидация диапазонов;
    различение м/м vs г/г; пометка предварительных. Возвращает сводку."""
    try:
        from app.services.macro_ingest import load_macro_config, upsert_point
    except Exception:  # noqa: BLE001
        return {"saved": 0, "note": "macro module unavailable"}
    cfg = load_macro_config()
    targets = cfg.get("news_extract", {})
    catalog = [{"code": c, "name": v["name"], "metrics": v["metrics"]}
               for c, v in targets.items() if isinstance(v, dict) and "name" in v]
    if not catalog or not reps:
        return {"saved": 0}
    saved = rejected = 0
    for ch in _chunks(reps, batch):
        payload = {"indicators": catalog,
                   "news": [{"id": r["id"], "title": r["title"], "text": r["announce"]} for r in ch]}
        rows = _llm_results(_EXTRACT_SYS, payload, max_tokens=4096)
        for rid, rec in rows.items():
            code = rec.get("indicator"); metric = rec.get("metric")
            spec = targets.get(code)
            if not spec or metric not in spec.get("metrics", []):
                rejected += 1
                continue
            as_of = _parse_asof(rec.get("as_of", ""))
            try:
                val = float(rec.get("value"))
            except (TypeError, ValueError):
                val = None
            if as_of is None or val is None:
                rejected += 1
                continue
            # валидация диапазона (отбрасываем явные ошибки распознавания)
            if not (spec["min"] <= val <= spec["max"]):
                logger.warning("Макро-извлечение: %s=%s вне диапазона [%s,%s] — отброшено",
                               code, val, spec["min"], spec["max"])
                rejected += 1
                continue
            # источник новости
            rep = next((r for r in reps if r["id"] == rid), None)
            res = upsert_point(db, code, as_of, metric, val,
                               unit=spec.get("unit"), is_preliminary=bool(rec.get("is_preliminary")),
                               source=rep["source"] if rep else "news",
                               source_url=rep["url"] if rep else None,
                               ingested_via="news", commit=False)
            if res in ("insert", "revise"):
                saved += 1
    db.commit()
    return {"saved": saved, "rejected": rejected}


# ----------------------------- Шаг 6: оркестрация + запись -----------------------------
def run_pipeline(db: Session) -> dict:
    """Полный прогон. Возвращает сводку для лога/диагностики."""
    cfg = load_config()
    items = fetch_new_items(db, cfg)
    if not items:
        return {"fetched": 0, "published": 0, "filtered_out": 0, "note": "нет новых записей"}

    thr = float(cfg.get("dedup_title_similarity", 0.62))
    items = cluster_items(items, thr)
    if cfg.get("dedup_llm", True):
        items = merge_clusters_llm(items, thr)

    # представитель каждого кластера (самый ранний) + сбор всех источников события
    by_cluster: dict[int, list[dict]] = {}
    for it in items:
        by_cluster.setdefault(it["cluster_idx"], []).append(it)
    reps = []
    for cidx, group in by_cluster.items():
        group.sort(key=lambda x: x["published_at"] or datetime.now(timezone.utc))
        rep = dict(group[0])
        rep["id"] = cidx
        rep["sources_json"] = [{"source": g["source"], "url": g["url"]} for g in group]
        reps.append(rep)

    # Шаг 3 — фильтр важности. ВАЖНО: различаем «явно решено» и «нет решения»
    # (сбой LLM). Неоценённые НЕ сохраняем вовсе — чтобы их переобработал
    # следующий прогон, а не потерять как ложно-отфильтрованные.
    keep_map = filter_importance(reps)
    kept = [r for r in reps if keep_map.get(r["id"], {}).get("keep") is True]
    rejected = [r for r in reps if r["id"] in keep_map
                and keep_map[r["id"]].get("keep") is False]
    undecided = len(reps) - len(kept) - len(rejected)
    if undecided:
        logger.warning("News: %d событий без решения фильтра (сбой LLM?) — будут переобработаны",
                       undecided)
    # importance из шага фильтра — нужен summarize() для глубины impact
    for r in kept:
        r["importance"] = keep_map.get(r["id"], {}).get("importance", "medium")

    # Шаг 4 — выжимка + impact (только по прошедшим фильтр)
    sum_map = summarize(kept) if kept else {}
    for r in kept:
        s = sum_map.get(r["id"], {})
        r["summary"] = (s.get("summary") or "").strip() or None
        r["impact"] = (s.get("impact") or "").strip() or None
        cat = (s.get("category") or "").strip()
        r["category"] = cat if cat in NEWS_CATEGORIES else None

    # Шаг 5 — маппинг тикеры/секторы
    map_map = map_tickers(kept, db) if kept else {}

    # Шаг 5-бис — извлечение числовых дата-точек макропоказателей (Конвейер 1, канал news)
    macro_extract = extract_macro_points(kept, db) if kept else {"saved": 0}

    model_used = f"{llm.provider_info().get('provider')}:{llm.provider_info().get('model')}"
    now = datetime.now(timezone.utc)
    published = 0
    published_rows: list[MarketUpdate] = []
    for r in kept:
        km = keep_map.get(r["id"], {})
        mm = map_map.get(r["id"], {})
        cluster_id = f"{now.strftime('%Y%m%d%H%M')}-{r['id']}"
        row = MarketUpdate(
            title=r["title"][:500],
            original_title=r["title"][:500],
            content=(r["announce"] or None),
            source=r["source"],
            source_url=r["url"],
            rubric=r["rubric"],
            category=r.get("category"),
            published_at=r["published_at"] or now,
            fetched_at=now,
            importance=km.get("importance") if km.get("importance") in ("high", "medium", "low") else "medium",
            summary=r.get("summary"),
            impact_comment=r.get("impact"),
            affected_tickers=mm.get("tickers") or [],
            affected_sectors=mm.get("sectors") or [],
            cluster_id=cluster_id,
            sources_json=r["sources_json"],
            model_used=model_used,
            status="published",
        )
        db.add(row)
        published_rows.append(row)
        published += 1

    # отфильтрованные (ЯВНО keep=false) сохраняем «лёгкими» строками: чтобы их
    # source_url попал в БД и они НЕ переобрабатывались. Неоценённые (сбой LLM)
    # сюда НЕ попадают — их подхватит следующий прогон.
    for r in rejected:
        km = keep_map.get(r["id"], {})
        db.add(MarketUpdate(
            title=r["title"][:500], original_title=r["title"][:500],
            source=r["source"], source_url=r["url"], rubric=r["rubric"],
            published_at=r["published_at"] or now, fetched_at=now,
            importance=km.get("importance") if km.get("importance") in ("high", "medium", "low") else "low",
            sources_json=r["sources_json"], model_used=model_used, status="filtered_out",
        ))

    db.commit()

    # Промоут важных новостей в аналитическую летопись (постоянная память агентов).
    # ОТДЕЛЬНЫЙ commit после основного: баг летописи не должен ронять новостной крон;
    # пропущенное подхватит идемпотентный catch-up бэкфилла (chronicle_backfill).
    chronicled = 0
    try:
        from app.services.chronicle import ingest_market_update
        for row in published_rows:
            if ingest_market_update(db, row) is not None:
                chronicled += 1
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("News→chronicle: пропущено из-за %s (подхватит бэкфилл)", type(e).__name__)

    summary = {"fetched": len(items), "clusters": len(reps),
               "published": published, "filtered_out": len(rejected),
               "undecided": undecided, "macro_points": macro_extract.get("saved", 0),
               "chronicled": chronicled, "model": model_used}
    logger.info("News pipeline: %s", summary)
    return summary
