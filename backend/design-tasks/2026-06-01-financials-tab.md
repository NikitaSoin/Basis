# Дизайн-ревью: вкладка «Финансы» карточки компании (renderFinancials)
Дата: 2026-06-01
Источник: inbasis.ru → карточка компании → таб «Финансы»
Компонент: `frontend/Basis/src/App.js`, функция `renderFinancials` (строки ~2227–2349)
Данные: `GET /api/companies/by-ticker/{ticker}/financials` (JSON, схема — `.claude/agents/financial-analyst.md`, профили `standard` и `bank`) + `/financials-summary` (markdown)

---

## Что я увидел

Сверху — аккуратный блок ключевых мультипликаторов (P/E, P/S, P/B, EV/EBITDA, ND/EBITDA, ROE) чипами, коридор справедливой цены и бейдж аномалии. Это хорошо. Но **ниже вся отчётность (P&L, баланс, ОДДС, динамика, методы оценки) выводится сплошной markdown-простынёй** из `financials_summary.md`. То есть самые ценные числа (выручка/прибыль по годам, дельты, методы оценки) приходят в JSON структурированно (`income_statement`, `balance_sheet`, `cash_flow`, `valuation.methods`), но рисуются как абзацы текста. Инвестор не может сравнить разряды по годам, не видит тренд, не видит таблицу методов оценки.

## Что не работает (приоритизировано)

1. **[КРИТИЧНО] Вся отчётность — текстом, а не таблицами.** Числа из `income_statement.*`, `balance_sheet.*`, `cash_flow.*` (массивы по `meta.fiscal_years`) есть в JSON, но рендерятся через markdown как проза. Глаз не может сравнить «выручка 2023 vs 2024», нет выравнивания разрядов, нет дельт г/г. Для финансового продукта это главный провал.
2. **[КРИТИЧНО] Нет визуализации тренда.** Динамика выручки / чистой прибыли / маржи по годам — это первое, что инвестор хочет увидеть глазами. Сейчас тренд надо вычитывать из текста. Графической библиотеки нет — но SVG из массивов рисуется в 40 строк.
3. **[ВАЖНО] Методы оценки спрятаны в тексте.** `valuation.methods[]` — это таблица (метод / справедливая цена / горизонт / статус). Показывается только финальный коридор. Инвестор не видит, КАК получен коридор, какие методы дали верх/низ, что помечено `insufficient_data`.
4. **[ВАЖНО] Коридор справедливой цены не выделен.** `fair_value_range` (conservative/base + current_price + upside/downside) — это главный вывод вкладки, а сейчас это одна строка мелким текстом. Должен быть визуальный «градусник»: где текущая цена внутри коридора.
5. **[ВАЖНО] Бейдж аномалии — жёлтая простыня.** `anomaly_note` у SNGS — это 4 строки густого текста жёлтым по жёлтому фону (низкий контраст, читать тяжело). Должна быть сворачиваемая карточка: заголовок-предупреждение всегда виден, детали — по клику.
6. **[МИНОР] `financials_summary.md` дублирует то, что теперь будет в таблицах.** После добавления таблиц текст должен стать коротким сопровождением РЯДОМ с цифрами (по секциям H2), а не повторять числа.
7. **[МИНОР] Хардкод цветов.** В текущем коде дельты раскрашены `#22c55e/#ef4444` вместо проектных `var(--positive)` / `var(--negative)`. Привести к переменным.

## Контракт данных (важно для реализации)

- Все ряды отчётности — **массивы по `meta.fiscal_years`**, `null` где данных нет (см. ROSN, SNGS — много `null` в хвостах). Рендер ОБЯЗАН переживать `null`: пропуск ячейки = «—», дельта от `null` не считается.
- Длина массива может НЕ совпадать с `fiscal_years` теоретически — всегда индексируйся по позиции года и бери `arr?.[i] ?? null`.
- **Банковский профиль** (`meta.profile === "bank"`): НЕТ `income_statement`/`cash_flow`. Вместо них `bank_pnl` (net_interest_income, net_fee_income, operating_income, provisions, operating_expenses, net_profit) и `bank_metrics` (nim, cost_of_risk, cir, roe, roa, capital_adequacy, loan_portfolio, deposits). `balance_sheet` усечён (total_assets, total_equity, book_value_per_share). Таблицы P&L/ОДДС/баланса должны **деградировать**: если блок отсутствует — секция не рендерится, ошибки нет.
- `valuation.methods[]` — у элемента может НЕ быть `fair_value_per_share` (null) и быть `status: "insufficient_data" | "not_applicable" | "ok"`. Горизонт — `horizon: "intrinsic_now" | "12m"`.
- Слишком длинные ряды (ROSN — 10 лет) на узком экране: таблица скроллится по X (как в `renderBusinessProfile`).

