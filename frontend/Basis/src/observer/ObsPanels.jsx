import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// MapLibre грузит воркер (парсинг тайлов) через import.meta.url относительно
// СВОЕГО модуля — CRA/webpack бандлит всё в один main.<hash>.js, там нет
// отдельного maplibre-gl-worker.mjs рядом, поэтому дефолтный путь резолвится
// в "" и воркер тихо не создаётся (карта грузит стиль, но тайлы никогда не
// рендерятся — пустой белый холст, без явной ошибки в консоли). Явно
// указываем URL воркера на статическую копию в public/ (см. её же
// maplibre-gl-shared.js рядом — воркер импортирует его относительным путём).
maplibregl.setWorkerUrl(`${process.env.PUBLIC_URL}/maplibre-gl-worker.js`);
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
  ShieldAlert,
  Sparkles,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Info,
  Gavel,
  Coins,
  Building2,
  Swords,
  X,
  CheckCircle2,
  AlarmClock,
  Rocket,
  RotateCcw,
  XCircle,
  Users,
  Zap,
  Factory,
  Anchor,
  ZoomIn,
  ZoomOut,
  Maximize2,
} from "lucide-react";
import { Disclosure, ANALYST_MD } from "../design/textblocks";
import { CompanyLogo } from "../design/CompanyLogo";

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
      { id: "corp-news", label: "Корп. события",     icon: Building2 },
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
  // По умолчанию — только важное (жалоба владельца: «новостей много, реально
  // важных мало, клиенту нужно быстро увидеть ценное»). «Все» — по клику.
  const [importance, setImportance] = useState("important");
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

      {/* Impact callout — для «важное» подчёркнуто явной подписью "Почему это
          важно" (жалоба владельца: важность должна быть видна, не потеряна
          среди общего текста), для остальных — компактный префикс как раньше */}
      {hasImpact && impactText && (
        high ? (
          <div className="obs-news-impact obs-news-impact--high">
            <div className="obs-news-impact-label">Почему это важно</div>
            {impactText}
          </div>
        ) : (
          <div className="obs-news-impact">↳ {impactText}</div>
        )
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
              || r.conclusion || r.data_gaps;
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
                      {r.data_gaps && (
                        <div className="obs-rep-gaps">
                          <b>Не хватает в источнике.</b> {r.data_gaps}
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
// ObsCorporateNews — «Корп. события»: лента НОВОСТЕЙ по компаниям, не календарь
// (владелец, 2026-07-15 — v1 сводилась к копии дивидендного календаря, переделано
// на момент-модель: каждая карточка привязана к конкретному переходу и стареет,
// не висит неделями одним и тем же фактом). По образцу ObsReports.
// Данные: GET /api/market/corporate-news (поля: kind, ticker, company,
// sector, date, title, detail, epistemic, link_to, likely_calendar_error).
// =============================================================

const CN_KIND_META = {
  report_published:     { label: "Отчёт вышел",              icon: FileText,     group: "reports"   },
  report_missing:        { label: "Ожидался, не вышел",       icon: Clock,        group: "reports"   },
  div_recommended:       { label: "Рекомендовано советом директоров", icon: Coins,        group: "dividend"  },
  div_approved:          { label: "Одобрено собранием акционеров",   icon: CheckCircle2, group: "dividend"  },
  div_cutoff_soon:       { label: "Последний день с дивидендом",     icon: AlarmClock,   group: "dividend"  },
  ipo_spo:               { label: "IPO / SPO",                icon: Rocket,       group: "placement" },
  share_issuance:        { label: "Допэмиссия",               icon: Layers,       group: "placement" },
  buyback:               { label: "Байбэк",                   icon: RotateCcw,    group: "placement" },
  delisting:             { label: "Делистинг",                icon: XCircle,      group: "placement" },
  ma:                    { label: "M&A",                      icon: Swords,       group: "business"  },
  management:            { label: "Менеджмент",                icon: Briefcase,    group: "business"  },
  ownership_change:      { label: "Смена акционеров",         icon: Users,        group: "business"  },
  div_policy_negative:   { label: "Дивидендная политика",     icon: Scale,        group: "business"  },
  promised_report_date:  { label: "Обещана дата отчёта",      icon: Calendar,     group: "business"  },
};

const CN_FILTERS = [
  { id: "all",        label: "Все"        },
  { id: "reports",    label: "Отчёты"     },
  { id: "dividend",   label: "Дивиденды"  },
  { id: "placement",  label: "Размещения" },
  { id: "business",   label: "Бизнес"     },
];

function ObsCorporateNews({ token, portfolioOnly, onSelectCompany, onOpenReports }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [kindFilter, setKindFilter] = useState("all");
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${apiUrl}/api/market/corporate-news?portfolio_only=${portfolioOnly}`, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token]);

  const items = data?.items || [];
  const sorted = [...items].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  const filtered = kindFilter === "all"
    ? sorted
    : sorted.filter((it) => (CN_KIND_META[it.kind] || {}).group === kindFilter);

  return (
    <div>
      <p className="obs-cn-desc">
        Единая лента корпоративных событий по компаниям: вышедшие и ожидавшиеся отчётности,
        объявленные дивиденды, значимые бизнес-новости. Ознакомительно, не индивидуальная
        инвестиционная рекомендация.
      </p>

      <div className="obs-cn-filters" role="group" aria-label="Фильтр по виду события">
        {CN_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`obs-cn-chip${kindFilter === f.id ? " obs-cn-chip--active" : ""}`}
            onClick={() => setKindFilter(f.id)}
          >{f.label}</button>
        ))}
      </div>

      {loading && <div className="obs-news-loading">Загрузка событий…</div>}
      {error && (
        <div className="obs-news-loading" style={{ color: "var(--danger)" }}>
          Не удалось загрузить корпоративные события.
        </div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <div className="obs-news-empty">
          {portfolioOnly ? "По бумагам портфеля событий нет." : "Событий по выбранному фильтру нет."}
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="obs-cn-list">
          {filtered.map((it, i) => {
            const meta = CN_KIND_META[it.kind] || { label: it.kind, icon: Info, group: "business" };
            const Icon = meta.icon;
            const muted = it.kind === "report_missing";
            const onCardClick =
              it.link_to === "reports" && onOpenReports ? onOpenReports :
              it.link_to === "company" && it.ticker && onSelectCompany ? () => onSelectCompany(it.ticker) :
              null;
            const clickable = Boolean(onCardClick);
            return (
              <div key={i} className={`obs-cn-card${muted ? " obs-cn-card--muted" : ""}`}>
                <div className="obs-cn-card-head">
                  <span
                    className={`obs-cn-kind-icon obs-cn-kind-icon--${muted ? "missing" : meta.group}`}
                    title={meta.label}
                    aria-hidden="true"
                  >
                    <Icon size={13} />
                  </span>
                  {it.ticker && <CompanyLogo ticker={it.ticker} name={it.company} size={28} />}
                  <div className="obs-cn-head-text">
                    <span className="obs-cn-ticker">{it.ticker}</span>
                    {it.company && <span className="obs-cn-company">{it.company}</span>}
                  </div>
                  <span className="obs-cn-date">{_obsDateRu(it.date)}</span>
                </div>

                <div className="obs-cn-title">
                  {clickable ? (
                    <button
                      type="button"
                      className="obs-rep-toggle"
                      style={{ fontSize: "14.5px", fontWeight: 600, textAlign: "left" }}
                      onClick={onCardClick}
                    >{it.title}</button>
                  ) : it.title}
                </div>

                {it.detail && <p className="obs-cn-detail">{it.detail}</p>}

                <div className="obs-cn-foot">
                  <span className={it.epistemic === "оценка" ? "obs-tag-estimate" : "obs-tag-fact"}>
                    {it.epistemic || "факт"}
                  </span>
                  {it.kind === "report_missing" && it.likely_calendar_error && (
                    <span className="obs-cn-cal-note">
                      <Info size={11} aria-hidden="true" /> вероятно, погрешность нашего календаря
                    </span>
                  )}
                </div>
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

// Дата — агрегированная оценка (не подтверждена эмитентом/биржей). ОПТ-ИН по явному
// сигналу, а не "всё, что не issuer" — большинство событий (дивиденды с суммой из
// листинга MOEX, оферты/погашения/экспирации, график ЦБ) вообще не заполняют
// payload.confidence, но это подтверждённые факты, не оценки; бейдж «оценка» должен
// стоять только там, где дата ДЕЙСТВИТЕЛЬНО не подтверждена (report_watch-детект
// отчётности — confidence:"public_aggregated" всегда; оценочный релиз ИПЦ —
// payload.estimated:true).
function _obsIsDateEstimate(e) {
  const p = e.payload || {};
  return p.confidence === "public_aggregated" || p.estimated === true;
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
            <div key={e.id || i} className="obs-tl-item" style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
              <div className="obs-tl-dot" style={{ background: typeM(e.type).color }} />
              {e.ticker && <CompanyLogo ticker={e.ticker} name={e.title} size={34} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="obs-tl-date">
                  {_obsDateRu(e.date)}{e.time ? ` · ${e.time} МСК` : ""}
                </div>
                <div className="obs-tl-title" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
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
                  {_obsIsDateEstimate(e) && (
                    <span className="obs-cal-conf obs-cal-conf--estimate" title="Дата — агрегированная оценка, не подтверждена эмитентом/биржей">оценка</span>
                  )}
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
                <div key={i} className="obs-cal-detail-card" style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  {e.ticker && <CompanyLogo ticker={e.ticker} name={e.title} size={34} />}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                      <div
                        className="obs-cal-detail-type"
                        style={{ background: typeM(e.type).color }}
                      >{typeM(e.type).label}</div>
                      {e.payload && e.payload.confidence !== "issuer" && (
                        <span className="obs-cal-conf obs-cal-conf--estimate" title="Дата — агрегированная оценка, не подтверждена эмитентом/биржей">оценка</span>
                      )}
                    </div>
                    <div className="obs-cal-detail-event-title">{e.title}</div>
                    {e.status && <div className="obs-cal-detail-sub">{e.status}</div>}
                    {e.type === "dividend" && e.payload && e.payload.dividend_yield != null && (
                      <div className="obs-cal-detail-sub">
                        Дивидендная доходность: ▲ {e.payload.dividend_yield}%
                      </div>
                    )}
                  </div>
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
// OBS BAROMETER — общий словарь для «Геополитика» и «Институты»:
// оба раздела — 13 субиндексов 1-5 + сценарии-вероятности + общий балл.
// Разница только в ПОЛЯРНОСТИ (для институтов выше=лучше, для гео выше=опаснее)
// и в наборе смысловых кластеров. Классы obs-inst-* — общий визуальный
// словарь обеих карт барометра (историческое имя от институционального
// барометра, переиспользуется геополитикой намеренно, чтобы оба «барометра»
// платформы читались как одно семейство).
// =========================

// Балл → цветовой уровень с учётом полярности шкалы
function obsScoreTier(score, polarity /* 'higherBetter' | 'higherWorse' */) {
  const s = Number(score);
  const norm = polarity === "higherWorse" ? 6 - s : s; // выше norm = всегда лучше
  if (norm >= 3.75) return { tier: "good", color: "var(--success)" };
  if (norm <= 2.5) return { tier: "bad", color: "var(--danger)" };
  return { tier: "mid", color: "var(--warning)" };
}

// Строку/число вероятности → целый процент
function obsParsePct(v) {
  if (v == null) return 0;
  if (typeof v === "number") return Math.round(v <= 1 ? v * 100 : v);
  const m = String(v).match(/(\d+(?:[.,]\d+)?)\s*%/);
  return m ? Math.round(parseFloat(m[1].replace(",", "."))) : 0;
}

// Общий балл → две группы субиндексов «тянут вниз» / «относительно лучше»
function obsBaroBalance(subindices, polarity) {
  if (!Array.isArray(subindices) || subindices.length === 0) return null;
  const scores = subindices.map((s) => Number(s.score));
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  if (min === max) return null;
  const lowGroup = subindices.filter((s) => Number(s.score) === min);
  const highGroup = subindices.filter((s) => Number(s.score) === max);
  const bad = polarity === "higherWorse" ? highGroup : lowGroup;
  const good = polarity === "higherWorse" ? lowGroup : highGroup;
  const badScore = polarity === "higherWorse" ? max : min;
  const goodScore = polarity === "higherWorse" ? min : max;
  return { bad, good, badScore, goodScore };
}

// Гейдж-шкала 1-5 под общим баллом
function ObsBaroScale({ score, max = 5, polarity, labels }) {
  const pct = Math.max(0, Math.min(1, (Number(score) - 1) / (max - 1)));
  const dirClass = polarity === "higherWorse" ? "obs-baro-scale--bad-high" : "obs-baro-scale--good-high";
  return (
    <div>
      <div className={`obs-baro-scale ${dirClass}`}>
        <div className="obs-baro-scale-track" />
        <div className="obs-baro-scale-marker" style={{ left: `${pct * 100}%` }} />
      </div>
      {labels && (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-tertiary)", marginBottom: 14 }}>
          <span>{labels[0]}</span>
          <span>{labels[1]}</span>
        </div>
      )}
    </div>
  );
}

// Hero-вердикт барометра: балл + шкала + текстовый вывод Basis + явный баланс
function ObsBaroHero({ eyebrow, asOf, score, verdict, polarity, scaleLabels, subindices, extra, coSignal }) {
  const tier = obsScoreTier(score, polarity);
  const balance = obsBaroBalance(subindices, polarity);
  return (
    <div className="obs-inst-hero">
      <div className="obs-inst-hero-top">
        <span className="obs-inst-hero-eyebrow"><Activity size={13} /> {eyebrow}</span>
        {asOf && <span className="obs-inst-hero-asof">срез на {asOf}</span>}
      </div>
      <div className="obs-inst-hero-score-row">
        <span className="obs-inst-hero-score" style={{ color: tier.color }}>
          {Number(score).toFixed(1)}<span className="obs-inst-hero-score-max">/5</span>
        </span>
        {coSignal}
      </div>
      <ObsBaroScale score={score} polarity={polarity} labels={scaleLabels} />
      {verdict && <p className="obs-inst-hero-verdict">{verdict}</p>}
      {balance && (
        <div className="obs-inst-hero-balance">
          <div className="obs-inst-hero-balance-row obs-inst-hero-balance-row--down">
            <TrendingDown size={14} />
            <span><b>Тянут вниз</b> ({balance.badScore}/5): {balance.bad.map((s) => s.label).join(", ")}</span>
          </div>
          <div className="obs-inst-hero-balance-row obs-inst-hero-balance-row--up">
            <TrendingUp size={14} />
            <span><b>Относительно лучше</b> ({balance.goodScore}/5): {balance.good.map((s) => s.label).join(", ")}</span>
          </div>
        </div>
      )}
      {extra}
    </div>
  );
}

// Вероятностная лесенка сценариев (сортировка по убыванию, текущий — подсвечен)
function ObsBaroLadder({ items, currentKey }) {
  const sorted = [...items].sort((a, b) => b.pct - a.pct);
  return (
    <div className="obs-inst-ladder">
      {sorted.map((it) => (
        <div key={it.key} className={`obs-inst-ladder-row${it.key === currentKey ? " obs-inst-ladder-row--current" : ""}`}>
          <span className="obs-inst-ladder-name">{it.label}</span>
          <span className="obs-inst-ladder-bar-track">
            <span className="obs-inst-ladder-bar-fill" style={{ width: `${it.pct}%` }} />
          </span>
          <span className="obs-inst-ladder-pct">{it.pct}%</span>
        </div>
      ))}
    </div>
  );
}

// 13 субиндексов, сгруппированных в смысловые кластеры-аккордеоны (native <details>)
// Одна строка субиндекса (ключ + метка + эпистемический тег + балл + rationale).
// Вынесено из ObsBaroClusters, чтобы переиспользовать вне аккордеона (напр. «Внешние оси»).
function ObsBaroSubRow({ s, polarity }) {
  const sTier = obsScoreTier(s.score, polarity);
  return (
    <div className="obs-inst-sub">
      <div className="obs-inst-sub-head">
        <span className="obs-inst-sub-key">{s.key}</span>
        <span className="obs-inst-sub-label">{s.label}</span>
        {s.type === "факт"
          ? <span className="obs-tag-fact">факт</span>
          : <span className="obs-inst-tag obs-inst-tag--est">оценка</span>}
        <span className="obs-inst-sub-score" style={{ color: sTier.color }}>
          {s.score}<span className="obs-inst-sub-score-max">/5</span>
        </span>
      </div>
      {s.rationale && <p className="obs-inst-sub-rationale" style={{ whiteSpace: "pre-line" }}>{s.rationale}</p>}
      {s.anchor_note && <p className="obs-inst-sub-rationale" style={{ color: "var(--text-tertiary)", fontStyle: "italic" }}>{s.anchor_note}</p>}
    </div>
  );
}

function ObsBaroClusters({ clusters, subindexMap, polarity }) {
  return (
    <div className="obs-inst-clusters">
      {clusters.map((cl) => {
        const items = cl.keys.map((k) => subindexMap[k]).filter(Boolean);
        if (items.length === 0) return null;
        const avg = items.reduce((a, s) => a + Number(s.score || 0), 0) / items.length;
        const avgTier = obsScoreTier(avg, polarity);
        const Icon = cl.icon;
        return (
          <details key={cl.name} className="obs-inst-cluster">
            <summary className="obs-inst-cluster-head">
              <Icon size={15} className="obs-inst-cluster-icon" />
              <span className="obs-inst-cluster-name">{cl.name}</span>
              <span className="obs-inst-segbar">
                {items.map((s) => (
                  <i key={s.key} className="on" style={{ "--sc": obsScoreTier(s.score, polarity).color }} title={`${s.key}: ${s.score}/5`} />
                ))}
              </span>
              <span className="obs-inst-cluster-avg" style={{ color: avgTier.color }}>
                {avg.toFixed(1)}<span className="obs-inst-cluster-avg-max">/5</span>
              </span>
              <ChevronDown size={15} className="obs-inst-chev" />
            </summary>
            <div className="obs-inst-cluster-body">
              {items.map((s) => <ObsBaroSubRow key={s.key} s={s} polarity={polarity} />)}
            </div>
          </details>
        );
      })}
    </div>
  );
}

// Маленький информационный чип «горизонт актуальности» рядом с заголовком раздела —
// поясняет, как часто барометр/раздел имеет смысл перепроверять.
function ObsHorizonChip({ children }) {
  return (
    <span className="obs-horizon-chip">
      <Clock size={11} aria-hidden="true" />
      {children}
    </span>
  );
}

// Методологические оговорки — ПЕРЕД hero (снижают тревогу до пугающих цифр, не после)
function ObsBaroCaveat({ flags }) {
  if (!Array.isArray(flags) || flags.length === 0) return null;
  return (
    <details className="obs-inst-details" style={{ marginTop: 0 }}>
      <summary>
        <AlertTriangle size={14} style={{ color: "var(--warning)", flexShrink: 0 }} />
        Методологические оговорки ({flags.length}) — экспертные оценки Basis, не официальная статистика
        <ChevronDown size={15} className="obs-inst-chev" />
      </summary>
      <div className="obs-inst-details-body">
        {flags.map((f, i) => <p key={i}>{f}</p>)}
      </div>
    </details>
  );
}

const INSTITUTIONS_CLUSTERS = [
  { name: "Власть и право", icon: Gavel, keys: ["M1", "M2", "M4"] },
  { name: "Экономика и бюджет", icon: Coins, keys: ["M3", "M6", "M8", "M12"] },
  { name: "Государство и рынок", icon: Building2, keys: ["M7", "M9", "M10"] },
  { name: "Внешний контур и риски", icon: ShieldAlert, keys: ["M5", "M11"] },
];

const GEO_CLUSTERS = [
  { name: "Конфликт и урегулирование", icon: Swords, keys: ["G1", "G2"] },
  { name: "Санкции и контур капитала", icon: ShieldAlert, keys: ["G3", "G4", "G7", "G8"] },
  { name: "Военная экономика и торговля", icon: Coins, keys: ["G5", "G6", "G12"] },
  { name: "Геополитические оси", icon: Globe, keys: ["G9", "G10", "G11", "G13"] },
];

// «Внешние оси» — вспомогательная детализация внутри G1-G13 (вклад конкретных внешних
// игроков в общий балл). Владелец забраковал попытку решить региональность ТОЛЬКО через
// эти оси («всё намешано, СВО/Ближний Восток/АТР было не различить») — основной ответ
// теперь блок «regions» (см. GEO_REGION_META ниже), эти оси остаются как более
// техническая детализация ниже по экрану, не как замена явной разбивки.
const GEO_AXES = [
  { key: "G9", short: "Китай / Индия (АТР, Global South)" },
  { key: "G10", short: "США" },
  { key: "G11", short: "ЕС / Великобритания" },
  { key: "G13", short: "Глобальный фон (Ормуз, нефть, третьи страны)" },
];

// Явная разбивка по геополитическим очагам (backend/config/geo_barometer.json → regions),
// по прямому требованию владельца: «раздели явно, так понятно откуда какая гадость
// прилетит, на кого влияет и сколько продлится».
const GEO_REGION_META = [
  { key: "svo", label: "СВО", icon: Swords },
  { key: "middle_east", label: "Ближний Восток", icon: AlertTriangle },
  { key: "atr", label: "АТР", icon: Globe },
];

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
  const [digest, setDigest] = useState([]);
  const [digestLoading, setDigestLoading] = useState(true);
  const [rate, setRate] = useState(null);        // /macro/rate — ставка + сигнал ЦБ (факт)
  const [numbers, setNumbers] = useState([]);     // /macro — твёрдые числа для плитки (факт)
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  // Загружаем список аналитических записок один раз
  useEffect(() => {
    setLoading(true);
    fetch(`${apiUrl}/api/market/macro/analytics?limit=20`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => { setDocs(d || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [apiUrl]);

  // Твёрдые числа (не суждение LLM, а факт из БД): ставка + сигнал ЦБ на конкретную дату,
  // и 3-4 ключевых индикатора для плитки перед prose-интерпретацией.
  useEffect(() => {
    fetch(`${apiUrl}/api/market/macro/rate`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setRate(d))
      .catch(() => setRate(null));
    fetch(`${apiUrl}/api/market/macro`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setNumbers(Array.isArray(d) ? d : []))
      .catch(() => setNumbers([]));
  }, [apiUrl]);

  // Дайджест внешних источников с макро-уклоном (Economist Finance, ISW, Carnegie
  // (телеграм-каналы, только макро-тезисы — не геополитика/институты, см. geo_digest.py),
  // MarketTwits и др.)
  useEffect(() => {
    fetch(`${apiUrl}/api/market/macro/digest?limit=30`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setDigest(d.articles || []))
      .catch(() => setDigest([]))
      .finally(() => setDigestLoading(false));
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
    { id: "other", label: "Другие" },
  ];

  // Единый список: записки ЦБ/ЦМАКП (macro/analytics) + статьи внешних источников
  // (macro/digest: Economist, ISW, Carnegie, MarketTwits и др.) — раньше внешние
  // источники всегда рисовались отдельным блоком под записками ЦБ/ЦМАКП, без
  // сортировки по дате и без фильтра. Теперь один список, отсортированный по дате
  // публикации, с отдельным чипом «Другие» для внешних источников.
  const filteredItems = (() => {
    let items;
    if (srcFilter === "other") {
      items = digest.map((d) => ({ ...d, _kind: "digest" }));
    } else if (srcFilter === "all") {
      items = [
        ...docs.map((d) => ({ ...d, _kind: "doc" })),
        ...digest.map((d) => ({ ...d, _kind: "digest" })),
      ];
    } else {
      items = docs.filter((d) => d.source === srcFilter).map((d) => ({ ...d, _kind: "doc" }));
    }
    return items.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
  })();

  const itemsLoading = srcFilter === "other" ? digestLoading
    : srcFilter === "all" ? (loading || digestLoading)
    : loading;

  const interpSections = interp?.sections || null;
  const scenarios = interpSections?.scenarios;

  // Сигнал одной строкой: ставка сейчас + сигнал ЦБ — ФАКТ из БД (не суждение LLM).
  const rateHeadline = rate?.key_rate?.value != null
    ? `Ключевая ставка ${_fmtNum(rate.key_rate.value)}%${rate.key_rate.as_of ? ` (на ${rate.key_rate.as_of})` : ""}`
      + (rate.meeting?.signal ? ` · сигнал ЦБ: ${rate.meeting.signal}` : "")
    : null;

  // Плитка твёрдых чисел перед prose-интерпретацией — ФАКТ, не суждение.
  const MACRO_TILE_CODES = ["key_rate", "inflation", "gdp", "budget_balance"];
  const macroTiles = MACRO_TILE_CODES
    .map((code) => numbers.find((n) => n.code === code))
    .filter((n) => n && n.has_data)
    .map((ind) => {
      const preferYoy = ind.metric_types?.includes("yoy") && ind.values?.yoy;
      const metricKey = preferYoy ? "yoy" : (ind.metric_types || ["level"])[0];
      const v = ind.values?.[metricKey] || Object.values(ind.values || {})[0];
      return {
        code: ind.code,
        title: ind.title,
        valStr: v ? `${_fmtNum(v.value)}${ind.unit === "%" ? "%" : ` ${ind.unit || ""}`}` : "—",
        asOf: v?.as_of,
        change: v?.change,
      };
    });

  return (
    <div>
      <p className="obs-art-desc">
        «Обзор» — записки ЦБ, ЦМАКП и внешние источники (Economist, ISW, Carnegie и др.) как есть.
        «Оценка ситуации» — что из этого следует, по мнению Basis.
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

          {itemsLoading && (
            <div className="obs-news-loading">Загружаем аналитику…</div>
          )}

          {!itemsLoading && filteredItems.length === 0 && (
            <div className="obs-art-empty">
              {srcFilter === "other"
                ? "Свежих материалов из внешних источников пока нет."
                : "Нет документов для выбранного источника. Аналитические записки появятся здесь после публикации."}
            </div>
          )}

          <div className="obs-art-list">
            {filteredItems.map((item) => (
              item._kind === "digest"
                ? <ObsDigestCard key={`d-${item.id}`} a={item} />
                : <ObsArticleCard key={`a-${item.id}`} doc={item} />
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
                <div className="obs-inst-hero-eyebrow" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Clock size={13} />
                  Срез на {new Date(interp.generated_at).toLocaleString("ru-RU")}
                  {interp.model_used ? ` · ${interp.model_used}` : ""}
                  {" · оценка Basis, не факт и не рекомендация"}
                </div>
              )}

              {/* СИГНАЛ, строка 1: ставка сейчас + сигнал ЦБ — ФАКТ из БД, не суждение LLM */}
              {rateHeadline && (
                <div className="obs-macro-headline">
                  <span className="obs-tag-fact">факт</span>
                  <span>{rateHeadline}</span>
                </div>
              )}

              {/* СИГНАЛ, строка 2: headline — одно предложение-вердикт, не абзац */}
              {interpSections.headline && (
                <div className="obs-macro-card obs-macro-lede-card">
                  <div className="obs-macro-eyebrow"><Activity size={12} style={{ marginRight: 5, verticalAlign: -2 }} />Главный вывод · суждение Basis</div>
                  <p className="obs-macro-lede">{interpSections.headline}</p>
                </div>
              )}

              {/* ДОКАЗАТЕЛЬСТВО, шаг 1: плитка твёрдых чисел — ФАКТ */}
              {macroTiles.length > 0 && (
                <div className="obs-grid8" role="list" aria-label="Ключевые макропоказатели">
                  {macroTiles.map((t) => (
                    <div key={t.code} role="listitem" className="obs-tile" style={{ cursor: "default" }}>
                      <div className="obs-tile-lbl">{t.title}</div>
                      <div className="obs-tile-val">{t.valStr}</div>
                      {t.asOf && <div className="obs-tile-date">{t.asOf}</div>}
                    </div>
                  ))}
                </div>
              )}

              {/* ДОКАЗАТЕЛЬСТВО, шаг 2: тезисы — атомарные точки, ВИДИМЫ по умолчанию (не в details:
                  простыня была не в упаковке, а в связной прозе; список даёт 4-6 точек приземления) */}
              {Array.isArray(interpSections.theses) && interpSections.theses.length > 0 && (
                <div className="obs-inst-card">
                  <div className="obs-inst-card-title"><Sparkles size={16} />По пунктам</div>
                  <div className="obs-inst-list">
                    {interpSections.theses.map((t, i) => (
                      <div key={i} className="obs-inst-row">
                        <div className="obs-inst-row-main">
                          <div className="obs-inst-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            {t.topic}
                            <span className={t.tag === "факт" ? "obs-tag-fact" : "obs-tag-judgment"}>{t.tag || "оценка"}</span>
                          </div>
                          {t.claim && <div style={{ fontWeight: 600, fontSize: 13.5, marginTop: 2 }}>{t.claim}</div>}
                          {t.detail && <div className="obs-inst-row-why">{t.detail}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ДОКАЗАТЕЛЬСТВО, шаг 3: сектора — попутный/встречный ветер, тот же визуальный
                  словарь, что и sector_flags в геополитике (единое семейство барометров) */}
              {Array.isArray(interpSections.sectors) && interpSections.sectors.length > 0 && (
                <div className="obs-inst-card">
                  <div className="obs-inst-card-title"><BarChart2 size={16} />Рынок и сектора</div>
                  <div className="obs-inst-list">
                    {interpSections.sectors.map((s, i) => {
                      const neg = /встречный/i.test(s.wind || "");
                      const pos = /попутный/i.test(s.wind || "");
                      return (
                        <div key={i} className="obs-inst-row">
                          <div className="obs-inst-row-main">
                            <div className="obs-inst-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              {neg ? <TrendingDown size={14} style={{ color: "var(--danger)" }} /> : pos ? <TrendingUp size={14} style={{ color: "var(--success)" }} /> : null}
                              {s.sector}
                              <span style={{ fontSize: 11, fontWeight: 700, color: neg ? "var(--danger)" : pos ? "var(--success)" : "var(--text-tertiary)", textTransform: "uppercase" }}>· {s.wind}</span>
                            </div>
                            {s.channel && <div className="obs-inst-row-why">{s.channel}</div>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* ДЕЙСТВИЕ, шаг 0: на что смотреть дальше */}
              {Array.isArray(interpSections.watch) && interpSections.watch.length > 0 && (
                <div className="obs-inst-checkpoint">
                  <div className="obs-inst-checkpoint-label"><Info size={12} />На что смотреть дальше</div>
                  {interpSections.watch.map((w, i) => (
                    <div key={i} className="obs-inst-checkpoint-text">{w}</div>
                  ))}
                </div>
              )}

              {/* ДЕЙСТВИЕ: сценарии base/bull/bear */}
              {scenarios && (
                <div>
                  <div className="obs-synth-head" style={{ marginBottom: 14 }}>Сценарии</div>
                  <div className="obs-scenario-row">
                    {[
                      { key: "base", data: scenarios.base, title: "Базовый", cls: "" },
                      { key: "bull", data: scenarios.bull, title: "Бычий", cls: " obs-scenario-card--bull" },
                      { key: "bear", data: scenarios.bear, title: "Медвежий", cls: " obs-scenario-card--bear" },
                    ].map(({ key, data, title, cls }) =>
                      data ? (
                        <div key={key} className={`obs-scenario-card${cls}`}>
                          <div className="obs-scenario-title">{title}</div>
                          {data.probability && (
                            <>
                              <div className="obs-scenario-prob">вероятность: {data.probability}</div>
                              {obsParsePct(data.probability) > 0 && (
                                <div className="obs-scenario-probbar">
                                  <div className="obs-scenario-probbar-fill" style={{ width: `${obsParsePct(data.probability)}%` }} />
                                </div>
                              )}
                            </>
                          )}
                          {data.key_numbers && (
                            <div className="obs-scenario-num">{data.key_numbers}</div>
                          )}
                          {data.triggers && (
                            <div className="obs-scenario-trig">
                              <b>Триггеры</b>
                              {data.triggers}
                            </div>
                          )}
                        </div>
                      ) : null
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
// OBS GEO THEATER MAP — интерактивная карта очага («Оценка ситуации» →
// GEO_REGION_META карточка): линия фронта, удары, критическая инфраструктура,
// базы и войска, флот. Данные: GET /api/market/geo-map/{theater} →
// backend/config/geo_map_<theater>.json. Компонент театр-агностичен: если
// файла для очага ещё нет (404), рендерит null — новые очаги (Ближний
// Восток, АТР) появятся сами, без правки кода, когда появятся их файлы.
// =========================

const GEOMAP_TYPE_META = {
  front_shift:    { label: "Линия фронта",   icon: Swords    },
  strike:         { label: "Удары",          icon: Zap       },
  critical_infra: { label: "Инфраструктура", icon: Factory   },
  military_base:  { label: "Базы и войска",  icon: Building2 },
  fleet:          { label: "Флот",           icon: Anchor    },
};

// Театры, для которых базовый стиль тайлов ПРИНУДИТЕЛЬНО глушится по слоям
// подписей (source-layer "place") — открытые тайлы (OpenStreetMap/OpenMapTiles)
// подписывают украинские города на украинском (name:nonlatin), это НАПРЯМУЮ
// нарушает требование юрComplaince (см. память feedback_ru_market_legal_framing):
// названия городов на платформе — только на русском. Вместо подписей тайлов
// показываем ИСКЛЮЧИТЕЛЬНО свои waypoints (уже на русском). Ближний Восток/АТР —
// такого риска нет, подписи тайлов там остаются (богаче из коробки).
const GEOMAP_SUPPRESS_TILE_LABELS = new Set(["svo"]);

const GEOMAP_TILE_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

function readBasisMapColors() {
  const fallback = {
    ru: "#BE123C", contested: "#B45309", accent: "#C97A4A",
    textPrimary: "#1a1a1a", textSecondary: "#4a4a4a", bgElevated: "#ffffff",
  };
  if (typeof window === "undefined") return { ...fallback, token: (name, fb) => fb || "#888" };
  const cs = getComputedStyle(document.documentElement);
  const pick = (name, fb) => { const v = cs.getPropertyValue(name); return v && v.trim() ? v.trim() : fb; };
  return {
    ru: pick("--danger", fallback.ru),
    contested: pick("--warning", fallback.contested),
    accent: pick("--accent", fallback.accent),
    textPrimary: pick("--text-primary", fallback.textPrimary),
    textSecondary: pick("--text-secondary", fallback.textSecondary),
    bgElevated: pick("--bg-elevated", fallback.bgElevated),
    // Универсальный доступ к ЛЮБОМУ токену (--danger/--warning/--cat-1..8 и т.п.) —
    // нужен для choropleth-раскраски статуса контроля территории, где заранее
    // неизвестно, сколько control-ключей понадобится (СВО — 3, Ближний Восток —
    // уже 5, следующий очаг — своё число); см. controlColorToken() ниже.
    token: (name, fb) => pick(`--${name}`, fb || "#888"),
  };
}

// --- Choropleth-раскраска статуса control региона: раньше жёстко на 3 значения
// ("ru"/"contested"/"ua"), теперь по РЕАЛЬНОМУ набору ключей в
// base_map.control_legend конкретного очага — компонент остаётся
// театр-агностичным (СВО — 3 ключа, Ближний Восток — 5 после добавления
// "primary_adversary"/"us_base_host", следующий очаг — сколько угодно, без
// правки кода).
//
// Базовая тройка (ru/contested/ua) держит курируемые токены — ru/contested это
// уже устоявшееся легитимное применение семантики --danger/--warning к ФАКТУ на
// карте (не рыночному сигналу, см. комментарий у paint-эффекта ниже); ua —
// нейтральный --text-secondary (та же «приглушённая» роль, что уже была у ua
// исторически — bg-base+text-secondary+border), сознательно НЕ цветной: (1) не
// синий — --info в этом файле уже занят под эпистемический тег «оценка»
// (.obs-tag-estimate), в панели деталей региона тег контроля и тег «оценка»
// стоят РЯДОМ, одинаковый синий стёр бы разницу; (2) не --cat-8 (серый) — на
// белом фоне светлой темы контраст текста серый-на-белом ниже AA (~2.8:1),
// --text-secondary тут ощутимо контрастнее (>7:1) и это уже основной «нейтральный
// текст» токен продукта. Доп. ключи БВ курированы отдельно (пурпурный/бирюзовый —
// заведомо разные и от красно-жёлтой пары, и от серого/синего). Любой
// НЕИЗВЕСТНЫЙ ключ будущего очага детерминированно получает следующий свободный
// слот categorical Okabe-Ito палитры (--cat-*, colorblind-safe) — легитимное
// применение категориальной палитры: control региона — данные (категория), не хром.
const CONTROL_COLOR_CURATED = {
  ru: "danger",
  contested: "warning",
  ua: "text-secondary",
  primary_adversary: "cat-7",
  us_base_host: "cat-3",
};
const CONTROL_CAT_FALLBACK_SLOTS = [1, 2, 4, 5, 6]; // без 3/7/8 — уже раздано выше

function controlColorToken(key, allKeys) {
  if (CONTROL_COLOR_CURATED[key]) return CONTROL_COLOR_CURATED[key];
  const others = (allKeys || []).filter((k) => !CONTROL_COLOR_CURATED[k]).sort();
  const idx = Math.max(0, others.indexOf(key));
  return `cat-${CONTROL_CAT_FALLBACK_SLOTS[idx % CONTROL_CAT_FALLBACK_SLOTS.length]}`;
}

function controlColorHex(colors, key, allKeys) {
  return colors.token ? colors.token(controlColorToken(key, allKeys), "#888") : "#888";
}

function controlSoftColorHex(colors, key, allKeys) {
  const base = controlColorToken(key, allKeys);
  return colors.token ? colors.token(`${base}-soft`, "rgba(136,136,136,0.14)") : "rgba(136,136,136,0.14)";
}

// --- Fill/line-opacity по ключу control: дефолт красит ЛЮБОЙ ключ (~0.3 заливка
// /~0.85 линия — как раньше у "ru"), кроме явно обнулённых в
// base_map.control_paint_opacity очага (сейчас — только "ua" в СВО: регионы «под
// контролем Украины» сознательно не красим, юр./редакционное решение владельца,
// см. комментарий у paint-эффекта). ru/contested держат исторические точные числа
// (0.3/0.26 заливка, 0.85/0.7 линия), чтобы не менять уже принятый вид карты СВО.
const CONTROL_FILL_OPACITY_DEFAULTS = { ru: 0.3, contested: 0.26 };
const CONTROL_LINE_OPACITY_DEFAULTS = { ru: 0.85, contested: 0.7 };
const CONTROL_FILL_OPACITY_FALLBACK = 0.3;
const CONTROL_LINE_OPACITY_FALLBACK = 0.85;

function controlFillOpacity(key, overrides) {
  if (overrides && Object.prototype.hasOwnProperty.call(overrides, key)) return overrides[key];
  if (Object.prototype.hasOwnProperty.call(CONTROL_FILL_OPACITY_DEFAULTS, key)) return CONTROL_FILL_OPACITY_DEFAULTS[key];
  return CONTROL_FILL_OPACITY_FALLBACK;
}

function controlLineOpacity(key, overrides) {
  if (overrides && Object.prototype.hasOwnProperty.call(overrides, key)) return overrides[key];
  if (Object.prototype.hasOwnProperty.call(CONTROL_LINE_OPACITY_DEFAULTS, key)) return CONTROL_LINE_OPACITY_DEFAULTS[key];
  return CONTROL_LINE_OPACITY_FALLBACK;
}

// Пилюля-тег статуса контроля в панели деталей региона — та же логика «честно
// показываем, как оно красится на карте», что и у образца легенды: если ключ у
// этого очага обнулён (сейчас только "ua" в СВО), тег выглядит «пустым»
// (обводка, без заливки), не изображает цвет, которого на карте нет.
function controlTagStyle(colors, key, allKeys, paintOverrides) {
  const painted = controlFillOpacity(key, paintOverrides) > 0;
  if (!painted) {
    return { background: "var(--bg-base)", color: "var(--text-secondary)", border: "1px solid var(--border-subtle)" };
  }
  return { background: controlSoftColorHex(colors, key, allKeys), color: controlColorHex(colors, key, allKeys) };
}

// Токены дизайн-системы — реальные hex по текущей теме (MapLibre paint не умеет
// читать var(--...) напрямую). Пересчитываем при смене темы (MutationObserver
// на data-theme/class <html>), а НЕ хардкодим — единый источник по-прежнему
// styles/tokens.css.
function useBasisMapColors() {
  const [colors, setColors] = useState(readBasisMapColors);
  useEffect(() => {
    const obs = new MutationObserver(() => setColors(readBasisMapColors()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });
    return () => obs.disconnect();
  }, []);
  return colors;
}

function geomapAspect(bounds) {
  if (!bounds) return 1.5;
  const [[minLon, minLat], [maxLon, maxLat]] = bounds;
  const midLat = (minLat + maxLat) / 2;
  const dLon = (maxLon - minLon) * Math.cos((midLat * Math.PI) / 180);
  const dLat = maxLat - minLat;
  const raw = dLat > 0 ? dLon / dLat : 1.5;
  return Math.min(2.3, Math.max(1.05, raw));
}

const GEOMAP_EMPTY_FC = { type: "FeatureCollection", features: [] };
// Общий стабильный fallback для control_legend/control_paint_opacity, когда их
// нет в данных очага — ОДИН и тот же объект-ссылка на каждом рендере (не новый
// {} каждый раз), иначе useMemo/useEffect ниже, завязанные на его identity,
// пересчитывались бы на КАЖДЫЙ рендер компонента, а не только при смене данных.
const GEOMAP_EMPTY_OBJ = {};

function ObsGeoTheaterMap({ theaterKey, regionLabel, token, direction, directionColor }) {
  const [status, setStatus] = useState("loading"); // loading | ready | empty
  const [data, setData] = useState(null);
  const [activeType, setActiveType] = useState("all");
  // Единый выбор: либо маркер события, либо область карты — { kind: "event"|"region", key }.
  // Если открыты оба одновременно, приоритет у маркера (он визуально поверх области,
  // клик по нему просто не долетает до заливки региона под ним).
  const [selected, setSelected] = useState(null);
  // "theater" — основная карта очага (СВО и т.п.); "russia" — доп. карта всей России
  // целиком для ударов вглубь — переключатель рядом с фильтрами, независим от
  // фильтра по типу события. Один и тот же экземпляр MapLibre живёт между
  // переключениями — просто подменяем данные источников и перелетаем к новым bounds.
  const [activeMap, setActiveMap] = useState("theater");
  const [styleLoaded, setStyleLoaded] = useState(false);
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef([]); // [{ id, marker, root, el }]
  // MapLibre-квирк: маркер-кнопка лежит поверх канваса, но у САМОГО ПЕРВОГО клика
  // после загрузки карты браузер иногда резолвит mousedown на канвас, а mouseup —
  // уже на кнопку; итоговый синтетический "click" достаётся их общему предку
  // (canvasContainer), и клик по маркеру ошибочно долетает до клика по региону под
  // ним (проверено: воспроизводится стабильно на первом клике, ловится флагом —
  // маркер сам обрабатывает через надёжный pointerup, а не через "click").
  const suppressNextRegionClickRef = useRef(false);
  const prevActiveMapRef = useRef(activeMap);
  const colors = useBasisMapColors();
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    let cancelled = false;
    setStatus("loading");
    setSelected(null);
    setActiveType("all");
    setActiveMap("theater");
    fetch(`${apiUrl}/api/market/geo-map/${theaterKey}`, { headers: authHeaders })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { if (!cancelled) { setData(d); setStatus("ready"); } })
      .catch(() => { if (!cancelled) setStatus("empty"); });
    return () => { cancelled = true; };
  }, [theaterKey, apiUrl]);

  const russiaMap = data?.russia_wide_map || null;
  const onRussiaMap = activeMap === "russia" && !!russiaMap;
  const activeBaseMap = data ? (onRussiaMap ? russiaMap.base_map : data.base_map) : null;
  const controlLegend = data?.base_map?.control_legend || GEOMAP_EMPTY_OBJ;
  // Не у каждого очага есть смысл «статус контроля территории» (СВО — да; Ближний
  // Восток/АТР — нет единого понятия «чья территория», там страны/акватории со своим
  // суверенитетом) — choropleth-легенду и тег контроля показываем только если сами
  // данные очага реально несут control_legend, не по умолчанию для любого театра.
  const controlLegendKeys = useMemo(() => Object.keys(controlLegend), [controlLegend]);
  const hasControlLegend = controlLegendKeys.length > 0;
  const controlPaintOverrides = data?.base_map?.control_paint_opacity || GEOMAP_EMPTY_OBJ;

  const regionsFC = activeBaseMap?.regions_geojson || GEOMAP_EMPTY_FC;
  // Линия фронта — отдельная явная линия (не только заливка регионов статусом
  // контроля): реконструирована как граница между агрегированной зоной ru+contested
  // и зоной ua (см. backend, shapely boundary intersection по районам до слияния в
  // области) — «где именно проходит» видно отдельно от «чей регион в целом».
  const frontlineFC = (!onRussiaMap && activeBaseMap?.frontline_geojson) || GEOMAP_EMPTY_FC;

  const regionsBySlug = useMemo(() => {
    const m = {};
    regionsFC.features.forEach((f) => { m[f.properties.slug] = f.properties; });
    return m;
  }, [regionsFC]);
  // Маркеры событий (в т.ч. ударов вглубь России) показываем ВСЕГДА, не только
  // после переключения на «Россия целиком» (владелец: «без нажатия кнопки должны
  // отображаться удары вглубь») — переключатель ниже теперь влияет только на то,
  // какой набор РЕГИОНОВ (закраска очага vs субъекты РФ) активен, реальная карта
  // не заперта «режимами», события/маркеры доступны панорамированием как на
  // обычной карте. Комбинируем waypoints и events обоих наборов (слаги не
  // пересекаются между театром и Россией целиком).
  const waypointsBySlug = useMemo(() => {
    const m = {};
    (data?.base_map?.waypoints_geojson?.features || []).forEach((f) => { m[f.properties.slug] = { ...f.properties, coords: f.geometry.coordinates }; });
    (russiaMap?.base_map?.waypoints_geojson?.features || []).forEach((f) => { m[f.properties.slug] = { ...f.properties, coords: f.geometry.coordinates }; });
    return m;
  }, [data, russiaMap]);

  const events = useMemo(
    () => [...(Array.isArray(data?.events) ? data.events : []), ...(Array.isArray(russiaMap?.events) ? russiaMap.events : [])],
    [data, russiaMap]
  );
  const onMapEvents = useMemo(
    () => events.filter((e) => e.waypoint && waypointsBySlug[e.waypoint]),
    [events, waypointsBySlug]
  );
  const typeOk = (t) => activeType === "all" || activeType === t;

  const selectEvent = useCallback(
    (id) => setSelected((prev) => (prev?.kind === "event" && prev.key === id ? null : { kind: "event", key: id })),
    []
  );
  const selectRegion = useCallback(
    (slug) => setSelected((prev) => (prev?.kind === "region" && prev.key === slug ? null : { kind: "region", key: slug })),
    []
  );
  const closeDetail = () => setSelected(null);

  const selectedEvent = selected?.kind === "event" ? events.find((e) => e.id === selected.key) : null;
  const selectedRegion = selected?.kind === "region" ? regionsBySlug[selected.key] : null;

  // --- Инициализация MapLibre: один раз, когда данные готовы и контейнер смонтирован.
  useEffect(() => {
    if (status !== "ready" || !data?.base_map?.bounds || !containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: GEOMAP_TILE_STYLE_URL,
      bounds: data.base_map.bounds,
      fitBoundsOptions: { padding: 16 },
      attributionControl: false,
      dragRotate: false,
      touchPitch: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
    mapRef.current = map;

    map.on("load", () => {
      // Тайлы (OpenStreetMap/OpenMapTiles) подписывают населённые пункты в т.ч.
      // на украинском (name:nonlatin) — юридический риск для платформы, работающей
      // в РФ (см. память feedback_ru_market_legal_framing). Для СВО глушим ВСЕ
      // подписи слоя "place" из тайлов и полагаемся только на свои waypoints
      // (уже на русском) — для Ближнего Востока/АТР такого риска нет, оставляем.
      if (GEOMAP_SUPPRESS_TILE_LABELS.has(theaterKey)) {
        // Не глушим слой подписей целиком (владелец: «городов очень мало, ты не
        // можешь спарсить города?») — у тайлов OpenMapTiles/OSM ЕСТЬ отдельное
        // поле name:ru почти для всех городов/посёлков/сёл (проверено: 95-100%
        // покрытие по классам city/town/village) — переключаем сами подписи на
        // него вместо name/name:nonlatin (украинская кириллица) и добавляем
        // фильтр "есть name:ru" — там, где поля нет (редкое исключение), место
        // просто не подписывается, а не подставляется украинское название.
        map.getStyle().layers.forEach((l) => {
          if (l["source-layer"] === "place") {
            map.setLayoutProperty(l.id, "text-field", ["get", "name:ru"]);
            const existingFilter = l.filter || ["all"];
            map.setFilter(l.id, ["all", existingFilter, ["has", "name:ru"]]);
          }
        });
        // OSM/OpenMapTiles рисуют границу Крыма и новых территорий отдельным
        // пунктирным слоем boundary_disputed (свойство disputed=1 в исходных
        // данных) — визуально это читается как «спорная территория», что
        // противоречит нашей же закраске этих регионов как российских (см.
        // feedback_ru_market_legal_framing). Глушим сам пунктир — наш выбор
        // здесь однозначен (регионы закрашены statusом "ru"), лишняя
        // пунктирная линия только подрывает эту однозначность.
        map.getStyle().layers.forEach((l) => {
          if (l.id === "boundary_disputed") map.setLayoutProperty(l.id, "visibility", "none");
        });
      }

      map.addSource("regions", { type: "geojson", data: GEOMAP_EMPTY_FC });
      map.addSource("regions-active", { type: "geojson", data: GEOMAP_EMPTY_FC });
      map.addSource("frontline", { type: "geojson", data: GEOMAP_EMPTY_FC });

      // Choropleth статуса контроля — факт «чья территория», не рыночный сигнал
      // good/bad (легитимное применение --danger/--warning к данным, см. конституцию).
      // Заливка полупрозрачная и только там, где есть control_legend — иначе (карта
      // России целиком, где такого понятия нет) слой невидим, служит только
      // кликабельной областью для подписи региона в детали-панели.
      map.addLayer({ id: "regions-fill", type: "fill", source: "regions", paint: { "fill-color": "#888", "fill-opacity": 0 } });
      map.addLayer({ id: "regions-line", type: "line", source: "regions", paint: { "line-color": "#888", "line-opacity": 0, "line-width": 1.1 } });
      // Линия фронта — САМА линия боевого соприкосновения, отдельно от заливки
      // регионов (владелец: «где линия фронта? сейчас просто регионы закрашены»).
      // Двухслойная линия (подложка толще+бледнее, поверх тоньше+ярче) — читаемый
      // приём для «зазубренной» боевой линии на карте, не сливается с дорогами тайла.
      map.addLayer({ id: "frontline-casing", type: "line", source: "frontline", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colors.ru, "line-opacity": 0.35, "line-width": 5 } });
      map.addLayer({ id: "frontline-line", type: "line", source: "frontline", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": colors.ru, "line-width": 2, "line-dasharray": [2, 1.4] } });
      map.addLayer({ id: "regions-active-line", type: "line", source: "regions-active", paint: { "line-color": colors.accent, "line-width": 2.4 } });
      // Свои waypoints-dot/label слои убраны (2026-07-23) — у тайла (после
      // переключения на name:ru выше) уже полное покрытие городов/сёл на
      // русском лучше, чем наш ручной набор из ~20 точек; waypoints остаются
      // только JS-справочником координат для маркеров событий, без своего
      // визуального слоя (не дублируем подписи тайла).

      map.on("mouseenter", "regions-fill", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "regions-fill", () => { map.getCanvas().style.cursor = ""; });
      map.on("click", "regions-fill", (e) => {
        if (suppressNextRegionClickRef.current) { suppressNextRegionClickRef.current = false; return; }
        const slug = e.features?.[0]?.properties?.slug;
        if (slug) selectRegion(slug);
      });
    });

    // "load" стреляет сразу после разбора стиля/источников — камера (bounds→fitBounds
    // конструктора) в этот момент ещё может быть не устаканена, и maplibregl.Marker,
    // созданный ДО этого, считает свою экранную позицию по незавершённому transform —
    // маркеры событий физически создаются, но невидимы (нулевые/случайные координаты)
    // до следующего пересоздания. Воспроизводилось стабильно на свежем монтировании
    // карты (первый заход на «Оценка ситуации»): фильтр «Все» — 0 маркеров, любой
    // клик по чипу-фильтру (пересоздаёт маркеры) — маркеры появляются корректно.
    // "idle" — гарантированно после того, как рендер и начальная камера устаканились.
    map.once("idle", () => setStyleLoaded(true));

    return () => { markersRef.current.forEach(({ marker, root }) => { root.unmount(); marker.remove(); }); markersRef.current = []; map.remove(); mapRef.current = null; };
  }, [status, theaterKey]);

  // --- Синхронизация данных источников + раскраски при смене очага/России/фильтра/темы.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    map.getSource("regions")?.setData(regionsFC);
    map.getSource("frontline")?.setData(frontlineFC);
    // Красим ПО ФИЧЕ (control: <ключ>), не блоком «весь набор регионов либо
    // красим, либо нет» — на карте «Россия целиком» у большинства регионов
    // control нет вовсе (нейтральны), но у Крыма/ДНР/ЛНР/новых областей он ЕСТЬ
    // ("ru") — владелец: «границы проведены как будто эти регионы украинские,
    // надо чтобы было видно, что российские» — сплошная закраска снимает
    // двусмысленность независимо от того, как тайл рисует границу под низом.
    // Набор ключей — ЛЮБОЕ число, реально присутствующее в control_legend очага
    // (СВО — 3, Ближний Восток — 5 после primary_adversary/us_base_host, следующий
    // очаг — сколько угодно, без правки кода); opacity по ключу можно явно
    // обнулить через base_map.control_paint_opacity (сейчас только "ua" в СВО —
    // регионы «под контролем Украины» сознательно не красим, это НЕ трогать).
    let fillColor = "#888";
    let fillOpacity = 0;
    let lineOpacity = 0;
    if (controlLegendKeys.length) {
      const colorArgs = [];
      const fillOpArgs = [];
      const lineOpArgs = [];
      controlLegendKeys.forEach((key) => {
        colorArgs.push(key, controlColorHex(colors, key, controlLegendKeys));
        fillOpArgs.push(key, controlFillOpacity(key, controlPaintOverrides));
        lineOpArgs.push(key, controlLineOpacity(key, controlPaintOverrides));
      });
      fillColor = ["match", ["get", "control"], ...colorArgs, "#888"];
      fillOpacity = ["match", ["get", "control"], ...fillOpArgs, 0];
      lineOpacity = ["match", ["get", "control"], ...lineOpArgs, 0];
    }
    map.setPaintProperty("regions-fill", "fill-color", fillColor);
    map.setPaintProperty("regions-fill", "fill-opacity", fillOpacity);
    map.setPaintProperty("regions-line", "line-color", fillColor);
    map.setPaintProperty("regions-line", "line-opacity", lineOpacity);
    map.setPaintProperty("regions-active-line", "line-color", colors.accent);
    map.setPaintProperty("frontline-casing", "line-color", colors.ru);
    map.setPaintProperty("frontline-line", "line-color", colors.ru);
  }, [styleLoaded, regionsFC, frontlineFC, colors, controlLegendKeys, controlPaintOverrides]);

  // --- Перелёт к новым bounds при переключении «очаг ↔ Россия целиком» (не на
  // самой первой загрузке стиля — тот перелёт уже сделан конструктором карты).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    if (prevActiveMapRef.current !== activeMap) {
      prevActiveMapRef.current = activeMap;
      if (activeBaseMap?.bounds) map.fitBounds(activeBaseMap.bounds, { padding: 24, duration: 600 });
    }
  }, [styleLoaded, activeMap]);

  // --- Маркеры событий (HTML/React-иконки поверх канваса через maplibregl.Marker —
  // сама библиотека держит их позицию в px синхронно с пан/зумом карты, ручной
  // пересчёт процентов больше не нужен). Пересобираем при смене набора видимых
  // событий (очаг/Россия, фильтр по типу) — состояние «выбрано» красим отдельно.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    markersRef.current.forEach(({ marker, root }) => { root.unmount(); marker.remove(); });
    markersRef.current = [];

    const grouped = new Map();
    onMapEvents.filter((e) => typeOk(e.type)).forEach((e) => {
      if (!grouped.has(e.waypoint)) grouped.set(e.waypoint, []);
      grouped.get(e.waypoint).push(e);
    });

    grouped.forEach((evs, wpKey) => {
      const wp = waypointsBySlug[wpKey];
      if (!wp) return;
      evs.forEach((ev, i) => {
        const offsetX = (i - (evs.length - 1) / 2) * 22;
        const meta = GEOMAP_TYPE_META[ev.type];
        const Icon = meta?.icon || AlertTriangle;
        const el = document.createElement("button");
        el.type = "button";
        el.className = `obs-geomap-marker${ev.stale ? " obs-geomap-marker--stale" : ""}`;
        el.setAttribute("aria-label", `${meta?.label || ev.type}: ${ev.label}`);
        el.setAttribute("aria-pressed", "false");
        el.title = `${meta?.label || ev.type}: ${ev.label}`;
        // pointerup — надёжный сигнал и для мыши, и для тача (см. комментарий у
        // suppressNextRegionClickRef); "click" оставлен только для клавиатурной
        // активации (Enter/Space на сфокусированной кнопке — evt.detail === 0 у
        // синтетического клика без реального указателя, у мыши/тача всегда >= 1).
        el.addEventListener("pointerup", (evt) => {
          suppressNextRegionClickRef.current = true;
          evt.stopPropagation();
          selectEvent(ev.id);
        });
        el.addEventListener("click", (evt) => {
          evt.stopPropagation();
          if (evt.detail === 0) selectEvent(ev.id);
        });
        const root = createRoot(el);
        root.render(<Icon size={13} aria-hidden="true" />);
        const marker = new maplibregl.Marker({ element: el, offset: [offsetX, 0] }).setLngLat(wp.coords).addTo(map);
        markersRef.current.push({ id: ev.id, marker, root, el });
      });
    });
  }, [styleLoaded, onMapEvents, activeType, waypointsBySlug]);

  // --- Визуальное состояние «выбрано» — маркер события (класс на элементе,
  // без пересборки) и контур области (отдельный источник regions-active).
  useEffect(() => {
    markersRef.current.forEach(({ id, el }) => {
      const active = selected?.kind === "event" && selected.key === id;
      el.classList.toggle("obs-geomap-marker--active", active);
      el.setAttribute("aria-pressed", String(active));
    });
  }, [selected]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !styleLoaded) return;
    const src = map.getSource("regions-active");
    if (!src) return;
    if (selected?.kind === "region") {
      const feat = regionsFC.features.find((f) => f.properties.slug === selected.key);
      src.setData(feat ? { type: "FeatureCollection", features: [feat] } : GEOMAP_EMPTY_FC);
    } else {
      src.setData(GEOMAP_EMPTY_FC);
    }
  }, [styleLoaded, selected, regionsFC]);

  const zoomIn = () => mapRef.current?.zoomIn({ duration: 200 });
  const zoomOut = () => mapRef.current?.zoomOut({ duration: 200 });
  const resetView = () => { if (activeBaseMap?.bounds) mapRef.current?.fitBounds(activeBaseMap.bounds, { padding: 24, duration: 400 }); };

  // Осознанное отсутствие данных (карта для этого очага ещё не собрана) —
  // молча ничего не рендерим, никакого «ошибка загрузки». Хуки выше должны
  // отработать безусловно на каждый рендер (Rules of Hooks) — сам bail-out
  // строго после них.
  if (status !== "ready" || !data || !data.base_map) return null;

  const aspect = geomapAspect(activeBaseMap?.bounds);

  return (
    <div className="obs-inst-card obs-geomap">
      <div className="obs-geomap-head">
        <div className="obs-geomap-title">
          <Layers size={14} aria-hidden="true" />
          {onRussiaMap
            ? "Удары вглубь России — вся территория"
            : `Карта${regionLabel ? `: ${regionLabel}` : " очага"} — ${hasControlLegend ? "контроль территории, удары, инфраструктура" : "обстановка, манёвры, инфраструктура"}`}
        </div>
        {!onRussiaMap && direction && (
          <span className="obs-region-card-dir" style={{ color: directionColor, borderColor: directionColor }}>{direction}</span>
        )}
        {data.as_of && <span className="obs-geomap-asof">срез на {data.as_of}</span>}
      </div>

      {!onRussiaMap && data.territorial_change && (() => {
        const tc = data.territorial_change;
        const valueLabel = tc.km2_range ? `${tc.km2_range[0]}–${tc.km2_range[1]}` : tc.km2_value;
        return (
          <div className="obs-geomap-territorial-stat" title={tc.note}>
            <TrendingDown size={13} aria-hidden="true" />
            <span className="obs-geomap-territorial-value">{valueLabel} км²/мес</span>
            <span className="obs-tag-estimate">оценка</span>
            {tc.trend && <span className="obs-geomap-territorial-trend">{tc.trend}</span>}
          </div>
        );
      })()}

      {!onRussiaMap && data.front_line_summary && <p className="obs-geomap-prose">{data.front_line_summary}</p>}

      <div className="obs-geomap-filterbar">
        <button
          type="button"
          className={`obs-chip${activeType === "all" ? " obs-chip--active" : ""}`}
          onClick={() => setActiveType("all")}
        >Все</button>
        {Object.entries(GEOMAP_TYPE_META).map(([type, meta]) => (
          <button
            key={type}
            type="button"
            className={`obs-chip${activeType === type ? " obs-chip--active" : ""}`}
            onClick={() => setActiveType(type)}
          >{meta.label}</button>
        ))}
        {russiaMap && (
          <button
            type="button"
            className={`obs-chip obs-geomap-russia-toggle${onRussiaMap ? " obs-chip--active" : ""}`}
            onClick={() => { setActiveMap((m) => (m === "russia" ? "theater" : "russia")); setSelected(null); }}
          >
            <Globe size={12} aria-hidden="true" /> {onRussiaMap ? "← Вернуться к очагу" : "Карта России целиком"}
          </button>
        )}
      </div>

      <div className="obs-geomap-frame" style={{ aspectRatio: aspect }}>
        <div className="obs-geomap-maplibre" ref={containerRef} />
        <div className="obs-geomap-zoomctl">
          <button type="button" onClick={zoomIn} aria-label="Приблизить"><ZoomIn size={14} /></button>
          <button type="button" onClick={zoomOut} aria-label="Отдалить"><ZoomOut size={14} /></button>
          <button type="button" onClick={resetView} aria-label="Сбросить масштаб"><Maximize2 size={13} /></button>
        </div>
      </div>

      {activeBaseMap.note && (
        <p className="obs-geomap-method-note"><Info size={11} aria-hidden="true" />{activeBaseMap.note}</p>
      )}

      <div className="obs-geomap-legend">
        {!onRussiaMap && hasControlLegend && (
          <div className="obs-geomap-legend-group">
            {controlLegendKeys.map((c) => {
              // Образец легенды честно повторяет то, КАК ключ реально красится на
              // карте (см. paint-эффект выше): если для очага/ключа fill-opacity
              // обнулена (сейчас только "ua" в СВО) — образец тоже «пустой»
              // (обводка без заливки), а не врёт цветом, которого на карте нет.
              const painted = controlFillOpacity(c, controlPaintOverrides) > 0;
              const hex = controlColorHex(colors, c, controlLegendKeys);
              const swatchStyle = painted
                ? { background: hex, opacity: 0.6, border: `1px solid ${hex}` }
                : { background: "var(--bg-surface)", border: "1px solid var(--border-subtle)" };
              return (
                <span key={c} className="obs-geomap-legend-item">
                  <span className="obs-geomap-legend-swatch" style={swatchStyle} aria-hidden="true" />
                  {controlLegend[c] || c}
                </span>
              );
            })}
          </div>
        )}
        <div className="obs-geomap-legend-group">
          {Object.entries(GEOMAP_TYPE_META).map(([type, meta]) => (
            <span key={type} className="obs-geomap-legend-item"><meta.icon size={12} aria-hidden="true" />{meta.label}</span>
          ))}
          <span className="obs-geomap-legend-item obs-geomap-legend-item--muted">
            <span className="obs-geomap-legend-dot" aria-hidden="true" />Ориентир на карте
          </span>
        </div>
      </div>

      {!onRussiaMap && data.black_sea_fleet_summary && <p className="obs-geomap-prose">{data.black_sea_fleet_summary}</p>}

      {selectedEvent && (
        <div className="obs-geomap-detail" role="region" aria-label="Детали события на карте">
          <button type="button" className="obs-geomap-detail-close" onClick={closeDetail} aria-label="Закрыть детали">
            <X size={14} />
          </button>
          <div className="obs-geomap-detail-head">
            {(() => {
              const M = GEOMAP_TYPE_META[selectedEvent.type]?.icon || AlertTriangle;
              return <M size={15} aria-hidden="true" />;
            })()}
            <span className="obs-geomap-detail-type">{GEOMAP_TYPE_META[selectedEvent.type]?.label || selectedEvent.type}</span>
            <span className={selectedEvent.epistemic === "оценка" ? "obs-tag-estimate" : "obs-tag-fact"}>
              {selectedEvent.epistemic || "факт"}
            </span>
            {selectedEvent.confidence && (
              <span className="obs-geomap-confidence">confidence {selectedEvent.confidence}</span>
            )}
            {selectedEvent.stale && (
              <span className="obs-geomap-stale-badge"><AlertTriangle size={11} aria-hidden="true" />нет свежих данных</span>
            )}
          </div>
          <h4 className="obs-geomap-detail-title">{selectedEvent.label}</h4>
          {selectedEvent.description && <p className="obs-geomap-detail-desc">{selectedEvent.description}</p>}
          {selectedEvent.note && <p className="obs-geomap-detail-note">{selectedEvent.note}</p>}
          <div className="obs-geomap-detail-foot">
            {selectedEvent.date && <span>{selectedEvent.date}</span>}
            {selectedEvent.source && (
              selectedEvent.source_url
                ? <a href={selectedEvent.source_url} target="_blank" rel="noreferrer">{selectedEvent.source} ↗</a>
                : <span>{selectedEvent.source}</span>
            )}
          </div>
        </div>
      )}

      {selectedRegion && (
        <div className="obs-geomap-detail" role="region" aria-label="Детали региона на карте">
          <button type="button" className="obs-geomap-detail-close" onClick={closeDetail} aria-label="Закрыть детали">
            <X size={14} />
          </button>
          <div className="obs-geomap-detail-head">
            <Layers size={15} aria-hidden="true" />
            {/* "context" — регионы вроде Краснодарского края (даёт географический контекст
                событию рядом, но сам не часть вопроса контроля территории СВО) — тег статуса
                для них не показываем вовсе, а не подсовываем ложное "под контролем Украины".
                Условие теперь смотрит на РЕАЛЬНЫЙ набор ключей control_legend очага (не на
                зашитую тройку "ru"/"contested"/"ua") — Ближний Восток отдаёт тег и для
                "primary_adversary"/"us_base_host" тоже. */}
            {hasControlLegend && Object.prototype.hasOwnProperty.call(controlLegend, selectedRegion.control) && (
              <>
                <span
                  className="obs-geomap-region-tag"
                  style={controlTagStyle(colors, selectedRegion.control, controlLegendKeys, controlPaintOverrides)}
                >
                  {controlLegend[selectedRegion.control] || selectedRegion.control}
                </span>
                {/* Статус контроля — классификация Basis, не всегда бесспорный факт (см.
                    data_flags: Луганск и др. — предмет спора сторон) — эпистемический тег
                    обязателен на каждом аналитическом утверждении, как у событий выше. */}
                <span className="obs-tag-estimate">оценка</span>
                {selectedRegion.control_confidence && (
                  <span className="obs-geomap-confidence">confidence {selectedRegion.control_confidence}</span>
                )}
              </>
            )}
          </div>
          <h4 className="obs-geomap-detail-title">{selectedRegion.name_ru}</h4>
          {selectedRegion.control_note && <p className="obs-geomap-detail-desc">{selectedRegion.control_note}</p>}
        </div>
      )}

      <ObsBaroCaveat flags={data.data_flags} />
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
  const [geoHorizon, setGeoHorizon] = useState("6m"); // 6m | 18m — переключатель горизонта сценариев
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

      {/* Фильтр регионов — относится ТОЛЬКО к «Обзору» (лента фактов по региону).
          Барометр «Оценка ситуации» — единый показатель на весь рынок, регион-независимый;
          поэтому чипы скрыты в этом режиме (см. пояснение ниже), чтобы не создавать
          ложное впечатление, будто барометр можно фильтровать по региону. */}
      {mode === "overview" && regions.length > 0 && (
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

      {mode === "assessment" && (
        <div className="obs-baro-note">
          <Info size={14} />
          <span>Барометр ниже — <b>единый показатель для российского рынка в целом</b>, не разбит по регионам (СВО / Ближний Восток / АТР — это оси одного барометра, G9–G11). Фильтр по региону выше относится только к ленте фактов на вкладке «Обзор».</span>
        </div>
      )}

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
              {!baroLoading && baro && (() => {
                const subMap = {};
                (baro.subindices || []).forEach((s) => { subMap[s.key] = s; });
                const horizon = geoHorizon;
                const probs = horizon === "18m" ? baro.scenario?.probabilities_18m : baro.scenario?.probabilities_6m;
                const GEO_SCEN_LABELS = {
                  S1_breakthrough: "S1 · Прорыв к миру",
                  S2_ceasefire: "S2 · Перемирие",
                  S3_attrition: "S3 · Затяжная война",
                  S4_escalation: "S4 · Эскалация",
                };
                const ladderItems = Object.entries(probs || {}).map(([k, v]) => ({
                  key: k,
                  label: GEO_SCEN_LABELS[k] || k,
                  pct: obsParsePct(v),
                }));
                const currentMatch = String(baro.scenario?.current_lean || "").match(/S[1-4]/);
                const currentKey = currentMatch ? ladderItems.find((it) => it.key.startsWith(currentMatch[0]))?.key : null;

                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <ObsBaroCaveat flags={baro.data_flags} />

                    <ObsBaroHero
                      eyebrow="Геополитический барометр · оценка Basis"
                      asOf={baro.as_of}
                      score={baro.barometer?.overall}
                      verdict={baro.barometer?.label}
                      polarity="higherWorse"
                      scaleLabels={["низкий риск", "высокий риск"]}
                      subindices={baro.subindices}
                    />

                    {/* Явная разбивка по очагам — владелец прямо попросил разделить
                        (единый барометр читался как «всё замешано», СВО/Ближний Восток/АТР
                        было не различить). Три самостоятельные мини-оценки: откуда угроза,
                        куда движется, кого касается, сколько продлится. Общий барометр выше
                        остаётся агрегатом (SVO доминирует по весу), это — детализация. */}
                    {baro.regions && (
                      <div>
                        <div className="obs-synth-head" style={{ marginBottom: 14 }}>По очагам: откуда, на кого и насколько долго</div>
                        <div className="obs-region-grid">
                          {GEO_REGION_META.map(({ key, label, icon: Icon }) => {
                            const r = baro.regions[key];
                            if (!r) return null;
                            const esc = /эскалац/i.test(r.direction || "");
                            const desc = /деэскалац/i.test(r.direction || "");
                            const dirColor = esc ? "var(--danger)" : desc ? "var(--success)" : "var(--text-tertiary)";
                            return (
                              <div key={key} className="obs-region-card">
                                <div className="obs-region-card-head">
                                  <Icon size={16} />
                                  <span className="obs-region-card-name">{label}</span>
                                  <span className="obs-region-card-dir" style={{ color: dirColor, borderColor: dirColor }}>{r.direction}</span>
                                </div>
                                {r.label && <div className="obs-region-card-label">{r.label}</div>}
                                {r.duration_estimate && (
                                  <div className="obs-region-card-duration"><Clock size={12} />{r.duration_estimate}</div>
                                )}
                                {r.summary && <p className="obs-region-card-summary">{r.summary}</p>}
                                {Array.isArray(r.affected) && r.affected.length > 0 && (
                                  <div className="obs-region-card-affected">
                                    <div className="obs-region-card-affected-label">Кого касается</div>
                                    <div className="obs-region-card-chips">
                                      {r.affected.map((a, i) => <span key={i} className="obs-region-chip">{a}</span>)}
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>

                        {/* Карты очагов — ВНЕ узкой 3-колоночной сетки (obs-region-grid,
                            minmax(260px,1fr) слишком тесно для читаемой интерактивной карты
                            с подписями — ОТК персоны это подтвердил). Каждая карта — свой
                            полноширинный obs-inst-card, компонент сам вернёт null, если для
                            очага ещё нет geo_map_<theater>.json — Ближний Восток/АТР появятся
                            автоматически, без правки кода, когда появятся их файлы. */}
                        {GEO_REGION_META.map(({ key, label }) => {
                          const r = baro.regions[key];
                          const esc = /эскалац/i.test(r?.direction || "");
                          const desc = /деэскалац/i.test(r?.direction || "");
                          const dirColor = esc ? "var(--danger)" : desc ? "var(--success)" : "var(--text-tertiary)";
                          return (
                            <ObsGeoTheaterMap
                              key={key} theaterKey={key} regionLabel={label} token={token}
                              direction={r?.direction} directionColor={dirColor}
                            />
                          );
                        })}
                      </div>
                    )}

                    {baro.scenario && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title">
                          <Swords size={16} />
                          Сценарий: {baro.scenario.current_lean ? baro.scenario.current_lean.split(",")[0].trim() : "—"}
                          {baro.scenario.confidence && <span className="obs-inst-scenario-current">confidence {baro.scenario.confidence}</span>}
                        </div>
                        {baro.scenario.current_lean && (
                          <p className="obs-inst-card-sub" style={{ maxWidth: "100%" }}>{baro.scenario.current_lean}</p>
                        )}
                        <div className="obs-seg" style={{ marginBottom: 14 }}>
                          <button className={`obs-seg-opt${geoHorizon === "6m" ? " obs-seg-opt--on" : ""}`} onClick={() => setGeoHorizon("6m")}>6 мес.</button>
                          <button className={`obs-seg-opt${geoHorizon === "18m" ? " obs-seg-opt--on" : ""}`} onClick={() => setGeoHorizon("18m")}>18 мес.</button>
                        </div>
                        <ObsBaroLadder items={ladderItems} currentKey={currentKey} />
                        {Array.isArray(baro.scenario.triggers) && baro.scenario.triggers.length > 0 && (
                          <>
                            <div className="obs-inst-checkpoint">
                              <div className="obs-inst-checkpoint-label"><Info size={12} />Ближайший триггер пересмотра</div>
                              <div className="obs-inst-checkpoint-text">{baro.scenario.triggers[0]}</div>
                            </div>
                            {baro.scenario.triggers.length > 1 && (
                              <details className="obs-inst-details">
                                <summary>Другие триггеры ({baro.scenario.triggers.length - 1})<ChevronDown size={15} className="obs-inst-chev" /></summary>
                                <div className="obs-inst-details-body">
                                  {baro.scenario.triggers.slice(1).map((t, i) => <p key={i}>{t}</p>)}
                                </div>
                              </details>
                            )}
                          </>
                        )}
                      </div>
                    )}

                    {/* Секторные последствия — сразу под сценариями: «что это значит для моих бумаг» читается раньше, чем расхождение с рынком/детальные оси. */}
                    {Array.isArray(baro.sector_flags) && baro.sector_flags.length > 0 && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title"><Briefcase size={16} />Секторные последствия</div>
                        <div className="obs-inst-list">
                          {baro.sector_flags.map((s, i) => {
                            const neg = /негатив/i.test(s.direction || "");
                            const pos = /позитив/i.test(s.direction || "");
                            return (
                              <div key={i} className="obs-inst-row">
                                <div className="obs-inst-row-main">
                                  <div className="obs-inst-row-title" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    {neg ? <TrendingDown size={14} style={{ color: "var(--danger)" }} /> : pos ? <TrendingUp size={14} style={{ color: "var(--success)" }} /> : null}
                                    {s.sector}
                                    <span style={{ fontSize: 11, fontWeight: 700, color: neg ? "var(--danger)" : pos ? "var(--success)" : "var(--text-tertiary)", textTransform: "uppercase" }}>· {s.direction}</span>
                                  </div>
                                  {s.reasoning && <div className="obs-inst-row-why">{s.reasoning}</div>}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {baro.implied_market && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title"><BarChart2 size={16} />Расхождение с рынком</div>
                        {baro.implied_market.market_pricing_lean && (
                          <p style={{ fontSize: 12.5, color: "var(--text-tertiary)", fontStyle: "italic", marginBottom: 10 }}>{baro.implied_market.market_pricing_lean}</p>
                        )}
                        <p style={{ margin: 0, fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.7 }}>{baro.implied_market.divergence}</p>
                      </div>
                    )}

                    {/* «Внешние оси» — прямой ответ на «а Ближний Восток и АТР?»: явно
                        именованные G9 (Китай/Индия), G10 (США), G11 (ЕС/UK), G13 (глобальный
                        фон/Ормуз) с вкладом в общий балл. Следующий уровень детализации
                        внутри ЕДИНОГО барометра — не отдельные региональные барометры. */}
                    {(() => {
                      const axisItems = GEO_AXES.map((a) => subMap[a.key]).filter(Boolean);
                      if (axisItems.length === 0) return null;
                      return (
                        <div className="obs-inst-card">
                          <div className="obs-inst-card-title"><Globe size={16} />Внешние оси: Китай/Индия, США, ЕС, глобальный фон</div>
                          <div className="obs-inst-card-sub">Барометр — единый показатель для всего рынка; эти 4 оси из G1–G13 отвечают за вклад конкретных внешних игроков и регионов (АТР, Запад, Ормуз) в общий балл.</div>
                          <div>
                            {axisItems.map((s) => <ObsBaroSubRow key={s.key} s={s} polarity="higherWorse" />)}
                          </div>
                        </div>
                      );
                    })()}

                    {/* Резюме оставлено: в отличие от короткого hero-вердикта, здесь конкретные
                        даты/цифры/кросс-ссылки на макро — не пересказ, а более полная синтез-картина. */}
                    {baro.summary && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title"><FileText size={16} />Резюме · развёрнутая оценка Basis</div>
                        <p style={{ whiteSpace: "pre-line", margin: 0, fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.7 }}>{baro.summary}</p>
                      </div>
                    )}

                    {Array.isArray(baro.subindices) && baro.subindices.length > 0 && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title"><Globe size={16} />Показатели (G1–G13)</div>
                        <div className="obs-inst-card-sub">Сгруппированы по смыслу — балл 5/5 всегда означает наибольший риск для рынка, 1/5 — наименьший.</div>
                        <ObsBaroClusters clusters={GEO_CLUSTERS} subindexMap={subMap} polarity="higherWorse" />
                      </div>
                    )}

                    {Array.isArray(baro.watchlist_30d) && baro.watchlist_30d.length > 0 && (
                      <div className="obs-inst-card">
                        <div className="obs-inst-card-title"><Clock size={16} />За чем следить (30 дней)</div>
                        <div className="obs-inst-watch-group">
                          {baro.watchlist_30d.map((w, i) => (
                            <div key={i} className="obs-inst-watch-row">
                              <span className="obs-inst-watch-n">{i + 1}</span>
                              <span><b>{w.signal}</b>{w.window ? ` — ${w.window}` : ""}{w.expected_effect ? `. ${w.expected_effect}` : ""}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
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

          {!baroLoading && baro && (() => {
            // M13 — интегральный вектор дрейфа, не отдельный «фактор» — выносим в hero,
            // остальные 12 группируем в смысловые кластеры.
            const drift = (baro.subindices || []).find((s) => s.key === "M13");
            const restSub = (baro.subindices || []).filter((s) => s.key !== "M13");
            const subMap = {};
            restSub.forEach((s) => { subMap[s.key] = s; });

            const scenarioEntries = Object.entries(baro.scenario?.probabilities || {});
            const ladderItems = scenarioEntries.map(([name, p]) => ({ key: name, label: name, pct: obsParsePct(p) }));
            const alertsSorted = Array.isArray(baro.alerts)
              ? [...baro.alerts].sort((a, b) => (b.date || "").localeCompare(a.date || ""))
              : [];

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <ObsBaroCaveat flags={baro.data_flags} />

                <ObsBaroHero
                  eyebrow="Институциональный барометр · оценка Basis"
                  asOf={baro.as_of}
                  score={baro.barometer?.overall}
                  verdict={baro.barometer?.label}
                  polarity="higherBetter"
                  scaleLabels={["слабые институты", "сильные институты"]}
                  subindices={restSub}
                  coSignal={baro.institutional_crp_floor_pp != null && (
                    <div className="obs-inst-hero-cosignal">
                      <span className="obs-inst-hero-cosignal-label">CRP-«пол»</span>
                      <span className="obs-inst-hero-cosignal-value">
                        {baro.institutional_crp_floor_pp}<span className="obs-inst-hero-cosignal-unit">п.п.</span>
                      </span>
                    </div>
                  )}
                  extra={drift && (
                    <div className="obs-inst-hero-drift">
                      <div className="obs-inst-hero-drift-label"><TrendingDown size={12} />{drift.key} · {drift.label}</div>
                      <p>{drift.rationale}</p>
                    </div>
                  )}
                />

                {baro.crp_floor_rationale && (
                  <div className="obs-inst-card">
                    <div className="obs-inst-card-title"><Landmark size={16} />Институциональный «пол» CRP</div>
                    <div className="obs-inst-crp-value">
                      {baro.institutional_crp_floor_pp}<span className="obs-inst-crp-unit">п.п. к стоимости капитала</span>
                    </div>
                    <details className="obs-inst-details">
                      <summary>Как посчитан пол и от чего зависит диапазон<ChevronDown size={15} className="obs-inst-chev" /></summary>
                      <div className="obs-inst-details-body">
                        <p style={{ whiteSpace: "pre-line" }}>{baro.crp_floor_rationale}</p>
                      </div>
                    </details>
                  </div>
                )}

                {baro.scenario && (
                  <div className="obs-inst-card">
                    <div className="obs-inst-card-title">
                      <Gavel size={16} />
                      Сценарий: {baro.scenario.current}
                      <span className="obs-inst-scenario-current">текущий</span>
                    </div>
                    <ObsBaroLadder items={ladderItems} currentKey={baro.scenario.current} />
                    {Array.isArray(baro.scenario.triggers_for_revision) && baro.scenario.triggers_for_revision.length > 0 && (
                      <>
                        <div className="obs-inst-checkpoint">
                          <div className="obs-inst-checkpoint-label"><Info size={12} />Ближайший триггер пересмотра</div>
                          <div className="obs-inst-checkpoint-text">{baro.scenario.triggers_for_revision[0]}</div>
                        </div>
                        {baro.scenario.triggers_for_revision.length > 1 && (
                          <details className="obs-inst-details">
                            <summary>Другие триггеры ({baro.scenario.triggers_for_revision.length - 1})<ChevronDown size={15} className="obs-inst-chev" /></summary>
                            <div className="obs-inst-details-body">
                              {baro.scenario.triggers_for_revision.slice(1).map((t, i) => <p key={i}>{t}</p>)}
                            </div>
                          </details>
                        )}
                      </>
                    )}
                  </div>
                )}

                {restSub.length > 0 && (
                  <div className="obs-inst-card">
                    <div className="obs-inst-card-title"><Building2 size={16} />Показатели (M1–M12)</div>
                    <div className="obs-inst-card-sub">5/5 — сильный институт (низкий риск для держателя акций), 1/5 — слабый (высокий риск).</div>
                    <ObsBaroClusters clusters={INSTITUTIONS_CLUSTERS} subindexMap={subMap} polarity="higherBetter" />
                  </div>
                )}

                {alertsSorted.length > 0 && (
                  <div className="obs-inst-card">
                    <div className="obs-inst-card-title"><AlertTriangle size={16} />Что нового</div>
                    <div className="obs-inst-list">
                      {alertsSorted.map((al, i) => (
                        <div key={i} className="obs-inst-row">
                          <div className="obs-inst-row-main">
                            <div className="obs-inst-row-title">{al.title}</div>
                            {al.why_it_matters && <div className="obs-inst-row-why">{al.why_it_matters}</div>}
                            {(al.date || al.source) && (
                              <div className="obs-inst-row-meta">
                                {al.date && <span className="obs-inst-row-date">{al.date}</span>}
                                {al.date && al.source && " · "}
                                {al.source && <span className="obs-inst-row-source">{al.source}</span>}
                              </div>
                            )}
                          </div>
                          {al.type && (al.type === "факт"
                            ? <span className="obs-tag-fact">факт</span>
                            : <span className="obs-inst-tag obs-inst-tag--est">{al.type}</span>)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Array.isArray(baro.power_map_top_conflicts) && baro.power_map_top_conflicts.length > 0 && (
                  <div className="obs-inst-card">
                    <div className="obs-inst-card-title"><Swords size={16} />Карта конфликтов элит</div>
                    <div className="obs-inst-card-sub">Реконструкция по открытым источникам — версии, не подтверждённые факты аппаратной борьбы.</div>
                    <div className="obs-inst-list">
                      {baro.power_map_top_conflicts.map((c, i) => (
                        <div key={i} className="obs-inst-row">
                          <div className="obs-inst-row-main">
                            <div className="obs-inst-row-title">{c.title}</div>
                            {Array.isArray(c.parties) && (
                              <div className="obs-inst-row-status">{c.parties.join(" vs ")}</div>
                            )}
                            {c.status && <div className="obs-inst-row-why">{c.status}</div>}
                            {c.source && <div className="obs-inst-row-meta"><span className="obs-inst-row-source">{c.source}</span></div>}
                          </div>
                          {c.type && (c.type === "факт"
                            ? <span className="obs-tag-fact">факт</span>
                            : <span className="obs-inst-tag obs-inst-tag--est">{c.type}</span>)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
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

function ObsPulseCard({ item, onClick }) {
  if (!item) return null;
  const chg = item.change_pct;
  const dCls = chg == null ? "obs-d-neutral" : chg > 0 ? "obs-d-good" : chg < 0 ? "obs-d-bad" : "obs-d-neutral";
  const color = chg == null ? "var(--text-tertiary)" : chg > 0 ? "var(--success)" : chg < 0 ? "var(--danger)" : "var(--text-tertiary)";
  const lvl = item.level;
  const dec = item.unit === "%" || item.unit === "₽/г" ? 2 : (lvl != null && lvl > 1000 ? 0 : 2);
  const Tag = onClick ? "button" : "div";
  return (
    <Tag className="obs-tile" style={onClick ? undefined : { cursor: "default" }} onClick={onClick} type={onClick ? "button" : undefined}>
      <div className="obs-tile-lbl">{item.name}</div>
      <div className="obs-tile-val">{lvl != null ? lvl.toLocaleString("ru-RU", { maximumFractionDigits: dec }) : "—"}{item.unit ? (item.unit === "%" ? "%" : " " + item.unit) : ""}</div>
      {chg != null && <div className={"obs-tile-delta " + dCls}>{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {Math.abs(chg).toFixed(2)}%</div>}
      {item.spark && item.spark.length > 1 && <div style={{ marginTop: 8 }}><ObsSparkline points={item.spark} color={color} /></div>}
      {item.note && <div className="obs-tile-date">{item.note}</div>}
    </Tag>
  );
}

const OBS_FG_COMP_LABELS = {
  momentum: "Импульс рынка (IMOEX к MA125)",
  volatility: "Волатильность (RVI)",
  breadth: "Ширина рынка (доля бумаг в плюсе за 20 дн.)",
  risk_appetite: "Спрос на риск (акции vs гособлигации, 20 дн.)",
};

function ObsFearGreedCard({ fg, onOpenDetail }) {
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
          {onOpenDetail && (
            <button type="button" className="obs-rep-toggle" style={{ fontSize: "12.5px", fontWeight: 600, marginTop: 8 }} onClick={onOpenDetail}>
              Подробный разбор →
            </button>
          )}
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

function ObsMarketPulse({ onSelectCompany, onSelectIndex, onOpenFearGreed, driverChart }) {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [pulse, setPulse] = useState(null);
  const [loading, setLoading] = useState(true);
  const { stocks, loading: stocksLoading } = useObsStocksLive();
  // График драйвера (клик по «Нефть Brent»/«USD·RUB»/«ОФЗ 10 лет» на Рынке) —
  // null: нет запроса, []: загружено и пусто, [...]: точки {as_of, value}.
  const [driverPts, setDriverPts] = useState(null);
  const [driverDismissed, setDriverDismissed] = useState(false);

  useEffect(() => {
    let alive = true;
    fetch(`${apiUrl}/api/market/pulse`).then(r => (r.ok ? r.json() : null)).then(d => {
      if (!alive) return;
      setPulse(d);
      setLoading(false);
    }).catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [apiUrl]);

  useEffect(() => {
    setDriverDismissed(false);
    if (!driverChart) { setDriverPts(null); return; }
    let alive = true;
    setDriverPts(null);
    fetch(`${apiUrl}/api/market/instruments/${driverChart.asset_class}/${driverChart.secid}/history?days=365`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!alive) return;
        const field = driverChart.field || "close";
        // фьючерсы часто торгуются по settle, а close пуст — тот же фоллбэк, что
        // backend использует для last/prev в get_history() (services/instrument_history.py).
        const pts = (d?.points || [])
          .map(p => ({ as_of: p.date, value: p[field] != null ? p[field] : (p.close != null ? p.close : p.settle) }))
          .filter(p => p.value != null);
        setDriverPts(pts);
      }).catch(() => { if (alive) setDriverPts([]); });
    return () => { alive = false; };
  }, [apiUrl, driverChart]);

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
      {driverChart && !driverDismissed && (
        <div className="obs-hero-rate">
          <div className="obs-hero-topline">
            <div className="obs-hero-label">{driverChart.name} · история</div>
            <button type="button" onClick={() => setDriverDismissed(true)}
              style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", fontSize: "13px" }}>
              ✕ Закрыть
            </button>
          </div>
          {/* 🔴 2026-07-16: плитка каждый раз указывает на КОНКРЕТНЫЙ инструмент (ближайший
              непогашенный фьючерс / ближайшая по дюрации ОФЗ), не на непрерывный ряд «цена
              нефти»/«доходность 10Y» — разные контракты/выпуски расходятся в цене. Честная
              подпись вместо голого названия драйвера, чтобы не выдавать один инструмент за
              общий ряд (владелец: график «не та информация» — весенний пик был у другого,
              уже погашенного контракта). Continuous-склейка — отдельная задача, не здесь. */}
          {driverChart.instrument_label && (
            <div className="obs-hero-sub" style={{ fontSize: "12.5px", color: "var(--text-tertiary)", marginTop: -4, marginBottom: 8 }}>
              {driverChart.instrument_label}
              {driverPts && driverPts.length > 0 && ` · история с ${_obsDateRu(driverPts[0].as_of)}`}
            </div>
          )}
          {driverPts === null ? (
            <div className="tw-py-6 tw-text-text-tertiary tw-text-[13px]">Загружаем график...</div>
          ) : driverPts.length < 2 ? (
            <div className="obs-news-empty">Недостаточно истории для графика.</div>
          ) : (
            <ObsLineChart series={[{ name: driverChart.name, color: "var(--accent)", points: driverPts }]} viewW={1000} viewH={260} unit={driverChart.unit || ""} />
          )}
        </div>
      )}

      <ObsTickerMarquee stocks={stocks} onSelectCompany={onSelectCompany} />

      <ObsFearGreedCard fg={pulse.fear_greed} onOpenDetail={onOpenFearGreed} />

      <div className="obs-content-eyebrow" style={{ margin: "22px 0 10px" }}>Индексы</div>
      <div className="obs-grid8">
        {pulse.indices.map(idx => (
          <ObsPulseCard key={idx.ticker} item={idx} onClick={onSelectIndex ? () => onSelectIndex(idx.ticker) : undefined} />
        ))}
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
        {pulse.sectors.map(s => (
          <ObsPulseCard key={s.ticker} item={s} onClick={onSelectIndex ? () => onSelectIndex(s.ticker) : undefined} />
        ))}
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

function ObsEconomy({ token, forceIndicator }) {
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
      // default detail: пришли с конкретного драйвера (напр. плитка «USD/RUB» из
      // «Что движет рынком») — открываем именно его индикатор, иначе первый RU с данными.
      const forced = forceIndicator && arr.find((x) => x.code === forceIndicator && x.has_data);
      const first = forced || arr.find((x) => x.has_data && x.display_group === "ru");
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
  ObsCorporateNews,
  ObsMacroArticles,
  ObsGeopolitics,
  ObsInstitutions,
  ObsMarketPulse,
  ObsMarketMap,
  ObsAiReview,
  ObsEconomy,
  ObsLineChart,
  ObsHorizonChip,
};
