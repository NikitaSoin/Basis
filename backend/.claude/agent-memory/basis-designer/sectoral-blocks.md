---
name: sectoral-blocks
description: Паттерн условных секторных блоков в renderFinancials — рендерятся только при наличии полей в JSON
metadata:
  type: project
---

## Паттерн

Секторные блоки — функции `renderXxxBlock()`, рендерятся после основных отчётов (P&L/баланс),
до комментария аналитика. Каждая возвращает null если данных нет.

## E-commerce (OZON): GMV

Поле: `finJson.gmv_mlrd` — объект с:
- `fiscal_years`: число[] (может отличаться от meta.fiscal_years!)
- `values`: число[] (млрд ₽)
- `revenue_take_rate_pct`: число[] (precomputed — не пересчитывать)
- `note`: строка

Рендер: таблица год×строка (GMV / take rate), delta г/г через <Delta />.
Take rate delta — в п.п. (not yoy%), вывод ▲/▼ + "пп" суффикс.

## Нефтегаз (ROSN и др.): НДПИ + миноритарий

Поля:
- `is.expense_lines[].name` — ищем по regex `/НДПИ|Налоги,?\s*кроме/i`
- `is.minority_interest` — массив абс. значений
- `is.net_profit_total` — ЧП группы (знаменатель для доли меньш.)

Вычисляемые строки:
- НДПИ / Выручка, % = ndpiArr[i] / is.revenue[i] * 100
- Доля меньш. / ЧП группы, % = minority_interest[i] / abs(net_profit_total[i]) * 100

Рендер через tableSection(Database, "Отраслевые показатели", rows, true).

**How to apply:** перед добавлением нового секторного блока — проверь финансовую схему компании,
найди уникальное поле в JSON и добавь аналогичный renderXxxBlock() с проверкой на null.