---

## Что предлагаю (конкретно)

Новая структура вкладки сверху вниз:
1. Блок мультипликаторов (**оставить как есть**, только цвета на переменные).
2. **Коридор справедливой цены** — выделенный «градусник» (новый блок, см. Правка 2).
3. **Графики динамики** — выручка + чистая прибыль (столбцы) и маржа (линия), SVG (Правка 3).
4. **Таблицы по годам** — P&L, Баланс, ОДДС (или Bank P&L + Bank-метрики), с дельтами г/г (Правка 4).
5. **Методы оценки** — таблица (Правка 5).
6. **Бейдж аномалии** — сворачиваемая карточка (Правка 6).
7. **Текст из summary.md** — короткими секциями по H2, рядом с таблицами, не сплошняком (Правка 7).

Все блоки — в едином визуальном языке: карточка `background: var(--bg-surface)`, `border: 1px solid var(--border)`, `borderRadius: 12`, заголовок с lucide-иконкой 16px цвета `var(--accent)`.

---

## Готовый JSX/CSS

> Всё ниже — вставлять ВНУТРЬ `renderFinancials`. Хелперы (`fmt`, `lastNN`) уже есть в функции — переиспользуй. Иконки добавь в общий импорт lucide-react (`TrendingUp`, `Scale`, `Wallet`, `Target`, `ChevronDown`, `AlertTriangle`).

### 0. Общие хелперы (добавить в начало `renderFinancials`, после `fmt`)

```jsx
const years = meta.fiscal_years || [];
const at = (arr, i) => (Array.isArray(arr) ? (arr[i] ?? null) : null);
const isBank = meta.profile === "bank";

// форматирование больших чисел отчётности (млн → читаемо)
const fmtBig = (v) => {
  if (typeof v !== "number") return "—";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return (v / 1_000_000).toFixed(2) + " трлн";
  if (abs >= 1_000) return (v / 1_000).toFixed(1) + " млрд";
  return v.toLocaleString("ru-RU");
};
// дельта год-к-году в % между двумя соседними значениями
const yoy = (cur, prev) =>
  (typeof cur === "number" && typeof prev === "number" && prev !== 0)
    ? ((cur - prev) / Math.abs(prev)) * 100
    : null;

const cardStyle = {
  background: "var(--bg-surface)", borderRadius: 12, padding: 18,
  border: "1px solid var(--border)",
};
const cardHead = (Icon, title, right) => (
  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
    <h4 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-1)", display: "flex", alignItems: "center", gap: 8 }}>
      <Icon size={16} style={{ color: "var(--accent)" }} />{title}
    </h4>
    {right}
  </div>
);
```

### 1. Таблица отчётности по годам — компонент `FinTable`

Универсальная таблица: заголовок-колонки = годы, строки = метрики. Числа моноширинно и вправо, опциональная строка-дельта г/г по знаку. Корректно ест `null`.

