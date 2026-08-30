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
# Голый год — тоже период: у ФосАгро 39 документов на странице и НИ ОДНОГО с
# кварталом в названии, там просто «ИНТЕГРИРОВАННЫЙ ОТЧЕТ 2025». Проверено на
# живой странице 2026-08-29 — без этого правила годовая отчётность не находилась.
_YEAR_RE = re.compile(r"(?<!\d)(20[12]\d)(?!\d)")

# Тип документа. Нужен, потому что на одной странице лежат вперемешку
# «Интегрированный отчёт» (ESG-брошюра на 300 страниц), презентация для
# инвесторов и собственно финансовая отчётность. Для разбора нужна последняя —
# качать брошюру вместо отчётности значит потратить деньги на LLM впустую.
_KIND_RULES = (
    ("ifrs_statements", ("мсфо", "ifrs", "консолидированная финансовая",
                         "консолидированной финансовой", "consolidated financial",
                         "financial statements", "финансовая отчетность",
                         "финансовая отчётность")),
    ("ras_statements", ("рсбу", "бухгалтерская отчет", "бухгалтерская отчёт", "ras ")),
    ("results_release", ("финансовые результаты", "операционные результаты",
                         "results for", "пресс-релиз", "press release")),
    ("presentation", ("презентац", "presentation", "investor day", "слайд")),
    ("annual_report", ("годовой отчет", "годовой отчёт", "интегрированный отчет",
                       "интегрированный отчёт", "annual report", "integrated report")),
)
# Порядок предпочтения при выборе, что качать первым.
_KIND_PRIORITY = {"ifrs_statements": 5, "ras_statements": 4, "results_release": 3,
                  "annual_report": 2, "presentation": 1, "other": 0}


def _doc_kind(label: str, url: str) -> str:
    hay = f"{label} {url}".lower()
    for kind, words in _KIND_RULES:
        if any(w in hay for w in words):
            return kind
    return "other"


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
                      # 🔴 «Файл» не равно «есть расширение»: у ФосАгро документы
                      # лежат на CDN без расширения вовсе (…/upload/iblock/245/txku…),
                      # и распознаются только по подписи ссылки.
                      "is_file": by_ext or by_word,
                      "has_ext": by_ext,
                      "kind": _doc_kind(label, url),
                      "period_hint": _period_from(label) or _period_from(url)})
    # дубли по адресу
    uniq, seen = [], set()
    for l in links:
        if l["url"] in seen:
            continue
        seen.add(l["url"])
        uniq.append(l)
    return uniq


def _doc_year(*parts: str) -> int | None:
    """Год документа — максимальный, встреченный в подписи или адресе. Максимум,
    а не первый: в адресе часто сидит год архива («/2019/upload/…»), а в подписи
    актуальный период."""
    years = []
    for p in parts:
        years += [int(m.group(1)) for m in _YEAR_RE.finditer(p or "")]
    return max(years) if years else None


def _period_from(s: str) -> str | None:
    m = _PERIOD_RE.search(s or "")
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()[:32]
    y = _YEAR_RE.search(s or "")
    return y.group(1) if y else None


