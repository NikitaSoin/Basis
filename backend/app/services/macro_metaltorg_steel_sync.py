"""Синхронизация РОССИЙСКИХ цен на чёрные металлы (metaltorg.ru).

Владелец явно отклонил (2026-07-27) ранее подключённый CME HRC=F (Yahoo Finance,
см. macro_yahoo_commodities_sync.py) как "рынок США нас не интересует" и попросил
именно рублёвые внутренние цены — они определяют экономику Северстали/НЛМК/ММК/
Мечела, а не мировой ориентир (собственные материалы металлургов подчёркивают, что
российские внутренние цены обычно ВЫШЕ мировых и определяются спросом, не паритетом
экспорта). НЕ убираем yahoo_steel_hrc (он остаётся честным ориентиром НАПРАВЛЕНИЯ
мирового цикла для того, кому это нужно) — но commodity_exposure металлургов
переключается на ЭТОТ ряд как основной, российский.

Источник — https://www.metaltorg.ru/cources/russian/, страница отдаётся БЕЗ логина,
БЕСПЛАТНО, но 🔴 в кодировке windows-1251 (НЕ UTF-8!) — декодируем explicit, иначе
любой байтовый grep/regex по русским строкам молча не находит совпадений (так уже
ловились один раз — см. work-journal.md 2026-07-28: WebFetch видел данные корректно,
прямой curl без iconv — нет, из-за этого самого несовпадения кодировки).

Страница даёт два разных по глубине источника данных:
  1. "Сводный индекс цен" (композитный индекс чёрных металлов, отн.ед.) — ПОЛНАЯ
     история (~13 месяцев на момент подключения) встроена прямо в HTML как JS-массив
     (`data.addRows([...])` для Google Charts, в <script>, НЕ AJAX/API) — сервер
     отдаёт её при КАЖДОЙ загрузке страницы, без параметров периода. Разрешение
     фактически недельное (значения обновляются раз в ~7 дней, не ежедневно —
     несмотря на дневные timestamp'ы в массиве).
  2. 10 отдельных товарных позиций (руб/т) — станицаа даёт бесплатно ТОЛЬКО текущее
     + предыдущее значение (2 точки), глубокий архив — платный (проверено:
     /cources/russian/prices/index.php отвечает "имеют только подписчики"). Поэтому
     по товарным позициям набираем СВОЮ историю день за днём через суточный крон,
     а не бэкфиллим прошлое (его не существует в бесплатном доступе).

Курируем ТОЛЬКО 2 из 10 товарных позиций страницы — те, что реально использует
commodity_exposure металлургов (см. .claude/agents/market-analyst.md): "Лист
горячекатаный" (плоский прокat, НЛМК/Северсталь/ММК/ПРОФНАСТИЛ) и "Арматура"
(сортовой прокат, ЧМК/Мечел). Остальные 7 позиций страницы (х/к и оцинкованный
рулон, круг, уголок, балка, швеллер, труба водогазопроводная — труба электросварная
пока тоже не курируем, у ТРМК профиль ОCTG/бесшовные трубы, welded pipe — не точный
прокси) НЕ регистрируем — нет потребителя на платформе; добавить точечно, когда
появится компания, которой это будет нужно (не плодить неиспользуемые ряды).

🔴 Источник НЕофициальный (не биржа/ЦБ/Росстат), верстка старая (HTML4, вложенные
таблицы, невалидный HTML местами) — парсим устойчивым регексом по маркерам
(bgcolor="#F1F4F5", <font color="Black"><b>), не BeautifulSoup. Владелец одобрил
компромисс явно, аналогично Yahoo Finance/TankerMap (см. work-journal.md 2026-07-28).
"""
from __future__ import annotations

