import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Activity,
  BarChart2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ExternalLink,
  Info,
  Sparkles,
  X,
  Zap,
} from "lucide-react";
import { Button, Card, Badge, Chip } from "../design/primitives";
import { Prose, Disclosure, ANALYST_MD } from "../design/textblocks";

const _SOURCE_LABEL = { interfax: "Интерфакс", rbc: "РБК", kommersant: "Коммерсантъ" };

// Категория по содержанию → спокойная цветовая точка (принцип «цвет в данных»,
// нейтральный бейдж + маркер-точка). Берём КАТЕГОРИАЛЬНУЮ палитру --cat-N, а не
// семантические success/warning (они закреплены за дельтами/риском — ОТК-дизайн).
const CATEGORY_COLOR = {
  "Экономика": "var(--cat-2)",
  "Рынки": "var(--cat-1)",
  "Бизнес": "var(--cat-3)",
  "Политика": "var(--cat-8)",
  "Геополитика": "var(--cat-6)",
};

function NewsFeed({ token, portfolioOnly, onSelectCompany }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [importance, setImportance] = useState("all");
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ limit: "120" });
    if (importance !== "all") params.set("importance", importance);
    if (portfolioOnly) params.set("portfolio_only", "true");
    fetch(`${apiUrl}/api/market/news?${params}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setItems(Array.isArray(d) ? d : []); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [importance, portfolioOnly, token]);

  // Лента «как в Telegram»: хронология по ВОЗРАСТАНИЮ (новые снизу), курсор
  // прочтения per-user (localStorage; ключ по id пользователя), автоскролл к первой
  // непрочитанной, отметка прочтения по факту показа на экране (IntersectionObserver).
  const uid = (() => { try { return JSON.parse(localStorage.getItem("basis_user"))?.id ?? "anon"; } catch { return "anon"; } })();
  const cursorKey = `basis_news_read_${uid}`;
  // Курсор прочтения ЗАМОРОЖЕН на момент открытия ленты: разделитель «Непрочитанное»
  // и маркеры считаются от него и НЕ едут за чтением. localStorage обновляется в фоне —
  // чтобы при СЛЕДУЮЩЕМ открытии разделитель встал на новое место. В рамках сессии
  // (смена фильтра) baseline сохраняется.
  const baselineRef = useRef(null);
  if (baselineRef.current === null) {
    const v = Number(localStorage.getItem(cursorKey));
    baselineRef.current = Number.isFinite(v) ? v : 0;
  }
  const baseline = baselineRef.current;
  const seenRef = useRef(baseline);
  const saveTimer = useRef(null);
  const firstUnreadRef = useRef(null);

  const sorted = [...items].sort((a, b) => {
    const ta = new Date(a.published_at || 0).getTime(), tb = new Date(b.published_at || 0).getTime();
    return (ta - tb) || ((a.id || 0) - (b.id || 0));
  });
  const firstUnreadIdx = sorted.findIndex((n) => (n.id || 0) > baseline);

  // автоскролл к первой непрочитанной (или вниз — к самым свежим) после загрузки
  useEffect(() => {
    if (loading || sorted.length === 0) return;
    const t = setTimeout(() => {
      if (firstUnreadRef.current) firstUnreadRef.current.scrollIntoView({ block: "center", behavior: "auto" });
    }, 80);
    return () => clearTimeout(t);
  }, [loading, items.length, importance, portfolioOnly]);

  // Прочтение копится в localStorage (только вперёд), БЕЗ ре-рендера — чтобы
  // визуально ничего не двигалось во время чтения.
  const markSeen = (id) => {
    if (!id || id <= seenRef.current) return;
    seenRef.current = id;
    clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      localStorage.setItem(cursorKey, String(seenRef.current));
      // TODO (follow-up): синк курсора на бэкенд для кросс-девайс per-user.
    }, 500);
  };

  const IMP_TABS = [
    { id: "all", label: "Все" },
    { id: "high", label: "Важное" },
    { id: "medium", label: "Среднее" },
  ];

  return (
    <div>
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2 tw-mb-5">
        {IMP_TABS.map((t) => (
          <Chip key={t.id} selected={importance === t.id} onClick={() => setImportance(t.id)}>
            {t.label}
          </Chip>
        ))}
      </div>

      {loading ? (
        <div className="tw-flex tw-items-center tw-justify-center tw-py-16 tw-text-text-secondary tw-animate-pulse">
          Загружаем ленту...
        </div>
      ) : error ? (
        <Card><div className="tw-text-[14px] tw-text-danger">Не удалось загрузить ленту. Попробуйте обновить страницу.</div></Card>
      ) : sorted.length === 0 ? (
        <Card>
          <div className="tw-text-[14px] tw-text-text-secondary tw-leading-relaxed">
            {portfolioOnly
              ? "По вашему портфелю значимых новостей за этот период нет."
              : "За этот период значимых рыночных новостей нет."}
            <span className="tw-text-text-tertiary"> Это нормально: лента показывает только то, что серьёзно влияет на рынок, и честно молчит, когда таких событий нет.</span>
          </div>
        </Card>
      ) : (
        <div className="tw-space-y-3">
          {sorted.map((n, i) => {
            const unread = (n.id || 0) > baseline;
            const isFirstUnread = i === firstUnreadIdx;
            return (
              <React.Fragment key={n.id}>
                {isFirstUnread && (
                  <div ref={firstUnreadRef} className="tw-flex tw-items-center tw-gap-2 tw-py-1">
                    <span className="tw-h-px tw-flex-1 tw-bg-accent tw-opacity-40" />
                    <span className="tw-text-[11px] tw-font-semibold tw-uppercase tw-tracking-wide tw-text-accent">Непрочитанное</span>
                    <span className="tw-h-px tw-flex-1 tw-bg-accent tw-opacity-40" />
                  </div>
                )}
                <NewsCard n={n} unread={unread} onSeen={markSeen} onSelectCompany={onSelectCompany} />
              </React.Fragment>
            );
          })}
        </div>
      )}
    </div>
  );
}

function NewsCard({ n, onSelectCompany, unread, onSeen }) {
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
  return (
    <div ref={ref}>
    <Card className={`${high ? "tw-border-l-2 tw-border-l-accent" : ""} ${unread ? "tw-ring-1 tw-ring-accent-soft" : ""}`}>
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2 tw-mb-1.5 tw-text-[12px] tw-text-text-tertiary">
        {unread && <span aria-label="непрочитано" className="tw-inline-block tw-w-[7px] tw-h-[7px] tw-rounded-pill tw-bg-accent tw-shrink-0" />}
        <span className="tw-font-medium tw-text-text-secondary">{_SOURCE_LABEL[n.source] || n.source || "Источник"}</span>
        {n.published_at && <span className="tw-font-mono">{_newsTime(n.published_at)}</span>}
        {n.category && CATEGORY_COLOR[n.category] && (
          <Badge tone="neutral">
            <span aria-hidden="true" className="tw-inline-block tw-w-2 tw-h-2 tw-rounded-pill"
                  style={{ backgroundColor: CATEGORY_COLOR[n.category] }} />
            {n.category}
          </Badge>
        )}
        {high && <Badge tone="accent">важное</Badge>}
        {n.source_url && (
          <a href={n.source_url} target="_blank" rel="noopener noreferrer"
             className="tw-ml-auto tw-inline-flex tw-items-center tw-gap-1 tw-text-text-tertiary hover:tw-text-accent tw-no-underline">
            Источник <ExternalLink size={12} />
          </a>
        )}
      </div>

      <h3 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-leading-snug tw-mb-1.5">{n.title}</h3>

      {n.summary && (
        <p className="tw-text-[13px] tw-leading-[20px] tw-text-text-secondary tw-mb-2.5">{n.summary}</p>
      )}

      {n.impact_comment && (
        <div className="tw-flex tw-gap-2 tw-rounded-md tw-bg-accent-soft tw-px-3 tw-py-2 tw-mb-2.5">
          <Zap size={14} className="tw-text-accent tw-shrink-0 tw-mt-0.5" aria-hidden="true" />
          <div className="tw-text-[13px] tw-leading-[19px] tw-text-text-secondary">
            <span className="tw-font-medium tw-text-text-primary">На что влияет. </span>{n.impact_comment}
          </div>
        </div>
      )}

      {((n.affected_tickers && n.affected_tickers.length > 0) ||
        (n.affected_sectors && n.affected_sectors.length > 0)) && (
        <div className="tw-flex tw-flex-wrap tw-gap-1.5">
          {(n.affected_tickers || []).map((t) => (
            <button key={t} onClick={() => onSelectCompany && onSelectCompany(t)}
              className="tw-inline-flex tw-items-center tw-gap-1 tw-rounded-pill tw-bg-bg-hover tw-border tw-border-border-subtle tw-px-2 tw-py-1 tw-text-[12px] tw-text-text-secondary tw-cursor-pointer hover:tw-bg-accent-soft hover:tw-border-accent hover:tw-text-accent tw-transition-colors focus-visible:tw-outline-none focus-visible:tw-shadow-focus">
              {t}
            </button>
          ))}
          {(n.affected_sectors || []).map((s) => (
            <span key={s} className="tw-inline-flex tw-items-center tw-rounded-pill tw-bg-bg-hover tw-px-2 tw-py-1 tw-text-[12px] tw-text-text-tertiary">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Честная пометка для общерыночных событий без прямого эмитента (иначе пустой
          низ карточки воспринимается как «недозаполнено») — ОТК-персона. */}
      {(!n.affected_tickers || n.affected_tickers.length === 0) &&
       (!n.affected_sectors || n.affected_sectors.length === 0) && (
        <div className="tw-text-[12px] tw-text-text-tertiary">Влияет на рынок в целом — без привязки к конкретным бумагам</div>
      )}
    </Card>
    </div>
  );
}

// =========================
// MACRO VIEW (Обозреватель · Направление 2 — Макрообзор)
// =========================

// Полноценный мульти-линейный график: оси (Y %, X даты), тултип при наведении,
// ползунок по времени. Паттерн осей/тултипа — как в BenchmarkChart (Анализ портфеля).
// series: [{ name, color, points:[{as_of,value}] }]
function MacroChart({ series, height = 200, unit = "" }) {
  const [hover, setHover] = useState(null);   // индекс по объединённой оси дат
  const svgRef = useRef(null);
  const W = 640, H = height, padL = 42, padR = 12, padT = 12, padB = 26;

  const allDates = [...new Set(series.flatMap((s) => s.points.map((p) => p.as_of)))].sort();
  const n = allDates.length;
  const all = series.flatMap((s) => s.points.map((p) => p.value)).filter((v) => v != null);
  if (n < 2 || all.length < 2) return <div className="tw-text-[12px] tw-text-text-tertiary tw-py-4">Недостаточно точек для графика.</div>;
  let max = Math.max(...all), min = Math.min(...all);
  const pad = (max - min) * 0.08 || 1; max += pad; min -= pad;
  const span = (max - min) || 1;
  const xAt = (i) => padL + (n <= 1 ? 0 : (i * (W - padL - padR)) / (n - 1));
  const yAt = (v) => padT + (1 - (v - min) / span) * (H - padT - padB);
  // значение ряда на дату d (или последнее до неё)
  const valAt = (s, d) => {
    let r = null;
    for (const p of s.points) { if (p.as_of <= d && p.value != null) r = p.value; }
    return r;
  };
  const path = (s) => {
    const seg = [];
    s.points.filter((p) => p.value != null).forEach((p) => {
      const i = allDates.indexOf(p.as_of);
      if (i >= 0) seg.push(`${seg.length === 0 ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(p.value).toFixed(1)}`);
    });
    return seg.join(" ");
  };
  const fmtD = (iso) => { const [y, m] = iso.split("-"); return `${m}.${y.slice(2)}`; };
  const fmtFull = (iso) => { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; };
  const onMove = (e) => {
    const el = svgRef.current; if (!el) return;
    const rect = el.getBoundingClientRect();
    const xSvg = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((xSvg - padL) / (W - padL - padR)) * (n - 1));
    setHover(i >= 0 && i < n ? i : null);
  };
  const yTicks = [max, (max + min) / 2, min];
  const xTickIdx = [0, Math.floor(n / 2), n - 1];

  return (
    <div className="tw-relative">
      {hover != null && (
        <div className="tw-absolute tw-z-10 tw-pointer-events-none tw-bg-bg-overlay tw-border tw-border-border-subtle tw-rounded-md tw-shadow-lg tw-px-3 tw-py-2 tw-text-[12px]"
             style={{ left: `${(xAt(hover) / W) * 100}%`, top: 0, transform: xAt(hover) > W * 0.6 ? "translateX(-105%)" : "translateX(8px)" }}>
          <div className="tw-text-text-tertiary tw-font-mono tw-mb-1">{fmtFull(allDates[hover])}</div>
          {series.map((s, k) => {
            const val = valAt(s, allDates[hover]);
            return <div key={k} className="tw-text-text-secondary tw-flex tw-items-center tw-gap-1.5">
              <span className="tw-inline-block tw-w-2.5 tw-h-2.5 tw-rounded-pill" style={{ backgroundColor: s.color }} />
              {s.name} <b className="tw-font-mono tw-tabular-nums tw-text-text-primary">{val == null ? "—" : val.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}{unit}</b>
            </div>;
          })}
        </div>
      )}
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}
           role="img" aria-label="График показателя" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {yTicks.map((v, k) => (
          <g key={k}>
            <line x1={padL} x2={W - padR} y1={yAt(v)} y2={yAt(v)} stroke="var(--border-subtle)" strokeWidth="1" strokeDasharray="3 4" />
            <text x={padL - 6} y={yAt(v) + 4} textAnchor="end" fontSize="10.5" fill="var(--text-tertiary)" fontFamily="monospace">{v.toFixed(1)}{unit}</text>
          </g>
        ))}
        {xTickIdx.map((i, k) => (
          <text key={k} x={xAt(i)} y={H - 8} textAnchor={k === 0 ? "start" : k === xTickIdx.length - 1 ? "end" : "middle"}
                fontSize="10.5" fill="var(--text-tertiary)" fontFamily="monospace">{fmtD(allDates[i])}</text>
        ))}
        {series.map((s, i) => <path key={i} d={path(s)} fill="none" stroke={s.color} strokeWidth="1.8" />)}
        {hover != null && (
          <g>
            <line x1={xAt(hover)} x2={xAt(hover)} y1={padT} y2={H - padB} stroke="var(--text-tertiary)" strokeWidth="1" strokeDasharray="2 3" />
            {series.map((s, k) => { const val = valAt(s, allDates[hover]); return val == null ? null :
              <circle key={k} cx={xAt(hover)} cy={yAt(val)} r="3" fill={s.color} />; })}
          </g>
        )}
      </svg>
      {series.length > 1 && (
        <div className="tw-flex tw-flex-wrap tw-gap-3 tw-mt-1.5 tw-text-[11px] tw-text-text-tertiary">
          {series.map((s, i) => (
            <span key={i} className="tw-inline-flex tw-items-center tw-gap-1">
              <span className="tw-inline-block tw-w-4 tw-h-1 tw-rounded-pill" style={{ backgroundColor: s.color }} />{s.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// Совместимость со старыми вызовами (карточка-плитка): тонкая обёртка над MacroChart.
function MacroLineChart({ series, height = 150 }) {
  return <MacroChart series={series} height={height} />;
}

const _MET_LABEL = { mom: "м/м", yoy: "г/г", level: "", wow: "нед." };
const _fmtNum = (x) => (x == null ? "—" : Number(x).toLocaleString("ru-RU", { maximumFractionDigits: 2 }));

// Кнопка-«i» с пояснением показателя по клику (не hover — доступнее и на
// мобильных); тот же паттерн, что и в Скринере (InfoTip в ScreenerNeo.jsx),
// но перенесён на токены/tw-классы этого файла. Поповер — position:"fixed" по
// координатам из getBoundingClientRect, НЕ absolute: карточка лежит в
// скролл-сетке с overflow, absolute обрезался бы родителем. stopPropagation
// обязателен — кнопка внутри кликабельной <button> всей карточки (открывает
// MacroDetailModal), клик по «i» не должен её триггерить.
function MacroInfoTip({ text }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const popRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    window.addEventListener("scroll", () => setOpen(false), { capture: true, once: true });
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  if (!text) return null;
  const toggle = (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      const W = 260;
      const left = Math.max(12, Math.min(r.left, window.innerWidth - W - 12));
      setPos({ top: r.bottom + 6, left });
    }
    setOpen((o) => !o);
  };
  const onKeyDown = (e) => {
    if (e.key === "Enter" || e.key === " ") toggle(e);
  };
  return (
    <span className="tw-relative tw-inline-flex">
      {/* span, не button — эта подсказка лежит ВНУТРИ кликабельной <button> всей
          карточки (MacroIndicatorCard), а <button> внутри <button> — невалидная
          HTML-вложенность (React иначе кидает validateDOMNesting-предупреждение). */}
      <span
        ref={btnRef}
        role="button"
        tabIndex={0}
        aria-label="Пояснение"
        onClick={toggle}
        onKeyDown={onKeyDown}
        className="tw-inline-flex tw-items-center tw-justify-center tw-w-[15px] tw-h-[15px] tw-rounded-full tw-border tw-border-border-subtle tw-bg-transparent tw-text-[9.5px] tw-font-semibold tw-font-mono tw-text-text-tertiary tw-cursor-pointer tw-flex-none hover:tw-border-accent hover:tw-text-accent focus-visible:tw-outline-none focus-visible:tw-shadow-focus"
      >
        i
      </span>
      {open && pos && (
        <span
          ref={popRef}
          role="tooltip"
          onClick={(e) => e.stopPropagation()}
          style={{ position: "fixed", top: pos.top, left: pos.left }}
          className="tw-w-[260px] tw-bg-bg-elevated tw-border tw-border-border-subtle tw-rounded-md tw-shadow-lg tw-p-3 tw-text-[12.5px] tw-text-text-secondary tw-leading-[1.45] tw-z-50"
        >
          {text}
        </span>
      )}
    </span>
  );
}

// Плитка-вход: число, изменение, дата, краткое «как влияет». Клик → окно (B).
function MacroIndicatorCard({ ind, onOpen }) {
  const v = ind.values?.[(ind.metric_types || ["level"])[0]] || Object.values(ind.values || {})[0];
  if (!ind.has_data) {
    return (
      <Card>
        <div className="tw-text-[13px] tw-font-medium tw-text-text-primary tw-mb-1">{ind.title}</div>
        <div className="tw-text-[12px] tw-text-text-tertiary">Данные за период ещё не вышли.</div>
      </Card>
    );
  }
  return (
    <Card className={`tw-cursor-pointer hover:tw-border-accent tw-transition-colors ${ind.in_portfolio ? "tw-border-l-2 tw-border-l-accent" : ""}`}>
      <button onClick={() => onOpen(ind)} className="tw-block tw-w-full tw-text-left tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded-sm">
        <div className="tw-flex tw-items-baseline tw-justify-between tw-gap-2 tw-mb-0.5">
          <span className="tw-inline-flex tw-items-center tw-gap-1">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">{ind.title}</span>
            <MacroInfoTip text={ind.influence_short || ind.influence_full} />
          </span>
          {v?.is_preliminary && <Badge tone="neutral">предв.</Badge>}
        </div>
        <div className="tw-flex tw-items-baseline tw-gap-2">
          <span className="tw-text-[22px] tw-font-semibold tw-text-text-primary tw-tabular-nums">{_fmtNum(v?.value)}{ind.unit === "%" ? "%" : ""}</span>
          {ind.unit && ind.unit !== "%" && <span className="tw-text-[12px] tw-text-text-tertiary">{ind.unit}</span>}
          {v?.change != null && (
            <span className={`tw-text-[12px] tw-tabular-nums ${v.change > 0 ? "tw-text-success" : v.change < 0 ? "tw-text-danger" : "tw-text-text-tertiary"}`}>
              {v.change > 0 ? "▲" : v.change < 0 ? "▼" : ""}{_fmtNum(Math.abs(v.change))}
            </span>
          )}
        </div>
        <div className="tw-text-[11px] tw-text-text-tertiary tw-mb-1.5">{v?.as_of}</div>
        {ind.influence_short && <div className="tw-text-[12px] tw-text-text-secondary tw-leading-[17px] tw-line-clamp-2">{ind.influence_short}</div>}
        <div className="tw-text-[11px] tw-text-accent tw-mt-1.5 tw-inline-flex tw-items-center tw-gap-1"><Activity size={12} /> Подробнее и график</div>
      </button>
    </Card>
  );
}

// Окно показателя (B): полноценный график (оси/тултип/ползунок), переключатель
// метрики, наложение другого показателя, пояснение influence.
function MacroDetailModal({ ind, allInds, onClose }) {
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const [metric, setMetric] = useState((ind.metric_types || ["level"])[0]);
  const [base, setBase] = useState(null);     // {points}
  const [overlayCode, setOverlayCode] = useState("");
  const [overlay, setOverlay] = useState(null);
  const v = ind.values?.[metric] || Object.values(ind.values || {})[0];

  useEffect(() => {
    fetch(`${apiUrl}/api/market/macro/${ind.code}/series?metric=${metric}`)
      .then((r) => (r.ok ? r.json() : null)).then((d) => setBase(d?.points || [])).catch(() => setBase([]));
  }, [ind.code, metric]);
  useEffect(() => {
    if (!overlayCode) { setOverlay(null); return; }
    const oi = allInds.find((x) => x.code === overlayCode);
    const om = (oi?.metric_types || ["level"])[0];
    fetch(`${apiUrl}/api/market/macro/${overlayCode}/series?metric=${om}`)
      .then((r) => (r.ok ? r.json() : null)).then((d) => setOverlay({ name: oi?.title || overlayCode, points: d?.points || [] })).catch(() => setOverlay(null));
  }, [overlayCode]);

  const series = [{ name: ind.title, color: "var(--accent)", points: base || [] }];
  if (overlay) series.push({ name: overlay.name, color: "var(--cat-6)", points: overlay.points });

  return (
    <div className="tw-fixed tw-inset-0 tw-z-50 tw-flex tw-items-center tw-justify-center tw-p-4" style={{ backgroundColor: "var(--bg-overlay)" }} onClick={onClose}>
      <div className="tw-bg-bg-elevated tw-rounded-lg tw-shadow-xl tw-max-w-3xl tw-w-full tw-max-h-[90vh] tw-overflow-auto tw-p-5" onClick={(e) => e.stopPropagation()}>
        <div className="tw-flex tw-items-start tw-justify-between tw-mb-3">
          <div>
            <div className="tw-text-[18px] tw-font-medium tw-text-text-primary">{ind.title}</div>
            <div className="tw-text-[22px] tw-font-semibold tw-text-text-primary tw-tabular-nums">{_fmtNum(v?.value)}{ind.unit === "%" ? "%" : ` ${ind.unit || ""}`}
              <span className="tw-text-[12px] tw-text-text-tertiary tw-ml-2 tw-font-normal">{v?.as_of}{_MET_LABEL[metric] ? ` · ${_MET_LABEL[metric]}` : ""}</span>
            </div>
          </div>
          <button onClick={onClose} aria-label="Закрыть" className="tw-bg-transparent tw-border-0 tw-cursor-pointer tw-text-text-tertiary hover:tw-text-text-primary focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded-sm"><X size={20} /></button>
        </div>

        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2 tw-mb-3">
          {(ind.metric_types || []).length > 1 && (ind.metric_types).map((m) => (
            <button key={m} onClick={() => setMetric(m)}
              className={`tw-text-[12px] tw-px-2 tw-py-0.5 tw-rounded-sm tw-cursor-pointer tw-border focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${metric === m ? "tw-border-accent tw-text-accent" : "tw-border-border-subtle tw-text-text-tertiary"}`}>
              {_MET_LABEL[m] || m}
            </button>
          ))}
          <span className="tw-ml-auto tw-text-[12px] tw-text-text-tertiary">Наложить:</span>
          <select value={overlayCode} onChange={(e) => setOverlayCode(e.target.value)}
            className="tw-text-[12px] tw-px-2 tw-py-1 tw-rounded-sm tw-border tw-border-border-subtle tw-bg-bg-base tw-text-text-primary focus-visible:tw-outline-none focus-visible:tw-shadow-focus">
            <option value="">— нет —</option>
            {allInds.filter((x) => x.code !== ind.code && x.has_data).map((x) => <option key={x.code} value={x.code}>{x.title}</option>)}
          </select>
        </div>

        {base === null ? <div className="tw-text-[13px] tw-text-text-tertiary tw-py-6 tw-animate-pulse">Загружаем график...</div>
          : <MacroChart series={series} height={240} unit={ind.unit === "%" ? "%" : ""} />}

        {(ind.influence_full || ind.influence_short) && (
          <div className="tw-mt-4 tw-border-t tw-border-border-subtle tw-pt-3">
            <div className="tw-text-[13px] tw-font-medium tw-text-text-primary tw-mb-1">Как влияет на рынок</div>
            <div className="tw-text-[13px] tw-text-text-secondary tw-leading-[20px]">{ind.influence_full || ind.influence_short}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function MacroView({ token, portfolioOnly }) {
  const [data, setData] = useState(null);
  const [rate, setRate] = useState(null);
  const [analytics, setAnalytics] = useState([]);
  const [rateChart, setRateChart] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  useEffect(() => {
    setLoading(true); setError(false);
    const h = token ? { Authorization: `Bearer ${token}` } : {};
    Promise.all([
      fetch(`${apiUrl}/api/market/macro${portfolioOnly ? "?portfolio_only=true" : ""}`, { headers: h }).then((r) => (r.ok ? r.json() : Promise.reject())),
      fetch(`${apiUrl}/api/market/macro/rate`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      fetch(`${apiUrl}/api/market/macro/analytics`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]).then(([m, rt, an]) => { setData(m); setRate(rt); setAnalytics(an || []); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token]);

  // ряды для наложения в блоке ставки (ставка/инфляция/ожидания)
  useEffect(() => {
    const get = (code, metric) => fetch(`${apiUrl}/api/market/macro/${code}/series?metric=${metric}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    Promise.all([get("key_rate", "level"), get("inflation", "yoy"), get("inflation_expectations", "level")])
      .then(([kr, inf, exp]) => {
        const s = [];
        if (kr?.points?.length) s.push({ name: "Ставка", color: "var(--accent)", points: kr.points });
        if (inf?.points?.length) s.push({ name: "Инфляция г/г", color: "var(--cat-6)", points: inf.points });
        if (exp?.points?.length) s.push({ name: "Инфл. ожидания", color: "var(--cat-2)", points: exp.points });
        if (s.length) setRateChart(s);
      });
  }, []);

  const [tab, setTab] = useState("indicators");
  const [country, setCountry] = useState("all");
  const [srcFilter, setSrcFilter] = useState("all");
  const [detail, setDetail] = useState(null);

  if (loading) return <div className="tw-flex tw-items-center tw-justify-center tw-py-16 tw-text-text-secondary tw-animate-pulse">Загружаем макрообзор...</div>;
  if (error) return <Card><div className="tw-text-[14px] tw-text-danger">Не удалось загрузить данные. Показываем последнее известное при следующей загрузке.</div></Card>;

  const COUNTRY_OF = { all: () => true, ru: (x) => x.country === "ru", us: (x) => x.country === "us",
    eu: (x) => x.country === "eu", cn: (x) => x.country === "cn", world: (x) => x.country === "world" };
  const inds = (data || []).filter(COUNTRY_OF[country] || (() => true));
  const ruInds = inds.filter((x) => x.display_group === "ru");
  const worldInds = inds.filter((x) => x.display_group === "world");
  const reviews = (analytics || []).filter((d) => srcFilter === "all" || d.source === srcFilter);

  const TABS = [
    { id: "indicators", label: "Показатели", icon: Activity },
    { id: "reviews", label: "Аналитические обзоры", icon: FileText },
    { id: "interpreter", label: "Интерпретатор", icon: Zap },
  ];
  const COUNTRIES = [["all", "Все"], ["ru", "Россия"], ["us", "США"], ["eu", "ЕС"], ["cn", "КНР"], ["world", "Мир"]];

  return (
    <div>
      {detail && <MacroDetailModal ind={detail} allInds={data || []} onClose={() => setDetail(null)} />}

      <div className="tw-flex tw-flex-wrap tw-gap-2 tw-mb-5 tw-border-b tw-border-border-subtle tw-pb-3">
        {TABS.map((t) => (
          <Chip key={t.id} selected={tab === t.id} onClick={() => setTab(t.id)}>
            <t.icon size={13} className="tw-shrink-0" aria-hidden="true" /> {t.label}
          </Chip>
        ))}
      </div>

      {/* ВКЛАДКА: ПОКАЗАТЕЛИ */}
      {tab === "indicators" && (
        <div className="tw-space-y-8">
          {rate?.key_rate && (
            <Card>
              <div className="tw-flex tw-flex-wrap tw-items-baseline tw-gap-3 tw-mb-2">
                <span className="tw-text-[14px] tw-font-medium tw-text-text-primary">Ключевая ставка ЦБ</span>
                <span className="tw-text-[28px] tw-font-semibold tw-text-accent tw-tabular-nums">{rate.key_rate.value}%</span>
                <span className="tw-text-[12px] tw-text-text-tertiary">на {rate.key_rate.as_of}</span>
              </div>
              <div className="tw-flex tw-flex-wrap tw-gap-x-6 tw-gap-y-1 tw-text-[13px] tw-text-text-secondary tw-mb-3">
                {rate.meeting?.next_meeting_date && <span>След. заседание: <b>{rate.meeting.next_meeting_date}</b></span>}
                {rate.meeting?.consensus_forecast && <span>Консенсус: <b>{rate.meeting.consensus_forecast}</b></span>}
                {rate.meeting?.signal && <span>Сигнал: {rate.meeting.signal}</span>}
              </div>
              {rate.meeting?.press_summary && (
                <div className="tw-text-[13px] tw-text-text-secondary tw-leading-relaxed tw-bg-bg-hover tw-rounded-md tw-p-2.5 tw-mb-3 tw-whitespace-pre-line">{rate.meeting.press_summary}</div>
              )}
              {rateChart && <MacroChart series={rateChart} height={200} unit="%" />}
              {rate.meetings && rate.meetings.length > 1 && (
                <details className="tw-mt-3 tw-text-[13px]">
                  <summary className="tw-cursor-pointer tw-text-text-secondary tw-select-none">История заседаний ({rate.meetings.length - 1})</summary>
                  <div className="tw-mt-2 tw-space-y-2">
                    {rate.meetings.slice(1).map((m, i) => (
                      <div key={i} className="tw-border-t tw-border-border-subtle tw-pt-2">
                        <div className="tw-flex tw-items-baseline tw-gap-2">
                          <span className="tw-font-mono tw-text-text-tertiary">{m.decision_date}</span>
                          <span className="tw-font-medium tw-text-text-primary tw-tabular-nums">{m.rate_value}%</span>
                          {m.signal && <span className="tw-text-[12px] tw-text-text-tertiary tw-truncate">{m.signal}</span>}
                        </div>
                        {m.press_summary && <div className="tw-text-[12px] tw-text-text-secondary tw-leading-[18px] tw-mt-1 tw-whitespace-pre-line">{m.press_summary}</div>}
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </Card>
          )}

          <div className="tw-flex tw-flex-wrap tw-gap-1.5">
            {COUNTRIES.map(([id, lbl]) => (
              <Chip key={id} selected={country === id} onClick={() => setCountry(id)}>{lbl}</Chip>
            ))}
          </div>

          {ruInds.length > 0 && (
            <div>
              <h2 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-3">Показатели РФ</h2>
              <div className="tw-grid tw-gap-3" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))" }}>
                {ruInds.map((ind) => <MacroIndicatorCard key={ind.code} ind={ind} onOpen={setDetail} />)}
              </div>
            </div>
          )}
          {worldInds.length > 0 && (
            <div>
              <h2 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-3">Мир</h2>
              <div className="tw-grid tw-gap-3" style={{ gridTemplateColumns: "repeat(auto-fill,minmax(260px,1fr))" }}>
                {worldInds.map((ind) => <MacroIndicatorCard key={ind.code} ind={ind} onOpen={setDetail} />)}
              </div>
            </div>
          )}

          <MacroForecastTable />
        </div>
      )}

      {/* ВКЛАДКА: АНАЛИТИЧЕСКИЕ ОБЗОРЫ */}
      {tab === "reviews" && (
        <div>
          <div className="tw-flex tw-flex-wrap tw-gap-1.5 tw-mb-4">
            {[["all", "Все"], ["cmasf", "ЦМАКП"], ["cbr", "Банк России"]].map(([id, lbl]) => (
              <Chip key={id} selected={srcFilter === id} onClick={() => setSrcFilter(id)}>{lbl}</Chip>
            ))}
          </div>
          {reviews.length === 0 ? (
            <Card><div className="tw-text-[13px] tw-text-text-tertiary">Новых аналитических документов пока нет — мониторинг проверяет источники ежедневно.</div></Card>
          ) : (
            <div className="tw-space-y-3">
              {reviews.map((d) => (
                <Card key={d.id}>
                  <div className="tw-flex tw-items-center tw-gap-2 tw-mb-1 tw-text-[12px] tw-text-text-tertiary">
                    <span className="tw-font-medium tw-text-text-secondary">{d.source === "cbr" ? "Банк России" : d.source === "cmasf" ? "ЦМАКП" : d.source}</span>
                    {d.doc_type && <Badge tone="neutral">{d.doc_type}</Badge>}
                    {d.published_at && <span>{d.published_at}</span>}
                  </div>
                  <h3 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-1.5">{d.title}</h3>
                  {d.summary && <p className="tw-text-[13px] tw-text-text-secondary tw-leading-[20px] tw-mb-2">{d.summary}</p>}
                  {d.key_takeaways?.length > 0 && (
                    <ul className="tw-text-[13px] tw-text-text-secondary tw-leading-[20px] tw-mb-2 tw-list-disc tw-pl-4 tw-space-y-0.5">
                      {d.key_takeaways.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  )}
                  {d.interpretation && (
                    <div className="tw-flex tw-gap-2 tw-rounded-md tw-bg-accent-soft tw-px-3 tw-py-2 tw-mb-2">
                      <Zap size={14} className="tw-text-accent tw-shrink-0 tw-mt-0.5" aria-hidden="true" />
                      <div className="tw-text-[13px] tw-leading-[19px] tw-text-text-secondary">
                        <span className="tw-font-medium tw-text-text-primary">Интерпретация Basis. </span>{d.interpretation}
                      </div>
                    </div>
                  )}
                  {d.source_url && (
                    <a href={d.source_url} target="_blank" rel="noopener noreferrer"
                       className="tw-text-[12px] tw-text-accent tw-inline-flex tw-items-center tw-gap-1 tw-no-underline hover:tw-underline">
                      Оригинал <ExternalLink size={12} />
                    </a>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ВКЛАДКА: ИНТЕРПРЕТАТОР */}
      {tab === "interpreter" && <MacroInterpreterTab token={token} />}
    </div>
  );
}

// D. Таблица среднесрочного прогноза ЦБ (вкладка Показатели, ниже).
function MacroForecastTable() {
  const [fc, setFc] = useState(null);
  const [scIdx, setScIdx] = useState(0);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  useEffect(() => {
    fetch(`${apiUrl}/api/market/macro/forecast`).then((r) => (r.ok ? r.json() : null)).then(setFc).catch(() => setFc(null));
  }, []);
  if (!fc || !fc.rows?.length) {
    return (
      <div>
        <h2 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-3">Среднесрочный прогноз Банка России</h2>
        <Card><div className="tw-text-[13px] tw-text-text-tertiary">Прогноз ЦБ появится после ближайшей публикации (мониторинг ЦБ проверяет источники ежедневно).</div></Card>
      </div>
    );
  }
  // Сценарии ЦБ: базовый + (если опубликованы) проинфляционный/дезинфляционный/рисковый.
  const scenarios = (Array.isArray(fc.scenarios) && fc.scenarios.length)
    ? fc.scenarios
    : [{ scenario: fc.scenario || "базовый", comment: fc.comment, rows: fc.rows }];
  const sel = scenarios[Math.min(scIdx, scenarios.length - 1)] || scenarios[0];
  const rows = sel.rows || [];
  const years = [...new Set(rows.map((r) => r.year))].sort();
  const indicators = [...new Set(rows.map((r) => r.indicator))];
  const cell = (ind, year) => rows.find((r) => r.indicator === ind && r.year === year);
  return (
    <div>
      <h2 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-1">Среднесрочный прогноз Банка России</h2>
      {fc.as_of && <div className="tw-text-[12px] tw-text-text-tertiary tw-mb-3">по состоянию на {fc.as_of}</div>}
      {scenarios.length > 1 && (
        <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-1.5 tw-mb-3">
          {scenarios.map((s, i) => (
            <Chip key={s.scenario} selected={i === scIdx} onClick={() => setScIdx(i)}>
              {s.scenario.charAt(0).toUpperCase() + s.scenario.slice(1)}
            </Chip>
          ))}
        </div>
      )}
      <Card>
        <div className="tw-overflow-x-auto">
          <table className="tw-w-full tw-text-[13px] tw-border-collapse">
            <thead>
              <tr className="tw-text-text-tertiary tw-text-left">
                <th className="tw-py-1.5 tw-pr-3 tw-font-medium">Показатель {scenarios.length > 1 ? `· ${sel.scenario}` : ""}</th>
                {years.map((y) => <th key={y} className="tw-py-1.5 tw-px-3 tw-font-medium tw-text-right tw-tabular-nums">{y}</th>)}
              </tr>
            </thead>
            <tbody>
              {indicators.map((ind) => (
                <tr key={ind} className="tw-border-t tw-border-border-subtle">
                  <td className="tw-py-1.5 tw-pr-3 tw-text-text-primary">{ind}</td>
                  {years.map((y) => { const c = cell(ind, y); return <td key={y} className="tw-py-1.5 tw-px-3 tw-text-right tw-tabular-nums tw-text-text-secondary">{c ? c.value : "—"}</td>; })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {sel.comment && <div className="tw-text-[13px] tw-text-text-secondary tw-leading-[20px] tw-mt-3 tw-pt-3 tw-border-t tw-border-border-subtle">{sel.comment}</div>}
      </Card>
    </div>
  );
}

// G. Интерпретатор — ИИ-анализ всей макроситуации (по методичке, DeepSeek Pro reasoning).
function MacroInterpreterTab({ token }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [regen, setRegen] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

  const load = () => {
    setLoading(true);
    fetch(`${apiUrl}/api/market/macro/interpretation`).then((r) => (r.ok ? r.json() : null))
      .then((d) => { setData(d); setLoading(false); }).catch(() => setLoading(false));
  };
  useEffect(load, []);

  const regenerate = () => {
    setRegen(true);
    fetch(`${apiUrl}/api/market/macro/interpretation`, { method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((r) => (r.ok ? r.json() : null)).then((d) => { if (d) setData(d); }).finally(() => setRegen(false));
  };

  const SECTIONS = [
    ["current_picture", "Текущая картина"],
    ["rate_outlook", "Ставка: ближайшее решение и траектория"],
    ["cb_forecast_view", "Прогноз ЦБ: оценка вероятности"],
    ["market_sectors", "Рынок и сектора"],
    ["scenarios", "Сценарии: base / bull / bear"],
  ];

  return (
    <div>
      <div className="tw-flex tw-items-center tw-justify-between tw-gap-3 tw-mb-4">
        <div className="tw-text-[12px] tw-text-text-tertiary">
          {data?.generated_at ? `Срез на ${new Date(data.generated_at).toLocaleString("ru-RU")}` : "Анализ ещё не сформирован"}
          {data?.model_used ? ` · ${data.model_used}` : ""}
        </div>
        <Button onClick={regenerate} disabled={regen} loading={regen} variant="secondary" iconLeft={!regen ? <Zap size={14} /> : null}>
          {regen ? "Анализируем..." : "Обновить анализ"}
        </Button>
      </div>

      {loading ? (
        <div className="tw-flex tw-items-center tw-justify-center tw-py-16 tw-text-text-secondary tw-animate-pulse">Загружаем интерпретацию...</div>
      ) : !data || !data.sections ? (
        <Card><div className="tw-text-[14px] tw-text-text-secondary tw-leading-relaxed">Интерпретация ещё не сформирована. Нажмите «Обновить анализ» — ИИ соберёт связную картину по всем показателям, аналитике ЦБ/ЦМАКП и прогнозу (это рассуждающая модель, займёт ~1-2 минуты).</div></Card>
      ) : (
        <div className="tw-space-y-4">
          <div className="tw-text-[12px] tw-text-text-tertiary tw-italic">Это аналитическая интерпретация Basis (оценка, не факт и не рекомендация «купить/продать»).</div>
          {SECTIONS.map(([key, title]) => data.sections[key] && (
            <Card key={key}>
              <div className="tw-flex tw-items-center tw-gap-2.5 tw--mx-4 tw--mt-4 tw-mb-3 tw-px-4 tw-py-3 tw-bg-accent-soft tw-border-b tw-border-border-subtle">
                <span className="tw-w-1 tw-h-5 tw-rounded-pill tw-bg-accent tw-shrink-0" aria-hidden="true" />
                <h3 className="tw-m-0 tw-text-[15px] tw-font-bold tw-text-text-primary">{title}</h3>
              </div>
              <Prose><ReactMarkdown remarkPlugins={[remarkGfm]} components={ANALYST_MD}>{data.sections[key]}</ReactMarkdown></Prose>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

// =========================
// MARKET MAPS (Обозреватель · Направление 6 — Карты рынка)
// =========================
// Две карты: Тепловая (изменение цены за период) и Недооценённость (апсайд к
// МОДЕЛЬНОЙ справедливой цене). Без сигналов «купить/продать». Тап → карточка.

// Спокойная diverging-шкала (приглушённые зелёный/красный): «цвет в данных».
function _mapTileColor(v, cap) {
  if (v == null) return "rgba(120,120,120,0.06)";
  const t = Math.max(-1, Math.min(1, v / cap));
  const a = 0.10 + 0.55 * Math.abs(t);
  return t >= 0 ? `rgba(46,125,90,${a})` : `rgba(190,68,68,${a})`;
}

function MarketMapTile({ tile, metric, cap, maxCap, onSelect }) {
  const v = metric === "upside" ? tile.upside_pct : tile.change_pct;
  // размер плитки по капитализации (sqrt-сжатие, с минимумом для читаемости)
  const ratio = maxCap > 0 && tile.market_cap ? Math.sqrt(tile.market_cap / maxCap) : 0.4;
  const basis = Math.round(96 + ratio * 150); // 96..246px
  // глиф ▲/▼ — по конституции направление кодируется не только цветом
  const glyph = v == null ? "" : v > 0 ? "▲ " : v < 0 ? "▼ " : "";
  const sign = v == null ? "" : v > 0 ? "+" : "";
  return (
    <button
      onClick={() => onSelect && onSelect(tile.ticker)}
      title={`${tile.name} · ${tile.sector}`}
      style={{ backgroundColor: _mapTileColor(v, cap), flexBasis: basis, flexGrow: 1 }}
      className="tw-min-w-[92px] tw-h-[62px] tw-rounded-md tw-border tw-border-border-subtle tw-px-2 tw-py-1.5 tw-text-left tw-cursor-pointer tw-transition-transform tw-duration-150 hover:tw-scale-[1.03] focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-flex tw-flex-col tw-justify-between"
    >
      <span className="tw-text-[12px] tw-font-semibold tw-text-text-primary tw-font-mono tw-truncate">{tile.ticker}</span>
      <span className="tw-text-[13px] tw-font-mono tw-tabular-nums tw-text-text-primary">
        {v == null ? "—" : `${glyph}${sign}${v.toFixed(metric === "upside" ? 0 : 1)}%`}
      </span>
    </button>
  );
}

function MarketMaps({ token, portfolioOnly, onSelectCompany }) {
  const [mapType, setMapType] = useState("heatmap"); // heatmap | valuation
  const [period, setPeriod] = useState("day");       // day | week | month
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    setLoading(true); setError(false);
    const url = mapType === "heatmap"
      ? `${apiUrl}/api/market/maps/heatmap?period=${period}&portfolio_only=${portfolioOnly}`
      : `${apiUrl}/api/market/maps/valuation?portfolio_only=${portfolioOnly}`;
    fetch(url, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [mapType, period, portfolioOnly, token]);

  const metric = mapType === "valuation" ? "upside" : "change";
  const cap = mapType === "valuation" ? 40 : (period === "month" ? 20 : period === "week" ? 10 : 5);
  const sectors = data?.sectors || [];
  const maxCap = Math.max(1, ...sectors.flatMap((s) => s.tiles.map((t) => t.market_cap || 0)));
  const isEmpty = !loading && !error && sectors.length === 0 && (!data?.uncovered || data.uncovered.length === 0);

  const PERIODS = [{ id: "day", label: "Сутки" }, { id: "week", label: "Неделя" }, { id: "month", label: "Месяц" }];

  return (
    <div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-3">
        Две карты рынка: <b>Тепловая</b> — движение цены за период; <b>Недооценённость</b> —
        потенциал к модельной справедливой цене. Тап по бумаге открывает карточку.
      </p>
      {/* Переключатель карт */}
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-2 tw-mb-4">
        <Chip selected={mapType === "heatmap"} onClick={() => setMapType("heatmap")}>
          <Activity size={13} className="tw-shrink-0" aria-hidden="true" /> Тепловая
        </Chip>
        <Chip selected={mapType === "valuation"} onClick={() => setMapType("valuation")}>
          <BarChart2 size={13} className="tw-shrink-0" aria-hidden="true" /> Недооценённость
        </Chip>
        {mapType === "heatmap" && (
          <div className="tw-flex tw-gap-1 tw-ml-2">
            {PERIODS.map((p) => (
              <button key={p.id} onClick={() => setPeriod(p.id)}
                className={`tw-px-3 tw-py-1 tw-text-[12px] tw-rounded-pill tw-border tw-cursor-pointer tw-transition-colors ${period === p.id ? "tw-border-accent tw-bg-accent-soft tw-text-accent" : "tw-border-border-subtle tw-text-text-secondary hover:tw-border-accent"}`}>
                {p.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Легенда + дисклеймер */}
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-3 tw-mb-5 tw-text-[12px] tw-text-text-tertiary">
        <span className="tw-inline-flex tw-items-center tw-gap-1">
          <span className="tw-w-3 tw-h-3 tw-rounded-sm" style={{ backgroundColor: _mapTileColor(-cap, cap) }} />
          {mapType === "valuation" ? "переоценена" : "снижение"}
        </span>
        <span className="tw-inline-flex tw-items-center tw-gap-1">
          <span className="tw-w-3 tw-h-3 tw-rounded-sm" style={{ backgroundColor: _mapTileColor(cap, cap) }} />
          {mapType === "valuation" ? "потенциал вверх" : "рост"}
        </span>
        <span>· размер плитки — капитализация · тап → карточка</span>
      </div>

      {mapType === "valuation" && (
        <div className="tw-mb-5 tw-flex tw-items-start tw-gap-2 tw-text-[12px] tw-text-text-secondary tw-bg-accent-soft tw-border tw-border-border-subtle tw-rounded-md tw-px-3 tw-py-2">
          <Info size={14} className="tw-shrink-0 tw-mt-0.5 tw-text-accent" aria-hidden="true" />
          <span><b>Модельная оценка, не сигнал на покупку.</b> Цвет — потенциал к <b>модельной</b>
          справедливой цене Basis (считается живьём от текущей цены). Методика и оговорки — в карточке компании.</span>
        </div>
      )}

      {loading && <div className="tw-text-[13px] tw-text-text-tertiary tw-py-10 tw-text-center">Загрузка карты…</div>}
      {error && <div className="tw-text-[13px] tw-text-danger tw-py-10 tw-text-center">Не удалось загрузить карту. Попробуйте позже.</div>}
      {isEmpty && (
        <div className="tw-text-[13px] tw-text-text-tertiary tw-py-10 tw-text-center">
          {portfolioOnly ? "В вашем портфеле нет бумаг для этой карты." : "Нет данных для отображения."}
        </div>
      )}

      {!loading && !error && sectors.map((s) => (
        <div key={s.sector} className="tw-mb-5">
          <div className="tw-flex tw-items-baseline tw-justify-between tw-mb-2">
            <h3 className="tw-text-[14px] tw-font-medium tw-text-text-primary tw-m-0">{s.sector}</h3>
            <span className="tw-text-[11px] tw-text-text-tertiary">{s.tiles.length}</span>
          </div>
          <div className="tw-flex tw-flex-wrap tw-gap-1.5">
            {s.tiles.map((t) => (
              <MarketMapTile key={t.ticker} tile={t} metric={metric} cap={cap} maxCap={maxCap} onSelect={onSelectCompany} />
            ))}
          </div>
        </div>
      ))}

      {/* Недооценённость: непокрытые бумаги отдельной группой */}
      {mapType === "valuation" && !loading && data?.uncovered?.length > 0 && (
        <div className="tw-mt-6 tw-pt-4 tw-border-t tw-border-border-subtle">
          <h3 className="tw-text-[14px] tw-font-medium tw-text-text-secondary tw-mb-2">Оценка недоступна <span className="tw-text-[11px] tw-text-text-tertiary">({data.uncovered.length})</span></h3>
          <div className="tw-flex tw-flex-wrap tw-gap-1.5">
            {data.uncovered.map((t) => (
              <button key={t.ticker} onClick={() => onSelectCompany && onSelectCompany(t.ticker)}
                title={`${t.name} · ${t.sector}`}
                className="tw-min-w-[92px] tw-h-[44px] tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-base tw-px-2 tw-text-left tw-cursor-pointer hover:tw-border-accent focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-flex tw-items-center">
                <span className="tw-text-[12px] tw-font-semibold tw-font-mono tw-text-text-secondary tw-truncate">{t.ticker}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// =========================
// OBSERVER REPORT (Обозреватель · Направление 5 — ИИ-обзор)
// =========================
const _RPT_TYPES = [
  { id: "express", label: "Экспресс", horizon: "±2 дня", time: "~минута", desc: "Ключевые новости и ближайшие события по портфелю" },
  { id: "detailed", label: "Подробный", horizon: "±7 дней", time: "3–5 мин", desc: "Новости недели со связкой влияния, макро, отчёты, календарь" },
  { id: "deep", label: "Глубокий", horizon: "±30 дней", time: "полное чтение", desc: "Месячный обзор: фон, макро, геополитика, карты рынка, темы" },
];

function ObserverReportView({ token, onSelectCompany }) {
  const [type, setType] = useState("express");
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState(null);
  const [collapsed, setCollapsed] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  const loadHistory = () => {
    if (!token) return;
    fetch(`${apiUrl}/api/observer/reports`, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : []).then(setHistory).catch(() => setHistory([]));
  };
  useEffect(loadHistory, [token]);

  const generate = () => {
    setGenerating(true); setError(null); setReport(null);
    fetch(`${apiUrl}/api/observer/reports?type=${type}`, { method: "POST", headers: authHeaders })
      .then((r) => r.json().then((d) => ({ ok: r.ok, d })))
      .then(({ ok, d }) => { if (ok) { setReport(d); loadHistory(); } else setError(d.detail || "Ошибка генерации"); })
      .catch((e) => setError(e.message || "Сетевая ошибка"))
      .finally(() => setGenerating(false));
  };
  const openReport = (id) => {
    fetch(`${apiUrl}/api/observer/reports/${id}`, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : null).then((d) => d && setReport(d)).catch(() => {});
  };

  if (!token) {
    return <div className="tw-text-[13px] tw-text-text-secondary tw-py-10 tw-text-center">
      Войдите, чтобы генерировать персональные сводные отчёты по вашему портфелю.
    </div>;
  }

  const refByKind = (report?.source_refs || []);
  return (
    <div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-4">
        Сводный обзор «что важного происходит» — синтез данных платформы (Лента, Макро, Отчёты,
        Календарь, Геополитика, Карты) под ваш портфель. Строго по данным, со ссылками на источники,
        без рекомендаций. Не является ИИР.
      </p>

      <div className="tw-grid tw-gap-3 tw-mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
        {_RPT_TYPES.map((t) => (
          <button key={t.id} onClick={() => setType(t.id)}
            className={`tw-text-left tw-rounded-lg tw-border tw-px-4 tw-py-3 tw-cursor-pointer tw-transition-colors focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${type === t.id ? "tw-border-accent tw-bg-accent-soft" : "tw-border-border-subtle tw-bg-bg-elevated hover:tw-border-accent"}`}>
            <div className="tw-flex tw-items-baseline tw-gap-2">
              <span className="tw-text-[14px] tw-font-medium tw-text-text-primary">{t.label}</span>
              <span className="tw-text-[11px] tw-text-text-tertiary">{t.horizon} · {t.time}</span>
            </div>
            <p className="tw-text-[12px] tw-text-text-secondary tw-mt-1 tw-m-0">{t.desc}</p>
          </button>
        ))}
      </div>

      <Button onClick={generate} disabled={generating} loading={generating}
        iconLeft={!generating ? <Sparkles size={14} /> : null}>
        {generating ? "Генерируем отчёт…" : "Сгенерировать отчёт"}
      </Button>
      {error && <div className="tw-text-[13px] tw-text-danger tw-mt-3">{error}</div>}

      {report && (
        <Card className="tw-mt-5">
          <div className="tw-flex tw-items-center tw-justify-between tw-gap-2 tw-mb-2">
            <h3 className="tw-text-[16px] tw-font-medium tw-text-text-primary tw-m-0">
              {(_RPT_TYPES.find((x) => x.id === report.report_type) || {}).label || "Отчёт"} · обзор
            </h3>
            <div className="tw-flex tw-items-center tw-gap-2.5 tw-shrink-0">
              <span className="tw-text-[11px] tw-text-text-tertiary">{report.generated_at ? report.generated_at.slice(0, 16).replace("T", " ") : ""}</span>
              <button
                type="button"
                onClick={() => setCollapsed((v) => !v)}
                aria-expanded={!collapsed}
                className="tw-inline-flex tw-items-center tw-gap-1 tw-bg-transparent tw-border-0 tw-cursor-pointer tw-text-[12px] tw-text-accent hover:tw-underline tw-p-0 focus-visible:tw-outline-none focus-visible:tw-shadow-focus"
              >
                {collapsed ? <>Развернуть <ChevronDown size={14} /></> : <>Свернуть <ChevronUp size={14} /></>}
              </button>
            </div>
          </div>
          {!collapsed && (<>
          <div className="tw-max-w-[72ch]">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={ANALYST_MD}>{report.content || ""}</ReactMarkdown>
          </div>
          {refByKind.length > 0 && (
            <div className="tw-mt-4 tw-pt-3 tw-border-t tw-border-border-subtle">
              <div className="tw-text-[11px] tw-uppercase tw-tracking-wide tw-text-text-tertiary tw-mb-2">Источники</div>
              <div className="tw-flex tw-flex-col tw-gap-1">
                {refByKind.map((r, i) => {
                  const kindLabel = { news: "Новость", earnings: "Отчёт", calendar: "Событие", macro: "Макро", geo: "Геополитика" }[r.kind] || r.kind;
                  return (
                  <div key={i} className="tw-text-[12px] tw-text-text-secondary tw-flex tw-items-baseline tw-gap-2">
                    <span className="tw-font-mono tw-text-text-tertiary tw-shrink-0">[{r.ref}]</span>
                    <span className="tw-text-text-tertiary tw-shrink-0 tw-w-[64px]">{kindLabel}</span>
                    {r.ticker
                      ? <button onClick={() => onSelectCompany && onSelectCompany(r.ticker)} className="tw-text-accent tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer hover:tw-underline focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded tw-text-left">{r.title || r.ticker}</button>
                      : r.url
                        ? <a href={r.url} target="_blank" rel="noreferrer" className="tw-text-accent hover:tw-underline focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded tw-truncate">{r.title}</a>
                        : <span className="tw-truncate">{r.title}</span>}
                  </div>
                  );
                })}
              </div>
            </div>
          )}
          <p className="tw-text-[11px] tw-text-text-tertiary tw-mt-3">Синтез по данным платформы. Без рекомендаций. Не является ИИР.</p>
          </>)}
        </Card>
      )}

      {history.length > 0 && (
        <div className="tw-mt-6">
          <h3 className="tw-text-[14px] tw-font-medium tw-text-text-primary tw-mb-2">Мои отчёты</h3>
          <div className="tw-flex tw-flex-col tw-divide-y tw-divide-border-subtle">
            {history.map((h) => (
              <button key={h.id} onClick={() => openReport(h.id)}
                className="tw-flex tw-items-center tw-gap-3 tw-py-2 tw-text-left tw-bg-transparent tw-border-0 tw-cursor-pointer hover:tw-bg-bg-base focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded">
                <Badge tone="neutral">{(_RPT_TYPES.find((x) => x.id === h.report_type) || {}).label || h.report_type}</Badge>
                <span className="tw-text-[11px] tw-text-text-tertiary tw-w-[110px] tw-shrink-0">{h.generated_at ? h.generated_at.slice(0, 16).replace("T", " ") : ""}</span>
                <span className="tw-text-[12px] tw-text-text-secondary tw-truncate tw-flex-1">{h.preview}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// =========================
// GEOPOLITICS VIEW (Обозреватель · Направление 7 — Геополитика)
// =========================
function GeoScenario({ name, label, tone, sc, onSelectCompany }) {
  if (!sc) return null;
  return (
    <div className="tw-rounded-md tw-border tw-border-border-subtle tw-px-3 tw-py-2" style={{ borderLeft: `3px solid ${tone}` }}>
      <div className="tw-flex tw-items-center tw-gap-2 tw-mb-1">
        <span className="tw-text-[12px] tw-font-semibold tw-text-text-primary">{label}</span>
        <Badge tone="neutral">оценка Basis</Badge>
      </div>
      {sc.text && <p className="tw-text-[13px] tw-text-text-secondary tw-m-0 tw-leading-relaxed">{sc.text}</p>}
      {Array.isArray(sc.triggers) && sc.triggers.length > 0 && (
        <div className="tw-text-[11px] tw-text-text-tertiary tw-mt-1.5">Триггеры: {sc.triggers.join(" · ")}</div>
      )}
    </div>
  );
}

function GeoRegionCard({ block, deep, onSelectCompany }) {
  if (!block) return null;
  // Маленький заголовок секции внутри плитки (единый стиль).
  const secLabel = (t) => <div className="tw-text-[11px] tw-uppercase tw-tracking-wide tw-text-text-tertiary tw-mb-2">{t}</div>;
  const hasChips = block.affected_sectors?.length > 0 || block.affected_tickers?.length > 0;
  return (
    // Регион = ГРУППА: заголовок над плитками (на базовом фоне), затем отдельные
    // плитки-сиблинги по темам — НЕ всё в одной большой плитке.
    <div className="tw-flex tw-flex-col tw-gap-2.5">
      <div className="tw-flex tw-items-baseline tw-justify-between tw-gap-2">
        <h3 className="tw-text-[16px] tw-font-semibold tw-text-text-primary tw-m-0">{block.title}</h3>
        {block.in_portfolio && <Badge tone="accent">в портфеле</Badge>}
      </div>

      {/* Плитка: ситуация + кого касается */}
      {(block.status_text || hasChips) && (
        <Card>
          {block.status_text && <p className="tw-text-[14px] tw-text-text-primary tw-leading-[1.6] tw-m-0">{block.status_text}</p>}
          {hasChips && (
            <div className={`tw-flex tw-flex-wrap tw-gap-1.5 tw-items-center ${block.status_text ? "tw-mt-3" : ""}`}>
              {(block.affected_sectors || []).map((s, i) => <Chip key={"s" + i}>{s}</Chip>)}
              {(block.affected_tickers || []).map((t, i) => (
                <button key={"t" + i} onClick={() => onSelectCompany && onSelectCompany(t)}
                  className="tw-font-mono tw-text-[12px] tw-px-2 tw-py-1 tw-rounded-pill tw-border tw-border-border-subtle tw-text-accent tw-bg-transparent tw-cursor-pointer hover:tw-border-accent focus-visible:tw-outline-none focus-visible:tw-shadow-focus">
                  {t}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Плитка: каналы влияния (цветные мини-плитки внутри) */}
      {Array.isArray(block.channels) && block.channels.length > 0 && (
        <Card>
          {secLabel("Каналы влияния")}
          <div className="tw-flex tw-flex-col tw-gap-2">
            {block.channels.map((c, i) => (
              <div key={i} className="tw-rounded-md tw-bg-bg-base tw-border tw-border-border-subtle tw-px-3 tw-py-2">
                <div className="tw-text-[13px] tw-font-semibold tw-text-accent">{c.channel}</div>
                {c.effect && <div className="tw-text-[13px] tw-text-text-secondary tw-leading-[1.55] tw-mt-0.5">{c.effect}</div>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Плитка: сценарии (глубокая аналитика) */}
      {deep && block.scenarios && (
        <Card>
          {secLabel("Сценарии — оценка Basis")}
          <div className="tw-flex tw-flex-col tw-gap-2">
            <GeoScenario label="Базовый" tone="var(--accent)" sc={block.scenarios.base} onSelectCompany={onSelectCompany} />
            <GeoScenario label="Оптимистичный" tone="var(--success)" sc={block.scenarios.bull} onSelectCompany={onSelectCompany} />
            <GeoScenario label="Негативный" tone="var(--danger)" sc={block.scenarios.bear} onSelectCompany={onSelectCompany} />
          </div>
        </Card>
      )}

      {/* Плитка: что это значит для рынков (отдельная плитка-вывод) */}
      {block.market_impact && (
        <Card>
          {secLabel("Что это значит для рынков")}
          <p className="tw-text-[14px] tw-text-text-primary tw-leading-[1.6] tw-m-0">{block.market_impact}</p>
        </Card>
      )}
    </div>
  );
}

function GeopoliticsView({ token, portfolioOnly, onSelectCompany }) {
  const [tab, setTab] = useState("overview"); // overview | deep
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${apiUrl}/api/market/geopolitics?portfolio_only=${portfolioOnly}`, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [portfolioOnly, token]);

  const blocks = (data?.tabs?.[tab]) || [];
  return (
    <div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-3">
        Как геополитика транслируется в рынок и бумаги. Тон нейтральный, без политических оценок.
        Прогнозы — сценарные, «оценка Basis». Не является ИИР.
      </p>
      <div className="tw-flex tw-gap-1 tw-mb-5 tw-border-b tw-border-border-subtle">
        {[{ id: "overview", label: "Обзор" }, { id: "deep", label: "Глубокая аналитика" }].map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`tw-px-4 tw-py-2 tw-text-[14px] tw-font-medium tw-bg-transparent tw-border-0 tw-cursor-pointer tw--mb-px tw-border-b-2 tw-transition-colors tw-rounded-t-sm focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${tab === t.id ? "tw-text-accent tw-border-accent" : "tw-text-text-secondary tw-border-transparent hover:tw-text-text-primary"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="tw-text-[13px] tw-text-text-tertiary tw-py-10 tw-text-center">Загрузка…</div>}
      {error && <div className="tw-text-[13px] tw-text-danger tw-py-10 tw-text-center">Не удалось загрузить геополитику.</div>}
      {!loading && !error && blocks.length === 0 && (
        <div className="tw-text-[13px] tw-text-text-tertiary tw-py-8 tw-text-center">
          {portfolioOnly ? "По бумагам портфеля значимых изменений нет." : "Значимых изменений нет."}
        </div>
      )}
      {!loading && blocks.length > 0 && (
        // gap-7 между РЕГИОНАМИ (внутри региона плитки идут тесной группой gap-2.5),
        // чтобы группы тем разных регионов визуально не сливались.
        <div className="tw-flex tw-flex-col tw-gap-7">
          {blocks.map((b) => (
            <GeoRegionCard key={b.region} block={b} deep={tab === "deep"} onSelectCompany={onSelectCompany} />
          ))}
        </div>
      )}
    </div>
  );
}

// =========================
// EARNINGS FEED (Обозреватель · Направление 3 — Анализ отчётностей)
// =========================
function EarningsFeed({ token, portfolioOnly, onSelectCompany }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
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
  const impTone = { high: "accent", medium: "info", low: "neutral" };
  const pub = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : null;
  return (
    <div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-4">
        Вышедшие отчётности покрываемых компаний: что показал отчёт, одной строкой. Тап → карточка
        с полным «Разбором отчёта» и обновлёнными метриками. Ознакомительно, не ИИР.
      </p>
      {loading && <div className="tw-text-[13px] tw-text-text-tertiary tw-py-10 tw-text-center">Загрузка…</div>}
      {error && <div className="tw-text-[13px] tw-text-danger tw-py-10 tw-text-center">Не удалось загрузить ленту отчётов.</div>}
      {!loading && !error && reports.length === 0 && (
        <div className="tw-text-[13px] tw-text-text-tertiary tw-py-8 tw-text-center">
          {portfolioOnly ? "По бумагам портфеля новых отчётов нет." : "Новых отчётов нет."}
        </div>
      )}
      {!loading && reports.length > 0 && (
        <Card>
          <div className="tw-flex tw-flex-col tw-divide-y tw-divide-border-subtle">
            {reports.map((r, i) => (
              <button key={i} onClick={() => onSelectCompany && onSelectCompany(r.ticker)}
                className="tw-flex tw-items-center tw-gap-3 tw-py-2 tw-text-left tw-bg-transparent tw-border-0 tw-cursor-pointer hover:tw-bg-bg-base focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded">
                <span className="tw-font-mono tw-font-semibold tw-text-text-primary tw-w-[64px] tw-shrink-0">{r.ticker}</span>
                <span className="tw-text-[11px] tw-text-text-tertiary tw-w-[112px] tw-shrink-0">{r.period} · {r.standard || r.report_type}{pub(r.published_at) ? <span className="tw-block tw-text-text-tertiary">вышел {pub(r.published_at)}</span> : null}</span>
                <span className="tw-text-[13px] tw-text-text-secondary tw-truncate tw-flex-1">
                  {r.status === "extract_failed" ? "Отчёт вышел — цифры на проверке" : (r.one_liner || "Разбор готовится…")}
                </span>
                {r.importance && <Badge tone={impTone[r.importance] || "neutral"}>{r.importance === "high" ? "важно" : r.importance === "medium" ? "средне" : "—"}</Badge>}
                <ChevronRight size={14} className="tw-text-text-tertiary tw-shrink-0" />
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

// =========================
// CALENDAR VIEW (Обозреватель · Направление 4 — Календари)
// =========================
const _CAL_TYPES = [
  { id: "", label: "Все" },
  { id: "dividend", label: "Дивиденды" },
  { id: "corporate", label: "Корпсобытия" },
  { id: "macro", label: "Макрорелизы" },
  { id: "bond_offer", label: "Оферты" },
  { id: "bond_maturity", label: "Погашения" },
  { id: "expiration", label: "Экспирации" },
  { id: "ipo", label: "IPO" },
];
const _CAL_TONE = { dividend: "success", macro: "accent", bond_offer: "warning", bond_maturity: "neutral", expiration: "info", ipo: "accent", corporate: "neutral" };
const _CAL_LABEL = { dividend: "Дивиденд", macro: "Макро", bond_offer: "Оферта", bond_maturity: "Погашение", expiration: "Экспирация", ipo: "IPO", corporate: "Корпсобытие" };
const _dmy = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "—";

function CalendarView({ token, portfolioOnly, onSelectCompany }) {
  const [evType, setEvType] = useState("");
  const [scope, setScope] = useState("upcoming"); // upcoming | past
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  useEffect(() => {
    setLoading(true); setError(false);
    const u = `${apiUrl}/api/market/calendar?scope=${scope}&portfolio_only=${portfolioOnly}` + (evType ? `&event_type=${evType}` : "");
    fetch(u, { headers: authHeaders })
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [evType, scope, portfolioOnly, token]);


  const events = data?.events || [];
  const ipoEvents = events.filter((e) => e.type === "ipo");
  const nonIpo = events.filter((e) => e.type !== "ipo");
  // Технические события облигаций/фьючерсов засоряют основной поток — отделяем их
  // в свёрнутую секцию (только в режиме «Все»; при выборе конкретного типа показываем как есть).
  const TECH_TYPES = ["bond_offer", "bond_maturity", "expiration"];
  const splitTech = evType === "";
  const techEvents = splitTech ? nonIpo.filter((e) => TECH_TYPES.includes(e.type)) : [];
  const mainEvents = splitTech ? nonIpo.filter((e) => !TECH_TYPES.includes(e.type)) : nonIpo;

  const calRow = (e) => {
    const p = e.payload || {};
    const clickable = e.ticker && (e.type === "dividend");
    return (
      <div key={e.id} className="tw-flex tw-items-center tw-gap-3 tw-py-2 tw-text-[13px]">
        <span className="tw-font-mono tw-text-text-secondary tw-w-[68px] tw-shrink-0 tw-tabular-nums">{_dmy(e.date)}{e.time ? <span className="tw-block tw-text-[11px] tw-text-text-tertiary">{e.time} МСК</span> : null}</span>
        <Badge tone={_CAL_TONE[e.type] || "neutral"}>{_CAL_LABEL[e.type] || e.type}</Badge>
        <div className="tw-min-w-0 tw-flex-1">
          {clickable
            ? <button onClick={() => onSelectCompany && onSelectCompany(e.ticker)} className="tw-text-text-primary tw-bg-transparent tw-border-0 tw-p-0 tw-cursor-pointer hover:tw-underline focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-text-left tw-truncate tw-max-w-full">{e.title}</button>
            : <span className="tw-text-text-primary tw-truncate tw-block">{e.title}</span>}
          {e.type === "dividend" && (
            <div className="tw-text-[11px] tw-text-text-tertiary tw-mt-0.5">
              Купить до <b className="tw-text-text-secondary">{_dmy(p.buy_by_date)}</b> · отсечка {_dmy(p.record_date)}
              {p.dividend_yield != null && <> · доходность <b className="tw-text-success">▲ {p.dividend_yield}%</b></>}
            </div>
          )}
          {(e.type === "bond_offer" || e.type === "bond_maturity") && (
            <div className="tw-text-[11px] tw-text-text-tertiary tw-mt-0.5">
              {p.coupon_type === "floater" ? "флоатер" : p.coupon_type === "fixed" ? "фикс. купон" : p.coupon_type || ""}
              {p.ytm != null && <> · YTM ~{p.ytm}%{p.yield_indicative ? " (индикативно)" : ""}</>}
              {p.rating && <> · {p.rating}</>}
            </div>
          )}
          {e.status && (e.type === "macro" || e.type === "corporate") && <div className="tw-text-[11px] tw-text-text-tertiary tw-mt-0.5">{e.status}{p.note ? ` · ${p.note}` : ""}</div>}
        </div>
      </div>
    );
  };

  return (
    <div>
      <p className="tw-text-[13px] tw-text-text-secondary tw-mb-3">
        Будущие и прошедшие события рынка: дивиденды (с датами «купить до» и отсечки), макрорелизы,
        оферты и погашения облигаций, экспирации, IPO. Тон справочный, без призывов.
      </p>

      {/* Фильтры: тип + предстоящие/прошедшие (тумблер портфеля — общий в шапке Обозревателя) */}
      <div className="tw-flex tw-flex-wrap tw-items-center tw-gap-1.5 tw-mb-3">
        {_CAL_TYPES.map((t) => (
          <Chip key={t.id || "all"} selected={evType === t.id} onClick={() => setEvType(t.id)}>{t.label}</Chip>
        ))}
      </div>
      <div className="tw-flex tw-gap-1 tw-mb-5">
        {[{ id: "upcoming", label: "Предстоящие" }, { id: "past", label: "Прошедшие" }].map((s) => (
          <button key={s.id} onClick={() => setScope(s.id)}
            className={`tw-px-3 tw-py-1.5 tw-text-[12px] tw-rounded-pill tw-border tw-cursor-pointer tw-transition-colors focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${scope === s.id ? "tw-border-accent tw-bg-accent-soft tw-text-accent" : "tw-border-border-subtle tw-text-text-secondary hover:tw-border-accent"}`}>
            {s.label}
          </button>
        ))}
      </div>

      {loading && <div className="tw-text-[13px] tw-text-text-tertiary tw-py-10 tw-text-center">Загрузка календаря…</div>}
      {error && <div className="tw-text-[13px] tw-text-danger tw-py-10 tw-text-center">Не удалось загрузить календарь.</div>}
      {!loading && !error && mainEvents.length === 0 && (
        <div className="tw-text-[13px] tw-text-text-tertiary tw-py-8 tw-text-center">
          {portfolioOnly ? "В вашем портфеле нет событий в этом фильтре." : "Событий не найдено."}
        </div>
      )}
      {!loading && !error && (evType === "dividend" || evType === "") && scope === "upcoming" && (
        <div className="tw-mb-4 tw-text-[12px] tw-text-text-tertiary tw-bg-bg-base tw-border tw-border-border-subtle tw-rounded-md tw-px-3 tw-py-2">
          Будущие дивиденды появляются здесь после объявления компаниями (источник — листинг MOEX).
          Если выплат нет — значит компании их ещё не анонсировали.
        </div>
      )}

      {!loading && mainEvents.length > 0 && (
        <Card>
          <div className="tw-flex tw-flex-col tw-divide-y tw-divide-border-subtle">
            {mainEvents.map(calRow)}
          </div>
        </Card>
      )}

      {/* Технические события (оферты · погашения · экспирации) — отдельной свёрнутой
          секцией, чтобы не засоряли основной поток. */}
      {!loading && techEvents.length > 0 && (
        <div className="tw-mt-4">
          <Disclosure summary={`Технические события облигаций и фьючерсов — оферты · погашения · экспирации (${techEvents.length})`} defaultOpen={false}>
            <Card className="tw-mt-2">
              <div className="tw-flex tw-flex-col tw-divide-y tw-divide-border-subtle">
                {techEvents.map(calRow)}
              </div>
            </Card>
          </Disclosure>
        </div>
      )}

      {/* IPO / размещения */}
      <div className="tw-mt-8">
        <h3 className="tw-text-[15px] tw-font-medium tw-text-text-primary tw-mb-2">IPO и размещения</h3>
        {ipoEvents.length === 0 ? (
          <div className="tw-text-[13px] tw-text-text-tertiary tw-bg-bg-base tw-border tw-border-border-subtle tw-rounded-md tw-px-3 tw-py-3">Ближайших размещений не анонсировано.</div>
        ) : (
          <div className="tw-flex tw-flex-col tw-gap-2">
            {ipoEvents.map((e) => (
              <Card key={e.id}>
                <div className="tw-flex tw-items-baseline tw-gap-2 tw-mb-1">
                  <Badge tone="accent">IPO/SPO</Badge>
                  <span className="tw-text-[11px] tw-text-text-tertiary">{_dmy(e.date)} · анонс</span>
                </div>
                <div className="tw-text-[13px] tw-text-text-primary">{e.title}</div>
                {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer" className="tw-text-[12px] tw-text-accent hover:tw-underline focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded">источник</a>}
              </Card>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}


export {
  NewsFeed,
  NewsCard,
  MacroChart,
  MacroLineChart,
  MacroIndicatorCard,
  MacroDetailModal,
  MacroView,
  MacroForecastTable,
  MacroInterpreterTab,
  MarketMapTile,
  MarketMaps,
  ObserverReportView,
  GeoScenario,
  GeoRegionCard,
  GeopoliticsView,
  EarningsFeed,
  CalendarView,
};
