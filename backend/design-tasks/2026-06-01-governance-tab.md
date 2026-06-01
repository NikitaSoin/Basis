# Дизайн-ревью / ТЗ: новая вкладка «Корпоративное управление»

Дата: 2026-06-01
Источник: новая вкладка в карточке компании (inbasis.ru → CompanyCard)
Трудозатраты: **L (день+)** — новая вкладка с 4 секциями, 5 новыми SVG/JSX-компонентами.

---

## Что я увидел

В `frontend/Basis/src/App.js` (единый файл, ~5285 строк) карточка компании — это
компонент `CompanyCard`. Внутри есть таб-бар (строки ~3232–3254) и набор
рендер-функций: `renderOverview`, `renderBusinessProfile`, `renderFinancials`,
`renderDeepDive`, `renderConsilium`, `renderStressTest`. Эталон качества —
`renderFinancials` (строки 2324–2700): аккуратные карточки на `cardStyle`,
заголовки через `cardHead(Icon, title, right)`, таблицы с zebra и tabular-nums,
чистый SVG `miniChart`, «градусник» `fairValueBar`, разбивка markdown по H2 через
`splitH2`, модульный компонент `ScatterMap` (строки 1380–1440).

**Задача:** добавить вкладку «Корпоративное управление» в том же стиле. Данные:
- `GET /api/companies/by-ticker/{ticker}/governance` → JSON (схема в задании)
- `GET /api/companies/by-ticker/{ticker}/governance-summary` → markdown.

Нельзя: внешние библиотеки графиков (recharts несовместим с React 19) — **только
чистый SVG**. Нельзя выдумывать CSS-переменные.

---

## Доступные CSS-переменные (использовать ТОЛЬКО их)

`--accent`, `--accent-fade`, `--accent-text`, `--text-1`, `--text-2`, `--text-3`,
`--bg-surface`, `--bg-card`, `--bg-app`, `--border`, `--border-mid`,
`--positive`, `--negative`, `--pos-fade`, `--neg-fade`.

НЕ вводить `--bg-base`, `--green`, `--surface2` и т.п. — их нет.

---

## Цветовые соглашения (несут смысл, не украшают)

**Тип акционера (`type`)** — заливка сегмента стека/доната. Фиксированная палитра:

| type | цвет | смысл |
|---|---|---|
| `state` | `var(--negative)` | государство (риск для миноритария) |
| `strategic` | `var(--accent)` | стратег |
| `management` | `var(--accent-text)` | менеджмент |
| `institutional` | `var(--text-2)` | институционалы |
| `foreign` | `var(--text-2)` opacity 0.7 | иностранцы |
| `treasury` | `var(--border-mid)` | казначейские |
| `free_float` | `var(--positive)` | свободное обращение (хорошо) |
| `other` | `var(--text-3)` | прочее |

Реализуй как объект `TYPE_COLOR` и `TYPE_LABEL` (рус. подписи для легенды), с
фолбэком `other`. Логика: гос/казначейские/прочее тяготеют к приглушённым/
тревожным тонам, free_float — зелёный (для инвестора это плюс ликвидности).

**Impact прецедента (`impact`)** — метка-точка и border-left карточки:
- `positive` → `var(--positive)` + фон `var(--pos-fade)`
- `neutral` → `var(--text-3)` + фон прозрачный
- `negative` → `var(--negative)` + фон `var(--neg-fade)`

**Severity риска (`severity`)** — border-left и подпись карточки:
- `high` → `var(--negative)`
- `medium` → акцент-жёлтого нет в палитре → используй `var(--accent)` для medium
  НЕ подходит (акцент = кликабельность). Поэтому: `medium` → `#C9A227` инлайн
  (единственное допустимое исключение — жёлтого нет в теме; задай его локальной
  константой `const WARN = "#C9A227"` в начале рендера, прокомментируй).
- `low` → `var(--text-3)`

