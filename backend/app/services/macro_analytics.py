"""MacroAnalyticsService — Конвейер 2: автоматический мониторинг аналитики.

Постоянный пайплайн (раз в сутки), НЕ разовое скачивание:
1) ОБНАРУЖЕНИЕ новых документов ПАРСЕРОМ (код, бесплатно): зайти на страницы
   публикаций (ЦБ /dkp/, ЦМАКП forecast.ru), собрать ссылки на PDF, сравнить с уже
   обработанными (по source_url) → новые.
2) СКАЧИВАНИЕ нового PDF (код) + извлечение текста (pypdf).
3) АНАЛИЗ И ПЕРЕСКАЗ — DeepSeek (LLM-прослойка): выжимка строго по тексту + тезисы
   с акцентом на ВЛИЯНИЕ (компании/секторы/рынок/ставка/макро). Запрет на додумывание.
4) СОХРАНЕНИЕ в MacroAnalyticsDoc.
УСТОЙЧИВОСТЬ: если страница-источник дала 0 ссылок (смена вёрстки) — лог-алерт,
НЕ падаем молча.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.models.macro import MacroAnalyticsDoc
from app.services import llm
from app.services.macro_ingest import load_macro_config

logger = logging.getLogger(__name__)

_HTTP = {"User-Agent": "BasisMacroBot/1.0 (+https://inbasis.ru)"}
_MAX_PER_RUN = 6        # потолок новых документов за прогон (контроль стоимости)
_MAX_PDF_CHARS = 14000  # сколько текста PDF отдаём модели (хватает на выжимку)
_FRESH_DAYS = 92        # берём только свежие документы (последние ~3 мес), архив игнорируем

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
           "sep": 9, "oct": 10, "nov": 11, "dec": 12, "june": 6, "july": 7,
           "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6, "июл": 7,
           "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}


def doc_date(url: str) -> date | None:
    """Извлечь дату публикации документа из URL/имени файла (для отсева архива).

    Поддержанные форматы: YYYYMMDD (comment_20210422), DDMMYYYY (29052026),
    MMYYYY (Mon042026), YY-MM (Infl_exp_21-08), месяц-имя_YYYY (SOI_may_2026),
    голый год (shlyk2026 / VIRUS2019). None — если дату определить нельзя.

    Форматы без явного дня (MMYYYY / месяц-имя_YYYY / YY-MM) угадывают день=28 —
    ПРИБЛИЖЕНИЕ, не факт публикации. Угадка зажимается сверху сегодняшней датой
    (min(guess, today)): документ уже обнаружен на сайте источника → он ТОЧНО
    опубликован не позже сегодня, а «день=28» иногда попадал в будущее (баг:
    inFOM_26-07.pdf для отчёта за июль отдавал 28 июля, хотя ЦБ мог опубликовать
    его раньше — например 23-го, и сайт уже отдавал PDF). Без зажима фронт
    показывал бы дату публикации «из будущего», которая ещё не наступила."""
    s = url.lower()
    today = date.today()
    for m in re.finditer(r"(\d{8})", s):  # YYYYMMDD | DDMMYYYY
        for fmt in ("%Y%m%d", "%d%m%Y"):
            try:
                d = datetime.strptime(m.group(1), fmt).date()
                if 2008 <= d.year <= 2030:
                    return min(d, today)
            except ValueError:
                continue
    m = re.search(r"(\d{2})(20\d{2})(?!\d)", s)  # MMYYYY: 042026
    if m and 1 <= int(m.group(1)) <= 12:
        return min(date(int(m.group(2)), int(m.group(1)), 28), today)
    m = re.search(r"(" + "|".join(_MONTHS) + r")[_\-]?(20\d{2})", s)  # may_2026
    if m:
        return min(date(int(m.group(2)), _MONTHS[m.group(1)], 28), today)
    m = re.search(r"(?<!\d)(\d{2})-(\d{2})(?!\d)", s)  # YY-MM: 21-08 (вкл. старые 14-02)
    if m:
        yy, mm = 2000 + int(m.group(1)), int(m.group(2))
        if 1 <= mm <= 12 and 2008 <= yy <= 2030:
            return min(date(yy, mm, 28), today)
    # УДАЛЁН fallback «голый год → 30 июня»: он подставлял вымышленную дату
    # (не факт публикации) для любого URL без месяца/дня — типично для ЦМАКП
    # (forecast.ru). При «голом годе» вызывающий код обязан обратиться к
    # page_date() (реальная дата со страницы), а не выдумывать середину года.
    return None


def page_date(url: str) -> date | None:
    """Дата публикации со СТРАНИЦЫ документа (запасной путь, если в URL даты нет):
    ищем дату в тексте/метаданных. None — если не нашли."""
    try:
        r = httpx.Client(timeout=15, headers=_HTTP, follow_redirects=True).get(url)
        if r.status_code != 200:
            return None
        txt = r.text
    except Exception:  # noqa: BLE001
        return None
    # ISO/DD.MM.YYYY/«12 мая 2026»
    m = re.search(r"(20[0-2]\d)-(\d{2})-(\d{2})", txt) or re.search(r"(\d{2})\.(\d{2})\.(20[0-2]\d)", txt)
    if m:
        g = m.groups()
        try:
            return date(int(g[0]), int(g[1]), int(g[2])) if len(g[0]) == 4 else date(int(g[2]), int(g[1]), int(g[0]))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+(" + "|".join(k for k in _MONTHS if len(k) > 2) + r")\w*\s+(20[0-2]\d)", txt.lower())
    if m:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1)))
        except (ValueError, KeyError):
            return None
    return None


def _is_fresh(url: str) -> bool:
    """Свежий ли документ. Сначала дата из URL (без сетевых запросов); если там только
    «голый год» (типично для ЦМАКП) — один сетевой запрос на страницу за реальной датой.
    ПРИ СОМНЕНИИ ОТБРАСЫВАЕМ: дату определить не удалось → НЕ берём (лучше пробел, чем
    архив с выдуманной датой)."""
    d = doc_date(url) or page_date(url)
    return d is not None and d >= (date.today() - timedelta(days=_FRESH_DAYS))


def _excluded(url: str) -> bool:
    """URL в чёрном списке паттернов (тангенциальные ДИП-записки и т.п. — не обзоры)."""
    pats = load_macro_config().get("analytics_exclude_url_patterns", [])
    low = (url or "").lower()
    return any(p.lower() in low for p in pats)


def cleanup_old(db: Session, days: int = _FRESH_DAYS) -> int:
    """Удалить из БД обзоры старше `days` ИЛИ с НЕопределяемой датой (при сомнении —
    убираем: лучше пробел, чем архив). Дату берём из URL, иначе со страницы.
    Заодно ПЕРЕСЧИТЫВАЕТ published_at для оставшихся строк — если логика доопределения
    даты поменялась (напр. фикс бага с угадкой дня=28, уходившей в будущее), старые
    строки, сохранённые до фикса, сами не исправятся: published_at пишется один раз при
    создании и не переоценивается, кроме как здесь."""
    cutoff = date.today() - timedelta(days=days)
    removed = 0
    fixed = 0
    for d in db.query(MacroAnalyticsDoc).all():
        url = d.source_url or ""
        if _excluded(url):  # тангенциальные записки — убираем из обзоров
            db.delete(d)
            removed += 1
            continue
        # НЕ доверяем published_at (мог быть ошибочно = today у старых записей):
        # определяем дату заново из URL, иначе со страницы документа.
        dd = doc_date(url) or page_date(url)
        if dd is None or dd < cutoff:
            db.delete(d)
            removed += 1
            continue
        if dd != d.published_at:
            d.published_at = dd
            fixed += 1
    db.commit()
    if removed or fixed:
        logger.info("Аналитика: удалено %d обзоров, исправлено дат %d (старше %d дн. или без надёжной даты)",
                    removed, fixed, days)
    return removed

_DOC_SYS = (
    "Ты пересказываешь аналитический документ (Банк России / ЦМАКП) для "
    "инвестиционно-аналитической платформы. Дан текст документа. Верни строго JSON "
    "{\"title\": \"<краткий заголовок документа>\", \"summary\": \"<выжимка 3-5 "
    "предложений строго по тексту>\", \"key_takeaways\": [\"<тезис>\", ...]}. "
    "key_takeaways — 3-6 тезисов с акцентом на ВЛИЯНИЕ: что документ значит для "
    "компаний/секторов/рынка/ключевой ставки/макро (НЕ общий пересказ, а выводы, "
    "влияющие на рынок). ЖЁСТКОЕ ПРАВИЛО: только из текста документа, не выдумывай "
    "факты/цифры; без торговых рекомендаций. Никакого текста вне JSON."
)


_INTERP_SYS = (
    "Ты — макроаналитик Basis. Дана выжимка аналитического документа (ЦБ/ЦМАКП). "
    "Дай КОРОТКУЮ интерпретацию (2-4 предложения): на какие рынки/секторы/компании и на "
    "ключевую ставку это влияет и НА ЧТО ОБРАТИТЬ ВНИМАНИЕ В ПЕРВУЮ ОЧЕРЕДЬ (главное, не всё "
    "подряд), через какой механизм. Опирайся только на содержание выжимки, без выдумок, без "
    "‘купить/продать’. Верни строго JSON {\"interpretation\": \"...\"}. Без текста вне JSON."
)


def _interpret(title: str, summary: str | None, takeaways: list) -> str | None:
    """F: интерпретация влияния через DeepSeek Pro (reasoning)."""
    if not summary and not takeaways:
        return None
    payload = {"title": title, "summary": summary, "key_takeaways": takeaways}
    import json as _json
    try:
        out = llm.complete(_INTERP_SYS, _json.dumps(payload, ensure_ascii=False),
                           json_mode=True, thinking=True, model=llm.pro_model(), max_tokens=3000)
        return (out.get("interpretation") or "").strip() or None
    except llm.LLMError as e:
        logger.warning("Интерпретация обзора не получена: %s", e)
        return None


def _absolutize(href: str, base: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return base.rstrip("/") + "/" + href.lstrip("/")


def discover(db: Session) -> list[dict]:
    """Собрать ссылки на новые документы (которых ещё нет в БД). Парсер, без LLM."""
    cfg = load_macro_config()
    known = {u for (u,) in db.query(MacroAnalyticsDoc.source_url).all()}
    found: list[dict] = []
    for src in cfg.get("analytics_sources", []):
        try:
            r = httpx.Client(timeout=25, headers=_HTTP, follow_redirects=True).get(src["page_url"])
            r.raise_for_status()
            html = r.text
        except Exception as e:  # noqa: BLE001
            logger.warning("Аналитика: страница %s недоступна: %s", src["page_url"], type(e).__name__)
            continue
        ext = src.get("ext", ".pdf")
        links = re.findall(r'href="([^"]+%s)"' % re.escape(ext), html, flags=re.IGNORECASE)
        if not links:
            # СЛЕПОТА парсера — алерт владельцу (смена вёрстки), не молчим
            logger.warning("Аналитика-мониторинг: источник %s (%s) дал 0 ссылок — "
                           "возможна смена вёрстки сайта!", src["source"], src["page_url"])
            continue
        seen = set()
        per_src = 0
        cap = int(src.get("max", _MAX_PER_RUN))
        for href in links:
            url = _absolutize(href, src["base_url"])
            if url in known or url in seen:
                continue
            if not _is_fresh(url) or _excluded(url):  # архив или тангенциальная записка
                continue
            seen.add(url)
            title = href.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            found.append({"source": src["source"], "doc_type": src.get("doc_type"),
                          "url": url, "title": title})
            per_src += 1
            if per_src >= cap:  # не более N новых на источник за прогон
                break
    return found


def _pdf_text(url: str) -> str | None:
    try:
        r = httpx.Client(timeout=40, headers=_HTTP, follow_redirects=True).get(url)
        r.raise_for_status()
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        parts = []
        for page in reader.pages[:20]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) > _MAX_PDF_CHARS:
                break
        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        return text[:_MAX_PDF_CHARS] or None
    except Exception as e:  # noqa: BLE001
        logger.warning("Аналитика: не удалось извлечь PDF %s: %s", url, type(e).__name__)
        return None


def process(db: Session, max_docs: int = _MAX_PER_RUN) -> dict:
    """Полный прогон мониторинга: обнаружить новые → скачать → выжимка LLM → сохранить."""
    cleanup_old(db)  # сначала убираем архив с витрины
    candidates = discover(db)
    if not candidates:
        return {"discovered": 0, "saved": 0}
    model_used = f"{llm.provider_info().get('provider')}:{llm.provider_info().get('model')}"
    saved = 0
    for c in candidates[:max_docs]:
        pub_date = doc_date(c["url"]) or page_date(c["url"])
        if pub_date is None:
            logger.warning("Аналитика: дата публикации не определена для %s — пропуск "
                           "(не выдумываем)", c["url"])
            continue
        text = _pdf_text(c["url"])
        if not text or len(text) < 400:
            continue  # не извлеклось содержимое — пропускаем (не выдумываем)
        try:
            out = llm.complete(_DOC_SYS, text[:_MAX_PDF_CHARS], json_mode=True, max_tokens=2048)
        except llm.LLMError as e:
            logger.error("Аналитика: LLM не дал выжимку для %s: %s", c["url"], e)
            continue
        title = (out.get("title") or c["title"])[:500]
        summary = (out.get("summary") or "").strip() or None
        takeaways = out.get("key_takeaways") or []
        # F. Интерпретация «на что влияет / на кого смотреть в первую очередь» —
        # это РАССУЖДЕНИЕ → DeepSeek Pro (reasoning), не Flash.
        interp = _interpret(title, summary, takeaways)
        db.add(MacroAnalyticsDoc(
            source=c["source"], doc_type=c["doc_type"], title=title,
            summary=summary, key_takeaways=takeaways, interpretation=interp,
            published_at=pub_date, source_url=c["url"],
            model_used=model_used + ("+pro" if interp else ""),
        ))
        saved += 1
    db.commit()
    res = {"discovered": len(candidates), "saved": saved}
    logger.info("Аналитика-мониторинг: %s", res)
    return res
