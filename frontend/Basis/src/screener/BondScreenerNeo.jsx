// Basis Bond Screener — Neo-Institutional, на живых данных /api/screener/bonds.
// Порт прототипа Bonds.html (тот же дизайн, что у скринера акций): пресеты, выбор
// типа (ОФЗ/корп/фикс/флоатеры/квазивалютные/с офертой), конструктор с гистограммами,
// таблица и карта. Заголовок бумаги — НЕ выдуманный балл, а вердикт «доходность vs
// риск» (светофор + Risk Score 1–5) из той же методики, что в карточке облигации.
import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import "../styles/screener.css";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";
const NN = " ";
const grp = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NN);
const num = (v, d = 1) => { if (v == null || isNaN(v)) return null; const s = Number(v).toFixed(d).replace(".", ","); const [i, f] = s.split(","); return grp(i) + (f ? "," + f : ""); };

// нац. шкала рейтинга: ранг 20..1 ↔ буква
const RATING_NAMES = { 20: "AAA", 19: "AA+", 18: "AA", 17: "AA-", 16: "A+", 15: "A", 14: "A-", 13: "BBB+", 12: "BBB", 11: "BBB-", 10: "BB+", 9: "BB", 8: "BB-", 7: "B+", 6: "B", 5: "B-", 4: "CCC", 3: "CC", 2: "C", 1: "D" };
const ratingLabel = (rank) => rank == null ? "—" : (RATING_NAMES[Math.round(rank)] || "—");
const ratingColor = (rank) => { if (rank == null) return "var(--ink-3)"; if (rank >= 17) return "var(--pos)"; if (rank >= 14) return "var(--info)"; if (rank >= 11) return "var(--ink-2)"; if (rank >= 8) return "var(--amber)"; return "var(--neg)"; };
// Risk Score 1 (надёжно) → 5 (риск) по границам методики
const riskColor = (r) => r == null ? "var(--ink-3)" : r <= 1.8 ? "var(--pos)" : r <= 2.6 ? "var(--info)" : r <= 3.4 ? "var(--ink-2)" : r <= 4.2 ? "var(--amber)" : "var(--neg)";
// светофор вердикта (orange = промежуток amber→red, тема-safe через color-mix)
const LIGHT_COLOR = { green: "var(--pos)", amber: "var(--amber)", orange: "color-mix(in srgb, var(--amber) 50%, var(--neg))", red: "var(--neg)", gray: "var(--ink-3)" };
const lightRank = (l) => ({ green: 4, amber: 3, orange: 2, red: 1, gray: 0 })[l] ?? 0;
const soft = (c, p) => `color-mix(in srgb, ${c} ${p}%, transparent)`;

const verdictText = (r) => {
  const { vkind: k, light: l } = r;
  if (k === "ofz") return "Госдолг";
  if (k === "defaulted") return "Дефолт";
  if (k === "near_offer") return "Срок искажает YTM";
  if (k === "structured") return "По формуле";
  if (k === "nodata") return "Нет оценки";
  if (k === "floater") return ({ green: "Риск низкий", amber: "Риск средний", orange: "Риск повышен", red: "Риск высокий" })[l] || "Флоатер";
  return ({ green: "Риск оплачен", amber: "Справедливо", orange: "Недоплачен", red: "Не оплачен" })[l] || "—";
};
const verdictTip = (r) => {
  switch (r.vkind) {
    case "ofz": return "ОФЗ — госдолг РФ, кредитного риска практически нет; доходность ≈ безрисковая ставка, основной риск процентный (дюрация).";
    case "defaulted": return "Дефолт / режим Д — возврат тела под вопросом, доходность к погашению нерелевантна.";
    case "near_offer": return "До ближайшей оферты/погашения считаные месяцы — YTM технически раздут коротким хвостом, это не премия за риск.";
    case "structured": return "Структурная нота / выплата по формуле — обычной доходности к погашению у бумаги нет.";
    case "nodata": return "Нет рыночной оценки (неликвид / нет YTM) — соответствие доходности риску по рынку оценить нельзя.";
    case "floater": return `Плавающий купон: процентного риска тела почти нет, риск здесь кредитный. Risk Score ${num(r.risk, 1)} из 5 (≈ ${r.bgroup || "—"}).`;
    default: {
      const base = ({ green: "Риск оплачен", amber: "Оценено справедливо", orange: "Доходность недоплачивает за риск", red: "Риск существенно недоплачен" })[r.light] || "";
      if (r.spr == null || r.required == null) return base;
      return `${base}. Спред ${r.spr} б.п. против требуемых ~${r.required} б.п. за этот риск (премия ${r.premium > 0 ? "+" : ""}${r.premium} б.п.).`;
    }
  }
};
const couponLine = (r) => {
  if (r.ct === "floater") return r.flspr != null ? `КС + ${num(r.flspr / 100, 2)}%` : "плавающий (КС/RUONIA)";
  if (r.ct === "fixed") return r.cpn != null ? `${num(r.cpn, 1)}% годовых` : null;
  if (r.ct === "linker") return "индексация на инфляцию";
  if (r.ct === "structured") return "выплата по формуле";
  return r.cpn != null ? `${num(r.cpn, 1)}%` : null;
};

