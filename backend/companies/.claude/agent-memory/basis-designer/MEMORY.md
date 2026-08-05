# Project Memory — basis-designer

- [build-seo-pages-gotcha](build-seo-pages-gotcha.md) — bare `craco build` deletes 1580 SEO pages; must also run `node scripts/generate-seo-pages.js`
- [markets-tab-m5-namespace](markets-tab-m5-namespace.md) — «Рынки» tab uses `m5-*` CSS classes aliased to canon tokens, NOT legacy — follow the convention, don't rewrite to `bs-*`
- [commodity-exposure-block](commodity-exposure-block.md) — «Товар компании» block: gate honest-degradation text on `benchmark_key==="none"`, not on `current_price` presence (price often only in reasoning prose)
