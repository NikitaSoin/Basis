---
name: macroeconomics-tab-component
description: MacroeconomicsTab.jsx (company card tab) — six-block layout from macro_tab.json; 2026-09-16 doработка added the scenario "ladder", base-bridge callout, two-layer lead/details/takeaway text, factor strength bar; Playwright route-order gotcha that cost a full debugging round
metadata:
  type: project
---

Base build 2026-09-16 (morning): `frontend/Basis/src/company/MacroeconomicsTab.jsx` +
`frontend/Basis/src/styles/macroeconomics-tab.css`, wired into `CompanyCardView.jsx`'s
`renderMacro()` as `if (macroTab) return <MacroeconomicsTab .../>`. Data:
`GET /api/companies/by-ticker/{T}/macro-tab` → `backend/companies/<T>/macro_tab.json` (+ `calc`
merged from `macro_scenarios.json`). Spec: `docs/Описание_вкладки_макроэкономика.md` (six fixed
blocks) + `docs/macro_model_contract_v1.md` (field shapes, §7/7.1).

**Same-day rewrite (2026-09-16, afternoon) per
`docs/macro_tab_product_recommendations_2026-09-16.md`** — this is the current state of the
component, superseding the original layout described below where they conflict. Kept from the
original build without change: pure `--bs-deep-*` dark wiring technique, the 3-color epistemic
tag mapping, `.app-shell` scroll-container screenshot technique — see those sections below.

## What changed in the 16.09 doработка (product recommendations B/C/D/E)
- **Blocks 1/2/5 → two-layer text.** `now.lead` (bold, big) + `now.text` (full) +
  `now.details` (under a `<details>` "Подробнее") + `now.takeaway` ("Итог для инвестора" line).
  Same lead/details/takeaway pattern in `FactorCard` (block 2, `f.details`+`f.strength_basis`
  moved under "Подробнее") and `PriceLinkBlock` (block 5, `priceLink.takeaway`). None of the 10
  numeric-pilot files had `lead`/`details`/`takeaway` populated as of 2026-09-16 — fallback is
  `firstSentence(now.text)` (regex-split on first `.`/`!`/`?`/`…`), which necessarily duplicates
  the opening sentence until the writer fills `lead` with real distinct copy. This is the
  expected/instructed transitional cost, not a bug — don't "fix" it by trying to strip the
  duplicate sentence out of `now.text` (fragile string surgery, high risk of mangling grammar).
- **Block 2 factor cards got a decorative strength bar** (`FactorStrengthBar`): centered track,
  fills right (green) for `sign:"помогает"`, left (red) for `"мешает"`, nothing for `"двояко"`.
  Purely `aria-hidden` reinforcement of the existing dots+word — never the only signal.
- **Block 4 scenarios: 2×2 card grid → "ladder" (`.mt-ladder`).** One shared-frame list of
  native `<details>` rows (`LadderRow`), 2026 row (`normalizeC2026`) on top, then the 4 scenario
  rows (`normalizeRow`) **sorted by actual outcome for the company, not by the CB's scenario
  label**: `scenarioSortScore()` prefers real `net_profit.pct_base` (continuous) → derived/
  explicit `verdict` (±1000 tiebreak, JS sort is stable so ties keep source order) → canonical
  `risk,proinflation,base,disinflation` rank only as last-resort fallback (e.g. a
  qualitative file with zero signal at all). **This is a deliberate interpretation, not
  arbitrary**: LKOH's own "Рисковый" scenario has the HIGHEST profit (+49%, ruble devaluation
  outweighs the risk premium for an exporter) — sorting by the scenario's macro-risk *label*
  would put it at the "worse" end, which is backwards for this company and contradicts the
  brief's own worked example ("ЛУКОЙЛ Рисковый: ▲ выше"). Verified live: LKOH numeric rows
  sorted proinflation(+3%) → base(+8%) → disinflation(+18%) → risk(+49%); GAZP qualitative
  (verdict-only, no numbers) sorted risk(мешает) → base/disinflation/proinflation (tied
  помогает, kept source order).
  - Row summary is a CSS grid (`name | conditions | verdict | number | chevron`); body
    (revenue-secondary, explanation, dominant_factor, flags, on-click range bar reusing the old
    `RangeBar`/`computeProfitDomain`) only renders if there's something to show — rows with
    nothing (`!hasBody`) render as a plain non-interactive flat div, not an empty disclosure.
  - Main number rounding is `fmtStep()`: nearest 1, or nearest 10 only if `|base| > 1000` — this
    is the literal rule given in-task, and it's narrower than the recommendations doc's own
    illustrative "≈410 (320–540)" example (409/318/541 rounded to nearest 10 despite being
    <1000) — deliberately followed the explicit numeric rule over the doc's loose prose example.
  - Percent-hiding: `pctThin` (blanket, computed once from `|net_profit_scenario_base| < 5% ×
    revenue`) OR the row's own `net_profit.pct_hidden === true` (real field, confirmed live in
    UNAC's data with value `true` on every row) → hides ONLY the profit delta-percent, not
    revenue's (revenue rarely has the same thin-base distortion; scoped separately via
    `rev.pct_hidden`).
  - `headline` field (`scenarios.rows[].headline`) is contractually **"▲/≈/▼ слово — причина"
    as ONE string** (§7.1) — but the row already shows a colored `VerdictChip` pill with the
    same glyph+word right above it. Showing the raw headline duplicated it ("▼ мешает" chip,
    then "▼ мешает — дорогой долг…" text right below). Fixed with `headlineReason()`: strips a
    leading `/^[▲≈▼]\s*(помогает|мешает|примерно так же)\s*[—-]\s*/i` match, falls back to the
    raw string if it doesn't match (defensive — confirmed live that the writer changed headline
    phrasing TWICE during this session, once with the prefix, once without, component handled
    both without changes).