```jsx
// rows: [{ label, arr, fmt?: fn, delta?: bool, bold?: bool, muted?: bool }]
const FinTable = ({ rows }) => (
  <div style={{ overflowX: "auto", margin: "2px 0" }}>
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left", padding: "6px 10px", color: "var(--text-3)", fontWeight: 600, fontSize: 11, textTransform: "uppercase", letterSpacing: "0.04em", borderBottom: "1px solid var(--border-mid)", position: "sticky", left: 0, background: "var(--bg-surface)" }}>
            Показатель
          </th>
          {years.map((y, i) => (
            <th key={i} style={{ textAlign: "right", padding: "6px 10px", color: "var(--text-3)", fontWeight: 600, fontSize: 11, borderBottom: "1px solid var(--border-mid)", whiteSpace: "nowrap" }}>
              {y}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => {
          const f = row.fmt || fmtBig;
          return (
            <tr key={ri}
              onMouseEnter={e => e.currentTarget.style.background = "var(--accent-fade)"}
              onMouseLeave={e => e.currentTarget.style.background = ri % 2 ? "var(--bg-card)" : "transparent"}
              style={{ background: ri % 2 ? "var(--bg-card)" : "transparent" }}>
              <td style={{ padding: "6px 10px", color: row.muted ? "var(--text-3)" : "var(--text-2)", fontWeight: row.bold ? 600 : 400, whiteSpace: "nowrap", position: "sticky", left: 0, background: "inherit", fontSize: row.muted ? 12 : 13 }}>
                {row.label}
              </td>
              {years.map((y, i) => {
                const v = at(row.arr, i);
                const d = row.delta ? yoy(v, at(row.arr, i - 1)) : null;
                return (
                  <td key={i} style={{ padding: "6px 10px", textAlign: "right", color: row.bold ? "var(--text-1)" : "var(--text-2)", fontWeight: row.bold ? 600 : 400, fontFamily: "monospace", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                    {v == null ? <span style={{ color: "var(--text-3)" }}>—</span> : f(v)}
                    {d != null && (
                      <span style={{ display: "block", fontSize: 10.5, fontWeight: 600, color: d >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {d >= 0 ? "+" : ""}{d.toFixed(1)}%
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  </div>
);
```

Использование (стандартный профиль) — три карточки в свёрнутых `<details>` (P&L открыт, остальное свёрнуто):

```jsx
const is = finJson?.income_statement || {};
const bs = finJson?.balance_sheet || {};
const cf = finJson?.cash_flow || {};
const m  = is.margins || {};

const pnlRows = !isBank ? [
  { label: "Выручка",          arr: is.revenue,          bold: true, delta: true },
  { label: "EBITDA",           arr: is.ebitda,           delta: true },
  { label: "Операц. прибыль",  arr: is.operating_profit, delta: true },
  { label: "Чистая прибыль",   arr: is.net_profit,       bold: true, delta: true },
  { label: "Маржа EBITDA, %",  arr: m.ebitda_margin, fmt: v => fmt(v, 1) + "%", muted: true },
  { label: "Чистая маржа, %",  arr: m.net_margin,    fmt: v => fmt(v, 1) + "%", muted: true },
] : [];

const bsRows = [
  { label: "Активы",        arr: bs.total_assets,      bold: true },
  { label: "Капитал",       arr: bs.total_equity },
  { label: "Обязательства", arr: bs.total_liabilities },
  { label: "Чистый долг",   arr: bs.net_debt },
  { label: "ND / EBITDA",   arr: bs.ratios?.net_debt_ebitda, fmt: v => fmt(v, 2) + "×", muted: true },
].filter(r => Array.isArray(r.arr) && r.arr.some(x => x != null));

const cfRows = !isBank ? [
  { label: "Операц. поток (CFO)", arr: cf.cfo, bold: true },
  { label: "CapEx",               arr: cf.capex },
  { label: "FCF",                 arr: cf.fcf, bold: true, delta: true },
  { label: "FCF-маржа, %",        arr: cf.ratios?.fcf_margin, fmt: v => fmt(v, 1) + "%", muted: true },
].filter(r => Array.isArray(r.arr) && r.arr.some(x => x != null)) : [];

// банковский профиль
const bp = finJson?.bank_pnl || {};
const bm = finJson?.bank_metrics || {};
const bankPnlRows = isBank ? [
  { label: "Чистый проц. доход",  arr: bp.net_interest_income, bold: true, delta: true },
  { label: "Чистый комис. доход", arr: bp.net_fee_income, delta: true },
  { label: "Операц. доходы",      arr: bp.operating_income },
  { label: "Резервы",             arr: bp.provisions },
  { label: "Чистая прибыль",      arr: bp.net_profit, bold: true, delta: true },
] : [];
const bankMetricRows = isBank ? [
  { label: "ЧПМ (NIM), %",        arr: bm.nim, fmt: v => fmt(v, 2) + "%", muted: true },
  { label: "Стоимость риска, %",  arr: bm.cost_of_risk, fmt: v => fmt(v, 2) + "%", muted: true },
  { label: "CIR, %",              arr: bm.cir, fmt: v => fmt(v, 1) + "%", muted: true },
  { label: "ROE, %",              arr: bm.roe, fmt: v => fmt(v, 1) + "%", muted: true },
  { label: "Достаточность кап., %", arr: bm.capital_adequacy, fmt: v => fmt(v, 1) + "%", muted: true },
] : [];

// рендер-обёртка одной сворачиваемой секции таблицы
const TableSection = ({ icon: Icon, title, rows, open = false }) =>
  rows && rows.length ? (
    <details open={open} style={cardStyle}>
      <summary style={{ cursor: "pointer", listStyle: "none", display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 700, color: "var(--text-1)" }}>
        <Icon size={16} style={{ color: "var(--accent)" }} />{title}
        <ChevronDown size={15} style={{ color: "var(--text-3)", marginLeft: "auto" }} />
      </summary>
      <div style={{ marginTop: 12 }}><FinTable rows={rows} /></div>
    </details>
  ) : null;
```

