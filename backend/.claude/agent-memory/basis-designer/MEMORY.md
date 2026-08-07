# Basis Designer Memory

- [Bank financials field map](bank-financials-fields.md) — поля bank_pnl/bank_metrics/balance_sheet для SBER/VTBR/BSPB: именование varies (interest_income_gross vs total_interest_income), n10/n12 vs capital_adequacy
- [Sectoral blocks pattern](sectoral-blocks.md) — паттерн условных секторных блоков: GMV (finJson.gmv_mlrd) для OZON, НДПИ+миноритарий (is.expense_lines + is.minority_interest) для нефтегаза
- [NEO dark accent token gap — УСТАРЕЛО/исправлено](neo-dark-accent-token-gap.md) — проверено 2026-07-26, все accent-companion токены в .dark .cc-root уже медные
- [tw-font-mono ≠ NEO mono](tw-font-mono-not-neo-mono.md) — tw-font-mono = JetBrains Mono (классика); для NEO-чисел — .cc-num / var(--cc-mono)
- [Тарифы/Профиль на NEO, тариф реально переключается](tariffs-account-live.md) — src/account/, tierCatalog.js общий источник, квота — правило не счётчик, 3 фичи Максимума честно «Скоро»
- [Пересборка фронта: npm run build, не craco build](frontend-build-command.md) — package.json build = craco build && generate-seo-pages.js; голый craco build удаляет 264 SEO-страницы из закоммиченного build/
- [compare-asset не знает отраслевые TR-тикеры](compare-asset-sector-tr-gap.md) — /api/market/compare-asset хардкодит IMOEX/RTSI/MCFTR, для MEOGTR и т.п. 404 → нужен бэкенд-фикс для секторных пресетов «Сравнение»
- [Тёмный рельс-сайдбар — общий паттерн](dark-rail-sidebar-family.md) — obs/mkt/pf/scmp/asst-sidebar: одна и та же скоупленная палитра #12131A-триады, theme-invariant dark; бери 1:1 для новых сайдбаров
- [Контраст accent/on-accent](accent-on-accent-contrast-caveat.md) — белый текст на медном --accent в светлой теме ≈3.3:1 (ниже AA), сайт-вайд пре-существующее, не чинить точечно
- [Edit-квирк на длинном old_string](large-edit-old-string-quirk.md) — 100+ строк иногда не матчится хотя текст идентичен побайтово; дели на куски по 30-60 строк
