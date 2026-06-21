# Basis Neo-Institutional Research System
## Company Card — Developer Implementation Specification

**Status:** normative · **Scope:** Company Card route only · **Themes:** light (`:root`) + dark (`.dark`)
**Reference prototypes:** `redesign/direction-a-hybrid.html` (dark), `redesign/direction-a-light.html` (light)

Two themes in one visual logic:
- **Dark — “Basis Neo-Institutional Command Center”**
- **Light — “Basis Light Institutional Research Desk”**

Structure, layout, typography, spacing, and component anatomy are **identical across themes**. Only color tokens (and a few surface-fill values) differ. Every component references `var(--cc-*)`; theme switching is token-only via a `data-theme` / `.dark` class on the route wrapper.

> Product rule: this is decision-support, never advice. No buy/sell language, no broker UX, no trading signals. Preserve the fact / estimate / judgment epistemics and ▲/▼ semantic deltas.

---

## 1. Design-system name

**Basis Neo-Institutional Research System** — the unified system covering both the dark Command Center and the light Research Desk surfaces of the Company Card.

---

## 2. CSS variables (tokens)

Add a scoped namespace to `src/styles/tokens.css`. Define the **light** set on `:root` (the product default convention) and the **dark** overrides on `.dark`. Scope everything under the Company Card wrapper class `.cc-root` so the rest of the app is untouched.

```css
/* src/styles/tokens.css — Basis Neo-Institutional Research System */

/* ============ LIGHT — “Research Desk” (default) ============ */
.cc-root, .cc-root:root {
  --cc-bg:            #F6F3EC;   /* warm research paper */
  --cc-bg-2:          #EFEBE1;   /* secondary background */
  --cc-panel:         #FFFFFF;   /* panel / tile */
  --cc-panel-2:       #FBF9F4;   /* elevated / nested cell */
  --cc-line:          rgba(20,18,14,0.10);  /* border */
  --cc-line-2:        rgba(20,18,14,0.18);  /* strong border */
  --cc-ink:           #16130E;   /* text primary (warm near-black) */
  --cc-ink-2:         #544E44;   /* text secondary */
  --cc-ink-3:         #857D6F;   /* text muted */
  --cc-accent:        #1F3FC4;   /* institutional cobalt */
  --cc-accent-hover:  #18308F;   /* accent hover (darker) */
  --cc-accent-2:      #23379C;   /* accent text / emphasis */
  --cc-accent-soft:   rgba(31,63,196,0.08);
  --cc-amber:         #9A5B12;   /* warning / caution */
  --cc-amber-soft:    rgba(154,91,18,0.10);
  --cc-success:       #15803D;
  --cc-danger:        #B23052;
  --cc-violet:        #6D28D9;   /* insight / scenario */
  --cc-info:          #0A5E8A;   /* estimate */
  --cc-chart-grid:    rgba(20,18,14,0.06);  /* chart gridlines */
  --cc-hero-texture:  rgba(20,18,14,0.05);  /* hero grid lines */
  --cc-hero-glow:     rgba(31,63,196,0.07); /* hero radial glow */
}

/* ============ DARK — “Command Center” ============ */
.cc-root.dark, .dark .cc-root {
  --cc-bg:            #0B0E13;   /* graphite base */
  --cc-bg-2:          #10141B;
  --cc-panel:         #151922;
  --cc-panel-2:       #181D27;
  --cc-line:          rgba(255,255,255,0.07);
  --cc-line-2:        rgba(255,255,255,0.12);
  --cc-ink:           #ECEFF5;
  --cc-ink-2:         #A2ABBC;
  --cc-ink-3:         #717A89;
  --cc-accent:        #5B7CFF;   /* = Basis dark --accent (#5B79FF) */
  --cc-accent-hover:  #7088F2;
  --cc-accent-2:      #93A8F5;   /* accent text on dark */
  --cc-accent-soft:   rgba(91,124,255,0.13);
  --cc-amber:         #E0A24A;
  --cc-amber-soft:    rgba(224,162,74,0.12);
  --cc-success:       #3FB984;
  --cc-danger:        #E5708A;
  --cc-violet:        #A78BFA;
  --cc-info:          #5FB3E6;
  --cc-chart-grid:    rgba(255,255,255,0.07);
  --cc-hero-texture:  rgba(255,255,255,0.07);
  --cc-hero-glow:     rgba(91,124,255,0.14);
}
```

**Epistemic mapping** (the analytical backbone — both themes):

