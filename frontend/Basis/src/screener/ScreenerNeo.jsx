// Basis Screener — Neo-Institutional, на живых данных /api/screener/scored.
// Порт дизайн-прототипа Direction A: пресеты, конструктор с гистограммами, таблица
// (BASIS-пилюля + перцентильные полоски с медианой + логотипы), карта из субиндексов,
// панель деталей. ОДИН движок (бэк) питает балл/полоски/карту — без мок-чисел.
import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import "../styles/screener.css";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";
const NN = " ", NB = " ";
const grp = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NN);
const num = (v, d = 1) => { if (v == null || isNaN(v)) return null; const s = Number(v).toFixed(d).replace(".", ","); const [i, f] = s.split(","); return grp(i) + (f ? "," + f : ""); };
const money = (rub) => { if (rub == null) return null; if (Math.abs(rub) >= 1e12) return num(rub / 1e12, 2) + NB + "трлн" + NB + "₽"; return num(rub / 1e9, rub / 1e9 >= 100 ? 0 : 1) + NB + "млрд" + NB + "₽"; };

// Метрики UI (ключи = ключи бэка). dir: low = меньше выгоднее.
const METRICS = {
  upside:        { label: "Потенциал", unit: "%", dir: "high", dom: [-50, 150], dec: 0, group: "Оценка" },
  pe:            { label: "P / E", unit: "×", dir: "low", dom: [0, 20], dec: 1, group: "Оценка" },
  ev_ebitda:     { label: "EV / EBITDA", unit: "×", dir: "low", dom: [0, 12], dec: 1, group: "Оценка" },
  div_yield:     { label: "Дивдоходность", unit: "%", dir: "high", dom: [0, 18], dec: 1, group: "Оценка" },
  roe:           { label: "ROE", unit: "%", dir: "high", dom: [0, 45], dec: 0, group: "Качество" },
  ebitda_margin: { label: "EBITDA-маржа", unit: "%", dir: "high", dom: [0, 65], dec: 0, group: "Качество" },
  fcf_yield:     { label: "FCF-доходность", unit: "%", dir: "high", dom: [-5, 25], dec: 1, group: "Качество" },
  nd_ebitda:     { label: "Чист. долг / EBITDA", unit: "×", dir: "low", dom: [-5, 4], dec: 1, group: "Устойчивость" },
  beta:          { label: "Бета", unit: "", dir: "low", dom: [0, 2], dec: 2, group: "Устойчивость" },
  volatility:    { label: "Волатильность", unit: "%", dir: "low", dom: [0, 80], dec: 0, group: "Устойчивость" },
  mcap:          { label: "Капитализация", unit: "", dir: "high", dom: [0, 9e12], dec: 0, money: true, group: "Размер" },
};
const GROUPS = ["Оценка", "Качество", "Устойчивость", "Размер"];
const TABLE_METRICS = ["pe", "ev_ebitda", "roe", "ebitda_margin", "nd_ebitda", "div_yield", "fcf_yield", "mcap"];
const PRESETS = [
  { id: "all", name: "Все бумаги", desc: "Без фильтров", ranges: {} },
  { id: "cheapcf", name: "Дешёвый кэшфлоу", desc: "EV/EBITDA ≤ 4 · FCF-дох ≥ 8", ranges: { ev_ebitda: [0, 4], fcf_yield: [8, 25] } },
  { id: "divcov", name: "Дивиденд с покрытием", desc: "Дивдох ≥ 9% · долг ≤ 1,5×", ranges: { div_yield: [9, 18], nd_ebitda: [-5, 1.5] } },
  { id: "qgarp", name: "Качество по цене", desc: "ROE ≥ 20% · P/E ≤ 7", ranges: { roe: [20, 45], pe: [0, 7] } },
  { id: "lowlev", name: "Низкий долг", desc: "Чист. долг/EBITDA ≤ 0,5×", ranges: { nd_ebitda: [-5, 0.5] } },
  { id: "undervalued", name: "С потенциалом", desc: "Потенциал к справедливой ≥ 20%", ranges: { upside: [20, 150] } },
];
const UNIVERSES = [
  { id: "liquid", label: "Ликвидные акции МосБиржи", short: "Ликвидные" },
  { id: "midcap", label: "Расширенный набор (~60)", short: "Расширенный" },
  { id: "all", label: "Все акции (~262)", short: "Все акции" },
];
const CAT = ["--cat-1", "--cat-2", "--cat-3", "--cat-4", "--cat-5", "--cat-6", "--cat-7", "--cat-8"];
const METHOD_TIP = "Композитная оценка Basis v0 — Качество 40% · Цена 35% · Устойчивость 25%, по позиции среди выбранного набора акций. Финансовые метрики; качественные направления (бизнес-модель, управление, рынок, макро, геополитика) — в разработке. Предварительная методика, уточняется.";

