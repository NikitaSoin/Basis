// =============================================================
// BASIS ACCOUNT — tier catalog (single source of truth).
// Pure data, no JSX — both PricingView and ProfileView read tier copy
// from here so the two pages can never disagree on what each tier
// includes. Backend contract: SubscriptionType.free|plus|premium
// (backend/app/models/user.py) — ids below match those values exactly.
//
// Honesty rules baked into this data (owner правки, 2026-07-08):
//   - Скринер is IDENTICAL on every tier — deliberately absent from
//     compareCells; covered by one sentence above the table instead
//     (see PricingView.jsx).
//   - Free's "3 deep dives / month" is a CONSTANT (the tier's rule),
//     never a usage counter — there is no backend field yet for
//     "how many already used", so we never print a fake "2 of 3" readout.
//   - Premium's three roadmap rows are honestly marked "Скоро": the
//     portfolio "ИИ-Диагноз" panel today is a hardcoded illustrative
//     example (pros/cons are fixed strings, not computed per user),
//     and stress-test / AI-assistant are literal ComingSoonView stubs
//     in App.js (cases "stress" / "ai" in renderView()).
// =============================================================

export const TIER_RANK = { free: 0, plus: 1, premium: 2 };

export const TIERS = [
  {
    id: "free",
    name: "Бесплатный",
    priceRub: 0,
    eyebrow: null,
    description:
      "Вся платформа доступна без ограничений — глубина разбора выдаётся по счётчику: 3 полных разбора в месяц.",
    bullets: [
      { text: "Карточки всех компаний — обзор, цифры, мультипликаторы, вывод по каждой вкладке", accent: true },
      { text: "Скринер без ограничений — все метрики, пресеты и конструктор" },
      { text: "Обозреватель — лента, карта рынка, календарь, отчётности, макро, гео" },
      { text: "Портфель любого размера — состав, индекс качества и корреляции одной сводной цифрой" },
    ],
    compareCells: {
      tabsText: "Вывод одной строкой",
      deepDives: "3 в месяц (любой объект)",
      decisionRail: "Только направление",
      aiOverview: "Заголовочный вывод",
      portfolioRisk: "Заголовковой цифрой",
      aiDiagnosis: null,
      stressTest: null,
      aiAssistant: null,
    },
  },
  {
    id: "plus",
    name: "Plus",
    priceRub: 390,
    eyebrow: "Полная аналитика",
    description: "Вся аналитика, которую Basis уже посчитал, — без лимитов.",
    bullets: [
      { text: "Полный текст разбора всех вкладок карточки компании — без лимита", accent: true },
      { text: "Точная целевая цена, потенциал и детализация уверенности в Decision-rail" },
      { text: "Обозреватель — полный синтез ИИ-обзора дня, не только заголовок" },
      { text: "Портфель — Sharpe, Sortino, VaR, бета и полная матрица корреляций" },
    ],
    compareCells: {
      tabsText: "Полный текст",
      deepDives: "Без лимита",
      decisionRail: "Точная цена и потенциал",
      aiOverview: "Полный синтез",
      portfolioRisk: "Sharpe, Sortino, VaR, бета, матрица",
      aiDiagnosis: null,
      stressTest: null,
      aiAssistant: null,
    },
  },
  {
    id: "premium",
    name: "Max",
    priceRub: 990,
    eyebrow: null,
    description: "Всё из Plus — и живой ИИ-анализ, когда он появится, без дополнительной оплаты.",
    bullets: [
      { text: "Все возможности тарифа Plus — без ограничений", accent: true },
      { text: "Живой ИИ-диагноз портфеля по вашим реальным позициям", soon: true },
      { text: "Стресс-тест портфеля на кризисных сценариях", soon: true },
      { text: "ИИ-помощник — диалоговый чат по рынку и портфелю", soon: true },
    ],
    compareCells: {
      tabsText: "Полный текст",
      deepDives: "Без лимита",
      decisionRail: "Точная цена и потенциал",
      aiOverview: "Полный синтез",
      portfolioRisk: "Sharpe, Sortino, VaR, бета, матрица",
      aiDiagnosis: "Скоро",
      stressTest: "Скоро",
      aiAssistant: "Скоро",
    },
  },
];

// Compare-table rows — DIFFERENCES ONLY, grouped by product section.
// Скринер and "can I open a card / see the feed / hold N positions" are
// equal on every tier and are covered by one sentence above the table
// instead (see PricingView.jsx) rather than repeated as all-✓ rows here.
export const COMPARE_GROUPS = [
  {
    title: "Карточка компании",
    rows: [
      { key: "tabsText", label: "Разбор по вкладкам (бизнес-модель, управление, рынки, макро, гео)" },
      { key: "deepDives", label: "Глубоких разборов" },
      { key: "decisionRail", label: "Справедливая цена и потенциал (Decision-rail)" },
    ],
  },
  {
    title: "Обозреватель",
    rows: [{ key: "aiOverview", label: "ИИ-обзор дня" }],
  },
  {
    title: "Портфель",
    rows: [{ key: "portfolioRisk", label: "Риск-метрики и корреляции" }],
  },
  {
    title: "В разработке",
    rows: [
      { key: "aiDiagnosis", label: "Живой ИИ-диагноз портфеля по факту позиций" },
      { key: "stressTest", label: "Стресс-тест портфеля" },
      { key: "aiAssistant", label: "ИИ-помощник (диалоговый чат)" },
    ],
  },
];

export function getTier(id) {
  return TIERS.find((t) => t.id === id) || TIERS[0];
}