| Level | Token | Meaning |
|---|---|---|
| Факт (fact) | `--cc-ink-2` | sourced |
| Оценка (estimate) | `--cc-info` | model-based |
| Суждение (judgment) | `--cc-accent` | interpretation |
| Сценарий (scenario) | `--cc-violet` | conditional |

**Semantic rule:** `--cc-success` / `--cc-danger` only ever appear next to a ▲/▼/▬ glyph (never as decoration).

---

## 3. Typography

```css
--cc-serif: "Source Serif 4", Georgia, "Times New Roman", serif;
--cc-sans:  "Inter", system-ui, sans-serif;
--cc-mono:  "JetBrains Mono", ui-monospace, monospace;
```

| Role | Family | Size / Weight | Tracking · Line-height |
|---|---|---|---|
| H1 — hero company name | serif | 50px / 600 | −0.018em · 1.02 |
| H2 — section heading | serif | 27px / 600 | −0.015em · 1.1 |
| H3 — tile heading | serif | 19px / 600 | −0.01em · 1.3 |
| Exec panel title | serif | 22px / 600 | −0.01em |
| Lead / thesis | serif | 21px / 400 | — · 1.5 |
| Reading copy (lede) | serif | 16.5px / 400 | — · 1.72 (max 66ch) |
| Insight line | serif | 17px / 400 | — · 1.55 |
| Body / UI default | sans | 14px / 400–500 | — · 1.5 |
| Label / eyebrow | sans | 11px / 600 | 0.14em · UPPERCASE |
| Caption / meta | sans·mono | 11–13px | — |
| Price (hero) | mono | 52px / 500 | −0.02em · 1 |
| Metric value | mono | 30px / 500 | −0.02em |
| Table / figure | mono | 13–14px | tabular |

**Line heights:** `--lh-tight:1.1` · `--lh-body:1.6` · `--lh-read:1.72`.
**Letter spacing:** display `−0.018em` · heading `−0.015em` · eyebrow `0.14em`.

**Mono / tabular rule:** every number, ticker, delta, percentage, multiple, and figure uses `--cc-mono` with `font-variant-numeric: tabular-nums lining-nums`. ru-RU formatting (comma decimal, narrow-nbsp thousands, nbsp before unit).

**Serif usage rule:** serif is for editorial authority — hero name, section/tile/exec titles, lead & thesis, reading prose, insights, scenario labels. **Never** serif for: eyebrows/labels, nav, buttons, chips, or numbers (those are sans or mono).

---

## 4. Layout

| Token | Value |
|---|---|
| Max content width | `1340px` (centered, `--cc-page-x: 32px` gutters; 18px ≤720) |
| Top nav height | `62px` (sticky, `top:0`) |
| Tab nav height | `~49px` (sticky, `top:62px`) |
| Hero | content-driven, padding `40px 0 44px` (full-bleed dark/paper, inner wrap) |
| Main grid | `grid-template-columns: minmax(0,1fr) 332px; gap: 30px; align-items:start` |
| Main content column | `minmax(0,1fr)` (fluid, `min-width:0`) |
| Right rail width | `332px` (sticky, `top:118px`, `align-self:start`) |
| Vertical rhythm (tile gap) | `22px` between stacked tiles |
| Card radius | `--cc-r-lg:14px` (panels) · `--cc-r:12px` (metrics) · `--cc-r-sm:8px` (chips/buttons) · pill `9999px` |
| Card padding | `24px 26px` (tiles) · `15–16px` (metric/cells) |
| Elevation | single soft shadow `0 1px 2px rgba(0,0,0,.28)` + `--cc-line` border (no glow) |
| Focus ring | `0 0 0 3px var(--cc-accent-soft)` |

Stacking order (top→down): glass top nav → full-bleed hero → sticky tab bar → two-column body (`.cc-layout`). Each analytical section carries an `id` matching its tab key for scroll-spy.

---

## 5. Components

For each: **purpose · visual · props · states · theme behavior**. All consume `var(--cc-*)`; theme behavior is identical unless noted (= tokens flip).

### MarketTopNav
- **Purpose:** global product nav (Рынок · Обозреватель · Портфель · Скрининг · Тарифы · Профиль).
- **Visual:** sticky 62px glass bar (`backdrop-filter: blur(14px)` over `--cc-bg` tint); brand mark + “Basis”; right-aligned search pill.
- **Props:** `active: string`, `items: string[]`, `onNavigate(key)`.
- **States:** idle (`--cc-ink-2`) · hover (`--cc-ink` + faint fill) · active (`--cc-ink`, 600). Company Card sets `active="Рынок"`.
- **Theme:** glass tint `rgba(11,14,19,.8)` dark / `rgba(246,243,236,.84)` light.

