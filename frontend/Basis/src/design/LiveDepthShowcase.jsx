// =============================================================
// BASIS — «Живость и глубина» showcase (route /_design, gallery section)
// Demonstrates the DOSED balance: a restrained monochrome shell with a
// few precise points of colour / depth / motion — IN THE DATA, not the
// chrome. Buttons stay one cobalt accent; gain/loss stay success/danger;
// the Okabe-Ito categorical palette (--cat-1..8) lives only inside data
// widgets (chart series, sector chips, treemap).
//
// Pure JS. No new npm packages: motion is CSS transition + SVG
// stroke-dashoffset + a small requestAnimationFrame count-up. Every
// effect is gated by usePrefersReducedMotion (count-up jumps to final,
// draw appears instantly, decor stops, hover-lift disabled).
// =============================================================
import React, { useEffect, useId, useRef, useState } from "react";
import { usePrefersReducedMotion, Badge } from "./primitives";
import { formatNumber, formatPercent } from "./format";

const cx = (...p) => p.filter(Boolean).join(" ");

/* ---------- in-view trigger (replays motion on each entry) ---------- */
// Fires `true` while the node is on screen; used to (re)start count-up
// and stroke-draw so the owner can scroll back and watch them again.
function useInView(threshold = 0.35) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const obs = new IntersectionObserver(
      ([e]) => setInView(e.isIntersecting),
      { threshold }
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [threshold]);
  return [ref, inView];
}

/* ---------- count-up via requestAnimationFrame ---------- */
// Animates 0 → value over ~700ms. reduced-motion or !active → final value.
function useCountUp(value, active, reduced, duration = 700) {
  const [n, setN] = useState(reduced ? value : 0);
  useEffect(() => {
    if (reduced || !active) {
      setN(value);
      return;
    }
    let raf;
    const start = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration);
      // easeOutCubic — settles, never overshoots (no celebratory bounce)
      const eased = 1 - Math.pow(1 - p, 3);
      setN(value * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, active, reduced, duration]);
  return n;
}

/* ---------- gallery chrome (local) ---------- */
function SubHead({ n, title, hint }) {
  return (
    <div className="tw-mb-4">
      <h3 className="tw-text-[18px] tw-font-semibold tw-text-text-primary tw-m-0">
        {n} · {title}
      </h3>
      {hint && <p className="tw-text-[13px] tw-text-text-tertiary tw-m-0 tw-mt-1">{hint}</p>}
    </div>
  );
}

function Note({ children }) {
  return (
    <p
      className="tw-text-[12px] tw-text-text-tertiary tw-mt-2"
      style={{ letterSpacing: "0.01em" }}
    >
      {children}
    </p>
  );
}

/* =============================================================
   1 · DEPTH — flat-vs-layered comparison
   ============================================================= */

function FlatTile({ caption, value }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-1 tw-bg-bg-elevated tw-border tw-border-border-subtle tw-rounded-md tw-p-4">
      <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.06em" }}>
        {caption}
      </div>
      <span className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums" style={{ fontSize: "30px", lineHeight: 1 }}>
        {value}
      </span>
    </div>
  );
}

