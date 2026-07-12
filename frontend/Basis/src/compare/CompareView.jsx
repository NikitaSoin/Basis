// Сравнение активов (2026-07-11, восстановлено 2026-07-12 после потери в App.js
// при рефакторинге на отдельные файлы — см. docs/work-journal.md). Конкурентный
// разбор Инвестминт/ПроФинанс: сопоставление бумаг бок о бок по ключевым метрикам
// + нормализованная динамика цены. Инструмент сопоставления, НЕ рекомендация.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "../design/primitives";
import { CompanyLogo } from "../design/CompanyLogo";
import {
  METRICS as STOCK_METRICS,
  GROUPS as STOCK_METRIC_GROUPS,
  InfoTip as ScreenerInfoTip,
  fmtMetric as fmtStockMetric,
  FAIR_VALUE_HINT,
} from "../screener/ScreenerNeo";

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

// Компактный self-contained мультисерийный линейный график (замена утраченного
// ObsLineChart) — только то, что нужно для нормализованной динамики цены.
function CompareLineChart({ series, viewW = 1000, viewH = 280, unit = "%" }) {
  const pad = { top: 12, right: 12, bottom: 24, left: 44 };
  const allPoints = series.flatMap((s) => s.points.filter((p) => p.value != null));
  if (!allPoints.length) return null;
  const dates = Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.as_of)))).sort();
  const vals = allPoints.map((p) => p.value);
  let min = Math.min(...vals, 0), max = Math.max(...vals, 0);
  if (min === max) { min -= 1; max += 1; }
  const spanY = max - min;
  const spanX = Math.max(1, dates.length - 1);
  const xIdx = new Map(dates.map((d, i) => [d, i]));
  const x = (i) => pad.left + (i / spanX) * (viewW - pad.left - pad.right);
  const y = (v) => pad.top + (1 - (v - min) / spanY) * (viewH - pad.top - pad.bottom);
  const zeroY = y(0);
  const yTicks = [min, min + spanY / 2, max];
  return (
    <svg width="100%" viewBox={`0 0 ${viewW} ${viewH}`} role="img" aria-label="Динамика цены">
      {yTicks.map((t, i) => (
        <g key={i}>
          <line x1={pad.left} x2={viewW - pad.right} y1={y(t)} y2={y(t)} stroke="var(--border-subtle)" strokeWidth="1" />
          <text x={pad.left - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--text-tertiary)" fontFamily="var(--font-mono)">
            {t.toFixed(0)}{unit}
          </text>
        </g>
      ))}
      {min < 0 && max > 0 && (
        <line x1={pad.left} x2={viewW - pad.right} y1={zeroY} y2={zeroY} stroke="var(--text-tertiary)" strokeWidth="1" strokeDasharray="3,3" />
      )}
      {series.map((s) => {
        const pts = s.points.filter((p) => p.value != null && xIdx.has(p.as_of));
        if (pts.length < 2) return null;
        const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(xIdx.get(p.as_of)).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
        return <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth="1.75" strokeLinejoin="round" strokeLinecap="round" />;
      })}
    </svg>
  );
}

export default function CompareView({ onOpenCompany }) {
  const apiUrl = apiBase();
  const [selected, setSelected] = usePersistedState("compare.tickers", ["SBER", "GAZP"]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [priceData, setPriceData] = useState({});
  const [priceLoading, setPriceLoading] = useState(false);

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
    if (!items.length) { setPriceData({}); return; }
    setPriceLoading(true);
    let alive = true;
    Promise.all(
      items.map((it) =>
        fetch(`${apiUrl}/api/companies/by-ticker/${it.ticker}/quotes/history?days=365`)
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
  }, [tickersKey, apiUrl]); // eslint-disable-line

  const priceSeries = useMemo(
    () =>
      items
        .filter((it) => priceData[it.ticker]?.length)
        .map((it, i) => {
          const pts = priceData[it.ticker].filter((p) => p.close != null);
          const base = pts[0]?.close;
          return {
            name: it.ticker,
            color: CMP_CAT_COLORS[i % CMP_CAT_COLORS.length],
            points: pts.map((p) => ({ as_of: p.date, value: base ? (p.close / base - 1) * 100 : null })),
          };
        }),
    [items, priceData]
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
            {items.map((it) => (
              <div key={it.ticker} className="cmp-card">
                <button className="cmp-card-x" onClick={() => removeTicker(it.ticker)} aria-label={`Убрать ${it.ticker}`}>×</button>
                <CompanyLogo ticker={it.ticker} name={it.name} size={36} />
                <button className="cmp-card-name" onClick={() => onOpenCompany && onOpenCompany(it.ticker)}>{it.name}</button>
                <span className="cmp-card-tk">{it.ticker}</span>
                <span className="cmp-card-px">{it.price != null ? it.price.toLocaleString("ru-RU", { maximumFractionDigits: 2 }) : "—"} ₽</span>
              </div>
            ))}
          </div>

          <Card header="Динамика цены за год (нормализовано к 0%)" style={{ marginTop: 20 }}>
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
                <CompareLineChart series={priceSeries} viewW={1000} viewH={280} unit="%" />
              </>
            ) : (
              <div className="tw-py-8 tw-text-text-tertiary tw-text-[13px]">Нет данных истории цены.</div>
            )}
          </Card>

          <div className="cmp-table-wrap" style={{ marginTop: 20 }}>
            <table className="cmp-table">
              <thead>
                <tr>
                  <th className="cmp-th-metric">Метрика</th>
                  {items.map((it) => <th key={it.ticker}>{it.ticker}</th>)}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Справедливая цена<ScreenerInfoTip text={FAIR_VALUE_HINT} /></td>
                  {items.map((it) => <td key={it.ticker}>{fmtStockMetric("fair_value", it.fair_value)}</td>)}
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
                </tr>
                <tr>
                  <td>BASIS-балл</td>
                  {items.map((it) => <td key={it.ticker}>{it.basis ?? "—"}</td>)}
                </tr>
                {STOCK_METRIC_GROUPS.map((g) => (
                  <React.Fragment key={g}>
                    <tr className="cmp-group-row"><td colSpan={items.length + 1}>{g}</td></tr>
                    {Object.keys(STOCK_METRICS).filter((k) => STOCK_METRICS[k].group === g).map((k) => (
                      <tr key={k}>
                        <td>{STOCK_METRICS[k].label}{STOCK_METRICS[k].hint && <ScreenerInfoTip text={STOCK_METRICS[k].hint} />}</td>
                        {items.map((it) => <td key={it.ticker}>{fmtStockMetric(k, k === "mcap" ? it.market_cap : it.raw?.[k])}</td>)}
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
