---
name: obs-barometer-redesign
description: Shared "barometer" design pattern (obs-baro-*/obs-inst-*) reused for both ObsGeopolitics and ObsInstitutions assessment modes; ObsMacroArticles lede/evidence restructure
metadata:
  type: project
---

2026-07-12: full redesign of the three Обозреватель "Оценка ситуации" screens per owner
feedback (macro/geo/institutions all called out as poorly designed). Files: `frontend/Basis/src/observer/ObsPanels.jsx`
(`ObsMacroArticles`, `ObsGeopolitics`, `ObsInstitutions` + new shared helpers above them),
`frontend/Basis/src/styles/observer-v2.css`.

## Key discovery: orphaned CSS from a pre-crash session
Commit f46b7e18 (2026-07-10) added ~686 lines of `obs-inst-*` CSS (hero score+verdict,
probability ladder, cluster-accordion subindices, alert rows, CRP-floor display) for a
planned Institutions redesign — but the JSX consuming it was NEVER committed (session
likely crashed before that commit landed). This matches the owner's "институты — как до
краша, но не идеал" comment. The CSS had already passed a real design/product review
(see commit message) so I reused it as-is rather than redesigning from scratch — saved a
lot of time. **Always grep for orphaned CSS blocks (`grep -rL <selector-prefix>` shows
classes with zero JSX consumers) before starting a redesign — a previous session may have
left usable, already-reviewed work.**

## Shared pattern (reusable for future "score-grid" screens)
`obs-inst-*` in observer-v2.css is now a GENERIC barometer vocabulary, not
institutions-specific despite the name (kept the name to avoid touching 686 lines of
reviewed CSS). Reused verbatim by `ObsGeopolitics` too. New shared JS helpers live in
ObsPanels.jsx right before `ObsMacroArticles`:
- `obsScoreTier(score, polarity)` — polarity `'higherBetter'` (institutions: 5=strong
  institutions) vs `'higherWorse'` (geo: 5=max risk) — same 1-5 scale, opposite meaning.
  Always verify polarity against the actual JSON before reusing (`backend/config/institutional_barometer.json`
  vs `geo_barometer.json` — check a few subindex scores against their rationale prose).
- `obsParsePct(v)` — parses "68% (62-73%)" style strings OR raw 0-1 floats.
- `obsBaroBalance(subindices, polarity)` — data-driven "what's dragging it down / what's
  relatively better" from min/max scoring subindices. Deliberately NOT hardcoded per
  company/snapshot — recomputes from whatever JSON is live.
- `ObsBaroScale` — 1-5 gauge with colored gradient direction flipped by polarity.
- `ObsBaroHero`, `ObsBaroLadder`, `ObsBaroClusters`, `ObsBaroCaveat` — the four building
  blocks. `ObsBaroClusters` groups 12-13 subindices into 4 thematic clusters
  (`INSTITUTIONS_CLUSTERS`, `GEO_CLUSTERS` consts) as native `<details>` accordions — no
  React state needed, keyboard-accessible for free. This replaced the old pattern of one
  full-width `.obs-art-card` per subindex (13 cards read like a news feed — the owner's
  main complaint), now 4 compact cluster rows that expand to reveal 2-4 subindex
  rationale blocks each.

## Geo region-agnostic fix
Owner's "почему только Россия, а Ближний Восток/АТР?" complaint was actually a UI bug:
the geo-barometer (`/api/market/geo-barometer`) is ONE score for the whole RU market
(13 subindices G1-G13, G9/G10/G11 already cover China/US/EU axes) — NOT per-region. The
region filter chips (СВО/Ближний Восток/АТР) are real and correct for the "Обзор" tab
(per-region news digest) but were staying visible+clickable in "Оценка ситуации" mode
too, implying the barometer was region-scoped when it wasn't. Fix: region chips now only
render in `mode==='overview'`; a new `.obs-baro-note` info banner explains the barometer
is market-wide when in assessment mode.

## Macro (ObsMacroArticles) signal/evidence split
No numeric score exists for macro (freeform LLM prose sections), so could not reuse the
barometer hero. Instead: `current_picture` gets its own `.obs-macro-lede-card` with
larger serif (Fraunces) text — reads as "the signal" — while `rate_outlook`/
`cb_forecast_view`/`market_sectors` render as smaller sans-serif `.obs-macro-card`
blocks with a section icon — "the evidence". Deliberately did NOT attempt to
programmatically extract a "headline sentence" from the prose (regex-splitting Russian
text on periods risks truncating mid-abbreviation/mid-number) — CSS-only size/font
differentiation is safer and was sufficient for the hierarchy fix.

