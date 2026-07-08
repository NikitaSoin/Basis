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
function MCard({ label, value, median, lower, unit, lossValue }) {
  const has = typeof value === "number" && !isNaN(value);
  const hasMed = typeof median === "number" && !isNaN(median) && median !== 0;
  const isLoss = !has && typeof lossValue === "number" && lossValue < 0;
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
      <div className="mc-top">
        <span className="mc-l">{label}</span>
        <span className="mc-v">
          {has
            ? fmtV(value)
            : isLoss
              ? <span style={{ color: "var(--ink-3)" }}>—</span>
              : <span style={{ color: "var(--ink-3)", fontSize: 12 }}>н.д.</span>}
        </span>
      </div>
      {!has ? (
        <div className="mc-ctx" style={{ marginTop: 9 }}>
          <span className="med" style={{ fontStyle: "italic" }}>
            {isLoss ? "убыток — неприменимо" : "нет данных"}
          </span>
        </div>
      ) : hasMed ? (
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
  const wrapRef = useRef(null);
  const [tip, setTip] = useState(null);
  const showTip = (e, p) => { const r = wrapRef.current && wrapRef.current.getBoundingClientRect(); if (!r) return; setTip({ left: e.clientX - r.left, top: e.clientY - r.top, t: p.ticker, xv: fn(get(p, xk)), yv: fn(get(p, yk)) }); };
  return (
    <div className="fc-scat fc-scat-big" ref={wrapRef}>
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
            <g className={`bub${me ? " me" : ""}`} key={i} onMouseEnter={(e) => showTip(e, p)} onMouseMove={(e) => showTip(e, p)} onMouseLeave={() => setTip(null)}>
              <circle cx={cx.toFixed(1)} cy={cy.toFixed(1)} r={rr} fill={c} fillOpacity={me ? 0.85 : 0.5} stroke={c} strokeWidth={me ? 2 : 1.3} />
              <text className={`lbl${me ? " me" : ""}`} x={(cx + rr + 3).toFixed(1)} y={(cy + 4).toFixed(1)}>{p.ticker}</text>
            </g>
          );
        })}
      </svg>
      {tip && (
        <div className="scat-tip" style={{ opacity: 1, left: Math.min(tip.left + 14, (wrapRef.current ? wrapRef.current.clientWidth : 600) - 150), top: tip.top + 14 }}>
          <b>{tip.t}</b>{AX[xk]}: {tip.xv}<br />{AX[yk]}: {tip.yv}
        </div>
      )}
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

  // Единица отчётности РАЗНАЯ по компаниям (млн / млрд / тыс) — приводим денежные
  // суммы к млн (внутренняя норма bln), иначе у OZON «млрд» рисуется как «млн».
  const U = ({ "млн": 1, "млрд": 1000, "тыс": 0.001, "тысячи": 0.001, "тыс. руб.": 0.001 })[meta.unit] ?? 1;
  const B = (v) => bln(v == null || isNaN(v) ? null : v * U); // денежное значение → {v,u} в млрд/трлн

  // ── полные статьи отчётности (как в прежнем рендере): вложенные объекты баланса,
  // статьи затрат, потоки ОДДС, банковский профиль ── */
  const isBank = meta.profile === "bank";
  const adjBlk = fin.adjusted || {};
  const bp = fin.bank_pnl || {}, bmx = fin.bank_metrics || {};
  const ga = (o, k) => (o && Array.isArray(o[k]) && o[k].some((x) => x != null)) ? o[k] : null;
  const orSum = (explicit, comps) => {
    if (Array.isArray(explicit) && explicit.some((x) => x != null)) return explicit;
    const cs = comps.filter(Array.isArray);
    if (!cs.length) return null;
    const n = Math.max(...cs.map((a) => a.length));
    const out = Array.from({ length: n }, (_, i) => { let s = null; cs.forEach((a) => { if (a[i] != null) s = (s ?? 0) + a[i]; }); return s; });
    return out.some((x) => x != null) ? out : null;
  };
  // bmA — банковские метрики добывались разными агентами с разными именами полей.
  // Перебирает алиасы и возвращает первый непустой массив.
  const bmA = (...names) => {
    for (const n of names) { const a = ga(bmx, n); if (a) return a; }
    return null;
  };
  // ── Pre-computed bank arrays (used in rows, kfi, mcards, pnlRows) ──────────
  const bNipArr  = isBank ? (ga(bp,"net_interest_income") || null) : null;
  const bNpArr   = isBank ? (ga(bp,"net_profit") || ga(is,"net_profit") || null) : null;
  const bRoeArr  = isBank ? bmA("roe","roe_pct","roe_rep_pct","roe_reported_pct","roe_reported") : null;
  const bNimArr  = isBank ? bmA("nim","nim_pct","nim_proxy_pct") : null;
  const bN10Arr  = isBank ? bmA("n1_0","capital_adequacy_n10","capital_adequacy","capital_adequacy_h1_0_pct","capital_adequacy_h1") : null;
  const bLoanArr = isBank ? (bmA("loan_portfolio","loan_portfolio_gross","loan_portfolio_net_mln","loan_portfolio_mln","loans_gross") || ga(bs,"net_loans") || ga(bs,"gross_loans")) : null;
  const bDepArr  = isBank ? (ga(bs,"customer_deposits") || bmA("deposits","deposits_mln")) : null;
  const bProvArr = isBank ? (ga(bp,"provisions") || ga(bp,"impairment_charges")) : null;
  const bNfiArr  = isBank ? (ga(bp,"net_fee_income") || null) : null;
  const bTradArr = isBank ? ga(bp,"trading_income") : null;
  const bInsArr  = isBank ? ga(bp,"net_insurance_income") : null;
  // Итоговый массив операционных доходов (explicit или сумма компонент)
  const bOpFinalArr = isBank
    ? orSum(ga(bp,"operating_income"), [bNipArr, bNfiArr, bInsArr, ga(bp,"other_income")])
    : null;
  // Computed: "Прочие операционные доходы" — plug = bOpFinal − сумма известных компонент
  const bOtherOpArr = isBank && bOpFinalArr ? (() => {
    const comps = [bNipArr, bNfiArr, bTradArr, bInsArr].filter(Array.isArray);
    if (!comps.length) return null;
    const len = Math.max(bOpFinalArr.length, ...comps.map((a) => a.length));
    const out = Array.from({ length: len }, (_, i) => {
      const oi = bOpFinalArr[i]; if (oi == null) return null;
      let sub = 0; comps.forEach((a) => { if (a[i] != null) sub += a[i]; });
      const diff = oi - sub;
      return Math.abs(diff) > Math.abs(oi) * 0.05 ? diff : null;
    });
    return out.some((x) => x != null) ? out : null;
  })() : null;
  // Computed: "ОД после резервов" = bOpFinal − |provisions|
  const bOpAfterProvArr = isBank && bOpFinalArr && bProvArr ? (() => {
    const len = Math.max(bOpFinalArr.length, bProvArr.length);
    const out = Array.from({ length: len }, (_, i) => {
      const oi = bOpFinalArr[i], prov = bProvArr[i];
      if (oi == null || prov == null) return null;
      return oi - Math.abs(prov);
    });
    return out.some((x) => x != null) ? out : null;
  })() : null;
  const eqb = (bs.equity && !Array.isArray(bs.equity)) ? bs.equity : {};
  const nca = bs.non_current_assets || {}, cua = bs.current_assets || {};
  const ncl = bs.non_current_liabilities || {}, cul = bs.current_liabilities || {};
  const totalEquityArr = ga(bs, "total_equity") || ga(eqb, "total_equity") || (Array.isArray(bs.equity) ? bs.equity : fin.total_equity);
  const costFmt = is.cost_format || ((Array.isArray(is.cogs) && is.cogs.some((x) => x != null)) ? "by_function" : "by_nature");
  const isByFunc = costFmt === "by_function";
  const expLines = Array.isArray(is.expense_lines) ? is.expense_lines : [];
  const rosArr = (margins.ros && margins.ros.some && margins.ros.some((x) => x != null)) ? margins.ros : margins.net_margin;

  /* 1. Разбор отчёта */
  const revYoy = yoy(is.revenue), npYoy = yoy(is.net_profit), ebYoy = yoy(is.ebitda);
  const bNipYoy = isBank ? yoy(bNipArr) : null;
  const bNpYoy  = isBank ? yoy(bNpArr)  : null;
  const rows = [];
  if (isBank) {
    if (lastN(bNipArr) != null) { const b = B(lastN(bNipArr)); rows.push({ ic: bNipYoy >= 0 ? "ok" : "warn", t: <>ЧПД {bNipYoy != null ? <><b>{bNipYoy >= 0 ? "+" : "−"}{num(Math.abs(bNipYoy), 1)} %</b> </> : ""}до {b.v} {b.u}</> }); }
    if (lastN(bNpArr) != null) { const b = B(lastN(bNpArr)); rows.push({ ic: bNpYoy >= 0 ? "ok" : "warn", t: <>Чистая прибыль {bNpYoy != null ? <><b>{bNpYoy >= 0 ? "+" : "−"}{num(Math.abs(bNpYoy), 1)} %</b> </> : ""}до {b.v} {b.u}</> }); }
    const roeVal = lastN(bRoeArr); if (roeVal != null) { const tone = roeVal >= 15 ? "ok" : roeVal >= 8 ? "warn" : "no"; rows.push({ ic: tone, t: <>ROE <b>{num(roeVal, 1)} %</b> — {roeVal >= 15 ? "высокая" : roeVal >= 8 ? "умеренная" : "низкая"} рентабельность капитала</> }); }
    const n10Val = lastN(bN10Arr); if (n10Val != null) { const tone = n10Val >= 12 ? "ok" : n10Val >= 8 ? "warn" : "no"; rows.push({ ic: tone, t: <>Достаточность капитала Н1.0 <b>{num(n10Val, 1)} %</b> — {n10Val >= 12 ? "выше нормы" : n10Val >= 8 ? "у минимума" : "ниже нормы"}</> }); }
  } else {
    if (lastN(is.revenue) != null) { const b = B(lastN(is.revenue)); rows.push({ ic: "ok", t: <>Выручка {revYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(revYoy), 1)} %</b> до {b.v} {b.u}</> }); }
    if (lastN(is.ebitda) != null) { const b = B(lastN(is.ebitda)); rows.push({ ic: "ok", t: <>EBITDA {ebYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(ebYoy), 1)} %</b> до {b.v} {b.u}{ebMargin != null && <>; рентабельность <b>{num(ebMargin, 1)} %</b></>}</> }); }
    if (lastN(is.net_profit) != null) { const b = B(lastN(is.net_profit)); rows.push({ ic: npYoy >= 0 ? "ok" : "warn", t: <>Чистая прибыль <b>{npYoy >= 0 ? "+" : "−"}{num(Math.abs(npYoy), 1)} %</b> до {b.v} {b.u}</> }); }
    if (nde != null) { const tone = nde < 1.5 ? "ok" : nde <= 3 ? "warn" : "no"; const word = nde < 1.5 ? "низкая" : nde <= 3 ? "умеренная" : "повышенная"; const nd = lastN(bs.net_debt); rows.push({ ic: tone, t: <>{nd != null && <>Чистый долг {B(nd).v} {B(nd).u}, </>}<b>ND/EBITDA {num(nde, 2)}×</b> — {word} долговая нагрузка</> }); }
  }
  const verdictHead = isBank
    ? (bNpYoy != null
        ? `Чистая прибыль ${bNpYoy >= 0 ? "выросла" : "снизилась"} на ${num(Math.abs(bNpYoy), 0)} %${bNipYoy != null ? ` при ${bNipYoy >= 0 ? "росте" : "снижении"} ЧПД на ${num(Math.abs(bNipYoy), 1)} %` : ""}`
        : `Итоги ${lastYr} · ${std}`)
    : ((npYoy != null && revYoy != null)
        ? `Чистая прибыль ${npYoy >= 0 ? "выросла" : "снизилась"} на ${num(Math.abs(npYoy), 0)} % при ${revYoy >= 0 ? "росте" : "снижении"} выручки на ${num(Math.abs(revYoy), 1)} %`
        : `Итоги ${lastYr} · ${std}`);

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
  const kfi = isBank ? [
    { l: "Чистый процентный доход", a: bNipArr,  d: bNipYoy },
    { l: "Чистая прибыль",          a: bNpArr,   d: bNpYoy },
    { l: "ROE",        pctv: lastN(bRoeArr), d: yoy(bRoeArr),  isPP: true },
    { l: "ЧПМ (NIM)", pctv: lastN(bNimArr), d: yoy(bNimArr),  isPP: true },
    { l: "Кредитный портфель", a: bLoanArr, d: yoy(bLoanArr) },
    { l: "Средства клиентов",  a: bDepArr,  d: yoy(bDepArr)  },
  ] : [
    { l: "Выручка", a: is.revenue, d: revYoy }, { l: "EBITDA", a: is.ebitda, d: ebYoy },
    { l: "Чистая прибыль", a: is.net_profit, d: npYoy }, { l: "FCF", a: cf.fcf, d: yoy(cf.fcf) },
    { l: "Маржа EBITDA", pctv: ebMargin, d: (ebMargin != null && prevN(margins.ebitda_margin) != null) ? ebMargin - prevN(margins.ebitda_margin) : null, isPP: true },
    { l: "Чистый долг", a: bs.net_debt, d: yoy(bs.net_debt) },
  ];
  const sm = sectorMult && company && company.sector && sectorMult[company.sector] && sectorMult[company.sector].n >= 4 ? sectorMult[company.sector] : null;
  const npLast = lastN(is.net_profit);
  const ebLast = lastN(is.ebitda);
  const bNpLast = isBank ? lastN(bNpArr) : null;
  const mcards = isBank ? [
    { label: "P/E",        value: cur.pe,  median: sm ? sm.pe : (hist.pe_5y_median ?? hist.pe_5y_avg), lower: true,  unit: "x", lossValue: bNpLast },
    { label: "P/B",        value: cur.pb,  median: sm ? sm.pb : (hist.pb_5y_median ?? hist.pb_5y_avg), lower: true,  unit: "x", lossValue: bNpLast },
    { label: "ROE",        value: lastN(bRoeArr), median: sm ? sm.roe : null, lower: false, unit: "pct" },
    { label: "ЧПМ (NIM)", value: lastN(bNimArr), median: null, lower: false, unit: "pct" },
    { label: "CoR",        value: lastN(bmA("cost_of_risk","cor","cor_pct","cost_of_risk_pct","cost_of_risk_pct_implied")), median: null, lower: true, unit: "pct" },
    { label: "CIR",        value: lastN(bmA("cir","cir_pct")), median: null, lower: true, unit: "pct" },
  ] : [
    { label: "P/E",       value: cur.pe,       median: sm ? sm.pe       : (hist.pe_5y_median       ?? hist.pe_5y_avg),       lower: true,  unit: "x",   lossValue: npLast },
    { label: "EV/EBITDA", value: cur.ev_ebitda, median: sm ? sm.ev_ebitda: (hist.ev_ebitda_5y_median ?? hist.ev_ebitda_5y_avg), lower: true,  unit: "x",   lossValue: ebLast },
    { label: "P/B",       value: cur.pb,       median: sm ? sm.pb       : (hist.pb_5y_median       ?? hist.pb_5y_avg),       lower: true,  unit: "x",   lossValue: npLast },
    { label: "P/S",       value: cur.ps,       median: sm ? sm.ps       : (hist.ps_5y_median       ?? hist.ps_5y_avg),       lower: true,  unit: "x",   lossValue: npLast },
    { label: "ND/EBITDA", value: nde,           median: sm ? sm.nd_ebitda: null,                                              lower: true,  unit: "x" },
    { label: "ROE",       value: lastN(ret.roe), median: sm ? sm.roe     : null,                                              lower: false, unit: "pct" },
  ];

  /* 4. Таблицы по годам — ПОЛНЫЕ статьи (как в прежнем рендере). kind: money|pct|ratio|x|rub.
        det:true — деталь (скрыта до «Детализация статей»). */
  const yslice = years.slice(-5);
  const sl = (a) => (Array.isArray(a) ? a.slice(-5) : []);
  const M = (l, a, o = {}) => ({ l, a, kind: "money", ...o });
  const pnlRows = isBank
    ? [
        // ── Процентный блок ──────────────────────────────────────────────────
        M("Процентные доходы",              ga(bp,"interest_income_gross")||ga(bp,"interest_income")||ga(bp,"total_interest_income"), { det: true }),
        M("Процентные расходы",             ga(bp,"interest_expense_gross")||ga(bp,"interest_expense"), { det: true, muted: true, sign: -1 }),
        M("Чистый процентный доход",        ga(bp,"net_interest_income"), { bold: true }),
        // ── Комиссионный блок ────────────────────────────────────────────────
        M("Комиссионные доходы",            ga(bp,"fee_income_gross")||ga(bp,"fee_income"), { det: true }),
        M("Комиссионные расходы",           ga(bp,"fee_expense"), { det: true, muted: true, sign: -1 }),
        M("Чистый комиссионный доход",      ga(bp,"net_fee_income"), { bold: true }),
        // ── Прочие операционные доходы ───────────────────────────────────────
        M("Торговый доход",                 ga(bp,"trading_income")),
        M("Чистый страховой доход",         ga(bp,"net_insurance_income")),
        bOtherOpArr ? M("Прочие операционные доходы", bOtherOpArr, { muted: true }) : null,
        // ── Операционные доходы (итог до резервов) ───────────────────────────
        M("Операционные доходы (до резервов)", bOpFinalArr, { bold: true }),
        // ── Резервы и итог после резервов ────────────────────────────────────
        M("Резервы под кредитные убытки (CoR)", ga(bp,"provisions")||ga(bp,"impairment_charges"), { muted: true, sign: -1 }),
        bOpAfterProvArr ? M("Операционные доходы после резервов", bOpAfterProvArr, { bold: true }) : null,
        // ── Расходы → прибыль ────────────────────────────────────────────────
        M("Операционные расходы",           ga(bp,"operating_expenses"), { muted: true, sign: -1 }),
        M("Прибыль до налога",              ga(bp,"pre_tax_profit"), { bold: true }),
        M("Налог на прибыль",               ga(bp,"income_tax"), { det: true, muted: true, sign: -1 }),
        M("Чистая прибыль",                 ga(bp,"net_profit"), { bold: true }),
        M("Чистая прибыль (норм.)",         ga(bp,"net_profit_adj")||ga(adjBlk,"net_profit_adj"), { bold: true, accent: true }),
      ].filter(Boolean)
    : [
        M("Выручка", is.revenue, { bold: true }),
        ...(isByFunc
          ? [
              M("Себестоимость", is.cogs, { det: true, muted: true }),
              M("Валовая прибыль", orSum(is.gross_profit, [is.revenue, is.cogs && is.cogs.map((x) => x == null ? null : -x)]), { bold: true }),
              M("Операционные расходы", is.operating_expenses, { det: true, muted: true }),
            ]
          : expLines.map((el) => M(el.name, el.values, { det: true, muted: true }))),
        M("EBITDA", is.ebitda, { bold: true }),
        M("Амортизация", is.da, { det: true, muted: true }),
        M("Операционная прибыль (EBIT)", is.operating_profit, { bold: true }),
        M("Финансовые расходы", is.finance_costs, { det: true, muted: true }),
        M("Финансовые доходы", is.finance_income, { det: true, muted: true }),
        M("Прибыль до налога", is.pre_tax_profit, { det: true, muted: true }),
        M("Налог на прибыль", is.income_tax, { det: true, muted: true }),
        M("Чистая прибыль", is.net_profit, { bold: true }),
        M("Чистая прибыль (норм.)", adjBlk.net_profit_adj, { bold: true, accent: true }),
        ...(isByFunc ? [{ l: "Валовая маржа", a: margins.gross_margin, kind: "pct", det: true, muted: true }] : []),
        { l: "Маржа EBITDA", a: margins.ebitda_margin, kind: "pct", det: true, muted: true },
        { l: "Операционная маржа", a: margins.operating_margin, kind: "pct", det: true, muted: true },
        { l: "Рентабельность (ROS)", a: rosArr, kind: "pct", muted: true },
      ];
  const bsRows = isBank
    ? [
        { l: "АКТИВЫ", sectionHeader: true },
        M("Денежные средства",          ga(bs,"cash_and_equivalents")||ga(bs,"cash")||cua.cash),
        M("Средства в банках (МБК)",    ga(bs,"due_from_banks")),
        M("Портфель ценных бумаг",      ga(bs,"securities")||ga(bs,"investment_securities")),
        M("Кредитный портфель валовой", ga(bs,"gross_loans"), { bold: true }),
        M("Резервы",                    ga(bs,"loan_provisions"), { det: true, muted: true }),
        M("Кредиты юрлицам",            ga(bs,"loans_corporate"), { det: true }),
        M("Кредиты физлицам",           ga(bs,"loans_retail"), { det: true }),
        M("Кредитный портфель чистый",  ga(bs,"net_loans"), { bold: true }),
        M("Основные средства и НМА",    ga(bs,"ppe_intangibles")),
        M("Прочие активы",              ga(bs,"other_assets")),
        M("ИТОГО АКТИВЫ",               ga(bs,"total_assets")||bs.total_assets, { bold: true }),
        { l: "ПАССИВЫ", sectionHeader: true },
        M("Средства банков (МБК)",      ga(bs,"due_to_banks")),
        M("Средства клиентов",          orSum(ga(bs,"customer_deposits"),[ga(bs,"deposits_retail"),ga(bs,"deposits_corporate")]), { bold: true }),
        M("Депозиты физлиц",            ga(bs,"deposits_retail"), { det: true }),
        M("Депозиты юрлиц",             ga(bs,"deposits_corporate"), { det: true }),
        M("Выпущенные облигации",        ga(bs,"debt_securities_issued")),
        M("Субординированный долг",      ga(bs,"subordinated_debt")),
        M("Прочие обязательства",        ga(bs,"other_liabilities")),
        M("ИТОГО ОБЯЗАТЕЛЬСТВА",         ga(bs,"total_liabilities")||bs.total_liabilities, { bold: true }),
        M("Капитал",                     totalEquityArr, { bold: true }),
        M("Уставный капитал",            ga(bs,"share_capital_and_premium")||eqb.share_capital, { det: true, muted: true }),
        M("Нераспределённая прибыль",    ga(bs,"retained_earnings")||eqb.retained_earnings, { det: true, muted: true }),
        { l: "Балансовая ст-ть / акция", a: ga(bs,"book_value_per_share")||bs.book_value_per_share, kind: "rub", muted: true },
      ]
    : [
        M("Внеоборотные активы", orSum(ga(nca, "total_non_current"), [nca.ppe, nca.intangibles, nca.goodwill, nca.long_term_investments, nca.other_non_current]), { bold: true }),
        M("Основные средства", nca.ppe, { det: true, muted: true }),
        M("Нематериальные активы", nca.intangibles, { det: true, muted: true }),
        M("Гудвил", nca.goodwill, { det: true, muted: true }),
        M("Долгосрочные вложения", nca.long_term_investments, { det: true, muted: true }),
        M("Прочие внеоборотные", nca.other_non_current, { det: true, muted: true }),
        M("Оборотные активы", orSum(ga(cua, "total_current"), [cua.inventory, cua.receivables, cua.cash, cua.short_term_investments, cua.other_current]), { bold: true }),
        M("Запасы", cua.inventory, { det: true, muted: true }),
        M("Дебиторская задолженность", cua.receivables, { det: true, muted: true }),
        M("Денежные средства", cua.cash || bs.cash, { det: true, muted: true }),
        M("Краткосрочные вложения", cua.short_term_investments, { det: true, muted: true }),
        M("Прочие оборотные", cua.other_current, { det: true, muted: true }),
        M("ИТОГО АКТИВЫ", bs.total_assets, { bold: true }),
        M("Капитал", totalEquityArr, { bold: true }),
        M("Уставный капитал", eqb.share_capital, { det: true, muted: true }),
        M("Нераспределённая прибыль", eqb.retained_earnings, { det: true, muted: true }),
        M("Добавочный капитал", eqb.additional_paid_in, { det: true, muted: true }),
        M("Прочий капитал", eqb.other_equity, { det: true, muted: true }),
        M("Долгосрочные обязательства", orSum(ga(ncl, "total_non_current_liab"), [ncl.long_term_debt, ncl.deferred_tax, ncl.other_non_current_liab]), { bold: true }),
        M("Долгосрочный долг", ncl.long_term_debt || bs.long_term_debt, { det: true, muted: true }),
        M("Отложенный налог", ncl.deferred_tax, { det: true, muted: true }),
        M("Прочие долгосрочные", ncl.other_non_current_liab, { det: true, muted: true }),
        M("Краткосрочные обязательства", orSum(ga(cul, "total_current_liab"), [cul.short_term_debt, cul.payables, cul.other_current_liab]), { bold: true }),
        M("Краткосрочный долг", cul.short_term_debt || bs.short_term_debt, { det: true, muted: true }),
        M("Кредиторская задолженность", cul.payables, { det: true, muted: true }),
        M("Прочие краткосрочные", cul.other_current_liab, { det: true, muted: true }),
        M("ИТОГО ОБЯЗАТЕЛЬСТВА", bs.total_liabilities, { bold: true }),
        M("Чистый долг", bs.net_debt),
        { l: "ND / EBITDA", a: ndeArr, kind: "x", muted: true },
      ];
  // Детализация статей ОДДС добывается по одной компании за раз (report-fetcher
  // из разных PDF) — качество покрытия сильно разное. Показывать список из
  // 15-20 статей, где заполнено 1-2, хуже, чем не показывать вовсе («простыня
  // пропусков» — жалоба владельца). Порог: статью включаем, только если у неё
  // заполнено ≥40% лет; весь блок статей потока — только если так заполнено
  // большинство статей (иначе оставляем один агрегат CFO/CFI/CFF без разбивки).
  const fillRatio = (vals) => {
    const arr = Array.isArray(vals) ? vals : [];
    if (!arr.length) return 0;
    return arr.filter((v) => v != null).length / arr.length;
  };
  const usableLines = (lines) => {
    if (!lines.length) return [];
    const decent = lines.filter((l) => fillRatio(l.values) >= 0.4);
    return decent.length / lines.length >= 0.5 ? decent : [];
  };
  const cfoLines = usableLines(Array.isArray(cf.cfo_lines) ? cf.cfo_lines : []);
  const cfiLinesRaw = Array.isArray(cf.cfi_lines) ? cf.cfi_lines : [];
  const cfiLines = usableLines(cfiLinesRaw);
  const cffLines = usableLines(Array.isArray(cf.cff_lines) ? cf.cff_lines : []);
  // Капзатраты — отдельное поле cf.capex, независимое от cfi_lines (детализация
  // инвестпотока не всегда явно называет статью «капзатраты» на разбор PDF) —
  // показываем его ВСЕГДА, если есть значения, не только когда cfi_lines пустой.
  const capexAlreadyListed = cfiLines.some((l) => /капзатрат|капвложен|capex/i.test(l.name || ""));
  const cfRows = isBank ? [] : [
    M("Операционный поток (CFO)", cf.cfo, { bold: true }),
    ...cfoLines.map((l) => M(l.name, l.values, { det: true, muted: true })),
    M("Инвестиционный поток (CFI)", cf.cfi, { bold: true }),
    ...(!capexAlreadyListed && fillRatio(cf.capex) > 0 ? [M("Капзатраты", cf.capex, { det: true, muted: true })] : []),
    ...cfiLines.map((l) => M(l.name, l.values, { det: true, muted: true })),
    M("Финансовый поток (CFF)", cf.cff, { bold: true }),
    ...cffLines.map((l) => M(l.name, l.values, { det: true, muted: true })),
    M("Чистое изменение ДС", orSum(cf.net_change_in_cash, [cf.cfo, cf.cfi, cf.cff]), { bold: true }),
    M("Свободный поток (FCF)", cf.fcf, { bold: true, accent: true }),
    { l: "FCF-маржа", a: cf.ratios && cf.ratios.fcf_margin, kind: "pct", muted: true },
  ];
  const npSlice = sl(is.net_profit);
  const ebSlice = sl(is.ebitda);
  const multRows = [
    { l: "P/E",         a: mult.pe,       kind: "ratio",              lossArr: npSlice },
    { l: "P/E (норм.)", a: mult.pe_adj,   kind: "ratio", accent: true, lossArr: npSlice },
    { l: "P/S",         a: mult.ps,       kind: "ratio",              lossArr: npSlice },
    { l: "P/B",         a: mult.pb,       kind: "ratio",              lossArr: npSlice },
    { l: "EV/EBITDA",   a: mult.ev_ebitda, kind: "ratio",              lossArr: ebSlice },
    ...(!isBank ? [
      { l: "ROE", a: ret.roe, kind: "pct", muted: true },
      { l: "ROA", a: ret.roa, kind: "pct", muted: true },
      { l: "ROIC", a: ret.roic, kind: "pct", muted: true },
    ] : []),
    { l: "Маржа EBITDA", a: margins.ebitda_margin, kind: "pct", muted: true },
    { l: "Чистая маржа", a: margins.net_margin, kind: "pct", muted: true },
  ];
  // Банковские метрики — отдельная таблица (владелец: «у Сбера метрики в мультипликаторах — вынести отдельно»)
  const bankMetricRows = isBank ? [
    { l: "ЧПМ (NIM), %",              a: bmA("nim","nim_pct","nim_proxy_pct"),                                      kind: "pct", bold: true },
    { l: "Стоимость риска (CoR), %",  a: bmA("cost_of_risk","cor","cor_pct","cost_of_risk_pct","cor_pct_implied"),  kind: "pct" },
    { l: "Стоимость фондирования, %", a: bmA("funding_rate_pct","cost_of_funding_pct"),                             kind: "pct" },
    { l: "CIR, %",                    a: bmA("cir","cir_pct"),                                                      kind: "pct" },
    { l: "ROE, %",                    a: bmA("roe","roe_pct","roe_rep_pct","roe_reported_pct","roe_reported"),       kind: "pct", bold: true },
    { l: "ROE норм., %",              a: bmA("roe_adjusted","roe_adj","roe_adj_pct"),                               kind: "pct", accent: true },
    { l: "ROA, %",                    a: bmA("roa","roa_pct","roa_adj_pct"),                                        kind: "pct" },
    { l: "Н1.0, %",                   a: bmA("n1_0","capital_adequacy_n10","capital_adequacy","capital_adequacy_h1_0_pct","capital_adequacy_h1"), kind: "pct" },
    { l: "Н1.2, %",                   a: bmA("n1_2","capital_adequacy_n12"),                                        kind: "pct" },
    { l: "Кредитный портфель",        a: bmA("loan_portfolio","loan_portfolio_gross","loan_portfolio_net_mln","loan_portfolio_mln","loans_gross"), kind: "money", bold: true },
    { l: "Депозиты клиентов",         a: bmA("deposits","deposits_mln"),                                            kind: "money" },
    { l: "BVPS, ₽/акц.",             a: bmA("bvps")||ga(bs,"book_value_per_share"),                               kind: "rub", muted: true },
  ].filter((r) => r.a && sl(r.a).some((x) => x != null)) : [];
  const TABLES = { pnl: pnlRows, bs: bsRows, cf: cfRows, mult: multRows };
  const hasTable = (k) => TABLES[k].some((r) => !r.sectionHeader && sl(r.a).some((x) => x != null));
  const tabsAvail = ["pnl", "bs", "cf", "mult"].filter(hasTable);
  const curTab = tabsAvail.includes(tab) ? tab : (tabsAvail[0] || "pnl");
  const TLABEL = { pnl: "P&L", bs: "Баланс", cf: "ОДДС", mult: "Мультипликаторы" };
  const curHasDet = TABLES[curTab].some((r) => !r.sectionHeader && r.det && sl(r.a).some((x) => x != null));
  // форматирование ячейки по kind
  // j — индекс в yslice (для проверки убытка по соответствующему году)
  const fmtCell = (r, v, j) => {
    if (v == null || isNaN(v)) {
      if (r.lossArr && j != null && r.lossArr[j] != null && r.lossArr[j] < 0)
        return <span style={{ color: "var(--ink-3)", fontSize: 11 }} title="убыток — неприменимо">—</span>;
      return <span style={{ color: "var(--ink-3)", fontSize: 11 }}>н.д.</span>;
    }
    if (r.kind === "pct") return num(v, 1) + " %";
    if (r.kind === "ratio") return num(v, 2);
    if (r.kind === "x") return num(v, 2) + "×";
    if (r.kind === "rub") return num(v, 1) + " ₽";
    return B(v).v; // money
  };
  const cellDelta = (r, vals, j) => {
    if (j === 0 || !["money", "pct"].includes(r.kind)) return null;
    const cv = vals[j], pv = vals[j - 1];
    if (cv == null || pv == null) return null;
    if (r.kind === "pct") { const dd = cv - pv; const cls = dd > 0.05 ? "up" : dd < -0.05 ? "dn" : "fl"; return <span className={`yoy ${cls}`}>{dd > 0 ? "▲" : dd < 0 ? "▼" : "▬"} {num(Math.abs(dd), 1)} пп</span>; }
    if (pv === 0) return null;
    const ch = (cv - pv) / Math.abs(pv) * 100; const cls = ch > 0.5 ? "up" : ch < -0.5 ? "dn" : "fl";
    return <span className={`yoy ${cls}`}>{ch > 0 ? "▲" : ch < 0 ? "▼" : "▬"} {num(Math.abs(ch), 1)} %</span>;
  };
  const unitNote = curTab === "mult" ? "×, %" : "млрд ₽";

  /* динамика */
  const fmtT = (v) => num(v / 1000, 2), fmtN = (v) => num(v, 0), fmtP = (v) => num(v, 0);
  const dyn = [];
  if (sl(is.revenue).some((x) => x != null)) dyn.push({ l: "Выручка", data: sl(is.revenue).map((v) => v == null ? null : v * U / 1000), color: "var(--accent)", fmt: fmtT, head: B(lastN(is.revenue)), d: revYoy, cap: "трлн ₽" });
  if (sl(is.net_profit).some((x) => x != null)) dyn.push({ l: "Чистая прибыль", data: sl(is.net_profit).map((v) => v == null ? null : v * U / 1000), color: "var(--amber)", fmt: fmtN, head: B(lastN(is.net_profit)), d: npYoy, cap: "млрд ₽" });
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
              {kfi.map((k, i) => { const b = k.pctv != null ? { v: num(k.pctv, 1), u: "%" } : B(lastN(k.a)); return (<div className="kf" key={i}><span className="kf-l">{k.l}</span><span className="kf-v">{b.v}<s> {b.u}</s></span><span className="kf-d">{k.d != null && <Delta v={k.d} pp={k.isPP} />}</span></div>); })}
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
                  {curHasDet && <button className={`det-toggle${detOpen ? " on" : ""}`} type="button" onClick={() => setDetOpen((o) => !o)}>
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
                        if (r.sectionHeader) return (
                          <tr key={i} className="section-hdr"><td colSpan={yslice.length + 1}>{r.l}</td></tr>
                        );
                        if (r.det && !detOpen) return null;
                        const rawVals = sl(r.a);
                        if (!rawVals.some((x) => x != null)) return null;
                        // sign=-1: вычитаемые строки (расходы/резервы/налог) показываем отрицательно
                        const vals = r.sign === -1 ? rawVals.map((v) => (v == null ? null : -Math.abs(v))) : rawVals;
                        const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                        return (<tr className={cls} key={i}><td style={{ paddingLeft: r.det ? 24 : undefined, color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}</td>{yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j)}</span>{cellDelta(r, vals, j)}</td>)}</tr>);
                      })}
                    </tbody>
                  </table>
                </div>

                {normYears.length > 0 && (<>
                  <div className="subh">Нормализация прибыли · отчётная → скорректированная</div>
                  <table className="fc-norm"><tbody>
                    {normYears.map((nz, i) => (
                      <React.Fragment key={i}>
                        <tr className="yr"><td colSpan="3">{nz.y} · отчётная {B(nz.rep).v} → <span style={{ color: "var(--pos)" }}>норм. {B(nz.adv).v} {B(nz.adv).u}</span></td></tr>
                        <tr><td>{nz.delta >= 0 ? "+ " : "− "}Разовые (обесценение, курсовые), нетто налога</td><td className={`amt ${nz.delta >= 0 ? "pos" : "neg"}`}>{nz.delta >= 0 ? "+" : "−"}{B(Math.abs(nz.delta)).v}</td><td className="lvl"><span className="tg fc-tg-e">оценка</span></td></tr>
                      </React.Fragment>
                    ))}
                  </tbody></table>
                  <div className="fc-note">Корректировки нормализуют разовые статьи (обесценение, курсовые) — операционный результат ровнее отчётной строки. Источник чисел — financials.json (adjusted).</div>
                </>)}
                <div className="foot-note">Числа карточки — из единого источника financials.json ({std}). Для циклических компаний P/E на отдельном годе менее надёжен, чем EV/EBITDA и P/B.</div>
              </div>
            </details>
          )}

          {/* 4b. Банковские метрики по годам */}
          {isBank && bankMetricRows.length > 0 && (
            <details className="disc" open>
              <summary><div><div className="dt">Банковские метрики по годам</div><div className="dd">NIM · CoR · CIR · ROE · достаточность капитала · портфель</div></div><span className="tag tag-fact" style={{ marginLeft: 8 }}>факт</span><span className="chev">▾</span></summary>
              <div className="disc-body">
                <div className="tbl-scroll">
                  <table className="ftbl">
                    <thead><tr><th>Показатель</th>{yslice.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                    <tbody>
                      {bankMetricRows.map((r, i) => {
                        const vals = sl(r.a);
                        const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                        return (
                          <tr className={cls} key={i}>
                            <td style={{ color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}</td>
                            {yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j)}</span>{cellDelta(r, vals, j)}</td>)}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="foot-note">NIM — чистая процентная маржа; CoR — стоимость кредитного риска; стоимость фондирования — процентные расходы к средним процентным обязательствам; CIR — отношение расходов к доходам; Н1.0/Н1.2 — нормативы достаточности капитала (РСБУ). Источник: financials.json (bank_metrics).</div>
              </div>
            </details>
          )}

          {/* 4c. Небанковский бизнес (экосистема) */}
          {isBank && (() => {
            const eco = fin.ecosystem;
            if (!eco) return null;
            const ecoRows = [
              M("Выручка",         ga(eco,"revenue_mln"),    { bold: true }),
              M("Расходы",         ga(eco,"expenses_mln"),   { muted: true }),
              M("Результат нетто", ga(eco,"net_result_mln"), { bold: true, accent: true }),
            ].filter((r) => r.a && sl(r.a).some((x) => x != null));
            if (!ecoRows.length) return null;
            return (
              <details className="disc" open>
                <summary><div><div className="dt">Небанковский бизнес (экосистема)</div><div className="dd">Выручка · расходы · результат нетто по годам</div></div><span className="tag tag-fact" style={{ marginLeft: 8 }}>факт</span><span className="chev">▾</span></summary>
                <div className="disc-body">
                  <div className="tbl-scroll">
                    <table className="ftbl">
                      <thead><tr><th>млрд ₽</th>{yslice.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                      <tbody>
                        {ecoRows.map((r, i) => {
                          const vals = sl(r.a);
                          const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                          return (
                            <tr className={cls} key={i}>
                              <td style={{ color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}</td>
                              {yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j)}</span>{cellDelta(r, vals, j)}</td>)}
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              </details>
            );
          })()}

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
