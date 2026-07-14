---
name: obs-corporate-news
description: ObsCorporateNews (Обозреватель → «Корп. события») component/CSS pattern + calendar confidence badge — reuse before touching corp-news or calendar epistemic tags again
metadata:
  type: project
---

Added 2026-07-14: new sidebar section «Корп. события» (`ObsCorporateNews` in
`frontend/Basis/src/observer/ObsPanels.jsx`, wired in `OBS_ZONES` under zone
`market` right after `reports`, rendered via `case "corp-news":` in
`frontend/Basis/src/App.js`). Backend: `GET /api/market/corporate-news`.

**New reusable global tag class: `.obs-tag-estimate`** (in `observer-v2.css`,
placed in the new CORPORATE NEWS SECTION block but usable anywhere) — background
`var(--info-soft)` / color `var(--info)`, same shape as `.obs-tag-fact`/
`.obs-tag-judgment`. This is the canonical "оценка" epistemic tag for obs-*
(mirrors `.bs-tag-estimate` in `basis-design-system.css` which uses
`--bs-estimate` blue — same semantic slot, different token family). Use this
class, don't invent another "estimate" tag.

**New reusable badge: `.obs-cal-conf` / `.obs-cal-conf--estimate`** — compact
secondary badge (9.5px) for calendar events whose date is an aggregated guess
rather than issuer-confirmed (`payload.confidence !== "issuer"`, including when
the field is absent — absence means unconfirmed, NOT "assume issuer"). Wired
into both `ObsCalendar` list view (`.obs-tl-title`) and grid day-detail view
(next to `.obs-cal-detail-type` pill). Deliberately only renders when NOT
issuer-confirmed — no competing "подтверждено" badge was added (would be visual
noise; absence of the badge already reads as "trustworthy default").

**Kind→group→color mapping pattern** (`CN_KIND_META` in ObsPanels.jsx): 4 colour
groups only (`reports`=accent/copper, `missing`=neutral/text-tertiary,
`dividend`=success, `business`=info), even though there are 6 `kind` values —
the 3 `business_*` subkinds share the `business`/info colour and are
differentiated only by icon (Swords/Scale/Briefcase), because the filter chips
also group them together. Don't split business_* into separate colours without
also splitting the filter chip.

**`report_missing` styling is an explicit owner instruction, not a design
guess**: this event ("отчёт ожидался по календарю, не нашли источник") must
NEVER use danger/red — it's an epistemic gap in Basis's own calendar, not an
accusation against the company. Card gets `.obs-cn-card--muted` (flat, no
shadow-hover emphasis) always for this kind; when `likely_calendar_error: true`
an extra muted note chip (`.obs-cn-cal-note`, text-tertiary, Info icon) reads
"вероятно, погрешность нашего календаря". If this pattern needs touching again,
preserve the "no red for our own data gaps" rule — it generalizes beyond this
one component (any Basis-side data-completeness gap vs. company-caused issue
should follow the same muted/neutral treatment).

Click-through is gated strictly on backend's `link_to === "reports"` field
(not by kind or by presence of ticker) — the backend explicitly encodes which
items are clickable, don't infer it client-side.

See also [[obs-economy-pattern]], [[obs-barometer-redesign]] for other obs-*
CSS/section patterns in the same file.
