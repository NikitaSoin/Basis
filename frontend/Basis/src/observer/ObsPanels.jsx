import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Newspaper,
  Activity,
  Briefcase,
  Landmark,
  Layers,
  Calendar,
  ChevronDown,
  Clock,
  FileText,
  BarChart2,
  Globe,
  Scale,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";
import { Disclosure, ANALYST_MD } from "../design/textblocks";

// =========================
// OBSERVER V2 — sidebar layout (Этап 1 каркас)
// Тёмный фиксированный сайдбар, 3 зоны, 9 разделов.
// Пилот: «Лента новостей» → реальный <NewsFeed>.
// Остальные 8 — структурные плейсхолдеры.
// =========================

const OBS_ZONES = [
  {
    id: "data",
    label: "Данные",
    items: [
      { id: "news",    label: "Лента новостей",           icon: Newspaper  },
      { id: "economy", label: "Экономическая статистика", icon: Activity   },
    ],
  },
  {
    id: "market",
    label: "Рынок",
    items: [
      { id: "pulse",    label: "Обзор рынка",        icon: TrendingUp },
      { id: "maps",     label: "Карта рынка",        icon: Layers   },
      { id: "calendar", label: "Календарь событий",  icon: Calendar },
      { id: "reports",  label: "Отчёты",             icon: FileText },
    ],
  },
  {
    id: "analysis",
    label: "Разбор",
    items: [
      { id: "macro",        label: "Макроэкономика",          icon: BarChart2  },
      { id: "geo",          label: "Геополитика",             icon: Globe      },
      { id: "institutions", label: "Институциональная среда", icon: ShieldCheck },
      { id: "ai",           label: "ИИ-обзор и анализ",       icon: Sparkles   },
    ],
  },
];

// Описания для плейсхолдеров (не пилотных разделов)
const OBS_SECTION_META = {
  economy:      { title: "Экономическая статистика", eyebrow: "Данные",  blurb: "Ключевые макроиндикаторы России: ставка ЦБ, инфляция, ВВП, курсы валют, занятость. Раздел в подготовке." },
  maps:         { title: "Карта рынка",              eyebrow: "Рынок",   blurb: "Тепловая карта акций, облигаций и фьючерсов — размер плитки по капитализации, цвет по динамике." },
  calendar:     { title: "Календарь событий",        eyebrow: "Рынок",   blurb: "Дивидендные отсечки, собрания акционеров, публикации отчётностей, макростатистика." },
  reports:      { title: "Отчёты",                   eyebrow: "Рынок",   blurb: "Разборы вышедших квартальных и годовых результатов с оценкой ключевых метрик." },
  macro:        { title: "Макроэкономика",           eyebrow: "Разбор",  blurb: "Аналитические записки ЦБ, ЦМАКП, прогнозы — с интерпретацией Basis: что из этого следует для инвестора." },
  geo:          { title: "Геополитика",              eyebrow: "Разбор",  blurb: "Ключевые геополитические события и их влияние на рынок — экспортёры, сырьё, курс рубля." },
  institutions: { title: "Институциональная среда",  eyebrow: "Разбор",  blurb: "Изменения в регулировании, налоговой политике и корпоративных правилах, влияющих на эмитентов." },
  ai:           { title: "ИИ-обзор и анализ",        eyebrow: "Разбор",  blurb: "Еженедельный синтез: что происходит на рынке и какие выводы делает Basis по совокупности сигналов." },
};

function ObsSectionPlaceholder({ sectionId }) {
  const meta = OBS_SECTION_META[sectionId] || { title: "Раздел", eyebrow: "Обозреватель", blurb: "Раздел в подготовке." };
  const Icon = (OBS_ZONES.flatMap((z) => z.items).find((i) => i.id === sectionId) || {}).icon || Sparkles;
  return (
    <div className="obs-panel">
      <div className="obs-sec-head">
        <span className="obs-sec-eyebrow">{meta.eyebrow}</span>
        <h2 className="obs-sec-title">{meta.title}</h2>
      </div>
      <div className="obs-placeholder">
        <div className="obs-placeholder__icon">
          <Icon size={24} aria-hidden="true" />
        </div>
        <h3 className="obs-placeholder__title">Раздел в подготовке</h3>
        <p className="obs-placeholder__body">{meta.blurb}</p>
        <span className="obs-placeholder__badge">Скоро</span>
      </div>
    </div>
  );
}

// =============================================================
// ObsNewsFeed — «Лента новостей» точно по прототипу observer-sidebar-v2.html
// Два filterbar (важность + тема), клиентские фильтры, карточки .obs-news-card,
// cursor прочтения из localStorage (перенесён из NewsFeed).
// =============================================================

function _newsTime(iso) {
  try {
    const dt = new Date(iso);
    if (isNaN(dt)) return "";
    const msk = new Date(dt.getTime() + (dt.getTimezoneOffset() + 180) * 60000);
    const hh = String(msk.getHours()).padStart(2, "0");
    const mm = String(msk.getMinutes()).padStart(2, "0");
    const nowMsk = new Date(Date.now() + (new Date().getTimezoneOffset() + 180) * 60000);
    const sameDay = msk.getDate() === nowMsk.getDate() && msk.getMonth() === nowMsk.getMonth();
    return sameDay ? `${hh}:${mm}` : `${String(msk.getDate()).padStart(2, "0")}.${String(msk.getMonth() + 1).padStart(2, "0")} ${hh}:${mm}`;
  } catch { return ""; }
}

const _SOURCE_LABEL = { interfax: "Интерфакс", rbc: "РБК", kommersant: "Коммерсантъ" };

const _NEWS_TOPIC_MAP = {
  business: ["Бизнес"],
  macro:    ["Экономика", "Рынки", "Макроэкономика"],
  politics: ["Политика", "Геополитика"],
};