- **Base-bridge callout (`BaseBridgeCallout`, new, sits above the ladder).** If
  `scenarios.base_fact.net_profit_scenario_base` differs from `.net_profit` by >0.5, renders a
  clickable one-liner "База для сценариев ≈380 млрд ₽ — не 93 из «Финансов» и не −1 064 из
  отчёта" + "почему" that expands to the bridge steps (via shared `resolveBridge()`/
  `BridgeBody()`, factored out of the old `HowComputedBlock`-only bridge renderer so both
  locations parse the same 3 historically-observed shapes — object rows / string array /
  single prose note). Else renders a short "Точка отсчёта — 2025 год: …" line. **Bug found and
  fixed live**: `ScenariosBlock` computes `bf = obj(scn.base_fact) || {}` for OTHER call sites
  (`refValue`/`refYear` props must never be `undefined.x`), but passing that same
  already-`|| {}`-coerced `bf` into `BaseBridgeCallout` defeated its `if (!bf) return null`
  guard — an empty object is truthy, so it fell through to the short-form branch and rendered
  **"Точка отсчёта — предыдущий год: выручка — млрд ₽, чистая прибыль — млрд ₽"** (all
  em-dashes) for GAZP, whose `scenarios.base_fact` is genuinely `null` (no financial model yet).
  This is exactly the "прочерки" defect the constitution calls out by name. Fix: guard on
  **content**, not object-truthiness — `if (!bf || (!isNum(bf.revenue) && !isNum(bf.net_profit)))
  return null;`. General lesson: an `obj(x) || {}` fallback that's safe for property-access call
  sites is NOT safe to hand to a child component's own `if (!x) return null` guard — truthiness
  checks on a coalesced empty object don't detect "no data."
