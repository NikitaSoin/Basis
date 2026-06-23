/* Вкладка «Финансы и оценка» — гибрид-дизайн (порт docs/Finance.zip → Finance.html).
   Ответ-первым: Разбор отчёта → Справедливая стоимость («поле оценок» + методы с раскрытием
   выкладки) → Ключевые показатели и мультипликаторы с контекстом к медиане сектора →
   раскрытие «Прибыль и рентабельность» (графики + таблицы). Всё из financials.json для
   ЛЮБОЙ компании; методики (коридор, методы оценки) НЕ пересчитываются — берутся из
   valuation.fair_value_range / valuation.methods[].explain (заповедник). Служебные поля
   (data_flags / *_note технические / CFO=null) в UI НЕ выводятся; честные оговорки
   (caveats методов, methods_divergence_note) — выводятся. */
import React, { useState } from "react";
import "../styles/finance.css";

/* ── helpers ─────────────────────────────────────────────── */
const num = (v, d = 1) =>
  v == null || isNaN(v) ? "—" : Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
// млн ₽ → строка в млрд/трлн (без знака валюты), + единица отдельно
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
const Delta = ({ v, suffix = "%", d = 1, pp = false }) =>
  v == null || isNaN(v) ? null : (
    <span className={`delta ${v >= 0 ? "up" : "dn"}`}>
      {v >= 0 ? "▲" : "▼"} {num(Math.abs(v), d)} {pp ? "пп" : suffix}
    </span>
  );

const METHOD_LABEL = {
  DCF: "DCF", dcf: "DCF",
  historical_pe: "Истор. P/E", historical_pb: "Истор. P/B",
  relative_peers: "Сектор (EV/EBITDA)", relative: "Относительная",
  CAPM: "CAPM 12 мес.", capm: "CAPM 12 мес.",
  dividend: "Дивидендный", ddm: "Дивидендный",
  NAV: "NAV", nav: "NAV", SOTP: "SOTP", sotp: "SOTP",
  pbv_roe: "P/BV × ROE", "P/BV×ROE": "P/BV × ROE",
};
const methodName = (m) => METHOD_LABEL[m] || METHOD_LABEL[String(m || "").toLowerCase()] || String(m || "Метод");

/* мини-спарклайн из ряда */
function Spark({ series }) {
  const xs = (series || []).filter((x) => x != null);
  if (xs.length < 2) return null;
  const mx = Math.max(...xs.map(Math.abs)) || 1;
  return (
    <div className="spark">
      {xs.map((x, i) => (
        <i key={i} className={i === xs.length - 1 ? "last" : ""} style={{ height: `${clamp((Math.abs(x) / mx) * 100, 6, 100)}%` }} />
      ))}
    </div>
  );
}

/* карточка мультипликатора с позицией к медиане сектора */
function MCard({ label, value, median, medLabel, lowerBetter, fmtV }) {
  const has = typeof value === "number" && !isNaN(value);
  const hasMed = typeof median === "number" && !isNaN(median) && median !== 0;
  let pos = 50, tone = "var(--ink-3)", ctx = "норма не задана";
  if (has && hasMed) {
    pos = clamp(50 * (value / median), 6, 94);
    const cheaper = value < median; // дешевле/ниже медианы
    const good = lowerBetter ? cheaper : !cheaper;
    tone = Math.abs(value / median - 1) < 0.06 ? "var(--ink-3)" : good ? "var(--pos)" : "var(--neg)";
    if (lowerBetter) ctx = cheaper ? "дешевле сектора" : "дороже сектора";
    else ctx = cheaper ? "ниже сектора" : "выше сектора";
  }
  return (
    <div className="mc">
      <div className="mc-top">
        <span className="mc-l">{label}</span>
        <span className="mc-v">{has ? fmtV(value) : "—"}</span>
      </div>
      {hasMed ? (
        <>
          <div className="mc-track">
            <span className="mc-med" style={{ left: "50%" }} />
            {has && <span className="mc-dot" style={{ left: `${pos}%`, background: tone }} />}
          </div>
          <div className="mc-ctx">
            <span style={{ color: tone }}>{ctx}</span>
            <span className="med">{medLabel || "медиана"} {fmtV(median)}</span>
          </div>
        </>
      ) : (
        <div className="mc-ctx" style={{ marginTop: 9 }}><span className="med">медиана сектора недоступна</span></div>
      )}
    </div>
  );
}

