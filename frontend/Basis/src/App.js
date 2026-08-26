import { claimGuestData } from "./guest";
import { ScrollRail } from "./design/ScrollRail";
import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import DesignSystem from "./design/DesignSystem";
import { initAnalytics, trackPageView, logPageView } from "./analytics";
import { BasisLogomark } from "./design/logomarks";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Search,
  SlidersHorizontal,
  Scale,
  Wallet,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Activity,
  Briefcase,
  Target,
  PieChart,
  Zap,
  ChevronRight,
  Globe,
  Calendar,
  Sparkles,
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
  FileText,
  Settings,
  Sun,
  Moon,
  LogOut,
  X,
  Trash2,
  ChevronDown,
  ChevronUp,
  Check,
  Pencil,
  Newspaper,
  ExternalLink,
  Clock,
  MoreHorizontal,
} from "lucide-react";
import { Button, Card, Badge, Chip, Input, IconButton, Tooltip, Table, Delta, KpiTile, usePrefersReducedMotion, ComingSoonView } from "./design/primitives";
import { formatMoney, formatPercent as fmtPercent, formatNumber, formatNumber as fmtNumber, formatMultiple } from "./design/format";
import { WeightBar, MetricBar, CorrelationHeatmap, ImpactBar, useCountUp, catFor } from "./design/PortfolioViz";
import { CompanyLogo } from "./design/CompanyLogo";
import { Prose, LeadStatement, KeyTakeaway, Disclosure, ANALYST_MD } from "./design/textblocks";
import { CompanyIdentityBlock, PricePanel, MetricStrip, ResearchTabs as NeoResearchTabs, DecisionSupportRail } from "./company/neo";
// ─── ДРОБЛЕНИЕ БАНДЛА (владелец, 2026-07-30) ───────────────────────────────────
// Бандл был 3,0 МБ ОДНИМ куском: человеку, пришедшему из поиска на карточку одной
// компании, отдавалась вся платформа разом — портфель, скринеры, стресс-тест, карты.
// Замер с боя: 2,2 с только на скачивание, плюс парсинг. Бьёт и по впечатлению
// («открывается медленно»), и по ранжированию — скорость входит в оценку страницы.
// Ленивыми сделаны разделы, которые НЕ нужны для просмотра карточки; сама карточка и
// лендинг остаются в основном бандле — именно на них приходят из поиска.
const ScreenerNeo = React.lazy(() => import("./screener/ScreenerNeo"));
const BondScreenerNeo = React.lazy(() => import("./screener/BondScreenerNeo"));
const MarketNeo = React.lazy(() => import("./market/MarketNeo"));
import { IndexHubView, IndexDetailView, FearGreedDetailView } from "./market/IndexViews";
import "./market/market-m5.css";
import LandingNeo from "./market/LandingNeo";
import BusinessModelTab from "./company/BusinessModelTab";
import FinanceTab from "./company/FinanceTab";
import GovernanceTab from "./company/GovernanceTab";
import "./styles/governance.css";
import "./styles/macro.css";
import "./styles/observer-v2.css";
import { BondRiskAnalysis } from "./design/bondrisk";
import { AppearGroup, PageDecor, DECOR_ENABLED } from "./design/motion";
import {
  OBS_ZONES,
  ObsSectionPlaceholder,
  ObsNewsFeed,
  ObsCalendar,
  ObsReports,
  ObsCorporateNews,
  ObsMacroArticles,
  ObsBusinessArticles,
  ObsGeopolitics,
  ObsInstitutions,
  ObsMarketPulse,
  ObsMarketMap,
  ObsAiReview,
  ObsEconomy,
  ObsHorizonChip,
} from "./observer/ObsPanels";
import {
  NewsFeed,
  MacroView,
  MarketMaps,
  ObserverReportView,
  GeopoliticsView,
  EarningsFeed,
  CalendarView,
} from "./observer/ObsLegacyViews";
const PortfolioV2 = React.lazy(() => import("./portfolio/PortfolioViews").then((m) => ({ default: m.PortfolioV2 })));
const StressTestView = React.lazy(() => import("./portfolio/StressTestView"));
import { AuthModal } from "./account/AccountPanels";
import RegisterNudge from "./account/RegisterNudge";
import PricingView from "./account/PricingView";
import ProfileView from "./account/ProfileView";
import { CompanyCard, CompaniesView, NEO_CARD, BondCard, FuturesCard, FundCard, SpotCard } from "./company/CompanyCardView";
import AssistantView from "./AssistantView";
import { AssistantNudge } from "./design/AssistantNudge";
import "./styles/compare.css";
const ScreenerCompareView = React.lazy(() => import("./screener/ScreenerCompareShell"));
import "./styles/mobile-nav.css";
import { useMobileSidebarDrawer, MobileSectionBar, MobileDrawerBackdrop, useDesktopSidebarCollapse, DesktopSidebarCollapse, DesktopSidebarHandle } from "./design/MobileSidebarDrawer";
import useTourEngine from "./tour/useTourEngine";
import TourOverlay from "./tour/TourOverlay";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";

function ObserverV2({
  token, onSelectCompany, onOpenBond, onOpenFuture, onOpenFund, onOpenSpot,
  onSelectIndex, onOpenFearGreed, onOpenIndexHub,
  indexTicker, showIndexHub, onCloseIndexUI,
  forceSection, driverChart, forceEconIndicator, onOpenPortfolio,
}) {
  // forceSection — вход с Рынка (клик по драйверу «Нефть»/«USD·RUB»/«ОФЗ» → "pulse",
  // «Ставка ЦБ» → "economy"); ObserverV2 монтируется заново при каждом входе на
  // activeTab==="overview" (см. App.js renderView), так что initial state достаточно —
  // не нужен эффект-синхронизация.
  const [activeSection, setActiveSection] = useState(forceSection || "news");
  const [portfolioOnly, setPortfolioOnly] = useState(false);
  // Мобильный (≤760px) выезжающий сайдбар — тот же переиспользуемый паттерн,
  // что у Портфеля/Скринера (design/MobileSidebarDrawer.jsx). Обозреватель —
  // самый крупный из четырёх экранов с докованным .obs-sidebar, владелец
  // (2026-07-21, третий заход): «не сделал возможность убрать сайдбар и
  // добавить — как в портфельной аналитике и скринере».
  const [drawerOpen, setDrawerOpen, drawerNarrow] = useMobileSidebarDrawer();
  const [sbCollapsed, toggleSb] = useDesktopSidebarCollapse();
  const activeSectionLabel = OBS_ZONES.flatMap((z) => z.items).find((it) => it.id === activeSection)?.label;
  // Страницы индексов (владелец: «нужно, чтобы сайдбар оставался виден и на
  // самой странице индекса, а не только после возврата назад») рендерятся
  // ВНУТРИ этого же .obs-shell — сайдбар остаётся, меняется только .obs-main.
  // Клик по любому пункту сайдбара ниже явно закрывает режим индекса
  // (onCloseIndexUI) — иначе пользователь «застревал» бы и там тоже.
  const inIndexMode = Boolean(indexTicker || showIndexHub);
  // Явная кнопка «← Вернуться к обзору» сверху слева на странице индекса
  // (владелец) — ведёт конкретно в «Обзор рынка», откуда обычно и попадают
  // на индексы (не просто «закрыть», а предсказуемо в конкретный раздел).
  const backToOverview = () => { onCloseIndexUI(); setActiveSection("pulse"); };

  const renderSection = () => {
    switch (activeSection) {
      case "news":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Данные</span>
              <h2 className="obs-sec-title">Лента новостей</h2>
            </div>
            <ObsNewsFeed token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
          </div>
        );
      case "economy":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Данные</span>
              <h2 className="obs-sec-title">Экономическая статистика</h2>
            </div>
            <ObsEconomy token={token} forceIndicator={forceEconIndicator} />
          </div>
        );
      case "pulse":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Обзор рынка</h2>
            </div>
            <ObsMarketPulse onSelectCompany={onSelectCompany} onSelectIndex={onSelectIndex} onOpenFearGreed={onOpenFearGreed} driverChart={driverChart} />
          </div>
        );
      case "maps":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Карта рынка</h2>
            </div>
            <ObsMarketMap
              token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany}
              onOpenBond={onOpenBond} onOpenFuture={onOpenFuture} onOpenFund={onOpenFund} onOpenSpot={onOpenSpot}
            />
          </div>
        );
      case "calendar":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Календарь событий</h2>
            </div>
            <ObsCalendar token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
          </div>
        );
      case "reports":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Отчёты</h2>
            </div>
            <ObsReports token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
          </div>
        );
      case "corp-news":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Корп. события</h2>
            </div>
            <ObsCorporateNews token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} onOpenReports={() => { setActiveSection("reports"); syncUrl({ view: "overview", obs: "reports" }); }} />
          </div>
        );
      case "macro":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">Макроэкономика</h2>
              <ObsHorizonChip>горизонт актуальности: дни-недели</ObsHorizonChip>
            </div>
            <ObsMacroArticles token={token} onSelectCompany={onSelectCompany} onOpenPortfolio={onOpenPortfolio}
              onOpenEconomy={() => { setActiveSection("economy"); syncUrl({ view: "overview", obs: "economy" }); }} />
          </div>
        );
      case "business":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">Бизнес</h2>
              <ObsHorizonChip>горизонт актуальности: дни-недели</ObsHorizonChip>
            </div>
            <ObsBusinessArticles />
          </div>
        );
      case "geo":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">Влияние геополитики на российский рынок</h2>
              <ObsHorizonChip>горизонт актуальности: недели-месяцы</ObsHorizonChip>
            </div>
            <ObsGeopolitics token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
          </div>
        );
      case "institutions":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">Институциональная среда</h2>
              <ObsHorizonChip>горизонт актуальности: месяцы-годы</ObsHorizonChip>
            </div>
            <ObsInstitutions token={token} />
          </div>
        );
      case "ai":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">ИИ-обзор и анализ</h2>
            </div>
            <ObsAiReview token={token} onSelectCompany={onSelectCompany} />
          </div>
        );
      default:
        return <ObsSectionPlaceholder sectionId={activeSection} />;
    }
  };

  return (
    <div className={"obs-shell" + (sbCollapsed ? " dsc-collapsed" : "")}>
      {drawerOpen && <MobileDrawerBackdrop onClose={() => setDrawerOpen(false)} />}
      {sbCollapsed && <DesktopSidebarHandle onToggle={toggleSb} />}
      {/* ---- Dark sidebar ---- */}
      <nav
        className={`obs-sidebar msd-drawer${drawerOpen ? " msd-drawer--open" : ""}`}
        aria-label="Разделы Обозревателя"
        /* цель шага тура «Обозреватель» — весь список разделов (tour/tourSteps.js) */
        data-tour="observer"
        inert={drawerNarrow && !drawerOpen}
      >
        <div className="obs-depth-strip" aria-hidden="true" />
        <DesktopSidebarCollapse onToggle={toggleSb} />
        <div className="obs-eyebrow">Обозреватель</div>

        {OBS_ZONES.map((zone) => (
          <div key={zone.id} className="obs-zone">
            <div className="obs-zone-label">{zone.label}</div>
            {zone.items.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`obs-item${!inIndexMode && activeSection === id ? " obs-item--active" : ""}`}
                onClick={() => { onCloseIndexUI(); setActiveSection(id); setDrawerOpen(false); syncUrl({ view: "overview", obs: id }); }}
                aria-current={!inIndexMode && activeSection === id ? "page" : undefined}
              >
                <span className="obs-item__icon"><Icon size={15} aria-hidden="true" /></span>
                {label}
              </button>
            ))}
          </div>
        ))}

        <div className="obs-foot">
          <button
            type="button"
            onClick={() => setPortfolioOnly((v) => !v)}
            aria-pressed={portfolioOnly}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: portfolioOnly ? "var(--accent)" : "transparent",
              border: `1px solid ${portfolioOnly ? "var(--accent)" : "var(--obs-deep-line)"}`,
              color: portfolioOnly ? "#fff" : "var(--obs-deep-ink2)",
              borderRadius: "999px",
              padding: "7px 13px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              width: "100%",
              justifyContent: "center",
              marginBottom: "10px",
              transition: "background 160ms ease, border-color 160ms ease, color 160ms ease",
            }}
          >
            <Briefcase size={13} aria-hidden="true" />
            Только мой портфель
          </button>
        </div>
      </nav>

      {/* ---- Light main area ---- */}
      <main className="obs-main" key={inIndexMode ? `index:${indexTicker || "hub"}` : activeSection}>
        {/* Линия-навигация по длинному разделу (design/ScrollRail): секции — из
            заголовков панелей и глубоких карточек; коротким разделам не рисуется */}
        <ScrollRail minCount={2} deps={[activeSection, inIndexMode]}
          selector='[data-rail], .obs-sec-title, .obs-deep-eyebrow, .obs-main h2, .obs-main h3, .obs-main h4, .obs-main [class*="-card-title"], .obs-main [class*="-sec-t"]' />
        <MobileSectionBar
          title={inIndexMode ? "Индексы" : activeSectionLabel}
          open={drawerOpen}
          onOpenMenu={() => setDrawerOpen(true)}
        />
        {inIndexMode ? (
          <div className="obs-panel">
            {indexTicker === "FEARGREED" ? (
              <FearGreedDetailView onOpenHub={onOpenIndexHub} onBackToOverview={backToOverview} />
            ) : indexTicker ? (
              <IndexDetailView ticker={indexTicker} onOpenHub={onOpenIndexHub} onSelectCompany={onSelectCompany} onBackToOverview={backToOverview} />
            ) : (
              <IndexHubView onBack={onCloseIndexUI} onSelectIndex={onSelectIndex} onOpenFearGreed={onOpenFearGreed} onBackToOverview={backToOverview} />
            )}
          </div>
        ) : (
          renderSection()
        )}
      </main>
    </div>
  );
}