…и в JSX-выводе:

```jsx
{isBank ? (
  <>
    <TableSection icon={BarChart2} title="Отчёт о прибылях (банк)" rows={bankPnlRows} open />
    <TableSection icon={Target}    title="Банковские метрики"      rows={bankMetricRows} />
    <TableSection icon={Scale}     title="Баланс"                  rows={bsRows} />
  </>
) : (
  <>
    <TableSection icon={BarChart2} title="Прибыли и убытки (P&L)" rows={pnlRows} open />
    <TableSection icon={Scale}     title="Баланс"                 rows={bsRows} />
    <TableSection icon={Wallet}    title="Денежные потоки (ОДДС)" rows={cfRows} />
  </>
)}
```

### 2. Коридор справедливой цены — «градусник»

Выделенный блок: где текущая цена относительно conservative/base. Заменяет нынешнюю строку «Справедливая цена:».

```jsx
const FairValueBar = ({ fvr, currency }) => {
  const lo = fvr.conservative, hi = fvr.base, cur = fvr.current_price ?? meta.last_price;
  if (typeof lo !== "number" || typeof hi !== "number" || typeof cur !== "number") return null;
  // шкала с запасом 15% по краям
  const min = Math.min(lo, cur) * 0.92, max = Math.max(hi, cur) * 1.08;
  const pos = v => ((v - min) / (max - min)) * 100;
  const up = fvr.upside_downside_pct;
  return (
    <div style={cardStyle}>
      {cardHead(Target, "Справедливая стоимость", typeof up === "number" && (
        <span style={{ fontSize: 15, fontWeight: 700, color: up >= 0 ? "var(--positive)" : "var(--negative)" }}>
          {up >= 0 ? "▲ +" : "▼ "}{up}% {up >= 0 ? "апсайд" : "даунсайд"}
        </span>
      ))}
      <div style={{ position: "relative", height: 46, marginTop: 8 }}>
        {/* трек */}
        <div style={{ position: "absolute", top: 20, left: 0, right: 0, height: 6, background: "var(--bg-card)", borderRadius: 3 }} />
        {/* коридор conservative→base */}
        <div style={{ position: "absolute", top: 20, height: 6, borderRadius: 3, background: "var(--accent)", opacity: 0.5, left: `${pos(lo)}%`, width: `${pos(hi) - pos(lo)}%` }} />
        {/* маркер текущей цены */}
        <div style={{ position: "absolute", top: 14, left: `${pos(cur)}%`, transform: "translateX(-50%)", width: 2, height: 18, background: "var(--text-1)" }} />
        <div style={{ position: "absolute", top: 0, left: `${pos(cur)}%`, transform: "translateX(-50%)", fontSize: 11, color: "var(--text-1)", fontWeight: 600, whiteSpace: "nowrap" }}>
          {cur} ₽
        </div>
        {/* подписи краёв */}
        <div style={{ position: "absolute", top: 30, left: `${pos(lo)}%`, transform: "translateX(-50%)", fontSize: 11, color: "var(--text-3)", fontFamily: "monospace" }}>{lo}</div>
        <div style={{ position: "absolute", top: 30, left: `${pos(hi)}%`, transform: "translateX(-50%)", fontSize: 11, color: "var(--text-3)", fontFamily: "monospace" }}>{hi}</div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-2)", marginTop: 6 }}>
        <span>Консервативно: <b style={{ color: "var(--text-1)" }}>{lo} {currency}</b></span>
        <span>База: <b style={{ color: "var(--text-1)" }}>{hi} {currency}</b></span>
      </div>
      {typeof fvr.broker_12m_target === "number" && (
        <div style={{ fontSize: 12, color: "var(--text-3)", marginTop: 6 }}>
          Консенсус брокеров 12м: ~{fvr.broker_12m_target} ₽
          {typeof fvr.broker_12m_upside_pct === "number" ? ` (+${fvr.broker_12m_upside_pct}%)` : ""}
        </div>
      )}
    </div>
  );
};
```

