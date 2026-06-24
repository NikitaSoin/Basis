/* Вкладка «Финансы и оценка» — гибрид-дизайн, ПОЛНЫЙ перенос прототипа Finance.html.
   Двухколоночный макет: основной поток (dash) + правый рейл «Заметка аналитика».
   Ответ-первым: Разбор отчёта → Справедливая стоимость («поле оценок» с раскрытием
   выкладки методов) → Ключевые показатели + мультипликаторы с контекстом к сектору →
   раскрытие «Прибыль и рентабельность» (SVG-графики динамики, таблицы P&L/Баланс/ОДДС/
   Мультипликаторы с дельтой год-к-году, детализация статей, нормализация) → раскрытие
   «Позиционирование в секторе» (сравнение конкурентов по годам + карты сектора).
   Все числа — из financials.json и эндпоинта peers-multiples; методики (коридор, методы
   оценки) НЕ пересчитываются — берутся из valuation.fair_value_range / methods[].explain
   (заповедник). Служебные поля (data_flags, технические *_note) в UI не выводятся;
   честные оговорки методов сохранены. Работает для любой компании. */
import React, { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "../styles/finance.css";

/* ── helpers ─────────────────────────────────────────────── */
const num = (v, d = 1) =>
  v == null || isNaN(v) ? "—" : Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
function bln(vMln) {
  if (vMln == null || isNaN(vMln)) return { v: "—", u: "" };
  const mlrd = vMln / 1000;
  if (Math.abs(mlrd) >= 1000) return { v: num(mlrd / 1000, 2), u: "трлн ₽" };
  return { v: num(mlrd, Math.abs(mlrd) >= 100 ? 0 : 1), u: "млрд ₽" };
}
const lastN = (a) => (Array.isArray(a) ? [...a].reverse().find((x) => x != null) ?? null : null);
const prevN = (a) => {
  if (!Array.isArray(a)) return null;
  const xs = [...a].reverse().filter((x) => x != null);
  return xs.length > 1 ? xs[1] : null;
};
const yoy = (a) => {
  const c = lastN(a), p = prevN(a);
  return typeof c === "number" && typeof p === "number" && p !== 0 ? ((c - p) / Math.abs(p)) * 100 : null;
};
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const Delta = ({ v, d = 1, pp = false }) =>
  v == null || isNaN(v) ? null : (
    <span className={`delta ${v >= 0 ? "up" : "dn"}`} style={{ fontSize: 11 }}>
      {v >= 0 ? "▲" : "▼"} {num(Math.abs(v), d)} {pp ? "пп" : "%"}
    </span>
  );

const METHOD_LABEL = {
  DCF: "DCF", dcf: "DCF",
  historical_pe: "Истор. P/E (fwd)", historical_pb: "Истор. P/B",
  relative_peers: "Сектор (EV/EBITDA)", relative: "Относительная",
  CAPM: "CAPM 12 мес.", capm: "CAPM 12 мес.",
  dividend: "Дивидендный", ddm: "Дивидендный",
  NAV: "NAV", nav: "NAV", SOTP: "SOTP", sotp: "SOTP",
  pbv_roe: "P/BV × ROE", "P/BV×ROE": "P/BV × ROE",
};
const methodName = (m) => METHOD_LABEL[m] || METHOD_LABEL[String(m || "").toLowerCase()] || String(m || "Метод");

/* ── SVG столбиковый график динамики (порт barChart) ── */
function BarChart({ data, color, fmt }) {
  const xs = (data || []).filter((x) => x != null);
  if (xs.length < 2) return null;
  const w = 176, h = 74, n = xs.length;
  const mn = Math.min(...xs), mx = Math.max(...xs), r = (mx - mn) || 1;
  const pB = 14, plotH = h - 20 - pB, slot = w / n, bw = slot * 0.5;
  const xi = (i) => i * slot + slot / 2;
  const yi = (v) => h - pB - (5 + ((v - mn) / r) * plotH);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block", overflow: "visible" }}>
      {xs.map((v, i) => {
        const bh = 5 + ((v - mn) / r) * plotH, x = xi(i), y = h - pB - bh, last = i === n - 1;
        return <rect key={i} x={(x - bw / 2).toFixed(1)} y={y.toFixed(1)} width={bw.toFixed(1)} height={bh.toFixed(1)} rx="2" fill={color} fillOpacity={last ? 1 : 0.32} />;
      })}
      {xs.map((v, i) => {
        const last = i === n - 1;
        return <text key={i} className="bc-v" x={xi(i)} y={(yi(v) - 5).toFixed(1)} textAnchor="middle" style={last ? { fill: color, fontWeight: 600 } : undefined}>{fmt(v)}</text>;
      })}
    </svg>
  );
}

