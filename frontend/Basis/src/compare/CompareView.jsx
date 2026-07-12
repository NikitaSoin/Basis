// Сравнение активов (2026-07-11, восстановлено 2026-07-12 после потери в App.js
// при рефакторинге на отдельные файлы — см. docs/work-journal.md). Конкурентный
// разбор Инвестминт/ПроФинанс: сопоставление бумаг бок о бок по ключевым метрикам
// + нормализованная динамика цены. Инструмент сопоставления, НЕ рекомендация.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "../design/primitives";
import { CompanyLogo } from "../design/CompanyLogo";
import { ObsLineChart } from "../observer/ObsPanels";
import {
  METRICS as STOCK_METRICS,
  GROUPS as STOCK_METRIC_GROUPS,
  InfoTip as ScreenerInfoTip,
  fmtMetric as fmtStockMetric,
  FAIR_VALUE_HINT,
} from "../screener/ScreenerNeo";

// Период графика цены — тот же паттерн (id/label/days) и тот же визуальный
// язык кнопок, что PRICE_CHART_PERIODS в company/CompanyCardView.jsx (карточка
// компании), НЕ изобретён заново.
const CMP_PRICE_PERIODS = [
  { id: "1m", label: "1М", days: 30 },
  { id: "3m", label: "3М", days: 90 },
  { id: "6m", label: "6М", days: 180 },
  { id: "1y", label: "1Г", days: 365 },
  { id: "3y", label: "3Г", days: 1095 },
  { id: "all", label: "Всё", days: 4000 },
];

// Переключатель период/режим — идентичные tw-классы кнопкам периода в
// company/CompanyCardView.jsx:88-101 (единый визуальный язык фильтров сайта,
// не Chip и не что-то новое).
function CmpPillButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`tw-px-2.5 tw-py-1 tw-rounded-sm tw-text-[12px] tw-font-medium tw-border tw-cursor-pointer tw-transition-colors focus-visible:tw-outline-none focus-visible:tw-shadow-focus ${
        active
          ? "tw-bg-accent tw-text-white tw-border-accent"
          : "tw-bg-transparent tw-text-text-secondary tw-border-border-subtle hover:tw-border-border-strong"
      }`}
    >
      {children}
    </button>
  );
}