// Depth tile: soft shadow + a faint inner top highlight (1px inset) so the
// surface reads as a raised slab, not a sticker. Dark theme: per the
// constitution we drop drop-shadow and rely on layer + 1px border.
function DepthTile({ caption, value, lift }) {
  return (
    <div
      className={cx(
        "tw-relative tw-flex tw-flex-col tw-gap-1 tw-rounded-md tw-p-4",
        "tw-bg-bg-elevated tw-border tw-border-border-strong",
        "tw-shadow-md dark:tw-shadow-none",
        "tw-transition-transform tw-transition-shadow tw-duration-200",
        lift && "hover:tw-shadow-lg hover:-tw-translate-y-0.5"
      )}
      style={{ willChange: "transform" }}
    >
      {/* inner highlight — a hairline of light along the top edge */}
      <span
        aria-hidden="true"
        className="tw-pointer-events-none tw-absolute tw-inset-x-0 tw-top-0 tw-h-px tw-rounded-t-md"
        style={{ background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent)" }}
      />
      <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.06em" }}>
        {caption}
      </div>
      <span className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums" style={{ fontSize: "30px", lineHeight: 1 }}>
        {value}
      </span>
    </div>
  );
}

function DepthSection({ reduced }) {
  const tiles = [
    { caption: "Выручка", value: "1 388" },
    { caption: "EBITDA", value: "421" },
    { caption: "Чистая прибыль", value: "166" },
  ];
  return (
    <div>
      <SubHead
        n="1"
        title="Глубина"
        hint="Слева — плоско (без тени, тонкая граница). Справа — те же плитки на токенах теней + слой и внутренний хайлайт."
      />
      <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-6">
        <div>
          <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.06em" }}>
            Было · плоско
          </div>
          <div className="tw-grid tw-grid-cols-3 tw-gap-3">
            {tiles.map((t) => (
              <FlatTile key={t.caption} {...t} />
            ))}
          </div>
        </div>
        <div>
          <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary tw-mb-2" style={{ letterSpacing: "0.06em" }}>
            Стало · глубина (hover — подъём)
          </div>
          <div className="tw-grid tw-grid-cols-3 tw-gap-3">
            {tiles.map((t) => (
              <DepthTile key={t.caption} {...t} lift={!reduced} />
            ))}
          </div>
        </div>
      </div>
      <Note>
        Токены: светлая — <code>--shadow-md</code> (карточки) → <code>--shadow-lg</code> (hover);
        тёмная — drop-тень отключена (<code>dark:shadow-none</code>), глубина через слой <code>--bg-elevated</code> + 1px <code>--border-strong</code>.
      </Note>
    </div>
  );
}

/* =============================================================
   2 · COLOUR IN DATA — area chart, gradient sparklines, metric
   bars, sector chips, treemap.
   ============================================================= */

// Build a smooth-ish polyline path from y-values (0..1 normalised).
function buildPath(values, w, h, pad = 4) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const step = w / (values.length - 1 || 1);
  const inner = h - pad * 2;
  return values.map((v, i) => {
    const x = +(i * step).toFixed(2);
    const y = +(pad + inner - ((v - min) / span) * inner).toFixed(2);
    return [x, y];
  });
}

// AREA CHART — single series, line in cat colour, area fades line→transparent
// (Fiscal-style). Stroke draws in on appear via stroke-dashoffset.
function AreaChart({ values, colorVar, w = 520, h = 160, active, reduced }) {
  const uid = useId();
  const pad = 8;
  const coords = buildPath(values, w, h, pad);
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `${coords[0][0]},${h - pad} ${line} ${coords[coords.length - 1][0]},${h - pad}`;
  const fillId = `area-fill-${uid}`;
  const pathRef = useRef(null);
  const [len, setLen] = useState(0);
  useEffect(() => {
    if (pathRef.current) setLen(pathRef.current.getTotalLength());
  }, [values]);
  const draw = !reduced && active;
  const grid = [0.25, 0.5, 0.75];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="tw-block tw-w-full tw-h-auto" role="img" aria-label="График динамики выручки с заливкой площади">
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={`var(${colorVar})`} stopOpacity="0.30" />
          <stop offset="100%" stopColor={`var(${colorVar})`} stopOpacity="0" />
        </linearGradient>
      </defs>
      {grid.map((g) => (
        <line key={g} x1="0" x2={w} y1={pad + (h - pad * 2) * g} y2={pad + (h - pad * 2) * g} stroke="var(--border-subtle)" strokeWidth="1" />
      ))}
      <polygon
        points={area}
        fill={`url(#${fillId})`}
        style={{ opacity: draw ? 1 : reduced ? 1 : 0, transition: reduced ? undefined : "opacity 600ms ease 200ms" }}
      />
      <polyline
        ref={pathRef}
        points={line}
        fill="none"
        stroke={`var(${colorVar})`}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={
          reduced || !len
            ? undefined
            : {
                strokeDasharray: len,
                strokeDashoffset: draw ? 0 : len,
                transition: "stroke-dashoffset 900ms cubic-bezier(0.16,1,0.3,1)",
              }
        }
      />
    </svg>
  );
}