/* ── карточка мультипликатора с позицией к медиане сектора (порт mcard) ── */
function MCard({ label, value, median, lower, unit }) {
  const has = typeof value === "number" && !isNaN(value);
  const hasMed = typeof median === "number" && !isNaN(median) && median !== 0;
  const fmtV = (x) => num(x, Math.abs(x) >= 100 ? 0 : x >= 10 ? 1 : 2) + (unit === "pct" ? " %" : "×");
  let left = 50, col = "var(--ink-3)", txt = "норма не задана";
  if (has && hasMed) {
    const ratio = value / median, devPct = Math.round((ratio - 1) * 100);
    left = clamp((ratio - 0.4) / (2.5 - 0.4), 0, 1) * 100;
    let good;
    if (lower) {
      good = value < median;
      txt = devPct === 0 ? "на среднем" : devPct > 0 ? `+${devPct}% · дороже среднего` : `${devPct}% · дешевле среднего`;
    } else {
      good = value > median;
      txt = `${devPct >= 0 ? "+" : ""}${devPct}% · ${value >= median ? "выше" : "ниже"} среднего`;
    }
    col = devPct === 0 ? "var(--ink-3)" : good ? "var(--pos)" : "var(--amber)";
  }
  return (
    <div className="mc">
      <div className="mc-top"><span className="mc-l">{label}</span><span className="mc-v">{has ? fmtV(value) : "—"}</span></div>
      {hasMed ? (
        <>
          <div className="mc-track"><span className="mc-med" style={{ left: "50%" }} /><span className="mc-dot" style={{ left: `${left}%`, background: col }} /></div>
          <div className="mc-ctx"><span className="med">среднее {fmtV(median)}</span><span style={{ color: col, fontWeight: 600 }}>{txt}</span></div>
        </>
      ) : (
        <div className="mc-ctx" style={{ marginTop: 9 }}><span className="med">среднее по сектору недоступно</span></div>
      )}
    </div>
  );
}

