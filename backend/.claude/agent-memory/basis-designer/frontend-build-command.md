---
name: frontend-build-command
description: правильная команда пересборки фронта — npm run build, НЕ голый craco build (иначе теряются закоммиченные SEO-страницы компаний)
metadata:
  type: project
---

`frontend/Basis/package.json` → `"build": "craco build && node scripts/generate-seo-pages.js"`.
Второй шаг генерирует 264 статические страницы `build/company/<TICKER>/index.html` +
`sitemap.xml` (client-side SPA не даёт ботам ничего без этого — см. комментарий в
`scripts/generate-seo-pages.js`).

Если пересобрать ТОЛЬКО `CI=false npx --no-install craco build` (без второго шага — так
исторически формулировалась инструкция в CLAUDE.md/задачах), CRA **удаляет всю
`build/`-директорию перед сборкой**, включая эти 264 `company/*/index.html` — и они
остаются удалёнными в git, потому что raw craco build их не создаёт заново.
`git status` после такой сборки покажет сотни `D frontend/Basis/build/company/.../index.html`.

**Как надо:** `cd frontend/Basis && CI=false npm run build` (или `craco build`, затем
ВСЕГДА следом `node scripts/generate-seo-pages.js`). Перед `git add build/` проверяй
`git status --short frontend/Basis/build` — там должны быть ТОЛЬКО новый хэш
`main.<hash>.js`/`.css`, `asset-manifest.json`, `index.html`; если видишь `D` по
`build/company/*` — забыл SEO-шаг, перезапусти его перед коммитом.

**Why:** комментарий в generate-seo-pages.js подтверждает, что билд-окружение Timeweb
реально гоняет `npm run build` на сервере (не только отдаёт закоммиченный build/, как
считалось раньше) — значит расхождение между «как собираю я» и «как собирает прод»
создаёт скрытый риск отката SEO-страниц.

**How to apply:** каждый раз, когда задача явно просит `CI=false npx --no-install
craco build` (частая формулировка в design-tasks) — выполняй её, но ДОБАВЛЯЙ
`node scripts/generate-seo-pages.js` следом и сверяй `git status` на предмет `D
build/company/*` перед тем как считать сборку готовой к коммиту.
