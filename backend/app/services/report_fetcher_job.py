"""Прод-добытчик отчётных релизов: код + DeepSeek, БЕЗ внешних агентов.

Владелец (2026-07-31): добытчик нужен, но «только на дипсик» — облачная
Claude-рутина отключена в тот же день (см. память проекта
feedback-no-claude-agents-in-prod). Этот модуль — та же идея в разрешённой
архитектуре: обычный крон бэкенда, детерминированные источники, LLM-шаги через
llm.complete() (DeepSeek), приём — существующий ingest_agent_source (дальше
работает штатный конвейер: экстракция цифр → богатый дайджест).

ПОЧЕМУ БЕЗ ПОИСКОВИКА. DDG и Bing с обычного HTTP закрыты анти-ботами (проверено
2026-07-31: DDG отдаёт anomaly-заглушку 202, Bing — 400). Вместо поиска — два
детерминированных источника кандидатов:
  1) smart-lab.ru/forum/news/{TICKER}/ — агрегатор новостей ПО ТИКЕРУ без
     анти-бота; заголовки говорящие, часто с цифрами прямо в заголовке
     («ВТБ РСБУ 6 мес: процентные доходы ..., чистая прибыль ...»);
  2) собственная Лента (market_updates по тикеру) — source_url статей СМИ.

Роль DeepSeek здесь — только ВЫБОР ссылок (по заголовкам решить, где вероятнее
полные цифры отчёта за нужный период). Извлечение цифр из добытого текста делает
штатный экстрактор конвейера со своей валидацией — этот модуль цифры не трогает.

Границы (те же, что у dev-субагента report-fetcher): один проход, лимит тикеров
за прогон, не долбить источники, честно пропускать недобытое — пропуск лучше
выдумки. Идемпотентность через wishlist: добытое из списка исчезает.
"""
from __future__ import annotations

import html as _html
import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.services import llm

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_SMARTLAB = "https://smart-lab.ru/forum/news/{ticker}/"
_MAX_TICKERS_PER_RUN = 4
_MAX_FETCH_PER_TICKER = 3

_PICK_SYS = (
    "Ты выбираешь ссылки для добычи ПОЛНОГО текста отчётного релиза компании. "
    "Дан тикер, период отчёта и список заголовков со ссылками. Выбери до 3 ссылок, "
    "в которых вероятнее всего есть КОНКРЕТНЫЕ ЦИФРЫ финансовых результатов именно "
    "ЭТОГО периода (выручка/EBITDA/чистая прибыль/операционные показатели). "
    "Пропускай: котировки и движения акций, дивидендные новости, прогнозы аналитиков, "
    "смежные корпоративные новости без цифр отчёта, другие периоды. "
    'Верни строго JSON {"urls": ["...", ...]} (может быть пустым). Без текста вне JSON.'
)


def build_wishlist(db: Session, days_back: int = 2) -> list[dict]:
    """Что добывать: свежие отчётные события без источника или с разбором без выручки.
    Единая логика для крона и debug-эндпоинта fetch-wishlist."""
    from app.models.earnings import EarningsReport, EarningsFigures
    cutoff = date.today() - timedelta(days=days_back)
    rows = (db.query(EarningsReport, EarningsFigures)
            .outerjoin(EarningsFigures, EarningsFigures.report_id == EarningsReport.id)
            .filter(EarningsReport.published_at.isnot(None),
                    EarningsReport.published_at >= cutoff).all())
    out = []
    for r, fig in rows:
        reason = None
        if r.status == "needs_source":
            reason = "нет источника"
        elif r.status == "processed" and (fig is None or fig.revenue_ttm is None):
            reason = "разбор без выручки (обрывок источника)"
        if reason:
            out.append({"ticker": r.ticker, "period": r.period, "standard": r.standard,
                        "published_at": r.published_at.isoformat(), "reason": reason})
    # «нет источника» — приоритетнее, чем добор выручки к готовому разбору
    out.sort(key=lambda x: 0 if x["reason"] == "нет источника" else 1)
    return out


def _smartlab_candidates(ticker: str) -> list[dict]:
    """Заголовки+ссылки из smart-lab.ru/forum/news/{TICKER}/ (до 25 верхних)."""
    try:
        r = httpx.Client(timeout=15, headers={"User-Agent": _UA},
                         follow_redirects=True).get(_SMARTLAB.format(ticker=ticker))
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        logger.info("report-fetch: smart-lab %s недоступен (%s)", ticker, type(e).__name__)
        return []
    out = []
    for m in re.finditer(r'<a href="(/blog/[^"]+\.php)"[^>]*>([^<]{25,200})</a>', r.text):
        title = _html.unescape(m.group(2)).strip()
        out.append({"title": title, "url": "https://smart-lab.ru" + m.group(1)})
        if len(out) >= 25:
            break
    return out


def _lenta_candidates(db: Session, ticker: str, days: int = 5) -> list[dict]:
    """Статьи СМИ о тикере из собственной Ленты (заголовок + source_url)."""
    from app.models.market import MarketUpdate
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (db.query(MarketUpdate)
            .filter(MarketUpdate.published_at >= cutoff,
                    MarketUpdate.status == "published",
                    MarketUpdate.affected_tickers.contains([ticker]),
                    MarketUpdate.source_url.isnot(None))
            .order_by(MarketUpdate.published_at.desc()).limit(20).all())
    return [{"title": r.title, "url": r.source_url} for r in rows if r.source_url]