- **Block 5 price-link mechanisms**: was 3 numbered steps each showing title + universal theory
  (`m.text`) + company-specific line (`m.company`) inline; now only title + `m.company` show by
  default, all 3 `m.text` theory paragraphs move into ONE shared `<details>` "Как это работает
  вообще" below the steps (was: implicit per-mechanism theory, now: one combined disclosure).
  `price_link.number` re-skinned from a big serif `.mt-estimate-callout` into a smaller sans
  `.mt-signal-chip` ("chip", per brief wording) — same estimate-blue soft background, just less
  visual weight. The pre-existing `data-n={i===2 && mechs.length===3 ? "1+2" : ...}` hack (3rd
  step visually labeled "1+2" because it's literally the union of mechanisms 1 and 2 in every
  company's data) was preserved unchanged — confirmed still fires correctly post-rewrite.
- **`staleness` callout reheaded** "Поправка на сегодня" (was an inline `<b>` lead-in reading
  "Что изменилось с даты сценариев.") — same position (above the ladder), same
  always-expanded `.bs-callout` (never wrapped in `<details>`), just a proper heading line now
  (`.mt-callout-heading`, reused generically, not staleness-specific).
- Full block-order inside `ScenariosBlock`: source line → held_at_base_note callout → staleness
  callout ("Поправка на сегодня") → `BaseBridgeCallout` → interim_fact line → legend line
  (click-hint for numeric, epistemic-disclaimer for qualitative) → `.mt-ladder` (2026 row + 4
  sorted scenario rows) → `numbers_note` (qualitative-only) → `scenarios.takeaway` → "Оговорки и
  допущения" details (always last).

## Playwright route-registration order — cost a full debugging round, general lesson
**Playwright runs the MOST RECENTLY REGISTERED matching `page.route()` handler FIRST**, not the
most specific one and not registration order. Registering a broad catch-all
(`page.route(/.*\/api\/.*/, ...)`) AFTER specific mocks
(`page.route("**/api/companies", ...)`) means the catch-all — being newer — intercepts and
`fulfill()`s EVERY request itself, and the specific handlers never run at all (no error, no
warning — the specific route handlers are just silently dead code). Symptom looked exactly like
a real app bug: "Компания «LKOH» не найдена в базе" even though the mocked company list was
correct — the list fetch itself was 404ing via the catch-all. Confirmed via
`page.on("response", ...)` logging showing `RESP: 404 .../api/companies` despite a specific
mock being registered for that exact URL. **Fix: register the broad catch-all FIRST, specific
overrides AFTER** (last-registered = highest priority, so overrides must come last). This
inverts the "intuitive" registration order and is worth checking first, before assuming a
mocked component itself is broken, any time a Playwright-mocked page shows a not-found/empty
state you don't expect. See also `[[playwright-maplibre-verification]]` for other route-mocking
gotchas (CORS header on `fulfill`, mock every gating fetch) — this ordering issue is a distinct,
earlier-in-the-pipeline failure mode from those.

## `build/` is now gitignored (2026-08-03+) — the old BUILD_PATH-scratch caution is obsolete
`[[craco-build-verification-safety]]` and `[[concurrent-session-build-race]]` (and the
`frontend/Basis`-local `craco-build-touches-real-build-dir.md`) all documented an elaborate
`BUILD_PATH=<scratch>` workaround because a bare `craco build` used to wipe ~1580 *committed*
SEO pages in `frontend/Basis/build/`, and concurrent sessions could race on that same git-tracked
directory. As of the 2026-08-03 deploy-model change (`frontend/Basis/build/` added to
`.gitignore`, confirmed via `git ls-files frontend/Basis/build` → 0 files), **none of that risk
exists anymore**: a full `npm run build` (bundle + all SEO generators) against the real
`build/` directory is now a purely local, non-git-tracked artifact — safe to run directly,
no scratch redirection needed, no race with other sessions' commits possible. Ran the full
`npm run build` twice in one session here with zero issue. Still true and unaffected: bare
`craco build` alone (without the SEO generator chain) leaves `build/` without SEO pages — but
since nothing commits that directory anymore, the actual cost of doing that locally is just an
incomplete local verification, not a lost deploy artifact. Prefer the full `npm run build` per
CLAUDE.md's own documented smoke-test command; it takes noticeably longer (SEO generators fetch
live snapshots from the production API) but is the actually-correct dress rehearsal.

