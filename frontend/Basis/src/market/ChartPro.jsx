// =============================================================
// ChartPro — «нормальный» ценовой график (задание владельца 2026-07-17:
// «хотя бы часть функционала как у TradingView/ProFinance»).
//
// Умеет: таймфреймы 1м/5м/15м/1ч/4ч/Д/Н/М; японские свечи ↔ линия;
// скользящие средние (пресеты EMA 9/20/50/100/200 + своя MA/EMA с любым
// периодом); полосы Боллинджера (20, 2σ); осциллятор RSI(14) отдельной
// панелью. Движок — lightweight-charts v5 (open-source библиотека
// TradingView, Apache-2.0; их атрибуция-логотип в углу оставлена).
//
// Данные — /api/market/candles/{asset_class}/{secid}?tf= (MOEX ISS,
// см. backend/app/services/candles.py). Время в свечах — биржевое
// (московское) как epoch-«как будто UTC»: шкала показывает время биржи,
// а не локальное время браузера (стандартный приём lightweight-charts).
//
// Индикаторы считаются на клиенте (EMA/SMA/σ/RSI-Уайлдер) — это чистая
// математика по уже загруженному ряду, бэкенд не нужен.
// Настройки (таймфрейм, вид, индикаторы) — в localStorage, общие для
// всех графиков: пользователь настроил один раз — везде так.
// =============================================================
import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { createChart, CandlestickSeries, LineSeries } from "lightweight-charts";
import "../styles/chartpro.css";

const apiUrl = process.env.REACT_APP_API_URL || "http://localhost:8000";

const TFS = [
  ["1m", "1м"], ["5m", "5м"], ["15m", "15м"], ["1h", "1ч"],
  ["4h", "4ч"], ["1d", "Д"], ["1w", "Н"], ["1M", "М"],
];
const INTRADAY = new Set(["1m", "5m", "15m", "1h", "4h"]);
const EMA_PRESETS = [9, 20, 50, 100, 200];

// Палитра оверлеев — только цвета данных из канона (хардкода нет: значения
// читаются из CSS-токенов в рантайме, см. _cssColor ниже).
const MA_TOKEN_BY_PERIOD = {
  9: "--bs-copper", 20: "--bs-estimate", 50: "--cc-violet",
  100: "--cc-amber", 200: "--cc-info",
};
const CUSTOM_TOKENS = ["--bs-up", "--bs-down", "--cc-violet", "--cc-info", "--cc-amber"];

/* ---------- индикаторная математика ---------- */

function sma(candles, period) {
  const out = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].c;
    if (i >= period) sum -= candles[i - period].c;
    if (i >= period - 1) out.push({ time: candles[i].t, value: sum / period });
  }
  return out;
}

function ema(candles, period) {
  const out = [];
  const k = 2 / (period + 1);
  let prev = null;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i].c;
    prev = prev === null ? c : c * k + prev * (1 - k);
    if (i >= period - 1) out.push({ time: candles[i].t, value: prev });
  }
  return out;
}

function bollinger(candles, period = 20, mult = 2) {
  const mid = [], up = [], low = [];
  let sum = 0, sumSq = 0;
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i].c;
    sum += c; sumSq += c * c;
    if (i >= period) {
      const o = candles[i - period].c;
      sum -= o; sumSq -= o * o;
    }
    if (i >= period - 1) {
      const mean = sum / period;
      const sd = Math.sqrt(Math.max(0, sumSq / period - mean * mean));
      mid.push({ time: candles[i].t, value: mean });
      up.push({ time: candles[i].t, value: mean + mult * sd });
      low.push({ time: candles[i].t, value: mean - mult * sd });
    }
  }
  return { mid, up, low };
}

function rsi(candles, period = 14) {
  // Классический RSI со сглаживанием Уайлдера.
  const out = [];
  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i < candles.length; i++) {
    const d = candles[i].c - candles[i - 1].c;
    const gain = Math.max(d, 0), loss = Math.max(-d, 0);
    if (i <= period) {
      avgGain += gain / period; avgLoss += loss / period;
      if (i === period) {
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        out.push({ time: candles[i].t, value: 100 - 100 / (1 + rs) });
      }
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      out.push({ time: candles[i].t, value: 100 - 100 / (1 + rs) });
    }
  }
  return out;
}

