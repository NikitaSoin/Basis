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

🔴 Какие центры реально доступны С БОЕВОГО СЕРВЕРА (замер 2026-08-29, проверять
только оттуда — с ноутбука картина другая):

    ПРАЙМ  disclosure.1prime.ru    200  ← используем, есть постоянная страница по ИНН
    СКРИН  disclosure.skrin.ru     200  ← резерв (там лента по ДАТАМ, не по эмитенту)
    АК&М   disclosure.ru           200     не подключён, точка расширения
    АЗИПИ  e-disclosure.azipi.ru   ConnectTimeout — НЕДОСТУПЕН
    Интерфакс e-disclosure.ru      403 (JS-challenge) — нужен headless-браузер

Первая версия этого модуля ходила в АЗИПИ — и возвращала ноль по всем эмитентам,
потому что центр с боя не отвечает вовсе. Это же объясняет ноль записей от АЗИПИ в
замере источников: код `report_watch._from_azipi` существует, но исполниться не
может. Работаем через ПРАЙМ: у него страница эмитента адресуется прямо по ИНН
(portal/default.aspx?emId=<ИНН>), что и требуется для реестра.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import httpx

logger = logging.getLogger(__name__)

_PRIME_BASE = "https://disclosure.1prime.ru"
_AZIPI_BASE = "https://e-disclosure.azipi.ru"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
_TIMEOUT = 20

# Категории раскрытия по Положению №714-П, за которыми стоит отчётность.
#
# 🔴 Список выведен из ФАКТИЧЕСКИХ заголовков ленты эмитента, а не из головы.
# Первая версия фильтра («бухгалтерск», «финансовой отчетности», «мсфо», …) не
# пропустила НИ ОДНОГО из 280 сообщений Татнефти: реальные категории называются
# иначе. Две, которые действительно нужны:
#   «Финансовые результаты деятельности эмитента (компаний группы эмитента)
#    (прогнозные, предварительные, фактические)» — сами результаты;
#   «Сообщение о порядке доступа к инсайдерской информации, содержащейся в
#    документе эмитента» — именно ЭТИМ сообщением эмитент публикует адрес, по
#    которому лежит файл отчётности. Категория звучит канцелярски и к отчётности
#    на слух не относится — угадать её было нельзя, только увидеть.
# Прежние формулировки оставлены: у других центров раскрытия заголовки свои.
_REPORT_TITLES = (
    "финансовые результаты деятельности",
    "порядок доступа к инсайдерской информации",
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



_EVENT_DATE_RE = re.compile(
    r"Дата наступления события[^:]*:\s*(\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}\s+\S+\s+\d{4})",
    re.IGNORECASE)
_RU_MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
              "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11,
              "декабря": 12}


def _parse_ru_date(s: str):
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d))
        except ValueError:
            return None
    m = re.match(r"(\d{1,2})\s+(\S+)\s+(\d{4})", s)
    if m:
        d, mon, y = m.groups()
        mo = _RU_MONTHS.get(mon.lower())
        if mo:
            try:
                return date(int(y), mo, int(d))
            except ValueError:
                return None
    return None


def issuer_page(inn: str) -> str | None:
    """Постоянный адрес страницы эмитента по ИНН — точка входа в реестр раскрытия.

    ПРАЙМ адресует эмитента прямо по ИНН, без поискового запроса: один предсказуемый
    адрес вместо ручного справочника IR-ссылок на 264 компании. АЗИПИ оставлен
    резервом — он требует поиска и с боевого сервера сейчас не отвечает.
    """
    return f"{_PRIME_BASE}/portal/default.aspx?emId={inn}" if inn else None


def _prime_message_url(inn: str, guid: str) -> str:
    return f"{_PRIME_BASE}/Portal/GetMessage.aspx?emId={inn}&guid={guid}"