// Метрики конструктора/таблицы (ключи = ключи строки бэка).
const METRICS = {
  ytm: { label: "Доходность", short: "YTM", unit: "%", dir: "high", dom: [0, 40], dec: 1, group: "Доходность" },
  spr: { label: "Спред к ОФЗ", short: "Спред", unit: " б.п.", dir: "high", dom: [0, 2000], dec: 0, group: "Доходность" },
  cpn: { label: "Купон", short: "Купон", unit: "%", dir: "high", dom: [0, 28], dec: 1, group: "Доходность" },
  rat: { label: "Кред. рейтинг", short: "Рейтинг", unit: "", dir: "high", dom: [1, 20], dec: 0, group: "Кредитный риск", rating: true },
  risk: { label: "Risk Score", short: "Risk", unit: "", dir: "low", dom: [1, 5], dec: 1, group: "Кредитный риск" },
  mat: { label: "До погашения", short: "Срок", unit: " г.", dir: "low", dom: [0, 15], dec: 1, group: "Срок" },
  dur: { label: "Дюрация", short: "Дюрация", unit: " г.", dir: "low", dom: [0, 10], dec: 1, group: "Срок" },
  px: { label: "Цена", short: "Цена", unit: "%", dir: "low", dom: [40, 110], dec: 1, group: "Цена / объём" },
};
const GROUPS = ["Доходность", "Кредитный риск", "Срок", "Цена / объём"];
const TABLE_METRICS = ["ytm", "spr", "cpn", "mat", "rat", "dur", "px"];
const fmtMetric = (k, v) => { if (v == null) return "—"; const M = METRICS[k]; return M.rating ? ratingLabel(v) : num(v, M.dec) + (M.unit || ""); };

const PRESETS = [
  { id: "all", name: "Все бумаги", desc: "Без фильтров", ranges: {}, type: "all" },
  { id: "paidrisk", name: "Риск оплачен", desc: "Доходность оправдывает риск · методика Basis", ranges: {}, type: "all", light: ["green"] },
  { id: "safeinc", name: "Надёжный доход", desc: "Оценка риска Basis ≤ 1,8 из 5", ranges: { risk: [1, 1.8] }, type: "all" },
  { id: "short", name: "Короткие ≤ 2 лет", desc: "До погашения ≤ 2 лет", ranges: { mat: [0, 2] }, type: "all" },
  { id: "premium", name: "Премия в корпоратах", desc: "Спред ≥ 300 б.п. · рейтинг ≥ BBB−", ranges: { spr: [300, 2000], rat: [11, 20], risk: [1, 3.4] }, type: "corp" },
  { id: "float", name: "Флоатеры", desc: "Купон следует за ключевой ставкой", ranges: {}, type: "float" },
  { id: "quasi", name: "Валютные (замещающие)", desc: "Номинал в валюте — защита от девальвации", ranges: {}, type: "quasi" },
  { id: "hy", name: "ВДО — высокий риск", desc: "Спред ≥ 600 б.п. · риск повышен", ranges: { spr: [600, 2000], risk: [3.4, 5] }, type: "all" },
];
const TYPES = [
  { id: "all", label: "Все облигации", pred: () => true },
  { id: "ofz", label: "ОФЗ", pred: (r) => r.bt === "ofz" },
  { id: "corp", label: "Корпоративные", pred: (r) => r.bt !== "ofz" },
  { id: "fix", label: "Фикс. купон", pred: (r) => r.ct === "fixed" },
  { id: "float", label: "Флоатеры", pred: (r) => r.ct === "floater" },
  { id: "quasi", label: "Квазивалютные", pred: (r) => r.quasi },
  { id: "offer", label: "С офертой", pred: (r) => r.has_offer },
];
const typePred = (id) => (TYPES.find((t) => t.id === id) || TYPES[0]).pred;
const CAT = ["--cat-1", "--cat-2", "--cat-3", "--cat-4", "--cat-5", "--cat-6", "--cat-7", "--cat-8"];
// Сколько строк/точек рисуем за раз: вся БД (~3177 бумаг) в DOM = десятки тысяч узлов
// и многосекундный рендер. Фильтрация идёт по ВСЕЙ выборке, в DOM — только верхушка
// по текущей сортировке; ниже подсказка сузить фильтр.
const RENDER_CAP = 300;
const METHOD_TIP = "Вердикт «доходность vs риск» по методике Basis (docs/bond_analys.md): фактический спред к ОФЗ → требуемый спред за кредитный риск (медиана группы + Risk Score 1–5) → светофор + проверка ожидаемыми потерями и стоп-правила. Это аналитический ориентир, не сигнал к покупке/продаже.";

