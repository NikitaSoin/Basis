import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Newspaper,
  Activity,
  Layers,
  Calendar,
  FileText,
  BarChart2,
  Globe,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { Disclosure } from "../design/textblocks";

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
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

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

          {/* ===== ОЦЕНКА СИТУАЦИИ: deep-card с суждением Basis ===== */}
          {mode === "assessment" && (
            <div className="obs-deep-card">
              <div className="obs-deep-eyebrow">Оценка ситуации · суждение Basis</div>
              <h3>Куда идёт ситуация и что это значит для рынка</h3>

              {deepBlock?.market_impact && (
                <p style={{ marginBottom: 18 }}>{deepBlock.market_impact}</p>
              )}
              {!deepBlock?.market_impact && overviewBlock?.status_text && (
                <p style={{ marginBottom: 18 }}>{overviewBlock.status_text}</p>
              )}

              {/* Первыми затронуты — каналы влияния */}
              {Array.isArray(deepBlock?.channels) && deepBlock.channels.length > 0 && (
                <div className="obs-deep-divider">
                  <div className="obs-deep-divider-title">Каналы влияния</div>
                  {deepBlock.channels.map((c, i) => (
                    <div key={i} style={{ marginBottom: 10 }}>
                      <div style={{ fontWeight: 600, fontSize: 13, color: "var(--obs-dc-ink)", marginBottom: 3 }}>
                        {c.channel}
                      </div>
                      {c.effect && (
                        <p style={{ marginBottom: 0, fontSize: 13 }}>{c.effect}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Сценарии */}
              {deepBlock?.scenarios && (
                <div className="obs-deep-divider">
                  <div className="obs-deep-divider-title" style={{ marginBottom: 14 }}>
                    Сценарии — оценка Basis
                  </div>
                  {/* Сценарии рендерим в светлой карточке, вне dark-card — для читаемости */}
                </div>
              )}
            </div>
          )}

          {/* Сценарии вне dark-card (светлый фон, tabular) */}
          {mode === "assessment" && deepBlock?.scenarios && (
            <div style={{ marginTop: 16 }}>
              <div className="obs-scenario-row">
                {deepBlock.scenarios.base && (
                  <div className="obs-scenario-card">
                    <div className="obs-scenario-title">Базовый</div>
                    {deepBlock.scenarios.base.probability && (
                      <div className="obs-scenario-prob">вероятность: {deepBlock.scenarios.base.probability}</div>
                    )}
                    {(deepBlock.scenarios.base.key_numbers || deepBlock.scenarios.base.description) && (
                      <div className="obs-scenario-num">
                        {deepBlock.scenarios.base.key_numbers || deepBlock.scenarios.base.description}
                      </div>
                    )}
                    {deepBlock.scenarios.base.triggers && (
                      <div className="obs-scenario-trig">
                        <b>Триггеры</b>
                        {deepBlock.scenarios.base.triggers}
                      </div>
                    )}
                  </div>
                )}
                {deepBlock.scenarios.bull && (
                  <div className="obs-scenario-card obs-scenario-card--bull">
                    <div className="obs-scenario-title">Оптимистичный</div>
                    {deepBlock.scenarios.bull.probability && (
                      <div className="obs-scenario-prob">вероятность: {deepBlock.scenarios.bull.probability}</div>
                    )}
                    {(deepBlock.scenarios.bull.key_numbers || deepBlock.scenarios.bull.description) && (
                      <div className="obs-scenario-num">
                        {deepBlock.scenarios.bull.key_numbers || deepBlock.scenarios.bull.description}
                      </div>
                    )}
                    {deepBlock.scenarios.bull.triggers && (
                      <div className="obs-scenario-trig">
                        <b>Триггеры</b>
                        {deepBlock.scenarios.bull.triggers}
                      </div>
                    )}
                  </div>
                )}
                {deepBlock.scenarios.bear && (
                  <div className="obs-scenario-card obs-scenario-card--bear">
                    <div className="obs-scenario-title">Негативный</div>
                    {deepBlock.scenarios.bear.probability && (
                      <div className="obs-scenario-prob">вероятность: {deepBlock.scenarios.bear.probability}</div>
                    )}
                    {(deepBlock.scenarios.bear.key_numbers || deepBlock.scenarios.bear.description) && (
                      <div className="obs-scenario-num">
                        {deepBlock.scenarios.bear.key_numbers || deepBlock.scenarios.bear.description}
                      </div>
                    )}
                    {deepBlock.scenarios.bear.triggers && (
                      <div className="obs-scenario-trig">
                        <b>Триггеры</b>
                        {deepBlock.scenarios.bear.triggers}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
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

// =========================
// OBS MARKET PULSE — Обозреватель · Обзор рынка (2026-07-11, восстановлено
// 2026-07-12). Бегущая лента + индекс страха и жадности Basis + индексы/
// сектора/ставки/сырьё/металлы (/api/market/pulse) + лидеры дня (перенесены
// сюда из «Рынок → Карта рынка»).
// =========================
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
      <div className="obs-tile-val">
        {lvl != null ? lvl.toLocaleString("ru-RU", { maximumFractionDigits: dec }) : "—"}
        {item.unit ? (item.unit === "%" ? "%" : " " + item.unit) : ""}
      </div>
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

function useObsStocksLive() {
  const [stocks, setStocks] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
    let alive = true;
    Promise.all([
      fetch(`${apiUrl}/api/screener/scored?universe=all`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${apiUrl}/api/quotes/realtime`, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([sc, live]) => {
      if (!alive) return;
      const rows = (sc?.rows || []).map((r) => {
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
  const items = stocks.filter((s) => s.chg != null && s.price != null).slice(0, 24);
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
    fetch(`${apiUrl}/api/market/pulse`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (!alive) return; setPulse(d); setLoading(false); })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [apiUrl]);

  if (loading) return <div className="tw-flex tw-items-center tw-justify-center tw-py-20 tw-text-text-tertiary tw-animate-pulse">Загружаем обзор рынка...</div>;
  if (!pulse) return <div className="obs-news-empty">Не удалось загрузить обзор рынка. Попробуйте позже.</div>;

  const withChg = stocks.filter((s) => s.chg != null);
  const sorted = [...withChg].sort((a, b) => b.chg - a.chg);
  const gain = sorted.slice(0, 5), lose = [...sorted].reverse().slice(0, 5);

  return (
    <div>
      <ObsTickerMarquee stocks={stocks} onSelectCompany={onSelectCompany} />
      <ObsFearGreedCard fg={pulse.fear_greed} />

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Индексы</div>
      <div className="obs-grid8">{pulse.indices.map((idx) => <ObsPulseCard key={idx.ticker} item={idx} />)}</div>

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Лидеры дня</div>
      {stocksLoading ? (
        <div className="tw-py-6 tw-text-text-tertiary tw-text-[13px]">Загружаем лидеров дня...</div>
      ) : gain.length || lose.length ? (
        <div className="obs-movers-grid">
          <div>
            <div className="obs-movers-eyebrow obs-d-good">↑ Лидеры роста</div>
            {gain.map((s) => <ObsMoversRow key={s.t} s={s} onSelectCompany={onSelectCompany} />)}
          </div>
          <div>
            <div className="obs-movers-eyebrow obs-d-bad">↓ Лидеры падения</div>
            {lose.map((s) => <ObsMoversRow key={s.t} s={s} onSelectCompany={onSelectCompany} />)}
          </div>
        </div>
      ) : (
        <div className="obs-news-empty">Нет данных о дневном изменении.</div>
      )}

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Секторальные индексы MOEX</div>
      <div className="obs-grid8">{pulse.sectors.map((s) => <ObsPulseCard key={s.ticker} item={s} />)}</div>

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Ставки денежного рынка · сырьё · металлы</div>
      <div className="obs-grid8">
        {pulse.rates.map((r) => <ObsPulseCard key={r.ticker} item={r} />)}
        {pulse.oil && <ObsPulseCard item={pulse.oil} />}
        {pulse.metals.map((m) => <ObsPulseCard key={m.ticker} item={m} />)}
      </div>
    </div>
  );
}

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
};
