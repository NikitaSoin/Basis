---
name: build-seo-pages-gotcha
description: bare `craco build` (as literally written in CLAUDE.md) wipes the ~1580 per-ticker static SEO pages in build/ — must also run generate-seo-pages.js
metadata:
  type: project
---

Running exactly the command CLAUDE.md documents — `cd frontend/Basis && CI=false npx
--no-install craco build` — regenerates `build/` from scratch and DELETES the
per-company static SEO pages (`build/<TICKER>/index.html`, `build/<TICKER>/business/`,
`/finance/`, `/dividends/`, `/macro/`, `/geo/`, plus `build/company/` catalog and
`sitemap.xml` — ~1580 files total). Confirmed via `git status`: after a bare craco
build these all showed as deleted (`D`).

**Why:** `package.json`'s real `"build"` script is `craco build && node
scripts/generate-seo-pages.js` — the SEO generator is a SEPARATE second step,
undocumented in CLAUDE.md's shorthand deploy instruction. `craco build` alone only
produces the SPA shell (`index.html`, `static/js|css/main.<hash>.*`).

**How to apply:** after any `craco build` for deploy, ALSO run
`node scripts/generate-seo-pages.js` (from `frontend/Basis/`) before committing
`build/` — confirms via `git status frontend/Basis/build` showing modifications
instead of deletions on the `build/<TICKER>/...` paths. Cheap (~few seconds,
pure Node, no network). Skipping it silently regresses SEO/Yandex indexing on next
deploy even though the app itself still works fine — easy to miss because the app
"looks done" without it.
