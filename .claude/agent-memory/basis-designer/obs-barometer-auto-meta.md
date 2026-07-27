---
name: obs-barometer-auto-meta
description: ObsBaroHero/_meta rendering for the autonomous barometer reviser (source expert|auto, generated_at, expert_anchor_as_of, trigger_reason) + per-subindex delta_rationale tag
metadata:
  type: project
---

2026-07-27: owner shipped `backend/app/services/barometer_reviser.py` +
`backend/app/services/barometer_store.py` (single read-path for both
`/api/market/geo-barometer` and `/api/market/institutions`, reads a DB-published
row, not the config JSON file directly anymore) — the reviser can autonomously
move subindex scores between expert runs and PUBLISH DIRECTLY (owner cancelled
the shadow-mode plan same day, `290f6e2bc7`: "пусть агент сразу на бой катит").
I wired the frontend render for the resulting `_meta` field same session, in
`frontend/Basis/src/observer/ObsPanels.jsx` (`ObsBaroHero`, `ObsBaroSubRow`) +
`frontend/Basis/src/styles/observer-v2.css` (`.obs-baro-auto-*`,
`.obs-inst-tag--auto`).

## Verified real backend contract (read the service, don't trust a task prompt's
paraphrase — matched exactly here, but always re-check)
`barometer_store.get_payload_with_meta()`:
```
payload["_meta"] = {
  "source": row.source,                # "expert" | "auto"
  "generated_at": row.created_at.isoformat(),
  "expert_anchor_as_of": (expert.payload or {}).get("as_of") if expert else payload.get("as_of"),
  "trigger_reason": row.trigger_reason,
}
```
Body of the barometer (barometer/subindices/scenario/regions) is untouched when
auto — only scores + this added `_meta` change. Per-subindex, the reviser writes
`delta_rationale` (verified string, `backend/app/services/barometer_reviser.py`
literally requires "КАЖДОЕ изменение балла снабди delta_rationale") onto moved
subindex objects only — untouched subindices don't get the field at all.

## Two-tier date design (deliberate, not just "add a badge")
`ObsBaroHero` now takes a `meta` prop. When `meta?.source === "auto"`, the
`.obs-inst-hero-top` right slot (previously always "срез на {asOf}") switches
to a two-line note instead of adding alongside it — showing BOTH the
auto-revision date (`generated_at`) AND the expert anchor date
(`expert_anchor_as_of`) explicitly, smaller/dimmer for the anchor line. This
mirrors the honesty requirement already established by
[[obs-situation-overlay]] (anchor `as_of` always visible, never let a fresher
delta-layer imply the whole barometer is fresh) — same principle, now applied
to the barometer's OWN scores, not just an annotation layer on top of them.
Helper: `obsFmtDDMM(iso)` (new, next to `obsParsePct`) — ISO → "ДД.ММ", reused
from the exact recipe already used inline in `ObsSituationOverlay`
(`toLocaleDateString("ru-RU", {day:"2-digit", month:"2-digit"})`).

## Per-subindex "оценка (авто)" tag
`ObsBaroSubRow` (shared by `ObsBaroClusters` accordions AND the standalone geo
"Внешние оси" reuse, see [[obs-barometer-redesign]]) — added a second small
pill next to the existing факт/оценка `type` tag, gated on `s.delta_rationale`
truthy, native `title={s.delta_rationale}` tooltip (no new UI chrome for the
tooltip itself). Deliberately did NOT replace the факт/оценка tag — they're
orthogonal axes (epistemic level of the rationale text vs. "was this score
recently auto-revised"), both can be true at once, confirmed this renders fine
stacked (`ФАКТ` + `ОЦЕНКА (АВТО)` side by side, wraps cleanly on
`.obs-inst-sub-head`'s existing flex-wrap).

## Muted-by-design color choice (explicit owner/task instruction, not my default)
Both the hero note and the subindex tag use ONLY `var(--text-tertiary)` (+
`var(--border-strong)` outline for the tag pill, no fill) — no --info/--warning/
--accent. This was an explicit task requirement ("приглушённая, не кричащая —
это не тревога, а прозрачность"), differs from the existing filled
`.obs-inst-tag--est`/`.obs-tag-estimate` (--info blue) pattern used for the
regular факт/оценка epistemic tags. Reused the exact outlined/transparent
recipe already established by `.obs-overlay-badge.obs-overlay-align--confirm`
(the "подтверждает"/neutral state in [[obs-situation-overlay]]) rather than
inventing a new visual language for "neutral/informational pill".

## Verification
Real prod data for `source:"auto"` wasn't available yet at implementation time
(reviser publishes on event, not guaranteed present) — verified via Playwright
route-mocking on a local `craco start` dev server (arbitrary port, e.g. 3459;
CORS satisfied via `Access-Control-Allow-Origin: '*'` on every
`route.fulfill()`, per [[playwright-maplibre-verification]] — exact-3000 origin
matching is only needed against a REAL local backend, not needed here).

**New gotcha found this session, worth remembering**: the two barometer
screens use DIFFERENT segment-toggle button labels for the same "assessment"
mode — Geo (`ObsGeopolitics`) uses `"Оценка ситуации"`, Institutions
(`ObsInstitutions`) uses `"Текущая ситуация"` — a single shared selector string
across both pages will silently time out on whichever one doesn't match. Also:
`ObsGeopolitics`'s barometer hero is nested inside
`!loading && !error && activeRegion && (...)` — `activeRegion` comes from a
SEPARATE fetch (`/api/market/geopolitics` overview `tabs.overview`/`tabs.deep`
arrays, needs `{region, title, ...}` entries), NOT from `/api/market/geo-barometer`
itself. Mocking only the barometer endpoint leaves the whole assessment block
(including the hero) unmounted with an unrelated "Нет геополитических данных"
empty state from a sibling block — mock BOTH endpoints for this screen, same
"mock every gating fetch on the path" lesson as [[playwright-maplibre-verification]]
but a new concrete instance of it (ObsInstitutions has no such gate, only
ObsGeopolitics does).
