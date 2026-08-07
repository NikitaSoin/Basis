---
name: compare-asset-sector-tr-gap
description: /api/market/compare-asset НЕ поддерживает отраслевые TR-тикеры (SECTOR_TR_TICKERS) — только IMOEX/RTSI/MCFTR + Fund secid, для секторных пресетов сравнения нужен доп. бэкенд-фикс
metadata:
  type: project
---

При реализации design-task 2026-07-24 (портфель: сравнение/риски) добавлены чипы
«быстро добавить отраслевой индекс» в «+Добавить сравнение» (`PortfolioViews.jsx`,
`addSectorPreset`) — по спеке должны переиспользовать `GET /api/market/compare-asset?
ticker=MEOGTR` (и т.д., см. `SECTOR_TR_TICKERS` в `app/services/moex_history.py`:
MEOGTR/MEMMTR/MEFNTR/MECNTR/METNTR/MEEUTR/MECHTR/METLTR/MEITTR/MERETR).

Обнаружено (не чинил — вне роли фронтенд-агента, `/backend` не трогаю): в
`app/api/market.py` `compare_asset_series()` при отсутствии тикера среди `Company`
идёт в `_compare_index_series()` ТОЛЬКО если `ticker in ("IMOEX","RTSI","MCFTR")`
(хардкод), иначе падает в `_compare_fund_series()` (ищет `Fund.secid`) → 404 «тикер
не найден» для всех 10 секторных TR-тикеров, хотя данные для них РЕАЛЬНО есть в
`IndexHistory` (их же читает `load_index_series()` для sector_blend в
`compute_portfolio_metrics`, `app/services/portfolio.py` ~L863-878).

**Why:** пресеты чипов на фронте уже готовы и рабочим путём переиспользуют
`compareLines`/`rebaseToMasterStart` — но клик по чипу сейчас покажет
`compareError` («индекс пока недоступен для сравнения»), а не добавит линию,
пока это не пофикшено на бэке.

**How to apply:** одна строка фикса — в `_compare_index_series`/условии
`compare_asset_series` заменить хардкод-кортеж на проверку `ticker.upper() in
SECTOR_TR_TICKER_LIST` (уже экспортируется из `moex_history.py`) ИЛИ просто
`in (*SECTOR_TR_TICKERS.values(), "IMOEX", "RTSI", "MCFTR")`. После фикса — чипы
секторов в «Сравнение» заработают без изменений на фронте.
