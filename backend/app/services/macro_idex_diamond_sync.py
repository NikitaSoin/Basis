"""Синхронизация индекса цен на алмазы IDEX Diamond Index (idexonline.com).

Владелец прислал скриншот графика IDEX (idexonline.com/diamond_prices_index,
5-летний период, текущее значение 83.47, -0.01%) и спросил: "мы не можем какой-то
дурацкий индекс спарсить? ты главное сможешь его обновлять?" (2026-07-27) — просьба
касалась АЛРОСА (ALRS), у которой commodity_exposure по алмазам был benchmark_key
"none" (Rapaport упомянут только в прозе, живого ряда не было).

Технический разбор: страница idexonline.com/diamond_prices_index рисует график через
Flot.js, данные тянет с БЕСПЛАТНОГО (без ключа/логина) JSON-эндпоинта
`Bid_Control-home_graph?driver_id=<N>&fromDate=YYYY-M-D&toDate=YYYY-M-D`. driver_id=0
даёт композитный индекс ("Итого"/Total) — ПОДТВЕРЖДЕНО: значение на дату проверки
(2026-07-27) совпало со скриншотом владельца (83.4696 ≈ 83.47) с точностью до сотых.
driver_id=1..15 — отдельные драйверы по категориям/размерам бриллиантов (НЕ композит —
проверено эмпирически: driver_id=1 дал другое число, не совпадающее со скриншотом).

Формат ответа: `{"label": "Total", "data": [[epoch_ms, value], ...]}` — эпоха в
МИЛЛИСЕКУНДАХ UTC. Полная история с driver_id=0 доступна с 2015-01-01 (4226 точек на
момент подключения) — БЕЗ пагинации, одним запросом; страница отдаёт то же самое, что
видит браузер, никакой авторизации/cookie не требуется (проверено прямым curl).

🔴 Источник НЕофициальный (не биржа/ЦБ/официальный отраслевой индекс) — внутренний AJAX
идекс страницы АЙДЕКС (израильской биржи необработанных алмазов), может измениться/
закрыться без предупреждения, как и остальные курируемые неофициальные источники
(Yahoo Finance, TankerMap, metaltorg.ru). Владелец одобрил компромисс явно, приложив
скриншот и спросив про обновляемость (см. work-journal.md 2026-07-28).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.services.macro_ingest import upsert_point

logger = logging.getLogger(__name__)

_URL = "https://www.idexonline.com/Bid_Control-home_graph"
_HTTP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
_CODE = "idex_diamond"
_FROM = date(2015, 1, 1)  # начало доступной истории у источника


def sync_idex_diamond(db: Session, from_date: date = _FROM) -> dict:
    """Полный охват от from_date (по умолчанию — вся доступная история, 2015-01-01)
    до сегодня при каждом запуске: один JSON-запрос, ~140КБ на всю историю — дешевле
    и надёжнее, чем догонять частичное окно (как Yahoo-commodities/TankerMap max)."""
    today = date.today()
    params = {"driver_id": 0, "fromDate": f"{from_date.year}-{from_date.month}-{from_date.day}",
              "toDate": f"{today.year}-{today.month}-{today.day}"}
    try:
        r = httpx.get(_URL, params=params, timeout=30, headers=_HTTP, follow_redirects=True)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("IDEX Diamond Index: источник недоступен: %s", type(e).__name__)
        return {"error": f"fetch_failed:{type(e).__name__}"}

    rows = payload.get("data") or []
    if not rows or payload.get("label") != "Total":
        logger.warning("IDEX Diamond Index: неожиданный формат ответа (label=%s, %d точек)",
                       payload.get("label"), len(rows))
        return {"error": "unexpected_format", "label": payload.get("label"), "points": len(rows)}

    saved, skipped = 0, 0
    for ts_ms, value in rows:
        try:
            d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
            val = float(value)
        except (TypeError, ValueError, OSError):
            continue
        res = upsert_point(db, _CODE, d, "level", val, unit="индекс",
                           source="IDEX Diamond Index", source_url="https://www.idexonline.com/diamond_prices_index",
                           ingested_via="idex", commit=False)
        if res in ("insert", "revise"):
            saved += 1
        else:
            skipped += 1
    db.commit()
    logger.info("IDEX Diamond Index: %d сохранено, %d без изменений (%d точек в ответе)",
                saved, skipped, len(rows))
    return {"saved": saved, "skipped": skipped, "points": len(rows)}