// Простой self-contained столбчатый график (группировка по годам, одна группа
// столбцов на год, один столбец на компанию) — для годовой метрики иногда
// читается яснее непрерывной линии между редкими точками (7-10 лет). Hover —
// тот же визуальный язык тултипа, что ObsLineChart (.obs-chart-tooltip).
function CompareBarChart({ series, viewW = 1000, viewH = 260, unit = "" }) {
  const [hoverI, setHoverI] = useState(null);
  const svgRef = useRef(null);
  const pad = { top: 12, right: 12, bottom: 26, left: 48 };
  const years = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.as_of)))).sort();
  const n = years.length;
  if (n < 1) return null;
  const vals = series.flatMap((s) => s.points.map((p) => p.value)).filter((v) => v != null);
  let vmin = Math.min(...vals, 0), vmax = Math.max(...vals, 0);
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const rpad = (vmax - vmin) * 0.1 || 1; vmin -= rpad; vmax += rpad;
  const plotW = viewW - pad.left - pad.right, plotH = viewH - pad.top - pad.bottom;
  const groupW = plotW / n;
  const barGap = 3;
  const barW = Math.max(3, (groupW - barGap * (series.length + 1)) / series.length);
  const y = (v) => pad.top + (1 - (v - vmin) / (vmax - vmin)) * plotH;
  const zeroY = y(0);

  const onMove = (e) => {
    const el = svgRef.current; if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const px = ((cx - rect.left) / rect.width) * viewW;
    let i = Math.floor((px - pad.left) / groupW);
    setHoverI(Math.max(0, Math.min(n - 1, i)));
  };

  const hoverX = hoverI != null ? pad.left + hoverI * groupW + groupW / 2 : 0;
  const tipPct = hoverI != null ? (hoverX / viewW) * 100 : 0;
  const tipRight = tipPct > 55;

  return (
    <div style={{ position: "relative" }}>
      {hoverI != null && (
        <div className="obs-chart-tooltip" style={{ left: tipRight ? undefined : `${tipPct}%`, right: tipRight ? `${100 - tipPct}%` : undefined, top: "8px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-tertiary)", marginBottom: "6px" }}>{years[hoverI]}</div>
          {series.map((s, k) => {
            const v = s.points.find((p) => p.as_of === years[hoverI])?.value;
            return (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12.5px", marginTop: "3px" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: s.color, display: "inline-block", flexShrink: 0 }} />
                <span style={{ color: "var(--text-secondary)" }}>{s.name}</span>
                <b style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums" }}>{v == null ? "—" : v.toFixed(1)}{unit}</b>
              </div>
            );
          })}
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${viewW} ${viewH}`}
        style={{ width: "100%", height: "auto", cursor: "crosshair", display: "block", touchAction: "none" }}
        onPointerMove={onMove}
        onPointerLeave={() => setHoverI(null)}
        role="img"
        aria-label="Метрика по годам"
      >
        {[vmin, vmin + (vmax - vmin) / 2, vmax].map((t, i) => (
          <g key={i}>
            <line x1={pad.left} x2={viewW - pad.right} y1={y(t)} y2={y(t)} stroke="var(--border-subtle)" strokeWidth="1" />
            <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--text-tertiary)" fontFamily="var(--font-mono)">{t.toFixed(0)}{unit}</text>
          </g>
        ))}
        {vmin < 0 && vmax > 0 && <line x1={pad.left} x2={viewW - pad.right} y1={zeroY} y2={zeroY} stroke="var(--text-tertiary)" strokeWidth="1" />}
        {years.map((yr, i) => (
          <text key={yr} x={pad.left + i * groupW + groupW / 2} y={viewH - 6} textAnchor="middle" fontSize="10" fill="var(--text-tertiary)" fontFamily="var(--font-mono)">{yr}</text>
        ))}
        {hoverI != null && (
          <rect x={pad.left + hoverI * groupW} y={pad.top} width={groupW} height={plotH} fill="var(--bg-hover)" opacity="0.5" />
        )}
        {years.map((yr, gi) =>
          series.map((s, si) => {
            const v = s.points.find((p) => p.as_of === yr)?.value;
            if (v == null) return null;
            const bx = pad.left + gi * groupW + barGap + si * (barW + barGap);
            const barY = Math.min(y(v), zeroY), barH = Math.abs(y(v) - zeroY);
            return <rect key={`${gi}-${si}`} x={bx} y={barY} width={barW} height={Math.max(1, barH)} fill={s.color} rx="1.5" />;
          })
        )}
      </svg>
    </div>
  );
}

const apiBase = () => process.env.REACT_APP_API_URL || "http://localhost:8000";

// Кэш в памяти модуля — переживает переключение вкладок в рамках сессии (как
// у списков Рынка/Скринера), НЕ localStorage — сравнение не обязано жить между визитами.
const _cmpCache = {};
function usePersistedState(key, initial) {
  const [v, setV] = useState(() => (key in _cmpCache ? _cmpCache[key] : initial));
  useEffect(() => { _cmpCache[key] = v; }, [key, v]);
  return [v, setV];
}

const COMPARE_MAX = 6;
const CMP_CAT_COLORS = ["var(--cat-1)", "var(--cat-2)", "var(--cat-3)", "var(--cat-4)", "var(--cat-5)", "var(--cat-6)"];

function CompareSearchAdd({ pool, selected, onAdd, disabled }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  const results = q.trim()
    ? pool.filter((c) => !selected.includes(c.ticker) && ((c.name || "").toLowerCase().includes(q.toLowerCase()) || c.ticker.toLowerCase().includes(q.toLowerCase()))).slice(0, 8)
    : [];
  return (
    <div className="cmp-search" ref={ref}>
      <input
        className="cmp-search-input"
        placeholder={disabled ? `Максимум ${COMPARE_MAX} компаний` : "Добавить компанию — тикер или название"}
        value={q}
        disabled={disabled}
        onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {open && results.length > 0 && (
        <div className="cmp-search-menu">
          {results.map((c) => (
            <button key={c.ticker} className="cmp-search-item" onClick={() => { onAdd(c.ticker); setQ(""); setOpen(false); }}>
              <b>{c.ticker}</b><span>{c.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function cmpScoreColor(s) {
  if (s == null) return "var(--text-tertiary)";
  const t = Math.max(0, Math.min(1, (s - 45) / (82 - 45)));
  const hue = t < 0.5 ? (t / 0.5) * 33 : 33 + ((t - 0.5) / 0.5) * 105;
  return `hsl(${hue.toFixed(0)} 64% 42%)`;
}

// Метрики с однозначным «лучше/хуже» — только они получают зелёную подсветку.
// Мультипликаторы (P/E, EV/EBITDA и т.п.) намеренно исключены: низкое значение
// не всегда значит «дёшево» (см. hint-тексты в ScreenerNeo.METRICS).
const CMP_UNAMBIGUOUS = ["div_yield", "roe", "ebitda_margin", "fcf_yield"];
function cmpBestTicker(items, key, dir) {
  const withVal = items.filter((it) => it.raw?.[key] != null);
  if (withVal.length < 2) return null;
  return withVal.reduce((b, c) => ((dir === "high" ? c.raw[key] > b.raw[key] : c.raw[key] < b.raw[key]) ? c : b)).ticker;
}

// Дополнительные метрики из financials.json (metrics_timeseries) — 10-метричный
// набор /api/screener/scored заточен под скоринг, не под полноту сравнения;
// ProFinance даёт P/B, P/S, ROA/ROIC, операционную/чистую маржу и рост
// выручки/прибыли — этого у нас не было. Тот же массив metrics_timeseries
// (последнее значение = «текущее») даёт график по годам ниже.
const CMP_FIN_METRICS = {
  pb:                  { label: "P / B",                unit: "×", dec: 1, group: "Оценка (из отчётности)" },
  ps:                  { label: "P / S",                unit: "×", dec: 2, group: "Оценка (из отчётности)" },
  roa:                 { label: "ROA",                  unit: "%", dec: 1, group: "Качество (из отчётности)", high: true },
  roic:                { label: "ROIC",                 unit: "%", dec: 1, group: "Качество (из отчётности)", high: true },
  operating_margin:    { label: "Операционная маржа",   unit: "%", dec: 1, group: "Качество (из отчётности)", high: true },
  net_margin:          { label: "Чистая маржа",         unit: "%", dec: 1, group: "Качество (из отчётности)", high: true },
  net_interest_margin: { label: "ЧПМ (NIM, банки)",     unit: "%", dec: 1, group: "Качество (из отчётности)", high: true },
  revenue_growth:      { label: "Рост выручки, г/г",         unit: "%", dec: 1, group: "Рост", high: true },
  net_profit_growth:   { label: "Рост чистой прибыли, г/г", unit: "%", dec: 1, group: "Рост", high: true },
};
const CMP_FIN_GROUPS = ["Оценка (из отчётности)", "Качество (из отчётности)", "Рост"];
// Метрики, доступные для графика по годам (объединение — не у всех компаний
// заполнено всё; профиль «банк» использует net_interest_margin вместо
// gross/ebitda/operating_margin).
const CMP_YEARLY_METRICS = [
  { key: "revenue_growth", label: "Рост выручки", unit: "%" },
  { key: "net_profit_growth", label: "Рост чистой прибыли", unit: "%" },
  { key: "roe", label: "ROE", unit: "%" },
  { key: "roa", label: "ROA", unit: "%" },
  { key: "roic", label: "ROIC", unit: "%" },
  { key: "net_margin", label: "Чистая маржа", unit: "%" },
  { key: "operating_margin", label: "Операционная маржа", unit: "%" },
  { key: "ebitda_margin", label: "EBITDA-маржа", unit: "%" },
  { key: "net_interest_margin", label: "ЧПМ (NIM, банки)", unit: "%" },
  { key: "pe", label: "P / E", unit: "×" },
  { key: "pb", label: "P / B", unit: "×" },
  { key: "ps", label: "P / S", unit: "×" },
  { key: "ev_ebitda", label: "EV / EBITDA", unit: "×" },
  { key: "net_debt_ebitda", label: "Чистый долг / EBITDA", unit: "×" },
];

function _lastNN(arr) {
  if (!Array.isArray(arr)) return null;
  for (let i = arr.length - 1; i >= 0; i--) {
    if (arr[i] != null) return arr[i];
  }
  return null;
}
function fmtFinMetric(k, v) {
  if (v == null) return "—";
  const m = CMP_FIN_METRICS[k];
  return Number(v).toLocaleString("ru-RU", { maximumFractionDigits: m?.dec ?? 1, minimumFractionDigits: 0 }) + (m?.unit || "");
}
function cmpFinBestTicker(finByTicker, items, key) {
  const withVal = items
    .map((it) => ({ it, v: _lastNN(finByTicker[it.ticker]?.metrics_timeseries?.[key]) }))
    .filter((x) => x.v != null);
  if (withVal.length < 2) return null;
  return withVal.reduce((b, c) => (c.v > b.v ? c : b)).it.ticker;
}

// Кураторский набор метрик — то, что реально нужно для решения (продуктовый
// разбор 2026-07-12: полный дамп 26+ строк перегружает, а не помогает).
// Остальное — за «Развернуть все метрики». trendKey — ключ в
// metrics_timeseries для колонки «Тренд» (не у всех метрик есть годовой ряд —
// тогда просто «—», честно, не подделываем).
const CMP_CURATED = [
  { key: "div_yield", label: "Дивдоходность", source: "raw", trendKey: null },
  { key: "roe", label: "ROE", source: "raw", trendKey: "roe" },
  { key: "pe", label: "P / E", source: "raw", trendKey: "pe" },
  { key: "nd_ebitda", label: "Чист. долг / EBITDA", source: "raw", trendKey: "net_debt_ebitda" },
  { key: "pb", label: "P / B", source: "fin", trendKey: "pb" },
  { key: "mcap", label: "Капитализация", source: "raw", trendKey: null },
];

function _cmpRowValue(it, row, finData) {
  if (row.key === "mcap") return it.market_cap;
  if (row.source === "fin") return _lastNN(finData[it.ticker]?.metrics_timeseries?.[row.key]);
  return it.raw?.[row.key];
}
function _cmpRowFmt(row, v) {
  return row.source === "fin" ? fmtFinMetric(row.key, v) : fmtStockMetric(row.key, v);
}
// Приглушаем строку, если значения между бумагами почти не различаются
// (< DIVERGE_THRESHOLD относительного разброса) — «на чём расходятся», а не
// «вот все числа подряд» (тот же принцип, что в CompareVerdict).
function cmpRowDiverges(items, row, finData) {
  const vals = items.map((it) => _cmpRowValue(it, row, finData)).filter((v) => v != null);
  if (vals.length < 2) return null;
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const scale = Math.max(Math.abs(lo), Math.abs(hi)) || 1;
  return (hi - lo) / scale >= DIVERGE_THRESHOLD;
}

// Мини-спарклайн (одна линия на бумагу) для колонки «Тренд» — клик открывает
// полный интерактивный график в карточке «Метрика по годам» выше.
function CmpTrendSpark({ items, finData, trendKey, label, onOpen }) {
  if (!trendKey) return <span className="cmp-trend-empty">—</span>;
  const years = Array.from(new Set(items.flatMap((it) => finData[it.ticker]?.meta?.fiscal_years || []))).sort((a, b) => a - b);
  const series = items
    .map((it, i) => {
      const fin = finData[it.ticker];
      const arr = fin?.metrics_timeseries?.[trendKey];
      const fy = fin?.meta?.fiscal_years;
      if (!arr || !fy) return null;
      const byYear = {}; fy.forEach((y, idx) => { byYear[y] = arr[idx]; });
      return { color: CMP_CAT_COLORS[i % CMP_CAT_COLORS.length], vals: years.map((y) => byYear[y] ?? null) };
    })
    .filter((s) => s && s.vals.some((v) => v != null));
  if (!series.length) return <span className="cmp-trend-empty">—</span>;
  const all = series.flatMap((s) => s.vals).filter((v) => v != null);
  let vmin = Math.min(...all), vmax = Math.max(...all);
  if (vmin === vmax) { vmin -= 1; vmax += 1; }
  const w = 52, h = 22, n = years.length;
  const x = (i) => (n > 1 ? (i / (n - 1)) * w : w / 2);
  const y = (v) => h - ((v - vmin) / (vmax - vmin)) * h;
  return (
    <button type="button" className="cmp-trend-btn" onClick={onOpen} title={`Открыть «${label}» по годам, ${years[0]}–${years[years.length - 1]}`}>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
        {series.map((s, si) => {
          const pts = s.vals.map((v, i) => (v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
          if (pts.length < 2) return null;
          return <polyline key={si} points={pts.join(" ")} fill="none" stroke={s.color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />;
        })}
      </svg>
    </button>
  );
}

// Короткий синтез над таблицей для 3+ бумаг (для ровно 2 — см. CompareVerdict
// ниже, полноценная панель «Точки расхождения»). «Вердикт поверх данных» по
// дизайн-конституции Basis — голая таблица без интерпретации не считается
// готовым экраном.
function CompareSynthesis({ items }) {
  if (items.length < 2) return null;
  const pickBasis = () => {
    const withVal = items.filter((it) => it.basis != null);
    if (withVal.length < 2) return null;
    return withVal.reduce((a, b) => (b.basis > a.basis ? b : a));
  };
  const pickMetric = (key, label) => {
    const withVal = items.filter((it) => it.raw?.[key] != null);
    if (withVal.length < 2) return null;
    const best = withVal.reduce((a, b) => (b.raw[key] > a.raw[key] ? b : a));
    return `выше ${label} — ${best.name} (${fmtStockMetric(key, best.raw[key])})`;
  };
  const lines = [];
  const bestBasis = pickBasis();
  if (bestBasis) lines.push(`выше BASIS-балл — ${bestBasis.name} (${bestBasis.basis})`);
  const y = pickMetric("div_yield", "дивдоходность"); if (y) lines.push(y);
  const r = pickMetric("roe", "ROE"); if (r) lines.push(r);
  if (!lines.length) return null;
  return (
    <div className="bs-callout" style={{ marginTop: 16 }}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
        <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8Z" />
      </svg>
      <p><span className="bs-tag-judgment" style={{ marginRight: 8 }}>суждение Basis</span>{lines.join(" · ")}.</p>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════════
// ВЕРДИКТ «Точки расхождения» — хедлайн экрана для ровно 2 бумаг (самый
// частый реальный сценарий — «дошёл до 2 похожих кандидатов, надо выбрать»,
// по продуктовому разбору 2026-07-12). Дамбл-плот на каждую реально
// расходящуюся ось (оси, где значения почти равны — не показываем вообще,
// не только приглушаем, чтобы не плодить шум) + связный текст-размен вместо
// перечисления «лучших по метрике» + предупреждение о сопоставимости секторов.
// ═════════════════════════════════════════════════════════════════════════
const CMP_AXES = [
  { key: "pe", label: "Оценка (P / E)", dir: "low", unit: "×", dec: 1 },
  { key: "roe", label: "Качество (ROE)", dir: "high", unit: "%", dec: 1 },
  { key: "div_yield", label: "Дивдоходность", dir: "high", unit: "%", dec: 1 },
  { key: "nd_ebitda", label: "Долговая нагрузка (чист. долг / EBITDA)", dir: "low", unit: "×", dec: 1 },
];
const DIVERGE_THRESHOLD = 0.08; // относительный разрыв меньше — считаем «примерно равны», ось не показываем

function _cmpFmtAxis(v, unit, dec) {
  return v.toLocaleString("ru-RU", { maximumFractionDigits: dec, minimumFractionDigits: 0 }) + unit;
}

const CMP_AXIS_PHRASE = {
  pe: (leader, v1, v2) => `${leader} дешевле по мультипликатору (P/E ${v1} против ${v2})`,
  roe: (leader, v1, v2) => `${leader} выше по рентабельности капитала (ROE ${v1} против ${v2})`,
  div_yield: (leader, v1, v2) => `${leader} даёт выше дивдоходность (${v1} против ${v2})`,
  nd_ebitda: (leader, v1, v2) => `${leader} несёт меньшую долговую нагрузку (чист. долг/EBITDA ${v1} против ${v2})`,
};

function CompareVerdict({ items }) {
  if (items.length !== 2) return null;
  const [a, b] = items;

  const axes = CMP_AXES
    .map((ax) => {
      const va = a.raw?.[ax.key], vb = b.raw?.[ax.key];
      if (va == null || vb == null) return null;
      const scale = Math.max(Math.abs(va), Math.abs(vb)) || 1;
      const relGap = Math.abs(va - vb) / scale;
      if (relGap < DIVERGE_THRESHOLD) return null;
      const lo = Math.min(va, vb), hi = Math.max(va, vb);
      const span = hi - lo || 1;
      const posFor = (v) => 18 + ((v - lo) / span) * 64; // 18%..82%
      const leaderIsA = ax.dir === "high" ? va > vb : va < vb;
      return { ...ax, va, vb, posA: posFor(va), posB: posFor(vb), leaderIsA, relGap };
    })
    .filter(Boolean)
    .sort((x, y) => y.relGap - x.relGap)
    .slice(0, 4);

  if (!axes.length) return null;

  const aLines = axes.filter((ax) => ax.leaderIsA).map((ax) => CMP_AXIS_PHRASE[ax.key](a.name, _cmpFmtAxis(ax.va, ax.unit, ax.dec), _cmpFmtAxis(ax.vb, ax.unit, ax.dec)));
  const bLines = axes.filter((ax) => !ax.leaderIsA).map((ax) => CMP_AXIS_PHRASE[ax.key](b.name, _cmpFmtAxis(ax.vb, ax.unit, ax.dec), _cmpFmtAxis(ax.va, ax.unit, ax.dec)));
  const sentences = [aLines.length ? aLines.join(", ") + "." : null, bLines.length ? bLines.join(", ") + "." : null].filter(Boolean);

  const sameSector = a.sector && b.sector && a.sector === b.sector;

  return (
    <div className="cmp-verdict">
      <div className="cmp-verdict-top">
        <div>
          <div className="cmp-verdict-eyebrow">{sameSector ? `Обе — ${a.sector.toLowerCase()}` : "Разные секторы"}</div>
          <h2 className="cmp-verdict-title">Точки расхождения</h2>
        </div>
        <span className="bs-tag-judgment">суждение Basis</span>
      </div>

      <div className="cmp-verdict-legend">
        <span className="cmp-verdict-legend-item"><span className="cmp-verdict-legend-dot" style={{ background: "var(--cat-1)" }} />{a.name}</span>
        <span className="cmp-verdict-legend-item"><span className="cmp-verdict-legend-dot" style={{ background: "var(--cat-2)" }} />{b.name}</span>
      </div>

      <div className="cmp-axes">
        {axes.map((ax) => (
          <div key={ax.key}>
            <div className="cmp-axis-label">{ax.label}</div>
            <div className="cmp-axis-plot">
              <div className="cmp-axis-track" />
              <div className="cmp-axis-connector" style={{ left: `${Math.min(ax.posA, ax.posB)}%`, width: `${Math.abs(ax.posA - ax.posB)}%` }} />
              <div className={"cmp-axis-val cmp-axis-val--a" + (ax.posA < ax.posB ? " cmp-axis-val--below" : "")} style={{ left: `${ax.posA}%` }}>{_cmpFmtAxis(ax.va, ax.unit, ax.dec)}</div>
              <div className="cmp-axis-dot cmp-axis-dot--a" style={{ left: `${ax.posA}%` }} title={`${a.name}: ${_cmpFmtAxis(ax.va, ax.unit, ax.dec)}`} />
              <div className={"cmp-axis-val cmp-axis-val--b" + (ax.posB < ax.posA ? " cmp-axis-val--below" : "")} style={{ left: `${ax.posB}%` }}>{_cmpFmtAxis(ax.vb, ax.unit, ax.dec)}</div>
              <div className="cmp-axis-dot cmp-axis-dot--b" style={{ left: `${ax.posB}%` }} title={`${b.name}: ${_cmpFmtAxis(ax.vb, ax.unit, ax.dec)}`} />
            </div>
          </div>
        ))}
      </div>

      {sentences.length > 0 && (
        <div className="cmp-verdict-text">
          {sentences.map((s, i) => <p key={i} style={{ margin: i === 0 ? 0 : "8px 0 0" }}><b>{s}</b></p>)}
          {" "}Не сигнал «купить дешевле/дороже» — структурный размен между показателями, решение остаётся за вами.
        </div>
      )}

      <div className="cmp-comparability">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16h.01" /></svg>
        {sameSector ? (
          <span><b>Сопоставимо напрямую</b> — {a.name} и {b.name} из одного сектора ({a.sector}), мультипликаторы считаются по одной методике.</span>
        ) : (
          <span><b>Разные секторы</b> — {a.name} ({a.sector || "сектор не указан"}) и {b.name} ({b.sector || "сектор не указан"}). Мультипликаторы (P/E, EV/EBITDA и т.п.) между разными секторами напрямую не сопоставимы — разная структура бизнеса и капитала.</span>
        )}
      </div>
    </div>
  );
}

export default function CompareView({ onOpenCompany }) {
  const apiUrl = apiBase();
  const [selected, setSelected] = usePersistedState("compare.tickers", ["SBER", "GAZP"]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [priceData, setPriceData] = useState({});
  const [priceLoading, setPriceLoading] = useState(false);
  const [liveQuotes, setLiveQuotes] = useState({});
  const [finData, setFinData] = useState({});
  const [finLoading, setFinLoading] = useState(false);
  const [yearlyMetric, setYearlyMetric] = useState("revenue_growth");
  const [yearlyChartType, setYearlyChartType] = useState("bar");
  const [pricePeriod, setPricePeriod] = useState("1y");
  const [priceMode, setPriceMode] = useState("rel"); // rel = %, abs = ₽
  const [expandMetrics, setExpandMetrics] = useState(false);
  const yearlyCardRef = useRef(null);
  const openYearly = (key) => {
    setYearlyMetric(key);
    yearlyCardRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  useEffect(() => {
    fetch(`${apiUrl}/api/screener/scored?universe=all`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { setRows(Array.isArray(d?.rows) ? d.rows : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [apiUrl]);

  const byTicker = useMemo(() => {
    const m = {};
    rows.forEach((r) => { m[r.ticker] = r; });
    return m;
  }, [rows]);

  const items = selected.map((t) => byTicker[t]).filter(Boolean);
  const addTicker = (t) => setSelected((s) => (s.includes(t) || s.length >= COMPARE_MAX ? s : [...s, t]));
  const removeTicker = (t) => setSelected((s) => s.filter((x) => x !== t));
  const tickersKey = selected.join(",");

  useEffect(() => {
    fetch(`${apiUrl}/api/quotes/realtime`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setLiveQuotes(d))
      .catch(() => {});
  }, [apiUrl, tickersKey]);

  useEffect(() => {
    if (!items.length) { setPriceData({}); return; }
    setPriceLoading(true);
    let alive = true;
    const days = (CMP_PRICE_PERIODS.find((p) => p.id === pricePeriod) || CMP_PRICE_PERIODS[3]).days;
    Promise.all(
      items.map((it) =>
        fetch(`${apiUrl}/api/companies/by-ticker/${it.ticker}/quotes/history?days=${days}`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    ).then((results) => {
      if (!alive) return;
      const out = {};
      results.forEach((d, i) => { if (d?.points?.length) out[items[i].ticker] = d.points; });
      setPriceData(out);
      setPriceLoading(false);
    });
    return () => { alive = false; };
    // rows в зависимостях намеренно: items вычисляется из rows (грузится
    // асинхронно ПОСЛЕ монтирования) — без этого эффект успевал отработать
    // и выйти по пустому items ДО того, как rows вообще подгрузился, и
    // повторно уже не срабатывал (график цены не подтягивался).
  }, [tickersKey, apiUrl, rows, pricePeriod]); // eslint-disable-line

  useEffect(() => {
    if (!items.length) { setFinData({}); return; }
    setFinLoading(true);
    let alive = true;
    Promise.all(
      items.map((it) =>
        fetch(`${apiUrl}/api/companies/by-ticker/${it.ticker}/financials`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
      )
    ).then((results) => {
      if (!alive) return;
      const out = {};
      results.forEach((d, i) => { if (d?.metrics_timeseries) out[items[i].ticker] = d; });
      setFinData(out);
      setFinLoading(false);
    });
    return () => { alive = false; };
  }, [tickersKey, apiUrl, rows]); // eslint-disable-line

  const yearlySeries = useMemo(() => {
    const years = Array.from(
      new Set(items.flatMap((it) => finData[it.ticker]?.meta?.fiscal_years || []))
    ).sort((a, b) => a - b);
    return items
      .map((it, i) => {
        const fin = finData[it.ticker];
        const arr = fin?.metrics_timeseries?.[yearlyMetric];
        const fy = fin?.meta?.fiscal_years;
        if (!arr || !fy) return null;
        const byYear = {};
        fy.forEach((y, idx) => { byYear[y] = arr[idx]; });
        return {
          name: it.name,
          color: CMP_CAT_COLORS[i % CMP_CAT_COLORS.length],
          points: years.map((y) => ({ as_of: String(y), value: byYear[y] ?? null })),
        };
      })
      .filter(Boolean);
  }, [items, finData, yearlyMetric]);

  const priceSeries = useMemo(
    () =>
      items
        .filter((it) => priceData[it.ticker]?.length)
        .map((it, i) => {
          const pts = priceData[it.ticker].filter((p) => p.close != null);
          const base = pts[0]?.close;
          return {
            name: it.name,
            color: CMP_CAT_COLORS[i % CMP_CAT_COLORS.length],
            points: pts.map((p) => ({
              as_of: p.date,
              value: priceMode === "abs" ? p.close : base ? (p.close / base - 1) * 100 : null,
            })),
          };
        }),
    [items, priceData, priceMode]
  );

  if (loading) {
    return <div className="tw-flex tw-items-center tw-justify-center tw-py-24 tw-text-text-tertiary tw-text-[18px] tw-animate-pulse">Загружаем данные для сравнения...</div>;
  }

  return (
    <div className="cmp-screen">
      <h1 className="tw-text-[28px] tw-font-display tw-font-medium tw-text-text-primary tw-mb-1">Сравнение активов</h1>
      <p className="tw-text-[13px] tw-text-text-tertiary tw-mb-4">
        До {COMPARE_MAX} акций рядом — метрики, оценка, динамика цены. Инструмент сопоставления, не рекомендация.
      </p>
      <CompareSearchAdd pool={rows} selected={selected} onAdd={addTicker} disabled={selected.length >= COMPARE_MAX} />

      {items.length === 0 ? (
        <div className="tw-py-16 tw-text-center tw-text-text-tertiary">Добавьте хотя бы одну компанию, чтобы начать сравнение.</div>
      ) : (
        <>
          <div className="cmp-cards">
            {items.map((it) => {
              const q = liveQuotes[it.ticker];
              const chg = q ? q.change_pct : null;
              const px = q?.price ?? it.price;
              return (
                <div key={it.ticker} className="cmp-card">
                  <button className="cmp-card-x" onClick={() => removeTicker(it.ticker)} aria-label={`Убрать ${it.ticker}`}>×</button>
                  <CompanyLogo ticker={it.ticker} name={it.name} size={36} />
                  <button className="cmp-card-name" onClick={() => onOpenCompany && onOpenCompany(it.ticker)}>{it.name}</button>
                  <span className="cmp-card-tk">{it.ticker}</span>
                  <span className="cmp-card-px">{px != null ? px.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—"} ₽</span>
                  {chg != null && (
                    <span className={"cmp-card-chg " + (chg > 0 ? "cmp-pos" : chg < 0 ? "cmp-neg" : "")}>
                      {chg > 0 ? "▲" : chg < 0 ? "▼" : "▬"} {Math.abs(chg).toFixed(2)}%
                    </span>
                  )}
                  <span className="cmp-card-cap">{it.market_cap != null ? fmtStockMetric("mcap", it.market_cap) : "—"}</span>
                </div>
              );
            })}
          </div>

          <Card header="Динамика цены" style={{ marginTop: 20 }}>
            <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3 tw-mb-3">
              <div className="tw-flex tw-gap-1" role="group" aria-label="Период графика">
                {CMP_PRICE_PERIODS.map((p) => (
                  <CmpPillButton key={p.id} active={pricePeriod === p.id} onClick={() => setPricePeriod(p.id)}>{p.label}</CmpPillButton>
                ))}
              </div>
              <div className="tw-flex tw-gap-1" role="group" aria-label="В рублях или нормализовано">
                <CmpPillButton active={priceMode === "rel"} onClick={() => setPriceMode("rel")}>% от начала периода</CmpPillButton>
                <CmpPillButton active={priceMode === "abs"} onClick={() => setPriceMode("abs")}>В рублях</CmpPillButton>
              </div>
            </div>
            {priceLoading ? (
              <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Загружаем историю цен...</div>
            ) : priceSeries.length ? (
              <>
                <div className="tw-flex tw-flex-wrap tw-gap-3 tw-mb-2 tw-text-[12px] tw-text-text-secondary">
                  {priceSeries.map((s) => (
                    <span key={s.name} className="tw-inline-flex tw-items-center tw-gap-1.5">
                      <i style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: s.color }} />
                      {s.name}
                    </span>
                  ))}
                </div>
                <ObsLineChart series={priceSeries} viewW={1000} viewH={280} unit={priceMode === "abs" ? "₽" : "%"} />
                {priceMode === "abs" && (
                  <p className="tw-text-[11px] tw-text-text-tertiary tw-mt-2">
                    В рублях бумаги с сильно разной ценой акции визуально сжимаются к одной линии — для сравнения темпа роста удобнее «% от начала периода».
                  </p>
                )}
              </>
            ) : (
              <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Нет данных истории цены.</div>
            )}
          </Card>

          <div ref={yearlyCardRef}>
          <Card header="Метрика по годам (из отчётности)" style={{ marginTop: 20 }}>
            <div className="tw-flex tw-flex-wrap tw-items-center tw-justify-between tw-gap-3 tw-mb-3">
              <div className="tw-flex tw-flex-wrap tw-gap-1.5">
                {CMP_YEARLY_METRICS.map((m) => (
                  <button
                    key={m.key}
                    type="button"
                    onClick={() => setYearlyMetric(m.key)}
                    className={`tw-px-2.5 tw-py-1 tw-text-[12px] tw-rounded-pill tw-border tw-cursor-pointer tw-transition-colors ${
                      yearlyMetric === m.key
                        ? "tw-border-accent tw-bg-accent-soft tw-text-accent"
                        : "tw-border-border-subtle tw-text-text-secondary hover:tw-border-accent"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
              <div className="tw-flex tw-gap-1" role="group" aria-label="Тип графика">
                <CmpPillButton active={yearlyChartType === "bar"} onClick={() => setYearlyChartType("bar")}>Столбцы</CmpPillButton>
                <CmpPillButton active={yearlyChartType === "line"} onClick={() => setYearlyChartType("line")}>Линия</CmpPillButton>
              </div>
            </div>
            {finLoading ? (
              <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Загружаем отчётность...</div>
            ) : yearlySeries.length ? (
              <>
                <div className="tw-flex tw-flex-wrap tw-gap-3 tw-mb-2 tw-text-[12px] tw-text-text-secondary">
                  {yearlySeries.map((s) => (
                    <span key={s.name} className="tw-inline-flex tw-items-center tw-gap-1.5">
                      <i style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: s.color }} />
                      {s.name}
                    </span>
                  ))}
                </div>
                {yearlyChartType === "bar" ? (
                  <CompareBarChart series={yearlySeries} viewW={1000} viewH={260} unit={CMP_YEARLY_METRICS.find((m) => m.key === yearlyMetric)?.unit || ""} />
                ) : (
                  <ObsLineChart series={yearlySeries} viewW={1000} viewH={260} unit={CMP_YEARLY_METRICS.find((m) => m.key === yearlyMetric)?.unit || ""} />
                )}
              </>
            ) : (
              <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Нет данных отчётности по выбранной метрике.</div>
            )}
          </Card>
          </div>

          {items.length === 2 ? <CompareVerdict items={items} /> : <CompareSynthesis items={items} />}

          <div className="cmp-table-wrap" style={{ marginTop: 20 }}>
            <table className="cmp-table">
              <thead>
                <tr>
                  <th className="cmp-th-metric">Метрика</th>
                  {items.map((it) => (
                    <th key={it.ticker}>
                      <div className="cmp-th-company">
                        <CompanyLogo ticker={it.ticker} name={it.name} size={20} />
                        {it.name}
                      </div>
                    </th>
                  ))}
                  <th className="cmp-th-trend">Тренд, годы</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Справедливая цена<ScreenerInfoTip text={FAIR_VALUE_HINT} /></td>
                  {items.map((it) => <td key={it.ticker}>{fmtStockMetric("fair_value", it.fair_value)}</td>)}
                  <td className="cmp-trend-cell"><span className="cmp-trend-empty">—</span></td>
                </tr>
                <tr>
                  <td>Потенциал (апсайд)</td>
                  {items.map((it) => {
                    const up = it.fair_value && it.price ? (it.fair_value / it.price - 1) * 100 : null;
                    return (
                      <td key={it.ticker} className={up == null ? "" : up >= 0 ? "cmp-pos" : "cmp-neg"}>
                        {up == null ? "—" : (up >= 0 ? "+" : "") + up.toFixed(0) + "%"}
                      </td>
                    );
                  })}
                  <td className="cmp-trend-cell"><span className="cmp-trend-empty">—</span></td>
                </tr>
                <tr>
                  <td>BASIS-балл</td>
                  {items.map((it) => (
                    <td key={it.ticker}>
                      {it.basis != null ? <span className="cmp-score" style={{ background: cmpScoreColor(it.basis) }}>{it.basis}</span> : "—"}
                    </td>
                  ))}
                  <td className="cmp-trend-cell"><span className="cmp-trend-empty">—</span></td>
                </tr>
                {CMP_CURATED.map((row) => {
                  const diverges = cmpRowDiverges(items, row, finData);
                  return (
                    <tr key={row.key} className={diverges === true ? "cmp-diverges" : diverges === false ? "cmp-equal" : ""}>
                      <td>{row.label}</td>
                      {items.map((it) => (
                        <td key={it.ticker} className="cmp-cellval">{_cmpRowFmt(row, _cmpRowValue(it, row, finData))}</td>
                      ))}
                      <td className="cmp-trend-cell">
                        <CmpTrendSpark items={items} finData={finData} trendKey={row.trendKey} label={row.label} onOpen={() => openYearly(row.trendKey)} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <button type="button" className="cmp-expand-toggle" onClick={() => setExpandMetrics((v) => !v)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" style={{ transform: expandMetrics ? "rotate(180deg)" : undefined, transition: "transform .15s" }}><path d="M6 9l6 6 6-6" /></svg>
            {expandMetrics ? "Свернуть" : "Развернуть все метрики"}
          </button>

          {expandMetrics && (
            <div className="cmp-table-wrap" style={{ marginTop: 12 }}>
              <table className="cmp-table">
                <thead>
                  <tr>
                    <th className="cmp-th-metric">Метрика</th>
                    {items.map((it) => (
                      <th key={it.ticker}>
                        <div className="cmp-th-company">
                          <CompanyLogo ticker={it.ticker} name={it.name} size={20} />
                          {it.name}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {STOCK_METRIC_GROUPS.map((g) => (
                    <React.Fragment key={g}>
                      <tr className="cmp-group-row"><td colSpan={items.length + 1}>{g}</td></tr>
                      {Object.keys(STOCK_METRICS).filter((k) => STOCK_METRICS[k].group === g && !CMP_CURATED.some((c) => c.key === k)).map((k) => {
                        const bestT = CMP_UNAMBIGUOUS.includes(k) ? cmpBestTicker(items, k, STOCK_METRICS[k].dir) : null;
                        return (
                          <tr key={k}>
                            <td>{STOCK_METRICS[k].label}{STOCK_METRICS[k].hint && <ScreenerInfoTip text={STOCK_METRICS[k].hint} />}</td>
                            {items.map((it) => {
                              const v = k === "mcap" ? it.market_cap : it.raw?.[k];
                              const pct = it.percentiles?.[k];
                              return (
                                <td key={it.ticker} className={bestT === it.ticker ? "cmp-best" : ""}>
                                  <span className="cmp-cellval">{fmtStockMetric(k, v)}</span>
                                  {pct != null && k !== "mcap" && (
                                    <span className="cmp-cellbar"><i className={pct >= 80 ? "strong" : ""} style={{ width: Math.max(4, pct) + "%" }} /></span>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  ))}
                  {CMP_FIN_GROUPS.map((g) => {
                    const keys = Object.keys(CMP_FIN_METRICS).filter((k) => CMP_FIN_METRICS[k].group === g && !CMP_CURATED.some((c) => c.key === k));
                    if (!keys.length) return null;
                    return (
                      <React.Fragment key={g}>
                        <tr className="cmp-group-row"><td colSpan={items.length + 1}>{g}</td></tr>
                        {keys.map((k) => {
                          const bestT = CMP_FIN_METRICS[k].high ? cmpFinBestTicker(finData, items, k) : null;
                          return (
                            <tr key={k}>
                              <td>{CMP_FIN_METRICS[k].label}</td>
                              {items.map((it) => {
                                const v = _lastNN(finData[it.ticker]?.metrics_timeseries?.[k]);
                                return (
                                  <td key={it.ticker} className={bestT === it.ticker ? "cmp-best" : ""}>
                                    <span className="cmp-cellval">{finLoading && !finData[it.ticker] ? "…" : fmtFinMetric(k, v)}</span>
                                  </td>
                                );
                              })}
                            </tr>
                          );
                        })}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          <p className="tw-text-[11.5px] tw-text-text-tertiary tw-mt-2 tw-max-w-[70ch]">
            Приглушено — где значения между бумагами почти не различаются; полоской слева отмечены строки
            с реальным расхождением. Зелёным — лучшее значение там, где оно однозначно (дивдоходность, ROE,
            EBITDA-маржа, FCF-доходность и т.д.) — мультипликаторы (P/E, EV/EBITDA, P/B, P/S) без подсветки
            «лучше/хуже»: низкое значение не всегда означает недооценку. Значок в колонке «Тренд» открывает
            график метрики по годам выше. Метрики «из отчётности» — последнее известное годовое значение
            (не у всех профилей заполнены все поля — банки и обычные компании считаются по разным метрикам маржи).
          </p>
        </>
      )}
    </div>
  );
}