const scoreColor = (s) => { if (s == null) return "var(--ink-3)"; const t = Math.max(0, Math.min(1, (s - 45) / (82 - 45))); const hue = t < 0.5 ? (t / 0.5) * 33 : 33 + ((t - 0.5) / 0.5) * 105; return `hsl(${hue.toFixed(0)} 64% 42%)`; };
const fmtMetric = (k, v) => { if (v == null) return "—"; const M = METRICS[k]; return M.money ? money(v) : num(v, M.dec) + (M.unit || ""); };
const histogram = (arr, dom, buckets = 18) => { const [a, b] = dom; const h = new Array(buckets).fill(0); (arr || []).forEach((v) => { let i = Math.floor((v - a) / (b - a) * buckets); i = Math.max(0, Math.min(buckets - 1, i)); h[i]++; }); return h; };
const matchesRanges = (row, ranges) => { for (const k in ranges) { const [lo, hi] = ranges[k]; const v = k === "mcap" ? row.mcap : row.raw[k]; if (v == null) return false; if (v < lo - 1e-9 || v > hi + 1e-9) return false; } return true; };

// ───────────────────────────────────────── sub-components ─────────────────────────────────────────
function ConfDots({ level }) {
  const n = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return <span className="sc-conf" title={"Уверенность: " + (level === "high" ? "высокая" : level === "medium" ? "средняя" : "низкая (мало валидных метрик / искажения)")}>{[0, 1, 2].map((i) => <i key={i} className={i < n ? "on" : ""} />)}</span>;
}
function ScoreBadge({ s, dim }) {
  if (s == null) return <span className="sc-score dim" style={{ background: "var(--ink-3)" }}>—</span>;
  return <span className={"sc-score" + (dim ? " dim" : "")} style={{ background: scoreColor(s) }}>{s}</span>;
}
function PctBar({ pct, big }) {
  if (pct == null) return null;
  const Tag = big ? "div" : "span";
  return <Tag className={big ? "sc-dr-stat-bar" : "sc-cellbar"}><i className={pct >= 80 ? "strong" : ""} style={{ width: Math.max(4, pct) + "%" }} /><span className="med" /></Tag>;
}
function MetricCell({ mkey, v, pct }) {
  if (v == null) return <td className="sc-td sc-num sc-na">—</td>;
  return <td className="sc-td sc-num"><span className="sc-cellval">{fmtMetric(mkey, v)}</span>{mkey !== "mcap" && <PctBar pct={pct} />}</td>;
}

function SortHead({ label, k, sort, setSort, align = "right", title }) {
  const active = sort.key === k;
  return (
    <th className={"sc-th" + (align === "left" ? " sc-th-l" : "") + (active ? " on" : "")} title={title}
      onClick={() => setSort((s) => ({ key: k, dir: s.key === k && s.dir === "desc" ? "asc" : "desc" }))}>
      <span>{label}</span>
      <svg className="sc-sort" width="9" height="11" viewBox="0 0 9 11" aria-hidden="true">
        <path d="M4.5 0l3 4h-6z" className={active && sort.dir === "asc" ? "a" : ""} />
        <path d="M4.5 11l-3-4h6z" className={active && sort.dir === "desc" ? "a" : ""} />
      </svg>
    </th>
  );
}