// =========================
// OVERVIEW VIEW (Обозреватель — легаси, заменён ObserverV2)
// =========================

function OverviewView({ token, onSelectCompany }) {
  // Направления Обозревателя. №1 — Лента новостей (готово); остальные — по мере выката.
  const [section, setSection] = useState("news");
  const [portfolioOnly, setPortfolioOnly] = useState(false);

  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">Обозреватель рынка</h1>
        <p className="view-subtitle">Контекстное понимание рыночного фона</p>
      </div>

      {/* Шапка Обозревателя: направления + общий тумблер «Только мой портфель».
          Липкая — кнопки блоков доступны при любом скролле длинной ленты. */}
      <div className="tw-sticky tw-top-0 tw-z-20 tw-bg-bg-base tw-flex tw-flex-wrap tw-items-center tw-gap-2 tw-py-3 tw-mb-4 tw-border-b tw-border-border-subtle">
        <Chip selected={section === "news"} onClick={() => setSection("news")}>
          <Newspaper size={13} className="tw-shrink-0" aria-hidden="true" /> Лента новостей
        </Chip>
        <Chip selected={section === "macro"} onClick={() => setSection("macro")}>
          <Activity size={13} className="tw-shrink-0" aria-hidden="true" /> Макрообзор
        </Chip>
        <Chip selected={section === "maps"} onClick={() => setSection("maps")}>
          <Layers size={13} className="tw-shrink-0" aria-hidden="true" /> Карты рынка
        </Chip>
        <Chip selected={section === "calendar"} onClick={() => setSection("calendar")}>
          <Calendar size={13} className="tw-shrink-0" aria-hidden="true" /> Календарь
        </Chip>
        <Chip selected={section === "earnings"} onClick={() => setSection("earnings")}>
          <FileText size={13} className="tw-shrink-0" aria-hidden="true" /> Отчёты
        </Chip>
        <Chip selected={section === "geo"} onClick={() => setSection("geo")}>
          <Globe size={13} className="tw-shrink-0" aria-hidden="true" /> Геополитика
        </Chip>
        <Chip selected={section === "report"} onClick={() => setSection("report")}>
          <Sparkles size={13} className="tw-shrink-0" aria-hidden="true" /> ИИ-обзор
        </Chip>
        <button
          type="button"
          onClick={() => setPortfolioOnly((v) => !v)}
          aria-pressed={portfolioOnly}
          title="Показывать только новости, затрагивающие бумаги вашего портфеля"
          className={`tw-ml-auto tw-inline-flex tw-items-center tw-gap-2 tw-rounded-pill tw-border tw-px-3 tw-py-1 tw-text-[13px] tw-cursor-pointer tw-transition-colors focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${
            portfolioOnly
              ? "tw-border-accent tw-bg-accent-soft tw-text-accent"
              : "tw-border-border-subtle tw-text-text-secondary hover:tw-border-accent"
          }`}
        >
          <Briefcase size={13} aria-hidden="true" /> Только мой портфель
        </button>
      </div>

      {section === "news" ? (
        <NewsFeed token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
      ) : section === "macro" ? (
        <MacroView token={token} portfolioOnly={portfolioOnly} />
      ) : section === "maps" ? (
        <MarketMaps token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
      ) : section === "calendar" ? (
        <CalendarView token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
      ) : section === "earnings" ? (
        <EarningsFeed token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
      ) : section === "geo" ? (
        <GeopoliticsView token={token} portfolioOnly={portfolioOnly} onSelectCompany={onSelectCompany} />
      ) : section === "report" ? (
        <ObserverReportView token={token} onSelectCompany={onSelectCompany} />
      ) : null}
    </div>
  );
}

// slug URL-раздела (/company/T/<slug>/) → вкладка карточки (initialTab). Держать
// в синхроне с TAB_PAGES в scripts/generate-seo-pages.js — там же генератор SEO-
// страниц с теми же адресами. slug "dividends" сознательно ведёт на вкладку
// "governance" (дивиденды — часть блока управления в самой карточке).

// ─────────────────────────────────────────────────────────────────────────────
// Синхронизация АДРЕСА со состоянием приложения (владелец, 2026-07-30).
//
// Было: адрес читался только при загрузке, а дальше не менялся — открыв
// inbasis.ru/#method и походив по разделам и карточкам, пользователь всё время
// оставался на том же URL. Последствия: ссылку на конкретную бумагу нельзя ни
// отправить, ни сохранить в закладки (получатель попадёт туда, откуда начинал
// отправитель), кнопка «назад» уводит с платформы вместо шага назад, а для поиска
// у сотен разборов нет собственных адресов — на запрос «акции Газпрома» мы
// конкурируем одной общей страницей вместо страницы про Газпром.
//
// Формат адресов повторяет уже существующие пре-рендеренные SEO-страницы
// (scripts/generate-seo-pages.js), чтобы статика и SPA жили на ОДНИХ И ТЕХ ЖЕ
// путях, а не в двух параллельных мирах: /company/GAZP/, /company/GAZP/finance/.
// Разделы платформы пока остаются на query-форме ?view=…, которую понимает и
// парсер ниже, и CTA-ссылки внутри интент-лендингов.
const TAB_TO_SEO_SLUG = { business: "business", finance: "finance", governance: "dividends", macro: "macro", geo: "geo" };

function buildAppUrl({ company, cardTab, view, obs }) {
  if (company) {
    const slug = TAB_TO_SEO_SLUG[cardTab];
    return `/company/${String(company).toUpperCase()}/${slug ? slug + "/" : ""}`;
  }
  if (view && view !== "landing") {
    const q = new URLSearchParams({ view });
    if (obs) q.set("obs", obs);
    return `/?${q.toString()}`;
  }
  return "/";
}

// pushState, а не replaceState: каждый переход должен попадать в историю, иначе
// «назад» по-прежнему выкидывает с платформы. Тихо игнорируем сбой (Safari в
// приватном режиме умеет бросать на частых pushState).
// Заголовок вкладки должен идти за состоянием вместе с адресом. Иначе, зайдя из поиска
// на страницу Сбербанка и перейдя в «Обозреватель», пользователь весь сеанс видит в
// заголовке «Сбербанк (SBER)» — владелец поймал это на скриншоте 2026-07-30. Для
// поисковых систем тайтл берётся из статики при обходе, здесь речь про живой сеанс.
// Заголовки секций Обозревателя: владелец (2026-07-30) — «в обозревателе и везде, где
// есть вкладки на сайдбаре, должны быть отдельные страницы и должно различаться».
// Адрес и заголовок теперь меняются на каждой секции, а не остаются общими для всего
// раздела: иначе «Отчёты» и «Геополитика» — одна и та же страница и для пользователя
// (нельзя переслать ссылку на нужную), и для поиска.
const OBS_TITLES = {
  news: "Новости фондового рынка России — Basis",
  economy: "Экономическая статистика России: ставка, инфляция, ВВП — Basis",
  pulse: "Обзор рынка: индексы, ширина рынка, драйверы — Basis",
  maps: "Карта рынка акций Мосбиржи — Basis",
  calendar: "Календарь событий: отчётности, дивиденды, собрания — Basis",
  reports: "Отчёты компаний: разбор вышедшей отчётности — Basis",
  "corp-news": "Корпоративные события эмитентов — Basis",
  macro: "Макрообзор российской экономики — Basis",
  geo: "Геополитика и российский рынок — Basis",
  institutions: "Институциональная среда — Basis",
  ai: "ИИ-обзор рынка — Basis",
};

const VIEW_TITLES = {
  companies: "Рынок: акции, облигации, фонды, фьючерсы — Basis",
  overview: "Обозреватель рынка: новости, макро, отчёты — Basis",
  portfolio: "Портфель: диагностика и риски — Basis",
  screener: "Скринер акций и облигаций — Basis",
  stress: "Стресс-тестирование — Basis",
  ai: "ИИ-помощник — Basis",
  pricing: "Тарифы — Basis",
  landing: "Basis — анализ российского рынка для частного инвестора",
};