**Оценки 1–5 (ScoreBar)** — заливка бара по значению:
- score ≥ 4 → `var(--positive)`
- score 3 → `var(--text-2)`
- score ≤ 2 → `var(--negative)`

---

## Структура вкладки (порядок секций сверху вниз)

0. **Плашка data_quality** (если `meta.data_quality === "low"`) — узкая полоса
   сверху, фон `var(--neg-fade)`, border-left `var(--negative)`, текст
   «Данные ограниченной полноты — выводы предварительные».
1. **Структура владения** (StackedOwnershipBar + free float + контролирующий +
   классы акций).
2. **Дивиденды** (таблица истории + DividendChart + «Политика vs практика»).
3. **Прецеденты по миноритариям** (лента PrecedentCard + общий score).
4. **Качество управления и риски** (6 ScoreBar + overall крупно + strengths +
   RiskCard + мини-факты СД/прозрачность).
5. **Сопроводительный текст** из summary.md — короткими секциями по H2 (`splitH2` +
   `mdc`), НЕ простыня.

---

## Правка 1: Wiring (state + fetch + таб + диспетчеризация рендера)

### 1a. State (рядом с finJson, строки ~1723–1727)
```jsx
const [govMd, setGovMd] = useState(null);
const [govJson, setGovJson] = useState(null);
const [govLoading, setGovLoading] = useState(true);
```

### 1b. Fetch-effect (скопировать паттерн financials, после строки ~1804)
```jsx
useEffect(() => {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  setGovLoading(true);
  setGovMd(null);
  setGovJson(null);
  const base = `${apiUrl}/api/companies/by-ticker/${company.ticker}`;
  Promise.all([
    fetch(`${base}/governance-summary`).then(r => r.ok ? r.text() : null).catch(() => null),
    fetch(`${base}/governance`).then(r => r.ok ? r.json() : null).catch(() => null),
  ]).then(([md, js]) => { setGovMd(md); setGovJson(js); setGovLoading(false); });
}, [company.ticker]);
```

### 1c. Таб-бар — добавить пункт после «Финансы» (строки ~3232–3239)
```jsx
{ id: "finance", label: "Финансы" },
{ id: "governance", label: "Управление" },   // ← новый
{ id: "deep", label: "Глубокий разбор" },
```
Подпись «Управление» (не «Корпоративное управление») — иначе таб-бар переполнится
на мобильном. Полное название вынести в заголовок секции внутри вкладки.

### 1d. Диспетчеризация (строки ~3256–3263)
```jsx
{tab === "governance" && renderGovernance()}
```

---

## Правка 2: Каркас `renderGovernance()`

Разместить рядом с `renderFinancials` (после строки ~2700). Переиспользовать
локальные хелперы из паттерна финансов (объявить заново внутри функции — они там
локальные): `cardStyle`, `cardHead`, `splitH2`, `mdc`, `fmt`.

```jsx
const renderGovernance = () => {
  if (govLoading) return (
    <div className="flex items-center justify-center py-16">
      <div className="text-slate-400 animate-pulse">Загружаем данные по управлению...</div>
    </div>
  );
  if (!govMd && !govJson) return renderComingSoon("Корпоративное управление");

  const WARN = "#C9A227"; // жёлтого нет в теме — единственное инлайн-исключение для severity=medium
  const meta = govJson?.meta || {};
  const own = govJson?.ownership || {};
  const div = govJson?.dividends || {};
  const mino = govJson?.minority_treatment || {};
  const gq = govJson?.governance_quality || {};
  const flags = govJson?.data_flags || [];

  const cardStyle = { background: "var(--bg-surface)", borderRadius: 12, padding: 18, border: "1px solid var(--border)" };
  const cardHead = (Icon, title, right) => (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
      <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-1)", display: "flex", alignItems: "center", gap: 8 }}>
        <Icon size={16} style={{ color: "var(--accent)" }} />{title}
      </h4>
      {right}
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {meta.data_quality === "low" && <DataQualityBanner flags={flags} />}
      {/* секция 1 — владение */}
      {/* секция 2 — дивиденды */}
      {/* секция 3 — прецеденты */}
      {/* секция 4 — качество и риски */}
      {/* секция 5 — текст summary по H2 */}
    </div>
  );
};
```