export default function FinanceTab({ fin, company, price, sectorMult }) {
  const [tab, setTab] = useState("pnl");
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

  const livePrice = typeof price === "number" ? price : (fvr.current_price ?? meta.last_price ?? null);
  const ndeArr = (bs.ratios && bs.ratios.net_debt_ebitda) || mt.net_debt_ebitda;
  const nde = lastN(ndeArr);

  /* ── 1. Разбор отчёта (verdict) ── */
  const revYoy = yoy(is.revenue), npYoy = yoy(is.net_profit), ebYoy = yoy(is.ebitda);
  const ebMargin = lastN(is.margins && is.margins.ebitda_margin);
  const rows = [];
  if (lastN(is.revenue) != null) {
    const b = bln(lastN(is.revenue));
    rows.push({ ic: "ok", t: <>Выручка {revYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(revYoy), 1)} %</b> до {b.v} {b.u}</> });
  }
  if (lastN(is.ebitda) != null) {
    const b = bln(lastN(is.ebitda));
    rows.push({ ic: "ok", t: <>EBITDA {ebYoy >= 0 ? "выросла" : "снизилась"} на <b>{num(Math.abs(ebYoy), 1)} %</b> до {b.v} {b.u}{ebMargin != null && <>; рентабельность <b>{num(ebMargin, 1)} %</b></>}</> });
  }
  if (lastN(is.net_profit) != null) {
    const b = bln(lastN(is.net_profit));
    rows.push({ ic: npYoy >= 0 ? "ok" : "warn", t: <>Чистая прибыль <b>{npYoy >= 0 ? "+" : "−"}{num(Math.abs(npYoy), 1)} %</b> до {b.v} {b.u}</> });
  }
  if (nde != null) {
    const tone = nde < 1.5 ? "ok" : nde <= 3 ? "warn" : "no";
    const word = nde < 1.5 ? "низкая" : nde <= 3 ? "умеренная" : "повышенная";
    const ndAbs = lastN(bs.net_debt);
    rows.push({ ic: tone, t: <>{ndAbs != null && <>Чистый долг {bln(ndAbs).v} {bln(ndAbs).u}, </>}<b>ND/EBITDA {num(nde, 2)}×</b> — {word} долговая нагрузка</> });
  }
  const verdictHead = (npYoy != null && revYoy != null)
    ? `Чистая прибыль ${npYoy >= 0 ? "выросла" : "снизилась"} на ${num(Math.abs(npYoy), 0)} % при ${revYoy >= 0 ? "росте" : "снижении"} выручки на ${num(Math.abs(revYoy), 1)} %`
    : `Итоги ${lastYr} · ${std}`;

  /* ── 2. Справедливая стоимость ── */
  const base = typeof fvr.base === "number" ? fvr.base : null;
  const cons = typeof fvr.conservative === "number" ? fvr.conservative : null;
  const upside = base && livePrice ? (base / livePrice - 1) * 100 : (typeof fvr.upside_downside_pct === "number" ? fvr.upside_downside_pct : null);
  const methods = (val.methods || []).filter((m) => typeof m.fair_value_per_share === "number" && m.fair_value_per_share > 0 && !["not_applicable", "insufficient_data"].includes(m.status));
  const mvals = methods.map((m) => m.fair_value_per_share);
  const domVals = [...mvals, cons, base, livePrice].filter((x) => typeof x === "number" && x > 0);
  const dmin = domVals.length ? Math.min(...domVals) * 0.92 : 0;
  const dmax = domVals.length ? Math.max(...domVals) * 1.06 : 1;
  const span = dmax - dmin || 1;
  const posOf = (v) => clamp(((v - dmin) / span) * 100, 1, 99);
  const isAnchor = (m) => m.horizon && m.horizon !== "intrinsic_now" ? true : base ? (m.fair_value_per_share < base * 0.6 || m.fair_value_per_share > base * 1.5) : false;
  const sortedM = [...methods].sort((a, b2) => a.fair_value_per_share - b2.fair_value_per_share);
  const toneVsPrice = (v) => (livePrice ? (v > livePrice * 1.05 ? "var(--pos)" : v < livePrice * 0.95 ? "var(--neg)" : "var(--ink-3)") : "var(--ink)");
  const divergenceNote = val.methods_divergence_note;

  /* ── 3. Ключевые показатели ── */
  const kfi = [
    { l: "Выручка", a: is.revenue, d: revYoy },
    { l: "EBITDA", a: is.ebitda, d: ebYoy },
    { l: "Чистая прибыль", a: is.net_profit, d: npYoy },
    { l: "FCF", a: cf.fcf, d: yoy(cf.fcf) },
    { l: "Маржа EBITDA", pctv: ebMargin, d: (ebMargin != null && prevN(is.margins && is.margins.ebitda_margin) != null) ? ebMargin - prevN(is.margins.ebitda_margin) : null, isPP: true },
    { l: "Чистый долг", a: bs.net_debt, d: yoy(bs.net_debt) },
  ];
  const sm = sectorMult && company && company.sector && sectorMult[company.sector] && sectorMult[company.sector].n >= 4 ? sectorMult[company.sector] : null;
  const mcards = [
    { label: "P/E", value: cur.pe, median: sm ? sm.pe : (hist.pe_5y_median ?? hist.pe_5y_avg), lowerBetter: true, fmtV: (x) => num(x, 1) + "×" },
    { label: "P/B", value: cur.pb, median: sm ? sm.pb : (hist.pb_5y_median ?? hist.pb_5y_avg), lowerBetter: true, fmtV: (x) => num(x, 2) + "×" },
    { label: "EV/EBITDA", value: cur.ev_ebitda, median: sm ? sm.ev_ebitda : (hist.ev_ebitda_5y_median ?? hist.ev_ebitda_5y_avg), lowerBetter: true, fmtV: (x) => num(x, 1) + "×" },
    { label: "ND/EBITDA", value: nde, median: sm ? sm.nd_ebitda : null, lowerBetter: true, fmtV: (x) => num(x, 2) + "×" },
    { label: "ROE", value: lastN(ret.roe), median: sm ? sm.roe : null, lowerBetter: false, fmtV: (x) => num(x, 1) + " %" },
    { label: "ROIC", value: lastN(ret.roic), median: null, lowerBetter: false, fmtV: (x) => num(x, 1) + " %" },
  ];
  const medLabel = sm ? "сектор" : "норма 5л";

  /* ── 4. Таблицы по годам (последние 5) ── */
  const yslice = years.slice(-5);
  const sl = (a) => (Array.isArray(a) ? a.slice(-5) : []);
  const TABLES = {
    pnl: [
      { l: "Выручка", a: is.revenue, cls: "bold" },
      { l: "Валовая прибыль", a: is.gross_profit },
      { l: "EBITDA", a: is.ebitda, cls: "bold" },
      { l: "EBIT", a: is.operating_profit },
      { l: "Чистая прибыль", a: is.net_profit, cls: "bold" },
      { l: "ЧП норм.", a: adj.net_profit_adj, cls: "accent" },
      { l: "Маржа EBITDA", a: is.margins && is.margins.ebitda_margin, suf: " %", d: 1 },
      { l: "Рент. (ROS)", a: ret.ros || (is.margins && is.margins.ros), suf: " %", d: 1 },
    ],
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
      { l: "P/E", a: mult.pe, suf: "", d: 2 },
      { l: "P/B", a: mult.pb, suf: "", d: 2 },
      { l: "EV/EBITDA", a: mult.ev_ebitda, suf: "", d: 2 },
      { l: "ROE", a: ret.roe, suf: " %", d: 1, cls: "bold" },
      { l: "ROIC", a: ret.roic, suf: " %", d: 1 },
    ],
  };
  const isRatio = (t) => t === "mult";
  const cellFmt = (r, t) => (v) => {
    if (v == null || isNaN(v)) return "—";
    if (r.suf != null) return num(v, r.d ?? 2) + r.suf;
    if (isRatio(t)) return num(v, 2);
    const b = bln(v); return b.v;
  };
  const hasTable = (k) => TABLES[k].some((r) => sl(r.a).some((x) => x != null));
  const tabsAvail = ["pnl", "bs", "cf", "mult"].filter(hasTable);
  const TLABEL = { pnl: "P&L", bs: "Баланс", cf: "ОДДС", mult: "Мультипликаторы" };
  const unitNote = isRatio(tab) ? "×, %" : "млрд ₽";

  /* динамика — мини-карточки */
  const dyn = [
    { l: "Выручка", a: is.revenue, money: true },
    { l: "Чистая прибыль", a: is.net_profit, money: true },
    { l: "Маржа EBITDA", a: is.margins && is.margins.ebitda_margin, money: false, suf: " %" },
  ];

  return (
    <div className="fin-hybrid">
      {/* 1. Разбор отчёта */}
      {rows.length > 0 && (
        <div className="card">
          <h3>Разбор отчёта <span className="tag tag-fact">факт</span><span className="hmeta">{lastYr} · {std}</span></h3>
          <div className="verdict" style={{ marginTop: 14 }}>
            <div className="vh">{verdictHead}</div>
            {rows.map((r, i) => (
              <div className="vrow" key={i}>
                <span className={`ic ${r.ic}`}>{r.ic === "ok" ? "✓" : r.ic === "warn" ? "!" : "✕"}</span>
                <span>{r.t}</span>
              </div>
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
              <div>
                <div className="big">{num(base, base >= 1000 ? 0 : base >= 100 ? 0 : 1)}<s> ₽</s></div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>база · модельная цена</div>
              </div>
              {upside != null && <div className={`ud delta ${upside >= 0 ? "up" : "dn"}`}>{upside >= 0 ? "▲" : "▼"} {num(Math.abs(upside), 1)} % {upside >= 0 ? "апсайд" : "даунсайд"}</div>}
              <div className="corr">
                коридор<br /><b>{cons != null ? `${num(cons, 0)} – ${num(base, 0)} ₽` : `${num(base, 0)} ₽`}</b>
                {livePrice && <><br /><span style={{ fontSize: 11 }}>тек. {num(livePrice, 2)} ₽</span></>}
              </div>
            </div>
          )}

          {/* football field */}
          {sortedM.length > 0 && (
            <>
              <div className="ff">
                {sortedM.map((m, i) => {
                  const v = m.fair_value_per_share;
                  const anchor = isAnchor(m);
                  const tone = toneVsPrice(v);
                  const dv = livePrice ? (v / livePrice - 1) * 100 : null;
                  return (
                    <div className="ff-row" key={i}>
                      <span className="ff-nm"><span className={anchor ? "anch" : "clust"} />{methodName(m.method)}</span>
                      <span className="ff-track">
                        {cons != null && base != null && <span className="ff-band" style={{ left: `${posOf(cons)}%`, width: `${posOf(base) - posOf(cons)}%` }} />}
                        {livePrice && <span className="ff-curl" style={{ left: `${posOf(livePrice)}%` }} />}
                        <span className="ff-dot" style={{ left: `${posOf(v)}%`, background: tone }} />
                      </span>
                      <span className="ff-val">
                        <span className="pv">{num(v, v >= 100 ? 0 : 1)} ₽</span>
                        {dv != null && <span className={`pd delta ${dv >= 0 ? "up" : "dn"}`}>{dv >= 0 ? "+" : "−"}{num(Math.abs(dv), 0)} %</span>}
                      </span>
                    </div>
                  );
                })}
                <div className="ff-axis"><span>{num(dmin, 0)} ₽</span><span>{num(dmax, 0)} ₽</span></div>
              </div>
              <div className="ff-legend">
                <span><span className="ff-nm"><span className="clust" /></span> центральный кластер</span>
                <span><span className="ff-nm"><span className="anch" /></span> внешний якорь</span>
                <span><span style={{ width: 14, height: 0, borderTop: "2px dashed var(--accent)", display: "inline-block" }} /> коридор</span>
                {livePrice && <span><span style={{ width: 2, height: 12, background: "var(--ink-3)", display: "inline-block" }} /> текущая цена</span>}
              </div>
            </>
          )}

          {divergenceNote && (
            <div className="ff-note">
              <div className="nh">Честно · почему методы расходятся</div>
              {divergenceNote}
            </div>
          )}

          {/* методы — раскрытие выкладки */}
          {sortedM.length > 0 && (
            <>
              <div className="subh" style={{ marginTop: 20 }}>Выводы по методам · раскройте любой</div>
              <div className="methods">
                {sortedM.map((m, i) => {
                  const v = m.fair_value_per_share;
                  const anchor = isAnchor(m);
                  const dv = livePrice ? (v / livePrice - 1) * 100 : null;
                  const ex = m.explain || {};
                  const inputs = ex.inputs && typeof ex.inputs === "object" ? Object.entries(ex.inputs) : [];
                  const ka = (!inputs.length && m.key_assumptions && typeof m.key_assumptions === "object") ? Object.entries(m.key_assumptions) : [];
                  const steps = Array.isArray(ex.steps) ? ex.steps : [];
                  const caveats = Array.isArray(ex.caveats) ? ex.caveats : [];
                  return (
                    <details className="m-acc" key={i}>
                      <summary>
                        <span className="mn"><span className={anchor ? "anch" : "clust"} />{methodName(m.method)}{m.horizon && m.horizon !== "intrinsic_now" && <s>горизонт {m.horizon}</s>}</span>
                        <span className="mv" style={{ color: toneVsPrice(v) }}>{num(v, v >= 100 ? 1 : 2)} ₽</span>
                        {dv != null ? <span className={`md delta ${dv >= 0 ? "up" : "dn"}`}>{dv >= 0 ? "+" : "−"}{num(Math.abs(dv), 0)} %</span> : <span className="md" />}
                        <span className="chev">▾</span>
                      </summary>
                      <div className="m-body">
                        {(inputs.length > 0 || ka.length > 0) && <>
                          <div className="subh">Входные данные</div>
                          <div className="fc-kv">
                            {(inputs.length ? inputs : ka).map(([k, vv], j) => (
                              <React.Fragment key={j}><span className="k">{k}</span><span className="v">{String(vv)}</span></React.Fragment>
                            ))}
                          </div>
                        </>}
                        {steps.length > 0 && <>
                          <div className="subh">Решение по шагам</div>
                          <ol className="fc-steps">{steps.map((s, j) => <li key={j}>{s}</li>)}</ol>
                        </>}
                        {caveats.length > 0 && <>
                          <div className="subh">Оговорки</div>
                          {caveats.map((c, j) => <div className="fc-warn" key={j}>{c}</div>)}
                        </>}
                        {!inputs.length && !ka.length && !steps.length && !caveats.length && (
                          <div className="fc-note">Выкладка метода не детализирована.</div>
                        )}
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
        <h3>Ключевые показатели и мультипликаторы <span className="tag tag-fact">факт</span><span className="hmeta">{livePrice ? `цена ${num(livePrice, 2)} ₽ · ` : ""}позиция к {sm ? "медиане сектора" : "своей 5-летней норме"}</span></h3>
        <p className="sub">Масштаб бизнеса — абсолютные показатели за {lastYr} ({std})</p>
        <div className="kfi">
          {kfi.map((k, i) => {
            const b = k.pctv != null ? { v: num(k.pctv, 1), u: "%" } : bln(lastN(k.a));
            return (
              <div className="kf" key={i}>
                <span className="kf-l">{k.l}</span>
                <span className="kf-v">{b.v}<s> {b.u}</s></span>
                <span className="kf-d">{k.d != null && <Delta v={k.d} pp={k.isPP} />}</span>
              </div>
            );
          })}
        </div>
        <p className="sub" style={{ marginTop: 16 }}>Мультипликаторы — не просто число, а позиция относительно {sm ? "среднего по сектору" : "собственной 5-летней нормы"}</p>
        <div className="mcards">
          {mcards.map((m, i) => <MCard key={i} {...m} medLabel={medLabel} />)}
        </div>
      </div>

      {/* 4. Прибыль и рентабельность по годам */}
      {tabsAvail.length > 0 && (
        <details className="disc" open>
          <summary>
            <div><div className="dt">Прибыль и рентабельность по годам</div><div className="dd">Динамика · отчётность за {yslice.length} лет</div></div>
            <span className="tag tag-fact" style={{ marginLeft: 8 }}>факт</span>
            <span className="chev">▾</span>
          </summary>
          <div className="disc-body">
            <div className="subh">Динамика {yslice[0]}–{lastYr}</div>
            <div className="fc-dyn">
              {dyn.filter((d) => sl(d.a).some((x) => x != null)).map((d, i) => {
                const b = d.money ? bln(lastN(d.a)) : { v: num(lastN(d.a), 1), u: d.suf ? "%" : "" };
                const yy = yoy(d.a);
                return (
                  <div className="d" key={i}>
                    <div className="dl">{d.l}</div>
                    <div className="dv">{b.v}<s> {b.u}</s> {yy != null && <Delta v={yy} pp={false} />}</div>
                    <Spark series={sl(d.a)} />
                  </div>
                );
              })}
            </div>

            <div className="subh">Отчётность и мультипликаторы</div>
            <div className="miniseg">
              {tabsAvail.map((k) => (
                <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{TLABEL[k]}</button>
              ))}
            </div>
            <div className="tbl-scroll">
              <table className="ftbl">
                <thead><tr><th>{unitNote}</th>{yslice.map((y) => <th key={y}>{y}</th>)}</tr></thead>
                <tbody>
                  {TABLES[tabsAvail.includes(tab) ? tab : tabsAvail[0]].map((r, i) => {
                    const vals = sl(r.a);
                    if (!vals.some((x) => x != null)) return null;
                    const f = cellFmt(r, tabsAvail.includes(tab) ? tab : tabsAvail[0]);
                    return (
                      <tr className={r.cls || ""} key={i}>
                        <td>{r.l}</td>
                        {yslice.map((y, j) => <td key={y}>{f(vals[j])}</td>)}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="foot-note">Числа карточки — из единого источника financials.json ({std}). Для циклических компаний P/E на отдельном годе менее надёжен, чем EV/EBITDA и P/B.</div>
          </div>
        </details>
      )}
    </div>
  );
}