function syncTitle(state) {
  try {
    if (state.company) {
      const t = String(state.company).toUpperCase();
      document.title = `${t}: разбор компании — Basis`;
      return;
    }
    if (state.view === "overview" && state.obs && OBS_TITLES[state.obs]) {
      document.title = OBS_TITLES[state.obs];
      return;
    }
    document.title = VIEW_TITLES[state.view] || VIEW_TITLES.landing;
  } catch {}
}

function syncUrl(state) {
  try {
    const url = buildAppUrl(state);
    if (window.location.pathname + window.location.search !== url) {
      window.history.pushState(state, "", url);
      // 🔴 В SPA адрес меняется без перезагрузки, и счётчик сам этого НЕ видит: без
      // явной отправки за весь сеанс засчитается один просмотр — точка входа. Тогда
      // отчёт по страницам не покажет ни переходов между карточками, ни вкладок, то
      // есть ровно то, ради чего аналитику и ставят.
      trackPageView(url);
      logPageView();
    }
    syncTitle(state);
  } catch {}
}

// Человекочитаемые адреса разделов (они же — статические SEO-лендинги). Раньше раздел
// жил на ДВУХ адресах: /karta-rynka-aktsiy/ (статика, её видит поиск) и
// /?view=overview&obs=maps (приложение). Владелец поймал следствие: «вбиваю „карта рынка
// basis“ — в выдаче общее название платформы, а не „Карта рынка“», потому что по
// служебному адресу отдаётся общий index.html. Теперь адрес ОДИН: с него робот получает
// нужный заголовок и текст, а приложение открывает соответствующий раздел.
const LANDING_ROUTES = {
  "analiz-portfelya": { view: "portfolio" },
  "stress-test-portfelya": { view: "stress" },
  "skrining-aktsiy": { view: "screener" },
  "skrining-obligatsiy": { view: "screener" },
  "obzor-rynka": { view: "overview", obs: "pulse" },
  "novosti-fondovogo-rynka": { view: "overview", obs: "news" },
  "ekonomicheskaya-statistika-rossii": { view: "overview", obs: "economy" },
  "karta-rynka-aktsiy": { view: "overview", obs: "maps" },
  "kalendar-otchetnostey": { view: "overview", obs: "calendar" },
  "dividendnyy-kalendar": { view: "overview", obs: "calendar" },
  "razbor-otchetnosti-kompaniy": { view: "overview", obs: "reports" },
  "makroobzor-rossiyskoy-ekonomiki": { view: "overview", obs: "macro" },
  "geopolitika-i-rossiyskiy-rynok": { view: "overview", obs: "geo" },
  "institutsionalnaya-sreda": { view: "overview", obs: "institutions" },
  "korporativnye-sobytiya-emitentov": { view: "overview", obs: "corp-news" },
  "ii-pomoshchnik-investoru": { view: "ai" },
  "futures-moex": { view: "companies", tab: "futures" },
  "bpif-etf-moex": { view: "companies", tab: "funds" },
  "kak-vybrat-ofz": { view: "companies", tab: "bonds" },
  "vdo-obligatsii": { view: "companies", tab: "bonds" },
  "spravedlivaya-tsena-aktsiy": { view: "companies", tab: "stocks" },
};

const SEO_SLUG_TO_TAB = {
  business: "business",
  finance: "finance",
  dividends: "governance",
  macro: "macro",
  geo: "geo",
  // Страница разбора отчёта (/company/<T>/otchet/) ведёт во вкладку «Финансы» — там
  // отчётность и живёт. Без этой строки переход со статической страницы в приложение
  // открывал карточку на «Обзоре», игнорируя раздел, по которому человек пришёл.
  otchet: "finance",

  // 🔴 СТРАНИЦЫ МЕТРИК. Владелец 04.08: «ссылки местами работают криво — открывают не ту
  // информацию, которая человеку нужна». Диагностика подтвердила и показала масштаб: из
  // 4378 страниц разделов 2800 уводили не туда. 1767 открывали вообще ГЛАВНУЮ — в их
  // адресе есть дефис, а группа раздела в разборе пути была [a-z]+ без дефиса, поэтому
  // совпадения не возникало и приложение уходило в ветку «это не карточка». Сюда попали
  // ВСЕ 259 страниц справедливой цены. Ещё 1033 открывали карточку, но на «Обзоре»,
  // потому что их slug просто не был описан здесь.
  // Все эти показатели живут во вкладке «Финансы и оценка».
  "spravedlivaya-tsena": "finance",
  vyruchka: "finance",
  "chistaya-pribyl": "finance",
  "operatsionnaya-pribyl": "finance",
  ebitda: "finance",
  aktivy: "finance",
  "sobstvennyy-kapital": "finance",
  "chistyy-dolg": "finance",
  "dolgovaya-nagruzka": "finance",
  "operatsionnyy-denezhnyy-potok": "finance",
  "svobodnyy-denezhnyy-potok": "finance",
  roe: "finance",
  roa: "finance",

  // Владелец 2026-08-06: «прогноз открывает обзор — справедливую цену, график — график
  // акции в обзоре». Обе страницы новые (спрос по Вордстату: «акции роснефть график»
  // 3126, «прогноз» 2518), раньше таких адресов не существовало.
  grafik: "overview",
  prognoz: "overview",
};

/** Разборы отчётности за период — /company/<T>/otchet-2-kvartal-2026/ и подобные.
 *  Их десятки и они прибавляются каждый отчётный сезон, поэтому не перечисляем
 *  поимённо, а разбираем по префиксу. 🔴 Цифры в адресе — причина, по которой
 *  группа раздела в регулярке стала [a-z0-9-]+: без цифр «otchet-2025-god-msfo»
 *  не совпадал вовсе и человек попадал на главную (тот же дефект, что чинили утром). */
function seoSlugToTab(slug) {
  if (!slug) return undefined;
  if (SEO_SLUG_TO_TAB[slug]) return SEO_SLUG_TO_TAB[slug];
  if (/^otchet-/.test(slug)) return "finance";
  return undefined;
}

// Куда ПРОКРУТИТЬ внутри вкладки. Открыть верную вкладку мало: страница /dividends/
// приводила в «Корпоративное управление», где сверху структура собственности и баллы,
// а дивиденды — третьим блоком. Человек, пришедший по запросу про дивиденды, их не видел
// и не обязан догадываться, что надо листать.
const SEO_SLUG_TO_ANCHOR = {
  dividends: "blk-dividends",
  // Вкладка «Финансы» длинная: сверху разбор отчёта, ниже ключевые показатели с
  // мультипликаторами, ещё ниже таблицы по годам. Открывать её сверху человеку, который
  // искал «выручка Сбербанка» или «ROE Лукойла», — та же ошибка, что была с дивидендами.
  // Два якоря покрывают все 13 страниц показателей:
  //   blk-fin-key   — ключевые показатели и мультипликаторы (сюда же справедливая цена);
  //   blk-fin-years — «Прибыль и рентабельность по годам»: P&L, баланс, ОДДС, рентабельность.
  // «Прогноз» ведёт к блоку справедливой цены в обзоре — за ним человек и приходит.
  prognoz: "blk-fair-value",
  // «График» — к самому графику котировки.
  grafik: "blk-price-chart",
  "spravedlivaya-tsena": "blk-fin-key",
  vyruchka: "blk-fin-years",
  "chistaya-pribyl": "blk-fin-years",
  "operatsionnaya-pribyl": "blk-fin-years",
  ebitda: "blk-fin-years",
  aktivy: "blk-fin-years",
  "sobstvennyy-kapital": "blk-fin-years",
  "chistyy-dolg": "blk-fin-years",
  "dolgovaya-nagruzka": "blk-fin-years",
  "operatsionnyy-denezhnyy-potok": "blk-fin-years",
  "svobodnyy-denezhnyy-potok": "blk-fin-years",
  roe: "blk-fin-years",
  roa: "blk-fin-years",
};

/**
 * Прокрутка к блоку, когда он появится. Карточка грузит данные асинхронно, поэтому
 * элемента в момент разбора адреса ещё нет — ждём его появления, но НЕ бесконечно.
 * Если блока не будет (у компании нет дивидендной истории — таких 79 из 264), просто
 * останемся наверху вкладки: это корректная деградация, а не поломка.
 */
function scrollToBlockWhenReady(anchorId, tries = 20) {
  if (!anchorId) return;
  let n = 0;
  const tick = () => {
    const el = document.getElementById(anchorId);
    if (el) {
      try { el.scrollIntoView({ behavior: "smooth", block: "start" }); } catch { el.scrollIntoView(); }
      return;
    }
    if (++n < tries) setTimeout(tick, 250);
  };
  setTimeout(tick, 250);
}

// Резолвер карточки: значение может быть объектом компании или тикером-строкой.
const CompanyCardResolver = ({ value, onBack, initialTab, onTabChange }) => {
  const [obj, setObj] = useState(typeof value === "object" && value ? value : null);
  const [notFound, setNotFound] = useState(false);
  useEffect(() => {
    if (typeof value === "object" && value) { setObj(value); return; }
    if (typeof value !== "string") return;
    let alive = true;
    // Ускорение старта из поиска: раньше ради ОДНОЙ компании тянулся весь список
    // (86 КБ, ~0,8 с) — при заходе на /company/SBER/ это добавлялось к 2+ с загрузки
    // бандла. Сначала пробуем лёгкий профиль по тикеру, список остаётся фолбэком.
    fetch(`${apiBase()}/api/companies`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => { if (!alive) return; const c = (list || []).find((x) => x.ticker === value); c ? setObj(c) : setNotFound(true); })
      .catch(() => alive && setNotFound(true));
    return () => { alive = false; };
  }, [value]);
  // Данные реально пришли (карточка есть ИЛИ точно не найдена) — сигнал статическим
  // SEO-страницам (build/company/<T>/..., см. scripts/generate-seo-pages.js), что
  // пора спрятать текстовую заглушку и показать живую карточку. Событие, а не проп —
  // страница-обёртка не часть React-дерева, слушает window напрямую.
  useEffect(() => {
    if (!obj && !notFound) return;
    try { window.dispatchEvent(new Event("basis:company-ready")); } catch {}
  }, [obj, notFound]);
  if (obj) return <CompanyCard company={obj} onBack={onBack} initialTab={initialTab} onTabChange={onTabChange} />;
  if (notFound) return <div className="tw-py-12 tw-text-text-tertiary">Компания «{String(value)}» не найдена в базе. <button onClick={onBack} className="tw-text-accent tw-underline tw-bg-transparent tw-border-0 tw-cursor-pointer">Назад</button></div>;
  return <div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-text-[18px] tw-animate-pulse">Открываем карточку...</div>;
};

