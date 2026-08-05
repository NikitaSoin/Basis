---
name: commodity-exposure-block
description: «Товар компании» block in Рынки tab reads commodity_exposure from market.json — data quirk: current_price is often absent even when a live benchmark exists (price only in reasoning prose); must gate honest-degradation text on benchmark_key==="none", not on current_price presence
metadata:
  type: project
---

Implemented in `frontend/Basis/src/company/CompanyCardView.jsx`,
`renderCommodityExposure()` inside `renderMarket()` (~line 5547), styled in
`frontend/Basis/src/market/market-m5.css` (`.m5-cmx-*` classes, appended at file
end). Rendered right after the top verdict/KPI strip, before the primary-market
segment-control card (per product brief: price is more decision-relevant than
market share, belongs above it). Backend already returns the field with no
changes needed — `GET /api/companies/by-ticker/{ticker}/market` just dumps
`market.json` as-is (`app/api/companies.py`), and `commodity_exposure` is a
top-level key in that file.

**Data quirk found while building (2026-07-22):** `current_price` (the
structured `{value, unit, as_of, certainty, source_ref}` object) is populated
inconsistently across the first 8 rollout tickers (ALRS/LKOH/GMKN/RUAL/MAGN/
PHOR/AFLT/PLZL). GMKN and PLZL have it on every item. But LKOH (Urals), RUAL
(aluminum revenue side), MAGN (both cost items), PHOR (all 3 revenue items),
AFLT (kerosene) have `benchmark_status: "live"` (a real live/quotable series
exists) yet NO `current_price` object — the actual number only appears embedded
in the `reasoning` prose (e.g. "~$57–65/барр").

**Why it matters:** the UI must NOT say "no public benchmark exists" just
because `current_price` is missing — that would be false for these live-series
cases. The correct gate is `benchmark_key === "none"` (present and reliable on
every example so far, including cases where `benchmark_status` itself is absent
from the JSON, e.g. ALRS). Implementation: show the price row only if
`current_price` is present; show the honest-degradation caption only if
`benchmark_key === "none"`; otherwise (live/planned benchmark, just no
structured snapshot yet) render nothing for the price row and rely on the
cycle gauge + prose reasoning, which already carries the number.

**How to apply:** if a future pass adds `current_price` more consistently
across the ~50-company rollout, this fallback becomes mostly dormant but
should stay — it's the correct honest behavior either way. Also:
`current_price.value` is sometimes a pre-formatted STRING with the unit baked
in (PLZL: `"~$4 060–4 100/унц"`), not always a number — the unit chip is only
rendered when `value` is numeric, to avoid duplicating units like
"...унц USD за тройскую унцию".