import logging
import re
from datetime import date

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_URL = "https://www.metaltorg.ru/cources/russian/"
_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# Полная строка таблицы: название (ссылка или font) + ед.изм. + текущее (Black) +
# предыдущее (Gray) значение. HTML-комментарии убираем ДО матчинга (regex ниже) —
# у некоторых строк есть закомментированная альтернативная разметка того же вида
# (дубли <td>), без вырезания комментариев регекс путается и матчит внутри них.
_ROW_RE = re.compile(
    r'<td bgcolor="#F1F4F5">\s*(?:<a[^>]*>\s*([^<]+?)\s*</a>|<font[^>]*>([^<]+)</font>),?\s*([^<]*?)\s*</td>\s*'
    r'<td bgcolor="#F1F4F5" align="right">\s*'
    r'<font color="Black"><b>([\d.]+)</b></font>\s*'
    r'(?:<a.*?</a>)?\s*'
    r'<br>\s*'
    r'<font color="Gray"><b>([\d.]+)</b></font>',
    re.DOTALL,
)
_CHART_ROW_RE = re.compile(r"new Date\((\d+),(\d+),\s*(\d+)\),(?:null|[\d.]+),([\d.]+)\]")

# Название на странице → (indicator_code, источник для лога). Курируемое
# подмножество — см. докстринг файла.
_PRODUCTS = {
    "Лист горячекатаный": "metaltorg_hrc",
    "Арматура": "metaltorg_rebar",
}
_COMPOSITE_CODE = "metaltorg_steel_index"


def sync_metaltorg_steel(db: Session) -> dict:
    """Полный пересчёт при каждом запуске (как у Yahoo-синка): ряд короткий,
    страница сама переотдаёт всё окно истории композитного индекса — дешевле и
    надёжнее частичного догона, заодно самозалечивает пропущенные суточные точки
    товарных позиций, если крон не отработал день-два."""
    try:
        r = httpx.get(_URL, timeout=25, headers=_HTTP, follow_redirects=True)
        r.raise_for_status()
        html = r.content.decode("windows-1251", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.warning("metaltorg.ru: страница недоступна: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}

    html_clean = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    out: dict = {}

    chart_match = re.search(r"data\.addRows\(\[(.*?)\]\s*\)\s*;", html_clean, re.DOTALL)
    if chart_match:
        by_day: dict[date, float] = {}
        for y, m, d, val in _CHART_ROW_RE.findall(chart_match.group(1)):
            try:
                by_day[date(int(y), int(m) + 1, int(d))] = float(val)
            except ValueError:
                continue
        saved = 0
        for day, val in sorted(by_day.items()):
            res = upsert_point(db, _COMPOSITE_CODE, day, "level", val, unit="индекс",
                               source="Металл Торг.Ру (Сводный индекс цен)", source_url=_URL,
                               ingested_via="metaltorg", commit=False)
            if res in ("insert", "revise"):
                saved += 1
        out[_COMPOSITE_CODE] = {"saved": saved, "points": len(by_day)}
    else:
        logger.warning("metaltorg.ru: встроенный график композитного индекса не найден (изменилась вёрстка?)")
        out[_COMPOSITE_CODE] = {"error": "chart_not_found"}

    today = date.today()
    seen = set()
    for m in _ROW_RE.finditer(html_clean):
        name = (m.group(1) or m.group(2) or "").strip()
        if name not in _PRODUCTS or name in seen:
            continue
        seen.add(name)
        code = _PRODUCTS[name]
        try:
            val = float(m.group(4))
        except ValueError:
            continue
        res = upsert_point(db, code, today, "level", val, unit="руб/т",
                           source="Металл Торг.Ру", source_url=_URL,
                           ingested_via="metaltorg", commit=False)
        out[code] = {"saved": 1 if res in ("insert", "revise") else 0, "value": val}

    missing = set(_PRODUCTS) - seen
    if missing:
        logger.warning("metaltorg.ru: не найдены товарные позиции на странице: %s", missing)

    db.commit()
    logger.info("metaltorg.ru: %s", out)
    return out