**Why this approach over a full rewrite:** effort was time-boxed; reusing already-built
CSS + writing thin generic JS helpers shared across 2 of 3 screens was the highest
leverage path. Bridge/persona-specific sections from the pre-crash commit description
(e.g. "что это значит для разных типов бумаг") were deliberately skipped — they'd
require hardcoded narrative text not driven by the JSON schema, which risks going stale.
**How to apply:** if asked to extend Geo/Institutions further, add fields to the
JSON schema first rather than inventing copy in JSX.

## 2026-07-12 round 2: product-analyst-fin IA pass on top of the visual redesign
Same 3 screens, same files. This round applied a product-analyst's information-architecture
spec (reorder + new blocks) on top of the already-shipped visual language above — reused
`ObsBaroHero`/`ObsBaroLadder`/`ObsBaroClusters`/`ObsBaroCaveat`/`GEO_CLUSTERS` verbatim, did
NOT redesign.

- **`ObsHorizonChip`** (new, exported from ObsPanels.jsx, used from App.js's `ObserverV2`
  section-header switch) — small pill next to the `<h2 className="obs-sec-title">` showing
  how often the barometer/section is worth rechecking ("дни-недели" macro / "недели-месяцы"
  geo / "месяцы-годы" institutions). Section headers live in App.js, NOT in the Obs* panel
  components themselves — `obs-sec-head` wrapper is per-case in `ObserverV2.renderSection()`.
- **`ObsBaroSubRow`** extracted from inside `ObsBaroClusters`' map callback into its own
  function — reused it standalone (outside any `<details>` accordion) for a new "Внешние оси"
  card in Geo. Pattern: when a per-item JSX block needs reuse outside its original accordion
  wrapper, extract it as a named component, don't copy-paste.
- **Geo "Внешние оси" block** (owner's "а Ближний Восток и АТР?" complaint, round 2): added
  a NEW named card between `implied_market` and the full G1-G13 `ObsBaroClusters` list, pulling
  G9(Китай/Индия)/G10(США)/G11(ЕС/UK)/G13(глобальный фон/Ормуз) out of `subMap` via a
  `GEO_AXES` const and rendering each with `ObsBaroSubRow`. Deliberately duplicated with the
  existing "Геополитические оси" cluster inside the full G1-G13 list (kept both) — this
  mirrors the macro lede/evidence pattern (promoted excerpt + full detail below), not a
  contradiction.
- **Geo reorder**: sector_flags card moved to directly after the scenario/ladder card (was
  after implied_market). `baro.summary` block — checked against `barometer.label` (hero
  verdict) using real `backend/config/geo_barometer.json`: label is a short one-liner, summary
  is a much longer synthesis with specific dates/numbers/cross-refs to macro not present in
  label → kept it (not a duplicate), repositioned it between "Внешние оси" and the full
  G1-G13 list rather than removing it. **Before deleting a "summary looks duplicate" block,
  always diff it against the actual JSON, not just the JSX** — text that reads similar in
  the abstract can differ a lot in a real snapshot.
- **Macro hard-numbers tile**: `/api/market/macro` (same endpoint `ObsEconomy` already uses)
  DOES have structured numeric fields (`key_rate`, `inflation` yoy, `gdp` yoy, `budget_balance`
  — see `backend/config/macro_indicators.json` for the canonical code list) even though the
  interpretation endpoint (`/api/market/macro/interpretation`) is pure LLM prose. Added a
  4-tile `.obs-grid8`/`.obs-tile` strip (reused ObsEconomy's exact CSS classes, non-interactive
  divs not buttons) between the `current_picture` lede and the prose evidence cards. Also added
  a one-line FACT headline ("Ключевая ставка X% · сигнал ЦБ: ...") sourced from
  `/api/market/macro/rate` (`key_rate` + `meeting.signal`) — this is real DB data, NOT an
  LLM-prose regex-extraction, so it doesn't hit the "risky to parse Russian sentences" problem
  noted in the entry above; tagged with `.obs-tag-fact`.
- **Macro prose shortening**: did NOT truncate/rewrite the LLM-generated `rate_outlook`/
  `cb_forecast_view`/`market_sectors` text (that's a backend prompt-length decision, out of
  scope for a frontend pass) — instead wrapped the three cards in a `<details className="obs-macro-evidence">`
  accordion, closed by default, so the screen READS shorter without losing any content one
  click away.
- **Institutions CRP-floor "co-signal"**: added a `coSignal` prop to `ObsBaroHero` (renders
  inside `.obs-inst-hero-score-row`, right next to the big score number) — used only by
  Institutions to show the CRP-floor value inline with the hero score. The full rationale
  card (`crp_floor_rationale` + `<details>` "как посчитан") stays where it already was,
  directly after the hero — that position was ALREADY correct pre-this-session (a product
  spec assumption that it was "buried mid-screen" turned out to be wrong when checked against
  the live JSX; always verify a product-analyst's "current state" claim against the actual
  file before moving things around).
- Region chips in Geo assessment mode: re-verified still correctly gated to
  `mode === 'overview'` only (from round 1) — no regression, nothing to fix.