Иконки берём из уже импортированного набора (Tabler/lucide), которым пользуется
`renderFinancials`: для секций используем `Users` (владение), `Coins`/`TrendingUp`
(дивиденды), `Scale` (миноритарии), `ShieldCheck` (качество), `Info` (текст).
Если иконки нет в импорте — добавить в общий импорт-блок вверху файла. Размер 16,
цвет `var(--accent)`.

---

## Правка 3: Секция 1 — СТРУКТУРА ВЛАДЕНИЯ

Карточка `cardStyle`, заголовок «Структура владения».

Состав:
- **StackedOwnershipBar** (горизонтальный стек на 100% ширины) + легенда.
- Крупная плашка **free float** справа от заголовка (`cardHead(... , right)`):
  `own.free_float_pct`% моноширинным, подпись «free float», цвет `var(--positive)`.
- Плашка контролирующего собственника / конечного бенефициара (border-left).
- Карточки классов акций (`own.share_classes`) — грид 2 колонки.

### Компонент `StackedOwnershipBar`
Чистый SVG-стек по `shareholders` (сортировать по `stake_pct` убыв., но `free_float`
и `treasury` — в конец). Высота бара 28px, скруглённые края. Тонкие белые
разделители между сегментами (`stroke var(--bg-surface)` 1px). Сегмент < 3% не
подписывать внутри — только в легенде. Контролирующий (`is_controlling`) —
обвести `stroke var(--text-1)` 1.5px.

```jsx
function StackedOwnershipBar({ shareholders = [] }) {
  const order = { free_float: 1, treasury: 2 };
  const data = [...shareholders]
    .filter(s => typeof s.stake_pct === "number" && s.stake_pct > 0)
    .sort((a, b) => (order[a.type] || 0) - (order[b.type] || 0) || b.stake_pct - a.stake_pct);
  const total = data.reduce((s, x) => s + x.stake_pct, 0) || 100;
  const W = 100, H = 28; // viewBox в процентах ширины
  let acc = 0;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: 28, display: "block", borderRadius: 6, overflow: "hidden" }}>
        {data.map((s, i) => {
          const w = (s.stake_pct / total) * W;
          const x = acc; acc += w;
          const c = TYPE_COLOR[s.type] || TYPE_COLOR.other;
          return (
            <g key={i}>
              <rect x={x} y={0} width={w} height={H} fill={c}
                stroke={s.is_controlling ? "var(--text-1)" : "var(--bg-surface)"}
                strokeWidth={s.is_controlling ? 1.5 : 0.5} vectorEffect="non-scaling-stroke" />
              {w > 9 && <text x={x + w / 2} y={H / 2 + 3} textAnchor="middle" fontSize="7"
                fill="var(--bg-app)" fontWeight="600" style={{ fontVariantNumeric: "tabular-nums" }}>
                {s.stake_pct.toFixed(0)}%</text>}
            </g>
          );
        })}
      </svg>
      {/* легенда */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", marginTop: 12 }}>
        {data.map((s, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-2)" }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: TYPE_COLOR[s.type] || TYPE_COLOR.other, flexShrink: 0 }} />
            <span style={{ color: "var(--text-1)" }}>{s.name}</span>
            <span style={{ fontFamily: "monospace", fontVariantNumeric: "tabular-nums", color: "var(--text-1)", fontWeight: 600 }}>{s.stake_pct.toFixed(1)}%</span>
            {s.is_controlling && <span style={{ fontSize: 10, color: "var(--text-3)" }}>контроль</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
```
> `vectorEffect="non-scaling-stroke"` обязателен из-за `preserveAspectRatio="none"`
> (иначе разделители растянутся). Текст внутри сегментов читается на любой заливке
> цветом `var(--bg-app)` — фон приложения, т.е. контраст к цветным сегментам. Если
> на светлой теме контраст слабый — допустимо переключить на `#fff`/`#000` по
> яркости сегмента; на старте оставь `var(--bg-app)`.

