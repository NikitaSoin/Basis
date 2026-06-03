// =============================================================
// BASIS LOGOMARK CONCEPTS — gallery-only (route /_design).
// Four candidate brand marks for «Basis», an independent
// investment-analytics platform. Values: trust, logic, base/
// foundation, reducing uncertainty, second opinion.
//
// Pure inline SVG, coloured ONLY via design tokens (cobalt
// --accent + neutrals, --accent-2 used sparingly). No raster.
// Each mark takes a `size` prop and uses a fixed viewBox so it
// scales crisply from 16px (favicon) up to 64px (hero).
//
// This file defines the marks + a showcase body. It is rendered
// inside DesignSystem.jsx ONLY — real Sidebar / index.html /
// App.js are NOT touched. The owner picks a direction here.
// =============================================================
import React from "react";

const cx = (...parts) => parts.filter(Boolean).join(" ");

/* =============================================================
   CONCEPT 1 — «Монограмма B / слои-фундамент»
   The letter B built from stacked horizontal bands sitting on a
   base line: reads as a B at large size, as a solid layered block
   at favicon size. Idea: a brand built on layers of analysis,
   resting on a firm foundation.
   ============================================================= */
export function MarkMonogram({ size = 32, title = "Basis — монограмма B" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* rounded square plate (soft accent wash) */}
      <rect x="1" y="1" width="30" height="30" rx="7" fill="var(--accent-soft)" />
      {/* B spine */}
      <rect x="8.5" y="7" width="3.2" height="18" rx="1.2" fill="var(--accent)" />
      {/* upper bowl */}
      <path
        d="M11.7 7h6.4c2.7 0 4.6 1.7 4.6 4.2 0 2.5-1.9 4.1-4.6 4.1h-6.4V7z"
        fill="var(--accent)"
      />
      {/* lower bowl (slightly wider — the "foundation") */}
      <path
        d="M11.7 15.3h7.1c2.9 0 4.9 1.8 4.9 4.4 0 2.6-2 4.3-4.9 4.3h-7.1v-8.7z"
        fill="var(--accent)"
      />
      {/* knockout slits = the layer separation, drawn in plate colour */}
      <rect x="13.4" y="9.4" width="6.2" height="2.4" rx="1.2" fill="var(--bg-elevated)" />
      <rect x="13.4" y="17.7" width="6.8" height="2.6" rx="1.3" fill="var(--bg-elevated)" />
      {/* base line under the mark — the "basis" */}
      <rect x="7" y="26.4" width="18" height="2" rx="1" fill="var(--accent)" opacity="0.55" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 2 — «Опора / базис: рост на прочной основе»
   A thick grounded base bar; from it rises a stepped column
   (a small chart / growth) anchored on the base. Idea: growth
   that stands on a solid foundation — disciplined, not hype.
   ============================================================= */
export function MarkFoundation({ size = 32, title = "Basis — опора и рост" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* rising steps standing on the base */}
      <rect x="8" y="16" width="4" height="8" rx="1.2" fill="var(--accent)" opacity="0.55" />
      <rect x="14" y="11" width="4" height="13" rx="1.2" fill="var(--accent)" opacity="0.78" />
      <rect x="20" y="6" width="4" height="18" rx="1.2" fill="var(--accent)" />
      {/* the foundation — one strong horizontal that everything rests on */}
      <rect x="4" y="24.5" width="24" height="3.6" rx="1.8" fill="var(--accent)" />
      {/* tiny pier marks under the base = piles into bedrock */}
      <rect x="7" y="28.4" width="2.4" height="2.4" rx="0.8" fill="var(--accent)" opacity="0.45" />
      <rect x="22.6" y="28.4" width="2.4" height="2.4" rx="0.8" fill="var(--accent)" opacity="0.45" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 3 — «Призма / грань: второе мнение»
   A triangular prism with an incoming ray splitting into a small
   fan on exit. Idea: one input seen through analysis becomes a
   spectrum of perspectives — the "second opinion". Accent-2
   (violet) is used sparingly here for ONE refracted ray, the rest
   cobalt — the single dosed marketing touch.
   ============================================================= */
export function MarkPrism({ size = 32, title = "Basis — призма, второе мнение" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* incoming ray */}
      <rect x="2" y="15" width="7" height="2" rx="1" fill="var(--accent)" opacity="0.6" />
      {/* prism body */}
      <path
        d="M11 24L18 7l7 17H11z"
        fill="var(--accent-soft)"
        stroke="var(--accent)"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      {/* refracted fan on exit — three diverging rays (one violet) */}
      <path d="M22.5 18.5l7.5-3" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
      <path d="M23 21l7 0.5" stroke="var(--accent-2)" strokeWidth="2" strokeLinecap="round" />
      <path d="M22.5 23.5l7 4" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" opacity="0.55" />
    </svg>
  );
}

/* =============================================================
   CONCEPT 4 — «Оси данных / координата»
   Minimal mark from an L-shaped axis (the base + the upright)
   with a plotted point and a short trend tick. Idea: clear,
   honest data on coordinates — analytics distilled to a glyph.
   Extremely legible at 16px because it is just 3 strokes + a dot.
   ============================================================= */
export function MarkAxes({ size = 32, title = "Basis — оси данных" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      fill="none"
    >
      {/* L axis — vertical + horizontal base */}
      <path
        d="M8 5v19h19"
        stroke="var(--accent)"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* trend line rising to the plotted point */}
      <path
        d="M11 20l5-5 4 2 5-8"
        stroke="var(--accent)"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.45"
      />
      {/* the plotted point — the conclusion / second opinion */}
      <circle cx="25" cy="9" r="3.2" fill="var(--accent)" />
      <circle cx="25" cy="9" r="3.2" fill="none" stroke="var(--bg-elevated)" strokeWidth="1.4" />
    </svg>
  );
}