const histogram = (arr, dom, buckets = 18) => { const [a, b] = dom; const h = new Array(buckets).fill(0); (arr || []).forEach((v) => { let i = Math.floor((v - a) / (b - a) * buckets); i = Math.max(0, Math.min(buckets - 1, i)); h[i]++; }); return h; };
const matchesRanges = (row, ranges) => { for (const k in ranges) { const [lo, hi] = ranges[k]; const v = row[k]; if (v == null) return false; if (v < lo - 1e-9 || v > hi + 1e-9) return false; } return true; };

// ───────────────────────────── sub-components ─────────────────────────────
function ConfDots({ level }) {
  const n = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return <span className="sc-conf" title={"Уверенность данных: " + (level === "high" ? "высокая" : level === "medium" ? "средняя" : "низкая")}>{[0, 1, 2].map((i) => <i key={i} className={i < n ? "on" : ""} />)}</span>;
}
function VerdictPill({ r }) {
  const c = LIGHT_COLOR[r.light] || "var(--ink-3)";
  return <span className="bd-verdict" title={verdictTip(r)} style={{ color: c, borderColor: soft(c, 42), background: soft(c, 12) }}><i />{verdictText(r)}</span>;
}
function RiskPill({ r, compact }) {
  if (r == null) return null;
  const c = riskColor(r);
  return <span className="bd-risk" title={"Кредитный риск Basis: " + num(r, 1) + " из 5"} style={{ borderColor: soft(c, 55), color: c }}><b>{num(r, 1)}</b>{!compact && <span className="bd-risk-x">/5</span>}</span>;
}
function PctBar({ pct }) { if (pct == null) return null; return <span className="sc-cellbar"><i className={pct >= 80 ? "strong" : ""} style={{ width: Math.max(4, pct) + "%" }} /></span>; }

function RatingCell({ v }) {
  if (v == null) return <td className="sc-td sc-num sc-na">—</td>;
  const c = ratingColor(v), pos = Math.max(0, Math.min(1, (v - 1) / 19));
  return <td className="sc-td sc-num"><span className="bd-rating" style={{ color: c, borderColor: soft(c, 40), background: soft(c, 12) }}>{ratingLabel(v)}</span><span className="sc-cellbar"><i style={{ width: Math.max(6, pos * 100) + "%", background: c, opacity: 1 }} /></span></td>;
}
function MetricCell({ mkey, v, pct }) {
  if (mkey === "rat") return <RatingCell v={v} />;
  if (v == null) return <td className="sc-td sc-num sc-na">—</td>;
  return <td className="sc-td sc-num"><span className="sc-cellval">{fmtMetric(mkey, v)}</span>{mkey !== "px" && <PctBar pct={pct} />}</td>;
}
function SortHead({ label, k, sort, setSort, align = "right", title }) {
  const active = sort.key === k;
  return (
    <th className={"sc-th" + (align === "left" ? " sc-th-l" : "") + (active ? " on" : "")} title={title}
      onClick={() => setSort((s) => ({ key: k, dir: s.key === k && s.dir === "desc" ? "asc" : "desc" }))}>
      <span>{label}</span>
      <svg className="sc-sort" width="9" height="11" viewBox="0 0 9 11" aria-hidden="true"><path d="M4.5 0l3 4h-6z" className={active && sort.dir === "asc" ? "a" : ""} /><path d="M4.5 11l-3-4h6z" className={active && sort.dir === "desc" ? "a" : ""} /></svg>
    </th>
  );
}