Опциональный донат НЕ обязателен — stacked-bar самодостаточен и компактнее. Если
разработчик хочет донат, делать как `<circle>` со `stroke-dasharray` — но это
nice-to-have, не блокер.

### Плашка контролирующего / бенефициара
Под баром, две строки фактов:
```jsx
<div style={{ marginTop: 14, padding: 12, borderRadius: 8, background: "var(--bg-card)", borderLeft: "3px solid var(--accent)" }}>
  <Fact label="Контролирующий собственник" value={own.controlling_shareholder || "—"} />
  <Fact label="Конечный бенефициар" value={own.ultimate_beneficiary || "—"} />
  <Fact label="Концентрация владения" value={own.ownership_concentration || "—"} />
  <Fact label="Доля государства" value={typeof own.state_share_pct === "number" ? own.state_share_pct + "%" : "—"} />
</div>
```
`Fact` — простой ряд: слева `var(--text-3)` 12px, справа `var(--text-1)` 13px 600.

### Карточки классов акций (`own.share_classes`)
Грид `repeat(auto-fit, minmax(220px, 1fr))`, gap 12. Каждая карточка:
```jsx
<div style={{ ...cardStyle, background: "var(--bg-card)", padding: 14 }}>
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
    <span style={{ fontWeight: 700, color: "var(--text-1)", fontSize: 13 }}>
      {sc.class === "preferred" ? "Привилегированные (ап)" : "Обыкновенные (ао)"}
    </span>
    <span style={{ fontFamily: "monospace", fontSize: 12, color: "var(--text-3)" }}>{sc.ticker}</span>
  </div>
  <div style={{ display: "flex", gap: 18, marginTop: 10 }}>
    <Metric label="Голосов / акцию" value={sc.votes_per_share} />
    <Metric label="Доля капитала" value={typeof sc.share_of_capital_pct === "number" ? sc.share_of_capital_pct + "%" : "—"} />
  </div>
  <div style={{ fontSize: 12, color: "var(--text-2)", marginTop: 10, lineHeight: 1.5 }}>
    <b style={{ color: "var(--text-1)" }}>Дивиденд:</b> {sc.dividend_rule || "—"}
  </div>
  {sc.note && <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6 }}>{sc.note}</div>}
</div>
```
`Metric` — вертикальный: подпись `var(--text-3)` 11px сверху, значение моно
`var(--text-1)` 15px 600 снизу.

---

## Правка 4: Секция 2 — ДИВИДЕНДЫ

Карточка `cardStyle`, заголовок «Дивиденды». Три блока внутри.

### 4a. Сводка политики (`div.policy`) — узкая плашка вверху
Если `policy.exists`: показать `policy.summary`, под ним мелкие факты
`target_basis`, `target_payout_pct`%, `frequency`, источник `source` (мелким
`var(--text-3)`). Если `!exists` — плашка `var(--neg-fade)` «Формальной
дивполитики нет».

### 4b. DividendChart (SVG bar по годам)
По образцу `miniChart` из финансов, но: бары разного цвета —
`paid===false` (пропуск) → `var(--text-3)` opacity 0.4; `special===true` →
`var(--accent)`; обычная выплата → `var(--positive)`. Подпись года под баром,
значение DPS над баром мелким.