def verify_page(url: str) -> dict:
    """Что на странице реально есть. Отдаёт факты, а не вердикт: сколько ссылок
    на документы, сколько из них файлы, примеры — по ним решает вызывающий."""
    code, html = _fetch(url)
    if not html:
        return {"url": url, "http": code, "ok": False, "reason": "страница не открылась"}
    links = _doc_links(html, url)
    files = [l for l in links if l["is_file"]]
    by_kind: dict[str, int] = {}
    for l in links:
        by_kind[l["kind"]] = by_kind.get(l["kind"], 0) + 1
    # 🔴 Годится страница, где есть ФИНАНСОВАЯ отчётность, а не просто много
    # файлов. Проверено на ФосАгро: на /investors/reports/ 39 документов и ноль
    # отчётности — одни интегрированные отчёты (ESG-брошюры). Считать такую
    # страницу «найденной» значит потом скармливать модели не тот документ.
    statements = by_kind.get("ifrs_statements", 0) + by_kind.get("ras_statements", 0)
    releases = by_kind.get("results_release", 0)
    return {
        "url": url, "http": code,
        "ok": bool(statements or releases or files),
        "has_statements": bool(statements),
        "text_len": len(html),
        "doc_links": len(links), "file_links": len(files),
        "statements": statements, "releases": releases,
        "by_kind": by_kind,
        "with_period": sum(1 for l in links if l["period_hint"]),
        "examples": [{"label": l["label"], "url": l["url"][:140], "kind": l["kind"],
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
        # Вес по убыванию ценности: сама отчётность → релизы результатов →
        # просто файлы. Без этого побеждала страница с максимумом PDF, а это
        # обычно архив годовых брошюр.
        v["score"] = (c["score"]
                      + v.get("statements", 0) * 10
                      + v.get("releases", 0) * 4
                      + min(v.get("file_links", 0), 10)
                      + min(v.get("with_period", 0), 10))
        checked.append(v)
        # Ранний выход только когда нашли именно отчётность — иначе продолжаем
        # смотреть остальных кандидатов.
        if v.get("statements", 0) >= 2:
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
           "st": ("ok" if verified.get("has_statements") else
                  ("docs_only" if verified.get("ok") else "no_docs")), "src": "search",
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


def _staleness(links: list[dict], since: date | None) -> str | None:
    """Почему сохранённая страница больше не годится. None — годится.

    🔴 Проверяем не только «открылась ли», но и СОДЕРЖИМОЕ: после редизайна
    старый адрес часто продолжает отвечать 200, отдавая архив прошлых лет или
    вообще другой раздел. Такая страница хуже, чем 404: она молча делает вид,
    что источник жив."""
    if not links:
        return "на странице нет ссылок на документы"
    years = []
    for l in links:
        for token in (l.get("period_hint") or "", l.get("label") or ""):
            m = _YEAR_RE.search(token)
            if m:
                years.append(int(m.group(1)))
    if not years:
        return None  # периодов не видно — не повод считать страницу мёртвой
    ref = (since or date.today()).year
    # Отчёт за прошлый год — норма (годовая отчётность выходит весной); всё, что
    # старше, означает, что свежие документы уехали на другой адрес.
    if max(years) < ref - 1:
        return f"самый свежий документ за {max(years)} год, ожидается {ref - 1}–{ref}"
    return None


def _rebind(db: Session, ticker: str, old_url: str | None, reason: str) -> dict | None:
    """Найти страницу заново и записать в реестр вместо протухшей."""
    logger.info("ir_registry: перепривязка %s (%s), был %s", ticker, reason, old_url)
    res = build_for_ticker(db, ticker, save=True)
    if not res.get("found"):
        # Реестр не трогаем: старый адрес хотя бы известен, а причину пишем —
        # по ней видно, что источник требует ручного взгляда.
        db.execute(text("UPDATE ir_pages SET stale_reason = :r, updated_at = now() "
                        "WHERE ticker = :t"), {"r": reason[:200], "t": ticker})
        db.commit()
        return None
    db.execute(text(
        "UPDATE ir_pages SET previous_url = :old, rebound_count = rebound_count + 1, "
        "stale_reason = :r, updated_at = now() WHERE ticker = :t"),
        {"old": (old_url or "")[:600], "r": reason[:200], "t": ticker})
    db.commit()
    return res.get("best")


def latest_documents(db: Session, ticker: str, since: date | None = None,
                     limit: int = 8, allow_rebind: bool = True) -> dict:
    """Свежие документы отчётности эмитента по сохранённой IR-странице.

    Даты у файлов на сайте почти никогда не проставлены машиночитаемо, поэтому
    свежесть определяем по ПЕРИОДУ в названии («1П2026», «за 6 месяцев 2026»),
    а не по дате публикации — так же, как это делает человек глазами."""
    rebound_from = None
    page = get_page(db, ticker)
    if not page:
        # Страницы нет вовсе — ищем сразу: «нет в реестре» не должно быть концом
        # процесса, процесс обязан заканчиваться добычей.
        if not allow_rebind:
            return {"found": False, "reason": f"IR-страница для {ticker} не в реестре"}
        best = _rebind(db, ticker, None, "страницы не было в реестре")
        if not best:
            return {"found": False, "reason": f"страницу с отчётностью {ticker} найти не удалось"}
        page, rebound_from = get_page(db, ticker), "не было в реестре"

    code, html = _fetch(page["url"])
    links = _doc_links(html, page["url"]) if html else []
    reason = (f"страница не открылась (код {code})" if not html
              else _staleness(links, since))
    if reason and allow_rebind:
        best = _rebind(db, ticker, page["url"], reason)
        if best:
            page, rebound_from = get_page(db, ticker), reason
            code, html = _fetch(page["url"])
            links = _doc_links(html, page["url"]) if html else []
    if not html:
        return {"found": False, "url": page["url"],
                "reason": f"страница {page['url']} не открылась (код {code})",
                "rebound_from": rebound_from}
    files = [l for l in links if l["is_file"]] or links
    if since:
        year = since.year
        # Оставляем то, что упоминает текущий или прошлый год: отчётность за
        # период всегда несёт год в названии.
        years = {str(year), str(year - 1)}
        with_year = [l for l in files if any(y in (l["label"] + l["url"]) for y in years)]
        files = with_year or files
    # 🔴 Порядок важен: на одной странице лежат и финансовая отчётность, и
    # интегрированный отчёт на 300 страниц, и презентация. Разбирать надо
    # отчётность — иначе модель читает ESG-брошюру и не находит ни P&L, ни ОДДС
    # (у ФосАгро из 39 документов на странице отчётность — единицы).
    files.sort(key=lambda l: (-_KIND_PRIORITY.get(l.get("kind", "other"), 0),
                              0 if l.get("period_hint") else 1))
    if files:
        db.execute(text("UPDATE ir_pages SET last_ok_at = now(), stale_reason = NULL "
                        "WHERE ticker = :t"), {"t": ticker})
        db.commit()
    return {"found": bool(files), "url": page["url"], "count": len(files),
            "documents": files[:limit], "rebound_from": rebound_from,
            "by_kind": {k: sum(1 for l in files if l.get("kind") == k)
                        for k in {l.get("kind") for l in files}}}


def find_documents_by_search(name: str, ticker: str, year: int | None = None,
                             limit: int = 8) -> list[dict]:
    """Искать САМ ДОКУМЕНТ, а не страницу. Запасной путь, закрывающий два случая,
    которые страница не закрывает (оба найдены на бою 2026-08-29):

      • сайт рисуется скриптом — у Норникеля страницы отвечают 200, а ссылок в
        HTML ноль, потому что список документов подставляет JavaScript;
      • нужного документа нет на найденной странице — у Северстали на
        «financial-results» лежат только пресс-релизы и презентации, сама
        отчётность МСФО на другой странице.

    Поисковик индексирует PDF напрямую, поэтому запрос про отчётность часто
    ведёт прямо в файл, минуя навигацию сайта."""
    from app.services.agent_web import web_search
    y = year or date.today().year
    queries = [
        f"{name} консолидированная финансовая отчётность МСФО {y} pdf",
        f"{name} промежуточная сокращённая финансовая отчётность {y}",
        f'"{name}" отчётность МСФО {y} filetype:pdf',
    ]
    out, seen = [], set()
    for q in queries:
        for item in (web_search(q, max_results=6) or {}).get("results") or []:
            url = (item.get("url") or "").split("#")[0]
            if not url.startswith("http") or url in seen:
                continue
            if not _looks_like_issuer(url):
                continue
            label = (item.get("title") or "")[:160]
            kind = _doc_kind(label, url)
            # Берём только то, что похоже на отчётность или релиз результатов:
            # поиск охотно подсовывает новости и аналитику сторонних сайтов.
            if kind not in ("ifrs_statements", "ras_statements", "results_release"):
                continue
            seen.add(url)
            hint = _period_from(label) or _period_from(url)
            # 🔴 Отбрасываем заведомо старое. Поиск охотно отдаёт документ
            # трёхлетней давности (на бою так пришли «1П2025» и «9М2024», когда
            # шёл 2026-й) — а агент должен принести ПОСЛЕДНИЙ отчёт, иначе
            # карточка получит прошлогодние цифры как свежие.
            doc_year = _doc_year(hint, label, url)
            if doc_year and doc_year < y - 1:
                continue
            out.append({"url": url, "label": label, "kind": kind,
                        "is_file": url.lower().endswith(_DOC_EXT),
                        "period_hint": hint, "year": doc_year, "via": "search"})
        if len(out) >= limit:
            break
    # Сначала свежесть, потом тип: годовой отчёт за этот год полезнее, чем
    # отчётность МСФО двухлетней давности.
    out.sort(key=lambda l: (-(l.get("year") or 0), -_KIND_PRIORITY.get(l["kind"], 0)))
    return out[:limit]


def _known_annual_revenue(ticker: str) -> float | None:
    """Последняя годовая выручка компании из её карточки (млн ₽) — эталон
    масштаба для проверки извлечённых чисел."""
    from pathlib import Path
    import json as _json
    path = (Path(__file__).parent.parent.parent / "companies" / ticker.upper()
            / "financials.json")
    if not path.is_file():
        return None
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
        series = ((data.get("income_statement") or {}).get("revenue") or [])
        vals = [v for v in series if isinstance(v, (int, float)) and v]
        return float(vals[-1]) if vals else None
    except Exception:  # noqa: BLE001 — эталон необязателен
        return None


def harvest(db: Session, ticker: str, since: date | None = None,
            max_docs: int = 3, extract: bool = True) -> dict:
    """Сквозной проход: найти документ → прочитать → извлечь показатели.

    Владелец сформулировал требование к результату так: «процесс закончился
    добычей отчётности и извлечением». Поэтому здесь один вход и один ответ, а
    все промежуточные отказы — перепривязка реестра, нечитаемый файл, документ
    не той природы — разруливаются внутри: пробуем следующий документ, а не
    возвращаем ошибку на первом же.
    """
    from app.services import report_deep_extract as deep

    name_row = db.execute(text("SELECT name FROM companies WHERE ticker = :t"),
                          {"t": ticker}).first()
    company = name_row.name if name_row else ticker

    found = latest_documents(db, ticker, since=since, limit=max_docs + 3)
    docs = list(found.get("documents") or [])
    page_url = found.get("url")

    # Отчётности на странице может не быть вовсе (там релизы и презентации) или
    # страница может оказаться пустой в HTML (сайт на скриптах). Тогда ищем сам
    # документ — иначе процесс закончился бы ничем, а он обязан закончиться
    # добычей.
    has_statements = any(d.get("kind") in ("ifrs_statements", "ras_statements")
                         for d in docs)
    via_search: list[dict] = []
    if not docs or not has_statements:
        via_search = find_documents_by_search(
            company, ticker, year=(since or date.today()).year)
        # Найденное поиском ставим первым: это отчётность, а на странице —
        # в лучшем случае пресс-релиз.
        docs = via_search + docs
    if not docs:
        return {"ticker": ticker, "ok": False, "stage": "discovery",
                "reason": found.get("reason") or "документов не нашлось ни на странице, ни поиском",
                "ir_page": page_url, "rebound_from": found.get("rebound_from")}

    tried = []
    for doc in docs[:max_docs]:
        got = fetch_document(doc["url"], max_chars=90_000)
        if not got.get("ok") or len(got.get("text") or "") < 1500:
            tried.append({"url": doc["url"][:120], "kind": doc.get("kind"),
                          "result": "не прочитался"})
            continue
        if not extract:
            return {"ticker": ticker, "ok": True, "stage": "document", "document": doc,
                    "chars": got["chars"], "ir_page": page_url,
                    "via_search": bool(doc.get("via")),
                    "rebound_from": found.get("rebound_from"), "tried": tried}
        data = deep.extract_from_document(got["text"], company_name=company)
        if data is not None:
            # Масштаб проверяем по годовой выручке из карточки этой же компании:
            # «−30,3» при годовой выручке 712 900 млн — это миллиарды, а не провал
            # бизнеса. Ошибка масштаба не видна на глаз и уезжает молча.
            data = deep.normalize_scale(data, _known_annual_revenue(ticker))
        if data is None:
            tried.append({"url": doc["url"][:120], "kind": doc.get("kind"),
                          "result": "модель не признала отчётностью"})
            continue
        # Свежесть проверяем по ИЗВЛЕЧЁННОМУ периоду, а не по подписи ссылки:
        # подпись врёт чаще (в имени файла год выгрузки, а внутри отчёт за
        # прошлый период). Старый документ — не отказ, а повод взять следующий.
        ref_year = (since or date.today()).year
        got_year = _doc_year(str(data.get("period_label") or ""))
        if got_year and got_year < ref_year - 1:
            tried.append({"url": doc["url"][:120], "kind": doc.get("kind"),
                          "result": f"период {data.get('period_label')} — старый"})
            continue
        return {"ticker": ticker, "ok": True, "stage": "extracted",
                "ir_page": page_url, "via_search": bool(doc.get("via")),
                "rebound_from": found.get("rebound_from"),
                "document": {"url": doc["url"], "label": doc.get("label"),
                             "kind": doc.get("kind"), "period_hint": doc.get("period_hint")},
                "chars": got["chars"], "extracted": data, "tried": tried}
    return {"ticker": ticker, "ok": False, "stage": "extraction",
            "reason": "ни один из документов не разобрался",
            "ir_page": page_url, "rebound_from": found.get("rebound_from"),
            "searched": len(via_search), "tried": tried}


def fetch_document(url: str, max_chars: int = 120_000) -> dict:
    """Текст документа (pdf/html) — вход для извлечения показателей."""
    from app.services.article_texts import fetch_article_text
    txt = fetch_article_text(url)
    if not txt:
        return {"ok": False, "url": url, "reason": "документ не прочитался"}
    return {"ok": True, "url": url, "chars": len(txt), "text": txt[:max_chars]}