function ResultsTable({ rows, sort, setSort, density, onPick, picked, secColor, pctOf }) {
  return (
    <div className={"sc-tablewrap sc-d-" + density}>
      <table className="sc-table">
        <thead><tr>
          <SortHead label="Выпуск" k="n" sort={sort} setSort={setSort} align="left" />
          <SortHead label="Вердикт" k="verdict" sort={sort} setSort={setSort} title="Доходность vs риск — оплачен ли риск (методика Basis)" />
          {TABLE_METRICS.map((k) => <SortHead key={k} label={METRICS[k].short} k={k} sort={sort} setSort={setSort} title={METRICS[k].label} />)}
          <th className="sc-th sc-th-r2">Оферта / тип</th>
        </tr></thead>
        <tbody>
          {rows.slice(0, RENDER_CAP).map((r) => (
            <tr key={r.id} className={picked && picked.id === r.id ? "on" : ""} onClick={() => onPick(r)}>
              <td className="sc-td sc-id">
                <span className="sc-mono" style={{ background: soft(secColor(r.sec), 18), color: secColor(r.sec) }}>{r.ab}</span>
                <span className="sc-idtext"><b>{r.n}</b><span className="sc-idsub">{r.id} · {r.sec}</span></span>
              </td>
              <td className="sc-td"><span className="bd-scorewrap"><VerdictPill r={r} /><RiskPill r={r.risk} compact /></span></td>
              {TABLE_METRICS.map((k) => <MetricCell key={k} mkey={k} v={r[k]} pct={pctOf(k, r[k])} />)}
              <td className="sc-td sc-num">
                {r.offer ? <span className="bd-offer">{fmtDate(r.offer)}</span>
                  : r.quasi ? <span className="bd-tag-quasi">{r.cur === "CNY" ? "юаневая" : "валютная"}</span>
                    : r.ct === "floater" ? <span className="bd-tag-flt">флоатер</span>
                      : <span className="sc-na">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <div className="sc-noresult">Ни одна бумага не проходит все условия. Ослабьте критерии слева.</div>}
      {rows.length > RENDER_CAP && <div className="sc-noresult" style={{ padding: "12px 16px", textAlign: "left" }}>Показаны первые {RENDER_CAP} из {rows.length} по текущей сортировке. Сузьте фильтр слева, чтобы увидеть остальные.</div>}
    </div>
  );
}
const fmtDate = (iso) => iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : "—";

function AxisSelect({ side, value, onChange }) {
  const [open, setOpen] = useState(false);
  const cur = METRICS[value];
  return (
    <div className="sc-axdd-wrap">
      <span className="sc-axdd-side">Ось {side}</span>
      <button className="sc-axdd" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="sc-axdd-cur">{cur.label}{cur.unit ? <span className="sc-axdd-unit">{cur.unit.trim()}</span> : null}</span>
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" style={{ transform: open ? "rotate(180deg)" : "none" }}><path d="M4 6l4 4 4-4" /></svg>
      </button>
      {open && (
        <div className="sc-axdd-menu" onMouseLeave={() => setOpen(false)}>
          {GROUPS.map((g) => { const ks = Object.keys(METRICS).filter((k) => METRICS[k].group === g); return (
            <div key={g} className="sc-axdd-grp"><div className="sc-axdd-grp-t">{g}</div>
              {ks.map((k) => (
                <button key={k} className={"sc-axdd-item" + (k === value ? " on" : "")} onClick={() => { onChange(k); setOpen(false); }}>
                  <span>{METRICS[k].label}</span>{METRICS[k].unit && <span className="sc-axdd-item-u">{METRICS[k].unit.trim()}</span>}
                  {k === value && <svg className="sc-axdd-chk" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8.5l3.5 3.5L13 4.5" /></svg>}
                </button>
              ))}
            </div>); })}
        </div>
      )}
    </div>
  );
}

function MapView({ rows, onPick, picked, secColor, sectors }) {
  const [xKey, setXKey] = useState("dur");
  const [yKey, setYKey] = useState("ytm");
  const xa = METRICS[xKey], ya = METRICS[yKey];
  const W = 760, H = 452, padL = 64, padR = 26, padT = 30, padB = 64;
  const span = (a) => (a.dom[1] - a.dom[0]) || 1;
  const X = (v) => padL + (Math.max(xa.dom[0], Math.min(xa.dom[1], v)) - xa.dom[0]) / span(xa) * (W - padL - padR);
  const Y = (v) => H - padB - (Math.max(ya.dom[0], Math.min(ya.dom[1], v)) - ya.dom[0]) / span(ya) * (H - padT - padB);
  const xMid = (xa.dom[0] + xa.dom[1]) / 2, yMid = (ya.dom[0] + ya.dom[1]) / 2;
  const fmtAx = (a, v) => a.rating ? ratingLabel(v) : num(v, a.dec) + (a.unit ? a.unit.trim() : "");
  const valid = rows.filter((r) => r[xKey] != null && r[yKey] != null).slice(0, RENDER_CAP);
  return (
    <div className="sc-map">
      <div className="sc-map-ctrls">
        <AxisSelect side="X" value={xKey} onChange={setXKey} />
        <button className="sc-axswap" onClick={() => { setXKey(yKey); setYKey(xKey); }} title="Поменять оси" aria-label="Поменять оси"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 3L3 5l2 2M3 5h7M11 13l2-2-2-2M13 11H6" /></svg></button>
        <AxisSelect side="Y" value={yKey} onChange={setYKey} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="sc-map-svg" preserveAspectRatio="xMidYMid meet">
        <line x1={X(xMid)} y1={padT} x2={X(xMid)} y2={H - padB} className="sc-map-guide" />
        <line x1={padL} y1={Y(yMid)} x2={W - padR} y2={Y(yMid)} className="sc-map-guide" />
        {[0, 0.5, 1].map((f, i) => { const v = xa.dom[0] + f * span(xa); return <text key={"x" + i} x={X(v)} y={H - padB + 18} className="sc-map-tick" textAnchor="middle">{fmtAx(xa, v)}</text>; })}
        {[0, 0.5, 1].map((f, i) => { const v = ya.dom[0] + f * span(ya); return <text key={"y" + i} x={padL - 9} y={Y(v) + 3} className="sc-map-tick" textAnchor="end">{fmtAx(ya, v)}</text>; })}
        <text x={(padL + W - padR) / 2} y={H - 8} className="sc-map-axis" textAnchor="middle">{xa.label} · {xa.dir === "low" ? "← лучше" : "лучше →"}</text>
        <text x={18} y={(padT + H - padB) / 2} className="sc-map-axis" textAnchor="middle" transform={`rotate(-90 18 ${(padT + H - padB) / 2})`}>{ya.label} · {ya.dir === "low" ? "↓ лучше" : "↑ лучше"}</text>
        {valid.map((r) => { const on = picked && picked.id === r.id; const c = secColor(r.sec); return (
          <g key={r.id} className="sc-bub" onClick={() => onPick(r)} style={{ cursor: "pointer" }}>
            <circle cx={X(r[xKey])} cy={Y(r[yKey])} r={on ? 9 : 7} fill={c} fillOpacity={on ? 0.85 : 0.5} stroke={c} strokeWidth={on ? 2 : 1} />
          </g>); })}
      </svg>
      <div className="sc-map-legend">
        {sectors.map((s) => <span key={s} className="sc-leg"><i style={{ background: secColor(s) }} />{s}</span>)}
        {valid.length < rows.length && <span className="sc-leg sc-leg-na">{rows.length - valid.length} скрыто (нет данных по осям / сверх лимита показа)</span>}
      </div>
    </div>
  );
}

function DetailDrawer({ row, onClose, onOpenCompany, secColor }) {
  if (!row) return null;
  const r = row;
  const stats = ["ytm", "spr", "cpn", "mat", "dur", "px"];
  return (
    <>
      <div className="sc-scrim" onClick={onClose} />
      <aside className="sc-drawer" role="dialog" aria-label={"Детали " + r.n}>
        <div className="sc-dr-head">
          <span className="sc-mono lg" style={{ background: soft(secColor(r.sec), 18), color: secColor(r.sec) }}>{r.ab}</span>
          <div><div className="sc-dr-name">{r.n}</div><div className="sc-dr-sub">{r.id} · {r.sec}</div></div>
          <button className="sc-dr-x" onClick={onClose} aria-label="Закрыть"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg></button>
        </div>
        <div className="sc-dr-price">
          {r.ytm != null ? <span className="sc-dr-px">{num(r.ytm, 1)}%<span className="bd-px-u"> YTM</span></span> : <span className="sc-dr-px bd-px-u">без YTM</span>}
          {r.px != null && <span className="bd-px-2">цена {num(r.px, 1)}%</span>}
          <span className="sc-dr-score"><VerdictPill r={r} /></span>
        </div>
        <div className="bd-dr-badges">
          {r.rating && <span className="bd-rating lg" style={{ color: ratingColor(r.rat), borderColor: soft(ratingColor(r.rat), 42), background: soft(ratingColor(r.rat), 12) }}>{r.rating}</span>}
          <RiskPill r={r.risk} />
          {couponLine(r) && <span className="bd-tag-flt" style={{ color: "var(--ink-2)", background: soft("var(--ink)", 7) }}>{couponLine(r)}</span>}
          {r.quasi && <span className="bd-tag-quasi">{r.cur}</span>}
          <span className="bd-dr-conf">Данные <ConfDots level={r.conf} /></span>
        </div>
        <div className="bd-dr-verdict">{verdictTip(r)}</div>
        <div className="sc-eyebrow" style={{ margin: "4px 0 8px" }}>Параметры · позиция на рынке</div>
        <div className="sc-dr-stats">
          {stats.map((k) => { const v = r[k]; return (
            <div key={k} className="sc-dr-stat"><div className="sc-dr-stat-l">{METRICS[k].label}</div><div className="sc-dr-stat-v">{fmtMetric(k, v)}</div></div>); })}
        </div>
        <div className="sc-dr-actions">
          {r.tk
            ? <button className="sc-btn-primary" onClick={() => onOpenCompany && onOpenCompany(r.tk)}>Открыть карточку эмитента · {r.tk}</button>
            : <div className="sc-dr-note" style={{ margin: 0 }}>Непубличный эмитент — отдельной карточки компании нет. Полный разбор бумаги — в разделе «Рынок → Облигации».</div>}
        </div>
        <p className="sc-dr-note">Вердикт «доходность к риску», спред и Risk Score — аналитический ориентир Basis (методика docs/bond_analys.md), не инвестиционная рекомендация.</p>
      </aside>
    </>
  );
}

// ───────────── rail ─────────────
function HistogramRangeSlider({ mkey, range, onChange, dist }) {
  const M = METRICS[mkey]; const [a, b] = M.dom; const [lo, hi] = range || M.dom;
  const trackRef = useRef(null);
  const hist = useMemo(() => histogram(dist, M.dom), [dist, mkey]); // eslint-disable-line
  const hmax = Math.max(...hist, 1);
  const pct = (v) => ((v - a) / (b - a)) * 100;
  const snap = (v) => { const step = (b - a) / 100; return Math.round(v / step) * step; };
  const fromX = useCallback((clientX) => { const el = trackRef.current; if (!el) return lo; const rc = el.getBoundingClientRect(); let t = (clientX - rc.left) / rc.width; t = Math.max(0, Math.min(1, t)); return snap(a + t * (b - a)); }, [a, b, lo]); // eslint-disable-line
  const onDown = (which) => (e) => { e.preventDefault(); const move = (ev) => { const cx = ev.touches ? ev.touches[0].clientX : ev.clientX; const v = fromX(cx); onChange(which === "lo" ? [Math.min(v, hi), hi] : [lo, Math.max(v, lo)]); }; const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); }; window.addEventListener("pointermove", move); window.addEventListener("pointerup", up); };
  const bw = (b - a) / hist.length;
  return (
    <div className="sc-hrs">
      <div className="sc-hrs-hist" aria-hidden="true">{hist.map((c, i) => { const center = a + (i + 0.5) * bw; const inside = center >= lo && center <= hi; return <span key={i} className={"sc-bar" + (inside ? " on" : "")} style={{ height: (c / hmax * 100) + "%" }} />; })}</div>
      <div className="sc-hrs-track" ref={trackRef}>
        <span className="sc-hrs-fill" style={{ left: pct(lo) + "%", right: (100 - pct(hi)) + "%" }} />
        <button className="sc-hrs-thumb" style={{ left: pct(lo) + "%" }} onPointerDown={onDown("lo")} aria-label="Минимум" />
        <button className="sc-hrs-thumb" style={{ left: pct(hi) + "%" }} onPointerDown={onDown("hi")} aria-label="Максимум" />
      </div>
    </div>
  );
}
const fmtBound = (mkey, v) => { const M = METRICS[mkey]; return M.rating ? ratingLabel(v) : num(v, M.dec) + (M.unit || ""); };
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
function CriteriaRail({ ranges, sector, typeId, lightFilter, onRangeChange, onAdd, onRemove, onReset, resultCount, total, distributions, allRows, onCollapse }) {
  const activeKeys = Object.keys(ranges);
  const countFor = (k) => allRows.filter((r) => matchesRanges(r, { [k]: ranges[k] }) && (!sector || r.sec === sector) && typePred(typeId)(r)).length;
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
        <div className="sc-funnel-txt"><b>{resultCount}</b> из {total} бумаг проходят<span className="sc-funnel-sub">{activeKeys.length + (sector ? 1 : 0) + (typeId !== "all" ? 1 : 0) + (lightFilter ? 1 : 0)} активных условий</span></div>
      </div>
      <div className="sc-rail-scroll">
        {activeKeys.length === 0 && !sector && <div className="sc-empty">Фильтров нет — показаны все бумаги. Добавьте критерий или выберите готовый скрин.</div>}
        {GROUPS.map((g) => { const ks = activeKeys.filter((k) => METRICS[k].group === g); return ks.length ? (
          <div key={g} className="sc-crit-grp"><div className="sc-crit-grp-t">{g}</div>
            {ks.map((k) => <CriterionRow key={k} mkey={k} range={ranges[k]} matchCount={countFor(k)} dist={distributions[k]} onChange={(rr) => onRangeChange(k, rr)} onRemove={() => onRemove(k)} />)}
          </div>) : null; })}
        <AddCriterion activeKeys={activeKeys} onAdd={onAdd} />
      </div>
    </aside>
  );
}

function PickDropdown({ label, value, valueLabel, dot, options, onChange }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sc-universe-pick-wrap">
      <button className="sc-universe-pick" onClick={() => setOpen((o) => !o)}>
        <span className="sc-up-label">{label}:</span>{dot && <span className="sc-sec-dot" style={{ background: dot }} />}<b>{valueLabel}</b>
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" style={{ transform: open ? "rotate(180deg)" : "none" }}><path d="M4 6l4 4 4-4" /></svg>
      </button>
      {open && <div className="sc-up-menu" onMouseLeave={() => setOpen(false)}>
        {options.map((o) => <button key={o.id} className={"sc-up-item" + (o.id === value ? " on" : "")} onClick={() => { onChange(o.id); setOpen(false); }}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>{o.dot && <span className="sc-sec-dot" style={{ background: o.dot }} />}{o.label}</span>
          {o.count != null && <span className="sc-up-item-c">{o.count}</span>}
        </button>)}
      </div>}
    </div>
  );
}