```jsx
function DividendChart({ history = [] }) {
  const data = [...history].sort((a, b) => a.year - b.year);
  if (!data.length) return null;
  const W = 360, H = 150, padX = 8, padTop = 20, padBot = 22;
  const vals = data.map(d => d.dps || 0);
  const max = Math.max(...vals, 0) || 1;
  const n = data.length;
  const slot = (W - 2 * padX) / n;
  const bw = Math.min(34, slot * 0.6);
  const yAt = v => padTop + (1 - v / max) * (H - padTop - padBot);
  const colorOf = d => d.paid === false ? "var(--text-3)" : d.special ? "var(--accent)" : "var(--positive)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {data.map((d, i) => {
        const x = padX + i * slot + slot / 2;
        const v = d.dps || 0;
        const y = d.paid === false ? H - padBot - 2 : yAt(v);
        const h = d.paid === false ? 2 : Math.max(H - padBot - yAt(v), 1);
        return (
          <g key={i}>
            <rect x={x - bw / 2} y={y} width={bw} height={h} rx="2"
              fill={colorOf(d)} opacity={d.paid === false ? 0.4 : 0.9} />
            {d.paid !== false && v > 0 &&
              <text x={x} y={y - 4} textAnchor="middle" fontSize="8" fill="var(--text-2)"
                style={{ fontVariantNumeric: "tabular-nums" }}>{v}</text>}
            {d.paid === false &&
              <text x={x} y={H - padBot - 6} textAnchor="middle" fontSize="8" fill="var(--text-3)">×</text>}
            <text x={x} y={H - 6} textAnchor="middle" fontSize="8.5" fill="var(--text-3)"
              fontFamily="monospace">{String(d.year).slice(2)}</text>
          </g>
        );
      })}
    </svg>
  );
}
```
Под графиком — мини-легенда цветов (выплата / спецдивиденд / не платили), точками
как в легенде владения.

### 4c. Таблица истории (`div.history`)
Колонки: Год · DPS · Payout % · Див.доходность % · Флаг. Числа вправо, моно,
tabular-nums, zebra `ri % 2 ? var(--bg-card)`. Флаг: «спец» (`var(--accent)`) /
«не платили» (`var(--text-3)`) / `paid` без флага — пусто. Заголовки колонок —
11px uppercase `var(--text-3)` (как `finTable`).

### 4d. Блок «Политика vs практика» (`div.policy_vs_practice`)
Отдельная плашка с border-left, цвет по `assessment`:
- содержит «соблюда»/«стабиль»/положительная формулировка → `var(--positive)` + `var(--pos-fade)`
- «наруша»/«пропуск»/«непредсказуем» → `var(--negative)` + `var(--neg-fade)`
- иначе нейтрально `var(--text-3)`
Делай через явный маппинг по ключевым словам в `assessment`; не угадывай строки
наобум — сделай функцию `assessTone(text)` с понятными правилами и фолбэком
neutral. Внутри: крупно `assessment`, ниже `commentary` (13px var(--text-2)),
если `skipped_years.length` — строка «Пропущенные годы: 2020, 2022» моно.

---

## Правка 5: Секция 3 — ПРЕЦЕДЕНТЫ ПО МИНОРИТАРИЯМ

Карточка `cardStyle`, заголовок «Отношение к миноритариям», справа в `cardHead` —
крупный score (`mino.score`/5) как ScoreBar-инлайн или текст
`{mino.score}/5`. Под заголовком `mino.summary` (13px). Ниже — лента
`PrecedentCard` (вертикальный стек, gap 10), сортировка по `year` убыв.

### Компонент `PrecedentCard`
```jsx
function PrecedentCard({ p }) {
  const tone = {
    positive: { c: "var(--positive)", bg: "var(--pos-fade)" },
    negative: { c: "var(--negative)", bg: "var(--neg-fade)" },
  }[p.impact] || { c: "var(--text-3)", bg: "transparent" };
  return (
    <div style={{ background: tone.bg, borderLeft: `3px solid ${tone.c}`,
      borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: tone.c, flexShrink: 0 }} />
        <span style={{ fontWeight: 600, color: "var(--text-1)", fontSize: 13 }}>{p.title}</span>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-3)", fontFamily: "monospace" }}>{p.year}</span>
      </div>
      <div style={{ fontSize: 11, color: "var(--text-3)", margin: "2px 0 0 16px" }}>{p.type}</div>
      <div style={{ fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5, margin: "6px 0 0 16px" }}>{p.description}</div>
    </div>
  );
}
```