## Live data changed under me mid-session — confirms the architecture, not a bug
`backend/companies/GAZP/macro_tab.json` went from ALL of `now`/`drivers`/`peers`/`price_link`/
`how_computed`/`staleness` being `null` (true qualitative skeleton, matches the brief's
description) to fully populated — TWICE, with different `verdict`/`headline` wording each
time — during the ~2 hours of this session, because a parallel writer-agent session was
actively filling it in at the same time (expected per CLAUDE.md's "несколько сессий — норма").
Confirms in practice, not just in theory: (1) always read the CURRENT on-disk file right before
screenshotting, don't trust an earlier read/memory of "what's null"; (2) the component's
"render only what's present, nothing crashes on partial/absent blocks" design is load-bearing,
not defensive-for-its-own-sake — it got exercised for real, unplanned, and held up; (3) the
`headlineReason()` prefix-strip above specifically survived the writer changing whether the
prefix was even present, which is exactly the kind of upstream-format churn this pattern needs
to tolerate.

---

## Original build notes (2026-09-16 morning, still accurate)

Built against LKOH/MGNT/SBER as named examples but the pilot had ALREADY grown to 10 tickers
(+ FEES/MTSS/NLMK/PHOR/SMLT/UNAC/YDEX) by the time this landed. **By the afternoon rewrite, the
pilot had grown again to 35 companies total, of which only the same original 10 are the full
numeric variant — the other 25 are `scenarios.variant:"qualitative"` skeletons like GAZP.
Qualitative is the MAJORITY case (25/35), not an edge case** — always design and test against
it first-class, not as an afterthought fallback path.

### Pure `--bs-*` dark-theme wiring, no hex, no legacy `--cc-*`
`basis-design-system.css` ships `--bs-deep-*` as a fixed dark palette for `.bs-deep-card`
only — it explicitly does NOT switch under `.dark` (see its own header comment). Reused the
exact technique already in `styles/stress-test.css` (its `--st-*` projection, light values
by default + full override under `.dark`), but instead of inventing new dark hex values,
pointed the dark branch straight at the ALREADY-SHIPPED `--bs-deep-*` family:
```css
.macro-tab-v2 { --mt-surface: var(--bs-surface-2); --mt-ink: var(--bs-ink); ... }
.dark .macro-tab-v2, [data-theme="dark"] .macro-tab-v2 {
  --mt-surface: var(--bs-deep-2); --mt-ink: var(--bs-deep-ink); ...
}
.dark .macro-tab-v2 .bs-card, [data-theme="dark"] .macro-tab-v2 .bs-card {
  background: var(--mt-surface); border-color: var(--mt-line);
}
```
Zero hardcoded hex anywhere. `.bs-card` itself stays untouched globally — the dark override
is scoped under `.macro-tab-v2` only. New elements living INSIDE the always-dark
`.bs-deep-card` (block 1's `now.details`/`now.takeaway`) must be colored directly with
`--bs-deep-*` tokens, NOT the `--mt-*` projection — that card doesn't follow site theme, so its
children shouldn't either. Needed 2-class specificity (`.macro-tab-v2 .mt-now .mt-details`) to
reliably outrank the generic `.mt-details`/`.bs-deep-card p` rules regardless of CSS source
order — cheaper than reasoning about import order between `basis-design-system.css` and this
file.

### Five epistemic labels → reused only THREE canon chip colors
Spec's five number-labels (из источника / из структуры / оценка / прогноз / разовый) map
onto canon's three chip colors, not five new hues: fact-gray for из источника+из структуры,
estimate-blue for оценка+прогноз, judgment-copper for разовый+суждение. The label TEXT itself
still shows the precise distinction; only the color bucket is 3-way. Deliberate, to stay within
"2-3 accents per block" dosing and not invent new tag colors.

### Real schema variance across the pilot (defend against all of it)
- `how_computed.base_values.net_profit` is NOT universal — some tickers only have
  `net_profit_reported`/`net_profit_adjusted`(/`net_profit_base`); fall back
  `net_profit ?? net_profit_adjusted ?? net_profit_reported` or the row silently vanishes.
- "Мост к устойчивой базе прибыли" (`base_bridge`) appears in THREE different shapes: array of
  `{step,amount,label}` objects (LKOH/FEES), array of plain pre-formatted STRINGS one level up
  at `how_computed.base_bridge` instead of `base_values.base_bridge` (UNAC), or a single prose
  paragraph `base_values.bridge_note` (SMLT/YDEX). `resolveBridge(bv, hc)` centralizes all
  three; `typeof bridge.rows[0] === "object"` distinguishes rows-of-objects from
  rows-of-strings.
- The "this is comparative statics, not a growth forecast" caveat sentence exists under FOUR
  different field names, one file each: `scenarios.framing`, `.note`, `.reading_note`,
  `.scope_note` — take the first non-null of all four.
- `scenarios.base_fact` can be entirely `null` (not just missing sub-fields) — see the
  BaseBridgeCallout bug above; anywhere `scn.base_fact` gets read, check for `null` explicitly,
  don't assume "object present but some fields absent" is the only degraded state.
- SBER's `base_fact.note` explicitly states "мост между ними не нужен" (no one-off items in
  2025) — the non-bridge short-form branch isn't just a fallback for missing data, it's the
  CORRECT rendering for companies with a clean base too; don't treat it as second-class.
- Before trusting a memory-cited field path/shape on a NEW ticker, re-run a key-diff (walk
  `glob('backend/companies/*/macro_tab.json')`, dump union-minus-intersection of keys) — this
  pilot's schema visibly hadn't converged as of 2026-09-16 and moved twice more within one
  session (see "Live data changed under me" above).

### Verification technique — `.app-shell` is the real scroll container, not window/body
`page.screenshot(full_page=True)` and `locator(".macro-tab-v2").screenshot()` BOTH silently
fail on this app: `full_page` only captures one viewport (document/body isn't what scrolls),
and the element screenshot produces a tall image with real content only at the very top and
a duplicated fragment at the very bottom with a huge blank gap in between. Fix: manually
`scroller.evaluate("(el,y) => el.scrollTo(0,y)")` on `page.locator(".app-shell")` in
~900-1200px steps, plain bounded `page.screenshot()` (no `full_page`) at each step. Also
dismiss the "Аналитика посещений" cookie-consent banner (`page.get_by_text("Отклонить").click()`)
before any capture.

Fast route to a live component render without a backend: mock only
`GET /api/companies` (list, resolves the `company` object) and
`GET /api/companies/by-ticker/{T}/macro-tab` (real fixture JSON straight off disk); catch-all
404 everything else under `/api/` — **remember the route-order gotcha above: register the
catch-all FIRST, then the specific overrides**. Deep-link URL:
`http://host/?company=<TICKER>&tab=macro` (query-param form — works directly on `/`, no SEO-slug
static routing needed). `python3 -m playwright` (pip-installed) has cached chromium already —
no `npm install playwright` needed. Serving the REAL `build/` output via
`python3 -m http.server <port>` (from inside `build/`) after a full `npm run build` is a good,
simple static server for this — no SPA-fallback routing needed since the deep-link form hits `/`
directly, not a sub-path.
