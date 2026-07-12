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

// Короткий синтез над таблицей — «вердикт поверх данных» по дизайн-конституции
// Basis (голая таблица без интерпретации не считается готовым экраном).
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
    return `выше ${label} — ${best.ticker} (${fmtStockMetric(key, best.raw[key])})`;
  };
  const lines = [];
  const bestBasis = pickBasis();
  if (bestBasis) lines.push(`выше BASIS-балл — ${bestBasis.ticker} (${bestBasis.basis})`);
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

export default function CompareView({ onOpenCompany }) {
  const apiUrl = apiBase();
  const [selected, setSelected] = usePersistedState("compare.tickers", ["SBER", "GAZP"]);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [priceData, setPriceData] = useState({});
  const [priceLoading, setPriceLoading] = useState(false);
  const [liveQuotes, setLiveQuotes] = useState({});

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

          <CompareSynthesis items={items} />

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
                  {items.map((it) => (
                    <td key={it.ticker}>
                      {it.basis != null ? <span className="cmp-score" style={{ background: cmpScoreColor(it.basis) }}>{it.basis}</span> : "—"}
                    </td>
                  ))}
                </tr>
                {STOCK_METRIC_GROUPS.map((g) => (
                  <React.Fragment key={g}>
                    <tr className="cmp-group-row"><td colSpan={items.length + 1}>{g}</td></tr>
                    {Object.keys(STOCK_METRICS).filter((k) => STOCK_METRICS[k].group === g).map((k) => {
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
              </tbody>
            </table>
          </div>
          <p className="tw-text-[11.5px] tw-text-text-tertiary tw-mt-2 tw-max-w-[70ch]">
            Зелёным — лучшее значение среди сравниваемых бумаг (только дивдоходность, ROE, EBITDA-маржа,
            FCF-доходность). Полоска под числом — позиция относительно всего рынка (перцентиль Basis).
            Мультипликаторы (P/E, EV/EBITDA и т.д.) — без подсветки «лучше/хуже»: низкое значение не всегда
            означает недооценку.
          </p>
        </>
      )}
    </div>
  );
}