---

## Правка 6: Секция 4 — КАЧЕСТВО УПРАВЛЕНИЯ И РИСКИ

Карточка `cardStyle`, заголовок «Качество управления». Внутри 4 подблока.

### 6a. Overall крупно (`gq.scores.overall`) — справа в `cardHead`
Большое число `{overall.score}/5` (24px 700, цвет по порогу: ≥4 positive, 3
text-1, ≤2 negative). Под ним `overall.rationale` мелким `var(--text-3)`.

### 6b. 6 шкал — ScoreBar
Грид `repeat(auto-fit, minmax(240px, 1fr))`, gap 12. Шкалы:
`ownership_transparency`, `minority_protection`, `dividend_consistency`,
`board_independence`, `disclosure`, `overall`. Подписи рус.:
```jsx
const SCORE_LABELS = {
  ownership_transparency: "Прозрачность владения",
  minority_protection: "Защита миноритариев",
  dividend_consistency: "Стабильность дивидендов",
  board_independence: "Независимость СД",
  disclosure: "Раскрытие информации",
  overall: "Интегральная оценка",
};
```

### Компонент `ScoreBar`
5 сегментов-«пилюль» (наглядно, без библиотек). Заполненные — цветом по score,
пустые — `var(--bg-card)`. Rationale — мелким текстом под баром (мобильно проще
тапа; задание допускает «по тапу/мелким текстом» — выбираем мелкий текст, без
JS-состояния).
```jsx
function ScoreBar({ label, score, rationale }) {
  const s = Math.max(0, Math.min(5, Math.round(score || 0)));
  const c = s >= 4 ? "var(--positive)" : s === 3 ? "var(--text-2)" : "var(--negative)";
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 12.5, color: "var(--text-1)" }}>{label}</span>
        <span style={{ fontFamily: "monospace", fontSize: 12, color: c, fontWeight: 600 }}>{s}/5</span>
      </div>
      <div style={{ display: "flex", gap: 3 }}>
        {[1,2,3,4,5].map(i => (
          <span key={i} style={{ flex: 1, height: 6, borderRadius: 3,
            background: i <= s ? c : "var(--bg-card)" }} />
        ))}
      </div>
      {rationale && <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6, lineHeight: 1.45 }}>{rationale}</div>}
    </div>
  );
}
```

### 6c. Strengths (зелёные) + Risks (RiskCard)
Два столбца на десктопе (`repeat(auto-fit, minmax(260px, 1fr))`), на мобильном —
один. Strengths — список плашек `var(--pos-fade)` border-left `var(--positive)`,
короткий текст. Risks — `RiskCard` по severity.

### Компонент `RiskCard`
```jsx
function RiskCard({ r, warn }) {
  const tone = { high: "var(--negative)", medium: warn, low: "var(--text-3)" }[r.severity] || "var(--text-3)";
  const SEV = { high: "высокий", medium: "средний", low: "низкий" }[r.severity] || r.severity;
  return (
    <div style={{ borderLeft: `3px solid ${tone}`, background: "var(--bg-card)",
      borderRadius: 8, padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span style={{ fontWeight: 600, color: "var(--text-1)", fontSize: 13 }}>{r.title}</span>
        <span style={{ marginLeft: "auto", fontSize: 10.5, fontWeight: 600, color: tone,
          textTransform: "uppercase", letterSpacing: "0.03em" }}>{SEV}</span>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5, marginTop: 6 }}>{r.description}</div>
    </div>
  );
}
```
`warn` прокидывать = `WARN` (`#C9A227`).