### NeoCompanyHero
- **Purpose:** the powerful first screen / command stage.
- **Visual:** full-bleed surface with three calm decorative layers — radial glow (`--cc-hero-glow`, ≤.14 opacity), masked grid texture (`--cc-hero-texture`, 66px), low-opacity decorative price line. Three content rows: identity+price, stats, thesis/risk/CTAs.
- **Props:** `company`, `quote`, `analysis`, `onWatch()`, `onCheckIdea()`.
- **States:** static (no entrance loops); respects `prefers-reduced-motion`.
- **Theme:** dark = graphite stage; light = warm paper. Glow/texture intensity re-tuned per theme (lower on light).

### CompanyIdentityBlock
- **Purpose:** identify the instrument.
- **Visual:** 60px logo tile (radius 10; deep-navy `#14224E`/white serif monogram on light, `--cc-panel-2` on dark) + serif name (H1) + mono meta row (ticker chip · exchange · sector · session dot).
- **Props:** `name, ticker, exchange, sector, logoUrl, marketStatus`.
- **States:** session dot — open (`--cc-success`) / closed (`--cc-ink-3`).
- **Theme:** tokens flip.

### PricePanel
- **Purpose:** live price + daily move + cap/updated.
- **Visual:** mono 52px price + currency; `Delta` (▲/▼ + abs ₽ + “за день”); eyebrow stats Капитализация · Обновлено · Текущий тон (amber pill).
- **Props:** `last, currency, changePct, changeAbs, marketCap, asOf, tone`.
- **States:** up/down/flat color via `Delta`; tone pill maps tone→amber.
- **Theme:** tokens flip.

### MetricStrip
- **Purpose:** 7 headline KPIs (Выручка · EBITDA margin · Net debt/EBITDA · FCF · Дивдоходность · EV/EBITDA · Потенциал к справ. ст.).
- **Visual:** `grid repeat(4,1fr) gap 13px` (wraps 4+3); each = flat `--cc-panel` card, radius 12, FEJ tag top-right, eyebrow caption, mono 30px value + unit, `Delta` + sparkline.
- **Props:** `metrics: [{ caption, value, unit, delta, level, spark[] }]`.
- **States:** hover deepens border to `--cc-line-2` (no lift).
- **Theme:** tokens flip; sparkline stroke = sign color.

### ResearchTabs
- **Purpose:** section navigation (Обзор · Бизнес-модель · Финансы и оценка · Корпоративное управление · Рынки · Макро · Геополитика).
- **Visual:** sticky glass bar `top:62px`; underline-on-active (`--cc-accent`), horizontal scroll on overflow.
- **Props:** `tabs:[{id,label}]`, `activeId`, `onSelect(id)`.
- **States:** idle/hover/active; **scroll-spy** — IntersectionObserver (`rootMargin:-130px 0 -70% 0`) sets active; click smooth-scrolls to section (offset −120px).
- **Theme:** glass tint per theme.

### ExecutiveIntelligencePanel
- **Purpose:** “Что важно сейчас” — top briefing.
- **Visual:** panel with 2px accent left edge; serif title + tone pill; 3–5 numbered serif insights each with FEJ tag; 3-cell footer grid — Главный риск (amber cell) · Что уже в цене · Что изменит вывод; foot = ConfidenceStatus + “Не является инвестиционной рекомендацией”.
- **Props:** `insights:[{text,level}], mainRisk, pricedIn, whatChanges, tone, confidence, updated`.
- **States:** static.
- **Theme:** tokens flip.

### DecisionSupportRail
- **Purpose:** sticky right rail — decision support, not advice.
- **Visual:** single card, hairline-separated blocks: tone strip (amber) → Ключевые риски (top 4 + severity dots) → Что отслеживать (checklist) → Источники (SourceStatus) → Уверенность (ConfidenceStatus) → CTAs (Проверить идею primary, Сценарный анализ secondary) → disclaimer.
- **Props:** `tone, risks[], monitor[], sourcesCount, confidence, onCheckIdea, onScenarios`.
- **States:** sticky `top:118px`; collapses into flow ≤1080px (moves above content).
- **Theme:** tokens flip.

### RiskStack
- **Purpose:** the typed risk register (Сырьевой, Санкционный, Валютный, Дивидендный, Оценки, Долговая нагрузка, Налоговый, Управления).
- **Visual:** 2-col grid of risk cards: name + RiskSeverityBar (5 dots) + text + meta (Горизонт + ConfidenceStatus).
- **Props:** `risks:[{type,severity(1–5),confidence,horizon,text}]`.
- **States:** static (optional hover border).
- **Theme:** tokens flip.