function ResultsTable({ rows, sort, setSort, density, onPick, picked, secColor, Logo }) {
  return (
    <div className={"sc-tablewrap sc-d-" + density}>
      <table className="sc-table">
        <thead>
          <tr>
            <SortHead label="Компания" k="n" sort={sort} setSort={setSort} align="left" />
            <SortHead label="BASIS" k="basis" sort={sort} setSort={setSort} title="Композитная оценка Basis v0" />
            {TABLE_METRICS.map((k) => <SortHead key={k} label={METRICS[k].label} k={k} sort={sort} setSort={setSort} />)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.t} className={picked && picked.t === r.t ? "on" : ""} onClick={() => onPick(r)}>
              <td className="sc-td sc-id">
                {Logo ? <Logo ticker={r.t} name={r.n} size={34} /> : <span className="sc-mono" style={{ background: secColor(r.sec) + "22", color: secColor(r.sec) }}>{r.t.slice(0, 2)}</span>}
                <span className="sc-idtext"><b>{r.n}</b><span className="sc-idsub">{r.t} · {r.sec}</span></span>
              </td>
              <td className="sc-td sc-num"><span className="sc-scorewrap"><ScoreBadge s={r.basis} dim={r.low_confidence} /><ConfDots level={r.conf} /></span></td>
              {TABLE_METRICS.map((k) => <MetricCell key={k} mkey={k} v={k === "mcap" ? r.mcap : r.raw[k]} pct={r.percentiles[k]} />)}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <div className="sc-noresult">Ни одна бумага не проходит все условия. Ослабьте критерии слева.</div>}
    </div>
  );
}

