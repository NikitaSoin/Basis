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
// neutral — для показателей, где знак не равен «лучше/хуже» (чистый долг: рост долга не
// всегда негатив, снижение не всегда позитив). Глиф ▲/▼ остаётся, цвет снимается: иначе
// получалось, что бар мы уже нейтрализовали, а дельта рядом всё ещё красит рост долга
// зелёным (ОТК 2026-07-29).
const Delta = ({ v, d = 1, pp = false, neutral = false }) =>
  v == null || isNaN(v) ? null : (
    <span className={`delta${neutral ? "" : v >= 0 ? " up" : " dn"}`} style={neutral ? { fontSize: 11, color: "var(--ink-3)" } : { fontSize: 11 }}>
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
  // 🔴 Владелец 2026-07-29: диапазон лет расширен (не резать до 5/8 периодов) —
  // при n>6 слот (w/n) у 9px моно-шрифта подписей уже недостаточен, соседние
  // подписи налезают друг на друга. Оставляем подпись только у первой и
  // последней точки (сам ряд столбиков всё равно показывает тренд высотой) —
  // подписывать каждую точку не нужно, если их больше шести.
  const showLabel = (i) => n <= 6 || i === 0 || i === n - 1;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ display: "block", overflow: "visible" }}>
      {xs.map((v, i) => {
        const bh = 5 + ((v - mn) / r) * plotH, x = xi(i), y = h - pB - bh, last = i === n - 1;
        return <rect key={i} x={(x - bw / 2).toFixed(1)} y={y.toFixed(1)} width={bw.toFixed(1)} height={bh.toFixed(1)} rx="2" fill={color} fillOpacity={last ? 1 : 0.32} />;
      })}
      {xs.map((v, i) => {
        const last = i === n - 1;
        return showLabel(i) && <text key={i} className="bc-v" x={xi(i)} y={(yi(v) - 5).toFixed(1)} textAnchor="middle" style={last ? { fill: color, fontWeight: 600 } : undefined}>{fmt(v)}</text>;
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

/* Разделы заметки режем по СМЫСЛУ заголовка, а не по порядку в файле.
   `financials_summary.md` писал субагент свободными заголовками (одна и та же тема —
   «Дорого/дёшево», «Дорого / дёшево», «Дорого или дёшево», «Мультипликаторы»), а
   число разделов гуляет 4–9, поэтому прежний slice(0,6) молча выбрасывал хвост у
   половины компаний. Владелец 2026-07-30: из заметки убрать оценку и мультипликаторы
   (единственная цена карточки — BFV сверху), прогноз-прозу заменить прикидкой по
   темпу, отчётность (выручка + баланс + ОДДС) слить в ОДИН пункт. */
// Порядок проверок важен: сначала оценка (её убираем всегда), потом честные
// оговорки (иначе «Ключевые риски ОЦЕНКИ» уехали бы в мусор), потом процессные
// отчёты агента, а всё остальное — содержательное, идёт в разбор отчётности.
const SEC_VALUATION = /справедлив|дорого|дёшев|дешев|мультипликатор|коридор|прогноз/i;
const SEC_TAIL = /риск|ограничен|оговорк|аномал|ненадёжн|не верить|надёжност|статус данных|качество (данных|показателей)/i;
const SEC_PROCESS = /^(отчёт|итог|data)|чек-лист|методическ|методолог|резюме для аналитика|данные-флаги|связность|синтез|расхождение методов|\bоценк/i;

function groupSections(md) {
  const facts = [], tail = [];
  parseSections(md).forEach((s) => {
    if (SEC_VALUATION.test(s.title)) return;
    if (SEC_TAIL.test(s.title)) { tail.push(s); return; }
    if (SEC_PROCESS.test(s.title)) return;
    facts.push(s);
  });
  const join = (list) => list.map((s) => `### ${s.title}\n\n${s.body}`).join("\n\n");
  const out = [];
  if (facts.length) out.push({ title: "Что показывают отчёты", body: join(facts) });
  if (tail.length) out.push({ title: "Чему тут не верить", body: join(tail) });
  return out;
}

/* ── Прикидка «если темп удержится» (эндпоинт /run-rate, движок run_rate.py) ──
   НЕ прогноз аналитика и НЕ вторая справедливая цена: закрытая часть года ×
   историческая сезонная доля → годовой итог → форвардные мультипликаторы к живой
   цене. Коридор — фактический разброс доли за прошлые годы, не «±5 п.п.». */
const RR_COL = { low: "медленнее", mid: "текущий темп", high: "быстрее" };
const RR_UNIT = { "млн": 1, "млрд": 1000, "тыс": 0.001, "тысячи": 0.001, "тыс. руб.": 0.001 };

function RunRateBlock({ rr }) {
  if (!rr || rr.status !== "ok") return null;
  const sc = rr.scenarios || {};
  const mid = sc.mid;
  if (!mid) return null;
  const cols = ["low", "mid", "high"].filter((k) => sc[k]);
  const u = RR_UNIT[rr.unit] ?? 1;
  // Единица — на СТРОКУ, а не общая: у банка ЧПД может быть в трлн, а прибыль в млрд.
  // Общая единица в шапке соврала бы в 1000× (те же грабли, что у таблицы финмодели).
  const rowUnit = (key) => {
    const nums = cols.map((k) => sc[k][key]).filter((v) => typeof v === "number" && !isNaN(v)).map(Math.abs);
    const maxMlrd = (nums.length ? Math.max(...nums) : 0) * u / 1000;
    return maxMlrd >= 1000
      ? { div: 1e6 / u, dec: 2, l: "трлн ₽" }
      : { div: 1e3 / u, dec: maxMlrd >= 100 ? 0 : 1, l: "млрд ₽" };
  };
  const uTop = rowUnit("revenue"), uProfit = rowUnit("profit");
  const money = (v, un) => (typeof v === "number" ? num(v / un.div, un.dec) : "—");
  const gp = rr.growth?.profit_pct;
  const rows = [
    { l: `${rr.top_label}, ${uTop.l}`, f: (s) => money(s.revenue, uTop), skip: mid.revenue == null },
    { l: `Чистая прибыль, ${uProfit.l}`, f: (s) => money(s.profit, uProfit), bold: true },
    { l: "Прибыль на акцию, ₽", f: (s) => (s.eps == null ? "—" : num(s.eps, s.eps >= 100 ? 0 : 2)) },
    { l: "P/E", f: (s) => (s.pe == null ? "—" : num(s.pe, 2)), bold: true },
    { l: "P/B", f: (s) => (s.pb == null ? "—" : num(s.pb, 2)), skip: mid.pb == null },
    { l: `Дивиденд, ₽${rr.payout_pct ? ` (payout ${num(rr.payout_pct, 0)} %)` : ""}`, f: (s) => (s.dps == null ? "—" : num(s.dps, 2)), skip: mid.dps == null },
    { l: "Дивдоходность", f: (s) => (s.div_yield_pct == null ? "—" : `${num(s.div_yield_pct, 1)} %`), bold: true, skip: mid.div_yield_pct == null },
  ].filter((r) => !r.skip);

  return (
    <div className="rr">
      <div className="rr-h">Если темп удержится <span className="tag tag-model">модель</span></div>
      <div className="rr-lead">
        {gp != null && <>Прибыль <b>{gp >= 0 ? "+" : "−"}{num(Math.abs(gp), 1)} %</b> г/г за {rr.period.word} {rr.year}. </>}
        При таком темпе до конца года: <b>P/E {num(mid.pe, 2)}</b>
        {mid.div_yield_pct != null && <> · дивдоходность <b>{num(mid.div_yield_pct, 1)} %</b></>}
      </div>
      <div className="rr-tw">
        <table className="rr-t">
          <thead><tr><th />{cols.map((k) => <th key={k} className={k === "mid" ? "me" : ""}>{RR_COL[k]}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td className={r.bold ? "l b" : "l"}>{r.l}</td>
                {cols.map((k) => <td key={k} className={`v${k === "mid" ? " me" : ""}${r.bold ? " b" : ""}`}>{r.f(sc[k])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rr-note">
        Сезонность учтена по истории: {rr.period.word} даёт <b>{num(rr.period.closed_share_pct, 1)} %</b> годовой прибыли
        {rr.period.share_years > 1 ? <> (медиана {rr.period.share_years} прошлых лет, коридор — их фактический разброс)</> : <> (один прошлый год — коридор не строится)</>}.
        {" "}{rr.disclaimer}
      </div>
      {(rr.warnings || []).length > 0 && (
        <div className="an-flags rr-w">{rr.warnings.map((w, i) => <div className="an-flag" key={i}>{w}</div>)}</div>
      )}
    </div>
  );
}

export default function FinanceTab({ fin, company, price, sectorMult, peersData, finMd }) {
  const [tab, setTab] = useState("pnl");
  const [detOpen, setDetOpen] = useState(false);
  const [peerYear, setPeerYear] = useState(null);
  const [period, setPeriod] = useState("annual"); // "annual" | "interim" — переключатель периодичности таблиц
  // На мобильном (≤1020px) правый рейл «Заметка аналитика» больше не стекает в конец
  // вкладки — открывается выезжающей справа панелью (паттерн Скринера, sc-drawer),
  // триггер — компактный тизер вверху dash. На десктопе rail всегда открыт (sticky).
  const [railOpen, setRailOpen] = useState(false);
  // Прогнозная финмодель (пилот 3-5 компаний) — отдельный эндпоинт, 404 = модели нет
  // (секция ниже просто не рендерится). Самостоятельный fetch, не завязан на fin.
  const [model, setModel] = useState(null);
  // Шапка заметки — справедливая цена по методике Basis (BFV, тот же эндпоинт и то же
  // число, что в «Обзоре»): владелец 2026-07-30 — сверху ТОЛЬКО она, без коридора,
  // уверенности и счётчика источников. Прежде здесь стояла старая мульти-методная
  // оценка из financials.json — из-за этого на карточке было ДВЕ разные цены.
  const [bfv, setBfv] = useState(null);
  // Прикидка «если темп удержится» — /run-rate, тело всегда со status (не ok → блока нет)
  const [runRate, setRunRate] = useState(null);
  useEffect(() => {
    setModel(null); setBfv(null); setRunRate(null);
    const ticker = company?.ticker;
    if (!ticker) return;
    const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";
    const base = `${apiUrl}/api/companies/by-ticker/${ticker}`;
    let alive = true;
    const get = (path, set) => fetch(`${base}${path}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) set(d); })
      .catch(() => { if (alive) set(null); });
    get("/financial-model", setModel);
    get("/bfv", setBfv);
    get("/run-rate", setRunRate);
    return () => { alive = false; };
  }, [company?.ticker]);

  if (!fin) return null;

  const meta = fin.meta || {};
  const interim = fin.interim || {};
  const hasInterim = Array.isArray(interim.periods) && interim.periods.length > 0;
  const usingInterim = hasInterim && period === "interim";
  const is = (usingInterim ? interim.income_statement : fin.income_statement) || {};
  const adj = fin.adjusted || {};
  const bs = (usingInterim ? interim.balance_sheet : fin.balance_sheet) || {};
  const cf = (usingInterim ? interim.cash_flow : fin.cash_flow) || {};
  const ret = fin.returns || {};
  const mt = fin.metrics_timeseries || {};
  const mult = fin.multiples || {};
  const cur = mult.current || {};
  const hist = mult.historical_avg || {};
  const val = fin.valuation || {};
  const fvr = val.fair_value_range || {};
  const years = usingInterim ? interim.periods.map((p) => p.label) : (meta.fiscal_years || []).map(String);
  const std = meta.reporting_standard || "МСФО";
  const lastYr = years[years.length - 1] || "";
  const ccy = "₽";

  // 🔴 Динамика на ПРОМЕЖУТОЧНЫХ периодах — только к СОПОСТАВИМОМУ периоду прошлого
  // года. В interim.periods перемешаны разные по длине периоды (ROSN: 6М·9М·3М·6М·9М·3М),
  // и общий yoy() «последнее ÷ предыдущее» сравнивал квартал с девятью месяцами —
  // выходило бессмысленное «−63 % г/г». Пару считает бэкенд (interim_periods.py) и
  // отдаёт готовым индексом interim.yoy_idx; нет пары в ряду — дельты нет (пусто
  // честнее ложного числа). На годовых рядах поведение прежнее.
  const yoyIdx = usingInterim && Array.isArray(interim.yoy_idx) ? interim.yoy_idx : null;
  const yoyAt = (a) => {
    if (!yoyIdx) return yoy(a);
    if (!Array.isArray(a)) return null;
    let i = -1;
    for (let k = a.length - 1; k >= 0; k--) { if (a[k] != null) { i = k; break; } }
    if (i < 0) return null;
    const j = yoyIdx[i];
    const p = j == null ? null : a[j];
    return typeof p === "number" && p !== 0 ? ((a[i] - p) / Math.abs(p)) * 100 : null;
  };
  // Подпись сопоставления периодов в интерим-режиме («6М 2025 к 6М 2024»). Стояла в шапке
  // «Разбора отчёта»; плитку убрали 2026-07-30, а дельты YoY остались в диаграммах динамики —
  // подпись переехала туда же, к ним, иначе непонятно, с чем сравнивается период.
  const yoyPairLabel = (() => {
    if (!yoyIdx) return null;
    const src = (interim.bank_pnl || {}).net_profit || (interim.income_statement || {}).net_profit || null;
    if (!Array.isArray(src)) return null;
    let i = -1;
    for (let k = src.length - 1; k >= 0; k--) { if (src[k] != null) { i = k; break; } }
    const j = i >= 0 ? yoyIdx[i] : null;
    const ps = interim.periods || [];
    return j != null && ps[i] && ps[j] ? `${ps[i].label} к ${ps[j].label}` : null;
  })();

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
  const bp = (usingInterim ? interim.bank_pnl : fin.bank_pnl) || {}, bmx = (usingInterim ? interim.bank_metrics : fin.bank_metrics) || {};
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
  const revYoy = yoyAt(is.revenue), npYoy = yoyAt(is.net_profit), ebYoy = yoyAt(is.ebitda);
  const bNipYoy = isBank ? yoyAt(bNipArr) : null;
  const bNpYoy  = isBank ? yoyAt(bNpArr)  : null;
  // rows / verdictHead (тезисы «Разбора отчёта» и его шапка) удалены вместе с плиткой
  // 2026-07-30 — больше не читались никем. Годовые дельты выше (revYoy/npYoy/ebYoy,
  // bNipYoy/bNpYoy) НЕ трогать: на них стоят диаграммы динамики ниже.

  /* 2. Справедливой стоимости из financials.json во вкладке БОЛЬШЕ НЕТ. Блок «как
     сходятся методы» уехал в «Обзор» (2026-07-29), а шапка «Заметки аналитика»
     переведена на BFV (2026-07-30): пока она показывала fair_value_range.base,
     на одной карточке жили ДВЕ разные справедливые цены — цена методики Basis в
     «Обзоре» и старая мульти-методная в заметке. Единственная цена — BFV. */

  /* 3. Ключевые показатели + мультипликаторы */
  const kfi = isBank ? [
    { l: "Чистый процентный доход", a: bNipArr,  d: bNipYoy },
    { l: "Чистая прибыль",          a: bNpArr,   d: bNpYoy },
    { l: "ROE",        pctv: lastN(bRoeArr), d: yoyAt(bRoeArr),  isPP: true },
    { l: "ЧПМ (NIM)", pctv: lastN(bNimArr), d: yoyAt(bNimArr),  isPP: true },
    { l: "Кредитный портфель", a: bLoanArr, d: yoyAt(bLoanArr) },
    { l: "Средства клиентов",  a: bDepArr,  d: yoyAt(bDepArr)  },
  ] : [
    { l: "Выручка", a: is.revenue, d: revYoy }, { l: "EBITDA", a: is.ebitda, d: ebYoy },
    { l: "Чистая прибыль", a: is.net_profit, d: npYoy }, { l: "FCF", a: cf.fcf, d: yoyAt(cf.fcf) },
    { l: "Маржа EBITDA", pctv: ebMargin, d: (ebMargin != null && prevN(margins.ebitda_margin) != null) ? ebMargin - prevN(margins.ebitda_margin) : null, isPP: true },
    { l: "Чистый долг", a: bs.net_debt, d: yoyAt(bs.net_debt), neutral: true },
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
        det:true — деталь (скрыта до «Детализация статей»).
     🔴 Раньше искусственно резалось до последних 5 (год)/8 (интерим) периодов —
     владелец 2026-07-29: данные по некоторым компаниям собраны с 2016 года (17/264
     компаний имеют полную историю 2016-2025, остальные — короче, самая частая
     точка старта 2021 — 108/264), а вкладка «Финансы» их не показывала, обрезая
     историю визуально до 2021. Таблицы уже вёрстаны со скроллом (.tbl-scroll,
     overflow-x:auto) — показываем ВСЮ доступную историю, не резервируем число. */
  const yslice = years;
  const sl = (a) => (Array.isArray(a) ? a : []);
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
          // Статьи моста: СНАЧАЛА актуальные (заполнен последний год), потом
          // исторические. У компаний со сменой стандарта (Яндекс: US GAAP до
          // 2022 → МСФО с 2023) каждая статья живёт только в своей эре — без
          // сортировки актуальный мост перемешивался с прочерками старой эры
          // и читался как «дыры» (владелец, 2026-07-28).
          : [...expLines].sort((a, b) => {
              const lastOf = (l) => { const v = l.values || []; return v[v.length - 1] != null ? 0 : 1; };
              return lastOf(a) - lastOf(b);
            }).map((el) => M(el.name, el.values, { det: true, muted: true }))),
        M("EBITDA", is.ebitda, { bold: true }),
        // Справочная «Амортизация» — только если её НЕТ среди статей моста
        // (при by_nature D&A обычно уже статья expense_lines — иначе дубль
        // одной величины двумя строками, жалоба владельца 2026-07-28).
        ...(expLines.some((el) => /аморт|износ|d&a/i.test(el.name || ""))
          ? [] : [M("Амортизация", is.da, { det: true, muted: true })]),
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
  const tabsAvail = ["pnl", "bs", "cf", ...(usingInterim ? [] : ["mult"])].filter(hasTable);
  const curTab = tabsAvail.includes(tab) ? tab : (tabsAvail[0] || "pnl");
  const TLABEL = { pnl: "P&L", bs: "Баланс", cf: "ОДДС", mult: "Мультипликаторы" };
  const curHasDet = TABLES[curTab].some((r) => !r.sectionHeader && r.det && sl(r.a).some((x) => x != null));
  // Единица — на СТРОКУ (тот же принцип, что «Финансовая модель» ниже — moneyRowUnit):
  // B(v) внутри молча переключает млрд↔трлн по величине КАЖДОЙ ячейки независимо
  // (bln()), а прежний код брал только {}.v без {}.u — строка со значением ≥ 1 трлн ₽
  // (выручка/активы Газпрома, Роснефти, Сбера и т.п.) показывалась под общей шапкой
  // «млрд ₽», занижая масштаб в 1000×. Единица — по МАКСИМУМУ |значения| в строке
  // (по всем годам), одна на всю строку — чтобы годы внутри строки не расходились.
  const rowMoneyUnit = (vals) => {
    const nums = (vals || []).filter((v) => typeof v === "number" && !isNaN(v)).map((v) => Math.abs(v * U) / 1000);
    const maxMlrd = nums.length ? Math.max(...nums) : 0;
    return maxMlrd >= 1000 ? { div: 1e6, dec: 2, u: "трлн ₽" } : { div: 1e3, dec: maxMlrd >= 100 ? 0 : 1, u: "млрд ₽" };
  };
  // форматирование ячейки по kind
  // j — индекс в yslice (для проверки убытка по соответствующему году)
  const fmtCell = (r, v, j, rowUnit) => {
    if (v == null || isNaN(v)) {
      if (r.lossArr && j != null && r.lossArr[j] != null && r.lossArr[j] < 0)
        return <span style={{ color: "var(--ink-3)", fontSize: 11 }} title="убыток — неприменимо">—</span>;
      return <span style={{ color: "var(--ink-3)", fontSize: 11 }}>н.д.</span>;
    }
    if (r.kind === "pct") return num(v, 1) + " %";
    if (r.kind === "ratio") return num(v, 2);
    if (r.kind === "x") return num(v, 2) + "×";
    if (r.kind === "rub") return num(v, 1) + " ₽";
    if (rowUnit) return num((v * U) / rowUnit.div, rowUnit.dec); // money, единица строки
    return B(v).v; // money — фолбэк там, где строка не передана
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
  // единица теперь показывается ПО СТРОКЕ (rowMoneyUnit, см. выше) — общий заголовок
  // не может нести одну единицу для всех строк таблицы (разный масштаб млрд/трлн)
  const unitNote = curTab === "mult" ? "×, %" : "Показатель";

  /* динамика — столбчатые диаграммы ключевых показателей (рендерятся в блоке
     «Ключевые показатели и мультипликаторы»; владелец 2026-07-29: диаграммы динамики
     переехали из «Прибыли и рентабельности» сюда, к своим же числам). Деньги — в
     млрд ₽, при масштабе > 1000 млрд подписи в трлн (иначе 5-значные числа не читаются). */
  const fmtN0 = (v) => num(v, 0), fmtN2 = (v) => num(v, 2);
  const bnScale = (a) => sl(a).map((v) => (v == null ? null : v * U / 1000));   // → млрд ₽
  const moneyChart = (l, arr, color, head, d, neutralDelta = false) => {
    if (!sl(arr).some((x) => x != null)) return null;
    const b = bnScale(arr);
    const mx = Math.max(0, ...b.filter((x) => x != null).map((x) => Math.abs(x)));
    const tri = mx >= 1000;
    return { l, data: tri ? b.map((x) => (x == null ? null : x / 1000)) : b,
             color, fmt: tri ? fmtN2 : fmtN0, head, d, neutralDelta, cap: tri ? "трлн ₽" : "млрд ₽" };
  };
  const kfiCharts = (isBank ? [
    moneyChart("Чистый процентный доход", bNipArr, "var(--accent)", B(lastN(bNipArr)), bNipYoy),
    moneyChart("Чистая прибыль", bNpArr, "var(--amber)", B(lastN(bNpArr)), bNpYoy),
    moneyChart("Кредитный портфель", bLoanArr, "var(--pos)", B(lastN(bLoanArr)), yoyAt(bLoanArr)),
    moneyChart("Средства клиентов", bDepArr, "var(--ink-3)", B(lastN(bDepArr)), yoyAt(bDepArr)),
  ] : [
    moneyChart("Выручка", is.revenue, "var(--accent)", B(lastN(is.revenue)), revYoy),
    moneyChart("EBITDA", is.ebitda, "var(--pos)", B(lastN(is.ebitda)), ebYoy),
    moneyChart("Чистая прибыль", is.net_profit, "var(--amber)", B(lastN(is.net_profit)), npYoy),
    moneyChart("FCF", cf.fcf, "var(--accent)", B(lastN(cf.fcf)), yoyAt(cf.fcf)),
    // чистый долг: чистый кэш (≤0) — зелёный (позитив), реальный долг — нейтральный
    // (не красный: рост долга ≠ всегда плохо, а красный при чистом кэше вводил в заблуждение)
    moneyChart("Чистый долг", bs.net_debt, (lastN(bs.net_debt) != null && lastN(bs.net_debt) <= 0) ? "var(--pos)" : "var(--ink-3)", B(lastN(bs.net_debt)), yoyAt(bs.net_debt), true),
  ]).filter(Boolean);

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

  // база капитализации (backend/app/services/share_capital.py): по каким классам
  // акций посчитаны P/E и P/B — приходит только когда поправка применилась
  const capBasis = (fin.multiples || {}).capital_basis || null;
  const shareCnt = (n) => (n >= 1e9 ? `${num(n / 1e9, 2)} млрд` : n >= 1e6 ? `${num(n / 1e6, 1)} млн` : num(n, 0));
  const capClassLine = capBasis && Array.isArray(capBasis.classes) && capBasis.classes.length > 1
    ? capBasis.classes.map((c) => `${c.ticker || c.class} ${shareCnt(c.count || 0)} шт${c.listed === false ? " (вне биржи)" : ""}`).join(" + ")
    : null;

  /* рейл «Заметка аналитика» */
  const railSections = groupSections(finMd);
  // Шапка — BFV. status ≠ ok (отрицательный капитал, ROE ниже терминального роста и
  // прочие зоны неприменимости, см. docs/bfv_limitations.md) → числа НЕТ, вместо него
  // честная причина. Старую оценку из financials.json сюда не подставляем — именно
  // подмена одной методики другой и рождала две разные цены на карточке.
  const bfvOk = !!(bfv && bfv.status === "ok" && typeof bfv.fair_price === "number");
  const bfvFair = bfvOk ? bfv.fair_price : null;
  const bfvUpside = bfvOk && typeof bfv.upside_pct === "number" ? bfv.upside_pct : null;
  const bfvWhy = bfv && bfv.status !== "ok"
    ? ((Array.isArray(bfv.warnings) && bfv.warnings[0]) || "методика к этой компании неприменима")
    : null;
  const railVerdict = bfvUpside == null ? "" : Math.abs(bfvUpside) < 10 ? "оценён справедливо" : bfvUpside > 0 ? "есть потенциал роста" : "оценён с премией к модели";
  const caveats = [];
  (val.methods || []).forEach((m) => { const cs = (m.explain && m.explain.caveats) || []; cs.forEach((c) => { if (caveats.length < 3 && c && !caveats.includes(c)) caveats.push(c); }); });

  /* 6. Финансовая модель (прогноз) — пилотный эндпоинт /financial-model, 404 = null,
     секция ниже просто не рендерится. Числа модели уже в млн ₽ (revenue/ebitda/
     net_profit/fcf и банковские net_interest_income/net_fee_income/operating_income)
     и ₽/акция (eps/dps/bvps) — bln()/num() применяются НАПРЯМУЮ, без множителя единиц
     U (тот привязан к financials.json, у модели своя единица).
     ЕДИНИЦЫ: bln() сам переключает млрд↔трлн по величине значения (у SBER net_profit
     2026 = 1 920 000 млн = 1,92 ТРЛН) — единицу НЕЛЬЗЯ хардкодить в заголовке/футноуте,
     иначе она соврёт в 1000× для компаний за порогом трлн. moneyRowUnit() считает ОДНУ
     единицу на строку (по максимальному |значению| в строке — база+живое, все годы) и
     показывает её один раз в первой колонке; сами ячейки — просто число в этой единице
     (никакого дублирования "млрд ₽" 21 раз в таблице). */
  const mMeta = model?.meta || {};
  const mHorizon = (mMeta.horizon_years || []).map(String);
  const mForecastBase = model?.forecast?.base || {};
  const mLiveAdj = model?.live_adjusted_base || null;
  const mDriversByKey = {};
  (model?.drivers || []).forEach((d) => { mDriversByKey[d.key] = d; });
  const SCEN_LABEL = { bear: "Медведь", base: "База", bull: "Бык" };
  // Реестр строк на ВСЕ известные сектор-шаблоны пилота (oil_gas/retail — revenue+ebitda+fcf;
  // banking — net_interest_income/net_fee_income/operating_income+roe/nim+bvps вместо них) —
  // рендерится только то, что реально пришло в forecast.base, остальное фильтруется ниже.
  const FM_ROW_DEFS = [
    { key: "revenue", l: "Выручка", kind: "money", bold: true },
    { key: "net_interest_income", l: "Чистый процентный доход", kind: "money", bold: true },
    { key: "net_fee_income", l: "Чистый комиссионный доход", kind: "money" },
    { key: "operating_income", l: "Операционные доходы", kind: "money", bold: true },
    { key: "ebitda", l: "EBITDA", kind: "money", bold: true },
    { key: "margins_ebitda_pct", l: "Маржа EBITDA", kind: "pct", muted: true },
    { key: "net_profit", l: "Чистая прибыль", kind: "money", bold: true },
    { key: "fcf", l: "FCF", kind: "money", bold: true },
    { key: "roe_pct", l: "ROE", kind: "pct", muted: true },
    { key: "nim_pct", l: "ЧПМ (NIM)", kind: "pct", muted: true },
    { key: "eps_rub", l: "EPS", kind: "rub" },
    { key: "dps_rub", l: "DPS", kind: "rub" },
    { key: "bvps_rub", l: "BVPS", kind: "rub", muted: true },
  ];
  const FM_ROWS = FM_ROW_DEFS.filter((r) => mHorizon.some((y) => mForecastBase[r.key]?.[y] != null));
  // Единица на СТРОКУ (не глобальная): по максимальному |значению| в строке (база + живое,
  // по всем годам горизонта) — те же пороги, что у bln().
  const moneyRowUnit = (vals) => {
    const nums = (vals || []).filter((v) => typeof v === "number" && !isNaN(v)).map((v) => Math.abs(v));
    const maxMlrd = (nums.length ? Math.max(...nums) : 0) / 1000;
    return maxMlrd >= 1000 ? { div: 1e6, dec: 2, u: "трлн ₽" } : { div: 1e3, dec: maxMlrd >= 100 ? 0 : 1, u: "млрд ₽" };
  };
  // moneyUnit не передан → форматируем как самостоятельное число через bln() (свой юнит,
  // возвращается инлайн) — нужно для track record, где строка не привязана к горизонту.
  const fmtFmVal = (v, kind, moneyUnit) => {
    if (v == null || isNaN(v)) return "—";
    if (kind === "pct") return `${num(v, 1)} %`;
    if (kind === "rub") return `${num(v, 0)} ${ccy}`;
    if (moneyUnit) return num(v / moneyUnit.div, moneyUnit.dec);
    const b = bln(v);
    return `${b.v} ${b.u}`;
  };
  const mHasLiveRow = (key) => !!(mLiveAdj && mLiveAdj[key] && mHorizon.some((y) => mLiveAdj[key][y] != null));
  const meaningfulDiff = (a, b) => a != null && b != null && Math.abs(a - b) > Math.abs(b || 1) * 0.002;
  const mVal = model?.valuation || {};
  const mWeighted = typeof mVal.weighted_fair_price_rub === "number" ? mVal.weighted_fair_price_rub : null;
  const mLivePrice = typeof model?.live_price_rub === "number" ? model.live_price_rub : null;
  const mUpsideLive = typeof model?.upside_pct_live === "number" ? model.upside_pct_live : null;
  const mFwdPeLive = typeof model?.forward_pe_live === "number" ? model.forward_pe_live : null;
  const mBasePct = model?.scenario_weights?.base != null ? Math.round(model.scenario_weights.base * 100) : null;
  const mScenPrices = model ? ["bear", "base", "bull"].map((k) => ({
    key: k, label: SCEN_LABEL[k], weight: model.scenario_weights?.[k], price: mVal.per_scenario?.[k]?.fair_price_rub,
  })).filter((s) => typeof s.price === "number") : [];
  const mSensRows = Array.isArray(model?.sensitivity) ? model.sensitivity : [];
  const mTrackRows = Array.isArray(model?.track_record) ? model.track_record : [];
  const mDataFlags = Array.isArray(model?.data_flags) ? model.data_flags : [];
  const mBridge = model?.bridge || null;
  const MFM_METRIC_LABEL = {
    revenue: "Выручка", ebitda: "EBITDA", net_profit: "Чистая прибыль", fcf: "FCF", eps_rub: "EPS", dps_rub: "DPS",
    net_interest_income: "ЧПД", net_fee_income: "ЧКД", operating_income: "Опер. доходы",
    roe_pct: "ROE", nim_pct: "NIM", bvps_rub: "BVPS",
  };
  const mMetricKind = (metric) => (FM_ROW_DEFS.find((r) => r.key === metric) || {}).kind || "money";

  return (
    <div className="fin-hybrid">
      <div className="layout">
        <div className="dash">
          {/* «Свежее событие: вышел отчёт» (report_watch.py) убрано отсюда 2026-07-29
              (владелец: дублировало «Разбор отчёта» ниже и путало) — теперь живёт
              в «Обзоре» (renderOverview, CompanyCardView.jsx), где ему и место как
              самому свежему сигналу; прошлые разборы не теряются — история в
              /earnings/archive (см. CompanyCardView renderOverview). */}

          {/* Тизер-триггер «Заметка аналитика» — виден только на мобильном (≤1020px,
              CSS). На десктопе rail открыт всегда рядом (sticky), тизер там не нужен. */}
          <button type="button" className="fv-rail-teaser" onClick={() => setRailOpen(true)}>
            <span className="fv-rail-teaser-ic">✎</span>
            <span className="fv-rail-teaser-body">
              <span className="fv-rail-teaser-t">Заметка аналитика{railVerdict ? ` — ${railVerdict}` : ""}</span>
              {bfvFair != null && <span className="fv-rail-teaser-v">{num(bfvFair, bfvFair >= 100 ? 0 : 1)} {ccy}{bfvUpside != null && <span className={`delta ${bfvUpside >= 0 ? "up" : "dn"}`} style={{ marginLeft: 8 }}>{bfvUpside >= 0 ? "▲" : "▼"} {num(Math.abs(bfvUpside), 0)} %</span>}</span>}
            </span>
            <span className="fv-rail-teaser-chev">›</span>
          </button>

          {/* «Разбор отчёта» убран отсюда 2026-07-30 (владелец): плитка открывала вкладку
              и повторяла то, что вкладка и так раскрывает ниже подробно. Сам разбор живёт
              в «Обзоре» (renderOverview, CompanyCardView.jsx) — там ему место как ответу
              сверху. Тезисы rows/verdictHead удалены выше вместе с плиткой (их больше
              никто не читал). */}

          {/* 2. Справедливая стоимость и BFV перенесены во вкладку «Обзор»
              (владелец 2026-07-29): главная цена = «Справедливая цена по методике
              Base» (движок BFV), рядом исторические P/E и P/B. Обычный DCF / CAPM /
              секторный EV/EBITDA убраны. См. renderOverview в CompanyCardView.jsx. */}
          {/* 3. Ключевые показатели и мультипликаторы */}
          <div className="card">
            <h3>Ключевые показатели и мультипликаторы <span className="tag tag-fact">факт</span><span className="hmeta">{livePrice ? `цена ${num(livePrice, 2)} ${ccy} · ` : ""}позиция к {sm ? "среднему по сектору" : "своей 5-летней норме"}</span></h3>
            {/* База капитализации. У эмитентов с несколькими классами акций (а у
                Транснефти обыкновенные вообще не торгуются) P/E и P/B считаются от
                капитализации ЭМИТЕНТА — иначе они занижены в разы. Показываем это
                только там, где поправка реально сработала, чтобы не шуметь. */}
            {capBasis && Math.abs((capBasis.factor ?? 1) - 1) > 0.05 && (
              <div className="cap-basis">
                <b>{capBasis.basis}</b>
                {capClassLine && <> — {capClassLine}</>}
                {capBasis.reliability === "low" && <> · надёжность оценки неторгуемого класса низкая</>}
                {(capBasis.warnings || []).map((w, i) => <div className="cb-w" key={i}>{w}</div>)}
              </div>
            )}
            {/* Сетка «Масштаб бизнеса — абсолютные показатели за <год>» убрана 2026-07-30
                (владелец): те же Выручка / EBITDA / Чистая прибыль / FCF / Чистый долг за
                последний год уже стоят в заголовках диаграмм динамики ниже — числа
                дублировались один в один. Массив kfi оставлен: на нём считаются ряды и
                дельты для самих диаграмм. */}
            {kfiCharts.length > 0 && (<>
              <p className="sub">Динамика {yslice[0]}–{lastYr} — как менялись главные показатели ({std}){yoyPairLabel ? ` · сравнение ${yoyPairLabel}` : ""}</p>
              <div className="fc-dyn">
                {kfiCharts.map((d, i) => (
                  <div className="d" key={i}>
                    <div className="dl">{d.l}</div>
                    <div className="dv">{d.head.v}<s> {d.head.u}</s> {d.d != null && <Delta v={d.d} pp={d.isPP} neutral={d.neutralDelta} />}</div>
                    <BarChart data={d.data} color={d.color} fmt={d.fmt} />
                    <div className="bc-cap">{d.cap}{d.cap.endsWith("· ") ? "" : " · "}{yslice[0]}–{lastYr}</div>
                  </div>
                ))}
              </div>
            </>)}
            <p className="sub" style={{ marginTop: 16 }}>Мультипликаторы — не просто число, а позиция относительно {sm ? "среднего по сектору" : "собственной 5-летней нормы"}</p>
            <div className="mcards">{mcards.map((m, i) => <MCard key={i} {...m} />)}</div>
          </div>

          {/* 4. Прибыль и рентабельность */}
          {tabsAvail.length > 0 && (
            <details className="disc" open>
              <summary><div><div className="dt">Прибыль и рентабельность по годам</div><div className="dd">Отчётность за {yslice.length} лет · мультипликаторы · нормализация прибыли</div></div><span className="tag tag-fact" style={{ marginLeft: 8 }}>факт</span><span className="tag tag-est">оценка</span><span className="chev">▾</span></summary>
              <div className="disc-body">
                <div className="subh">Отчётность и мультипликаторы</div>
                <div className="mtbar">
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                    {hasInterim && (
                      <div className="miniseg">
                        <button className={period === "annual" ? "on" : ""} onClick={() => setPeriod("annual")}>Годовые</button>
                        <button className={period === "interim" ? "on" : ""} onClick={() => setPeriod("interim")}>Квартальные</button>
                      </div>
                    )}
                    <div className="miniseg">{tabsAvail.map((k) => <button key={k} className={curTab === k ? "on" : ""} onClick={() => setTab(k)}>{TLABEL[k]}</button>)}</div>
                  </div>
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
                        const rowUnit = r.kind === "money" ? rowMoneyUnit(vals) : null;
                        const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                        return (<tr className={cls} key={i}><td style={{ paddingLeft: r.det ? 24 : undefined, color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}{rowUnit && <span className="fm-row-unit"> · {rowUnit.u}</span>}</td>{yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j, rowUnit)}</span>{cellDelta(r, vals, j)}</td>)}</tr>);
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
                {meta.disclosure_note && <div className="foot-note" style={{ color: "var(--ink-3)" }}>Почему часть строк пуста: {meta.disclosure_note}</div>}
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
                        const rowUnit = r.kind === "money" ? rowMoneyUnit(vals) : null;
                        const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                        return (
                          <tr className={cls} key={i}>
                            <td style={{ color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}{rowUnit && <span className="fm-row-unit"> · {rowUnit.u}</span>}</td>
                            {yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j, rowUnit)}</span>{cellDelta(r, vals, j)}</td>)}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="foot-note">NIM — чистая процентная маржа; CoR — стоимость кредитного риска; стоимость фондирования — процентные расходы к средним процентным обязательствам; CIR — отношение расходов к доходам; Н1.0/Н1.2 — нормативы достаточности капитала (РСБУ). Источник: financials.json (bank_metrics).</div>
                {meta.disclosure_note && <div className="foot-note" style={{ color: "var(--ink-3)" }}>Почему часть строк пуста: {meta.disclosure_note}</div>}
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
                      <thead><tr><th>Показатель</th>{yslice.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                      <tbody>
                        {ecoRows.map((r, i) => {
                          const vals = sl(r.a);
                          const rowUnit = r.kind === "money" ? rowMoneyUnit(vals) : null;
                          const cls = [r.bold ? "bold" : "", r.accent ? "accent" : ""].filter(Boolean).join(" ");
                          return (
                            <tr className={cls} key={i}>
                              <td style={{ color: r.muted && !r.bold ? "var(--ink-3)" : undefined }}>{r.l}{rowUnit && <span className="fm-row-unit"> · {rowUnit.u}</span>}</td>
                              {yslice.map((y, j) => <td key={y}><span className="cv">{fmtCell(r, vals[j], j, rowUnit)}</span>{cellDelta(r, vals, j)}</td>)}
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

          {/* 6. Финансовая модель (прогноз) — пилот 3-5 компаний, /financial-model.
              404 → model=null → секция целиком не рендерится (ни заголовка, ни заглушки). */}
          {model && (
            <>
              <div className="card">
                <h3>Финансовая модель (прогноз) <span className="tag tag-model">модель</span><span className="hmeta">{mMeta.model_version ? `${mMeta.model_version} · ` : ""}горизонт {mHorizon.join("–")}</span></h3>
                {mMeta.model_status && <p className="sub">{mMeta.model_status}</p>}

                {model.structure_stale && (
                  <div className="ff-note" style={{ marginBottom: 16 }}>
                    <div className="nh">Модель ждёт пересборки</div>
                    Живой драйвер сдвинулся дальше барьера линейной эластичности (±40 % от базового уровня) — механический пересчёт ниже капирован и может быть неточным. Нужна ручная пересборка структуры аналитиком.
                  </div>
                )}

                {(mWeighted != null || mLivePrice != null) && (
                  <div className="fair">
                    {mWeighted != null && (
                      <div>
                        <div className="big">{num(mWeighted, mWeighted >= 100 ? 0 : 1)}<s> {ccy}</s></div>
                        <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>взвешенная справедливая · модель</div>
                      </div>
                    )}
                    {mUpsideLive != null && (
                      <div className={`ud delta ${mUpsideLive >= 0 ? "up" : "dn"}`}>{mUpsideLive >= 0 ? "▲" : "▼"} {num(Math.abs(mUpsideLive), 1)} % {mUpsideLive >= 0 ? "апсайд" : "даунсайд"} от живой цены</div>
                    )}
                    <div className="corr">
                      {mLivePrice != null && <>живая цена<br /><b>{num(mLivePrice, 2)} {ccy}</b></>}
                      {mFwdPeLive != null && <><br /><span style={{ fontSize: 11 }}>форв. P/E живой {num(mFwdPeLive, 1)}×</span></>}
                    </div>
                  </div>
                )}

                {mScenPrices.length > 0 && (
                  <div className="fm-scen-row">
                    {mScenPrices.map((s) => (
                      <div className={`fm-scen-chip${s.key === "base" ? " fm-scen-base" : ""}`} key={s.key}>
                        <span className="fm-scen-lbl">{s.label}{s.weight != null ? ` · вес ${Math.round(s.weight * 100)} %` : ""}</span>
                        <span className="fm-scen-val">{num(s.price, s.price >= 100 ? 0 : 1)} {ccy}</span>
                      </div>
                    ))}
                  </div>
                )}
                {mScenPrices.length > 0 && (
                  <div className="ff-note" style={{ marginTop: 14 }}>
                    <div className="nh">Как читать сценарии</div>
                    База — не среднее, а наиболее вероятный режим рынка прямо сейчас{mBasePct != null ? ` (вес ${mBasePct} %)` : ""}; бык и медведь — другой набор допущений по цене/ставке/риску, а не симметричные «±%». Если вес медведя и быка не совпадают — это суждение аналитика о том, куда смещён риск.
                  </div>
                )}
              </div>

              <details className="disc" open>
                <summary>
                  <div><div className="dt">Прогноз по годам</div><div className="dd">Прогноз · драйверы · чувствительность · мост</div></div>
                  <span className="tag tag-model" style={{ marginLeft: 8 }}>модель</span>
                  <span className="chev">▾</span>
                </summary>
                <div className="disc-body">
                  {FM_ROWS.length > 0 && (
                    <>
                      <div className="subh">Прогноз {mHorizon[0]}–{mHorizon[mHorizon.length - 1]}</div>
                      <div className="tbl-scroll">
                        <table className="ftbl">
                          <thead><tr><th>Показатель</th>{mHorizon.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                          <tbody>
                            {FM_ROWS.map((r) => {
                              const rowLive = mHasLiveRow(r.key);
                              const rowUnit = r.kind === "money"
                                ? moneyRowUnit(mHorizon.flatMap((y) => [mForecastBase[r.key]?.[y], mLiveAdj?.[r.key]?.[y]]))
                                : null;
                              return (
                                <tr className={r.bold ? "bold" : ""} key={r.key}>
                                  <td style={{ color: r.muted ? "var(--ink-3)" : undefined }}>
                                    {r.l}{rowUnit && <span className="fm-row-unit"> · {rowUnit.u}</span>}
                                    {rowLive && <span className="fm-live-chip" style={{ marginLeft: 6 }}>⚡ живой пересчёт</span>}
                                  </td>
                                  {mHorizon.map((y) => {
                                    const baseV = mForecastBase[r.key]?.[y];
                                    const liveV = mLiveAdj?.[r.key]?.[y];
                                    const showV = liveV != null ? liveV : baseV;
                                    if (showV == null) return <td key={y}><span style={{ color: "var(--ink-3)", fontSize: 11 }}>н.д.</span></td>;
                                    return (
                                      <td key={y}>
                                        <span className="cv">{fmtFmVal(showV, r.kind, rowUnit)}</span>
                                        {meaningfulDiff(liveV, baseV) && <div className="fm-basehint">база {fmtFmVal(baseV, r.kind, rowUnit)}</div>}
                                      </td>
                                    );
                                  })}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <div className="fc-note">Единица указана у каждой строки (масштаб млрд/трлн ₽ зависит от величины — EPS/DPS/BVPS в ₽/акция, ROE/NIM/маржа в %).{mLiveAdj ? " ⚡ живой пересчёт — база скорректирована под текущие значения живых драйверов (Brent/курс/ставка и т.п.), см. «Драйверы модели» ниже; исходный (застывший на дату сборки) уровень — под живым значением." : ""}</div>
                    </>
                  )}

                  {(model.drivers || []).length > 0 && (
                    <>
                      <div className="subh" style={{ marginTop: 22 }}>Драйверы модели</div>
                      <div className="fm-drivers">
                        {model.drivers.map((d, i) => {
                          const kindLabel = { live: "live", assumption: "допущение", macro: "макро" }[d.kind] || d.kind;
                          const kindCls = { live: "fm-kind-live", assumption: "fm-kind-assum", macro: "fm-kind-macro" }[d.kind] || "";
                          return (
                            <div className="fm-drv" key={d.key || i}>
                              <div className="fm-drv-top">
                                <span className="fm-drv-name">{d.name}</span>
                                <span className={`fm-drv-kind ${kindCls}`}>{kindLabel}</span>
                              </div>
                              {d.kind === "live" ? (
                                <div className="fm-drv-live">
                                  <span className="fm-drv-vals">база {num(d.base_value, 2)} → живое <b>{num(d.live_value, 2)}</b></span>
                                  {typeof d.live_shift_pct === "number" && <Delta v={d.live_shift_pct} d={1} />}
                                </div>
                              ) : d.scenario_values ? (
                                <div className="fm-drv-scen">
                                  {["bear", "base", "bull"].map((k) => d.scenario_values[k] != null && (
                                    <span className="fm-scen-mini" key={k}><i>{SCEN_LABEL[k]}</i>{num(d.scenario_values[k], 1)}</span>
                                  ))}
                                </div>
                              ) : (
                                <div className="fm-drv-vals">база {num(d.base_value, 2)}</div>
                              )}
                              {d.kind === "live" && d.live_status && <div className="fm-drv-status">{d.live_status}</div>}
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}

                  {mBridge && Array.isArray(mBridge.steps) && mBridge.steps.length > 0 && (
                    <>
                      {/* Заголовок и «итого» — БЕЗ хардкода метрики: мост EBITDA у oil_gas/retail,
                          но мост ЧИСТОЙ ПРИБЫЛИ у banking (SBER) — bridge.from несёт точное имя. */}
                      <div className="subh" style={{ marginTop: 22 }}>Мост</div>
                      {mBridge.from && <div className="fc-note" style={{ marginTop: 0, marginBottom: 10 }}>{mBridge.from}</div>}
                      <div className="fm-bridge-list">
                        {mBridge.steps.map((s, i) => (
                          <div className="fm-bridge-row" key={i}>
                            <span className="fm-bridge-name">{s.name}</span>
                            <span className={`delta ${s.delta >= 0 ? "up" : "dn"}`}>{s.delta >= 0 ? "▲" : "▼"} {bln(Math.abs(s.delta)).v} {bln(Math.abs(s.delta)).u}</span>
                          </div>
                        ))}
                        {typeof mBridge.delta_total === "number" && (
                          <div className="fm-bridge-row fm-bridge-total">
                            <span className="fm-bridge-name">Итого изменение</span>
                            <span className={`delta ${mBridge.delta_total >= 0 ? "up" : "dn"}`}>{mBridge.delta_total >= 0 ? "▲" : "▼"} {bln(Math.abs(mBridge.delta_total)).v} {bln(Math.abs(mBridge.delta_total)).u}</span>
                          </div>
                        )}
                      </div>
                      {mBridge.note && <div className="fc-note">{mBridge.note}</div>}
                    </>
                  )}

                  {mSensRows.length > 0 && (
                    <>
                      <div className="subh" style={{ marginTop: 22 }}>Чувствительность</div>
                      <div className="tbl-scroll">
                        <table className="ftbl">
                          <thead><tr><th>Драйвер</th><th>Сдвиг</th><th>Δ прибыль</th><th>Δ цена</th></tr></thead>
                          <tbody>
                            {mSensRows.map((s, i) => {
                              const dName = mDriversByKey[s.driver]?.name || s.driver;
                              const npDn = /^[-−]/.test(String(s.net_profit_pct ?? ""));
                              const fpDn = /^[-−]/.test(String(s.fair_price_pct ?? ""));
                              return (
                                <tr key={i}>
                                  <td>{dName}</td>
                                  <td>{s.shift}</td>
                                  <td><span className={`delta ${npDn ? "dn" : "up"}`}>{npDn ? "▼" : "▲"} {s.net_profit_pct}</span></td>
                                  <td><span className={`delta ${fpDn ? "dn" : "up"}`}>{fpDn ? "▼" : "▲"} {s.fair_price_pct}</span></td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {mSensRows.some((s) => s.note) && (
                        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
                          {mSensRows.filter((s) => s.note).map((s, i) => (
                            <div className="fc-note" key={i}><b>{mDriversByKey[s.driver]?.name || s.driver}:</b> {s.note}</div>
                          ))}
                        </div>
                      )}
                    </>
                  )}

                  <div className="subh" style={{ marginTop: 22 }}>История прогнозов (track record)</div>
                  {mTrackRows.length > 0 ? (
                    <div className="tbl-scroll">
                      <table className="ftbl">
                        <thead><tr><th>Период</th><th>Метрика</th><th>Прогноз</th><th>Факт</th><th>Ошибка</th></tr></thead>
                        <tbody>
                          {mTrackRows.map((t, i) => {
                            const tKind = mMetricKind(t.metric);
                            const errDn = typeof t.error_pct === "number" && t.error_pct < 0;
                            return (
                              <tr key={i}>
                                <td>{t.period}</td>
                                <td>{MFM_METRIC_LABEL[t.metric] || t.metric}</td>
                                <td>{fmtFmVal(t.forecast, tKind)}</td>
                                <td>{fmtFmVal(t.actual, tKind)}</td>
                                <td>{typeof t.error_pct === "number" ? <span className={`delta ${errDn ? "dn" : "up"}`}>{errDn ? "▼" : "▲"} {num(Math.abs(t.error_pct), 1)} %</span> : "—"}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="fc-note">{model.track_record_note || "Пилотная модель — история прогноз/факт пока не накоплена, появится после ближайшей отчётности."}</p>
                  )}

                  <p className="foot-note" style={{ marginTop: 18 }}>Прогноз — модель Basis (оценка/суждение), не факт и не рекомендация. Не является ИИР.</p>
                </div>
              </details>

              {mDataFlags.length > 0 && (
                <details className="disc">
                  <summary>
                    <div><div className="dt">Ограничения модели</div><div className="dd">{mDataFlags.length} пункт{mDataFlags.length === 1 ? "" : mDataFlags.length < 5 ? "а" : "ов"} — что не гарантировано, где деградация</div></div>
                    <span className="tag tag-est" style={{ marginLeft: 8 }}>оценка</span>
                    <span className="chev">▾</span>
                  </summary>
                  <div className="disc-body">
                    {mDataFlags.map((f, i) => <div className="fc-warn" key={i}>{f}</div>)}
                  </div>
                </details>
              )}
            </>
          )}

        </div>

        {/* правый рейл — Заметка аналитика. На мобильном (≤1020px) — выезжающая справа
            панель поверх контента (открывается тизером выше), на десктопе — как раньше,
            sticky-сайдбар, всегда открыт (railOpen не влияет на CSS выше брейкпоинта). */}
        {railOpen && <div className="fv-rail-scrim" onClick={() => setRailOpen(false)} />}
        <aside className={`fv-rail${railOpen ? " fv-rail--open" : ""}`}>
          <button type="button" className="fv-rail-x" onClick={() => setRailOpen(false)} aria-label="Закрыть">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>
          </button>
          <div className="eyebrow">Заметка аналитика</div>
          {bfvFair != null && <div className="an-fv"><span className="b">{num(bfvFair, bfvFair >= 100 ? 0 : 1)}<s> {ccy}</s></span>{bfvUpside != null && <span className={`u delta ${bfvUpside >= 0 ? "up" : "dn"}`}>{bfvUpside >= 0 ? "▲" : "▼"} {num(Math.abs(bfvUpside), 0)} %</span>}</div>}
          <div className="an-meta">{bfvFair != null ? "Справедливая цена по методике Basis" : <>Справедливая цена по методике Basis не считается — {bfvWhy || "нет данных"}</>}</div>

          <RunRateBlock rr={runRate} />

          {railSections.length > 0 && <>
            <div className="an-sec">Разбор по разделам</div>
            {railSections.map((s, i) => (
              <details className="an-note" key={i}>
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
