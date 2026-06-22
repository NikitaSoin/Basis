/* Экран «Рынок» (Direction A) на живых данных. Порт прототипа docs/Market.zip:
   пульс (индексы/ширина рынка/драйверы) + вкладки классов (Акции/Облигации/Фьючерсы/
   Фонды/Валюта-металлы/Опционы). Данные — наши эндпоинты (MOEX/Тинькофф), а не mock:
   /screener/scored (акции: цена, капитализация, апсайд к справедливой, BASIS, уверенность),
   /quotes/realtime (дневная дельта + ширина), /market/indices, /market/drivers,
   /bonds, /futures, /funds, /spot, /market/instruments/sparklines (мини-графики).
   Эпистемика: котировки = факт; тон рынка и трактовка драйверов = оценка/суждение Basis. */
import React, { useState, useEffect, useMemo } from "react";
import "../styles/market.css";

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";
const NB = " ";

// ── форматтеры ──
function grp(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }
function num(v, d = 2) {
  if (v == null || isNaN(v)) return "—";
  const s = Number(v).toFixed(d).replace(".", ",");
  const [i, f] = s.split(",");
  return grp(i) + (f ? "," + f : "");
}
function money(rub) {
  if (rub == null || isNaN(rub)) return "—";
  const mlrd = rub / 1e9;
  if (mlrd >= 1000) return num(mlrd / 1000, 2) + NB + "трлн" + NB + "₽";
  if (mlrd >= 1) return num(mlrd, 1) + NB + "млрд" + NB + "₽";
  return num(rub / 1e6, 0) + NB + "млн" + NB + "₽";
}

// fair-value upside (%) → зелёный (выше) → оранжевый (~0) → красный (ниже)
function fvColor(fv) {
  const t = Math.max(-1, Math.min(1, fv / 25));
  if (t >= 0) return `hsl(${(40 + 108 * t).toFixed(0)} ${(80 - 25 * t).toFixed(0)}% ${(48 - 8 * t).toFixed(0)}%)`;
  const k = -t, h = ((40 - 48 * k) % 360 + 360) % 360;
  return `hsl(${h.toFixed(0)} ${(80 - 18 * k).toFixed(0)}% ${(48 + 4 * k).toFixed(0)}%)`;
}
// дневное изменение → диверг. heat-цвет
function heatColor(chg) {
  const x = Math.max(-3, Math.min(3, chg || 0)) / 3;
  if (Math.abs(x) < 0.05) return "hsl(42 6% 62%)";
  if (x > 0) { const k = x; return `hsl(148 ${(34 + 44 * k).toFixed(0)}% ${(45 - 7 * k).toFixed(0)}%)`; }
  const k = -x; return `hsl(352 ${(36 + 42 * k).toFixed(0)}% ${(53 - 7 * k).toFixed(0)}%)`;
}

// секторные цвета: явные для основных + стабильный хэш-fallback
const SECTOR_COLORS = {
  "Нефть и газ": "#C2792E", "Финансы": "#1F8A5B", "Банки": "#1F8A5B",
  "Металлургия": "#7C6FE0", "Металлургия и добыча": "#7C6FE0", "Добыча": "#7C6FE0",
  "IT": "#2A6FDB", "Технологии": "#2A6FDB", "IT-сектор": "#2A6FDB",
  "Потребительский сектор": "#C44B9E", "Ритейл": "#C44B9E", "Потребительские товары": "#C44B9E",
  "Телеком": "#3FA7C4", "Телекоммуникации": "#3FA7C4",
  "Электроэнергетика": "#D9A441", "Энергетика": "#D9A441",
  "Химия": "#5B9E4B", "Химия и нефтехимия": "#5B9E4B",
  "Девелопмент": "#B2643A", "Строительство": "#B2643A",
  "Транспорт": "#6B7A8F", "Транспорт и логистика": "#6B7A8F", "Машиностроение": "#8A6FB0",
  "Здравоохранение": "#4FA98C", "Сельское хозяйство": "#9BAA3E", "Прочее": "#857D6F",
};
function secColor(name) {
  if (SECTOR_COLORS[name]) return SECTOR_COLORS[name];
  let h = 0; for (let i = 0; i < (name || "").length; i++) h = (h * 31 + name.charCodeAt(i)) % 360;
  return `hsl(${h} 42% 48%)`;
}

// Фиксированный порядок секторов (как на остальной платформе): нефть и газ → финансы → …
const SECTOR_ORDER = ["Нефть и газ", "Финансы", "Металлургия", "IT-сектор", "Потребительский сектор", "Телеком", "Электроэнергетика", "Химия", "Девелопмент", "Транспорт и логистика", "Здравоохранение", "Машиностроение"];
const sectorRank = (s) => { const i = SECTOR_ORDER.indexOf(s); return i === -1 ? 999 : i; };
function orderSectors(names) {
  return [...names].sort((a, b) => { const ra = sectorRank(a), rb = sectorRank(b); return ra !== rb ? ra - rb : a.localeCompare(b, "ru"); });
}