### 3. SVG-графики динамики (без библиотек)

Два переиспользуемых компонента: столбчатый (выручка / чистая прибыль) и линейный (маржа). Чистый SVG, отзывчивый по ширине (`viewBox` + `width:100%`). Игнорируют `null`.

```jsx
// Универсальный мини-график. type: "bar" | "line". data: число|null[]
const MiniChart = ({ data, labels, type = "bar", color = "var(--accent)", height = 120, unit = "" }) => {
  const W = 320, H = height, padX = 6, padTop = 14, padBot = 18;
  const pts = (data || []).map((v, i) => ({ v, i, y: v }));
  const vals = pts.map(p => p.v).filter(v => typeof v === "number");
  if (!vals.length) return null;
  const max = Math.max(...vals, 0), min = Math.min(...vals, 0);
  const span = (max - min) || 1;
  const n = pts.length;
  const xAt = i => padX + (n === 1 ? (W - 2 * padX) / 2 : (i * (W - 2 * padX)) / (n - 1));
  const yAt = v => padTop + (1 - (v - min) / span) * (H - padTop - padBot);
  const zeroY = yAt(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} preserveAspectRatio="none">
      {/* нулевая линия, если данные пересекают 0 */}
      {min < 0 && max > 0 && (
        <line x1={padX} x2={W - padX} y1={zeroY} y2={zeroY} stroke="var(--border-mid)" strokeWidth="1" />
      )}
      {type === "bar" && pts.map((p, i) => {
        if (typeof p.v !== "number") return null;
        const bw = Math.max(6, (W - 2 * padX) / n * 0.6);
        const x = xAt(i) - bw / 2;
        const y = p.v >= 0 ? yAt(p.v) : zeroY;
        const h = Math.abs(yAt(p.v) - zeroY);
        const neg = p.v < 0;
        return <rect key={i} x={x} y={y} width={bw} height={Math.max(h, 1)} rx="2"
          fill={neg ? "var(--negative)" : color} opacity={neg ? 0.9 : 0.85} />;
      })}
      {type === "line" && (() => {
        const seg = pts.filter(p => typeof p.v === "number");
        const d = seg.map((p, k) => `${k === 0 ? "M" : "L"}${xAt(p.i).toFixed(1)},${yAt(p.v).toFixed(1)}`).join(" ");
        return (
          <>
            <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {seg.map((p, k) => <circle key={k} cx={xAt(p.i)} cy={yAt(p.v)} r="2.5" fill={color} />)}
          </>
        );
      })()}
      {/* подписи лет под осью */}
      {(labels || []).map((lb, i) => (
        <text key={i} x={xAt(i)} y={H - 5} textAnchor="middle" fontSize="8" fill="var(--text-3)" fontFamily="monospace">
          {String(lb).slice(2)}
        </text>
      ))}
    </svg>
  );
};
```

Использование — карточка с тремя графиками (для банка: проц. доход + чистая прибыль + ROE):

```jsx
const chartRevenue = isBank ? bp.net_interest_income : is.revenue;
const chartProfit  = isBank ? bp.net_profit          : is.net_profit;
const chartMargin  = isBank ? bm.roe                  : m.net_margin;

const hasCharts = [chartRevenue, chartProfit, chartMargin].some(a => Array.isArray(a) && a.some(x => x != null));

{hasCharts && (
  <div style={cardStyle}>
    {cardHead(TrendingUp, "Динамика по годам")}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 18 }}>
      <div>
        <div style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 6 }}>{isBank ? "Чистый проц. доход" : "Выручка"}</div>
        <MiniChart data={chartRevenue} labels={years} type="bar" />
      </div>
      <div>
        <div style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 6 }}>Чистая прибыль</div>
        <MiniChart data={chartProfit} labels={years} type="bar" color="var(--accent)" />
      </div>
      <div>
        <div style={{ fontSize: 12, color: "var(--text-2)", marginBottom: 6 }}>{isBank ? "ROE, %" : "Чистая маржа, %"}</div>
        <MiniChart data={chartMargin} labels={years} type="line" color="var(--positive)" />
      </div>
    </div>
  </div>
)}
```