/* ---- registry of concepts ---- */
export const LOGOMARKS = [
  {
    key: "monogram",
    Mark: MarkMonogram,
    name: "Монограмма B · слои-фундамент",
    idea: "Буква B собрана из горизонтальных слоёв на опорной линии. Бренд, выстроенный на слоях анализа, стоящих на прочном основании.",
  },
  {
    key: "foundation",
    Mark: MarkFoundation,
    name: "Опора · рост на прочной базе",
    idea: "Толстая горизонталь-основание, из неё растут ступени-столбики. Дисциплинированный рост, стоящий на твёрдом базисе, а не на хайпе.",
  },
  {
    key: "prism",
    Mark: MarkPrism,
    name: "Призма · второе мнение",
    idea: "Луч входит в грань и расходится веером перспектив. Один вход через анализ → спектр взглядов. Один луч — акцент-2 (дозированно).",
  },
  {
    key: "axes",
    Mark: MarkAxes,
    name: "Оси данных · координата",
    idea: "L-ось (основание + вертикаль) с трендом и нанесённой точкой. Честные данные на координатах — аналитика, сжатая до глифа.",
  },
];

/* =============================================================
   WORDMARK LOCKUP — mark + the word «Basis» beside it.
   Uses the display font + cobalt; gallery preview only.
   ============================================================= */
function Lockup({ Mark }) {
  return (
    <div className="tw-inline-flex tw-items-center tw-gap-2.5">
      <Mark size={28} />
      <span
        className="tw-text-text-primary"
        style={{
          fontFamily: "var(--font-display)",
          fontWeight: 600,
          fontSize: "22px",
          letterSpacing: "-0.01em",
          lineHeight: 1,
        }}
      >
        Basis
      </span>
    </div>
  );
}

/* small labelled swatch for one rendered size */
function SizeSwatch({ Mark, px, note }) {
  return (
    <div className="tw-flex tw-flex-col tw-items-center tw-gap-1.5">
      <div
        className="tw-flex tw-items-center tw-justify-center tw-rounded-md tw-border tw-border-border-subtle tw-bg-bg-base"
        style={{ width: "72px", height: "72px" }}
      >
        <Mark size={px} />
      </div>
      <span className="tw-text-[11px] tw-text-text-tertiary tw-leading-none">{note}</span>
    </div>
  );
}

function ConceptCard({ concept }) {
  const { Mark, name, idea } = concept;
  return (
    <div className="tw-bg-bg-elevated tw-border tw-border-border-strong tw-rounded-lg tw-shadow-sm dark:tw-shadow-none tw-p-5 tw-flex tw-flex-col tw-gap-4">
      {/* header: name + hero-size mark */}
      <div className="tw-flex tw-items-center tw-justify-between tw-gap-3">
        <div>
          <div className="tw-text-[14px] tw-font-semibold tw-text-text-primary">{name}</div>
          <p className="tw-text-[12px] tw-text-text-secondary tw-mt-1 tw-mb-0 tw-max-w-[44ch]">{idea}</p>
        </div>
        {/* hero — ~64px */}
        <div className="tw-shrink-0">
          <Mark size={64} />
        </div>
      </div>

      {/* size ramp incl. favicon sizes */}
      <div className="tw-flex tw-flex-wrap tw-items-end tw-gap-4 tw-pt-1">
        <SizeSwatch Mark={Mark} px={32} note="32 · сайдбар" />
        <SizeSwatch Mark={Mark} px={24} note="24 · сайдбар" />
        <SizeSwatch Mark={Mark} px={32} note="32 · фавикон" />
        <SizeSwatch Mark={Mark} px={16} note="16 · фавикон" />
      </div>

      {/* favicon legibility strip — marks on the actual tiny scale, inline */}
      <div className="tw-flex tw-items-center tw-gap-3 tw-rounded-md tw-bg-bg-base tw-border tw-border-border-subtle tw-px-3 tw-py-2">
        <span className="tw-text-[11px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          16px в ряд
        </span>
        <Mark size={16} />
        <Mark size={16} />
        <Mark size={16} />
        <span className="tw-text-[11px] tw-text-text-tertiary">— читается в мелком</span>
      </div>

      {/* wordmark lockup */}
      <div className="tw-flex tw-items-center tw-gap-3 tw-pt-1">
        <span className="tw-text-[11px] tw-uppercase tw-text-text-tertiary" style={{ letterSpacing: "0.05em" }}>
          Лого + слово
        </span>
        <Lockup Mark={Mark} />
      </div>
    </div>
  );
}

/* ---- the showcase body (rendered once per theme by the gallery) ---- */
export function LogomarkBody() {
  return (
    <div className="tw-grid tw-grid-cols-1 lg:tw-grid-cols-2 tw-gap-5">
      {LOGOMARKS.map((c) => (
        <ConceptCard key={c.key} concept={c} />
      ))}
    </div>
  );
}
