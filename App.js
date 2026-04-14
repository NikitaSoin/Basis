import React, { useMemo, useState } from "react";
import {
  Search,
  TrendingUp,
  TrendingDown,
  Activity,
  Briefcase,
  AlertTriangle,
  Target,
  PieChart,
  ShieldAlert,
  Zap,
  ChevronRight,
  Globe,
  Upload,
  User,
  CreditCard,
  ShieldCheck,
  Layout,
  Info,
  Layers,
  Users,
  Plus,
  BarChart2,
  Database,
  ArrowRightLeft,
  BookOpen,
  FileText,
  Settings,
} from "lucide-react";

// =========================
// HELPERS
// =========================

const formatCurrency = (val) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  }).format(val);

const formatPercent = (val, digits = 1) =>
  `${val > 0 ? "+" : ""}${Number(val).toFixed(digits)}%`;

const badgeClass = (impact) => {
  if (impact === "positive")
    return "text-green-400 bg-green-500/10 border-green-500/20";
  if (impact === "negative")
    return "text-red-400 bg-red-500/10 border-red-500/20";
  return "text-slate-300 bg-slate-700/40 border-slate-600";
};

// =========================
// MOCK DATA
// =========================

const MOCK_MARKET_NEWS = {
  express: [
    {
      time: "10:00",
      text: "ЦБ РФ сохранил ставку на уровне 16%. Рынок акций отреагировал нейтрально.",
      impact: "neutral",
    },
    {
      time: "09:30",
      text: "Нефть Brent превысила $85 за баррель на фоне сокращения запасов.",
      impact: "positive",
    },
    {
      time: "Вчера",
      text: "Яндекс завершил первый этап реструктуризации. Акции +3%.",
      impact: "positive",
    },
  ],
  detailed: [
    {
      title: "Замедление потребительского кредитования",
      text: "По данным ЦБ, темпы роста потребкредитования в марте снизились на 15% м/м. Это оказывает давление на выручку банковского сектора.",
      sector: "Финансы",
      impact: "negative",
    },
    {
      title: "Рекордные дивиденды в нефтегазе",
      text: "Лукойл и Роснефть рекомендовали дивиденды выше ожиданий рынка. Ожидается приток ликвидности после дивидендных гэпов.",
      sector: "Нефтегаз",
      impact: "positive",
    },
  ],
  deep: [
    {
      title: "Анализ макроструктуры РФ 2026",
      text: "Структурная трансформация экономики приводит к росту внутреннего спроса при дефиците кадров. Это фундаментальный риск для инфляции.",
      sector: "Макро",
      impact: "neutral",
      factors:
        "Рынок труда, траектория ставки, бюджетный импульс, кредитование, темпы роста номинальных доходов и чувствительность мультипликаторов к ставке дисконтирования.",
    },
  ],
};

const MOCK_COMPANIES = [
  {
    ticker: "YDEX",
    name: "МКПАО Яндекс",
    sector: "IT и Телеком",
    price: 4120.5,
    change: 2.15,
    beta: 1.4,
    rsi: 52,
    overview: {
      action:
        "Акция торгуется с повышенной волатильностью относительно IMOEX. Акции не находятся в зоне перекупленности. Ключевой драйвер — завершение корпоративной реструктуризации. Текущая динамика — это event-driven переоценка, а не классический фундаментальный тренд.",
      macro:
        "Замедление экономики давит на выручку (реклама, e-commerce), но слабая экономика повышает вероятность снижения ставки, что ведет к росту оценок. Макрофакторы действуют разнонаправленно.",
      politics:
        "Общий уровень геополитической напряженности и неопределенность по внешнеполитическим событиям. Рост рисков снижает оценки, улучшение фона — сжимает дисконт.",
    },
    pros: [
      {
        title: "Устойчивый рост выручки выше рынка",
        desc: "Факт: выручка растёт ~35–45% г/г. Компания растёт в 4–6 раз быстрее экономики.",
      },
      {
        title: "Потенциал роста прибыльности",
        desc: "При нормализации структуры бизнеса EBITDA margin может вырасти к ~15–20%.",
      },
      {
        title: "Низкая долговая нагрузка",
        desc: "Net Debt / EBITDA ≈ 0–1x. Финансовые риски ограничены.",
      },
      {
        title: "Оценка допустима при текущих темпах",
        desc: "Текущая доходность ниже безрисковой, но компенсируется ростом прибыли ~20–30%+.",
      },
    ],
    cons: [
      {
        title: "Доходность ниже безрисковой ставки",
        desc: "Earnings yield ~3–5% против ~12–14% по ОФЗ. Акция переоценена при отсутствии роста.",
      },
      {
        title: "Разрыв между ростом выручки и прибыли",
        desc: "Инвестиции в новые сегменты съедают маржу.",
      },
      {
        title: "Концентрация на одном рынке",
        desc: ">90% выручки генерируется в России. Зависимость от локальной экономики.",
      },
      {
        title: "Чувствительность к ставке",
        desc: "Высокая ставка → высокий коэффициент дисконтирования → давление на оценку.",
      },
    ],
    risks: [
      {
        title: "Финальные условия реструктуризации хуже ожиданий",
        prob: "Средняя",
        effect: "−30% … −50%",
        type: "Событийный",
        sign: "negative",
      },
      {
        title: "Более мягкая денежно-кредитная политика",
        prob: "Средняя",
        effect: "+20% … +40%",
        type: "Макро",
        sign: "positive",
      },
      {
        title: "Ускорение роста IT-рынка в РФ",
        prob: "Средняя",
        effect: "+15% … +30%",
        type: "Отраслевой",
        sign: "positive",
      },
      {
        title: "Резкое замедление экономики РФ",
        prob: "Средняя",
        effect: "−20% … −35%",
        type: "Макро",
        sign: "negative",
      },
    ],
    fairValue: {
      dcf: { bear: 2800, base: 4000, bull: 5200 },
      pe: { bear: 2400, base: 3200, bull: 4000 },
      yield: { bear: 1600, base: 2000, bull: 2400 },
    },
    deepDive: [
      {
        category: "Бизнес-модель",
        details:
          "Ключевые сегменты: Поиск и портал (высокая маржа), E-commerce, Райдтех (стадия масштабирования и выхода в прибыль). Сильная экосистемная синергия.",
      },
      {
        category: "Финансы",
        details:
          "Выручка: ~800 млрд руб (ТТМ). EBITDA: ~120 млрд руб. CAPEX растет из-за инвестиций в инфраструктуру (серверы, AI).",
      },
      {
        category: "Конкуренты",
        details:
          "VK (соцсети/реклама), Сбер (экосистема), Ozon (e-commerce). Яндекс сохраняет лидерство в поиске (>60%) и такси.",
      },
    ],
    consilium: [
      {
        broker: "Т-Инвестиции",
        date: "10.04.2026",
        rec: "Покупать",
        target: 4800,
        args: "Завершение переезда, недооценка к историческим мультипликаторам",
        match: "Согласны",
      },
      {
        broker: "БКС",
        date: "05.04.2026",
        rec: "Держать",
        target: 4200,
        args: "Риски навеса акций после обмена",
        match: "Частично",
      },
      {
        broker: "СберИнвестиции",
        date: "28.03.2026",
        rec: "Покупать",
        target: 5000,
        args: "Сильные темпы роста e-commerce и финтеха",
        match: "Согласны",
      },
    ],
  },
  {
    ticker: "SBER",
    name: "Сбербанк ПАО",
    sector: "Финансовый",
    price: 316.4,
    change: 0.04,
    beta: 1.1,
    rsi: 49,
  },
  {
    ticker: "VTBR",
    name: "Банк ВТБ",
    sector: "Финансовый",
    price: 0.024,
    change: 2.06,
    beta: 1.3,
    rsi: 54,
  },
  {
    ticker: "MOEX",
    name: "Московская биржа",
    sector: "Финансовый",
    price: 215.1,
    change: -0.5,
    beta: 0.95,
    rsi: 46,
  },
  {
    ticker: "LKOH",
    name: "Лукойл ПАО",
    sector: "Нефтегазовый",
    price: 7450.0,
    change: 1.12,
    beta: 0.9,
    rsi: 55,
  },
  {
    ticker: "ROSN",
    name: "Роснефть",
    sector: "Нефтегазовый",
    price: 580.2,
    change: -0.3,
    beta: 1.0,
    rsi: 47,
  },
  {
    ticker: "NVTK",
    name: "Новатэк ПАО",
    sector: "Нефтегазовый",
    price: 1259.0,
    change: 0.85,
    beta: 1.05,
    rsi: 50,
  },
  {
    ticker: "GAZP",
    name: "Газпром ПАО",
    sector: "Нефтегазовый",
    price: 133.68,
    change: -0.23,
    beta: 1.15,
    rsi: 44,
  },
];