def _message_urls(msg_url: str) -> tuple[str, list[str]]:
    """Текст сообщения о раскрытии + все ссылки из него.

    Ссылки собираем и из href, и из видимого текста: адрес страницы с полным текстом
    эмитент по Положению №714-П пишет ПРОЗОЙ в теле сообщения, ссылкой он там быть
    не обязан.
    """
    try:
        r = httpx.get(msg_url, timeout=_TIMEOUT, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    except Exception:  # noqa: BLE001
        return "", []
    hrefs = re.findall(r'href="([^"]+)"', html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    urls = list(_URL_RE.findall(text))
    for h in hrefs:
        if h.startswith("http"):
            urls.append(h)
        elif h.startswith("/"):
            urls.append(f"{_PRIME_BASE}{h}")
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

    Возвращает {"org_page", "messages", "documents", "site_links"}. Пустой результат —
    нормальный исход, а не ошибка: у эмитента может не быть раскрытия за это окно.

    🔴 В таблице ПРАЙМ первая ячейка — порядковый НОМЕР строки, а не дата (в отличие
    от СКРИН и АЗИПИ). Дата события лежит только внутри самого сообщения, поэтому
    сначала фильтруем по КАТЕГОРИИ (дёшево, по заголовку), и лишь потом читаем
    содержимое и проверяем дату. Обратный порядок означал бы чтение всей ленты
    эмитента ради нескольких строк.
    """
    until = until or date.today()
    org = issuer_page(inn)
    if not org:
        return {"org_page": None, "messages": [], "documents": [], "site_links": []}
    try:
        r = httpx.get(org, timeout=_TIMEOUT, headers=_UA, follow_redirects=True)
        r.raise_for_status()
        html = r.text
    except Exception:  # noqa: BLE001
        logger.warning("report_documents: страница эмитента не открылась: %s", org)
        return {"org_page": org, "messages": [], "documents": [], "site_links": []}

    # Счётчики разбора: без них «ноль сообщений» неотличим от «страница пустая»,
    # «строки не те» и «фильтр по категории слишком узкий» — а это три разные починки.
    diag = {"html_chars": len(html), "rows": 0, "rows_with_message": 0,
            "titles_seen": [], "matched_category": 0,
            "window": [since.isoformat(), until.isoformat()]}
    candidates: list[dict] = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        diag["rows"] += 1
        if "GetMessage" not in row:
            continue
        diag["rows_with_message"] += 1
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 2:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cells[1])).strip()
        # РАЗНЫЕ заголовки, а не первые восемь: первые восемь — это подряд идущие
        # решения СД и собрания, по ним нельзя понять, есть ли вообще у эмитента
        # категория «раскрытие отчётности» в этом центре.
        short = title[:110]
        if short not in diag["titles_seen"] and len(diag["titles_seen"]) < 30:
            diag["titles_seen"].append(short)
        if not any(k in title.lower() for k in _REPORT_TITLES):
            continue
        diag["matched_category"] += 1
        gm = re.search(r"guid=(\{[0-9A-Fa-f-]+\})", row)
        if not gm:
            continue
        candidates.append({"title": title[:200], "url": _prime_message_url(inn, gm.group(1))})
        if len(candidates) >= max_messages * 3:
            break

    picked: list[dict] = []
    documents: list[dict] = []
    site_links: list[str] = []
    diag["msg_fetched"] = 0
    diag["msg_empty"] = 0
    diag["msg_out_of_window"] = 0
    diag["msg_no_date"] = 0
    for cand in candidates:
        if len(picked) >= max_messages:
            break
        text, urls = _message_urls(cand["url"])
        if not text:
            # Страница сообщения не открылась или пуста. Отличать это от «дата не
            # подошла» обязательно: первое чинится запросом, второе — окном дат.
            diag["msg_empty"] += 1
            if not diag.get("msg_fail_example"):
                diag["msg_fail_example"] = cand["url"]
            continue
        diag["msg_fetched"] += 1
        dm = _EVENT_DATE_RE.search(text)
        msg_date = _parse_ru_date(dm.group(1)) if dm else None
        if msg_date is None:
            diag["msg_no_date"] += 1
        if len(diag.setdefault("msg_dates", [])) < 8:
            diag["msg_dates"].append(msg_date.isoformat() if msg_date else None)
        if msg_date and not (since <= msg_date <= until):
            diag["msg_out_of_window"] += 1
            continue
        msg = {"date": msg_date.isoformat() if msg_date else None,
               "title": cand["title"], "url": cand["url"], "chars": len(text)}
        picked.append(msg)
        for u in urls:
            if _PRIME_BASE in u:
                continue  # навигация самого портала
            if _DOC_EXT_RE.search(u):
                documents.append({"url": u, "from": cand["url"], "date": msg["date"],
                                  "looks_relevant": bool(_DOC_HINT_RE.search(u))})
            elif u.startswith("http"):
                site_links.append(u)

    site_links = [u for u in dict.fromkeys(site_links)
                  if not re.search(r"cbr\.ru|consultant|garant|yandex|google|vk\.com|t\.me|"
                                   r"1prime\.ru|interfax", u, re.I)]
    return {"org_page": org, "messages": picked, "documents": documents,
            "site_links": site_links[:12], "diag": diag}


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
