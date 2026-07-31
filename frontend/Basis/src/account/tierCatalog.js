// =============================================================
// BASIS ACCOUNT — tier catalog (single source of truth).
// Pure data, no JSX — both PricingView and ProfileView read tier copy
// from here so the two pages can never disagree on what each tier
// includes. Backend contract: SubscriptionType.free|plus|premium
// (backend/app/models/user.py).
//
// 🔴 ДВА ТАРИФА (владелец, 2026-08-01): «пусть останется один тариф Max,
// без Плюс; в Max доступно всё; у Max две стоимости — 390 ₽/мес и 1990 ₽/год».
// "plus" УБРАН ИЗ UI, но ОСТАВЛЕН в enum БД (backend/app/models/user.py):
// удаление значения из PG-энума — миграция с риском уронить существующие
// строки, а пользы ноль. Вместо этого разовый перевод plus → premium
// (Plus стоил ровно 390 ₽, столько же теперь стоит Max — никто не теряет).
// TIER_RANK держит plus между free и premium, чтобы старая запись в БД
// (если вдруг всплывёт) сравнивалась предсказуемо, а не падала на undefined.
//
// 🔴 ЧЕСТНОСТЬ ПРО ЛИМИТЫ БЕСПЛАТНОГО. Владелец: «в обычном тарифе ПОКА
// глобально всё должно быть открыто, но стратегически надо будет ограничить».
// Значит таблица ниже описывает ЗАДУМАННУЮ границу продукта, а код её ещё
// НЕ ПРИМЕНЯЕТ. Поэтому на странице тарифов стоит явная плашка «ограничения
// бесплатного пока не включены» (PricingView) — иначе страница обещала бы
// бесплатному пользователю ограничения, которых он не увидит, и наоборот
// продавала бы Max за то, что и так открыто. Когда появится enforcement —
// снять плашку (FREE_LIMITS_ENFORCED ниже).
// =============================================================

export const TIER_RANK = { free: 0, plus: 1, premium: 2 };

// Ограничения бесплатного тарифа ещё не включены в коде (см. шапку файла).
// Переключить в true ОДНОВРЕМЕННО с появлением реальных гейтов.
export const FREE_LIMITS_ENFORCED = false;

export const TIERS = [
  {
    id: "free",
    name: "Бесплатный",
    priceRub: 0,
    priceRubYear: 0,
    eyebrow: null,
    description:
      "Рынок, скринер, карточки компаний и портфель — чтобы работать с платформой каждый день.",
    bullets: [
      { text: "Карточки всех компаний, облигаций, фондов и фьючерсов", accent: true },
      { text: "Скринер без ограничений — все метрики, пресеты и конструктор" },
      { text: "Обозреватель — лента новостей, карта рынка, календарь, макро и гео" },
      { text: "Портфель до 50 позиций — состав, доходность, базовая аналитика" },
    ],
    compareCells: {
      cardAnalytics: "Базовая",
      fairPrice: null,
      observerDeep: "Лента и данные",
      portfolioAnalytics: "Частичная",
      stressTest: "Готовые сценарии",
      aiAssistant: "До 2 запросов в сутки",
    },
  },
  {
    id: "premium",
    name: "Max",
    priceRub: 390,
    priceRubYear: 1990,
    eyebrow: "Всё включено",
    description: "Полный доступ ко всей платформе — вся аналитика, все разборы, без лимитов.",
    bullets: [
      { text: "Вся аналитика карточки — полный разбор по каждой вкладке", accent: true },
      { text: "Справедливая цена и потенциал по методике Basis" },
      { text: "Обозреватель целиком — разборы отчётов и все аналитические разборы" },
      { text: "Полная аналитика портфеля и стресс-тест со своими сценариями" },
      { text: "ИИ-ассистент без ограничения по числу запросов" },
    ],
    compareCells: {
      cardAnalytics: "Полная",
      fairPrice: "Да",
      observerDeep: "Всё, включая разборы",
      portfolioAnalytics: "Полная",
      stressTest: "Свои сценарии",
      aiAssistant: "Без ограничений",
    },
  },
];

// Compare-table rows — DIFFERENCES ONLY, grouped by product section.
// Скринер, поиск, карточки бумаг и лента Обозревателя
// одинаковы на обоих тарифах — они покрыты одной фразой над таблицей
// (см. PricingView.jsx), а не строками со сплошными «✓».
export const COMPARE_GROUPS = [
  {
    title: "Карточка компании",
    rows: [
      { key: "cardAnalytics", label: "Аналитика по вкладкам (бизнес-модель, финансы, управление, рынки, макро, гео)" },
      { key: "fairPrice", label: "Справедливая цена и потенциал" },
    ],
  },
  {
    title: "Обозреватель",
    rows: [{ key: "observerDeep", label: "Разборы отчётов и аналитические разборы" }],
  },
  {
    title: "Портфель",
    rows: [
      { key: "portfolioAnalytics", label: "Аналитика портфеля" },
      { key: "stressTest", label: "Стресс-тестирование" },
    ],
  },
  {
    title: "ИИ-ассистент",
    rows: [{ key: "aiAssistant", label: "Запросы к ассистенту" }],
  },
];

export function getTier(id) {
  // plus убран из UI (см. шапку) — старую запись в БД показываем как Max:
  // Plus стоил столько же, сколько теперь Max, и Max включает всё, что было в Plus.
  if (id === "plus") return TIERS.find((t) => t.id === "premium");
  return TIERS.find((t) => t.id === id) || TIERS[0];
}