function AxisSelect({ side, value, onChange, axes }) {
  const [open, setOpen] = useState(false);
  const cur = axes.find((a) => a.key === value) || axes[0];
  const groups = [{ t: "Субиндексы Basis", keys: axes.filter((a) => a.sub).map((a) => a.key) }];
  GROUPS.forEach((g) => groups.push({ t: g, keys: axes.filter((a) => a.group === g).map((a) => a.key) }));
  return (
    <div className="sc-axdd-wrap">
      <span className="sc-axdd-side">Ось {side}</span>
      <button className="sc-axdd" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="sc-axdd-cur">{cur.label}{cur.unit ? <span className="sc-axdd-unit">{cur.unit}</span> : null}</span>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" style={{ transform: open ? "rotate(180deg)" : "none" }}><path d="M4 6l4 4 4-4" /></svg>
      </button>
      {open && (
        <div className="sc-axdd-menu" onMouseLeave={() => setOpen(false)}>
          {groups.map((g) => g.keys.length ? (
            <div key={g.t}><div className="sc-axdd-grp-t">{g.t}</div>
              {g.keys.map((k) => { const d = axes.find((a) => a.key === k); return (
                <button key={k} className={"sc-axdd-item" + (k === value ? " on" : "")} onClick={() => { onChange(k); setOpen(false); }}>
                  <span>{d.label}</span>{d.unit && <span className="sc-axdd-item-u">{d.unit}</span>}
                  {k === value && <svg className="sc-axdd-chk" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8.5l3.5 3.5L13 4.5" /></svg>}
                </button>); })}
            </div>) : null)}
        </div>
      )}
    </div>
  );
}

function MapView({ rows, onPick, picked, secColor, sectors }) {
  const [xKey, setXKey] = useState("value");
  const [yKey, setYKey] = useState("quality");
  const AXES = [
    { key: "value", label: "Оценка (дёшево)", unit: "", dom: [0, 100], sub: true, get: (r) => r.subindices.value },
    { key: "quality", label: "Качество", unit: "", dom: [0, 100], sub: true, get: (r) => r.subindices.quality },
    { key: "stability", label: "Устойчивость", unit: "", dom: [0, 100], sub: true, get: (r) => r.subindices.stability },
    { key: "basis", label: "BASIS-балл", unit: "", dom: [0, 100], sub: true, get: (r) => r.basis },
    ...Object.keys(METRICS).map((k) => ({ key: k, label: METRICS[k].label, unit: METRICS[k].unit, dom: METRICS[k].dom, group: METRICS[k].group, money: METRICS[k].money, dir: METRICS[k].dir, get: (r) => k === "mcap" ? r.mcap : r.raw[k] })),
  ];
  const xa = AXES.find((a) => a.key === xKey), ya = AXES.find((a) => a.key === yKey);
  const W = 760, H = 452, padL = 60, padR = 26, padT = 30, padB = 64;
  const span = (a) => (a.dom[1] - a.dom[0]) || 1;
  const X = (v) => padL + (Math.max(xa.dom[0], Math.min(xa.dom[1], v)) - xa.dom[0]) / span(xa) * (W - padL - padR);
  const Y = (v) => H - padB - (Math.max(ya.dom[0], Math.min(ya.dom[1], v)) - ya.dom[0]) / span(ya) * (H - padT - padB);
  const R = (m) => 7 + Math.sqrt((m || 0) / 1e9) / 4;
  const xMid = (xa.dom[0] + xa.dom[1]) / 2, yMid = (ya.dom[0] + ya.dom[1]) / 2;
  const fmtAx = (a, v) => a.money ? money(v) : num(v, a.sub ? 0 : (METRICS[a.key] ? METRICS[a.key].dec : 0)) + (a.unit || "");
  const valid = rows.filter((r) => xa.get(r) != null && ya.get(r) != null);
  return (
    <div className="sc-map">
      <div className="sc-map-ctrls">
        <AxisSelect side="X" value={xKey} onChange={setXKey} axes={AXES} />
        <button className="sc-axswap" onClick={() => { setXKey(yKey); setYKey(xKey); }} title="Поменять оси" aria-label="Поменять оси"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3L3 5l2 2M3 5h7M11 13l2-2-2-2M13 11H6" /></svg></button>
        <AxisSelect side="Y" value={yKey} onChange={setYKey} axes={AXES} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sc-map-svg" preserveAspectRatio="xMidYMid meet">
        <line x1={X(xMid)} y1={padT} x2={X(xMid)} y2={H - padB} className="sc-map-guide" />
        <line x1={padL} y1={Y(yMid)} x2={W - padR} y2={Y(yMid)} className="sc-map-guide" />
        {[0, 0.5, 1].map((f, i) => { const v = xa.dom[0] + f * span(xa); return <text key={"x" + i} x={X(v)} y={H - padB + 18} className="sc-map-tick" textAnchor="middle">{fmtAx(xa, v)}</text>; })}
        {[0, 0.5, 1].map((f, i) => { const v = ya.dom[0] + f * span(ya); return <text key={"y" + i} x={padL - 9} y={Y(v) + 3} className="sc-map-tick" textAnchor="end">{fmtAx(ya, v)}</text>; })}
        <text x={(padL + W - padR) / 2} y={H - 8} className="sc-map-axis" textAnchor="middle">{xa.label} · {xa.dir === "low" ? "← лучше" : "лучше →"}</text>
        <text x={18} y={(padT + H - padB) / 2} className="sc-map-axis" textAnchor="middle" transform={`rotate(-90 18 ${(padT + H - padB) / 2})`}>{ya.label} · {ya.dir === "low" ? "↓ лучше" : "↑ лучше"}</text>
        {valid.map((r) => { const on = picked && picked.t === r.t; const c = secColor(r.sec); return (
          <g key={r.t} className="sc-bub" onClick={() => onPick(r)} style={{ cursor: "pointer" }}>
            <circle cx={X(xa.get(r))} cy={Y(ya.get(r))} r={R(r.mcap)} fill={c} fillOpacity={on ? 0.85 : 0.5} stroke={c} strokeWidth={on ? 2 : 1} />
            <text x={X(xa.get(r))} y={Y(ya.get(r)) + 3} className="sc-bub-t" textAnchor="middle">{r.t}</text>
          </g>); })}
      </svg>
      <div className="sc-map-legend">
        {sectors.map((s) => <span key={s} className="sc-leg"><i style={{ background: secColor(s) }} />{s}</span>)}
        <span className="sc-leg sc-leg-size"><i className="sz sz1" /><i className="sz sz2" /><i className="sz sz3" />размер = капитализация</span>
        {valid.length < rows.length && <span className="sc-leg sc-leg-na">{rows.length - valid.length} без данных по осям скрыты</span>}
      </div>
    </div>
  );
}

function DetailDrawer({ row, onClose, onOpenCompany, secColor, Logo }) {
  if (!row) return null;
  const subs = [["value", "Оценка"], ["quality", "Качество"], ["stability", "Устойчивость"]];
  const stats = ["pe", "ev_ebitda", "roe", "ebitda_margin", "nd_ebitda", "div_yield", "fcf_yield", "beta", "volatility"];
  return (
    <>
      <div className="sc-scrim" onClick={onClose} />
      <aside className="sc-drawer" role="dialog" aria-label={"Детали " + row.n}>
        <div className="sc-dr-head">
          {Logo ? <Logo ticker={row.t} name={row.n} size={46} /> : <span className="sc-mono lg" style={{ background: secColor(row.sec) + "22", color: secColor(row.sec) }}>{row.t.slice(0, 2)}</span>}
          <div><div className="sc-dr-name">{row.n}</div><div className="sc-dr-sub">{row.t} · {row.sec}</div></div>
          <button className="sc-dr-x" onClick={onClose} aria-label="Закрыть"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg></button>
        </div>
        <div className="sc-dr-price">
          {row.price != null && <span className="sc-dr-px">{num(row.price, 2)} ₽</span>}
          <span className="sc-dr-score"><ScoreBadge s={row.basis} dim={row.low_confidence} /><ConfDots level={row.conf} /></span>
        </div>
        {row.low_confidence && <div className="sc-dr-thesis" style={{ borderLeftColor: "var(--amber)" }}>Низкая уверенность: мало валидных метрик{row.anomaly ? " / искажающие корп-эффекты (учтены)" : ""}. Балл — приблизительный ориентир.</div>}
        <div className="sc-eyebrow" style={{ margin: "4px 0 8px" }}>Субиндексы (перцентиль в наборе)</div>
        <div className="sc-dr-subi">
          {subs.map(([k, l]) => <div key={k} className="sc-dr-subi-c"><div className="sc-dr-subi-l">{l}</div><div className="sc-dr-subi-v" style={{ color: scoreColor(row.subindices[k]) }}>{row.subindices[k] == null ? "—" : Math.round(row.subindices[k])}</div></div>)}
        </div>
        <div className="sc-eyebrow" style={{ margin: "4px 0 8px" }}>Показатели · позиция на рынке</div>
        <div className="sc-dr-stats">
          {stats.map((k) => { const v = row.raw[k], p = row.percentiles[k]; return (
            <div key={k} className="sc-dr-stat">
              <div className="sc-dr-stat-l">{METRICS[k].label}</div>
              <div className="sc-dr-stat-v">{fmtMetric(k, v)}</div>
              {v != null && <PctBar pct={p} big />}
            </div>); })}
        </div>
        <div className="sc-dr-actions">
          <button className="sc-btn-primary" onClick={() => onOpenCompany && onOpenCompany(row.t)}>Открыть карточку компании</button>
        </div>
        <p className="sc-dr-note">Композитная оценка и позиции — аналитический ориентир Basis (v0, предварительная методика), не инвестиционная рекомендация.</p>
      </aside>
    </>
  );
}

// ───────────── rail (histogram range sliders + criteria) ─────────────
function HistogramRangeSlider({ mkey, range, onChange, dist }) {
  const M = METRICS[mkey]; const [a, b] = M.dom; const [lo, hi] = range || M.dom;
  const trackRef = useRef(null);
  const hist = useMemo(() => histogram(dist, M.dom), [dist, mkey]); // eslint-disable-line
  const hmax = Math.max(...hist, 1);
  const pct = (v) => ((v - a) / (b - a)) * 100;
  const snap = (v) => { const step = (b - a) / 100; return Math.round(v / step) * step; };
  const fromX = useCallback((clientX) => { const el = trackRef.current; if (!el) return lo; const r = el.getBoundingClientRect(); let t = (clientX - r.left) / r.width; t = Math.max(0, Math.min(1, t)); return snap(a + t * (b - a)); }, [a, b, lo]); // eslint-disable-line
  const onDown = (which) => (e) => { e.preventDefault(); const move = (ev) => { const cx = ev.touches ? ev.touches[0].clientX : ev.clientX; const v = fromX(cx); onChange(which === "lo" ? [Math.min(v, hi), hi] : [lo, Math.max(v, lo)]); }; const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); }; window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); };
  const bw = (b - a) / hist.length;
  return (
    <div className="sc-hrs">
      <div className="sc-hrs-hist" aria-hidden="true">
        {hist.map((c, i) => { const center = a + (i + 0.5) * bw; const inside = center >= lo && center <= hi; return <span key={i} className={"sc-bar" + (inside ? " on" : "")} style={{ height: (c / hmax * 100) + "%" }} />; })}
      </div>
      <div className="sc-hrs-track" ref={trackRef}>
        <span className="sc-hrs-fill" style={{ left: pct(lo) + "%", right: (100 - pct(hi)) + "%" }} />
        <button className="sc-hrs-thumb" style={{ left: pct(lo) + "%" }} onPointerDown={onDown("lo")} aria-label="Минимум" />
        <button className="sc-hrs-thumb" style={{ left: pct(hi) + "%" }} onPointerDown={onDown("hi")} aria-label="Максимум" />
      </div>
    </div>
  );
}
function fmtBound(mkey, v) { const M = METRICS[mkey]; return M.money ? money(v) : num(v, M.dec) + (M.unit || ""); }
function CriterionRow({ mkey, range, onChange, onRemove, matchCount, dist }) {
  const M = METRICS[mkey]; const [lo, hi] = range;
  const atFloor = lo <= M.dom[0] + 1e-9, atCeil = hi >= M.dom[1] - 1e-9;
  const readout = atFloor && !atCeil ? "≤ " + fmtBound(mkey, hi) : !atFloor && atCeil ? "≥ " + fmtBound(mkey, lo) : fmtBound(mkey, lo) + " – " + fmtBound(mkey, hi);
  return (
    <div className="sc-crit">
      <div className="sc-crit-head"><span className="sc-crit-label">{M.label}</span><span className="sc-crit-count">{matchCount}</span>
        <button className="sc-crit-x" onClick={onRemove} aria-label="Убрать критерий"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg></button>
      </div>
      <div className="sc-crit-readout">{readout}</div>
      <HistogramRangeSlider mkey={mkey} range={range} onChange={onChange} dist={dist} />
    </div>
  );
}
function AddCriterion({ activeKeys, onAdd }) {
  const [open, setOpen] = useState(false);
  const avail = Object.keys(METRICS).filter((k) => !activeKeys.includes(k));
  return (
    <div className="sc-add">
      <button className="sc-add-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M8 3v10M3 8h10" /></svg>Добавить критерий</button>
      {open && <div className="sc-add-menu" onMouseLeave={() => setOpen(false)}>
        {GROUPS.map((g) => { const ks = avail.filter((k) => METRICS[k].group === g); return ks.length ? (
          <div key={g} className="sc-add-grp"><div className="sc-add-grp-t">{g}</div>{ks.map((k) => <button key={k} className="sc-add-item" onClick={() => { onAdd(k); setOpen(false); }}>{METRICS[k].label}</button>)}</div>) : null; })}
      </div>}
    </div>
  );
}
function CriteriaRail({ ranges, sectors, secList, secColor, onRangeChange, onAdd, onRemove, onToggleSector, onReset, resultCount, total, distributions, allRows, onCollapse }) {
  const activeKeys = Object.keys(ranges);
  const countFor = (k) => allRows.filter((r) => matchesRanges(r, { [k]: ranges[k] }) && (!sectors.length || sectors.includes(r.sec))).length;
  return (
    <aside className="sc-rail">
      <div className="sc-rail-head">
        <div><div className="sc-eyebrow">Критерии скрина</div><div className="sc-rail-title">Конструктор фильтра</div></div>
        <div className="sc-rail-head-act"><button className="sc-reset" onClick={onReset}>Сбросить</button>
          <button className="sc-collapse" onClick={onCollapse} title="Свернуть фильтры" aria-label="Свернуть"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 3.5L5 8l4.5 4.5" /><path d="M13 3.5v9" /></svg></button>
        </div>
      </div>
      <div className="sc-funnel">
        <div className="sc-funnel-bar"><span className="sc-funnel-fill" style={{ width: (total ? resultCount / total * 100 : 0) + "%" }} /></div>
        <div className="sc-funnel-txt"><b>{resultCount}</b> из {total} бумаг проходят<span className="sc-funnel-sub">{activeKeys.length + (sectors.length ? 1 : 0)} активных условий</span></div>
      </div>
      <div className="sc-rail-scroll">
        <div className="sc-sectors">{secList.map((s) => <button key={s} className={"sc-sec-chip" + (sectors.includes(s) ? " on" : "")} onClick={() => onToggleSector(s)}><span className="sc-sec-dot" style={{ background: secColor(s) }} />{s}</button>)}</div>
        {activeKeys.length === 0 && sectors.length === 0 && <div className="sc-empty">Фильтров нет — показаны все бумаги. Добавьте критерий или выберите готовый скрин.</div>}
        {GROUPS.map((g) => { const ks = activeKeys.filter((k) => METRICS[k].group === g); return ks.length ? (
          <div key={g} className="sc-crit-grp"><div className="sc-crit-grp-t">{g}</div>
            {ks.map((k) => <CriterionRow key={k} mkey={k} range={ranges[k]} matchCount={countFor(k)} dist={distributions[k]} onChange={(r) => onRangeChange(k, r)} onRemove={() => onRemove(k)} />)}
          </div>) : null; })}
        <AddCriterion activeKeys={activeKeys} onAdd={onAdd} />
      </div>
    </aside>
  );
}