/* ── кастомный селектор оси (порт ds-sel) ── */
function DSel({ value, options, onPick }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className={`ds-sel${open ? " open" : ""}`} ref={ref}>
      <button className="ds-sel-btn" type="button" onClick={() => setOpen((o) => !o)}>
        {options[value]}
        <svg className="cv" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="ds-sel-menu">
          {Object.keys(options).map((k) => (
            <div key={k} className={`ds-sel-opt${k === value ? " sel" : ""}`} onClick={() => { onPick(k); setOpen(false); }}>{options[k]}</div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── карта сектора (scatter с выбором осей, порт bigScatter) ── */
const AX = { pe: "P/E, ×", ps: "P/S, ×", pb: "P/B, ×", ev_ebitda: "EV/EBITDA, ×", nd_ebitda: "ND/EBITDA, ×", roe: "ROE, %" };
function Scatter({ peers, year, meTicker }) {
  const [yk, setYk] = useState("pb");
  const [xk, setXk] = useState("roe");
  const get = (p, k) => { const r = p.by_year && p.by_year[year]; return r && r[k] != null ? r[k] : null; };
  const pts = (peers || []).filter((p) => get(p, xk) != null && get(p, yk) != null);
  if (pts.length < 2) return <div className="fc-note2">Недостаточно данных конкурентов для карты за {year}.</div>;
  const xs = pts.map((p) => get(p, xk)), ys = pts.map((p) => get(p, yk));
  let xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const xp = (xmax - xmin || 1) * 0.15, yp = (ymax - ymin || 1) * 0.15;
  xmin -= xp; xmax += xp; ymin -= yp; ymax += yp;
  if (xmin > 0) xmin = 0; if (ymin > 0) ymin = 0;
  const W = 620, H = 340, pL = 58, pR = 26, pT = 18, pB = 48;
  const X = (v) => pL + ((v - xmin) / (xmax - xmin)) * (W - pL - pR);
  const Y = (v) => H - pB - ((v - ymin) / (ymax - ymin)) * (H - pT - pB);
  const fn = (v) => num(v, 2);
  const ticks = [0, 1, 2, 3, 4];
  return (
    <div className="fc-scat fc-scat-big">
      <div className="scat-axsel">
        <label>Ось Y</label><DSel value={yk} options={AX} onPick={setYk} />
        <span className="axx">×</span>
        <label>Ось X</label><DSel value={xk} options={AX} onPick={setXk} />
      </div>
      <svg className="bigscat" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
        {ticks.map((i) => { const vx = xmin + (xmax - xmin) * i / 4; return <g key={`x${i}`}><line className="g" x1={X(vx).toFixed(1)} y1={pT} x2={X(vx).toFixed(1)} y2={H - pB} /><text className="tk" x={X(vx).toFixed(1)} y={H - pB + 16} textAnchor="middle">{fn(vx)}</text></g>; })}
        {ticks.map((j) => { const vy = ymin + (ymax - ymin) * j / 4; return <g key={`y${j}`}><line className="g" x1={pL} y1={Y(vy).toFixed(1)} x2={W - pR} y2={Y(vy).toFixed(1)} /><text className="tk" x={pL - 8} y={(Y(vy) + 4).toFixed(1)} textAnchor="end">{fn(vy)}</text></g>; })}
        {xmin < 0 && xmax > 0 && <line className="gz" x1={X(0).toFixed(1)} y1={pT} x2={X(0).toFixed(1)} y2={H - pB} />}
        {ymin < 0 && ymax > 0 && <line className="gz" x1={pL} y1={Y(0).toFixed(1)} x2={W - pR} y2={Y(0).toFixed(1)} />}
        <text className="ax" x={(pL + W - pR) / 2} y={H - 8} textAnchor="middle">{AX[xk]}</text>
        <text className="ax" x="16" y={((pT + H - pB) / 2).toFixed(1)} textAnchor="middle" transform={`rotate(-90 16 ${((pT + H - pB) / 2).toFixed(1)})`}>{AX[yk]}</text>
        {pts.map((p, i) => {
          const me = p.ticker === meTicker, c = me ? "var(--accent)" : "var(--ink-2)", rr = me ? 11 : 8;
          const cx = X(get(p, xk)), cy = Y(get(p, yk));
          return (
            <g className={`bub${me ? " me" : ""}`} key={i}>
              <title>{`${p.ticker}\n${AX[xk]}: ${fn(get(p, xk))}\n${AX[yk]}: ${fn(get(p, yk))}`}</title>
              <circle cx={cx.toFixed(1)} cy={cy.toFixed(1)} r={rr} fill={c} fillOpacity={me ? 0.85 : 0.5} stroke={c} strokeWidth={me ? 2 : 1.3} />
              <text className={`lbl${me ? " me" : ""}`} x={(cx + rr + 3).toFixed(1)} y={(cy + 4).toFixed(1)}>{p.ticker}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ── правый рейл «Заметка аналитика» ── */
const RAIL_MD = {
  h1: () => null, h2: () => null, h3: ({ children }) => <b>{children}</b>,
  p: ({ children }) => <p style={{ margin: "0 0 6px" }}>{children}</p>,
  ul: ({ children }) => <ul style={{ margin: "0 0 6px", paddingLeft: 16 }}>{children}</ul>,
  li: ({ children }) => <li style={{ marginBottom: 2 }}>{children}</li>,
  strong: ({ children }) => <b>{children}</b>,
  table: ({ children }) => <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse", margin: "4px 0" }}>{children}</table>,
  td: ({ children }) => <td style={{ padding: "2px 4px", borderBottom: "1px solid var(--line)" }}>{children}</td>,
  th: ({ children }) => <th style={{ padding: "2px 4px", textAlign: "left", color: "var(--ink-3)" }}>{children}</th>,
};
function parseSections(md) {
  if (!md) return [];
  const parts = md.split(/\n(?=##\s+)/).filter((s) => /^##\s+/.test(s.trim()));
  return parts.map((s) => {
    const m = s.match(/^##\s+(.+)/);
    const title = (m ? m[1] : "Раздел").replace(/^\d+[.)]\s*/, "").trim();
    const body = s.replace(/^##\s+.+\n?/, "").trim();
    return { title, body };
  }).filter((x) => x.body);
}

export default function FinanceTab({ fin, company, price, sectorMult, peersData, finMd }) {
  const [tab, setTab] = useState("pnl");
  const [detOpen, setDetOpen] = useState(false);
  const [peerYear, setPeerYear] = useState(null);
  if (!fin) return null;

  const meta = fin.meta || {};
  const is = fin.income_statement || {};
  const adj = fin.adjusted || {};
  const bs = fin.balance_sheet || {};
  const cf = fin.cash_flow || {};
  const ret = fin.returns || {};
  const mt = fin.metrics_timeseries || {};
  const mult = fin.multiples || {};
  const cur = mult.current || {};
  const hist = mult.historical_avg || {};
  const val = fin.valuation || {};
  const fvr = val.fair_value_range || {};
  const years = (meta.fiscal_years || []).map(String);
  const std = meta.reporting_standard || "МСФО";
  const lastYr = years[years.length - 1] || "";
  const ccy = "₽";

  const livePrice = typeof price === "number" ? price : (fvr.current_price ?? meta.last_price ?? null);
  const ndeArr = (bs.ratios && bs.ratios.net_debt_ebitda) || mt.net_debt_ebitda;
  const nde = lastN(ndeArr);
  const margins = is.margins || {};
  const ebMargin = lastN(margins.ebitda_margin);

  /* 1. Разбор отчёта */
  const revYoy = yoy(is.revenue), npYoy = yoy(is.net_profit), ebYoy = yoy(is.ebitda);
  const rows = [];
  if (lastN(is.revenue) != null) { const b = bln(lastN(is.revenue)); rows.push({ ic: "ok", t: <>Выручка {revYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(revYoy), 1)} %</b> до {b.v} {b.u}</> }); }
  if (lastN(is.ebitda) != null) { const b = bln(lastN(is.ebitda)); rows.push({ ic: "ok", t: <>EBITDA {ebYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(ebYoy), 1)} %</b> до {b.v} {b.u}{ebMargin != null && <>; рентабельность <b>{num(ebMargin, 1)} %</b></>}</> }); }
  if (lastN(is.net_profit) != null) { const b = bln(lastN(is.net_profit)); rows.push({ ic: npYoy >= 0 ? "ok" : "warn", t: <>Чистая прибыль <b>{npYoy >= 0 ? "+" : "−"}{num(Math.abs(npYoy), 1)} %</b> до {b.v} {b.u}</> }); }
  if (nde != null) { const tone = nde < 1.5 ? "ok" : nde <= 3 ? "warn" : "no"; const word = nde < 1.5 ? "низкая" : nde <= 3 ? "умеренная" : "повышенная"; const nd = lastN(bs.net_debt); rows.push({ ic: tone, t: <>{nd != null && <>Чистый долг {bln(nd).v} {bln(nd).u}, </>}<b>ND/EBITDA {num(nde, 2)}×</b> — {word} долговая нагрузка</> }); }
  const verdictHead = (npYoy != null && revYoy != null)
    ? `Чистая прибыль ${npYoy >= 0 ? "выросла" : "снизилась"} на ${num(Math.abs(npYoy), 0)} % при ${revYoy >= 0 ? "росте" : "снижении"} выручки на ${num(Math.abs(revYoy), 1)} %`
    : `Итоги ${lastYr} · ${std}`;

  /* 2. Справедливая стоимость */
  const base = typeof fvr.base === "number" ? fvr.base : null;
  const cons = typeof fvr.conservative === "number" ? fvr.conservative : null;
  const upside = base && livePrice ? (base / livePrice - 1) * 100 : (typeof fvr.upside_downside_pct === "number" ? fvr.upside_downside_pct : null);
  const methods = (val.methods || []).filter((m) => typeof m.fair_value_per_share === "number" && m.fair_value_per_share > 0 && !["not_applicable", "insufficient_data"].includes(m.status));
  const sortedM = [...methods].sort((a, b2) => a.fair_value_per_share - b2.fair_value_per_share);
  const ffVals = [...methods.map((m) => m.fair_value_per_share), base].filter((x) => typeof x === "number" && x > 0);
  const lo = ffVals.length ? Math.min(...ffVals) * 0.9 : 0;
  const hi = ffVals.length ? Math.max(...ffVals) * 1.04 : 1;
  const ffspan = hi - lo || 1;
  const fpos = (v) => clamp(((v - lo) / ffspan) * 100, 0, 100);
  const isAnchor = (m) => (m.horizon && m.horizon !== "intrinsic_now") ? true : (base ? (m.fair_value_per_share < base * 0.6 || m.fair_value_per_share > base * 1.5) : false);
  const toneVsPrice = (v) => (livePrice ? (v > livePrice * 1.05 ? "var(--pos)" : v < livePrice * 0.95 ? "var(--neg)" : "var(--ink-3)") : "var(--accent)");
  const divergenceNote = val.methods_divergence_note;

  /* 3. Ключевые показатели + мультипликаторы */
  const kfi = [
    { l: "Выручка", a: is.revenue, d: revYoy }, { l: "EBITDA", a: is.ebitda, d: ebYoy },
    { l: "Чистая прибыль", a: is.net_profit, d: npYoy }, { l: "FCF", a: cf.fcf, d: yoy(cf.fcf) },
    { l: "Маржа EBITDA", pctv: ebMargin, d: (ebMargin != null && prevN(margins.ebitda_margin) != null) ? ebMargin - prevN(margins.ebitda_margin) : null, isPP: true },
    { l: "Чистый долг", a: bs.net_debt, d: yoy(bs.net_debt) },
  ];
  const sm = sectorMult && company && company.sector && sectorMult[company.sector] && sectorMult[company.sector].n >= 4 ? sectorMult[company.sector] : null;
  const mcards = [
    { label: "P/E", value: cur.pe, median: sm ? sm.pe : (hist.pe_5y_median ?? hist.pe_5y_avg), lower: true, unit: "x" },
    { label: "EV/EBITDA", value: cur.ev_ebitda, median: sm ? sm.ev_ebitda : (hist.ev_ebitda_5y_median ?? hist.ev_ebitda_5y_avg), lower: true, unit: "x" },
    { label: "P/B", value: cur.pb, median: sm ? sm.pb : (hist.pb_5y_median ?? hist.pb_5y_avg), lower: true, unit: "x" },
    { label: "P/S", value: cur.ps, median: sm ? sm.ps : (hist.ps_5y_median ?? hist.ps_5y_avg), lower: true, unit: "x" },
    { label: "ND/EBITDA", value: nde, median: sm ? sm.nd_ebitda : null, lower: true, unit: "x" },
    { label: "ROE", value: lastN(ret.roe), median: sm ? sm.roe : null, lower: false, unit: "pct" },
  ];

  /* 4. Таблицы по годам */
  const yslice = years.slice(-5);
  const sl = (a) => (Array.isArray(a) ? a.slice(-5) : []);
  const pnlRows = [
    { l: "Выручка", a: is.revenue, cls: "bold" },
    { l: "Себестоимость продаж", a: is.cogs, det: true },
    { l: "Валовая прибыль", a: is.gross_profit, det: true },
    { l: "EBITDA", a: is.ebitda, cls: "bold" },
    { l: "Амортизация", a: is.da, det: true },
    { l: "EBIT", a: is.operating_profit, det: true },
    { l: "Чистая прибыль", a: is.net_profit, cls: "bold" },
    { l: "ЧП норм.", a: adj.net_profit_adj, cls: "accent" },
    { l: "Маржа EBITDA", a: margins.ebitda_margin, suf: " %", d: 1 },
    { l: "Рент. (ROS)", a: ret.ros || margins.ros, suf: " %", d: 1 },
  ];
  const TABLES = {
    pnl: pnlRows,
    bs: [
      { l: "Внеоборотные активы", a: bs.non_current_assets },
      { l: "Оборотные активы", a: bs.current_assets },
      { l: "Итого активы", a: bs.total_assets, cls: "bold" },
      { l: "Капитал", a: bs.equity || bs.total_equity || fin.total_equity, cls: "bold" },
      { l: "Чистый долг", a: bs.net_debt, cls: "bold" },
      { l: "ND / EBITDA", a: ndeArr, suf: "×", d: 2, cls: "accent" },
    ],
    cf: [
      { l: "Операционный (CFO)", a: cf.cfo, cls: "bold" },
      { l: "Инвестиционный (CFI)", a: cf.cfi },
      { l: "Капзатраты", a: cf.capex },
      { l: "Финансовый (CFF)", a: cf.cff },
      { l: "Свободный поток (FCF)", a: cf.fcf, cls: "bold accent" },
    ],
    mult: [
      { l: "P/E", a: mult.pe, d: 2 }, { l: "P/B", a: mult.pb, d: 2 },
      { l: "EV/EBITDA", a: mult.ev_ebitda, d: 2 },
      { l: "ROE", a: ret.roe, suf: " %", d: 1, cls: "bold" }, { l: "ROIC", a: ret.roic, suf: " %", d: 1 },
    ],
  };
  const hasTable = (k) => TABLES[k].some((r) => sl(r.a).some((x) => x != null));
  const tabsAvail = ["pnl", "bs", "cf", "mult"].filter(hasTable);
  const curTab = tabsAvail.includes(tab) ? tab : (tabsAvail[0] || "pnl");
  const TLABEL = { pnl: "P&L", bs: "Баланс", cf: "ОДДС", mult: "Мультипликаторы" };
  const yoyAnnotate = curTab !== "mult";
  // ячейка значения
  const fmtCell = (r, v) => {
    if (v == null || isNaN(v)) return "—";
    if (r.suf != null) return num(v, r.d ?? 2) + r.suf;
    if (curTab === "mult") return num(v, r.d ?? 2);
    return bln(v).v;
  };
  const cellDelta = (r, vals, j) => {
    if (!yoyAnnotate || j === 0) return null;
    const cv = vals[j], pv = vals[j - 1];
    if (cv == null || pv == null) return null;
    const isPct = r.suf === " %";
    if (isPct) { const dd = cv - pv; const cls = dd > 0.05 ? "up" : dd < -0.05 ? "dn" : "fl"; return <span className={`yoy ${cls}`}>{dd > 0 ? "▲" : dd < 0 ? "▼" : "▬"} {num(Math.abs(dd), 1)} пп</span>; }
    if (pv === 0) return null;
    const ch = (cv / pv - 1) * 100; const cls = ch > 0.5 ? "up" : ch < -0.5 ? "dn" : "fl";
    return <span className={`yoy ${cls}`}>{ch > 0 ? "▲" : ch < 0 ? "▼" : "▬"} {num(Math.abs(ch), 1)} %</span>;
  };
  const unitNote = curTab === "mult" ? "×, %" : "млрд ₽";

  /* динамика */
  const fmtT = (v) => num(v / 1000, 2), fmtN = (v) => num(v, 0), fmtP = (v) => num(v, 0);
  const dyn = [];
  if (sl(is.revenue).some((x) => x != null)) dyn.push({ l: "Выручка", data: sl(is.revenue).map((v) => v == null ? null : v / 1000), color: "var(--accent)", fmt: fmtT, head: bln(lastN(is.revenue)), d: revYoy, cap: "трлн ₽" });
  if (sl(is.net_profit).some((x) => x != null)) dyn.push({ l: "Чистая прибыль", data: sl(is.net_profit).map((v) => v == null ? null : v / 1000), color: "var(--amber)", fmt: fmtN, head: bln(lastN(is.net_profit)), d: npYoy, cap: "млрд ₽" });
  if (sl(margins.ebitda_margin).some((x) => x != null)) dyn.push({ l: "Маржа EBITDA", data: sl(margins.ebitda_margin), color: "var(--pos)", fmt: fmtP, head: { v: num(ebMargin, 1), u: "%" }, d: (ebMargin != null && prevN(margins.ebitda_margin) != null) ? ebMargin - prevN(margins.ebitda_margin) : null, isPP: true, cap: "% · " });

  /* нормализация (последние 2 года, отчётная → норм.) */
  const normYears = [];
  if (Array.isArray(adj.net_profit_adj) && Array.isArray(is.net_profit)) {
    for (let i = years.length - 1; i >= Math.max(0, years.length - 2); i--) {
      const rep = is.net_profit[i], adv = adj.net_profit_adj[i];
      if (rep != null && adv != null && Math.abs(adv - rep) > 1) normYears.push({ y: years[i], rep, adv, delta: adv - rep });
    }
  }

  /* 5. Позиционирование — конкуренты по годам + карты */
  const peerObj = peersData && company && peersData[company.sector] ? peersData[company.sector] : null;
  const peerYears = peerObj ? peerObj.years : [];
  const activeYear = peerYear || (peerYears.length ? peerYears[peerYears.length - 1] : null);
  const PK = [["pe", false], ["ps", false], ["pb", false], ["ev_ebitda", false], ["nd_ebitda", false], ["roe", true]];
  const peerCell = (p) => p.by_year && p.by_year[activeYear] ? p.by_year[activeYear] : {};
  let peerRows = [], peerAvg = {};
  if (peerObj && activeYear) {
    // компания первой, далее по алфавиту; среднее — без аномальных
    const peers = [...peerObj.peers].sort((a, b2) => (a.ticker === company.ticker ? -1 : b2.ticker === company.ticker ? 1 : a.ticker.localeCompare(b2.ticker)));
    peerRows = peers.filter((p) => p.by_year && p.by_year[activeYear]);
    const sums = {}, cnts = {};
    PK.forEach(([k]) => { sums[k] = 0; cnts[k] = 0; });
    peerRows.forEach((p) => { if (p.anomaly) return; const r = peerCell(p); PK.forEach(([k]) => { if (r[k] != null) { sums[k] += r[k]; cnts[k]++; } }); });
    PK.forEach(([k]) => { peerAvg[k] = cnts[k] ? sums[k] / cnts[k] : null; });
  }
  const pcell = (v, isRoe) => v == null ? "—" : num(v, 2) + (isRoe ? " %" : "");
  const hasAnomalyShown = peerRows.some((p) => p.anomaly);

  /* рейл «Заметка аналитика» */
  const conf = ({ high: "высокая", medium: "средняя", low: "низкая" })[meta.data_quality] || "средняя";
  const sourcesCount = Array.isArray(fin.sources) ? fin.sources.length : null;
  const railSections = parseSections(finMd).slice(0, 6);
  const railVerdict = upside == null ? "" : Math.abs(upside) < 10 ? "оценён справедливо" : upside > 0 ? "есть потенциал роста" : "оценён с премией к модели";
  const caveats = [];
  (val.methods || []).forEach((m) => { const cs = (m.explain && m.explain.caveats) || []; cs.forEach((c) => { if (caveats.length < 3 && c && !caveats.includes(c)) caveats.push(c); }); });

  return (
    <div className="fin-hybrid">
      <div className="layout">
        <div className="dash">
          {/* 1. Разбор отчёта */}
          {rows.length > 0 && (
            <div className="card">
              <h3>Разбор отчёта <span className="tag tag-fact">факт</span><span className="hmeta">{lastYr} · {std}</span></h3>
              <div className="verdict" style={{ marginTop: 14 }}>
                <div className="vh">{verdictHead}</div>
                {rows.map((r, i) => (
                  <div className="vrow" key={i}><span className={`ic ${r.ic}`}>{r.ic === "ok" ? "✓" : r.ic === "warn" ? "!" : "✕"}</span><span>{r.t}</span></div>
                ))}
              </div>
            </div>
          )}

          {/* 2. Справедливая стоимость */}
          {(base || methods.length > 0) && (
            <div className="card">
              <h3>Справедливая стоимость — как сходятся методы <span className="tag tag-judg">суждение</span></h3>
              <p className="sub">«Поле оценок»: каждый метод даёт свою цену; коридор строим по центральному кластеру, крайние методы — внешние якоря</p>
              {base && (
                <div className="fair">
                  <div><div className="big">{num(base, base >= 100 ? 0 : 1)}<s> {ccy}</s></div><div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>база · модельная цена</div></div>
                  {upside != null && <div className={`ud delta ${upside >= 0 ? "up" : "dn"}`}>{upside >= 0 ? "▲" : "▼"} {num(Math.abs(upside), 1)} % {upside >= 0 ? "апсайд" : "даунсайд"}</div>}
                  <div className="corr">коридор<br /><b>{cons != null ? `${num(cons, 0)} – ${num(base, 0)} ${ccy}` : `${num(base, 0)} ${ccy}`}</b>{livePrice && <><br /><span style={{ fontSize: 11 }}>тек. {num(livePrice, 2)} {ccy}</span></>}</div>
                </div>
              )}
              {sortedM.length > 0 && (
                <div className="ff">
                  {base != null && <div className="ff-scale"><span className="ff-faircap" style={{ left: `${fpos(base)}%` }}>справ. {num(base, 0)} {ccy}</span></div>}
                  {sortedM.map((m, i) => {
                    const v = m.fair_value_per_share, anchor = isAnchor(m), dv = livePrice ? (v / livePrice - 1) * 100 : null;
                    return (
                      <div className="ff-row" key={i}>
                        <span className="ff-nm"><span className={anchor ? "anch" : "clust"} />{methodName(m.method)}</span>
                        <span className="ff-track">{base != null && <span className="curl" style={{ left: `${fpos(base)}%` }} />}<span className="ff-dot" style={{ left: `${fpos(v)}%`, background: toneVsPrice(v) }} /></span>
                        <span className="ff-val"><span className="pv">{num(v, v >= 100 ? 1 : 1)}</span>{dv != null && <span className={`pd delta ${dv >= 0 ? "up" : "dn"}`}>{dv >= 0 ? "+" : "−"}{num(Math.abs(dv), 0)} %</span>}</span>
                      </div>
                    );
                  })}
                  <div className="ff-axis"><span style={{ left: 0, transform: "translateX(0)" }}>{num(lo, 0)} {ccy}</span><span style={{ left: "50%" }}>{num((lo + hi) / 2, 0)} {ccy}</span><span style={{ left: "100%", transform: "translateX(-100%)" }}>{num(hi, 0)} {ccy}</span></div>
                </div>
              )}
              {divergenceNote && <div className="ff-note"><div className="nh">Честно · почему методы расходятся</div>{divergenceNote}</div>}
              {sortedM.length > 0 && (
                <>
                  <div className="subh" style={{ marginTop: 20 }}>Выводы по методам · раскройте любой</div>
                  <div className="methods">
                    {sortedM.map((m, i) => {
                      const v = m.fair_value_per_share, anchor = isAnchor(m), dv = livePrice ? (v / livePrice - 1) * 100 : null, ex = m.explain || {};
                      const inputs = ex.inputs && typeof ex.inputs === "object" ? Object.entries(ex.inputs) : [];
                      const ka = (!inputs.length && m.key_assumptions && typeof m.key_assumptions === "object") ? Object.entries(m.key_assumptions) : [];
                      const steps = Array.isArray(ex.steps) ? ex.steps : [];
                      const cav = Array.isArray(ex.caveats) ? ex.caveats : [];
                      return (
                        <details className="m-acc" key={i}>
                          <summary>
                            <span className="mn"><span className={anchor ? "anch" : "clust"} />{methodName(m.method)}{m.horizon && m.horizon !== "intrinsic_now" && <s>горизонт {m.horizon}</s>}</span>
                            <span className="mv" style={{ color: toneVsPrice(v) }}>{num(v, v >= 100 ? 1 : 2)} {ccy}</span>
                            {dv != null ? <span className={`md delta ${dv >= 0 ? "up" : "dn"}`}>{dv >= 0 ? "+" : "−"}{num(Math.abs(dv), 0)} %</span> : <span className="md" />}
                            <span className="chev">▾</span>
                          </summary>
                          <div className="m-body">
                            {(inputs.length > 0 || ka.length > 0) && <><div className="subh">Входные данные</div><div className="fc-kv">{(inputs.length ? inputs : ka).map(([k, vv], j) => (<React.Fragment key={j}><span className="k">{k}</span><span className="v">{String(vv)}</span></React.Fragment>))}</div></>}
                            {steps.length > 0 && <><div className="subh">Решение по шагам</div><ol className="fc-steps">{steps.map((s, j) => <li key={j}>{s}</li>)}</ol></>}
                            {cav.length > 0 && <><div className="subh">Оговорки</div>{cav.map((c, j) => <div className="fc-warn" key={j}>{c}</div>)}</>}
                            {!inputs.length && !ka.length && !steps.length && !cav.length && <div className="fc-note">Выкладка метода не детализирована.</div>}
                          </div>
                        </details>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          )}

          {/* 3. Ключевые показатели и мультипликаторы */}
          <div className="card">
            <h3>Ключевые показатели и мультипликаторы <span className="tag tag-fact">факт</span><span className="hmeta">{livePrice ? `цена ${num(livePrice, 2)} ${ccy} · ` : ""}позиция к {sm ? "среднему по сектору" : "своей 5-летней норме"}</span></h3>
            <p className="sub">Масштаб бизнеса — абсолютные показатели за {lastYr} ({std})</p>
            <div className="kfi">
              {kfi.map((k, i) => { const b = k.pctv != null ? { v: num(k.pctv, 1), u: "%" } : bln(lastN(k.a)); return (<div className="kf" key={i}><span className="kf-l">{k.l}</span><span className="kf-v">{b.v}<s> {b.u}</s></span><span className="kf-d">{k.d != null && <Delta v={k.d} pp={k.isPP} />}</span></div>); })}
            </div>
            <p className="sub" style={{ marginTop: 16 }}>Мультипликаторы — не просто число, а позиция относительно {sm ? "среднего по сектору" : "собственной 5-летней нормы"}</p>
            <div className="mcards">{mcards.map((m, i) => <MCard key={i} {...m} />)}</div>
          </div>

          {/* 4. Прибыль и рентабельность */}
          {tabsAvail.length > 0 && (
            <details className="disc" open>
              <summary><div><div className="dt">Прибыль и рентабельность по годам</div><div className="dd">Графики динамики · отчётность за {yslice.length} лет · нормализация прибыли</div></div><span className="tag tag-fact" style={{ marginLeft: 8 }}>факт</span><span className="tag tag-est">оценка</span><span className="chev">▾</span></summary>
              <div className="disc-body">
                {dyn.length > 0 && (<>
                  <div className="subh">Динамика {yslice[0]}–{lastYr}</div>
                  <div className="fc-dyn">
                    {dyn.map((d, i) => (
                      <div className="d" key={i}>
                        <div className="dl">{d.l}</div>
                        <div className="dv">{d.head.v}<s> {d.head.u}</s> {d.d != null && <Delta v={d.d} pp={d.isPP} />}</div>
                        <BarChart data={d.data} color={d.color} fmt={d.fmt} />
                        <div className="bc-cap">{d.cap}{d.cap.endsWith("· ") ? "" : " · "}{yslice[0]}–{lastYr}</div>
                      </div>
                    ))}
                  </div>
                </>)}

                <div className="subh">Отчётность и мультипликаторы</div>
                <div className="mtbar">
                  <div className="miniseg">{tabsAvail.map((k) => <button key={k} className={curTab === k ? "on" : ""} onClick={() => setTab(k)}>{TLABEL[k]}</button>)}</div>
                  {curTab === "pnl" && <button className={`det-toggle${detOpen ? " on" : ""}`} type="button" onClick={() => setDetOpen((o) => !o)}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M7 12h10M10 18h4" /></svg>
                    <span>Детализация статей</span>
                    <svg className="di" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 9l6 6 6-6" /></svg>
                  </button>}
                </div>
                <div className="tbl-scroll">
                  <table className="ftbl">
                    <thead><tr><th>{unitNote}</th>{yslice.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                    <tbody>
                      {TABLES[curTab].map((r, i) => {
                        if (r.det && !detOpen) return null;
                        const vals = sl(r.a);
                        if (!vals.some((x) => x != null)) return null;
                        return (<tr className={r.cls || ""} key={i}><td>{r.l}</td>{yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j])}</span>{cellDelta(r, vals, j)}</td>)}</tr>);
                      })}
                    </tbody>
                  </table>
                </div>

                {normYears.length > 0 && (<>
                  <div className="subh">Нормализация прибыли · отчётная → скорректированная</div>
                  <table className="fc-norm"><tbody>
                    {normYears.map((nz, i) => (
                      <React.Fragment key={i}>
                        <tr className="yr"><td colSpan="3">{nz.y} · отчётная {num(nz.rep / 1000, 1)} → <span style={{ color: "var(--pos)" }}>норм. {num(nz.adv / 1000, 1)} млрд</span></td></tr>
                        <tr><td>{nz.delta >= 0 ? "+ " : "− "}Разовые (обесценение, курсовые), нетто налога</td><td className={`amt ${nz.delta >= 0 ? "pos" : "neg"}`}>{nz.delta >= 0 ? "+" : "−"}{num(Math.abs(nz.delta) / 1000, 1)}</td><td className="lvl"><span className="tg fc-tg-e">оценка</span></td></tr>
                      </React.Fragment>
                    ))}
                  </tbody></table>
                  <div className="fc-note">Корректировки нормализуют разовые статьи (обесценение, курсовые) — операционный результат ровнее отчётной строки. Источник чисел — financials.json (adjusted).</div>
                </>)}
                <div className="foot-note">Числа карточки — из единого источника financials.json ({std}). Для циклических компаний P/E на отдельном годе менее надёжен, чем EV/EBITDA и P/B.</div>
              </div>
            </details>
          )}

          {/* 5. Позиционирование в секторе */}
          {peerObj && peerRows.length > 1 && (
            <details className="disc" open>
              <summary><div><div className="dt">Позиционирование в секторе</div><div className="dd">Сравнение с конкурентами по годам · карты мультипликаторов</div></div><span className="tag tag-est" style={{ marginLeft: 8 }}>оценка</span><span className="chev">▾</span></summary>
              <div className="disc-body">
                <div className="subh" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                  <span>Сравнение с конкурентами</span>
                  <div className="miniseg" style={{ textTransform: "none", letterSpacing: 0 }}>{peerYears.map((y) => <button key={y} className={activeYear === y ? "on" : ""} onClick={() => setPeerYear(y)}>{y}</button>)}</div>
                </div>
                <div className="tbl-scroll">
                  <table className="ftbl">
                    <thead><tr><th>Тикер</th><th>P/E</th><th>P/S</th><th>P/B</th><th>EV/EBITDA</th><th>ND/EBITDA</th><th>ROE</th></tr></thead>
                    <tbody>
                      {peerRows.map((p) => { const r = peerCell(p); const me = p.ticker === company.ticker; return (<tr className={me ? "me" : ""} key={p.ticker}><td>{p.ticker}{p.anomaly ? " *" : ""}</td>{PK.map(([k, isRoe]) => <td key={k}>{pcell(r[k], isRoe)}</td>)}</tr>); })}
                      <tr className="med"><td>Среднее сектора</td>{PK.map(([k, isRoe]) => <td key={k}>{pcell(peerAvg[k], isRoe)}</td>)}</tr>
                    </tbody>
                  </table>
                </div>
                <div className="subh">Карты сектора <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0, color: "var(--ink-3)" }}>· наведите на точку для тикера</span></div>
                <Scatter peers={peerRows} year={activeYear} meTicker={company.ticker} />
                <div className="fc-note2">Сравнение по внутренним мультипликаторам Basis за {activeYear} ({std}).{hasAnomalyShown ? " * — компании с искажёнными мультипликаторами (внутригрупповые операции, низкий free-float) исключены из среднего." : ""}</div>
              </div>
            </details>
          )}

          <p className="foot-note">Композитная оценка, перцентили и нормализация — аналитические ориентиры Basis по вселенной сектора. Это не инвестиционная рекомендация и не сигнал к покупке или продаже.</p>
        </div>

        {/* правый рейл — Заметка аналитика */}
        <aside className="fv-rail">
          <div className="eyebrow">Заметка аналитика</div>
          {base && <div className="an-fv"><span className="b">{num(base, base >= 100 ? 0 : 1)}<s> {ccy}</s></span>{upside != null && <span className={`u delta ${upside >= 0 ? "up" : "dn"}`}>{upside >= 0 ? "▲" : "▼"} {num(Math.abs(upside), 0)} %</span>}</div>}
          <div className="an-meta">Справедливая стоимость{cons != null && base != null && <> · коридор <b>{num(cons, 0)}–{num(base, 0)} {ccy}</b></>} · уверенность <b>{conf}</b>{sourcesCount ? <> · {sourcesCount} источн.</> : null}</div>
          {(railVerdict || (npYoy != null && revYoy != null)) && <div className="hx-vsub"><b>{railVerdict ? railVerdict.charAt(0).toUpperCase() + railVerdict.slice(1) + "." : ""}</b>{npYoy != null && revYoy != null && <> Прибыль {npYoy >= 0 ? "+" : "−"}{num(Math.abs(npYoy), 0)} % при выручке {revYoy >= 0 ? "+" : "−"}{num(Math.abs(revYoy), 1)} %.</>}</div>}

          {railSections.length > 0 && <>
            <div className="an-sec">Разбор по разделам</div>
            {railSections.map((s, i) => (
              <details className="an-note" key={i} open={i === 0}>
                <summary><span className="nn">{i + 1}</span><span className="nt">{s.title}</span><span className="nc">▾</span></summary>
                <div className="an-body"><ReactMarkdown remarkPlugins={[remarkGfm]} components={RAIL_MD}>{s.body}</ReactMarkdown></div>
              </details>
            ))}
          </>}

          {caveats.length > 0 && <>
            <div className="an-sec">Ограничения данных</div>
            <div className="an-flags">{caveats.map((c, i) => <div className="an-flag" key={i}>{c}</div>)}</div>
          </>}

          <p className="fv-note">Заметка аналитика-агента Basis — аналитический ориентир, не инвестиционная рекомендация.</p>
        </aside>
      </div>
    </div>
  );
}