const MOCK_PORTFOLIO = [
  {
    ticker: "SBER",
    name: "Сбербанк",
    shares: 1000,
    avgPrice: 280.0,
    currentPrice: 316.4,
    beta: 1.1,
    pe: 4.5,
    pe_hist: 5.8,
    divYield: 10.5,
    expReturn: 15.2,
    stdDev: 12.4,
  },
  {
    ticker: "LKOH",
    name: "Лукойл",
    shares: 50,
    avgPrice: 6500.0,
    currentPrice: 7450.0,
    beta: 0.9,
    pe: 5.2,
    pe_hist: 6.5,
    divYield: 12.0,
    expReturn: 18.1,
    stdDev: 10.8,
  },
  {
    ticker: "YDEX",
    name: "Яндекс",
    shares: 100,
    avgPrice: 3500.0,
    currentPrice: 4120.5,
    beta: 1.4,
    pe: 25.0,
    pe_hist: 32.0,
    divYield: 0,
    expReturn: 22.4,
    stdDev: 25.6,
  },
];

const MOCK_CORRELATION = [
  [1.0, 0.45, 0.12],
  [0.45, 1.0, 0.05],
  [0.12, 0.05, 1.0],
];

// =========================
// HEADER
// =========================

const Header = ({ activeTab, setActiveTab }) => (
  <header className="border-b border-slate-800 bg-slate-900/95 p-4">
    <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
      <div
        className="flex items-center gap-2 text-indigo-400 font-bold text-xl cursor-pointer"
        onClick={() => setActiveTab("market")}
      >
        <Activity size={28} />
        <span className="tracking-tight uppercase">Базис</span>
      </div>

      <nav className="flex bg-slate-800 rounded-lg p-1">
        {[
          { id: "market", icon: Globe, label: "Обозреватель" },
          { id: "screener", icon: Search, label: "Компании" },
          { id: "portfolio", icon: Briefcase, label: "Портфель" },
          { id: "profile", icon: User, label: "Профиль" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md transition-all ${
              activeTab === tab.id
                ? "bg-indigo-600 text-white shadow-lg"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-700"
            }`}
          >
            <tab.icon size={18} />
            <span className="hidden md:inline font-medium text-sm">
              {tab.label}
            </span>
          </button>
        ))}
      </nav>
    </div>
  </header>
);

// =========================
// MARKET OBSERVER
// =========================

const MarketObserver = () => {
  const [view, setView] = useState("express");

  const indicators = [
    { label: "IMOEX", val: "3 450.20", ch: "+0.4%" },
    { label: "Ключ. ставка", val: "16.00%", ch: "0.0%" },
    { label: "USD/RUB", val: "92.50", ch: "-0.2%" },
    { label: "Brent", val: "$86.40", ch: "+1.2%" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">
            Обозреватель рынка
          </h2>
          <p className="text-slate-400">Контекстное понимание рыночного фона</p>
        </div>

        <div className="flex bg-slate-800 rounded-lg p-1">
          {[
            { id: "express", label: "Экспресс-отчет" },
            { id: "detailed", label: "Детальный обзор" },
            { id: "deep", label: "Глубокое исследование" },
          ].map((v) => (
            <button
              key={v.id}
              onClick={() => setView(v.id)}
              className={`px-3 py-1 text-xs md:text-sm rounded transition-colors ${
                view === v.id
                  ? "bg-indigo-500 text-white"
                  : "text-slate-400 hover:bg-slate-700"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div className="col-span-1 lg:col-span-2 space-y-4">
          <h3 className="text-lg font-semibold text-slate-300 border-b border-slate-700 pb-2">
            Результаты анализа
          </h3>

          {view === "express" && (
            <div className="space-y-4">
              {MOCK_MARKET_NEWS.express.map((news, i) => (
                <div
                  key={i}
                  className="bg-slate-800 p-4 rounded-xl border border-slate-700 flex gap-4"
                >
                  <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-full h-fit">
                    <Zap size={18} />
                  </div>
                  <div>
                    <span className="text-xs text-slate-500 font-mono">
                      {news.time}
                    </span>
                    <p className="text-slate-200 mt-1">{news.text}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {view === "detailed" && (
            <div className="space-y-4">
              {MOCK_MARKET_NEWS.detailed.map((news, i) => (
                <div
                  key={i}
                  className="bg-slate-800 p-5 rounded-xl border border-slate-700"
                >
                  <div className="flex justify-between items-center mb-2 gap-3">
                    <h4 className="text-white font-semibold">{news.title}</h4>
                    <span
                      className={`text-xs px-2 py-1 rounded border ${badgeClass(
                        news.impact
                      )}`}
                    >
                      {news.sector}
                    </span>
                  </div>
                  <p className="text-slate-400 text-sm leading-relaxed">
                    {news.text}
                  </p>
                </div>
              ))}
            </div>
          )}

          {view === "deep" && (
            <div className="space-y-4">
              {MOCK_MARKET_NEWS.deep.map((news, i) => (
                <div
                  key={i}
                  className="bg-slate-800 p-6 rounded-xl border border-indigo-500/30 bg-gradient-to-br from-slate-800 to-indigo-950/20"
                >
                  <h4 className="text-xl text-white font-bold mb-3">
                    {news.title}
                  </h4>
                  <p className="text-slate-300 text-sm leading-relaxed mb-4">
                    {news.text}
                  </p>
                  <div className="p-4 bg-slate-900/50 rounded-lg border border-slate-700 text-indigo-300 text-xs">
                    <p className="font-bold mb-1 uppercase tracking-wider">
                      Факторы влияния
                    </p>
                    {news.factors}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="col-span-1 space-y-4">
          <h3 className="text-lg font-semibold text-slate-300 border-b border-slate-700 pb-2">
            Индикаторы
          </h3>
          <div className="grid grid-cols-2 gap-3">
            {indicators.map((ind, i) => (
              <div
                key={i}
                className="bg-slate-800 p-4 rounded-xl border border-slate-700"
              >
                <div className="text-slate-400 text-xs mb-1">{ind.label}</div>
                <div className="text-white font-semibold">{ind.val}</div>
                <div
                  className={`text-xs mt-1 ${
                    ind.ch.startsWith("+")
                      ? "text-green-400"
                      : ind.ch === "0.0%"
                      ? "text-slate-500"
                      : "text-red-400"
                  }`}
                >
                  {ind.ch}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// =========================
// COMPANY LIST
// =========================

const CompanyList = ({ onSelectCompany }) => {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    return MOCK_COMPANIES.filter(
      (c) =>
        c.name.toLowerCase().includes(search.toLowerCase()) ||
        c.ticker.toLowerCase().includes(search.toLowerCase())
    );
  }, [search]);

  const sectors = useMemo(() => {
    const grouped = {};
    filtered.forEach((c) => {
      if (!grouped[c.sector]) grouped[c.sector] = [];
      grouped[c.sector].push(c);
    });
    return grouped;
  }, [filtered]);

  return (
    <div className="space-y-6">
      <div className="relative">
        <Search className="absolute left-4 top-3.5 text-slate-500" size={20} />
        <input
          type="text"
          placeholder="Поиск компании по названию или тикеру..."
          className="w-full bg-slate-800 border border-slate-700 text-white rounded-xl pl-12 pr-4 py-3 focus:outline-none focus:border-indigo-500 transition-colors shadow-inner"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {Object.entries(sectors).map(([sector, comps]) => (
        <div key={sector} className="space-y-4">
          <h3 className="text-xl font-semibold text-slate-300 border-b border-slate-700 pb-2">
            {sector}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {comps.map((c) => (
              <div
                key={c.ticker}
                onClick={() => onSelectCompany(c)}
                className="bg-slate-800 border border-slate-700 hover:border-indigo-500/50 p-4 rounded-xl cursor-pointer transition-all hover:shadow-lg hover:-translate-y-1 group"
              >
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <div className="font-bold text-white text-lg group-hover:text-indigo-400 transition-colors">
                      {c.ticker}
                    </div>
                    <div className="text-slate-400 text-sm truncate max-w-[150px]">
                      {c.name}
                    </div>
                  </div>

                  <div className="text-right">
                    <div className="text-white font-medium">
                      {c.price.toLocaleString("ru-RU")} ₽
                    </div>
                    <div
                      className={`flex items-center justify-end text-sm font-medium ${
                        c.change >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {c.change >= 0 ? (
                        <TrendingUp size={14} className="mr-1" />
                      ) : (
                        <TrendingDown size={14} className="mr-1" />
                      )}
                      {c.change > 0 ? "+" : ""}
                      {c.change}%
                    </div>
                  </div>
                </div>

                <div className="flex justify-end mt-4">
                  <span className="text-xs text-indigo-400 flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                    Открыть карточку <ChevronRight size={14} />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// =========================
// COMPANY CARD
// =========================

const CompanyCard = ({ company, onBack }) => {
  const [tab, setTab] = useState("overview");
  const [stressScenario, setStressScenario] = useState(null);

  const data = company.overview ? company : MOCK_COMPANIES[0];

  const renderOverview = () => (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <h4 className="text-indigo-400 font-semibold mb-3 flex items-center gap-2">
            <Activity size={18} />
            Что происходит с акцией?
          </h4>
          <p className="text-slate-300 text-sm leading-relaxed">
            {data.overview.action}
          </p>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <h4 className="text-indigo-400 font-semibold mb-3 flex items-center gap-2">
            <Globe size={18} />
            Макро и Геополитика
          </h4>
          <p className="text-slate-300 text-sm leading-relaxed mb-2">
            <span className="text-slate-500 font-medium">Макро:</span>{" "}
            {data.overview.macro}
          </p>
          <p className="text-slate-300 text-sm leading-relaxed">
            <span className="text-slate-500 font-medium">Политика:</span>{" "}
            {data.overview.politics}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 border-t-4 border-t-green-500">
          <h4 className="text-green-400 font-semibold mb-4 flex items-center gap-2">
            <TrendingUp size={18} />
            Аргументы ЗА
          </h4>
          <ul className="space-y-4">
            {data.pros.map((p, i) => (
              <li key={i}>
                <div className="text-white text-sm font-medium mb-1">
                  {i + 1}. {p.title}
                </div>
                <div className="text-slate-400 text-xs">{p.desc}</div>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 border-t-4 border-t-red-500">
          <h4 className="text-red-400 font-semibold mb-4 flex items-center gap-2">
            <TrendingDown size={18} />
            Аргументы ПРОТИВ
          </h4>
          <ul className="space-y-4">
            {data.cons.map((p, i) => (
              <li key={i}>
                <div className="text-white text-sm font-medium mb-1">
                  {i + 1}. {p.title}
                </div>
                <div className="text-slate-400 text-xs">{p.desc}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
        <h4 className="text-amber-400 font-semibold mb-4 flex items-center gap-2">
          <ShieldAlert size={18} />
          Основные риски
        </h4>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-400 uppercase bg-slate-900/50">
              <tr>
                <th className="px-4 py-3 rounded-tl-lg">Событие</th>
                <th className="px-4 py-3">Вероятность</th>
                <th className="px-4 py-3">Влияние на цену</th>
                <th className="px-4 py-3">Тип</th>
                <th className="px-4 py-3 rounded-tr-lg">Знак</th>
              </tr>
            </thead>
            <tbody>
              {data.risks.map((r, i) => (
                <tr key={i} className="border-b border-slate-700/50">
                  <td className="px-4 py-3 text-white font-medium">
                    {r.title}
                  </td>
                  <td className="px-4 py-3 text-slate-300">{r.prob}</td>
                  <td
                    className={`px-4 py-3 font-mono ${
                      r.sign === "positive" ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {r.effect}
                  </td>
                  <td className="px-4 py-3 text-slate-300">{r.type}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        r.sign === "positive"
                          ? "bg-green-500/10 text-green-400 border border-green-500/20"
                          : "bg-red-500/10 text-red-400 border border-red-500/20"
                      }`}
                    >
                      {r.sign === "positive" ? "Позитив" : "Негатив"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
        <h4 className="text-indigo-400 font-semibold mb-4 flex items-center gap-2">
          <Target size={18} />
          Справедливая цена
        </h4>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { title: "По модели DCF", data: data.fairValue.dcf },
            { title: "Исторический P/E", data: data.fairValue.pe },
            { title: "Доходность vs Ставка", data: data.fairValue.yield },
          ].map((m, i) => (
            <div
              key={i}
              className="bg-slate-900 rounded-lg p-4 border border-slate-700/50"
            >
              <div className="text-slate-400 text-sm mb-3">{m.title}</div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs text-red-400">Bear</span>
                <span className="text-sm font-mono text-white">
                  {m.data.bear} ₽
                </span>
              </div>
              <div className="flex justify-between items-center mb-2 bg-indigo-500/10 -mx-2 px-2 py-1 rounded border border-indigo-500/20">
                <span className="text-xs text-indigo-300 font-bold">Base</span>
                <span className="text-base font-bold font-mono text-white">
                  {m.data.base} ₽
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-green-400">Bull</span>
                <span className="text-sm font-mono text-white">
                  {m.data.bull} ₽
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderDeepDive = () => (
    <div className="space-y-4">
      <div className="bg-indigo-500/10 border border-indigo-500/20 text-indigo-200 p-4 rounded-xl flex items-start gap-3">
        <Info size={20} className="mt-0.5 flex-shrink-0" />
        <p className="text-sm">
          Глубокий разбор собирает данные по бизнес-модели, финансам и
          макро-среде, формируя фундамент для оценки.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {data.deepDive.map((d, i) => (
          <div
            key={i}
            className="bg-slate-800 p-5 rounded-xl border border-slate-700"
          >
            <h4 className="text-white font-semibold mb-2 flex items-center gap-2">
              <Layers size={16} className="text-indigo-400" />
              {d.category}
            </h4>
            <p className="text-slate-300 text-sm">{d.details}</p>
          </div>
        ))}
      </div>
    </div>
  );

  const renderConsilium = () => (
    <div className="space-y-4">
      <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
        <h4 className="text-white font-semibold mb-4 flex items-center gap-2">
          <Users size={18} className="text-indigo-400" />
          Консилиум аналитиков
        </h4>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-slate-400 uppercase border-b border-slate-700">
              <tr>
                <th className="px-4 py-3">Брокер</th>
                <th className="px-4 py-3">Дата</th>
                <th className="px-4 py-3">Рекомендация</th>
                <th className="px-4 py-3 text-right">Target</th>
                <th className="px-4 py-3">Аргументы</th>
                <th className="px-4 py-3">Платформа</th>
              </tr>
            </thead>
            <tbody>
              {data.consilium.map((c, i) => (
                <tr key={i} className="border-b border-slate-700/50">
                  <td className="px-4 py-3 text-white font-medium">
                    {c.broker}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{c.date}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs ${
                        c.rec === "Покупать"
                          ? "bg-green-500/20 text-green-400"
                          : "bg-amber-500/20 text-amber-400"
                      }`}
                    >
                      {c.rec}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-white">
                    {c.target} ₽
                  </td>
                  <td className="px-4 py-3 text-slate-300 text-xs max-w-xs truncate">
                    {c.args}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs font-semibold ${
                        c.match === "Согласны"
                          ? "text-green-400"
                          : "text-amber-400"
                      }`}
                    >
                      {c.match}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );

  const renderStressTest = () => {
    const results = {
      rate_up: {
        title: "Ставка +2 п.п.",
        revenue: "+18%",
        margin: "13.5%",
        profit: "-12%",
        fair: "3 650 ₽",
        delta: "-14%",
        text: "Главный канал ухудшения — более высокая ставка дисконтирования и замедление роста.",
      },
      inflation: {
        title: "Рост инфляции",
        revenue: "+20%",
        margin: "12.8%",
        profit: "-15%",
        fair: "3 520 ₽",
        delta: "-16%",
        text: "Главный канал ухудшения — рост издержек и сжатие маржи.",
      },
      recession: {
        title: "Замедление экономики",
        revenue: "+14%",
        margin: "12.0%",
        profit: "-22%",
        fair: "3 300 ₽",
        delta: "-21%",
        text: "Главный канал ухудшения — замедление рекламы, e-commerce и потребительского спроса.",
      },
    };

    const result = stressScenario ? results[stressScenario] : null;

    return (
      <div className="space-y-6">
        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <h4 className="text-white font-semibold mb-4 flex items-center gap-2">
            <Zap size={18} className="text-indigo-400" />
            Выберите сценарий шока
          </h4>

          <div className="flex flex-wrap gap-3 mb-6">
            {[
              { id: "rate_up", label: "Ставка +2 п.п." },
              { id: "inflation", label: "Рост инфляции" },
              { id: "recession", label: "Замедление экономики" },
            ].map((scen) => (
              <button
                key={scen.id}
                onClick={() => setStressScenario(scen.id)}
                className={`px-4 py-2 rounded-lg text-sm transition-colors border ${
                  stressScenario === scen.id
                    ? "bg-indigo-600 border-indigo-500 text-white"
                    : "bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200"
                }`}
              >
                {scen.label}
              </button>
            ))}
          </div>

          {result ? (
            <div className="bg-slate-900 p-5 rounded-xl border border-slate-700 relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                <ShieldAlert size={100} />
              </div>

              <h5 className="text-indigo-400 font-semibold mb-4">
                Результат симуляции: {result.title}
              </h5>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="bg-slate-800 p-3 rounded">
                  <div className="text-slate-400 text-xs mb-1">
                    Выручка 2027
                  </div>
                  <div className="text-white font-mono">{result.revenue}</div>
                </div>
                <div className="bg-slate-800 p-3 rounded">
                  <div className="text-slate-400 text-xs mb-1">
                    EBITDA margin
                  </div>
                  <div className="text-white font-mono">{result.margin}</div>
                </div>
                <div className="bg-slate-800 p-3 rounded">
                  <div className="text-slate-400 text-xs mb-1">
                    Чистая прибыль
                  </div>
                  <div className="text-red-400 font-mono">{result.profit}</div>
                </div>
                <div className="bg-slate-800 p-3 rounded border border-red-500/30">
                  <div className="text-slate-400 text-xs mb-1">Цена по DCF</div>
                  <div className="text-white font-mono text-lg">
                    {result.fair}{" "}
                    <span className="text-red-400 text-sm">
                      ({result.delta})
                    </span>
                  </div>
                </div>
              </div>

              <div className="bg-red-500/10 border-l-4 border-red-500 p-3 rounded-r text-sm text-slate-300">
                <span className="font-semibold text-red-400">
                  Интерпретация платформы:{" "}
                </span>
                {result.text}
              </div>
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500 text-sm bg-slate-900 rounded-xl border border-slate-700 border-dashed">
              Выберите сценарий выше, чтобы запустить пересчёт финансовой модели
              компании.
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 mb-2">
        <button
          onClick={onBack}
          className="text-slate-400 hover:text-white transition-colors bg-slate-800 p-2 rounded-full border border-slate-700"
        >
          <ChevronRight className="rotate-180" size={20} />
        </button>

        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            {company.name}
            <span className="text-slate-500 text-lg font-normal">
              {company.ticker}
            </span>
          </h2>

          <div className="flex items-center gap-3 text-sm mt-1">
            <span className="text-slate-400">{company.sector}</span>
            <span className="text-white font-mono font-medium">
              {formatCurrency(company.price)}
            </span>
            <span
              className={`font-medium ${
                company.change >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {company.change > 0 ? "+" : ""}
              {company.change}%
            </span>
          </div>
        </div>
      </div>

      <div className="flex bg-slate-800 p-1 rounded-lg overflow-x-auto">
        {[
          { id: "overview", label: "1. Обзор" },
          { id: "deep", label: "2. Глубокий разбор" },
          { id: "consilium", label: "3. Консилиум" },
          { id: "stress", label: "4. Стресс-тест" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`whitespace-nowrap px-4 py-2 text-sm font-medium rounded-md transition-colors flex-1 ${
              tab === t.id
                ? "bg-indigo-600 text-white shadow"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {company.ticker === "YDEX" ? (
        <>
          {tab === "overview" && renderOverview()}
          {tab === "deep" && renderDeepDive()}
          {tab === "consilium" && renderConsilium()}
          {tab === "stress" && renderStressTest()}
        </>
      ) : (
        <div className="bg-slate-800 p-10 text-center rounded-xl border border-slate-700">
          <AlertTriangle size={48} className="mx-auto text-slate-500 mb-4" />
          <h3 className="text-xl text-white font-medium mb-2">
            Демонстрационные данные
          </h3>
          <p className="text-slate-400 max-w-md mx-auto">
            В MVP версии подробные данные заполнены только для компании{" "}
            <b>МКПАО Яндекс (YDEX)</b>.
          </p>
          <button
            onClick={onBack}
            className="mt-6 text-indigo-400 hover:text-indigo-300 underline"
          >
            Вернуться к списку
          </button>
        </div>
      )}
    </div>
  );
};

// =========================
// PORTFOLIO
// =========================

const PortfolioView = () => {
  const [tab, setTab] = useState("holdings");
  const [stressScenario, setStressScenario] = useState("black_swan");
  const [showUploadModal, setShowUploadModal] = useState(false);

  const stats = useMemo(() => {
    const totalValue = MOCK_PORTFOLIO.reduce(
      (acc, p) => acc + p.shares * p.currentPrice,
      0
    );
    const totalCost = MOCK_PORTFOLIO.reduce(
      (acc, p) => acc + p.shares * p.avgPrice,
      0
    );
    const totalProfit = totalValue - totalCost;
    const profitPct = (totalProfit / totalCost) * 100;

    const avgBeta = MOCK_PORTFOLIO.reduce(
      (acc, p) => acc + p.beta * ((p.shares * p.currentPrice) / totalValue),
      0
    );

    const avgYield = MOCK_PORTFOLIO.reduce(
      (acc, p) => acc + p.divYield * ((p.shares * p.currentPrice) / totalValue),
      0
    );

    const portExp = MOCK_PORTFOLIO.reduce(
      (acc, p) =>
        acc + p.expReturn * ((p.shares * p.currentPrice) / totalValue),
      0
    );

    const portStd = MOCK_PORTFOLIO.reduce(
      (acc, p) => acc + p.stdDev * ((p.shares * p.currentPrice) / totalValue),
      0
    );

    return {
      totalValue,
      totalCost,
      totalProfit,
      profitPct,
      avgBeta,
      avgYield,
      portExp,
      portStd,
    };
  }, []);

  const portfolioScore = 68;

  const stressMap = {
    black_swan: {
      label: "Черный лебедь (-20%)",
      drop: stats.avgBeta * 20,
      valueLoss: stats.totalValue * (stats.avgBeta * 0.2),
      text: "Сценарий широкой рыночной коррекции. Главный риск — концентрация в нескольких бумагах и высокий удельный вес финансового сектора.",
    },
    rate_up: {
      label: "Ставка ЦБ +5%",
      drop: 11.8,
      valueLoss: stats.totalValue * 0.118,
      text: "Наиболее чувствителен банковский блок и бумаги с длинной дюрацией оценки.",
    },
    oil_crash: {
      label: "Крах нефти ($40)",
      drop: 8.6,
      valueLoss: stats.totalValue * 0.086,
      text: "Главный канал — ухудшение переоценки сырьевого сектора и давление на внешний баланс.",
    },
  };

  const currentStress = stressMap[stressScenario];

  const renderHoldings = () => (
    <div className="space-y-8 p-4">
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="p-4 border-b border-slate-700 bg-slate-800/50 flex justify-between items-center">
          <h4 className="text-white font-semibold">Ваши позиции</h4>
          <button className="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded text-sm transition-colors">
            + Добавить сделку
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500 uppercase bg-slate-900/50">
              <tr>
                <th className="px-6 py-4">Актив</th>
                <th className="px-6 py-4 text-right">Кол-во</th>
                <th className="px-6 py-4 text-right">Средняя</th>
                <th className="px-6 py-4 text-right">Текущая</th>
                <th className="px-6 py-4 text-right">Доля</th>
                <th className="px-6 py-4 text-right">Результат</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {MOCK_PORTFOLIO.map((p) => {
                const value = p.shares * p.currentPrice;
                const weight = (value / stats.totalValue) * 100;
                const profit = p.shares * (p.currentPrice - p.avgPrice);
                const pPct = (p.currentPrice / p.avgPrice - 1) * 100;

                return (
                  <tr key={p.ticker}>
                    <td className="px-6 py-4 font-bold text-white">
                      {p.ticker}
                      <span className="block text-xs text-slate-500 font-normal">
                        {p.name}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right text-slate-300">
                      {p.shares}
                    </td>
                    <td className="px-6 py-4 text-right text-slate-400">
                      {formatCurrency(p.avgPrice)}
                    </td>
                    <td className="px-6 py-4 text-right text-white font-mono">
                      {formatCurrency(p.currentPrice)}
                    </td>
                    <td className="px-6 py-4 text-right text-slate-300">
                      <div className="flex items-center justify-end gap-2">
                        <span className="font-mono">{weight.toFixed(1)}%</span>
                        <div className="w-12 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-indigo-500"
                            style={{ width: `${weight}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td
                      className={`px-6 py-4 text-right font-bold ${
                        profit >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {profit >= 0 ? "+" : ""}
                      {formatCurrency(profit)}
                      <span className="block text-xs font-normal">
                        {pPct >= 0 ? "+" : ""}
                        {pPct.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="p-4 border-b border-slate-700 bg-slate-800/50">
          <h4 className="text-white font-semibold">
            Аналитические метрики портфеля
          </h4>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500 uppercase bg-slate-900/50">
              <tr>
                <th className="px-6 py-4">Актив</th>
                <th className="px-6 py-4">Ожид. доходность</th>
                <th className="px-6 py-4">Std Deviation</th>
                <th className="px-6 py-4">P/E тек.</th>
                <th className="px-6 py-4">P/E ист.</th>
                <th className="px-6 py-4">Beta</th>
                <th className="px-6 py-4">Див. дох.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {MOCK_PORTFOLIO.map((p) => (
                <tr key={`${p.ticker}_metrics`}>
                  <td className="px-6 py-4 font-bold text-white">{p.ticker}</td>
                  <td className="px-6 py-4 text-green-400">+{p.expReturn}%</td>
                  <td className="px-6 py-4 text-slate-400">{p.stdDev}%</td>
                  <td className="px-6 py-4 text-white">{p.pe}x</td>
                  <td className="px-6 py-4 text-slate-500">{p.pe_hist}x</td>
                  <td className="px-6 py-4 text-indigo-400 font-mono">
                    {p.beta}
                  </td>
                  <td className="px-6 py-4 text-amber-400">{p.divYield}%</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t border-slate-700 bg-slate-900/40">
              <tr>
                <td className="px-6 py-4 font-semibold text-white">Портфель</td>
                <td className="px-6 py-4 text-green-400">
                  +{stats.portExp.toFixed(1)}%
                </td>
                <td className="px-6 py-4 text-slate-300">
                  {stats.portStd.toFixed(1)}%
                </td>
                <td className="px-6 py-4 text-slate-500">—</td>
                <td className="px-6 py-4 text-slate-500">—</td>
                <td className="px-6 py-4 text-indigo-400 font-mono">
                  {stats.avgBeta.toFixed(2)}
                </td>
                <td className="px-6 py-4 text-amber-400">
                  {stats.avgYield.toFixed(1)}%
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  );

  const renderAggregate = () => (
    <div className="p-4">
      <h3 className="text-white font-semibold mb-4">
        Агрегирующие метрики и Индекс портфеля
      </h3>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="col-span-1 bg-slate-900 border border-slate-700 rounded-xl p-6 flex flex-col items-center justify-center">
          <div className="text-slate-400 text-sm mb-2">Portfolio Score</div>
          <div className="text-6xl font-bold text-amber-400 mb-2">
            {portfolioScore}
            <span className="text-2xl text-slate-500">/100</span>
          </div>
          <div className="px-3 py-1 bg-amber-500/10 text-amber-500 rounded-full text-sm font-medium border border-amber-500/20">
            Умеренное качество (Fair)
          </div>
        </div>

        <div className="col-span-1 lg:col-span-2 grid grid-cols-2 gap-4">
          {[
            {
              label: "Соответствие риску",
              val: "8/10",
              desc: "Подходит для консервативного инвестора",
              color: "text-green-400",
            },
            {
              label: "Доходность к риску",
              val: "4.5/10",
              desc: "Низкая премия за риск",
              color: "text-red-400",
            },
            {
              label: "Защита от просадок",
              val: "7/10",
              desc: "Хорошая дивидендная подушка",
              color: "text-amber-400",
            },
            {
              label: "Диверсификация",
              val: "3/10",
              desc: "Сильный перекос в РФ Финансы",
              color: "text-red-400",
            },
          ].map((m, i) => (
            <div
              key={i}
              className="bg-slate-900 border border-slate-700 p-4 rounded-lg"
            >
              <div className="text-slate-400 text-xs mb-1">{m.label}</div>
              <div className={`text-xl font-bold font-mono ${m.color}`}>
                {m.val}
              </div>
              <div className="text-xs text-slate-500 mt-1">{m.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderCorrelation = () => {
    const labels = ["SBER", "LKOH", "YDEX"];

    return (
      <div className="p-4">
        <h3 className="text-white font-semibold mb-2">
          Оценка диверсификации и скрытой концентрации
        </h3>
        <p className="text-sm text-slate-400 mb-6">
          Тепловая карта показывает, как активы движутся относительно друг друга
          (1.0 = синхронно, 0 = независимо).
        </p>

        <div className="overflow-x-auto">
          <div className="min-w-[420px] max-w-md mx-auto bg-slate-900 p-4 rounded-xl border border-slate-700">
            <div className="grid grid-cols-4 gap-1 text-center text-xs font-mono">
              <div className="p-2"></div>
              {labels.map((label) => (
                <div key={`h-${label}`} className="p-2 text-slate-400">
                  {label}
                </div>
              ))}
              {labels.map((rowLabel, i) => (
                <React.Fragment key={rowLabel}>
                  <div className="p-2 text-slate-400 text-right flex items-center justify-end">
                    {rowLabel}
                  </div>
                  {MOCK_CORRELATION[i].map((value, j) => (
                    <div
                      key={`${i}-${j}`}
                      className={`p-2 rounded ${
                        value >= 0.9
                          ? "bg-indigo-500 text-white"
                          : value >= 0.4
                          ? "bg-indigo-500/40 text-indigo-100"
                          : value >= 0.1
                          ? "bg-indigo-500/20 text-indigo-200"
                          : "bg-indigo-500/10 text-indigo-200"
                      }`}
                    >
                      {value.toFixed(2)}
                    </div>
                  ))}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-6 bg-amber-500/10 border border-amber-500/20 p-4 rounded-lg text-sm text-amber-200">
          <span className="font-bold">Вывод:</span> У портфеля средняя
          корреляция между Сбером и Лукойлом (0.45) из-за общей
          макро-зависимости от курса рубля и ставки. Яндекс выступает хорошим
          диверсификатором.
        </div>
      </div>
    );
  };

  const renderAiDiagnosis = () => (
    <div className="p-6">
      <h3 className="text-white font-semibold mb-4 text-lg flex items-center gap-2">
        <Zap size={20} className="text-indigo-400" />
        Общий диагноз портфеля
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="space-y-2">
          <h4 className="text-green-400 font-medium">
            Щит портфеля (Аргументы ЗА)
          </h4>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <span className="text-green-500 mt-0.5">•</span>
              Высокая ожидаемая див. доходность (около 11% годовых), создающая
              подушку безопасности.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-500 mt-0.5">•</span>
              Наличие Яндекса защищает портфель от стагнации, добавляя сильный
              фактор роста.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-500 mt-0.5">•</span>
              Устойчивость к девальвации рубля благодаря доле экспортёра
              (Лукойл).
            </li>
          </ul>
        </div>

        <div className="space-y-2">
          <h4 className="text-red-400 font-medium">
            Уязвимости (Аргументы ПРОТИВ)
          </h4>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              Жёсткая концентрация в 3 бумагах — риск отдельных корпоративных
              событий критичен.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              Сильная зависимость финансового сектора от роста ключевой ставки.
            </li>
            <li className="flex items-start gap-2">
              <span className="text-red-500 mt-0.5">•</span>
              Отсутствие защитных активов при высоких ставках на рынке.
            </li>
          </ul>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-700 p-4 rounded-xl">
        <h4 className="text-indigo-400 font-medium mb-2 text-sm">
          Резюме платформы
        </h4>
        <p className="text-slate-300 text-sm leading-relaxed">
          Портфель представляет собой агрессивную ставку на российские голубые
          фишки с перекосом в дивидендную историю Сбербанка. Он хорошо держит
          инфляционный удар, но уязвим к сценарию жесткой ДКП и геополитическим
          шокам. Базовая рекомендация — ребалансировка и добавление защитных
          инструментов.
        </p>
      </div>
    </div>
  );

  const renderStress = () => (
    <div className="p-6 space-y-6">
      <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5">
        <h4 className="text-white font-semibold mb-4 flex items-center gap-2">
          <ShieldAlert size={18} className="text-indigo-400" />
          Стресс-тестирование портфеля
        </h4>

        <div className="flex flex-wrap gap-3 mb-6">
          {[
            { id: "black_swan", label: "Черный лебедь (-20%)" },
            { id: "rate_up", label: "Ставка ЦБ +5%" },
            { id: "oil_crash", label: "Крах нефти ($40)" },
          ].map((s) => (
            <button
              key={s.id}
              onClick={() => setStressScenario(s.id)}
              className={`px-4 py-2 rounded-lg text-sm border transition-colors ${
                stressScenario === s.id
                  ? "bg-indigo-600 border-indigo-500 text-white"
                  : "bg-slate-900 border-slate-700 text-slate-300 hover:border-red-500 hover:text-red-400"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-700">
            <div className="text-xs text-slate-500 uppercase mb-1">
              Ожидаемое падение
            </div>
            <div className="text-2xl font-bold text-red-400">
              -{currentStress.drop.toFixed(1)}%
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {currentStress.label}
            </div>
          </div>

          <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-700">
            <div className="text-xs text-slate-500 uppercase mb-1">
              Потеря стоимости
            </div>
            <div className="text-2xl font-bold text-white">
              {formatCurrency(currentStress.valueLoss)}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Оценка по текущей структуре портфеля
            </div>
          </div>
        </div>

        <div className="mt-4 bg-red-500/10 border-l-4 border-red-500 p-4 rounded-r text-sm text-slate-300">
          <span className="font-semibold text-red-400">
            Интерпретация платформы:{" "}
          </span>
          {currentStress.text}
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-center gap-4 bg-indigo-600/10 border border-indigo-500/30 p-6 rounded-2xl">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-indigo-500 text-white rounded-xl shadow-lg shadow-indigo-500/20">
            <Upload size={24} />
          </div>
          <div>
            <h3 className="text-white font-bold text-lg">Загрузить портфель</h3>
            <p className="text-indigo-200/70 text-sm">
              Импортируйте данные через текст или фото отчета брокера
            </p>
          </div>
        </div>

        <button
          onClick={() => setShowUploadModal(true)}
          className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-2.5 rounded-xl font-semibold transition-all flex items-center gap-2"
        >
          <Plus size={18} />
          Начать импорт
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <div className="text-slate-500 text-xs mb-1 uppercase">Стоимость</div>
          <div className="text-2xl font-bold text-white font-mono">
            {formatCurrency(stats.totalValue)}
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <div className="text-slate-500 text-xs mb-1 uppercase">Прибыль</div>
          <div
            className={`text-2xl font-bold font-mono ${
              stats.totalProfit >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            {stats.totalProfit >= 0 ? "+" : ""}
            {formatCurrency(stats.totalProfit)}
          </div>
          <div
            className={`text-xs mt-1 ${
              stats.profitPct >= 0 ? "text-green-500" : "text-red-500"
            }`}
          >
            {formatPercent(stats.profitPct, 2)}
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <div className="text-slate-500 text-xs mb-1 uppercase">
            Beta (Риск)
          </div>
          <div className="text-2xl font-bold text-indigo-400 font-mono">
            {stats.avgBeta.toFixed(2)}
          </div>
        </div>

        <div className="bg-slate-800 p-5 rounded-xl border border-slate-700">
          <div className="text-slate-500 text-xs mb-1 uppercase">
            Див. доходность
          </div>
          <div className="text-2xl font-bold text-amber-400 font-mono">
            {stats.avgYield.toFixed(1)}%
          </div>
        </div>
      </div>

      <div className="flex bg-slate-800 border-b border-slate-700 overflow-x-auto">
        {[
          { id: "holdings", label: "Состав" },
          { id: "metrics", label: "Агрегирующая таблица" },
          { id: "correlation", label: "Матрица корреляций" },
          { id: "ai", label: "ИИ-Диагноз" },
          { id: "stress", label: "Стресс-тест" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-6 py-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
              tab === t.id
                ? "border-indigo-500 text-indigo-400 bg-slate-800/50"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bg-slate-800 rounded-xl border border-slate-700 p-1 min-h-[400px]">
        {tab === "holdings" && renderHoldings()}
        {tab === "metrics" && renderAggregate()}
        {tab === "correlation" && renderCorrelation()}
        {tab === "ai" && renderAiDiagnosis()}
        {tab === "stress" && renderStress()}
      </div>

      {showUploadModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 p-8 rounded-3xl max-w-md w-full relative">
            <button
              onClick={() => setShowUploadModal(false)}
              className="absolute top-4 right-4 text-slate-500 hover:text-white"
            >
              ✕
            </button>

            <h3 className="text-2xl font-bold text-white mb-4">
              Импорт активов
            </h3>

            <div className="space-y-4">
              <div className="p-4 border-2 border-dashed border-slate-700 rounded-xl text-center hover:border-indigo-500 transition-colors cursor-pointer group">
                <Upload
                  size={32}
                  className="mx-auto text-slate-600 mb-2 group-hover:text-indigo-500"
                />
                <p className="text-slate-400 text-sm">
                  Перетащите скриншот из брокера
                </p>
              </div>

              <textarea
                placeholder="Или введите текст: SBER 100 280.50..."
                className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-white text-sm focus:outline-none focus:border-indigo-500 h-24"
              />

              <button className="w-full bg-indigo-600 text-white py-3 rounded-xl font-bold">
                Загрузить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// =========================
// PROFILE
// =========================

const ProfileView = () => (
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
    <div className="lg:col-span-1 space-y-6">
      <div className="bg-slate-800 p-6 rounded-2xl border border-slate-700">
        <div className="flex flex-col items-center text-center">
          <div className="w-24 h-24 bg-gradient-to-tr from-indigo-600 to-indigo-400 rounded-full flex items-center justify-center mb-4 border-4 border-slate-900 shadow-xl">
            <User size={48} className="text-white" />
          </div>
          <h3 className="text-xl font-bold text-white">Александр Инвестор</h3>
          <p className="text-slate-500 text-sm">ID: 4829-BS-2026</p>
          <div className="mt-4 flex gap-2">
            <span className="px-3 py-1 bg-green-500/10 text-green-400 border border-green-500/20 rounded-full text-xs font-bold flex items-center gap-1">
              <ShieldCheck size={12} />
              Верифицирован
            </span>
          </div>
        </div>
      </div>

      <div className="bg-gradient-to-br from-indigo-600 to-indigo-800 p-6 rounded-2xl text-white shadow-xl">
        <div className="flex justify-between items-start mb-6">
          <div className="p-2 bg-white/20 rounded-lg">
            <CreditCard size={24} />
          </div>
          <span className="text-xs bg-white/20 px-2 py-1 rounded uppercase font-bold tracking-widest">
            Premium
          </span>
        </div>

        <div className="mb-6">
          <p className="text-indigo-100 text-xs uppercase tracking-wider mb-1">
            План подписки
          </p>
          <h4 className="text-2xl font-bold">Базис.Максимум</h4>
        </div>

        <div className="space-y-2 text-sm text-indigo-100">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
            Безлимитный DCF-анализ
          </div>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 bg-white rounded-full"></div>
            Карта рынка (Real-time)
          </div>
        </div>

        <button className="w-full mt-6 bg-white text-indigo-600 py-2.5 rounded-xl font-bold hover:bg-indigo-50 transition-colors">
          Управлять подпиской
        </button>
      </div>
    </div>

    <div className="lg:col-span-2 space-y-6">
      <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
        <div className="p-6 border-b border-slate-700">
          <h3 className="text-xl font-bold text-white">Настройки платформы</h3>
        </div>

        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <label className="block">
              <span className="text-slate-400 text-sm">Валюта отображения</span>
              <select className="mt-1 w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white">
                <option>RUB (₽)</option>
                <option>USD ($)</option>
                <option>CNY (¥)</option>
              </select>
            </label>

            <label className="block">
              <span className="text-slate-400 text-sm">Источник данных</span>
              <select className="mt-1 w-full bg-slate-900 border border-slate-700 rounded-xl p-2.5 text-white">
                <option>MOEX ISS API</option>
                <option>Refinitiv (Beta)</option>
              </select>
            </label>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-slate-900/50 rounded-xl border border-slate-700">
              <span className="text-slate-300 text-sm">
                Уведомления о гэпах
              </span>
              <div className="w-10 h-5 bg-indigo-600 rounded-full relative">
                <div className="w-4 h-4 bg-white rounded-full absolute right-0.5 top-0.5 shadow"></div>
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-900/50 rounded-xl border border-slate-700">
              <span className="text-slate-300 text-sm">Публичный профиль</span>
              <div className="w-10 h-5 bg-slate-700 rounded-full relative">
                <div className="w-4 h-4 bg-white rounded-full absolute left-0.5 top-0.5 shadow"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-slate-800 p-6 rounded-2xl border border-slate-700">
        <div className="flex items-center gap-3 mb-6">
          <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg">
            <Layout size={20} />
          </div>
          <h3 className="text-xl font-bold text-white">
            Планирование (Estate Plan)
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-slate-900/50 border border-slate-700 rounded-xl hover:border-indigo-500 transition-colors cursor-pointer group">
            <h4 className="text-white font-semibold mb-1 group-hover:text-indigo-400">
              Наследование
            </h4>
            <p className="text-slate-500 text-xs leading-relaxed">
              Настройте автоматическую передачу прав доступа к аналитике и
              портфелям.
            </p>
          </div>

          <div className="p-4 bg-slate-900/50 border border-slate-700 rounded-xl hover:border-indigo-500 transition-colors cursor-pointer group">
            <h4 className="text-white font-semibold mb-1 group-hover:text-indigo-400">
              Налоговая оптимизация
            </h4>
            <p className="text-slate-500 text-xs leading-relaxed">
              Календарь ЛДВ (льгота на долгосрочное владение) и расчет НДФЛ.
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
);

// =========================
// APP
// =========================

export default function App() {
  const [activeTab, setActiveTab] = useState("market");
  const [selectedCompany, setSelectedCompany] = useState(null);

  const renderContent = () => {
    if (selectedCompany) {
      return (
        <CompanyCard
          company={selectedCompany}
          onBack={() => setSelectedCompany(null)}
        />
      );
    }

    switch (activeTab) {
      case "market":
        return <MarketObserver />;
      case "screener":
        return <CompanyList onSelectCompany={setSelectedCompany} />;
      case "portfolio":
        return <PortfolioView />;
      case "profile":
        return <ProfileView />;
      default:
        return <MarketObserver />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans selection:bg-indigo-500/30">
      <Header
        activeTab={activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setSelectedCompany(null);
        }}
      />

      <main className="max-w-7xl mx-auto p-4 md:p-8">{renderContent()}</main>

      <footer className="mt-20 border-t border-slate-900 p-8 text-center text-slate-600 text-sm">
        <p>
          © 2026 Платформа Базис — Профессиональная аналитика для частных
          инвесторов.
        </p>
        <p className="mt-2 text-slate-700">
          Не является индивидуальной инвестиционной рекомендацией.
        </p>
      </footer>
    </div>
  );
}