// Единый плейсхолдер «Раздел в разработке» — один на все будущие блоки.
// =========================
// ВЕРХНЯЯ НАВИГАЦИЯ (глобальный шелл вместо левого рейла) — единый компонент.
// =========================
const TOPNAV_ITEMS = [
  { id: "companies", label: "Рынок" },
  { id: "overview", label: "Обозреватель" },
  { id: "portfolio", label: "Портфель" },
  { id: "stress", label: "Стресс-тестирование" },
  { id: "screener", label: "Скринер" },
  { id: "ai", label: "Ассистент" },
  { id: "pricing", label: "Тарифы" },
  { id: "profile", label: "Профиль" },
];

// =========================
// МОБИЛЬНАЯ НИЖНЯЯ НАВИГАЦИЯ (≤760px, см. styles/mobile-nav.css)
// =========================
// Критичный баг (владелец, 2026-07-21, скриншоты с телефона): на портрете
// шапка — одна строка (лого + 8 текстовых пунктов TOPNAV_ITEMS + поле поиска
// шириной 200px) без переноса — поиск съедал половину ширины, 8 пунктов
// сжимались в нечитаемую непрокручиваемую полоску; попасть в другой раздел
// можно было только повернув телефон в альбомную ориентацию. Решение —
// постоянный нижний таббар (паттерн Т-Инвестиций): 4 самых частых раздела
// прямыми кнопками + «Ещё» открывает шторку с остальными. Тот же список
// разделов, что TOPNAV_ITEMS, просто перегруппирован под маленький экран
// (подписи короче — под иконкой в 75px ширины «Обозреватель» не влезает).
const MOBILE_TAB_ITEMS = [
  { id: "companies", label: "Рынок", icon: BarChart2 },
  { id: "overview", label: "Обзор", icon: Newspaper },
  { id: "portfolio", label: "Портфель", icon: Wallet },
  { id: "screener", label: "Скринер", icon: SlidersHorizontal },
];
const MOBILE_MORE_ITEMS = [
  { id: "stress", label: "Стресс-тестирование", icon: Zap },
  { id: "ai", label: "Ассистент", icon: Sparkles },
  { id: "pricing", label: "Тарифы", icon: CreditCard },
  { id: "profile", label: "Профиль", icon: User },
];

function MobileTabBar({ activeTab, onNav, moreOpen, onToggleMore }) {
  const moreActive = moreOpen || MOBILE_MORE_ITEMS.some((it) => it.id === activeTab);
  return (
    <nav className="mnav-tabbar" aria-label="Основная навигация">
      {MOBILE_TAB_ITEMS.map((it) => {
        const active = activeTab === it.id;
        const Icon = it.icon;
        return (
          <button
            key={it.id}
            type="button"
            onClick={() => onNav(it.id)}
            aria-current={active || undefined}
            className={`mnav-item${active ? " mnav-item--active" : ""}`}
          >
            <span className="mnav-item__icon" aria-hidden="true">
              <Icon size={20} strokeWidth={active ? 2.25 : 1.85} />
            </span>
            <span>{it.label}</span>
          </button>
        );
      })}
      <button
        type="button"
        onClick={onToggleMore}
        aria-haspopup="true"
        aria-expanded={moreOpen}
        className={`mnav-item${moreActive ? " mnav-item--active" : ""}`}
      >
        <span className="mnav-item__icon" aria-hidden="true">
          <MoreHorizontal size={20} strokeWidth={moreActive ? 2.25 : 1.85} />
        </span>
        <span>Ещё</span>
      </button>
    </nav>
  );
}

