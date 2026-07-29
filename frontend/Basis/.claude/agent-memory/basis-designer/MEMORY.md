# Memory index

- [Portfolio V2 sidebar shell](portfolio-v2-sidebar.md) — Портфель rebuilt as ObserverV2-style dark sidebar; PortfolioView kept as legacy; data-gaps forced honest stubs (no dividend calendar, no P&L breakdown, no factor-sensitivity data)
- [Mobile nav shell fix](mobile-nav-shell.md) — TopNav had zero mobile handling (portrait broke nav); added bottom tabbar+sheet; full-bleed shells each need own tabbar-clearance padding; internal sidebars fixed separately, see below
- [Mobile sidebar drawer](mobile-sidebar-drawer.md) — reusable toggle drawer (hook+CSS) for dark internal sidebars, wired into Портфель+Скринер+Рынок 2026-07-21; Обозреватель's .obs-sidebar still pending; hook has 3rd `drawerNarrow`→`inert` return value
- [Inline-style mobile audit debt](inline-style-mobile-audit-debt.md) — fixed one hardcoded gridTemplateColumns inline layout (Портфель hero card); owner flagged more likely exist repo-wide, full audit is separate future task
- [Mobile dense cards](mobile-dense-cards.md) — "больше карточек в ряд" на мобильном: считай ширину контейнера ДО правок; если рич-карточка физически не влезает — новый урезанный JSX-набор полей, не CSS-сжатие; кейс — Рынок mini-cards
- [ChartPro rollout — indices](chartpro-rollout-indices.md) — заменил ObsLineChart на ChartPro для IMOEX/MCFTR/RTSI; ловушка дублирующего period-переключателя и как её решил; кандидаты на ту же замену дальше
- [lightweight-charts multi-series pattern](lightweight-charts-multiseries-pattern.md) — BenchmarkChart (Портфель→Сравнение) SVG→lightweight-charts: цвета canvas vs DOM, тултип через param.logical, избегай ребилда графика от нестабильных пропсов
- [craco build touches real build/](craco-build-touches-real-build-dir.md) — bare `craco build` (буквально из CLAUDE.md) удаляет ~1580 пререндеренных SEO-страниц без пересборки; для проверки компиляции — BUILD_PATH=scratch, не реальный build/
