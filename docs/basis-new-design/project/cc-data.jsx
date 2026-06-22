// Basis — Company Card · data + shared primitives. Exported to window.
// Illustrative analytical content for Роснефть (ROSN). Numbers are mock,
// formatted per ru-RU rules (comma decimals, narrow-nbsp grouping, nbsp+unit).

const NB = "\u00A0";   // no-break space (before units)
const NN = "\u202F";   // narrow no-break space (thousands)

const COMPANY = {
  name: "Роснефть",
  ticker: "ROSN",
  exchange: "MOEX",
  sector: "Нефть и газ",
  monogram: "Р",
  price: "512,40",
  currency: "₽",
  change: 0.84,            // daily, %
  marketCap: `5,43${NB}трлн${NB}₽`,
  updated: "сегодня, 18:42 МСК",
  isin: "RU000A0J2Q06",
};

// Tabs — exact labels from the brief.
const TABS = [
  { id: "overview",   label: "Обзор" },
  { id: "business",   label: "Бизнес-модель" },
  { id: "financials", label: "Финансы и оценка" },
  { id: "governance", label: "Корпоративное управление" },
  { id: "markets",    label: "Рынки" },
  { id: "macro",      label: "Макро" },
  { id: "geopolitics",label: "Геополитика" },
];

// Top nav — exact labels from the brief.
const NAV = ["Рынок", "Обозреватель", "Портфель", "Скрининг", "Тарифы", "Профиль"];

// Seven headline metrics for the Overview grid.
const METRICS = [
  { caption: "Выручка, LTM",       value: "9,12", unit: `трлн${NB}₽`, delta: 4.6,  level: "fact" },
  { caption: "EBITDA margin",      value: "29,8", unit: "%",          delta: -1.2, level: "estimate" },
  { caption: "Net debt / EBITDA",  value: "1,3",  unit: "×",          level: "estimate" },
  { caption: "FCF, LTM",           value: "1,18", unit: `трлн${NB}₽`, delta: -8.4, level: "estimate" },
  { caption: "Дивдоходность",      value: "10,4", unit: "%",          level: "estimate" },
  { caption: "EV / EBITDA",        value: "3,4",  unit: "×",          level: "estimate" },
  { caption: "Потенциал к справ. ст.", value: "+18", unit: "%",       level: "judgment" },
];

// Executive summary — «Что важно сейчас».
const EXEC = {
  tone: "cautious",
  toneLabel: "Осторожно-конструктивный",
  insights: [
    "Денежный поток остаётся высоким, но FCF под давлением капзатрат на «Восток Ойл» и роста процентных расходов.",
    "Дисконт оценки к мировым мейджорам отражает санкционную и страновую премию за риск, а не качество активов.",
    "Дивиденд формально устойчив (50% от прибыли по МСФО), но чувствителен к курсу рубля и цене Urals.",
    "«Восток Ойл» — главный фактор стоимости на горизонте 3–5 лет и одновременно источник неопределённости по срокам.",
  ],
  mainRisk: "Снижение цены Urals и/или укрепление рубля одновременно сжимают выручку и дивидендную базу.",
  mainRiskType: "commodity",
  mainRiskSeverity: "medium",
  whatWouldChange: "Устойчивый выход Urals ниже 55 $/барр., новые санкции на экспорт или сдвиг сроков «Восток Ойл» вправо.",
  priced: "Рынок уже закладывает санкционный дисконт и слабый рубль; менее учтён потенциал «Восток Ойл» и контроль над капзатратами.",
};

// Financials table (МСФО, трлн ₽ кроме margin).
const FIN_COLS = [
  { key: "row", label: "Показатель" },
  { key: "y23", label: "2023" },
  { key: "y24", label: "2024" },
  { key: "ltm", label: "LTM" },
];
const FIN_ROWS = [
  { row: "Выручка",          y23: "9,16", y24: "9,04", ltm: "9,12" },
  { row: "EBITDA",           y23: "2,80", y24: "2,55", ltm: "2,72" },
  { row: "Чистая прибыль",   y23: "1,27", y24: "1,06", ltm: "1,14" },
  { row: "FCF",              y23: "1,43", y24: "1,29", ltm: "1,18" },
  { row: "Чистый долг",      y23: "3,45", y24: "3,58", ltm: "3,54" },
  { row: "Капзатраты",       y23: "1,29", y24: "1,47", ltm: "1,56" },
];

// Revenue-by-segment mini table.
const SEG_COLS = [
  { key: "seg", label: "Сегмент" },
  { key: "share", label: "Доля выручки" },
  { key: "note", label: "Комментарий" },
];
const SEG_ROWS = [
  { seg: "Разведка и добыча", share: `48${NB}%`, note: "Ядро бизнеса, низкая себестоимость барреля" },
  { seg: "Переработка и сбыт", share: `41${NB}%`, note: "НПЗ, опт и розница топлива в РФ" },
  { seg: "Газ и СПГ",          share: `7${NB}%`,  note: "Растущий, но пока вторичный сегмент" },
  { seg: "Прочее",             share: `4${NB}%`,  note: "Сервисы, трейдинг, логистика" },
];

