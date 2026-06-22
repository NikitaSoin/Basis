# Basis Design System — “Institutional Clarity”

A design system for **Basis / Inbasis** ([inbasis.ru](https://inbasis.ru)) — an independent
investment-analytics platform and **“second opinion”** for self-directed private investors
on the Russian market.

Basis is **not** a broker, a trading terminal, a buy/sell signal service, or a hype AI app.
It is an independent analytical layer that helps investors **reduce uncertainty** through
structured, transparent analysis with honest caveats. This design system exists to evolve
the existing product into a more coherent, premium, trustworthy whole — *without* destroying
its working logic, structure, or analytical depth.

> **Design philosophy — “Basis Institutional Clarity.”**
> Institutional-grade analytical depth, made understandable for a private investor.
> It should feel like a calm **financial research cockpit** — an analytical workspace and a
> structured second-opinion system. It should **never** feel like a broker app, a trading
> terminal, a crypto dashboard, a Telegram signal channel, or a colorful fintech casino.

---

## Sources

This system was reverse-engineered from the live Basis codebase. The reader (human or agent)
can explore these further to build higher-fidelity Basis designs:

- **GitHub:** [`NikitaSoin/Basis`](https://github.com/NikitaSoin/Basis) — the production
  monorepo (React CRA frontend + FastAPI backend).
  - `frontend/Basis/src/styles/tokens.css` — the canonical token dictionary (ported here).
  - `frontend/Basis/src/styles.css` — base resets, app layout, sidebar.
  - `frontend/Basis/src/design/primitives.jsx` — Button, IconButton, Card, Badge, Chip,
    Tooltip, Input, Select, Modal, Tabs, Table, Delta, KpiTile.
  - `frontend/Basis/src/design/textblocks.jsx` — Prose, LeadStatement, KeyTakeaway,
    Disclosure, StatInline, PullQuote.
  - `frontend/Basis/src/design/bondrisk.jsx` — the structured bond-risk verdict renderer.
  - `frontend/Basis/src/design/logomarks.jsx` — brand-mark concepts + the approved
    «слои-фундамент» monogram B.
  - `frontend/Basis/tailwind.config.js` — `tw-`-prefixed utilities mapped onto the tokens.
  - `frontend/Basis/src/App.js` — almost the entire product UI (≈727 KB, single file).
  - `CLAUDE.md` (repo root) — the product “constitution” (values, the protected design
    system «заповедник», the three-level certainty methodology).

**Implementation note.** The live frontend is React CRA (plain JS), Tailwind with a
**`tw-` prefix**, CSS variables in `tokens.css`, and primitives in `src/design/*.jsx`.
Everything in this system is built to translate 1:1 into those tokens and React components —
no concept here requires a rewrite.

---

## The Three Levels of Certainty — the backbone of Basis

Every analytical statement in Basis belongs to **one of three epistemic levels**, and the
interface must make the distinction visible. This is the single most important idea in the
product, and the design system encodes it as first-class tokens and a component
(`FactEstimateJudgmentTag`).

| Level | Russian | Meaning | Token / color |
|---|---|---|---|
| **Fact** | факт | Supported by a source | `--fact` — neutral grey |
| **Estimate** | оценка | Model-based calculation | `--estimate` — info blue |
| **Judgment** | суждение | Analytical interpretation (not a prediction) | `--judgment` — cobalt accent |
| **Scenario** | сценарий | A conditional “if X then Y” path | `--scenario` — violet |

Color here is **reasoning support, not decoration.** Investment analysis is ambiguous;
color must help the investor think, never tell them what to do.

---

## Product areas

1. **Market** — grid/list of companies, asset-class switcher (stocks · bonds · futures ·
   funds · currency/metals), live prices, daily change, market cap, logos, heatmaps, screening.
2. **Company card** — a structured research dossier with tabs: Overview · Business model ·
   Financials & valuation · Corporate governance · Markets · Macro · Geopolitics.
3. **Market observer** — a decision-support briefing: news feed, macro overview, market maps,
   calendar, reporting analysis, geopolitics, AI overview.
4. **Portfolio** — a risk-diagnostic cockpit: holdings, weights, returns & risk, volatility,
   beta, CAPM, alpha, correlations, benchmark chart, portfolio health, stress scenarios.
5. **Bonds** — centered on one question: *“Is the yield adequate for the risk?”* — spread to
   OFZ, rating vs market-implied risk, 1–5 risk score, blocks A–F, expected loss PD×LGD.

---

## CONTENT FUNDAMENTALS — how Basis writes

**Language.** Primary UI language is **Russian** (ru-RU). Numbers follow strict ru-RU
typographic rules (see `tokens` + the production `format.js`):
- decimal separator = **comma** → `4 977,5`
- thousands grouping = **narrow no-break space** (U+202F) → `1 250 000`
- a **no-break space** before a unit → `9,2 %`, `4 977,5 ₽`, `6,4 ×`

**Tone.** Calm, analytical, honest, senior. The voice of a careful research desk, not a
salesperson. Basis treats *honesty about uncertainty as a trust feature* — a callout like
**«Честно: данные противоречивы»** is value, never an apology.

**Casing.** Sentence case for body and headings. **Uppercase + letter-spacing** (`--ls-eyebrow`)
is reserved for small eyebrow labels (column headers, section kickers like `АРИФМЕТИКА`,
`ГЛАВНЫЕ АРГУМЕНТЫ`).

**Person.** Addressed to the investor as **«вы»** implicitly; the product speaks about the
analysis, not about itself. It frames help as *“what matters now”* and *“what would change
the conclusion”* — never *“we recommend.”*

**Words Basis PREFERS:**
> Что важно сейчас · Ключевые риски · Что уже может быть в цене · Что изменит вывод ·
> Проверить идею · Сценарный анализ · Факты и допущения · Второе мнение перед решением ·
> Не является инвестиционной рекомендацией · Доказательства и источники

**Words Basis AVOIDS (anti-hype, anti-casino):**
> ~~Купить сейчас~~ · ~~Продать сейчас~~ · ~~Топ-сигнал~~ · ~~AI-выбор акции~~ · ~~🚀~~ ·
> ~~Гарантированный рост~~ · ~~Лёгкие деньги~~ · ~~Лучшая идея~~

**Emoji.** Essentially none in chrome. The **only** glyphs used semantically are the
delta arrows **▲ / ▼ / ▬** (gain/loss/flat) and a small set of status glyphs (`⚠ ℹ ⚖ →`).
The bond-risk verdict uses traffic-light dots (🔴🟠🟡🟢⚪) as a deliberate, contained
exception inside that one analytical component. No decorative emoji anywhere.

**Density.** Medium. More analytical than a consumer fintech app, less dense than a Bloomberg
terminal. Long analytical prose is **never** rendered as one wall of text — each topic is its
own tile (see Layout below), with a lead conclusion up front and evidence one click away.

---

## VISUAL FOUNDATIONS

**Color vibe.** Warm and serious. A **cream off-white** app background (`#F8F7F4`) with
**pure-white tiles** floating on top — the signature “плитки на тёплом фоне.” The one
signature accent is **cobalt** (`#2347D9`). Violet (`--accent-2`, `#8B5CF6`) appears *rarely*
and only for AI/insight accents and the marketing hero gradient. Green/red appear **only** to
carry meaning, always with a ▲/▼ glyph. A colorblind-safe **Okabe-Ito** categorical palette
is used **strictly inside data viz** (charts, sector chips, treemaps) — never in chrome.

**Typography.** **Inter** for UI, text, and headings (large headings use Inter's
display optical size via the `opsz` axis); **JetBrains Mono** for numbers, tickers, and formulas. Financial figures are
**tabular, lining numerals** everywhere, **right-aligned** in tables. Big figures (KPI values,
hero numbers) are set **light weight** (300) and tracked tight for an editorial feel. Reading
copy sits at 15px / line-height 1.6, capped to a ~68ch measure.

**Backgrounds.** Flat warm cream. **No photographic imagery, no full-bleed hero photos, no
repeating textures.** The only gradients are (a) the foundation gradient inside the logomark
and (b) a single dosed cobalt→violet marketing hero gradient. In the **dark theme** only, a
very faint decorative orbit/glow is allowed on landing/pricing (`--decor-*`); in light it is
fully off.

**Cards / tiles.** White (`--bg-elevated`), `--radius-md` (8px) corners, a **1px
`--border-strong`** outer border so each tile reads as a distinct plate off the cream, plus a
soft layered shadow (`--shadow-md`). On hover, the shadow deepens to `--shadow-lg` and the
border to `--border-hover` — depth, not movement. **No colored-left-border-only cards** as a
generic pattern (the left accent bar is reserved for `LeadStatement` and `KeyTakeaway`).

**Borders.** Two weights: `--border-subtle` for internal hairlines (table rows, dividers) and
`--border-strong` for the outer edge of tiles. This keeps tables from turning into a heavy grid
while tiles still separate cleanly.

**Shadows.** Light theme = soft warm-neutral layered drop shadows (a tight near shadow + a
softer far shadow). Dark theme = a crisp 1px border *as the first shadow layer* + a gentle dark
drop, so depth survives on near-black without a muddy halo.

**Radii.** 4 (inputs/chips) · 6 (buttons) · 8 (cards, default) · 12 (panels/modals) ·
16 (feature surfaces) · pill (badges/chips).

**Motion.** Dosed and short. `--motion-fast` (150ms) for hover/micro, `--motion-base` (250ms)
for tabs and transitions, `--ease-out` `cubic-bezier(0.16,1,0.3,1)`. **No bounce, no infinite
decorative loops** on content. Everything respects `prefers-reduced-motion`.

**Hover states.** Buttons darken to `--accent-hover` (primary) or fill `--accent-soft`
(secondary/ghost). Cards lift via shadow + border. Table rows tint to `--bg-hover`.
**Press state:** a 1px downward nudge (`active:translate-y-px`), never a scale/bounce.

**Focus.** Every interactive element carries a visible ring: `--shadow-focus`
(`0 0 0 3px var(--accent-soft)`).

**Transparency & blur.** Used sparingly: a scrim (`--bg-overlay`) behind modals, optionally
with a small `backdrop-filter: blur(4px)`. Soft token fills (`*-soft`) are translucent so they
sit calmly on any surface.

**Layout rules.**
1. **Tile-based analytical reading** — each topic is its own sibling tile on the base
   background, never one undifferentiated block.
2. **Progressive disclosure** — conclusion first, then the logic, then the evidence.
3. **Evidence-first trust** — sources, dates, assumptions, and confidence are visible or one
   click away (`EvidenceDrawer`, `SourceTag`).
4. **Decision-support, not advice** — the UI helps the investor think, never instructs.
5. Clear visual separation between **fact · estimate · judgment · scenario · risk · source.**
   App shell: a fixed **64px icon sidebar** (left; bottom bar on mobile) + scrolling work area.

---

## ICONOGRAPHY

Basis uses **inline SVG icons** drawn at a **consistent stroke weight (~1.5–2px), rounded
caps/joins**, currentColor-driven so they inherit text color and theme. There is **no icon
font and no raster icons** in the product. Icons are functional and quiet — they label
navigation and actions, never decorate.

- **Recommendation for new work:** use **[Lucide](https://lucide.dev)** (CDN) — its 1.5–2px
  rounded-stroke style matches the hand-drawn product icons almost exactly. *(Substitution
  flagged: the production app hand-rolls a small set of inline SVGs rather than pulling a named
  library; Lucide is the closest faithful match for filling gaps. If you need pixel-exact
  parity for an existing glyph, copy it from `App.js`.)*
- **Brand marks** live in `assets/`: `logomark.svg` (the approved «слои-фундамент» monogram B
  with the foundation gradient), `wordmark.svg` (mark + “Basis”), and `favicon.svg` (cobalt
  app-icon plate). The mark reads cleanly down to 16px.
- **Semantic glyphs** (not icons): delta arrows **▲ ▼ ▬**, and `⚠ ℹ ⚖ →` inside analytical
  callouts. Bond-risk verdicts use traffic-light dots 🔴🟠🟡🟢⚪ — a contained exception.
- **No emoji** in chrome, lists, or marketing.

---

## Index / manifest

```
styles.css                  ← consumers link THIS (── @imports everything below)
tokens/
  fonts.css                 Inter + JetBrains Mono (Google Fonts)
  colors.css                surfaces, text, accent, semantic, categorical, epistemic
  typography.css            families, weights, type scale, line-height, tracking
  spacing.css               8pt grid, radius, elevation, motion
  base.css                  element resets + tabular-number defaults
assets/
  logomark.svg  wordmark.svg  favicon.svg
guidelines/                 foundation specimen cards (Design System tab)
components/
  core/        Button, IconButton, Badge, Chip, Input, Select, Toggle, Tooltip
  layout/      Card, KpiTile / MetricCard
  data/        DataTable (financial), Delta
  feedback/    Callout / KeyTakeaway, EmptyState, Skeleton, Modal/Drawer
  analytical/  FactEstimateJudgmentTag, RiskBadge, SourceTag, ConfidenceBadge,
               ExecutiveSummaryCard, KeyTakeaway, MetricExplainer, ScenarioTabs,
               BondRiskScoreCard, FactorImpactCard, MacroTransmissionCard
ui_kits/
  market/      Company market grid + asset-class switcher
  company/     Company research-dossier card
  portfolio/   Portfolio risk cockpit
  bonds/       Bond yield-vs-risk view
SKILL.md                    Agent-Skill manifest (downloadable)
```

See **CONTENT FUNDAMENTALS**, **VISUAL FOUNDATIONS**, and **ICONOGRAPHY** above before
designing. When in doubt: calm, structured, honest; conclusion first, evidence one click away;
color carries meaning, never mood.