### 4. Таблица методов оценки

```jsx
const methods = finJson?.valuation?.methods || [];
const METHOD_RU = { DCF: "DCF", historical_pe: "Истор. P/E", relative_peers: "По пирам", CAPM: "CAPM", dividend: "Дивидендный", dividend_gordon: "Дивид. (Гордон)" };
const HORIZON_RU = { intrinsic_now: "сейчас", "12m": "12 мес." };
const statusBadge = (s) => {
  const map = {
    ok:                { t: "ок",        c: "var(--positive)", bg: "rgba(63,185,80,0.12)" },
    insufficient_data: { t: "мало данных", c: "var(--text-3)", bg: "var(--bg-card)" },
    not_applicable:    { t: "n/a",       c: "var(--text-3)", bg: "var(--bg-card)" },
  };
  const x = map[s] || map.ok;
  return <span style={{ fontSize: 11, fontWeight: 600, color: x.c, background: x.bg, padding: "2px 8px", borderRadius: 6 }}>{x.t}</span>;
};

{methods.length > 0 && (
  <div style={cardStyle}>
    {cardHead(Scale, "Методы оценки")}
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {["Метод", "Справедливая цена", "Горизонт", "Статус"].map((h, i) => (
              <th key={i} style={{ textAlign: i === 1 ? "right" : "left", padding: "6px 10px", color: "var(--text-3)", fontWeight: 600, fontSize: 11, textTransform: "uppercase", borderBottom: "1px solid var(--border-mid)" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {methods.map((mt, i) => (
            <tr key={i} style={{ background: i % 2 ? "var(--bg-card)" : "transparent", opacity: mt.status === "insufficient_data" || mt.status === "not_applicable" ? 0.6 : 1 }}>
              <td style={{ padding: "7px 10px", color: "var(--text-1)" }}>{METHOD_RU[mt.method] || mt.method}</td>
              <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: "monospace", fontVariantNumeric: "tabular-nums", color: "var(--text-1)", fontWeight: 600 }}>
                {typeof mt.fair_value_per_share === "number" ? `${mt.fair_value_per_share} ₽` : "—"}
              </td>
              <td style={{ padding: "7px 10px", color: "var(--text-2)" }}>{HORIZON_RU[mt.horizon] || mt.horizon || "—"}</td>
              <td style={{ padding: "7px 10px" }}>{statusBadge(mt.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
)}
```

> Размести этот блок **под** `FairValueBar`: сначала вывод (коридор), потом «как получили» (методы).

### 5. Бейдж аномалии — сворачиваемая карточка

Заменяет нынешний жёлтый блок (строки ~2329–2334). Всегда виден заголовок-предупреждение; текст `anomaly_note` — по клику.

```jsx
{finJson?.anomaly_flag && finJson?.anomaly_note && (
  <details style={{ background: "rgba(248,81,73,0.06)", border: "1px solid rgba(248,81,73,0.25)", borderRadius: 12, padding: "12px 16px" }}>
    <summary style={{ cursor: "pointer", listStyle: "none", display: "flex", alignItems: "center", gap: 10, fontSize: 13.5, fontWeight: 600, color: "var(--negative)" }}>
      <AlertTriangle size={16} style={{ flexShrink: 0 }} />
      Мультипликаторы структурно искажены — раскрыть пояснение
      <ChevronDown size={15} style={{ marginLeft: "auto", color: "var(--negative)" }} />
    </summary>
    <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-2)", margin: "10px 0 0" }}>
      {finJson.anomaly_note}
    </p>
  </details>
)}
```

> Важно: текст — нейтральным `var(--text-2)` на лёгком красном фоне (не «жёлтым по жёлтому»). Только заголовок акцентно-красный. Бейдж размести СРАЗУ под блоком мультипликаторов (как сейчас), чтобы предупреждение читалось до цифр.

### 6. Текст из summary.md — секциями рядом, не сплошняком