// GRADIENT SPARKLINE — like the one in KpiTile but standalone; colour from
// semantic sign (gain green / loss red), area fades under the line.
function GradSpark({ data, w = 120, h = 40 }) {
  const uid = useId();
  const coords = buildPath(data, w, h, 4);
  const line = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const area = `0,${h} ${line} ${w},${h}`;
  const [lx, ly] = coords[coords.length - 1];
  const up = data[data.length - 1] >= data[0];
  const color = up ? "var(--success)" : "var(--danger)";
  const id = `gs-${uid}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true" className="tw-block">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${id})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lx} cy={ly} r="2.25" fill={color} />
    </svg>
  );
}

// METRIC BAR — «Здоровье портфеля» style. Each metric a meaningful colour:
// Quality cat-3 (green), Yield cat-1 (orange), Diversification cat-5 (blue),
// Risk by value via success/danger semantics. Bar fills width on appear.
function MetricBar({ label, value, colorVar, active, reduced }) {
  return (
    <div className="tw-flex tw-flex-col tw-gap-1">
      <div className="tw-flex tw-items-baseline tw-justify-between">
        <span className="tw-text-[13px] tw-text-text-secondary">{label}</span>
        <span className="tw-text-[13px] tw-font-mono tw-tabular-nums tw-text-text-primary">{value}/100</span>
      </div>
      <div className="tw-h-2 tw-rounded-pill tw-bg-bg-base tw-overflow-hidden tw-border tw-border-border-subtle">
        <div
          className="tw-h-full tw-rounded-pill"
          style={{
            background: `var(${colorVar})`,
            width: reduced || active ? `${value}%` : "0%",
            transition: reduced ? undefined : "width 800ms cubic-bezier(0.16,1,0.3,1)",
          }}
        />
      </div>
    </div>
  );
}

// SECTOR CHIP — soft cat-N background + saturated cat-N text (muted, not loud).
function SectorChip({ label, n }) {
  return (
    <span
      className="tw-inline-flex tw-items-center tw-gap-1.5 tw-rounded-pill tw-px-2.5 tw-py-1 tw-text-[12px] tw-font-medium"
      style={{ background: `var(--cat-${n}-soft)`, color: `var(--cat-${n})` }}
    >
      <span aria-hidden="true" className="tw-w-2 tw-h-2 tw-rounded-pill" style={{ background: `var(--cat-${n})` }} />
      {label}
    </span>
  );
}

// TREEMAP — fixed grid of rectangles sized by weight, coloured by daily %
// (green↔red ramp), PortfolioPilot-style. Pure layout maths, no library.
function Treemap({ cells, reduced, active }) {
  // simple squarified-ish: lay rows greedily to fill a 4-unit-tall grid.
  // Here we hand-place into a 12-col × 8-row grid via flex weights for clarity.
  return (
    <div className="tw-grid tw-gap-1" style={{ gridTemplateColumns: "repeat(6, 1fr)", gridAutoRows: "44px" }}>
      {cells.map((c, i) => {
        const pct = c.pct;
        // colour ramp: strong green at +3, strong red at -3, neutral grey near 0
        const mag = Math.min(1, Math.abs(pct) / 3);
        const colorVar = pct >= 0 ? "--success" : "--danger";
        return (
          <div
            key={c.label}
            className="tw-relative tw-flex tw-flex-col tw-justify-between tw-rounded-sm tw-p-1.5 tw-overflow-hidden"
            style={{
              gridColumn: `span ${c.cols}`,
              gridRow: `span ${c.rows}`,
              background: `color-mix(in srgb, var(${colorVar}) ${Math.round(mag * 70 + 8)}%, var(--bg-elevated))`,
              border: "1px solid var(--border-subtle)",
              opacity: reduced || active ? 1 : 0,
              transform: reduced || active ? "none" : "scale(0.96)",
              transition: reduced ? undefined : `opacity 400ms ease ${i * 35}ms, transform 400ms ease ${i * 35}ms`,
            }}
          >
            <span className="tw-text-[11px] tw-font-medium tw-leading-tight" style={{ color: "var(--text-primary)" }}>
              {c.label}
            </span>
            <span className="tw-text-[11px] tw-font-mono tw-tabular-nums" style={{ color: "var(--text-primary)" }}>
              {pct >= 0 ? "▲" : "▼"} {formatPercent(Math.abs(pct), { decimals: 1 })}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ColourSection({ reduced }) {
  const [ref, inView] = useInView();
  const revenue = [88, 92, 90, 101, 110, 118, 124, 130, 142, 151, 160, 172];
  const treemap = [
    { label: "ЛУКОЙЛ", cols: 3, rows: 2, pct: 1.8 },
    { label: "Сбер", cols: 3, rows: 2, pct: 0.6 },
    { label: "Газпром", cols: 2, rows: 2, pct: -2.4 },
    { label: "Норникель", cols: 2, rows: 1, pct: -0.9 },
    { label: "Яндекс", cols: 2, rows: 1, pct: 2.7 },
    { label: "Татнефть", cols: 2, rows: 1, pct: 1.1 },
    { label: "ВТБ", cols: 2, rows: 1, pct: -1.6 },
    { label: "МТС", cols: 2, rows: 1, pct: 0.3 },
  ];
  return (
    <div ref={ref}>
      <SubHead
        n="2"
        title="Цвет в данных (не в кнопках)"
        hint="Категориальная палитра + семантика живут внутри виджетов. На каждом блоке 2–3 цветовых акцента, оболочка нейтральна."
      />
      <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-6">
        {/* Area chart */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <div className="tw-flex tw-items-center tw-justify-between tw-mb-3">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Выручка, млрд ₽ · 12 кв.</span>
            <SectorChip label="Нефтегаз" n={1} />
          </div>
          <AreaChart values={revenue} colorVar="--cat-1" active={inView} reduced={reduced} />
          <Note>Линия и заливка — <code>--cat-1</code> (оранжевый), как акцентный график Fiscal. Один цвет на виджет.</Note>
        </div>

        {/* Sparklines */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Спарклайны · знак задаёт цвет</span>
          <div className="tw-mt-3 tw-grid tw-grid-cols-2 tw-gap-x-6 tw-gap-y-4">
            {[
              { t: "ЛУКОЙЛ", d: [40, 42, 41, 45, 48, 52, 55], v: 5.4 },
              { t: "Газпром", d: [60, 58, 57, 54, 52, 49, 47], v: -4.1 },
              { t: "Сбер", d: [30, 31, 33, 32, 35, 37, 40], v: 3.2 },
              { t: "ВТБ", d: [22, 21, 22, 20, 19, 18, 17], v: -2.6 },
            ].map((s) => (
              <div key={s.t} className="tw-flex tw-items-center tw-justify-between tw-gap-3">
                <span className="tw-text-[13px] tw-text-text-secondary">{s.t}</span>
                <div className="tw-flex tw-items-center tw-gap-2">
                  <GradSpark data={s.d} />
                  <span className={cx("tw-text-[12px] tw-font-mono tw-tabular-nums", s.v >= 0 ? "tw-text-success" : "tw-text-danger")}>
                    {s.v >= 0 ? "▲" : "▼"} {formatPercent(Math.abs(s.v))}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <Note>Цвет = семантика (<code>--success</code>/<code>--danger</code>), не палитра. Прибыль/убыток всегда с ▲/▼.</Note>
        </div>

        {/* Metric bars — Health */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Здоровье портфеля</span>
          <div className="tw-mt-3 tw-flex tw-flex-col tw-gap-3">
            <MetricBar label="Качество" value={78} colorVar="--cat-3" active={inView} reduced={reduced} />
            <MetricBar label="Доходность" value={64} colorVar="--cat-1" active={inView} reduced={reduced} />
            <MetricBar label="Диверсификация" value={52} colorVar="--cat-5" active={inView} reduced={reduced} />
            <MetricBar label="Риск (ниже — лучше)" value={71} colorVar="--danger" active={inView} reduced={reduced} />
          </div>
          <Note>Каждая полоса — свой осмысленный цвет: качество/доходность/диверс. из палитры, риск — семантикой.</Note>
        </div>

        {/* Sector chips + treemap */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Сектора · бейджи (приглушённо)</span>
          <div className="tw-mt-3 tw-flex tw-flex-wrap tw-gap-2">
            <SectorChip label="Нефтегаз" n={1} />
            <SectorChip label="Финансы" n={5} />
            <SectorChip label="Металлы" n={3} />
            <SectorChip label="IT" n={7} />
            <SectorChip label="Телеком" n={2} />
            <SectorChip label="Энергетика" n={6} />
          </div>
          <div className="tw-mt-4 tw-flex tw-items-center tw-justify-between">
            <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Карта дня · treemap</span>
            <span className="tw-text-[12px] tw-text-text-tertiary">размер = вес, цвет = дин. дня</span>
          </div>
          <div className="tw-mt-2">
            <Treemap cells={treemap} reduced={reduced} active={inView} />
          </div>
          <Note>Бейджи: soft-фон + насыщенный текст из палитры. Treemap: зелёный/красный по %, как PortfolioPilot.</Note>
        </div>
      </div>
    </div>
  );
}

/* =============================================================
   3 · MOTION — count-up, draw-in, hover-lift, sliding tab,
   one slow breathing decor element.
   ============================================================= */

function CountUpKpi({ caption, target, decimals, suffix, active, reduced }) {
  const n = useCountUp(target, active, reduced);
  return (
    <div className="tw-flex tw-flex-col tw-gap-1 tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
      <div className="tw-text-[12px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.06em" }}>
        {caption}
      </div>
      <span className="tw-font-display tw-font-light tw-text-text-primary tw-tabular-nums" style={{ fontSize: "32px", lineHeight: 1 }}>
        {formatNumber(n, { decimals })}
        {suffix && <span className="tw-text-[14px] tw-text-text-tertiary tw-ml-1">{suffix}</span>}
      </span>
    </div>
  );
}

// Sliding-underline tabs — the accent underline translates between tabs.
function SlideTabs() {
  const items = ["Обзор", "Финансы", "Управление"];
  const [active, setActive] = useState(0);
  const reduced = usePrefersReducedMotion();
  const refs = useRef([]);
  const [bar, setBar] = useState({ left: 0, width: 0 });
  useEffect(() => {
    const el = refs.current[active];
    if (el) setBar({ left: el.offsetLeft, width: el.offsetWidth });
  }, [active]);
  return (
    <div className="tw-relative tw-inline-flex tw-gap-1 tw-border-b tw-border-border-subtle">
      {items.map((label, i) => (
        <button
          key={label}
          ref={(el) => (refs.current[i] = el)}
          onClick={() => setActive(i)}
          className={cx(
            "tw-px-4 tw-py-2 tw-text-[14px] tw-font-medium tw-bg-transparent tw-border-0 tw-cursor-pointer",
            "focus-visible:tw-outline-none focus-visible:tw-shadow-focus tw-rounded-sm",
            i === active ? "tw-text-accent" : "tw-text-text-secondary hover:tw-text-text-primary"
          )}
          aria-pressed={i === active}
        >
          {label}
        </button>
      ))}
      <span
        aria-hidden="true"
        className="tw-absolute tw-bottom-0 tw-h-0.5 tw-bg-accent tw-rounded-pill"
        style={{
          left: bar.left,
          width: bar.width,
          transition: reduced ? undefined : "left 220ms cubic-bezier(0.16,1,0.3,1), width 220ms cubic-bezier(0.16,1,0.3,1)",
        }}
      />
    </div>
  );
}

// Slow decorative orbit — Fiscal "planet". Very slow (18s), low opacity,
// purely background. reduced-motion → static ring, no spin.
function OrbitDecor({ reduced }) {
  return (
    <svg
      viewBox="0 0 120 120"
      className="tw-absolute tw-right-4 tw-top-1/2 -tw-translate-y-1/2 tw-pointer-events-none"
      width="120"
      height="120"
      aria-hidden="true"
      style={{ opacity: 0.18 }}
    >
      <g
        style={
          reduced
            ? undefined
            : { transformOrigin: "60px 60px", animation: "basis-orbit 18s linear infinite" }
        }
      >
        <circle cx="60" cy="60" r="46" fill="none" stroke="var(--cat-5)" strokeWidth="1" strokeDasharray="2 6" />
        <circle cx="60" cy="14" r="5" fill="var(--cat-1)" />
        <circle cx="106" cy="60" r="3" fill="var(--cat-7)" />
      </g>
      <circle cx="60" cy="60" r="18" fill="none" stroke="var(--cat-5)" strokeWidth="1.5" />
    </svg>
  );
}

function MotionSection({ reduced }) {
  const [ref, inView] = useInView();
  const [playKey, setPlayKey] = useState(0); // bump to replay count-up/draw
  const active = inView; // count-up/draw run while in view or on replay
  const drawValues = [10, 14, 12, 20, 26, 30, 28, 36, 42];
  return (
    <div ref={ref}>
      <SubHead
        n="3"
        title="Движение (превью Фазы 4)"
        hint="Короткие 150–250 мс (декор — медленный). prefers-reduced-motion отключает count-up, прорисовку, подъём и вращение."
      />
      <div className="tw-mb-4">
        <button
          onClick={() => setPlayKey((k) => k + 1)}
          className="tw-inline-flex tw-items-center tw-gap-2 tw-px-4 tw-py-2 tw-min-h-[40px] tw-rounded-sm tw-text-[14px] tw-font-medium tw-bg-accent tw-text-on-accent tw-border tw-border-transparent hover:tw-bg-accent-hover focus-visible:tw-outline-none focus-visible:tw-shadow-focus active:tw-translate-y-px"
        >
          ↻ Проиграть заново
        </button>
        {reduced && (
          <span className="tw-ml-3 tw-text-[12px] tw-text-text-tertiary">
            Reduced-motion активен — анимации показаны в финальном состоянии.
          </span>
        )}
      </div>

      <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-6">
        {/* count-up KPIs */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Count-up чисел (rAF, 0 → значение)</span>
          <div key={playKey} className="tw-mt-3 tw-grid tw-grid-cols-2 tw-gap-3">
            <CountUpKpi caption="Выручка, млрд ₽" target={1388} decimals={0} active={active} reduced={reduced} />
            <CountUpKpi caption="Див. доходность" target={9.2} decimals={1} suffix="%" active={active} reduced={reduced} />
          </div>
          <Note>requestAnimationFrame, easeOutCubic ~700 мс. Без count-up при фоновом обновлении — только при появлении.</Note>
        </div>

        {/* draw-in line */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Плавная прорисовка графика</span>
          <div key={playKey} className="tw-mt-3">
            <AreaChart values={drawValues} colorVar="--cat-3" w={520} h={120} active={active} reduced={reduced} />
          </div>
          <Note>SVG <code>stroke-dasharray/dashoffset</code> + transition. Никаких пакетов.</Note>
        </div>

        {/* hover lift */}
        <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4">
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Hover-подъём карточки (scale 1.0 → 1.015)</span>
          <div className="tw-mt-3 tw-grid tw-grid-cols-3 tw-gap-3">
            {["A", "B", "C"].map((k) => (
              <div
                key={k}
                className={cx(
                  "tw-h-20 tw-rounded-md tw-bg-bg-base tw-border tw-border-border-strong tw-flex tw-items-center tw-justify-center tw-text-text-secondary tw-text-[13px]",
                  "tw-transition-transform tw-transition-shadow tw-duration-150",
                  !reduced && "hover:tw-shadow-md hover:tw-scale-[1.015]"
                )}
                style={{ willChange: "transform" }}
              >
                Наведи · {k}
              </div>
            ))}
          </div>
          <Note>scale 1.015 + тень, по конституции (не 1.1, без вращения). reduced-motion отключает.</Note>
        </div>

        {/* sliding tab + decor */}
        <div className="tw-relative tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-md tw-shadow-sm dark:tw-shadow-none tw-p-4 tw-overflow-hidden">
          <OrbitDecor reduced={reduced} />
          <span className="tw-text-[13px] tw-font-medium tw-text-text-primary">Slide активного таба + медленный декор</span>
          <div className="tw-mt-3">
            <SlideTabs />
          </div>
          <Note>Подчёркивание плавно переезжает (220 мс). Орбита-«планета» вращается 18 с, opacity 0.18; при reduced-motion — статична.</Note>
        </div>
      </div>
    </div>
  );
}

/* =============================================================
   Public: one full showcase body (rendered once per theme)
   ============================================================= */

export function LiveDepthBody() {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6 tw-py-8 tw-font-sans tw-flex tw-flex-col tw-gap-12">
      <DepthSection reduced={reduced} />
      <ColourSection reduced={reduced} />
      <MotionSection reduced={reduced} />
    </div>
  );
}

/* Preamble shown once above both-theme copies. */
export function LiveDepthPreamble() {
  return (
    <div className="tw-max-w-[1280px] tw-mx-auto tw-px-6">
      <div className="tw-flex tw-items-center tw-gap-2 tw-mb-2">
        <Badge tone="accent">Живость и глубина</Badge>
        <span className="tw-text-[12px] tw-text-text-tertiary">принцип языка Basis</span>
      </div>
      <p className="tw-text-[14px] tw-text-text-secondary tw-max-w-[720px] tw-m-0">
        Сдержанная монохромная оболочка + 2–3 «точки жизни» на экран. Цвет живёт{" "}
        <strong className="tw-text-text-primary">в данных</strong> (графики, сектора, treemap) — не в
        хроме. Кнопки — один кобальт-акцент, прибыль/убыток — зелёный/красный с ▲/▼. Глубина — мягкая,
        движение — короткое и осмысленное, всё уважает reduced-motion.
      </p>
    </div>
  );
}
