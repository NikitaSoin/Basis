---
name: portfolio-v2-sidebar
description: Portfolio page rebuilt as sidebar-shell (PortfolioV2) mirroring ObserverV2 pattern; legacy PortfolioView kept for reference
metadata:
  type: project
---

`PortfolioV2` (frontend/Basis/src/App.js, defined just before legacy `PortfolioView`,
~line 8113) replaced the old chip-tabs "Портфель" page with a dark-sidebar shell,
copying the exact structural pattern of `ObserverV2`/`observer-v2.css`
([[obs-economy-pattern]] if that exists — see `_obsRenderPanel`/`OBS_ZONES`/keep-alive
via `visitedSections` Set). New CSS file `src/styles/portfolio-v2.css` uses prefix
`.pf-*` with the same scoped `--pf-deep*` dark vars as `.obs-sidebar` (sidebar stays
dark in both light/dark theme). Route switch: `case "portfolio"` in the big render
switch now returns `<PortfolioV2 .../>` instead of `<PortfolioView .../>`.

**Why:** Task explicitly said "repeat the method already proven on Обозреватель" —
i.e. reuse the exact same architecture (dark sidebar + zones + keep-alive panels),
not invent a new one. `PortfolioView` was NOT deleted — kept below `PortfolioV2` as
legacy/rollback reference, same as `OverviewView` was kept after `ObserverV2` shipped.

**How to apply:** For any future "give page X the Обозреватель sidebar treatment"
request: (1) read `ObserverV2` + `observer-v2.css` as the exact template, (2) create
a new `<prefix>-v2.css` with scoped dark vars mirroring `.obs-sidebar`'s `--obs-deep*`,
(3) build `<PageName>V2` as a NEW component that keeps all existing data-fetching/
computed logic (copy verbatim, don't re-derive), reorganized into per-section render
functions selected by a zones config array + keep-alive Set, (4) leave the legacy
component in the file, only swap the render-switch case.

**Data-availability limits found in `PortfolioMetricsResponse`
(backend/app/schemas/portfolio.py) that forced honest stubs instead of the prototype's
mock numbers:** no per-position dividend calendar (next ex-date/amount) → "Ближайшие
выплаты" is a `pf-badge-soon` stub, not real dates. No per-position realized/
unrealized P&L, dividends-received, or commissions breakdown → kept using the existing
modal-based `EditPositionModal`/`AddPositionModal` flow instead of the prototype's
inline expandable edit-row with a P&L chip-stat breakdown. No macro/geo sensitivity
profile per company → "Факторный профиль портфеля" (ИИ-Диагноз) is a `pf-badge-soon`
stub, no fabricated ▲/▼ percentages. Custom stress-test scenario (own shock params)
is UI-only placeholder, not wired to a calc — matches CLAUDE.md's "stress-test is a
stub" status. Arbitrary "+ Добавить сравнение" (compare vs custom asset/portfolio/
formula) also a stub per the prototype's own admission it's mock-only.

Reused existing token-compliant building blocks instead of recreating the prototype's
raw inline CSS: `Card`/`Table`/`KpiTile`/`Chip`/`Badge`/`IconButton`/`Button` from
`design/primitives.jsx`; `WeightBar`/`MetricBar`/`CorrelationHeatmap`/`ImpactBar`/
`catFor` from `design/PortfolioViz.jsx`; `KeyTakeaway`/`Disclosure` from
`design/textblocks.jsx`; `AppearGroup` from `design/motion.jsx`; and the big
pre-written `MetricExplainers`/`METRIC_EXPLANATIONS` block (App.js ~7768-7940) which
already implements the prototype's "metric card with fact/estimate/judgment tag +
what/so-what/formula" pattern — didn't reinvent it.
