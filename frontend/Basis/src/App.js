import React, { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import DesignSystem from "./design/DesignSystem";
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
  ShieldAlert,
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
} from "lucide-react";
import { Button, Card, Badge, Chip, Input, IconButton, Tooltip, Table, Delta, KpiTile, usePrefersReducedMotion } from "./design/primitives";
import { formatMoney, formatPercent as fmtPercent, formatNumber, formatNumber as fmtNumber, formatMultiple } from "./design/format";
import { WeightBar, MetricBar, CorrelationHeatmap, ImpactBar, useCountUp, catFor } from "./design/PortfolioViz";
import { CompanyLogo } from "./design/CompanyLogo";
import { Prose, LeadStatement, KeyTakeaway, Disclosure, ANALYST_MD } from "./design/textblocks";
import { CompanyIdentityBlock, PricePanel, MetricStrip, ResearchTabs as NeoResearchTabs, DecisionSupportRail } from "./company/neo";
import ScreenerNeo from "./screener/ScreenerNeo";
import BondScreenerNeo from "./screener/BondScreenerNeo";
import MarketNeo from "./market/MarketNeo";
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
  ObsMacroArticles,
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
import { PortfolioV2 } from "./portfolio/PortfolioViews";
import { AuthModal } from "./account/AccountPanels";
import PricingView from "./account/PricingView";
import ProfileView from "./account/ProfileView";
import { CompanyCard, ScreenerView, CompaniesView, NEO_CARD, BondCard, FuturesCard, FundCard, SpotCard } from "./company/CompanyCardView";
import AssistantView from "./AssistantView";
import CompareView from "./compare/CompareView";
import "./styles/compare.css";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";