/* ---------- настройки (общие на все графики) ---------- */

const PREFS_KEY = "basis_chartpro";
const DEFAULT_PREFS = {
  tf: "1d", kind: "candles",           // kind: candles | line
  emas: [],                            // включённые пресеты EMA, напр. [20, 50]
  customs: [],                         // [{type:"ema"|"sma", period:34}]
  bollinger: false, rsi: false,
};

function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY));
    return p && typeof p === "object" ? { ...DEFAULT_PREFS, ...p } : { ...DEFAULT_PREFS };
  } catch { return { ...DEFAULT_PREFS }; }
}

/* ---------- цвета из CSS-токенов (тема-зависимые) ---------- */

function _cssColor(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

function readColors(el) {
  return {
    text: _cssColor(el, "--cc-ink-3", "#857D6F"),
    grid: _cssColor(el, "--cc-chart-grid", "rgba(20,18,14,0.06)"),
    border: _cssColor(el, "--cc-line", "rgba(20,18,14,0.10)"),
    up: _cssColor(el, "--bs-up", "#3E8464"),
    down: _cssColor(el, "--bs-down", "#B8503F"),
    accent: _cssColor(el, "--cc-accent", "#C97A4A"),
    ink3: _cssColor(el, "--cc-ink-3", "#857D6F"),
  };
}

/* ---------- компонент ---------- */

export default function ChartPro({ assetClass, secid, height = 380, className = "" }) {
  const [prefs, setPrefs] = useState(loadPrefs);
  const [data, setData] = useState(null);      // {candles, last, change_pct} | null
  const [state, setState] = useState("loading"); // loading | ready | empty | error
  const [ddOpen, setDdOpen] = useState(false);
  const [customType, setCustomType] = useState("ema");
  const [customPeriod, setCustomPeriod] = useState("");

  const wrapRef = useRef(null);
  const chartRef = useRef(null);   // {chart, main, overlays:[], rsiSeries}
  const ddRef = useRef(null);

  const setPref = useCallback((patch) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      try { localStorage.setItem(PREFS_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  /* -- загрузка свечей (+тихий автообновляльщик для интрадея) -- */
  useEffect(() => {
    if (!secid) return;
    let alive = true;
    const load = (silent) => {
      if (!silent) setState("loading");
      fetch(`${apiUrl}/api/market/candles/${assetClass}/${secid}?tf=${prefs.tf}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => {
          if (!alive) return;
          if (d && d.candles && d.candles.length) { setData(d); setState("ready"); }
          else if (!silent) { setData(null); setState("empty"); }
        })
        .catch(() => { if (alive && !silent) { setData(null); setState("error"); } });
    };
    load(false);
    const iv = INTRADAY.has(prefs.tf) ? setInterval(() => load(true), 60000) : null;
    return () => { alive = false; if (iv) clearInterval(iv); };
  }, [assetClass, secid, prefs.tf]);

  /* -- закрытие дропдауна по клику мимо -- */
  useEffect(() => {
    if (!ddOpen) return;
    const onDoc = (e) => { if (ddRef.current && !ddRef.current.contains(e.target)) setDdOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [ddOpen]);

  /* -- создание/пересборка графика -- */
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || state !== "ready" || !data) return;

    const colors = readColors(el);
    const rsiOn = prefs.rsi;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: height + (rsiOn ? 120 : 0),
      layout: {
        background: { color: "transparent" },
        textColor: colors.text,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 11,
        panes: { separatorColor: colors.border, enableResize: false },
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: {
        borderColor: colors.border,
        timeVisible: INTRADAY.has(prefs.tf),
        secondsVisible: false,
      },
      crosshair: { mode: 0 },
      localization: { locale: "ru-RU" },
    });

    const candles = data.candles;
    let main;
    if (prefs.kind === "candles") {
      main = chart.addSeries(CandlestickSeries, {
        upColor: colors.up, downColor: colors.down,
        wickUpColor: colors.up, wickDownColor: colors.down,
        borderVisible: false,
      });
      main.setData(candles.map((c) => ({ time: c.t, open: c.o, high: c.h, low: c.l, close: c.c })));
    } else {
      main = chart.addSeries(LineSeries, { color: colors.accent, lineWidth: 2 });
      main.setData(candles.map((c) => ({ time: c.t, value: c.c })));
    }

    // -- скользящие средние --
    const addLine = (points, color, width = 1) => {
      const s = chart.addSeries(LineSeries, {
        color, lineWidth: width, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(points);
      return s;
    };
    prefs.emas.forEach((p) => {
      if (candles.length >= p) addLine(ema(candles, p), _cssColor(el, MA_TOKEN_BY_PERIOD[p] || "--cc-violet", "#6D28D9"));
    });
    prefs.customs.forEach((cst, i) => {
      if (candles.length >= cst.period) {
        const pts = cst.type === "ema" ? ema(candles, cst.period) : sma(candles, cst.period);
        addLine(pts, _cssColor(el, CUSTOM_TOKENS[i % CUSTOM_TOKENS.length], "#0A5E8A"));
      }
    });

    // -- полосы Боллинджера --
    if (prefs.bollinger && candles.length >= 20) {
      const bb = bollinger(candles);
      addLine(bb.mid, colors.ink3);
      const bandOpts = { lineStyle: 2 }; // dashed
      const u = chart.addSeries(LineSeries, {
        color: colors.ink3, lineWidth: 1, priceLineVisible: false,
        lastValueVisible: false, crosshairMarkerVisible: false, ...bandOpts,
      });
      u.setData(bb.up);
      const l = chart.addSeries(LineSeries, {
        color: colors.ink3, lineWidth: 1, priceLineVisible: false,
        lastValueVisible: false, crosshairMarkerVisible: false, ...bandOpts,
      });
      l.setData(bb.low);
    }

    // -- RSI отдельной панелью --
    if (rsiOn && candles.length > 15) {
      const s = chart.addSeries(LineSeries, {
        color: colors.accent, lineWidth: 1.5,
        priceLineVisible: false, lastValueVisible: true,
      }, 1);
      s.setData(rsi(candles));
      [30, 70].forEach((lvl) => s.createPriceLine({
        price: lvl, color: colors.ink3, lineWidth: 1, lineStyle: 3,
        axisLabelVisible: false,
      }));
      const panes = chart.panes();
      if (panes[1]) panes[1].setHeight(110);
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (el.clientWidth) chart.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    // Смена темы: App перерисовывает всё дерево при переключении, но график —
    // императивный: следим за data-theme на <html> и пересоздаём палитру.
    const mo = new MutationObserver(() => {
      const c2 = readColors(el);
      chart.applyOptions({
        layout: { background: { color: "transparent" }, textColor: c2.text },
        grid: { vertLines: { color: c2.grid }, horzLines: { color: c2.grid } },
        rightPriceScale: { borderColor: c2.border },
        timeScale: { borderColor: c2.border },
      });
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class"] });

    chartRef.current = { chart };
    return () => { ro.disconnect(); mo.disconnect(); chart.remove(); chartRef.current = null; };
  }, [state, data, prefs, height]);

  /* -- тулбар -- */

  const toggleEma = (p) => setPref({
    emas: prefs.emas.includes(p) ? prefs.emas.filter((x) => x !== p) : [...prefs.emas, p].sort((a, b) => a - b),
  });

  const addCustom = () => {
    const per = parseInt(customPeriod, 10);
    if (!per || per < 2 || per > 500) return;
    if (prefs.customs.some((c) => c.period === per && c.type === customType)) return;
    setPref({ customs: [...prefs.customs, { type: customType, period: per }].slice(0, 5) });
    setCustomPeriod("");
  };

  const indicatorsOn = prefs.emas.length + prefs.customs.length + (prefs.bollinger ? 1 : 0) + (prefs.rsi ? 1 : 0);

  const changeCls = data && data.change_pct != null
    ? (data.change_pct > 0 ? "cpro-delta--up" : data.change_pct < 0 ? "cpro-delta--down" : "")
    : "";

  return (
    <div className={`cpro ${className}`}>
      <div className="cpro-bar">
        <div className="cpro-tfs" role="tablist" aria-label="Таймфрейм">
          {TFS.map(([tf, label]) => (
            <button
              key={tf} type="button" role="tab" aria-selected={prefs.tf === tf}
              className={`cpro-tf${prefs.tf === tf ? " cpro-tf--on" : ""}`}
              onClick={() => setPref({ tf })}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="cpro-bar-right">
          {data && data.last != null && (
            <span className="cpro-last">
              {data.last.toLocaleString("ru-RU")}
              {data.change_pct != null && (
                <span className={`cpro-delta ${changeCls}`}>
                  {data.change_pct > 0 ? "▲" : data.change_pct < 0 ? "▼" : ""}
                  {Math.abs(data.change_pct).toLocaleString("ru-RU")}%
                </span>
              )}
            </span>
          )}

          <div className="cpro-kind" role="tablist" aria-label="Вид графика">
            <button
              type="button" role="tab" aria-selected={prefs.kind === "candles"}
              className={`cpro-kbtn${prefs.kind === "candles" ? " cpro-kbtn--on" : ""}`}
              onClick={() => setPref({ kind: "candles" })}
              title="Японские свечи"
            >
              Свечи
            </button>
            <button
              type="button" role="tab" aria-selected={prefs.kind === "line"}
              className={`cpro-kbtn${prefs.kind === "line" ? " cpro-kbtn--on" : ""}`}
              onClick={() => setPref({ kind: "line" })}
              title="Линия по закрытиям"
            >
              Линия
            </button>
          </div>

          <div className="cpro-dd" ref={ddRef}>
            <button
              type="button" aria-expanded={ddOpen}
              className={`cpro-ddbtn${indicatorsOn ? " cpro-ddbtn--active" : ""}`}
              onClick={() => setDdOpen((v) => !v)}
            >
              Индикаторы{indicatorsOn ? ` · ${indicatorsOn}` : ""} ▾
            </button>
            {ddOpen && (
              <div className="cpro-panel">
                <div className="cpro-panel-sec">Скользящие средние (EMA)</div>
                <div className="cpro-panel-emas">
                  {EMA_PRESETS.map((p) => (
                    <label key={p} className="cpro-check">
                      <input type="checkbox" checked={prefs.emas.includes(p)} onChange={() => toggleEma(p)} />
                      <span>EMA {p}</span>
                    </label>
                  ))}
                </div>
                <div className="cpro-panel-sec">Своя средняя</div>
                <div className="cpro-custom-add">
                  <select value={customType} onChange={(e) => setCustomType(e.target.value)} aria-label="Тип средней">
                    <option value="ema">EMA</option>
                    <option value="sma">MA</option>
                  </select>
                  <input
                    type="number" min="2" max="500" placeholder="период"
                    value={customPeriod}
                    onChange={(e) => setCustomPeriod(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") addCustom(); }}
                    aria-label="Период средней"
                  />
                  <button type="button" onClick={addCustom}>Добавить</button>
                </div>
                {prefs.customs.length > 0 && (
                  <div className="cpro-custom-list">
                    {prefs.customs.map((c, i) => (
                      <span key={`${c.type}${c.period}`} className="cpro-custom-chip">
                        {c.type === "ema" ? "EMA" : "MA"} {c.period}
                        <button
                          type="button" aria-label="Убрать"
                          onClick={() => setPref({ customs: prefs.customs.filter((_, j) => j !== i) })}
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <div className="cpro-panel-sec">Наложения и осцилляторы</div>
                <label className="cpro-check">
                  <input type="checkbox" checked={prefs.bollinger} onChange={() => setPref({ bollinger: !prefs.bollinger })} />
                  <span>Полосы Боллинджера (20, 2σ)</span>
                </label>
                <label className="cpro-check">
                  <input type="checkbox" checked={prefs.rsi} onChange={() => setPref({ rsi: !prefs.rsi })} />
                  <span>RSI (14)</span>
                </label>
                {indicatorsOn > 0 && (
                  <button
                    type="button" className="cpro-clear"
                    onClick={() => setPref({ emas: [], customs: [], bollinger: false, rsi: false })}
                  >
                    Сбросить все
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {state === "loading" && <div className="cpro-msg" style={{ height }}>Загружаем график…</div>}
      {state === "empty" && <div className="cpro-msg" style={{ height }}>Нет данных за этот период</div>}
      {state === "error" && <div className="cpro-msg" style={{ height }}>Не удалось загрузить график</div>}
      <div
        ref={wrapRef}
        className="cpro-canvas"
        style={{ display: state === "ready" ? "block" : "none" }}
      />
    </div>
  );
}