function ObsNewsFeed({ token, portfolioOnly, onSelectCompany }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [importance, setImportance] = useState("all");
  const [topic, setTopic] = useState("all");
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Unread cursor (frozen on open, updates localStorage in background)
  const uid = (() => { try { return JSON.parse(localStorage.getItem("basis_user"))?.id ?? "anon"; } catch { return "anon"; } })();
  const cursorKey = `basis_news_read_${uid}`;
  const baselineRef = useRef(null);
  if (baselineRef.current === null) {
    const v = Number(localStorage.getItem(cursorKey));
    baselineRef.current = Number.isFinite(v) ? v : 0;
  }
  const baseline = baselineRef.current;
  const seenRef = useRef(baseline);
  const saveTimer = useRef(null);
  const firstUnreadRef = useRef(null);

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ limit: "120" });
    if (portfolioOnly) params.set("portfolio_only", "true");
    fetch(`${apiUrl}/api/market/news?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setItems(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token]);

  // Sort newest-first
  const sorted = [...items].sort((a, b) => {
    const ta = new Date(a.published_at || 0).getTime(), tb = new Date(b.published_at || 0).getTime();
    return (tb - ta) || ((b.id || 0) - (a.id || 0));
  });

  // Client-side filters
  const filtered = sorted.filter((n) => {
    const impOk = importance === "all" || (importance === "important" && n.importance === "high");
    const cat = n.category || "";
    const topicOk = topic === "all" || (_NEWS_TOPIC_MAP[topic] || []).some((t) => cat.includes(t));
    return impOk && topicOk;
  });

  const firstUnreadIdx = filtered.findIndex((n) => (n.id || 0) > baseline);

  // Scroll to first unread after load
  useEffect(() => {
    if (loading || filtered.length === 0) return;
    const t = setTimeout(() => {
      if (firstUnreadRef.current) firstUnreadRef.current.scrollIntoView({ block: "center", behavior: "auto" });
    }, 80);
    return () => clearTimeout(t);
  }, [loading]);

  const markSeen = (id) => {
    if (!id || id <= seenRef.current) return;
    seenRef.current = id;
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      localStorage.setItem(cursorKey, String(seenRef.current));
    }, 500);
  };

  return (
    <div>
      {/* Two filterbar rows: importance + vertical divider + topic */}
      <div className="obs-news-filters">
        <div className="obs-news-filterbar">
          {[
            { id: "all",       label: "Все" },
            { id: "important", label: "Важное" },
          ].map((o) => (
            <button
              key={o.id}
              type="button"
              className={"obs-news-chip" + (importance === o.id ? " obs-news-chip--active" : "")}
              onClick={() => setImportance(o.id)}
              aria-pressed={importance === o.id}
            >
              {o.label}
            </button>
          ))}
        </div>
        <div className="obs-news-divider" aria-hidden="true" />
        <div className="obs-news-filterbar">
          {[
            { id: "all",      label: "Все" },
            { id: "business", label: "Бизнес" },
            { id: "macro",    label: "Макроэкономика" },
            { id: "politics", label: "Политика" },
          ].map((o) => (
            <button
              key={o.id}
              type="button"
              className={"obs-news-chip" + (topic === o.id ? " obs-news-chip--active" : "")}
              onClick={() => setTopic(o.id)}
              aria-pressed={topic === o.id}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content area */}
      {loading ? (
        <div className="obs-news-loading">Загружаем ленту…</div>
      ) : error ? (
        <div className="obs-news-empty">Не удалось загрузить ленту. Попробуйте обновить страницу.</div>
      ) : filtered.length === 0 ? (
        <div className="obs-news-empty">
          {portfolioOnly
            ? "По вашему портфелю значимых новостей за этот период нет."
            : "Новостей по выбранным фильтрам нет."}
        </div>
      ) : (
        <div className="obs-news-list">
          {filtered.map((n, i) => {
            const isFirstUnread = i === firstUnreadIdx;
            const unread = (n.id || 0) > baseline;
            return (
              <React.Fragment key={n.id ?? i}>
                {isFirstUnread && (
                  <div ref={firstUnreadRef} className="obs-news-unread-sep" role="separator" aria-label="Непрочитанные новости">
                    <span className="obs-news-unread-label">Непрочитанное</span>
                  </div>
                )}
                <ObsNewsCardItem
                  n={n}
                  unread={unread}
                  onSeen={markSeen}
                  onSelectCompany={onSelectCompany}
                />
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ObsNewsCardItem({ n, unread, onSeen, onSelectCompany }) {
  const high = n.importance === "high";
  const ref = useRef(null);

  useEffect(() => {
    if (!onSeen || !ref.current) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => { if (e.isIntersecting) onSeen(n.id); });
    }, { threshold: 0.6 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [n.id]);

  const source = _SOURCE_LABEL[n.source] || n.source || "Источник";
  const time   = n.published_at ? _newsTime(n.published_at) : "";
  const cat    = n.category || "";

  // Build impact text: prefer impact_comment; fall back to generic phrasing with tickers
  const hasImpact = n.impact_comment || (n.affected_tickers && n.affected_tickers.length > 0);
  const impactText = n.impact_comment || (n.affected_tickers && n.affected_tickers.length > 0
    ? `затрагивает ${n.affected_tickers.join(", ")}`
    : null);

  return (
    <div ref={ref} className={"obs-news-card" + (unread ? " obs-news-card--unread" : "")}>
      {/* Meta: source · time · category | tag-judgment */}
      <div className="obs-news-meta">
        <div className="obs-news-meta-left">
          <span className="obs-news-source">{source}</span>
          {time && <><span aria-hidden="true">&nbsp;·&nbsp;</span><span className="obs-news-time">{time}</span></>}
          {cat  && <><span aria-hidden="true">&nbsp;·&nbsp;</span><span className="obs-news-category">{cat}</span></>}
        </div>
        {high && <span className="obs-tag-judgment" aria-label="Важное событие">важное</span>}
      </div>

      {/* Headline */}
      <h3 className="obs-news-title">{n.title}</h3>

      {/* Body summary */}
      {n.summary && <p className="obs-news-body">{n.summary}</p>}

      {/* Impact callout (↳ …) */}
      {hasImpact && impactText && (
        <div className="obs-news-impact">↳ {impactText}</div>
      )}

      {/* Clickable ticker chips (always show, even if already in impact text) */}
      {n.affected_tickers && n.affected_tickers.length > 0 && onSelectCompany && (
        <div className="obs-news-tickers">
          {n.affected_tickers.map((t) => (
            <button
              key={t}
              type="button"
              className="obs-news-ticker"
              onClick={() => onSelectCompany(t)}
              aria-label={"Открыть карточку " + t}
            >
              {t}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// =============================================================
// ObsReports — «Отчёты» точно по прототипу observer-sidebar-v2.html
// Карточки с метрик-чипами (Выручка/EBITDA/Прибыль, цвет по знаку),
// вердикт, разворот с секциями positives/risks/conclusion.
// Данные: GET /api/market/earnings (поля: revenue_pct, ebitda_pct,
// profit_pct, positives[], risks[], conclusion, sector, importance).
// =============================================================

function ObsReports({ token, portfolioOnly, onSelectCompany }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [openCards, setOpenCards] = useState({});
  const [sectorFilter, setSectorFilter] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${apiUrl}/api/market/earnings?portfolio_only=${portfolioOnly}`, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token]);

  const reports = data?.reports || [];
  const sectors = [...new Set(reports.map((r) => r.sector).filter(Boolean))].sort();
  const filtered = sectorFilter ? reports.filter((r) => r.sector === sectorFilter) : reports;

  // Detect negative value: starts with unicode minus '−' or ascii '-'
  const isNeg = (v) => v && (String(v).trimStart().startsWith("−") || String(v).trimStart().startsWith("-"));
  const metricColor = (v) => isNeg(v) ? "var(--danger)" : "var(--success)";
  const toggleCard = (i) => setOpenCards((o) => ({ ...o, [i]: !o[i] }));

  return (
    <div>
      <p className="obs-rep-desc">
        Вышедшие отчётности: цифры видно сразу, полный разбор — по клику. Ознакомительно, не ИИР.
      </p>

      {/* Sector filter chips */}
      {sectors.length > 0 && (
        <div className="obs-rep-filters" role="group" aria-label="Фильтр по сектору">
          <button
            type="button"
            className={`obs-rep-chip${!sectorFilter ? " obs-rep-chip--active" : ""}`}
            onClick={() => setSectorFilter(null)}
          >Все</button>
          {sectors.map((s) => (
            <button
              key={s}
              type="button"
              className={`obs-rep-chip${sectorFilter === s ? " obs-rep-chip--active" : ""}`}
              onClick={() => setSectorFilter(s)}
            >{s}</button>
          ))}
        </div>
      )}

      {loading && <div className="obs-news-loading">Загрузка отчётов…</div>}
      {error && <div className="obs-news-loading" style={{ color: "var(--danger)" }}>Не удалось загрузить отчёты.</div>}
      {!loading && !error && filtered.length === 0 && (
        <div className="obs-news-empty">
          {portfolioOnly ? "По бумагам портфеля новых отчётов нет." : "Отчётов не найдено."}
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="obs-rep-list">
          {filtered.map((r, i) => {
            const hasDetail = (r.positives && r.positives.length > 0)
              || (r.risks && r.risks.length > 0)
              || r.conclusion;
            const isOpen = !!openCards[i];
            const period = [r.period, r.standard || r.report_type, r.sector].filter(Boolean).join(" · ");
            return (
              <div key={i} className="obs-rep-card">
                {/* Header: ticker · period · importance badge */}
                <div className="obs-rep-card-head">
                  <span className="obs-rep-ticker">{r.ticker}</span>
                  <span className="obs-rep-period">{period}</span>
                  {r.importance === "high"
                    ? <span className="obs-tag-judgment" style={{ marginLeft: "auto" }}>важно</span>
                    : <span className="obs-tag-fact" style={{ marginLeft: "auto" }}>средне</span>
                  }
                </div>

                {/* Metric chips — shown only if structured pct fields present */}
                {(r.revenue_pct || r.ebitda_pct || r.profit_pct) && (
                  <div className="obs-rep-metrics">
                    {r.revenue_pct && (
                      <div className="obs-rep-metric">
                        <span className="rm-lbl">Выручка</span>
                        <span className="rm-val" style={{ color: metricColor(r.revenue_pct) }}>{r.revenue_pct}</span>
                      </div>
                    )}
                    {r.ebitda_pct && (
                      <div className="obs-rep-metric">
                        <span className="rm-lbl">EBITDA</span>
                        <span className="rm-val" style={{ color: metricColor(r.ebitda_pct) }}>{r.ebitda_pct}</span>
                      </div>
                    )}
                    {r.profit_pct && (
                      <div className="obs-rep-metric">
                        <span className="rm-lbl">Чистая прибыль</span>
                        <span className="rm-val" style={{ color: metricColor(r.profit_pct) }}>{r.profit_pct}</span>
                      </div>
                    )}
                  </div>
                )}

                {/* Verdict / one-liner */}
                {(r.one_liner || r.verdict) && (
                  <div className="obs-rep-verdict">{r.one_liner || r.verdict}</div>
                )}

                {/* Expand toggle + collapsible detail */}
                {hasDetail && (
                  <>
                    <button
                      type="button"
                      className="obs-rep-toggle"
                      onClick={() => toggleCard(i)}
                      aria-expanded={isOpen}
                    >
                      {isOpen ? "Свернуть ▴" : "Читать разбор ▾"}
                    </button>
                    <div className={`obs-rep-detail${isOpen ? " open" : ""}`}>
                      {r.positives && r.positives.length > 0 && (
                        <div className="obs-rep-section">
                          <div className="obs-rep-section-title positive">Позитив</div>
                          {r.positives.map((b, j) => (
                            <div key={j} className="obs-rep-bullet positive">{b}</div>
                          ))}
                        </div>
                      )}
                      {r.risks && r.risks.length > 0 && (
                        <div className="obs-rep-section">
                          <div className="obs-rep-section-title risk">Риски</div>
                          {r.risks.map((b, j) => (
                            <div key={j} className="obs-rep-bullet risk">{b}</div>
                          ))}
                        </div>
                      )}
                      {r.conclusion && (
                        <div className="obs-rep-conclusion">
                          <b>Вывод.</b> {r.conclusion}
                        </div>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// =============================================================
// ObsCalendar — «Календарь событий» точно по прототипу observer-sidebar-v2.html
// Два вида: список (timeline) и сетка месяца (7 колонок, навигация,
// клик по дню → детали ниже). Фильтры по типу события.
// Данные: GET /api/market/calendar (поля: id, date, time, type,
// title, ticker, status, payload, source_url).
// =============================================================

const OBS_CAL_TYPE_META = {
  macro:         { label: "Макро",       color: "var(--text-secondary)"       },
  dividend:      { label: "Дивиденды",   color: "var(--success)"              },
  corporate:     { label: "СД · ГОСА",   color: "var(--info)"                 },
  board:         { label: "СД · ГОСА",   color: "var(--info)"                 },
  ipo:           { label: "IPO · SPO",   color: "#8A4FBF"                     }, // data cat colour
  bond_offer:    { label: "Оферта",      color: "var(--warning)"              },
  bond_maturity: { label: "Погашение",   color: "var(--text-tertiary)"        },
  expiration:    { label: "Экспирация",  color: "var(--text-tertiary)"        },
};

const OBS_CAL_FILTERS = [
  { id: "all",       label: "Все"        },
  { id: "dividend",  label: "Дивиденды"  },
  { id: "earnings",  label: "Отчётности" },
  { id: "corporate", label: "СД · ГОСА"  },
  { id: "macro",     label: "Макро"      },
  { id: "ipo",       label: "IPO · SPO"  },
];

const OBS_MONTH_NAMES = [
  "Январь","Февраль","Март","Апрель","Май","Июнь",
  "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь",
];

const OBS_TECH_TYPES = ["bond_offer", "bond_maturity", "expiration"];

function _obsDateRu(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function ObsCalendar({ token, portfolioOnly, onSelectCompany }) {
  const [view, setView] = useState("list");        // "list" | "grid"
  const [typeFilter, setTypeFilter] = useState("all");
  const [gridDate, setGridDate] = useState(() => {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), 1);
  });
  const [selectedDay, setSelectedDay] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    setLoading(true); setError(false);
    const evParam = typeFilter !== "all" ? `&event_type=${typeFilter}` : "";
    fetch(
      `${apiUrl}/api/market/calendar?scope=upcoming&portfolio_only=${portfolioOnly}${evParam}`,
      { headers: authHeaders }
    )
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [typeFilter, portfolioOnly, token]);

  const events = data?.events || [];
  // In "all" mode: split tech events (bond ofers/maturities/expirations) into separate section
  const splitTech = typeFilter === "all";
  const techEvents = splitTech ? events.filter((e) => OBS_TECH_TYPES.includes(e.type)) : [];
  const mainEvents = splitTech ? events.filter((e) => !OBS_TECH_TYPES.includes(e.type)) : events;

  // Build date → events map for grid view
  const byDate = {};
  mainEvents.forEach((e) => {
    if (!byDate[e.date]) byDate[e.date] = [];
    byDate[e.date].push(e);
  });

  const todayIso = new Date().toISOString().slice(0, 10);

  // Resolve type meta (label + color)
  const typeM = (type) => OBS_CAL_TYPE_META[type] || { label: type, color: "var(--text-tertiary)" };

  // ---- Build calendar grid cells ----
  const buildCells = () => {
    const year = gridDate.getFullYear();
    const month = gridDate.getMonth();
    const firstDay = new Date(year, month, 1);
    const startOffset = (firstDay.getDay() + 6) % 7; // Monday = 0
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();
    const cells = [];
    // leading days from prev month
    for (let i = 0; i < startOffset; i++) {
      cells.push({ day: daysInPrevMonth - startOffset + i + 1, current: false });
    }
    // current month days
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      cells.push({ day: d, current: true, iso, events: byDate[iso] || [] });
    }
    // trailing days from next month
    const trailing = (7 - ((startOffset + daysInMonth) % 7)) % 7;
    for (let i = 1; i <= trailing; i++) {
      cells.push({ day: i, current: false });
    }
    return cells;
  };

  const shiftMonth = (delta) => {
    setGridDate((d) => new Date(d.getFullYear(), d.getMonth() + delta, 1));
    setSelectedDay(null);
  };

  const toggleDay = (iso) => setSelectedDay((prev) => (prev === iso ? null : iso));

  // ---- Sub-render: timeline list view ----
  const renderTimeline = () => {
    const sorted = [...mainEvents].sort((a, b) => a.date.localeCompare(b.date));
    if (sorted.length === 0) {
      return (
        <div className="obs-news-empty">
          {portfolioOnly ? "В портфеле событий не найдено." : "Предстоящих событий нет."}
        </div>
      );
    }
    return (
      <div className="obs-cal-card">
        <div className="obs-tl-wrap">
          <div className="obs-tl-line" aria-hidden="true" />
          {sorted.map((e, i) => (
            <div key={e.id || i} className="obs-tl-item">
              <div className="obs-tl-dot" style={{ background: typeM(e.type).color }} />
              <div className="obs-tl-date">
                {_obsDateRu(e.date)}{e.time ? ` · ${e.time} МСК` : ""}
              </div>
              <div className="obs-tl-title">
                {e.ticker && onSelectCompany
                  ? (
                    <button
                      type="button"
                      className="obs-rep-toggle"
                      style={{ fontSize: "14.5px", fontWeight: 600 }}
                      onClick={() => onSelectCompany(e.ticker)}
                    >{e.title}</button>
                  )
                  : e.title
                }
              </div>
              {e.type === "dividend" && e.payload && (
                <div className="obs-tl-sub">
                  {e.payload.buy_by_date && `Купить до ${_obsDateRu(e.payload.buy_by_date)}`}
                  {e.payload.record_date && ` · отсечка ${_obsDateRu(e.payload.record_date)}`}
                  {e.payload.dividend_yield != null && ` · доходность ▲ ${e.payload.dividend_yield}%`}
                </div>
              )}
              {(e.status || (e.payload && e.payload.note)) && e.type !== "dividend" && (
                <div className="obs-tl-sub">
                  {[e.status, e.payload?.note].filter(Boolean).join(" · ")}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ---- Sub-render: month grid view ----
  const renderGrid = () => {
    const year = gridDate.getFullYear();
    const month = gridDate.getMonth();
    const cells = buildCells();
    const selEvents = selectedDay ? (byDate[selectedDay] || []) : [];
    return (
      <div>
        {/* Month navigation */}
        <div className="obs-cal-nav">
          <button
            type="button"
            className="obs-cal-nav-btn"
            onClick={() => shiftMonth(-1)}
            aria-label="Предыдущий месяц"
          >←</button>
          <div className="obs-cal-month-label">{OBS_MONTH_NAMES[month]} {year}</div>
          <button
            type="button"
            className="obs-cal-nav-btn"
            onClick={() => shiftMonth(1)}
            aria-label="Следующий месяц"
          >→</button>
        </div>

        {/* Legend */}
        <div className="obs-cal-legend">
          {[
            { label: "Дивиденды",  color: "var(--success)"  },
            { label: "Отчётности", color: "var(--accent)"   },
            { label: "СД · ГОСА",  color: "var(--info)"     },
            { label: "Макро",      color: "var(--text-secondary)" },
            { label: "IPO · SPO",  color: "#8A4FBF"         },
          ].map((l) => (
            <span key={l.label} className="obs-cal-legend-item">
              <span className="obs-cal-legend-dot" style={{ background: l.color }} />
              <span>{l.label}</span>
            </span>
          ))}
        </div>

        {/* 7-column grid */}
        <div
          className="obs-cal-grid"
          role="grid"
          aria-label={`${OBS_MONTH_NAMES[month]} ${year}`}
        >
          {/* Day-of-week headers */}
          {["Пн","Вт","Ср","Чт","Пт","Сб","Вс"].map((d) => (
            <div key={d} className="obs-cal-weekday" role="columnheader">{d}</div>
          ))}

          {/* Day cells */}
          {cells.map((cell, idx) => {
            if (!cell.current) {
              return (
                <div key={`prev-${idx}`} className="obs-cal-day other-month" role="gridcell" aria-disabled="true">
                  <div className="obs-cal-day-num">{cell.day}</div>
                </div>
              );
            }
            const isToday = cell.iso === todayIso;
            const isSel   = cell.iso === selectedDay;
            const evts    = cell.events || [];
            return (
              <div
                key={cell.iso}
                className={`obs-cal-day${isToday ? " today" : ""}${isSel ? " selected" : ""}`}
                role="gridcell"
                aria-selected={isSel}
                aria-label={`${cell.day} ${OBS_MONTH_NAMES[month]}${evts.length ? `, ${evts.length} событий` : ""}`}
                tabIndex={0}
                onClick={() => toggleDay(cell.iso)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleDay(cell.iso); }
                }}
              >
                <div className="obs-cal-day-num">{cell.day}</div>
                {evts.slice(0, 2).map((ev, j) => (
                  <div
                    key={j}
                    className="obs-cal-pill"
                    style={{ background: typeM(ev.type).color }}
                  >
                    {ev.short || (ev.title && ev.title.length > 18 ? ev.title.slice(0, 16) + "…" : ev.title)}
                  </div>
                ))}
                {evts.length > 2 && (
                  <div className="obs-cal-more">+{evts.length - 2} ещё</div>
                )}
              </div>
            );
          })}
        </div>

        {/* Selected day detail */}
        {selectedDay && (
          <div className="obs-cal-day-detail">
            <div className="obs-cal-detail-title">{_obsDateRu(selectedDay)}</div>
            {selEvents.length === 0
              ? <p style={{ fontSize: "13px", color: "var(--text-tertiary)" }}>На этот день событий нет.</p>
              : selEvents.map((e, i) => (
                <div key={i} className="obs-cal-detail-card">
                  <div
                    className="obs-cal-detail-type"
                    style={{ background: typeM(e.type).color }}
                  >{typeM(e.type).label}</div>
                  <div className="obs-cal-detail-event-title">{e.title}</div>
                  {e.status && <div className="obs-cal-detail-sub">{e.status}</div>}
                  {e.type === "dividend" && e.payload && e.payload.dividend_yield != null && (
                    <div className="obs-cal-detail-sub">
                      Дивидендная доходность: ▲ {e.payload.dividend_yield}%
                    </div>
                  )}
                </div>
              ))
            }
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <p className="obs-cal-desc">
        Предстоящие события: дивиденды, отчётности, собрания СД/ГОСА, макростатистика, IPO/SPO.
        Оферты, погашения и экспирации — вынесены отдельно ниже.
      </p>

      {/* Controls: view toggle + type filter chips */}
      <div className="obs-cal-controls">
        {/* List / Grid segment */}
        <div className="obs-cal-seg" role="group" aria-label="Вид отображения">
          {[{ id: "list", label: "Список" }, { id: "grid", label: "Календарь" }].map((v) => (
            <button
              key={v.id}
              type="button"
              className={`obs-cal-seg-opt${view === v.id ? " obs-cal-seg-opt--on" : ""}`}
              onClick={() => setView(v.id)}
              aria-pressed={view === v.id}
            >{v.label}</button>
          ))}
        </div>

        {/* Type filter */}
        <div className="obs-cal-filterbar" role="group" aria-label="Тип события">
          {OBS_CAL_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`obs-cal-chip${typeFilter === f.id ? " obs-cal-chip--active" : ""}`}
              onClick={() => setTypeFilter(f.id)}
            >{f.label}</button>
          ))}
        </div>
      </div>

      {loading && <div className="obs-news-loading">Загрузка календаря…</div>}
      {error && (
        <div className="obs-news-loading" style={{ color: "var(--danger)" }}>
          Не удалось загрузить календарь.
        </div>
      )}

      {!loading && !error && (view === "list" ? renderTimeline() : renderGrid())}

      {/* Tech events section: bond offers / maturities / expirations */}
      {!loading && !error && techEvents.length > 0 && (
        <div style={{ marginTop: "14px", maxWidth: "960px" }}>
          <Disclosure
            summary={`Технические события — оферты · погашения · экспирации (${techEvents.length})`}
            defaultOpen={false}
          >
            <div className="obs-cal-card" style={{ marginTop: "8px" }}>
              <div className="obs-tl-wrap">
                <div className="obs-tl-line" aria-hidden="true" />
                {[...techEvents]
                  .sort((a, b) => a.date.localeCompare(b.date))
                  .map((e, i) => (
                    <div key={e.id || i} className="obs-tl-item">
                      <div className="obs-tl-dot" style={{ background: typeM(e.type).color }} />
                      <div className="obs-tl-date">{_obsDateRu(e.date)}</div>
                      <div className="obs-tl-title" style={{ fontSize: "13.5px" }}>{e.title}</div>
                      {e.payload && (
                        <div className="obs-tl-sub">
                          {[
                            e.payload.coupon_type === "floater" ? "флоатер"
                              : e.payload.coupon_type === "fixed" ? "фикс. купон"
                              : e.payload.coupon_type || null,
                            e.payload.ytm != null ? `YTM ~${e.payload.ytm}%${e.payload.yield_indicative ? " (индикативно)" : ""}` : null,
                            e.payload.rating || null,
                          ].filter(Boolean).join(" · ")}
                        </div>
                      )}
                    </div>
                  ))
                }
              </div>
            </div>
          </Disclosure>
        </div>
      )}
    </div>
  );
}

// =========================
// OBS ARTICLE CARD — expandable разбор-карточка документа ЦБ/ЦМАКП
// =========================
function ObsArticleCard({ doc }) {
  const [open, setOpen] = useState(false);
  const SOURCE_LABELS = { cmakp: "ЦМАКП", cbr: "Банк России" };
  const srcLabel = SOURCE_LABELS[doc.source] || doc.source || "Источник";
  const dateStr = doc.published_at ? doc.published_at.slice(0, 10) : "";

  return (
    <div className="obs-art-card">
      {/* Шапка: источник · тип документа · дата */}
      <div className="obs-art-head">
        <b>{srcLabel}</b>
        {doc.doc_type && <span>· {doc.doc_type} ·</span>}
        <span className="obs-art-date">{dateStr}</span>
      </div>

      {/* Заголовок */}
      <div className="obs-art-title">{doc.title}</div>

      {/* Выжимка (takeaway) */}
      {doc.summary && <div className="obs-art-takeaway">{doc.summary}</div>}

      {/* Кнопка раскрытия */}
      <button
        className="obs-art-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? "Свернуть ▴" : "Читать разбор целиком ▾"}
      </button>

      {/* Раскрытая секция */}
      {open && (
        <div className="obs-art-full">
          {Array.isArray(doc.key_takeaways) && doc.key_takeaways.length > 0 && (
            <ul>
              {doc.key_takeaways.map((t, i) => <li key={i}>{t}</li>)}
            </ul>
          )}

          {doc.interpretation && (
            <div className="obs-art-callout">
              {/* Молния-иконка (Basis interpretation) */}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
                <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" />
              </svg>
              <p><b>Интерпретация Basis.</b> {doc.interpretation}</p>
            </div>
          )}

          {doc.source_url && (
            <a href={doc.source_url} target="_blank" rel="noreferrer" className="obs-art-link">
              Оригинал ↗
            </a>
          )}
        </div>
      )}
    </div>
  );
}

// =========================
// OBS DIGEST CARD/LIST — переиспользуемая карточка для geo_digest (Геополитика per-регион +
// Институциональная среда «Обзор»). Формат как у ObsArticleCard (ЦБ/ЦМАКП), но источник —
// внешний (Рыбарь/Carnegie/re:russia/Economist/ISW), поэтому есть source_label-бейдж и
// отдельный investor_relevance callout.
// =========================
function ObsDigestCard({ a }) {
  const dateStr = a.published_at ? String(a.published_at).slice(0, 10) : "";
  return (
    <div className="obs-art-card">
      <div className="obs-art-head">
        {a.source_label && <b>{a.source_label}</b>}
        <span className="obs-art-date">{dateStr}</span>
      </div>
      <div className="obs-art-title">{a.title}</div>
      {a.summary && <div className="obs-art-takeaway">{a.summary}</div>}
      {Array.isArray(a.key_takeaways) && a.key_takeaways.length > 0 && (
        <ul style={{ margin: "10px 0 0", paddingLeft: 18 }}>
          {a.key_takeaways.map((t, i) => <li key={i} style={{ fontSize: 13, marginBottom: 4 }}>{t}</li>)}
        </ul>
      )}
      {a.investor_relevance && (
        <div className="obs-art-callout" style={{ marginTop: 12 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
            <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" />
          </svg>
          <p><b>Почему это важно инвестору.</b> {a.investor_relevance}</p>
        </div>
      )}
    </div>
  );
}

function ObsDigestList({ articles, loading, emptyHint }) {
  if (loading) return <div className="obs-news-loading">Загрузка…</div>;
  if (!articles || articles.length === 0) {
    return <div className="obs-art-empty">{emptyHint || "Свежих материалов пока нет."}</div>;
  }
  return (
    <div className="obs-art-list">
      {articles.map((a) => <ObsDigestCard key={a.id} a={a} />)}
    </div>
  );
}

// =========================
// OBS MACRO ARTICLES — Обозреватель · Разбор · Макроэкономика
// Две вкладки: Обзор (article-cards из /macro/analytics) +
//              Оценка ситуации (deep-card из /macro/interpretation).
// =========================
function ObsMacroArticles({ token }) {
  const [mode, setMode] = useState("overview"); // overview | assessment
  const [docs, setDocs] = useState([]);
  const [interp, setInterp] = useState(null);
  const [interpLoading, setInterpLoading] = useState(false);
  const [srcFilter, setSrcFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Загружаем список аналитических записок один раз
  useEffect(() => {
    setLoading(true);
    fetch(`${apiUrl}/api/market/macro/analytics?limit=20`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => { setDocs(d || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [apiUrl]);

  // Загружаем интерпретацию при переключении на «Оценка ситуации»
  useEffect(() => {
    if (mode === "assessment" && interp === null) {
      setInterpLoading(true);
      fetch(`${apiUrl}/api/market/macro/interpretation`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { setInterp(d); setInterpLoading(false); })
        .catch(() => setInterpLoading(false));
    }
  }, [mode, apiUrl, interp]);

  const SOURCE_CHIPS = [
    { id: "all", label: "Все" },
    { id: "cmakp", label: "ЦМАКП" },
    { id: "cbr", label: "Банк России" },
  ];

  const filteredDocs = docs.filter((d) =>
    srcFilter === "all" || d.source === srcFilter
  );

  // Секции интерпретации (порядок из прототипа)
  const INTERP_SECTIONS = [
    { key: "current_picture", label: "Текущая картина" },
    { key: "rate_outlook", label: "Ставка: ближайшее решение и траектория" },
    { key: "cb_forecast_view", label: "Прогноз ЦБ: оценка вероятности" },
    { key: "market_sectors", label: "Рынок и сектора" },
  ];

  const interpSections = interp?.sections || null;
  const scenarios = interpSections?.scenarios;

  return (
    <div>
      <p className="obs-art-desc">
        «Обзор» — записки ЦБ и ЦМАКП как есть. «Оценка ситуации» — что из этого следует, по мнению Basis.
      </p>

      {/* Сег-переключатель */}
      <div className="obs-seg">
        <button
          className={`obs-seg-opt${mode === "overview" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("overview")}
        >
          Обзор
        </button>
        <button
          className={`obs-seg-opt${mode === "assessment" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("assessment")}
        >
          Оценка ситуации
        </button>
      </div>

      {/* ===== ОБЗОР: article-cards ===== */}
      {mode === "overview" && (
        <>
          {/* Фильтр по источнику */}
          <div className="obs-filterbar">
            {SOURCE_CHIPS.map(({ id, label }) => (
              <button
                key={id}
                className={`obs-chip${srcFilter === id ? " obs-chip--active" : ""}`}
                onClick={() => setSrcFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {loading && (
            <div className="obs-news-loading">Загружаем аналитику…</div>
          )}

          {!loading && filteredDocs.length === 0 && (
            <div className="obs-art-empty">
              Нет документов для выбранного источника. Аналитические записки ЦБ и ЦМАКП
              появятся здесь после публикации.
            </div>
          )}

          <div className="obs-art-list">
            {filteredDocs.map((doc) => (
              <ObsArticleCard key={doc.id} doc={doc} />
            ))}
          </div>
        </>
      )}

      {/* ===== ОЦЕНКА СИТУАЦИИ: deep-card + секции интерпретации ===== */}
      {mode === "assessment" && (
        <>
          {interpLoading && (
            <div className="obs-news-loading">Загружаем интерпретацию…</div>
          )}

          {!interpLoading && !interpSections && (
            <div className="obs-deep-card">
              <div className="obs-deep-eyebrow">Оценка ситуации · суждение Basis</div>
              <h3>Интерпретация ещё не сформирована</h3>
              <p>
                Обновите анализ на вкладке «Макроэкономика → Экономическая статистика»,
                нажав кнопку «Обновить анализ» — ИИ-интерпретатор соберёт связную картину
                по всем показателям, аналитике ЦБ/ЦМАКП и прогнозу (~1–2 мин).
              </p>
            </div>
          )}

          {!interpLoading && interpSections && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {interp.generated_at && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  Срез на {new Date(interp.generated_at).toLocaleString("ru-RU")}
                  {interp.model_used ? ` · ${interp.model_used}` : ""}
                  {" · Это оценка Basis, не факт и не рекомендация."}
                </div>
              )}

              {/* Текстовые секции (кроме scenarios) */}
              {INTERP_SECTIONS.map(({ key, label }) =>
                interpSections[key] ? (
                  <div key={key} className="obs-deep-card">
                    <div className="obs-deep-eyebrow">{label} · суждение Basis</div>
                    <h3>{label}</h3>
                    <p style={{ whiteSpace: "pre-line" }}>{interpSections[key]}</p>
                  </div>
                ) : null
              )}

              {/* Сценарии base/bull/bear */}
              {scenarios && (
                <div>
                  <div className="obs-synth-head" style={{ marginBottom: 14 }}>Сценарии</div>
                  <div className="obs-scenario-row">
                    {/* Base */}
                    {scenarios.base && (
                      <div className="obs-scenario-card">
                        <div className="obs-scenario-title">Базовый</div>
                        {scenarios.base.probability && (
                          <div className="obs-scenario-prob">вероятность: {scenarios.base.probability}</div>
                        )}
                        {scenarios.base.key_numbers && (
                          <div className="obs-scenario-num">{scenarios.base.key_numbers}</div>
                        )}
                        {scenarios.base.triggers && (
                          <div className="obs-scenario-trig">
                            <b>Триггеры</b>
                            {scenarios.base.triggers}
                          </div>
                        )}
                      </div>
                    )}
                    {/* Bull */}
                    {scenarios.bull && (
                      <div className="obs-scenario-card obs-scenario-card--bull">
                        <div className="obs-scenario-title">Бычий</div>
                        {scenarios.bull.probability && (
                          <div className="obs-scenario-prob">вероятность: {scenarios.bull.probability}</div>
                        )}
                        {scenarios.bull.key_numbers && (
                          <div className="obs-scenario-num">{scenarios.bull.key_numbers}</div>
                        )}
                        {scenarios.bull.triggers && (
                          <div className="obs-scenario-trig">
                            <b>Триггеры</b>
                            {scenarios.bull.triggers}
                          </div>
                        )}
                      </div>
                    )}
                    {/* Bear */}
                    {scenarios.bear && (
                      <div className="obs-scenario-card obs-scenario-card--bear">
                        <div className="obs-scenario-title">Медвежий</div>
                        {scenarios.bear.probability && (
                          <div className="obs-scenario-prob">вероятность: {scenarios.bear.probability}</div>
                        )}
                        {scenarios.bear.key_numbers && (
                          <div className="obs-scenario-num">{scenarios.bear.key_numbers}</div>
                        )}
                        {scenarios.bear.triggers && (
                          <div className="obs-scenario-trig">
                            <b>Триггеры</b>
                            {scenarios.bear.triggers}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// =========================
// OBS GEOPOLITICS — Обозреватель · Разбор · Геополитика
// Регион-фильтр (чипы) + сег-переключатель Обзор/Оценка ситуации +
// deep-card по прототипу (тёмная карточка с суждением Basis).
// Данные: GET /api/market/geopolitics
// =========================
function ObsGeopolitics({ token, portfolioOnly, onSelectCompany }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [region, setRegion] = useState(null); // null = первый из списка
  const [mode, setMode] = useState("overview"); // overview | assessment
  const [digestByRegion, setDigestByRegion] = useState({});
  const [digestLoading, setDigestLoading] = useState({});
  const [baro, setBaro] = useState(null);
  const [baroLoading, setBaroLoading] = useState(true);
  const [openG, setOpenG] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    fetch(`${apiUrl}/api/market/geo-barometer`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setBaro(d))
      .catch(() => setBaro(null))
      .finally(() => setBaroLoading(false));
  }, [apiUrl]);

  // Лента материалов (Рыбарь/Carnegie/re:russia/Economist/ISW) по региону — грузим лениво,
  // при первом обращении к региону.
  const loadDigest = useCallback((r) => {
    if (!r || digestByRegion[r] !== undefined) return;
    setDigestLoading((s) => ({ ...s, [r]: true }));
    fetch(`${apiUrl}/api/market/geopolitics/${r}/digest`, { headers: authHeaders })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((d) => setDigestByRegion((s) => ({ ...s, [r]: d.articles || [] })))
      .catch(() => setDigestByRegion((s) => ({ ...s, [r]: [] })))
      .finally(() => setDigestLoading((s) => ({ ...s, [r]: false })));
  }, [apiUrl]);

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetch(
      `${apiUrl}/api/market/geopolitics?portfolio_only=${portfolioOnly}`,
      { headers: authHeaders }
    )
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token, apiUrl]);

  // Данные приходят раздельно по вкладкам (overview / deep).
  // Мы объединяем всё в один список регионов.
  const allBlocks = [
    ...(data?.tabs?.overview || []),
    ...(data?.tabs?.deep || []),
  ];

  // Уникальные регионы (ключи) из обоих наборов
  const regionMap = new Map();
  (data?.tabs?.overview || []).forEach((b) => {
    if (!regionMap.has(b.region)) regionMap.set(b.region, { overview: b, deep: null });
    else regionMap.get(b.region).overview = b;
  });
  (data?.tabs?.deep || []).forEach((b) => {
    if (!regionMap.has(b.region)) regionMap.set(b.region, { overview: null, deep: b });
    else regionMap.get(b.region).deep = b;
  });

  const regions = Array.from(regionMap.keys());
  const activeRegion = region || regions[0] || null;
  const regionData = activeRegion ? regionMap.get(activeRegion) : null;

  useEffect(() => {
    if (activeRegion) loadDigest(activeRegion);
  }, [activeRegion, loadDigest]);

  // Блок для текущего режима
  const overviewBlock = regionData?.overview;
  const deepBlock = regionData?.deep;

  // Секторы из active block (объединяем оба источника)
  const affectedSectors = [
    ...new Set([
      ...(overviewBlock?.affected_sectors || []),
      ...(deepBlock?.affected_sectors || []),
    ])
  ];
  const affectedTickers = [
    ...new Set([
      ...(overviewBlock?.affected_tickers || []),
      ...(deepBlock?.affected_tickers || []),
    ])
  ];

  const titleBlock = overviewBlock || deepBlock;

  return (
    <div>
      <p className="obs-art-desc">
        «Обзор» — что произошло (факты). «Оценка ситуации» — прогноз Basis: куда идёт регион
        и что это значит для российского рынка.
      </p>

      {/* Фильтр регионов */}
      {regions.length > 0 && (
        <div className="obs-filterbar">
          {regions.map((r) => {
            const b = regionMap.get(r);
            const lbl = (b.overview?.title || b.deep?.title || r);
            return (
              <button
                key={r}
                className={`obs-chip${activeRegion === r ? " obs-chip--active" : ""}`}
                onClick={() => setRegion(r)}
              >
                {lbl}
              </button>
            );
          })}
        </div>
      )}

      {/* Сег-переключатель */}
      <div className="obs-seg">
        <button
          className={`obs-seg-opt${mode === "overview" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("overview")}
        >
          Обзор
        </button>
        <button
          className={`obs-seg-opt${mode === "assessment" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("assessment")}
        >
          Оценка ситуации
        </button>
      </div>

      {loading && (
        <div className="obs-news-loading">Загрузка геополитики…</div>
      )}
      {error && (
        <div style={{ color: "var(--danger)", fontSize: 13, padding: "24px 0" }}>
          Не удалось загрузить геополитику.
        </div>
      )}

      {!loading && !error && regions.length === 0 && (
        <div className="obs-art-empty">
          {portfolioOnly
            ? "По бумагам портфеля значимых изменений нет."
            : "Нет геополитических данных."}
        </div>
      )}

      {!loading && !error && activeRegion && (
        <>
          {/* ===== ОБЗОР: deep-card с фактами ===== */}
          {mode === "overview" && (
            <div className="obs-deep-card">
              <div className="obs-deep-eyebrow">Обзор · факты</div>
              <h3>{titleBlock?.title || activeRegion}</h3>
              {overviewBlock?.status_text && (
                <p style={{ marginBottom: 18 }}>{overviewBlock.status_text}</p>
              )}
              {(affectedSectors.length > 0 || affectedTickers.length > 0) && (
                <div className="obs-deep-chips">
                  {affectedSectors.map((s, i) => (
                    <span key={"s" + i} className="obs-deep-chip-sector">{s}</span>
                  ))}
                  {affectedTickers.map((t, i) => (
                    <button
                      key={"t" + i}
                      className="obs-deep-chip-ticker"
                      onClick={() => onSelectCompany && onSelectCompany(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ===== ОБЗОР: лента материалов по региону (Рыбарь/Carnegie/re:russia/Economist/ISW) ===== */}
          {mode === "overview" && (
            <div style={{ marginTop: 16 }}>
              <div className="obs-synth-head" style={{ marginBottom: 14 }}>Материалы по региону</div>
              <ObsDigestList
                articles={digestByRegion[activeRegion]}
                loading={digestLoading[activeRegion]}
                emptyHint="Свежих материалов по региону пока нет — источники обновляются раз в час."
              />
            </div>
          )}

          {/* ===== ОЦЕНКА СИТУАЦИИ: единый геополитический барометр (G1-G13, сценарии S1-S4) ===== */}
          {mode === "assessment" && (
            <>
              {baroLoading && <div className="obs-news-loading">Загрузка барометра…</div>}
              {!baroLoading && !baro && (
                <div className="obs-art-empty">Барометр пока недоступен.</div>
              )}
              {!baroLoading && baro && (
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div className="obs-deep-card">
                    <div className="obs-deep-eyebrow">Геополитический барометр · оценка Basis · срез на {baro.as_of}</div>
                    <h3>Итоговый балл: {baro.barometer?.overall} / 5</h3>
                    {baro.barometer?.label && <p style={{ marginBottom: 0 }}>{baro.barometer.label}</p>}
                  </div>

                  {baro.scenario && (
                    <div>
                      <div className="obs-synth-head" style={{ marginBottom: 14 }}>
                        Сценарии (6 мес.) {baro.scenario.confidence ? `· confidence ${baro.scenario.confidence}` : ""}
                      </div>
                      <div className="obs-scenario-row">
                        {Object.entries(baro.scenario.probabilities_6m || {}).map(([name, p]) => (
                          <div key={name} className="obs-scenario-card">
                            <div className="obs-scenario-title">{name}</div>
                            <div className="obs-scenario-prob">вероятность: {Math.round(p * 100)}%</div>
                          </div>
                        ))}
                      </div>
                      {Array.isArray(baro.scenario.triggers) && baro.scenario.triggers.length > 0 && (
                        <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 10 }}>
                          Триггеры пересмотра: {baro.scenario.triggers.join("; ")}
                        </p>
                      )}
                    </div>
                  )}

                  {baro.implied_market && (
                    <div className="obs-deep-card">
                      <div className="obs-deep-eyebrow">Имплайд-рынок · оценка Basis</div>
                      <h3>Расхождение с рынком</h3>
                      <p style={{ marginBottom: 0 }}>{baro.implied_market.divergence || baro.implied_market.market_pricing_lean}</p>
                    </div>
                  )}

                  {Array.isArray(baro.sector_flags) && baro.sector_flags.length > 0 && (
                    <div>
                      <div className="obs-synth-head" style={{ marginBottom: 14 }}>Секторные последствия</div>
                      <div className="obs-deep-chips">
                        {baro.sector_flags.map((s, i) => (
                          <span key={i} className="obs-deep-chip-sector" title={s.reasoning}>
                            {s.sector} · {s.direction}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {Array.isArray(baro.subindices) && baro.subindices.length > 0 && (
                    <div>
                      <div className="obs-synth-head" style={{ marginBottom: 14 }}>Субиндексы (G1–G13)</div>
                      <div className="obs-art-list">
                        {baro.subindices.map((s) => (
                          <div key={s.key} className="obs-art-card">
                            <div className="obs-art-head">
                              <b>{s.key}</b>
                              <span className="obs-art-date">балл {s.score}/5</span>
                            </div>
                            <div className="obs-art-title">{s.label}</div>
                            <button
                              className="obs-art-toggle"
                              onClick={() => setOpenG((k) => (k === s.key ? null : s.key))}
                              aria-expanded={openG === s.key}
                            >
                              {openG === s.key ? "Свернуть ▴" : "Обоснование ▾"}
                            </button>
                            {openG === s.key && (
                              <div className="obs-art-full">
                                <p style={{ whiteSpace: "pre-line" }}>{s.rationale}</p>
                                {s.anchor_note && <p style={{ whiteSpace: "pre-line", color: "var(--text-tertiary)", fontSize: 13 }}>{s.anchor_note}</p>}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {baro.summary && (
                    <div className="obs-deep-card">
                      <div className="obs-deep-eyebrow">Резюме · оценка Basis</div>
                      <p style={{ whiteSpace: "pre-line", marginBottom: 0 }}>{baro.summary}</p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

// =========================
// OBS INSTITUTIONS — Обозреватель · Институциональная среда
// «Обзор» — лента материалов (geo_digest, target=institutions). «Текущая ситуация» —
// институциональный барометр (M1-M13, сценарии, алерты) из /api/market/institutions.
// =========================
function ObsInstitutions({ token }) {
  const [mode, setMode] = useState("overview");
  const [digest, setDigest] = useState(null);
  const [digestLoading, setDigestLoading] = useState(true);
  const [baro, setBaro] = useState(null);
  const [baroLoading, setBaroLoading] = useState(true);
  const [openKey, setOpenKey] = useState(null);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    fetch(`${apiUrl}/api/market/institutions/digest`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setDigest(d.articles || []))
      .catch(() => setDigest([]))
      .finally(() => setDigestLoading(false));
    fetch(`${apiUrl}/api/market/institutions`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setBaro(d))
      .catch(() => setBaro(null))
      .finally(() => setBaroLoading(false));
  }, [apiUrl]);

  const SCENARIO_LABELS = {
    "Инерция": "obs-scenario-card",
    "Замирение": "obs-scenario-card obs-scenario-card--bull",
    "Эскалация": "obs-scenario-card obs-scenario-card--bear",
  };

  return (
    <div>
      <p className="obs-art-desc">
        «Обзор» — материалы по институциональной среде (регулирование, собственность,
        госсектор), пересказ близко к тексту, без указания источников. «Текущая ситуация» —
        институциональный барометр Basis: 13 показателей, сценарии, активные алерты.
      </p>

      <div className="obs-seg">
        <button
          className={`obs-seg-opt${mode === "overview" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("overview")}
        >
          Обзор
        </button>
        <button
          className={`obs-seg-opt${mode === "assessment" ? " obs-seg-opt--on" : ""}`}
          onClick={() => setMode("assessment")}
        >
          Текущая ситуация
        </button>
      </div>

      {mode === "overview" && (
        <ObsDigestList
          articles={digest}
          loading={digestLoading}
          emptyHint="Свежих материалов пока нет — источники обновляются раз в час."
        />
      )}

      {mode === "assessment" && (
        <>
          {baroLoading && <div className="obs-news-loading">Загрузка барометра…</div>}

          {!baroLoading && !baro && (
            <div className="obs-art-empty">Барометр пока недоступен.</div>
          )}

          {!baroLoading && baro && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="obs-deep-card">
                <div className="obs-deep-eyebrow">Барометр · оценка Basis · срез на {baro.as_of}</div>
                <h3>Итоговый балл: {baro.barometer?.overall} / 5</h3>
                {baro.barometer?.label && <p style={{ marginBottom: 0 }}>{baro.barometer.label}</p>}
              </div>

              {baro.scenario && (
                <div>
                  <div className="obs-synth-head" style={{ marginBottom: 14 }}>
                    Сценарий: {baro.scenario.current}
                  </div>
                  <div className="obs-scenario-row">
                    {Object.entries(baro.scenario.probabilities || {}).map(([name, p]) => (
                      <div key={name} className={SCENARIO_LABELS[name] || "obs-scenario-card"}>
                        <div className="obs-scenario-title">{name}</div>
                        <div className="obs-scenario-prob">вероятность: {Math.round(p * 100)}%</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {Array.isArray(baro.alerts) && baro.alerts.length > 0 && (
                <div>
                  <div className="obs-synth-head" style={{ marginBottom: 14 }}>Активные алерты</div>
                  <div className="obs-art-list">
                    {baro.alerts.map((al, i) => (
                      <div key={i} className="obs-art-card">
                        <div className="obs-art-head">
                          {al.type && <b>{al.type}</b>}
                          <span className="obs-art-date">{al.date}</span>
                        </div>
                        <div className="obs-art-title">{al.title}</div>
                        {al.why_it_matters && <div className="obs-art-takeaway">{al.why_it_matters}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {Array.isArray(baro.subindices) && baro.subindices.length > 0 && (
                <div>
                  <div className="obs-synth-head" style={{ marginBottom: 14 }}>Показатели (M1–M13)</div>
                  <div className="obs-art-list">
                    {baro.subindices.map((s) => (
                      <div key={s.key} className="obs-art-card">
                        <div className="obs-art-head">
                          <b>{s.key}</b>
                          <span>· {s.type} ·</span>
                          <span className="obs-art-date">балл {s.score}/5</span>
                        </div>
                        <div className="obs-art-title">{s.label}</div>
                        <button
                          className="obs-art-toggle"
                          onClick={() => setOpenKey((k) => (k === s.key ? null : s.key))}
                          aria-expanded={openKey === s.key}
                        >
                          {openKey === s.key ? "Свернуть ▴" : "Обоснование ▾"}
                        </button>
                        {openKey === s.key && (
                          <div className="obs-art-full">
                            <p style={{ whiteSpace: "pre-line" }}>{s.rationale}</p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {baro.crp_floor_rationale && (
                <div className="obs-deep-card">
                  <div className="obs-deep-eyebrow">Институциональный «пол» CRP · оценка Basis</div>
                  <h3>{baro.institutional_crp_floor_pp} п.п.</h3>
                  <p style={{ whiteSpace: "pre-line", marginBottom: 0 }}>{baro.crp_floor_rationale}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
const _fmtNum = (x) => (x == null ? "—" : Number(x).toLocaleString("ru-RU", { maximumFractionDigits: 2 }));



function ObsLineChart({ series, viewW = 1000, viewH = 240, unit = "%" }) {
  const [hoverIdx, setHoverIdx] = React.useState(null);
  const svgRef = React.useRef(null);
  const padL = 52, padR = 14, padT = 16, padB = 26;
  const plotW = viewW - padL - padR;
  const plotH = viewH - padT - padB;

  // Унифицированная ось дат по всем рядам
  const allDates = [...new Set(series.flatMap(s => s.points.map(p => p.as_of)))].sort();
  const n = allDates.length;

  if (n < 2) {
    return (
      <div style={{ color: "var(--text-tertiary)", fontSize: "12px", padding: "16px 0" }}>
        Недостаточно точек для графика.
      </div>
    );
  }

  // Для каждого ряда выравниваем pts по allDates (последнее известное значение)
  const seriesAligned = series.map(s => {
    const pts = allDates.map(d => {
      let r = null;
      for (const p of s.points) { if (p.as_of <= d && p.value != null) r = p.value; }
      return r;
    });
    return { ...s, pts };
  });

  // Общий min/max
  let vmin = Infinity, vmax = -Infinity;
  seriesAligned.forEach(s => s.pts.forEach(v => { if (v != null) { if (v < vmin) vmin = v; if (v > vmax) vmax = v; } }));
  const rpad = (vmax - vmin) * 0.12 || 1; vmin -= rpad; vmax += rpad;

  const xAt = i => padL + i * (plotW / (n - 1));
  const yAt = v => padT + plotH - ((v - vmin) / (vmax - vmin)) * plotH;

  const fmtDate = iso => { const [y, m] = iso.split("-"); return `${m}.${y.slice(2)}`; };
  const fmtDateFull = iso => { const p = iso.split("-"); return p.length === 3 ? `${p[2]}.${p[1]}.${p[0]}` : iso; };

  const xTickEvery = Math.ceil(n / 6);
  const gridN = 4;

  const onPtrMove = e => {
    const el = svgRef.current; if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const px = (cx - rect.left) / rect.width * viewW;
    let i = Math.round((px - padL) / (plotW / (n - 1)));
    setHoverIdx(Math.max(0, Math.min(n - 1, i)));
  };

  // Полилинии по ряду: разбиваем на непрерывные куски (пропускаем null)
  const buildSegs = pts => {
    const segs = []; let cur = [];
    pts.forEach((v, i) => {
      if (v != null) { cur.push(`${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`); }
      else if (cur.length) { segs.push(cur.join(" ")); cur = []; }
    });
    if (cur.length) segs.push(cur.join(" "));
    return segs;
  };

  const hx = hoverIdx != null ? xAt(hoverIdx) : 0;
  const tipPct = hoverIdx != null ? (hx / viewW) * 100 : 0;
  const tipRight = tipPct > 55;

  return (
    <div style={{ position: "relative" }}>
      {hoverIdx != null && (
        <div className="obs-chart-tooltip" style={{
          left: tipRight ? undefined : `${tipPct}%`,
          right: tipRight ? `${100 - tipPct}%` : undefined,
          top: "8px",
        }}>
          <div style={{ fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)", fontSize: "11px", color: "var(--text-tertiary)", marginBottom: "6px" }}>
            {fmtDateFull(allDates[hoverIdx])}
          </div>
          {seriesAligned.map((s, k) => {
            const v = s.pts[hoverIdx];
            return (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12.5px", marginTop: "3px" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: s.color, display: "inline-block", flexShrink: 0 }} />
                <span style={{ color: "var(--text-secondary)" }}>{s.name}</span>
                <b style={{ marginLeft: "auto", fontFamily: "var(--font-mono, monospace)", fontVariantNumeric: "tabular-nums" }}>
                  {v == null ? "—" : v.toFixed(2)}{unit}
                </b>
              </div>
            );
          })}
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${viewW} ${viewH}`}
        style={{ width: "100%", height: "auto", cursor: "crosshair", display: "block", touchAction: "none" }}
        onPointerMove={onPtrMove}
        onPointerLeave={() => setHoverIdx(null)}
        role="img"
        aria-label="График макроэкономического показателя"
      >
        {/* Горизонтальные линии сетки: 5 уровней, первая сплошная, остальные dasharray 2,6 */}
        {Array.from({ length: gridN + 1 }, (_, g) => {
          const v = vmin + (vmax - vmin) * g / gridN;
          const y = yAt(v);
          return (
            <g key={g}>
              <line x1={padL} y1={y} x2={viewW - padR} y2={y}
                stroke="var(--border-subtle)" strokeWidth="1"
                strokeDasharray={g === 0 ? undefined : "2,6"} />
              <text x={padL - 8} y={y + 4} textAnchor="end"
                fontFamily="IBM Plex Mono, monospace" fontSize="10.5"
                fill="var(--text-tertiary)">
                {v.toFixed(1)}{unit}
              </text>
            </g>
          );
        })}
        {/* X-метки дат */}
        {allDates.map((d, i) => i % xTickEvery !== 0 ? null : (
          <text key={i} x={xAt(i)} y={viewH - 8} textAnchor="middle"
            fontFamily="IBM Plex Mono, monospace" fontSize="10"
            fill="var(--text-tertiary)">
            {fmtDate(d)}
          </text>
        ))}
        {/* Ряды — polyline stroke-width 2.5 */}
        {seriesAligned.map((s, si) =>
          buildSegs(s.pts).map((pts, pi) => (
            <polyline key={`${si}-${pi}`} points={pts}
              fill="none" stroke={s.color} strokeWidth="2.5"
              strokeLinejoin="round" strokeLinecap="round" />
          ))
        )}
        {/* Hover: вертикальная направляющая */}
        {hoverIdx != null && (
          <line x1={hx} y1={padT} x2={hx} y2={viewH - padB}
            stroke="var(--text-tertiary)" strokeWidth="1" strokeDasharray="3,3" />
        )}
        {/* Hover: точки на рядах */}
        {hoverIdx != null && seriesAligned.map((s, k) => {
          const v = s.pts[hoverIdx]; if (v == null) return null;
          return <circle key={k} cx={hx} cy={yAt(v)} r="4.5"
            fill={s.color} stroke="var(--bg-elevated)" strokeWidth="2" />;
        })}
      </svg>
    </div>
  );
}

// =========================
// PRICE HISTORY CHART — общий для акций/облигаций/фьючерсов/фондов
// =========================
// Один компонент, разные источники: fetchUrl уже включает asset-специфичный
// путь (/companies/by-ticker/{t}/quotes/history для акций,
// /market/instruments/{class}/{secid}/history для облигаций/фьючерсов/фондов —
// оба отдают {last, change_pct, points:[{date, close|settle}]}, см. backend).
// Рисует через уже готовый ObsLineChart (тот же тултип/сетка, что в
// Обозревателе). unit — «₽» акции/фонды, «%» облигации (цена = % номинала).
const OBS_MAP_GAMMA = 0.6;
const OBS_MAP_STOPS = [
  [-1.0, [ 35,  10,  14]], // самое сильное падение дня — почти чёрный бордовый
  [-0.75,[ 96,  22,  25]], // глубокий бордовый
  [-0.5, [156,  40,  33]], // насыщенный красный
  [-0.25,[196,  76,  44]],
  [-0.08,[221, 117,  55]],
  [ 0,   [231, 145,  56]], // нейтраль — тёплая медь (как было)
  [ 0.08,[192, 154,  60]],
  [ 0.25,[138, 156,  68]],
  [ 0.5, [ 78, 145,  76]],
  [ 0.75,[ 46, 124,  73]],
  [ 1.0, [ 20,  88,  58]], // самый сильный рост дня — глубокий изумрудный
];
function _obsMapPctColor(pct, refMax) {
  if (pct == null) return "rgb(140,130,120)";
  const domain = refMax > 0 ? refMax : 2.5;
  const tRaw = Math.max(-1, Math.min(1, pct / domain));
  const t = Math.sign(tRaw) * Math.pow(Math.abs(tRaw), OBS_MAP_GAMMA);
  for (let i = 0; i < OBS_MAP_STOPS.length - 1; i++) {
    const [p1, c1] = OBS_MAP_STOPS[i];
    const [p2, c2] = OBS_MAP_STOPS[i + 1];
    if (t >= p1 && t <= p2) {
      const f = p2 === p1 ? 0 : (t - p1) / (p2 - p1);
      const rgb = c1.map((c, j) => Math.round(c + (c2[j] - c) * f));
      return `rgb(${rgb.join(",")})`;
    }
  }
  return "rgb(231,145,56)";
}
// Домен шкалы — реальный максимум |изменения| СРЕДИ ТЕКУЩЕЙ выборки плиток
// (весь рынок или сектор при drill-down): «распределение, которое сейчас на
// карте», буквально. Пол 4%, чтобы на очень спокойном рынке шум в ±0.3% не
// красился на полную. Никакого клампа сверху — самый сильный мувер дня ВСЕГДА
// получает самый тёмный тон, каким бы большим он ни был.
function _obsMapDomain(values) {
  const abs = (values || [])
    .filter((v) => v != null && isFinite(v))
    .map((v) => Math.abs(v));
  if (!abs.length) return 4;
  return Math.max(4, ...abs);
}
// Градиент легенды из тех же стопов и той же гамма-кривой, что красят плитки —
// не может разъехаться с реальной раскраской карты.
function _obsMapGradientCss() {
  const N = 40;
  const stopsCss = [];
  for (let i = 0; i <= N; i++) {
    const tRaw = (i / N) * 2 - 1; // -1..1 равномерно по позиции легенды
    const t = Math.sign(tRaw) * Math.pow(Math.abs(tRaw), OBS_MAP_GAMMA);
    let rgb = OBS_MAP_STOPS[OBS_MAP_STOPS.length - 1][1];
    for (let k = 0; k < OBS_MAP_STOPS.length - 1; k++) {
      const [p1, c1] = OBS_MAP_STOPS[k];
      const [p2, c2] = OBS_MAP_STOPS[k + 1];
      if (t >= p1 && t <= p2) {
        const f = p2 === p1 ? 0 : (t - p1) / (p2 - p1);
        rgb = c1.map((c, j) => Math.round(c + (c2[j] - c) * f));
        break;
      }
    }
    stopsCss.push(`rgb(${rgb.join(",")}) ${((i / N) * 100).toFixed(1)}%`);
  }
  return `linear-gradient(90deg,${stopsCss.join(",")})`;
}

// Squarified treemap — прямой порт из прототипа (observer-sidebar-v2.html).
// Мутирует items: добавляет {x, y, w, h} к каждому элементу.
function _obsSquarify(items, x, y, w, h) {
  if (!items.length) return items;
  if (items.length === 1) {
    items[0].x = x; items[0].y = y; items[0].w = w; items[0].h = h;
    return items;
  }
  const total = items.reduce((s, i) => s + i.weight, 0);
  const scale = (w * h) / total;

  function worstRatio(row, length) {
    const sum = row.reduce((s, i) => s + i.weight * scale, 0);
    let mx = -Infinity, mn = Infinity;
    row.forEach(i => { const a = i.weight * scale; if (a > mx) mx = a; if (a < mn) mn = a; });
    return Math.max((length * length * mx) / (sum * sum), (sum * sum) / (length * length * mn));
  }

  function layoutRow(row, cx, cy, cw, ch) {
    const rowArea = row.reduce((s, i) => s + i.weight * scale, 0);
    if (cw < ch) {
      const rowH = rowArea / cw; let px = cx;
      row.forEach(item => {
        const iw = (item.weight * scale) / rowH;
        item.x = px; item.y = cy; item.w = iw; item.h = rowH; px += iw;
      });
    } else {
      const rowW = rowArea / ch; let py = cy;
      row.forEach(item => {
        const ih = (item.weight * scale) / rowW;
        item.x = cx; item.y = py; item.w = rowW; item.h = ih; py += ih;
      });
    }
  }

  let row = [], rest = items.slice();
  let cx = x, cy = y, cw = w, ch = h;
  while (rest.length) {
    const length = cw < ch ? cw : ch;
    const testRow = row.concat([rest[0]]);
    if (!row.length || worstRatio(testRow, length) <= worstRatio(row, length)) {
      row = testRow; rest = rest.slice(1);
    } else {
      layoutRow(row, cx, cy, cw, ch);
      const rowArea = row.reduce((s, i) => s + i.weight * scale, 0);
      if (cw < ch) { cy += rowArea / cw; ch -= rowArea / cw; }
      else { cx += rowArea / ch; cw -= rowArea / ch; }
      row = [];
    }
  }
  if (row.length) layoutRow(row, cx, cy, cw, ch);
  return items;
}

// Подтягивает верхние границы «соседних по факту» рядов секторов — убирает
// пиксельную погрешность squarify между соседними секторами.
function _obsSnapSectorRows(items) {
  const THRESHOLD = 14;
  const sorted = items.slice().sort((a, b) => a.y - b.y);
  const groups = [];
  sorted.forEach(item => {
    let group = groups.find(g => Math.abs(g[0].y - item.y) < THRESHOLD);
    if (!group) { group = []; groups.push(group); }
    group.push(item);
  });
  groups.forEach(group => {
    const minY = Math.min(...group.map(i => i.y));
    group.forEach(item => { item.h = (item.y + item.h) - minY; item.y = minY; });
  });
}

// =========================
// OBS MARKET MAP — visible-tile budget
// =========================
// Реальные числа: облигации — 2804 плитки на карте, один сектор «Корпораты —
// прочие» держит 965 из них; фьючерсы — 459. Акции (~260 на всю карту) —
// рабочий эталон плотности, не трогаем (бюджет практически бесконечный).
// Тайлы внутри сектора уже отсортированы backend'ом по весу по убыванию
// (market_maps._pack_sectors) — slice(0, cap) = честный топ по обороту/капе,
// не случайный срез.
const OBS_MAP_BUDGET = {
  bonds:   { total: 200, min: 4, max: 28 },
  futures: { total: 140, min: 4, max: 24 },
  funds:   { total: 999, min: 9999, max: 9999 },
  stocks:  { total: 999, min: 9999, max: 9999 },
};

// Потолок плиток НА СЕКТОР — пропорционально его доле в общем весе карты,
// зажат в [min,max]. sec.market_cap — сумма веса сектора (та же величина,
// что уже определяет площадь коробки сектора на карте).
// Доля считается от СЖАТОГО веса (степень 0.3, тот же приём, что _mcW у
// отдельных тайлов) — у облигаций ОФЗ реально держат ~87% дневного оборота
// всего рынка; на линейной доле это забирало весь бюджет себе (28 из 200 по
// max-клампу, остаток НИКОМУ не доставался — остальные 25 секторов упирались
// в голый min=4, реальный total рендерился ~127 из целевых 200). Компрессия
// возвращает бюджет крупным-по-числу-бумаг, но не самым оборотистым секторам
// («Корпораты — прочие» 965 бумаг: 4 → 15 плиток), сохраняя порядок значимости.
function _obsCapSectorTiles(activeSectors, budget) {
  const compW = (mc) => Math.pow(Math.max(mc || 1, 1), 0.3);
  const totalWeight = activeSectors.reduce((s, sec) => s + compW(sec.market_cap), 0);
  return activeSectors.map(sec => {
    const share = totalWeight > 0 ? compW(sec.market_cap) / totalWeight : 0;
    const cap = Math.min(budget.max, Math.max(budget.min, Math.round(share * budget.total)));
    const truncated = sec.tiles.length > cap;
    return {
      ...sec,
      visibleTiles: truncated ? sec.tiles.slice(0, cap) : sec.tiles,
      totalCount: sec.tiles.length,
      truncated,
    };
  });
}

// =========================
// OBS MARKET MAP component
// =========================
function ObsMarketMap({ token, portfolioOnly, onSelectCompany, onOpenBond, onOpenFuture, onOpenFund, onOpenSpot }) {
  const [assetClass, setAssetClass] = useState("stocks");   // stocks | bonds | futures | funds | currency
  const [mapType, setMapType]       = useState("heatmap"); // heatmap | valuation (только для stocks)
  const [period, setPeriod]         = useState("day");     // day | week | month (только для stocks)
  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState(false);
  const [drillSector, setDrillSector] = useState(null);
  // Секторы, для которых пользователь явно попросил «показать все N» в drill-
  // down (обходит DRILL_CAP ниже) — сбрасывается вместе с drillSector.
  const [expandedSectors, setExpandedSectors] = useState(() => new Set());
  const apiUrl      = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  // У фьючерсов/фондов/валюты нет ни «недооценённости» (нет справедливой цены —
  // дериватив/упаковка), ни истории week/month через этот путь — только дневная тепловая карта.
  const hasMapTypeToggle = assetClass === "stocks";
  const hasPeriodToggle  = assetClass === "stocks";

  useEffect(() => {
    setLoading(true); setError(false); setDrillSector(null); setExpandedSectors(new Set());
    let url;
    if (assetClass === "stocks") {
      url = mapType === "heatmap"
        ? `${apiUrl}/api/market/maps/heatmap?period=${period}&portfolio_only=${portfolioOnly}`
        : `${apiUrl}/api/market/maps/valuation?portfolio_only=${portfolioOnly}`;
    } else if (assetClass === "bonds") {
      url = `${apiUrl}/api/market/maps/heatmap/bonds`;
    } else if (assetClass === "futures") {
      url = `${apiUrl}/api/market/maps/heatmap/futures`;
    } else if (assetClass === "funds") {
      url = `${apiUrl}/api/market/maps/heatmap/funds`;
    } else if (assetClass === "currency") {
      url = `${apiUrl}/api/market/maps/spot`;
    } else {
      setLoading(false);
      return;
    }
    fetch(url, { headers: authHeaders })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [assetClass, mapType, period, portfolioOnly, token]);

  const allSectors = data?.sectors || [];
  const spotItems  = data?.items || [];
  const isEmpty    = !loading && !error &&
    (assetClass === "currency" ? spotItems.length === 0 : allSectors.length === 0);

  // Домен цветовой шкалы — считаем ОДИН раз на уровне компонента (не внутри
  // renderTreemap), чтобы плитки и легенда-градиент ниже смотрели на одно и
  // то же число. Пересчитывается при смене drill-down сектора — «распределение
  // на карте прямо сейчас» включает именно то, что видно (весь рынок или один
  // сектор при разборе).
  const activeSectors = drillSector
    ? allSectors.filter(s => s.sector === drillSector)
    : allSectors;
  const mapMetric = mapType === "valuation" ? "upside_pct" : "change_pct";
  const mapDomain = _obsMapDomain(
    activeSectors.flatMap(s => s.tiles.map(t => (t[mapMetric] != null ? t[mapMetric] : t.change_pct)))
  );
  const spotDomain = _obsMapDomain(spotItems.map(it => it.change_pct));

  // --- Build SVG treemap ---
  const renderTreemap = () => {
    if (!activeSectors.length) return null;

    const W     = 1160;
    const HEAD  = 26;
    const GAP   = 3;
    const metric = mapMetric;

    // Бюджет видимых плиток (см. OBS_MAP_BUDGET выше) — у обзора ограничивает
    // КАЖДЫЙ сектор пропорционально его весу, у drill-down один общий потолок
    // на единственный видимый сектор (обходится явным «показать все N»).
    const DRILL_CAP = 220;
    const budget = OBS_MAP_BUDGET[assetClass] || OBS_MAP_BUDGET.stocks;
    const cappedSectors = drillSector
      ? activeSectors.map(sec => {
          const expanded  = expandedSectors.has(sec.sector);
          const truncated = !expanded && sec.tiles.length > DRILL_CAP;
          return {
            ...sec,
            visibleTiles: truncated ? sec.tiles.slice(0, DRILL_CAP) : sec.tiles,
            totalCount: sec.tiles.length,
            truncated,
          };
        })
      : _obsCapSectorTiles(activeSectors, budget);

    // Высота карты — от РЕАЛЬНО отрисованного числа плиток (капнутые + по
    // одной «+N ещё»-ячейке на урезанный сектор), не от полного размера
    // вселенной: иначе сокращаем число плиток, но не отдаём им ту площадь,
    // ради которой сокращали. Целевая площадь на плитку — у акций/фондов
    // (эталон плотности, не трогаем) ~850px² (~29×29); у облигаций/фьючерсов
    // (после бюджета плиток всё равно местами вылезал текст на вытянутых
    // squarify-прямоугольниках) — почти вдвое просторнее, ~1600px² (~40×40),
    // «квадраты покрупнее» по прямой просьбе владельца поверх уже точного
    // (не переполняющего плитку) fitLabel ниже.
    const TILE_AREA = (assetClass === "bonds" || assetClass === "futures") ? 1600 : 850;
    const renderedTiles = cappedSectors.reduce(
      (sum, s) => sum + s.visibleTiles.length + (s.truncated ? 1 : 0), 0
    );
    const totalH = Math.max(drillSector ? 480 : 900, Math.ceil(renderedTiles * TILE_AREA / 1160));

    // Sector items: вес = сумма СЖАТЫХ капитализаций (степень 0.3 вместо корня 0.5 —
    // на РЕАЛЬНОЙ капе Роснефть/Сбер в разы больше средних, sqrt сжимал недостаточно и
    // гиганты «раздували» карту; pow 0.3 выравнивает плитки как в прототипе, сохраняя порядок капы)
    const _mcW = (mc) => Math.pow(Math.max(mc || 1, 1), 0.15);
    // Вес коробки сектора — от ПОЛНОГО набора бумаг (s.tiles = все, до
    // среза): площадь честно отражает долю рынка/оборота, даже когда внутри
    // отрисован только топ-N. Но у некоторых секторов реальный вес почти
    // нулевой относительно остальных (напр. «Процентные» у фьючерсов —
    // большинство контрактов на ставку не имеют открытых позиций вообще) —
    // на строго пропорциональном squarify это давало коробку настолько
    // маленькую, что заголовок и тайлы внутри неё наезжали друг на друга
    // («в карту не влазят»). Пол в 15% от «среднего» сектора не даёт коробке
    // схлопнуться, при этом почти не искажает раскладку у нормальных секторов
    // (их реальный вес и так намного выше пола).
    const rawSectorW = s => s.tiles.reduce((sum, t) => sum + _mcW(t.market_cap), 0);
    const rawWeights = cappedSectors.map(rawSectorW);
    const equalShare = (rawWeights.reduce((a, b) => a + b, 0) || 1) / (cappedSectors.length || 1);
    const MIN_SECTOR_SHARE = 0.15;
    const sectorItems = cappedSectors.map((s, i) => ({
      key:    s.sector,
      weight:     Math.max(rawWeights[i], equalShare * MIN_SECTOR_SHARE),
      tiles:      s.visibleTiles,
      totalCount: s.totalCount,
      truncated:  s.truncated,
    }));
    _obsSquarify(sectorItems, 0, 0, W, totalH);
    if (!drillSector) _obsSnapSectorRows(sectorItems);

    const svgElements = [];
    sectorItems.forEach(sec => {
      const innerY = sec.y + HEAD;
      const innerH = Math.max(sec.h - HEAD, 10);

      // Ticker items для вложенного treemap
      const tickerItems = sec.tiles.map(t => ({
        key:    t.ticker,
        weight: _mcW(t.market_cap),
        ticker: t.ticker,
        name:   t.name,
        pct:    t[metric] != null ? t[metric] : t["change_pct"],
      }));
      // Синтетическая плитка «+N ещё» — участвует в том же squarify, что и
      // обычные тайлы (получает пропорциональную площадь автоматически),
      // клик разворачивает сектор (обзор → drill-down того же сектора;
      // drill-down → «показать все N» через expandedSectors).
      const hiddenCount = sec.totalCount - sec.tiles.length;
      if (sec.truncated && hiddenCount > 0) {
        const avgWeight = tickerItems.length
          ? tickerItems.reduce((s, t) => s + t.weight, 0) / tickerItems.length
          : 1;
        tickerItems.push({ key: `__more_${sec.key}`, weight: avgWeight, isMore: true, hiddenCount });
      }
      _obsSquarify(
        tickerItems,
        sec.x + GAP,
        innerY + GAP,
        Math.max(sec.w - GAP * 2, 1),
        Math.max(innerH - GAP * 2, 1)
      );

      // Сектор-заголовок (тёмная полоса) — клик для drill-down в overview.
      // Честный счётчик при частичном показе («28 из 965», не просто «28»)
      // + «›» намекает на кликабельность (drill-down доступен только в обзоре).
      svgElements.push(
        <g key={`sh-${sec.key}`}
           style={{ cursor: drillSector ? "default" : "pointer" }}
           role={drillSector ? undefined : "button"}
           aria-label={drillSector ? undefined : `Детальный вид — ${sec.key}`}
           tabIndex={drillSector ? -1 : 0}
           onClick={() => !drillSector && setDrillSector(sec.key)}
           onKeyDown={e => e.key === "Enter" && !drillSector && setDrillSector(sec.key)}>
          <rect x={sec.x + GAP} y={sec.y + GAP} width={Math.max(sec.w - GAP * 2, 1)} height={Math.max(HEAD - GAP, 1)} fill="#1B1C26" rx="2" />
          <text
            x={sec.x + GAP + 8} y={sec.y + GAP + 15}
            fontFamily="Inter, system-ui, sans-serif"
            fontSize="11.5" fontWeight="700" fill="#EDEBE3"
            style={{ textTransform: "uppercase", letterSpacing: "0.03em", userSelect: "none", pointerEvents: "none" }}>
            {sec.key} · {sec.truncated ? `${sec.tiles.length} из ${sec.totalCount}` : sec.totalCount}{!drillSector ? "  ›" : ""}
          </text>
        </g>
      );

      // Тикер-плитки
      tickerItems.forEach(it => {
        // Синтетическая «+N ещё» — та же squarify-геометрия (it.x/y/w/h), свой
        // рендер: пунктирная медная рамка + счётчик, клик разворачивает.
        if (it.isMore) {
          const tileW = Math.max(it.w - 1, 1), tileH = Math.max(it.h - 1, 1);
          const compact = it.w < 46 || it.h < 30;
          const onExpand = () => drillSector
            ? setExpandedSectors(prev => new Set(prev).add(sec.key))
            : setDrillSector(sec.key);
          svgElements.push(
            <g key={it.key}
               style={{ cursor: "pointer" }}
               role="button" tabIndex={0}
               aria-label={`Показать ещё ${it.hiddenCount} бумаг сектора ${sec.key}`}
               onClick={onExpand}
               onKeyDown={e => e.key === "Enter" && onExpand()}>
              <title>{`Показать ещё ${it.hiddenCount}`}</title>
              <rect x={it.x} y={it.y} width={tileW} height={tileH}
                    fill="#1B1C26" stroke="var(--accent)" strokeWidth="1" strokeDasharray="3,2" rx="1" />
              <text x={it.x + it.w / 2} y={it.y + it.h / 2 + (compact ? 4 : -4)}
                    textAnchor="middle" fontFamily="var(--font-mono)"
                    fontSize={compact ? 11 : 15} fontWeight="700" fill="var(--accent)"
                    style={{ pointerEvents: "none", userSelect: "none" }}>
                +{it.hiddenCount}
              </text>
              {!compact && (
                <text x={it.x + it.w / 2} y={it.y + it.h / 2 + 12}
                      textAnchor="middle" fontFamily="Inter, system-ui, sans-serif"
                      fontSize="9.5" fontWeight="600" fill="#EDEBE3"
                      style={{ textTransform: "uppercase", letterSpacing: "0.02em", pointerEvents: "none", userSelect: "none" }}>
                  показать ещё
                </text>
              )}
            </g>
          );
          return;
        }

        const v       = it.pct;
        const tileW   = Math.max(it.w - 1, 1);
        const tileH   = Math.max(it.h - 1, 1);
        const fontBig = it.w > 60 && it.h > 42;
        const lblFontSize = fontBig ? 14 : 10;
        const valFontSize = fontBig ? 11 : 8.5;
        const sign    = v == null ? "" : v >= 0 ? "+" : "−";
        const glyph   = v == null ? "" : v > 0 ? "▲ " : v < 0 ? "▼ " : "";  // aria-label only

        // Клик по плитке открывает карточку своего класса актива — для акций
        // компанию, для остальных классов их собственную карточку (BondCard/
        // FuturesCard/FundCard), тем же паттерном, что уже работал для акций.
        const openHandler = assetClass === "stocks" ? onSelectCompany
          : assetClass === "bonds" ? onOpenBond
          : assetClass === "futures" ? onOpenFuture
          : assetClass === "funds" ? onOpenFund
          : null;
        const clickable = !!openHandler;
        // Подпись плитки: у акций тикер уже читаемый (SBER); у облигаций/
        // фьючерсов/фондов тикер — это SECID/ISIN (напр. RU000A106JZ9),
        // нечитаемый — показываем короткое название бумаги, если оно есть.
        const rawLabel = assetClass === "stocks" ? it.ticker : (it.name || it.ticker);
        // Раньше подпись обрезалась по ФИКСИРОВАННОМУ числу символов (14)
        // независимо от реальной ширины плитки — на узких плитках (даже
        // формально «больших» по squarify-эвристике width×height, но
        // вытянутых) текст вылезал за границы прямоугольника. Теперь ширина
        // подписи меряется от РЕАЛЬНОЙ ширины плитки (грубая эвристика
        // ширины символа Inter/Mono Bold ≈ 0.62×fontSize — с запасом, лучше
        // недо-, чем пере-заполнить). Значение (%) не обрезаем — усечённое
        // число вводит в заблуждение («12…» похоже на 12, а это может быть
        // 120%), просто прячем целиком, если не влезает.
        const CHAR_W = 0.62;
        const fitLabel = (txt, fontSize) => {
          if (!txt) return "";
          const maxChars = Math.floor((it.w - 6) / (fontSize * CHAR_W));
          if (maxChars <= 1) return "";
          return txt.length <= maxChars ? txt : txt.slice(0, maxChars - 1) + "…";
        };
        const label = fitLabel(rawLabel, lblFontSize);
        const valStr = v == null ? "—" : `${sign}${Math.abs(v).toFixed(1)}%`;
        const valFits = it.h > 14 && (it.w - 6) >= valStr.length * valFontSize * CHAR_W;
        const hasLbl = label.length > 0 && it.h > 16;
        const hasVal = valFits;
        svgElements.push(
          <g key={it.key}
             style={{ cursor: clickable ? "pointer" : "default" }}
             role={clickable ? "button" : undefined}
             aria-label={`${it.ticker}${it.name ? " — " + it.name : ""}${v != null ? ", " + glyph + sign + v.toFixed(1) + "%" : ""}`}
             tabIndex={clickable && drillSector ? 0 : -1}
             onClick={() => clickable && openHandler(it.ticker)}
             onKeyDown={e => clickable && e.key === "Enter" && openHandler(it.ticker)}>
            {/* Нативный browser-тултип — на КАЖДОЙ плитке независимо от размера
                (раньше подсказка при наведении была только для скринридеров
                через aria-label; на маленьких плитках без подписи мышиный
                пользователь не видел вообще ничего). */}
            <title>{`${it.ticker}${it.name ? " — " + it.name : ""}${v != null ? ", " + glyph + sign + v.toFixed(1) + "%" : ", нет данных об изменении"}`}</title>
            <rect
              x={it.x} y={it.y} width={tileW} height={tileH}
              fill={_obsMapPctColor(v, mapDomain)}
              stroke="rgba(255,255,255,0.3)" strokeWidth="0.75"
              rx="1" />
            {hasLbl && hasVal && (
              <>
                <text
                  x={it.x + it.w / 2} y={it.y + it.h / 2 - (fontBig ? 5 : 0)}
                  textAnchor="middle"
                  fontFamily="Inter, system-ui, sans-serif"
                  fontSize={fontBig ? 14 : 10} fontWeight="700" fill="#fff"
                  style={{ pointerEvents: "none", userSelect: "none" }}>
                  {label}
                </text>
                <text
                  x={it.x + it.w / 2} y={it.y + it.h / 2 + (fontBig ? 17 : 11)}
                  textAnchor="middle"
                  fontFamily="'JetBrains Mono', 'IBM Plex Mono', monospace"
                  fontSize={fontBig ? 11 : 8.5} fill="rgba(255,255,255,0.88)"
                  style={{ pointerEvents: "none", userSelect: "none" }}>
                  {valStr}
                </text>
              </>
            )}
            {hasLbl && !hasVal && (
              <text
                x={it.x + it.w / 2} y={it.y + it.h / 2 + 3}
                textAnchor="middle"
                fontFamily="Inter, system-ui, sans-serif"
                fontSize="10" fontWeight="700" fill="#fff"
                style={{ pointerEvents: "none", userSelect: "none" }}>
                {label}
              </text>
            )}
            {!hasLbl && hasVal && (
              <text
                x={it.x + it.w / 2} y={it.y + it.h / 2 + 3}
                textAnchor="middle"
                fontFamily="'JetBrains Mono', 'IBM Plex Mono', monospace"
                fontSize="9" fontWeight="600" fill="rgba(255,255,255,0.92)"
                style={{ pointerEvents: "none", userSelect: "none" }}>
                {valStr}
              </text>
            )}
          </g>
        );
      });
    });

    return (
      <svg
        viewBox={`0 0 ${W} ${totalH}`}
        style={{ width: "100%", height: "auto", display: "block", borderRadius: "8px", overflow: "hidden" }}
        role="img"
        aria-label={drillSector ? `Карта рынка — сектор ${drillSector}` : "Карта рынка — все секторы"}>
        {svgElements}
      </svg>
    );
  };

  // Валюта/металлы — те же squarify/цвет/тайл-визуал, что и остальные классы
  // (визуальная согласованность — «карта», а не только список карточек ниже).
  // Веса синтетические: нет естественной «капитализации» у курса пары/грамма
  // металла — сектор по числу инструментов, тайл внутри сектора поровну
  // (честно, не выдумываем размер значимости конкретной валюты/металла).
  const renderSpotTreemap = () => {
    if (!spotItems.length) return null;
    const W = 1160, HEAD = 26, GAP = 3, totalH = 240;
    const byKind = {};
    spotItems.forEach((it) => { (byKind[it.kind] || (byKind[it.kind] = [])).push(it); });
    const sectorItems = Object.entries(byKind).map(([kind, items]) => ({ key: kind, weight: items.length, tiles: items }));
    _obsSquarify(sectorItems, 0, 0, W, totalH);
    _obsSnapSectorRows(sectorItems);

    const svgElements = [];
    sectorItems.forEach((sec) => {
      const innerY = sec.y + HEAD;
      const innerH = Math.max(sec.h - HEAD, 10);
      const tickerItems = sec.tiles.map((it) => ({ key: it.ticker, weight: 1, ticker: it.ticker, name: it.name, pct: it.change_pct, price: it.last_price }));
      _obsSquarify(tickerItems, sec.x + GAP, innerY + GAP, Math.max(sec.w - GAP * 2, 1), Math.max(innerH - GAP * 2, 1));

      svgElements.push(
        <g key={`sh-${sec.key}`}>
          <rect x={sec.x + GAP} y={sec.y + GAP} width={Math.max(sec.w - GAP * 2, 1)} height={Math.max(HEAD - GAP, 1)} fill="#1B1C26" rx="2" />
          <text x={sec.x + GAP + 8} y={sec.y + GAP + 15} fontFamily="Inter, system-ui, sans-serif" fontSize="11.5" fontWeight="700" fill="#EDEBE3"
            style={{ textTransform: "uppercase", letterSpacing: "0.03em", userSelect: "none", pointerEvents: "none" }}>
            {sec.key} · {sec.tiles.length}
          </text>
        </g>
      );

      tickerItems.forEach((it) => {
        const v = it.pct;
        const tileW = Math.max(it.w - 1, 1), tileH = Math.max(it.h - 1, 1);
        const hasLbl = it.w > 60 && it.h > 30;
        const sign = v == null ? "" : v >= 0 ? "+" : "−";
        svgElements.push(
          <g key={it.key}
             style={{ cursor: onOpenSpot ? "pointer" : "default" }}
             role={onOpenSpot ? "button" : undefined}
             aria-label={`${it.name}${it.price != null ? ", " + it.price.toLocaleString("ru-RU") + " ₽" : ""}${v != null ? ", " + sign + Math.abs(v).toFixed(2) + "%" : ""}`}
             tabIndex={onOpenSpot ? 0 : -1}
             onClick={() => onOpenSpot && onOpenSpot(it.ticker)}
             onKeyDown={(e) => onOpenSpot && e.key === "Enter" && onOpenSpot(it.ticker)}>
            <rect x={it.x} y={it.y} width={tileW} height={tileH} fill={_obsMapPctColor(v, spotDomain)} stroke="rgba(255,255,255,0.3)" strokeWidth="0.75" rx="1" />
            {hasLbl && (
              <>
                <text x={it.x + it.w / 2} y={it.y + it.h / 2 - 12} textAnchor="middle" fontFamily="Inter, system-ui, sans-serif" fontSize="13" fontWeight="700" fill="#fff"
                  style={{ pointerEvents: "none", userSelect: "none" }}>{it.name}</text>
                <text x={it.x + it.w / 2} y={it.y + it.h / 2 + 7} textAnchor="middle" fontFamily="'JetBrains Mono','IBM Plex Mono',monospace" fontSize="12.5" fill="#fff"
                  style={{ pointerEvents: "none", userSelect: "none" }}>
                  {it.price != null ? it.price.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) + " ₽" : "—"}
                </text>
                <text x={it.x + it.w / 2} y={it.y + it.h / 2 + 23} textAnchor="middle" fontFamily="'JetBrains Mono','IBM Plex Mono',monospace" fontSize="10.5" fill="rgba(255,255,255,0.8)"
                  style={{ pointerEvents: "none", userSelect: "none" }}>
                  {v == null ? "—" : `${sign}${Math.abs(v).toFixed(2)}%`}
                </text>
              </>
            )}
          </g>
        );
      });
    });

    return (
      <svg viewBox={`0 0 ${W} ${totalH}`}
        style={{ width: "100%", height: "auto", display: "block", borderRadius: "8px", overflow: "hidden", marginBottom: "18px" }}
        role="img" aria-label="Карта валют и металлов">
        {svgElements}
      </svg>
    );
  };

  const PERIODS = [
    { id: "day",   label: "Сутки" },
    { id: "week",  label: "Неделя" },
    { id: "month", label: "Месяц" },
  ];

  // Секторные чипы для фильтрации (из данных)
  const sectorKeys = allSectors.map(s => s.sector);

  return (
    <div className="obs-map-wrap">
      <p className="obs-map-desc">
        Все бумаги сразу на одной карте — размер плитки отражает капитализацию, цвет — движение цены.
        Клик по сектору сужает карту до него.
      </p>

      {/* ── assetToggle: Акции / Облигации / Фьючерсы / Фонды / Валюта ── */}
      <div className="obs-asset-toggle" role="group" aria-label="Класс активов">
        {[
          { id: "stocks",   label: "Акции" },
          { id: "bonds",    label: "Облигации" },
          { id: "futures",  label: "Фьючерсы" },
          { id: "funds",    label: "Фонды" },
          { id: "currency", label: "Валюта/металлы" },
        ].map(ac => (
          <button
            key={ac.id}
            type="button"
            className={`obs-cal-seg-opt${assetClass === ac.id ? " obs-cal-seg-opt--on" : ""}`}
            onClick={() => { setAssetClass(ac.id); setDrillSector(null); setExpandedSectors(new Set()); }}
            aria-pressed={assetClass === ac.id}
          >
            {ac.label}
          </button>
        ))}
      </div>

      {/* Контент: реальные карты по всем классам */}
      {assetClass === "currency" ? (
        <>
          {loading && <div className="obs-news-loading">Загрузка…</div>}
          {error   && <div className="obs-news-loading" style={{ color: "var(--danger)" }}>Не удалось загрузить данные. Попробуйте позже.</div>}
          {isEmpty && <div className="obs-news-empty">Нет данных для отображения.</div>}
          {/* Только карта — раньше карта + список карточек ниже дублировали
              друг друга (тайлы уже показывают имя/цену/% при достаточном
              размере, а тут всего 6 инструментов — тайлы крупные). */}
          {!loading && !error && !isEmpty && renderSpotTreemap()}
        </>
      ) : (
        <>
          {/* ── mapToggle + periodToggle + gradient legend в одной строке (только акции) ── */}
          <div className="obs-map-controls">
            {hasMapTypeToggle && (
              <div className="obs-cal-seg" id="mapToggle">
                <button
                  type="button"
                  className={`obs-cal-seg-opt${mapType === "heatmap" ? " obs-cal-seg-opt--on" : ""}`}
                  onClick={() => { setMapType("heatmap"); setDrillSector(null); setExpandedSectors(new Set()); }}
                  aria-pressed={mapType === "heatmap"}>
                  Тепловая
                </button>
                <button
                  type="button"
                  className={`obs-cal-seg-opt${mapType === "valuation" ? " obs-cal-seg-opt--on" : ""}`}
                  onClick={() => { setMapType("valuation"); setDrillSector(null); setExpandedSectors(new Set()); }}
                  aria-pressed={mapType === "valuation"}>
                  Недооценённость
                </button>
              </div>
            )}
            {hasPeriodToggle && (
              <div className="obs-cal-seg" id="periodToggle">
                {PERIODS.map(p => (
                  <button key={p.id} type="button"
                    className={`obs-cal-seg-opt${period === p.id ? " obs-cal-seg-opt--on" : ""}`}
                    onClick={() => setPeriod(p.id)}
                    aria-pressed={period === p.id}>
                    {p.label}
                  </button>
                ))}
              </div>
            )}
            {/* Градиент-легенда — адаптивная: концы шкалы = ±реальный максимум
                |изменения| ТЕКУЩЕЙ выборки (весь рынок или один сектор при
                drill-down), не фикс ±2%. Клампа нет — самый сильный мувер дня
                ВСЕГДА совпадает с самым тёмным концом легенды (см. _obsMapDomain). */}
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span className="obs-map-legend-mono"
                style={{ color: "rgb(35,10,14)", fontSize: "11px", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}
                aria-label={`минус ${mapDomain.toFixed(1)} процента и сильнее`}>
                −{mapDomain.toFixed(1)}%
              </span>
              <div aria-hidden="true"
                style={{ width: "150px", height: "9px", borderRadius: "5px",
                  background: _obsMapGradientCss() }} />
              <span className="obs-map-legend-mono"
                style={{ color: "rgb(16,72,50)", fontSize: "11px", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}
                aria-label={`плюс ${mapDomain.toFixed(1)} процента и сильнее`}>
                +{mapDomain.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* ── sectorChips: Все + секторы из данных ── */}
          {!loading && !error && sectorKeys.length > 0 && (
            <div className="obs-sector-filterbar" role="group" aria-label="Фильтр по сектору">
              <button
                type="button"
                className={`obs-chip${drillSector === null ? " obs-chip--active" : ""}`}
                onClick={() => { setDrillSector(null); setExpandedSectors(new Set()); }}
                aria-pressed={drillSector === null}>
                Все
              </button>
              {sectorKeys.map(k => (
                <button
                  key={k}
                  type="button"
                  className={`obs-chip${drillSector === k ? " obs-chip--active" : ""}`}
                  onClick={() => { setDrillSector(drillSector === k ? null : k); setExpandedSectors(new Set()); }}
                  aria-pressed={drillSector === k}>
                  {k}
                </button>
              ))}
            </div>
          )}

          {/* Хлебная крошка drill-down (дополнительно к чипам) */}
          {drillSector && (
            <button className="obs-map-breadcrumb"
              onClick={() => { setDrillSector(null); setExpandedSectors(new Set()); }}
              aria-label="Вернуться к обзору всего рынка">
              ‹ Весь рынок · <b>{drillSector}</b>
            </button>
          )}

          {/* Состояния загрузки / ошибки / пустоты */}
          {loading && <div className="obs-news-loading">Загрузка карты…</div>}
          {error   && <div className="obs-news-loading" style={{ color: "var(--danger)" }}>Не удалось загрузить карту. Попробуйте позже.</div>}
          {isEmpty && <div className="obs-news-empty">{portfolioOnly ? "В вашем портфеле нет бумаг для этой карты." : "Нет данных для отображения."}</div>}

          {/* SVG treemap */}
          {!loading && !error && !isEmpty && renderTreemap()}

          {/* Дисклеймер для режима оценки (только акции) */}
          {assetClass === "stocks" && mapType === "valuation" && !loading && !error && (
            <div className="obs-map-valuation-note">
              <b>Модельная оценка, не сигнал на покупку.</b> Потенциал к модельной справедливой цене Basis (считается
              живьём от текущей цены). Методика и оговорки — в карточке компании.
            </div>
          )}
          {/* Дисклеймер по весу плитки для фьючерсов/фондов (вес не капитализация) */}
          {assetClass === "futures" && !loading && !error && !isEmpty && (
            <div className="obs-map-valuation-note">
              Размер плитки — условная стоимость открытых позиций (ГО×плечо), не капитализация: у фьючерсов её не бывает.
            </div>
          )}
          {assetClass === "funds" && !loading && !error && !isEmpty && (
            <div className="obs-map-valuation-note">
              Размер плитки — дневной торговый оборот (ликвидность), не СЧА фонда: она не публикуется по каждой бумаге на бирже.
            </div>
          )}
          {assetClass === "bonds" && !loading && !error && !isEmpty && (
            <div className="obs-map-valuation-note">
              Размер плитки — дневной торговый оборот. Показаны только бумаги с реальными данными
              за последние 30 дней{data?.total_universe ? ` — ${data.count} из ${data.total_universe} выпусков (${data.coverage_pct}%)` : ""}:
              российский рынок корпоративных облигаций неоднородно ликвиден, многие выпуски торгуются
              не каждый день — это не пробел загрузки, а свойство рынка. Покрытие растёт со временем
              по мере накопления истории торгов.
            </div>
          )}
        </>
      )}
    </div>
  );
}

// =========================
// OBS AI REVIEW — constants
// =========================
const _OBS_TOPIC_META = {
  biz:          { icon: Briefcase, label: "Бизнес" },
  macro:        { icon: Landmark,  label: "Макроэкономика" },
  geo:          { icon: Globe,     label: "Геополитика" },
  institutions: { icon: Scale,     label: "Институты" },
  mixed:        { icon: Layers,    label: "Смешанный" },
};

const _OBS_DEPTH_META = {
  express:  { label: "Экспресс",  horizon: "±2 дня",   time: "~минута" },
  detailed: { label: "Подробный", horizon: "±7 дней",  time: "3–5 мин" },
  deep:     { label: "Глубокий",  horizon: "±30 дней", time: "полное чтение" },
};

// =========================
// OBS AI REVIEW — epistemic badges + sectioned report body
// Легенда факт/оценка/суждение переиспользует цветовую пару
// obs-inst-tag--est/--judg (см. секцию OBS-INSTITUTIONS в observer-v2.css).
// Разбивка по H2 — тот же приём, что splitH2 в InstitutionsTab.jsx
// (независимая копия: файлы платформы самодостаточны по конвенции).
// =========================

const OBS_EPI_LABEL   = { fact: "Факт", est: "Оценка", judg: "Суждение" };
const OBS_EPI_TAG_CLS = { fact: "obs-ai-tag--fact", est: "obs-ai-tag--est", judg: "obs-ai-tag--judg" };
const ObsEpiTag = ({ variant, title }) => (
  <span className={`obs-ai-tag ${OBS_EPI_TAG_CLS[variant] || OBS_EPI_TAG_CLS.est}`} title={title}>
    {OBS_EPI_LABEL[variant] || "Оценка"}
  </span>
);

// Заголовок иногда несёт эпистемическую оговорку в скобках в конце
// ("Карта рынка (модельная оценка, не сигнал)") — вытаскиваем в бейдж вместо
// серого текста внутри жирного h2. Скобки без эпистемической лексики (даты,
// «нейтральный обзор по каналам» и т.п.) остаются как обычный текст —
// намеренно консервативно, чтобы не заляпать бейджами то, что бейджем не является.
const HEADING_PAREN_RE = /\s*\(([^)]{3,60})\)\s*$/;
function classifyEpi(inner) {
  if (/\bфакт/i.test(inner)) return "fact";
  if (/суждени/i.test(inner)) return "judg";
  if (/оценк|модел/i.test(inner)) return "est";
  return null;
}
function splitHeadingEpi(raw) {
  const text = String(raw || "").trim();
  const m = text.match(HEADING_PAREN_RE);
  if (!m) return { main: text, badge: null };
  const variant = classifyEpi(m[1]);
  if (!variant) return { main: text, badge: null };
  return { main: text.slice(0, m.index).trim(), badge: { variant, full: m[1] } };
}
function ObsSectionHeadingContent({ text, showChevron }) {
  const { main, badge } = splitHeadingEpi(text);
  return (
    <>
      <span className="obs-ai-section-heading-txt">{main}</span>
      {badge && <ObsEpiTag variant={badge.variant} title={badge.full} />}
      {showChevron && <ChevronDown size={14} className="obs-ai-section-chev" aria-hidden="true" />}
    </>
  );
}

// h2 c эпистемическим бейджем — локальная надстройка над ANALYST_MD только для
// ИИ-обзора. ANALYST_MD шарится с карточками облигаций/компаний — не трогаем его,
// чтобы не задеть те страницы.
const OBS_MD = {
  ...ANALYST_MD,
  h2: ({ children }) => (
    <h2 className="obs-ai-section-heading">
      <ObsSectionHeadingContent text={mdText(children)} />
    </h2>
  ),
};

// Разбивка отчёта по H2 (как InstitutionsTab.splitH2). "---"-разделители,
// которыми модель разделяет секции в исходном markdown, обрезаем — границу
// секции теперь рисует сама шапка (border-top), второй разделитель избыточен.
function stripTrailingHr(body) {
  const lines = body.replace(/\s+$/, "").split("\n");
  while (lines.length && /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(lines[lines.length - 1])) {
    lines.pop();
    while (lines.length && lines[lines.length - 1].trim() === "") lines.pop();
  }
  return lines.join("\n");
}
function splitObsSections(md) {
  const src = String(md || "");
  const cut = src.search(/\n(?=##\s+)/);
  const lead = cut === -1 ? src : src.slice(0, cut);
  const rest = cut === -1 ? "" : src.slice(cut + 1);
  const parts = rest ? rest.split(/\n(?=##\s+)/).filter((s) => /^##\s+/.test(s)) : [];
  return {
    lead,
    sections: parts.map((s) => {
      const m = s.match(/^##\s+(.+)/);
      return { heading: (m ? m[1] : "").trim(), body: stripTrailingHr(s.replace(/^##\s+.+\n?/, "")) };
    }),
  };
}

// Секции-«хвосты» (полный список календаря и т.п.) — свёрнуты по умолчанию,
// остальное открыто: отчёт читают за один проход, сворачивание — опция для
// уже прочитанного, не дефолт-барьер на пути к контенту.
const OBS_SECTION_AUX_RE = /календар|полный\s*список/i;
// Порог, ниже которого секционирование не даёт выгоды (короткий Экспресс) —
// откалибровано по «Глубокому» образцу; свериться на реальных Экспресс/
// Подробный прогонах после раскатки и подправить при необходимости.
const OBS_SECTION_THRESHOLD = 4;

function ObsReportBody({ content }) {
  const { lead, sections } = useMemo(() => splitObsSections(content), [content]);
  if (sections.length < OBS_SECTION_THRESHOLD) {
    return (
      <div className="obs-ai-report-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={OBS_MD}>{content || ""}</ReactMarkdown>
      </div>
    );
  }
  return (
    <div className="obs-ai-report-body">
      {lead.trim() && <ReactMarkdown remarkPlugins={[remarkGfm]} components={OBS_MD}>{lead}</ReactMarkdown>}
      {sections.map((s, i) => {
        if (i === 0) {
          return (
            <div className="obs-ai-section obs-ai-section--lead" key={i}>
              <h2 className="obs-ai-section-heading"><ObsSectionHeadingContent text={s.heading} /></h2>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={OBS_MD}>{s.body}</ReactMarkdown>
            </div>
          );
        }
        const aux = OBS_SECTION_AUX_RE.test(s.heading);
        return (
          <details className="obs-ai-section" key={i} open={!aux}>
            <summary className="obs-ai-section-heading">
              <ObsSectionHeadingContent text={s.heading} showChevron />
            </summary>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={OBS_MD}>{s.body}</ReactMarkdown>
          </details>
        );
      })}
    </div>
  );
}

// ---- Источники: группировка по kind (было — плоский список) ----
const OBS_SRC_KIND_META = {
  news:     { label: "Новости",     icon: Newspaper },
  macro:    { label: "Макро",       icon: Landmark },
  earnings: { label: "Отчёты",      icon: FileText },
  geo:      { label: "Геополитика", icon: Globe },
  calendar: { label: "События",     icon: Calendar },
};
const OBS_SRC_KIND_ORDER = ["news", "macro", "earnings", "geo", "calendar"];
function groupSourceRefs(refs) {
  const by = {};
  (refs || []).forEach((r) => { (by[r.kind] || (by[r.kind] = [])).push(r); });
  const keys = [
    ...OBS_SRC_KIND_ORDER.filter((k) => by[k]?.length),
    ...Object.keys(by).filter((k) => !OBS_SRC_KIND_ORDER.includes(k)),
  ];
  return keys.map((kind) => ({ kind, items: by[kind], meta: OBS_SRC_KIND_META[kind] || { label: kind, icon: FileText } }));
}

function ObsAiReview({ token, onSelectCompany }) {
  // Дефолт "Смешанный" (не "Макро") — иначе первый экран нового пользователя,
  // если он просто жмёт «Сгенерировать» не трогая переключатели, даёт отчёт
  // слепой к гео/институтам/карте рынка — плохое первое впечатление.
  const [topic, setTopic]           = useState("mixed");
  const [depth, setDepth]           = useState("express");
  const [report, setReport]         = useState(null);
  const [history, setHistory]       = useState([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError]           = useState(null);
  const [collapsed, setCollapsed]   = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [histFilter, setHistFilter]   = useState("all");
  const apiUrl      = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  const loadHistory = () => {
    if (!token) return;
    fetch(`${apiUrl}/api/observer/reports`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : []).then(setHistory).catch(() => setHistory([]));
  };
  useEffect(loadHistory, [token]);

  const generate = () => {
    setGenerating(true); setError(null); setReport(null);
    fetch(`${apiUrl}/api/observer/reports?type=${depth}&topic=${topic}`, {
      method: "POST", headers: authHeaders,
    })
      .then(r => r.json().then(d => ({ ok: r.ok, d })))
      .then(({ ok, d }) => {
        if (ok) { setReport(d); loadHistory(); }
        else setError(d.detail || "Ошибка генерации");
      })
      .catch(e => setError(e.message || "Сетевая ошибка"))
      .finally(() => setGenerating(false));
  };

  const openReport = (id) => {
    fetch(`${apiUrl}/api/observer/reports/${id}`, { headers: authHeaders })
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        setReport(d);
        if (d.report_type) setDepth(d.report_type);
        if (d.topic)       setTopic(d.topic);
        setShowHistory(false);
        setCollapsed(false);
      })
      .catch(() => {});
  };

  if (!token) {
    return (
      <div className="obs-news-empty">
        Войдите, чтобы генерировать персональные сводные отчёты по вашему портфелю.
      </div>
    );
  }

  const curDepthMeta = _OBS_DEPTH_META[depth]  || { label: depth };
  const curTopicMeta = _OBS_TOPIC_META[topic]  || { icon: Layers, label: topic };

  /* ─────────────── HISTORY VIEW ─────────────── */
  if (showHistory) {
    const HIST_FILTERS = [
      ["all", "Все"], ["biz", "Бизнес"], ["macro", "Макроэкономика"],
      ["geo", "Геополитика"], ["institutions", "Институты"], ["mixed", "Смешанный"],
    ];
    const filtered = histFilter === "all"
      ? history
      : history.filter(h => h.topic === histFilter);

    return (
      <div className="obs-ai-wrap">
        {/* Sec-head */}
        <div className="obs-sec-head">
          <div style={{ display: "flex", alignItems: "baseline", gap: "13px" }}>
            <span className="obs-sec-eyebrow">Разбор</span>
            <h2 className="obs-sec-title">История отчётов</h2>
          </div>
          <button className="obs-ai-hist-back" onClick={() => setShowHistory(false)}>
            ← Назад к обзору и анализу
          </button>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "13px", maxWidth: "760px",
                    marginBottom: "20px", marginTop: "-14px" }}>
          Все сгенерированные отчёты. Клик по карточке открывает содержание отчёта.
        </p>

        {/* Filter chips */}
        <div className="obs-ai-hist-filters">
          {HIST_FILTERS.map(([id, label]) => (
            <button key={id}
              className={`obs-ai-hist-filter-chip${histFilter === id ? " obs-ai-hist-filter-chip--on" : ""}`}
              onClick={() => setHistFilter(id)}
              aria-pressed={histFilter === id}>
              {label}
            </button>
          ))}
        </div>

        {/* Report list */}
        <div className="obs-ai-hist-list" style={{ maxWidth: "920px" }}>
          {filtered.length === 0 ? (
            <div className="obs-news-empty">Нет отчётов по выбранному фильтру.</div>
          ) : filtered.map(h => {
            const dm = _OBS_DEPTH_META[h.report_type] || { label: h.report_type };
            const tm = _OBS_TOPIC_META[h.topic || "mixed"] || { icon: Layers, label: h.topic || "—" };
            return (
              <button key={h.id} className="obs-ai-hist-card" onClick={() => openReport(h.id)}>
                <div className="obs-ai-hist-icon" aria-hidden="true"><tm.icon size={17} /></div>
                <div className="obs-ai-hist-body">
                  <div className="obs-ai-hist-title">Обзор — {tm.label}</div>
                  <div className="obs-ai-hist-time">
                    {h.generated_at ? h.generated_at.slice(0, 16).replace("T", " ") : ""}
                  </div>
                </div>
                <span className="obs-ai-hist-depth" aria-label={`Глубина: ${dm.label}`}>{dm.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  /* ─────────────── MAIN (GENERATE) VIEW ─────────────── */
  return (
    <div className="obs-ai-wrap">
      {/* ---- Sec-head with "История" link right-aligned ---- */}
      <div className="obs-sec-head" style={{ justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "13px" }}>
          <span className="obs-sec-eyebrow">Разбор</span>
          <h2 className="obs-sec-title">ИИ-обзор и анализ</h2>
        </div>
        <button className="obs-ai-hist-link" onClick={() => setShowHistory(true)}>
          <Clock size={14} aria-hidden="true" /> История отчётов →
        </button>
      </div>

      <p className="obs-map-desc" style={{ marginTop: "-14px" }}>
        Настройте глубину и тему — от короткой сводки по портфелю до макроэкономического разбора со
        сценариями. Строго по данным платформы, без рекомендаций. Не является ИИР.
      </p>

      {/* ── Single flex row: [Глубина] [Тема] [Кнопка → right] ── */}
      <div className="obs-ai-controls-row">

        {/* Глубина */}
        <div>
          <div className="obs-ai-section-label">Глубина</div>
          <div className="obs-ai-plan-grid" role="group" aria-label="Глубина анализа">
            {Object.entries(_OBS_DEPTH_META).map(([id, m]) => (
              <button key={id}
                className={`obs-ai-plan${depth === id ? " obs-ai-plan--on" : ""}`}
                onClick={() => setDepth(id)}
                aria-pressed={depth === id}>
                <span className="obs-ai-plan-label">{m.label}</span>
                <span className="obs-ai-plan-horizon">{m.horizon}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Тема */}
        <div>
          <div className="obs-ai-section-label">Тема</div>
          <div className="obs-ai-topic-seg" role="group" aria-label="Тема анализа">
            {Object.entries(_OBS_TOPIC_META).map(([id, m]) => (
              <button key={id}
                className={`obs-cal-seg-opt${topic === id ? " obs-cal-seg-opt--on" : ""}`}
                onClick={() => setTopic(id)}
                aria-pressed={topic === id}>
                <m.icon size={14} aria-hidden="true" />
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* Кнопка — прижата вправо через margin-left:auto */}
        <div style={{ marginLeft: "auto" }}>
          {/* Invisible spacer so the button bottom-aligns with the plan cards */}
          <div style={{ fontSize: "11px", marginBottom: "8px", visibility: "hidden" }} aria-hidden="true">·</div>
          <button className="obs-ai-generate-btn" onClick={generate} disabled={generating}
            aria-busy={generating}>
            {generating ? "Генерируем отчёт…" : (<><Sparkles size={15} aria-hidden="true" /> Сгенерировать отчёт</>)}
          </button>
        </div>

      </div>

      <div className="obs-ai-epi-legend">
        <span className="obs-ai-tag obs-ai-tag--fact">факт</span>
        <span className="obs-ai-tag obs-ai-tag--est">оценка</span>
        <span className="obs-ai-tag obs-ai-tag--judg">суждение</span>
        <span className="obs-ai-epi-legend-text">
          — уровни достоверности в тексте отчёта. Итоговые выводы Basis — оценка и суждение,
          не рекомендация «купить/продать». Не является ИИР.
        </span>
      </div>
      {error && (
        <div className="obs-news-loading" style={{ color: "var(--danger)", paddingTop: 0 }}>{error}</div>
      )}

      {/* ---- Текущий отчёт ---- */}
      {report && (
        <div className="obs-ai-report-card">
          <div className="obs-ai-report-head">
            <div className="obs-ai-report-title">
              {(_OBS_DEPTH_META[report.report_type] || {}).label || report.report_type}
              {" · "}
              {(_OBS_TOPIC_META[report.topic] || curTopicMeta).label}
            </div>
            <div className="obs-ai-report-meta">
              <span>{report.generated_at ? report.generated_at.slice(0, 16).replace("T", " ") : ""}</span>
              <button className="obs-ai-collapse-btn"
                onClick={() => setCollapsed(v => !v)}
                aria-expanded={!collapsed}>
                {collapsed ? "Развернуть ▾" : "Свернуть ▴"}
              </button>
            </div>
          </div>
          {!collapsed && (
            <>
              <ObsReportBody content={report.content} />
              {(report.source_refs || []).length > 0 && (
                <div className="obs-ai-sources">
                  <div className="obs-ai-sources-label">Источники · {report.source_refs.length}</div>
                  {groupSourceRefs(report.source_refs).map(({ kind, meta, items }) => (
                    <div key={kind} className="obs-ai-source-group">
                      <div className="obs-ai-source-group-head">
                        <meta.icon size={13} aria-hidden="true" />
                        {meta.label}
                        <span className="obs-ai-source-group-count">{items.length}</span>
                      </div>
                      {items.map((r, i) => (
                        <div key={i} className="obs-ai-source-row">
                          <span className="obs-ai-source-ref">[{r.ref}]</span>
                          {r.ticker
                            ? <button className="obs-ai-source-link"
                                onClick={() => onSelectCompany && onSelectCompany(r.ticker)}>
                                {r.title || r.ticker}
                              </button>
                            : r.url
                              ? <a href={r.url} target="_blank" rel="noreferrer" className="obs-ai-source-link">{r.title}</a>
                              : <span className="obs-ai-source-plain">{r.title}</span>}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              <p style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "12px", marginBottom: 0 }}>
                Синтез по данным платформы. Без рекомендаций.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ObsMarketPulse — «Обзор рынка» (2026-07-11, по просьбе владельца после разбора
// конкурентов Инвестминт/ПроФинанс): бегущая лента + лидеры дня (перенесены из
// раздела «Рынок» → вкладка Акции → карта, там были доступны только после
// скролла вниз) + индексы/секторы/ставки/нефть/металлы + индекс страха-жадности
// Basis. Данные — /api/market/pulse (индексы+секторы+ставки+нефть+металлы+
// индекс страха-жадности) + /api/screener/scored + /api/quotes/realtime (лента
// и лидеры — тот же паттерн слияния live-дельты, что был в MarketNeo.jsx).
// ─────────────────────────────────────────────────────────────────────────────
function ObsSparkline({ points, color = "var(--accent)", w = 96, h = 28 }) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points), max = Math.max(...points);
  const span = (max - min) || 1;
  const step = w / (points.length - 1);
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - ((p - min) / span) * h).toFixed(1)}`).join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" style={{ display: "block" }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function ObsPulseCard({ item }) {
  if (!item) return null;
  const chg = item.change_pct;
  const dCls = chg == null ? "obs-d-neutral" : chg > 0 ? "obs-d-good" : chg < 0 ? "obs-d-bad" : "obs-d-neutral";
  const color = chg == null ? "var(--text-tertiary)" : chg > 0 ? "var(--success)" : chg < 0 ? "var(--danger)" : "var(--text-tertiary)";
  const lvl = item.level;
  const dec = item.unit === "%" || item.unit === "₽/г" ? 2 : (lvl != null && lvl > 1000 ? 0 : 2);
  return (
    <div className="obs-tile" style={{ cursor: "default" }}>
      <div className="obs-tile-lbl">{item.name}</div>
      <div className="obs-tile-val">{lvl != null ? lvl.toLocaleString("ru-RU", { maximumFractionDigits: dec }) : "—"}{item.unit ? (item.unit === "%" ? "%" : " " + item.unit) : ""}</div>
      {chg != null && <div className={"obs-tile-delta " + dCls}>{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {Math.abs(chg).toFixed(2)}%</div>}
      {item.spark && item.spark.length > 1 && <div style={{ marginTop: 8 }}><ObsSparkline points={item.spark} color={color} /></div>}
      {item.note && <div className="obs-tile-date">{item.note}</div>}
    </div>
  );
}

const OBS_FG_COMP_LABELS = {
  momentum: "Импульс рынка (IMOEX к MA125)",
  volatility: "Волатильность (RVI)",
  breadth: "Ширина рынка (доля бумаг в плюсе за 20 дн.)",
  risk_appetite: "Спрос на риск (акции vs гособлигации, 20 дн.)",
};

function ObsFearGreedCard({ fg }) {
  if (!fg || fg.score == null) {
    return (
      <div className="obs-hero-rate">
        <div className="obs-hero-label">Индекс страха и жадности Basis</div>
        <div className="obs-hero-meta">{fg?.note || "Недостаточно данных для расчёта."}</div>
      </div>
    );
  }
  const score = fg.score;
  const color = score < 20 ? "var(--danger)"
    : score < 40 ? "color-mix(in srgb, var(--danger) 55%, var(--text-tertiary))"
    : score < 60 ? "var(--text-tertiary)"
    : score < 80 ? "color-mix(in srgb, var(--success) 55%, var(--text-tertiary))"
    : "var(--success)";
  return (
    <div className="obs-hero-rate">
      <div className="obs-hero-topline">
        <div>
          <div className="obs-hero-label">Индекс страха и жадности Basis</div>
          <div className="obs-hero-num" style={{ color }}>{Math.round(score)}</div>
          <div className="obs-hero-meta">{fg.label} · охват {fg.coverage}</div>
        </div>
        <div className="obs-hero-note">
          {fg.methodology_note}
          <div className="obs-tag-judgment">оценка/модель Basis</div>
        </div>
      </div>
      <div className="obs-fg-comps">
        {Object.entries(fg.components || {}).map(([key, c]) => (
          <div key={key} className="obs-fg-comp">
            <span className="obs-fg-comp-lbl">{OBS_FG_COMP_LABELS[key] || key}</span>
            <span className="obs-fg-comp-val">{c.score != null ? Math.round(c.score) : "—"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Общий фетч акций (scored + live дельта) — питает и бегущую ленту, и лидеров
// дня. Тот же merge, что раньше делал MarketNeo.jsx для своего внутреннего
// «Лидеры дня» под картой рынка (перенесено сюда целиком, не дублировано).
function useObsStocksLive() {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
    let alive = true;
    Promise.all([
      fetch(`${apiUrl}/api/screener/scored?universe=all`).then(r => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${apiUrl}/api/quotes/realtime`, { cache: "no-store" }).then(r => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([sc, live]) => {
      if (!alive) return;
      const rows = (sc?.rows || []).map(r => {
        const q = live ? live[r.ticker] : null;
        return { t: r.ticker, n: r.name, price: (q && q.price != null) ? q.price : r.price, chg: q ? q.change_pct : null };
      });
      setStocks(rows);
      setLoading(false);
    }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  return { stocks, loading };
}

function ObsTickerMarquee({ stocks, onSelectCompany }) {
  const items = stocks.filter(s => s.chg != null && s.price != null).slice(0, 24);
  if (!items.length) return null;
  const dup = [...items, ...items];
  return (
    <div className="obs-ticker">
      <div className="obs-ticker-row">
        {dup.map((s, i) => (
          <button key={s.t + "-" + i} className="obs-ticker-item" onClick={() => onSelectCompany && onSelectCompany(s.t)}>
            <b>{s.t}</b>
            <span className="obs-ticker-px">{s.price.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</span>
            <span className={"obs-ticker-chg " + (s.chg > 0 ? "obs-d-good" : s.chg < 0 ? "obs-d-bad" : "obs-d-neutral")}>
              {s.chg > 0 ? "▲" : s.chg < 0 ? "▼" : "▬"} {Math.abs(s.chg).toFixed(2)}%
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function ObsMoversRow({ s, onSelectCompany }) {
  return (
    <button className="obs-mover-row" onClick={() => onSelectCompany && onSelectCompany(s.t)}>
      <span className="obs-mover-id"><b>{s.t}</b><span className="obs-mover-n">{s.n}</span></span>
      <span className="obs-mover-px">{s.price != null ? s.price.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—"} ₽</span>
      <span className={"obs-mover-chg " + (s.chg > 0 ? "obs-d-good" : s.chg < 0 ? "obs-d-bad" : "obs-d-neutral")}>
        {s.chg > 0 ? "▲" : s.chg < 0 ? "▼" : "▬"} {Math.abs(s.chg).toFixed(2)}%
      </span>
    </button>
  );
}

function ObsMarketPulse({ onSelectCompany }) {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [pulse, setPulse] = useState(null);
  const [loading, setLoading] = useState(true);
  const { stocks, loading: stocksLoading } = useObsStocksLive();

  useEffect(() => {
    let alive = true;
    fetch(`${apiUrl}/api/market/pulse`).then(r => (r.ok ? r.json() : null)).then(d => {
      if (!alive) return;
      setPulse(d);
      setLoading(false);
    }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [apiUrl]);

  if (loading) {
    return <div className="tw-flex tw-items-center tw-justify-center tw-py-20 tw-text-text-tertiary tw-animate-pulse">Загружаем обзор рынка...</div>;
  }
  if (!pulse) {
    return <div className="obs-news-empty">Не удалось загрузить обзор рынка. Попробуйте позже.</div>;
  }

  const withChg = stocks.filter(s => s.chg != null);
  const sorted = [...withChg].sort((a, b) => b.chg - a.chg);
  const gain = sorted.slice(0, 5), lose = [...sorted].reverse().slice(0, 5);

  return (
    <div>
      <ObsTickerMarquee stocks={stocks} onSelectCompany={onSelectCompany} />

      <ObsFearGreedCard fg={pulse.fear_greed} />

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Индексы</div>
      <div className="obs-grid8">
        {pulse.indices.map(idx => <ObsPulseCard key={idx.ticker} item={idx} />)}
      </div>

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Лидеры дня</div>
      {stocksLoading ? (
        <div className="tw-py-6 tw-text-text-tertiary tw-text-[13px]">Загружаем лидеров дня...</div>
      ) : gain.length || lose.length ? (
        <div className="obs-movers-grid">
          <div>
            <div className="obs-movers-eyebrow obs-d-good">↑ Лидеры роста</div>
            {gain.map(s => <ObsMoversRow key={s.t} s={s} onSelectCompany={onSelectCompany} />)}
          </div>
          <div>
            <div className="obs-movers-eyebrow obs-d-bad">↓ Лидеры падения</div>
            {lose.map(s => <ObsMoversRow key={s.t} s={s} onSelectCompany={onSelectCompany} />)}
          </div>
        </div>
      ) : (
        <div className="obs-news-empty">Нет данных о дневном изменении.</div>
      )}

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Секторальные индексы MOEX</div>
      <div className="obs-grid8">
        {pulse.sectors.map(s => <ObsPulseCard key={s.ticker} item={s} />)}
      </div>

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Ставки денежного рынка · сырьё · металлы</div>
      <div className="obs-grid8">
        {pulse.rates.map(r => <ObsPulseCard key={r.ticker} item={r} />)}
        {pulse.oil && <ObsPulseCard item={pulse.oil} />}
        {pulse.metals.map(m => <ObsPulseCard key={m.ticker} item={m} />)}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ObsEconomy — «Экономическая статистика» точно по прототипу observer-sidebar-v2.html
// Данные: /api/market/macro/rate, /api/market/macro, /api/market/macro/forecast,
//         /api/market/macro/{code}/series
// ─────────────────────────────────────────────────────────────────────────────

// Индикаторы, у которых положительная дельта семантически плохая
const _INVERSE_SIGN = new Set([
  "inflation", "inflation_weekly", "inflation_expectations",
  "key_rate", "unemployment", "hh_index",
  "cn_inflation",
]);

function ObsEconomy({ token }) {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // ── data state ──
  const [rate, setRate] = useState(null);
  const [indicators, setIndicators] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [survey, setSurvey] = useState(null);
  const [rateChart, setRateChart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fcScIdx, setFcScIdx] = useState(0);

  // ── detail chart state ──
  const [detailInd, setDetailInd] = useState(null);
  const [detailPts, setDetailPts] = useState(null);  // null=loading, []=no data
  const [overlayCode, setOverlayCode] = useState("");
  const [overlayPts, setOverlayPts] = useState(null);
  const [ddOpen, setDdOpen] = useState(false);
  const [inflMetric, setInflMetric] = useState("yoy"); // м/м · г/г toggle for inflation
  const ddRef = React.useRef(null);
  const detailCardRef = React.useRef(null);

  // close dropdown on outside click
  useEffect(() => {
    const handler = (e) => { if (ddRef.current && !ddRef.current.contains(e.target)) setDdOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── primary data fetch ──
  useEffect(() => {
    const h = token ? { Authorization: `Bearer ${token}` } : {};
    setLoading(true);
    Promise.all([
      fetch(`${apiUrl}/api/market/macro/rate`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${apiUrl}/api/market/macro`, { headers: h }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${apiUrl}/api/market/macro/forecast`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${apiUrl}/api/market/macro/expert-survey`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([rt, inds, fc, sv]) => {
      setRate(rt);
      const arr = Array.isArray(inds) ? inds : [];
      setIndicators(arr);
      setForecast(fc);
      setSurvey(sv);
      setLoading(false);
      // default detail: first RU indicator with data
      const first = arr.find((x) => x.has_data && x.display_group === "ru");
      if (first) setDetailInd(first);
    });
  }, [token]);

  // ── hero chart (ставка + инфляция + ожидания) ──
  useEffect(() => {
    const get = (code, metric) =>
      fetch(`${apiUrl}/api/market/macro/${code}/series?metric=${metric}`)
        .then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([
      get("key_rate", "level"),
      get("inflation", "yoy"),
      get("inflation_expectations", "level"),
    ]).then(([kr, inf, exp]) => {
      const s = [];
      if (kr?.points?.length)  s.push({ name: "Ключевая ставка", color: "#C97A4A", points: kr.points });
      if (inf?.points?.length) s.push({ name: "Инфляция г/г",   color: "#7A8CA8", points: inf.points });
      if (exp?.points?.length) s.push({ name: "Инфл. ожидания", color: "#D9A441", points: exp.points });
      if (s.length) setRateChart(s);
    });
  }, []);

  // ── detail series (base) ──
  useEffect(() => {
    if (!detailInd) return;
    setDetailPts(null);
    // для индикаторов с mom/yoy — используем выбранный метрик; иначе первый в списке
    const hasMomYoy = detailInd.metric_types?.includes("mom") && detailInd.metric_types?.includes("yoy");
    const metric = hasMomYoy ? inflMetric : (detailInd.metric_types || ["level"])[0];
    fetch(`${apiUrl}/api/market/macro/${detailInd.code}/series?metric=${metric}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setDetailPts(d?.points || []))
      .catch(() => setDetailPts([]));
  }, [detailInd, inflMetric]);

  // ── overlay series ──
  useEffect(() => {
    if (!overlayCode) { setOverlayPts(null); return; }
    const oi = indicators.find((x) => x.code === overlayCode);
    const metric = (oi?.metric_types || ["level"])[0];
    fetch(`${apiUrl}/api/market/macro/${overlayCode}/series?metric=${metric}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setOverlayPts({ name: oi?.title || overlayCode, points: d.points || [] }); })
      .catch(() => setOverlayPts(null));
  }, [overlayCode, indicators]);

  // ── helpers ──
  const openTile = (ind) => {
    setDetailInd(ind);
    setOverlayCode("");
    setOverlayPts(null);
  };

  // Выбирает индикатор И плавно скроллит к detail-графику
  const openAndScroll = (ind) => {
    openTile(ind);
    setTimeout(() => {
      detailCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
  };

  // delta colour class — semantic: for inverse indicators, positive change = bad
  const deltaClass = (code, change) => {
    if (change == null) return "obs-d-neutral";
    const isInverse = _INVERSE_SIGN.has(code);
    if (change > 0) return isInverse ? "obs-d-bad" : "obs-d-good";
    if (change < 0) return isInverse ? "obs-d-good" : "obs-d-bad";
    return "obs-d-neutral";
  };

  const fmtDelta = (change) => {
    if (change == null) return null;
    const abs = Math.abs(change).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
    return `${change > 0 ? "▲" : change < 0 ? "▼" : ""} ${abs}`;
  };

  if (loading) {
    return (
      <div className="tw-flex tw-items-center tw-justify-center tw-py-20 tw-text-text-tertiary tw-animate-pulse">
        Загружаем макростатистику...
      </div>
    );
  }

  // ── tiles: RU group first, then world ──
  const ruInds = indicators.filter((x) => x.display_group === "ru");
  const worldInds = indicators.filter((x) => x.display_group === "world");
  const allTiles = [...ruInds, ...worldInds];
  // overlay options: all indicators with data except the current base
  const overlayOptions = indicators.filter((x) => x.has_data && x.code !== detailInd?.code);

  // ── detail chart series ──
  const detailChartSeries = [];
  if (detailPts?.length && detailInd) {
    detailChartSeries.push({ name: detailInd.title, color: "var(--accent)", points: detailPts });
  }
  if (overlayPts) {
    detailChartSeries.push({ name: overlayPts.name, color: "var(--cat-6)", points: overlayPts.points });
  }

  // ── forecast ──
  const fcScenarios = (Array.isArray(forecast?.scenarios) && forecast.scenarios.length)
    ? forecast.scenarios
    : (forecast?.rows?.length ? [{ scenario: forecast.scenario || "базовый", comment: forecast.comment, rows: forecast.rows }] : []);
  const fcSel = fcScenarios[Math.min(fcScIdx, fcScenarios.length - 1)];
  const fcRows = fcSel?.rows || [];
  const fcYears = [...new Set(fcRows.map((r) => r.year))].sort();
  const fcInds = [...new Set(fcRows.map((r) => r.indicator))];
  const fcCell = (ind, year) => fcRows.find((r) => r.indicator === ind && r.year === year);

  return (
    <div>
      {/* ──────────── 1. HERO RATE ──────────── */}
      {rate?.key_rate && (
        <div className="obs-hero-rate">
          <div className="obs-hero-topline">
            <div>
              <div className="obs-hero-label">Ключевая ставка ЦБ</div>
              <div className="obs-hero-num">
                {_fmtNum(rate.key_rate.value)}<sup>%</sup>
              </div>
              <div className="obs-hero-meta">
                на {rate.key_rate.as_of}
                {rate.meeting?.next_meeting_date && (
                  <> · след. заседание <b>{rate.meeting.next_meeting_date}</b></>
                )}
              </div>
            </div>
            <div className="obs-hero-note">
              {/* Не пересказ официального релиза ЦБ — это НАША интерпретация
                  того, куда, скорее всего, движется траектория, с пометкой
                  «суждение». Официальный сигнал ЦБ (rate.meeting.signal),
                  если есть — тоже наше прочтение его формулировки, не цитата. */}
              {rate.meeting?.signal
                ? rate.meeting.signal
                : "Пока нет сигналов, что регулятор готов резко менять курс — вероятнее плавное движение вслед за инфляцией, а не скачок в ту или иную сторону."}
              {rate.meeting?.consensus_forecast && (
                <> Рыночный консенсус — <b>{rate.meeting.consensus_forecast}</b>.</>
              )}
              {" "}<span className="obs-tag-judgment">суждение Basis</span>
            </div>
          </div>

          {rateChart && (
            <div>
              <div className="obs-legend">
                {rateChart.map((s, i) => (
                  <span key={i}>
                    <i style={{ background: s.color }} />
                    {s.name}
                  </span>
                ))}
              </div>
              <ObsLineChart series={rateChart} viewW={1000} viewH={340} unit="%" />
            </div>
          )}
        </div>
      )}

      {/* ──────────── 2. INDICATOR GRID ──────────── */}
      {allTiles.length > 0 && (
        <>
          <div className="obs-grid8" role="list" aria-label="Экономические показатели">
            {allTiles.map((ind) => {
              // Предпочитаем yoy над mom для отображения в плитке (inflation: metric_types=["mom","yoy"])
              const preferYoy = ind.metric_types?.includes("yoy") && ind.values?.yoy;
              const metricKey = preferYoy ? "yoy" : (ind.metric_types || ["level"])[0];
              const v = ind.values?.[metricKey] || Object.values(ind.values || {})[0];
              const valStr = v ? `${_fmtNum(v.value)}${ind.unit === "%" ? "%" : ""}` : "—";
              const deltaStr = fmtDelta(v?.change);
              const dCls = deltaClass(ind.code, v?.change);
              const isActive = detailInd?.code === ind.code;
              return (
                <button
                  key={ind.code}
                  role="listitem"
                  className={`obs-tile${isActive ? " obs-tile--active" : ""}`}
                  style={isActive ? { background: "var(--accent-soft)" } : {}}
                  onClick={(e) => { e.currentTarget.blur(); openTile(ind); }}
                  aria-pressed={isActive}
                  aria-label={`${ind.title}: ${valStr}`}
                >
                  <div className="obs-tile-lbl">{ind.title}</div>
                  <div className="obs-tile-val">{valStr}</div>
                  {(deltaStr || ind.influence_short) && (
                    <div className={`obs-tile-delta ${dCls}`}>
                      {deltaStr || ind.influence_short}
                    </div>
                  )}
                  {v?.as_of && <div className="obs-tile-date">{v.as_of}</div>}
                  <button
                    type="button"
                    className="obs-tile-link"
                    onClick={(e) => { e.stopPropagation(); e.currentTarget.blur(); openAndScroll(ind); }}
                    tabIndex={-1}
                    aria-label={`График — ${ind.title}`}
                  >
                    📈 График
                  </button>
                </button>
              );
            })}
          </div>
          <div className="obs-grid8-foot">
            * Данные обновляются при выходе официальной статистики. Нажмите плитку чтобы увидеть график.
          </div>
        </>
      )}

      {/* ──────────── 3. DETAIL CHART ──────────── */}
      <div className="obs-detail-card" ref={detailCardRef}>
        <div className="obs-detail-head">
          <h3 className="obs-detail-title">
            {detailInd
              ? (detailInd.metric_types?.includes("mom") && detailInd.metric_types?.includes("yoy")
                  ? `${detailInd.title} (${inflMetric === "mom" ? "м/м" : "г/г"})`
                  : detailInd.title)
              : "Выберите показатель"}
          </h3>
          {detailInd && (
            <div className="obs-detail-overlay-row">
              <span>Наложить:</span>
              <div
                ref={ddRef}
                className={`obs-dd${ddOpen ? " obs-dd--open" : ""}`}
              >
                <button
                  type="button"
                  className="obs-dd-trigger"
                  onClick={() => setDdOpen((v) => !v)}
                  aria-haspopup="listbox"
                  aria-expanded={ddOpen}
                >
                  <span>{overlayCode ? overlayOptions.find((x) => x.code === overlayCode)?.title || overlayCode : "— нет —"}</span>
                  <span className="obs-dd-arrow" aria-hidden="true">▾</span>
                </button>
                {ddOpen && (
                  <div className="obs-dd-panel" role="listbox">
                    <div
                      className={`obs-dd-option${!overlayCode ? " obs-dd-option--selected" : ""}`}
                      role="option"
                      aria-selected={!overlayCode}
                      onClick={() => { setOverlayCode(""); setOverlayPts(null); setDdOpen(false); }}
                    >
                      — нет —
                    </div>
                    {overlayOptions.map((opt) => (
                      <div
                        key={opt.code}
                        className={`obs-dd-option${overlayCode === opt.code ? " obs-dd-option--selected" : ""}`}
                        role="option"
                        aria-selected={overlayCode === opt.code}
                        onClick={() => { setOverlayCode(opt.code); setDdOpen(false); }}
                      >
                        {opt.title}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="obs-detail-hint" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
          <span>
            {detailInd
              ? (detailInd.influence_short || "Кликните «График» у любого показателя выше, чтобы посмотреть его здесь и сравнить с другим рядом.")
              : "Кликните «График» у любого показателя выше."}
          </span>
          {/* м/м · г/г toggle — только для индикаторов с обоими метриками */}
          {detailInd?.metric_types?.includes("mom") && detailInd?.metric_types?.includes("yoy") && (
            <span className="obs-infl-toggle" role="group" aria-label="Выбор периода инфляции">
              <button
                type="button"
                className={`obs-infl-toggle-opt${inflMetric === "mom" ? " obs-infl-toggle-opt--on" : ""}`}
                onClick={() => setInflMetric("mom")}
                aria-pressed={inflMetric === "mom"}
              >м/м</button>
              <button
                type="button"
                className={`obs-infl-toggle-opt${inflMetric === "yoy" ? " obs-infl-toggle-opt--on" : ""}`}
                onClick={() => setInflMetric("yoy")}
                aria-pressed={inflMetric === "yoy"}
              >г/г</button>
            </span>
          )}
        </div>
        {detailPts === null && <div className="tw-text-text-tertiary tw-text-sm tw-animate-pulse tw-py-6">Загружаем ряд...</div>}
        {detailChartSeries.length > 0 && (
          <ObsLineChart
            series={detailChartSeries}
            viewW={900} viewH={150}
            unit={detailInd?.unit === "%" ? "%" : ""}
          />
        )}
        {detailPts !== null && detailChartSeries.length === 0 && (
          <div className="tw-text-text-tertiary tw-text-sm tw-py-6">Данных для графика пока нет.</div>
        )}
      </div>

      {/* ──────────── 4. FORECAST TABLE ──────────── */}
      {fcRows.length > 0 ? (
        <div className="obs-forecast-card">
          <h3 className="obs-forecast-title">Прогноз Банка России</h3>
          {forecast?.as_of && (
            <div className="obs-forecast-asof">по состоянию на {forecast.as_of}</div>
          )}
          {fcScenarios.length > 1 && (
            <div className="tw-flex tw-flex-wrap tw-gap-1.5 tw-mb-3">
              {fcScenarios.map((s, i) => (
                <button
                  key={s.scenario}
                  type="button"
                  onClick={() => setFcScIdx(i)}
                  className={`tw-text-[12px] tw-px-3 tw-py-1 tw-rounded-pill tw-font-semibold tw-border tw-cursor-pointer tw-transition-colors ${
                    i === fcScIdx
                      ? "tw-bg-accent tw-border-accent tw-text-white"
                      : "tw-bg-transparent tw-border-border-subtle tw-text-text-secondary hover:tw-border-border-strong"
                  }`}
                >
                  {s.scenario.charAt(0).toUpperCase() + s.scenario.slice(1)}
                </button>
              ))}
            </div>
          )}
          <div style={{ overflowX: "auto" }}>
            <table className="obs-forecast-table">
              <thead>
                <tr>
                  <th>Показатель{fcScenarios.length > 1 ? ` · ${fcSel?.scenario}` : ""}</th>
                  <th>Факт сейчас</th>
                  {fcYears.map((y) => <th key={y}>{y}</th>)}
                </tr>
              </thead>
              <tbody>
                {fcInds.map((ind) => {
                  // find current fact from indicators list (loose match)
                  const liveInd = indicators.find((x) =>
                    x.title?.toLowerCase().includes(ind.toLowerCase().slice(0, 6))
                  );
                  const lv = liveInd?.values?.[(liveInd?.metric_types || ["level"])[0]];
                  const factStr = lv ? `${_fmtNum(lv.value)}${liveInd?.unit === "%" ? "%" : ""}` : "—";
                  return (
                    <tr key={ind}>
                      <td>{ind}</td>
                      <td style={{ fontFamily: "var(--font-mono)", color: "var(--text-secondary)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                        {factStr}
                      </td>
                      {fcYears.map((y) => {
                        const c = fcCell(ind, y);
                        return (
                          <td key={y}>
                            {c ? <span className="obs-range-pill">{c.value}</span> : "—"}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {fcSel?.comment && (
            <div className="obs-forecast-comment">{fcSel.comment}</div>
          )}
        </div>
      ) : (
        <div className="obs-forecast-card">
          <h3 className="obs-forecast-title">Прогноз Банка России</h3>
          <p style={{ fontSize: "13px", color: "var(--text-tertiary)", marginTop: "10px" }}>
            Прогноз ЦБ появится после ближайшей публикации — мониторинг ЦБ проверяет источники ежедневно.
          </p>
        </div>
      )}

      {/* ──────────── 5. МАКРООПРОС ЦБ (независимый консенсус, не сценарии самого ЦБ) ──────────── */}
      {survey?.rows?.length > 0 && (() => {
        const svYears = [...new Set(survey.rows.map((r) => r.year))].sort();
        const svInds = [...new Set(survey.rows.map((r) => r.indicator))];
        const svCell = (ind, y) => survey.rows.find((r) => r.indicator === ind && r.year === y);
        return (
          <div className="obs-forecast-card">
            <h3 className="obs-forecast-title">Макроэкономический опрос Банка России</h3>
            <div className="obs-forecast-asof">
              Независимый консенсус{survey.n_respondents ? ` · ~${survey.n_respondents} аналитиков` : ""}
              {survey.as_of ? ` · опрос на ${survey.as_of}` : ""} — не прогноз самого ЦБ, для сверки
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="obs-forecast-table">
                <thead>
                  <tr>
                    <th>Показатель</th>
                    {svYears.map((y) => <th key={y}>{y}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {svInds.map((ind) => (
                    <tr key={ind}>
                      <td>{ind}</td>
                      {svYears.map((y) => {
                        const c = svCell(ind, y);
                        return <td key={y}>{c ? <span className="obs-range-pill">{c.value}</span> : "—"}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// Декларативная карта раздел → JSX для keep-alive рендера.
// Все ПОСЕЩЁННЫЕ разделы остаются в DOM; неактивные — display:none.
// Повторное переключение — мгновенно, без повторного fetch.

export {
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
  ObsLineChart,
};