// Scenario analysis.
const SCENARIOS = {
  base: {
    assumptions: "Urals ~62 $/барр., USD/RUB ~92, добыча в рамках квот ОПЕК+, «Восток Ойл» по графику.",
    revenue: 3, margin: -0.5, fcf: -4,
    materialize: "Стабильный экспорт в Азию с умеренным дисконтом, дивиденд 50% прибыли МСФО сохраняется.",
    invalidate: "Падение Urals ниже 55 $/барр. на квартал и дольше.",
  },
  bull: {
    assumptions: "Urals 70–75 $/барр., слабый рубль (USD/RUB > 95), ускорение «Восток Ойл».",
    revenue: 12, margin: 2, fcf: 18,
    materialize: "Рост цен на нефть + слабый рубль расширяют рублёвую выручку и дивидендную базу.",
    invalidate: "Резкое укрепление рубля нивелирует ценовой эффект.",
  },
  bear: {
    assumptions: "Urals 50–55 $/барр., крепкий рубль (USD/RUB < 85), расширение санкционного дисконта.",
    revenue: -11, margin: -3, fcf: -28,
    materialize: "Снижение цен и крепкий рубль сжимают денежный поток и давят на дивиденд.",
    invalidate: "Ослабление рубля или сужение дисконта к Brent.",
  },
  stress: {
    assumptions: "Urals < 45 $/барр., новые вторичные санкции на покупателей, рост стоимости логистики.",
    revenue: -22, margin: -6, fcf: -55,
    materialize: "Комбинация низких цен и логистических ограничений требует сокращения капзатрат и дивиденда.",
    invalidate: "Снятие части ограничений или координированное сокращение добычи ОПЕК+.",
  },
};

// Key risks for the sidebar + risks tile.
const RISKS = [
  { type: "commodity",  severity: "medium", text: "Цена Urals и дисконт к Brent определяют выручку напрямую." },
  { type: "fx",         severity: "medium", text: "Укрепление рубля сжимает рублёвую выручку и дивидендную базу." },
  { type: "sanctions",  severity: "high",   text: "Вторичные санкции на покупателей и логистику экспорта." },
  { type: "leverage",   severity: "low",    text: "Долг управляем (1,3× EBITDA), но капзатраты растут." },
  { type: "governance", severity: "medium", text: "Контроль государства и крупные стратегические проекты." },
];

// What to monitor — sidebar checklist.
const MONITOR = [
  "Динамика Urals и дисконт к Brent",
  "Курс USD/RUB и его влияние на выручку",
  "Прогресс и капзатраты «Восток Ойл»",
  "Решения ОПЕК+ по квотам добычи",
  "Дивидендные рекомендации совета директоров",
];

// Sources for the evidence tile + sidebar status.
const SOURCES = [
  { name: "МСФО-отчётность, 9М 2025", date: "14.11.2025", href: "#" },
  { name: "Пресс-релиз по добыче",     date: "ноя 2025",   href: "#" },
  { name: "Bloomberg — котировки Urals", date: "сегодня",  href: "#" },
  { name: "ЦБ РФ — курс и ставка",      date: "сегодня",   href: "#" },
  { name: "Решения ОПЕК+",              date: "окт 2025",  href: "#" },
];

// --- shared layout primitives ---

function Eyebrow({ children, style }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 600, textTransform: "uppercase",
      letterSpacing: "var(--ls-eyebrow)", color: "var(--text-tertiary)", ...style,
    }}>{children}</div>
  );
}

function Para({ children, style }) {
  return (
    <p style={{
      fontSize: 15, lineHeight: 1.6, color: "var(--text-secondary)",
      margin: "0 0 10px", maxWidth: "68ch", ...style,
    }}>{children}</p>
  );
}

// A standard analytical tile: title row (+ optional epistemic tag / aside) and body.
function Tile({ title, tag, aside, children, id, style }) {
  const { FactEstimateJudgmentTag } = window.BasisDesignSystem_c4316a;
  return (
    <section id={id} style={{
      background: "var(--bg-elevated)", border: "1px solid var(--border-strong)",
      borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-md)",
      padding: "20px 22px", ...style,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
        <h3 style={{ fontFamily: "var(--font-display)", fontSize: 18, fontWeight: 600, margin: 0, color: "var(--text-primary)", letterSpacing: "var(--ls-heading)" }}>{title}</h3>
        {tag && <FactEstimateJudgmentTag level={tag} />}
        {aside && <div style={{ marginLeft: "auto" }}>{aside}</div>}
      </div>
      {children}
    </section>
  );
}

Object.assign(window, {
  CC_NB: NB, CC_NN: NN,
  CC_COMPANY: COMPANY, CC_TABS: TABS, CC_NAV: NAV, CC_METRICS: METRICS,
  CC_EXEC: EXEC, CC_FIN_COLS: FIN_COLS, CC_FIN_ROWS: FIN_ROWS,
  CC_SEG_COLS: SEG_COLS, CC_SEG_ROWS: SEG_ROWS, CC_SCENARIOS: SCENARIOS,
  CC_RISKS: RISKS, CC_MONITOR: MONITOR, CC_SOURCES: SOURCES,
  CCEyebrow: Eyebrow, CCPara: Para, CCTile: Tile,
});
