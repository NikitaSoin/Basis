"""Добыча САМОГО ФАЙЛА отчётности — центры раскрытия и IR-страницы эмитента.

Зачем этот слой существует. Замер потока за август 2026 (52 записи об отчётах у 15
компаний) показал, откуда платформа реально берёт отчётность:

    лента новостей   20      добытчик smart-lab   9
    старый ручной     9      ГИР БО (ФНС)         9
    заголовок события 5      СКРИН/ПРАЙМ/АЗИПИ    0   ← ноль

Три аккредитованных ЦБ центра раскрытия подключены кодом (report_watch._from_skrin/
_from_azipi/_from_prime), но за период не дали НИ ОДНОЙ записи. Причина в том, КАК их
вызывают: только вокруг даты КАЛЕНДАРНОГО события. Большинство отчётов детектится из
Ленты новостей, у них календарного события нет — и до центров раскрытия дело не
доходит вовсе. Платформа читает пересказ отчёта в новости вместо самого отчёта.

Отсюда потолок, который владелец видит на карточке: из пресс-релиза извлекаются
заголовочные числа (выручка/EBITDA/прибыль/долг, с 2026-08-28 плюс активы/капитал/
операционный поток/капзатраты), а постатейного P&L, баланса и ОДДС нет — их в
новости просто не бывает. Постатейные данные приходят только ручным путём
(субагент-добытчик → financials.json).

Этот модуль закрывает разрыв с другого конца: идёт от ЭМИТЕНТА (по ИНН), а не от
календарного события, и ищет не текст новости, а ДОКУМЕНТ — pdf/xls с отчётностью.

Что он делает:
  1. находит страницу эмитента в центре раскрытия (АЗИПИ отдаёт постоянный адрес
     вида /organization/personal-pages/<id>/ по ИНН — это и есть машиночитаемая
     точка входа, «реестр» строить вручную не нужно);
  2. читает ленту сообщений эмитента за окно дат, отбирая раскрытия отчётности;
  3. из текста сообщения достаёт ссылки. Шаблон Положения №714-П обязывает эмитента
     указать «адрес страницы в сети Интернет, на которой опубликован полный текст» —
     это, как правило, ссылка на IR-раздел САМОЙ компании. Так IR-сайт берётся из
     первоисточника, а не угадывается по названию;
  4. отбирает среди ссылок кандидатов на файл отчётности и вытягивает их текст
     (pdf читается pypdf — см. article_texts.fetch_article_text).

Чего он НЕ делает: не извлекает показатели и ничего не пишет в карточку. Его выход —
текст документа; дальше по цепочке идёт извлечение (report_watch) и слияние
(interim_overlay). Разделение намеренное: добыча ломается от сети и анти-ботов, а
извлечение — от формулировок, это разные отказы и чинить их надо порознь.

🔴 e-disclosure.ru (Интерфакс, самый полный) сюда НЕ входит: с боевого сервера отдаёт
403 (JS-challenge ServicePipe), это не лечится User-Agent'ом. Проверено 2026-08-28:
СКРИН 200, IR-сайты компаний 200 (tatneft.ru, gazprom.ru), e-disclosure 403.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_AZIPI_BASE = "https://e-disclosure.azipi.ru"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_TIMEOUT = 20

# Категории раскрытия по Положению №714-П, за которыми стоит отчётность.
_REPORT_TITLES = (
    "бухгалтерск", "финансовой отчетности", "финансовой отчётности",
    "консолидированной финансовой", "промежуточной", "мсфо", "отчет эмитента",
    "отчёт эмитента", "существенных фактах",
)

# Расширения, за которыми лежит сама отчётность. zip/rar не берём: внутри архива
# может быть что угодно, а распаковка на проде — отдельная поверхность отказа.
_DOC_EXT_RE = re.compile(r"\.(pdf|xlsx?|docx?)(\?|$)", re.I)

# Ссылка на файл/страницу с полным текстом внутри сообщения о раскрытии.
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)

# Слова, по которым ссылка похожа на отчётность, а не на устав или анкету.
_DOC_HINT_RE = re.compile(
    r"отч[её]т|бухгалт|финанс|мсфо|ifrs|рсбу|консолид|report|statement|fs[-_]?\d|"
    r"итог|результат", re.I)


def azipi_org_page(inn: str) -> str | None:
    """Постоянный адрес страницы эмитента в АЗИПИ по ИНН. Это точка входа в реестр:
    один запрос вместо ручного справочника IR-адресов на 264 компании."""
    if not inn:
        return None
    try:
        r = httpx.get(f"{_AZIPI_BASE}/search/index.php",
                      params={"orgs": "Y", "ORG_INN": inn, "search_organization": "Поиск"},
                      timeout=_TIMEOUT, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        m = re.search(r'href="(/organization/personal-pages/\d+/)"', r.text)
        return f"{_AZIPI_BASE}{m.group(1)}" if m else None
    except Exception:  # noqa: BLE001 — недоступность центра не должна ронять вызывающего
        logger.warning("report_documents: АЗИПИ не ответил по ИНН %s", inn)
        return None


def _message_urls(msg_url: str) -> tuple[str, list[str]]:
    """Текст сообщения о раскрытии + все ссылки из него."""
    try:
        r = httpx.get(msg_url, timeout=_TIMEOUT, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    except Exception:  # noqa: BLE001
        return "", []
    # ссылки берём ДО срезания тегов: часть адресов живёт только в href
    hrefs = re.findall(r'href="([^"]+)"', html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    urls = [u for u in _URL_RE.findall(text)]
    for h in hrefs:
        if h.startswith("http"):
            urls.append(h)
        elif h.startswith("/"):
            urls.append(f"{_AZIPI_BASE}{h}")
    seen, out = set(), []
    for u in urls:
        u = u.rstrip(".,;)")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return text, out


def find_report_docs(inn: str, since: date, until: date | None = None,
                     max_messages: int = 6) -> dict:
    """Документы отчётности эмитента за окно дат.

    Возвращает {"org_page", "messages": [...], "documents": [...], "site_links": [...]}.
    documents — прямые ссылки на файлы (pdf/xls/doc), site_links — адреса страниц
    (обычно IR-раздел компании), куда эмитент отправляет за полным текстом.
    Пустой результат — нормальный исход, а не ошибка: у эмитента может не быть
    раскрытия в этом центре или за это окно.
    """
    until = until or date.today()
    org = azipi_org_page(inn)
    if not org:
        return {"org_page": None, "messages": [], "documents": [], "site_links": []}
    try:
        r = httpx.get(org, timeout=_TIMEOUT, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        html = r.text
    except Exception:  # noqa: BLE001
        logger.warning("report_documents: страница эмитента не открылась: %s", org)
        return {"org_page": org, "messages": [], "documents": [], "site_links": []}

    picked: list[dict] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        if "/messages/" not in row:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 3:
            continue
        date_txt = re.sub(r"<[^>]+>", "", cells[0]).strip()
        try:
            d, mo, y = date_txt.split(".")
            row_date = date(int(y), int(mo), int(d))
        except ValueError:
            continue
        if not (since <= row_date <= until):
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[2])).strip()
        if not any(k in title.lower() for k in _REPORT_TITLES):
            continue
        m = re.search(r'href="(/messages/\d+/)"', cells[2])
        if not m:
            continue
        picked.append({"date": row_date.isoformat(), "title": title[:200],
                       "url": f"{_AZIPI_BASE}{m.group(1)}"})
        if len(picked) >= max_messages:
            break

    documents: list[dict] = []
    site_links: list[str] = []
    for msg in picked:
        text, urls = _message_urls(msg["url"])
        msg["chars"] = len(text)
        for u in urls:
            if _AZIPI_BASE in u and "/messages/" in u:
                continue  # ссылка на саму себя
            if _DOC_EXT_RE.search(u):
                documents.append({"url": u, "from": msg["url"], "date": msg["date"],
                                  "looks_relevant": bool(_DOC_HINT_RE.search(u))})
            elif u.startswith("http") and _AZIPI_BASE not in u:
                site_links.append(u)

    # свои и очевидно нерелевантные адреса не тащим дальше
    site_links = [u for u in dict.fromkeys(site_links)
                  if not re.search(r"cbr\.ru|consultant|garant|yandex|google|vk\.com|t\.me", u, re.I)]
    return {"org_page": org, "messages": picked, "documents": documents,
            "site_links": site_links[:12]}


def fetch_document_text(url: str) -> dict:
    """Текст документа по ссылке (pdf через pypdf, html — очисткой тегов).

    Переиспользует article_texts.fetch_article_text — тот же путь, которым платформа
    уже читает бюллетени ЦБ и статьи, вместе с его потолком в 60k знаков и защитой
    от заглушек короче 200 знаков.
    """
    from app.services.article_texts import fetch_article_text
    t = fetch_article_text(url)
    return {"url": url, "ok": bool(t), "chars": len(t or ""), "text": t or ""}


def probe(inn: str, days_back: int = 120) -> dict:
    """Диагностика: что вообще доступно по эмитенту. Без записи в БД."""
    res = find_report_docs(inn, date.today() - timedelta(days=days_back))
    res["documents_fetchable"] = []
    for doc in res["documents"][:3]:
        got = fetch_document_text(doc["url"])
        res["documents_fetchable"].append(
            {"url": doc["url"], "ok": got["ok"], "chars": got["chars"],
             "head": got["text"][:200]})
    return res