### 6d. Мини-факты СД и прозрачности (`gq.board`, `gq.transparency`)
Горизонтальная лента мини-метрик (как `Metric`-ряд), grid auto-fit:
- Размер СД (`board.size`)
- Независимых директоров (`board.independent_directors`,
  `board.independent_share_pct`%)
- Комитеты (`board.committees.join(", ")` или количество)
- Отчётность по МСФО (`transparency.ifrs_reporting` → «Да»/«Нет»)
- Регулярность (`transparency.reporting_regularity`)
- Уровень раскрытия (`transparency.disclosure_level`)

---

## Правка 7: Секция 5 — текст summary.md

В самом низу. `splitH2(govMd)` → для каждой секции `cardStyle` с заголовком H2 и
телом через `<ReactMarkdown remarkPlugins={[remarkGfm]} components={mdc}>`. Это
сопроводиловка — НЕ дублировать ей цифры из карточек. Если `govMd` пуст — секцию
не рендерить.

---

## Мобильная адаптация

- Все гриды — `repeat(auto-fit, minmax(...px, 1fr))`, схлопываются в 1 колонку.
- SVG-компоненты — `width: "100%"`, `height: auto` (кроме StackedOwnershipBar:
  фиксированная высота 28px, ширина 100%).
- Таб-бар уже `overflowX: "auto"` — новый таб «Управление» туда влезает.
- В `cardHead` уже `flexWrap: "wrap"` — крупные правые элементы (free float,
  overall) переносятся под заголовок на узком экране.
- Легенды — `flexWrap: "wrap"`.
- Минимальный размер тела текста 12px, заголовки секций 14px (как в финансах).

---

## Размещение новых компонентов

`StackedOwnershipBar`, `DividendChart`, `ScoreBar`, `PrecedentCard`, `RiskCard`,
`DataQualityBanner` — объявить как **отдельные функции верхнего уровня** рядом с
`ScatterMap` (строка ~1380), НЕ внутри `CompanyCard` (чтобы не пересоздавались на
каждый рендер и были переиспользуемы). `TYPE_COLOR`, `TYPE_LABEL`, `SCORE_LABELS`
— модульные константы там же. `Fact`, `Metric` — мелкие, можно объявить рядом или
инлайнить.

---

## Чего НЕ менять (важно!)

- Не трогать `renderFinancials`, `ScatterMap`, `splitH2`, `mdc`, `cardStyle`,
  `cardHead` — копируй паттерн, не рефактори существующее.
- Не вводить внешние графические библиотеки.
- Не менять backend-эндпоинты — они уже есть (`/governance`,
  `/governance-summary`).
- Не вводить новые CSS-переменные (единственное исключение — локальная константа
  `WARN = "#C9A227"` для severity=medium, т.к. жёлтого в палитре нет;
  прокомментировать).
- Не показывать всю историю дивидендов простынёй — таблица + график, длинную
  историю при необходимости прятать под `<details>` (паттерн `tableSection`).

---

## Зависимости / открытые вопросы

- Иконки секций (`Users`, `Coins`, `Scale`, `ShieldCheck`, `Coins`/`TrendingUp`)
  должны быть в импорт-блоке вверху `App.js`. Если каких-то нет — добавить в
  существующий импорт из того же пакета иконок, что и `Target`, `ChevronDown`,
  `Info`.
- Жёлтый для severity=medium отсутствует в теме — введён локально `#C9A227`.
  Если владелец продукта захочет добавить `--warning` в CSS-переменные позже —
  заменить эту константу одной правкой.
- Текст внутри сегментов StackedOwnershipBar цветом `var(--bg-app)` может слабо
  контрастировать на светлой теме на светлых сегментах — проверить визуально, при
  необходимости подобрать контраст по яркости сегмента.
