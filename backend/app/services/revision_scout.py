"""Активная ревизия карточек: агент идёт и проверяет, изменилось ли что-нибудь.

🔴 Владелец, 2026-08-26: «возможно, изменений нет потому, что не вся информация
появилась — надо сделать механизм дополнительной перепроверки; и если нашли информацию,
источник, с которого её тянули, должен попасть в пул источников».

В чём разница с тем, что было. Патчер прозы РЕАКТИВЕН: он ждёт сигнала во входном
потоке и правит вкладку под него. Пока сигнала нет, вкладка молчит — и выглядит это как
«изменений нет», хотя честный ответ другой: «мы не смотрели». Замер, который это
показал: по институтам за 30 дней пришло 11 сигналов на 5 компаний из 264, по
геополитике — 33 на 14. Ждать такого потока по каждой компании бессмысленно, его просто
нет: 13 лент физически не покрывают 264 эмитента и 513 эмитентов облигаций.

Ревизия работает наоборот — ПО КРУГУ. Берёт объекты, которых дольше всего не проверяли,
и сама идёт искать: узкий веб-поиск по теме вкладки → строгое извлечение → сверка с тем,
что уже написано в разборе. Нашла существенное — заводит сигнал в ту же шину, и вкладку
правит уже существующий патчер под своим гейтом (второй раз механику правки не пишем).
Не нашла — записывает факт проверки, и объект уходит в конец круга.

Побочный, но важный эффект: каждый адрес, откуда взят факт, уходит в пул источников
(`source_pool`). Домен, пригодившийся несколько раз, становится постоянной лентой — то
есть платформа сама расширяет свой входной поток вместо того, чтобы ждать, пока это
заметит человек.

Что здесь НЕ делается: ревизия не переписывает прозу и не публикует ничего сама. Её
выход — сигнал с ссылкой на источник. Это сознательно: правка проходит через гейт
патчера, а не через второй, отдельно написанный и отдельно ломающийся путь.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.geo import CardProseOverlay, CompanySignal
from app.services import llm

logger = logging.getLogger(__name__)

# Вкладка → (как называть тему в запросе, вкладка сигнала для шины)
_TOPICS = {
    "governance": ("акционеры, дивидендная политика, совет директоров, менеджмент",
                   "governance"),
    "institutions": ("государство, регулирование, суды, налоги, госзаказ", "institutions"),
    "geo": ("санкции, экспортные рынки, логистика, зарубежные активы", "geo"),
    "business": ("сделки, слияния и поглощения, новые активы, инвестпрограмма", "ma"),
    "markets": ("рынок сбыта, цены на продукцию, доля рынка, конкуренты", "markets"),
    "finance": ("выручка, прибыль, долг, отчётность", "finance"),
}

# Как часто один и тот же объект×вкладка попадает на ревизию
_CIRCLE_DAYS = 30
# Ревизия дороже патча (поиск + извлечение), поэтому партия маленькая, но круг
# закрывается: 20 пар в день × 30 дней = 600 проверок, а пар (264 компании × 6 вкладок)
# полторы тысячи — то есть полный круг примерно за два с половиной месяца по всем
# вкладкам сразу, и месяц по любой отдельной.
_BATCH = 20

_SYS = (
    "Ты — ревизор аналитической карточки. Тебе дают КРАТКОЕ содержание того, что уже "
    "написано в разборе, и свежие материалы из поиска. Твоя работа — найти то, чего в "
    "разборе НЕТ и что меняет картину: сделка, смена собственника, решение регулятора, "
    "новая программа, санкция, суд, крупный контракт, изменение дивидендной политики.\n"
    "Верни строго JSON: {\"changed\": true|false, \"facts\": [{\"claim\": \"<одно "
    "предложение, что именно произошло>\", \"date\": \"YYYY-MM-DD или пусто\", "
    "\"url\": \"<адрес источника из списка>\", \"source\": \"<название издания>\"}], "
    "\"note\": \"<если changed=false — почему: всё уже отражено / ничего значимого>\"}\n"
    "ЖЁСТКО: (1) только про указанную компанию, однофамильцев и тёзок не брать; "
    "(2) факт должен быть НОВЫМ по отношению к разбору — пересказ уже написанного не "
    "нужен; (3) слухи, прогнозы аналитиков и «источники сообщают» не факты — их не "
    "берём; (4) url обязателен и должен быть из переданного списка; (5) максимум три "
    "самых важных факта. Ничего существенного нет — {\"changed\": false}. "
    "Никакого текста вне JSON."
)


def _prose_digest(db: Session, ticker: str, tab: str, limit: int = 1800) -> str:
    """Что уже написано во вкладке (оверлей → файл), сжато до головы разбора."""
    try:
        from app.services.card_prose_patcher import read_prose
        md, _ = read_prose(db, ticker, tab)
    except Exception:  # noqa: BLE001
        md = None
    return (md or "")[:limit]


def _candidates(db: Session, batch: int, tabs: list[str] | None) -> list[tuple[str, str]]:
    """Пары (тикер, вкладка), которых дольше всего не проверяли."""
    tickers = [r[0] for r in db.execute(text(
        "SELECT ticker FROM companies ORDER BY market_cap DESC NULLS LAST")).all()]
    if not tickers:
        return []
    use_tabs = [t for t in (tabs or list(_TOPICS)) if t in _TOPICS]
    seen: dict[tuple[str, str], datetime] = {}
    for tk, tab, ts in db.query(CardProseOverlay.ticker, CardProseOverlay.tab,
                                func.max(CardProseOverlay.created_at)).group_by(
            CardProseOverlay.ticker, CardProseOverlay.tab).all():
        seen[(tk.upper(), tab)] = ts
    # ревизия тоже считается «касанием»: её след — сигнал источника revision_scout
    for tk, tab, ts in db.query(CompanySignal.ticker, CompanySignal.card_tab,
                                func.max(CompanySignal.created_at)).filter(
            CompanySignal.source_key == "revision_scout").group_by(
            CompanySignal.ticker, CompanySignal.card_tab).all():
        prose_tab = next((p for p, (_, st) in _TOPICS.items() if st == tab), None)
        if not prose_tab:
            continue
        key = (tk.upper(), prose_tab)
        if key not in seen or (ts and seen[key] and ts > seen[key]):
            seen[key] = ts
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_CIRCLE_DAYS)
    pairs = [(tk, tab) for tk in tickers for tab in use_tabs
             if (seen.get((tk, tab)) or epoch) < cutoff]
    pairs.sort(key=lambda p: seen.get(p) or epoch)
    return pairs[:batch]


def _search(name: str, ticker: str, topic: str) -> list[dict]:
    from app.services.agent_web import web_search
    year = date.today().year
    out: list[dict] = []
    for q in (f"{name} {topic} {year}", f"{name} новости {topic}"):
        try:
            res = web_search(q, 6)
        except Exception as e:  # noqa: BLE001
            logger.warning("revision_scout: поиск упал (%s)", type(e).__name__)
            continue
        if isinstance(res, dict) and not res.get("error"):
            out.extend(r for r in (res.get("results") or []) if isinstance(r, dict))
        if len(out) >= 8:
            break
    return out[:10]


def _make_signal(db: Session, ticker: str, prose_tab: str, fact: dict) -> bool:
    """Завести сигнал в шину — дальше вкладку правит патчер под своим гейтом."""
    signal_tab = _TOPICS[prose_tab][1]
    claim = str(fact.get("claim") or "").strip()
    url = str(fact.get("url") or "").strip()
    if len(claim) < 25 or not url.startswith("http"):
        return False
    dedup = hashlib.sha1(f"{ticker}|{prose_tab}|{claim[:120]}".encode()).hexdigest()[:32]
    exists = db.query(CompanySignal.id).filter(
        CompanySignal.ticker == ticker, CompanySignal.signal_type == "revision",
        CompanySignal.dedup_key == dedup).first()
    if exists:
        return False
    try:
        pub = date.fromisoformat(str(fact.get("date"))[:10])
    except (TypeError, ValueError):
        pub = date.today()
    db.add(CompanySignal(
        ticker=ticker, signal_type="revision", card_tab=signal_tab,
        importance="high", trust="media", internal=False,
        title=claim[:400], summary=f"Найдено ревизией карточки ({prose_tab}). {claim}"[:2000],
        source_key="revision_scout", source_url=url[:1000],
        published_at=pub, dedup_key=dedup))
    return True


# ---------------------- ревизия ЭМИТЕНТОВ облигаций ----------------------
# Владелец, 2026-08-26: «по облигациям не исключаю, что вообще нужна отдельная очередь,
# когда агент отправляется и проверяет, есть ли изменения». Так и есть: у эмитента нет
# тикера и нет входного потока — 13 лент про непубличную лизинговую компанию не пишут
# никогда. Единственный способ узнать, что у неё сменился собственник или вышел новый
# рейтинг, — пойти и посмотреть.
_ISSUER_TOPICS = {
    "issuer_risk": "рейтинг, дефолт, реструктуризация, суд, долговая нагрузка",
    "issuer_business": "бизнес, собственники, сделки, новые проекты",
    "issuer_financials": "выручка, прибыль, отчётность, облигационный выпуск",
}
_ISSUER_CIRCLE_DAYS = 60      # профилей 513 — круг длиннее, чем у компаний
_ISSUER_BATCH = 10


def _issuer_name(slug: str) -> str:
    """Человеческое имя эмитента из слага папки."""
    return slug.replace("_cat-", "").replace("-", " ").strip()


def _issuer_candidates(db: Session, batch: int, tabs: list[str] | None) -> list[tuple[str, str]]:
    from app.services.card_prose_patcher import ISSUERS_DIR
    if not ISSUERS_DIR.exists():
        return []
    slugs = sorted(d.name for d in ISSUERS_DIR.iterdir()
                   if d.is_dir() and not d.name.startswith("."))
    use = [t for t in (tabs or list(_ISSUER_TOPICS)) if t in _ISSUER_TOPICS]
    seen: dict[tuple[str, str], datetime] = {}
    for tk, tab, ts in db.query(CardProseOverlay.ticker, CardProseOverlay.tab,
                                func.max(CardProseOverlay.created_at)).filter(
            CardProseOverlay.tab.in_(list(_ISSUER_TOPICS))).group_by(
            CardProseOverlay.ticker, CardProseOverlay.tab).all():
        seen[(tk.lower(), tab)] = ts
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_ISSUER_CIRCLE_DAYS)
    pairs = [(s, tab) for s in slugs for tab in use
             if (seen.get((s.lower(), tab)) or epoch) < cutoff]
    pairs.sort(key=lambda p: seen.get((p[0].lower(), p[1])) or epoch)
    return pairs[:batch]


def run_issuer_revision(db: Session, batch: int = _ISSUER_BATCH,
                        tabs: list[str] | None = None,
                        only_slug: str | None = None) -> dict:
    """Ревизия профилей эмитентов облигаций: проверить и вписать найденное."""
    from app.services.card_prose_patcher import read_prose, run_issuer_add

    pairs = ([(only_slug, t) for t in (tabs or list(_ISSUER_TOPICS))] if only_slug
             else _issuer_candidates(db, batch, tabs))
    stats = {"проверено": 0, "с изменениями": 0, "правок опубликовано": 0,
             "правок отклонено": 0, "источников записано": 0, "details": []}
    for slug, tab in pairs:
        name = _issuer_name(slug)
        results = _search(name, slug, _ISSUER_TOPICS[tab])
        if not results:
            stats["details"].append({"эмитент": slug, "раздел": tab, "note": "поиск пуст"})
            continue
        try:
            prose, _ = read_prose(db, slug, tab)
        except Exception:  # noqa: BLE001
            prose = None
        if not prose:
            stats["details"].append({"эмитент": slug, "раздел": tab, "note": "нет профиля"})
            continue
        payload = {"issuer": name, "tab": tab, "already_written": prose[:1800],
                   "found": [{"title": r.get("title"),
                              "text": str(r.get("snippet") or "")[:400],
                              "url": r.get("url")} for r in results]}
        try:
            out = llm.complete(_SYS, json.dumps(payload, ensure_ascii=False),
                               json_mode=True, max_tokens=900)
        except llm.LLMError as e:
            logger.warning("revision_scout: эмитент %s/%s — LLM не отработал: %s",
                           slug, tab, e)
            continue
        stats["проверено"] += 1
        if not isinstance(out, dict) or not out.get("changed"):
            stats["details"].append({"эмитент": slug, "раздел": tab,
                                     "note": str((out or {}).get("note") or "")[:80]})
            continue
        stats["с изменениями"] += 1
        for f in [x for x in (out.get("facts") or []) if isinstance(x, dict)][:2]:
            try:
                row = run_issuer_add(db, slug, tab, f)
            except Exception:  # noqa: BLE001
                logger.exception("revision_scout: правка профиля %s не прошла", slug)
                continue
            if row is not None:
                key = "правок опубликовано" if row.status == "published" else "правок отклонено"
                stats[key] += 1
            try:
                from app.services.source_pool import record_find
                if record_find(db, str(f.get("url") or ""), topic=tab, found_for=slug,
                               note=str(f.get("source") or "")[:200]):
                    stats["источников записано"] += 1
            except Exception:  # noqa: BLE001
                logger.warning("revision_scout: источник эмитента не записан", exc_info=True)
        db.commit()
    logger.info("revision_scout(эмитенты): %s",
                {k: v for k, v in stats.items() if k != "details"})
    return stats


def run_revision(db: Session, batch: int = _BATCH, tabs: list[str] | None = None,
                 only_ticker: str | None = None) -> dict:
    """Один прогон ревизии по кругу. Возвращает сводку."""
    from app.models.company import Company

    if only_ticker:
        pairs = [(only_ticker.upper(), t) for t in (tabs or list(_TOPICS))]
    else:
        pairs = _candidates(db, batch, tabs)
    stats = {"проверено": 0, "с изменениями": 0, "новых сигналов": 0,
             "источников записано": 0, "без изменений": 0, "details": []}
    names = {c.ticker: (c.name or c.ticker) for c in db.query(Company).all()}

    for ticker, tab in pairs:
        topic, _ = _TOPICS[tab]
        results = _search(names.get(ticker, ticker), ticker, topic)
        if not results:
            stats["details"].append({"ticker": ticker, "tab": tab, "note": "поиск пуст"})
            continue
        payload = {
            "company": names.get(ticker, ticker), "ticker": ticker, "tab": tab,
            "already_written": _prose_digest(db, ticker, tab),
            "found": [{"title": r.get("title"), "text": str(r.get("snippet") or "")[:400],
                       "url": r.get("url")} for r in results],
        }
        try:
            out = llm.complete(_SYS, json.dumps(payload, ensure_ascii=False),
                               json_mode=True, max_tokens=900)
        except llm.LLMError as e:
            logger.warning("revision_scout: %s/%s — LLM не отработал: %s", ticker, tab, e)
            continue
        stats["проверено"] += 1
        if not isinstance(out, dict) or not out.get("changed"):
            stats["без изменений"] += 1
            stats["details"].append({"ticker": ticker, "tab": tab,
                                     "note": str((out or {}).get("note") or "")[:80]})
            continue
        stats["с изменениями"] += 1
        facts = [f for f in (out.get("facts") or []) if isinstance(f, dict)][:3]
        made = 0
        for f in facts:
            if _make_signal(db, ticker, tab, f):
                made += 1
            # 🔴 Источник в пул — независимо от того, завёлся сигнал или нет: адрес
            # пригодился, значит сайт про эту компанию пишет.
            try:
                from app.services.source_pool import record_find
                if record_find(db, str(f.get("url") or ""), topic=tab, found_for=ticker,
                               note=str(f.get("source") or "")[:200]):
                    stats["источников записано"] += 1
            except Exception:  # noqa: BLE001
                logger.warning("revision_scout: источник не записан", exc_info=True)
        db.commit()
        stats["новых сигналов"] += made
        stats["details"].append({"ticker": ticker, "tab": tab, "facts": len(facts),
                                 "signals": made})
    logger.info("revision_scout: %s", {k: v for k, v in stats.items() if k != "details"})
    return stats