function UniversePicker({ value, onChange, count }) {
  const [open, setOpen] = useState(false);
  const cur = UNIVERSES.find((u) => u.id === value) || UNIVERSES[0];
  return (
    <div className="sc-universe-pick-wrap">
      <button className="sc-universe-pick" onClick={() => setOpen((o) => !o)}>
        <span className="sc-up-label">Набор:</span><b>{cur.short}</b>{count != null && <span className="sc-up-count">{count}</span>}
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" style={{ transform: open ? "rotate(180deg)" : "none" }}><path d="M4 6l4 4 4-4" /></svg>
      </button>
      {open && <div className="sc-up-menu" onMouseLeave={() => setOpen(false)}>
        {UNIVERSES.map((u) => <button key={u.id} className={"sc-up-item" + (u.id === value ? " on" : "")} onClick={() => { onChange(u.id); setOpen(false); }}><span>{u.label}</span></button>)}
      </div>}
    </div>
  );
}

// ───────────────────────────────────────── main ─────────────────────────────────────────
export default function ScreenerNeo({ onOpenCompany, Logo }) {
  const [universe, setUniverse] = useState("liquid");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [ranges, setRanges] = useState({});
  const [sectors, setSectors] = useState([]);
  const [presetId, setPresetId] = useState("all");
  const [sort, setSort] = useState({ key: "basis", dir: "desc" });
  const [density, setDensity] = useState("comfortable");
  const [view, setView] = useState("table");
  const [railOpen, setRailOpen] = useState(true);
  const [picked, setPicked] = useState(null);

  useEffect(() => {
    setLoading(true); setError(false);
    fetch(`${apiBase()}/api/screener/scored?universe=${universe}`)
      .then((r) => r.ok ? r.json() : Promise.reject())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [universe]);

  // нормализация серверных строк
  const rows = useMemo(() => (data?.rows || []).map((r) => ({
    t: r.ticker, n: r.name, sec: r.sector || "—", price: r.price, mcap: r.market_cap,
    basis: r.basis, low_confidence: r.low_confidence, anomaly: r.anomaly, reduced_set: r.reduced_set,
    conf: r.low_confidence ? "low" : (r.data_quality === "medium" ? "medium" : "high"),
    raw: { ...(r.raw || {}), mcap: r.market_cap }, percentiles: r.percentiles || {}, subindices: r.subindices || {},
  })), [data]);
  const distributions = data?.distributions || {};
  const secList = useMemo(() => [...new Set(rows.map((r) => r.sec))].sort(), [rows]);
  const secColorMap = useMemo(() => { const m = {}; secList.forEach((s, i) => { m[s] = `var(${CAT[i % CAT.length]})`; }); return m; }, [secList]);
  const secColor = (s) => secColorMap[s] || "var(--ink-3)";

  const filtered = useMemo(() => {
    let out = rows.filter((r) => matchesRanges(r, ranges) && (!sectors.length || sectors.includes(r.sec)));
    const { key, dir } = sort;
    out = [...out].sort((a, b) => {
      const av = key === "n" ? a.n : key === "basis" ? a.basis : key === "mcap" ? a.mcap : a.raw[key];
      const bv = key === "n" ? b.n : key === "basis" ? b.basis : key === "mcap" ? b.mcap : b.raw[key];
      if (av == null) return 1; if (bv == null) return -1;
      if (typeof av === "string") return dir === "desc" ? bv.localeCompare(av) : av.localeCompare(bv);
      return dir === "desc" ? bv - av : av - bv;
    });
    return out;
  }, [rows, ranges, sectors, sort]);

  const applyPreset = (p) => { setPresetId(p.id); setRanges({ ...p.ranges }); };
  const reset = () => { setRanges({}); setSectors([]); setPresetId("all"); };
  const total = rows.length;

  if (loading) return <div className="sc-screen"><div className="sc-noresult" style={{ padding: "80px" }}>Загружаем скрин…</div></div>;
  if (error) return <div className="sc-screen"><div className="sc-noresult" style={{ padding: "80px", color: "var(--cc-danger)" }}>Не удалось загрузить скрин.</div></div>;

  return (
    <div className="sc-screen">
      <div className="sc-page-head">
        <div>
          <h1 className="sc-page-title">Скринер акций</h1>
          <p className="sc-page-sub">Фильтр и сортировка по метрикам Basis. <span className="sc-modeltag" title={METHOD_TIP}>модель · BASIS v0</span> — инструмент поиска, выводы за вами.</p>
        </div>
        <span className="sc-scale"><span className="sc-scale-bar" style={{ background: `linear-gradient(90deg, ${[0, .25, .5, .75, 1].map((f) => scoreColor(45 + f * 37)).join(",")})` }} /><span className="sc-scale-lbl"><b>BASIS</b> — слабее → сильнее</span></span>
      </div>

      <div className="sc-filter-bar">
        <div className="sc-filter-presets">
          <div className="sc-filter-eyebrow">Готовые скрины</div>
          <div className="sc-presets">
            {PRESETS.map((p) => <button key={p.id} className={"sc-preset" + (presetId === p.id ? " on" : "")} onClick={() => applyPreset(p)}><div className="pn">{p.name}</div><div className="pd">{p.desc}</div></button>)}
          </div>
        </div>
        <div className="sc-filter-universe">
          <div className="sc-filter-eyebrow">Набор акций</div>
          <UniversePicker value={universe} onChange={setUniverse} count={data?.universe?.count} />
        </div>
      </div>

      <div className={"sc-layout" + (railOpen ? "" : " sc-collapsed")}>
        {railOpen && (
          <CriteriaRail ranges={ranges} sectors={sectors} secList={secList} secColor={secColor}
            onRangeChange={(k, r) => { setRanges((rs) => ({ ...rs, [k]: r })); setPresetId(null); }}
            onAdd={(k) => { setRanges((rs) => ({ ...rs, [k]: [...METRICS[k].dom] })); setPresetId(null); }}
            onRemove={(k) => { setRanges((rs) => { const n = { ...rs }; delete n[k]; return n; }); setPresetId(null); }}
            onToggleSector={(s) => setSectors((ss) => ss.includes(s) ? ss.filter((x) => x !== s) : [...ss, s])}
            onReset={reset} resultCount={filtered.length} total={total} distributions={distributions} allRows={rows} onCollapse={() => setRailOpen(false)} />
        )}
        <div className="sc-results">
          <div className="sc-toolbar"><div className="sc-toolbar-top">
            {!railOpen && <button className="sc-filters-btn" onClick={() => setRailOpen(true)}>Фильтры{Object.keys(ranges).length + (sectors.length ? 1 : 0) > 0 && <span className="sc-filters-n">{Object.keys(ranges).length + (sectors.length ? 1 : 0)}</span>}</button>}
            <span className="sc-count"><b>{filtered.length}</b> из {total}</span>
            <div className="sc-tool-r">
              <div className="sc-seg" role="group" aria-label="Плотность"><button className={density === "comfortable" ? "on" : ""} onClick={() => setDensity("comfortable")}>Просторно</button><button className={density === "compact" ? "on" : ""} onClick={() => setDensity("compact")}>Плотно</button></div>
              <div className="sc-seg" role="group" aria-label="Вид">
                <button className={view === "table" ? "on" : ""} onClick={() => setView("table")}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="12" height="10" rx="1.5" /><path d="M2 6.5h12M6 6.5V13" /></svg>Таблица</button>
                <button className={view === "map" ? "on" : ""} onClick={() => setView("map")}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 14V2M2 14h12" strokeLinecap="round" /><circle cx="6" cy="9" r="1.6" /><circle cx="10" cy="5.5" r="1.6" /></svg>Карта</button>
              </div>
            </div>
          </div></div>
          {view === "table"
            ? <ResultsTable rows={filtered} sort={sort} setSort={setSort} density={density} onPick={setPicked} picked={picked} secColor={secColor} Logo={Logo} />
            : <MapView rows={filtered} onPick={setPicked} picked={picked} secColor={secColor} sectors={secList} />}
        </div>
      </div>

      <p className="sc-foot-note">BASIS-балл — композитная оценка Basis v0 (Качество 40% · Цена 35% · Устойчивость 25%) по позиции среди выбранного набора акций. Финансовые метрики; качественные направления в разработке. Тикеры с искажающими корп-эффектами (размытие, «кубышка», разовые списания) помечены пониженной уверенностью и не считаются «лучшими». Предварительная методика — не инвестиционная рекомендация.</p>

      <DetailDrawer row={picked} onClose={() => setPicked(null)} onOpenCompany={onOpenCompany} secColor={secColor} Logo={Logo} />
    </div>
  );
}