def _pick_urls(ticker: str, period: str | None, candidates: list[dict]) -> list[str]:
    """DeepSeek выбирает до 3 ссылок по заголовкам. Сбой LLM → простая эвристика."""
    if not candidates:
        return []
    try:
        out = llm.complete(
            _PICK_SYS,
            f"Тикер: {ticker}. Период отчёта: {period or 'свежий'}.\n" +
            "\n".join(f"{c['url']} — {c['title']}" for c in candidates[:40]),
            json_mode=True, max_tokens=400)
        urls = [u for u in (out.get("urls") or []) if isinstance(u, str) and u.startswith("http")]
        known = {c["url"] for c in candidates}
        urls = [u for u in urls if u in known]  # только из предложенного списка
        if urls:
            return urls[:_MAX_FETCH_PER_TICKER]
    except (llm.LLMError, AttributeError, TypeError) as e:
        logger.warning("report-fetch: LLM-выбор ссылок не удался (%s) — эвристика", e)
    kw = re.compile(r"прибыл|убыт|выручк|ebitda|oibda|gmv|мсфо|рсбу|результат", re.I)
    return [c["url"] for c in candidates if kw.search(c["title"])][:_MAX_FETCH_PER_TICKER]


_NUM_NEAR = r"[^.]{0,80}?\d"


def _looks_substantive(text: str) -> bool:
    """Кодовая проверка добычи: минимум два финансовых показателя с цифрами рядом."""
    hits = 0
    for kw in (r"выручк", r"ebitda|oibda", r"чист\w+ (?:прибыл|убыт)", r"gmv",
               r"процентн\w+ доход", r"комиссионн\w+ доход"):
        if re.search(kw + _NUM_NEAR, text, re.I | re.S):
            hits += 1
    return hits >= 2


def _disclosure_texts(ticker: str, inn: str | None, pub: date) -> list[str]:
    """ПЕРВОИСТОЧНИК — аккредитованные ЦБ центры раскрытия (владелец 2026-07-31:
    «агент же может ходить в центры раскрытия — мы их подключили»). СКРИН/ПРАЙМ/
    АЗИПИ уже интегрированы в report_watch для календарного пути — здесь те же
    фетчеры дергаются по ИНН эмитента вокруг даты публикации. Их тексты идут
    ПЕРВЫМИ в блобе: раскрытие эмитента приоритетнее пересказов."""
    if not inn:
        return []
    from app.services.report_watch import _from_skrin, _from_prime, _from_azipi
    out = []
    for name, fn in (("СКРИН", _from_skrin), ("ПРАЙМ", _from_prime), ("АЗИПИ", _from_azipi)):
        try:
            txt = fn(inn, pub)
        except Exception as e:  # noqa: BLE001 — один упавший центр не валит добычу
            logger.info("report-fetch: %s по %s недоступен (%s)", name, ticker, type(e).__name__)
            continue
        if txt and len(txt) >= 200:
            out.append(f"[РАСКРЫТИЕ · {name}]\n{txt[:6000]}")
        if len(out) >= 2:   # двух центров достаточно, не дублируем одно сообщение трижды
            break
    return out


def fetch_missing_reports(db: Session, max_tickers: int = _MAX_TICKERS_PER_RUN) -> dict:
    """Один проход добытчика. Идемпотентен: закрытые позиции уходят из wishlist."""
    from app.services.report_watch import _fetch_article_text, ingest_agent_source
    from app.services.calendar_events import _load_inn_ticker_map
    wishlist = build_wishlist(db)
    if not wishlist:
        return {"status": "empty"}
    # ИНН → тикер (rates.csv); карта нужна центрам раскрытия
    inn_by_ticker: dict[str, str] = {}
    try:
        for inn, tickers in _load_inn_ticker_map().items():
            for tk in tickers:
                inn_by_ticker.setdefault(tk, inn)
    except Exception:  # noqa: BLE001
        pass
    done, skipped = [], []
    seen: set[str] = set()
    for item in wishlist:
        if len(done) + len(skipped) >= max_tickers:
            break
        t = item["ticker"]
        if t in seen:
            continue
        seen.add(t)
        try:
            pub = date.fromisoformat(item["published_at"])
        except (TypeError, ValueError):
            pub = date.today()
        texts = _disclosure_texts(t, inn_by_ticker.get(t), pub)
        used_urls: list[str] = []
        candidates = _smartlab_candidates(t) + _lenta_candidates(db, t)
        urls = _pick_urls(t, item.get("period"), candidates)
        for u in urls:
            full = _fetch_article_text(u, limit=8000)
            if full:
                texts.append(full)
                used_urls.append(u)
        blob = "\n\n---\n\n".join(texts)[:12000]
        if not blob or not _looks_substantive(blob):
            skipped.append({"ticker": t, "reason": "источники без цифр отчёта",
                            "candidates": len(candidates), "articles": len(used_urls),
                            "disclosures": len(texts) - len(used_urls)})
            continue
        res = ingest_agent_source(db, t, blob, used_urls[0] if used_urls else None,
                                  item.get("period"), item.get("standard"))
        (done if not res.get("error") else skipped).append(
            {"ticker": t, **({"source": used_urls[0]} if used_urls else {}), **res})
    result = {"status": "done", "wishlist": len(wishlist), "ingested": done, "skipped": skipped}
    logger.info("report-fetch: %s", result)
    return result
