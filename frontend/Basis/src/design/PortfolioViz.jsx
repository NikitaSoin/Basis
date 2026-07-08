// =============================================================
// BASIS — Portfolio data-viz sub-components (Phase 3, Portfolio page)
// Reusable widgets that carry the approved "live language": colour IN
// the data (cat-1..8 for categories, success/danger for value), dosed
// depth, and short motion. All effects gated by usePrefersReducedMotion.
// Pure JS, no new npm packages: CSS transitions + SVG + rAF count-up.
// Token-only colours — no hard-coded hex.
// =============================================================
import React, { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./primitives";
import { formatNumber, formatPercent } from "./format";

const cx = (...p) => p.filter(Boolean).join(" ");

/* ---------- count-up via requestAnimationFrame ---------- */
// 0 → value over ~700ms on FIRST run only. reduced-motion → final value.
// `gate` (optional): a caller-owned mutable object `{ played: bool }`. When
// supplied, the count-up plays only the FIRST time across the gate's lifetime —
// even if THIS component remounts (e.g. a tab panel is closed and reopened).
// Keep the gate in a ref that outlives remounts (e.g. at the PAGE level) so the
// number animates once per page visit and snaps on every tab/click/refresh.
export function useCountUp(value, duration = 320, gate = null) {
  const reduced = usePrefersReducedMotion();
  const alreadyPlayed = reduced || (gate ? gate.played : false);
  const [n, setN] = useState(alreadyPlayed ? value : 0);
  const started = useRef(false);
  useEffect(() => {
    if (reduced) {
      setN(value);
      return;
    }
    // run once; afterwards snap to the latest value so a tab switch / click /
    // background refresh updates the number without replaying the count.
    const done = gate ? gate.played : started.current;
    if (done) {
      setN(value);
      return;
    }
    if (gate) gate.played = true;
    started.current = true;
    let raf;
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration);
      const eased = 1 - Math.pow(1 - p, 3); // easeOutCubic, no overshoot
      setN(value * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration, reduced]);
  return n;
}

/* ---------- sector → cat-token mapping (stable, colourblind-safe) ---------- */
const SECTOR_CAT = {
  Финансы: 5,
  Нефтегаз: 1,
  "Нефть и газ": 1,
  Металлы: 3,
  Металлургия: 3,
  IT: 7,
  Технологии: 7,
  Телеком: 2,
  Энергетика: 6,
  Потребительский: 4,
  Девелопмент: 8,
  Химия: 6,
};
// Deterministic fallback so unknown sectors/tickers still get a stable cat.
export function catFor(key) {
  if (key && SECTOR_CAT[key]) return SECTOR_CAT[key];
  const s = String(key || "");
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return (h % 8) + 1;
}

/* ---------- SectorChip — soft cat bg + saturated cat text ---------- */
export function SectorChip({ label, n }) {
  const cat = n || catFor(label);
  return (
    <span
      className="tw-inline-flex tw-items-center tw-gap-1.5 tw-rounded-pill tw-px-2.5 tw-py-1 tw-text-[12px] tw-font-medium"
      style={{ background: `var(--cat-${cat}-soft)`, color: `var(--cat-${cat})` }}
    >
      <span aria-hidden="true" className="tw-w-2 tw-h-2 tw-rounded-pill" style={{ background: `var(--cat-${cat})` }} />
      {label}
    </span>
  );
}

/* ---------- TickerBadge — small mono monogram tile in a cat colour ---------- */
export function TickerBadge({ ticker, n }) {
  const cat = n || catFor(ticker);
  return (
    <span
      className="tw-flex tw-items-center tw-justify-center tw-shrink-0 tw-rounded-md tw-font-mono tw-font-bold tw-tabular-nums"
      style={{
        width: 32,
        height: 32,
        fontSize: 10,
        letterSpacing: "-0.03em",
        background: `var(--cat-${cat}-soft)`,
        color: `var(--cat-${cat})`,
        border: `1px solid var(--cat-${cat}-soft)`,
      }}
      aria-hidden="true"
    >
      {String(ticker || "").slice(0, 4)}
    </span>
  );
}

/* ---------- WeightBar — share-of-portfolio mini bar (cat colour) ---------- */
export function WeightBar({ pct, n = 5 }) {
  const reduced = usePrefersReducedMotion();
  const [w, setW] = useState(reduced ? pct : 0);
  useEffect(() => {
    if (reduced) { setW(pct); return; }
    const r = requestAnimationFrame(() => setW(pct));
    return () => cancelAnimationFrame(r);
  }, [pct, reduced]);
  return (
    <div className="tw-h-1.5 tw-w-10 tw-rounded-pill tw-bg-bg-hover tw-overflow-hidden">
      <div
        className="tw-h-full tw-rounded-pill"
        style={{
          width: `${Math.min(w, 100)}%`,
          background: `var(--cat-${n})`,
          transition: reduced ? undefined : "width 700ms cubic-bezier(0.16,1,0.3,1)",
        }}
      />
    </div>
  );
}

/* ---------- MetricBar — «Здоровье портфеля» style coloured bar ---------- */
// colorVar is a token name e.g. "--cat-3" or "--danger". Bar fills on mount.
export function MetricBar({ label, value, max = 100, colorVar, suffix = `/${100}` }) {
  const reduced = usePrefersReducedMotion();
  const [w, setW] = useState(reduced ? value : 0);
  useEffect(() => {
    if (reduced) { setW(value); return; }
    const r = requestAnimationFrame(() => setW(value));
    return () => cancelAnimationFrame(r);
  }, [value, reduced]);
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const wPct = Math.max(0, Math.min(100, (w / max) * 100));
  return (
    <div className="tw-flex tw-items-center tw-gap-3">
      <span className="tw-text-[13px] tw-text-text-secondary tw-w-32 tw-shrink-0">{label}</span>
      <div className="tw-flex-1 tw-h-1.5 tw-rounded-pill tw-bg-bg-hover tw-overflow-hidden">
        <div
          className="tw-h-full tw-rounded-pill"
          style={{
            width: `${wPct}%`,
            background: `var(${colorVar})`,
            transition: reduced ? undefined : "width 800ms cubic-bezier(0.16,1,0.3,1)",
          }}
        />
      </div>
      <span
        className="tw-text-[13px] tw-font-mono tw-tabular-nums tw-w-12 tw-text-right tw-shrink-0"
        style={{ color: `var(${colorVar})` }}
      >
        {Math.round(pct)}
        <span className="tw-text-text-tertiary">{suffix}</span>
      </span>
    </div>
  );
}

/* ---------- CorrelationHeatmap — token-based, semantic ramp ---------- */
// High correlation (→1) = warm danger-tinted; low/negative = cool success-
// tinted; near-zero = neutral. Diagonal (self, =1) reads as neutral strong.
function corrCell(v, isDiag) {
  // Диагональ (бумага сама с собой) — явно нейтральная, вне шкалы (не данные,
  // тавтология), как в HTML-прототипе (.corr-diag).
  if (isDiag) {
    return { bg: "var(--pf-surface-3)", fg: "var(--pf-ink-3)", diag: true };
  }
  if (v == null || typeof v !== "number") {
    // мало совпадающих торговых дат у пары — корреляция не рассчитана
    return { bg: "var(--bg-elevated)", fg: "var(--text-tertiary)" };
  }
  // Линейная интерполяция neutral→red (v>=0) / neutral→green (v<0), буквально
  // как corrColor() в HTML-прототипе (red=184,80,63 / green=62,132,100 /
  // neutral=239,234,224 ≈ --pf-surface-3), не пороговая ступенчатая шкала.
  const clamp = Math.max(-1, Math.min(1, v));
  const pct = Math.round(Math.abs(clamp) * 100);
  const varName = clamp >= 0 ? "--pf-down" : "--pf-up";
  return {
    bg: `color-mix(in srgb, var(${varName}) ${pct}%, var(--pf-surface-3))`,
    fg: pct > 55 ? "#fff" : "var(--pf-ink)",
  };
}

export function CorrelationHeatmap({ labels = [], matrix = [] }) {
  const reduced = usePrefersReducedMotion();
  const [appeared, setAppeared] = useState(reduced);
  useEffect(() => {
    if (reduced) { setAppeared(true); return; }
    const r = requestAnimationFrame(() => setAppeared(true));
    return () => cancelAnimationFrame(r);
  }, [reduced]);
  const n = labels.length;
  return (
    <div className="tw-flex tw-justify-center tw-overflow-x-auto">
      <div
        className="tw-inline-grid"
        style={{ gridTemplateColumns: `auto repeat(${n}, minmax(56px, 1fr))` }}
      >
        {/* corner */}
        <div />
        {labels.map((l) => (
          <div key={`col-${l}`} className="tw-px-2 tw-py-1.5 tw-text-center tw-text-[12px] tw-font-mono tw-text-text-tertiary">
            {l}
          </div>
        ))}
        {labels.map((rowLabel, i) => (
          <React.Fragment key={`row-${rowLabel}`}>
            <div className="tw-px-2 tw-py-2 tw-flex tw-items-center tw-justify-end tw-text-[12px] tw-font-mono tw-text-text-tertiary">
              {rowLabel}
            </div>
            {(matrix[i] || []).map((v, j) => {
              const { bg, fg, diag } = corrCell(v, i === j);
              return (
                <div
                  key={`${i}-${j}`}
                  className="tw-flex tw-items-center tw-justify-center tw-text-[12px] tw-font-mono tw-tabular-nums tw-py-3"
                  style={{
                    background: bg,
                    border: diag ? "1px dashed var(--pf-line-2)" : "none",
                    borderRadius: 0,
                    color: fg,
                    fontWeight: diag ? 400 : 600,
                    opacity: reduced || appeared ? 1 : 0,
                    transition: reduced ? undefined : `opacity 280ms ease ${(i * n + j) * 22}ms`,
                  }}
                  title={diag ? `${rowLabel} · ${rowLabel}: бумага сама с собой (не данные)` : v == null ? `${rowLabel} · ${labels[j]}: мало совпадающих дат` : `${rowLabel} · ${labels[j]}: ${formatNumber(v, { decimals: 2 })}`}
                >
                  {v == null ? "—" : formatNumber(v, { decimals: 2 })}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

/* ---------- Treemap — cells sized by weight, coloured by P&L sign ---------- */
// cells: [{ label, weight (0..1), pct (signed %) }]. Greedy row layout into a
// fixed 6-col grid; cell colour ramps green↔red by daily/total % (PortfolioPilot
// style). Pure layout maths, token colours, dosed appear-stagger.
export function Treemap({ cells = [] }) {
  const reduced = usePrefersReducedMotion();
  const [appeared, setAppeared] = useState(reduced);
  useEffect(() => {
    if (reduced) { setAppeared(true); return; }
    const r = requestAnimationFrame(() => setAppeared(true));
    return () => cancelAnimationFrame(r);
  }, [reduced]);
  // assign column spans (1..3) from weight; rows always span 1, taller cells
  // for the heaviest holdings.
  const total = cells.reduce((a, c) => a + (c.weight || 0), 0) || 1;
  const laid = cells.map((c) => {
    const share = (c.weight || 0) / total;
    const cols = share > 0.33 ? 3 : share > 0.16 ? 2 : 1;
    const rows = share > 0.25 ? 2 : 1;
    return { ...c, cols, rows };
  });
  return (
    <div className="tw-grid tw-gap-1" style={{ gridTemplateColumns: "repeat(6, 1fr)", gridAutoRows: "44px" }}>
      {laid.map((c, i) => {
        const pct = c.pct || 0;
        const mag = Math.min(1, Math.abs(pct) / 3);
        const colorVar = pct >= 0 ? "--success" : "--danger";
        return (
          <div
            key={c.label}
            className="tw-relative tw-flex tw-flex-col tw-justify-between tw-rounded-sm tw-p-1.5 tw-overflow-hidden"
            style={{
              gridColumn: `span ${c.cols}`,
              gridRow: `span ${c.rows}`,
              background: `color-mix(in srgb, var(${colorVar}) ${Math.round(mag * 65 + 8)}%, var(--bg-elevated))`,
              border: "1px solid var(--border-subtle)",
              opacity: reduced || appeared ? 1 : 0,
              transform: reduced || appeared ? "none" : "scale(0.96)",
              transition: reduced ? undefined : `opacity 360ms ease ${i * 35}ms, transform 360ms ease ${i * 35}ms`,
            }}
          >
            <span className="tw-text-[11px] tw-font-medium tw-leading-tight tw-text-text-primary">{c.label}</span>
            <span className="tw-text-[11px] tw-font-mono tw-tabular-nums tw-text-text-primary">
              {pct >= 0 ? "▲" : "▼"} {formatPercent(Math.abs(pct), { decimals: 1 })}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/* ---------- ImpactBar — signed stress-impact bar (centre origin) ---------- */
// value is a signed % (negative = loss). Bar grows left of centre for loss,
// right for gain. danger/success semantics with ▲/▼ in the caller.
export function ImpactBar({ value, max = 25 }) {
  const reduced = usePrefersReducedMotion();
  const [w, setW] = useState(reduced ? Math.abs(value) : 0);
  useEffect(() => {
    if (reduced) { setW(Math.abs(value)); return; }
    const r = requestAnimationFrame(() => setW(Math.abs(value)));
    return () => cancelAnimationFrame(r);
  }, [value, reduced]);
  const neg = value < 0;
  const pct = Math.min(100, (w / max) * 100);
  return (
    <div className="tw-relative tw-h-2 tw-rounded-pill tw-bg-bg-hover tw-overflow-hidden">
      {/* centre tick */}
      <span aria-hidden="true" className="tw-absolute tw-left-1/2 tw-top-0 tw-bottom-0 tw-w-px tw-bg-border-strong" />
      <div
        className={cx("tw-absolute tw-top-0 tw-bottom-0", neg ? "tw-right-1/2" : "tw-left-1/2")}
        style={{
          width: `${pct / 2}%`,
          background: neg ? "var(--pf-down)" : "var(--pf-up)",
          transition: reduced ? undefined : "width 800ms cubic-bezier(0.16,1,0.3,1)",
          borderRadius: 9999,
        }}
      />
    </div>
  );
}

export { cx as _vizCx };
