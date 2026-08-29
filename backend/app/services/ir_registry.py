"""Реестр IR-страниц эмитентов — где у компании лежит сама отчётность.

Зачем. Разведка 2026-08-29 показала: центры раскрытия рынок не покрывают
(см. work-journal, «Добыча файлов отчётности упирается в стену») — у Татнефти в
ПРАЙМ последние раскрытия отчётности за 2023 год, у Норникеля/МТС/ФосАгро/Сбера
категорий нет вовсе, Интерфакс закрыт JS-проверкой, АК&М рисуется скриптом.
При этом САЙТЫ САМИХ КОМПАНИЙ с боевого сервера доступны — неизвестен ПУТЬ к
разделу с отчётностью, и угадать его нельзя: `tatneft.ru/aktsioneram-i-investoram/`
даёт 404, хотя корень отвечает.

Решение владельца (вариант 2): собрать адреса один раз и хранить. Реестр строится
поиском, проверяется загрузкой страницы и живёт в БД — обновить запись можно без
выкатки, а собирать его надо С БОЕВОГО СЕРВЕРА: сеть инстанса и сеть разработчика
видят интернет по-разному (см. память проекта про probe-url).

Что здесь есть:
  discover_candidates() — поиск кандидатов по названию компании;
  verify_page()         — что реально лежит на странице: ссылки на pdf/xlsx,
                          похожие на отчётность, и их даты/названия;
  build_for_ticker()    — найти, проверить, записать лучший вариант;
  latest_documents()    — по сохранённой странице отдать свежие документы.

Чего здесь НЕТ: извлечения показателей. Выход слоя — ссылки и текст документа,
дальше работает извлечение (report_watch) и слияние (interim_overlay). Разделение
намеренное: добыча ломается от сети и анти-ботов, извлечение — от формулировок.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Агрегаторы и витрины — на них отчётность есть, но это ПЕРЕСКАЗ. Нам нужен
# первоисточник: сайт самого эмитента.
_NOT_ISSUER = (
    "smart-lab.ru", "smartlab.ru", "e-disclosure.ru", "disclosure.ru", "1prime.ru",
    "skrin.ru", "azipi.ru", "interfax.ru", "rbc.ru", "kommersant.ru", "vedomosti.ru",
    "finam.ru", "bcs", "tinkoff.ru", "tbank.ru", "sberbank.com/ru/investor" "moex.com",
    "wikipedia.org", "conomy.ru", "investing.com", "tradingview.com", "dohod.ru",
    "youtube.com", "t.me", "vk.com", "cbr.ru", "nalog.ru", "rusprofile.ru",
    "list-org.com", "audit-it.ru", "consultant.ru", "garant.ru",
)

# Путь, по которому у российских эмитентов обычно живёт раскрытие. Порядок важен:
# чем выше, тем точнее попадание в страницу СО СПИСКОМ ДОКУМЕНТОВ, а не в общий
# раздел «Акционерам».
_PATH_HINTS = (
    "raskrytie", "disclosure", "otchet", "reports", "reporting", "financial",
    "finansovaya", "msfo", "ifrs", "results", "investor", "investors",
    "aktsioneram", "shareholders", "ir",
)

# Признаки того, что ссылка ведёт на документ отчётности, а не на пресс-релиз.
_DOC_EXT = (".pdf", ".xlsx", ".xls", ".zip", ".docx")
_DOC_WORDS = (
    "отчет", "отчёт", "отчетность", "отчётность", "мсфо", "рсбу", "ifrs", "ras",
    "financial", "statements", "консолидированн", "промежуточн", "квартал",
    "полугод", "annual", "interim", "results",
)
_PERIOD_RE = re.compile(
    r"(?:(1|2|3|4)\s*(?:кв|квартал)|(\d)\s*(?:мес|месяц)|(1|2)\s*(?:п|полугод)|"
    r"(?:q([1-4]))|(?:h([12])))[^\d]{0,12}(20\d{2})|(20\d{2})[^\d]{0,12}"
    r"(?:(1|2|3|4)\s*(?:кв|квартал)|(?:q([1-4])))", re.IGNORECASE)


def _client():
    from app.services.agent_web import _client as web_client
    return web_client()


def _fetch(url: str) -> tuple[int, str]:
    """Страница глазами боевого сервера. При отказе — вторая попытка через релей
    (Cloudflare Worker), которым в проекте обходится egress-блокировка."""
    from app.services.agent_web import via_proxy
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
               "Accept-Language": "ru,en;q=0.8"}
    for target in (url, via_proxy(url)):
        try:
            with _client() as c:
                r = c.get(target, headers=headers, follow_redirects=True)
            if r.status_code < 400 and r.text:
                return r.status_code, r.text
            last = r.status_code
        except Exception as e:  # noqa: BLE001
            logger.info("ir_registry: %s не открылся (%s)", target[:80], type(e).__name__)
            last = 0
        if target != url:
            return last, ""
    return last, ""


def _looks_like_issuer(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return bool(host) and not any(bad in host for bad in _NOT_ISSUER)


def _path_score(url: str) -> int:
    path = (urlparse(url).path or "").lower()
    return sum(2 if h in path else 0 for h in _PATH_HINTS)


def discover_candidates(name: str, ticker: str, limit: int = 8) -> list[dict]:
    """Кандидаты в IR-страницу. Несколько формулировок запроса: одна и та же
    компания у разных эмитентов названа по-разному («Группа», «ПАО», бренд)."""
    from app.services.agent_web import web_search
    queries = [
        f"{name} раскрытие информации финансовая отчётность МСФО",
        f"{name} инвесторам отчётность консолидированная МСФО скачать",
        f"{name} акционерам и инвесторам финансовые результаты отчёт",
    ]
    seen, out = set(), []
    for q in queries:
        res = web_search(q, max_results=6) or {}
        for item in res.get("results") or []:
            url = (item.get("url") or "").split("#")[0]
            if not url.startswith("http") or url in seen or not _looks_like_issuer(url):
                continue
            seen.add(url)
            out.append({"url": url, "title": (item.get("title") or "")[:160],
                        "score": _path_score(url)})
        if len(out) >= limit:
            break
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def _doc_links(html: str, base_url: str) -> list[dict]:
    """Ссылки на документы отчётности со страницы. Смотрим и расширение, и текст
    ссылки: часть эмитентов отдаёт файл через скрипт (/download?id=…), и по
    адресу это не документ, а по подписи — «Консолидированная отчётность МСФО»."""
    links = []
    for m in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        href, label = m.group(1).strip(), re.sub(r"<[^>]+>", " ", m.group(2))
        label = re.sub(r"\s+", " ", label).strip()[:160]
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base_url, href)
        low_url, low_label = url.lower(), label.lower()
        by_ext = low_url.endswith(_DOC_EXT)
        by_word = any(w in low_label for w in _DOC_WORDS) or any(w in low_url for w in _DOC_WORDS)
        if not (by_ext or by_word):
            continue
        if not by_ext and not by_word:
            continue
        links.append({"url": url, "label": label,
                      "is_file": by_ext,
                      "period_hint": _period_from(label) or _period_from(url)})
    # дубли по адресу
    uniq, seen = [], set()
    for l in links:
        if l["url"] in seen:
            continue
        seen.add(l["url"])
        uniq.append(l)
    return uniq


def _period_from(s: str) -> str | None:
    m = _PERIOD_RE.search(s or "")
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(0)).strip()[:32]


def verify_page(url: str) -> dict:
    """Что на странице реально есть. Отдаёт факты, а не вердикт: сколько ссылок
    на документы, сколько из них файлы, примеры — по ним решает вызывающий."""
    code, html = _fetch(url)
    if not html:
        return {"url": url, "http": code, "ok": False, "reason": "страница не открылась"}
    links = _doc_links(html, url)
    files = [l for l in links if l["is_file"]]
    return {
        "url": url, "http": code, "ok": bool(links),
        "text_len": len(html),
        "doc_links": len(links), "file_links": len(files),
        "with_period": sum(1 for l in links if l["period_hint"]),
        "examples": [{"label": l["label"], "url": l["url"][:140],
                      "period": l["period_hint"]} for l in (files or links)[:6]],
    }


def build_for_ticker(db: Session, ticker: str, name: str | None = None,
                     save: bool = True) -> dict:
    """Найти и проверить IR-страницу компании; лучший вариант записать в реестр."""
    if not name:
        row = db.execute(text("SELECT name FROM companies WHERE ticker = :t"),
                         {"t": ticker}).first()
        name = row.name if row else ticker
    cands = discover_candidates(name, ticker)
    if not cands:
        return {"ticker": ticker, "found": False, "reason": "поиск не дал кандидатов"}

    checked = []
    for c in cands[:5]:
        v = verify_page(c["url"])
        v["title"] = c["title"]
        v["score"] = c["score"] + v.get("file_links", 0) * 3 + v.get("with_period", 0) * 2
        checked.append(v)
        # Ранний выход: страница со списком файлов и распознанными периодами —
        # это то, что нужно, дальше искать незачем.
        if v.get("file_links", 0) >= 3 and v.get("with_period", 0) >= 2:
            break
    checked.sort(key=lambda x: -x.get("score", 0))
    best = checked[0]
    if not best.get("ok"):
        return {"ticker": ticker, "found": False, "reason": "на найденных страницах нет документов",
                "checked": checked}
    if save:
        save_page(db, ticker, best)
    return {"ticker": ticker, "found": True, "best": best, "checked": checked}


def save_page(db: Session, ticker: str, verified: dict) -> None:
    db.execute(text("""
        INSERT INTO ir_pages (ticker, url, title, doc_links, file_links, status,
                              source, examples, checked_at, updated_at)
        VALUES (:t, :u, :title, :dl, :fl, :st, :src, CAST(:ex AS jsonb), now(), now())
        ON CONFLICT (ticker) DO UPDATE SET
            url = EXCLUDED.url, title = EXCLUDED.title, doc_links = EXCLUDED.doc_links,
            file_links = EXCLUDED.file_links, status = EXCLUDED.status,
            source = EXCLUDED.source, examples = EXCLUDED.examples,
            checked_at = now(), updated_at = now()
    """), {"t": ticker, "u": verified["url"], "title": (verified.get("title") or "")[:250],
           "dl": verified.get("doc_links", 0), "fl": verified.get("file_links", 0),
           "st": "ok" if verified.get("ok") else "no_docs", "src": "search",
           "ex": __import__("json").dumps(verified.get("examples") or [], ensure_ascii=False)})
    db.commit()


def get_page(db: Session, ticker: str) -> dict | None:
    row = db.execute(text(
        "SELECT ticker, url, title, doc_links, file_links, status, checked_at "
        "FROM ir_pages WHERE ticker = :t"), {"t": ticker}).first()
    if not row:
        return None
    return {"ticker": row.ticker, "url": row.url, "title": row.title,
            "doc_links": row.doc_links, "file_links": row.file_links,
            "status": row.status, "checked_at": row.checked_at}


def latest_documents(db: Session, ticker: str, since: date | None = None,
                     limit: int = 8) -> dict:
    """Свежие документы отчётности эмитента по сохранённой IR-странице.

    Даты у файлов на сайте почти никогда не проставлены машиночитаемо, поэтому
    свежесть определяем по ПЕРИОДУ в названии («1П2026», «за 6 месяцев 2026»),
    а не по дате публикации — так же, как это делает человек глазами."""
    page = get_page(db, ticker)
    if not page:
        return {"found": False, "reason": f"IR-страница для {ticker} не в реестре"}
    code, html = _fetch(page["url"])
    if not html:
        return {"found": False, "reason": f"страница {page['url']} не открылась (код {code})",
                "url": page["url"]}
    links = _doc_links(html, page["url"])
    files = [l for l in links if l["is_file"]] or links
    if since:
        year = since.year
        # Оставляем то, что упоминает текущий или прошлый год: отчётность за
        # период всегда несёт год в названии.
        years = {str(year), str(year - 1)}
        with_year = [l for l in files if any(y in (l["label"] + l["url"]) for y in years)]
        files = with_year or files
    return {"found": bool(files), "url": page["url"], "count": len(files),
            "documents": files[:limit]}


def fetch_document(url: str, max_chars: int = 120_000) -> dict:
    """Текст документа (pdf/html) — вход для извлечения показателей."""
    from app.services.article_texts import fetch_article_text
    txt = fetch_article_text(url)
    if not txt:
        return {"ok": False, "url": url, "reason": "документ не прочитался"}
    return {"ok": True, "url": url, "chars": len(txt), "text": txt[:max_chars]}