### RiskSeverityBar
- **Purpose:** ordinal severity encoding.
- **Visual:** 5 small squares; filled steps colored 1–2 `--cc-ink-2`, 3 `--cc-amber`, 4–5 `--cc-danger`. Also a horizontal **spectrum** variant: gradient track (`linear-gradient(90deg,#C9CCD4,--cc-amber,--cc-danger)` light / `#3C4760→amber→danger` dark) with plotted dots.
- **Props:** `severity:1–5`, `variant:"dots"|"spectrum"`, `items[]` (spectrum).
- **States:** static.
- **Theme:** off-track color flips (`rgba(0,0,0,.12)` light / `--cc-line-2` dark).

### AnalystTile
- **Purpose:** wrapper for every analytical section (Бизнес-модель, Финансы и оценка, Управление, Рынки, Риски, etc.).
- **Visual:** section header (mono number + serif H2 + FEJ tag) above a flat `--cc-panel` panel (radius 14, padding 24/26). Body holds lede (serif, 66ch), DataTable, KeyTakeaway, Callout as needed.
- **Props:** `number, title, level, id, children`.
- **States:** static; `id` enables scroll-spy.
- **Theme:** tokens flip.

### MacroTransmissionFlow
- **Purpose:** signature chain — Фактор → Канал → Влияние на бизнес → P&L/FCF/баланс → Инвест-вывод.
- **Visual:** vertical numbered rail; 34px circular nodes + connector line; serif step text; last node filled `--cc-accent` (white index), its text `--cc-accent-2`/600. Header: factor title + “Макро” kind tag (`--cc-accent-soft`) + ConfidenceStatus.
- **Props:** `title, steps:[string|{label,text}], confidence, kind:"macro"`.
- **States:** static. Factors: key rate, inflation, ruble, oil price.
- **Theme:** tokens flip; node bg `--cc-panel-2`.

### GeoTransmissionFlow
- **Purpose:** same chain, geopolitical factors (sanctions, tech dependency, logistics, export).
- **Visual:** identical to MacroTransmissionFlow but kind tag “Гео” uses `--cc-violet` family.
- **Props:** `…kind:"geo"`.
- **States/Theme:** as above. (Implement as one component with `kind` prop = restyled existing `MacroTransmissionCard`.)

### ScenarioPanel
- **Purpose:** Base / Bull / Bear / Stress comparison.
- **Visual:** 2×2 grid; each card has a top color bar (base `--cc-accent`, bull `--cc-success`, bear `--cc-danger`, stress danger→maroon gradient), serif label + probability chip, assumptions, **diverging impact bars** (Выручка/Маржа/FCF/Оценка from a center axis, +right `--cc-success` / −left `--cc-danger`, signed mono value), and two notes (Что должно произойти / Что опровергнет — amber).
- **Props:** `scenarios:[{key,label,prob,assumptions,revenue,margin,fcf,valuation,must,invalidate}]`.
- **States:** static (optionally tabbed on mobile).
- **Theme:** track fills `rgba(0,0,0,.06)` light / `rgba(255,255,255,.05)` dark.

### EvidencePanel
- **Purpose:** sources + limitations (evidence-first trust).
- **Visual:** 2-col grid of source chips (doc icon + name + mono date + FEJ tag) + dashed limitations box.
- **Props:** `sources:[{name,date,level,href}], limitations`.
- **States:** chip hover → accent border (when `href`).
- **Theme:** tokens flip.

### SourceStatus
- **Purpose:** rail freshness indicator.
- **Visual:** “N источников · актуальны” + green “проверено” dot.
- **Props:** `count, verified`.
- **States:** verified (`--cc-success`) / stale (`--cc-amber`).

### ConfidenceStatus
- **Purpose:** analyst confidence (reuse existing `ConfidenceBadge`).
- **Visual:** 3 ascending bars (6/9/12px), filled count = low/med/high in `--cc-accent`; label “Уверенность: …”.
- **Props:** `level:"low"|"medium"|"high"`, `showLabel`.
- **States:** 3 levels.

### FactEstimateJudgmentTag
- **Purpose:** epistemic marker (reuse existing primitive).
- **Visual:** tiny uppercase pill; color per level (fact ink / estimate info / judgment accent / scenario violet).
- **Props:** `level:"fact"|"estimate"|"judgment"|"scenario"`, `size`.
- **States:** static. **Theme:** tokens flip; meaning is theme-invariant.

