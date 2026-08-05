---
name: markets-tab-m5-namespace
description: the «Рынки» company-card tab (renderMarket in CompanyCardView.jsx) uses an "m5-*" CSS namespace, not "bs-*" — it is already on-canon (copper/Fraunces/IBM Plex Mono), NOT legacy
metadata:
  type: project
---

`frontend/Basis/src/company/CompanyCardView.jsx`, function `renderMarket()`
(~line 5506+), and its stylesheet `frontend/Basis/src/market/market-m5.css` use a
distinct class prefix `m5-*` (e.g. `.m5-card`, `.m5-tag-fact`, `.m5-vlead`,
`.m5-cyc`, `.m5-valbox`) instead of the `bs-*` classes from
`basis-design-system.css`.

**Why this is NOT the legacy/classic system:** `.m5-root` (top wrapper class) aliases
every `--m5-*` variable straight to the app's `tokens.css` NEO tokens
(`--accent`, `--bg-elevated`, `--text-primary`, `--success`, `--danger`, `--warning`,
`--font-mono`, `--cc-serif`, etc.) — and those NEO tokens already resolve to canon
values: `--accent:#C97A4A` (copper), `--font-mono:"IBM Plex Mono"`,
`--cc-serif:"Fraunces"`. Confirmed by reading `tokens.css` directly — this is a
pre-existing, deliberate "point the m5 palette at the app's real tokens" port
(see the file's own header comment: "точный порт макета markets-m5.html... Все
классы с префиксом m5- — нулевой риск коллизий"). It is functionally equivalent
to `--bs-*`, just a different naming convention used only within this one tab.

**How to apply:** when extending or fixing the «Рынки» tab, follow the existing
`m5-*` convention (reuse classes like `.m5-tag`/`.m5-vlead`/`.m5-valassum`/
`.m5-share-cap` where they fit) rather than introducing raw `bs-*` classes or
inline hex — both end up rendering identically, but mixing namespaces in one file
is confusing for the next editor. Don't flag `m5-*` usage here as a legacy-system
violation; it isn't one. New CSS added for this tab lives in `market-m5.css`.