function ObserverV2({ token, onSelectCompany, onOpenBond, onOpenFuture, onOpenFund, onOpenSpot }) {
  const [activeSection, setActiveSection] = useState("news");
  const [portfolioOnly, setPortfolioOnly] = useState(false);

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
            <ObsEconomy token={token} />
          </div>
        );
      case "pulse":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Рынок</span>
              <h2 className="obs-sec-title">Обзор рынка</h2>
            </div>
            <ObsMarketPulse onSelectCompany={onSelectCompany} />
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
      case "macro":
        return (
          <div className="obs-panel">
            <div className="obs-sec-head">
              <span className="obs-sec-eyebrow">Разбор</span>
              <h2 className="obs-sec-title">Макроэкономика</h2>
              <ObsHorizonChip>горизонт актуальности: дни-недели</ObsHorizonChip>
            </div>
            <ObsMacroArticles token={token} />
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
    <div className="obs-shell">
      {/* ---- Dark sidebar ---- */}
      <nav className="obs-sidebar" aria-label="Разделы Обозревателя">
        <div className="obs-depth-strip" aria-hidden="true" />
        <div className="obs-eyebrow">Обозреватель</div>

        {OBS_ZONES.map((zone) => (
          <div key={zone.id} className="obs-zone">
            <div className="obs-zone-label">{zone.label}</div>
            {zone.items.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                className={`obs-item${activeSection === id ? " obs-item--active" : ""}`}
                onClick={() => setActiveSection(id)}
                aria-current={activeSection === id ? "page" : undefined}
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
          Basis не брокер и не&nbsp;даёт рекомендаций «купить/продать».
        </div>
      </nav>

      {/* ---- Light main area ---- */}
      <main className="obs-main" key={activeSection}>
        {renderSection()}
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

// Резолвер карточки: значение может быть объектом компании или тикером-строкой.
const CompanyCardResolver = ({ value, onBack }) => {
  const [obj, setObj] = useState(typeof value === "object" && value ? value : null);
  const [notFound, setNotFound] = useState(false);
  useEffect(() => {
    if (typeof value === "object" && value) { setObj(value); return; }
    if (typeof value !== "string") return;
    let alive = true;
    fetch(`${apiBase()}/api/companies`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => { if (!alive) return; const c = (list || []).find((x) => x.ticker === value); c ? setObj(c) : setNotFound(true); })
      .catch(() => alive && setNotFound(true));
    return () => { alive = false; };
  }, [value]);
  if (obj) return <CompanyCard company={obj} onBack={onBack} />;
  if (notFound) return <div className="tw-py-12 tw-text-text-tertiary">Компания «{String(value)}» не найдена в базе. <button onClick={onBack} className="tw-text-accent tw-underline tw-bg-transparent tw-border-0 tw-cursor-pointer">Назад</button></div>;
  return <div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-text-[18px] tw-animate-pulse">Открываем карточку...</div>;
};

// Единый плейсхолдер «Раздел в разработке» — один на все будущие блоки.
function ComingSoonView({ icon: Icon = Sparkles, title, blurb }) {
  return (
    <div>
      <div className="view-header">
        <h1 className="view-title">{title}</h1>
      </div>
      <div className="tw-flex tw-items-center tw-justify-center tw-py-20">
        <Card className="tw-max-w-[460px] tw-w-full tw-text-center">
          <div className="tw-flex tw-flex-col tw-items-center tw-gap-4 tw-py-6">
            <span className="tw-w-14 tw-h-14 tw-rounded-xl tw-bg-accent-soft tw-flex tw-items-center tw-justify-center tw-shrink-0">
              <Icon size={26} className="tw-text-accent" aria-hidden="true" />
            </span>
            <div>
              <h2 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0 tw-mb-2">Раздел в разработке</h2>
              <p className="tw-text-[14px] tw-text-text-secondary tw-leading-[1.6] tw-m-0">
                {blurb || "Этот раздел скоро появится — мы его готовим. Загляните позже."}
              </p>
            </div>
            <Badge tone="neutral">Скоро</Badge>
          </div>
        </Card>
      </div>
    </div>
  );
}

// =========================
// ВЕРХНЯЯ НАВИГАЦИЯ (глобальный шелл вместо левого рейла) — единый компонент.
// =========================
const TOPNAV_ITEMS = [
  { id: "companies", label: "Рынок" },
  { id: "overview", label: "Обозреватель" },
  { id: "portfolio", label: "Портфель" },
  { id: "screener", label: "Скринер" },
  { id: "compare", label: "Сравнение" },
  { id: "ai", label: "Ассистент" },
  { id: "pricing", label: "Тарифы" },
  { id: "profile", label: "Профиль" },
];

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
    <div ref={boxRef} className="tw-relative tw-flex-shrink-0">
      <div className="tw-flex tw-items-center tw-gap-2 tw-h-9 tw-px-3 tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-elevated tw-text-text-tertiary focus-within:tw-border-accent" style={{ minWidth: 200 }}>
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

function TopNav({ activeTab, onNav, theme, toggleTheme, onOpenCompany }) {
  return (
    <header
      className="tw-sticky tw-top-0 tw-z-40 tw-border-b tw-border-border-subtle"
      style={{ background: "color-mix(in srgb, var(--cc-bg, var(--bg-base)) 85%, transparent)", backdropFilter: "blur(10px)", WebkitBackdropFilter: "blur(10px)" }}
    >
      <div className="tw-mx-auto tw-flex tw-h-[60px] tw-items-center tw-gap-6 tw-px-5 sm:tw-px-7" style={{ maxWidth: 1340 }}>
        <button
          type="button"
          aria-label="Basis — на главную"
          onClick={() => onNav("landing")}
          className="tw-appearance-none tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer tw-flex tw-items-center tw-gap-2 tw-flex-shrink-0"
        >
          <BasisLogomark size={26} slit="var(--bg-base)" crisp />
          <span className="tw-font-display tw-text-[17px] tw-font-semibold tw-text-text-primary">Basis</span>
        </button>

        <nav aria-label="Основная навигация" className="tw-flex tw-items-center tw-gap-0.5 tw-flex-1 tw-overflow-x-auto">
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

        <div className="tw-flex tw-items-center tw-gap-2 tw-flex-shrink-0">
          <TopNavSearch onOpenCompany={onOpenCompany} />
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

  // Deep-link по ?company=TICKER — вход из статических SEO-страниц
  // (build/company/<TICKER>/, см. scripts/generate-seo-pages.js) в живое приложение.
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const t = params.get("company");
      if (t) setSelectedCompany(t.toUpperCase());
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
  };

  const handleLogout = () => {
    localStorage.removeItem("basis_token");
    localStorage.removeItem("basis_user");
    setUser(null);
    setToken(null);
    setActiveTab("landing");
  };

  // После смены тарифа (PricingView/ProfileView → POST /api/auth/me/subscription)
  // бэкенд возвращает ПОЛНЫЙ UserResponse — кладём его в стейт напрямую (тот же
  // паттерн, что уже есть в эффекте /api/auth/me выше), рефетч не нужен.
  const handleUserUpdate = (updatedUser) => {
    setUser(updatedUser);
    localStorage.setItem("basis_user", JSON.stringify(updatedUser));
  };

  const navigate = (tab) => {
    setActiveTab(tab);
    setSelectedCompany(null);
  };

  const renderView = () => {
    if (selectedCompany) {
      // selectedCompany может быть ОБЪЕКТОМ (из грида) или ТИКЕРОМ-строкой (из
      // ссылок эмитент→компания в облигациях/фьючерсах и из скринера) — резолвер
      // приводит к объекту, который ждёт CompanyCard.
      return <CompanyCardResolver value={selectedCompany} onBack={() => setSelectedCompany(null)} />;
    }
    if (selectedBond) return <BondCard secid={selectedBond} onBack={() => setSelectedBond(null)} onSelectCompany={setSelectedCompany} />;
    if (selectedFuture) return <FuturesCard secid={selectedFuture} onBack={() => setSelectedFuture(null)} onSelectCompany={setSelectedCompany} />;
    if (selectedFund) return <FundCard secid={selectedFund} onBack={() => setSelectedFund(null)} />;
    if (selectedSpot) return <SpotCard secid={selectedSpot} onBack={() => setSelectedSpot(null)} />;
    switch (activeTab) {
      case "companies":
        return <CompaniesView onSelectCompany={setSelectedCompany} />;
      case "screener":
        return <ScreenerView onSelectCompany={setSelectedCompany} token={token} onAuthRequired={() => setShowAuthModal(true)} />;
      case "overview":
        return (
          <ObserverV2
            token={token} onSelectCompany={setSelectedCompany}
            onOpenBond={setSelectedBond} onOpenFuture={setSelectedFuture} onOpenFund={setSelectedFund} onOpenSpot={setSelectedSpot}
          />
        );
      case "portfolio":
        return <PortfolioV2 token={token} onAuthRequired={() => setShowAuthModal(true)} onOpenCompany={setSelectedCompany} />;
      case "strategies":
        return <ComingSoonView icon={Target} title="Портфельные стратегии" blurb="Подбор готовой стратегии под ваш профиль риска. Раздел скоро появится — мы его готовим." />;
      case "stress":
        return <ComingSoonView icon={ShieldAlert} title="Стресс-тестирование" blurb="Проверка портфеля на просадку в кризисных сценариях. Раздел скоро появится." />;
      case "ai":
        return <AssistantView token={token} onAuthRequired={() => setShowAuthModal(true)} onOpenCompany={setSelectedCompany} />;
      case "compare":
        return <CompareView onOpenCompany={setSelectedCompany} />;
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
          />
        );
      default:
        return <CompaniesView onSelectCompany={setSelectedCompany} />;
    }
  };

  if (typeof window !== "undefined" && window.location.pathname === "/_design") {
    return <DesignSystem />;
  }

  const isLanding = activeTab === "landing" && !selectedCompany;
  const toggleTheme = () => setTheme(t => t === "dark" ? "light" : "dark");

  return (
    <div data-theme={theme} className={`tw-bg-bg-base tw-text-text-primary${NEO_CARD ? " cc-root" : ""}`}>
      <div className="app-shell">
        <TopNav
          activeTab={selectedCompany ? null : activeTab}
          onNav={navigate}
          theme={theme}
          toggleTheme={toggleTheme}
          onOpenCompany={setSelectedCompany}
        />
        {isLanding ? (
          <ViewErrorBoundary routeKey="landing">
            <LandingNeo
              onNavigate={navigate}
              onOpenCompany={setSelectedCompany}
              onShowAuth={() => setShowAuthModal(true)}
              theme={theme}
              toggleTheme={toggleTheme}
            />
          </ViewErrorBoundary>
        ) : (
          <main className="app-main-top">
            <ViewErrorBoundary routeKey={`${activeTab}:${selectedCompany ? "card" : "list"}`}>
              {renderView()}
            </ViewErrorBoundary>
          </main>
        )}
      </div>

      {showAuthModal && (
        <AuthModal onClose={() => setShowAuthModal(false)} onSuccess={handleLogin} />
      )}
    </div>
  );
}
