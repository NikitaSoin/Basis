"""Инструменты агента-добытчика макроданных (шаг 4 агентного контура).

🔴 Почему отдельный набор, а не existing execute_tool: тот заточен под ОДИН тикер
(`allowed_ticker`, условие `tickers ? :tk` в летописи) — это правильно для пилота по
компании, но макро-вопрос тикера не имеет. Пилот не трогаем: у него свой контур,
свой гейт и свои лимиты.

🔴 ПОРЯДОК ПОИСКА — требование владельца (2026-08-02): «необязательно прям сайт
Росстата — в крупных СМИ обычно есть новости на эту тему, условные коммерсант/интерфакс/
РБК которые мы к себе тянем могут дать что нужно, может даже в нашей ленте что-то есть».
Проверено на данных: в летописи лежит Коммерсант «Росстат фиксирует стабильную
занятость» свежее нашего ряда безработицы — число уже в потоке платформы, просто не
извлечено в ряд. Поэтому: сначала СВОЯ лента → потом дочитать первоисточник по ссылке
→ и только затем веб-поиск. Это и дешевле, и быстрее, и материалы уже отобраны нами.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "search_our_feed",
        "description": ("ПЕРВЫЙ инструмент, с которого надо начинать. Полнотекстовый поиск по "
                        "ленте и летописи платформы (Коммерсант, Интерфакс, РБК, ЦБ, ЦМАКП, "
                        "аналитические каналы). Часто нужное число уже пришло к нам — тогда "
                        "не нужен ни веб-поиск, ни сайт первоисточника."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "ключевые слова, напр. «безработица Росстат июнь»"},
            "days": {"type": "integer", "description": "окно поиска в днях, по умолчанию 120"},
            "limit": {"type": "integer", "description": "сколько записей вернуть, максимум 15"},
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_feed_item",
        "description": ("Полный текст записи ленты по id из search_our_feed. Если в пересказе "
                        "числа нет, а ссылка есть — инструмент сам дочитает первоисточник."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "integer"}}, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "get_series_state",
        "description": "Что у нас сейчас лежит в ряду показателя: последние точки, единица, частота.",
        "parameters": {"type": "object", "properties": {
            "code": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Поиск в интернете. Использовать, ТОЛЬКО если своя лента не дала ответа.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_document",
        "description": "Скачать страницу/PDF по URL и вернуть текст — для проверки числа в первоисточнике.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
]


def _search_our_feed(db: Session, query: str, days: int, limit: int) -> dict:
    """Полнотекстовый поиск по летописи. Без привязки к тикеру — вопрос макро."""
    days = max(7, min(int(days or 120), 1095))
    limit = max(1, min(int(limit or 8), 10))
    words = [w for w in str(query or "").split() if len(w) > 2][:6]
    if not words:
        return {"error": "empty_query"}
    # 🔴 Экранируем спецсимволы регулярки: слово из запроса идёт В ШАБЛОН, и «5,84%»
    # или «(инФОМ)» иначе уронят поиск целиком.
    words = [re.sub(r"([\\^$.|?*+()\[\]{}])", r"\\\1", w) for w in words]
    # 🔴 РАНЖИРОВАНИЕ ПО ЧИСЛУ СОВПАВШИХ СЛОВ, а не «подходит любое слово».
    # Первая версия склеивала условия через OR и сортировала по дате: на запрос
    # «PMI России индекс деловой активности» первыми шли «Трамп допустил захват
    # Гренландии» и «Южнокорейский рынок акций» — совпало слово «России». Агент
    # получал мусор, решал, что в ленте ничего нет, и уходил в веб, сжигая шаги.
    # Теперь релевантность = сколько слов запроса реально встретилось, заголовок
    # весит вдвое против пересказа, и результаты ниже порога отбрасываются.
    params = {"days": days, "lim": limit}
    score_parts, where_parts = [], []
    for i, w in enumerate(words):
        # 🔴 Граница слова, а не подстрока. С «%май%» по запросу про зарплаты за МАЙ
        # первым шёл «в Москве запретят МАЙнинг»: подстрока совпала, релевантность
        # набралась, агент принимал мусор за материал по теме.
        # Длинному слову хватает границы СЛЕВА (\m) — так ловятся словоформы
        # («Росстат» → «Росстата»). Короткому нужна граница с ОБЕИХ сторон (\y),
        # иначе «май» снова цепляет «майнинг».
        params[f"w{i}"] = (r"\y" + w + r"\y") if len(w) <= 4 else (r"\m" + w)
        score_parts.append(f"(CASE WHEN title ~* :w{i} THEN 2 ELSE 0 END)")
        score_parts.append(f"(CASE WHEN summary ~* :w{i} THEN 1 ELSE 0 END)")
        where_parts.append(f"(title ~* :w{i} OR summary ~* :w{i})")
    score = " + ".join(score_parts)
    # 🔴 Порог пропорционален длине запроса: примерно половина слов должна реально
    # встретиться. С фиксированным порогом 3 запрос из шести слов проходил по двум
    # случайным совпадениям («2026», «плата»), и агент получал ленту про АЗС и
    # банковские карты вместо материала о зарплатах — а пустая выдача честнее:
    # по ней он сразу уходит в веб, где данные и лежат.
    params["min_score"] = 2 if len(words) <= 2 else max(3, len(words))
    sql = (f"SELECT id, title, summary, source_key, source_url, "
           f"COALESCE(event_date, published_at::date) AS d, ({score}) AS rel "
           f"FROM chronicle_entries "
           f"WHERE published_at > now() - (:days || ' days')::interval "
           f"AND ({' OR '.join(where_parts)}) "
           f"AND ({score}) >= :min_score "
           f"ORDER BY rel DESC, d DESC NULLS LAST LIMIT :lim")
    try:
        rows = db.execute(text(sql), params).all()
    except Exception:  # noqa: BLE001
        logger.warning("gap_tools: поиск по ленте не отработал", exc_info=True)
        return {"error": "search_failed"}
    if not rows:
        # Явная подсказка вместо пустого списка: агент не должен гадать, «плохо
        # искал» или «в ленте этого нет».
        return {"found": 0, "items": [],
                "note": "в ленте платформы ничего релевантного — ищи в вебе"}
    return {"found": len(rows), "items": [
        {"id": r[0], "date": str(r[5]) if r[5] else None, "title": r[1],
         "summary": (r[2] or "")[:220], "source": r[3], "url": r[4], "relevance": r[6]}
        for r in rows]}


def _read_feed_item(db: Session, item_id: int) -> dict:
    """Полный текст записи; при отсутствии — дочитывает первоисточник по ссылке."""
    row = db.execute(text(
        "SELECT id, title, summary, full_text, source_url FROM chronicle_entries WHERE id=:i"
    ), {"i": item_id}).first()
    if not row:
        return {"error": "not_found"}
    full = row[3]
    if not full and row[4]:
        try:
            from app.services.article_texts import fetch_article_text
            full = fetch_article_text(row[4])
            if full:
                db.execute(text("UPDATE chronicle_entries SET full_text=:t WHERE id=:i"),
                           {"t": full, "i": item_id})
                db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.warning("gap_tools: не дочитал первоисточник", exc_info=True)
    # 🔴 Возвращаем НЕ весь текст, а фрагменты вокруг чисел. Агент ищет значение
    # показателя — ему нужны места, где числа, а не статья целиком. Первая версия
    # отдавала 20 000 знаков (~9k токенов за вызов) и агент сжигал весь бюджет за
    # два обращения, не дойдя до ответа (2026-08-02).
    return {"id": row[0], "title": row[1], "summary": row[2],
            "source_url": row[4],
            "number_snippets": _number_snippets(full) if full else None,
            "note": None if full else "полный текст недоступен — работай по пересказу или ищи иначе"}


def _number_snippets(text: str, limit: int = 14, width: int = 160) -> list[str]:
    """Фрагменты вокруг чисел с единицами — то, ради чего текст и открывали."""
    out, used = [], []
    pattern = re.compile(r"\d+[.,]?\d*\s*(?:%|процент\w*|млрд|млн|трлн|руб|п\.п\.|пункт\w*)", re.I)
    for m in pattern.finditer(text or ""):
        start = max(0, m.start() - width // 2)
        if any(abs(start - u) < width // 2 for u in used):
            continue  # не дублируем соседние вхождения
        used.append(start)
        out.append(re.sub(r"\s+", " ", text[start:m.end() + width // 2]).strip())
        if len(out) >= limit:
            break
    return out


def _get_series_state(db: Session, code: str) -> dict:
    from app.models.macro import MacroIndicator
    ind = db.get(MacroIndicator, str(code or "").strip())
    if not ind:
        return {"error": "unknown_indicator"}
    rows = db.execute(text(
        "SELECT as_of, value, metric FROM macro_data_points WHERE indicator_code=:c "
        "ORDER BY as_of DESC LIMIT 6"), {"c": ind.code}).all()
    # 🔴 СТРАНА обязательна в ответе. Без неё агент нашёл КИТАЙСКИЙ композитный PMI и
    # предложил его для российского ряда — число в тексте было, гейт пропустил
    # (2026-08-02). Показатель без страны — это не показатель.
    country = {"ru": "Россия", "cn": "Китай", "us": "США", "eu": "Еврозона",
               "world": "мир"}.get(ind.country, ind.country or "не указана")
    return {"code": ind.code, "title": ind.title, "unit": ind.unit,
            "country": country, "frequency": ind.frequency,
            "warning": f"Нужны данные ИМЕННО по стране: {country}. Значение по другой "
                       f"стране в этот ряд не подходит.",
            "last_points": [{"date": str(r[0]), "value": float(r[1]), "metric": r[2]} for r in rows]}


def execute(db: Session, name: str, args: dict) -> dict:
    """Диспетчер макро-инструментов. Тикер не участвует — вопрос макроэкономический."""
    if name == "search_our_feed":
        return _search_our_feed(db, str(args.get("query", "")),
                                int(args.get("days", 120) or 120),
                                int(args.get("limit", 10) or 10))
    if name == "read_feed_item":
        return _read_feed_item(db, int(args.get("id", 0) or 0))
    if name == "get_series_state":
        return _get_series_state(db, str(args.get("code", "")))
    if name == "web_search":
        from app.services.agent_web import web_search
        return web_search(str(args.get("query", "")), int(args.get("max_results", 5) or 5))
    if name == "fetch_document":
        from app.services.agent_web import fetch_document
        return fetch_document(str(args.get("url", "")))
    return {"error": "unknown_tool"}
