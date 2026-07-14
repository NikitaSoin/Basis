---
name: obs-economy-pattern
description: ObsEconomy component: hero-rate + grid8 tiles + inline detail chart + forecast table wired to real macro API
metadata:
  type: project
---

ObsEconomy (added 2026-07-04) replaces `<MacroView>` in `case 'economy'` of ObserverV2.

## Files changed
- `frontend/Basis/src/App.js` — new `ObsEconomy` function (~line 12992), `_INVERSE_SIGN` Set just before it
- `frontend/Basis/src/styles/observer-v2.css` — appended all `obs-hero-*`, `obs-grid8`, `obs-tile-*`, `obs-d-*`, `obs-dd*`, `obs-detail-*`, `obs-forecast-*`, `obs-range-pill`, `obs-legend`, `obs-tag-judgment`

## API endpoints used
- `GET /api/market/macro/rate` — hero block (key_rate value, meeting date/signal/next)
- `GET /api/market/macro` — indicator tiles (display_group: ru/world, values, change, influence_short)
- `GET /api/market/macro/{code}/series?metric=level|yoy` — line charts (hero + detail)
- `GET /api/market/macro/forecast` — prognosis table (scenarios, rows: indicator/year/value)

## Key design patterns
- Hero chart reuses existing `MacroChart` SVG component (no new deps)
- Delta semantic inversion: `_INVERSE_SIGN` Set flips color for inflation/unemployment/hh_index/key_rate (up = bad)
- Grid tiles are `<button>` elements, clicking opens detail chart inline (no modal)
- Custom dropdown (`obs-dd`) for overlay series selection — outside-click closes via `useRef` + `document.addEventListener`
- Forecast table `Факт сейчас` column: loose title-match from live indicators (first 6 chars)
- MacroView is NOT deleted — still used in company card macro tab (renderMacro ~line 5822)

**Why:** MacroView had tabs/modal — prototype wanted flat sequential layout (hero → grid → detail → forecast) matching the prototypeexact layout.
**How to apply:** When adding new indicator codes to DB, they automatically appear in the grid without component changes. Semantic inversion set may need extending for new codes.