// ── мелкие компоненты ──
function Delta({ pct, abs }) {
  const cls = pct > 0 ? "up" : pct < 0 ? "dn" : "fl";
  const g = pct > 0 ? "▲" : pct < 0 ? "▼" : "▬";
  if (pct == null) return <span className="mk-delta fl"><span className="mk-delta-pct">—</span></span>;
  return (
    <span className={"mk-delta " + cls}>
      {abs != null && <span className="mk-delta-abs">{pct > 0 ? "+" : "−"}{num(Math.abs(abs), 2)}{NB}₽</span>}
      <span className="mk-delta-pct">{g} {num(Math.abs(pct), 2)}{NB}%</span>
    </span>
  );
}
function Mono({ t, color, sm }) {
  return <span className={"mk-mono" + (sm ? " sm" : "")} style={{ background: (color || "var(--accent)") + "22", color: color || "var(--accent)" }}>{(t || "").slice(0, 2)}</span>;
}
function ConfDots({ level }) {
  const n = level === "high" ? 3 : level === "medium" ? 2 : 1;
  return <span className="mk-conf" title={"Уверенность Basis: " + (level === "high" ? "высокая" : level === "medium" ? "средняя" : "низкая")}>{[0, 1, 2].map(i => <i key={i} className={i < n ? "on" : ""} />)}</span>;
}
function Spark({ data, up, w = 116, h = 30 }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  const min = Math.min(...data), max = Math.max(...data), rng = (max - min) || 1;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, h - 3 - ((v - min) / rng) * (h - 6)]);
  const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const id = "mks" + Math.round((data[0] || 0) * 100) + "_" + data.length;
  return (
    <svg width={w} height={h} className={"mk-spark " + (up ? "up" : "dn")} style={{ color: up ? "var(--pos)" : "var(--neg)" }} aria-hidden="true">
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="currentColor" stopOpacity=".18" /><stop offset="1" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>
      <path d={d + ` L${w} ${h} L0 ${h} Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function ConfFromRow(row) {
  if (row.low_confidence) return "low";
  return row.data_quality === "high" ? "high" : row.data_quality === "low" ? "low" : "medium";
}

// ══════════════════ ПУЛЬС ══════════════════
function ToneRow({ adv, dec, total }) {
  const ratio = total ? adv / total : 0;
  const toneVal = Math.round(ratio * 100);
  const label = ratio >= 0.62 ? "Аппетит к риску" : ratio >= 0.48 ? "Осторожный аппетит" : ratio >= 0.32 ? "Осторожно" : "Уход от риска";
  const c = fvColor((toneVal - 50) * 0.4);
  return (
    <div className="mk-tone-row">
      <span className="mk-tone-dot" style={{ background: c }} />
      <span>Тон рынка: <b style={{ color: c }}>{label}</b> <span className="mk-epi">· оценка Basis</span></span>
    </div>
  );
}
function Pulse({ index, drivers, adv, dec, flat, total }) {
  return (
    <div className="mk-pulse">
      <div>
        <div className="mk-eyebrow">{index ? index.name : "Индекс МосБиржи"}</div>
        {index ? (
          <>
            <div className="mk-idx-row">
              <span className="mk-idx-level">{num(index.level, 1)}</span>
              <span className={"mk-delta " + (index.change_pct >= 0 ? "up" : "dn")}>
                <span className="mk-delta-pct">{index.change_pct >= 0 ? "▲" : "▼"} {num(Math.abs(index.change_pct || 0), 2)}{NB}%</span>
              </span>
            </div>
            <Spark data={index.spark} up={index.change_pct >= 0} w={150} h={36} />
          </>
        ) : <div className="mk-epi" style={{ marginTop: 8 }}>загрузка…</div>}
      </div>

      <div>
        <div className="mk-eyebrow">Ширина рынка</div>
        <div className="mk-breadth-bar">
          <span className="seg up" style={{ flexGrow: adv || 0.001 }} />
          <span className="seg fl" style={{ flexGrow: flat || 0.2 }} />
          <span className="seg dn" style={{ flexGrow: dec || 0.001 }} />
        </div>
        <div className="mk-breadth-legend">
          <span className="up"><b>{adv}</b> растут</span>
          <span className="fl"><b>{flat}</b> ровно</span>
          <span className="dn"><b>{dec}</b> падают</span>
        </div>
        <ToneRow adv={adv} dec={dec} total={total} />
      </div>

      <div>
        <div className="mk-eyebrow">Что движет рынком сегодня <span className="mk-epi">· суждение Basis</span></div>
        <div className="mk-drivers">
          {(drivers || []).map(d => (
            <div key={d.name} className="mk-driver">
              <div className="mk-driver-n">{d.name}</div>
              <div className="mk-driver-v">{d.value} <span className={"mk-d " + (d.dir > 0 ? "up" : d.dir < 0 ? "dn" : "fl")}>{d.dir > 0 ? "▲" : d.dir < 0 ? "▼" : "▬"}</span></div>
              <div className="mk-driver-e">{d.effect}</div>
            </div>
          ))}
          {(!drivers || !drivers.length) && <div className="mk-epi">нет данных по драйверам</div>}
        </div>
      </div>
    </div>
  );
}

// ══════════════════ АКЦИИ ══════════════════
function SectorNav({ stocks, sector, onSelect }) {
  const stats = useMemo(() => {
    const by = {};
    stocks.forEach(s => { (by[s.sec] = by[s.sec] || []).push(s); });
    return orderSectors(Object.keys(by)).map(g => {
      const items = by[g], withChg = items.filter(x => x.chg != null);
      const avg = withChg.length ? withChg.reduce((a, x) => a + x.chg, 0) / withChg.length : null;
      return { g, n: items.length, avg };
    });
  }, [stocks]);
  const withChg = stocks.filter(x => x.chg != null);
  const allAvg = withChg.length ? withChg.reduce((a, x) => a + x.chg, 0) / withChg.length : null;
  const chgCls = v => v == null ? "fl" : v > 0 ? "up" : v < 0 ? "dn" : "fl";
  return (
    <div className="mk-secnav">
      <button className={"mk-secn" + (sector === "Все" ? " on" : "")} onClick={() => onSelect("Все")}>
        <span className="mk-secn-top"><span className="mk-secn-alldot" />Все секторы</span>
        <span className="mk-secn-bot"><span className="mk-secn-n">{stocks.length} бумаг</span><span className={"mk-secn-chg " + chgCls(allAvg)}>{allAvg == null ? "—" : (allAvg > 0 ? "+" : "") + num(allAvg, 2) + "%"}</span></span>
      </button>
      {stats.map(s => (
        <button key={s.g} className={"mk-secn" + (sector === s.g ? " on" : "")} onClick={() => onSelect(s.g)} style={{ "--sc": secColor(s.g) }}>
          <span className="mk-secn-top"><span className="mk-secn-dot" style={{ background: secColor(s.g) }} />{s.g}</span>
          <span className="mk-secn-bot"><span className="mk-secn-n">{s.n} бум.</span><span className={"mk-secn-chg " + chgCls(s.avg)}>{s.avg == null ? "—" : (s.avg > 0 ? "+" : "") + num(s.avg, 2) + "%"}</span></span>
        </button>
      ))}
    </div>
  );
}

function Heatmap({ stocks, onOpen }) {
  const by = {};
  stocks.forEach(s => { (by[s.sec] = by[s.sec] || []).push(s); });
  const order = orderSectors(Object.keys(by));
  return (
    <div className="mk-heat">
      <div className="mk-heat-head">
        <span className="mk-heat-title">Карта рынка</span>
        <div className="mk-heat-legend"><span>Падение</span><span className="mk-heat-scale" /><span>Рост</span></div>
      </div>
      {order.map(g => {
        const items = [...by[g]].sort((a, b) => (b.mcap || 0) - (a.mcap || 0));
        const withChg = items.filter(x => x.chg != null);
        const avg = withChg.length ? withChg.reduce((s, x) => s + x.chg, 0) / withChg.length : null;
        const cap = items.reduce((s, x) => s + (x.mcap || 0), 0);
        return (
          <div key={g} className="mk-heat-band">
            <div className="mk-heat-band-h">
              <span className="mk-heat-band-dot" style={{ background: secColor(g) }} />
              <span className="mk-heat-band-n">{g}</span>
              <span className={"mk-heat-band-avg " + (avg == null ? "fl" : avg > 0 ? "up" : avg < 0 ? "dn" : "fl")}>{avg == null ? "" : (avg > 0 ? "+" : "") + num(avg, 2) + "%"}</span>
              <span className="mk-heat-band-cap">{money(cap)}</span>
            </div>
            <div className="mk-heat-tiles">
              {items.map(s => {
                const big = (s.mcap || 0) / 1e9 >= 1400;
                return (
                  <button key={s.t} className={"mk-tile" + (big ? " big" : "")} onClick={() => onOpen(s)}
                    style={{ flexGrow: Math.max(1, (s.mcap || 0) / 1e9), flexBasis: Math.max(54, (s.mcap || 0) / 1e9 / 22) + "px", background: heatColor(s.chg) }}
                    title={`${s.n} · ${s.chg == null ? "—" : (s.chg > 0 ? "+" : "") + num(s.chg, 2) + "%"}`}>
                    <span className="mk-tile-t">{s.t}</span>
                    <span className="mk-tile-c">{s.chg == null ? "—" : (s.chg > 0 ? "+" : "") + num(s.chg, 1) + "%"}</span>
                    {big && <span className="mk-tile-n">{s.n}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Movers({ stocks, onOpen, Logo }) {
  const sorted = stocks.filter(s => s.chg != null).sort((a, b) => b.chg - a.chg);
  const gain = sorted.slice(0, 5), lose = [...sorted].reverse().slice(0, 5);
  const Row = ({ s }) => (
    <button className="mk-mv" onClick={() => onOpen(s)}>
      {Logo ? <Logo ticker={s.t} name={s.n} size={30} /> : <Mono t={s.t} color={secColor(s.sec)} sm />}
      <span className="mk-mv-id"><b>{s.n}</b><span className="mk-mv-tk">{s.t}</span></span>
      <span className="mk-mv-px">{num(s.price, 2)}<span className="mk-cur"> ₽</span></span>
      <span className={"mk-mv-chg " + (s.chg > 0 ? "up" : s.chg < 0 ? "dn" : "fl")}>{s.chg > 0 ? "▲" : s.chg < 0 ? "▼" : "▬"} {num(Math.abs(s.chg), 2)}%</span>
    </button>
  );
  return (
    <div className="mk-movers">
      <div className="mk-mv-col"><div className="mk-eyebrow up-e">↑ Лидеры роста</div>{gain.map(s => <Row key={s.t} s={s} />)}</div>
      <div className="mk-mv-col"><div className="mk-eyebrow dn-e">↓ Лидеры падения</div>{lose.map(s => <Row key={s.t} s={s} />)}</div>
    </div>
  );
}

function ToneChip({ upside, conf }) {
  if (upside == null) return <span className="mk-tone"><span className="mk-epi">нет оценки</span></span>;
  const fv = Math.round(upside), c = fvColor(fv);
  return (
    <span className="mk-tone" title="Потенциал к справедливой цене (оценка Basis) — не рекомендация">
      <span className="mk-tone-dot" style={{ background: c }} />
      <span className="mk-tone-l" style={{ color: c }}>{fv > 0 ? "+" : ""}{fv}%</span>
      <span className="mk-tone-cap">к справедл.</span>
      <ConfDots level={conf} />
    </span>
  );
}
function StockCard({ s, onOpen, Logo }) {
  return (
    <button className="mk-card" onClick={() => onOpen(s)}>
      <div className="mk-card-top">
        {Logo ? <Logo ticker={s.t} name={s.n} size={38} /> : <Mono t={s.t} color={secColor(s.sec)} />}
        <div className="mk-card-id"><b>{s.n}</b><span className="mk-card-tk">{s.t} · {s.sec}</span></div>
      </div>
      <div className="mk-card-px">
        <span className="mk-card-price">{num(s.price, 2)}<span className="mk-cur"> ₽</span></span>
        <Delta pct={s.chg} abs={s.chgAbs} />
      </div>
      <div className="mk-card-foot"><span className="mk-cap">{money(s.mcap)}</span><ToneChip upside={s.upside} conf={s.conf} /></div>
    </button>
  );
}
function StockCards({ stocks, onOpen, Logo }) {
  const by = {};
  stocks.forEach(s => { (by[s.sec] = by[s.sec] || []).push(s); });
  Object.keys(by).forEach(g => by[g].sort((a, b) => (b.mcap || 0) - (a.mcap || 0))); // внутри сектора — по капитализации
  const order = orderSectors(Object.keys(by));
  if (!stocks.length) return <div className="mk-empty">Ничего не найдено. Измените запрос или сектор.</div>;
  return (
    <div className="mk-stack">
      {order.map(g => (
        <section key={g}>
          <div className="mk-grp-head"><span className="mk-grp-dot" style={{ background: secColor(g) }} />{g}<span className="mk-grp-n">{by[g].length}</span></div>
          <div className="mk-grid">{by[g].map(s => <StockCard key={s.t} s={s} onOpen={onOpen} Logo={Logo} />)}</div>
        </section>
      ))}
    </div>
  );
}
function StockRows({ stocks, onOpen, Logo }) {
  if (!stocks.length) return <div className="mk-empty">Ничего не найдено. Измените запрос или сектор.</div>;
  const sorted = [...stocks].sort((a, b) => (b.mcap || 0) - (a.mcap || 0)); // по капитализации
  return (
    <div className="mk-tablewrap" style={{ marginTop: 18 }}>
      <table className="mk-table mk-rows">
        <thead><tr><th className="l">Бумага</th><th>Цена</th><th>За день</th><th>Капитализация</th><th className="l">К справедливой цене</th></tr></thead>
        <tbody>
          {sorted.map(s => {
            const fv = s.upside == null ? null : Math.round(s.upside), tc = fv == null ? "var(--ink-3)" : fvColor(fv);
            const n = s.conf === "high" ? 3 : s.conf === "medium" ? 2 : 1;
            return (
              <tr key={s.t} onClick={() => onOpen(s)} style={{ cursor: "pointer" }}>
                <td className="l">
                  <div className="mk-row-id">
                    <span className="mk-tonebar" style={{ background: tc }} title="Тон Basis" />
                    {Logo ? <Logo ticker={s.t} name={s.n} size={30} /> : <Mono t={s.t} color={secColor(s.sec)} sm />}
                    <span className="mk-bond-id"><b>{s.n}</b><span className="mk-sub">{s.t} · {s.sec}</span></span>
                  </div>
                </td>
                <td className="num">{num(s.price, 2)}{NB}₽</td>
                <td className="num"><Delta pct={s.chg} /></td>
                <td className="num dim">{money(s.mcap)}</td>
                <td className="l"><span className="mk-row-tone"><span className="mk-tone-dot" style={{ background: tc }} /><span style={{ color: tc, fontWeight: 600, fontSize: 13, fontFamily: "'JetBrains Mono',monospace" }}>{fv == null ? "—" : (fv > 0 ? "+" : "") + fv + "%"}</span><span className="mk-conf">{[0, 1, 2].map(i => <i key={i} className={i < n ? "on" : ""} />)}</span></span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ══════════════════ ОБЛИГАЦИИ ══════════════════
function reliOf(b) {
  const t = (b.risk_tier || "").toLowerCase();
  if (["high", "low", "reliable", "investment"].includes(t)) return { k: "pos", label: b.risk_label || "Надёжный" };
  if (["speculative", "vdo", "junk", "high_yield"].includes(t)) return { k: "neg", label: b.risk_label || "ВДО" };
  return { k: "amber", label: b.risk_label || "Средний" };
}
const RELI_COLOR = { pos: "var(--pos)", amber: "var(--amber)", neg: "var(--neg)" };
function SegGroup({ label, options, value, onChange }) {
  return (
    <div className="mk-seg-group">
      <span className="mk-seg-lbl">{label}</span>
      <div className="mk-seg">
        {options.map(o => { const v = Array.isArray(o) ? o[0] : o, l = Array.isArray(o) ? o[1] : o; return <button key={v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>{l}</button>; })}
      </div>
    </div>
  );
}
function ViewToggle({ view, setView }) {
  return (
    <div className="mk-seg-group mk-seg-view">
      <span className="mk-seg-lbl">Вид</span>
      <div className="mk-seg">
        <button className={view === "rows" ? "on" : ""} onClick={() => setView("rows")}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 4h12M2 8h12M2 12h12" strokeLinecap="round" /></svg>Лента</button>
        <button className={view === "cards" ? "on" : ""} onClick={() => setView("cards")}><svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" /></svg>Карточки</button>
      </div>
    </div>
  );
}
function BondsTab({ rows, query, onOpen }) {
  const [coupon, setCoupon] = useState("Любой купон");
  const [reli, setReli] = useState("Любая надёжность");
  const [sort, setSort] = useState("default");
  const [view, setView] = useState("rows");
  const reliMap = { "Надёжные": "pos", "Средний риск": "amber", "ВДО": "neg" };
  let list = rows.filter(b => {
    const q = !query || ((b.short_name || "") + " " + (b.secid || "") + " " + (b.isin || "")).toLowerCase().includes(query.toLowerCase());
    const ct = (b.coupon_type || "").toLowerCase();
    const cmatch = coupon === "Любой купон" || (coupon === "Фикс" && ct.includes("fix")) || (coupon === "Флоатеры" && (ct.includes("float") || ct.includes("flo")));
    const rmatch = reli === "Любая надёжность" || reliOf(b).k === reliMap[reli];
    return q && cmatch && rmatch;
  });
  if (sort === "ytm") list = [...list].sort((a, b) => (b.ytm || 0) - (a.ytm || 0));
  else if (sort === "spread") list = [...list].sort((a, b) => (b.spread_bp || 0) - (a.spread_bp || 0));
  else if (sort === "dur") list = [...list].sort((a, b) => (a.duration_years || 99) - (b.duration_years || 99));
  list = list.slice(0, 400);
  return (
    <div>
      <div className="mk-filterbar">
        <SegGroup label="Купон" value={coupon} onChange={setCoupon} options={["Любой купон", "Фикс", "Флоатеры"]} />
        <SegGroup label="Надёжность" value={reli} onChange={setReli} options={["Любая надёжность", "Надёжные", "Средний риск", "ВДО"]} />
        <SegGroup label="Сортировка" value={sort} onChange={setSort} options={[["default", "По умолчанию"], ["spread", "Спред к ОФЗ"], ["ytm", "Доходность"], ["dur", "Дюрация"]]} />
        <ViewToggle view={view} setView={setView} />
      </div>
      <div className="mk-grp-head" style={{ marginTop: 20 }}>Выпуски<span className="mk-grp-n">{list.length}</span></div>
      {view === "cards" ? (
        <div className="mk-grid">{list.map(b => {
          const rel = reliOf(b), col = RELI_COLOR[rel.k];
          return (
            <button key={b.secid} className="mk-card mk-card-asset" onClick={() => onOpen(b.secid)}>
              <div className="mk-card-top"><span className="mk-mono" style={{ background: col + "22", color: col }}>{(b.short_name || b.secid).slice(0, 2)}</span><div className="mk-card-id"><b>{b.short_name}</b><span className="mk-card-tk">{b.isin}</span></div></div>
              <div className="mk-asset-big"><span className="mk-asset-bigv">{num(b.ytm, 1)}<span className="mk-cur"> %</span></span><span className="mk-asset-biglbl">YTM</span></div>
              <div className="mk-reli"><span className={"mk-badge mk-badge-" + rel.k}>{rel.label}</span>{b.agency_rating && <span className="mk-ag">{b.agency_rating}</span>}{b.basis_group && <span className="mk-basis">Basis {b.basis_group}</span>}</div>
              <div className="mk-card-stats">
                {b.spread_bp != null && <span><i>Спред ОФЗ</i>+{b.spread_bp} б.п.</span>}
                {b.duration_years != null && <span><i>Дюрация</i>{num(b.duration_years, 1)} г</span>}
                {b.last_price != null && <span><i>Цена</i>{num(b.last_price, 1)}%</span>}
              </div>
            </button>
          );
        })}</div>
      ) : (
        <div className="mk-tablewrap">
          <table className="mk-table"><thead><tr><th className="l">Выпуск</th><th className="l mk-reli-c">Рынок</th><th className="l mk-reli-c">Агентство</th><th>Цена</th><th>Спред к ОФЗ</th><th>YTM</th><th>Дюрация</th><th>Погашение</th></tr></thead>
            <tbody>
              {list.map(b => {
                const rel = reliOf(b);
                return (
                  <tr key={b.secid} onClick={() => onOpen(b.secid)} style={{ cursor: "pointer" }}>
                    <td className="l"><div className="mk-bond-id"><b>{b.short_name}</b><span className="mk-sub">{b.isin}{b.issuer_name ? " · " + b.issuer_name : ""}</span></div></td>
                    <td className="l mk-reli-c"><span className={"mk-badge mk-badge-" + rel.k}>{rel.label}</span></td>
                    <td className="l mk-reli-c">{b.agency_rating ? <span className="mk-ag">{b.agency_rating}</span> : <span className="dim">—</span>}</td>
                    <td className="num strong">{b.last_price != null ? num(b.last_price, 2) + NB + "%" : "—"}</td>
                    <td className="num"><span className="mk-spread">{b.spread_bp != null ? "+" + b.spread_bp + NB + "б.п." : "—"}</span></td>
                    <td className="num strong">{b.ytm != null ? num(b.ytm, 1) + NB + "%" : "—"}</td>
                    <td className="num">{b.duration_years != null ? num(b.duration_years, 1) + NB + "г" : "—"}</td>
                    <td className="num dim">{b.maturity_date || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!list.length && <div className="mk-empty">Нет выпусков под фильтры.</div>}
        </div>
      )}
    </div>
  );
}

// ══════════════════ ФЬЮЧЕРСЫ ══════════════════
// дневное изменение фьючерса: посл. цена против расчётной цены прошлого клиринга
const futChg = (f) => (f.last_price != null && f.prev_settle ? (Number(f.last_price) / Number(f.prev_settle) - 1) * 100 : null);
function LevBadge({ lev }) {
  if (lev == null) return <span className="mk-lev mk-lev-warn">—</span>;
  const tone = lev >= 10 ? "neg" : lev >= 7 ? "amber" : "warn";
  return <span className={"mk-lev mk-lev-" + tone}>{num(lev, 1)}×</span>;
}
function FuturesTab({ rows, query, onOpen }) {
  const [grpf, setGrpf] = useState("Все");
  const [view, setView] = useState("rows");
  const groupLabel = f => f.kind_label || "Прочее";
  const allGroups = useMemo(() => [...new Set(rows.map(groupLabel))], [rows]);
  const filt = rows.filter(f => (grpf === "Все" || groupLabel(f) === grpf) && (!query || ((f.sec_name || f.asset_name || "") + " " + f.secid).toLowerCase().includes(query.toLowerCase())));
  const by = {}; filt.forEach(f => { (by[groupLabel(f)] = by[groupLabel(f)] || []).push(f); });
  const order = Object.keys(by).sort((a, b) => by[b].length - by[a].length);
  return (
    <div>
      <div className="mk-callout amber">
        <b>Высокорисковый инструмент.</b> Фьючерс — дериватив со встроенным <b>плечом</b> (усиливает и прибыль, и убыток) и <b>датой экспирации</b>; для хеджа и спекуляции, а не «вложение». Basis показывает анатомию риска — плечо, ГО, срок, — а не торговые сигналы.
      </div>
      <div className="mk-filterbar" style={{ marginTop: 18 }}>
        <SegGroup label="Категория" value={grpf} onChange={setGrpf} options={["Все", ...allGroups]} />
        <ViewToggle view={view} setView={setView} />
      </div>
      {!order.length && <div className="mk-tablewrap" style={{ marginTop: 16 }}><div className="mk-empty">Ничего не найдено.</div></div>}
      {order.map(g => (
        <div key={g}>
          <div className="mk-grp-head" style={{ marginTop: 16 }}>{g}<span className="mk-grp-n">{by[g].length}</span></div>
          {view === "cards" ? (
            <div className="mk-grid">{by[g].map(f => { const chg = futChg(f); return (
              <button key={f.secid} className="mk-card mk-card-asset" onClick={() => onOpen(f.secid)}>
                <div className="mk-card-top"><span className="mk-mono" style={{ background: "var(--accent-soft)", color: "var(--accent-2)" }}>{f.secid.slice(0, 2)}</span><div className="mk-card-id"><b>{f.secid}</b><span className="mk-card-tk">{f.asset_name || f.sec_name}</span></div></div>
                <div className="mk-asset-big">
                  <span className="mk-asset-bigv">{num(f.last_price, 2)}</span>
                  {chg != null && <span className={"mk-delta " + (chg > 0 ? "up" : chg < 0 ? "dn" : "fl")}><span className="mk-delta-pct">{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {num(Math.abs(chg), 2)}%</span></span>}
                </div>
                <div className="mk-card-stats">
                  <span><i>Плечо</i>{f.leverage != null ? num(f.leverage, 1) + "×" : "—"}</span>
                  {f.days_to_expiry != null && <span><i>До эксп.</i>{f.days_to_expiry} дн</span>}
                  {f.initial_margin != null && <span><i>ГО</i>{grp(Math.round(f.initial_margin))} ₽</span>}
                  {f.open_position != null && <span><i>Откр. поз.</i>{grp(f.open_position)}</span>}
                </div>
              </button>
            ); })}</div>
          ) : (
            <div className="mk-tablewrap">
              <table className="mk-table"><thead><tr><th className="l">Контракт</th><th>Цена</th><th>За день</th><th>Плечо</th><th>До эксп.</th><th>ГО</th><th>Откр. позиции</th></tr></thead>
                <tbody>
                  {by[g].map(f => { const chg = futChg(f); return (
                    <tr key={f.secid} onClick={() => onOpen(f.secid)} style={{ cursor: "pointer" }}>
                      <td className="l"><div className="mk-bond-id"><b>{f.secid}</b><span className="mk-sub">{f.asset_name || f.sec_name}</span></div></td>
                      <td className="num strong">{f.last_price != null ? num(f.last_price, 2) : "—"}</td>
                      <td className="num">{chg == null ? <span className="dim">—</span> : <span className={"mk-delta " + (chg > 0 ? "up" : chg < 0 ? "dn" : "fl")}><span className="mk-delta-pct">{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {num(Math.abs(chg), 2)}{NB}%</span></span>}</td>
                      <td className="num"><LevBadge lev={f.leverage} /></td>
                      <td className="num">{f.days_to_expiry != null ? f.days_to_expiry + NB + "дн" : "—"}</td>
                      <td className="num">{f.initial_margin != null ? grp(Math.round(f.initial_margin)) + NB + "₽" : "—"}</td>
                      <td className="num dim">{f.open_position != null ? grp(f.open_position) : "—"}</td>
                    </tr>
                  ); })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════ ФОНДЫ ══════════════════
function FundsTab({ rows, query, onOpen, sparks }) {
  const [grpf, setGrpf] = useState("Все");
  const [view, setView] = useState("rows");
  const groupLabel = f => f.type_label || "Прочее";
  const allGroups = useMemo(() => [...new Set(rows.map(groupLabel))], [rows]);
  const filt = rows.filter(f => (grpf === "Все" || groupLabel(f) === grpf) && (!query || ((f.sec_name || "") + " " + f.secid).toLowerCase().includes(query.toLowerCase())));
  const by = {}; filt.forEach(f => { (by[groupLabel(f)] = by[groupLabel(f)] || []).push(f); });
  const order = Object.keys(by).sort((a, b) => by[b].length - by[a].length);
  const chgOf = f => (sparks[f.secid] || {}).change_pct;
  return (
    <div>
      <div className="mk-callout">
        <b>Фонды (БПИФ / ETF)</b> — это корзина активов, а не отдельная идея. Ключевое — <b>что внутри</b>, комиссия фонда (TER) и насколько точно он следует за индексом. Basis показывает состав и издержки, а не «доходность в прошлом как обещание».
      </div>
      <div className="mk-filterbar" style={{ marginTop: 18 }}>
        <SegGroup label="Категория" value={grpf} onChange={setGrpf} options={["Все", ...allGroups]} />
        <ViewToggle view={view} setView={setView} />
      </div>
      {!order.length && <div className="mk-tablewrap" style={{ marginTop: 16 }}><div className="mk-empty">Ничего не найдено.</div></div>}
      {order.map(g => (
        <div key={g}>
          <div className="mk-grp-head" style={{ marginTop: 16 }}>{g}<span className="mk-grp-n">{by[g].length}</span></div>
          {view === "cards" ? (
            <div className="mk-grid">{by[g].map(f => { const chg = chgOf(f); return (
              <button key={f.secid} className="mk-card mk-card-asset" onClick={() => onOpen(f.secid)}>
                <div className="mk-card-top"><span className="mk-mono" style={{ background: "var(--accent-soft)", color: "var(--accent-2)" }}>{f.secid.slice(0, 2)}</span><div className="mk-card-id"><b>{f.secid}</b><span className="mk-card-tk">{f.sec_name}</span></div></div>
                <div className="mk-asset-big"><span className="mk-asset-bigv">{num(f.last_price, 2)}<span className="mk-cur"> ₽</span></span>{chg != null && <span className={"mk-delta " + (chg > 0 ? "up" : chg < 0 ? "dn" : "fl")}><span className="mk-delta-pct">{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {num(Math.abs(chg), 2)}%</span></span>}</div>
                <div className="mk-card-stats">
                  {f.benchmark && <span className="full"><i>Отслеживает</i>{f.benchmark}</span>}
                  {f.ter != null && <span><i>Комиссия</i>{num(f.ter, 2)}%</span>}
                  {f.val_today != null && <span><i>Оборот</i>{money(f.val_today)}</span>}
                </div>
              </button>
            ); })}</div>
          ) : (
            <div className="mk-tablewrap">
              <table className="mk-table"><thead><tr><th className="l">Фонд</th><th className="l">Отслеживает</th><th>Цена пая</th><th>За день</th><th>Комиссия (TER)</th><th>Оборот</th></tr></thead>
                <tbody>
                  {by[g].map(f => { const chg = chgOf(f); return (
                    <tr key={f.secid} onClick={() => onOpen(f.secid)} style={{ cursor: "pointer" }}>
                      <td className="l"><div className="mk-bond-id"><b>{f.secid}</b><span className="mk-sub">{f.sec_name}</span></div></td>
                      <td className="l dim">{f.benchmark || "—"}</td>
                      <td className="num">{num(f.last_price, 2)}{NB}₽</td>
                      <td className="num">{chg == null ? <span className="dim">—</span> : <span className={"mk-delta " + (chg > 0 ? "up" : chg < 0 ? "dn" : "fl")}><span className="mk-delta-pct">{chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {num(Math.abs(chg), 2)}{NB}%</span></span>}</td>
                      <td className="num strong">{f.ter != null ? num(f.ter, 2) + NB + "%" : "—"}</td>
                      <td className="num dim">{f.val_today != null ? money(f.val_today) : "—"}</td>
                    </tr>
                  ); })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════ ВАЛЮТА И МЕТАЛЛЫ ══════════════════
function FxMetalsTab({ rows, onOpen }) {
  const fx = rows.filter(r => r.kind === "currency");
  const metals = rows.filter(r => r.kind === "metal");
  const List = ({ items, dec }) => (
    <div className="mk-tablewrap">
      <table className="mk-table"><thead><tr><th className="l">Инструмент</th><th>Цена (₽)</th><th>За день</th></tr></thead>
        <tbody>
          {items.map(r => (
            <tr key={r.secid} onClick={() => onOpen(r.secid)} style={{ cursor: "pointer" }}>
              <td className="l"><b className="mk-fx-n">{r.name}</b></td>
              <td className="num">{num(r.last_price, dec)}</td>
              <td className="num">{r.change_pct == null ? <span className="dim">—</span> : <span className={"mk-delta " + (r.change_pct > 0 ? "up" : r.change_pct < 0 ? "dn" : "fl")}><span className="mk-delta-pct">{r.change_pct > 0 ? "+" : ""}{num(r.change_pct, 2)}{NB}%</span></span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <div>
      <div className="mk-callout">
        Валюта и металлы — это <b>не «актив со справедливой ценой»</b>, а макро-индикаторы. Курс рубля зависит от ставки ЦБ, нефти и платёжного баланса; золото — защитный актив. Basis объясняет роль в портфеле, а не «куда пойдёт цена». После санкций 2024 на бирже ликвидны в основном <b>доллар и юань</b>.
      </div>
      {fx.length > 0 && <><div className="mk-grp-head" style={{ marginTop: 18 }}>Валюты<span className="mk-grp-n">{fx.length}</span></div><List items={fx} dec={3} /></>}
      {metals.length > 0 && <><div className="mk-grp-head" style={{ marginTop: 20 }}>Драгметаллы<span className="mk-grp-n">{metals.length}</span></div><List items={metals} dec={2} /></>}
    </div>
  );
}

function OptionsTab({ onOpen, hasOptions }) {
  return (
    <div>
      <div className="mk-callout amber">
        <b>Опционы — инструмент для опытных.</b> Это право (не обязанность) купить или продать базовый актив по цене страйк до экспирации. Цена зависит не только от направления, но и от <b>времени</b> и <b>волатильности</b> — можно быть «правым по рынку» и всё равно потерять. Basis раскрывает структуру риска, а не сигналы.
      </div>
      <div className="mk-options-empty">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17l5-5 4 3 6-7" /><path d="M16 8h4v4" /></svg>
        <div className="mk-opt-t">Анализ опционов скоро</div>
        <p>Готовим разбор по базовым активам: цепочки страйков, подразумеваемую волатильность и анатомию риска позиции — в логике Basis, без торговых сигналов.</p>
      </div>
    </div>
  );
}

// ══════════════════ ГЛАВНЫЙ КОМПОНЕНТ ══════════════════
function inTradingHours() {
  // MOEX: утренняя сессия с 07:00, основная + вечерняя до ~23:50 МСК (будни).
  const msk = new Date(new Date().toLocaleString("en-US", { timeZone: "Europe/Moscow" }));
  const day = msk.getDay();
  if (day === 0 || day === 6) return false;
  const t = msk.getHours() * 60 + msk.getMinutes();
  return t >= 7 * 60 && t <= 23 * 60 + 50;
}

export default function MarketNeo({ onOpenCompany, onOpenBond, onOpenFuture, onOpenFund, onOpenSpot, onOpenOption, Logo }) {
  const persist = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
  const [tab, setTab] = useState(() => persist("mk.tab", "stocks"));
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("Все");
  const [stockView, setStockView] = useState(() => persist("mk.sview2", "list"));

  const [scored, setScored] = useState([]);
  const [capByTicker, setCapByTicker] = useState({}); // combined_market_cap (обычка+преф)
  const [live, setLive] = useState({});
  const [quoteSrc, setQuoteSrc] = useState(null);   // tinkoff | moex_iss
  const [quoteTime, setQuoteTime] = useState(null);  // _fetched_at (тикает каждый запрос)
  const [index, setIndex] = useState(null);
  const [drivers, setDrivers] = useState([]);
  const [bonds, setBonds] = useState([]);
  const [futures, setFutures] = useState([]);
  const [funds, setFunds] = useState([]);
  const [spot, setSpot] = useState([]);
  const [fundSparks, setFundSparks] = useState({});
  const [loading, setLoading] = useState(true);

  const saveTab = (t) => { setTab(t); setQuery(""); setSector("Все"); try { localStorage.setItem("mk.tab", t); } catch {} };
  const saveSView = (v) => { setStockView(v); try { localStorage.setItem("mk.sview2", v); } catch {} };

  // акции (scored) + пульс + капитализации: загрузка при монтировании И периодическое
  // освежение, пока экран открыт (цены/капы идут из quotes, бэк обновляет ~раз в 5 мин —
  // подстраховка к realtime-поллингу ниже, чтобы цифры не «застывали»).
  useEffect(() => {
    const api = apiBase();
    let alive = true;
    const ns = { cache: "no-store" };
    const ts = () => Date.now();
    const load = () => Promise.all([
      fetch(`${api}/api/screener/scored?universe=all&_=${ts()}`, ns).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${api}/api/market/indices?_=${ts()}`, ns).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${api}/api/market/drivers?_=${ts()}`, ns).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${api}/api/companies?_=${ts()}`, ns).then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([sc, idx, dr, comp]) => {
      if (!alive) return;
      if (Array.isArray(comp)) {
        const m = {};
        comp.forEach(c => {
          const cap = c.combined_market_cap != null ? c.combined_market_cap : c.market_cap;
          if (cap != null) m[c.ticker] = parseFloat(cap);
        });
        setCapByTicker(m);
      }
      if (sc && Array.isArray(sc.rows)) {
        setScored(sc.rows.map(r => ({
          t: r.ticker, n: r.name, sec: r.sector || "Прочее", price: r.price,
          mcap: r.market_cap, upside: r.raw ? r.raw.upside : null, basis: r.basis,
          conf: ConfFromRow(r),
        })));
      }
      if (Array.isArray(idx) && idx.length) setIndex(idx.find(x => x.ticker === "IMOEX") || idx[0]);
      if (Array.isArray(dr)) setDrivers(dr);
      setLoading(false);
    }).catch(() => { if (alive) setLoading(false); });
    load();
    const iv = setInterval(load, inTradingHours() ? 90000 : 180000);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  // живые котировки (дневная дельта + ширина рынка). Тинькофф realtime.
  // ВАЖНО: cache-busting (?_=ts) + cache:"no-store" — иначе прокси/браузер отдаёт
  // фоновому fetch СТАРЫЙ ответ (а перезагрузка идёт мимо кеша), и экран «застывает»
  // до F5. setInterval + опрос при возврате на вкладку.
  useEffect(() => {
    let alive = true, inFlight = false;
    const tick = () => {
      if (inFlight) return;                 // не накладываем запросы, если бэк отвечает медленно
      inFlight = true;
      fetch(`${apiBase()}/api/quotes/realtime?_=${Date.now()}`, { cache: "no-store" })
        .then(r => (r.ok ? r.json() : null))
        .then(d => {
          if (!alive || !d) return;
          const { _moex_time, _fetched_at, _source, ...q } = d;
          setLive(q); setQuoteSrc(_source || null); setQuoteTime(_fetched_at || _moex_time || null);
        }).catch(() => {}).finally(() => { inFlight = false; });
    };
    tick();
    // Близко к реал-тайму: 2с в торги / 10с вне (вне торгов сделок нет — цены не двигаются).
    const id = setInterval(tick, inTradingHours() ? 2000 : 10000);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { alive = false; clearInterval(id); document.removeEventListener("visibilitychange", onVis); };
  }, []);

  // Списки классов: рефетч при открытии вкладки + периодическое освежение, пока экран
  // открыт (чтобы котировки обновлялись без перезагрузки). Облигации (3152 строки,
  // снапшот на бэке раз в день) освежаем реже, остальные — каждые 30с в торги.
  useEffect(() => {
    const api = apiBase();
    const map = { bonds: ["/api/bonds", setBonds], futures: ["/api/futures", setFutures], funds: ["/api/funds", setFunds], fx: ["/api/spot", setSpot] };
    const entry = map[tab];
    if (!entry) return;
    const [url, setter] = entry;
    let alive = true;
    const sep = url.includes("?") ? "&" : "?";
    const load = () => fetch(`${api}${url}${sep}_=${Date.now()}`, { cache: "no-store" }).then(r => r.ok ? r.json() : []).then(d => {
      if (!alive) return;
      const arr = Array.isArray(d) ? d : [];
      setter(arr);
      if (tab === "funds" && arr.length) {
        const ids = arr.map(f => f.secid).slice(0, 200).join(",");
        fetch(`${api}/api/market/instruments/sparklines?asset_class=fund&secids=${encodeURIComponent(ids)}&days=30&_=${Date.now()}`, { cache: "no-store" })
          .then(r => r.ok ? r.json() : {}).then(s => alive && setFundSparks(s || {})).catch(() => {});
      }
    }).catch(() => {});
    load();
    const period = !inTradingHours() ? 180000 : (tab === "bonds" ? 120000 : 30000);
    const iv = setInterval(load, period);
    return () => { alive = false; clearInterval(iv); };
  }, [tab]);

  // акции с живой дельтой
  const stocks = useMemo(() => scored.map(s => {
    const q = live[s.t];
    const mcap = capByTicker[s.t] != null ? capByTicker[s.t] : s.mcap; // обычка+преф
    return { ...s, mcap, price: (q && q.price != null) ? q.price : s.price, chg: q ? q.change_pct : null, chgAbs: q ? q.change_abs : null };
  }), [scored, live, capByTicker]);

  const stocksFiltered = useMemo(() => stocks.filter(s =>
    (sector === "Все" || s.sec === sector) && (!query || (s.n + " " + s.t).toLowerCase().includes(query.toLowerCase()))
  ), [stocks, sector, query]);

  const breadth = useMemo(() => {
    const withChg = stocks.filter(s => s.chg != null);
    const adv = withChg.filter(s => s.chg > 0).length;
    const dec = withChg.filter(s => s.chg < 0).length;
    return { adv, dec, flat: withChg.length - adv - dec, total: withChg.length };
  }, [stocks]);

  const TABS = [
    { id: "stocks", label: "Акции", count: scored.length || null },
    { id: "bonds", label: "Облигации", count: bonds.length || null },
    { id: "futures", label: "Фьючерсы", count: futures.length || null },
    { id: "funds", label: "Фонды", count: funds.length || null },
    { id: "fx", label: "Валюта и металлы", count: spot.length || null },
    { id: "options", label: "Опционы", count: null },
  ];
  const showSearch = tab !== "fx" && tab !== "options" && !(tab === "stocks" && stockView !== "list");
  const placeholder = tab === "bonds" ? "Поиск по выпуску / ISIN…" : tab === "futures" ? "Поиск по контракту / базовому активу…" : tab === "funds" ? "Поиск по фонду…" : "Поиск по тикеру или названию…";

  return (
    <div className="mk-screen">
      <div className="mk-page-head">
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <h1 className="mk-page-title">Рынок</h1>
          <span className="mk-quote-live" title="Источник котировок акций. Тинькофф — реал-тайм; MOEX — запасной (с задержкой). Время обновляется на каждом опросе (6с).">
            <span className={"mk-live-dot" + (quoteSrc === "tinkoff" ? " on" : quoteSrc ? " warn" : "")} />
            {quoteSrc === "tinkoff" ? "Тинькофф · реал-тайм" : quoteSrc === "moex_iss" ? "MOEX · запасной (задержка)" : "Котировки…"}
            {quoteTime && <span className="mk-live-t">· {String(quoteTime).slice(11, 19)}</span>}
          </span>
        </div>
        <p className="mk-page-sub">Котировки и аналитика российского рынка — со взглядом Basis на риск и справедливую цену, а не торговые сигналы.</p>
      </div>

      <div className="mk-tabbar" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={"mk-tab" + (tab === t.id ? " on" : "")} onClick={() => saveTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {showSearch && (
        <div className="mk-toolbar">
          <label className="mk-search">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder={placeholder} />
          </label>
        </div>
      )}

      {tab === "stocks" && (
        <div className="mk-viewtog">
          <button className={stockView === "list" ? "on" : ""} onClick={() => saveSView("list")}><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="3" width="5" height="4" rx="1" /><rect x="9" y="3" width="5" height="4" rx="1" /><rect x="2" y="9" width="5" height="4" rx="1" /><rect x="9" y="9" width="5" height="4" rx="1" /></svg>Карточки</button>
          <button className={stockView === "rows" ? "on" : ""} onClick={() => saveSView("rows")}><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 4h12M2 8h12M2 12h12" strokeLinecap="round" /></svg>Лента</button>
          <button className={stockView === "map" ? "on" : ""} onClick={() => saveSView("map")}><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="7" height="7" rx="1" /><rect x="11" y="2" width="3" height="7" rx="1" /><rect x="2" y="11" width="5" height="3" rx="1" /><rect x="9" y="11" width="5" height="3" rx="1" /></svg>Карта рынка</button>
        </div>
      )}

      {tab === "stocks" && <Pulse index={index} drivers={drivers} adv={breadth.adv} dec={breadth.dec} flat={breadth.flat} total={breadth.total} />}
      {tab === "stocks" && !loading && <SectorNav stocks={stocks} sector={sector} onSelect={setSector} />}

      {loading && tab === "stocks" ? <div className="mk-loading">Загружаем рынок…</div> : (
        <>
          {tab === "stocks" && stockView === "map" && <><Heatmap stocks={stocksFiltered} onOpen={s => onOpenCompany(s.t)} /><div className="mk-sec-title">Лидеры дня</div><Movers stocks={stocksFiltered} onOpen={s => onOpenCompany(s.t)} Logo={Logo} /></>}
          {tab === "stocks" && stockView === "rows" && <StockRows stocks={stocksFiltered} onOpen={s => onOpenCompany(s.t)} Logo={Logo} />}
          {tab === "stocks" && stockView === "list" && <StockCards stocks={stocksFiltered} onOpen={s => onOpenCompany(s.t)} Logo={Logo} />}
          {tab === "bonds" && <BondsTab rows={bonds} query={query} onOpen={onOpenBond} />}
          {tab === "futures" && <FuturesTab rows={futures} query={query} onOpen={onOpenFuture} />}
          {tab === "funds" && <FundsTab rows={funds} query={query} onOpen={onOpenFund} sparks={fundSparks} />}
          {tab === "fx" && <FxMetalsTab rows={spot} onOpen={onOpenSpot} />}
          {tab === "options" && <OptionsTab onOpen={onOpenOption} />}
        </>
      )}

      <p className="mk-foot-note">Котировки — MOEX / Т-Инвестиции (могут отставать на несколько минут). Basis — независимый аналитический «второй взгляд»; не брокер и не источник торговых сигналов. Ничто здесь не является инвестиционной рекомендацией.</p>
    </div>
  );
}
