# Аудит фронтенда — архитектура и техдолг

Дата: 2026-07-26. Область: `/frontend/Basis`. Метод: статический анализ src/ + разбор собранного `build/` (main.73e878d8.js). Ничего не редактировалось.

**Важное уточнение к CLAUDE.md:** App.js уже НЕ 8k строк — он разгружен до **1050 строк** (чистый шелл: топ-нав, роутер-switch, error boundary). Гиганты переехали: **`company/CompanyCardView.jsx` — 7 389 строк** и **`observer/ObsPanels.jsx` — 6 675 строк**. Мёртвый `renderFinancials` тоже переехал в CompanyCardView (строки 3911–5181). CLAUDE.md стоит обновить.

---

## ТОП-10 (приоритет / трудоёмкость S<0.5д, M=0.5–2д, L>2д)

| # | Проблема | Приоритет | Труд. |
|---|----------|-----------|-------|
| 1 | **Code splitting отсутствует полностью** — 0 вызовов `React.lazy`/`import()`; весь сайт (Обозреватель, карточка, портфель, скринер, лендинг, /_design) — один чанк 793 KB gzip. Route-чанки дали бы −40…50% initial load | ВЫСОКИЙ | M |
| 2 | **MapLibre = ~216 KB gzip (27% бандла) грузится на каждой странице**, включая лендинг — статический импорт в ObsPanels.jsx:5; используется только картами гео/рынка. Динамический `import()` внутри карт-компонентов — самый дешёвый большой выигрыш | ВЫСОКИЙ | S |
| 3 | **~2 900 строк мёртвого кода в бандле**: хвост renderFinancials ~1 255 стр. (достижим для 1 компании из 268), ObsLegacyViews.jsx 1 500 стр. (единственный потребитель — сам мёртвый OverviewView в App.js:352–420), classic-ветка карточки за `?classic=1` | ВЫСОКИЙ | S–M |
| 4 | **Роутинг: URL есть только у /company/*** — облигации/фьючерсы/фонды (~3 100 бумаг!), 11 секций Обозревателя, индексы, скринер, портфель, стресс-тест не имеют адреса: нельзя пошарить, F5 сбрасывает, SEO — ноль | ВЫСОКИЙ | M (слой pushState) |
| 5 | **Данные: 164 fetch-вызова без кэша/дедупликации** — `/api/screener/scored` ×9, `/api/quotes/realtime` ×8, `/api/companies` ×8; ObserverV2 ремоунтится при каждом входе и по key на каждую секцию → полный рефетч. Нужен мини-кэш/useFetch | ВЫС/СРЕДН | M |
| 6 | **CRA — тупик**: react-scripts 5.0.1 (заморожен, CRA официально закрыт), React 19.2.6 — комбинация вне поддержки; craco-костыли под OOM Timeweb (`concatenateModules:false` раздувает бандл, sourcemaps выключены → нет анализа/отладки). Vite снял бы OOM и вернул sourcemaps | СРЕДНИЙ | M (1–2 дня) |
| 7 | **Два файла-гиганта**: CompanyCardView.jsx 7 389 стр. = 47 компонентов и 7 самостоятельных экранов (CompanyCard, CompaniesView, Bond/Futures/Fund/SpotCard, ScreenerView); ObsPanels.jsx 6 675 стр. = 79 компонентов. Дешёвые выносы перечислены ниже | СРЕДНИЙ | M–L |
| 8 | **4 токен-системы** (`--bs-` 282, `--cc-` 430, `--pf-` 298, `obs-` 1 839 использований) + рудимент classic. Дешёвый путь: свести `--cc-`/`--pf-` к алиасам `var(--bs-*)` в одном файле + запрет новых; полное переименование ~730 мест — дорого и не срочно | СРЕДНИЙ | S (алиасы) / L (полное) |
| 9 | **Паттерн fetch+loading+error скопипащен ~53 раза** (53 loading-стейта, 23 error-стейта, 17 глухих `catch(() => {})`) — один хук `useFetch` закрыл бы и №5 частично | СРЕДНИЙ | S (хук) + постепенно |
| 10 | **Нет root error boundary**: ViewErrorBoundary в App.js покрывает только контент-зону; краш в TopNav/шелле/index.js = белый экран. Одна обёртка в index.js | НИЗКИЙ | S |

---

## Детали

### 1. Размеры (реальные, wc -l)

```
7389  company/CompanyCardView.jsx   47 компонентов, 7 экранов
6675  observer/ObsPanels.jsx        79 компонентов, весь Обозреватель + обе карты
5425  styles/observer-v2.css
4286  portfolio/PortfolioViews.jsx
1500  observer/ObsLegacyViews.jsx   ← мёртвый (см. п.2)
1313  company/FinanceTab.jsx
1169  portfolio/StressTestView.jsx
1125  market/MarketNeo.jsx
1050  App.js                        ← уже разгружен, чистый шелл
 930  compare/CompareView.jsx
 879  styles/portfolio-v2.css
 867  company/GeoTab.jsx
 777  design/primitives.jsx
 741  design/DesignSystem.jsx       ← прод-бандл ради dev-роута /_design
 678  styles/assistant.css
```
Всего src: ~49 900 строк, 65 файлов.

**Что выносится дёшево (границы уже чистые, только импорты поправить):**
- Из CompanyCardView: `BondCard`, `FuturesCard`, `FundCard`, `SpotCard`, `CompaniesView`, `ScreenerView` — это независимые экраны, экспортируются из того же файла (стр. 7389). Каждый — механический вынос.
- Из ObsPanels: блок гео-карт (всё с префиксами GEOMAP/SVO/TERR + ObsGeoWorldMap/ObsGeoTheaters) — он же держит статический импорт maplibre → вынос решает и №2; ObsMarketPulse-кластер (Sparkline/PulseCard/Momentum/ArcGauge/FearGreed/Tornado); ObsEconomy.

### 2. Мёртвый код

- **renderFinancials, CompanyCardView.jsx:3911–5181 (~1 270 строк).** Ранний return: нет данных → заглушка; есть `finJson` → `<FinanceTab/>` (стр. 3924). Хвост (~1 255 строк: renderBridgePlate, renderMethodsBlock, renderSectorCharts/Table, renderGmvBlock, renderOilSectorBlock) исполняется ТОЛЬКО при «finMd есть, finJson нет» — таких компаний **1 из 268**. Практически мёртв, CLAUDE.md прав по сути.
- **OverviewView, App.js:352–420** — легаси-Обозреватель, нигде не вызывается (грепом по всему src — ноль ссылок). ~70 строк.
- **ObsLegacyViews.jsx (1 500 строк)** — NewsFeed/MacroView/MarketMaps/ObserverReportView/GeopoliticsView/EarningsFeed/CalendarView импортируются в App.js, но используются только мёртвым OverviewView → весь файл едет в бандл зря. Удаление: −1 570 строк одним PR.
- **Classic-карточка** — `NEO_CARD` (CompanyCardView:1727) отключается только `?classic=1`/localStorage; `!NEO`-ветка в рендере + `MOCK_COMPANIES` (стр. 253, фолбэк на стр. 3183). Скромно по строкам, но захламляет главный файл.
- **DesignSystem.jsx (741) + LiveDepthShowcase.jsx (648)** — dev-витрина `/_design`, статически импортирована в App.js:2 → в прод-бандле. Лениво грузить или вырезать из прода.
- **console.log: всего 3 на весь src** — чисто. Закомментированных глыб кода нет (высокая плотность `//` в ObsPanels — это пояснительные комментарии, стиль проекта, не мусор).

### 3. Бандл (793 KB gzip JS + 83 KB gzip CSS)

Разложение минифицированного main.js по маркерам библиотек (окна 32 KB, gzip-оценка на окно; sourcemaps отключены в craco — точнее не разобрать):

| Слой | ~gzip | Доля |
|------|------|------|
| Собственный код (49 900 строк src) | ~400 KB | ~50% |
| maplibre-gl v6 | ~216 KB | ~27% |
| react-dom + прочие либы (lucide ~40 KB, markdown-стек ~30 KB и пр.) | ~135 KB | ~17% |
| lightweight-charts | ~42 KB | ~5% |

- **maplibre** — только `observer/ObsPanels.jsx` (worker уже вынесен в public/, стр. 15 — полдела сделано). Динамический import = −216 KB на всех страницах без карт, включая лендинг.
- **lightweight-charts** — PortfolioViews + market/ChartPro; лениво = −42 KB с лендинга.
- **lucide-react**: 17 файлов импортируют именованно, tree-shaking работает, но `concatenateModules:false` (craco, анти-OOM) ослабляет минификацию всего бандла — на Vite/esbuild этот костыль не нужен.
- **Зависимости (depcheck вручную)**: все 9 prod-зависимостей используются. Мусор в devDeps: `typescript@4.9.5` + `@types/react*` — **ни одного .ts/.tsx файла и нет tsconfig.json**; `"main": "src/index.tsx"` в package.json — битая ссылка (файл — index.js). `@craco/craco` числится в dependencies, а не devDependencies.
- **Максимум от route-чанков** (по убыванию): (1) карты/maplibre; (2) Обозреватель целиком (ObsPanels + observer-v2.css 5 425 строк); (3) карточка компании (CompanyCardView + FinanceTab + Geo/Governance/Institutions/BusinessModel табы); (4) портфель+lightweight-charts; (5) /_design. Лендинг-first-load реально сжать до ~200–250 KB gzip.
- CSS 528 KB raw / 83 KB gzip одним файлом — вторично, но observer-v2.css тоже уехал бы в чанк Обозревателя.

### 4. Токен-системы (объёмы по грепу src)

| Система | Использований | Где живёт |
|---------|--------------|-----------|
| `obs-*` (классы+токены) | 1 839 | observer-v2.css (937) + ObsPanels (829) + App.js (61) |
| `--cc-*` | 430 | tokens.css (89), company/neo.jsx, screener.css, account.css, geo/finance/market/governance.css |
| `--pf-*` | 298 | PortfolioViews (160) + portfolio-v2.css (120) |
| `--bs-*` (канон) | 282 | basis-design-system.css (119), stress-test (93+22), account (17) |
| classic | 2 упоминания | только флаг `?classic=1` в CompanyCardView |

Канон (`--bs-`) — на 4-м месте по факту использования. По CLAUDE.md `--cc-`/`--pf-`/`obs-` — зеркала тех же значений → **реальная стоимость консолидации низкая, если делать алиасами** (`--cc-bg: var(--bs-surface)` и т.п. в одном файле-мосте): S, риск минимальный, дрейф значений исключается. Полное переименование ~730 вхождений в ~25 файлах — L и почти без пользы для пользователя; не рекомендуется как ближайший шаг. `obs-*` — в основном классы компонентов, не токены; трогать не надо, только их цветовые переменные завести на `--bs-`.

### 5. Роутинг: что БЕЗ URL (подтверждено: pushState/popstate — 0 вхождений в src)

Есть URL: `/company/TICKER/[slug]` (+ статические SEO-страницы через scripts/generate-seo-pages.js), фолбэк `?company=T&tab=X`, dev `/_design`. Всё остальное — state в памяти:
- **Карточки облигаций/фьючерсов/фондов/валюты (BondCard/FuturesCard/FundCard/SpotCard)** — ~3 100 бумаг вообще недостижимы по ссылке. Крупнейшая SEO/шаринг-потеря: скринер облигаций — фича платформы, а результат нельзя послать ссылкой.
- Обозреватель — все 11 секций (news/economy/pulse/maps/calendar/reports/corp-news/macro/geo/institutions/ai).
- Страницы индексов и «страх/жадность», хаб индексов.
- Разделы топ-нава: рынок/скринер/портфель/стресс-тест/ассистент/тарифы/профиль.
- Вкладки внутри Рынка и Скринера.
Следствия: F5 = сброс на лендинг, «поделиться» невозможно, у поисковиков только лендинг+компании, аналитика переходов слепа. Минимальный фикс — query/hash-синхронизация раздела+секции (M); полноценный router + SEO-страницы облигаций — отдельная L-задача.

### 6. Error boundaries

Есть `ViewErrorBoundary` (App.js:732) — классовый, покрывает контент-зону и лендинг, показывает сообщение + текст ошибки + «Повторить», сбрасывается при смене routeKey. Это хорошо. Дыры: (а) TopNav/MobileTabBar/AuthModal и сам App вне boundary — их краш = белый экран; (б) в index.js над `<App/>` ничего нет. Одна обёртка в index.js закрывает (S).

### 7. Состояние и данные

- **Контекстов НЕТ вообще** (`createContext` — 0). Всё через пропсы: `token` и `onSelectCompany` дриллятся App → ObserverV2/PortfolioV2/Screener → панели → элементы (2–4 уровня, широким фронтом — ObserverV2 принимает 14 пропсов). Терпимо по глубине, но каждый новый экран наращивает копипасту сигнатур.
- **164 fetch** в 20 файлах, ни кэша, ни дедупликации, ни abort-контроллеров (точечно есть `alive`-флаги). Дубли: `/api/screener/scored` ×9, `/api/quotes/realtime` ×8, `/api/companies` ×8 (TopNavSearch, CompanyCardResolver, CompaniesView, PortfolioViews…), `/api/market/pulse` ×7.
- **Архитектурный усилитель проблемы**: ObserverV2 ремоунтится при каждом входе на вкладку, а `<main key={activeSection}>` (App.js:324) ремоунтит секцию при каждом переключении → все данные секции перезапрашиваются каждый раз. Мини-кэш уровня модуля (Map по URL с TTL) в едином `useFetch` снял бы 80% лишнего трафика без новых зависимостей.

### 8. Доступность

Систематически — лучше среднего: 160 `aria-label`, aria-current/aria-pressed/aria-expanded в навигации, focus-trap в модалках и мобильной шторке, `focus-visible` 86 вхождений в CSS, `prefers-reduced-motion` в 13 css-файлах, inert на мобильном сайдбаре. Реальные пятна:
- 18 кликабельных `div/span/td` без role/键 (худший — MarketNeo.jsx ×5, скринеры ×6) — не работают с клавиатуры.
- `IconButton` (primitives.jsx:128) не требует aria-label типом — ревью call-sites точечно.
- Контрасты статически не проверить; токены систем задекларированы под контраст — выборочная проверка axe на живом сайте рекомендуется (S).

### 9. CRA + craco: насколько тупик

- react-scripts 5.0.1 — последний релиз (04.2022), CRA официально deprecated; **React 19.2.6 с ним формально не поддерживается** (работает, но каждое обновление экосистемы — лотерея).
- Билд уже упирался в OOM на Timeweb → craco выключает параллельный terser, sourcemaps и `concatenateModules` (= бандл больше, отладка прода невозможна). Это костыли вокруг webpack-памяти, у Vite/esbuild этой проблемы нет.
- Тестов нет (0 файлов) — мигрировать нечего.
- **Оценка миграции на Vite: M (1–2 дня)**: перенос index.html в корень (6 вхождений %PUBLIC_URL%), 59 использований `process.env.REACT_APP_*` → `import.meta.env` или define-шим, JSX в .js (App.js) → настройка esbuild loader или переименование в .jsx, tailwind/postcss — совместимы, generate-seo-pages.js — не зависит от сборщика, maplibre worker-путь (PUBLIC_URL) — проверить. Риск: билд-окружение Timeweb выполняет `npm run build` само — нужен Node 18+. Бонусы: быстрая сборка без OOM, sourcemaps, нормальный code splitting из коробки. Вывод: не пожар, но каждый новый краско-костыль приближает вынужденную миграцию — лучше сделать планово, ПОСЛЕ введения route-чанков не стоит (чанки переедут бесплатно, можно и до).

### 10. Копипаста, просящаяся в хук/утилиту

- `fetch → setLoading → setData → setErr → alive-флаг` — ~53 loading-стейта / 23 error-стейта руками; 17 глухих `catch(() => {})` (ошибки молча съедаются — пользователь видит вечный скелетон). Один `useFetch(url, {ttl})` + модульный кэш закрывает №5, №9 и глухие catch разом; внедрять новыми экранами + по мере касания старых.
- `apiBase()`/`process.env.REACT_APP_API_URL || "http://localhost:8000"` продублирован в десятках файлов — утилита `api.js` (S).
- Форматтеры чисел: часть в design/format.js (хорошо), но локальные `_fmtBig/_num1` в CompanyCardView (стр. 7182+) дублируют их — свести (S).

---

## Рекомендуемый порядок работ

1. **S, сразу**: удалить мёртвое (ObsLegacyViews + OverviewView + хвост renderFinancials) — −2 900 строк, минус риск «правим мёртвое».
2. **S**: динамический import maplibre (и карт-компонентов) — −216 KB gzip везде, где нет карт.
3. **M**: React.lazy route-чанки (Обозреватель / карточка / портфель / скринер / _design) — лендинг ~250 KB gzip.
4. **M**: `useFetch` с модульным кэшем + api.js; закрыть глухие catch.
5. **M**: query/hash-роутинг разделов + deep-link для облигаций (secid) — фундамент под SEO облигаций.
6. **S**: root error boundary; alias-мост `--cc-`/`--pf-` → `--bs-`; вычистить typescript/@types из devDeps.
7. **Планово (M)**: миграция на Vite — снимет OOM-костыли и вернёт sourcemaps.
8. Обновить CLAUDE.md: App.js больше не 8k; гиганты — CompanyCardView.jsx и ObsPanels.jsx; renderFinancials-мёртвый код теперь в CompanyCardView:3927–5181.