### KeyTakeaway
- **Purpose:** one-glance conclusion inside a tile (reuse existing).
- **Visual:** accent left bar + `--cc-accent-soft` fill, eyebrow “Вывод”, serif body.
- **Props:** `label`, `children`.
- **States:** static.

### PrimaryButton
- **Purpose:** main action (Проверить идею).
- **Visual:** solid `--cc-accent`, white text, radius 8, sans 600; no glow. Hover `--cc-accent-hover`; active translateY(1px).
- **Props:** `children, onClick, size, iconLeft/iconRight, disabled, loading`.
- **States:** default/hover/active/disabled/loading/focus-ring.
- **Theme:** tokens flip (on-accent text stays white).

### SecondaryButton
- **Purpose:** secondary action (В наблюдение, Сценарный анализ).
- **Visual:** `--cc-panel`/transparent bg + `--cc-line-2` border + `--cc-ink` text; hover faint fill.
- **Props:** as PrimaryButton.
- **States:** default/hover/active/disabled/focus.
- **Theme:** tokens flip.

> Implement Primary/SecondaryButton as `variant` of the existing `Button` primitive.

---

## 6. Implementation constraints

- Existing app is **React CRA, plain JavaScript** (no TypeScript).
- **Tailwind** uses the **`tw-` prefix**; extend `theme` with a `cc` namespace mapping to the CSS vars; use arbitrary values (`tw-bg-[var(--cc-panel)]`) for one-offs.
- CSS variables live in **`src/styles/tokens.css`** — add the scoped `.cc-root` light/dark blocks; do not edit existing global tokens.
- **Preserve all current product logic, routing, data selectors, and API contracts.** Consume existing data only.
- **Do not** rewrite backend/API · **do not** remove any of the 7 tabs · **do not** delete analytical content.
- **First and only implementation target: the Company Card page.** Other routes untouched.
- New shell components live under `src/company/` (or `src/design/company/`); reuse/restyle primitives in `src/design/*.jsx`.

```js
// tailwind.config.js
module.exports = {
  prefix: 'tw-',
  theme: { extend: {
    colors: { cc: {
      bg:'var(--cc-bg)', panel:'var(--cc-panel)', ink:'var(--cc-ink)',
      'ink-2':'var(--cc-ink-2)', accent:'var(--cc-accent)', amber:'var(--cc-amber)',
    }},
    fontFamily: { serif:['Source Serif 4','Georgia','serif'], mono:['JetBrains Mono','monospace'] },
    borderRadius: { cc:'14px' },
  }},
};
```

---

## 7. Implementation phases

**Phase 1 — Foundation & top of page**
Tokens (`.cc-root` light + dark) · Tailwind extension · route wrapper with `data-theme` · `MarketTopNav` · `NeoCompanyHero` (`CompanyIdentityBlock` + `PricePanel`) · `MetricStrip` · `ResearchTabs`. Wire existing quote/fundamentals/logo data — no selector changes.

**Phase 2 — Intelligence & support**
`ExecutiveIntelligencePanel` · `DecisionSupportRail` · `RiskStack` + `RiskSeverityBar` · `AnalystTile` wrapper for all analytical sections.

**Phase 3 — Analytical depth**
`MacroTransmissionFlow` · `GeoTransmissionFlow` · `ScenarioPanel` · `EvidencePanel` (+ `SourceStatus`, `ConfidenceStatus`). Full dark + light QA, then promote behind a feature flag.

---

## 8. Acceptance criteria

- [ ] Production build passes (`react-scripts build`); no new lint errors.
- [ ] Live company data renders: price, logo, ticker, market cap, change, analytics.
- [ ] **Both** dark and light themes render correctly and switch via `data-theme` / `.dark`.
- [ ] All seven Company Card tabs work and navigate to their sections.
- [ ] Design matches the selected Direction A language (serif headings, mono figures, flat tiles, restrained borders, no glow).
- [ ] No broker / trading-signal language; no buy/sell recommendations.
- [ ] No generic-SaaS look (tile-based analytical reading, editorial type, decision-support framing).
- [ ] No backend / API changes; existing contracts intact.
- [ ] Responsive: ≥1080 two-column; ≤1080 rail above content + metrics 3-up; ≤720 single-column, hit targets ≥44px.
- [ ] Visual diff vs. `direction-a-hybrid.html` / `direction-a-light.html` on the Роснефть (ROSN) data.

---

*Basis Neo-Institutional Research System · Company Card v1 · token values and prototypes are normative.*