// ───────────────────────────── main ─────────────────────────────
export default function BondScreenerNeo({ onOpenCompany }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [ranges, setRanges] = useState({});
  const [sector, setSector] = useState("");
  const [typeId, setTypeId] = useState("all");
  const [lightFilter, setLightFilter] = useState(null);
  const [presetId, setPresetId] = useState("all");
  const [sort, setSort] = useState({ key: "verdict", dir: "desc" });
  const [density, setDensity] = useState("comfortable");
  const [view, setView] = useState("table");
  const [railOpen, setRailOpen] = useState(true);
  const [picked, setPicked] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setLoading(true); setError(false);
    const url = `${apiBase()}/api/screener/bonds`;
    fetch(url)
      .then(async (r) => { if (!r.ok) { const t = await r.text().catch(() => ""); throw new Error(`HTTP ${r.status} ${t.slice(0, 200)}`); } return r.json(); })
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { console.error("Bond screener load failed:", url, e); setError(String(e && e.message || e)); setLoading(false); });
  }, [reloadKey]);

  const rows = useMemo(() => (data?.rows || []).map((r) => ({
    ...r,
    ab: (r.issuer || r.n || r.id || "··").replace(/^[^А-Яа-яA-Za-z0-9]+/, "").slice(0, 2).toUpperCase(),
    conf: r.rating && r.ytm != null ? "high" : (r.rating || r.ytm != null ? "medium" : "low"),
  })), [data]);
  const distributions = data?.distributions || {};
  const secList = useMemo(() => [...new Set(rows.map((r) => r.sec))].sort((a, b) => a.localeCompare(b, "ru")), [rows]);
  const secColorMap = useMemo(() => { const m = {}; secList.forEach((s, i) => { m[s] = `var(${CAT[i % CAT.length]})`; }); return m; }, [secList]);
  const secColor = (s) => secColorMap[s] || "var(--ink-3)";

  // перцентиль значения метрики среди ВСЕХ строк (для полосок в таблице)
  const pctOf = useMemo(() => {
    const sorted = {};
    Object.keys(METRICS).forEach((k) => { sorted[k] = rows.map((r) => r[k]).filter((v) => v != null).sort((a, b) => a - b); });
    return (k, v) => {
      if (v == null) return null; const arr = sorted[k]; if (!arr || arr.length < 2) return null;
      let lo = 0, hi = arr.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < v) lo = mid + 1; else hi = mid; }
      let p = lo / (arr.length - 1); return Math.round((METRICS[k].dir === "low" ? 1 - p : p) * 100);
    };
  }, [rows]);

  const filtered = useMemo(() => {
    const pred = typePred(typeId);
    let out = rows.filter((r) => matchesRanges(r, ranges) && (!sector || r.sec === sector) && pred(r) && (!lightFilter || lightFilter.includes(r.light)));
    const { key, dir } = sort;
    out = [...out].sort((a, b) => {
      if (key === "n") return dir === "desc" ? (b.n || "").localeCompare(a.n || "", "ru") : (a.n || "").localeCompare(b.n || "", "ru");
      if (key === "verdict") { const d = lightRank(b.light) - lightRank(a.light); if (d) return dir === "desc" ? d : -d; const pa = a.premium == null ? -1e9 : a.premium, pb = b.premium == null ? -1e9 : b.premium; return dir === "desc" ? pb - pa : pa - pb; }
      const av = a[key], bv = b[key];
      if (av == null) return 1; if (bv == null) return -1;
      return dir === "desc" ? bv - av : av - bv;
    });
    return out;
  }, [rows, ranges, sector, typeId, lightFilter, sort]);

  const applyPreset = (p) => { setPresetId(p.id); setRanges({ ...p.ranges }); setSector(""); setTypeId(p.type || "all"); setLightFilter(p.light || null); };
  const reset = () => { setRanges({}); setSector(""); setTypeId("all"); setLightFilter(null); setPresetId("all"); };
  const total = rows.length;
  const activeN = Object.keys(ranges).length + (sector ? 1 : 0) + (typeId !== "all" ? 1 : 0) + (lightFilter ? 1 : 0);

  const typeOptions = TYPES.map((t) => ({ id: t.id, label: t.label, count: rows.filter(t.pred).length }));
  const sectorOptions = [{ id: "", label: "Все секторы" }, ...secList.map((s) => ({ id: s, label: s, dot: secColor(s) }))];

  if (loading) return <div className="sc-screen"><div className="sc-noresult" style={{ padding: "80px" }}>Загружаем скрин облигаций…</div></div>;
  if (error) return (
    <div className="sc-screen"><div className="sc-noresult" style={{ padding: "64px 24px" }}>
      <div style={{ color: "var(--neg)", fontWeight: 600, marginBottom: 8 }}>Не удалось загрузить скринер облигаций.</div>
      <div className="sc-num" style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 16, wordBreak: "break-word" }}>{String(error)}</div>
      <button className="sc-btn-primary" style={{ display: "inline-block", width: "auto", padding: "10px 22px" }} onClick={() => setReloadKey((k) => k + 1)}>Повторить</button>
    </div></div>
  );

  return (
    <div className="sc-screen">
      <div className="sc-page-head">
        <div>
          <p className="sc-page-sub">Отбор по доходности, риску и сроку. <span className="sc-modeltag" title={METHOD_TIP}>методика · доходность vs риск</span> — показывает, насколько доходность компенсирует кредитный риск, а не просто «где больше процент».</p>
        </div>
        <span className="sc-scale" title="Светофор вердикта: оплачен ли риск доходностью">
          <span className="sc-scale-bar" style={{ background: `linear-gradient(90deg, ${LIGHT_COLOR.red}, ${LIGHT_COLOR.orange}, ${LIGHT_COLOR.amber}, ${LIGHT_COLOR.green})` }} />
          <span className="sc-scale-lbl"><b>Риск</b> не оплачен → оплачен</span>
        </span>
      </div>

      <div className="sc-filter-bar">
        <div className="sc-filter-presets">
          <div className="sc-filter-eyebrow">Готовые скрины</div>
          <div className="sc-presets">{PRESETS.map((p) => <button key={p.id} className={"sc-preset" + (presetId === p.id ? " on" : "")} onClick={() => applyPreset(p)}><div className="pn">{p.name}</div><div className="pd">{p.desc}</div></button>)}</div>
        </div>
        <div className="sc-filter-universe">
          <div className="sc-filter-eyebrow">Тип бумаги</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <PickDropdown label="Тип" value={typeId} valueLabel={(TYPES.find((t) => t.id === typeId) || TYPES[0]).label} options={typeOptions} onChange={(id) => { setTypeId(id); setPresetId(null); }} />
            <PickDropdown label="Сектор" value={sector} valueLabel={sector || "Все секторы"} dot={sector ? secColor(sector) : null} options={sectorOptions} onChange={(id) => { setSector(id); setPresetId(null); }} />
          </div>
        </div>
      </div>

      <div className={"sc-layout" + (railOpen ? "" : " sc-collapsed")}>
        {railOpen && (
          <CriteriaRail ranges={ranges} sector={sector} typeId={typeId} lightFilter={lightFilter}
            onRangeChange={(k, rr) => { setRanges((rs) => ({ ...rs, [k]: rr })); setPresetId(null); }}
            onAdd={(k) => { setRanges((rs) => ({ ...rs, [k]: [...METRICS[k].dom] })); setPresetId(null); }}
            onRemove={(k) => { setRanges((rs) => { const n = { ...rs }; delete n[k]; return n; }); setPresetId(null); }}
            onReset={reset} resultCount={filtered.length} total={total} distributions={distributions} allRows={rows} onCollapse={() => setRailOpen(false)} />
        )}
        <div className="sc-results">
          <div className="sc-toolbar"><div className="sc-toolbar-top">
            {!railOpen && <button className="sc-filters-btn" onClick={() => setRailOpen(true)}>Фильтры{activeN > 0 && <span className="sc-filters-n">{activeN}</span>}</button>}
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
            ? <ResultsTable rows={filtered} sort={sort} setSort={setSort} density={density} onPick={setPicked} picked={picked} secColor={secColor} pctOf={pctOf} />
            : (filtered.length ? <MapView rows={filtered} onPick={setPicked} picked={picked} secColor={secColor} sectors={secList} /> : <div className="sc-map"><div className="sc-noresult">Ни одна бумага не проходит все условия. Ослабьте критерии слева.</div></div>)}
        </div>
      </div>

      <p className="sc-foot-note">Вердикт «доходность vs риск», спред к ОФЗ, Risk Score 1–5 и ожидаемые потери рассчитаны кодом по методике Basis (docs/bond_analys.md) на данных MOEX. У флоатеров/линкеров и бумаг с близкой офертой YTM/спред к фиксированной ОФЗ некорректны — для них вердикт строится по кредитному риску. Это аналитический ориентир, не инвестиционная рекомендация и не сигнал к покупке или продаже.</p>

      <DetailDrawer row={picked} onClose={() => setPicked(null)} onOpenCompany={onOpenCompany} secColor={secColor} />
    </div>
  );
}