// Простая bottom-sheet шторка с оставшимися разделами. Escape/клик по скриму
// закрывают; базовый focus-trap + возврат фокуса на триггер — тот же паттерн,
// что AuthModal (account/AccountPanels.jsx). prefers-reduced-motion гасит
// анимацию появления (CSS, mobile-nav.css) — здесь только логика/доступность.
function MobileMoreSheet({ activeTab, onNav, onClose }) {
  const sheetRef = useRef(null);
  const triggerRef = useRef(null);

  useEffect(() => {
    triggerRef.current = document.activeElement;
    const firstBtn = sheetRef.current?.querySelector("button");
    firstBtn?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !sheetRef.current) return;
      const focusable = Array.from(sheetRef.current.querySelectorAll("button:not([disabled])"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !sheetRef.current.contains(active)) {
          e.preventDefault();
          last.focus();
        }
      } else if (active === last || !sheetRef.current.contains(active)) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (triggerRef.current && document.body.contains(triggerRef.current)) triggerRef.current.focus();
    };
  }, [onClose]);

  return (
    <div className="mnav-more-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={sheetRef} className="mnav-more-sheet" role="dialog" aria-modal="true" aria-label="Остальные разделы">
        <div className="mnav-more-handle" aria-hidden="true" />
        <div className="mnav-more-title">Остальные разделы</div>
        {MOBILE_MORE_ITEMS.map((it) => {
          const active = activeTab === it.id;
          const Icon = it.icon;
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => { onNav(it.id); onClose(); }}
              aria-current={active || undefined}
              className={`mnav-more-item${active ? " mnav-more-item--active" : ""}`}
            >
              <span className="mnav-more-item__icon" aria-hidden="true"><Icon size={17} /></span>
              {it.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// Поиск компании/тикера в шапке — подключён к /api/companies (не заглушка).
function TopNavSearch({ onOpenCompany }) {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const boxRef = useRef(null);
  useEffect(() => {
    const api = process.env.REACT_APP_API_URL || "http://localhost:8000";
    fetch(`${api}/api/companies`).then((r) => (r.ok ? r.json() : [])).then((d) => {
      if (Array.isArray(d)) setItems(d.map((c) => ({ t: c.ticker, n: c.name })));
    }).catch(() => {});
  }, []);
  useEffect(() => {
    const onDoc = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const res = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return items.filter((x) => (x.t || "").toLowerCase().includes(s) || (x.n || "").toLowerCase().includes(s)).slice(0, 8);
  }, [q, items]);
  const pick = (t) => { onOpenCompany(t); setQ(""); setOpen(false); };
  const onKey = (e) => {
    if (!open || !res.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(res.length - 1, h + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); pick(res[hi].t); }
    else if (e.key === "Escape") setOpen(false);
  };
  return (
    <div ref={boxRef} className="tw-relative tw-flex-shrink-0 topnav-search-wrap">
      <div className="tw-flex tw-items-center tw-gap-2 tw-h-9 tw-px-3 tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-elevated tw-text-text-tertiary focus-within:tw-border-accent topnav-search-box" style={{ minWidth: 200 }}>
        <Search size={15} />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); setHi(0); }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          placeholder="Поиск компании, тикера…"
          className="tw-bg-transparent tw-border-0 tw-outline-none tw-text-[13px] tw-text-text-primary tw-w-full tw-min-w-0"
        />
      </div>
      {open && res.length > 0 && (
        <div className="tw-absolute tw-right-0 tw-mt-1.5 tw-w-[300px] tw-max-h-[360px] tw-overflow-y-auto tw-rounded-lg tw-border tw-border-border-strong tw-bg-bg-elevated tw-shadow-lg tw-z-50 tw-p-1.5">
          {res.map((x, i) => (
            <button
              key={x.t}
              onMouseEnter={() => setHi(i)}
              onClick={() => pick(x.t)}
              className={`tw-flex tw-items-center tw-gap-2.5 tw-w-full tw-text-left tw-px-2.5 tw-py-2 tw-rounded-md tw-border-0 tw-cursor-pointer ${i === hi ? "tw-bg-bg-hover" : "tw-bg-transparent"}`}
            >
              <CompanyLogo ticker={x.t} name={x.n} size={26} />
              <span className="tw-flex tw-flex-col tw-min-w-0">
                <span className="tw-text-[13px] tw-font-medium tw-text-text-primary tw-truncate">{x.n}</span>
                <span className="tw-font-mono tw-text-[11px] tw-text-text-tertiary">{x.t}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function TopNav({ activeTab, onNav, theme, toggleTheme, onOpenCompany, isAuthenticated, onOpenAuth }) {
  return (
    <header
      className="tw-sticky tw-top-0 tw-z-40 tw-border-b tw-border-border-subtle"
      style={{ background: "color-mix(in srgb, var(--cc-bg, var(--bg-base)) 85%, transparent)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)" }}
    >
      <div className="tw-mx-auto tw-flex tw-h-[60px] tw-items-center tw-gap-6 tw-px-5 sm:tw-px-7 topnav-row" style={{ maxWidth: 1340 }}>
        <button
          type="button"
          aria-label="Basis — на главную"
          onClick={() => onNav("landing")}
          className="tw-appearance-none tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-flex tw-items-center tw-gap-2 tw-flex-shrink-0 topnav-logo"
        >
          <BasisLogomark size={26} slit="var(--bg-base)" crisp />
          <span className="tw-font-display tw-text-[17px] tw-font-semibold tw-text-text-primary">Basis</span>
        </button>

        {/* >760px: полный список пунктов. ≤760px: скрыт (topnav-links, см.
            mobile-nav.css) — переезжает в нижний фикс-таббар (MobileTabBar). */}
        <nav aria-label="Основная навигация" className="tw-flex tw-items-center tw-gap-0.5 tw-flex-1 tw-overflow-x-auto topnav-links">
          {TOPNAV_ITEMS.map((it) => {
            const active = activeTab === it.id;
            return (
              <button
                key={it.id}
                onClick={() => onNav(it.id)}
                aria-current={active || undefined}
                className={`tw-relative tw-whitespace-nowrap tw-border-0 tw-bg-transparent tw-cursor-pointer tw-px-3 tw-py-2 tw-rounded-md tw-text-[14px] ${active ? "tw-text-text-primary tw-font-semibold" : "tw-text-text-secondary tw-font-medium hover:tw-text-text-primary"}`}
              >
                {it.label}
                {active && <span aria-hidden="true" className="tw-absolute tw-left-3 tw-right-3 tw-bottom-[-1px] tw-h-0.5 tw-bg-accent tw-rounded-sm" />}
              </button>
            );
          })}
        </nav>

        {/* Отдельный флекс-элемент строки шапки (НЕ вложен в topnav-actions):
            на ≤760px переезжает на вторую строку на всю ширину (order + flex-
            basis:100% в mobile-nav.css), тема остаётся в первой строке. */}
        <TopNavSearch onOpenCompany={onOpenCompany} />

        <div className="tw-flex tw-items-center tw-gap-2 tw-flex-shrink-0 topnav-actions">
          {/* Кнопки экскурса здесь БОЛЬШЕ НЕТ (владелец, 2026-08-05: «верхний
              сайдбар, пройти экскурс — перенеси внутрь профиля, на сайдбаре не
              оставляй»). Точка входа — раздел «Профиль» (account/ProfileView.jsx),
              она доступна и гостю. */}
          {/* Постоянная точка входа в регистрацию/вход (владелец, 2026-08-02):
              раньше в шапке НЕ было вообще никакой кнопки логина — единственный
              путь был пункт «Профиль» в TOPNAV_ITEMS (ведёт во вкладку профиля,
              не открывает форму входа). Показывается ТОЛЬКО когда пользователь
              не залогинен; после входа кнопка пропадает, остаётся «Профиль» в
              общем списке разделов. Сдержанный secondary-вариант (не primary) —
              не должна спорить по яркости с активной вкладкой навигации.
              Текстовая подпись прячется на ≤760px (styles/mobile-nav.css,
              .topnav-login-label) — остаётся иконка + aria-label, по той же
              логике, что уже сжимает поиск на мобильном. */}
          {!isAuthenticated && (
            <Button
              variant="secondary"
              size="md"
              iconLeft={<User size={15} />}
              onClick={onOpenAuth}
              aria-label="Войти или зарегистрироваться"
              className="topnav-login-btn"
            >
              <span className="topnav-login-label">Войти</span>
            </Button>
          )}
          <IconButton
            aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            onClick={toggleTheme}
            style={{ color: "var(--text-secondary)" }}
          >
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </IconButton>
        </div>
      </div>
    </header>
  );
}

// =========================
// APP
// =========================

// Граница ошибок: любой краш рендера экрана → видимое сообщение + кнопка вместо
// белого экрана. Текст ошибки показываем (помогает диагностике на бою).
class ViewErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(err) { return { err }; }
  componentDidCatch(err, info) { console.error("View crashed:", err, info); }
  componentDidUpdate(prev) { if (prev.routeKey !== this.props.routeKey && this.state.err) this.setState({ err: null }); }
  render() {
    if (this.state.err) {
      return (
        <div className="tw-flex tw-flex-col tw-items-center tw-justify-center tw-py-24 tw-px-6 tw-text-center">
          <div className="tw-text-[18px] tw-font-medium tw-text-text-primary tw-mb-2">Не удалось отобразить раздел</div>
          <div className="tw-font-mono tw-text-[12px] tw-text-text-tertiary tw-mb-5 tw-max-w-[680px] tw-break-words">{String(this.state.err && this.state.err.message || this.state.err)}</div>
          <button onClick={() => this.setState({ err: null })} className="tw-px-5 tw-py-2.5 tw-rounded-md tw-bg-accent tw-text-white tw-text-[14px] tw-border-0 tw-cursor-pointer">Повторить</button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  const [activeTab, setActiveTab] = useState("landing");
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedBond, setSelectedBond] = useState(null);
  const [selectedFuture, setSelectedFuture] = useState(null);
  const [selectedFund, setSelectedFund] = useState(null);
  const [selectedSpot, setSelectedSpot] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(null);   // тикер индекса, или "FEARGREED"
  const [showIndexHub, setShowIndexHub] = useState(false);
  // Клик по плитке драйвера «Что движет рынком» (Рынок→Акции→Пульс) — форсирует
  // конкретную секцию Обозревателя при переходе (forceObsSection) + опционально
  // просит показать график инструмента (driverChart). См. openDriverChart ниже.
  const [forceObsSection, setForceObsSection] = useState(null);
  const [driverChart, setDriverChart] = useState(null);
  const [forceEconIndicator, setForceEconIndicator] = useState(null);
  // Вкладка карточки из deep-link (?company=T&tab=finance) — применяется только
  // при первом монтировании карточки, дальше пользователь управляет вкладками сам.
  const [initialCardTab, setInitialCardTab] = useState(null);
  // Вопрос, с которым человек уходит в Ассистента из подсказки «залипания»
  // (design/AssistantNudge): текст подставляется в поле ввода, НЕ отправляется
  // сам — решение спросить остаётся за человеком, и лимит не тратится впустую.
  const [assistantPrefill, setAssistantPrefill] = useState("");
  // Вкладка внутри раздела из адреса (?view=portfolio&tab=risk) — прокидывается в
  // MarketNeo/PortfolioV2/ObserverV2 как начальная секция.
  const [forceInnerTab, setForceInnerTab] = useState(null);
  // Подборка инструментов из адреса (/bonds/vdo/ → включить фильтр «ВДО»).
  // 🔴 Владелец 2026-08-26: «вбил высокодоходные облигации — открылась SEO-страница,
  // а должен открываться Рынок → облигации с уже включённым фильтром ВДО».
  const [forceMarketPreset, setForceMarketPreset] = useState(null);
  // Статическая SEO-страница, адрес которой приложение не распознало. В этом случае
  // НЕЛЬЗЯ рисовать главную: получается «сверху SEO-страница, снизу лендинг», что и
  // поймал владелец на /statistika/indeks-pmi/. Честнее оставить статику — она
  // полноценная — и не показывать приложение вовсе.
  const [staticOnly, setStaticOnly] = useState(false);
  // 🔴 Мягкий 404. Хостинг (Caddy на Timeweb) отдаёт index.html с кодом 200 на ЛЮБОЙ
  // несуществующий адрес — это ровно то, на что ругается Вебмастер («некорректно
  // настроен возврат 404»). Настроить сам код ответа можно только в панели хостинга,
  // из репозитория — нельзя. Но можно не делать вид, что страница существует: показать
  // честное «не найдено» и запретить индексирование метатегом, чтобы такие адреса не
  // расползались по индексу. Индексируемые страницы у нас статические, у них свой
  // robots=index, поэтому им это не вредит.
  const [notFound, setNotFound] = useState(false);
  // Экран результата подтверждения почты по ссылке из письма:
  // null | "pending" | "ok" | "already" | "error:<текст>"
  const [verifyEmail, setVerifyEmail] = useState(null);
  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem("basis_theme");
    if (stored === "dark" || stored === "light") return stored;
    // No explicit choice → default LIGHT (per design constitution; mirrors anti-FOUC script).
    return "light";
  });

  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("basis_user")); } catch { return null; }
  });
  const [token, setToken] = useState(() => localStorage.getItem("basis_token") || null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  // Шторка «Ещё» нижнего мобильного таббара (≤760px) — см. MobileTabBar/
  // MobileMoreSheet выше и app-shell ниже.
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  // Deep-link в карточку компании — два входа:
  // 1) /company/TICKER/[slug/] — основной URL страницы (см. scripts/generate-
  //    seo-pages.js): та же статическая SEO-страница, что раньше только звала в
  //    приложение кнопкой, теперь САМА содержит бандл и открывает карточку у себя
  //    (progressive takeover, #seo-static прячется по событию basis:company-ready
  //    из CompanyCardResolver). Короткие /TICKER/ редиректят сюда же build-time.
  // Кнопка «назад» браузера: без этого обработчика история, которую мы теперь пишем
  // через pushState, «прокручивалась» бы без изменения экрана — адрес менялся, а
  // приложение оставалось на прежнем состоянии.
  useEffect(() => {
    const onPop = () => {
      try {
        const m = window.location.pathname.match(/^\/company\/([A-Za-z0-9-]+)\/?([a-z0-9-]+)?\/?$/);
        if (m) {
          setSelectedCompany(m[1].toUpperCase());
          const slug = (m[2] || "").toLowerCase();
          const tab = seoSlugToTab(slug);
          if (tab) setInitialCardTab(tab);
          scrollToBlockWhenReady(SEO_SLUG_TO_ANCHOR[slug]);
          return;
        }
        setSelectedCompany(null);
        const view = (new URLSearchParams(window.location.search).get("view") || "").toLowerCase();
        const VIEW_TABS = ["companies", "overview", "portfolio", "stress", "screener", "ai", "pricing"];
        setActiveTab(VIEW_TABS.includes(view) ? view : "landing");
      } catch {}
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Аналитика: инициализация и первый просмотр. Без REACT_APP_METRIKA_ID модуль —
  // набор пустых операций, наружу не уходит ничего (см. src/analytics.js).
  // Первый просмотр отправляет сниппет счётчика в <head> — здесь его повторять НЕЛЬЗЯ,
  // иначе каждая точка входа считалась бы дважды и показатель отказов был бы занижен.
  useEffect(() => { initAnalytics(); logPageView(); }, []);

  // Кнопка «назад» — тоже переход между страницами, и его надо считать: иначе путь
  // пользователя в отчётах обрывается там, где он вернулся, а не там, где ушёл.
  useEffect(() => {
    const onPopTrack = () => { trackPageView(); logPageView(); };
    window.addEventListener("popstate", onPopTrack);
    return () => window.removeEventListener("popstate", onPopTrack);
  }, []);

  // 2) ?company=TICKER[&tab=finance] — старый query-формат, оставлен как фолбэк
  //    (используется CTA-ссылками внутри самих SEO-страниц: /?company=T&tab=X).
  useEffect(() => {
    try {
      const pathMatch = window.location.pathname.match(/^\/company\/([A-Za-z0-9]+)\/?([a-z0-9-]+)?\/?$/);
      if (pathMatch) {
        setSelectedCompany(pathMatch[1].toUpperCase());
        const slug = (pathMatch[2] || "").toLowerCase();
        const mappedTab = seoSlugToTab(slug);
        if (mappedTab) setInitialCardTab(mappedTab);
        scrollToBlockWhenReady(SEO_SLUG_TO_ANCHOR[slug]);
        return;
      }
      // 🔴 Страницы инструментов: /bonds/<КОД>/, /futures/<КОД>/, /funds/<КОД>/.
      // Владелец 2026-08-02: «вбил si 9 26 — открылась SEO-страница, а должна
      // подгружаться настоящая». Так и было: 3757 страниц облигаций, фондов и фьючерсов
      // вообще не поднимали приложение, потому что их собирает отдельный генератор, и
      // разбора адреса для них не существовало. Теперь адрес открывает карточку бумаги.
      //
      // Отличаем КОД БУМАГИ от подборки простым признаком: подборки называются строчными
      // латиницей (/bonds/ofz/, /bonds/vdo/, /bonds/vse/2/), а коды инструментов всегда
      // содержат заглавные — RU000A10FEP7, SU26247RMFS5, SiU6, TMOS. Проверять по списку
      // подборок хуже: список растёт, и про новую забудут.
      const mInstr = window.location.pathname.match(/^\/(bonds|futures|funds)\/([^/]+)\/?$/);
      if (mInstr && /[A-Z]/.test(mInstr[2])) {
        const code = mInstr[2];
        if (mInstr[1] === "bonds") setSelectedBond(code);
        else if (mInstr[1] === "futures") setSelectedFuture(code);
        else setSelectedFund(code);
        // 🔴 Без переключения раздела activeTab остаётся "landing", и приложение
        // рисует лендинг ВОКРУГ карточки — владелец увидел «половину лендинга»
        // вместо страницы фьючерса. Инструменты живут в разделе «Рынок».
        setActiveTab("companies");
        // 🔴 СОБЫТИЕ ЗДЕСЬ НЕ ШЛЁМ. Оно убирает статический SEO-текст из DOM, а данные
        // карточки ещё не загружены — между этими моментами на странице нет ни статики,
        // ни содержимого. Робот, исполняющий скрипты, видит пустоту, и страница теряет
        // релевантность: владелец заметил, что после подключения приложения фьючерс
        // перестал находиться по запросу, хотя раньше находился. Теперь событие шлёт
        // сама карточка (BondCard/FuturesCard/FundCard) по приходу данных — так же, как
        // карточка компании шлёт basis:company-ready.
        return;
      }

      // 🔴 ПОДБОРКИ И КАТАЛОГИ ИНСТРУМЕНТОВ: /bonds/vdo/, /bonds/ofz/, /bonds/vse/3/,
      // /futures/, /funds/. Ветка выше ловит только КОДЫ бумаг (в них есть заглавные), а
      // подборки называются строчными — и проваливались в самый низ, где приложение
      // оставляло статическую страницу и рисовало под ней ЛЕНДИНГ.
      // Владелец 2026-08-26: «вбил высокодоходные облигации, открылась SEO-страница, а
      // кнопка внизу вела на лендинг — что за бред? Должен открываться Рынок → облигации
      // с уже включённым фильтром ВДО».
      // Теперь адрес подборки открывает нужный раздел «Рынка», а слаг подборки уходит в
      // фильтр (соответствия — BOND_PRESETS в market/MarketNeo.jsx; там же объяснено,
      // почему для части подборок фильтра нет и мы честно открываем без него).
      // 🔴 Событие basis:app-ready ЗДЕСЬ НЕ ШЛЁМ — его посылает MarketNeo, когда список
      // реально пришёл с бэка. Пошли мы его сразу — статика удалилась бы, а список ещё
      // пуст, и робот увидел бы пустую страницу (так однажды «пропал» фьючерс из выдачи).
      const mColl = window.location.pathname.match(/^\/(bonds|futures|funds)(?:\/([a-z0-9-]+))?\/?/);
      if (mColl) {
        setActiveTab("companies");
        setForceInnerTab(mColl[1]);
        if (mColl[1] === "bonds" && mColl[2]) setForceMarketPreset(mColl[2]);
        return;
      }

      // Путь человекочитаемого раздела (/karta-rynka-aktsiy/ и т.п.)
      const landing = window.location.pathname.replace(/^\/|\/$/g, "");
      // 🔴 Страницы показателей и индексов (/statistika/…, /indeks/…) — их адреса
      // задаются генератором пачкой, перечислять каждый в LANDING_ROUTES бессмысленно.
      // Без этой ветки приложение не понимало адрес и рисовало ГЛАВНУЮ под статикой:
      // владелец поймал ровно это — «была SEO-страница, ниже лендинг, потом SEO-страница
      // пропала и остался лендинг». Теперь открывается тот раздел, о котором страница.
      // 🔴 Показатель открываем НА СВОЁМ МЕСТЕ, а не «раздел целиком». Человек искал
      // «недельная инфляция» — он должен увидеть её график, а не общий экран из полусотни
      // плиток, где её ещё надо найти глазами. Код показателя берём из meta, которую
      // проставил генератор: восстановить его из адреса нельзя, половина slug'ов русская
      // и таблица соответствия живёт в generate-seo-indicators.js. ObsEconomy уже умеет
      // открывать нужную плитку по forceIndicator — не хватало только этой передачи.
      const indMeta = landing.startsWith("statistika/")
        ? document.querySelector('meta[name="basis:indicator"]')?.getAttribute("content")
        : null;
      const prefixRoute = landing.startsWith("statistika/") ? { view: "overview", obs: "economy" }
        : (landing === "indeks-strakha-i-zhadnosti" || landing.startsWith("indeks/"))
          ? { view: "overview", obs: "pulse" } : null;
      const route = LANDING_ROUTES[landing] || prefixRoute;
      if (route) {
        if (indMeta) setForceEconIndicator(indMeta);
        if (route.obs) setForceObsSection(route.obs);
        if (route.tab) setForceInnerTab(route.tab);
        setActiveTab(route.view);
        // Сообщаем статике, что приложение взяло управление: без этого события
        // #seo-static остался бы поверх и получилась бы двойная страница. Событие
        // общее (не company-ready) — статика лендинга слушает оба.
        try { window.dispatchEvent(new Event("basis:app-ready")); } catch {}
        return;
      }
      const params = new URLSearchParams(window.location.search);
      const t = params.get("company");
      if (t) {
        setSelectedCompany(t.toUpperCase());
        const CARD_TABS = ["overview", "business", "finance", "governance", "markets", "macro", "geo", "institutions"];
        const tabP = (params.get("tab") || "").toLowerCase();
        if (CARD_TABS.includes(tabP)) setInitialCardTab(tabP);
        return;
      }
      // 3) ?view=portfolio|screener|overview|stress|companies[&obs=calendar] —
      //    deep-link из SEO-интент-лендингов (/analiz-portfelya/ и др., см.
      //    scripts/seo-landings-content.js): открыть сразу нужный раздел
      //    приложения; для Обозревателя опционально конкретная секция
      //    (ид из OBS_ZONES в observer/ObsPanels.jsx).
      // Ничего из известного не совпало. Если под нами лежит статическая страница —
      // не подменяем её главной (см. staticOnly).
      if (!params.get("view") && !params.get("company")
          && document.getElementById("seo-static")) {
        setStaticOnly(true);
        return;
      }
      // Статики под нами нет, адрес не корневой и ни на что не похож — страницы
      // действительно не существует. Раньше в этом случае молча показывалась главная.
      if (window.location.pathname !== "/" && !params.get("view") && !params.get("company")) {
        try {
          let m = document.querySelector('meta[name="robots"]');
          if (!m) { m = document.createElement("meta"); m.name = "robots"; document.head.appendChild(m); }
          m.content = "noindex, follow";
          document.title = "Страница не найдена — Basis";
        } catch {}
        setNotFound(true);
        return;
      }
      // Ссылка подтверждения почты из письма: /?view=verify-email&token=…
      // (ссылка ведёт на фронт, а не на API — адрес API периодически меняется).
      if ((params.get("view") || "").toLowerCase() === "verify-email" && params.get("token")) {
        const vtoken = params.get("token");
        setVerifyEmail("pending");
        fetch(`${apiUrl}/api/auth/verify-email`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: vtoken }),
        }).then(async (r) => {
          const d = await r.json().catch(() => ({}));
          if (r.ok && (d.status === "ok" || d.status === "already")) {
            setVerifyEmail(d.status);
            // Пользователь мог быть залогинен в этой же вкладке — обновляем его
            // копию сразу, чтобы профиль показал галочку без перезагрузки.
            const tk = localStorage.getItem("basis_token");
            if (tk) fetch(`${apiUrl}/api/auth/me`, { headers: { Authorization: `Bearer ${tk}` } })
              .then((rr) => (rr.ok ? rr.json() : null))
              .then((u) => { if (u) { setUser(u); localStorage.setItem("basis_user", JSON.stringify(u)); } })
              .catch(() => {});
          }
          else setVerifyEmail("error:" + (d.detail || "не получилось подтвердить адрес"));
        }).catch(() => setVerifyEmail("error:нет связи с сервером, попробуйте позже"));
        try { window.history.replaceState({}, "", "/"); } catch {}
        return;
      }
      const VIEW_TABS = ["companies", "overview", "portfolio", "stress", "screener", "ai", "pricing"];
      const viewP = (params.get("view") || "").toLowerCase();
      if (VIEW_TABS.includes(viewP)) {
        // ?tab=… — вкладка ВНУТРИ раздела (Рынок: stocks/bonds/futures/funds;
        // Портфель: composition/risk/correlation/quality/…). Без этого ссылка на
        // конкретную вкладку открывала раздел на дефолтной, и адрес терял смысл.
        const tabInner = (params.get("tab") || "").toLowerCase();
        if (tabInner) setForceInnerTab(tabInner);
        // ?preset=vdo — подборка, которую надо открыть с включённым фильтром.
        // 🔴 Владелец 2026-08-26: «в гугле открывается раздел облигации, но БЕЗ включённого
        // фильтра ВДО». Он нажимал кнопку на странице подборки, а она вела на общий
        // /?view=companies&tab=bonds. Адрес /bonds/vdo/ фильтр включал, кнопка — теряла.
        // Теперь слаг едет в параметре, и оба пути ведут к одному результату.
        const presetP = (params.get("preset") || "").toLowerCase();
        if (presetP) setForceMarketPreset(presetP);
        if (viewP === "overview") {
          const OBS_SECTIONS = ["news", "economy", "pulse", "maps", "calendar", "reports", "corp-news", "macro", "geo", "institutions", "ai"];
          const obsP = (params.get("obs") || "").toLowerCase();
          if (OBS_SECTIONS.includes(obsP)) setForceObsSection(obsP);
        }
        setActiveTab(viewP);
      }
    } catch {}
  }, []);

  useEffect(() => {
    const el = document.documentElement;
    el.classList.toggle("dark", theme === "dark");
    // Keep data-theme in sync for backward-compatible selectors.
    el.setAttribute("data-theme", theme);
    localStorage.setItem("basis_theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!token) return;
    fetch(`${apiUrl}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(u => {
        if (u) { setUser(u); localStorage.setItem("basis_user", JSON.stringify(u)); }
        else handleLogout();
      })
      .catch(() => {});
  }, []);

  const handleLogin = (newUser, newToken) => {
    setUser(newUser);
    setToken(newToken);
    setShowAuthModal(false);
    // 🔴 Перенос гостевого портфеля — ДО того, как экран начнёт грузить список.
    // Владелец 2026-08-04: «нужно, чтобы портфель, который был бы составлен, сохранился
    // после того как клиент пройдёт регистрацию, чтобы не слетело». Если не перенести
    // сразу, человек увидит пустой список и решит, что работа пропала.
    claimGuestData(process.env.REACT_APP_API_URL || "http://localhost:8000", newToken)
      .then((claimed) => {
        // Портфели уже принадлежат аккаунту, но смонтированный раздел мог успеть
        // загрузиться до переноса — перечитываем его состав.
        if (Array.isArray(claimed) && claimed.length) {
          try { window.dispatchEvent(new Event("basis:portfolios-claimed")); } catch { /* нет CustomEvent — не критично */ }
        }
      });
  };

  const handleLogout = () => {
    localStorage.removeItem("basis_token");
    localStorage.removeItem("basis_user");
    setUser(null);
    setToken(null);
    navigate("landing");
  };

  // После смены тарифа (PricingView/ProfileView → POST /api/auth/me/subscription)
  // бэкенд возвращает ПОЛНЫЙ UserResponse — кладём его в стейт напрямую (тот же
  // паттерн, что уже есть в эффекте /api/auth/me выше), рефетч не нужен.
  const handleUserUpdate = (updatedUser) => {
    setUser(updatedUser);
    localStorage.setItem("basis_user", JSON.stringify(updatedUser));
  };

  // Единая точка выбора компании: раньше setSelectedCompany дёргали напрямую из десятка
  // мест (список, скринер, лента, карты, портфель), и адрес не менялся ни в одном.
  // Обёртка ставит и состояние, и URL — правится в одном месте, а не в десяти.
  const selectCompany = (value) => {
    setSelectedCompany(value);
    const t = typeof value === "string" ? value : (value && value.ticker);
    if (t) syncUrl({ company: t });
  };

  // Что человек сейчас читает — из этого строится и подпись подсказки, и
  // заготовленный вопрос. key важен: при его смене таймеры «залипания»
  // сбрасываются, то есть на каждом новом экране отсчёт начинается заново.
  const assistantNudgeContext = React.useMemo(() => {
    const tickerOf = (v) => (typeof v === "string" ? v : (v && v.ticker) || "");
    if (selectedCompany) {
      const tk = tickerOf(selectedCompany);
      const nm = (typeof selectedCompany === "object" && selectedCompany.name) || tk;
      // Имя и тикер совпадают, когда карточка открыта по прямой ссылке (/company/SBER/)
      // и объекта компании ещё нет — тогда «SBER (SBER)» читалось бы как ошибка.
      const label = nm === tk ? tk : `${nm} (${tk})`;
      // nameFromCard: если имя равно тикеру (зашли по прямой ссылке и объекта компании
      // ещё нет), подсказка возьмёт настоящее название с самого экрана карточки.
      return { key: `company:${tk}`, subject: `карточку ${label}`, nameFromCard: nm === tk ? tk : null,
               question: `Объясни простыми словами, что сейчас главное в карточке ${label} — на что смотреть инвестору?` };
    }
    if (selectedBond) return { key: `bond:${selectedBond}`, subject: `этот выпуск (${selectedBond})`,
                               question: `Разбери выпуск ${selectedBond}: адекватна ли доходность взятому риску?` };
    if (selectedFund) return { key: `fund:${selectedFund}`, subject: `этот фонд (${selectedFund})`,
                               question: `Что внутри фонда ${selectedFund}, сколько он стоит по комиссии и честно ли следует бенчмарку?` };
    if (selectedFuture) return { key: `future:${selectedFuture}`, subject: `этот контракт (${selectedFuture})`,
                                 question: `Объясни контракт ${selectedFuture}: на что ставка, какое плечо и чем рискую?` };
    const byTab = {
      overview: { subject: "этот обзор рынка", q: "Что сейчас главное на рынке и что это значит для частного инвестора?" },
      companies: { subject: "этот раздел рынка", q: "С чего начать выбор бумаги на российском рынке — на какие метрики смотреть?" },
      screener: { subject: "метрики скринера", q: "Как правильно читать метрики скринера — P/E, дивдоходность, потенциал к справедливой цене?" },
      portfolio: { subject: "ваш портфель", q: "Посмотри мой портфель: какие риски в нём главные?" },
      stress: { subject: "этот стресс-тест", q: "Что показывает стресс-тест и как читать его результат?" },
    };
    const t = byTab[activeTab];
    return t ? { key: `tab:${activeTab}`, subject: t.subject, question: t.q } : null;
  }, [selectedCompany, selectedBond, selectedFund, selectedFuture, activeTab]);

  const navigate = (tab) => {
    setActiveTab(tab);
    setSelectedCompany(null);
    syncUrl({ view: tab });          // раздел получает свой адрес (?view=…)
    // Любая навигация закрывает мобильную шторку «Ещё», если была открыта —
    // единая точка, покрывает и её собственные пункты, и обычные клики по
    // TopNav/MobileTabBar.
    setMobileMoreOpen(false);
    // Экранные оверлеи (карточка облигации/фьючерса/фонда/спота) рендерятся
    // ПОВЕРХ activeTab в renderView() — раньше только selectedCompany
    // сбрасывался тут, остальные оставались висеть, и клик по верхней
    // навигации молча ничего не делал, пока такой оверлей открыт.
    setSelectedBond(null);
    setSelectedFuture(null);
    setSelectedFund(null);
    setSelectedSpot(null);
    // Индексы больше НЕ отдельный оверлей (владелец: «сайдбар должен
    // оставаться виден и на самой странице индекса») — рендерятся внутри
    // ObserverV2 при activeTab==="overview", поэтому здесь просто закрываем
    // режим индекса, а не полагаемся на порядок веток в renderView().
    setSelectedIndex(null);
    setShowIndexHub(false);
    setForceObsSection(null);
    setDriverChart(null);
    setForceEconIndicator(null);
  };

  // Живой тур по платформе (Часть A плана expressive-bubbling-firefly.md) —
  // единственный источник правды движка тура, вызывается ОДИН раз здесь,
  // прокидывается пропами вниз в TopNav (кнопка-точка входа) и TourOverlay
  // (подсветка + тултипы). Использует УЖЕ существующие navigate/selectCompany —
  // шаг тура делает РЕАЛЬНУЮ навигацию, не притворную.
  const tour = useTourEngine({ activeTab, navigate, onOpenCompany: selectCompany, showAuthModal });

  // Индекс/хаб индексов/индекс страха и жадности показываются ВНУТРИ
  // ObserverV2 (сайдбар Обозревателя остаётся виден и там), независимо от
  // того, откуда открыли — из «Обозревателя» (Обзор рынка) или из «Рынка»
  // (Пульс). Поэтому все три открывашки переключают activeTab на "overview"
  // синхронно с установкой индекса — ObserverV2 гарантированно окажется
  // смонтирован к моменту, когда ему нужно отрендерить страницу индекса.
  const openIndex = (ticker) => { setSelectedIndex(ticker); setShowIndexHub(false); setActiveTab("overview"); };
  const openFearGreed = () => { setSelectedIndex("FEARGREED"); setShowIndexHub(false); setActiveTab("overview"); };
  const openIndexHub = () => { setSelectedIndex(null); setShowIndexHub(true); setActiveTab("overview"); };
  const closeIndexUI = () => { setSelectedIndex(null); setShowIndexHub(false); };

  // Клик по плитке драйвера в «Что движет рынком» (Рынок→Акции). Владелец: «при
  // нажатии на нефть/курс рубля/доходность ОФЗ — перекидывало в обзор рынка где
  // есть графики; ключевая ставка — не в обзор, а в экономическую статистику».
  // «Ставка ЦБ» помечена бэкендом nav:"economy" (там уже есть график с историей),
  // остальные — chart:{asset_class,secid,...} → рисуем график прямо в Обзоре рынка.
  const openDriverChart = (driver) => {
    if (driver.nav === "economy") {
      setDriverChart(null);
      setForceEconIndicator(driver.nav_indicator || null);
      setForceObsSection("economy");
      setActiveTab("overview");
      return;
    }
    if (driver.chart) {
      setDriverChart({ ...driver.chart, name: driver.name });
      setForceObsSection("pulse");
      setActiveTab("overview");
    }
  };

  const renderView = () => {
    if (selectedCompany) {
      // selectedCompany может быть ОБЪЕКТОМ (из грида) или ТИКЕРОМ-строкой (из
      // ссылок эмитент→компания в облигациях/фьючерсах и из скринера) — резолвер
      // приводит к объекту, который ждёт CompanyCard.
      return <CompanyCardResolver value={selectedCompany} onBack={() => { setSelectedCompany(null); syncUrl({ view: activeTab }); }} initialTab={initialCardTab}
                onTabChange={(t) => { const tk = typeof selectedCompany === "string" ? selectedCompany : (selectedCompany && selectedCompany.ticker); if (tk) syncUrl({ company: tk, cardTab: t }); }} />;
    }
    if (selectedBond) return <BondCard secid={selectedBond} onBack={() => setSelectedBond(null)} onSelectCompany={selectCompany} />;
    if (selectedFuture) return <FuturesCard secid={selectedFuture} onBack={() => setSelectedFuture(null)} onSelectCompany={selectCompany} />;
    if (selectedFund) return <FundCard secid={selectedFund} onBack={() => setSelectedFund(null)} />;
    if (selectedSpot) return <SpotCard secid={selectedSpot} onBack={() => setSelectedSpot(null)} />;
    switch (activeTab) {
      case "companies":
        return <CompaniesView onSelectCompany={selectCompany} onSelectIndex={openIndex} onSelectDriver={openDriverChart} forceTab={forceInnerTab} forcePreset={forceMarketPreset} />;
      case "screener":
        return <ScreenerCompareView onSelectCompany={selectCompany} token={token} onAuthRequired={() => setShowAuthModal(true)} />;
      case "overview":
        return (
          <ObserverV2
            token={token} onSelectCompany={selectCompany}
            onOpenBond={setSelectedBond} onOpenFuture={setSelectedFuture} onOpenFund={setSelectedFund} onOpenSpot={setSelectedSpot}
            onSelectIndex={openIndex}
            onOpenFearGreed={openFearGreed}
            onOpenIndexHub={openIndexHub}
            indexTicker={selectedIndex}
            showIndexHub={showIndexHub}
            onCloseIndexUI={closeIndexUI}
            forceSection={forceObsSection}
            driverChart={driverChart}
            forceEconIndicator={forceEconIndicator}
            onOpenPortfolio={() => navigate("portfolio")}
          />
        );
      case "portfolio":
        return <PortfolioV2 token={token} onAuthRequired={() => setShowAuthModal(true)} onOpenCompany={selectCompany} forceSection={forceInnerTab} />;
      case "strategies":
        return <ComingSoonView icon={Target} title="Портфельные стратегии" blurb="Подбор готовой стратегии под ваш профиль риска. Раздел скоро появится — мы его готовим." />;
      case "stress":
        // 🔴 2026-07-16: пункт верхней навигации раньше вёл на ComingSoonView-заглушку.
        // Сначала (в тот же день) перенаправил на узкий портфельный стресс-тест внутри
        // Портфеля (бета×шок индекса, /api/portfolios/{id}/stress-test) — владелец
        // поправил 2026-07-17: это НЕ то, что должен быть блок «Стресс-тестирование».
        // Нужен сценарный «что если» на компании/акции/облигации целиком (война N лет,
        // обвал/скачок нефти, налоговое давление, инфляционные ожидания, сценарий ЦБ,
        // числовые шоки по нефти/курсу) — StressTestView, живой факторный движок
        // (backend/app/services/stress_scenarios.py), явно помечен как демо-версия.
        // Портфельный стресс-тест остаётся отдельно доступен внутри самого Портфеля.
        // 🔴 token обязателен (2026-08-08): экран ходит в закрываемые тарифом
        // эндпоинты, а без заголовка сервер видит ГОСТЯ — подписчик Max получал
        // «доступно на тарифе Max» на своей же оплаченной подписке.
        return <StressTestView token={token} onOpenCompany={selectCompany} />;
      case "ai":
        return <AssistantView token={token} onAuthRequired={() => setShowAuthModal(true)}
                 onOpenCompany={selectCompany} initialQuestion={assistantPrefill}
                 onQuestionConsumed={() => setAssistantPrefill("")} />;
      case "pricing":
        return (
          <PricingView
            user={user}
            token={token}
            onShowAuth={() => setShowAuthModal(true)}
            onUserUpdate={handleUserUpdate}
          />
        );
      case "profile":
        return (
          <ProfileView
            user={user}
            token={token}
            onLogout={handleLogout}
            onNavigate={navigate}
            onShowAuth={() => setShowAuthModal(true)}
            onUserUpdate={handleUserUpdate}
            tourLabel={tour.buttonLabel}
            onTourClick={tour.onEntryClick}
            tourCompleted={tour.phase === "completed"}
            tourPaused={tour.phase === "paused"}
          />
        );
      default:
        return <CompaniesView onSelectCompany={selectCompany} onSelectIndex={openIndex} onSelectDriver={openDriverChart} />;
    }
  };

  if (typeof window !== "undefined" && window.location.pathname === "/_design") {
    return <DesignSystem />;
  }

  // Адрес не распознан, а под приложением лежит статическая SEO-страница — показываем
  // только её. Иначе пользователь видит две страницы разом: сверху статику, снизу
  // главную приложения (баг, пойманный владельцем на странице PMI 2026-07-31).
  if (staticOnly) return null;

  if (notFound) {
    return (
      <div data-theme={theme} className="tw-bg-bg-base tw-text-text-primary">
        <div style={{ maxWidth: 640, margin: "0 auto", padding: "80px 20px", fontFamily: "var(--bs-sans, Inter, sans-serif)" }}>
          <p style={{ color: "var(--bs-copper, #C97A4A)", fontSize: 13, letterSpacing: ".08em", textTransform: "uppercase", margin: 0 }}>
            Ошибка 404
          </p>
          <h1 style={{ fontFamily: "var(--bs-serif, Fraunces, serif)", fontSize: 32, lineHeight: 1.2, margin: "10px 0 14px" }}>
            Такой страницы нет
          </h1>
          <p style={{ color: "var(--bs-muted, #5A5248)", lineHeight: 1.6, margin: "0 0 24px" }}>
            Возможно, адрес набран с опечаткой или страница была переименована.
            Вот основные разделы — оттуда можно найти нужное.
          </p>
          <ul style={{ lineHeight: 2, paddingLeft: 18, margin: 0 }}>
            <li><a href="/company/">Каталог компаний</a> — разборы по тикеру</li>
            <li><a href="/pokazateli/">Показатели и термины</a> — что означают цифры</li>
            <li><a href="/skrining-aktsiy/">Скрининг акций</a> и <a href="/skrining-obligatsiy/">облигаций</a></li>
            <li><a href="/obzor-rynka/">Обзор рынка</a>, <a href="/novosti-fondovogo-rynka/">новости</a></li>
            <li><a href="/">Главная страница Basis</a></li>
          </ul>
        </div>
      </div>
    );
  }

  if (verifyEmail) {
    const isErr = String(verifyEmail).startsWith("error:");
    const done = verifyEmail === "ok" || verifyEmail === "already";
    return (
      <div data-theme={theme} className="tw-bg-bg-base tw-text-text-primary">
        <div style={{ maxWidth: 560, margin: "0 auto", padding: "90px 20px", textAlign: "center", fontFamily: "var(--bs-sans, Inter, sans-serif)" }}>
          <div style={{ fontSize: 40, marginBottom: 14 }} aria-hidden="true">{done ? "✅" : isErr ? "⚠️" : "⏳"}</div>
          <h1 style={{ fontFamily: "var(--bs-serif, Fraunces, serif)", fontSize: 28, margin: "0 0 12px" }}>
            {verifyEmail === "ok" ? "Почта подтверждена"
              : verifyEmail === "already" ? "Почта уже была подтверждена"
                : isErr ? "Не получилось подтвердить" : "Подтверждаем адрес…"}
          </h1>
          <p style={{ color: "var(--bs-muted, #5A5248)", lineHeight: 1.6, margin: "0 0 26px" }}>
            {done ? "Спасибо! Статус адреса обновлён — это видно в разделе «Профиль»."
              : isErr ? String(verifyEmail).slice(6) + " Можно отправить письмо повторно из раздела «Профиль»."
                : "Секунду — проверяем ссылку из письма."}
          </p>
          {verifyEmail !== "pending" && (
            <button type="button" onClick={() => setVerifyEmail(null)}
              style={{ font: "inherit", fontWeight: 600, padding: "10px 26px", borderRadius: 999, border: "1px solid var(--bs-copper, #C97A4A)", background: "var(--bs-copper, #C97A4A)", color: "#fff", cursor: "pointer" }}>
              Перейти на платформу
            </button>
          )}
        </div>
      </div>
    );
  }

  // Лендинг — только когда НИЧЕГО не открыто. Раньше проверялась одна компания, и
  // открытая карточка облигации/фьючерса/фонда соседствовала с лендингом на экране.
  const isLanding = activeTab === "landing" && !selectedCompany
    && !selectedBond && !selectedFuture && !selectedFund && !selectedSpot;
  const toggleTheme = () => setTheme(t => t === "dark" ? "light" : "dark");

  // Ключ текущего «экрана» для RegisterNudge (владелец, 2026-08-02): смена
  // карточки компании/бумаги ИЛИ раздела навигации — это «новая страница»;
  // под-вкладки ВНУТРИ одной карточки (Финансы/Обзор той же компании) в счёт
  // не идут — счётчик молчит, пока пользователь листает вкладки одной карточки.
  const viewKey = selectedCompany
    ? `company:${typeof selectedCompany === "string" ? selectedCompany : selectedCompany.ticker}`
    : selectedBond ? `bond:${selectedBond}`
    : selectedFuture ? `future:${selectedFuture}`
    : selectedFund ? `fund:${selectedFund}`
    : selectedSpot ? `spot:${selectedSpot}`
    : `tab:${activeTab}`;

  return (
    <div data-theme={theme} className={`tw-bg-bg-base tw-text-text-primary${NEO_CARD ? " cc-root" : ""}`}>
      <div className="app-shell">
        <TopNav
          activeTab={selectedCompany ? null : activeTab}
          onNav={navigate}
          theme={theme}
          toggleTheme={toggleTheme}
          onOpenCompany={selectCompany}
          isAuthenticated={!!token}
          onOpenAuth={() => setShowAuthModal(true)}
        />
        {isLanding ? (
          <ViewErrorBoundary routeKey="landing">
            <LandingNeo
              onNavigate={navigate}
              onOpenCompany={selectCompany}
              onShowAuth={() => setShowAuthModal(true)}
              theme={theme}
              toggleTheme={toggleTheme}
            />
          </ViewErrorBoundary>
        ) : (
          <main className="app-main-top">
            <ViewErrorBoundary routeKey={`${activeTab}:${selectedCompany ? "card" : "list"}`}>
              {/* Suspense обязателен для ленивых разделов: пока грузится чанк, показываем
                  спокойную заглушку вместо срыва рендера. Текст нейтральный — раздел
                  может быть любым (портфель, скринер, карты). */}
              <React.Suspense fallback={<div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-animate-pulse">Загружаем раздел…</div>}>
                {renderView()}
              </React.Suspense>
            </ViewErrorBoundary>
          </main>
        )}
      </div>

      {/* Нижний фикс-таббар мобильной навигации (≤760px, display:none выше —
          styles/mobile-nav.css). Раньше не рендерился на посадочной странице
          («у неё свой мобильный хром») — владелец, 2026-07-21 (третий заход):
          с телефона на лендинге нет способа сразу попасть в Рынок/Обзор/
          Портфель без прохождения landing-CTA. У LandingNeo свой мобильный
          хром — это ВЕРХНИЙ маркетинговый nav (Features/Pricing), не имеет
          отношения к навигации по разделам приложения — конфликта с нижним
          таббаром нет (фиксированных элементов снизу в landing.css нет). */}
      {/* Подсказка «спросите ассистента» — показывается, когда человек ЗАЛИП на
          чтении (открыл давно и перестал листать), а не при входе. Контекст даёт
          заготовленный вопрос: из карточки спрашивается про компанию, из
          Обозревателя — про раздел. Владелец, 2026-08-20. */}
      <AssistantNudge
        context={assistantNudgeContext}
        disabled={isLanding || activeTab === "ai" || showAuthModal}
        onAsk={(q) => { setAssistantPrefill(q); navigate("ai"); }}
      />

      <MobileTabBar
        activeTab={selectedCompany || isLanding ? null : activeTab}
        onNav={navigate}
        moreOpen={mobileMoreOpen}
        onToggleMore={() => setMobileMoreOpen((v) => !v)}
      />
      {mobileMoreOpen && (
        <MobileMoreSheet
          activeTab={selectedCompany || isLanding ? null : activeTab}
          onNav={navigate}
          onClose={() => setMobileMoreOpen(false)}
        />
      )}

      {showAuthModal && (
        <AuthModal onClose={() => setShowAuthModal(false)} onSuccess={handleLogin} />
      )}

      {/* Отложенный тост-приглашение к регистрации (владелец, 2026-08-02) — по
          всему сайту, не привязан к конкретному разделу. Скрыт, пока открыт
          AuthModal (иначе просвечивал бы сквозь полупрозрачный скрим), и не
          рендерится вовсе для залогиненных — сам компонент решает, ждать
          таймер или нет (см. account/RegisterNudge.jsx).
          🔴 Гасится и на время тура: шаги тура сами переключают разделы, viewKey
          меняется на каждом шаге и нудж вылезал ровно поверх карточки тура —
          два приглашения одновременно читаются как каша (поймано прогоном тура
          2026-08-05). Приглашение к регистрации никуда не денется: тур
          заканчивается, phase уходит из "running", таймер нуджа продолжится. */}
      {!token && !showAuthModal && tour.phase !== "running" && tour.phase !== "welcome" && (
        <RegisterNudge onOpenAuth={() => setShowAuthModal(true)} viewKey={viewKey} />
      )}

      {/* Живой тур по платформе — приветствие/подсветка/тултипы/тост паузы.
          Один инстанс на всё приложение (не привязан к конкретному разделу),
          сам решает, показывать ли что-то, по tour.phase (design/TourOverlay.jsx). */}
      <TourOverlay tour={tour} />
    </div>
  );
}