`finMd` оставить, но: (а) рендерить ПОСЛЕ таблиц/графиков как «Комментарий аналитика», (б) разбить по H2 в сворачиваемые секции (переиспользуй `splitByH2` из `renderBusinessProfile` — вынеси её выше в общую область компонента, чтобы обе функции её видели). Каждую секцию — в `<details>`, первая открыта.

```jsx
{finMd && (
  <div style={cardStyle}>
    {cardHead(FileText, "Комментарий аналитика")}
    {splitByH2(finMd).map(({ heading, body }, i) => (
      <details key={i} open={i === 0} style={{ borderTop: i ? "1px solid var(--border-mid)" : "none", padding: "8px 0" }}>
        <summary style={{ cursor: "pointer", listStyle: "none", fontSize: 13, fontWeight: 600, color: "var(--text-1)", display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 3, height: 12, background: "var(--accent)", borderRadius: 2 }} />
          {heading}
          <ChevronDown size={14} style={{ marginLeft: "auto", color: "var(--text-3)" }} />
        </summary>
        <div style={{ paddingTop: 6 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdc}>{body}</ReactMarkdown>
        </div>
      </details>
    ))}
  </div>
)}
```

> Если в `finMd` нет H2 (`splitByH2` вернёт пусто) — фолбэк: рендерить `finMd` целиком как сейчас. Условие: `const secs = splitByH2(finMd); ... secs.length ? секции : <ReactMarkdown>{finMd}</ReactMarkdown>`.

### 7. Итоговый порядок вывода в `return renderFinancials`

```jsx
return (
  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
    {/* 1. мультипликаторы — существующий блок, цвета → переменные */}
    {/* 2. бейдж аномалии (Правка 5) */}
    {/* 3. <FairValueBar fvr={fvr} currency={meta.currency || "₽"} /> */}
    {/* 4. таблица методов оценки (Правка 4) */}
    {/* 5. графики динамики (Правка 3) */}
    {/* 6. таблицы P&L / Баланс / ОДДС или банковские (Правка 1) */}
    {/* 7. комментарий аналитика секциями (Правка 6) */}
  </div>
);
```

### 8. Замена хардкод-цветов в существующем блоке мультипликаторов

- Строка ~2315: `upside >= 0 ? "#22c55e" : "#ef4444"` → `upside >= 0 ? "var(--positive)" : "var(--negative)"`.
- Чипы: `background: "var(--bg-base, #0f172a)"` → `var(--bg-card)` (переменной `--bg-base` в проекте НЕТ, сейчас работает только фолбэк — заменить на реальную `--bg-card`).
- Бейдж аномалии (старый жёлтый) — удалить, заменён Правкой 5.

---

## Чего НЕ менять (важно!)

- **Блок ключевых мультипликаторов сверху** (чипы P/E, P/S, P/B, EV/EBITDA, ND/EBITDA, ROE) — хорош, плотный, читаемый. Только цвета на переменные (Правка 8).
- **Логику загрузки данных** (`useEffect` на строках ~1705–1719, `Promise.all` двух фетчей) — не трогать.
- **`mdc`-компоненты markdown** (строки ~2254–2283) — оставить, они используются для рендера секций summary в Правке 6.
- **Строку с относительной оценкой по сектору** (`rel.fair_value_per_share`, ~2322) — оставить под `FairValueBar` как доп. ориентир.
- `lastNN` и `fmt` — переиспользуй, не дублируй.

---

## Зависимости

- Иконки lucide: добавить в общий импорт `TrendingUp, Scale, Wallet, Target, AlertTriangle` (ChevronDown, FileText, BarChart2, ShieldAlert уже импортированы).
- `splitByH2` сейчас локальна в `renderBusinessProfile` — вынести в область компонента (выше обеих render-функций), чтобы переиспользовать.
- Данных, которых нет в JSON, не требуется — всё уже в схеме (`income_statement`, `balance_sheet`, `cash_flow`, `bank_pnl`, `bank_metrics`, `valuation.methods`, `fair_value_range`, `anomaly_flag/note`).

## Оценка трудозатрат

**M (полдня).** Чистый фронт, один файл, новых данных и бэкенда не требуется. Риск — корректная деградация банковского профиля (тестировать на банке: SBER/VTBR) и на «дырявых» данных (ROSN — хвост null, SNGS — anomaly + много null). Проверить: компания без `finJson` (только `finMd`) и компания без `finMd` (только числа) — оба пути уже обработаны фолбэками.
```
